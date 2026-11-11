#!/usr/bin/env python3
"""Repository gate: licenses and provenance of every image, content rules, secrets and local paths.

    python scripts/check_assets.py              check the repository this script lives in
    python scripts/check_assets.py --root DIR   check another tree (the tests do)

Exit code 0 = clean, 1 = problems (listed one per line). The CI runs this on every push and pull request.

What it enforces
  * every image file is listed in bench/ASSETS.json with a license from an allow-list and a matching sha256
  * bundled benchmark images are CC0 or public domain; linked images (CC BY-SA and the like) are never committed
  * no file or manifest text mentions lingerie, swimwear or adult content
  * no keys, tokens, private keys, local machine paths, personal e-mail addresses or internal project names in any text file
  * no .env files, key files, archives or binaries
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".avif"}
TEXT_EXT = {".md", ".py", ".yaml", ".yml", ".json", ".toml", ".txt", ".cfg", ".ini", ".svg", ".html", ".css", ".js", ".cff", ".sh", ".ps1", ".csv", ""}
BANNED_EXT = {".zip", ".7z", ".rar", ".tar", ".gz", ".exe", ".dll", ".so", ".dylib", ".pyc", ".pdf", ".psd", ".mp4", ".mov"}
SECRET_FILES = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", ".npmrc", ".pypirc")
ALLOWED_LICENSES = {"CC0", "Public domain", "CC BY 4.0"}
BUNDLED_LICENSES = {"CC0", "Public domain"}
MAX_IMAGE_BYTES = 2 * 1024 * 1024
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", "build", "dist"}
# the gate and its own test mention the patterns they look for
SELF = {"scripts/check_assets.py", "tests/test_assets_gate.py"}

# adult-content and lingerie vocabulary: matched on whole words of file names, ids and manifest text
BLOCKLIST = {"lingerie", "bra", "bras", "bralette", "underwear", "panty", "panties", "thong", "swimsuit", "swimwear", "bikini", "nude", "nudes",
             "nsfw", "porn", "erotic", "topless", "corset", "negligee"}
SECRET_PATTERNS = [
    ("a Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{30,}")),
    ("an API key of the sk- form", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("a GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("a hard-coded secret", re.compile(r"""(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['"][A-Za-z0-9_\-]{16,}['"]""")),
    ("a local Windows path", re.compile(r"\b[A-Za-z]:[\\/](Users|Claude|tmp|Windows)[\\/]")),
    ("a local user path", re.compile(r"/Users/[A-Za-z0-9._-]+/")),
]
INTERNAL_STRINGS = ("wearai/wearai", "qa-temp", "prototype/gen", "issue-drafts", "PRD-WB", "fidelity-test", "rocketfly888")
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
EMAIL_DOMAINS_OK = {"users.noreply.github.com", "noreply.github.com", "anthropic.com", "example.com", "example.org"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_files(root: Path) -> list:
    """Tracked files plus untracked files that are not ignored (what a commit would contain), or a plain walk outside a git checkout."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"], capture_output=True, check=True, timeout=60).stdout
        rels = [p for p in out.decode("utf-8", "replace").split("\0") if p]
        return sorted(rel for rel in rels if (root / rel).is_file())
    except (OSError, subprocess.SubprocessError):
        rels = []
        for p in root.rglob("*"):
            if p.is_file() and not (set(p.relative_to(root).parts) & SKIP_DIRS):
                rels.append(p.relative_to(root).as_posix())
        return sorted(rels)


def tokens(text: str) -> set:
    return set(re.split(r"[^a-z0-9]+", text.lower()))


def blocklisted(text: str) -> list:
    return sorted(tokens(text) & BLOCKLIST)


def run(root: Path) -> list:
    root = Path(root).resolve()
    problems = []
    files = list_files(root)
    fileset = set(files)

    # ------------------------------------------------------------------------------------------------ images and the manifest
    manifest_path = root / "bench" / "ASSETS.json"
    listed = {}
    if manifest_path.is_file():
        for a in json.loads(manifest_path.read_text(encoding="utf-8")).get("assets", []):
            listed[a["path"]] = a
    images = [f for f in files if Path(f).suffix.lower() in IMAGE_EXT]
    for f in images:
        a = listed.get(f)
        if a is None:
            problems.append(f"{f}: image is not listed in bench/ASSETS.json")
            continue
        if a.get("license") not in ALLOWED_LICENSES:
            problems.append(f"{f}: license {a.get('license')!r} is not one of {sorted(ALLOWED_LICENSES)}")
        if not a.get("origin"):
            problems.append(f"{f}: no origin recorded")
        if a.get("sha256") != sha256_file(root / f):
            problems.append(f"{f}: sha256 differs from bench/ASSETS.json")
        if (root / f).stat().st_size > MAX_IMAGE_BYTES:
            problems.append(f"{f}: larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MiB")
        hits = blocklisted(f + " " + " ".join(str(v) for v in a.values()))
        if hits:
            problems.append(f"{f}: file name or manifest text mentions {', '.join(hits)}")
    for path in listed:
        if path not in fileset:
            problems.append(f"{path}: listed in bench/ASSETS.json but not in the repository")

    # ------------------------------------------------------------------------------------------------ the cases
    cases_path = root / "bench" / "cases.yaml"
    if cases_path.is_file():
        import yaml

        committed = {sha256_file(root / f) for f in images}
        for c in yaml.safe_load(cases_path.read_text(encoding="utf-8")).get("cases", []):
            cid, s = c["id"], c["source"]
            hits = blocklisted(f"{cid} {c.get('name', '')} {c.get('klass', '')} {c.get('subcategory', '')}")
            if hits:
                problems.append(f"bench/cases.yaml case {cid}: mentions {', '.join(hits)}")
            if s.get("kind") == "bundled":
                rel = "bench/" + s["file"]
                if s.get("license") not in BUNDLED_LICENSES:
                    problems.append(f"bench/cases.yaml case {cid}: a bundled image must be CC0 or public domain (got {s.get('license')!r})")
                if rel not in fileset:
                    problems.append(f"bench/cases.yaml case {cid}: {rel} does not exist")
                elif sha256_file(root / rel) != s.get("sha256"):
                    problems.append(f"bench/cases.yaml case {cid}: sha256 of {rel} differs")
            elif s.get("kind") == "linked":
                for key in ("sha256_source", "sha256_saved"):
                    if s.get(key) and s[key] in committed:
                        problems.append(f"bench/cases.yaml case {cid}: the linked image is committed in the repository (sha256 {key}); linked images must stay out")
                if not str(s.get("url", "")).startswith("https://"):
                    problems.append(f"bench/cases.yaml case {cid}: the url must be https")
            else:
                problems.append(f"bench/cases.yaml case {cid}: source kind must be bundled or linked")

    # ------------------------------------------------------------------------------------------------ files that must not be here
    for f in files:
        name, ext = Path(f).name, Path(f).suffix.lower()
        if any(fnmatch.fnmatch(name, pat) for pat in SECRET_FILES):
            problems.append(f"{f}: a secrets or key file must not be committed")
        if ext in BANNED_EXT:
            problems.append(f"{f}: {ext} files do not belong in this repository")
        if ext not in IMAGE_EXT and blocklisted(f):
            problems.append(f"{f}: file name mentions {', '.join(blocklisted(f))}")

    # ------------------------------------------------------------------------------------------------ text: secrets, local paths, internal names
    for f in files:
        if f in SELF or Path(f).suffix.lower() not in TEXT_EXT or f in images:
            continue
        try:
            text = (root / f).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pat in SECRET_PATTERNS:
            m = pat.search(text)
            if m:
                problems.append(f"{f}: looks like {label} ({text.count(chr(10), 0, m.start()) + 1}:{m.start() - text.rfind(chr(10), 0, m.start())})")
        for s in INTERNAL_STRINGS:
            if s in text:
                problems.append(f"{f}: mentions an internal name ({s})")
        for m in EMAIL.finditer(text):
            if m.group(1).lower() not in EMAIL_DOMAINS_OK:
                problems.append(f"{f}: contains an e-mail address ({m.group(0)})")
                break
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    a = ap.parse_args(argv)
    problems = run(Path(a.root))
    for p in problems:
        print("PROBLEM " + p)
    print(f"{len(problems)} problem(s)" if problems else "clean: licenses, provenance, content and secrets all check out")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
