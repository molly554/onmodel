# Judge protocol

How one result photo is reviewed. The reference implementation is `onmodel/judge.py` and `onmodel/check.py`; the record it produces is described by [schemas/judgment.schema.json](../schemas/judgment.schema.json).

## Inputs

| Image | What it is |
|---|---|
| A | the real product photo: the ground truth for the product. It may show a hand, a mannequin or props; those are not part of the product |
| B | the photo to review |
| C | a zoomed crop of the product in B, so printed text and fine detail can be read |
| D | optional: the pose reference the generator was asked to follow |

Plus two hints: whether the person is wearing or holding the product, and the product's risk tags.

## Steps

1. **Locate and crop.** A cheap vision call returns a bounding box of the product in B (`box_2d`, 0 to 1000). The crop adds a 12 percent margin and is enlarged to about 1000 px on its long edge. If the box is missing or invalid, the whole frame is used.
2. **Ask nine fixed questions** ([rubric](rubric.md)). The reviewer answers each with `same`, `minor`, `different`, `cannot_tell` or `not_applicable`, and adds evidence and a place for every answer other than `same`. It never gives a score.
3. **List defects** with codes from the [failure taxonomy](failure-taxonomy.md). A code outside the list is rejected.
4. **Transcribe the printed text** of the product in A and in B, exactly as printed. The prompt forbids correcting spelling and filling in what the text should say.
5. **Validate.** The answer must be JSON that matches the schema: all nine items present, every answer and every defect code in its list. An invalid answer is asked for again (two attempts); after that the record says `ok: false` with the error. A failed review is never turned into a score.
6. **Text rule** ([hard rules](hard-rules.md)). It can change a `same`, `minor` or `not_applicable` answer to `different`. It never changes anything in the other direction.
7. **Score in code.** Points, veto and the Verified verdict come from `onmodel/scoring.py`. No model is involved in this step.
8. **Record.** The record holds the checklist, the text rule result, the scorecard, the fixes, the hashes of the input files, the name of the reviewer, a hash of the prompt, the rubric version and the package version.

## Why it is built this way

- **Separate questions, not one score.** In our mini test, with a free 0 to 2 scoring prompt, one of the two model reviewers (gemini-3.5-flash) scored every aspect 1 in 28 of 52 reviews, and the two reviewers gave the same verdict on 40 percent of the photos. Separate questions with a fixed vocabulary are easier to answer the same way twice, and easier to audit.
- **Code computes the points,** so "what does a 1 mean" cannot drift between reviewers or between versions.
- **"Cannot tell" is a legal answer.** It is never counted as `same`.
- **A pinned prompt.** The prompt is built from `taxonomy.py`; its hash is in the record. The default reviewer runs at temperature 0.

Whether this protocol agrees with human labels has not been measured yet. See [calibration](../docs/calibration.md).

## Not in 0.1

Planned, not implemented: a two-step cascade (a cheap reviewer first, a stronger one for doubtful photos or vetoes), a color rule, a scale rule for jewelry with a reference object, and a requirement that the reviewer and the image engine come from different vendors. In the mini test the engine and both reviewers were from one vendor, which may favor it.

## Your own reviewer

Any object with a `name` and an `ask_json(prompt, images, schema)` method works: `--judge package.module:ClassName`. It receives the prompt, the images as `(bytes, mime)` pairs and a JSON schema, and returns a `VlmResult`. `onmodel.judge.MockVlm` is the smallest example.
