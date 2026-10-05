# ADR-008: Self-contained authentication and private local storage

Status: Accepted

Context: No hosted service credentials are available. The development product must run end-to-end without mocking authentication or persistence.

Decision: Use Argon2 password hashing and opaque, hashed, revocable 14-day sessions in PostgreSQL. Browser sessions use HttpOnly SameSite=Strict cookies, Secure under HTTPS in production. Enforce browser Origin/Sec-Fetch-Site on mutations. Household membership remains server-authorized. Supabase remains a possible later identity adapter; V1 does not need hosted authentication.

Receipt files live in a private persistent directory, never a public web path. A membership-authorized backend endpoint serves the sanitized image. Production deployments must persist, restrict and back up that volume along with PostgreSQL. This is the private backend-mediated storage option in ADR-007, suitable for a two-person modular monolith.

Money is consistently integer grosze in Python, TypeScript, and PostgreSQL BIGINT. A deferred PostgreSQL constraint trigger verifies final expense allocation totals. Pocket money is a terminal transaction addressed to a member, with no category allocations. Savings transactions are account transfers linked to a goal.

Receipt extraction defaults to an honest manual draft; optional OpenAI or Google Gemini structured vision extraction is validated with Pydantic through the same provider interface (Gemini added 2026-10-05). Fixture mode only recognizes the exact bundled image, and is refused in production. No arbitrary real photo is converted into invented fixture data.

Consequences: The household product works locally without third-party keys. Password recovery/email delivery is outside this private deployment; document owner-assisted recovery via a local CLI. Live AI extraction requires an API key. Production requires HTTPS, persistent volumes and a single API process for in-process abuse limits; distributed rate limits may replace this only if scaling becomes necessary.
