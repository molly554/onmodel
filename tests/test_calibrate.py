import csv
import json
import random

import pytest
import recompute_mini_test as mini
from test_bench import _generated, quiet

from onmodel import bench as B
from onmodel.cli import main
from onmodel.judge import MockVlm

from conftest import make_checklist


def test_judge_level_maps_a_scorecard_to_three_levels():
    def card(**kw):
        base = {"verified": False, "dims": {"fidelity": 1}, "veto": []}
        base.update(kw)
        return base

    assert B.judge_level(card(verified=True, dims={"fidelity": 2})) == "pass"
    assert B.judge_level(card()) == "minor"
    assert B.judge_level(card(dims={"fidelity": 0})) == "fail"
    assert B.judge_level(card(dims={"fidelity": 2}, veto=["PART_MISSING"])) == "fail"


def test_kappa_agrees_with_the_standalone_script():
    rng = random.Random(3)
    for _ in range(50):
        pairs = [(rng.choice("abc"), rng.choice("abc")) for _ in range(rng.randint(5, 40))]
        assert B.cohen_kappa(pairs) == mini.kappa(pairs)
    assert B.cohen_kappa([("a", "a"), ("b", "b")]) == 1.0
    assert B.cohen_kappa([("a", "a")] * 5) == 1.0           # a single class: no chance correction possible


def labels_file(tmp_path, mapping):
    p = tmp_path / "labels.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "label", "note"])
        for k, v in mapping.items():
            w.writerow([k, v, "x"])
    return p


def reviewed_run(tmp_path):
    """Four photos, reviewed in the order N1_v0, N1_v1, T1_v0, T1_v1: pass, pass, minor, fail."""
    b, out = _generated(tmp_path)
    good = make_checklist()
    minor = make_checklist({"pose": "different", "identity": "different"})
    fail = make_checklist({"shape": "different"})
    B.run_judge(b, out, MockVlm([good, good, minor, fail]), workers=1, log=quiet)
    return out


def test_perfect_agreement(tmp_path):
    out = reviewed_run(tmp_path)
    labels = labels_file(tmp_path, {"N1_v0_1k_s1.jpg": "pass", "N1_v1_1k_s1.jpg": "pass", "T1_v0_1k_s1.jpg": "minor", "T1_v1_1k_s1.jpg": "fail"})
    r = B.calibrate(out, labels)
    assert r["photos"] == 4 and r["agree_3level"] == 1.0 and r["kappa_3level"] == 1.0 and r["agree_pass_vs_not"] == 1.0
    assert r["failures"] == {"labelled": 1, "caught": 1, "false_alarms": 0}
    g = r["gates"]
    assert g["agree_3level"]["met"] is True and g["failure_recall"]["met"] is True and g["photos"]["met"] is False    # four photos are not 150
    assert json.loads((out / "calibration.json").read_text(encoding="utf-8"))["judge"] == "mock"


def test_disagreement_is_counted(tmp_path):
    out = reviewed_run(tmp_path)
    labels = labels_file(tmp_path, {"N1_v0_1k_s1.jpg": "pass", "N1_v1_1k_s1.jpg": "minor", "T1_v0_1k_s1.jpg": "pass", "T1_v1_1k_s1.jpg": "pass"})
    r = B.calibrate(out, labels)
    assert r["agree_3level"] == 0.25 and r["failures"] == {"labelled": 0, "caught": 0, "false_alarms": 1}
    assert r["gates"]["failure_recall"]["value"] is None and r["gates"]["failure_recall"]["met"] is None      # no failure was labelled: nothing to recall
    assert r["judge_says_pass"] == 0.5 and r["labels_say_pass"] == 0.75
    assert r["confusion"]["minor->pass"] == 1 and r["confusion"]["pass->fail"] == 1 and r["confusion"]["pass->minor"] == 1


def test_unmatched_files_are_reported_not_hidden(tmp_path):
    out = reviewed_run(tmp_path)
    labels = labels_file(tmp_path, {"N1_v0_1k_s1.jpg": "pass", "somewhere/else.jpg": "fail"})
    r = B.calibrate(out, labels)
    assert r["photos"] == 1 and r["labelled_only"] == 1 and r["reviewed_only"] == 3


def test_calibration_errors(tmp_path):
    out = reviewed_run(tmp_path)
    with pytest.raises(B.BenchError, match="must be one of pass, minor, fail"):
        B.calibrate(out, labels_file(tmp_path, {"N1_v0_1k_s1.jpg": "great"}))
    bad = tmp_path / "bad.csv"
    bad.write_text("name,verdict\nx,pass\n", encoding="utf-8")
    with pytest.raises(B.BenchError, match="columns: file,label"):
        B.calibrate(out, bad)
    with pytest.raises(B.BenchError, match="no photo has both"):
        B.calibrate(out, labels_file(tmp_path, {"unknown.jpg": "pass"}))
    with pytest.raises(B.BenchError, match="no reviews"):
        B.calibrate(tmp_path / "empty", labels_file(tmp_path, {"a.jpg": "pass"}))
    with pytest.raises(B.BenchError, match="no reviews by nobody"):
        B.calibrate(out, labels_file(tmp_path, {"N1_v0_1k_s1.jpg": "pass"}), judge="nobody")


def test_the_command_prints_the_table(capsys, tmp_path):
    out = reviewed_run(tmp_path)
    labels = labels_file(tmp_path, {"N1_v0_1k_s1.jpg": "pass", "N1_v1_1k_s1.jpg": "pass", "T1_v0_1k_s1.jpg": "minor", "T1_v1_1k_s1.jpg": "fail"})
    code = main(["bench", "--bench", str(out.parent.parent), "calibrate", "--run", str(out), "--labels", str(labels)])
    text = capsys.readouterr().out
    assert code == 0 and "agreement, 3 levels" in text and "100%" in text and "failures caught (1 of 1)" in text and "proposals, not measured thresholds" in text
