"""check_pair: one product photo and one result photo in, one judgment record out.

The steps: find the product in the result and zoom in on it, send the images and the nine questions to a reviewer, validate the
answers, let the text rule make the verdict stricter when the printed words did not survive, then compute the scorecard in code.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

from . import __version__
from .judge import CHECKLIST_SCHEMA, RUBRIC_VERSION, Vlm, build_prompt, crop_product, load_image, locate_box, parse_checklist, to_jpeg
from .scoring import MIN_TOTAL, ChecklistError, advice, score
from .text_rule import DEFAULT_THRESHOLD, TextRuleResult, ocr_text_rule, text_recall

JUDGMENT_SCHEMA_ID = "onmodel/judgment@1"
TEXT_DEFECTS = ("TEXT_GARBLE", "TEXT_WRONG", "LABEL_OCCLUDED")


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def prompt_sha(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]


def _ref(path) -> dict:
    """What a record says about an input file: its name (never the folder it lives in) and its hash."""
    return {"file": Path(path).name, "sha256": sha256_file(path)}


def apply_text_rule(checklist: dict, rule: TextRuleResult | None) -> bool:
    """When the printed words did not survive, mark the text item "different". A rule only ever tightens a verdict. Returns True if it did."""
    if rule is None or not rule.flagged:
        return False
    item = checklist["items"]["text"]
    if item["answer"] not in ("same", "minor", "not_applicable"):
        return False   # already "different", or "cannot_tell": the rule has the same pixels to go on
    note = f"text rule ({rule.source}): {len(rule.found)} of {len(rule.expected)} words from the real product are readable in the result"
    item["answer"] = "different"
    item["evidence"] = f"{item['evidence']}; {note}" if item.get("evidence") else note
    if not any(d["code"] in TEXT_DEFECTS for d in checklist["defects"]):
        checklist["defects"].append({"code": "TEXT_GARBLE", "where": "product", "evidence": note})
    return True


def check_pair(product, result, *, vlm: Vlm, pose=None, verb: str = "wearing", tags=(), crop: bool = True, note: str = "the product",
               expected_text=None, ocr=None, min_total: int = MIN_TOTAL, threshold: float = DEFAULT_THRESHOLD, attempts: int = 2) -> dict:
    """product, result, pose: paths to image files. Returns a judgment record (see schemas/judgment.schema.json).

    expected_text: the words printed on the real product, if you know them. Without it the rule compares what the reviewer (or OCR) reads.
    ocr: an object with read(image) -> str (see text_rule.get_backend). Without it the rule uses the reviewer's own transcription.
    A failed review does not raise: the record has ok = false and an error message, and the caller decides what to do.
    """
    t0 = time.time()
    tags = tuple(tags)
    rec = {
        "schema": JUDGMENT_SCHEMA_ID, "onmodel_version": __version__, "rubric_version": RUBRIC_VERSION,
        "product": _ref(product), "result": _ref(result), "pose": _ref(pose) if pose else None,
        "verb": verb, "tags": list(tags),
        "judge": {"name": vlm.name, "prompt_sha": None, "crop": bool(crop), "box_2d": None},
        "ok": False, "error": "", "checklist": None, "text_rule": None, "rule_tightened": False,
        "scorecard": None, "advice": [], "usage": {}, "seconds": 0.0,
    }
    product_img, result_img = load_image(product), load_image(result)
    pose_img = load_image(pose) if pose else None

    box = locate_box(vlm, result_img, note) if crop else None
    crop_img = crop_product(result_img, box) if crop else None
    images = [to_jpeg(product_img), to_jpeg(result_img)]
    if crop_img is not None:
        images.append(to_jpeg(crop_img))
    if pose_img is not None:
        images.append(to_jpeg(pose_img))
    prompt = build_prompt(verb=verb, tags=tags, has_crop=crop_img is not None, has_pose=pose_img is not None)
    rec["judge"]["prompt_sha"] = prompt_sha(prompt)
    rec["judge"]["box_2d"] = box

    checklist, error = None, ""
    for _ in range(max(1, attempts)):
        r = vlm.ask_json(prompt, images, CHECKLIST_SCHEMA)
        rec["usage"] = r.usage or {}
        if not r.ok:
            error = r.error or "the reviewer returned no answer"
            continue
        try:
            checklist = parse_checklist(r.data)
            break
        except ChecklistError as e:
            error = str(e)
    if checklist is None:
        rec.update(error=error, seconds=round(time.time() - t0, 1))
        return rec

    probe = crop_img if crop_img is not None else result_img
    if ocr is not None:
        rule = ocr_text_rule(product_img, probe, ocr, expected=expected_text, threshold=threshold)
    else:
        rule = text_recall(expected_text or checklist["text_in_reference"], checklist["text_in_generated"], threshold=threshold, source="transcription")
    tightened = apply_text_rule(checklist, rule)

    card = score(checklist, min_total)
    rec.update(ok=True, checklist=checklist, text_rule=rule.to_dict() if rule else None, rule_tightened=tightened,
               scorecard=card.to_dict(), advice=advice(checklist), seconds=round(time.time() - t0, 1))
    return rec
