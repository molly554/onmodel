"""The skills carry their own copies of the scorer and the text rule so they run with nothing installed. These tests keep them identical to the package."""
import importlib.util
import random
import re
import subprocess
import sys

import pytest

from onmodel import taxonomy
from onmodel.scoring import Scorecard, advice, render_text, score
from onmodel.text_rule import text_recall

from conftest import ROOT, make_checklist

SKILL = ROOT / "skills" / "fidelity-check"


def load(name, path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vocab = load("vocab", SKILL / "scripts" / "vocab.py")
skill_score = load("skill_score", SKILL / "scripts" / "score.py")
skill_text = load("skill_text", SKILL / "scripts" / "text_match.py")


def test_the_vocabulary_is_identical():
    for name in ("FIDELITY_ITEMS", "OTHER_ITEMS", "ITEMS", "DIMENSIONS", "ANSWERS", "QUESTIONS", "DEFECTS", "VETO_CODES"):
        assert getattr(vocab, name) == getattr(taxonomy, name), name


def random_checklist(rng):
    cl = make_checklist()
    for k in taxonomy.ITEMS:
        a = rng.choice(taxonomy.ANSWERS)
        cl["items"][k] = {"answer": a} if a == "same" else {"answer": a, "evidence": f"e-{rng.randint(0, 99)}"}
    cl["defects"] = [{"code": c} for c in rng.sample(list(taxonomy.DEFECTS), rng.randint(0, 3))]
    return cl


def test_the_skill_scorer_matches_the_package_on_random_checklists():
    rng = random.Random(7)
    for _ in range(400):
        cl = random_checklist(rng)
        min_total = rng.choice([6, 8, 9])
        card = score(cl, min_total)
        mine = skill_score.score(cl, min_total)
        assert mine == card.to_dict()
        assert skill_score.advice(cl) == advice(cl)
        assert skill_score.render(mine, cl) == render_text(Scorecard(**mine), cl)


def test_the_skill_text_rule_matches_the_package():
    rng = random.Random(11)
    pool = ["labello", "classic", "soin", "protecteur", "nourrissant", "quotidien", "crème", "brûlée", "100", "ml", "ab", "SPORT", "Haut"]
    for _ in range(300):
        exp = " ".join(rng.choices(pool, k=rng.randint(0, 6)))
        obs = " ".join(rng.choices(pool, k=rng.randint(0, 6)))
        ref = text_recall(exp, obs)
        mine = skill_text.match(exp, obs)
        if ref is None:
            assert mine is None
        else:
            assert (mine["expected"], mine["found"], mine["missing"], mine["flagged"]) == (ref.expected, ref.found, ref.missing, ref.flagged)
            assert mine["recall"] == round(ref.recall, 3)


def test_the_skill_scorer_rejects_bad_input():
    with pytest.raises(ValueError, match="missing items"):
        skill_score.validate({"items": {}})
    with pytest.raises(ValueError, match="unknown defect code"):
        skill_score.validate(make_checklist(defects=["NOPE"]))
    with pytest.raises(ValueError, match="no JSON"):
        skill_score.load("nothing")


def run(*args, stdin=None):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, input=stdin, encoding="utf-8")


def test_the_skill_scripts_run_standalone_with_the_documented_exit_codes():
    example = SKILL / "references" / "checklist-example.json"
    r = run(SKILL / "scripts" / "score.py", example)
    assert r.returncode == 1 and "Verified: no" in r.stdout and "Total 8 / 10" in r.stdout
    import json
    r = run(SKILL / "scripts" / "score.py", "-", stdin=json.dumps(make_checklist()))
    assert r.returncode == 0 and "Verified: yes" in r.stdout
    assert run(SKILL / "scripts" / "score.py", "-", stdin="{}").returncode == 2
    r = run(SKILL / "scripts" / "text_match.py", "--expected", "alpha beta gamma", "--observed", "")
    assert r.returncode == 1 and "FLAGGED" in r.stdout
    assert run(SKILL / "scripts" / "text_match.py", "--expected", "alpha beta gamma", "--observed", "alpha beta").returncode == 0
    assert run(SKILL / "scripts" / "text_match.py", "--expected", "a b").returncode == 2


@pytest.mark.parametrize("name", ["fidelity-check", "shoot-brief"])
def test_skill_metadata_and_references(name):
    folder = ROOT / "skills" / name
    text = (folder / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\nname: (?P<name>[a-z0-9-]+)\ndescription: (?P<desc>.+)\n---\n", text)
    assert m and m["name"] == name and 40 < len(m["desc"]) < 1024
    for ref in re.findall(r"`((?:references|scripts)/[\w./-]+)`", text):
        assert (folder / ref).exists(), ref
