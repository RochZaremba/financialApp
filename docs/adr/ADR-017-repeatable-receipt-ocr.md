# ADR-017: Repeatable receipt OCR and safe provider diagnostics

Status: Accepted

## Decision

Every new upload and explicit reread records a `ReceiptOCRAttempt`: configured provider/model, elapsed time, complete/partial/failed outcome, safe diagnostic codes and a validated, household-scoped proposal. Original provider error messages, response bodies, API keys and images are not copied into diagnostics or logs. HTTP errors preserve the HTTP status and recognized Google status/reason enums; HTTP-200 failures distinguish blocked/empty/truncated generation and invalid structured data. Financial incompleteness and a mismatched item sum remain distinct from provider failure.

Members can reread the saved private image after failure, successful extraction or finalization. Rereading never overwrites receipt edits or creates a transaction. An unconfirmed receipt accepts a proposal only through an explicit apply operation, which replaces draft fields/items after a receipt revision check. Applying the same attempt twice is idempotent. Confirmed receipts support comparison only; the booked transaction, allocations, inventory links and budget remain unchanged.

Rereads require an idempotency key. PostgreSQL advisory locks deduplicate a repeated operation and reject concurrent distinct operations for the same receipt. Existing per-person/service OCR limits apply to uploads and rereads together; there is no implicit paid retry or silent provider switch. Draft editing can continue during extraction, and a changed saved revision makes applying the stale proposal fail safely.

Household receipt views expose the latest proposal and ten recent attempt summaries; older details remain available by authorized attempt ID. Export includes attempts, and receipt/household deletion removes their private content. An administrator sees only aggregate provider/model/outcome/code counts for the last seven days, capped at the most recent 10,000 attempts; no receipt, image, household or user details are included.

## Consequences

This extends ADR-004/008/016. It makes future failure rates diagnosable without pretending to reconstruct historical exceptions that were discarded by older versions. Live causes still require deployment evidence; mocked checks do not establish a live Gemini success rate. Migration 011 is additive and refuses to discard existing OCR history on downgrade.
