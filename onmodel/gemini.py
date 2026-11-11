"""Thin, dependency-free wrapper around the Gemini REST API.

  generate_image(...)  one image-generation / image-edit call with reference images  (Interactions API)
  ask_json(...)        one vision call that must answer in JSON matching a schema     (generateContent)

This is the code our internal mini test ran against the live API, with the internal key handling removed:
the API key is read from the GEMINI_API_KEY environment variable and is never printed or logged.
Costs are ESTIMATES computed from the token usage the API returns; check the vendor's price page before you budget.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request

BASE = "https://generativelanguage.googleapis.com/v1beta"

# $ per 1M tokens (low / high estimate for the non-image tokens). Image output is billed per image token.
COST = {
    "gemini-nano-banana-2.1": {"image": 30.0, "text": (3.75, 7.50)},   # a 1K image is 1120 tokens, about $0.034
    "gemini-3-pro-image":     {"image": 120.0, "text": (12.0, 12.0)},  # a 1K image is 1120 tokens, about $0.134
}


def get_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or None


def http(method: str, url: str, key: str, body=None, timeout: int = 300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {"error": {"message": str(e)}}
    except Exception as e:  # network-level failure
        return 0, {"error": {"message": f"{type(e).__name__}: {e}"}}


def err_msg(resp) -> str:
    e = resp.get("error") if isinstance(resp, dict) else None
    return (e.get("message") if isinstance(e, dict) else str(resp))[:300]


def find_images(obj, out: list) -> None:
    """Collect image blocks from a response, skipping intermediate 'thought' images."""
    if isinstance(obj, dict):
        if obj.get("thought") is True or obj.get("type") == "thought":
            return
        d, mime = obj.get("data"), obj.get("mime_type") or obj.get("mimeType")
        if isinstance(d, str) and isinstance(mime, str) and mime.startswith("image/"):
            out.append((mime, d))
        for v in obj.values():
            find_images(v, out)
    elif isinstance(obj, list):
        for v in obj:
            find_images(v, out)


def find_text(obj, out: list) -> None:
    if isinstance(obj, dict):
        t = obj.get("text")
        if isinstance(t, str) and obj.get("thought") is not True and obj.get("type") != "thought":
            out.append(t)
        for v in obj.values():
            find_text(v, out)
    elif isinstance(obj, list):
        for v in obj:
            find_text(v, out)


def image_cost(model: str, usage: dict):
    """(low, high) USD estimate for one image call from the usage block, or (None, None) when the model is not priced here."""
    c = COST.get(model)
    if not c or not usage:
        return None, None
    img = sum(m.get("tokens", 0) for m in usage.get("output_tokens_by_modality", []) if m.get("modality") == "image")
    other = max(usage.get("total_output_tokens", 0) - img, 0) + usage.get("total_thought_tokens", 0)
    return img * c["image"] / 1e6 + other * c["text"][0] / 1e6, img * c["image"] / 1e6 + other * c["text"][1] / 1e6


def generate_image(key: str, model: str, prompt: str, refs, ratio: str = "3:4", size: str = "1K", thinking=None, retries: int = 3) -> dict:
    """refs: list of (bytes, mime). The images are numbered in the prompt as [Image 1], [Image 2], ... in this order.
    Returns dict(ok, image, mime, usage, text, error, status, seconds, cost_lo, cost_hi)."""
    inp = [{"type": "text", "text": prompt}]
    for i, (data, mime) in enumerate(refs, 1):
        inp += [{"type": "text", "text": f"[Image {i}]"}, {"type": "image", "mime_type": mime, "data": base64.b64encode(data).decode()}]
    body = {"model": model, "input": inp, "response_format": {"type": "image", "aspect_ratio": ratio, "image_size": size}}
    if thinking:
        body["generation_config"] = {"thinking_level": thinking}
    t0, st, r = time.time(), 0, {}
    for attempt in range(retries):
        st, r = http("POST", f"{BASE}/interactions", key, body)
        if st in (0, 429, 500, 503) and attempt < retries - 1:
            time.sleep(6 * (attempt + 1))
            continue
        break
    out = dict(ok=False, image=None, mime=None, usage={}, text="", error="", status=st, seconds=round(time.time() - t0, 1), cost_lo=None, cost_hi=None)
    if st != 200:
        out["error"] = err_msg(r)
        return out
    out["usage"] = r.get("usage", {}) if isinstance(r, dict) else {}
    out["cost_lo"], out["cost_hi"] = image_cost(model, out["usage"])
    found, texts = [], []
    find_images(r, found)
    find_text(r, texts)
    out["text"] = " | ".join(texts)[:500]
    if not found:
        out["error"] = "no image returned"
        return out
    out["mime"], b64 = found[-1]
    out["image"] = base64.b64decode(b64)
    out["ok"] = True
    return out


def ask_json(key: str, model: str, prompt: str, images, schema: dict, retries: int = 3) -> dict:
    """One vision call that must return JSON. images: list of (bytes, mime). Returns dict(ok, data, usage, seconds, error, raw)."""
    parts = [{"text": prompt}]
    for data, mime in images:
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}})
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": schema}}
    t0, st, r = time.time(), 0, {}
    for attempt in range(retries):
        st, r = http("POST", f"{BASE}/models/{model}:generateContent", key, body)
        if st in (0, 429, 500, 503) and attempt < retries - 1:
            time.sleep(5 * (attempt + 1))
            continue
        break
    out = dict(ok=False, data=None, usage={}, seconds=round(time.time() - t0, 1), error="", raw="")
    if st != 200:
        out["error"] = f"HTTP {st}: {err_msg(r)}"
        return out
    out["usage"] = r.get("usageMetadata", {})
    try:
        txt = "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"] if not p.get("thought"))
        out["raw"] = txt[:4000]
        out["data"] = json.loads(txt)
        out["ok"] = True
    except Exception as e:
        out["error"] = f"could not parse the judge answer: {type(e).__name__}: {e}"
    return out
