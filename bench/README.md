# bench

The benchmark data and the runs. The commands are in [docs/quickstart.md](../docs/quickstart.md).

| Path | What it is |
|---|---|
| `cases.yaml` | the 9 cases: product, tags, pose photo, the words printed on the product, and where the photo comes from. Checked against [schemas/cases.schema.json](../schemas/cases.schema.json) |
| `golden/images/` | the 4 product photos that may be redistributed (CC0 or public domain) |
| `poses/` | the 9 pose photos: AI-generated adults, CC0, with the generation prompt of each in `ASSETS.json` |
| `ASSETS.json` | every image in the repository with its sha256, license and origin. `scripts/check_assets.py` enforces it |
| `runs/mini-test-v0.1/` | the published pilot run: [see its README](runs/mini-test-v0.1/README.md) |
| `.cache/` | the 5 linked photos after `onmodel bench fetch`. Never committed |
| `runs/<name>/` | your own runs. Never committed (only `mini-test-v0.1` is) |

## Bundled and linked photos

A **bundled** photo is in this repository and is CC0 or public domain.

A **linked** photo is shared under CC BY-SA. We do not copy it. `cases.yaml` records its URL, its author and the sha256 of the file we measured; `onmodel bench fetch` downloads it from an allow-listed host, refuses a file whose hash differs, and re-encodes it as a JPEG with a long edge of at most 2048 px.

## A run folder

```
runs/<name>/
  run.json            engine, recipe version, variants, resolutions, cases
  images/             <case>_<variant>_<res>_s<sample>.jpg, for example K04_v1_2k_s1.jpg
  ledger.jsonl        one line per generation: prompt, prompt hash, engine stamp, cost, time, ok or error
  judgments.jsonl     one line per review: the checklist, the text rule, the scorecard
  report.md, summary.json, scores.csv      from `onmodel bench report`
  calibration.json    from `onmodel bench calibrate`
```

The formats are in [schemas/](../schemas): `run-record.schema.json` for a ledger line and `judgment.schema.json` for a review.
