"""Server-only Enable Banking AIS; no bank passwords or payment methods."""

import base64
import json
import re
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

import httpx
import jwt
from cryptography.fernet import Fernet

from .config import settings
from .security import digest


@dataclass(frozen=True)
class BankConfig:
    household_id: str
    owner_id: str
    allowed_users: list[str]
    app_id: str
    private_key_path: str
    encryption_key_path: str
    vapid_key_path: str
    vapid_public_key: str
    contact_email: str

    def cipher(self):
        return Fernet(Path(self.encryption_key_path).read_bytes().strip())

    def seal(self, value):
        return self.cipher().encrypt(value.encode()).decode()

    def open(self, value):
        return self.cipher().decrypt(value.encode()).decode()


def config_path():
    return Path(settings.bank_config_path) if settings.bank_config_path else Path(settings.receipt_storage) / ".bank" / "config.json"


def load_config():
    try:
        path = config_path()
        if path.stat().st_mode & 0o077 or path.parent.stat().st_mode & 0o077:
            return None
        cfg = BankConfig(**json.loads(path.read_text()))
        for value in [cfg.household_id, cfg.owner_id, cfg.app_id, *cfg.allowed_users]:
            UUID(value)
        if len(set(cfg.allowed_users)) != 2 or cfg.owner_id not in cfg.allowed_users:
            return None
        for name in (cfg.private_key_path, cfg.encryption_key_path, cfg.vapid_key_path):
            secret = Path(name)
            if secret.resolve().parent != path.resolve().parent or secret.stat().st_mode & 0o077:
                return None
        cfg.cipher()
        return cfg
    except (OSError, ValueError, TypeError, KeyError):
        return None


class BankError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class EnableBanking:
    def __init__(self, cfg):
        self.cfg = cfg

    def call(self, method, path, data=None, params=None):
        now = int(time.time())
        try:
            token = jwt.encode(
                {"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": now, "exp": now + 120},
                Path(self.cfg.private_key_path).read_bytes(),
                algorithm="RS256",
                headers={"kid": self.cfg.app_id},
            )
            response = httpx.request(
                method,
                "https://api.enablebanking.com" + path,
                json=data,
                params=params,
                headers={"Authorization": "Bearer " + token},
                timeout=30,
                follow_redirects=False,
            )
            if not response.is_success:
                try:
                    code = response.json().get("error", "")
                except ValueError:
                    code = ""
                raise BankError(code if isinstance(code, str) and re.fullmatch(r"[A-Z_]{1,60}", code) else f"HTTP_{response.status_code}")
            if response.status_code == 204:
                return {}
            if len(response.content) > 8 * 1024 * 1024:
                raise BankError("RESPONSE_TOO_LARGE")
            return response.json()
        except BankError:
            raise
        except Exception:
            raise BankError("BANK_UNAVAILABLE") from None

    def banks(self):
        return self.call("GET", "/aspsps", params={"country": "PL", "service": "AIS"}).get("aspsps", [])

    def authorize(self, state, valid_until, bank):
        return self.call(
            "POST",
            "/auth",
            {
                "aspsp": {"name": bank, "country": "PL"},
                "psu_type": "personal",
                "language": "pl",
                "state": state,
                "redirect_url": settings.web_origin.rstrip("/") + "/",
                "access": {"valid_until": valid_until.isoformat()},
            },
        )

    def session(self, code):
        return self.call("POST", "/sessions", {"code": code})

    def revoke(self, session):
        return self.call("DELETE", "/sessions/" + quote(session, safe=""))

    def transactions(self, uid, start):
        rows, seen, continuation = [], set(), None
        for _ in range(100):
            params = {"date_from": start.isoformat()}
            if continuation:
                params["continuation_key"] = continuation
            result = self.call("GET", f"/accounts/{quote(uid, safe='')}/transactions", params=params)
            rows.extend(result["transactions"])
            if len(rows) > 10000:
                raise BankError("HISTORY_TOO_LARGE")
            continuation = result.get("continuation_key")
            if not continuation:
                return rows
            if continuation in seen:
                raise BankError("PAGINATION_LOOP")
            seen.add(continuation)
        raise BankError("HISTORY_TOO_LARGE")

    def balances(self, uid):
        return self.call("GET", f"/accounts/{quote(uid, safe='')}/balances").get("balances", [])


def minor_amount(value):
    try:
        decimal = Decimal(str(value)) * 100
        if not decimal.is_finite() or decimal != decimal.to_integral_value() or abs(decimal) > 100_000_000_000:
            raise ValueError()
        return int(decimal)
    except (InvalidOperation, ValueError, TypeError):
        raise BankError("INVALID_BANK_AMOUNT") from None


def movement(row, currency):
    if row.get("status") != "BOOK":
        return None
    try:
        money = row["transaction_amount"]
        if money["currency"] != currency:
            raise BankError("CURRENCY_MISMATCH")
        amount = abs(minor_amount(money["amount"]))
        direction = row["credit_debit_indicator"]
        if direction not in ("CRDT", "DBIT") or not amount:
            raise BankError("INVALID_BANK_MOVEMENT")
        day = date.fromisoformat(row["booking_date"])
        if not 2000 <= day.year <= 2100:
            raise ValueError()
        party = row.get("creditor" if direction == "DBIT" else "debtor") or {}
        descriptions = row.get("remittance_information", [])
        if isinstance(descriptions, str):
            descriptions = [descriptions]
        description = " · ".join(str(v) for v in [party.get("name", ""), *descriptions] if v)[:160] or "Operacja bankowa"
        reference = row.get("entry_reference")
        if reference is not None and not isinstance(reference, str):
            raise ValueError()
        counterpart = row.get("creditor_account" if direction == "DBIT" else "debtor_account") or {}
        iban = counterpart.get("iban", "").replace(" ", "").upper()
        return dict(
            amount=-amount if direction == "DBIT" else amount,
            date=day,
            description=description,
            reference=reference or None,
            counterparty_hash=digest(iban) if iban else None,
        )
    except BankError:
        raise
    except (ValueError, KeyError, TypeError):
        raise BankError("INVALID_BANK_MOVEMENT") from None


def push_url_allowed(url):
    from urllib.parse import urlsplit

    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and not parsed.username
            and not parsed.password
            and not parsed.fragment
            and parsed.port in (None, 443)
            and parsed.hostname in {"fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com"}
        )
    except ValueError:
        return False


def decode_push_key(value, length):
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        return len(decoded) == length
    except (ValueError, TypeError):
        return False
