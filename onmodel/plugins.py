"""Load a class given as 'package.module:ClassName': your own engine or reviewer that lives outside this package."""
from __future__ import annotations

import importlib
import os
import sys


def load_class(spec: str):
    mod, _, cls = spec.partition(":")
    if not mod or not cls:
        raise ValueError(f"expected 'package.module:ClassName', got {spec!r}")
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)   # like `python -m` and pytest: a file next to you can be imported
    try:
        module = importlib.import_module(mod)
    except ImportError as e:
        raise ValueError(f"cannot import {mod!r}: {e}") from e
    try:
        return getattr(module, cls)
    except AttributeError:
        raise ValueError(f"module {mod!r} has no class {cls!r}") from None
