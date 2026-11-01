"""One-time private activation. No credentials in arguments, logs, images or git."""

import argparse
import base64
import json
import os
import sys
from uuid import UUID

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from sqlalchemy import select

from .bank_provider import config_path
from .db import SessionLocal
from .models import Household, Member, User


def write_config(household_id, app_id, owner, users, raw):
    path = config_path()
    if path.exists():
        raise ValueError("Configuration already bound")
    private = serialization.load_pem_private_key(raw, password=None)
    if not isinstance(private, rsa.RSAPrivateKey) or private.key_size < 2048 or len(raw) > 16384:
        raise ValueError("Invalid RSA key")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    files = [path.parent / name for name in ("provider.pem", "encryption.key", "push.pem")]
    if any(file.exists() for file in files):
        raise ValueError("Existing secret files")
    key = ec.generate_private_key(ec.SECP256R1())
    values = [
        raw,
        Fernet.generate_key(),
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
    ]
    created = []
    try:
        for file, content in zip(files, values, strict=True):
            fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write(content)
            created.append(file)
        public = (
            base64.urlsafe_b64encode(
                key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
            )
            .decode()
            .rstrip("=")
        )
        cfg = dict(
            household_id=household_id,
            owner_id=owner.id,
            allowed_users=users,
            app_id=app_id,
            private_key_path=str(files[0]),
            encryption_key_path=str(files[1]),
            vapid_key_path=str(files[2]),
            vapid_public_key=public,
            contact_email=owner.email,
        )
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(cfg, output)
    except Exception:
        for file in created:
            file.unlink(missing_ok=True)
        raise


def eligible(db, household_id, owner_email):
    rows = db.execute(select(Member, User).join(User, Member.user_id == User.id).where(Member.household_id == household_id)).all()
    owners = [(m, u) for m, u in rows if m.role == "owner" and u.email == owner_email.strip().lower()]
    if not db.get(Household, household_id) or len(rows) != 2 or len(owners) != 1:
        raise ValueError("Household must have exactly two members and the specified owner")
    return owners[0][1], [u.id for _, u in rows]


def main():
    parser = argparse.ArgumentParser(description="Aktywuj prywatny bank dla domu z dwiema osobami.")
    parser.add_argument("--household-id", required=True)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--key-stdin", action="store_true", required=True)
    args = parser.parse_args()
    try:
        UUID(args.app_id)
        UUID(args.household_id)
        with SessionLocal() as db:
            owner, users = eligible(db, args.household_id, args.owner_email)
        write_config(args.household_id, args.app_id, owner, users, sys.stdin.buffer.read(16385))
    except Exception:
        raise SystemExit(
            "Aktywacja nie powiodła się. Sprawdź identyfikatory, dwóch członków domu i klucz RSA. Istniejących kluczy nie nadpisujemy."
        ) from None
    print("Aktywowano dostęp tylko dla wskazanego domu i jego dwóch obecnych użytkowników.")
    print("Klucze pozostają w prywatnym wolumenie. Produkcyjne API automatycznie uruchamia synchronizację w tle.")


if __name__ == "__main__":
    main()
