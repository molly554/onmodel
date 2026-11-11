# What Verified means

A photo is **Verified** when all three of these hold:

1. product fidelity is 2 / 2, which means shape, color, material, text and parts are all `same`;
2. the total is at least 8 / 10;
3. no veto defect was found.

When a photo is not Verified, the scorecard says why.

## Why it is about the product

Product fidelity is the lowest of its five items, so one difference in any of them, even a `minor` one, keeps the photo from being Verified. The other four dimensions (pose, identity, artifacts, scale) only count towards the total. One of them can be `different` (a total of 8) and the photo can still be Verified; two cannot (6).

The reason is the use case. A seller needs the photo to show the product they sell. A pose that drifted from the reference is a smaller problem than a label that says the wrong thing.

## Examples

These rows are computed by the scorer. A test recomputes them, so this table cannot drift from the code.

| The reviewer's answers | Total | Verified | Why |
|---|---|---|---|
| everything `same` | 10 | yes | |
| `text` is `minor` | 9 | no | product fidelity is 1 |
| `shape` is `different` | 8 | no | product fidelity is 0 |
| `pose` is `different` | 8 | yes | one other dimension at 0 is allowed |
| `pose` and `identity` are `different` | 6 | no | total below 8 |
| everything `same`, defect `PART_MISSING` | 10 | no | veto defect |
| `color` is `cannot_tell` | 9 | no | product fidelity is 1; a guess is not enough |
| `scale` is `cannot_tell` | 9 | yes | reported as "could not tell", costs one point |

## What Verified is not

- It is not a guarantee. A reviewer can be wrong, and the model reviewers we measured often were (see [the mini test](../docs/mini-test.md)).
- It is not a human review. Look at the photo yourself before you publish it.
- It is not comparable across rubric versions. Every record carries `rubric_version`.
- It says nothing about whether the photo is attractive, permitted on a marketplace, or safe to use in any other way.

## Starting values

The minimum total of 8, the point values and the list of veto codes are starting values. They have not been calibrated against human labels. The gates we propose before anyone publishes numbers from a reviewer are in [calibration](../docs/calibration.md).
