"""Starter recipes: load them and build the prompt for a product."""
from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml

from .taxonomy import RISK_TAGS

VARIANTS = ("v0", "v1", "repair")


def load_recipes(path: str | Path | None = None) -> dict:
    """The starter recipes shipped with onmodel, or your own file in the same format."""
    if path:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = resources.files("onmodel").joinpath("data/starter-recipes.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)


def _clean(s: str) -> str:
    return " ".join(str(s).split())


def build_prompt(recipes: dict, *, variant: str, verb: str, tags=()) -> str:
    """variant: v0 (generic), v1 (generic plus the rules of the tags) or repair (second pass for text)."""
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {', '.join(VARIANTS)}")
    if variant == "repair":
        return _clean(recipes["repair"])
    if verb not in recipes["verbs"]:
        raise ValueError(f"verb must be one of {', '.join(recipes['verbs'])}")
    unknown = [t for t in tags if t not in RISK_TAGS]
    if unknown:
        raise ValueError(f"unknown tags: {', '.join(unknown)} (known: {', '.join(RISK_TAGS)})")
    head = _clean(recipes["header"]).format(verb=recipes["verbs"][verb])
    if variant == "v0":
        return head + recipes["v0_tail"]
    rules = [_clean(recipes["rules"][t]) for t in recipes["rules"] if t in tags]
    return head + recipes["v1_lead"] + "\n- " + "\n- ".join(rules + [_clean(recipes["always"])])
