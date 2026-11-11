import json
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "bench"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from onmodel.judge import VlmResult  # noqa: E402
from onmodel.taxonomy import ITEMS  # noqa: E402


def make_image(path, size=(64, 80), color=(10, 120, 200)):
    Image.new("RGB", size, color).save(path, "JPEG")
    return Path(path)


def make_checklist(answers=None, defects=None, ref="", gen=""):
    """A checklist where every item is "same", with the given items changed: make_checklist({"text": "different"})."""
    items = {k: {"answer": "same"} for k in ITEMS}
    for k, v in (answers or {}).items():
        items[k] = v if isinstance(v, dict) else {"answer": v}
    return {"items": items, "defects": [{"code": c} if isinstance(c, str) else c for c in (defects or [])], "text_in_reference": ref, "text_in_generated": gen}


class Scripted:
    """A reviewer that returns scripted answers. A request for a bounding box gets a fixed box. Records the checklist calls."""

    name = "scripted"

    def __init__(self, *answers, box=(100, 100, 900, 900)):
        self.answers = list(answers)
        self.box = list(box)
        self.calls = []

    def ask_json(self, prompt, images, schema):
        if "box_2d" in json.dumps(schema):
            return VlmResult(ok=True, data={"box_2d": self.box})
        self.calls.append({"prompt": prompt, "images": len(images)})
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return a if isinstance(a, VlmResult) else VlmResult(ok=True, data=a)


@pytest.fixture
def bench_dir():
    return BENCH


@pytest.fixture
def imgs(tmp_path):
    return {
        "product": make_image(tmp_path / "product.jpg", (64, 80), (10, 120, 200)),
        "result": make_image(tmp_path / "result.jpg", (90, 120), (200, 150, 100)),
        "pose": make_image(tmp_path / "pose.jpg", (90, 120), (100, 100, 100)),
    }
