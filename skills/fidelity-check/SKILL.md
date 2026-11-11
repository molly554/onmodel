---
name: fidelity-check
description: Check whether an AI-generated on-model product photo (a person wearing or holding a product) still shows the real product. Use when the user gives a real product photo and a generated result photo and asks whether it is faithful, ready to publish, or what went wrong. Produces a scorecard with a Verified verdict and short fixes.
---

# Fidelity check

Compare a generated photo of a person wearing or holding a product with the real product photo, answer nine fixed questions, and let a script turn the answers into a scorecard. You judge what you see; the script does the arithmetic.

## What you need

- IMAGE A: the real product photo. It is the ground truth for the product.
- IMAGE B: the generated photo to review.
- Optional, IMAGE C: the pose reference the generator was given. With it you can answer the pose question; without it, answer `not_applicable`.

If you were given only one image, ask for the other. Do not review a photo against your memory of what the product should look like.

## Steps

1. Look at both images. If you can crop and enlarge, zoom in on the product in B, especially any printed text.
2. Answer the nine questions in `references/rubric.md` with one of `same`, `minor`, `different`, `cannot_tell`, `not_applicable`. For every answer other than `same`, add `evidence` (what you see, in a few words) and `where`.
3. List every problem as a defect with a code from the rubric (`TEXT_GARBLE`, `PART_MISSING`, ...). Use only those codes.
4. Transcribe the text that is legible on the product in A (`text_in_reference`) and in B (`text_in_generated`). Copy what is printed. Do not correct spelling and do not fill in what the text should say.
5. If the product carries text, run the text rule as a cross-check:
   `python scripts/text_match.py --expected "<text in A>" --observed "<text in B>"`
   If it exits with 1 (flagged), set the `text` answer to `different` and add `TEXT_GARBLE`.
6. Write the checklist as JSON (see `references/checklist-example.json`) to a temporary file and run:
   `python scripts/score.py <file>`
7. Reply with the scorecard exactly as the script printed it, then one or two sentences on what to change. Never compute points yourself and never say "Verified" unless the script did.

## Rules for the review

- Be literal. A different shade, a missing cap, one wrong letter, a sixth finger: each is a finding.
- Compare with A, not with what would look plausible. A photo can look good and still show another product.
- When you cannot see enough to decide, answer `cannot_tell`. It scores 1, never 2, so a product-fidelity question you could not answer blocks Verified: the photo cannot be Verified on a guess.
- Hands, mannequins and props that appear in A are not part of the product. If they show up in B, that is `LEAK_HAND_MANNEQUIN`.
- Printed text is checked character by character. Small print that is gibberish is `TEXT_GARBLE`; a wrong large word or logo is `TEXT_WRONG`.
- One review judges one photo. For several photos, review each and report them side by side.

## Limits

A model reviewer is not a person. In our mini test two model reviewers agreed with each other on only 39% of the photos, which is why the questions are fixed, the points are computed by code, and the text rule exists. Treat the scorecard as a fast first screen, and look at the photo yourself before you publish it.

Rubric version 1.0-draft. Source and the full benchmark: https://github.com/molly554/onmodel
