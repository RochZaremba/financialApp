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

Implementation: published a clean public root history without the private spreadsheet or prior private ancestors; retained local private files. Added product README with synthetic mobile/desktop previews, operation/contribution/security documentation, ignore rules, pinned workflows and dependency/issue/PR templates. Configured repository metadata, protected main and the main-only production environment. Full credential-free CI runs tests/build/migrations/browser reviews. Merged-main delivery verifies fresh native ARM64 images over HTTPS, streams a checksummed secret-free artifact through a dedicated restricted SSH key, preserves private env/volumes, backs up before migration, checks production and publishes the exact successful commit. Actual failed deliveries exposed and repaired the receipt-volume mount and Cloudflare health-probe identification; slow runner browser installation was replaced by official Playwright containers.

Verification: hosted fixed PR CI 37338101231 passed 7 frontend, 63 API, 17 deployment and 18 Chromium/WebKit E2E tests, plus 52 primary-screen, 32 state and 9 probe checks. Added public-health regression brings deployment coverage to 19 tests. Real merged-main workflow [37339000416](https://github.com/RochZaremba/financialApp/actions/runs/37339000416) passed native empty/populated receipt backups and 28 HTTPS production visual checks, then successfully deployed and published [v0.1.2](https://github.com/RochZaremba/financialApp/releases/tag/v0.1.2) for merge commit bf78ce1d42afa3f4d78acc6cfa7126c96bd93315 after repairing the receiver. Failed attempts restored production and did not publish. Actual server verification confirmed original record identities, named volumes, private configuration and exact deployed revision. Final documentation/health-regression PR must pass the same protected CI and release pipeline again; its resulting evidence is attached to its Actions run and Release.

Status: Verified — real hosted CI, deployment and release publication work; final merge repeats the delivery regression before the milestone is closed.

Follow-up verification: final health/documentation PR #10 passed 19 deployment tests and all existing product gates. [37342261637](https://github.com/RochZaremba/financialApp/actions/runs/37342261637) successfully built, tested, backed up, deployed and published [v0.1.3](https://github.com/RochZaremba/financialApp/releases/tag/v0.1.3), preserving identities, volumes and private configuration. Final review also corrected the three remaining QA browser clocks to match October fixtures, preventing future calendar changes from causing false CI failures. A real browser showed the future-month payout mismatch and correct 250,00 PLN after restoring the QA date. That QA-only fix passes through another protected PR and full release regression before closure; application date behavior is unchanged.

## 2026-10-05 — Nazwane źródła planowanego dochodu

User feedback: zastąpić pojedynczy planowany dochód możliwością dodawania wielu źródeł, nadawania nazw i wskazywania domownika, który dostarcza dochód.

Interpretation: each budget month has its own named planned income sources, optionally shared, with exact integer-grosze amounts. Their server-calculated sum funds the shared budget. Planning does not book actual account income.

Affected areas: monthly planning/read screen, income-source persistence/migration, household authorization, demo seed, export/deletion, browser flows and documentation.

Acceptance criteria: add/edit/remove multiple named sources and assign current household members; show sum and unassigned money immediately; persist after reload and isolate months/households. Preserve existing totals as a shared source without guessing the contributor. Reject foreign members, duplicate name/person pairs and invalid or excessive amounts atomically. Preserve legacy API totals and old plans during deployment/rollback. Test exact grosze, migration, authorization and primary mobile/desktop flows; complete two clean review loops.

Implementation: persisted monthly source records with named contributors and server-derived integer totals; legacy totals migrate as shared income. Added responsive add/edit/remove controls, source summaries, demo salary sources, export/deletion handling, exact-money/authorization/migration tests and browser flows. Save errors stay visible next to the primary action.

Verification: lint/typecheck/build, 7 frontend, 19 deployment and 67 API tests passed. Two successive complete source flows passed in Chromium desktop/mobile and WebKit, including 30 screenshots across all four widths, accessibility/overflow/alert-occlusion checks, person assignment, reload, corrections, deletion, errors and month isolation. The normal app starts with migration 005 and preserves all existing period amounts. See LOOP_LOG and PR #12 checks for full protected regressions and production delivery.

Status: Verified locally — two consecutive clean changed-flow loops; protected CI verifies the final published commit.

## 2026-10-08 — Salda kont w walutach

Feedback: „mogę dodać konto w euro i potem będzie się automatycznie przeliczało obecnym kursem na zł do RAZEM NA WASZYCH KONTACH”.
Interpretation: accounts retain native-currency balances; the server values the combined balance in PLN using the latest published NBP average rate, with visible rate date and honest unavailable/stale states. This is account valuation; household transactions and budgeting stay PLN.
Affected: account creation/cards/total, account persistence, overview, transaction account choices and server validation.
Acceptance: PLN default preserves existing accounts; support EUR/USD/GBP/CHF in integer minor units; exact server rounding; automatic cached NBP refresh; show native and PLN amounts/date; never silently omit an unpriced account from total; protect PLN transactions from foreign accounts; authorization/idempotency and migration tests; two clean responsive browser loops.
Status: implementation in progress.

Implementation/verification (account currency feedback): added currency selection, native balances, server-calculated PLN valuations and totals with NBP rate/date, automatic refresh and honest unavailable/cached states. Added migration 006 and currency-preserving export metadata. Kept PLN transactions safe through filtered choices and server validation. Full gate passed (7 frontend, 77 API, 20 deployment, 14 desktop/mobile E2E tests). Fixed a mobile rate-paragraph layout defect found by direct screenshot review; two subsequent clean four-viewport loops and 52 unmocked screen checks passed. Evidence: `artifacts/currency-final-check.log`, `artifacts/currency-clean-loops.log`, `artifacts/ui-review/currency/`, `artifacts/ui-review/currency-final/`, and LOOP_LOG. Status: verified locally; production delivery follows the existing merge-only workflow.
# 2026-10-08 — Rozszerzenia codziennego planowania

Feedback: dodać edycję transakcji, kopiowanie planu miesiąca, przenoszenie sald kopert albo procentowy podział nadwyżek na konta/oszczędności/cele, przypomnienia i różne cykle płatności, dokładniejsze wyszukiwanie oraz propozycję przydziałów budżetu z AI. Pracować na osobnych branchach i scalać przez PR-y.

Interpretation: six independently reviewable feature branches/PRs. Financial writes remain household-authorized, exact and idempotent. Copying or carrying a plan does not invent income or move account money. Surplus transfers require an explicit preview, exact percentages and confirmed account movement; the same leftover cannot be used twice. AI proposes editable allocations across active categories, with pocket/goal commitments preserved; it never saves automatically. Recurring expectations support non-monthly cycles and reminders without booking unpaid expenses.

Affected: Transactions, Budget, Home, Accounts/Goals, recurring expenses, household-scoped APIs, providers, migrations, PWA and QA.

Acceptance: see the 2026-10-08 extension criteria in docs/quality/ACCEPTANCE.md. Each PR must pass targeted financial/authorization/concurrency tests, regression gates and two consecutive clean browser/visual loops at all four required viewports before merge. Production delivery follows the existing merge-only workflow.

Implementation: transaction editing (#16), reviewed month copying (#17), advanced filters/product search (#18), weekly/monthly/quarterly/annual schedules with in-app reminders and calendar export (#19), reviewed all-category AI/history proposals (#20), and carry/proportional surplus settlement (#21). Separate branches and protected PR merges are used for every feature.

Rules: settlement explicitly closes the source month, requires real funding and paid/corrected scheduled payments; distribution records confirmed performed transfers. Calendar export is an importable schedule, not background push. AI receives bounded category aggregates/preferences, validates exact grosze and preserves pocket/goal commitments; only explicit application changes the draft and normal save writes it. Incoming carry is credited before funding scheduled expenses. Active schedule changes cannot strand unpaid occurrences in a closed month.

Verification: implementation defects and independent clean-loop evidence are recorded per feature in LOOP_LOG.md. Final integrated local verification passes 118 API tests, 7 frontend tests, lint/typecheck/build, and the proposal error/retry/review/stale-draft/application/save flow in Chromium desktop/mobile and WebKit with four-viewport accessibility/overflow checks. Each PR requires its independent complete protected gate before merge; Actions and Release evidence record the final second loop and production delivery through the existing merge-only workflow.

# 2026-10-08 — Połączenie z bankiem: rozpoznanie możliwości

Feedback: automatycznie pobierać wpływy i wydatki z banku, wiązać operacje z paragonami oraz zlecać prawdziwe przelewy (czynsz, oszczędności) z aplikacji; pytanie o sposób podłączenia.

Interpretation: account-information access (AIS), receipt reconciliation and payment initiation (PIS) are separate capabilities. The existing “Zrób przelew” records an internal account movement and does not send a payment order to a bank. This request is integration discovery, not an implemented banking connection.

Affected: Accounts, Transactions, receipt finalization/review, income, savings/goals, provider boundary and future payment-order state. ADR-003/005 already allow bank feeds and receipt matching; live payments need an additional architecture decision before implementation.

Proposed acceptance criteria for implementation: bank-supported consent flow with server-held credentials and renewable/revocable access; bounded background synchronization with honest last-sync/error states; idempotent import and pending/booked reconciliation; match existing manual/receipt movements without double-counting, use account/amount/currency/date/merchant signals and send ambiguous matches to Review Inbox; distinguish household transfers and pocket payouts from income/expense; retain item-level allocations and exact grosze. Payment initiation requires confirmed provider/bank eligibility, explicit recipient/account/amount/title review, bank authorization, idempotent orders, provider-verified status and reconciliation with imported operations. A bank callback alone must not mark an expense as paid. Verify authorization, financial invariants and two clean browser/visual loops for implemented slices.

Discovery evidence: inspected `apps/web/src/components/future-screens.tsx`, `receipt-screens.tsx`, `apps/api/app/domain.py`, `models.py` and receipt finalization in `main.py`. Checked Enable Banking API/control-panel/FAQ documentation: restricted production access is for linked-account testing; production PIS currently requires a company holding a PISP license. Bank, account type, intended audience and provider commercial terms remain to be established. Sources: https://enablebanking.com/docs/api/control-panel/ ; https://enablebanking.com/docs/faq/ ; https://enablebanking.com/docs/api/reference/ .

Status: discovery recorded; no application code or live bank connection changed. No implementation quality gates or visual-loop completion claimed.

User clarification: mBank and Santander plus other accounts; currently for Roch and Kaja, potentially other users later. Begin provider eligibility checks with those banks and private linked-account testing; broader access and live PIS remain separate commercial/regulatory integration decisions. Confirm the exact Santander institution and each savings account's API capabilities before promising coverage.

Further source verification: https://auth.enablebanking.com/guides/PL/ lists mBank and Santander Bank Polska. The linked-accounts documentation explicitly permits individual non-commercial use as well as evaluation; restricted mode is therefore not described as testing only. Verify terms for Kaja's separately owned accounts and any fees before selecting it for the household. https://enablebanking.com/docs/api/linked-accounts/ explains production registration, “Activate by linking accounts”, linked-account restrictions and the separate API authorization required afterward.
