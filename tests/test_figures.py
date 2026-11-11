import importlib.util
import re
import sys
import xml.dom.minidom

import pytest
from PIL import Image

from conftest import ROOT

SRC = ROOT / "docs" / "img" / "src"
IMG = ROOT / "docs" / "img"


def load(name):
    sys.path.insert(0, str(SRC))
    spec = importlib.util.spec_from_file_location(name, SRC / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


diagrams = load("make_diagrams")
hero = load("make_hero")


@pytest.mark.parametrize("name", list(diagrams.FIGURES))
def test_the_diagrams_are_what_the_generator_writes(name):
    assert (IMG / name).read_text(encoding="utf-8") == diagrams.FIGURES[name]()


@pytest.mark.parametrize("name", list(diagrams.FIGURES))
def test_the_diagrams_are_well_formed_and_self_contained(name):
    text = (IMG / name).read_text(encoding="utf-8")
    dom = xml.dom.minidom.parseString(text)
    root = dom.documentElement
    assert root.tagName == "svg" and root.getAttribute("viewBox") and root.getAttribute("role") == "img"
    assert dom.getElementsByTagName("title") and dom.getElementsByTagName("desc")
    assert not dom.getElementsByTagName("script") and not dom.getElementsByTagName("image") and not dom.getElementsByTagName("foreignObject")
    assert "var(" not in text and "<style" not in text                      # explicit colors, so the figure looks the same in any theme
    assert not re.findall(r"""(?:href|src)=["'](?!#)""", text)               # no external or relative references
    assert set(re.findall(r"https?://[^\s\"'<>]+", text)) <= {"http://www.w3.org/2000/svg"}


def test_the_hero_page_is_what_the_generator_writes():
    crops = {k: f"crops/{k}.jpg" for k in ("product-context", "product-label", "r1k-context", "r1k-label", "r2k-context", "r2k-label")}
    cards = hero.scorecards()
    assert (SRC / "hero.html").read_text(encoding="utf-8") == hero.build_html(crops, cards)
    assert (SRC / "social.html").read_text(encoding="utf-8") == hero.build_social_html(crops, cards)


def test_the_scorecards_in_the_hero_come_from_the_scorer():
    cards = hero.scorecards()
    assert (cards["1k"].verified, cards["1k"].total, cards["1k"].dims["fidelity"]) == (False, 8, 0)
    assert (cards["2k"].verified, cards["2k"].total) == (True, 10)
    page = (SRC / "hero.html").read_text(encoding="utf-8")
    assert "Verified: no" in page and "Verified: yes" in page and "Total 8 / 10" in page and "Total 10 / 10" in page


def test_the_images_have_the_expected_shape():
    assert Image.open(IMG / "hero.png").size == (2000, 1250)
    social = Image.open(IMG / "social-preview.jpg")
    assert social.size == (1280, 640) and (IMG / "social-preview.jpg").stat().st_size < 1_000_000       # GitHub accepts up to 1 MB
    for p in (SRC / "crops").glob("*.jpg"):
        assert Image.open(p).size in {(1000, 600), (1000, 500)}, p.name


def test_no_image_carries_metadata():
    """Photos are re-encoded without EXIF, GPS or text chunks. A leftover would leak a camera, a place or a path."""
    paths = [p for p in ROOT.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"} and ".venv" not in p.parts and ".cache" not in p.parts]
    assert len(paths) > 30
    for p in paths:
        im = Image.open(p)
        assert not im.getexif(), p
        assert not ({"exif", "xmp", "XML:com.adobe.xmp", "icc_profile"} & set(im.info)), p
        assert not [k for k in im.info if k.lower() in {"comment", "description", "software", "author", "copyright"}] and not getattr(im, "text", {}), p
