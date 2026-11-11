"""The text rule: do the words printed on the real product show up in the result?

It is a cheap check that does not depend on an LLM's reading. Take the words that can be read on the real product,
look for them in the result's product crop, and flag the photo when too few are found. In our mini test a free OCR rule
flagged 12 of 12 photos with garbled small print and 3 of 3 failures, with 2 false alarms in 17 good photos.

A rule can only make a verdict stricter. It never turns a "different" into a "same".
Two sources of the observed text:
  * OCR (preferred): independent of any model's habit of "correcting" what it reads.
  * the reviewer's transcription: works without installing anything, but a model may read what it expects to see.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Iterable, Protocol

# a word is three or more letters, or a number of two or more digits
_WORD = re.compile(r"[^\W\d_]{3,}|\d{2,}")
DEFAULT_THRESHOLD = 0.25


def words(text: str) -> list:
    """Lower-case words without accents, in order of appearance, without repeats."""
    t = unicodedata.normalize("NFKD", text.casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    out, seen = [], set()
    for w in _WORD.findall(t):
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


@dataclass
class TextRuleResult:
    source: str                      # "ocr" or "transcription"
    expected: list = field(default_factory=list)
    found: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    recall: float = 1.0
    threshold: float = DEFAULT_THRESHOLD
    flagged: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["recall"] = round(self.recall, 3)
        return d


def text_recall(expected, observed_text: str, *, threshold: float = DEFAULT_THRESHOLD, source: str = "transcription") -> TextRuleResult | None:
    """expected: a string or an iterable of strings (the words read on the real product). Returns None when there is nothing to check."""
    if isinstance(expected, str):
        exp = words(expected)
    else:
        exp = []
        for chunk in expected:
            for w in words(chunk):
                if w not in exp:
                    exp.append(w)
    if not exp:
        return None
    seen = set(words(observed_text or ""))
    found = [w for w in exp if w in seen]
    missing = [w for w in exp if w not in seen]
    recall = len(found) / len(exp)
    return TextRuleResult(source=source, expected=exp, found=found, missing=missing, recall=recall, threshold=threshold, flagged=recall < threshold)


class OcrBackend(Protocol):
    name: str

    def read(self, image) -> str:  # image: PIL.Image.Image
        ...


class TesseractBackend:
    """Uses the Tesseract binary through pytesseract (pip install 'onmodel[ocr]', plus the Tesseract program)."""

    name = "tesseract"

    def __init__(self, lang: str = "eng"):
        try:
            import pytesseract  # noqa: F401
        except ImportError as e:  # pragma: no cover - depends on the environment
            raise RuntimeError("the tesseract backend needs pytesseract: pip install 'onmodel[ocr]' (and install the Tesseract program)") from e
        self.lang = lang

    def read(self, image) -> str:  # pragma: no cover - depends on the environment
        import pytesseract

        return pytesseract.image_to_string(image, lang=self.lang)


def get_backend(name: str | None, lang: str = "eng") -> OcrBackend | None:
    if not name or name == "none":
        return None
    if name == "tesseract":
        return TesseractBackend(lang)
    raise ValueError(f"unknown OCR backend: {name} (use 'none' or 'tesseract', or pass your own object with a read(image) method)")


def ocr_text_rule(product_img, result_img, backend: OcrBackend, *, expected=None, rotations: Iterable = (0, 90, 270),
                  threshold: float = DEFAULT_THRESHOLD) -> TextRuleResult | None:
    """Words OCR can read on the result, searched at several rotations (the best recall wins).

    expected: the words printed on the real product, if you know them (a string or a list). Without it, OCR reads them off the product photo."""
    if expected:
        exp = words(expected) if isinstance(expected, str) else [w for chunk in expected for w in words(chunk)]
    else:
        exp = words(backend.read(product_img))
    if not exp:
        return None
    expected = exp
    best = None
    for r in rotations:
        rotated = result_img.rotate(r, expand=True) if r else result_img
        res = text_recall(expected, backend.read(rotated), threshold=threshold, source="ocr")
        if best is None or res.recall > best.recall:
            best = res
    return best
