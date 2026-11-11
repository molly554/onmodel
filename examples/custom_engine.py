"""A complete image engine in about twenty lines.

It makes no API call: it returns the pose photo with the product photo pasted into a corner, so you can see the plumbing work end to end.
To make it real, replace the body of generate() with a call to your own engine.

Run it from the root of the repository:

    onmodel bench run --engine examples.custom_engine:PasteEngine --cases K04,J01 --variants v1 --samples 1 --out paste-demo --yes
    onmodel bench judge --run paste-demo --judge mock --cases K04,J01
    onmodel bench report --run paste-demo

See docs/bring-your-engine.md.
"""
import io

from PIL import Image

from onmodel.engines import Generation


class PasteEngine:
    id = "paste-demo"                 # recorded in every ledger line and in the report
    max_reference_images = 2          # the benchmark sends two: the product photo, then the pose photo

    def estimate_cost(self, res, n=1):
        return 0.0, 0.0               # (low, high) in USD per n photos. Raise KeyError when you do not know: the dry run then says "unknown"

    def generate(self, prompt, refs, *, res="1k", ratio="3:4"):
        # refs is a list of (jpeg_bytes, mime_type), in the order of the prompt: [product photo, pose photo]
        (product, _), (pose, _) = refs
        photo = Image.open(io.BytesIO(pose)).convert("RGB")
        thumb = Image.open(io.BytesIO(product)).convert("RGB")
        thumb.thumbnail((photo.width // 3, photo.height // 3))
        photo.paste(thumb, (12, 12))
        out = io.BytesIO()
        photo.save(out, "JPEG", quality=90)
        return Generation(ok=True, image=out.getvalue(), mime="image/jpeg", cost_lo=0.0, cost_hi=0.0, seconds=0.0, stamp={"engine": self.id})
