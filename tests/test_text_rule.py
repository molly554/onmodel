from PIL import Image

from onmodel.text_rule import DEFAULT_THRESHOLD, get_backend, ocr_text_rule, text_recall, words


def test_words_drops_accents_case_short_words_and_repeats():
    assert words("Crème BRÛLÉE, 100 ml of AB ab crème") == ["creme", "brulee", "100"]


def test_recall_found_missing_and_flag():
    r = text_recall("LABELLO CLASSIC SOIN PROTECTEUR", "labello classic")
    assert r.found == ["labello", "classic"] and r.missing == ["soin", "protecteur"] and r.recall == 0.5 and not r.flagged
    r = text_recall("LABELLO CLASSIC SOIN PROTECTEUR", "lbello clasic")
    assert r.found == [] and r.recall == 0.0 and r.flagged


def test_the_threshold_is_strict_below():
    r = text_recall("alpha beta gamma delta", "alpha")                  # recall exactly 0.25
    assert r.recall == DEFAULT_THRESHOLD and not r.flagged
    assert text_recall("alpha beta gamma delta", "alpha", threshold=0.3).flagged


def test_expected_can_be_a_list_of_chunks():
    r = text_recall(["ALPHA", "BETA GAMMA", "alpha"], "gamma beta")
    assert r.expected == ["alpha", "beta", "gamma"] and r.found == ["beta", "gamma"]


def test_nothing_to_check_returns_none():
    assert text_recall("", "anything") is None
    assert text_recall("a b 1", "anything") is None                     # only words that are too short


def test_empty_observation_is_flagged():
    assert text_recall("alpha beta", "").flagged


class FakeOcr:
    name = "fake"

    def __init__(self, table):
        self.table, self.seen = table, []

    def read(self, image):
        self.seen.append(image.size)
        return self.table.get(image.size, "")


def test_ocr_rule_searches_rotations_and_keeps_the_best():
    product, result = Image.new("RGB", (10, 10)), Image.new("RGB", (40, 20))
    ocr = FakeOcr({(10, 10): "alpha beta gamma delta", (20, 40): "alpha beta gamma delta"})   # readable only after a 90 degree turn
    rule = ocr_text_rule(product, result, ocr)
    assert rule.source == "ocr" and rule.recall == 1.0 and not rule.flagged


def test_ocr_rule_flags_when_nothing_is_readable():
    product, result = Image.new("RGB", (10, 10)), Image.new("RGB", (40, 20))
    rule = ocr_text_rule(product, result, FakeOcr({(10, 10): "alpha beta gamma delta"}))
    assert rule.flagged and rule.recall == 0.0


def test_ocr_rule_uses_known_words_instead_of_reading_the_product():
    product, result = Image.new("RGB", (10, 10)), Image.new("RGB", (40, 20))
    ocr = FakeOcr({(40, 20): "alpha beta"})
    rule = ocr_text_rule(product, result, ocr, expected=["ALPHA", "BETA"])
    assert rule.recall == 1.0 and (10, 10) not in ocr.seen


def test_ocr_rule_returns_none_when_the_product_has_no_words():
    assert ocr_text_rule(Image.new("RGB", (10, 10)), Image.new("RGB", (40, 20)), FakeOcr({})) is None


def test_backends():
    assert get_backend(None) is None and get_backend("none") is None
    try:
        get_backend("nope")
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "unknown OCR backend" in str(e)
