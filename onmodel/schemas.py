"""JSON Schemas for the files onmodel reads and writes, built from the vocabulary in taxonomy.py so they cannot drift from the code.

`scripts/gen_schemas.py` writes them to schemas/*.json (what other tools and agent skills point at); a test checks the committed files match.
"""
from __future__ import annotations

from .taxonomy import ANSWERS, DEFECTS, DIMENSIONS, ITEMS, RISK_TAGS, SUBCATEGORIES

DRAFT = "https://json-schema.org/draft/2020-12/schema"
BASE = "https://github.com/molly554/onmodel/schemas/"


def _obj(props: dict, required=(), extra: bool = False) -> dict:
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": extra}


_item = _obj({"answer": {"enum": list(ANSWERS)}, "evidence": {"type": "string"}, "where": {"type": "string"}}, ["answer"], extra=True)
_defect = _obj({"code": {"enum": list(DEFECTS)}, "where": {"type": "string"}, "evidence": {"type": "string"}}, ["code"], extra=True)


def checklist_schema() -> dict:
    return {
        "$schema": DRAFT, "$id": BASE + "checklist.schema.json", "title": "onmodel checklist",
        "description": "A reviewer's answers to the nine questions about one result photo. Points are computed from this by code.",
        "type": "object",
        "properties": {
            "items": _obj({k: _item for k in ITEMS}, ITEMS, extra=False),
            "defects": {"type": "array", "items": _defect},
            "text_in_reference": {"type": "string", "description": "Text legible on the real product, line by line."},
            "text_in_generated": {"type": "string", "description": "Text legible on the product in the result, exactly as it appears."},
        },
        "required": ["items"],
        "additionalProperties": False,
    }


def _inline(schema: dict) -> dict:
    """A schema without its identity keys, to embed it in another one."""
    return {k: v for k, v in schema.items() if k not in ("$schema", "$id", "title", "description")}


def judgment_schema() -> dict:
    ref = _obj({"file": {"type": "string"}, "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}, ["file", "sha256"])
    card = _obj({
        "dims": _obj({d: {"enum": [0, 1, 2]} for d in DIMENSIONS}, DIMENSIONS),
        "total": {"type": "integer", "minimum": 0, "maximum": 10},
        "veto": {"type": "array", "items": {"enum": [c for c, d in DEFECTS.items() if d["veto"]]}},
        "unverifiable": {"type": "array", "items": {"enum": list(ITEMS)}},
        "verified": {"type": "boolean"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "max_total": {"const": 10},
    }, ["dims", "total", "veto", "unverifiable", "verified", "reasons", "max_total"])
    rule = _obj({
        "source": {"enum": ["ocr", "transcription"]}, "expected": {"type": "array", "items": {"type": "string"}},
        "found": {"type": "array", "items": {"type": "string"}}, "missing": {"type": "array", "items": {"type": "string"}},
        "recall": {"type": "number", "minimum": 0, "maximum": 1}, "threshold": {"type": "number"}, "flagged": {"type": "boolean"},
    }, ["source", "expected", "found", "missing", "recall", "threshold", "flagged"])
    return {
        "$schema": DRAFT, "$id": BASE + "judgment.schema.json", "title": "onmodel judgment record",
        "description": "The result of reviewing one result photo against its product photo (`onmodel check --json`, and one line of judgments.jsonl).",
        "type": "object",
        "properties": {
            "schema": {"const": "onmodel/judgment@1"}, "onmodel_version": {"type": "string"}, "rubric_version": {"type": "string"},
            "product": ref, "result": ref, "pose": {"oneOf": [ref, {"type": "null"}]},
            "verb": {"enum": ["wearing", "holding"]}, "tags": {"type": "array", "items": {"enum": list(RISK_TAGS)}},
            "judge": _obj({"name": {"type": "string"}, "prompt_sha": {"type": ["string", "null"]}, "crop": {"type": "boolean"},
                           "box_2d": {"oneOf": [{"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}, {"type": "null"}]}},
                          ["name", "prompt_sha", "crop", "box_2d"]),
            "ok": {"type": "boolean"}, "error": {"type": "string"},
            "checklist": {"oneOf": [_inline(checklist_schema()), {"type": "null"}]},
            "text_rule": {"oneOf": [rule, {"type": "null"}]}, "rule_tightened": {"type": "boolean"},
            "scorecard": {"oneOf": [card, {"type": "null"}]}, "advice": {"type": "array", "items": {"type": "string"}},
            "usage": {"type": "object"}, "seconds": {"type": "number"},
        },
        "required": ["schema", "onmodel_version", "rubric_version", "product", "result", "judge", "ok", "error", "scorecard"],
        "additionalProperties": True,
    }


def cases_schema() -> dict:
    source = {
        "oneOf": [
            _obj({"kind": {"const": "bundled"}, "file": {"type": "string"}, "page": {"type": "string"}, "license": {"enum": ["CC0", "Public domain"]},
                  "author": {"type": "string"}, "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}, ["kind", "file", "license", "sha256", "page"], extra=True),
            _obj({"kind": {"const": "linked"}, "url": {"type": "string", "pattern": "^https://"}, "page": {"type": "string"}, "license": {"type": "string"},
                  "author": {"type": "string"}, "sha256_source": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}, ["kind", "url", "license", "sha256_source", "page"], extra=True),
        ]
    }
    case = _obj({
        "id": {"type": "string", "pattern": "^[A-Za-z0-9]+$"}, "name": {"type": "string"}, "subcategory": {"enum": list(SUBCATEGORIES)},
        "verb": {"enum": ["wearing", "holding"]}, "tags": {"type": "array", "items": {"enum": list(RISK_TAGS)}}, "klass": {"type": "string"},
        "pose": {"type": "string"}, "text_gt": {"type": "array", "items": {"type": "string"}}, "source": source,
    }, ["id", "name", "subcategory", "verb", "tags", "pose", "source"], extra=False)
    return {
        "$schema": DRAFT, "$id": BASE + "cases.schema.json", "title": "onmodel benchmark cases",
        "type": "object", "properties": {"version": {"type": "integer"}, "cases": {"type": "array", "items": case, "minItems": 1}}, "required": ["version", "cases"],
        "additionalProperties": False,
    }


def run_record_schema() -> dict:
    return {
        "$schema": DRAFT, "$id": BASE + "run-record.schema.json", "title": "onmodel generation record",
        "description": "One line of a run's ledger.jsonl: what was asked of the engine and what came back.",
        "type": "object",
        "properties": {
            "schema": {"const": "onmodel/run-record@1"}, "file": {"type": "string"}, "case": {"type": "string"}, "variant": {"enum": ["v0", "v1", "repair"]},
            "res": {"type": "string"}, "sample": {"type": "integer", "minimum": 1}, "ratio": {"type": "string"}, "engine": {"type": "string"},
            "stamp": {"type": "object"}, "recipe_version": {"type": ["string", "null"]}, "prompt_sha": {"type": "string"}, "prompt": {"type": "string"},
            "pose": {"type": "string"}, "ok": {"type": "boolean"}, "error": {"type": "string"}, "seconds": {"type": "number"},
            "cost_lo": {"type": ["number", "null"]}, "cost_hi": {"type": ["number", "null"]}, "usage": {"type": "object"},
            "onmodel_version": {"type": "string"}, "ts": {"type": "string"},
        },
        "required": ["schema", "file", "case", "variant", "res", "sample", "engine", "prompt_sha", "ok", "ts"],
        "additionalProperties": True,
    }


ALL = {
    "checklist.schema.json": checklist_schema,
    "judgment.schema.json": judgment_schema,
    "cases.schema.json": cases_schema,
    "run-record.schema.json": run_record_schema,
}
