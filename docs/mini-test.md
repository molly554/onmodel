# Mini test, v0.1

A small test we ran on 2026-11-10, before building anything else: do the problems we expected show up when an image engine puts a real product into a model photo, and can a model reviewer find them? It is a pilot. Read the numbers as directions to check, not as results.

Every number on this page is recomputed from [`bench/runs/mini-test-v0.1/photos.csv`](../bench/runs/mini-test-v0.1/photos.csv) by `python scripts/recompute_mini_test.py`.

## Setup

- **Products.** 10 real product photos from open sources (Wikimedia Commons and Open Beauty Facts). 9 are in the public set ([bench/cases.yaml](../bench/cases.yaml)). The tenth, a lace garment on a mannequin, was part of the test and is left out of the public set; its photos are not counted anywhere on this page.
- **Task.** Swap the product: the engine gets the product photo, a pose photo of a person holding or wearing something else, and a prompt. It should return the same person in the same pose with the real product.
- **Photos.** The pose photos are AI-generated adults. Two photos per cell. Engine: `gemini-nano-banana-2.1` at 1K and at 2K. One extra photo per text product from `gemini-3-pro-image` at 1K.
- **Prompts.** `v0` is a generic instruction. `v1` adds one rule per risk tag of the product. `repair` is a second pass that edits a `v1` photo to fix printed text. All three are in [`onmodel/data/starter-recipes.yaml`](../onmodel/data/starter-recipes.yaml).
- **Size.** 52 photos in the public set (56 in the whole test). About 22 seconds per photo at 1K and 42 seconds at 2K. The 56 calls cost about $2.6 to $2.8, estimated from the token counts the API returned. The reviewers' cost was not tracked separately.

## Our labels

Each photo is labelled `pass`, `minor` or `fail`, with defect tags. We made the labels by looking at every photo, with AI assistance. No second person checked them, so they are not an independent human panel. 26 photos are `pass`, 23 `minor` and 3 `fail`. All labels and notes are in `photos.csv`.

## Findings

### 1. Small print needs pixels

| Render | Photos | Small print garbled |
|---|---|---|
| 1K | 8 | 8 |
| 2K | 4 | 0 |
| 1K, then a repair pass | 2 | 2 |
| 1K, `gemini-3-pro-image` | 2 | 2 |

Two products with small body text (a lip balm and a face cream tube). In our notes the brand name was usually right and the body copy under it was garbled. The first figure in the README shows one pair. A repair pass and a larger model did not fix it at 1K; 2K did.

### 2. A set of pieces can lose a piece

| Product | Generic prompt | With the product's rules | Same, at 2K |
|---|---|---|---|
| two lip products and a retail card | 2 of 2 photos lost or merged a piece | 0 of 2 | 1 of 2 |
| a glass bottle with a stopper | 0 of 2 | 0 of 2 | not run |

The rules helped at 1K and did not solve it at 2K. Two photos per cell cannot tell those apart.

### 3. Some problems are not prompt problems

- **Fingers over the label.** On one product, a tin held in two hands, fingers covered the label in 6 of 8 photos, including 2 of 2 at 1K with the rule "not covered by fingers" in the prompt. On the other three text products: 0 of 24.
- **Hem length.** In 5 of 8 dress photos at 1K, the hem followed the pose photo instead of the product.

Both are fixed by choosing the pose, not by rewording the prompt.

### 4. Two model reviewers disagreed

We asked two Gemini models to review every photo. They were given the product photo, the pose photo, the generated photo and a zoomed crop of the product, and scored five aspects (product fidelity, pose, identity, artifacts, proportion) from 0 to 2, with veto flags. We turned that into pass, minor or fail with a fixed rule: pass when Verified; fail when product fidelity was 0 or the reviewer flagged a wrong product, a missing part or garbled text; minor otherwise.

| Reviewer | Agrees with our label | Says pass (we say 50%) | Failures caught | False failures |
|---|---|---|---|---|
| gemini-3.5-flash-lite | 60% (kappa 0.38) | 38% | 3 of 3 | 12 |
| gemini-3.5-flash | 38% (kappa 0.0) | 6% | 0 of 3 | 8 |

The two reviewers gave the same verdict on 40% of the photos (kappa 0.12). gemini-3.5-flash scored every aspect 1 in 28 of 52 reviews. The engine and both reviewers were from the same vendor, which may favor it.

### 5. A free text rule found most of it

For the 32 photos of the four products that carry text, we asked a free OCR how many of the words it could read on the real product it could find again in the photo. Flagging a photo when fewer than a quarter were found:

| Photos | Flagged |
|---|---|
| garbled small print (12) | 12 |
| failures by our label (3) | 3 |
| the rest (17) | 2 |

The threshold of 0.25 was chosen after looking at these same photos, and the OCR was the one built into Windows, not Tesseract. This is an in-sample result.

## What changed because of this test

The checklist protocol in `onmodel check` follows from findings 4 and 5: separate fixed questions instead of free scores, "cannot tell" as a legal answer, points computed by code, a text rule that can only tighten a verdict. The [judge protocol](../spec/judge-protocol.md) has the details.

**The new protocol has not been measured.** The reviewers above used the earlier prompt. We do not yet know how well the checklist agrees with human labels; [calibration](calibration.md) says how to find out.

## What this test cannot tell you

- Two photos per cell. Differences of one or two photos are noise.
- One engine family. The same prompts may behave differently on other engines.
- Labels by us, with AI assistance, and no second labeller.
- Nine products, one photo of each. Other products will have other problems.
- Only the swap-the-product task. Adding a chosen model's face to the input was not tested.

## Reproduce

- The table of every photo: [`photos.csv`](../bench/runs/mini-test-v0.1/photos.csv). Columns: file, our label and tags, the verdicts of both reviewers, the OCR recall, the time per photo.
- The numbers: [`summary.json`](../bench/runs/mini-test-v0.1/summary.json), produced by `python scripts/recompute_mini_test.py --write`; `--check` fails if the two disagree. A test runs it.
- The photos of the four products whose product photo is CC0 or public domain: [`images/`](../bench/runs/mini-test-v0.1/images) (19 photos). The photos made from CC BY-SA product photos are not published.
- Review those photos again with a reviewer of your own, then compare with our labels:

```bash
cp -r bench/runs/mini-test-v0.1 bench/runs/my-rejudge
onmodel bench judge --run my-rejudge --judge gemini-3.5-flash-lite --cases K04,J01,A02,A04
onmodel bench calibrate --run my-rejudge --labels bench/runs/mini-test-v0.1/photos.csv
```
