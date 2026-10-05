import hashlib
import secrets
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import Depends, HTTPException, Request, Response
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Member, SessionToken, User

hasher = PasswordHash.recommended()
DUMMY_HASH = hasher.hash("dummy-password-for-timing-protection")
_attempts: dict[str, deque] = defaultdict(deque)
_lock = Lock()


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def rate_limit(key: str, limit: int, seconds: int = 60):
    now = datetime.now(timezone.utc).timestamp()
    with _lock:
        queue = _attempts[key]
        while queue and queue[0] < now - seconds:
            queue.popleft()
        if len(queue) >= limit:
            raise HTTPException(429, "Zbyt wiele prób. Spróbuj za chwilę.", headers={"Retry-After": str(seconds)})
        queue.append(now)
        if len(_attempts) > 10_000:
            for old in list(_attempts):
                if not _attempts[old] or _attempts[old][-1] < now - seconds:
                    del _attempts[old]


def set_session(db: Session, user: User, response: Response):
    raw = secrets.token_urlsafe(48)
    db.add(SessionToken(token_hash=digest(raw), user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(days=14)))
    response.set_cookie(
        "dom_session", raw, httponly=True, secure=settings.app_env == "production", samesite="strict", max_age=14 * 86400, path="/"
    )


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    raw = request.cookies.get("dom_session")
    session = db.get(SessionToken, digest(raw)) if raw else None
    if not session or session.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(401, "Sesja wygasła. Zaloguj się ponownie.")
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, "Zaloguj się ponownie.")
    return user


def household_member(household_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Member:
    member = db.scalar(select(Member).where(Member.household_id == household_id, Member.user_id == user.id))
    if not member:
        raise HTTPException(403, "Nie masz dostępu do tego gospodarstwa.")
    return member
