"""The docs are part of the product: their commands must parse, their examples must be what the tools print, and their tone must follow our rules."""
import re
import shlex

import pytest

from onmodel.cli import build_parser
from onmodel.scoring import render_text, score

from conftest import ROOT, make_checklist

FENCE = re.compile(r"^```(\w*)\n(.*?)^```", re.M | re.S)
MD_FILES = sorted(
    [p for p in ROOT.rglob("*.md") if not (set(p.relative_to(ROOT).parts) & {".venv", ".git", "node_modules", ".pytest_cache"})]
)
PROSE_FILES = [p for p in MD_FILES if p.name not in {"CODE_OF_CONDUCT.md", "PULL_REQUEST_TEMPLATE.md"}]


def commands(text):
    """Every line that starts with `onmodel ` inside a bash block, with continued lines joined and comments removed."""
    out = []
    for lang, body in FENCE.findall(text):
        if lang != "bash":
            continue
        joined = re.sub(r"\\\n\s*", " ", body)
        for line in joined.splitlines():
            line = re.sub(r"\s+#.*$", "", line.strip())
            if line.startswith("onmodel "):
                out.append(line)
    return out


def test_there_are_commands_to_check():
    total = sum(len(commands(p.read_text(encoding="utf-8"))) for p in MD_FILES)
    assert total >= 30


@pytest.mark.parametrize("path", MD_FILES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_every_onmodel_command_in_the_docs_is_valid(path):
    parser = build_parser()
    for line in commands(path.read_text(encoding="utf-8")):
        try:
            parser.parse_args(shlex.split(line)[1:])
        except SystemExit:
            pytest.fail(f"{path.name}: the command does not parse: {line}")


def test_the_scorecard_in_the_readmes_is_what_onmodel_score_prints():
    cl = __import__("json").loads((ROOT / "skills" / "fidelity-check" / "references" / "checklist-example.json").read_text(encoding="utf-8"))
    printed = render_text(score(cl), cl)
    for name in ("README.md", "README.zh-CN.md"):
        assert printed in (ROOT / name).read_text(encoding="utf-8"), name


def test_the_table_in_spec_verified_is_what_the_scorer_computes():
    cases = {
        "everything `same`": make_checklist(),
        "`text` is `minor`": make_checklist({"text": "minor"}),
        "`shape` is `different`": make_checklist({"shape": "different"}),
        "`pose` is `different`": make_checklist({"pose": "different"}),
        "`pose` and `identity` are `different`": make_checklist({"pose": "different", "identity": "different"}),
        "everything `same`, defect `PART_MISSING`": make_checklist(defects=["PART_MISSING"]),
        "`color` is `cannot_tell`": make_checklist({"color": "cannot_tell"}),
        "`scale` is `cannot_tell`": make_checklist({"scale": "cannot_tell"}),
    }
    rows = re.findall(r"^\| (.+?) \| (\d+) \| (yes|no) \|", (ROOT / "spec" / "verified.md").read_text(encoding="utf-8"), re.M)
    assert {r[0] for r in rows} == set(cases)
    for text, total, verified in rows:
        card = score(cases[text])
        assert (card.total, card.verified) == (int(total), verified == "yes"), text


def prose(text):
    text = FENCE.sub("", text)
    text = re.sub(r"`[^`\n]*`", "", text)               # inline code
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)    # images
    text = re.sub(r"\]\([^)]*\)", "]", text)            # link targets
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return text


EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐✅❌\U0001F000-\U0001F2FF]")
CLAIMS = re.compile(r"(world'?s first|\bthe first (open|ever|to)\b|first of its kind|revolutionary|breakthrough|state[- ]of[- ]the[- ]art|best[- ]in[- ]class|industry[- ]leading|game[- ]chang)", re.I)


@pytest.mark.parametrize("path", PROSE_FILES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_tone_no_emoji_no_exclamation_no_big_claims(path):
    text = path.read_text(encoding="utf-8")
    assert not EMOJI.search(text), f"{path.name}: emoji"
    body = prose(text)
    assert "!" not in body and "！" not in body, f"{path.name}: exclamation mark in prose"
    assert not CLAIMS.search(body), f"{path.name}: a claim we do not make"


def test_no_sales_language_and_the_company_appears_only_in_the_readme_footers():
    banned = re.compile(r"refund|credits?\b|utm_|fallback|wearai\.net/|Product Studio|Studio banner", re.I)
    for p in MD_FILES:
        assert not banned.search(p.read_text(encoding="utf-8")), p.name
    mentions = {p.name for p in MD_FILES if re.search(r"wearai", p.read_text(encoding="utf-8"), re.I)}
    assert mentions == {"README.md", "README.zh-CN.md"}


def test_the_readme_stays_short():
    assert len((ROOT / "README.md").read_bytes()) <= 9000


def test_both_readmes_have_the_same_sections_and_images():
    en, zh = (ROOT / "README.md").read_text(encoding="utf-8"), (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    images = lambda t: re.findall(r"\]\((docs/img/[^)]+)\)", t)  # noqa: E731
    assert images(en) == images(zh) and len(images(en)) == 5
    assert len(re.findall(r"^## ", en, re.M)) == len(re.findall(r"^## ", zh, re.M))
    assert len(FENCE.findall(en)) == len(FENCE.findall(zh))


def test_the_readme_does_not_promise_what_is_not_there():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "leaderboard" in text.lower() and "No leaderboard until" in text
    for phrase in ("pip install onmodel", "PyPI"):
        assert phrase not in text, phrase
