#!/usr/bin/env python3
"""Check the links and images in the Markdown files.

    python scripts/check_links.py               local links only: files and #anchors must exist (no network; used by the CI)
    python scripts/check_links.py --external    also request every http(s) link once (run it by hand before a release)

Exit code 0 = all good, 1 = broken links (listed).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_SRC = re.compile(r"""<(?:img|a|source)\b[^>]*?\b(?:src|href)=["']([^"']+)["']""", re.I)
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$", re.M)
FENCE = re.compile(r"^```.*?^```", re.M | re.S)
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "build", "dist", ".pytest_cache"}


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation removed, spaces to hyphens."""
    s = re.sub(r"`|\*|_", "", heading.strip().lower())
    s = re.sub(r"[^\w\- ]", "", s, flags=re.UNICODE)
    return s.replace(" ", "-")


def anchors(text: str) -> set:
    seen, out = {}, set()
    for _lvl, h in HEADING.findall(FENCE.sub("", text)):
        s = slug(h)
        n = seen.get(s, 0)
        seen[s] = n + 1
        out.add(s if n == 0 else f"{s}-{n}")
    return out


def md_files(root: Path) -> list:
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"], capture_output=True, check=True, timeout=60).stdout
        return sorted(root / p for p in out.decode("utf-8", "replace").split("\0") if p.endswith(".md") and (root / p).is_file())
    except (OSError, subprocess.SubprocessError):
        return sorted(p for p in root.rglob("*.md") if not (set(p.relative_to(root).parts) & SKIP_DIRS))


def check_external(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": "onmodel-link-check/0.1 (+https://github.com/molly554/onmodel)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return None if r.status < 400 else f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return None if e.code in (401, 403, 429) else f"HTTP {e.code}"   # some sites refuse automated clients; that is not a broken link
    except Exception as e:   # DNS, TLS, timeout
        return f"{type(e).__name__}: {e}"


def run(root: Path, external: bool = False) -> list:
    root = Path(root).resolve()
    problems, cache, ext_seen = [], {}, {}
    for md in md_files(root):
        rel = md.relative_to(root).as_posix()
        text = md.read_text(encoding="utf-8")
        body = FENCE.sub("", text)
        targets = LINK.findall(body) + HTML_SRC.findall(body)
        for t in targets:
            if t.startswith("mailto:"):
                continue
            if re.match(r"https?://", t):
                if external and t not in ext_seen:
                    ext_seen[t] = check_external(t)
                    if ext_seen[t]:
                        problems.append(f"{rel}: {t} -> {ext_seen[t]}")
                continue
            path, _, frag = urllib.parse.unquote(t).partition("#")
            if not path:
                target_file = md
            else:
                target_file = (root / path.lstrip("/")) if path.startswith("/") else (md.parent / path)
                target_file = target_file.resolve()
                if not target_file.exists():
                    problems.append(f"{rel}: {t} -> file not found")
                    continue
            if frag and target_file.suffix.lower() == ".md":
                if target_file not in cache:
                    cache[target_file] = anchors(target_file.read_text(encoding="utf-8"))
                if frag.lower() not in cache[target_file]:
                    problems.append(f"{rel}: {t} -> no such heading")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--external", action="store_true")
    a = ap.parse_args(argv)
    problems = run(Path(a.root), a.external)
    for p in problems:
        print("BROKEN " + p)
    print(f"{len(problems)} broken link(s)" if problems else "all links resolve")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
