"""Image engines: what turns (product photo, pose photo, prompt) into an on-model photo.

An engine is any object with an `id`, a `max_reference_images`, `estimate_cost()` and `generate()`.
`load_engine("package.module:Class")` lets you plug in your own; see docs/bring-your-engine.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from . import gemini
from .plugins import load_class


@dataclass
class Generation:
    ok: bool
    image: bytes | None = None
    mime: str | None = None
    usage: dict = field(default_factory=dict)
    cost_lo: float | None = None
    cost_hi: float | None = None
    seconds: float = 0.0
    error: str = ""
    stamp: dict = field(default_factory=dict)   # what you need to reproduce or compare a run: engine id, API, anything the vendor reports


class Engine(Protocol):
    id: str
    max_reference_images: int

    def estimate_cost(self, res: str, n: int = 1) -> tuple:  # (low, high) in USD; raises KeyError when unknown
        ...

    def generate(self, prompt: str, refs: list, *, res: str = "1k", ratio: str = "3:4") -> Generation:  # refs: [(bytes, mime), ...] in prompt order
        ...


class GeminiEngine:
    """Google's Gemini image models through the Interactions API (the code our mini test ran live).

    The estimates are what we observed in the mini test (per photo, 3:4): about $0.037-0.041 and 22 s at 1K and $0.056-0.061 and 42 s at 2K for
    gemini-nano-banana-2.1; about $0.14 at 1K for gemini-3-pro-image. Prices change: check the vendor's page.
    """

    OBSERVED = {
        "gemini-nano-banana-2.1": {"1k": (0.037, 0.041), "2k": (0.056, 0.061)},
        "gemini-3-pro-image": {"1k": (0.13, 0.14)},
    }
    max_reference_images = 2   # the benchmark sends two references (product, pose); the API accepts more, check the vendor's page

    def __init__(self, model: str = "gemini-nano-banana-2.1", api_key: str | None = None):
        self.id = model
        self.key = api_key or gemini.get_key()   # may be missing: a dry run does not need it, check_ready() insists

    def check_ready(self) -> None:
        if not self.key:
            raise RuntimeError("GEMINI_API_KEY is not set. Export it in your shell; onmodel never writes it anywhere.")

    def estimate_cost(self, res: str, n: int = 1) -> tuple:
        lo, hi = self.OBSERVED[self.id][res.lower()]
        return lo * n, hi * n

    def generate(self, prompt: str, refs: list, *, res: str = "1k", ratio: str = "3:4") -> Generation:
        self.check_ready()
        r = gemini.generate_image(self.key, self.id, prompt, refs, ratio=ratio, size=res.upper())
        return Generation(ok=r["ok"], image=r["image"], mime=r["mime"], usage=r["usage"], cost_lo=r["cost_lo"], cost_hi=r["cost_hi"],
                          seconds=r["seconds"], error=r["error"], stamp={"engine": self.id, "api": "gemini-interactions"})


class MockEngine:
    """Returns the last reference image (the pose photo) as the 'generated' photo. Free, instant, deterministic: for tests and `onmodel bench smoke`."""

    id = "mock"
    max_reference_images = 8

    def estimate_cost(self, res: str, n: int = 1) -> tuple:
        return 0.0, 0.0

    def generate(self, prompt: str, refs: list, *, res: str = "1k", ratio: str = "3:4") -> Generation:
        data, mime = refs[-1]
        return Generation(ok=True, image=data, mime=mime, cost_lo=0.0, cost_hi=0.0, seconds=0.0, stamp={"engine": "mock"})


def load_engine(spec: str) -> Engine:
    """'mock', a Gemini model name ('gemini-nano-banana-2.1'), or 'package.module:ClassName' (a class with a no-argument constructor)."""
    if spec == "mock":
        return MockEngine()
    if spec.startswith("gemini-"):
        return GeminiEngine(spec)
    if ":" in spec:
        return load_class(spec)()
    raise ValueError(f"unknown engine: {spec!r} (use 'mock', a gemini image model name, or 'package.module:Class')")
