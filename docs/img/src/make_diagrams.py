#!/usr/bin/env python3
"""Build the diagrams in docs/img/*.svg.

    python docs/img/src/make_diagrams.py

Standard library only. Every number in findings.svg is read from bench/runs/mini-test-v0.1/summary.json, so the figure cannot drift from the data.
The vocabulary in rubric.svg is read from onmodel/taxonomy.py. Colors are explicit (no CSS variables) and every figure has its own white card,
so they read the same on a light and a dark GitHub theme.
"""
from __future__ import annotations

import json
import sys
import textwrap
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE.parent
sys.path.insert(0, str(ROOT))

from onmodel.taxonomy import DEFECTS, FIDELITY_ITEMS, OTHER_ITEMS, VETO_CODES  # noqa: E402

FONT = "'Segoe UI', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
INK, MUTED, LINE, CARD = "#1f2328", "#59636e", "#d0d7de", "#ffffff"
TEAL = {"stroke": "#0f766e", "fill": "#e6f6f4", "ink": "#0b514b"}
AMBER = {"stroke": "#b45309", "fill": "#fef3c7", "ink": "#7c3a06"}
GRAY = {"stroke": "#6e7781", "fill": "#f0f2f4", "ink": "#424a53"}
GREEN = {"stroke": "#1a7f37", "fill": "#dafbe1", "ink": "#116329"}
RED = {"stroke": "#cf222e", "fill": "#ffebe9", "ink": "#a40e26"}
NEUTRAL = {"stroke": LINE, "fill": "#f6f8fa", "ink": INK}
CHAR = 0.55          # average glyph width as a fraction of the font size; generous, so text fits in any of the fallback fonts


class Svg:
    def __init__(self, w: int, h: int, title: str, desc: str):
        self.w, self.h, self.parts = w, h, []
        self.title, self.desc = title, desc

    def add(self, s: str) -> None:
        self.parts.append(s)

    def rect(self, x, y, w, h, style, rx=12, sw=1.5, dash=None) -> None:
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{style["fill"]}" stroke="{style["stroke"]}" stroke-width="{sw}"{d}/>')

    def text(self, x, y, s, size=16, weight=400, fill=INK, anchor="start", family=FONT, spacing=None) -> None:
        ls = f' letter-spacing="{spacing}"' if spacing else ""
        self.add(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{ls}>{escape(s)}</text>')

    def para(self, x, y, s, width, size=16, lh=1.4, weight=400, fill=INK, family=FONT, anchor="start") -> float:
        """Wrapped text. Returns the y of the line after the last one."""
        chars = max(8, int(width / (size * CHAR)))
        for line in textwrap.wrap(s, chars):
            self.text(x, y, line, size, weight, fill, anchor, family)
            y += size * lh
        return y

    def arrow(self, x1, y1, x2, y2, color=MUTED, sw=2.5) -> None:
        self.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}" marker-end="url(#arrow)"/>')

    def pill(self, x, y, w, h, label, style, size=15, weight=600) -> None:
        self.rect(x, y, w, h, style, rx=h / 2, sw=1.2)
        self.text(x + w / 2, y + h / 2 + size * 0.34, label, size, weight, style["ink"], "middle")

    def render(self) -> str:
        defs = (f'<defs><marker id="arrow" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{MUTED}"/></marker></defs>')
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" xml:space="preserve" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" role="img" aria-labelledby="t d">'
                f'<title id="t">{escape(self.title)}</title><desc id="d">{escape(self.desc)}</desc>{defs}'
                f'<rect x="0.75" y="0.75" width="{self.w - 1.5}" height="{self.h - 1.5}" rx="16" fill="{CARD}" stroke="{LINE}" stroke-width="1.5"/>')
        return head + "\n".join(self.parts) + "</svg>\n"


def header(s: Svg, title: str, sub: str) -> None:
    s.text(44, 64, title, 30, 700)
    s.text(44, 96, sub, 18, 400, MUTED)


# ------------------------------------------------------------------------------------------------------------------ how it works
def how_it_works() -> str:
    s = Svg(1200, 640, "How an onmodel check works",
            "A product photo, a pose photo and a prompt go into your image engine. The result photo, with the product photo, goes through onmodel check: "
            "a locator crops the product, a reviewer answers nine questions, a text rule compares printed words, and code computes the scorecard.")
    header(s, "How a check works", "One product photo and one result photo in. One scorecard out.")

    # inputs
    s.text(44, 140, "YOU HAVE", 13, 700, MUTED, spacing=1.2)
    for i, (t, sub) in enumerate((("Product photo", "the real product"), ("Pose photo", "a person posing with something else"), ("Prompt", "a starter recipe by risk tag"))):
        y = 152 + i * 74
        s.rect(44, y, 270, 62, NEUTRAL, rx=10)
        s.text(62, y + 27, t, 18, 700)
        s.text(62, y + 49, sub, 14, 400, MUTED)
    for y, y_end in ((183, 226), (257, 257), (331, 288)):
        s.arrow(318, y, 380, y_end, MUTED, 2)

    # engine
    s.rect(384, 192, 250, 130, AMBER, rx=12, dash="7 5")
    s.text(509, 238, "Your image engine", 20, 700, AMBER["ink"], "middle")
    s.para(509, 264, "Any engine. A Gemini adapter and a mock are included.", 210, 15, 1.35, 400, AMBER["ink"], anchor="middle")
    s.arrow(638, 257, 700, 257, MUTED, 2.5)

    # result
    s.rect(704, 192, 230, 130, NEUTRAL, rx=12)
    s.text(819, 238, "Result photo", 20, 700, INK, "middle")
    s.para(819, 264, "A person wearing or holding the product.", 190, 15, 1.35, 400, MUTED, anchor="middle")

    # note
    s.rect(958, 192, 198, 130, GRAY, rx=12)
    s.para(976, 222, "onmodel only needs the photos. It does not care how they were made, or by whom.", 164, 15, 1.4, 400, GRAY["ink"])

    s.arrow(819, 326, 819, 372, TEAL["stroke"], 3)

    # the check
    s.rect(44, 378, 1112, 232, TEAL, rx=16, sw=2)
    s.text(66, 410, "onmodel check", 20, 700, TEAL["ink"])
    s.text(1134, 410, "product photo + result photo (+ pose photo)", 15, 400, TEAL["ink"], "end")
    steps = (("1  Find and zoom", "A locator finds the product in the result and crops it, so print and fine detail can be read."),
             ("2  Nine fixed questions", "A reviewer, a model or a person, answers same, minor, different or cannot tell. No free scores."),
             ("3  Text rule", "Words printed on the real product are looked up in the result. It can only make a verdict stricter."),
             ("4  Code scores", "Points, veto and Verified come from a short script. The same answers always give the same card."))
    x = 66
    for t, d in steps:
        s.rect(x, 424, 208, 164, CARD if False else {"fill": "#ffffff", "stroke": TEAL["stroke"]}, rx=10, sw=1.2)
        s.text(x + 14, 452, t, 16, 700, TEAL["ink"])
        s.para(x + 14, 478, d, 182, 14.5, 1.38, 400, INK)
        x += 220
    # scorecard
    s.rect(x + 2, 424, 1134 - (x + 2) - 0, 164, {"fill": "#1f2328", "stroke": "#1f2328"}, rx=10)
    sx = x + 18
    lines = ("Fidelity   0 / 2", "Pose       2 / 2", "Identity   2 / 2", "Artifacts  2 / 2", "Scale      2 / 2")
    for i, ln in enumerate(lines):
        s.text(sx, 448 + i * 19, ln, 13.5, 400, "#e6edf3", family=MONO)
    s.text(sx, 552, "Total 8 / 10", 13.5, 700, "#e6edf3", family=MONO)
    s.text(sx, 572, "Verified: no", 13.5, 700, "#ffb3b8", family=MONO)
    return s.render()


# ------------------------------------------------------------------------------------------------------------------ rubric
def rubric() -> str:
    s = Svg(1200, 616, "The onmodel rubric",
            "Nine questions in five dimensions of 0 to 2 points each. Product fidelity is the lowest of shape, color, material, text and parts. "
            "A photo is Verified when product fidelity is 2 of 2, the total is at least 8 of 10 and no veto defect was found.")
    header(s, "Nine questions, five dimensions, one verdict", "A reviewer answers. Code scores. The questions never change.")

    # dimension cards
    y0, h = 128, 196
    white_teal = {"fill": "#ffffff", "stroke": TEAL["stroke"], "ink": TEAL["ink"]}
    s.rect(44, y0, 410, h, TEAL, rx=12, sw=2)
    s.text(62, y0 + 34, "Product fidelity", 21, 700, TEAL["ink"])
    s.text(62, y0 + 58, "0 to 2 points: the lowest of the five", 15, 400, TEAL["ink"])
    chip_w = {"shape": 64, "color": 60, "material": 86, "text": 52, "parts": 60}
    x = 62
    for k in FIDELITY_ITEMS:
        s.pill(x, y0 + 82, chip_w[k], 30, k.capitalize(), white_teal, 14, 600)
        x += chip_w[k] + 8
    s.para(62, y0 + 146, "Does the product still look like the real one?", 388, 15, 1.35, 400, TEAL["ink"])

    cards = {"pose": ("Pose", "Follows the pose photo: pose, framing, camera angle."),
             "identity": ("Identity", "Same person. No hand, mannequin or person from the product photo."),
             "artifacts": ("Artifacts", "No extra fingers, melted objects, stray text or watermarks."),
             "scale": ("Scale", "The product's real size is right against the body.")}
    x = 470
    for k in OTHER_ITEMS:
        t, d = cards[k]
        s.rect(x, y0, 162, h, NEUTRAL, rx=12)
        s.text(x + 16, y0 + 34, t, 20, 700)
        s.text(x + 16, y0 + 58, "0 to 2 points", 15, 400, MUTED)
        s.para(x + 16, y0 + 90, d, 134, 15, 1.38, 400, INK)
        x += 174

    # answers
    ya = y0 + h + 28
    s.text(44, ya + 24, "Each answer scores", 16, 700)
    x = 232
    for label, pts, st in (("same", 2, GREEN), ("minor", 1, AMBER), ("different", 0, RED), ("cannot tell", 1, GRAY), ("not applicable", 2, GRAY)):
        w = 38 + len(label) * 9 + 36
        s.rect(x, ya, w, 36, st, rx=18, sw=1.2)
        s.text(x + 18, ya + 24, label, 15, 600, st["ink"])
        s.text(x + w - 16, ya + 24, str(pts), 16, 700, st["ink"], "end")
        x += w + 12

    # verdict
    yv = ya + 62
    s.rect(44, yv, 1112, 176, TEAL, rx=14, sw=2)
    s.text(66, yv + 38, "Verified", 22, 700, TEAL["ink"])
    s.text(168, yv + 38, "=   product fidelity 2 / 2   +   total at least 8 / 10   +   no veto defect", 20, 600, TEAL["ink"])
    names = {"WRONG_PRODUCT": "wrong product", "COLOR_FAMILY": "wrong color family", "PART_MISSING": "missing part", "PART_MERGED": "merged parts",
             "PART_EXTRA": "extra part", "TEXT_WRONG": "wrong large word or logo", "LEAK_HAND_MANNEQUIN": "hand or mannequin carried over",
             "SEVERE_DEFORMITY": "severe deformity"}
    assert set(names) == set(VETO_CODES), "update the veto names in make_diagrams.py"
    s.text(66, yv + 74, "Any one veto defect blocks Verified, whatever the points say:", 16, 400, TEAL["ink"])
    x, y = 66, yv + 92
    for code in VETO_CODES:
        label = names[code]
        w = len(label) * 8.6 + 30
        if x + w > 1134:
            x, y = 66, y + 38
        s.pill(x, y, w, 30, label, white_teal, 14.5, 600)
        x += w + 10
    assert len(DEFECTS) == 18
    return s.render()



# ------------------------------------------------------------------------------------------------------------------ repository map
def repo_map() -> str:
    s = Svg(1200, 700, "What is in the onmodel repository",
            "Seven jobs, from understanding a product photo to running a service. Open parts are code under Apache-2.0 and data under CC0 or CC BY 4.0; "
            "the starter recipes are a tested baseline, not tuned; a hosted service with accounts and billing is not part of the repository.")
    header(s, "What is in this repository", "From a product photo to a verdict, and which parts you get.")
    x = 44
    for label, st in (("Open: code Apache-2.0, data CC0 or CC BY 4.0", TEAL), ("Starter: a tested baseline, not tuned", AMBER), ("Not here", GRAY)):
        w = len(label) * 8.6 + 40
        s.rect(x, 116, w, 32, st, rx=16, sw=1.2)
        s.text(x + 18, 137, label, 14.5, 600, st["ink"])
        x += w + 12

    rows = (
        ("Understand the product", [(TEAL, "onmodel analyze", "risk tags, parts and printed text from a product photo")]),
        ("Choose a recipe and a pose", [(AMBER, "Starter recipes", "one prompt rule per risk tag"), (TEAL, "9 pose photos", "AI-generated, CC0")]),
        ("Generate the photo", [(TEAL, "Engine adapters", "Gemini, a mock, or your own in about 20 lines")]),
        ("Check the photo", [(TEAL, "onmodel check", "nine questions, text rule, scorer, JSON record")]),
        ("Ask your coding agent", [(TEAL, "Two agent skills", "fidelity-check and shoot-brief, no key needed")]),
        ("Compare engines and recipes", [(TEAL, "onmodel bench", "fetch, run, judge, report: 4 CC0 or public-domain cases bundled, 5 linked by sha256")]),
        ("Run it as a service", [(GRAY, "Hosted product", "accounts, billing and a web interface are not part of this project")]),
    )
    y = 166
    for job, mods in rows:
        s.rect(44, y, 300, 62, NEUTRAL, rx=10)
        s.text(62, y + 38, job, 17.5, 700)
        s.arrow(350, y + 31, 392, y + 31, MUTED, 2)
        x, total = 398, 1156 - 398
        w = (total - 12 * (len(mods) - 1)) / len(mods)
        for st, t, d in mods:
            s.rect(x, y, w, 62, st, rx=10, sw=1.6)
            s.text(x + 16, y + 27, t, 17.5, 700, st["ink"])
            s.text(x + 16, y + 49, d, 14.5, 400, st["ink"])
            assert len(d) * 14.5 * CHAR < w - 30, f"text too long for its box: {d}"
            x += w + 12
        y += 74
    return s.render()



# ------------------------------------------------------------------------------------------------------------------ findings
def findings() -> str:
    d = json.loads((ROOT / "bench" / "runs" / "mini-test-v0.1" / "summary.json").read_text(encoding="utf-8"))
    sp, parts, lc, hem, rv, tr = d["small_print"], d["parts"]["K10"], d["label_covered"]["by_case"]["K01"], d["hem_length"], d["reviewers"], d["text_rule"]
    cards = (
        ("SMALL PRINT", f"{sp['1k']['garbled']} of {sp['1k']['photos']}", f"photos at 1K had garbled small print. At 2K: {sp['2k']['garbled']} of {sp['2k']['photos']}.", RED),
        ("SEVERAL PIECES", f"{parts['v0']['with_part_defect']} of {parts['v0']['photos']}",
         f"photos of a two-tube set lost a piece with a generic prompt. With the product's rules: {parts['v1']['with_part_defect']} of {parts['v1']['photos']} at 1K, {parts['v1_2k']['with_part_defect']} of {parts['v1_2k']['photos']} at 2K.", AMBER),
        ("FINGERS ON THE LABEL", f"{lc['label_covered']} of {lc['photos']}", "photos of one tin had fingers over the label, even though the prompt said not to.", AMBER),
        ("HEM LENGTH", f"{hem['followed_the_pose_photo']} of {hem['photos']}", "dress photos took the hem length from the pose photo, not from the product.", AMBER),
        ("MODEL REVIEWERS", f"{rv['judges_agree_with_each_other']:.0%}", f"agreement between two model reviewers on the same photos (kappa {rv['kappa_between_judges']}). One model reviewer alone is not enough.", RED),
        ("TEXT RULE", f"{tr['garbled_small_print']['flagged']} of {tr['garbled_small_print']['photos']}",
         f"garbled-print photos flagged by a free OCR rule, and {tr['fail']['flagged']} of {tr['fail']['photos']} failures. It also flagged {tr['ok']['flagged']} of {tr['ok']['photos']} good photos.", TEAL),
    )
    s = Svg(1200, 644, "What the onmodel mini test found",
            f"Preliminary results from {d['photos']} photos of {len(d['cases'])} products, two photos per cell, one image engine, with our own labels made with AI assistance. "
            + " ".join(f"{c[0].title()}: {c[1]} {c[2]}" for c in cards))
    header(s, "What we found (preliminary)", f"{d['photos']} photos of {len(d['cases'])} products, two per cell, one image engine, our own labels. Directions, not pass rates.")
    cw, ch, gx, gy, x0, y0 = 360, 196, 16, 16, 44, 126
    for i, (kicker, big, text, st) in enumerate(cards):
        cx, cy = x0 + (i % 3) * (cw + gx), y0 + (i // 3) * (ch + gy)
        s.rect(cx, cy, cw, ch, st, rx=12, sw=1.6)
        s.text(cx + 18, cy + 32, kicker, 13, 700, st["ink"], spacing=0.8)
        s.text(cx + 18, cy + 104, big, 44 if len(big) < 7 else 38, 700, st["ink"])
        s.para(cx + 172, cy + 60, text, cw - 172 - 16, 15, 1.38, 400, INK)
    yf = y0 + 2 * ch + gy + 18
    s.rect(44, yf, 1112, 66, NEUTRAL, rx=12)
    s.para(62, yf + 27, "Some problems are not prompt problems. Fingers over a label and a hem that follows the pose photo are fixed by choosing the pose, not by rewording. "
                        "Method, data and limits: docs/mini-test.md.", 1076, 15.5, 1.4, 400, INK)
    return s.render()



FIGURES = {"how-it-works.svg": how_it_works, "rubric.svg": rubric, "repo-map.svg": repo_map, "findings.svg": findings}


def main() -> int:
    for name, fn in FIGURES.items():
        (OUT / name).write_text(fn(), encoding="utf-8", newline="\n")
        print(f"wrote docs/img/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
