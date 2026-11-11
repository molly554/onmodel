# mini-test-v0.1

The published run of the pilot described in [docs/mini-test.md](../../../docs/mini-test.md). Preliminary: 2 photos per cell, one engine family, labels by us with AI assistance.

| File | What it is |
|---|---|
| `photos.csv` | one row per photo of the 9 public products (52 rows): our label and defect tags, the verdicts of two model reviewers, the OCR recall, the time per photo. `published` says whether the photo itself is in `images/` |
| `summary.json` | every number quoted in the README and in docs/mini-test.md. Produced from `photos.csv` by `python scripts/recompute_mini_test.py --write` |
| `run.json` | engine, recipe version, variants and cases of the pilot, in the format of a run folder |
| `images/` | the 19 photos made from the four product photos that are CC0 or public domain. CC0, see [ATTRIBUTION.md](../../../ATTRIBUTION.md) |

The photos made from the five CC BY-SA product photos are not published. Their rows are in `photos.csv`.

The names of the photos follow the benchmark: `<case>_<variant>_<res>_s<sample>.jpg`. The four photos from the larger `gemini-3-pro-image` model are named `<case>_v1_pro_s1.jpg` in `photos.csv`; they are not published.

To review the published photos again, copy the folder first, because `judge` writes into the run folder:

```bash
cp -r bench/runs/mini-test-v0.1 bench/runs/my-rejudge
onmodel bench judge --run my-rejudge --judge gemini-3.5-flash-lite --cases K04,J01,A02,A04
onmodel bench report --run my-rejudge
onmodel bench calibrate --run my-rejudge --labels bench/runs/mini-test-v0.1/photos.csv
```
