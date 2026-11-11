import json

import pytest
from jsonschema import Draft202012Validator

from onmodel import schemas
from onmodel.check import apply_text_rule, check_pair
from onmodel.judge import VlmResult
from onmodel.text_rule import text_recall

from conftest import Scripted, make_checklist

JUDGMENT = Draft202012Validator(schemas.judgment_schema())


def test_a_clean_photo_is_verified_and_the_record_validates(imgs):
    vlm = Scripted(make_checklist())
    rec = check_pair(imgs["product"], imgs["result"], vlm=vlm, pose=imgs["pose"], verb="holding", tags=("text", "hand"))
    assert rec["ok"] and rec["scorecard"]["verified"] and rec["scorecard"]["total"] == 10 and rec["advice"] == []
    assert rec["judge"]["box_2d"] == [100, 100, 900, 900] and rec["judge"]["crop"] is True
    assert vlm.calls[0]["images"] == 4                                    # product, result, crop, pose
    assert not list(JUDGMENT.iter_errors(rec))


def test_the_record_names_files_never_folders(imgs):
    rec = check_pair(imgs["product"], imgs["result"], vlm=Scripted(make_checklist()))
    assert rec["product"]["file"] == "product.jpg" and rec["pose"] is None
    text = json.dumps(rec)
    assert str(imgs["product"].parent) not in text and "\\" not in rec["result"]["file"] and "/" not in rec["result"]["file"]


def test_without_crop_or_pose_the_reviewer_gets_fewer_images(imgs):
    vlm = Scripted(make_checklist())
    rec = check_pair(imgs["product"], imgs["result"], vlm=vlm, crop=False)
    assert vlm.calls[0]["images"] == 2 and "zoomed crop" not in vlm.calls[0]["prompt"]
    assert rec["judge"]["crop"] is False and rec["judge"]["box_2d"] is None


def test_the_text_rule_makes_a_clean_verdict_stricter(imgs):
    vlm = Scripted(make_checklist(ref="LABELLO CLASSIC SOIN", gen=""))                 # the reviewer says everything is the same
    rec = check_pair(imgs["product"], imgs["result"], vlm=vlm, tags=("text",))
    assert rec["rule_tightened"] and not rec["scorecard"]["verified"]
    assert rec["checklist"]["items"]["text"]["answer"] == "different"
    assert [d["code"] for d in rec["checklist"]["defects"]] == ["TEXT_GARBLE"]
    assert rec["text_rule"]["source"] == "transcription" and rec["text_rule"]["flagged"]
    assert not list(JUDGMENT.iter_errors(rec))


def test_known_words_beat_the_reviewers_transcription_of_the_product(imgs):
    vlm = Scripted(make_checklist(ref="", gen="labello classic"))                       # transcribed nothing for the product, read the result well
    ok = check_pair(imgs["product"], imgs["result"], vlm=vlm, expected_text=["LABELLO", "CLASSIC"])
    assert ok["scorecard"]["verified"] and not ok["rule_tightened"]
    bad = check_pair(imgs["product"], imgs["result"], vlm=vlm, expected_text=["NIVEA", "CREME", "SPORT"])
    assert bad["rule_tightened"] and not bad["scorecard"]["verified"]


def test_the_text_rule_never_loosens_a_verdict(imgs):
    vlm = Scripted(make_checklist({"text": {"answer": "different", "evidence": "wrong brand word"}}, ["TEXT_WRONG"], ref="labello classic", gen="labello classic"))
    rec = check_pair(imgs["product"], imgs["result"], vlm=vlm)
    assert rec["checklist"]["items"]["text"]["answer"] == "different" and not rec["scorecard"]["verified"]
    assert rec["scorecard"]["veto"] == ["TEXT_WRONG"] and not rec["rule_tightened"]


def test_apply_text_rule_leaves_cannot_tell_and_unflagged_results_alone():
    flagged = text_recall("alpha beta gamma", "")
    ok = text_recall("alpha beta gamma", "alpha beta gamma")
    cl = make_checklist({"text": "cannot_tell"})
    assert apply_text_rule(cl, flagged) is False and cl["items"]["text"]["answer"] == "cannot_tell"
    cl = make_checklist()
    assert apply_text_rule(cl, ok) is False and apply_text_rule(cl, None) is False and cl["items"]["text"]["answer"] == "same"
    cl = make_checklist({"text": {"answer": "minor", "evidence": "a bit soft"}}, ["LABEL_OCCLUDED"])
    assert apply_text_rule(cl, flagged) is True
    assert cl["items"]["text"]["answer"] == "different" and "a bit soft; text rule" in cl["items"]["text"]["evidence"]
    assert [d["code"] for d in cl["defects"]] == ["LABEL_OCCLUDED"]                      # a text defect is already there: no second one


class FakeOcr:
    name = "fake"

    def read(self, image):
        return "alpha beta gamma" if image.size == (64, 80) else ""                       # reads the product, nothing in the result


def test_ocr_replaces_the_reviewers_transcription(imgs):
    vlm = Scripted(make_checklist(ref="alpha beta gamma", gen="alpha beta gamma"))      # the reviewer "reads" the right words
    rec = check_pair(imgs["product"], imgs["result"], vlm=vlm, ocr=FakeOcr())
    assert rec["text_rule"]["source"] == "ocr" and rec["rule_tightened"] and not rec["scorecard"]["verified"]


def test_a_failed_review_is_a_record_not_an_exception(imgs):
    rec = check_pair(imgs["product"], imgs["result"], vlm=Scripted(VlmResult(ok=False, error="HTTP 500")), attempts=2)
    assert not rec["ok"] and rec["error"] == "HTTP 500" and rec["scorecard"] is None and rec["checklist"] is None
    assert not list(JUDGMENT.iter_errors(rec))


def test_a_transient_failure_is_retried(imgs):
    vlm = Scripted(VlmResult(ok=False, error="HTTP 503"), make_checklist())
    rec = check_pair(imgs["product"], imgs["result"], vlm=vlm, attempts=2)
    assert rec["ok"] and len(vlm.calls) == 2
    vlm = Scripted(VlmResult(ok=False, error="HTTP 503"), make_checklist())
    assert not check_pair(imgs["product"], imgs["result"], vlm=vlm, attempts=1)["ok"]


def test_an_invalid_checklist_is_retried_then_reported(imgs):
    rec = check_pair(imgs["product"], imgs["result"], vlm=Scripted({"items": {}}), attempts=2)
    assert not rec["ok"] and "missing items" in rec["error"]


def test_min_total_is_passed_through(imgs):
    cl = make_checklist({"pose": "minor", "identity": "minor"})
    assert check_pair(imgs["product"], imgs["result"], vlm=Scripted(cl))["scorecard"]["verified"]
    assert not check_pair(imgs["product"], imgs["result"], vlm=Scripted(cl), min_total=9)["scorecard"]["verified"]


def test_missing_input_file_raises(imgs, tmp_path):
    with pytest.raises(FileNotFoundError):
        check_pair(tmp_path / "nope.jpg", imgs["result"], vlm=Scripted(make_checklist()))
