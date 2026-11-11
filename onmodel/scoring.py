"""Turn a checklist into a scorecard.

No model is involved here. A reviewer (a person, an LLM, a skill) answers nine fixed questions; this module turns the
answers into points, applies the veto rules and decides "Verified". The same checklist always gives the same card.

Points per answer: same / not_applicable = 2, minor = 1, cannot_tell = 1, different = 0.
Product fidelity is the minimum over its five items, so it is 2 only when all five are "same".
Five dimensions of 0-2 each give a total out of 10.

Verified = product fidelity 2 / 2, and total >= 8, and no veto. A "cannot_tell" scores 1, never 2: on a product-fidelity item it blocks
Verified (the photo cannot be Verified on a guess); on any other item it costs one point.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .taxonomy import ANSWERS, DEFECTS, DIMENSIONS, FIDELITY_ITEMS, ITEMS, OTHER_ITEMS, VETO_CODES

POINTS = {"same": 2, "not_applicable": 2, "minor": 1, "cannot_tell": 1, "different": 0}
MIN_TOTAL = 8


class ChecklistError(ValueError):
    """The checklist is not well formed (missing item, unknown answer, unknown defect code)."""


@dataclass
class Scorecard:
    dims: dict
    total: int
    veto: list = field(default_factory=list)
    unverifiable: list = field(default_factory=list)
    verified: bool = False
    reasons: list = field(default_factory=list)
    max_total: int = 10

    def to_dict(self) -> dict:
        return asdict(self)


def validate_checklist(checklist: dict) -> None:
    if not isinstance(checklist, dict) or not isinstance(checklist.get("items"), dict):
        raise ChecklistError("the checklist needs an 'items' object")
    items = checklist["items"]
    missing = [k for k in ITEMS if k not in items]
    if missing:
        raise ChecklistError(f"missing items: {', '.join(missing)}")
    for k in ITEMS:
        a = items[k].get("answer") if isinstance(items[k], dict) else None
        if a not in ANSWERS:
            raise ChecklistError(f"item '{k}': answer must be one of {', '.join(ANSWERS)} (got {a!r})")
    for d in checklist.get("defects", []) or []:
        if not isinstance(d, dict) or d.get("code") not in DEFECTS:
            raise ChecklistError(f"unknown defect code: {d.get('code') if isinstance(d, dict) else d!r}")


def score(checklist: dict, min_total: int = MIN_TOTAL) -> Scorecard:
    validate_checklist(checklist)
    items = checklist["items"]
    pts = {k: POINTS[items[k]["answer"]] for k in ITEMS}
    dims = {"fidelity": min(pts[k] for k in FIDELITY_ITEMS)}
    for k in OTHER_ITEMS:
        dims[k] = pts[k]
    total = sum(dims[d] for d in DIMENSIONS)
    veto = sorted({d["code"] for d in checklist.get("defects", []) or [] if d["code"] in VETO_CODES})
    unverifiable = [k for k in ITEMS if items[k]["answer"] == "cannot_tell"]

    reasons = []
    if dims["fidelity"] < 2:
        weak = [k for k in FIDELITY_ITEMS if pts[k] < 2]
        reasons.append(f"product fidelity is {dims['fidelity']} / 2 ({', '.join(weak)})")
    if total < min_total:
        reasons.append(f"total {total} / 10 is below {min_total}")
    if veto:
        reasons.append("veto: " + ", ".join(veto))
    if unverifiable:
        reasons.append("could not tell: " + ", ".join(unverifiable))
    verified = dims["fidelity"] == 2 and total >= min_total and not veto
    return Scorecard(dims=dims, total=total, veto=veto, unverifiable=unverifiable, verified=verified, reasons=reasons)


def advice(checklist: dict, limit: int = 3) -> list:
    """Short fixes for the defects found, most serious first (vetoes first), without repeats."""
    seen, out = set(), []
    codes = [d["code"] for d in checklist.get("defects", []) or [] if d.get("code") in DEFECTS]
    for code in sorted(codes, key=lambda c: (not DEFECTS[c]["veto"], c)):
        text = DEFECTS[code]["advice"]
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out[:limit]


def render_text(card: Scorecard, checklist: dict | None = None) -> str:
    """A plain-text scorecard, for the terminal and for the skill's answer."""
    items = (checklist or {}).get("items", {})
    notes = {}
    for k in ITEMS:
        it = items.get(k) or {}
        if it.get("answer") in ("minor", "different", "cannot_tell"):
            note = it.get("evidence") or it["answer"].replace("_", " ")
            notes[k] = f"{k}: {note}"
    lines = []
    labels = {"fidelity": "Fidelity", "pose": "Pose", "identity": "Identity", "artifacts": "Artifacts", "scale": "Scale"}
    group = {"fidelity": FIDELITY_ITEMS, "pose": ("pose",), "identity": ("identity",), "artifacts": ("artifacts",), "scale": ("scale",)}
    for d in DIMENSIONS:
        n = [notes[k] for k in group[d] if k in notes]
        first = f" {n[0]}" if n else ""
        lines.append(f" {labels[d]:<10} {card.dims[d]} / 2{first}")
        for extra in n[1:]:
            lines.append(f" {'':<10}       {extra}")
    lines.append(" " + "-" * 64)
    verdict = "yes" if card.verified else "no"
    why = "" if card.verified else f" ({'; '.join(card.reasons)})"
    lines.append(f" Total {card.total} / 10   Veto: {', '.join(card.veto) if card.veto else 'none'}   Verified: {verdict}{why}")
    tips = advice(checklist or {})
    if tips and not card.verified:
        lines.append(" Fix: " + " ".join(tips))
    return "\n".join(lines)
