import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import ReceiptOCRAttempt, Transaction, User
from app.ocr import error_details
from app.receipts import ProviderFailure

ROOT = Path(__file__).resolve().parents[3]


def upload(client, home):
    response = client.post(home["path"] + "/receipts", files={"file": ("lidl.png", (ROOT / "fixtures/lidl.png").read_bytes(), "image/png")})
    assert response.status_code == 201
    return response.json()


def retry(client, home, receipt, key="retry-operation-1"):
    return client.post(f"{home['path']}/receipts/{receipt['id']}/ocr", headers={"Idempotency-Key": key})


def apply(client, home, receipt, attempt):
    return client.post(
        f"{home['path']}/receipts/{receipt['id']}/ocr/{attempt['id']}/apply", json={"expected_updated_at": attempt["receipt_updated_at"]}
    )


@pytest.mark.parametrize(
    "status,code,kind",
    [
        (400, "INVALID_ARGUMENT", "invalid_request"),
        (401, "UNAUTHENTICATED", "access_denied"),
        (403, "PERMISSION_DENIED", "access_denied"),
        (404, "NOT_FOUND", "model_not_found"),
        (429, "RESOURCE_EXHAUSTED", "quota"),
        (503, "UNAVAILABLE", "service_unavailable"),
    ],
)
def test_safe_upstream_diagnostics_for_initial_upload_and_retry(client, household, monkeypatch, caplog, status, code, kind):
    monkeypatch.setattr(settings, "receipt_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "sensitive-api-key")
    body = {
        "error": {
            "code": status,
            "status": code,
            "message": "sensitive-api-key private receipt text",
            "details": [{"reason": "API_KEY_INVALID", "metadata": {"key": "sensitive-api-key"}}],
        }
    }
    monkeypatch.setattr(
        "app.receipts.httpx.post",
        lambda url, **kwargs: httpx.Response(status, json=body, headers={"retry-after": "30"}, request=httpx.Request("POST", url)),
    )
    receipt = upload(client, household)
    assert receipt["status"] == "failed"
    first = receipt["ocr_attempts"][0]
    assert first["diagnostics"]["code"] == code and first["diagnostics"]["kind"] == kind
    response = retry(client, household, receipt)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "failed" and result["diagnostics"]["http_status"] == status
    assert result["diagnostics"]["retry_after_seconds"] == 30
    assert "sensitive-api-key" not in response.text + json.dumps(receipt) + caplog.text
    assert "private receipt text" not in response.text + caplog.text
    assert result["model"] == settings.gemini_model
    identifier = client.get("/auth/me").json()["user"]["id"]
    with SessionLocal() as db:
        db.get(User, identifier).is_admin = True
        db.commit()
    summary = client.get("/admin/ocr-summary").json()
    assert summary["total"] == 2 and summary["groups"][0]["code"] == code and summary["groups"][0]["count"] == 2
    assert receipt["id"] not in json.dumps(summary) and "private receipt text" not in json.dumps(summary)


def test_retry_is_a_proposal_reuses_stored_photo_and_is_idempotent(client, household, monkeypatch):
    receipt = upload(client, household)
    path = f"{household['path']}/receipts/{receipt['id']}"
    saved = {k: receipt[k] for k in ("merchant", "date", "total", "items")}
    saved["merchant"] = "Moja ręczna poprawka"
    saved["items"] = [
        {k: v for k, v in item.items() if k in {"name", "quantity", "amount", "category_id", "confidence", "reviewed"}}
        for item in receipt["items"]
    ]
    assert client.put(path, json=saved).status_code == 200
    calls = []
    from app.receipts import FixtureProvider

    original = FixtureProvider.extract

    def extract(self, image, categories):
        calls.append(image)
        return original(self, image, categories)

    monkeypatch.setattr(FixtureProvider, "extract", extract)
    result = retry(client, household, receipt).json()
    assert result["status"] == "succeeded" and result["result"]["total"] == receipt["total"]
    assert retry(client, household, receipt).json()["id"] == result["id"] and len(calls) == 1
    assert client.get(path).json()["merchant"] == "Moja ręczna poprawka"
    response = apply(client, household, receipt, result)
    assert response.status_code == 200 and response.json()["merchant"] == "Lidl"
    assert apply(client, household, receipt, result).status_code == 200
    with SessionLocal() as db:
        assert len(db.scalars(select(ReceiptOCRAttempt)).all()) == 2
        assert not db.scalars(select(Transaction)).all()


def test_failed_retry_preserves_ready_items_and_manual_corrections(client, household, monkeypatch):
    receipt = upload(client, household)
    saved = receipt["ocr_attempts"][0]["result"] | {"merchant": "Własna poprawka"}
    receipt = client.put(f"{household['path']}/receipts/{receipt['id']}", json=saved).json()

    def fail(*args, **kwargs):
        raise httpx.ReadTimeout("private body sensitive-key")

    monkeypatch.setattr("app.receipts.FixtureProvider.extract", fail)
    result = retry(client, household, receipt).json()
    assert result["diagnostics"]["kind"] == "timeout"
    current = client.get(f"{household['path']}/receipts/{receipt['id']}").json()
    for key in ("merchant", "date", "total", "items", "status", "updated_at"):
        assert current[key] == receipt[key]
    assert apply(client, household, receipt, result).status_code == 422


def test_apply_rejects_concurrent_saved_corrections(client, household):
    receipt = upload(client, household)
    attempt = retry(client, household, receipt).json()
    proposal = attempt["result"] | {"merchant": "Poprawka po odczycie"}
    assert client.put(f"{household['path']}/receipts/{receipt['id']}", json=proposal).status_code == 200
    assert apply(client, household, receipt, attempt).status_code == 409
    assert client.get(f"{household['path']}/receipts/{receipt['id']}").json()["merchant"] == "Poprawka po odczycie"


def test_item_only_save_invalidates_an_older_ocr_proposal(client, household):
    receipt = upload(client, household)
    path = f"{household['path']}/receipts/{receipt['id']}"
    data = receipt["ocr_attempts"][0]["result"]
    receipt = client.put(path, json=data).json()
    attempt = retry(client, household, receipt).json()
    data["items"][0]["name"] = "Ręczna poprawka samej pozycji"
    updated = client.put(path, json=data).json()
    assert updated["updated_at"] != receipt["updated_at"]
    assert apply(client, household, receipt, attempt).status_code == 409
    assert client.get(path).json()["items"][0]["name"] == "Ręczna poprawka samej pozycji"


def test_confirmed_receipt_can_be_reread_without_changing_transaction(client, household):
    receipt = upload(client, household)
    data = {k: receipt[k] for k in ("merchant", "date", "total")}
    data["items"] = [
        {k: v for k, v in item.items() if k in {"name", "quantity", "amount", "category_id", "confidence", "reviewed"}}
        | {"reviewed": True, "category_id": household["data"]["categories"][0]["id"]}
        for item in receipt["items"]
    ]
    response = client.post(
        f"{household['path']}/receipts/{receipt['id']}/finalize", json=data | {"account_id": household["data"]["accounts"][0]["id"]}
    )
    assert response.status_code == 200
    transaction = response.json()
    result = retry(client, household, receipt).json()
    assert result["status"] == "succeeded" and apply(client, household, receipt, result).status_code == 409
    current = client.get(f"{household['path']}/receipts/{receipt['id']}").json()
    assert current["transaction_id"] == transaction["id"] and current["status"] == "confirmed"
    with SessionLocal() as db:
        assert len(db.scalars(select(Transaction)).all()) == 1


def test_attempts_are_household_scoped_and_summary_does_not_expose_receipts(client, household):
    receipt = upload(client, household)
    attempt = retry(client, household, receipt).json()
    with TestClient(app) as other:
        assert other.post("/auth/register", json={"email": "other@example.com", "password": "private-other-password"}).status_code == 201
        assert (
            other.post(
                f"{household['path']}/receipts/{receipt['id']}/ocr", headers={"Idempotency-Key": "private-other-attempt"}
            ).status_code
            == 403
        )
        assert other.get(f"{household['path']}/receipts/{receipt['id']}/ocr/{attempt['id']}").status_code == 403
        assert other.get("/admin/ocr-summary").status_code == 403
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "roch@example.com"))
        user.is_admin = True
        db.commit()
    summary = client.get("/admin/ocr-summary")
    assert summary.status_code == 200 and summary.json()["total"] == 0  # Fixture calls are not live-provider traffic.
    assert receipt["id"] not in summary.text and "Lidl" not in summary.text


@pytest.mark.parametrize("reason,kind", [("MAX_TOKENS", "output_truncated"), ("SAFETY", "blocked")])
def test_finish_reason_is_persistable_without_exposing_model_output(reason, kind):
    detail = error_details(ProviderFailure("sensitive raw payload", reason, kind=kind))
    assert detail["code"] == reason and detail["kind"] == kind and "sensitive" not in json.dumps(detail)


@pytest.mark.parametrize(
    "output,code",
    [
        ({"candidates": [{"finishReason": "MAX_TOKENS"}]}, "MAX_TOKENS"),
        ({"promptFeedback": {"blockReason": "SAFETY"}}, "SAFETY"),
        ({"candidates": []}, "NO_CANDIDATES"),
        (
            {
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": '{"merchant":"private receipt text","total":12.5}'}]}}
                ]
            },
            "SCHEMA_VALIDATION_FAILED",
        ),
    ],
)
def test_http_200_errors_keep_distinct_finish_and_validation_codes(client, household, monkeypatch, output, code):
    monkeypatch.setattr(settings, "receipt_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-only-key")
    monkeypatch.setattr(
        "app.receipts.httpx.post", lambda url, **kwargs: httpx.Response(200, json=output, request=httpx.Request("POST", url))
    )
    receipt = upload(client, household)
    assert receipt["ocr_attempts"][0]["diagnostics"]["code"] == code
    assert receipt["ocr_attempts"][0]["diagnostics"]["http_status"] == 200
    assert "private receipt text" not in json.dumps(receipt)


def test_partial_retry_reports_mismatched_sum_and_does_not_overwrite_current_items(client, household, monkeypatch):
    receipt = upload(client, household)
    from app.schemas import Extraction

    data = json.loads((ROOT / "fixtures/lidl.json").read_text())
    data["total"] = 100
    monkeypatch.setattr("app.receipts.FixtureProvider.extract", lambda *args: Extraction.model_validate(data))
    result = retry(client, household, receipt).json()
    assert result["status"] == "partial" and result["diagnostics"]["code"] == "TOTAL_MISMATCH"
    assert client.get(f"{household['path']}/receipts/{receipt['id']}").json()["total"] == receipt["total"]


def test_attempt_from_another_receipt_cannot_be_applied(client, household):
    first = upload(client, household)
    second = upload(client, household)
    attempt = retry(client, household, first).json()
    assert apply(client, household, second, attempt).status_code == 404


def test_retry_requires_image_key_and_respects_rate_limit(client, household):
    receipt = upload(client, household)
    assert client.post(f"{household['path']}/receipts/{receipt['id']}/ocr").status_code == 422
    for index in range(11):
        assert retry(client, household, receipt, f"rate-attempt-{index}").status_code == 200
    assert retry(client, household, receipt, "rate-attempt-last").status_code == 429


def test_parallel_retry_does_not_make_a_second_provider_call_or_block_draft_edits(client, household, monkeypatch):
    receipt = upload(client, household)
    from app.receipts import FixtureProvider

    original = FixtureProvider.extract
    started, release = Event(), Event()
    calls = []

    def extract(self, image, categories):
        calls.append(image)
        started.set()
        assert release.wait(10)
        return original(self, image, categories)

    monkeypatch.setattr(FixtureProvider, "extract", extract)
    with TestClient(app) as worker, ThreadPoolExecutor(max_workers=1) as executor:
        worker.cookies.update(client.cookies)
        future = executor.submit(retry, worker, household, receipt, "parallel-first-attempt")
        try:
            assert started.wait(5)
            assert retry(client, household, receipt, "parallel-second-attempt").status_code == 409
            proposal = receipt["ocr_attempts"][0]["result"] | {"merchant": "Poprawka podczas OCR"}
            assert client.put(f"{household['path']}/receipts/{receipt['id']}", json=proposal).status_code == 200
        finally:
            release.set()
        response = future.result(timeout=10)
    assert response.status_code == 200 and len(calls) == 1
    assert apply(client, household, receipt, response.json()).status_code == 409
