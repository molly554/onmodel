# Hard rules

Rules that do not depend on a model's judgment. A rule can only make a verdict stricter. It never turns a `different` into a `same`.

## The text rule

**Question.** Do the words printed on the real product show up in the result?

**Words.** Text is lower-cased, accents are removed, and a word is three or more letters, or a number of two or more digits. Repeats are dropped. Shorter words are ignored because they are the first thing an OCR gets wrong.

**Recall.** `recall = (expected words found in the result) / (expected words)`.

**Flag.** The photo is flagged when `recall < 0.25`. A flagged photo gets its `text` answer changed from `same`, `minor` or `not_applicable` to `different`, and a `TEXT_GARBLE` defect is added if the reviewer did not already list a text defect. A `cannot_tell` is left alone: the rule has the same pixels to go on. A product with no readable words is not checked.

**Where the words come from.**

| | Expected words (the real product) | Observed words (the result) |
|---|---|---|
| `--ocr tesseract` | the words you pass with `--expect-text`, or OCR of the product photo | OCR of the zoomed crop of the product in the result, tried at 0, 90 and 270 degrees; the best recall wins |
| default | the words you pass with `--expect-text`, or the reviewer's transcription of the product photo | the reviewer's transcription of the result |

OCR is preferred. A model that transcribes a result may read what it expects to see instead of what is printed, and then the rule sees nothing wrong. A person who knows the words (`--expect-text`, or `text_gt` in a benchmark case) is the best source of expected words.

## What we measured

On the 32 photos of the four products that carry text in the mini test, with Windows' built-in OCR:

| Photos | Flagged |
|---|---|
| garbled small print (12) | 12 |
| failures by our label (3) | 3 |
| the rest (17) | 2 |

Two caveats. The threshold of 0.25 was picked after looking at these same photos, so this is an in-sample result. And the OCR was Windows' own, not Tesseract, which is the backend that ships; its numbers are not measured yet. Artistic logos, curved or very small text, and scripts the OCR does not read are weak spots.

## Planned, not in 0.1

A color rule (histogram distance between the product and the product region of the result) and a scale rule for jewelry shot next to a reference object. Neither is implemented.
