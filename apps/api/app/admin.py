"""Host-provisioned administrators can recover ordinary user accounts."""

from typing import Annotated
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import StringConstraints
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import MCPConnection, PasswordResetEvent, SessionToken, User, ReceiptOCRAttempt
from .schemas import Credentials
from .security import current_user, hasher, rate_limit

router = APIRouter(prefix="/admin", tags=["administrator"])
Password = Annotated[str, StringConstraints(strip_whitespace=False, min_length=10, max_length=128)]


class PasswordReset(Credentials):
    admin_password: Password


def administrator(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Ta funkcja jest dostępna tylko dla administratora.")
    return user


@router.get("/ocr-summary")
def ocr_summary(actor: Annotated[User, Depends(administrator)], db: Annotated[Session, Depends(get_db)]):
    since = datetime.now(timezone.utc) - timedelta(days=7)
    # Metadata only: no result, image, receipt, household or user identifiers.
    rows = db.execute(
        select(ReceiptOCRAttempt.provider, ReceiptOCRAttempt.model, ReceiptOCRAttempt.status, ReceiptOCRAttempt.diagnostics)
        .where(ReceiptOCRAttempt.created_at >= since, ReceiptOCRAttempt.provider.in_(["gemini", "openai"]))
        .order_by(ReceiptOCRAttempt.created_at.desc())
        .limit(10001)
    ).all()
    truncated = len(rows) > 10000
    rows = rows[:10000]
    counts = Counter(
        (
            row.provider,
            row.model,
            row.status,
            row.diagnostics.get("kind", "none"),
            row.diagnostics.get("code", "OK"),
            row.diagnostics.get("http_status"),
        )
        for row in rows
    )
    return {
        "days": 7,
        "total": len(rows),
        "truncated": truncated,
        "groups": [
            dict(provider=k[0], model=k[1], status=k[2], kind=k[3], code=k[4], http_status=k[5], count=count) for k, count in counts.items()
        ],
    }


@router.post("/password-reset")
def reset_password(data: PasswordReset, actor: Annotated[User, Depends(administrator)], db: Annotated[Session, Depends(get_db)]):
    rate_limit(f"admin-reset:{actor.id}", 5, 300)
    if not hasher.verify(data.admin_password, actor.password_hash):
        raise HTTPException(403, "Nieprawidłowe hasło administratora.")
    target = db.scalar(select(User).where(User.email == data.email).with_for_update())
    if not target:
        raise HTTPException(404, "Nie znaleziono konta z tym adresem e-mail.")
    if target.is_admin:
        raise HTTPException(403, "Hasło administratora zmienia właściciel wdrożenia na serwerze.")
    target.password_hash = hasher.hash(data.password)
    target.updated_by = actor.id
    db.execute(delete(SessionToken).where(SessionToken.user_id == target.id))
    db.execute(delete(MCPConnection).where(MCPConnection.user_id == target.id))
    db.add(PasswordResetEvent(actor_id=actor.id, target_id=target.id, created_by=actor.id))
    db.commit()
    return {"ok": True}
