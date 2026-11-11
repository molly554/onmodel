import pytest

from onmodel.scoring import ChecklistError, advice, render_text, score
from onmodel.taxonomy import DEFECTS, FIDELITY_ITEMS, VETO_CODES

from conftest import make_checklist as cl


def test_all_same_is_verified_with_ten_points():
    card = score(cl())
    assert card.total == 10 and card.verified and card.veto == [] and card.reasons == []
    assert card.dims == {"fidelity": 2, "pose": 2, "identity": 2, "artifacts": 2, "scale": 2}


@pytest.mark.parametrize("item", FIDELITY_ITEMS)
def test_minor_on_any_fidelity_item_blocks_verified(item):
    card = score(cl({item: "minor"}))
    assert card.dims["fidelity"] == 1 and card.total == 9 and not card.verified
    assert any(item in r for r in card.reasons)


def test_fidelity_is_the_lowest_of_its_five_items():
    card = score(cl({"shape": "minor", "color": "different", "text": "minor"}))
    assert card.dims["fidelity"] == 0 and card.total == 8 and not card.verified


def test_cannot_tell_on_a_fidelity_item_blocks_verified_and_is_reported():
    card = score(cl({"color": "cannot_tell"}))
    assert not card.verified and card.unverifiable == ["color"] and card.dims["fidelity"] == 1


def test_cannot_tell_elsewhere_costs_one_point_and_is_reported():
    card = score(cl({"scale": "cannot_tell"}))
    assert card.total == 9 and card.verified and card.unverifiable == ["scale"]


def test_not_applicable_counts_as_two():
    assert score(cl({"pose": "not_applicable", "scale": "not_applicable"})).total == 10


def test_a_veto_defect_blocks_verified_whatever_the_points():
    card = score(cl(defects=["PART_MISSING"]))
    assert card.total == 10 and card.veto == ["PART_MISSING"] and not card.verified


def test_a_non_veto_defect_does_not_block_by_itself():
    assert score(cl(defects=["COLOR_OFF"])).verified


def test_every_veto_code_blocks():
    for code in VETO_CODES:
        assert not score(cl(defects=[code])).verified, code


def test_total_below_the_minimum_blocks_verified():
    card = score(cl({"pose": "different", "identity": "different"}))
    assert card.total == 6 and not card.verified
    assert any("below 8" in r for r in card.reasons)


def test_one_other_dimension_at_zero_is_still_verified():
    assert score(cl({"pose": "different"})).verified          # 8 of 10: the verdict is about the product


def test_min_total_can_be_raised():
    c = cl({"pose": "minor", "identity": "minor"})
    assert score(c).verified and not score(c, min_total=9).verified


def test_the_same_checklist_always_gives_the_same_card():
    c = cl({"text": "different"}, ["TEXT_GARBLE"])
    assert score(c).to_dict() == score(c).to_dict()


def test_validation_errors():
    with pytest.raises(ChecklistError, match="items"):
        score({})
    with pytest.raises(ChecklistError, match="missing items: scale"):
        c = cl()
        del c["items"]["scale"]
        score(c)
    with pytest.raises(ChecklistError, match="answer must be one of"):
        score(cl({"shape": "great"}))
    with pytest.raises(ChecklistError, match="unknown defect code"):
        score(cl(defects=["NOT_A_CODE"]))


def test_advice_puts_vetoes_first_dedupes_and_limits():
    c = cl(defects=["COLOR_OFF", "TEXT_GARBLE", "TEXT_WRONG", "PART_MISSING", "PART_MERGED", "SCALE_OFF"])
    tips = advice(c)
    assert len(tips) == 3 and len(set(tips)) == 3
    assert tips[0] == DEFECTS["PART_MERGED"]["advice"] or tips[0] == DEFECTS["PART_MISSING"]["advice"] or tips[0] == DEFECTS["TEXT_WRONG"]["advice"]
    assert advice(cl()) == []


def test_render_text_for_a_verified_and_a_failed_photo():
    ok = render_text(score(cl()), cl())
    assert "Total 10 / 10" in ok and "Verified: yes" in ok and "Fix:" not in ok
    bad_cl = cl({"text": {"answer": "different", "evidence": "small print is gibberish"}}, ["TEXT_GARBLE"])
    bad = render_text(score(bad_cl), bad_cl)
    assert "Verified: no" in bad and "small print is gibberish" in bad and "Fix: Render at 2K" in bad and "Fidelity   0 / 2" in bad
