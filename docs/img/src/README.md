# Figure sources

| Figure | Built by | Needs |
|---|---|---|
| `hero.png` and `social-preview.jpg` | `python docs/img/src/make_hero.py` | Pillow, and Chrome or Chromium (`CHROME=/path/to/chrome` if it is not found) |
| `how-it-works.svg`, `rubric.svg`, `repo-map.svg`, `findings.svg` | `python docs/img/src/make_diagrams.py` | the standard library |

`make_hero.py` crops `bench/golden/images/K04.jpg` and two photos from `bench/runs/mini-test-v0.1/images/` into `crops/`, computes the two scorecards with `onmodel.scoring.score`, writes `hero.html` and `social.html`, and renders them with headless Chrome. The scorecards come from checklists filled in by hand from our review notes, not from a model reviewer; the figure says so.

`make_diagrams.py` takes the numbers of `findings.svg` from `bench/runs/mini-test-v0.1/summary.json` and the vocabulary of `rubric.svg` from `onmodel/taxonomy.py`, so the figures cannot drift from the data and the code.

After rebuilding, run `python scripts/refresh_assets.py` to update the hashes in `bench/ASSETS.json`.

GitHub does not let a script set the social preview image. Upload `social-preview.jpg` by hand: Settings, Social preview.

The figures are licensed under CC BY 4.0. The crops are CC0.
