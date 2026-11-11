"""Look at a product photo and suggest what the recipes need: the sub-category, the risk tags, the parts and the printed text."""
from __future__ import annotations

from .judge import Vlm, load_image, to_jpeg
from .recipes import load_recipes
from .taxonomy import RISK_TAGS, SUBCATEGORIES

TAG_HELP = {
    "text": "words, letters, numbers or a logo are printed on the product",
    "glass": "glass or other transparent material",
    "metal": "polished or matte metal (jewelry, tins, caps)",
    "gem": "gemstones",
    "lace": "lace or embroidery",
    "black": "a deep black product, where detail is easy to lose",
    "pattern": "a printed or woven pattern",
    "multi": "more than one piece (a set, a bottle and its stopper, tubes and a card)",
    "hand": "the person holds the product in a hand",
    "worn_hand": "the product is worn on a finger",
    "person_in_photo": "the product photo itself shows a hand, a mannequin or a person that must not be copied",
}

ANALYSIS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "subcategory": {"type": "STRING", "enum": list(SUBCATEGORIES) + ["Other"]},
        "tags": {"type": "ARRAY", "items": {"type": "STRING", "enum": list(RISK_TAGS)}},
        "parts": {"type": "ARRAY", "items": {"type": "STRING"}},
        "text_lines": {"type": "ARRAY", "items": {"type": "STRING"}},
        "notes": {"type": "STRING"},
    },
    "required": ["subcategory", "tags", "parts", "text_lines"],
}


def build_analysis_prompt() -> str:
    lines = [
        "You prepare product photos for AI product photography. Look at this product photo and fill in the form.",
        "subcategory: the closest match from the list, or Other.",
        "tags: every tag that applies. Use only these tags:",
    ]
    lines += [f"  {k}: {v}" for k, v in TAG_HELP.items()]
    lines += [
        "parts: the separate pieces of the product that must all appear in a photo, one short phrase each (for example 'tube', 'cap', 'retail card').",
        'text_lines: every legible line of text printed on the product, exactly as printed. Use an empty list when there is none.',
        "notes: anything that will make this product hard to reproduce, in one sentence.",
    ]
    return "\n".join(lines)


def analyze_product(product, *, vlm: Vlm, recipes: dict | None = None) -> dict:
    """Returns {ok, subcategory, tags, verb, parts, text_lines, notes, error}. The verb comes from the starter recipe of the sub-category."""
    recipes = recipes or load_recipes()
    r = vlm.ask_json(build_analysis_prompt(), [to_jpeg(load_image(product))], ANALYSIS_SCHEMA)
    if not r.ok or not isinstance(r.data, dict):
        return {"ok": False, "error": r.error or "the reviewer returned no answer"}
    d = r.data
    sub = d.get("subcategory") if d.get("subcategory") in SUBCATEGORIES else "Other"
    default = recipes.get("subcategories", {}).get(sub, {})
    tags = [t for t in RISK_TAGS if t in (d.get("tags") or [])]
    for t in default.get("tags", []):
        if t not in tags and t in ("hand", "worn_hand"):   # how the product is held or worn follows from the sub-category
            tags.append(t)
    return {
        "ok": True, "error": "", "subcategory": sub, "tags": tags, "verb": default.get("verb", "wearing"),
        "parts": [str(p) for p in d.get("parts") or []], "text_lines": [str(t) for t in d.get("text_lines") or []],
        "notes": str(d.get("notes") or ""),
    }
