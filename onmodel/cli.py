"""Command line.

    onmodel score checklist.json          a reviewer's nine answers in, a scorecard out (no model, no key)
    onmodel check product.jpg result.jpg  review one result photo against its product photo
    onmodel analyze product.jpg           suggest tags and a starter prompt for a product photo
    onmodel recipe --verb holding --tags text,hand
    onmodel bench list | fetch | run | judge | report | calibrate | smoke

Exit codes of score and check: 0 = Verified, 1 = not Verified, 2 = error. That makes `onmodel check` usable as a gate in a script or a CI job.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from . import bench as bench_mod
from .analyze import analyze_product
from .check import check_pair
from .engines import load_engine
from .judge import DEFAULT_JUDGE, RUBRIC_VERSION, VERBS, load_vlm, parse_checklist
from .recipes import VARIANTS as RECIPE_VARIANTS
from .recipes import build_prompt, load_recipes
from .scoring import MIN_TOTAL, ChecklistError, advice, render_text, score
from .taxonomy import RISK_TAGS
from .text_rule import get_backend


def _csv(value: str | None) -> list:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def _tags(value: str | None) -> list:
    tags = _csv(value)
    bad = [t for t in tags if t not in RISK_TAGS]
    if bad:
        raise ValueError(f"unknown tags: {', '.join(bad)} (known: {', '.join(RISK_TAGS)})")
    return tags


def _read_text(arg: str) -> str:
    return sys.stdin.read() if arg == "-" else Path(arg).read_text(encoding="utf-8-sig")


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


# ----------------------------------------------------------------------------------------------------------- commands
def cmd_score(a) -> int:
    checklist = parse_checklist(_read_text(a.file))
    card = score(checklist, a.min_total)
    if a.json:
        print(_dump({"scorecard": card.to_dict(), "advice": advice(checklist)}))
    else:
        print(render_text(card, checklist))
    return 0 if card.verified else 1


def cmd_check(a) -> int:
    vlm = load_vlm(a.judge)
    ocr = get_backend(a.ocr, a.ocr_lang)
    rec = check_pair(a.product, a.result, vlm=vlm, pose=a.pose, verb=a.verb, tags=_tags(a.tags), crop=not a.no_crop, note=a.note or "the product",
                     expected_text=a.expect_text, ocr=ocr, min_total=a.min_total)
    if a.out:
        Path(a.out).write_text(_dump(rec), encoding="utf-8")
    if not rec["ok"]:
        print(f"error: the review failed: {rec['error']}", file=sys.stderr)
        return 2
    card = rec["scorecard"]
    if a.json:
        print(_dump(rec))
    else:
        print(f" Product {rec['product']['file']}   Result {rec['result']['file']}   Judge {rec['judge']['name']}   Rubric {RUBRIC_VERSION}")
        print()
        from .scoring import Scorecard
        print(render_text(Scorecard(**card), rec["checklist"]))
        rule = rec["text_rule"]
        if rule:
            found = f"{len(rule['found'])} of {len(rule['expected'])}"
            print(f" Text rule ({rule['source']}): {found} words from the real product are readable in the result"
                  + ("; this made the verdict stricter" if rec["rule_tightened"] else ""))
    return 0 if card["verified"] else 1


def cmd_analyze(a) -> int:
    recipes = load_recipes()
    res = analyze_product(a.product, vlm=load_vlm(a.judge), recipes=recipes)
    if not res["ok"]:
        print(f"error: the analysis failed: {res['error']}", file=sys.stderr)
        return 2
    prompt = build_prompt(recipes, variant=a.prompt, verb=res["verb"], tags=res["tags"]) if a.prompt else None
    if a.json:
        print(_dump({**res, "prompt": prompt}))
        return 0
    print(f" Sub-category  {res['subcategory']}\n Verb          {res['verb']}\n Tags          {', '.join(res['tags']) or 'none'}")
    print(f" Parts         {', '.join(res['parts']) or 'none listed'}")
    print(f" Printed text  {' / '.join(res['text_lines']) or 'none'}")
    if res["notes"]:
        print(f" Notes         {res['notes']}")
    if "text" in res["tags"]:
        print(" Tip           This product carries text: render at 2K or higher and keep the label facing the camera.")
    if prompt:
        print("\n Prompt (" + a.prompt + "):\n" + prompt)
    return 0


def cmd_recipe(a) -> int:
    print(build_prompt(load_recipes(a.recipes), variant=a.variant, verb=a.verb, tags=_tags(a.tags)))
    return 0


def _bench(a) -> Path:
    return bench_mod.find_bench_dir(a.bench)


def _run_dir(bench: Path, name: str) -> Path:
    p = Path(name)
    return p if p.is_absolute() or len(p.parts) > 1 else bench / "runs" / name


def cmd_bench_list(a) -> int:
    rows = bench_mod.list_cases(_bench(a))
    for r in rows:
        where = "bundled" if r["source"] == "bundled" else ("fetched" if r["on_disk"] else "not fetched")
        print(f" {r['id']:<5} {r['class']:<11} {r['license']:<14} {where:<12} {r['name']}")
    print(f"\n {len(rows)} cases")
    if any(r["source"] != "bundled" and not r["on_disk"] for r in rows):
        print(" Linked photos are downloaded and checked by:  onmodel bench fetch")
    return 0


def cmd_bench_fetch(a) -> int:
    bench = _bench(a)
    cases = bench_mod.select_cases(bench_mod.load_cases(bench), _csv(a.cases))
    results = bench_mod.fetch_linked(bench, cases, force=a.force)
    bad = [r for r in results if r["status"] in ("error", "changed")]
    for r in bad:
        print(f" {r['id']}: {r['status']}: {r.get('error', '')}", file=sys.stderr)
    print(f" {sum(r['status'] == 'fetched' for r in results)} fetched, {sum(r['status'] == 'cached' for r in results)} already cached, {len(bad)} problems")
    return 2 if bad else 0


def cmd_bench_run(a) -> int:
    bench = _bench(a)
    cases = bench_mod.select_cases(bench_mod.load_cases(bench), _csv(a.cases))
    engine = load_engine(a.engine)
    jobs = bench_mod.plan_jobs(cases, variants=_csv(a.variants), res_list=[r.lower() for r in _csv(a.res)], samples=a.samples)
    name = a.out or f"{engine.id}-{datetime.now().strftime('%Y%m%d-%H%M')}"
    out = _run_dir(bench, name)
    print(f" run folder: {out}")
    summary = bench_mod.run_generate(bench, jobs, engine, out, recipes=load_recipes(a.recipes), execute=a.yes, budget=a.budget if engine.id != "mock" else None,
                                     workers=a.workers, ratio=a.ratio)
    if a.yes:
        print(f" next: onmodel bench judge --run {out}")
        return 2 if summary["failed"] else 0
    return 0


def cmd_bench_judge(a) -> int:
    bench = _bench(a)
    out = _run_dir(bench, a.run)
    cases = bench_mod.select_cases(bench_mod.load_cases(bench), _csv(a.cases))
    summary = bench_mod.run_judge(bench, out, load_vlm(a.judge), cases=cases, crop=not a.no_crop, ocr=get_backend(a.ocr, a.ocr_lang), min_total=a.min_total, workers=a.workers)
    print(f" next: onmodel bench report --run {out}")
    return 2 if summary["failed"] else 0


def cmd_bench_report(a) -> int:
    out = _run_dir(_bench(a), a.run)
    bench_mod.build_report(out, judge=a.judge)
    print((out / "report.md").read_text(encoding="utf-8"))
    print(f" written: {out / 'report.md'}, {out / 'summary.json'}, {out / 'scores.csv'}")
    return 0


def cmd_bench_calibrate(a) -> int:
    out = _run_dir(_bench(a), a.run)
    r = bench_mod.calibrate(out, a.labels, judge=a.judge)
    g = r["gates"]

    def row(name, label, fmt):
        v = g[name]
        shown = "n/a" if v["value"] is None else fmt(v["value"])
        mark = "-" if v["met"] is None else ("yes" if v["met"] else "no")
        print(f" {label:<26} {shown:>7}   needed {fmt(v['needed']):>6}   met: {mark}")

    pct = lambda x: f"{x:.0%}"  # noqa: E731
    print(f" judge {r['judge']}  |  photos with a label and a review: {r['photos']}  (labelled only {r['labelled_only']}, reviewed only {r['reviewed_only']})")
    row("photos", "photos", lambda x: f"{x:.0f}")
    row("agree_3level", "agreement, 3 levels", pct)
    row("kappa_3level", "kappa, 3 levels", lambda x: f"{x:.2f}")
    row("failure_recall", f"failures caught ({r['failures']['caught']} of {r['failures']['labelled']})", pct)
    row("failure_precision", f"failures that were real", pct)
    row("agree_pass_vs_not", "agreement, pass or not", pct)
    print(f" the reviewer says pass for {pct(r['judge_says_pass'])} of the photos, your labels say {pct(r['labels_say_pass'])}")
    print(" The gates are proposals, not measured thresholds (docs/calibration.md).")
    print(f" written: {out / 'calibration.json'}")
    return 0


def cmd_bench_smoke(a) -> int:
    res = bench_mod.smoke(_bench(a))
    return 0 if res["photos"] and res["reviewed"] == res["photos"] else 1


def cmd_version(_a) -> int:
    print(f"onmodel {__version__} (rubric {RUBRIC_VERSION})")
    return 0


# ----------------------------------------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="onmodel", description="Check whether an AI-generated on-model product photo still shows your product.")
    ap.add_argument("--version", action="version", version=f"onmodel {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("version", help="print the version")
    p.set_defaults(fn=cmd_version)

    p = sub.add_parser("score", help="turn a reviewer's checklist (JSON) into a scorecard; no model, no key")
    p.add_argument("file", help="path to the checklist JSON, or - for stdin")
    p.add_argument("--min-total", type=int, default=MIN_TOTAL)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser("check", help="review one result photo against its product photo")
    p.add_argument("product")
    p.add_argument("result")
    p.add_argument("--pose", help="the pose reference photo the generator was given (adds the pose question)")
    p.add_argument("--verb", choices=VERBS, default="wearing", help="is the person wearing or holding the product")
    p.add_argument("--tags", help=f"comma separated risk tags: {', '.join(RISK_TAGS)}")
    p.add_argument("--judge", default=DEFAULT_JUDGE, help="'mock', a Gemini model name, or package.module:Class")
    p.add_argument("--no-crop", action="store_true", help="skip locating and zooming in on the product")
    p.add_argument("--ocr", default="none", help="'tesseract' to run the text rule with OCR instead of the reviewer's transcription")
    p.add_argument("--ocr-lang", default="eng")
    p.add_argument("--expect-text", help="the words printed on the real product, if you know them")
    p.add_argument("--note", help="a few words naming the product, to help find it in the photo")
    p.add_argument("--min-total", type=int, default=MIN_TOTAL)
    p.add_argument("--json", action="store_true", help="print the full judgment record")
    p.add_argument("--out", help="also write the judgment record to this file")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("analyze", help="suggest the sub-category, risk tags and a starter prompt for a product photo")
    p.add_argument("product")
    p.add_argument("--judge", default=DEFAULT_JUDGE)
    p.add_argument("--prompt", choices=("v0", "v1"), help="also print the starter prompt of this variant")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_analyze)

    p = sub.add_parser("recipe", help="print a starter prompt (no network)")
    p.add_argument("--verb", choices=VERBS, default="wearing")
    p.add_argument("--tags", help="comma separated risk tags")
    p.add_argument("--variant", choices=RECIPE_VARIANTS, default="v1")
    p.add_argument("--recipes", help="your own recipes file, same format as data/starter-recipes.yaml")
    p.set_defaults(fn=cmd_recipe)

    b = sub.add_parser("bench", help="the benchmark: fetch, generate, judge, report")
    b.add_argument("--bench", help="path to the bench folder (default: ./bench, or the one in the cloned repository)")
    bs = b.add_subparsers(dest="bench_cmd", required=True)

    p = bs.add_parser("list", help="list the cases and where each image comes from")
    p.set_defaults(fn=cmd_bench_list)

    p = bs.add_parser("fetch", help="download the linked product images and check them against the recorded sha256")
    p.add_argument("--cases", help="comma separated case ids (default: all)")
    p.add_argument("--force", action="store_true", help="download again even if cached")
    p.set_defaults(fn=cmd_bench_fetch)

    p = bs.add_parser("run", help="generate photos for the cases. A dry run unless you add --yes")
    p.add_argument("--engine", default="gemini-nano-banana-2.1", help="'mock', a Gemini image model name, or package.module:Class")
    p.add_argument("--variants", default="v0,v1", help="recipe variants: v0 (generic), v1 (tag rules), repair (text second pass)")
    p.add_argument("--res", default="1k", help="comma separated resolutions: 1k, 2k")
    p.add_argument("--samples", type=int, default=2, help="photos per case and variant (default 2)")
    p.add_argument("--cases", help="comma separated case ids (default: all)")
    p.add_argument("--out", help="run folder name under bench/runs/ (or a path). Reuse it to resume")
    p.add_argument("--budget", type=float, default=5.0, help="stop starting new calls when the estimated spend reaches this many USD")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--ratio", default="3:4")
    p.add_argument("--recipes", help="your own recipes file")
    p.add_argument("--yes", action="store_true", help="really call the engine (it costs money)")
    p.set_defaults(fn=cmd_bench_run)

    p = bs.add_parser("judge", help="review every photo of a run")
    p.add_argument("--run", required=True, help="run folder name or path")
    p.add_argument("--judge", default=DEFAULT_JUDGE)
    p.add_argument("--cases", help="comma separated case ids (default: all)")
    p.add_argument("--no-crop", action="store_true")
    p.add_argument("--ocr", default="none")
    p.add_argument("--ocr-lang", default="eng")
    p.add_argument("--min-total", type=int, default=MIN_TOTAL)
    p.add_argument("--workers", type=int, default=2)
    p.set_defaults(fn=cmd_bench_judge)

    p = bs.add_parser("report", help="aggregate the reviews of a run into report.md, summary.json and scores.csv")
    p.add_argument("--run", required=True)
    p.add_argument("--judge", help="needed only when the run was reviewed by several judges")
    p.set_defaults(fn=cmd_bench_report)

    p = bs.add_parser("calibrate", help="compare the reviews of a run with labels you made yourself")
    p.add_argument("--run", required=True)
    p.add_argument("--labels", required=True, help="CSV with the columns file,label (label: pass, minor or fail)")
    p.add_argument("--judge", help="needed only when the run was reviewed by several judges")
    p.set_defaults(fn=cmd_bench_calibrate)

    p = bs.add_parser("smoke", help="run the whole pipeline offline with mocks, to check the install")
    p.set_defaults(fn=cmd_bench_smoke)
    return ap


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:   # not a text stream we can reconfigure
            pass
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (bench_mod.BenchError, ChecklistError, RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
