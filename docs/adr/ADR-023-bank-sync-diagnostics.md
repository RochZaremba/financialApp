# ADR-023: Safe bank synchronization failure diagnostics

Status: Accepted. Extends ADR-022.

Persist only the latest failed synchronization's stage, allowlisted exception category/code, optional HTTP status, UTC occurrence time and elapsed milliseconds on its existing household-scoped connection. Never retain exception messages, tracebacks, provider bodies, bank/account/session identifiers, amounts or credentials in diagnostics or logs. Unknown provider codes and custom exception class names map to fixed safe codes. Authorized status responses revalidate the metadata; normal UI copy stays conversational and technical details expand explicitly.

Keep the six-hour durable lease after an actual attempted fetch, including failure, manual requests and restarts. Unmapped accounts make no provider call and take no lease. Waiting, failure, missing mapping and success have distinct responses. A parsing/database failure rolls back the whole batch before recording diagnostics in a fresh transaction, guarded by the original lease and still-active connection. Success clears the previous failure. No consent reset, extra paid request, financial rewrite or guessed historical exception is introduced.

Migration 016 adds one nullable JSON column, preserves existing connections/secrets and permits the previous image. Existing generic errors remain without retrospective details. Downgrade refuses to discard populated diagnostics. Synthetic regression and responsive browser evidence do not establish the cause of an earlier live exception that was not retained.
