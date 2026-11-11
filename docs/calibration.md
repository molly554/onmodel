# Calibrating a reviewer

A model reviewer can be wrong, and the ones we measured often were (see [the mini test](mini-test.md)). Before you trust one, or publish numbers that depend on it, compare it with labels made by people. This page says how, and which gates we propose.

## 1. Label some photos yourself

Take photos from a run (`bench/runs/<name>/images/`). Look at each one next to its product photo and give it one of three labels:

| Label | Meaning |
|---|---|
| `pass` | you would publish it |
| `minor` | a visible difference that does not change what the product looks like |
| `fail` | the product is wrong: a wrong or garbled word, a missing or merged part, a wrong color family, a different product |

Write a CSV with the columns `file` and `label`. Other columns are ignored.

```
file,label
K04_v1_1k_s1.jpg,minor
K04_v1_2k_s1.jpg,pass
J01_v0_1k_s2.jpg,pass
```

For anything you plan to publish, use at least 150 photos and two people who label separately. Compare their labels with each other first: if two people do not agree, a model cannot be asked to.

## 2. Review the same photos

```bash
onmodel bench judge --run my-run --judge gemini-3.5-flash-lite
```

## 3. Compare

```bash
onmodel bench calibrate --run my-run --labels my-labels.csv
```

The reviewer's scorecard is turned into the same three levels: `pass` when Verified, `fail` when product fidelity is 0 or a veto defect was found, `minor` otherwise. The command prints the measures below and writes `calibration.json` into the run folder.

| Measure | What it tells you | Proposed gate |
|---|---|---|
| agreement, 3 levels | how often the reviewer and you give the same level | 75% or more |
| kappa, 3 levels | the same, corrected for chance | 0.6 or more |
| failures caught | of the photos you labelled `fail`, how many the reviewer called `fail` | 90% or more |
| failures that were real | of the photos the reviewer called `fail`, how many you did too | 60% or more |
| agreement, pass or not | whether the reviewer's `pass` matches yours | 85% or more |
| photos | how many photos the comparison rests on | 150 or more |

## The gates are proposals

We picked the gates before looking at any data for the new protocol. They are a reasonable bar for a reviewer you publish numbers from, not thresholds we have measured. Change them if you have a reason, and say so.

For comparison, the two reviewers of the mini test, which used an earlier prompt, measured on our own labels:

| Reviewer | Agreement | Kappa | Failures caught | Failures that were real |
|---|---|---|---|---|
| gemini-3.5-flash-lite | 60% | 0.38 | 3 of 3 | 3 of 15 |
| gemini-3.5-flash | 38% | 0.0 | 0 of 3 | 0 of 8 |

Neither would have passed the gates. The checklist protocol in `onmodel check` has not been measured this way yet. When it has, the result will be added to this page.

## Pitfalls

- Do not label a photo after reading the reviewer's answer. Hide it.
- Do not tune the reviewer's prompt on the photos you calibrate with. Keep a second set for the final measurement.
- The same vendor for the engine and the reviewer can favor itself. Where you can, use different ones.
- A calibration is only valid for one reviewer, one rubric version and one kind of product. Calibrate again when any of them changes.
