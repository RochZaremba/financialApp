"""Allowlisted bank failure metadata; never exception messages, bodies or identifiers."""

from datetime import datetime, timezone
import re

from cryptography.fernet import InvalidToken
from sqlalchemy.exc import SQLAlchemyError

PROVIDER_CODES = frozenset(
    """ACCESS_DENIED ACCOUNT_DOES_NOT_EXIST ALREADY_AUTHORIZED ASPSP_ACCOUNT_NOT_ACCESSIBLE ASPSP_ERROR
    ASPSP_PAYMENT_NOT_ACCESSIBLE ASPSP_PSU_ACTION_REQUIRED ASPSP_RATE_LIMIT_EXCEEDED ASPSP_TIMEOUT
    AUTHORIZATION_NOT_PROVIDED CLOSED_SESSION DATE_FROM_IN_FUTURE DATE_TO_WITHOUT_DATE_FROM
    EXPIRED_AUTHORIZATION_CODE EXPIRED_SESSION INVALID_ACCOUNT_ID INVALID_HOST INVALID_PAYMENT
    NO_ACCOUNTS_ADDED PAYMENT_LIMIT_EXCEEDED PAYMENT_NOT_AUTHORIZED PAYMENT_NOT_FINALIZED PAYMENT_NOT_FOUND
    PAYMENT_SUBMISSION_NOT_DEFERRED PAYMENT_SUBMISSION_NOT_SUPPORTED PSU_HEADER_INVALID PSU_HEADER_NOT_PROVIDED
    REDIRECT_URI_NOT_ALLOWED REVOKED_SESSION SESSION_DOES_NOT_EXIST TRANSACTION_DOES_NOT_EXIST UNAUTHORIZED_ACCESS
    UNAUTHORIZED_IP UNTRUSTED_PAYMENT_PARTY WEBHOOK_URI_NOT_ALLOWED WRONG_ASPSP_PROVIDED WRONG_AUTHORIZATION_CODE
    WRONG_CONTINUATION_KEY WRONG_CREDENTIALS_PROVIDED WRONG_DATE_INTERVAL WRONG_REQUEST_PARAMETERS
    WRONG_SESSION_STATUS WRONG_TRANSACTIONS_PERIOD""".split()
)
INTERNAL_CODES = frozenset(
    """BANK_UNAVAILABLE BANK_TIMEOUT INVALID_BANK_RESPONSE RESPONSE_TOO_LARGE HISTORY_TOO_LARGE PAGINATION_LOOP
    INVALID_BANK_AMOUNT INVALID_BANK_MOVEMENT CURRENCY_MISMATCH INVALID_BANK_DATE BANK_ENTRY_CHANGED
    CONNECTION_CHANGED SYNC_FAILED SESSION_EXPIRED SESSION_NOT_FOUND""".split()
)
STAGES = frozenset(
    """load_accounts decrypt_account fetch_transactions parse_transactions fetch_balances parse_balances
    authorize_write save_entries save_balances commit""".split()
)
EXCEPTION_TYPES = frozenset(
    """BankError TimeoutException RequestError JSONDecodeError AttributeError KeyError TypeError ValueError
    InvalidToken DatabaseError OSError UnexpectedError""".split()
)


def safe_code(value):
    if isinstance(value, str) and (value in PROVIDER_CODES | INTERNAL_CODES or re.fullmatch(r"HTTP_[1-5][0-9]{2}", value)):
        return value
    return "SYNC_FAILED"


def exception_type(exc):
    # Do not serialize arbitrary class names: even those can contain private values.
    if isinstance(exc, InvalidToken):
        return "InvalidToken"
    if isinstance(exc, SQLAlchemyError):
        return "DatabaseError"
    for kind in (AttributeError, KeyError, TypeError, ValueError, OSError):
        if isinstance(exc, kind):
            return kind.__name__
    return "UnexpectedError"


def failure_diagnostic(exc, stage, duration_ms, http_status=None):
    kind = getattr(exc, "exception_type", None)
    return {
        "stage": stage if stage in STAGES else "load_accounts",
        "exception_type": kind if isinstance(kind, str) and kind in EXCEPTION_TYPES else exception_type(exc),
        "code": safe_code(getattr(exc, "code", None)),
        "http_status": http_status if type(http_status) is int and 100 <= http_status <= 599 else None,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": max(0, min(int(duration_ms), 24 * 60 * 60 * 1000)),
    }


def public_diagnostic(value):
    if not isinstance(value, dict):
        return None
    stage, kind = value.get("stage"), value.get("exception_type")
    if not isinstance(stage, str) or stage not in STAGES or not isinstance(kind, str) or kind not in EXCEPTION_TYPES:
        return None
    try:
        occurred = datetime.fromisoformat(value["occurred_at"])
        duration = value["duration_ms"]
        if occurred.tzinfo is None or type(duration) is not int or not 0 <= duration <= 24 * 60 * 60 * 1000:
            return None
    except (ValueError, TypeError, KeyError):
        return None
    status = value.get("http_status")
    return {
        "stage": stage,
        "exception_type": kind,
        "code": safe_code(value.get("code")),
        "http_status": status if type(status) is int and 100 <= status <= 599 else None,
        "occurred_at": occurred.astimezone(timezone.utc).isoformat(),
        "duration_ms": duration,
    }
