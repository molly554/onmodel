import csv
import json

import recompute_mini_test as mini
import yaml

from conftest import ROOT

RUN = ROOT / "bench" / "runs" / "mini-test-v0.1"


def summary():
    return json.loads((RUN / "summary.json").read_text(encoding="utf-8"))


def test_the_summary_is_what_the_table_gives():
    assert mini.main(["--check"]) == 0
    assert mini.compute(mini.load(RUN / "photos.csv")) == summary()


def test_the_table_covers_the_public_cases_only():
    cases = {c["id"] for c in yaml.safe_load((ROOT / "bench" / "cases.yaml").read_text(encoding="utf-8"))["cases"]}
    rows = list(csv.DictReader(open(RUN / "photos.csv", encoding="utf-8")))
    assert len(rows) == 52 and {r["case"] for r in rows} == cases and "A01" not in cases


def test_published_photos_match_the_table():
    rows = list(csv.DictReader(open(RUN / "photos.csv", encoding="utf-8")))
    published = {r["file"] for r in rows if r["published"] == "yes"}
    on_disk = {p.name for p in (RUN / "images").glob("*.jpg")}
    assert published == on_disk and len(on_disk) == 19
    cases = {c["id"]: c for c in yaml.safe_load((ROOT / "bench" / "cases.yaml").read_text(encoding="utf-8"))["cases"]}
    assert all(cases[r["case"]]["source"]["kind"] == "bundled" for r in rows if r["published"] == "yes")      # never a photo made from a CC BY-SA product photo


def test_the_numbers_quoted_in_the_readme_and_the_docs_are_the_summarys():
    s = summary()
    sp, parts, hem = s["small_print"], s["parts"]["K10"], s["hem_length"]
    lc, rv, tr = s["label_covered"]["by_case"]["K01"], s["reviewers"], s["text_rule"]
    assert (sp["1k"]["garbled"], sp["1k"]["photos"], sp["2k"]["garbled"], sp["2k"]["photos"]) == (8, 8, 0, 4)
    assert (parts["v0"]["with_part_defect"], parts["v1"]["with_part_defect"], parts["v1_2k"]["with_part_defect"]) == (2, 0, 1)
    assert (lc["label_covered"], lc["photos"], hem["followed_the_pose_photo"], hem["photos"]) == (6, 8, 5, 8)
    assert round(rv["judges_agree_with_each_other"] * 100) == 40 and rv["kappa_between_judges"] == 0.12
    assert (tr["garbled_small_print"]["flagged"], tr["garbled_small_print"]["photos"], tr["fail"]["flagged"], tr["ok"]["flagged"], tr["ok"]["photos"]) == (12, 12, 3, 2, 17)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "mini-test.md").read_text(encoding="utf-8")
    for phrase in ("8 of 8 photos at 1K and 0 of 4 at 2K", "2 of 2 photos with a generic prompt", "6 of 8 photos of one tin", "5 of 8 dress photos",
                   "agreed on 40 percent", "12 of 12 garbled-print photos", "52 photos of 9 products"):
        assert phrase in readme, phrase
    for phrase in ("60% (kappa 0.38)", "38% (kappa 0.0)", "28 of 52", "(kappa 0.12)", "6 of 8 photos", "5 of 8 dress photos", "26 photos are `pass`, 23 `minor` and 3 `fail`"):
        assert phrase in doc, phrase
