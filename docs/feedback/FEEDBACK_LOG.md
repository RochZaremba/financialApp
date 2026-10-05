# Feedback Log

Use this file as the durable user-feedback side of the Loop-Back Loop.

Template:

## YYYY-MM-DD - short title

User feedback:
- 

Interpretation:
- 

Affected areas:
- 

Acceptance criteria changes:
- 

Implementation:
- 

Verification:
- tests:
- screenshots:
- regression result:

Status: Open / Implemented / Verified

## 2026-10-05 — Pełny działający produkt

User feedback: Samodzielnie wdrożyć pełne MVP, uruchomić, sprawdzić wszystkie ekrany i powtarzać regresję aż do dwóch czystych pętli. Dane demo dla Rocha i Kai. Mock wyłącznie dla zewnętrznej usługi wymagającej klucza.

Interpretation: implement real persistence and household authorization, every primary flow, honest receipt fallback, polished Polish mobile/desktop experience.

Affected areas: all screens and domain rules.

Acceptance criteria: `docs/quality/ACCEPTANCE.md`.

Implementation: complete persisted MVP with real authentication, household/month budgets, pocket money, split transactions, private receipt items and review/learning, savings goals, recurring expenses, history, analytics and responsive Polish PWA. Fixture mode recognizes only the bundled receipt; unknown images remain editable manual drafts. A validated live OCR adapter is available when configured with an API key.

Verification: two consecutive clean final loops; each has lint/typecheck/production build, 6 Vitest + 28 pytest and 9 Chromium/WebKit E2E passes, plus 52 primary screen/viewport checks without page errors, accessibility violations or overflow. Additional 30 empty/error state checks, migration round trip, README setup reproduction, production Docker smoke and actual WebKit offline-origin test. Screenshot paths and individual repairs are recorded in `docs/quality/LOOP_LOG.md`.

Status: Verified. No known open P0/P1/P2. Live real-photo OCR awaits external credentials; fixture/manual behavior and provider contract/error handling are verified.

## 2026-10-05 — Google Gemini jako dostawca AI

User feedback: „dodaj możliwość kożystania z innych ai jak google z gemini”.

Interpretation: add a real Google Gemini adapter for receipt extraction and item classification, selectable through the existing server configuration alongside OpenAI. Keep credentials private and preserve manual recovery, validation and household learning.

Affected areas: receipt provider, configuration, deployment environment, upload notice and documentation.

Acceptance criteria: `RECEIPT_PROVIDER=gemini`, `GEMINI_API_KEY` and a configurable `GEMINI_MODEL` work locally and in production Compose. Send sanitized images and household categories to the official API, validate strict integer-grosze output, reject blocked/truncated/invalid responses, retain photos and unresolved tasks on failures, and show an accurate upload notice. Existing receipt and budget flows pass two clean regressions. Never claim a live Gemini call without credentials.

Implementation: real Gemini adapter and independent key/model configuration; production Compose forwards those settings. Shared extraction prompt/schema and domain pipeline preserve money/rules/review behavior. A server-derived capability flag fixes the upload notice for either AI provider, including missing keys. `.env` received only missing Gemini entries; existing settings were preserved.

Verification: two clean loops, each 6 Vitest + 40 pytest + 12 Chromium/WebKit E2E passes; 8 Gemini availability screenshots plus 52 primary screen regressions per loop at all required viewports, zero page errors/axe violations/overflow. Production images build and actual Gemini-without-key upload preserves a private photo and extraction task with no financial transaction. Evidence: `docs/quality/LOOP_LOG.md`.

Status: Verified. Live Gemini extraction was not called because no key is configured; adapter/HTTP contract and full persistence/recovery behavior are covered by tests.

## 2026-10-05 — Niezależny review przed release

User feedback: potraktować istniejący produkt adversarialnie; realnie przejść wszystkie ekrany, finanse, OCR, błędy i autoryzację; naprawić P0/P1/P2, wykonać dwa pełne czyste przebiegi i doprecyzować README.

Interpretation: previous green checks are a baseline, not evidence against new defects. Reproduce issues with isolated QA households and real browsers, then repair domain and interface behavior together.

Affected areas: every primary screen and flow, private receipt recovery, amounts, duplicate writes, authentication, startup and deployment.

Acceptance criteria: incomplete OCR must retain explicitly entered corrections without inventing a date or amount; changing payout recipients must offer the correct outstanding amount; negative account balances must remain exact; an empty zero-income plan must not claim completion; retrying one upload must not create extra receipts. Cross-household access and concurrent financial writes remain protected. Two consecutive complete browser/static/backend/visual regressions after the last repair, with evidence in LOOP_LOG.

Implementation: repaired incomplete OCR drafts and optional quantities, signed receipt discounts, duplicate uploads/finalizations and duplicate warnings after correction; corrected pocket-money amounts, negative balances and oversubscribed-plan feedback. Hardened household authorization, password handling, request/image limits and private-file recovery. Fixed offline/loading recovery, unpaid-pocket contrast, tablet amount wrapping, Safari scrolling/click interception and local process shutdown. The live Gemini contract now uses the supported JSON MIME enum and structural schema with full server validation; the proven configured model is `gemini-3.1-flash-lite`.

Verification: two consecutive complete final loops after the last source/configuration change, each with lint/typecheck/production build, 7 frontend tests, 63 API tests, 18 Chromium/WebKit E2E tests, 52 primary-screen checks, 32 state checks and 9 independent probes. No page exceptions, accessibility violations, horizontal overflow or split monetary labels in those checks. Additional verification covers fresh README setup/dev/stop/build/start, fresh migration upgrade/downgrade safety, 28 real HTTPS production screen checks, actual WebKit origin outages and 13 screens at equivalent 200% desktop zoom with keyboard navigation. Two real Gemini calls completed synthetic-receipt extraction, balanced category split, confirmation and budget update; the second used the saved `.env` without overrides. Original Roch/Kaja demo data was preserved. Logs and screenshot paths are recorded in `docs/quality/LOOP_LOG.md`.

Status: Verified — zero known open P0/P1/P2 in the reviewed V1 flows; two consecutive clean final passes. Earlier preparatory failures and no-key results above remain historical evidence, not the current release verdict.

## 2026-10-05 — Production build for Oracle

User feedback: przygotować build bez wersji demo do wdrożenia na `finance.rochzaremba.com`, serwer dostępny jako `ssh oracle`.

Interpretation: produce and verify a native ARM64 release with a fresh production database, disabled demo authentication and no bundled demo images/seed. Stage an independently deployable release and exact activation instructions; preparation must preserve existing server sites and local demo data.

Affected areas: Docker packaging, environment isolation, Oracle Compose/Caddy integration, deployment documentation.

Acceptance criteria: API/web ARM64 images build; production `/config` disables demo and `/auth/demo` refuses access; public demo receipt and seed are absent; two complete production browser flows pass on isolated fresh databases; no secrets in image/build archive; web binds only loopback and integrates with existing host Caddy without taking ports 80/443; staged release includes an activation command and backup instructions.

Implementation: production Docker images exclude the API seed and bundled demo receipt. Secret environment files are excluded from Docker contexts and source archives. Added native ARM64 Oracle Compose with loopback-only web on 8810, an existing-host-Caddy site and a backed-up/validated activation script. Staged release `20261005T133723Z` in `~/finance/releases/` on Oracle, using fresh production database credentials and the existing Gemini configuration; public activation is left as the requested deployment step.

Verification: native API/web build passed on Oracle; image inspection confirmed ARM64 and absence of demo assets/seed. Real production `/config` returned `demo_enabled: false`, and demo login returned 404. Two successive isolated production HTTPS browser loops each completed authentication/invitation, budgeting, pocket money, expenses, receipt drafts/discounts/duplicates, goals, recurring payments, export/deletion and 28 mobile/desktop visual checks without page errors, axe violations or overflow. Fresh second database had zero users. Local lint/typecheck, 7 frontend and 63 API tests passed. Existing-plus-finance Caddy configuration validated without loading it into the running service. Ready-image archive checksums matched both locally and remotely. QA containers/volumes were removed; existing server websites and local data were preserved.

Status: Verified — deployable ARM64 release staged; activation instructions in `deploy/ORACLE.md`. Evidence: `artifacts/oracle/` and `docs/quality/LOOP_LOG.md`.

## 2026-10-05 — GitHub publication and merge-only CI/CD

User feedback: opublikować projekt w `RochZaremba/financialApp`, dopracować README/opis/ignorowane pliki; CI sprawdza testy, a tylko merge do main wdraża działającą aplikację na Oracle i publikuje GitHub Release. Użytkownik potwierdził wykonanie początkowej aktywacji produkcji.

Interpretation: PR checks have no production credentials; direct pushes run verification only. A merged PR targeting main triggers fresh checks, native ARM64 release packaging, private Oracle update with preserved database/receipts/environment, then publication of the exact successful deployed commit. GitHub metadata and documentation must be usable by a new contributor.

Affected areas: repository history/publication, GitHub workflows/settings, release packaging, restricted SSH deployment, production backups/current-release tracking, README and contribution/security documentation.

Acceptance criteria: never publish private spreadsheets/env/keys/data, including earlier unpublished Git history; keep local private files. PR and merge CI run the full existing quality suite. Release assets contain no secrets. Deploy keeps the existing finance project/volumes/passwords, backs up before migrations, health-checks and restores previous images on failure without automatic schema downgrade. Dedicated deploy key is restricted to the deploy command; forks cannot receive it. GitHub Releases are created only after a successful merged-main deployment. Verify actual hosted CI and a real merge/deploy/release plus server-data preservation.

Status: In progress.
