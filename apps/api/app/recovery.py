"""Owner-issued, short-lived, single-account recovery; no universal password."""

import base64
import binascii
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import get_db
from .config import settings
from .models import PasswordResetEvent, RecoveryGrantUse, SessionToken, User
from .schemas import Credentials
from .security import digest, hasher, rate_limit

router = APIRouter(prefix="/auth", tags=["recovery"])
INVALID = "Klucz odzyskiwania jest nieprawidłowy, wygasł lub został już użyty."


class Grant(BaseModel):
    id: str = Field(pattern=r"^[0-9a-f]{32}$")
    target_email_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_key: str = Field(min_length=43, max_length=44)
    valid_from: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def bounded_lifetime(self):
        if not self.valid_from.tzinfo or not self.expires_at.tzinfo:
            raise ValueError("Recovery grants require explicit time zones")
        if not timedelta(0) < self.expires_at - self.valid_from <= timedelta(hours=24):
            raise ValueError("Recovery grants must expire within 24 hours")
        return self


# Public verification metadata only. Private signing keys are never deployed.
GRANTS = [Grant.model_validate(row) for row in json.loads(Path(settings.recovery_grants_file).read_text())]


def message(grant: Grant) -> bytes:
    return (
        f"financialApp:account-recovery:v1:{grant.id}:{grant.target_email_sha256}:"
        f"{grant.valid_from.isoformat()}:{grant.expires_at.isoformat()}"
    ).encode("ascii")


def decode(value: str) -> bytes:
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


class RecoveryInput(Credentials):
    key: str = Field(min_length=40, max_length=160)
    password_confirmation: Annotated[str, StringConstraints(strip_whitespace=False, min_length=10, max_length=128)]

    @model_validator(mode="after")
    def confirmed_password(self):
        if self.password != self.password_confirmation:
            raise ValueError("Passwords must match")
        return self


@router.post("/recover")
def recover(data: RecoveryInput, request: Request, response: Response, db: Annotated[Session, Depends(get_db)]):
    rate_limit(f"recovery-ip:{request.client.host}", 10, 300)
    rate_limit(f"recovery-account:{digest(data.email)}", 5, 300)
    try:
        grant_id, signature = data.key.split(".")
        grant = next(g for g in GRANTS if g.id == grant_id)
        now = datetime.now(timezone.utc)
        if not grant.valid_from <= now < grant.expires_at or not secrets.compare_digest(grant.target_email_sha256, digest(data.email)):
            raise ValueError("Invalid grant")
        Ed25519PublicKey.from_public_bytes(decode(grant.public_key)).verify(decode(signature), message(grant))
    except (ValueError, StopIteration, binascii.Error, InvalidSignature):
        raise HTTPException(400, INVALID) from None

    # Login and all recovery paths serialize on this same row. A durable nonce
    # remains consumed even after restart, account deletion or image rollback.
    user = db.scalar(select(User).where(User.email == data.email).with_for_update())
    now = datetime.now(timezone.utc)
    if not user or user.is_admin or not grant.valid_from <= now < grant.expires_at or db.get(RecoveryGrantUse, grant.id):
        raise HTTPException(400, INVALID)
    user.password_hash = hasher.hash(data.password)
    user.updated_by = None
    db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
    db.add(RecoveryGrantUse(id=grant.id, target_id=user.id, used_at=now))
    db.add(PasswordResetEvent(target_id=user.id))
    db.commit()
    response.delete_cookie("dom_session", path="/")
    return {"ok": True}
