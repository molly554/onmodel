import hashlib
import io
import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from PIL import Image

from onmodel import bench as B
from onmodel.engines import Generation, MockEngine
from onmodel.judge import MockVlm, VlmResult
from onmodel.recipes import load_recipes
from onmodel.schemas import cases_schema, run_record_schema
from onmodel.taxonomy import SUBCATEGORIES

from conftest import Scripted, make_checklist, make_image

R = load_recipes()


# ----------------------------------------------------------------------------------------------------------- helpers
def sha(path_or_bytes):
    data = path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).read_bytes()
    return hashlib.sha256(data).hexdigest()


def make_bench(root: Path, linked_bytes: bytes | None = None) -> Path:
    """A small bench: two bundled cases (one carries text) and, optionally, one linked case."""
    b = root / "bench"
    (b / "golden" / "images").mkdir(parents=True)
    (b / "poses").mkdir()
    cases = []
    for cid, tags, sub, verb in (("T1", ["text", "hand"], "Lipstick", "holding"), ("N1", ["metal"], "Necklaces", "wearing")):
        img = make_image(b / "golden" / "images" / f"{cid}.jpg", (80, 100), (30, 60, 90))
        make_image(b / "poses" / f"pose-{cid}.jpg", (60, 80), (200, 200, 200))
        cases.append({"id": cid, "name": f"case {cid}", "subcategory": sub, "verb": verb, "tags": tags, "klass": "t", "pose": f"pose-{cid}", "text_gt": [],
                      "source": {"kind": "bundled", "file": f"golden/images/{cid}.jpg", "page": "https://example.org/p", "license": "CC0", "author": "t", "sha256": sha(img)}})
    if linked_bytes is not None:
        make_image(b / "poses" / "pose-L1.jpg", (60, 80), (200, 200, 200))
        cases.append({"id": "L1", "name": "linked", "subcategory": "Rings", "verb": "wearing", "tags": ["metal"], "klass": "t", "pose": "pose-L1", "text_gt": [],
                      "source": {"kind": "linked", "url": "https://upload.wikimedia.org/x.jpg", "page": "https://example.org/l", "license": "CC BY-SA 4.0",
                                 "author": "t", "sha256_source": sha(linked_bytes)}})
    (b / "cases.yaml").write_text(yaml.safe_dump({"version": 1, "cases": cases}), encoding="utf-8")
    return b


def jpeg_bytes(size=(3000, 1500), color=(9, 9, 9)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


class FakeEngine:
    id = "fake"
    max_reference_images = 2

    def __init__(self, cost=(0.04, 0.05), fail_first=False, no_estimate=False):
        self.cost, self.fail_first, self.no_estimate, self.calls = cost, fail_first, no_estimate, []

    def estimate_cost(self, res, n=1):
        if self.no_estimate:
            raise KeyError(res)
        return self.cost

    def generate(self, prompt, refs, *, res="1k", ratio="3:4"):
        self.calls.append({"prompt": prompt, "refs": len(refs), "res": res})
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError("boom")
        return Generation(ok=True, image=jpeg_bytes((30, 40)), mime="image/jpeg", cost_lo=0.04, cost_hi=0.05, seconds=0.1, stamp={"engine": "fake"})


quiet = lambda *a, **k: None  # noqa: E731


# ----------------------------------------------------------------------------------------------------------- the bundled benchmark
def test_the_repository_bench_is_well_formed(bench_dir):
    data = yaml.safe_load((bench_dir / "cases.yaml").read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(cases_schema()).iter_errors(data))
    cases = B.load_cases(bench_dir)
    assert [c.id for c in cases] == ["K04", "J01", "A02", "A04", "K01", "K07", "K10", "G02", "J03"]
    for c in cases:
        assert c.subcategory in SUBCATEGORIES and B.pose_path(bench_dir, c).is_file()
        if c.bundled:
            assert c.source["license"] in ("CC0", "Public domain") and sha(B.product_path(bench_dir, c)) == c.source["sha256"]
        else:
            assert B.product_path(bench_dir, c) is None or (bench_dir / ".cache" / f"{c.id}.jpg").exists()
    assert sum(c.bundled for c in cases) == 4 and any("text" in c.tags for c in cases if c.bundled)


def test_list_and_select_cases(bench_dir):
    rows = B.list_cases(bench_dir)
    assert len(rows) == 9 and rows[0]["id"] == "K04" and rows[0]["on_disk"]
    cases = B.load_cases(bench_dir)
    assert [c.id for c in B.select_cases(cases, ["J01", "K04"])] == ["J01", "K04"]
    with pytest.raises(B.BenchError, match="unknown case id: Z9"):
        B.select_cases(cases, ["Z9"])


def test_smoke_runs_the_whole_pipeline_offline(bench_dir):
    res = B.smoke(bench_dir, log=quiet)
    assert res == {"cases": 4, "photos": 8, "generated": 8, "reviewed": 8, "verified": 6, "not_verified": 2, "text_rule_tightened": 2}


def test_find_bench_dir_order(tmp_path, monkeypatch):
    b = make_bench(tmp_path)
    monkeypatch.delenv("ONMODEL_BENCH", raising=False)
    assert B.find_bench_dir(b) == b.resolve()
    monkeypatch.setenv("ONMODEL_BENCH", str(b))
    assert B.find_bench_dir() == b.resolve()
    monkeypatch.delenv("ONMODEL_BENCH")
    monkeypatch.chdir(tmp_path)
    assert B.find_bench_dir() == b.resolve()


# ----------------------------------------------------------------------------------------------------------- planning and maths
def test_plan_jobs_gives_a_repair_pass_only_to_products_with_text(tmp_path):
    cases = B.load_cases(make_bench(tmp_path))
    jobs = B.plan_jobs(cases, variants=("v0", "v1", "repair"), res_list=("1k", "2k"), samples=2)
    assert len(jobs) == 2 * 2 * 2 + 2 * 2 * 2 + 1 * 2 * 2                  # T1: v0, v1, repair; N1: v0, v1
    assert {j.case.id for j in jobs if j.variant == "repair"} == {"T1"}
    assert jobs[0].file == "T1_v0_1k_s1.jpg" and B.NAME_RE.match(jobs[0].file)
    with pytest.raises(B.BenchError, match="variant"):
        B.plan_jobs(cases, variants=("v9",))
    with pytest.raises(B.BenchError, match="resolution"):
        B.plan_jobs(cases, res_list=("8k",))


def test_wilson_interval():
    assert B.wilson(0, 0) == (0.0, 1.0)
    lo, hi = B.wilson(3, 4)
    assert round(lo, 2) == 0.30 and round(hi, 2) == 0.95
    lo, hi = B.wilson(10, 10)
    assert round(lo, 2) == 0.72 and hi == 1.0
    assert B.wilson(0, 10)[0] == 0.0 and B.wilson(5, 10)[0] < 0.5 < B.wilson(5, 10)[1]


# ----------------------------------------------------------------------------------------------------------- fetch
def test_fetch_linked_verifies_the_hash_reencodes_and_caches(tmp_path):
    raw = jpeg_bytes()
    b = make_bench(tmp_path, raw)
    cases = B.load_cases(b)
    seen = []
    get = lambda url: (seen.append(url) or (raw, "image/jpeg"))  # noqa: E731
    res = B.fetch_linked(b, cases, get=get, log=quiet)
    assert [r["status"] for r in res] == ["fetched"] and res[0]["size"] == [2048, 1024] and res[0]["same_bytes_as_recorded"] is None
    assert Image.open(b / ".cache" / "L1.jpg").size == (2048, 1024) and seen == ["https://upload.wikimedia.org/x.jpg"]
    assert [r["status"] for r in B.fetch_linked(b, cases, get=get, log=quiet)] == ["cached"] and len(seen) == 1
    assert B.require_product(b, cases[2]) == b / ".cache" / "L1.jpg"


def test_fetch_linked_refuses_a_changed_file(tmp_path):
    b = make_bench(tmp_path, jpeg_bytes())
    res = B.fetch_linked(b, B.load_cases(b), get=lambda url: (jpeg_bytes(color=(200, 0, 0)), "image/jpeg"), log=quiet)
    assert res[0]["status"] == "changed" and "not used" in res[0]["error"] and not (b / ".cache" / "L1.jpg").exists()


def test_fetch_linked_reports_download_and_decode_errors(tmp_path):
    junk = b"not an image at all"
    b = make_bench(tmp_path, junk)
    def boom(url): raise ValueError("host is not on the allow-list")
    assert B.fetch_linked(b, B.load_cases(b), get=boom, log=quiet)[0]["status"] == "error"
    res = B.fetch_linked(b, B.load_cases(b), get=lambda url: (junk, "image/jpeg"), log=quiet)   # the hash matches, the bytes are not a picture
    assert res[0]["status"] == "error" and "could not decode" in res[0]["error"]


def test_a_linked_image_that_was_not_fetched_is_reported_clearly(tmp_path):
    b = make_bench(tmp_path, jpeg_bytes())
    with pytest.raises(B.BenchError, match="onmodel bench fetch --cases L1"):
        B.require_product(b, B.load_cases(b)[2])


# ----------------------------------------------------------------------------------------------------------- generate
def test_a_dry_run_writes_nothing_and_says_what_it_would_do(tmp_path):
    b = make_bench(tmp_path)
    cases = B.load_cases(b)
    lines = []
    out = tmp_path / "run"
    s = B.run_generate(b, B.plan_jobs(cases), FakeEngine(), out, recipes=R, execute=False, log=lines.append)
    assert not out.exists() and s["executed"] is False and s["to_generate"] == 4 and s["estimate_hi"] == pytest.approx(0.2)
    assert any("dry run" in l for l in lines) and any("would generate T1_v0_1k_s1.jpg" in l for l in lines)


def test_a_run_writes_images_a_ledger_and_run_json_and_can_resume(tmp_path):
    b = make_bench(tmp_path)
    cases = B.load_cases(b)
    jobs = B.plan_jobs(cases, variants=("v0", "v1", "repair"))
    out, eng = tmp_path / "run", FakeEngine()
    s = B.run_generate(b, jobs, eng, out, recipes=R, execute=True, workers=1, log=quiet)
    assert s["done"] == 5 and not s["failed"] and len(list((out / "images").glob("*.jpg"))) == 5
    repair = [c for c in eng.calls if c["prompt"].startswith("Image 1 is the real product photo")]
    assert len(repair) == 1 and repair[0]["refs"] == 2 and eng.calls[-1] is repair[0]            # the repair pass runs last, after its v1 photo exists
    ledger = B.load_jsonl(out / "ledger.jsonl")
    v = Draft202012Validator(run_record_schema())
    assert len(ledger) == 5 and all(not list(v.iter_errors(r)) for r in ledger)
    assert {r["recipe_version"] for r in ledger} == {R["version"]} and all(len(r["prompt_sha"]) == 12 and r["prompt"] for r in ledger)
    meta = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert meta["engine"] == "fake" and meta["variants"] == ["repair", "v0", "v1"] and meta["cases"] == ["N1", "T1"]
    again = B.run_generate(b, jobs, eng, out, recipes=R, execute=True, workers=1, log=quiet)       # resume: nothing left to do
    assert again["to_generate"] == 0 and again["done"] == 0 and len(B.load_jsonl(out / "ledger.jsonl")) == 5


def test_the_budget_guard_stops_new_calls(tmp_path):
    b = make_bench(tmp_path)
    jobs = B.plan_jobs(B.load_cases(b), variants=("v0", "v1"), samples=2)                         # 8 jobs, about $0.05 each at most
    s = B.run_generate(b, jobs, FakeEngine(), tmp_path / "run", recipes=R, execute=True, budget=0.12, workers=1, log=quiet)
    assert s["stopped_by_budget"] and s["done"] == 2 and s["spent_hi"] == pytest.approx(0.10)


def test_a_budget_needs_a_cost_estimate(tmp_path):
    b = make_bench(tmp_path)
    jobs = B.plan_jobs(B.load_cases(b))
    with pytest.raises(B.BenchError, match="cannot be enforced"):
        B.run_generate(b, jobs, FakeEngine(no_estimate=True), tmp_path / "run", recipes=R, execute=True, budget=1.0, log=quiet)
    s = B.run_generate(b, jobs, FakeEngine(no_estimate=True), tmp_path / "run2", recipes=R, execute=True, workers=1, log=quiet)   # without a budget it is fine
    assert s["done"] == 4 and s["estimate_lo"] is None


def test_one_failing_call_does_not_end_the_run(tmp_path):
    b = make_bench(tmp_path)
    jobs = B.plan_jobs(B.load_cases(b))
    out = tmp_path / "run"
    s = B.run_generate(b, jobs, FakeEngine(fail_first=True), out, recipes=R, execute=True, workers=1, log=quiet)
    assert s["done"] == 3 and len(s["failed"]) == 1
    bad = [r for r in B.load_jsonl(out / "ledger.jsonl") if not r["ok"]]
    assert len(bad) == 1 and "boom" in bad[0]["error"]
    assert B.run_generate(b, jobs, FakeEngine(), out, recipes=R, execute=True, workers=1, log=quiet)["done"] == 1      # the failed one is retried


def test_missing_inputs_fail_before_any_call(tmp_path):
    b = make_bench(tmp_path, jpeg_bytes())
    eng = FakeEngine()
    with pytest.raises(B.BenchError, match="bench fetch"):
        B.run_generate(b, B.plan_jobs(B.load_cases(b)), eng, tmp_path / "run", recipes=R, execute=True, log=quiet)
    assert eng.calls == []
    (b / "poses" / "pose-T1.jpg").unlink()
    with pytest.raises(B.BenchError, match="pose photo not found"):
        B.run_generate(b, B.plan_jobs(B.load_cases(b)[:1]), eng, tmp_path / "run", recipes=R, execute=True, log=quiet)


def test_an_engine_that_is_not_ready_is_reported_once(tmp_path):
    class NoKey(FakeEngine):
        def check_ready(self):
            raise RuntimeError("GEMINI_API_KEY is not set")
    b = make_bench(tmp_path)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        B.run_generate(b, B.plan_jobs(B.load_cases(b)), NoKey(), tmp_path / "run", recipes=R, execute=True, log=quiet)


# ----------------------------------------------------------------------------------------------------------- judge and report
def _generated(tmp_path):
    b = make_bench(tmp_path)
    out = tmp_path / "run"
    B.run_generate(b, B.plan_jobs(B.load_cases(b), variants=("v0", "v1")), MockEngine(), out, recipes=R, execute=True, workers=1, log=quiet)
    return b, out


def test_judge_writes_records_and_skips_what_is_done(tmp_path):
    b, out = _generated(tmp_path)
    vlm = MockVlm()
    s = B.run_judge(b, out, vlm, workers=1, log=quiet)
    assert s["photos"] == 4 and s["reviewed"] == 4 and vlm.calls == 4
    rows = B.load_jsonl(out / "judgments.jsonl")
    assert {r["file"] for r in rows} == {j for j in (p.name for p in (out / "images").glob("*.jpg"))}
    assert all(r["ok"] and r["case"] in ("T1", "N1") and r["variant"] in ("v0", "v1") and r["res"] == "1k" for r in rows)
    again = B.run_judge(b, out, vlm, workers=1, log=quiet)
    assert again["to_review"] == 0 and vlm.calls == 4


def test_failed_reviews_are_recorded_and_retried(tmp_path):
    b, out = _generated(tmp_path)
    s = B.run_judge(b, out, Scripted(VlmResult(ok=False, error="down")), workers=1, log=quiet)
    assert len(s["failed"]) == 4 and s["reviewed"] == 0 and all(not r["ok"] for r in B.load_jsonl(out / "judgments.jsonl"))
    s = B.run_judge(b, out, MockVlm(), workers=1, log=quiet)
    assert s["to_review"] == 4 and s["reviewed"] == 4


def test_the_report_counts_cells_and_writes_three_files(tmp_path):
    b, out = _generated(tmp_path)
    good, bad = make_checklist(), make_checklist({"pose": "different", "identity": "different"})
    B.run_judge(b, out, MockVlm([good, good, good, bad]), workers=1, log=quiet)       # sorted files: N1_v0, N1_v1, T1_v0, T1_v1 (the last one fails)
    rep = B.build_report(out)
    assert rep["photos"] == 4 and rep["directional_only"] and rep["judge"] == "mock"
    assert rep["cells"]["v0@1k"]["verified"] == 2 and rep["cells"]["v1@1k"]["verified"] == 1
    assert rep["cells"]["v1@1k"]["ci95"][0] < 0.5 < rep["cells"]["v1@1k"]["ci95"][1]
    assert rep["cases"]["T1"]["v1@1k"] == {"verified": 0, "n": 1}
    csv_lines = (out / "scores.csv").read_text(encoding="utf-8").splitlines()
    assert csv_lines[0].startswith("file,case,variant,res,sample,judge,total") and len(csv_lines) == 5
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "Directional only" in md and "| v1@1k | 2 | 1 | 50% |" in md and json.loads((out / "summary.json").read_text(encoding="utf-8"))["photos"] == 4


def test_a_photo_reviewed_twice_counts_once_and_the_latest_wins(tmp_path):
    b, out = _generated(tmp_path)
    B.run_judge(b, out, MockVlm(), workers=1, log=quiet)
    rows = B.load_jsonl(out / "judgments.jsonl")
    worse = dict(rows[0])
    worse["ts"] = "later"
    worse["scorecard"] = dict(worse["scorecard"], verified=False)
    with open(out / "judgments.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(worse) + "\n")
    rep = B.build_report(out)
    assert rep["photos"] == 4 and sum(c["verified"] for c in rep["cells"].values()) == 3


def test_report_needs_a_choice_when_several_judges_reviewed_the_run(tmp_path):
    b, out = _generated(tmp_path)
    B.run_judge(b, out, MockVlm(), workers=1, log=quiet)
    other = MockVlm()
    other.name = "other-judge"
    B.run_judge(b, out, other, workers=1, log=quiet)
    with pytest.raises(B.BenchError, match="several judges"):
        B.build_report(out)
    assert B.build_report(out, judge="other-judge")["judge"] == "other-judge"
    with pytest.raises(B.BenchError, match="no reviews by"):
        B.build_report(out, judge="nobody")


def test_report_without_reviews_says_what_to_run(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(B.BenchError, match="onmodel bench judge"):
        B.build_report(tmp_path / "empty")
