#!/usr/bin/env python3
"""Build docs/img/hero.png from files in this repository.

    python docs/img/src/make_hero.py            crops + hero.html + hero.png
    python docs/img/src/make_hero.py --no-png   crops + hero.html only

Needs Pillow and, for the PNG, Chrome or Chromium (set CHROME=/path/to/chrome if it is not found).

The figure: one product photo (CC0), two photos generated from it with the same prompt, the same pose photo and the same engine; only the
render size differs (1K and 2K). The scorecards under the photos are computed by onmodel.scoring.score from checklists filled in by hand
from our review notes (bench/runs/mini-test-v0.1/photos.csv), not produced by a model reviewer.
"""
from __future__ import annotations

import html
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from onmodel.scoring import score  # noqa: E402
from onmodel.taxonomy import ITEMS  # noqa: E402

PRODUCT = ROOT / "bench" / "golden" / "images" / "K04.jpg"
R1K = ROOT / "bench" / "runs" / "mini-test-v0.1" / "images" / "K04_v1_1k_s1.jpg"
R2K = ROOT / "bench" / "runs" / "mini-test-v0.1" / "images" / "K04_v1_2k_s1.jpg"
CROPS = HERE / "crops"

LF = chr(10)              # write the HTML with Unix line endings on every platform
CONTEXT = (1000, 600)     # 5:3, the full picture of the scene around the product
LABEL = (1000, 500)       # 2:1, the label enlarged


def load(p: Path) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(p)).convert("RGB")


def crop_frac(im: Image.Image, box, size, rotate_cw=False) -> Image.Image:
    """box = (x0, y0, x1, y1) as fractions of the image. Optionally turn the crop 90 degrees clockwise, so vertical print reads left to right."""
    w, h = im.size
    c = im.crop((round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h)))
    if rotate_cw:
        c = c.rotate(-90, expand=True)
    return c.resize(size, Image.LANCZOS)


def build_crops() -> dict:
    CROPS.mkdir(parents=True, exist_ok=True)
    prod, a, b = load(PRODUCT), load(R1K), load(R2K)
    # the product photo: the tube lies on its side, print reads left to right
    out = {
        "product-context": crop_frac(prod, (0.0, 0.10, 1.0, 0.90), CONTEXT),
        "product-label": crop_frac(prod, (0.33, 0.30, 0.80, 0.615), LABEL),
        # the results: the person holds the tube upright, so the print runs bottom to top; turn the label crop to read it
        "r1k-context": crop_frac(a, (0.0, 0.275, 1.0, 0.725), CONTEXT),
        "r1k-label": crop_frac(a, (0.368, 0.358, 0.592, 0.692), LABEL, rotate_cw=True),
        "r2k-context": crop_frac(b, (0.0, 0.275, 1.0, 0.725), CONTEXT),
        "r2k-label": crop_frac(b, (0.368, 0.358, 0.592, 0.692), LABEL, rotate_cw=True),
    }
    for name, im in out.items():
        im.save(CROPS / f"{name}.jpg", "JPEG", quality=90, optimize=True)
    return {k: f"crops/{k}.jpg" for k in out}


def checklist(**changes) -> dict:
    items = {k: {"answer": "same"} for k in ITEMS}
    items.update(changes)
    return {"items": items, "defects": []}


def scorecards() -> dict:
    garbled = checklist(text={"answer": "different", "evidence": "small print is gibberish"})
    garbled["defects"] = [{"code": "TEXT_GARBLE"}]
    return {"1k": score(garbled), "2k": score(checklist())}


def chip(card, text_note: str) -> str:
    ok = card.verified
    cls = "ok" if ok else "bad"
    return (f'<div class="chip {cls}"><span class="verdict">Verified: {"yes" if ok else "no"}</span>'
            f'<span class="nums">Fidelity {card.dims["fidelity"]} / 2 &nbsp;&middot;&nbsp; Total {card.total} / 10</span>'
            f'<span class="note">{html.escape(text_note)}</span></div>')


def build_html(crops: dict, cards: dict) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>onmodel hero</title>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; }}
  body {{ width: 1600px; height: 1000px; background: #ffffff; color: #1f2328; padding: 44px 64px 0; position: relative;
         font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial, sans-serif; }}
  h1 {{ margin: 0; font-size: 40px; line-height: 1.15; letter-spacing: -0.4px; font-weight: 700; white-space: nowrap; }}
  .sub {{ margin: 10px 0 0; font-size: 23px; color: #59636e; line-height: 1.35; }}
  .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 36px; margin-top: 26px; }}
  .card .kicker {{ font-size: 18px; font-weight: 700; letter-spacing: 1.4px; text-transform: uppercase; color: #59636e; margin-bottom: 10px; }}
  .card .kicker b {{ color: #1f2328; }}
  .shot {{ width: 100%; display: block; border-radius: 8px; border: 1px solid #d0d7de; }}
  .label {{ margin-top: 12px; border-width: 4px; }}
  .label.real {{ border-color: #8c959f; }} .label.bad {{ border-color: #cf222e; }} .label.ok {{ border-color: #1a7f37; }}
  .cap {{ margin: 8px 0 0; font-size: 19px; color: #59636e; min-height: 26px; white-space: nowrap; }}
  .chip {{ margin-top: 12px; border-radius: 8px; padding: 12px 16px; display: grid; gap: 2px; min-height: 116px; align-content: start; }}
  .chip.bad {{ background: #ffebe9; border: 1px solid #ff8182; }} .chip.ok {{ background: #dafbe1; border: 1px solid #4ac26b; }}
  .chip.plain {{ background: #f6f8fa; border: 1px solid #d0d7de; }}
  .chip .verdict {{ font-size: 26px; font-weight: 700; }}
  .chip.bad .verdict {{ color: #a40e26; }} .chip.ok .verdict {{ color: #116329; }} .chip.plain .verdict {{ color: #1f2328; }}
  .chip .nums {{ font-size: 20px; font-variant-numeric: tabular-nums; }} .chip .note {{ font-size: 19px; color: #424a53; }}
  footer {{ position: absolute; left: 64px; right: 64px; bottom: 22px; font-size: 16px; line-height: 1.4; color: #59636e; }}
</style></head>
<body>
  <h1>Same product, same prompt, same engine. Only the render size changed.</h1>
  <p class="sub">The small print under the logo is the first thing an image engine gets wrong. Real photos from our mini test, label enlarged.</p>
  <div class="grid">
    <div class="card">
      <div class="kicker"><b>Real product</b> &nbsp;photo</div>
      <img class="shot" src="{crops['product-context']}" alt="The real product: a blue lip balm tube on a table">
      <img class="shot label real" src="{crops['product-label']}" alt="The real label: Labello Classic, Soin Protecteur et Nourrissant au quotidien">
      <p class="cap">Small print: Soin Protecteur et Nourrissant au quotidien</p>
      <div class="chip plain"><span class="verdict">Ground truth</span><span class="nums">The photo every result is checked against</span></div>
    </div>
    <div class="card">
      <div class="kicker"><b>Generated at 1K</b> &nbsp;896 &times; 1200</div>
      <img class="shot" src="{crops['r1k-context']}" alt="A person holding the product, generated at 1K">
      <img class="shot label bad" src="{crops['r1k-label']}" alt="The label of the 1K photo: the logo is right, the small print is gibberish">
      <p class="cap">Logo right. Small print is gibberish.</p>
      {chip(cards['1k'], 'text: different (TEXT_GARBLE)')}
    </div>
    <div class="card">
      <div class="kicker"><b>Generated at 2K</b> &nbsp;1792 &times; 2400</div>
      <img class="shot" src="{crops['r2k-context']}" alt="A person holding the product, generated at 2K">
      <img class="shot label ok" src="{crops['r2k-label']}" alt="The label of the 2K photo: logo and small print are both correct">
      <p class="cap">Logo right. Small print reads correctly.</p>
      {chip(cards['2k'], 'nine of nine checks: same')}
    </div>
  </div>
  <footer>Engine: gemini-nano-banana-2.1, recipe v1, sample 1 of 2 (sample 2 behaved the same at each size). Product photo: Wikimedia Commons, CC0. The scorecards come from
  <code>onmodel score</code> on a checklist filled in by hand from our review notes, not from a model reviewer. Method and data: docs/mini-test.md</footer>
</body></html>
"""


def build_social_html(crops: dict, cards: dict) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>onmodel social preview</title>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; }}
  body {{ width: 1280px; height: 640px; background: #ffffff; color: #1f2328; position: relative; overflow: hidden;
         font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial, sans-serif; }}
  .left {{ position: absolute; left: 72px; top: 0; bottom: 0; width: 560px; display: flex; flex-direction: column; justify-content: center; }}
  .name {{ font-size: 84px; font-weight: 800; letter-spacing: -2px; line-height: 1; }}
  .tag {{ margin-top: 22px; font-size: 38px; font-weight: 600; line-height: 1.2; letter-spacing: -0.4px; }}
  .sub {{ margin-top: 18px; font-size: 25px; color: #59636e; }}
  .url {{ position: absolute; left: 72px; bottom: 44px; font-size: 22px; color: #59636e; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
  .right {{ position: absolute; right: 56px; top: 50px; width: 540px; display: grid; gap: 16px; }}
  .shot {{ position: relative; }}
  .shot img {{ display: block; width: 100%; border-radius: 12px; border: 5px solid; }}
  .shot.bad img {{ border-color: #cf222e; }} .shot.ok img {{ border-color: #1a7f37; }}
  .pill {{ position: absolute; left: 14px; bottom: 14px; padding: 7px 14px; border-radius: 999px; font-size: 21px; font-weight: 700; color: #fff; }}
  .bad .pill {{ background: #cf222e; }} .ok .pill {{ background: #1a7f37; }}
</style></head>
<body>
  <div class="left">
    <div class="name">onmodel</div>
    <div class="tag">Does your AI model photo still look like your product?</div>
    <div class="sub">A skill, a CLI and an open benchmark.</div>
  </div>
  <div class="url">github.com/molly554/onmodel</div>
  <div class="right">
    <div class="shot bad"><img src="{crops['r1k-label']}" alt=""><span class="pill">Generated at 1K &middot; {'Verified: yes' if cards['1k'].verified else 'Verified: no'}</span></div>
    <div class="shot ok"><img src="{crops['r2k-label']}" alt=""><span class="pill">Generated at 2K &middot; {'Verified: yes' if cards['2k'].verified else 'Verified: no'}</span></div>
  </div>
</body></html>
"""


def find_chrome() -> str | None:
    for c in (os.environ.get("CHROME"), shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser"),
              r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if c and Path(c).exists():
            return c
    return None


def render_png(html_path: Path, png_path: Path, width=1600, height=1000, scale=1.25) -> None:
    chrome = find_chrome()
    if not chrome:
        sys.exit("Chrome or Chromium not found. Set CHROME=/path/to/chrome, or run with --no-png and open hero.html yourself.")
    cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--force-device-scale-factor={scale}", f"--window-size={width},{height}",
           "--virtual-time-budget=1500", f"--screenshot={png_path}", html_path.as_uri()]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    crops = build_crops()
    cards = scorecards()
    page = HERE / "hero.html"
    page.write_text(build_html(crops, cards), encoding="utf-8", newline=LF)
    social = HERE / "social.html"
    social.write_text(build_social_html(crops, cards), encoding="utf-8", newline=LF)
    print(f"wrote {page.relative_to(ROOT)}, {social.relative_to(ROOT)} and {len(crops)} crops")
    if "--no-png" not in argv:
        png = HERE.parent / "hero.png"
        render_png(page, png)
        print(f"wrote {png.relative_to(ROOT)}")
        tmp = HERE / "_social.png"
        render_png(social, tmp, width=1280, height=640, scale=1)
        Image.open(tmp).convert("RGB").save(HERE.parent / "social-preview.jpg", "JPEG", quality=90, optimize=True)
        tmp.unlink()
        print(f"wrote {(HERE.parent / 'social-preview.jpg').relative_to(ROOT)} (upload it in Settings, Social preview)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
