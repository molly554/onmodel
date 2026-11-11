"""HTTPS GET helpers for fetching the golden set.

Talks only to an allow-list of reputable open sources and refuses to follow a redirect to anywhere else.
Everything downloaded is treated as untrusted data: size-capped here, type-checked and re-encoded by the caller.
"""
from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request

UA = "onmodel/0.1 (+https://github.com/molly554/onmodel)"
# Hosts that serve the images in bench/golden/cases.yaml. Add a host only when a case needs it.
FILE_HOSTS = {"images.metmuseum.org", "upload.wikimedia.org", "thumb.wikimedia.org", "images.openbeautyfacts.org", "static.openbeautyfacts.org"}
MAX_BYTES = 15 * 1024 * 1024


class _Guard(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlparse(newurl)
        if u.scheme != "https" or u.hostname not in self.hosts:
            raise urllib.error.URLError(f"redirect outside the allow-list refused: {u.hostname}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, hosts, accept: str):
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or u.hostname not in hosts:
        raise ValueError(f"host is not on the allow-list: {u.hostname}")
    opener = urllib.request.build_opener(_Guard(hosts))
    for attempt in range(5):  # polite retry when a server rate-limits us (429) or is briefly unavailable (503)
        try:
            return opener.open(urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept}), timeout=45)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == 4:
                raise
            wait = e.headers.get("Retry-After")
            time.sleep(min(float(wait), 60) if wait and wait.isdigit() else 4 * (attempt + 1))


def get_image_bytes(url: str, hosts=FILE_HOSTS):
    """Download one image file. Returns (bytes, content_type). Refuses anything that is not image/* or is larger than MAX_BYTES."""
    with _open(url, hosts, "image/*") as r:
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if not ctype.startswith("image/"):
            raise ValueError(f"not an image: {ctype}")
        raw = r.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("file larger than the size cap")
    return raw, ctype
