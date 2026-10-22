"""OCR attempts retain proposals and diagnostic codes, never raw provider errors."""

import logging
import time
from collections import defaultdict

import httpx
from pydantic import ValidationError

from .config import settings
from .domain import classify, records
from .models import Category, ClassificationRule, ReceiptOCRAttempt, uid
from .receipts import ProviderFailure, provider

logger = logging.getLogger(__name__)


def error_details(exc):
    detail = {"kind": "provider_error", "code": "UNKNOWN_ERROR", "http_status": None, "retryable": False}
    message = "Dostawca nie zwrócił odczytu. Spróbuj ponownie lub uzupełnij paragon ręcznie."
    if isinstance(exc, ProviderFailure):
        detail.update(kind=exc.kind, code=exc.code, retryable=exc.retryable, http_status=200)
        message = {
            "output_truncated": "Odpowiedź została ucięta przez limit generowania. Spróbuj ponownie; jeśli problem wraca, sprawdź model i jego limit odpowiedzi.",
            "blocked": "Dostawca zablokował zdjęcie lub przerwał generowanie. Sprawdź czytelność zdjęcia albo uzupełnij paragon ręcznie.",
            "empty_output": "Dostawca nie zwrócił żadnego wyniku odczytu. Spróbuj ponownie albo uzupełnij dane ręcznie.",
        }.get(exc.kind, message)
    elif isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail["http_status"] = status
        codes = {
            "INVALID_ARGUMENT",
            "UNAUTHENTICATED",
            "PERMISSION_DENIED",
            "NOT_FOUND",
            "RESOURCE_EXHAUSTED",
            "FAILED_PRECONDITION",
            "INTERNAL",
            "UNAVAILABLE",
            "DEADLINE_EXCEEDED",
            "CANCELLED",
            "UNKNOWN",
        }
        reasons = {"API_KEY_INVALID", "API_KEY_SERVICE_BLOCKED", "RATE_LIMIT_EXCEEDED", "QUOTA_EXCEEDED", "ACCESS_TOKEN_EXPIRED"}
        try:
            error = exc.response.json().get("error", {})
            code = error.get("status")
            if code in codes:
                detail["code"] = code
            for item in error.get("details", []):
                if isinstance(item, dict) and item.get("reason") in reasons:
                    detail["reason"] = item["reason"]
        except (ValueError, AttributeError, TypeError):
            pass
        if detail["code"] == "UNKNOWN_ERROR":
            detail["code"] = f"HTTP_{status}"
        if status == 429:
            detail.update(kind="quota", retryable=True)
            message = (
                "Przekroczono limit zapytań lub dostępny limit rozliczeniowy dostawcy. Sprawdź limity i rozliczenia przed ponowieniem."
            )
        elif status in (401, 403):
            detail["kind"] = "access_denied"
            message = "Brak dostępu do dostawcy. Sprawdź klucz API, uprawnienia i dostęp sieciowy."
        elif status == 404:
            detail["kind"] = "model_not_found"
            message = "Wybrany model lub adres usługi jest niedostępny. Sprawdź nazwę modelu i jego dostępność dla tego klucza."
        elif status == 400:
            detail["kind"] = "invalid_request"
            message = "Dostawca odrzucił format żądania, schemat odpowiedzi lub zdjęcie. Wymaga to sprawdzenia konfiguracji integracji."
        elif status >= 500:
            detail.update(kind="service_unavailable", retryable=True)
            message = "Usługa dostawcy jest chwilowo niedostępna lub przeciążona. Spróbuj ponownie później."
        retry_after = exc.response.headers.get("retry-after", "")
        if retry_after.isdigit():
            detail["retry_after_seconds"] = min(int(retry_after), 86400)
    elif isinstance(exc, httpx.TimeoutException):
        detail.update(kind="timeout", code="TIMEOUT", retryable=True)
        message = "Przekroczono czas oczekiwania na dostawcę OCR. Zdjęcie i zapisane dane pozostają dostępne; możesz ponowić odczyt."
    elif isinstance(exc, httpx.RequestError):
        detail.update(kind="connection", code="CONNECTION_ERROR", retryable=True)
        message = "Nie udało się połączyć z dostawcą OCR. Sprawdź dostęp sieciowy i spróbuj ponownie."
    elif isinstance(exc, ValidationError):
        detail.update(kind="invalid_output", code="SCHEMA_VALIDATION_FAILED", http_status=200)
        allowed = {"merchant", "date", "total", "items", "name", "quantity", "amount", "category_id", "confidence"}
        detail["fields"] = sorted(
            {str(part) for issue in exc.errors(include_input=False, include_context=False) for part in issue["loc"] if part in allowed}
        )
        message = "Odpowiedź dostawcy nie spełnia schematu danych paragonu (np. kwota lub data). Nie zapisano nieprawidłowych danych."
    elif isinstance(exc, ValueError) and "Brak klucza" in str(exc):
        detail.update(kind="configuration", code="MISSING_API_KEY")
        message = "Brak klucza API skonfigurowanego dostawcy OCR. Uzupełnij konfigurację albo paragon ręcznie."
    elif isinstance(exc, (ValueError, TypeError, AttributeError, KeyError)):
        detail.update(kind="invalid_output", code="INVALID_RESPONSE")
        message = "Dostawca zwrócił pustą lub nieprawidłową odpowiedź. Nie zastąpiono zapisanych danych."
    detail["message"] = message
    return detail


def proposal(db, household_id, extraction, categories):
    active = {c["id"] for c in categories}
    rules = records(db, ClassificationRule, household_id)
    items, totals = [], defaultdict(int)
    ambiguous = False
    for item in extraction.items:
        category, confidence = classify(db, household_id, item.name, extraction.merchant, rules=rules, active=active)
        if not category:
            category, confidence = (item.category_id, item.confidence) if item.category_id in active else (None, 0)
        if category and item.amount is not None:
            totals[category] += item.amount
        ambiguous |= category is None or confidence < round(settings.classification_review_threshold * 100)
        items.append(
            dict(
                name=item.name,
                quantity=item.quantity or "",
                amount=item.amount,
                category_id=category,
                confidence=confidence,
                reviewed=False,
            )
        )
    complete = bool(
        extraction.merchant
        and extraction.date
        and extraction.total
        and items
        and all(i["amount"] is not None for i in items)
        and sum(i["amount"] for i in items if i["amount"] is not None) == extraction.total
    )
    result = dict(
        merchant=extraction.merchant, date=extraction.date.isoformat() if extraction.date else None, total=extraction.total, items=items
    )
    return result, complete, ambiguous or any(value < 0 for value in totals.values())


def run_extraction(db, receipt, member, image, key):
    selected = settings.receipt_provider
    model = settings.gemini_model if selected == "gemini" else settings.openai_model if selected == "openai" else ""
    attempt = ReceiptOCRAttempt(
        id=uid(),
        household_id=receipt.household_id,
        receipt_id=receipt.id,
        key=key,
        provider=selected,
        model=model,
        created_by=member.user_id,
        receipt_updated_at=receipt.updated_at,
    )
    categories = [dict(id=c.id, name=c.name, group=c.group) for c in records(db, Category, receipt.household_id) if not c.archived]
    started = time.monotonic()
    try:
        extraction = provider().extract(image, categories)
    except Exception as exc:
        attempt.status = "failed"
        attempt.diagnostics = error_details(exc)
        logger.warning(
            "OCR failed attempt_id=%s provider=%s model=%s kind=%s code=%s http_status=%s",
            attempt.id,
            selected,
            model,
            attempt.diagnostics["kind"],
            attempt.diagnostics["code"],
            attempt.diagnostics["http_status"],
        )
        extraction = None
    finally:
        attempt.duration_ms = min(int((time.monotonic() - started) * 1000), 2_147_483_647)
    ambiguous = False
    if extraction is not None:
        # Classification/database errors must not be disguised as provider failures.
        attempt.result, complete, ambiguous = proposal(db, receipt.household_id, extraction, categories)
        attempt.status = "succeeded" if complete else "partial"
        if not complete:
            mismatch = bool(
                extraction.total
                and extraction.items
                and all(i.amount is not None for i in extraction.items)
                and sum(i.amount for i in extraction.items) != extraction.total
            )
            attempt.diagnostics = {
                "kind": "incomplete_data",
                "code": "TOTAL_MISMATCH" if mismatch else "INCOMPLETE_DATA",
                "http_status": 200 if selected in ("gemini", "openai") else None,
                "retryable": True,
                "message": "Odczytano dane, ale suma pozycji nie zgadza się z sumą paragonu."
                if mismatch
                else "Odczyt nie zawiera wszystkich wymaganych danych paragonu.",
            }
    db.add(attempt)
    db.flush()
    return attempt, ambiguous
