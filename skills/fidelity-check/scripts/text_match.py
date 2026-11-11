#!/usr/bin/env python3
"""The text rule, on its own: do the words printed on the real product show up in the result? Standard library only.

    python text_match.py --expected "LABELLO CLASSIC SOIN PROTECTEUR" --observed "LABELLO CLASSIC"
    python text_match.py --expected-file product.txt --observed-file result.txt --json

Prints the words found and missing and whether the photo is flagged (recall below 0.25).
Exit code: 0 = not flagged, 1 = flagged (set the checklist's "text" item to "different"), 2 = nothing to compare.
A rule only ever tightens a verdict: never use it to turn a "different" into a "same".
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

THRESHOLD = 0.25
_WORD = re.compile(r"[^\W\d_]{3,}|\d{2,}")   # three or more letters, or a number of two or more digits


def words(text):
    t = unicodedata.normalize("NFKD", text.casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    out, seen = [], set()
    for w in _WORD.findall(t):
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def match(expected, observed, threshold=THRESHOLD):
    exp = words(expected)
    if not exp:
        return None
    seen = set(words(observed or ""))
    found = [w for w in exp if w in seen]
    missing = [w for w in exp if w not in seen]
    recall = len(found) / len(exp)
    return {"expected": exp, "found": found, "missing": missing, "recall": round(recall, 3), "threshold": threshold, "flagged": recall < threshold}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--expected")
    ap.add_argument("--expected-file")
    ap.add_argument("--observed")
    ap.add_argument("--observed-file")
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    exp = a.expected if a.expected is not None else (Path(a.expected_file).read_text(encoding="utf-8") if a.expected_file else "")
    obs = a.observed if a.observed is not None else (Path(a.observed_file).read_text(encoding="utf-8") if a.observed_file else "")
    res = match(exp, obs, a.threshold)
    if res is None:
        print("nothing to compare: no words were given for the real product", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        print("found %d of %d words (recall %.2f, flag below %.2f)" % (len(res["found"]), len(res["expected"]), res["recall"], res["threshold"]))
        if res["missing"]:
            print("missing: " + ", ".join(res["missing"]))
        print("FLAGGED: set the text item to 'different'" if res["flagged"] else "not flagged")
    return 1 if res["flagged"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
