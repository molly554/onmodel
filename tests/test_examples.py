import json

import pytest

from onmodel.cli import main
from onmodel.engines import load_engine
from onmodel.judge import MockVlm, load_vlm
from onmodel.plugins import load_class

from conftest import ROOT


def test_the_custom_engine_example_runs_through_the_benchmark(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(ROOT)
    out = tmp_path / "paste-demo"
    code = main(["bench", "run", "--engine", "examples.custom_engine:PasteEngine", "--cases", "K04,J01", "--variants", "v1", "--samples", "1",
                 "--out", str(out), "--yes", "--workers", "1"])
    assert code == 0 and sorted(p.name for p in (out / "images").glob("*.jpg")) == ["J01_v1_1k_s1.jpg", "K04_v1_1k_s1.jpg"]
    ledger = [json.loads(line) for line in (out / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["engine"] for r in ledger} == {"paste-demo"} and all(r["ok"] for r in ledger)
    assert main(["bench", "judge", "--run", str(out), "--judge", "mock", "--cases", "K04,J01", "--workers", "1"]) == 0
    assert main(["bench", "report", "--run", str(out)]) == 0
    assert "paste-demo" in capsys.readouterr().out


def test_load_class_finds_modules_next_to_you(monkeypatch):
    monkeypatch.chdir(ROOT)
    assert load_class("examples.custom_engine:PasteEngine").__name__ == "PasteEngine"
    assert load_engine("examples.custom_engine:PasteEngine").id == "paste-demo"
    assert isinstance(load_vlm("onmodel.judge:MockVlm"), MockVlm)


@pytest.mark.parametrize("spec, message", [
    ("no-colon", "expected 'package.module:ClassName'"),
    ("not_a_module_at_all:Thing", "cannot import"),
    ("examples.custom_engine:Missing", "has no class 'Missing'"),
])
def test_load_class_errors_are_clear(spec, message):
    with pytest.raises(ValueError, match=message):
        load_class(spec)
