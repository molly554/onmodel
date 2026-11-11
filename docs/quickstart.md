# Quickstart

Five minutes from nothing to a scorecard. Python 3.10 or newer.

## 1. Install

```bash
pip install git+https://github.com/molly554/onmodel
```

To work with the benchmark you need a clone, because the benchmark data lives in the repository:

```bash
git clone https://github.com/molly554/onmodel
cd onmodel
pip install -e ".[dev]"
```

## 2. Score a checklist: no key, no network

A reviewer answers nine questions; `onmodel score` turns the answers into a scorecard. Try it on the example that ships with the skill:

```bash
onmodel score skills/fidelity-check/references/checklist-example.json
```

The exit code is 0 for Verified, 1 for not Verified, 2 for an invalid checklist. Add `--json` for a machine-readable card.

## 3. Check one photo

Set a Gemini key in your shell. onmodel reads it from the environment and never prints or stores it. Reviewing a photo sends the images to Google.

```bash
export GEMINI_API_KEY=your-key                    # PowerShell: $env:GEMINI_API_KEY = "your-key"
onmodel check product.jpg result.jpg --verb holding --tags text,hand --pose pose.jpg
```

- `--verb` says whether the person is `wearing` or `holding` the product. `--tags` lists the risks of the product: `text`, `glass`, `metal`, `gem`, `lace`, `black`, `pattern`, `multi`, `hand`, `worn_hand`, `person_in_photo`. They are hints for the reviewer.
- `--pose` adds the pose photo the engine was given, so the reviewer can answer the pose question. Without it, that question is "not applicable".
- `--expect-text "LABELLO CLASSIC"` gives the words printed on the product. The text rule is more reliable with known words than with a model's transcription.
- `--json` prints the full judgment record; `--out record.json` writes it to a file.
- `--judge` chooses the reviewer: a Gemini model name (the default is `gemini-3.5-flash-lite`), `mock` for a test without a key, or `package.module:ClassName` for your own.

Each review sends three or four images to the reviewer. The record keeps the token counts the API reported in `usage`. We have not priced the reviewer, so check the vendor's price list before you review thousands of photos.

### The text rule with OCR

By default the text rule compares the reviewer's own transcriptions. For a check that does not depend on the reviewer's reading, install Tesseract and its Python wrapper:

```bash
pip install "onmodel[ocr]"
onmodel check product.jpg result.jpg --tags text --ocr tesseract
```

## 4. Get a starter prompt

```bash
onmodel recipe --verb holding --tags text,hand          # a prompt, from the starter recipes
onmodel analyze product.jpg --prompt v1                 # tags and parts from a product photo, then the prompt
```

`analyze` uses the same reviewer settings as `check`. The recipes are a tested baseline, not tuned prompts: [starter recipes](../skills/shoot-brief/references/recipes.md).

## 5. Run the benchmark

```bash
onmodel bench smoke                        # the whole pipeline offline with mocks: proves the install works
onmodel bench list                         # the 9 cases and where each photo comes from
onmodel bench fetch                        # download the 5 linked photos and check their sha256
onmodel bench run --engine gemini-nano-banana-2.1 --res 2k            # a dry run: the plan and the estimated cost
onmodel bench run --engine gemini-nano-banana-2.1 --res 2k --out my-run --yes
onmodel bench judge --run my-run
onmodel bench report --run my-run
```

A real run needs `GEMINI_API_KEY` and costs money. It stops when the estimated spend reaches `--budget` (5 US dollars by default) and can be resumed with the same `--out`. To see what a run costs, run it without `--yes` first.

Your own engine: [bring your engine](bring-your-engine.md). Your own labels: [calibration](calibration.md).

## Troubleshooting

| Message | What to do |
|---|---|
| `GEMINI_API_KEY is not set` | export it in the same shell you run onmodel from |
| `no bench folder found` | run the command from a clone of the repository, or pass `--bench PATH` |
| `the product photo of K01 is not on disk` | run `onmodel bench fetch` first: that case is a linked photo |
| `the file at the URL changed` | the photo at the source is not the one we measured. `fetch` refuses it on purpose; open an issue |
| garbled characters in a Windows console | run `chcp 65001` or use Windows Terminal |
