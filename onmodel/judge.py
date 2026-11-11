"""The judge: nine fixed questions, a schema for the answer, and the clients that send them.

A reviewer does not give scores. It answers questions with "same / minor / different / cannot_tell / not_applicable" and lists defects
with codes. Points are computed by `scoring.score`, so the reviewer cannot drift on what a "1" means.
"""
from __future__ import annotations

import io
import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from PIL import Image, ImageOps

from . import gemini
from .plugins import load_class
from .scoring import ChecklistError, validate_checklist
from .taxonomy import ANSWERS, DEFECTS, ITEMS, QUESTIONS

DEFAULT_JUDGE = "gemini-3.5-flash-lite"   # the cheaper of the two judges of our mini test
RUBRIC_VERSION = "1.0-draft"
VERBS = ("wearing", "holding")


# ----------------------------------------------------------------------------------------------------------- prompt
def build_prompt(*, verb: str = "wearing", tags=(), has_crop: bool = True, has_pose: bool = False) -> str:
    letters = iter("ABCD")
    lines = [
        "You are a strict reviewer of AI-generated e-commerce product photos. Be literal and do not give the benefit of the doubt.",
        'If you cannot see something well enough to decide, answer "cannot_tell" instead of guessing.',
        "",
        "You receive these images, in this order:",
    ]
    a = next(letters)
    lines.append(f" IMAGE {a}: the REAL PRODUCT photo. It is the ground truth for the product. It may also show a hand, a mannequin, a background or props: those are NOT part of the product.")
    b = next(letters)
    lines.append(f" IMAGE {b}: the PHOTO TO REVIEW. It should show a person {verb} the exact product of IMAGE {a}.")
    if has_crop:
        lines.append(f" IMAGE {next(letters)}: a zoomed crop of the product region of IMAGE {b}, for checking fine detail and printed text.")
    if has_pose:
        lines.append(f" IMAGE {next(letters)}: the POSE REFERENCE the generator was asked to follow (the person, pose, framing and background).")
    lines += [
        "",
        f"Review IMAGE {b}. Answer each question below with one of: {', '.join(ANSWERS)}.",
        "  same = nothing wrong.  minor = visible but not damaging.  different = clearly wrong.",
        "  cannot_tell = you cannot see enough to decide.  not_applicable = the question does not apply.",
        'For every answer other than "same", add "evidence" (what you see, in a few words) and "where" (where in the photo).',
        "",
        "Questions:",
    ]
    for k in ITEMS:
        q = QUESTIONS[k]
        if k == "pose" and not has_pose:
            q = 'No pose reference was given: answer "not_applicable".'
        lines.append(f"  {k}: {q}")
    lines += [
        "",
        'Then list every problem you found as "defects", each with a "code", "where" and "evidence". Use only these codes:',
    ]
    lines += [f"  {code}: {d['meaning']}" for code, d in DEFECTS.items()]
    lines += [
        "",
        f'Transcribe: "text_in_reference" = all legible text on the product in IMAGE {a}, line by line. "text_in_generated" = all legible text on the product in IMAGE {b}'
        + (" (use the crop)" if has_crop else "")
        + ", exactly as it appears, WITHOUT correcting spelling and WITHOUT filling in what the text should say. Use an empty string when there is none.",
    ]
    if tags:
        lines += ["", f"This product is tagged: {', '.join(tags)}. Pay particular attention to those risks."]
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------------------------- schema (Gemini's OpenAPI subset; an enum is {type: STRING, format: enum, enum: [...]})
_ITEM = {"type": "OBJECT", "properties": {"answer": {"type": "STRING", "format": "enum", "enum": list(ANSWERS)}, "evidence": {"type": "STRING"}, "where": {"type": "STRING"}}, "required": ["answer"]}
CHECKLIST_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "items": {"type": "OBJECT", "properties": {k: _ITEM for k in ITEMS}, "required": list(ITEMS)},
        "defects": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"code": {"type": "STRING", "format": "enum", "enum": list(DEFECTS)}, "where": {"type": "STRING"}, "evidence": {"type": "STRING"}}, "required": ["code"]}},
        "text_in_reference": {"type": "STRING"},
        "text_in_generated": {"type": "STRING"},
    },
    "required": ["items", "defects", "text_in_reference", "text_in_generated"],
}
BOX_SCHEMA = {"type": "OBJECT", "properties": {"box_2d": {"type": "ARRAY", "items": {"type": "INTEGER"}}}, "required": ["box_2d"]}


def extract_json(text: str) -> dict:
    """The first JSON object in a model's answer (code fences and chatter around it are tolerated)."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        raise ChecklistError("no JSON object in the answer")
    try:
        return json.loads(t[i : j + 1])
    except json.JSONDecodeError as e:
        raise ChecklistError(f"the answer is not valid JSON: {e}") from e


def parse_checklist(raw) -> dict:
    """Accepts a dict or a string. Returns a validated checklist or raises ChecklistError."""
    data = extract_json(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        raise ChecklistError("the answer must be a JSON object")
    out = {
        "items": data.get("items", {}),
        "defects": [d for d in (data.get("defects") or []) if isinstance(d, dict)],
        "text_in_reference": str(data.get("text_in_reference") or ""),
        "text_in_generated": str(data.get("text_in_generated") or ""),
    }
    validate_checklist(out)
    return out


# ----------------------------------------------------------------------------------------------------------- clients
@dataclass
class VlmResult:
    ok: bool
    data: dict | None = None
    error: str = ""
    usage: dict = field(default_factory=dict)
    seconds: float = 0.0


class Vlm(Protocol):
    name: str

    def ask_json(self, prompt: str, images: list, schema: dict) -> VlmResult:  # images: list of (bytes, mime)
        ...


class GeminiVlm:
    def __init__(self, model: str = DEFAULT_JUDGE, api_key: str | None = None):
        self.model = model
        self.key = api_key or gemini.get_key()
        if not self.key:
            raise RuntimeError("GEMINI_API_KEY is not set. Export it in your shell; onmodel never writes it anywhere.")

    @property
    def name(self) -> str:
        return self.model

    def ask_json(self, prompt: str, images: list, schema: dict) -> VlmResult:
        r = gemini.ask_json(self.key, self.model, prompt, images, schema)
        return VlmResult(ok=r["ok"], data=r["data"], error=r["error"], usage=r["usage"], seconds=r["seconds"])


def default_mock_answer() -> dict:
    return {"items": {k: {"answer": "same"} for k in ITEMS}, "defects": [], "text_in_reference": "", "text_in_generated": ""}


class MockVlm:
    """Deterministic stand-in for tests, CI and `onmodel bench smoke`. No network, no key.

    answers: a dict (always returned), a list (returned in turn, then repeated), or a callable (prompt, images, schema) -> dict.
    A call that asks for a bounding box (BOX_SCHEMA) gets the whole frame."""

    name = "mock"

    def __init__(self, answers=None):
        self.answers = answers if answers is not None else default_mock_answer()
        self.calls = 0
        self._lock = threading.Lock()

    def ask_json(self, prompt: str, images: list, schema: dict) -> VlmResult:
        if schema is BOX_SCHEMA or "box_2d" in json.dumps(schema):
            return VlmResult(ok=True, data={"box_2d": [0, 0, 1000, 1000]})
        with self._lock:
            self.calls += 1
            n = self.calls
        a = self.answers
        if callable(a):
            data = a(prompt, images, schema)
        elif isinstance(a, list):
            data = a[(n - 1) % len(a)]
        else:
            data = a
        return VlmResult(ok=True, data=json.loads(json.dumps(data)))


def load_vlm(spec: str | None) -> Vlm:
    """'mock', a Gemini model name ('gemini-3.5-flash-lite'), or 'package.module:ClassName' (a class with a no-argument constructor)."""
    spec = spec or DEFAULT_JUDGE
    if spec == "mock":
        return MockVlm()
    if spec.startswith("gemini-"):
        return GeminiVlm(spec)
    if ":" in spec:
        return load_class(spec)()
    raise ValueError(f"unknown judge: {spec!r} (use 'mock', a gemini model name, or 'package.module:Class')")


# ----------------------------------------------------------------------------------------------------------- images
def load_image(path) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def to_jpeg(im: Image.Image, max_side: int = 1280):
    """(bytes, mime) of a JPEG no larger than max_side on its long edge: what we send to the judge."""
    s = max_side / max(im.size)
    if s < 1:
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=90)
    return b.getvalue(), "image/jpeg"


def locate_box(vlm: Vlm, result: Image.Image, description: str = "the product") -> list | None:
    """box_2d = [ymin, xmin, ymax, xmax], each 0 to 1000, or None when the locator fails."""
    prompt = (f"Return the tight bounding box of the product in this photo as box_2d = [ymin, xmin, ymax, xmax], each 0 to 1000. "
              f"The product is: {description}. The person is NOT part of the product. For jewelry or garments include the whole product.")
    r = vlm.ask_json(prompt, [to_jpeg(result)], BOX_SCHEMA)
    box = (r.data or {}).get("box_2d") if r.ok else None
    return box if box and len(box) == 4 and box[2] > box[0] and box[3] > box[1] else None


def crop_product(result: Image.Image, box_2d: list | None, margin: float = 0.12, target: int = 1000) -> Image.Image:
    """A zoomed crop of the product region (the whole frame when there is no box). Upscaling adds no detail but helps the reader."""
    if not box_2d:
        crop = result
    else:
        y0, x0, y1, x1 = [v / 1000 for v in box_2d]
        mx, my = (x1 - x0) * margin + 0.01, (y1 - y0) * margin + 0.01
        crop = result.crop((round(max(0, x0 - mx) * result.width), round(max(0, y0 - my) * result.height),
                            round(min(1, x1 + mx) * result.width), round(min(1, y1 + my) * result.height)))
    s = target / max(crop.size)
    if s > 1:
        crop = crop.resize((round(crop.width * s), round(crop.height * s)), Image.LANCZOS)
    return crop
