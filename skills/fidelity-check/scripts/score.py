#!/usr/bin/env python3
"""Turn a checklist (your answers to the nine questions) into a scorecard. Standard library only; no key, no network.

    python score.py checklist.json            print the scorecard
    python score.py checklist.json --json     print it as JSON
    cat checklist.json | python score.py -    read from stdin

Exit code: 0 = Verified, 1 = not Verified, 2 = the checklist is not valid.
The rules are the same as onmodel/scoring.py; a test keeps the two in step.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vocab import ANSWERS, DEFECTS, DIMENSIONS, FIDELITY_ITEMS, ITEMS, OTHER_ITEMS, VETO_CODES  # noqa: E402

POINTS = {"same": 2, "not_applicable": 2, "minor": 1, "cannot_tell": 1, "different": 0}
MIN_TOTAL = 8


def load(text):
    """The first JSON object in the text. Code fences and chatter around it are fine."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("no JSON object found")
    return json.loads(t[i : j + 1])


def validate(cl):
    if not isinstance(cl, dict) or not isinstance(cl.get("items"), dict):
        raise ValueError("the checklist needs an 'items' object")
    missing = [k for k in ITEMS if k not in cl["items"]]
    if missing:
        raise ValueError("missing items: " + ", ".join(missing))
    for k in ITEMS:
        it = cl["items"][k]
        a = it.get("answer") if isinstance(it, dict) else None
        if a not in ANSWERS:
            raise ValueError("item '%s': answer must be one of %s (got %r)" % (k, ", ".join(ANSWERS), a))
    for d in cl.get("defects") or []:
        if not isinstance(d, dict) or d.get("code") not in DEFECTS:
            raise ValueError("unknown defect code: %r" % (d.get("code") if isinstance(d, dict) else d))


def score(cl, min_total=MIN_TOTAL):
    validate(cl)
    items = cl["items"]
    pts = {k: POINTS[items[k]["answer"]] for k in ITEMS}
    dims = {"fidelity": min(pts[k] for k in FIDELITY_ITEMS)}
    for k in OTHER_ITEMS:
        dims[k] = pts[k]
    total = sum(dims[d] for d in DIMENSIONS)
    veto = sorted({d["code"] for d in cl.get("defects") or [] if d["code"] in VETO_CODES})
    unverifiable = [k for k in ITEMS if items[k]["answer"] == "cannot_tell"]
    reasons = []
    if dims["fidelity"] < 2:
        reasons.append("product fidelity is %d / 2 (%s)" % (dims["fidelity"], ", ".join(k for k in FIDELITY_ITEMS if pts[k] < 2)))
    if total < min_total:
        reasons.append("total %d / 10 is below %d" % (total, min_total))
    if veto:
        reasons.append("veto: " + ", ".join(veto))
    if unverifiable:
        reasons.append("could not tell: " + ", ".join(unverifiable))
    verified = dims["fidelity"] == 2 and total >= min_total and not veto
    return {"dims": dims, "total": total, "veto": veto, "unverifiable": unverifiable, "verified": verified, "reasons": reasons, "max_total": 10}


def advice(cl, limit=3):
    seen, out = set(), []
    codes = [d["code"] for d in cl.get("defects") or [] if d.get("code") in DEFECTS]
    for code in sorted(codes, key=lambda c: (not DEFECTS[c]["veto"], c)):
        text = DEFECTS[code]["advice"]
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out[:limit]


def render(card, cl):
    labels = {"fidelity": "Fidelity", "pose": "Pose", "identity": "Identity", "artifacts": "Artifacts", "scale": "Scale"}
    group = {"fidelity": FIDELITY_ITEMS, "pose": ("pose",), "identity": ("identity",), "artifacts": ("artifacts",), "scale": ("scale",)}
    notes = {}
    for k in ITEMS:
        it = cl["items"].get(k) or {}
        if it.get("answer") in ("minor", "different", "cannot_tell"):
            notes[k] = "%s: %s" % (k, it.get("evidence") or it["answer"].replace("_", " "))
    lines = []
    for d in DIMENSIONS:
        n = [notes[k] for k in group[d] if k in notes]
        lines.append(" %-10s %d / 2%s" % (labels[d], card["dims"][d], (" " + n[0]) if n else ""))
        for extra in n[1:]:
            lines.append(" %-10s       %s" % ("", extra))
    lines.append(" " + "-" * 64)
    why = "" if card["verified"] else " (%s)" % "; ".join(card["reasons"])
    lines.append(" Total %d / 10   Veto: %s   Verified: %s%s" % (card["total"], ", ".join(card["veto"]) or "none", "yes" if card["verified"] else "no", why))
    tips = advice(cl)
    if tips and not card["verified"]:
        lines.append(" Fix: " + " ".join(tips))
    return "\n".join(lines)


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    min_total = MIN_TOTAL
    for a in argv:
        if a.startswith("--min-total="):
            min_total = int(a.split("=", 1)[1])
    try:
        cl = load(sys.stdin.read() if args[0] == "-" else Path(args[0]).read_text(encoding="utf-8-sig"))
        card = score(cl, min_total)
    except (ValueError, OSError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    if "--json" in argv:
        print(json.dumps({"scorecard": card, "advice": advice(cl)}, indent=2))
    else:
        print(render(card, cl))
    return 0 if card["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
