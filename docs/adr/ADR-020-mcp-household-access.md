# ADR-020: Household access through MCP

Status: Accepted

The user wants AI clients to read and write application data, including meter readings.

Use the official Python MCP SDK, stateless Streamable HTTP at `/api/mcp` through the existing web proxy. A named connection is bound to its creator and one household. Keys are random, displayed once, stored only as SHA-256 hashes, expire within 90 days and can be revoked immediately. Creation requires the user's existing password. Membership is rechecked on every call; administrator or trusted-host password reset invalidates connections too.

Connections choose read or read/write access. MCP exposes the existing household API contract, including budgets, transactions, receipts, schedules, goals, shopping, activity, meters and export/deletion. Authentication, administration, invitation creation and connection management are excluded. No arbitrary URLs, SQL, filesystem paths or shell commands are tools. Household identity is fixed by the connection, never supplied by the model. Existing domain authorization, validation, revision checks, idempotency keys and paid AI limits remain authoritative.

Deletion tools require an explicit `confirm_delete: true`; household deletion also requires its exact name. Tool hints and instructions ask for user confirmation before financial/destructive changes; they are guidance, not an independent approval service. A read/write key intentionally grants data mutation capability. Audits record connection, tool, actor and HTTP result, without argument bodies, photos or credentials.

JPEG/PNG/WebP uploads use bounded base64 input, then the same sanitization/private storage as the UI. OCR proposes data and does not implicitly save/finalize it. Meter values are integer thousandths; money remains integer minor currency units.

This first transport uses Bearer keys for clients such as Codex. It does not advertise OAuth metadata or claim compatibility with hosted clients that require OAuth (including the ChatGPT custom-app login flow). OAuth authorization/consent can be added separately after the target client is known. No universal password, account recovery shortcut or new public database access is introduced.

The migration is additive and compatible with the previous images. Deployment remains the existing reviewed PR/release pipeline.
