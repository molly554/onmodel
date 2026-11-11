# Bring your own engine

The benchmark does not care which image engine makes the photos. An engine is any Python class with four things: an `id`, `max_reference_images`, `estimate_cost()` and `generate()`. [`examples/custom_engine.py`](../examples/custom_engine.py) is a complete one in about twenty lines.

```python
import io
from PIL import Image
from onmodel.engines import Generation


class PasteEngine:
    id = "paste-demo"                 # recorded in every ledger line and in the report
    max_reference_images = 2          # the benchmark sends two: the product photo, then the pose photo

    def estimate_cost(self, res, n=1):
        return 0.0, 0.0               # (low, high) in USD per n photos; raise KeyError if you do not know

    def generate(self, prompt, refs, *, res="1k", ratio="3:4"):
        # refs: [(jpeg_bytes, mime_type), ...] in the order the prompt names them: product photo, pose photo
        (product, _), (pose, _) = refs
        ...                           # call your engine here
        return Generation(ok=True, image=png_or_jpeg_bytes, mime="image/png", cost_lo=0.04, cost_hi=0.05,
                          seconds=12.3, stamp={"engine": self.id, "version": "2026-11"})
```

Run it:

```bash
onmodel bench run --engine examples.custom_engine:PasteEngine --cases K04,J01 --variants v1 --samples 1 --out paste-demo --yes
```

The class must have a constructor that takes no arguments. The module is found from the current folder, so you can keep your engine next to the data.

## What the benchmark expects

| | |
|---|---|
| `generate(prompt, refs, res, ratio)` | `prompt` is the text built from the [starter recipe](../skills/shoot-brief/references/recipes.md) for the case. `refs` are JPEG bytes, product photo first, pose photo second. For a `repair` pass the second image is the first result. `res` is `"1k"` or `"2k"`, `ratio` is `"3:4"`. |
| return value | a `Generation`. On a failure return `Generation(ok=False, error="...")` or raise: the call is recorded as failed and the run goes on. |
| `stamp` | whatever you need to reproduce or compare a run: model version, date, API name. It is written to `ledger.jsonl` next to the prompt hash and the cost. |
| `estimate_cost(res, n)` | used for the dry run and for `--budget`. If you cannot estimate, raise `KeyError`: the dry run says "unknown" and `--budget` refuses to start, because it could not be enforced. |
| `check_ready()` (optional) | called once before a real run. Raise `RuntimeError` with a clear message if, for example, a key is missing. |

Resolutions other than 1K and 2K, more than two reference images, and seeds are not part of the benchmark yet.

## Your own reviewer

The same works for the reviewer: `--judge package.module:ClassName`. A reviewer has a `name` and `ask_json(prompt, images, schema)`, where `images` is a list of `(bytes, mime)` and `schema` is a Gemini-style JSON schema. It returns an `onmodel.judge.VlmResult`. See [`MockVlm`](../onmodel/judge.py) for the smallest example, and the [judge protocol](../spec/judge-protocol.md) for what it is asked.

## Keep it honest

- Do not use the same vendor for the engine and the reviewer without saying so. It may favor itself.
- Record the engine version in `stamp`. Results are only comparable for one engine version, one recipe version and one rubric version.
- Run `onmodel bench run` without `--yes` first. It prints the plan and the estimated cost.
