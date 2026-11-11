import copy
import json

import pytest
import sync_generated
from jsonschema import Draft202012Validator

from onmodel import schemas
from onmodel.taxonomy import ANSWERS, DEFECTS, ITEMS

from conftest import ROOT, make_checklist


def test_generated_files_are_up_to_date():
    assert sync_generated.main(["--check"]) == 0


def test_committed_schemas_are_the_generated_ones():
    for name, fn in schemas.ALL.items():
        assert json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8")) == fn()


@pytest.mark.parametrize("name", list(schemas.ALL))
def test_every_schema_is_a_valid_json_schema(name):
    Draft202012Validator.check_schema(schemas.ALL[name]())


def test_the_checklist_schema_accepts_good_and_rejects_bad_checklists():
    v = Draft202012Validator(schemas.checklist_schema())
    assert not list(v.iter_errors(make_checklist({"text": {"answer": "different", "evidence": "x", "where": "y"}}, ["TEXT_GARBLE"], "a", "b")))
    bad_answer = make_checklist()
    bad_answer["items"]["shape"]["answer"] = "great"
    assert list(v.iter_errors(bad_answer))
    missing = make_checklist()
    del missing["items"]["scale"]
    assert list(v.iter_errors(missing))
    assert list(v.iter_errors(make_checklist(defects=[{"code": "NOT_A_CODE"}])))
    extra = make_checklist()
    extra["items"]["mood"] = {"answer": "same"}
    assert list(v.iter_errors(extra))


def test_the_schema_vocabulary_is_the_taxonomy():
    s = schemas.checklist_schema()
    assert list(s["properties"]["items"]["properties"]) == list(ITEMS)
    assert s["properties"]["items"]["properties"]["shape"]["properties"]["answer"]["enum"] == list(ANSWERS)
    assert s["properties"]["defects"]["items"]["properties"]["code"]["enum"] == list(DEFECTS)


def test_the_cases_schema_rejects_a_bundled_share_alike_image():
    v = Draft202012Validator(schemas.cases_schema())
    case = {"id": "X1", "name": "n", "subcategory": "Rings", "verb": "wearing", "tags": ["metal"], "pose": "p",
            "source": {"kind": "bundled", "file": "golden/images/X1.jpg", "page": "https://e.org", "license": "CC0", "sha256": "0" * 64}}
    assert not list(v.iter_errors({"version": 1, "cases": [case]}))
    bad = copy.deepcopy(case)
    bad["source"]["license"] = "CC BY-SA 3.0"
    assert list(v.iter_errors({"version": 1, "cases": [bad]}))
    bad = copy.deepcopy(case)
    bad["source"] = {"kind": "linked", "url": "http://insecure.example/x.jpg", "page": "p", "license": "CC BY-SA 4.0", "sha256_source": "0" * 64}
    assert list(v.iter_errors({"version": 1, "cases": [bad]}))
    bad = copy.deepcopy(case)
    bad["tags"] = ["shiny"]
    assert list(v.iter_errors({"version": 1, "cases": [bad]}))


def test_the_judgment_schema_rejects_a_malformed_record():
    v = Draft202012Validator(schemas.judgment_schema())
    rec = {"schema": "onmodel/judgment@1", "onmodel_version": "0.1.0", "rubric_version": "1.0-draft",
           "product": {"file": "a.jpg", "sha256": "0" * 64}, "result": {"file": "b.jpg", "sha256": "1" * 64}, "pose": None,
           "judge": {"name": "m", "prompt_sha": None, "crop": True, "box_2d": None}, "ok": False, "error": "x", "scorecard": None}
    assert not list(v.iter_errors(rec))
    assert list(v.iter_errors({**rec, "product": {"file": "a.jpg", "sha256": "nope"}}))
    assert list(v.iter_errors({**rec, "schema": "other"}))
    assert list(v.iter_errors({k: x for k, x in rec.items() if k != "judge"}))
