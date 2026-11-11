#!/usr/bin/env python3
"""Recompute every number we publish about the mini test from the per-photo table.

    python scripts/recompute_mini_test.py                 print the numbers
    python scripts/recompute_mini_test.py --write         also write bench/runs/mini-test-v0.1/summary.json
    python scripts/recompute_mini_test.py --check         exit 1 if summary.json is not what the table gives (used by the tests)

Input: bench/runs/mini-test-v0.1/photos.csv, one row per generated photo: our label (pass / minor / fail with defect tags), the verdicts of
two model reviewers, and the OCR result for photos of products that carry text. Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "bench" / "runs" / "mini-test-v0.1"
OCR_THRESHOLD = 0.25   # flag a photo when fewer than a quarter of the words OCR can read on the real product are found again in it
SMALL_PRINT = ("K04", "K07")


def load(path: Path) -> list:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["sample"] = int(r["sample"])
        r["tags"] = r["label_tags"].split()
    return rows


def kappa(pairs: list) -> float:
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (round((po - pe) / (1 - pe), 2) + 0.0) if pe < 1 else 1.0     # + 0.0 turns -0.0 into 0.0


def pct(k: int, n: int) -> float:
    return round(k / n, 2) if n else None


def config(r: dict) -> str:
    if r["variant"] == "repair":
        return "repair"
    if r["engine"] == "gemini-3-pro-image":
        return "pro"
    return r["res"]            # "1k" or "2k"


def compute(rows: list) -> dict:
    out = {"photos": len(rows), "cases": sorted({r["case"] for r in rows}), "labels": dict(sorted(Counter(r["label"] for r in rows).items()))}

    # 1. small print: render size
    sp = {}
    for key in ("1k", "2k", "repair", "pro"):
        sel = [r for r in rows if r["case"] in SMALL_PRINT and config(r) == key]
        sp[key] = {"photos": len(sel), "garbled": sum("text_small_garbled" in r["tags"] for r in sel)}
    out["small_print"] = sp

    # 2. products with several pieces: does listing the pieces help? (1K, recipe v0 = generic, v1 = with the product's rules)
    multi = {}
    for case in ("K10", "G02"):
        for key, variant, res in (("v0", "v0", "1k"), ("v1", "v1", "1k"), ("v1_2k", "v1", "2k")):
            sel = [r for r in rows if r["case"] == case and r["variant"] == variant and config(r) == res]
            multi.setdefault(case, {})[key] = {"photos": len(sel), "with_part_defect": sum(any(t.startswith("parts_") or t == "extra_part" for t in r["tags"]) for r in sel)}
    out["parts"] = multi

    # 2b. dresses: does the hem follow the product or the pose photo? (1K)
    dress = [r for r in rows if r["case"] in ("A02", "A04") and config(r) == "1k"]
    out["hem_length"] = {"photos": len(dress), "followed_the_pose_photo": sum("shape_length" in r["tags"] for r in dress)}

    # 3. fingers or props over the printed text, products that carry text
    text_cases = sorted({r["case"] for r in rows if r["ocr_readable_recall"] != ""})
    occl = {c: {"photos": sum(r["case"] == c for r in rows), "label_covered": sum(r["case"] == c and "text_occluded" in r["tags"] for r in rows)} for c in text_cases}
    out["label_covered"] = {"by_case": occl, "photos": sum(v["photos"] for v in occl.values()), "covered": sum(v["label_covered"] for v in occl.values())}

    # 4. model reviewers against our labels and against each other
    def lv(r, k): return r[k]
    judges = {}
    for name, key in (("judge_a", "judge_a_level"), ("judge_b", "judge_b_level")):
        pairs = [(r["label"], r[key]) for r in rows]
        fail = [(a == "fail", b == "fail") for a, b in pairs]
        tp, fp = sum(a and b for a, b in fail), sum((not a) and b for a, b in fail)
        fn = sum(a and (not b) for a, b in fail)
        judges[name] = {
            "model": rows[0][name], "photos": len(pairs), "agree_with_label": pct(sum(a == b for a, b in pairs), len(pairs)), "kappa_with_label": kappa(pairs),
            "says_pass": pct(sum(b == "pass" for _, b in pairs), len(pairs)), "caught_failures": f"{tp} of {tp + fn}", "false_failures": fp,
            "gave_every_aspect_a_1": sum(r[name + "_all_ones"] == "yes" for r in rows),
        }
    both = [(r["judge_a_level"], r["judge_b_level"]) for r in rows]
    out["reviewers"] = {**judges, "label_says_pass": pct(sum(r["label"] == "pass" for r in rows), len(rows)),
                        "judges_agree_with_each_other": pct(sum(a == b for a, b in both), len(both)), "kappa_between_judges": kappa(both)}

    # 5. the text rule with OCR
    groups = {"ok": [], "garbled_small_print": [], "fail": []}
    for r in rows:
        if r["ocr_readable_recall"] == "":
            continue
        g = "garbled_small_print" if "text_small_garbled" in r["tags"] else ("fail" if r["label"] == "fail" else "ok")
        groups[g].append(float(r["ocr_readable_recall"]))
    out["text_rule"] = {"threshold": OCR_THRESHOLD, **{g: {"photos": len(v), "flagged": sum(x < OCR_THRESHOLD for x in v)} for g, v in groups.items()}}

    # 6. time per photo
    t = {}
    for key in ("1k", "2k", "pro"):
        s = [float(r["seconds"]) for r in rows if config(r) == key and r["seconds"] != ""]
        t[key] = {"photos": len(s), "seconds_avg": round(sum(s) / len(s), 1)} if s else {}
    out["seconds_per_photo"] = t
    return out


def show(s: dict) -> None:
    sp, rv, tr = s["small_print"], s["reviewers"], s["text_rule"]
    print(f"photos {s['photos']} of {len(s['cases'])} products; our labels {s['labels']}")
    print(f"small print (K04, K07): 1K {sp['1k']['garbled']}/{sp['1k']['photos']} garbled, 2K {sp['2k']['garbled']}/{sp['2k']['photos']}, "
          f"repair pass {sp['repair']['garbled']}/{sp['repair']['photos']}, pro model {sp['pro']['garbled']}/{sp['pro']['photos']}")
    for case, d in s["parts"].items():
        print(f"parts, {case}: generic prompt {d['v0']['with_part_defect']}/{d['v0']['photos']} with a part defect, with the product's rules {d['v1']['with_part_defect']}/{d['v1']['photos']} "
              f"(at 2K {d['v1_2k']['with_part_defect']}/{d['v1_2k']['photos']})")
    print(f"dress hem followed the pose photo instead of the product: {s['hem_length']['followed_the_pose_photo']}/{s['hem_length']['photos']} photos")
    lc = s["label_covered"]
    per_case = ", ".join("%s %d/%d" % (c, v["label_covered"], v["photos"]) for c, v in lc["by_case"].items())
    print(f"label covered by fingers: {lc['covered']}/{lc['photos']} photos of products with text ({per_case})")
    for k in ("judge_a", "judge_b"):
        j = rv[k]
        print(f"reviewer {j['model']}: agrees with our label {j['agree_with_label']:.0%} (kappa {j['kappa_with_label']}), says pass {j['says_pass']:.0%} "
              f"(we say {rv['label_says_pass']:.0%}), caught failures {j['caught_failures']}, false failures {j['false_failures']}, "
              f"scored every aspect 1 in {j['gave_every_aspect_a_1']}/{j['photos']}")
    print(f"the two reviewers agree with each other {rv['judges_agree_with_each_other']:.0%} (kappa {rv['kappa_between_judges']})")
    print(f"text rule (OCR, threshold {tr['threshold']}): garbled small print flagged {tr['garbled_small_print']['flagged']}/{tr['garbled_small_print']['photos']}, "
          f"failures {tr['fail']['flagged']}/{tr['fail']['photos']}, good photos flagged {tr['ok']['flagged']}/{tr['ok']['photos']}")
    print("seconds per photo:", s["seconds_per_photo"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=str(RUN / "photos.csv"))
    ap.add_argument("--summary", default=str(RUN / "summary.json"))
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    s = compute(load(Path(a.csv)))
    text = json.dumps(s, indent=2, ensure_ascii=False) + "\n"
    if a.check:
        ok = Path(a.summary).is_file() and json.loads(Path(a.summary).read_text(encoding="utf-8")) == s
        print("summary.json matches photos.csv" if ok else "summary.json is out of date: run  python scripts/recompute_mini_test.py --write", file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    show(s)
    if a.write:
        Path(a.summary).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {a.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
