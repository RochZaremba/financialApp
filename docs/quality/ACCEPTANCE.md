# Acceptance criteria and implementation slices

Read all repository documentation on 2026-10-05. The initial repository contains instructions only.

1. Identity: real password authentication, revocable HttpOnly sessions, household creation, expiring invitation and second-member join; membership enforced in every scoped API route.
2. Budget: immutable per-month category-name snapshots, integer grosze, planned income and category/pocket/goal allocations, clear zero-unassigned feedback, previous/next month, new month setup.
3. Movement: idempotent manual income, expense splits, member pocket payout, account transfers; balanced category allocations, correct account balances and household totals.
4. Receipt: private validated image upload, real provider interface, honest manual draft without credentials, bundled image fixture explicitly identified, strict extraction schemas, household rule precedence, editable items/confidence, atomic idempotent finalization, unresolved-only Inbox. Every unconfirmed receipt remains discoverable after leaving/reloading the editor, including fully confident extraction.
5. Future: goals and actual contributions, recurring expected expenses with idempotent generation, compact analytics with observed-data caveats, accounts, export/delete, session expiry/offline/error states.
6. Consumer UX: restrained Polish interface, accessible forms, desktop sidebar/mobile bottom navigation, clear primary action, all screens at 390×844, 430×932, 768×1024, 1440×900.

Evidence: automated outputs and screenshots under ignored `artifacts/`; durable review findings in `docs/quality/LOOP_LOG.md`. Run two consecutive clean end-to-end/visual loops after fixes. Do not claim provider extraction against real photos without credentials.

Gemini extension (2026-10-05): select Google Gemini through environment configuration, independently configure key/model, validate output through the same Extraction schema, reject incomplete/blocked responses and preserve manual recovery. Upload copy reflects AI availability for either supported provider. Secrets stay server-side; household rules and financial invariants apply identically.

Independent release review (2026-10-05): exercise all screens and failure states in real browsers using isolated households; verify partial receipt drafts, explicit unknown dates, recipient-dependent payout suggestions, signed account balances, honest empty-budget feedback, upload retries, exact arithmetic and authorization. Repair reproduced defects and perform two consecutive full clean loops after final changes. Document exact tested startup commands and external-service limits.

Duplicate-review criterion: taking a different photo of a confirmed receipt must still trigger suspicion when merchant, date and total match. Confirmation requires an explicit separate-purchase acknowledgment; legitimate matching purchases remain possible. This also applies after manual OCR correction and simultaneous confirmations, with household isolation preserved.

Receipt quantities are informational and optional, as specified in AGENTS.md. A readable priced item without a legible quantity must remain usable without inventing one; its total and category still require exact validation.

Monthly trend must show full amounts without breaking the number between digits, including at tablet/mobile widths and equivalent 200% zoom. Horizontal rows may replace vertical bars to preserve exact grosze without cramped labels.

After correcting receipt headers and saving the draft, duplicate UI must reflect the recomputed server suspicion, retaining real matches and clearing disproved ones. Acknowledgment must not carry over from a previous saved revision.

Receipt controls must activate reliably while the browser scrolls/focuses fields. Focused and programmatically revealed controls must stay clear of the fixed mobile navigation; category selection must be visibly committed before draft save.

Oracle release preparation: native ARM64 images, no seed or public demo receipt in production containers, no demo login/configuration, isolated fresh-database production browser checks twice. Preserve existing host Caddy/sites, use loopback web port 8810 and stage release without enabling the public domain. Secrets remain private environment files excluded from build archives and Docker contexts.

GitHub CI/CD: public main history excludes personal spreadsheets and secrets; PR verification is read-only and credential-free. Only a merged PR to main invokes release: repeat full quality gates, build and package native ARM64 images, verify the production artifact, deploy over a dedicated restricted SSH credential with backups and existing volumes/environment, check origin/public health, then publish GitHub Release for the exact merged commit. Direct push and closing an unmerged PR cannot deploy or release. Failures cannot publish a successful release or auto-downgrade the database. Exercise actual hosted checks and a merged-main release before declaring complete.

CI browser reviews use the same fixed Europe/Warsaw QA date as the receipt/budget fixtures, rather than the runner's current month. A future calendar date must not turn the fixture payout or over-allocation checks into false failures.

Named monthly income sources: the plan accepts multiple names, exact amounts and household contributors (or a shared source). The server derives the total; planning never creates an actual income transaction. Existing totals migrate without change, months stay independent, cross-household member references are rejected, identical name/person pairs cannot be repeated, edits/deletions persist, and household export/deletion includes sources. Verify reload, 390/430/768/1440 layouts, empty/error states and two clean regressions.

## Account currency valuation (2026-10-08)
- Add PLN/EUR/USD/GBP/CHF accounts with native integer-minor-unit balances.
- Account cards show native currency and PLN valuation; total is server-calculated using latest NBP table A, with publication date.
- Rate failures show last known rate explicitly or an unavailable full total, never an apparently complete partial total.
- Existing accounts and all budget transactions remain PLN; foreign accounts cannot be used in PLN financial writes.
- Verify exact positive/negative rounding, invalid currencies/provider data, authorization/idempotency, fresh migration and two responsive UI loops.
