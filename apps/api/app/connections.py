"""Explicit per-user grants, never a shared application password."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .domain import audit, serialize
from .models import MCPConnection, Member, User
from .schemas import Name, Schema
from .security import digest, hasher, household_member, rate_limit

router = APIRouter(prefix="/households/{household_id}/connections", tags=["AI connections"])
Db = Annotated[Session, Depends(get_db)]
Membership = Annotated[Member, Depends(household_member)]


class ConnectionInput(Schema):
    name: Name
    access: Literal["read", "write"] = "read"
    days: int = Field(default=30, strict=True, ge=1, le=90)
    password: str = Field(min_length=10, max_length=128)


@router.get("")
def connection_list(household_id: str, member: Membership, db: Db):
    return [
        serialize(row)
        for row in db.scalars(
            select(MCPConnection)
            .where(MCPConnection.household_id == household_id, MCPConnection.user_id == member.user_id)
            .order_by(MCPConnection.created_at.desc())
            .limit(100)
        )
    ]


@router.post("", status_code=201)
def connection_create(household_id: str, data: ConnectionInput, member: Membership, db: Db):
    rate_limit(f"mcp-create:{member.user_id}", 5, 300)
    user = db.scalar(select(User).where(User.id == member.user_id).with_for_update())
    if not hasher.verify(data.password, user.password_hash):
        raise HTTPException(403, "Nieprawidłowe hasło konta.")
    now = datetime.now(timezone.utc)
    active = db.scalar(
        select(func.count())
        .select_from(MCPConnection)
        .where(MCPConnection.user_id == user.id, MCPConnection.revoked_at.is_(None), MCPConnection.expires_at > now)
    )
    if active >= 20:
        raise HTTPException(409, "Odłącz nieużywane połączenie. Limit to 20 aktywnych połączeń.")
    raw = "razem_mcp_" + secrets.token_urlsafe(48)
    row = MCPConnection(
        household_id=household_id,
        user_id=user.id,
        name=data.name,
        access=data.access,
        token_hash=digest(raw),
        expires_at=now + timedelta(days=data.days),
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    audit(db, member, "mcp.connect", row.id)
    db.commit()
    return dict(connection=serialize(row), token=raw)


@router.delete("/{connection_id}")
def connection_revoke(household_id: str, connection_id: str, member: Membership, db: Db):
    row = db.scalar(
        select(MCPConnection)
        .where(MCPConnection.id == connection_id, MCPConnection.household_id == household_id, MCPConnection.user_id == member.user_id)
        .with_for_update()
    )
    if not row:
        raise HTTPException(404, "Nie znaleziono połączenia.")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        row.updated_by = member.user_id
        audit(db, member, "mcp.revoke", row.id)
        db.commit()
    return {"ok": True}


def connection_auth(db, raw):
    row = db.scalar(select(MCPConnection).where(MCPConnection.token_hash == digest(raw))) if raw else None
    now = datetime.now(timezone.utc)
    if not row or row.revoked_at or row.expires_at <= now:
        raise HTTPException(401, "Połączenie AI wygasło lub zostało odłączone.")
    member = db.scalar(select(Member).where(Member.household_id == row.household_id, Member.user_id == row.user_id))
    if not member or not db.get(User, row.user_id):
        raise HTTPException(401, "Połączenie AI nie ma już dostępu do domu.")
    return row
