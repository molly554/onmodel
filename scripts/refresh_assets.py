#!/usr/bin/env python3
"""Recompute the sha256 of every image listed in bench/ASSETS.json (run it after you rebuild the figures).

    python scripts/refresh_assets.py

It only updates hashes of files that are already listed. A new image has to be added to the manifest by hand, with its license and origin;
scripts/check_assets.py refuses an image that is not listed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "bench" / "ASSETS.json"


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    changed = 0
    for a in data["assets"]:
        p = ROOT / a["path"]
        if not p.is_file():
            print(f"missing: {a['path']}")
            continue
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if digest != a["sha256"]:
            a["sha256"] = digest
            changed += 1
            print(f"updated: {a['path']}")
    MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{changed} hash(es) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
