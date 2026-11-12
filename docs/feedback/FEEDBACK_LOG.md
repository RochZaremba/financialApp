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


# 2026-10-08 — Wspólne zakupy, zapasy i czytelna nawigacja

Feedback: dodać planowanie zakupów w gospodarstwie, historię zakupów i aktualną lodówkę; poprawić nieczytelny i mało funkcjonalny panel nawigacji ze screena. Pracować przez branch/PR i feedback loop.

Interpretation: shared persistent shopping list with quantities, estimated costs and category; explicit purchase confirmation feeds purchase history and optional home inventory. Inventory supports fridge/freezer/pantry/household cupboard, exact quantities, expiry dates, consumption and minimum-stock reminders. Low-stock and previously purchased products can be added to the list. Confirmed receipt items may be explicitly reviewed and imported to inventory/history once; no invented OCR quantities and no duplicate financial expense. Buying on the list is an inventory operation; expense/receipt entry stays explicit.

Affected: new Zakupy screen (Lista, Zapasy, Historia), household authorization/persistence/export/deletion, confirmed receipt integration, desktop sidebar and mobile More/navigation.

Acceptance: criteria below are added before implementation in ACCEPTANCE.md. Complete shared two-member persistence, editing/removal, exact quantity/money totals, atomic retry-safe purchase/import, foreign-household denial, clear empty/loading/error states, grouped scrollable sidebar with useful household/profile actions, four responsive viewports and two consecutive clean actual browser/visual loops. Branch `feat/household-shopping-navigation`, protected PR merge and existing merge-only delivery.

Status: implementation in progress; no completed verification claimed.

Implementation/verification (shopping/navigation): persistent shared list with quantity/category/estimate, atomic purchase history and optional stock, fridge/freezer/pantry/cupboard batches, consumption, expiry/minimum reminders and refill suggestions, paginated history with repeat, explicitly reviewed receipt import optionally completing a current list item. Sidebar now groups finances and household planning, removes the decorative filler and has actionable settings/member/logout controls; mobile More and the Add shortcut expose the feature. Shopping does not silently book an expense. Added migration 009, export/deletion and household-only authorization.

Fixed actual loop defects: delayed prior command closing a newer editor (P1), clipped mobile location filter (P2), and history link alignment. Two subsequent clean loops each pass 9/9 Chromium desktop/mobile and WebKit scenarios with 96 screenshots and WCAG/overflow checks at the four required viewports. Full local regression: 131 API, 9 frontend and 20 deployment tests plus lint/typecheck/format/build. Evidence and visual findings: LOOP_LOG.md and `artifacts/shopping/`. Status: feature verified locally; protected PR #22 and existing merge-only delivery provide the hosted CI/release proof.

# 2026-10-22 — Konto administratora i odzyskiwanie hasła

Feedback: „Dodaj konto administratora gdzie można zresetować zapomniane hasło”.

Interpretation: add an explicitly provisioned application administrator and a responsive password-recovery panel. The administrator identifies an ordinary account by email, reauthenticates, and sets a new password. This is administrator-assisted recovery, without a public email-reset service.

Affected: authentication, account model/migrations, global administrator authorization, recovery audit, login help, desktop/mobile navigation and operator documentation. ADR-016 extends ADR-008.

Acceptance: no public/demo privilege escalation; role granted only from trusted server; panel works without a household; reset requires administrator session and password, respects CSRF and rate limits, validates and confirms the new password, preserves password whitespace, revokes every target session and records actor/target/time without credentials; users can sign in with the new password and cannot use the old one; ordinary accounts cannot reset passwords; clear error/success states; four viewport checks and existing regression gates. The destination email for provisioning is requested separately; no default administrator credentials are introduced.

Status: implemented and validated locally. Administrator recovery passed two final browser loops with four viewport/accessibility checks; 8 focused administrator API tests, frontend/static/build gates and desktop/mobile authentication regression passed. Full-suite shopping regression has a diagnosed existing expired-date fixture failure (see LOOP_LOG.md). The actual administrator email is still needed for account provisioning; production was not deployed.
# 2026-10-22 — Ponowny OCR i diagnostyka Gemini

Feedback: ponawiać OCR zapisanego zdjęcia po nieudanym i udanym odczycie; rozróżniać błędy Gemini, pokazać kody i wyjaśnić częste niepowodzenia.

Acceptance: authorized household members can explicitly rerun OCR on the stored image without a second upload or duplicate transaction; each paid operation is idempotent and rate-limited. A failed attempt preserves existing draft edits. Successful results are shown as a proposal and applied explicitly to an unconfirmed draft with concurrency protection; confirmed receipts allow diagnostic rereading without changing booked transactions. Store safe provider/model/status/error-code/duration metadata, distinguish timeout, quota, authorization, unavailable model/service, blocked/incomplete/invalid output and incomplete financial data, and never expose raw provider payloads, API keys or receipt text in diagnostics. Provide recent attempt history and aggregate administrator diagnostics without financial content. Test mocked provider failures, authorization, retries, preservation, confirmed receipt safety and responsive browser flows. No production failure rate or live root cause is claimed without production evidence.

Implementation/verification (OCR): added stored-image rereads, safe provider diagnostics, explicit proposal application, revision/idempotency/concurrency guards and metadata-only administrator statistics. Passed 161 API tests, 16 existing product E2E scenarios, frontend/static/build gates and two final OCR browser/visual loops with 24 state/viewport/accessibility checks. Migration preserves existing receipts and refuses history loss. See ADR-017 and LOOP_LOG.md. Live Gemini failure frequency remains unverified without production codes/credentials; no paid OCR or production deployment was performed.

# 2026-10-23 — Autorzy wpisów i aktywność domowników

Feedback: cancel and remove the temporary recovery-code work; the owner will regain SSH access. Add persistent authorship for receipts, expenses and income, and a screen showing how much each person added.

Cancellation: unmerged PR #33 was closed, both CI runs cancelled, its remote/local branch deleted, unpublished bearer token/public temporary files removed, and unused local-only recovery migration removed. No recovery feature or token was deployed. Existing released administrator/OCR functionality remains on main.

Interpretation and acceptance (before implementation): retain authenticated `created_by` on receipt/transaction creation and preserve it through another person's edits, OCR retries, finalization and idempotent retries. Show author names on receipts and transaction history. Add household-only Activity, reachable on desktop and mobile, with monthly/all-time per-person counts for receipts (including drafts), expenses and income, and integer-grosze expense/income sums. Group by the original recorder, not payer or income contributor. Use Europe/Warsaw creation-time boundaries; distinguish a receipt uploader from the person booking its expense; do not add receipt totals to expense totals. Include zero-activity members, former record authors and explicit unknown legacy authors without guessing. No credentials/emails or other household data in responses. Verify two real-user browser loops with four viewports, empty/error states and accessibility plus appropriate regression/static/API checks. Status: implemented and verified locally: 167 API tests, 9 frontend tests, 20 deployment tests, lint/typecheck/format/build, 16 product E2E scenarios and two clean browser loops with 40 viewport/accessibility checks. See ADR-018 and LOOP_LOG.md. New work has not been deployed.
# 2026-10-25 — Zdjęcia liczników i wykresy zużycia

Feedback: optionally photograph a utility meter from time to time, read it with AI and show attractive consumption charts.

Acceptance before implementation: named household meters with declared units, exact cumulative readings and editable dates; optional recurring in-app reminder; private sanitized photo, Gemini/OpenAI structured proposal with explicit confirmation/correction and manual/error fallback; durable idempotency and shared expensive-call limits; no fabricated fixture readings or automatic financial transactions. Handle irregular intervals, zero usage, out-of-order readings and reject decreasing/duplicate-day readings, explaining replacement/new-meter handling. Charts show actual interval consumption and daily averages, retain accessible history and author metadata, and avoid implying daily measurements from occasional photos. Enforce household isolation on every record/file, preserve data in migrations/export/deletion, and verify backend/static/browser/responsive/a11y flows in two clean loops. Status: locally verified: 189 API, 12 frontend, 20 deployment tests; lint/typecheck/format/build; 16 product E2E and two final four-viewport meter loops (32 accessibility/overflow checks). Migration preservation/downgrade protection and private image deletion/export passed. See ADR-019 and LOOP_LOG.md. No production deployment or paid AI calls.
# 2026-10-25 — Połączenie AI przez MCP

- Feedback: użytkownik chce połączyć aplikację z AI, z pełną obsługą danych, m.in. zapisem odczytów.
- Interpretacja: opcjonalny serwer MCP z operacjami istniejącego API gospodarstwa, odwoływalnymi połączeniami per użytkownik/dom i wyborem odczyt lub zapis; bez udostępniania haseł ani administracji kontami.
- Ekrany/reguły: Ustawienia domu / Połączenia z AI, autoryzacja gospodarstwa, autorstwo, walidacja, OCR, idempotencja i historia operacji.
- Kryteria: klient MCP inicjalizuje połączenie, widzi katalog, zapisuje prawidłowy odczyt bez duplikatu; odczyt nie pozwala na zapis; klucz nie daje dostępu do innych domów/administracji; wygaśnięcie/odłączenie/usunięcie członkostwa blokuje dostęp; panel działa na 4 viewportach. Pierwszy transport Bearer dla Codex/zgodnych klientów; logowanie OAuth dla hosted ChatGPT/Claude wymaga osobnego adaptera.
# 2026-10-27 — Godzina i kontekst codziennego odczytu

Użytkownik chce dokładną godzinę odczytu, szybkie tak/nie dla gotowania i urządzeń oraz krótką notatkę, aby porównywać codzienne zużycie. Kryteria: domyślna bieżąca godzina Warszawy z możliwością poprawienia; gotowanie/piekarnik/pralka/zmywarka jako opcjonalne tak/nie (brak wyboru nie oznacza nie); notatka do 240 znaków; kontekst zachowany przy edycji i dostępny w historii/wykresie/MCP/eksporcie. Starsze wpisy nie otrzymują wymyślonej godziny. Jeśli obie godziny są znane, średnia dobowa uwzględnia faktyczny czas między pomiarami. Czas dodania wpisu jest pokazywany osobno. Pozostaje jeden odczyt dziennie.
# mBank: automatyczne transakcje, uzgadnianie i powiadomienia — integracja prywatna

Użytkownik chce automatycznie rejestrować wpływy/wydatki z osobistego mBanku, przypominać o paragonie/tytule i usuwać rozbieżności; początkowo jedno konto, docelowo wiele. Potwierdził Android i iPhone. Zakres obejmuje rzeczywiste połączenie AIS, synchronizację w tle, rozróżnienie blokad i księgowań, dopasowanie istniejących wpisów/paragonów bez dubli, uzgodnienie sald i opt-in Web Push. Kryteria i zbadane ograniczenia dostawcy zapisano w BANK_INTEGRATION.md. Użytkownik następnie dostarczył aplikację Enable Banking PRODUCTION/AIS restricted, klucz i identyfikator wspólnego domu; zażądał ograniczenia do tego domu. Implementacja obejmuje jednorazową aktywację admina/właściciela z ponownym podaniem hasła i zatwierdzeniem dwóch obecnych osób, bez klucza/identyfikatorów klienta w kodzie. Sprawdzono wyłącznie rzeczywiste metadane aplikacji/katalog banków, bez sesji/operacji. Funkcja nie została jeszcze wdrożona ani aktywowana produkcyjnie; dowody testów i ograniczenia: LOOP_LOG.md/BANK_INTEGRATION.md.

# 2026-11-01 — Miejsce na Oracle i dokończenie wdrożenia

Feedback: „posprzątaj to i wdróż to by działało” po diagnozie 97% zajętości dysku oraz zatrzymanych web/API podczas wdrożenia v0.1.28.

Interpretacja: operacyjne usunięcie odtwarzalnego cache i wybranych nieużywanych obrazów, następnie dokończenie zweryfikowanego wydania po merge. Bez zmian funkcjonalnych, usuwania danych gospodarstw, wolumenów lub backupów.

Kryteria przed wykonaniem: brak równoległego wdrożenia; zachować obrazy v0.1.26/v0.1.27 do rollbacku i v0.1.28 do wdrożenia; potwierdzić commit/ARM64 i wynik istniejących bramek CI; odzyskać co najmniej 8 GiB; zachować prywatną konfigurację i wolumeny; sprawdzić backup bazy/zdjęć, migrację oraz zdrowie db/api/web; dwukrotnie sprawdzić origin/public health, wyłączenie demo i stronę logowania. Nie wykonywać downgrade ani produkcyjnych testów zapisujących fikcyjne finanse.

Wykonanie: pod blokadą wdrożeń usunięto cache nieużywany od co najmniej 7 dni (4,753 GB) i 17 konkretnych nieużywanych obrazów: finance starsze niż v0.1.26, dawne QA/bootstrap i Playwright. Zachowano v0.1.26/v0.1.27/v0.1.28, wszystkie wolumeny, backupy, konfigurację i pozostałe usługi. Dysk zmienił się z 97% / 1,5 GiB wolnego na 58% / około 20 GiB wolnego po wdrożeniu. Nie dodano automatycznego kasowania backupów.

Przyczyna potwierdzona logiem Actions: ENOSPC przerwał zapis archiwum zdjęć, a następnie uniemożliwił utworzenie katalogu rollbacku. Niekompletne archiwum zachowano jako `receipts.incomplete.tar.gz` z ostrzeżeniem `INCOMPLETE.txt`; pozostałą konfigurację przerwanego wydania przeniesiono do prywatnego `~/finance/interrupted/`. Przywrócono poprzednią wersję na czas ponowienia. Ponowiono wyłącznie nieudane joby istniejącego przebiegu, bez przebudowy obrazów.

Weryfikacja: [Actions 41351535260](https://github.com/RochZaremba/financialApp/actions/runs/41351535260) i [Release v0.1.28](https://github.com/RochZaremba/financialApp/releases/tag/v0.1.28) zakończyły się sukcesem. Zachowane wyniki bramek obejmują lint/typecheck/build, unit/API/migracje/E2E/visual oraz ARM64 production smoke dla tej samej paczki. Produkcja ma poprawny commit `83f61c7c97d304031092d5dcb76de8a5c14b41da`, migrację 015 i zdrowe db/api/web; liczebności użytkowników/domów/transakcji/paragonów/pozycji/odczytów pozostały identyczne. Nowy backup `v0.1.28-20261101T221411Z` zawiera bazę, konfigurację i archiwum zdjęć z poprawnym `gzip -t`.

Dwie czyste pętle operacyjnego smoke: origin i publiczne health/config, wyłączone demo, odmowa dostępu bez sesji, manifest/ikony PWA, logowanie/przełączanie rejestracji/walidacja pustego formularza i ochrona trasy Budżet. W obu przebiegach sprawdzono 390×844, 430×932, 768×1024 i 1440×900: brak błędów JavaScript/HTTP 5xx, przepełnień i naruszeń WCAG AA wykrywanych przez axe. Zrzuty każdego viewportu są identyczne między przebiegami i zostały ocenione wizualnie. Nie logowano się na konta domowników, nie tworzono danych finansowych ani nie aktywowano banku/OCR. Dowody: ignorowany `artifacts/operations-2026-11-01/` (`cleanup.log`, `prepare-retry.log`, `server-verification.log`, `browser-verification.log`, `browser-results.json`, osiem `login-pass-*.png`). Status: sprzątanie i wdrożenie zakończone; brak otwartych usterek w sprawdzonym zakresie operacyjnym.

# 2026-11-01 — Pierwsza rzeczywista synchronizacja mBank: SYNC_FAILED

Feedback: „co jest nie tak?”; zrzuty aktywnej restricted aplikacji Enable Banking z podłączonym rachunkiem oraz zgody w Razem z `SYNC_FAILED`, bez pierwszej udanej synchronizacji.

Interpretacja/zakres: zdiagnozować stan zgody i importu bez odczytu treści operacji, ponawiania autoryzacji ani obchodzenia sześciogodzinnej blokady. Dla ewentualnej poprawki kryteria obejmują bezpieczny kod/etap/klasę wyjątku bez danych bankowych i sekretów, uczciwe rozróżnienie błędu od terminu ponowienia, walidację odpowiedzi API oraz zachowanie atomowości/idempotencji i istniejącej zgody.

Wyniki diagnostyki tylko do odczytu: produkcja v0.1.28 pozostaje zdrowa; aktywna zgoda, jeden rachunek PLN z przypisaniem i datą początkową, konfiguracja i odszyfrowanie sesji/identyfikatora poprawne. Brak zaimportowanych bank entries, `last_sync` nieustawione. Próba zakończyła się po około 6,4 s kodem `SYNC_FAILED`; termin kolejnej próby to 2026-11-02 05:38 Europe/Warsaw. W kodzie `bank_sync.py:214` ten kod powstaje dla wyjątków innych niż `BankError`; klasa/etap/traceback są odrzucane, więc obecny zapis nie pozwala ustalić dokładnego miejsca awarii. Blokada jest zapisywana przed pobieraniem (`bank_sync.py:111`) i pozostaje także po błędzie. Logi potwierdzają poprawne aktywowanie i callback, nie zawierają wyjątków synchronizacji. Dokumentacja dostawcy potwierdza dostęp restricted do linked accounts i zawiera schematy odpowiedzi; to nie dowodzi przyczyny tej awarii. Źródła: https://enablebanking.com/docs/api/linked-accounts/ oraz https://enablebanking.com/docs/api/reference/ (skill read-docs). Otwarte: P1 pierwszego importu, P2 brak użytecznej bezpiecznej diagnostyki. Nie zmieniono kodu, danych, zgody ani harmonogramu i nie wywołano API banku podczas diagnozy; konkretnej przyczyny nie ustalono.

Zlecenie poprawki: „w takim razie zrób taką poprawkę”. Kryteria przed zmianą kodu: trwała diagnostyka ostatniej nieudanej próby (etap, dozwolony typ wyjątku, dozwolony kod, HTTP, czas) z migracją zgodną z poprzednim obrazem; bez wiadomości wyjątków, tracebacków, payloadów, identyfikatorów rachunku, kwot i sekretów w diagnostyce/logach. Rozróżnić brak przypisania, oczekiwanie na termin, nieudaną próbę i sukces; zachować sześciogodzinny odstęp bez resetowania obecnej zgody/limitu. Błąd parsowania lub zapisu ma pozostawić całe wcześniejsze dane i móc zapisać diagnostykę po rollbacku. Sprawdzić błędy HTTP/transportu/kształtu JSON/parsowania/bazy, ochronę sekretów, autoryzację i idempotencję; dwie czyste pętle rzeczywistego UI z syntetycznym dostawcą i czterema viewportami. Poprawka przechodzi branch/PR, bramki CI, merge i istniejące wdrożenie; brak obejścia live limitu i brak obietnicy ustalenia historycznego wyjątku, którego poprzedni kod nie zapisał.

Wykonanie i lokalna weryfikacja (2026-11-02): dodano bezpieczne metadane ostatniego błędu, migrację 016, allowlistę kodów/rodzajów, walidację kształtu odpowiedzi API i zapis diagnostyki po pełnym rollbacku. Panel rozróżnia błąd/oczekiwanie/brak przypisania/sukces, pokazuje szczegóły na żądanie i nie wyświetla zielonego powiadomienia po błędzie. Przeszło 252 testów API (39 bankowych), 13 frontendowych, 20 deploymentu, lint/typecheck/Ruff/format/pip-check, produkcyjny build Webpack, 34 E2E desktop/mobile oraz dwie czyste pętle bankowe po 36 screenshot/axe/overflow kontroli. Zakresy, rzeczywiste defekty i ograniczenie lokalnego Turbopack opisuje `docs/quality/LOOP_LOG.md`, decyzję ADR-023. Szczegóły starej próby pozostają nieznane; produkcyjna zgoda i termin nie zostały zmienione. Dostarczenie poprawki odbywa się przez istniejący chroniony PR/release.

# 2026-11-02 — Naprawa rzeczywistej synchronizacji po wdrożeniu diagnostyki

Feedback: „i zrób by działało poprawnie teraz po poprawce logów by synchronizowało się poprawnie”, następnie „kontynuuj”. Zakres rozszerza się na rzeczywiste pobranie i poprawny import, a nie samą diagnostykę.

Dowód wejściowy: v0.1.29/schema 016 wdrożone, pełne CI i release zakończone sukcesem. Automatyczna próba 2026-11-02 05:39 Europe/Warsaw otrzymała HTTP 200 i zakończyła się `AttributeError` na etapie `parse_transactions`; brak zaimportowanych bank entries. To zawęża problem do obsługi danych operacji, szczególnie opcjonalnych pól tekstowych/obiektowych; konkretnego pola jeszcze nie potwierdzono na rzeczywistych danych.

Kryteria przed zmianą kodu: poprawnie obsłużyć brakujące/puste opcjonalne pola bez wymyślania kwot, dat lub stron operacji; zachować ścisłą walidację wymaganych wartości, dokładne grosze, deduplikację, bezpieczną diagnostykę i całościowy rollback. Sprawdzić null/missing obu stron transakcji, brak IBAN/opisu oraz nieprawidłowe typy; wcześniejszy błąd diagnostyki odtworzyć bez uzależniania testu od pozostawienia naprawianego błędu. Wykonać dwie pętle UI/importu i właściwe regresje, przejść PR/CI/release oraz potwierdzić prawdziwy udany import z `last_sync`, saldem i brakiem duplikatów. Treści operacji i numery rachunków pozostają na Oracle; do diagnostyki wystarczą typy pól i liczniki. Na czas dostarczenia można odłożyć znaną błędną próbę, zachowując pierwotny termin do odtworzenia; po wdrożeniu nie skracać sześciogodzinnego odstępu od ostatniego faktycznego pobrania i nie odnawiać zgody bez potrzeby.

Wyniki lokalne: poprzedni parser odtwarza `AttributeError` dla syntetycznego `iban: null`; nowy akceptuje brak/null opcjonalnych pól, pozostawiając nierozpoznaną stronę bez wymyślonej tożsamości. Przeszło 277 testów API (64 bankowe) oraz dwie czyste pętle bankowe po 36 kontroli viewport/axe/overflow z nullable danymi dostawcy. Nie ma zmian schematu ani frontendu. Szczegóły i granice dowodów: `docs/quality/LOOP_LOG.md`. Najbliższa znana błędna próba została odłożona wyłącznie na czas naprawy, z pierwotnym terminem zapisanym prywatnie do przywrócenia po wdrożeniu. Rzeczywiste działanie zostanie potwierdzone po dostarczeniu poprawki.

# 2026-11-11 — Jednoznaczne pary, zwroty, automatyczny bufor i wyrównanie salda

Użytkownik chce automatycznie łączyć jedyną pasującą parę bank–paragon/wpis, także w odwrotnej kolejności, i rozpoznawać zwroty. Dwa obciążenia nie są zwrotem: wymagany jest rzeczywisty wpływ. Dodatkowo koperta Bufor ma automatycznie pokrywać przekroczenia innych kopert i pokazywać kto/ile z niej pobrał. W Banku ma być jawne wyrównanie salda aplikacji do salda księgowego banku.

Kryteria przed implementacją: unikalne dopasowanie po rachunku/kwocie/oknie dat bez dodatkowej akceptacji; konflikt wielu par pozostaje do wyboru, idempotencja i historia automatycznego powiązania; zwrot pełny/częściowy powiązany z pierwotnym wydatkiem, limit łącznych zwrotów, dokładny podział groszy i pomniejszenie wydatków/kategorii bez nowego dochodu; automatyczny zwrot wyłącznie przy zgodnym kontrahencie i jedynym możliwym zakupie, korekta błędnej klasyfikacji. Bufor jest ustawieniem miesiąca, dostaje pozostały plan i pokrywa deficyty tylko do wysokości dostępnych środków; widoczna lista kopert i kwot, niedobór i odzyskanie rezerwy po zwrocie, bez drugiego wydatku i zmiany zamkniętej historii. Wyrównanie jest świadomą, idempotentną korektą salda z kontrolą obu aktualnych wartości, historią autora i daty, bez wpływu na dochód/wydatki budżetu. Zachować izolację domu/dwóch zatwierdzonych osób i limity banku; migracje, regresje finansowe i dwa czyste przeglądy responsywne.

Wynik lokalny: 299 testów API, 13 testów frontendu, 20 testów wdrożeniowych i 16 istniejących scenariuszy przeglądarkowych przeszło. Dwie końcowe pętle nowych widoków po 60 kontroli (cztery szerokości, axe, brak overflow) są czyste. Sprawdzono migracje 001–018, zachowanie starej historii, odmowę utraty nowych danych i 274 testy poprzedniej wersji API na nowym schemacie. Szczegóły, wykryte poprawione defekty i granice dowodów: `docs/quality/LOOP_LOG.md`. Rzeczywiste wdrożenie jest osobnym etapem po CI; testy nie wykonywały operacji na danych finansowych użytkownika.

# 2026-11-11 — Odblokowanie wdrożenia PR #40

Użytkownik: „wdroz je napraw ga lub coś by to weszło”. Pełny etap testów CI 43093280754 zakończył się sukcesem, lecz diagnostyczny upload z `always()` utknął; anulowanie i force-cancel zostały przyjęte, przebieg ostatecznie anulowano. Ponowienie 43098599523 czeka bez jobów. Kryteria: obowiązkowe testy pozostają bramką, diagnostyczne screenshoty mają ograniczony czas i nie blokują wydania po udanych testach; paczka ARM64, smoke, backup i zdrowie produkcji pozostają obowiązkowe. Dostarczyć przez zwykły PR/merge/release, bez obchodzenia ochrony main.
