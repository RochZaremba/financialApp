# ADR-018: Entry authorship and household activity

Status: Accepted

## Decision

Expose the existing authenticated `created_by` metadata as a readable author name on receipt details and transaction history. Clients cannot submit creator identity. Subsequent edits, categorization, OCR and idempotent retries retain the original author. A receipt is authored by its uploader; its resulting expense is authored by the member who confirms it. These can be different people.

A read-only household-authorized Activity screen groups saved receipt counts (including drafts), expense/income counts and integer-grosze expense/income sums by original recorder. Receipt amounts are never added to expense totals. Transfers, savings and pocket-money movements do not contribute to expense/income activity counts. Attribution is documentary activity, not a statement about who paid, earned or contributed financially.

Monthly filters use `created_at` with half-open Europe/Warsaw month boundaries, including daylight-saving changes, independently of transaction/receipt purchase dates. An all-time option uses all preserved records. Removed drafts no longer count. Current members with no entries remain visible. Historical authors remain visible after leaving the household. Missing/deleted legacy authors are explicitly unknown and are never guessed or backfilled.

Names are joined only through authorized household records; responses contain no email addresses. Aggregate reads stay in SQL and author lookups on list responses are batched. The feature reuses durable record metadata and needs no schema migration or financial calculation changes.

## Consequences

Statistics describe data entry and can change when an entry is corrected or a draft is removed. They do not replace the audit log or immutable financial records. Members cannot query another household's activity. No global administrator privilege is involved.
