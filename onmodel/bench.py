"""The benchmark: cases, fetching the linked images, generating photos, judging them, and the report.

Everything that costs money is a dry run unless you say so (`--yes`). Everything can run offline with the mock engine and the mock reviewer
(`onmodel bench smoke`), which is what the tests and the CI do.

Layout of a bench folder (bench/ in the repository):
    cases.yaml            the cases: product, tags, pose, printed words, where the image comes from and under which license
    golden/images/        product photos that may be redistributed (CC0 or public domain only)
    poses/                pose reference photos (AI-generated, CC0)
    .cache/               linked images you fetched yourself (never committed)
    runs/<name>/          images/, ledger.jsonl (one line per generation), judgments.jsonl (one line per review), report files
"""
from __future__ import annotations

import concurrent.futures as cf
import csv
import hashlib
import io
import json
import math
import os
import re
import tempfile
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml
from PIL import Image, ImageOps

from . import __version__, safe_http
from .check import check_pair, prompt_sha, sha256_file
from .engines import Engine, MockEngine
from .judge import RUBRIC_VERSION, MockVlm, Vlm
from .recipes import build_prompt, load_recipes
from .scoring import MIN_TOTAL
from .taxonomy import DEFECTS, ITEMS

LEDGER_SCHEMA_ID = "onmodel/run-record@1"
RUN_SCHEMA_ID = "onmodel/run@1"
VARIANTS = ("v0", "v1", "repair")
RESOLUTIONS = ("1k", "2k")
NAME_RE = re.compile(r"^(?P<case>[A-Za-z0-9]+)_(?P<variant>v0|v1|repair)_(?P<res>\d+k)_s(?P<sample>\d+)\.jpg$")
MAX_SIDE_SAVED = 2048
SMALL_CELL = 20


class BenchError(RuntimeError):
    """Something the user can fix: a missing folder, an image that was not fetched, a budget that cannot be enforced."""


# ----------------------------------------------------------------------------------------------------------- cases
@dataclass(frozen=True)
class Case:
    id: str
    name: str
    subcategory: str
    verb: str
    tags: tuple
    klass: str
    pose: str
    text_gt: tuple
    source: dict

    @property
    def bundled(self) -> bool:
        return self.source.get("kind") == "bundled"


def find_bench_dir(explicit=None) -> Path:
    """--bench, then $ONMODEL_BENCH, then ./bench, then the bench/ next to the package (a clone of the repository)."""
    for c in (explicit, os.environ.get("ONMODEL_BENCH"), Path.cwd() / "bench", Path(__file__).resolve().parent.parent / "bench"):
        if c and (Path(c) / "cases.yaml").is_file():
            return Path(c).resolve()
    raise BenchError("no bench folder found. Run this from a clone of the repository (git clone https://github.com/molly554/onmodel), "
                     "or pass --bench PATH, or set ONMODEL_BENCH.")


def load_cases(bench: Path) -> list:
    data = yaml.safe_load((Path(bench) / "cases.yaml").read_text(encoding="utf-8"))
    out, seen = [], set()
    for raw in data.get("cases", []):
        if raw["id"] in seen:
            raise BenchError(f"duplicate case id: {raw['id']}")
        seen.add(raw["id"])
        out.append(Case(id=raw["id"], name=raw["name"], subcategory=raw["subcategory"], verb=raw["verb"], tags=tuple(raw.get("tags") or ()),
                        klass=raw.get("klass", ""), pose=raw["pose"], text_gt=tuple(raw.get("text_gt") or ()), source=dict(raw["source"])))
    return out


def select_cases(cases: list, ids=None) -> list:
    if not ids:
        return list(cases)
    by_id = {c.id: c for c in cases}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise BenchError(f"unknown case id: {', '.join(unknown)} (known: {', '.join(by_id)})")
    return [by_id[i] for i in ids]


def product_path(bench: Path, case: Case):
    """The product photo on disk, or None when it is a linked image that has not been fetched yet."""
    if case.bundled:
        p = Path(bench) / case.source["file"]
        return p if p.is_file() else None
    p = Path(bench) / ".cache" / f"{case.id}.jpg"
    return p if p.is_file() else None


def require_product(bench: Path, case: Case) -> Path:
    p = product_path(bench, case)
    if p is None:
        raise BenchError(f"the product photo of {case.id} is not on disk. It is a linked image: run  onmodel bench fetch --cases {case.id}")
    return p


def pose_path(bench: Path, case: Case) -> Path:
    p = Path(bench) / "poses" / f"{case.pose}.jpg"
    if not p.is_file():
        raise BenchError(f"pose photo not found: {p}")
    return p


def list_cases(bench: Path) -> list:
    rows = []
    for c in load_cases(bench):
        rows.append({"id": c.id, "name": c.name, "class": c.klass, "tags": list(c.tags), "source": c.source.get("kind"),
                     "license": c.source.get("license", ""), "on_disk": product_path(bench, c) is not None})
    return rows


# ----------------------------------------------------------------------------------------------------------- images
def save_jpeg(raw: bytes, dst: Path, max_side: int = MAX_SIDE_SAVED) -> tuple:
    """Decode untrusted image bytes, drop metadata, limit the long edge and write a JPEG. Returns the saved size."""
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    s = max_side / max(im.size)
    if s < 1:
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "JPEG", quality=92, optimize=True)
    return im.size


def path_to_jpeg(path, max_side: int):
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    s = max_side / max(im.size)
    if s < 1:
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue(), "image/jpeg"


# ----------------------------------------------------------------------------------------------------------- fetch
def fetch_linked(bench: Path, cases: list, *, get=None, force: bool = False, log=print) -> list:
    """Download the linked images into bench/.cache/. Each file is checked against the sha256 recorded in cases.yaml,
    so a changed or replaced file is refused instead of silently measured. Bundled cases are left alone."""
    get = get or safe_http.get_image_bytes
    cache = Path(bench) / ".cache"
    results = []
    for c in cases:
        if c.bundled:
            continue
        dst = cache / f"{c.id}.jpg"
        if dst.exists() and not force:
            results.append({"id": c.id, "status": "cached"})
            continue
        try:
            raw, _ctype = get(c.source["url"])
        except Exception as e:   # network, allow-list, size cap, not an image
            results.append({"id": c.id, "status": "error", "error": f"{type(e).__name__}: {e}"})
            log(f"  {c.id}: could not download ({type(e).__name__}: {e})")
            continue
        digest = hashlib.sha256(raw).hexdigest()
        want = c.source.get("sha256_source")
        if want and digest != want:
            results.append({"id": c.id, "status": "changed", "error": f"the file at the URL changed (sha256 {digest[:12]}..., expected {want[:12]}...); not used"})
            log(f"  {c.id}: the file at the URL changed; not used")
            continue
        try:
            size = save_jpeg(raw, dst)
        except Exception as e:
            results.append({"id": c.id, "status": "error", "error": f"could not decode the image: {type(e).__name__}: {e}"})
            continue
        saved = sha256_file(dst)
        recorded = c.source.get("sha256_saved")
        results.append({"id": c.id, "status": "fetched", "size": list(size), "sha256_saved": saved,
                        "same_bytes_as_recorded": (saved == recorded) if recorded else None})
        log(f"  {c.id}: fetched {size[0]}x{size[1]}")
    return results


# ----------------------------------------------------------------------------------------------------------- generate
@dataclass(frozen=True)
class Job:
    case: Case
    variant: str
    res: str
    sample: int

    @property
    def file(self) -> str:
        return f"{self.case.id}_{self.variant}_{self.res}_s{self.sample}.jpg"


def plan_jobs(cases: list, variants=("v0", "v1"), res_list=("1k",), samples: int = 1) -> list:
    for v in variants:
        if v not in VARIANTS:
            raise BenchError(f"unknown recipe variant: {v} (use {', '.join(VARIANTS)})")
    for r in res_list:
        if r not in RESOLUTIONS:
            raise BenchError(f"unknown resolution: {r} (use {', '.join(RESOLUTIONS)})")
    jobs = []
    for c in cases:
        for v in variants:
            if v == "repair" and "text" not in c.tags:
                continue   # only products that carry text get a text repair pass
            for r in res_list:
                for s in range(1, samples + 1):
                    jobs.append(Job(c, v, r, s))
    return jobs


def _est(engine: Engine, res: str):
    try:
        return engine.estimate_cost(res)
    except (KeyError, AttributeError, NotImplementedError):
        return None


def estimate(engine: Engine, jobs: list):
    """(low, high) in USD for these jobs, or (None, None) when the engine cannot say."""
    lo = hi = 0.0
    for j in jobs:
        e = _est(engine, j.res)
        if e is None:
            return None, None
        lo, hi = lo + e[0], hi + e[1]
    return lo, hi


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append_jsonl(path: Path, rec: dict, lock) -> None:
    with lock, open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_jsonl(path: Path) -> list:
    path = Path(path)
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def run_generate(bench: Path, jobs: list, engine: Engine, out_dir, *, recipes: dict, execute: bool = False, budget: float | None = None,
                 workers: int = 2, ratio: str = "3:4", log=print) -> dict:
    """Generate the photos of the jobs into out_dir/images/. A dry run (execute=False) only prints the plan and the estimated cost.
    Photos already on disk are skipped, so a run can be repeated or resumed."""
    out_dir = Path(out_dir)
    images = out_dir / "images"
    todo = [j for j in jobs if not (images / j.file).exists()]
    lo, hi = estimate(engine, todo)
    cost = "unknown" if lo is None else (f"${lo:.2f}-${hi:.2f}" if hi else "free")
    summary = {"planned": len(jobs), "to_generate": len(todo), "on_disk": len(jobs) - len(todo), "estimate_lo": lo, "estimate_hi": hi,
               "executed": False, "done": 0, "failed": [], "spent_lo": 0.0, "spent_hi": 0.0, "stopped_by_budget": False}
    log(f"engine {engine.id} | planned {len(jobs)} | to generate {len(todo)} | on disk {len(jobs) - len(todo)} | estimated cost {cost}")
    if not execute:
        for j in todo:
            log(f"   would generate {j.file}")
        log("(dry run: nothing was sent. Add --yes to run.)")
        return summary
    if budget and lo is None:
        raise BenchError("the engine gave no cost estimate, so --budget cannot be enforced. Drop --budget or add estimate_cost() to the engine.")
    if getattr(engine, "max_reference_images", 2) < 2:
        raise BenchError("the benchmark sends two reference images (product, pose); this engine accepts fewer")
    ready = getattr(engine, "check_ready", None)
    if ready:
        ready()   # e.g. a missing API key: say so once, before any job runs
    for j in todo:   # fail before any money is spent
        require_product(bench, j.case)
        pose_path(bench, j.case)
    images.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "run.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {"created": _now()}
    meta.update(schema=RUN_SCHEMA_ID, onmodel_version=__version__, engine=engine.id, recipes_version=recipes.get("version"), ratio=ratio,
                variants=sorted({j.variant for j in jobs}), resolutions=sorted({j.res for j in jobs}), cases=sorted({j.case.id for j in jobs}),
                updated=_now())
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    lock, ledger = threading.Lock(), out_dir / "ledger.jsonl"
    state = {"reserved": 0.0, "stop": False}

    def refs_for(job: Job):
        prod = path_to_jpeg(require_product(bench, job.case), 1536)
        if job.variant == "repair":
            first = images / f"{job.case.id}_v1_{job.res}_s{job.sample}.jpg"
            if not first.exists():
                raise BenchError(f"the v1 photo to repair is missing: {first.name}")
            return [prod, path_to_jpeg(first, 1280)]
        return [prod, path_to_jpeg(pose_path(bench, job.case), 1280)]

    def one(job: Job):
        est = _est(engine, job.res)
        est_hi = est[1] if est else 0.0
        with lock:
            if budget and state["reserved"] + est_hi > budget:
                state["stop"] = True
            if state["stop"]:
                return
            state["reserved"] += est_hi
        prompt = build_prompt(recipes, variant=job.variant, verb=job.case.verb, tags=job.case.tags)
        gen, err = None, ""
        try:
            refs = refs_for(job)
            gen = engine.generate(prompt, refs, res=job.res, ratio=ratio)
        except Exception as e:   # one bad call must not end the run
            err = f"{type(e).__name__}: {e}"
        rec = {"schema": LEDGER_SCHEMA_ID, "file": job.file, "case": job.case.id, "variant": job.variant, "res": job.res, "sample": job.sample,
               "ratio": ratio, "engine": engine.id, "stamp": gen.stamp if gen else {}, "recipe_version": recipes.get("version"),
               "prompt_sha": prompt_sha(prompt), "prompt": prompt, "pose": job.case.pose,
               "ok": bool(gen and gen.ok), "error": (gen.error if gen else err), "seconds": gen.seconds if gen else 0.0,
               "cost_lo": gen.cost_lo if gen else None, "cost_hi": gen.cost_hi if gen else None, "usage": gen.usage if gen else {},
               "onmodel_version": __version__, "ts": _now()}
        with lock:
            actual_hi = (gen.cost_hi if gen and gen.cost_hi is not None else est_hi)
            state["reserved"] += actual_hi - est_hi
            summary["spent_hi"] += actual_hi
            summary["spent_lo"] += (gen.cost_lo if gen and gen.cost_lo is not None else 0.0)
        _append_jsonl(ledger, rec, lock)
        if not rec["ok"]:
            summary["failed"].append(job.file)
            log(f"  {job.file}: FAILED {rec['error'][:160]}")
            return
        Image.open(io.BytesIO(gen.image)).convert("RGB").save(images / job.file, "JPEG", quality=93)
        summary["done"] += 1
        log(f"  {job.file} ok  {gen.seconds}s")

    first = [j for j in todo if j.variant != "repair"]
    second = [j for j in todo if j.variant == "repair"]   # a repair pass needs the v1 photo of the same sample
    t0 = time.time()
    for batch in (first, second):
        with cf.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            list(ex.map(one, batch))
    summary["executed"] = True
    summary["stopped_by_budget"] = state["stop"]
    log(f"done in {time.time() - t0:.0f}s | generated {summary['done']} | failed {len(summary['failed'])} | estimated spend up to ${summary['spent_hi']:.2f}")
    if state["stop"]:
        log(f"STOPPED by the budget guard (${budget:.2f}). Run again with the same --out to continue.")
    return summary


# ----------------------------------------------------------------------------------------------------------- judge
def run_judge(bench: Path, out_dir, vlm: Vlm, *, cases: list | None = None, crop: bool = True, ocr=None, use_text_gt: bool = True,
              min_total: int = MIN_TOTAL, workers: int = 2, log=print) -> dict:
    """Review every photo in out_dir/images/ and append a record to out_dir/judgments.jsonl. Photos already reviewed by this judge
    (same file, same bytes, same rubric version) are skipped; failed reviews are retried."""
    out_dir = Path(out_dir)
    by_id = {c.id: c for c in (cases or load_cases(bench))}
    files = sorted(p for p in (out_dir / "images").glob("*.jpg") if (m := NAME_RE.match(p.name)) and m["case"] in by_id)
    path = out_dir / "judgments.jsonl"
    done = {(r["result"]["file"], r["result"]["sha256"], r["judge"]["name"], r["rubric_version"]) for r in load_jsonl(path) if r.get("ok")}
    todo = [p for p in files if (p.name, sha256_file(p), vlm.name, RUBRIC_VERSION) not in done]
    summary = {"photos": len(files), "to_review": len(todo), "reviewed": 0, "failed": []}
    log(f"judge {vlm.name} | photos {len(files)} | to review {len(todo)} | already reviewed {len(files) - len(todo)}")
    for p in todo:   # fail before any review is paid for
        require_product(bench, by_id[NAME_RE.match(p.name)["case"]])
    lock = threading.Lock()

    def one(p: Path):
        m = NAME_RE.match(p.name)
        case = by_id[m["case"]]
        try:
            rec = check_pair(product_path(bench, case), p, vlm=vlm, pose=pose_path(bench, case), verb=case.verb, tags=case.tags, crop=crop,
                             note=case.name, expected_text=list(case.text_gt) if (use_text_gt and case.text_gt) else None, ocr=ocr, min_total=min_total)
        except Exception as e:   # one bad review must not end the run
            rec = {"ok": False, "error": f"{type(e).__name__}: {e}", "result": {"file": p.name, "sha256": sha256_file(p)}, "judge": {"name": vlm.name},
                   "rubric_version": RUBRIC_VERSION}
        rec.update(file=p.name, case=case.id, variant=m["variant"], res=m["res"], sample=int(m["sample"]), ts=_now())
        _append_jsonl(path, rec, lock)
        if rec["ok"]:
            summary["reviewed"] += 1
            card = rec["scorecard"]
            log(f"  {p.name}: {card['total']} / 10  {'Verified' if card['verified'] else 'not verified'}")
        else:
            summary["failed"].append(p.name)
            log(f"  {p.name}: review failed ({rec['error'][:160]})")

    with cf.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(one, todo))
    return summary


# ----------------------------------------------------------------------------------------------------------- report
def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    """95% interval for a proportion k / n. Honest about small samples: 3 of 4 is somewhere between 30% and 95%."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - m) / d), min(1.0, (c + m) / d)


def _cell_key(r: dict) -> str:
    return f"{r['variant']}@{r['res']}"


def build_report(out_dir, judge: str | None = None) -> dict:
    """Aggregate out_dir/judgments.jsonl into summary.json, scores.csv and report.md. Returns the summary."""
    out_dir = Path(out_dir)
    rows = [r for r in load_jsonl(out_dir / "judgments.jsonl") if r.get("ok")]
    if not rows:
        raise BenchError(f"no reviews found in {out_dir / 'judgments.jsonl'}. Run  onmodel bench judge --run {out_dir}")
    judges = sorted({r["judge"]["name"] for r in rows})
    if judge is None:
        if len(judges) > 1:
            raise BenchError(f"several judges found ({', '.join(judges)}); choose one with --judge")
        judge = judges[0]
    elif judge not in judges:
        raise BenchError(f"no reviews by {judge}; found: {', '.join(judges)}")
    latest = {}   # a photo reviewed twice counts once: the latest review wins
    for r in rows:
        if r["judge"]["name"] == judge:
            latest[r["file"]] = r
    rows = list(latest.values())

    cells, cases = {}, {}
    for r in rows:
        card = r["scorecard"]
        cell = cells.setdefault(_cell_key(r), {"n": 0, "verified": 0, "fidelity_2": 0, "total_sum": 0, "veto": {}, "defects": {}, "answers_different": {},
                                               "unverifiable": 0, "rule_tightened": 0})
        cell["n"] += 1
        cell["verified"] += bool(card["verified"])
        cell["fidelity_2"] += card["dims"]["fidelity"] == 2
        cell["total_sum"] += card["total"]
        cell["unverifiable"] += bool(card["unverifiable"])
        cell["rule_tightened"] += bool(r.get("rule_tightened"))
        for code in card["veto"]:
            cell["veto"][code] = cell["veto"].get(code, 0) + 1
        for d in r["checklist"]["defects"]:
            cell["defects"][d["code"]] = cell["defects"].get(d["code"], 0) + 1
        for k in ITEMS:
            if r["checklist"]["items"][k]["answer"] == "different":
                cell["answers_different"][k] = cell["answers_different"].get(k, 0) + 1
        cases.setdefault(r["case"], {}).setdefault(_cell_key(r), []).append(bool(card["verified"]))
    for cell in cells.values():
        lo, hi = wilson(cell["verified"], cell["n"])
        cell.update(verified_rate=round(cell["verified"] / cell["n"], 3), ci95=[round(lo, 3), round(hi, 3)], mean_total=round(cell["total_sum"] / cell["n"], 2))
        del cell["total_sum"]

    meta = json.loads((out_dir / "run.json").read_text(encoding="utf-8")) if (out_dir / "run.json").is_file() else {}
    summary = {"schema": "onmodel/report@1", "onmodel_version": __version__, "rubric_version": RUBRIC_VERSION, "generated": _now(), "run": meta,
               "judge": judge, "photos": len(rows), "directional_only": any(c["n"] < SMALL_CELL for c in cells.values()),
               "cells": dict(sorted(cells.items())), "cases": {k: {c: {"verified": sum(v), "n": len(v)} for c, v in sorted(cs.items())} for k, cs in sorted(cases.items())}}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    with open(out_dir / "scores.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "case", "variant", "res", "sample", "judge", "total", "fidelity", "pose", "identity", "artifacts", "scale", "verified", "veto", "defects"])
        for r in sorted(rows, key=lambda r: r["file"]):
            c = r["scorecard"]
            w.writerow([r["file"], r["case"], r["variant"], r["res"], r["sample"], judge, c["total"], c["dims"]["fidelity"], c["dims"]["pose"], c["dims"]["identity"],
                        c["dims"]["artifacts"], c["dims"]["scale"], int(c["verified"]), " ".join(c["veto"]), " ".join(d["code"] for d in r["checklist"]["defects"])])
    (out_dir / "report.md").write_text(render_report_md(summary), encoding="utf-8")
    return summary


def render_report_md(s: dict) -> str:
    L = [f"# onmodel bench report", "",
         f"- Judge: `{s['judge']}`   Rubric: `{s['rubric_version']}`   onmodel `{s['onmodel_version']}`",
         f"- Engine: `{s['run'].get('engine', 'unknown')}`   Photos reviewed: {s['photos']}", ""]
    if s["directional_only"]:
        L += [f"> Directional only. At least one cell has fewer than {SMALL_CELL} photos, so the intervals are wide. "
              "Read differences as hints to investigate, not as results.", ""]
    L += ["## Verified rate by recipe and resolution", "", "| Cell | Photos | Verified | Rate | 95% interval | Mean total | Could not tell |", "|---|---|---|---|---|---|---|"]
    for k, c in s["cells"].items():
        L.append(f"| {k} | {c['n']} | {c['verified']} | {c['verified_rate']:.0%} | {c['ci95'][0]:.0%} to {c['ci95'][1]:.0%} | {c['mean_total']} / 10 | {c['unverifiable']} |")
    L += ["", "## What went wrong", "", "| Cell | Defect | Photos |", "|---|---|---|"]
    any_defect = False
    for k, c in s["cells"].items():
        for code, n in sorted(c["defects"].items(), key=lambda kv: (-kv[1], kv[0])):
            L.append(f"| {k} | `{code}`{' (veto)' if DEFECTS[code]['veto'] else ''} | {n} |")
            any_defect = True
    if not any_defect:
        L.append("| all | none reported | 0 |")
    tightened = sum(c["rule_tightened"] for c in s["cells"].values())
    if tightened:
        L += ["", f"The text rule made {tightened} verdict(s) stricter (printed words from the real product were not readable in the result)."]
    cell_keys = list(s["cells"])
    L += ["", "## By case (verified / photos)", "", "| Case | " + " | ".join(cell_keys) + " |", "|---|" + "---|" * len(cell_keys)]
    for cid, per in s["cases"].items():
        L.append(f"| {cid} | " + " | ".join(f"{per[k]['verified']} / {per[k]['n']}" if k in per else "-" for k in cell_keys) + " |")
    L += ["", "Scores come from a model reviewer's checklist answers turned into points by code (`onmodel/scoring.py`). "
              "A reviewer can be wrong; see docs/calibration.md for how to check it against your own labels.", ""]
    return "\n".join(L)


# ----------------------------------------------------------------------------------------------------------- smoke
def smoke(bench: Path, log=print) -> dict:
    """The whole pipeline, offline: mock engine, mock reviewer, the bundled cases. Proves the install works; says nothing about quality.

    The mock reviewer answers "same" to everything and reads no text, so the text rule flags the one bundled product that has printed words.
    That is the expected result: it shows the rule biting."""
    cases = [c for c in load_cases(bench) if c.bundled and product_path(bench, c)]
    if not cases:
        raise BenchError("no bundled cases found in the bench folder")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "smoke"
        jobs = plan_jobs(cases, variants=("v0", "v1"), res_list=("1k",), samples=1)
        quiet = lambda *_a, **_k: None   # noqa: E731
        gen = run_generate(bench, jobs, MockEngine(), out, recipes=load_recipes(), execute=True, workers=1, log=quiet)
        jud = run_judge(bench, out, MockVlm(), cases=cases, workers=1, log=quiet)
        rep = build_report(out)
    verified = sum(c["verified"] for c in rep["cells"].values())
    result = {"cases": len(cases), "photos": rep["photos"], "generated": gen["done"], "reviewed": jud["reviewed"], "verified": verified,
              "not_verified": rep["photos"] - verified, "text_rule_tightened": sum(c["rule_tightened"] for c in rep["cells"].values())}
    log(f"smoke: {result['cases']} cases, {result['photos']} photos generated and reviewed offline; "
        f"{result['verified']} verified, {result['not_verified']} not verified ({result['text_rule_tightened']} by the text rule, as expected)")
    return result


# ----------------------------------------------------------------------------------------------------------- calibration
LEVELS = ("pass", "minor", "fail")
# Proposed gates for trusting a reviewer enough to publish its numbers. They are proposals, not measured thresholds: see docs/calibration.md.
GATES = {"photos": 150, "agree_3level": 0.75, "kappa_3level": 0.6, "failure_recall": 0.9, "failure_precision": 0.6, "agree_pass_vs_not": 0.85}


def judge_level(card: dict) -> str:
    """The three-level verdict of a scorecard: pass = Verified; fail = product fidelity 0 or a veto defect; minor = anything in between."""
    if card["verified"]:
        return "pass"
    if card["dims"]["fidelity"] == 0 or card["veto"]:
        return "fail"
    return "minor"


def cohen_kappa(pairs: list) -> float:
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (round((po - pe) / (1 - pe), 2) + 0.0) if pe < 1 else 1.0      # + 0.0 turns -0.0 into 0.0


def load_labels(path) -> dict:
    """A CSV with the columns file and label (pass, minor or fail), one row per photo you labelled yourself."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows or "file" not in rows[0] or "label" not in rows[0]:
        raise BenchError("the labels file needs the columns: file,label")
    out = {}
    for r in rows:
        if r["label"] not in LEVELS:
            raise BenchError(f"the label of {r['file']} must be one of {', '.join(LEVELS)} (got {r['label']!r})")
        out[Path(r["file"]).name] = r["label"]
    return out


def calibrate(out_dir, labels_csv, judge: str | None = None) -> dict:
    """Compare the reviews of a run with labels you made yourself. Writes calibration.json next to the run."""
    out_dir = Path(out_dir)
    labels = load_labels(labels_csv)
    rows = [r for r in load_jsonl(out_dir / "judgments.jsonl") if r.get("ok")]
    judges = sorted({r["judge"]["name"] for r in rows})
    if not judges:
        raise BenchError(f"no reviews found in {out_dir / 'judgments.jsonl'}. Run  onmodel bench judge --run {out_dir}")
    if judge is None:
        if len(judges) > 1:
            raise BenchError(f"several judges found ({', '.join(judges)}); choose one with --judge")
        judge = judges[0]
    elif judge not in judges:
        raise BenchError(f"no reviews by {judge}; found: {', '.join(judges)}")
    latest = {r["file"]: r for r in rows if r["judge"]["name"] == judge}
    common = sorted(set(labels) & set(latest))
    if not common:
        raise BenchError("no photo has both a label and a review. The file names in the labels file must match the files in the run's images/ folder")
    pairs = [(labels[f], judge_level(latest[f]["scorecard"])) for f in common]
    n = len(pairs)
    fails = [(a == "fail", b == "fail") for a, b in pairs]
    tp, fp = sum(a and b for a, b in fails), sum((not a) and b for a, b in fails)
    fn = sum(a and (not b) for a, b in fails)
    passes = [(a == "pass", b == "pass") for a, b in pairs]
    agree3, agree_pass = sum(a == b for a, b in pairs) / n, sum(a == b for a, b in passes) / n
    recall = tp / (tp + fn) if tp + fn else None
    precision = tp / (tp + fp) if tp + fp else None
    values = {"photos": n, "agree_3level": agree3, "kappa_3level": cohen_kappa(pairs), "failure_recall": recall, "failure_precision": precision, "agree_pass_vs_not": agree_pass}
    gates = {k: {"value": None if values[k] is None else round(values[k], 2), "needed": need, "met": None if values[k] is None else values[k] >= need} for k, need in GATES.items()}
    result = {"schema": "onmodel/calibration@1", "judge": judge, "rubric_version": RUBRIC_VERSION, "photos": n, "labelled_only": len(set(labels) - set(latest)),
              "reviewed_only": len(set(latest) - set(labels)), "agree_3level": round(agree3, 2), "kappa_3level": values["kappa_3level"],
              "agree_pass_vs_not": round(agree_pass, 2), "failures": {"labelled": tp + fn, "caught": tp, "false_alarms": fp},
              "judge_says_pass": round(sum(b for _, b in passes) / n, 2), "labels_say_pass": round(sum(a for a, _ in passes) / n, 2),
              "confusion": {f"{a}->{b}": c for (a, b), c in sorted(Counter(pairs).items())}, "gates": gates}
    (out_dir / "calibration.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return result
