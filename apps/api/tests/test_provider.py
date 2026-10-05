import base64
import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from app.config import Settings, settings
from app.receipts import GeminiProvider, OpenAIProvider, provider, gemini_schema
from app.schemas import Extraction

ROOT = Path(__file__).resolve().parents[3]


def gemini_output(output, finish_reason="STOP"):
    return {"candidates": [{"finishReason": finish_reason, "content": {"parts": [{"text": json.dumps(output)}]}}]}


def test_openai_adapter_structured_image_contract(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-not-a-real-key")
    expected = json.loads((ROOT / "fixtures/lidl.json").read_text())
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            200,
            json={"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(expected)}]}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.receipts.httpx.post", fake_post)
    result = OpenAIProvider().extract(b"image-bytes", [{"id": "category-test", "name": "Jedzenie"}])
    assert result.total == 13975
    url, kwargs = calls[0]
    assert url == "https://api.openai.com/v1/responses"
    payload = kwargs["json"]
    assert payload["store"] is False and payload["text"]["format"]["strict"] is True
    assert payload["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,")
    schema = payload["text"]["format"]["schema"]
    assert set(schema["properties"]) == set(schema["required"])
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(
    "output",
    [
        {"merchant": "Lidl", "date": "2026-10-04", "total": 139.75, "items": []},
        {"merchant": "Lidl", "date": "not-a-date", "total": 13975, "items": []},
        {"merchant": "Lidl", "date": None, "total": 13975, "items": [], "unexpected": "field"},
    ],
)
@pytest.mark.parametrize("adapter", [OpenAIProvider, GeminiProvider])
def test_ai_untrusted_output_is_rejected(monkeypatch, output, adapter):
    monkeypatch.setattr(settings, "openai_api_key", "test-not-a-real-key")
    monkeypatch.setattr(settings, "gemini_api_key", "test-not-a-real-key")
    monkeypatch.setattr(
        "app.receipts.httpx.post",
        lambda url, **kwargs: httpx.Response(
            200,
            json=gemini_output(output)
            if adapter is GeminiProvider
            else {"output": [{"content": [{"type": "output_text", "text": json.dumps(output)}]}]},
            request=httpx.Request("POST", url),
        ),
    )
    with pytest.raises(ValidationError):
        adapter().extract(b"image", [])


@pytest.mark.parametrize("adapter", [OpenAIProvider, GeminiProvider])
def test_missing_key_honest_failure(monkeypatch, adapter):
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr("app.receipts.httpx.post", lambda *a, **kw: pytest.fail("No network request without a key"))
    with pytest.raises(ValueError, match="Brak klucza"):
        adapter().extract(b"image", [])


def test_gemini_structured_image_contract_and_provider_selection(monkeypatch):
    monkeypatch.setattr(settings, "receipt_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-private-key")
    monkeypatch.setattr(settings, "gemini_model", "gemini-3.8-flash")
    expected = json.loads((ROOT / "fixtures/lidl.json").read_text())
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        payload = gemini_output(expected)
        payload["candidates"][0]["content"]["parts"].insert(0, {"thought": True, "text": "Not receipt output"})
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.receipts.httpx.post", fake_post)
    assert isinstance(provider(), GeminiProvider)
    result = provider().extract(b"sanitized-image", [{"id": "food-id", "name": "Jedzenie"}])
    assert result.total == 13975 and len(result.items) == 6
    url, request = calls[0]
    assert url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
    assert "test-private-key" not in url and request["headers"] == {"x-goog-api-key": "test-private-key"}
    assert request["timeout"] == 75
    payload = request["json"]
    assert payload["contents"][0]["parts"][1]["inlineData"] == {
        "mimeType": "image/png",
        "data": base64.b64encode(b"sanitized-image").decode(),
    }
    prompt = payload["contents"][0]["parts"][0]["text"]
    assert "integer grosze" in prompt and "food-id" in prompt
    fmt = payload["generationConfig"]["responseFormat"]["text"]
    assert fmt["mimeType"] == "APPLICATION_JSON"
    assert fmt["schema"]["additionalProperties"] is False
    amount = fmt["schema"]["$defs"]["ExtractedItem"]["properties"]["amount"]["anyOf"]
    assert [option["type"] for option in amount] == ["integer", "null"]
    assert "maximum" not in amount[0]
    assert Extraction.model_json_schema()["$defs"]["ExtractedItem"]["properties"]["amount"]["anyOf"][0]["maximum"] == 100_000_000_000


def test_gemini_wire_schema_retains_structure_but_domain_validation_remains_strict():
    wire = gemini_schema(Extraction.model_json_schema())
    assert set(wire["required"]) == set(wire["properties"])
    assert wire["additionalProperties"] is False
    assert wire["properties"]["items"]["items"]["$ref"] == "#/$defs/ExtractedItem"
    for invalid in [{"total": 100_000_000_001}, {"merchant": "x" * 121}, {"date": "wrong"}]:
        with pytest.raises(ValidationError):
            Extraction.model_validate({"merchant": "Sklep", "date": None, "total": None, "items": []} | invalid)


@pytest.mark.parametrize("finish_reason", ["MAX_TOKENS", "SAFETY", None])
def test_gemini_incomplete_response_is_never_accepted(monkeypatch, finish_reason):
    monkeypatch.setattr(settings, "gemini_api_key", "test-not-a-real-key")
    # Even valid-looking partial JSON must not be committed as a full extraction.
    expected = json.loads((ROOT / "fixtures/lidl.json").read_text())
    monkeypatch.setattr(
        "app.receipts.httpx.post",
        lambda url, **kwargs: httpx.Response(200, json=gemini_output(expected, finish_reason), request=httpx.Request("POST", url)),
    )
    with pytest.raises(ValueError, match="pełnego odczytu"):
        GeminiProvider().extract(b"image", [])


def test_gemini_blocked_prompt_and_timeout(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-not-a-real-key")
    monkeypatch.setattr(
        "app.receipts.httpx.post",
        lambda url, **kwargs: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}, request=httpx.Request("POST", url)),
    )
    with pytest.raises(ValueError, match="pełnego odczytu"):
        GeminiProvider().extract(b"image", [])

    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr("app.receipts.httpx.post", timeout)
    with pytest.raises(httpx.ReadTimeout):
        GeminiProvider().extract(b"image", [])


def test_receipt_configuration_validation():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, receipt_provider="typo")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, gemini_model="../other?key=secret")
    config = Settings(_env_file=None, receipt_provider="gemini", gemini_api_key="", openai_api_key="other-provider-key")
    assert not config.receipt_ai_available
    config.gemini_api_key = "configured"
    assert config.receipt_ai_available
