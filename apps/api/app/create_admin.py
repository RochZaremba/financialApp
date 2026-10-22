"""Provision an administrator only from the trusted deployment host."""

import argparse
import getpass

from pydantic import ValidationError
from sqlalchemy import delete, select

from .db import SessionLocal
from .models import SessionToken, User
from .schemas import Credentials
from .security import hasher


def main():
    parser = argparse.ArgumentParser(description="Utwórz konto administratora lub nadaj uprawnienia istniejącemu kontu.")
    parser.add_argument("email")
    parser.add_argument("--name", default="Administrator")
    args = parser.parse_args()
    try:
        # Reuse the application's normalization and validation without printing input.
        identity = Credentials(email=args.email, name=args.name, password="validation-only")
    except ValidationError:
        raise SystemExit("Podaj poprawny e-mail i imię (1–80 znaków).") from None
    if identity.email.endswith("@demo.local"):
        raise SystemExit("Konto demonstracyjne nie może być administratorem.")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == identity.email).with_for_update())
        if user and user.is_admin:
            print("Konto ma już uprawnienia administratora.")
            return
        if not user:
            password = getpass.getpass("Nowe hasło administratora (10–128 znaków): ")
            if not 10 <= len(password) <= 128 or password != getpass.getpass("Powtórz hasło: "):
                raise SystemExit("Hasła muszą być zgodne i zawierać 10–128 znaków.")
            user = User(email=identity.email, name=identity.name, password_hash=hasher.hash(password))
            db.add(user)
            db.flush()
        user.is_admin = True
        db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
        db.commit()
    print("Nadano uprawnienia administratora. Zaloguj się ponownie i otwórz /administrator.")


if __name__ == "__main__":
    main()
