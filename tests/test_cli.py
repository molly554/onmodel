import json

import pytest

from onmodel.cli import main

from conftest import ROOT, make_checklist

EXAMPLE = ROOT / "skills" / "fidelity-check" / "references" / "checklist-example.json"


def run(capsys, *argv):
    code = main([str(a) for a in argv])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_version(capsys):
    code, out, _ = run(capsys, "version")
    assert code == 0 and out.startswith("onmodel 0.1.0 (rubric ")


def test_score_exit_codes_and_output(capsys, tmp_path):
    code, out, _ = run(capsys, "score", EXAMPLE)
    assert code == 1 and "Total 8 / 10" in out and "Verified: no" in out and "Fix:" in out
    good = tmp_path / "good.json"
    good.write_text(json.dumps(make_checklist()), encoding="utf-8")
    code, out, _ = run(capsys, "score", good)
    assert code == 0 and "Verified: yes" in out
    code, out, _ = run(capsys, "score", good, "--json")
    assert code == 0 and json.loads(out)["scorecard"]["total"] == 10
    code, out, _ = run(capsys, "score", good, "--min-total", 11)
    assert code == 1


def test_score_reads_a_checklist_wrapped_in_a_code_fence(capsys, tmp_path):
    p = tmp_path / "answer.txt"
    p.write_text("```json\n" + json.dumps(make_checklist()) + "\n```", encoding="utf-8")
    assert run(capsys, "score", p)[0] == 0


def test_score_errors_exit_with_2(capsys, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"items": {}}', encoding="utf-8")
    code, _, err = run(capsys, "score", bad)
    assert code == 2 and err.startswith("error: missing items")
    assert run(capsys, "score", tmp_path / "missing.json")[0] == 2


def test_check_with_the_mock_judge(capsys, imgs):
    code, out, _ = run(capsys, "check", imgs["product"], imgs["result"], "--judge", "mock", "--pose", imgs["pose"], "--tags", "hand", "--verb", "holding")
    assert code == 0 and "Verified: yes" in out and "Judge mock" in out
    code, out, _ = run(capsys, "check", imgs["product"], imgs["result"], "--judge", "mock", "--json", "--no-crop")
    rec = json.loads(out)
    assert code == 0 and rec["scorecard"]["total"] == 10 and rec["judge"]["crop"] is False


def test_check_gives_exit_1_when_the_text_rule_flags_the_photo(capsys, imgs, tmp_path):
    out_file = tmp_path / "record.json"
    code, out, _ = run(capsys, "check", imgs["product"], imgs["result"], "--judge", "mock", "--expect-text", "LABELLO CLASSIC SOIN", "--out", out_file)
    assert code == 1 and "Verified: no" in out and "this made the verdict stricter" in out
    assert json.loads(out_file.read_text(encoding="utf-8"))["rule_tightened"] is True


def test_check_argument_errors(capsys, imgs, tmp_path):
    assert run(capsys, "check", imgs["product"], imgs["result"], "--judge", "mock", "--tags", "shiny")[0] == 2
    assert run(capsys, "check", imgs["product"], tmp_path / "nope.jpg", "--judge", "mock")[0] == 2
    code, _, err = run(capsys, "check", imgs["product"], imgs["result"], "--judge", "nonsense")
    assert code == 2 and "unknown judge" in err


def test_check_without_a_key_says_how_to_set_it(capsys, imgs, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    code, _, err = run(capsys, "check", imgs["product"], imgs["result"])
    assert code == 2 and "GEMINI_API_KEY is not set" in err


def test_recipe_prints_the_prompt(capsys):
    code, out, _ = run(capsys, "recipe", "--verb", "holding", "--tags", "text,hand")
    assert code == 0 and "TEXT AND LOGOS" in out and "HANDS:" in out and "hold the exact product" in out
    assert "TEXT AND LOGOS" not in run(capsys, "recipe", "--variant", "v0", "--tags", "text")[1]
    assert run(capsys, "recipe", "--tags", "shiny")[0] == 2


def test_bench_list_and_smoke(capsys):
    code, out, _ = run(capsys, "bench", "list")
    assert code == 0 and "9 cases" in out and "K04" in out
    code, out, _ = run(capsys, "bench", "smoke")
    assert code == 0 and "8 photos generated and reviewed offline" in out and "6 verified, 2 not verified" in out


def test_bench_run_is_a_dry_run_without_yes_and_needs_no_key(capsys, tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    out_dir = tmp_path / "runs" / "dry"
    code, out, _ = run(capsys, "bench", "run", "--cases", "K04,J01", "--variants", "v0,v1,repair", "--res", "1k,2k", "--samples", "1", "--out", out_dir)
    assert code == 0 and "dry run" in out and "would generate K04_repair_2k_s1.jpg" in out and "estimated cost $" in out
    assert not out_dir.exists()


def test_bench_run_with_yes_but_no_key_stops_before_spending(capsys, tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    code, _, err = run(capsys, "bench", "run", "--cases", "K04", "--yes", "--out", tmp_path / "r")
    assert code == 2 and "GEMINI_API_KEY is not set" in err and not (tmp_path / "r" / "images").exists()


def test_bench_run_judge_report_end_to_end_with_mocks(capsys, tmp_path):
    out_dir = tmp_path / "e2e"
    code, out, _ = run(capsys, "bench", "run", "--engine", "mock", "--cases", "K04,J01", "--variants", "v0,v1", "--samples", "1", "--out", out_dir, "--yes", "--workers", 1)
    assert code == 0 and len(list((out_dir / "images").glob("*.jpg"))) == 4
    code, out, _ = run(capsys, "bench", "judge", "--run", out_dir, "--judge", "mock", "--cases", "K04,J01", "--workers", 1)
    assert code == 0 and "photos 4 | to review 4" in out
    code, out, _ = run(capsys, "bench", "report", "--run", out_dir)
    assert code == 0 and "# onmodel bench report" in out and "v1@1k" in out and (out_dir / "summary.json").exists()


def test_bench_errors_are_reported_not_raised(capsys, tmp_path):
    code, _, err = run(capsys, "bench", "report", "--run", tmp_path / "nothing-here")
    assert code == 2 and err.startswith("error:")
    code, _, err = run(capsys, "bench", "fetch", "--cases", "Z9")
    assert code == 2 and "unknown case id" in err


def test_a_missing_subcommand_is_a_usage_error():
    with pytest.raises(SystemExit) as e:
        main([])
    assert e.value.code == 2
