"""The Gemini adapter, with the network replaced. The usage block below is a real one from our mini test (K01_v0_nano21_s1)."""
import base64
import json

import pytest

from onmodel import gemini
from onmodel.engines import GeminiEngine, load_engine
from onmodel.judge import BOX_SCHEMA, CHECKLIST_SCHEMA, GeminiVlm

from conftest import make_checklist

REAL_USAGE = {"total_tokens": 3951, "total_input_tokens": 2380,
              "input_tokens_by_modality": [{"modality": "image", "tokens": 2240}, {"modality": "text", "tokens": 140}],
              "total_cached_tokens": 0, "total_output_tokens": 1468, "output_tokens_by_modality": [{"modality": "image", "tokens": 1120}],
              "total_tool_use_tokens": 0, "total_thought_tokens": 103, "initial_input_tokens": 2380}
PNG = base64.b64encode(b"\x89PNG-fake-bytes").decode()


class FakeHttp:
    """Replaces gemini.http: returns the queued (status, body) pairs in order and records the requests."""

    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, method, url, key, body=None, timeout=300):
        self.requests.append({"method": method, "url": url, "key": key, "body": body})
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)


def test_the_cost_estimate_is_the_one_our_ledger_recorded():
    lo, hi = gemini.image_cost("gemini-nano-banana-2.1", REAL_USAGE)
    assert lo == pytest.approx(0.035291249999999996) and hi == pytest.approx(0.0369825)         # the cost_lo and cost_hi of that ledger line
    assert gemini.image_cost("some-other-model", REAL_USAGE) == (None, None) and gemini.image_cost("gemini-nano-banana-2.1", {}) == (None, None)


def test_generate_image_builds_the_interactions_request_and_returns_the_last_real_image(monkeypatch):
    thought = {"type": "thought", "data": PNG, "mime_type": "image/png"}                          # an intermediate image is skipped
    final = {"type": "image", "data": base64.b64encode(b"final-image").decode(), "mime_type": "image/png"}
    fake = FakeHttp((200, {"outputs": [thought, {"type": "text", "text": "done"}, final], "usage": REAL_USAGE}))
    monkeypatch.setattr(gemini, "http", fake)
    out = gemini.generate_image("KEY", "gemini-nano-banana-2.1", "make it", [(b"product", "image/jpeg"), (b"pose", "image/jpeg")], ratio="3:4", size="2K")
    assert out["ok"] and out["image"] == b"final-image" and out["mime"] == "image/png" and out["text"] == "done" and out["cost_hi"] == pytest.approx(0.0369825)
    req = fake.requests[0]
    assert req["method"] == "POST" and req["url"] == gemini.BASE + "/interactions" and req["key"] == "KEY"
    body = req["body"]
    assert body["model"] == "gemini-nano-banana-2.1" and body["response_format"] == {"type": "image", "aspect_ratio": "3:4", "image_size": "2K"}
    kinds = [(i["type"], i.get("text", "")[:9]) for i in body["input"]]
    assert kinds == [("text", "make it"), ("text", "[Image 1]"), ("image", ""), ("text", "[Image 2]"), ("image", "")]
    assert base64.b64decode(body["input"][2]["data"]) == b"product" and body["input"][4]["mime_type"] == "image/jpeg"


def test_generate_image_failures_are_reported_not_raised(monkeypatch):
    monkeypatch.setattr(gemini, "http", FakeHttp((400, {"error": {"message": "bad request"}})))
    out = gemini.generate_image("K", "gemini-nano-banana-2.1", "p", [])
    assert not out["ok"] and out["error"] == "bad request" and out["status"] == 400
    monkeypatch.setattr(gemini, "http", FakeHttp((200, {"outputs": [{"type": "text", "text": "I cannot do that"}], "usage": {}})))
    out = gemini.generate_image("K", "gemini-nano-banana-2.1", "p", [])
    assert not out["ok"] and out["error"] == "no image returned" and out["text"] == "I cannot do that"


def test_transient_errors_are_retried_then_given_up(monkeypatch):
    ok = (200, {"outputs": [{"type": "image", "data": PNG, "mime_type": "image/png"}], "usage": REAL_USAGE})
    fake = FakeHttp((503, {"error": {"message": "overloaded"}}), (429, {"error": {"message": "slow down"}}), ok)
    monkeypatch.setattr(gemini, "http", fake)
    assert gemini.generate_image("K", "gemini-nano-banana-2.1", "p", [])["ok"] and len(fake.requests) == 3
    fake = FakeHttp((503, {"error": {"message": "overloaded"}}))
    monkeypatch.setattr(gemini, "http", fake)
    out = gemini.generate_image("K", "gemini-nano-banana-2.1", "p", [], retries=2)
    assert not out["ok"] and len(fake.requests) == 2 and out["error"] == "overloaded"
    fake = FakeHttp((400, {"error": {"message": "bad"}}))
    monkeypatch.setattr(gemini, "http", fake)
    gemini.generate_image("K", "gemini-nano-banana-2.1", "p", [])
    assert len(fake.requests) == 1                                                                # a client error is not retried


def answer(text):
    return (200, {"candidates": [{"content": {"parts": [{"text": text}]}}], "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}})


def test_ask_json_builds_the_generate_content_request_and_parses_the_answer(monkeypatch):
    fake = FakeHttp(answer(json.dumps(make_checklist())))
    monkeypatch.setattr(gemini, "http", fake)
    out = gemini.ask_json("KEY", "gemini-3.5-flash-lite", "review", [(b"img", "image/jpeg")], CHECKLIST_SCHEMA)
    assert out["ok"] and out["data"]["items"]["text"]["answer"] == "same" and out["usage"]["promptTokenCount"] == 10
    req = fake.requests[0]
    assert req["url"] == gemini.BASE + "/models/gemini-3.5-flash-lite:generateContent"
    cfg = req["body"]["generationConfig"]
    assert cfg == {"temperature": 0, "responseMimeType": "application/json", "responseSchema": CHECKLIST_SCHEMA}
    parts = req["body"]["contents"][0]["parts"]
    assert parts[0] == {"text": "review"} and base64.b64decode(parts[1]["inline_data"]["data"]) == b"img"


def test_ask_json_reports_unusable_answers(monkeypatch):
    monkeypatch.setattr(gemini, "http", FakeHttp(answer("not json at all")))
    out = gemini.ask_json("K", "m", "p", [], BOX_SCHEMA)
    assert not out["ok"] and out["error"].startswith("could not parse the judge answer") and out["raw"] == "not json at all"
    monkeypatch.setattr(gemini, "http", FakeHttp((200, {"candidates": []})))
    assert not gemini.ask_json("K", "m", "p", [], BOX_SCHEMA)["ok"]
    monkeypatch.setattr(gemini, "http", FakeHttp((403, {"error": {"message": "key not valid"}})))
    out = gemini.ask_json("K", "m", "p", [], BOX_SCHEMA)
    assert out["error"] == "HTTP 403: key not valid"


def test_the_key_comes_from_the_environment_only(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert gemini.get_key() is None
    monkeypatch.setenv("GEMINI_API_KEY", "secret-value-123")
    assert gemini.get_key() == "secret-value-123"


def test_the_adapters_wrap_the_functions(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret-value-123")
    fake = FakeHttp(answer(json.dumps({"box_2d": [1, 2, 3, 4]})))
    monkeypatch.setattr(gemini, "http", fake)
    r = GeminiVlm("gemini-3.5-flash-lite").ask_json("p", [(b"i", "image/jpeg")], BOX_SCHEMA)
    assert r.ok and r.data == {"box_2d": [1, 2, 3, 4]} and fake.requests[0]["key"] == "secret-value-123"
    eng = load_engine("gemini-nano-banana-2.1")
    assert isinstance(eng, GeminiEngine) and eng.estimate_cost("2k", 2) == pytest.approx((0.112, 0.122))
    monkeypatch.setattr(gemini, "http", FakeHttp((200, {"outputs": [{"type": "image", "data": PNG, "mime_type": "image/png"}], "usage": REAL_USAGE})))
    g = eng.generate("p", [(b"a", "image/jpeg"), (b"b", "image/jpeg")], res="1k")
    assert g.ok and g.stamp == {"engine": "gemini-nano-banana-2.1", "api": "gemini-interactions"} and g.cost_hi == pytest.approx(0.0369825)


def test_an_engine_without_a_key_can_plan_but_not_run(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    eng = GeminiEngine()
    assert eng.estimate_cost("1k") == (0.037, 0.041)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not set"):
        eng.check_ready()
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not set"):
        eng.generate("p", [])
    with pytest.raises(KeyError):
        eng.estimate_cost("4k")


def test_the_key_never_reaches_a_record(monkeypatch, tmp_path):
    """A failing call must not put the key into an error message that ends up in a ledger or a judgment."""
    monkeypatch.setattr(gemini, "http", FakeHttp((401, {"error": {"message": "API key not valid. Please pass a valid API key."}})))
    out = gemini.generate_image("secret-value-123", "gemini-nano-banana-2.1", "p", [])
    assert "secret-value-123" not in json.dumps({k: v for k, v in out.items() if k != "image"})
    out = gemini.ask_json("secret-value-123", "m", "p", [], BOX_SCHEMA)
    assert "secret-value-123" not in json.dumps(out)
