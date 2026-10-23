#!/usr/bin/env python3
"""Issue one reviewed account-specific grant; never print the bearer token."""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))
from app.recovery import Grant, message  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    parser.add_argument("--token-file", type=Path, required=True, help="Private file outside the repository, created with mode 0600")
    parser.add_argument("--hours", type=int, default=24, choices=range(1, 25))
    args = parser.parse_args()
    destination = args.token_file.resolve()
    if destination.is_relative_to(ROOT):
        parser.error("The token must be saved outside the repository")
    email = args.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254 or email.endswith("@demo.local"):
        parser.error("Use an exact ordinary account email")
    private = Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    grant = Grant(
        id=uuid4().hex,
        target_email_sha256=hashlib.sha256(email.encode()).hexdigest(),
        public_key=base64.urlsafe_b64encode(private.public_key().public_bytes_raw()).decode().rstrip("="),
        valid_from=now,
        expires_at=now + timedelta(hours=args.hours),
    )
    token = grant.id + "." + base64.urlsafe_b64encode(private.sign(message(grant))).decode().rstrip("=")
    # Exclusive creation prevents accidental replacement of an existing secret.
    with os.fdopen(os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
        output.write(token + "\n")
    # Only public metadata is printed, for protected PR review and deployment.
    print(json.dumps(grant.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
