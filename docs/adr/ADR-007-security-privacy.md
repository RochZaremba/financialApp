# ADR-007: Security and privacy model

Status: Accepted

## Context

The system stores personal financial data and receipt images.

## Decision

- Enforce authorization by household membership on the server for every household-scoped read/write.
- Keep receipt images private.
- Use signed or server-mediated receipt access.
- Validate uploads and reject unsafe/oversized files.
- Keep secrets out of source control.
- Avoid sensitive production logging.
- Use idempotent financial write operations where duplicate submissions could create double counting.
- Add basic audit metadata to important records.
- Test cross-household access denial.
- Provide a household data export/delete path when feasible in V1, required before broader release.

## Consequences

Security boundaries are implemented as domain and API rules, not merely hidden buttons in the UI.
