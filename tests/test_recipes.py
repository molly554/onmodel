import pytest

from onmodel.analyze import ANALYSIS_SCHEMA, analyze_product, build_analysis_prompt
from onmodel.judge import VlmResult
from onmodel.recipes import build_prompt, load_recipes
from onmodel.taxonomy import RISK_TAGS, SUBCATEGORIES

from conftest import Scripted

R = load_recipes()


def test_every_risk_tag_has_exactly_one_rule():
    assert set(R["rules"]) == set(RISK_TAGS)


def test_every_subcategory_has_a_starting_point_with_valid_tags_and_verb():
    assert set(R["subcategories"]) == set(SUBCATEGORIES)
    for sub, d in R["subcategories"].items():
        assert d["verb"] in R["verbs"] and set(d["tags"]) <= set(RISK_TAGS), sub


def test_v0_is_the_generic_prompt():
    p = build_prompt(R, variant="v0", verb="holding", tags=("text",))
    assert p.startswith("Photorealistic e-commerce catalog photo edit.") and "hold the exact product from Image 1" in p
    assert p.endswith("No watermark.") and "TEXT AND LOGOS" not in p                      # v0 ignores tags


def test_v1_adds_the_rules_of_the_tags_in_recipe_order_then_the_always_rule():
    p = build_prompt(R, variant="v1", verb="wearing", tags=("metal", "text"))             # asked in the other order
    assert "wear the exact product" in p
    assert p.index("TEXT AND LOGOS") < p.index("METAL:") < p.index("SIZE:")
    assert "GLASS:" not in p and p.count("\n- ") == 3


def test_v1_without_tags_still_has_the_always_rule():
    p = build_prompt(R, variant="v1", verb="wearing")
    assert p.count("\n- ") == 1 and "SIZE:" in p


def test_repair_prompt_is_independent_of_the_product():
    assert build_prompt(R, variant="repair", verb="wearing") == build_prompt(R, variant="repair", verb="holding", tags=("text",))
    assert "printed text and logos on the product are identical to Image 1" in build_prompt(R, variant="repair", verb="wearing")


def test_bad_arguments():
    with pytest.raises(ValueError, match="variant"):
        build_prompt(R, variant="v9", verb="wearing")
    with pytest.raises(ValueError, match="verb"):
        build_prompt(R, variant="v1", verb="eating")
    with pytest.raises(ValueError, match="unknown tags: shiny"):
        build_prompt(R, variant="v1", verb="wearing", tags=("shiny",))


def test_a_custom_recipes_file_is_loaded(tmp_path):
    p = tmp_path / "mine.yaml"
    p.write_text("version: '9'\nheader: 'H {verb}'\nv0_tail: ' T'\nv1_lead: ' L'\nrules: {text: 'R'}\nalways: 'A'\nrepair: 'X'\nverbs: {wearing: wear, holding: hold}\n", encoding="utf-8")
    assert build_prompt(load_recipes(p), variant="v1", verb="wearing", tags=("text",)) == "H wear L\n- R\n- A"


def test_analysis_schema_enums():
    assert ANALYSIS_SCHEMA["properties"]["subcategory"]["enum"] == list(SUBCATEGORIES) + ["Other"]
    assert ANALYSIS_SCHEMA["properties"]["tags"]["items"]["enum"] == list(RISK_TAGS)
    p = build_analysis_prompt()
    for t in RISK_TAGS:
        assert f"  {t}: " in p


def test_analyze_product_uses_the_subcategory_to_set_the_verb_and_hand_tags(imgs):
    vlm = Scripted({"subcategory": "Lipstick", "tags": ["text", "bogus"], "parts": ["tube"], "text_lines": ["LABELLO"], "notes": "glossy"})
    res = analyze_product(imgs["product"], vlm=vlm)
    assert res["ok"] and res["verb"] == "holding" and res["tags"] == ["text", "hand"]
    assert res["parts"] == ["tube"] and res["text_lines"] == ["LABELLO"] and res["notes"] == "glossy"


def test_analyze_product_unknown_subcategory_and_failure(imgs):
    res = analyze_product(imgs["product"], vlm=Scripted({"subcategory": "Hats", "tags": ["pattern"], "parts": [], "text_lines": []}))
    assert res["subcategory"] == "Other" and res["verb"] == "wearing" and res["tags"] == ["pattern"]
    bad = analyze_product(imgs["product"], vlm=Scripted(VlmResult(ok=False, error="down")))
    assert bad == {"ok": False, "error": "down"}
