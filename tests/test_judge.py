import json

import pytest
from PIL import Image

from onmodel.judge import (BOX_SCHEMA, CHECKLIST_SCHEMA, GeminiVlm, MockVlm, VlmResult, build_prompt, crop_product, extract_json, load_vlm,
                           locate_box, parse_checklist, to_jpeg)
from onmodel.scoring import ChecklistError
from onmodel.taxonomy import ANSWERS, DEFECTS, ITEMS

from conftest import make_checklist


def test_parse_checklist_tolerates_fences_and_chatter():
    raw = "Here is my review:\n```json\n" + json.dumps(make_checklist({"text": "different"}, ["TEXT_GARBLE"])) + "\n```\nHope that helps."
    cl = parse_checklist(raw)
    assert cl["items"]["text"]["answer"] == "different" and cl["defects"][0]["code"] == "TEXT_GARBLE"


@pytest.mark.parametrize("raw, message", [
    ("no json here", "no JSON object"),
    ("{not json}", "not valid JSON"),
    ('{"items": {}}', "missing items"),
    (json.dumps(make_checklist(defects=["NOPE"])), "unknown defect code"),
    ("[1, 2]", "no JSON object|must be a JSON object"),
])
def test_parse_checklist_rejects_bad_answers(raw, message):
    with pytest.raises(ChecklistError, match=message):
        parse_checklist(raw)


def test_parse_checklist_drops_junk_defect_entries_and_fills_text_fields():
    cl = parse_checklist({"items": make_checklist()["items"], "defects": ["junk", None], "text_in_generated": None})
    assert cl["defects"] == [] and cl["text_in_reference"] == "" and cl["text_in_generated"] == ""


def test_extract_json_finds_the_object():
    assert extract_json('prefix {"a": 1} suffix') == {"a": 1}


def test_prompt_asks_every_question_and_names_every_defect_code():
    p = build_prompt(verb="holding", tags=("text", "hand"), has_crop=True, has_pose=True)
    for k in ITEMS:
        assert f"  {k}: " in p
    for code in DEFECTS:
        assert code in p
    assert "a person holding the exact product of IMAGE A" in p
    assert "IMAGE C: a zoomed crop" in p and "IMAGE D: the POSE REFERENCE" in p
    assert "tagged: text, hand" in p and "WITHOUT correcting spelling" in p


def test_prompt_adapts_when_there_is_no_pose_or_crop():
    p = build_prompt(has_crop=False, has_pose=False)
    assert "zoomed crop" not in p and "POSE REFERENCE" not in p
    assert 'No pose reference was given: answer "not_applicable"' in p
    p = build_prompt(has_crop=False, has_pose=True)
    assert "IMAGE C: the POSE REFERENCE" in p


def test_schema_enums_come_from_the_taxonomy():
    items = CHECKLIST_SCHEMA["properties"]["items"]["properties"]
    assert list(items) == list(ITEMS)
    assert items["text"]["properties"]["answer"]["enum"] == list(ANSWERS)
    assert CHECKLIST_SCHEMA["properties"]["defects"]["items"]["properties"]["code"]["enum"] == list(DEFECTS)
    # Gemini documents an enum as {type: STRING, format: enum, enum: [...]}
    assert items["text"]["properties"]["answer"]["format"] == "enum"
    assert CHECKLIST_SCHEMA["properties"]["defects"]["items"]["properties"]["code"]["format"] == "enum"


def test_mock_vlm_default_cycle_callable_and_box():
    vlm = MockVlm()
    assert vlm.ask_json("p", [], CHECKLIST_SCHEMA).data["items"]["text"]["answer"] == "same"
    assert vlm.ask_json("p", [], BOX_SCHEMA).data == {"box_2d": [0, 0, 1000, 1000]}
    assert vlm.calls == 1                                                # a box request is not a review
    a, b = make_checklist(), make_checklist({"text": "different"})
    cycling = MockVlm([a, b])
    assert [cycling.ask_json("p", [], CHECKLIST_SCHEMA).data["items"]["text"]["answer"] for _ in range(3)] == ["same", "different", "same"]
    assert MockVlm(lambda p, i, s: b).ask_json("p", [], CHECKLIST_SCHEMA).data == b


def test_load_vlm():
    assert isinstance(load_vlm("mock"), MockVlm)
    assert isinstance(load_vlm("onmodel.judge:MockVlm"), MockVlm)
    with pytest.raises(ValueError, match="unknown judge"):
        load_vlm("something-else")


def test_gemini_vlm_needs_a_key_from_the_environment(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not set"):
        GeminiVlm()
    monkeypatch.setenv("GEMINI_API_KEY", "x" * 12)
    assert GeminiVlm("gemini-3.5-flash-lite").name == "gemini-3.5-flash-lite"


def test_crop_product_geometry():
    im = Image.new("RGB", (400, 400))
    whole = crop_product(im, None)
    assert whole.size == (1000, 1000)                                    # no box: the whole frame, enlarged
    crop = crop_product(im, [250, 250, 750, 750], margin=0.0)            # the middle half, plus a 1% margin each side
    assert crop.size == (1000, 1000)
    big = crop_product(Image.new("RGB", (2000, 1000)), [0, 0, 1000, 500], margin=0.0, target=500)
    assert big.size == (1020, 1000)                                      # the left half plus the 1% margin; already larger than the target, so not enlarged


def test_crop_product_clamps_to_the_frame():
    crop = crop_product(Image.new("RGB", (100, 100)), [0, 0, 1000, 1000], margin=0.5, target=100)
    assert crop.size == (100, 100)


def test_locate_box_validates_the_answer():
    class V:
        name = "v"

        def __init__(self, data, ok=True):
            self.data, self.ok = data, ok

        def ask_json(self, prompt, images, schema):
            return VlmResult(ok=self.ok, data=self.data)

    im = Image.new("RGB", (50, 50))
    assert locate_box(V({"box_2d": [10, 20, 300, 400]}), im) == [10, 20, 300, 400]
    assert locate_box(V({"box_2d": [5, 5, 5, 5]}), im) is None
    assert locate_box(V({"box_2d": [1, 2, 3]}), im) is None
    assert locate_box(V(None, ok=False), im) is None


def test_to_jpeg_limits_the_long_edge():
    data, mime = to_jpeg(Image.new("RGB", (3000, 1000)), max_side=1280)
    assert mime == "image/jpeg" and Image.open(__import__("io").BytesIO(data)).size == (1280, 427)
