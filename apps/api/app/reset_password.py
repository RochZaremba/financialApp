"""Owner-assisted password recovery from the trusted deployment host."""

import getpass
import sys

from sqlalchemy import delete, select

from .db import SessionLocal
from .models import SessionToken, User
from .security import hasher


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.reset_password email@example.com")
    password = getpass.getpass("New password (at least 10 characters): ")
    if len(password) < 10 or len(password) > 128 or password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords must match and contain 10–128 characters.")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == sys.argv[1].lower()))
        if not user:
            raise SystemExit("User not found.")
        user.password_hash = hasher.hash(password)
        db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
        db.commit()
    print("Password changed; all previous sessions revoked.")


if __name__ == "__main__":
    main()
