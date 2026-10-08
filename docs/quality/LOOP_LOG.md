# Loop-Back Loop evidence

## 2026-10-05 — Initial implementation and review

Acceptance criteria were written before implementation in `ACCEPTANCE.md`.

Implemented slices: identity/household, integer budgets and allocations, movements/accounts, private receipt extraction and item review, Inbox, learning rules, goals, recurring payments, analytics, privacy/export/delete, responsive PWA.

Initial evidence:
- `artifacts/pytest-initial.log`: 14 passed, 3 failed; fixes below.
- `artifacts/pytest-second.log`: 17 passed.
- `artifacts/typecheck-second.log`, `artifacts/lint-second.log`: passed.
- `artifacts/vitest-initial.log`: 6 passed.
- `artifacts/ui-review/initial-home-{desktop,mobile}.png`: browser-rendered home screenshots inspected directly.

Defects and fixes:
- P2: small secondary typography on home. Increased label/meta typography across all viewports.
- P2: mobile Inbox status appeared below recent transactions. Reordered mobile home to envelopes → review count → recent transactions.
- P2: Next development indicator covered mobile navigation. Disabled development indicator.
- P1: Polish name normalization did not transliterate `ł`. Fixed normalization; rule-priority test passes.
- P2: oversized upload returned generic 422. Now returns explicit 413 before image decoding.
- Test setup: isolated test database, distinct idempotency keys for different requests, pytest import path.

Further review and two clean exit passes will be recorded below with exact commands and artifacts.

## Integration review and repairs

Evidence before final exit checks:
- `artifacts/e2e-fourth.log`: 4 browser scenarios passed on desktop/mobile.
- `artifacts/e2e-edges.log`: 2 additional real manual-split/photo-draft flows passed.
- `artifacts/pytest-expanded.log`: 27 API/provider tests passed.
- `artifacts/ui-review/final-design-review/`: 52 route/viewport screenshots; zero horizontal overflow, zero axe WCAG A/AA violations, zero page exceptions. All primary screens inspected visually.
- `artifacts/docker-smoke.log`: clean-volume production web 200, proxied DB health 200, demo login disabled (404), registration 201, household 201, Secure/HttpOnly cookies.

Defects found and fixed:
- P1: PostgreSQL SUM(BIGINT) returned Decimal; account balances serialized as strings and goal date calculation failed. Cast aggregate results to integers; assertions cover serialized money types and goal dates.
- P1: financial creation other than transactions could duplicate after a retry. Added migration 002, request fingerprints and household/user locks; repeated and concurrent transaction creation tests.
- P1: unallocated historical transactions were hidden by the current-month filter. Inbox now opens the exact transaction directly, even across months; tested through the UI.
- P1: an entirely confident receipt could become undiscoverable if the user left before finalizing. Added persistent confirmation tasks and migration 003 (including existing unconfirmed receipts), without requiring review of confident items; regression tests cover leaving and returning from Inbox.
- P1: Next proxy default 30-second timeout was shorter than OCR's 75-second timeout. Configured 120 seconds and an 11 MB multipart proxy limit.
- P2: receipt review expanded every confident item. Confident items now use compact summaries and optional pencil editing; only uncertain items expand.
- P2: form field accessible names included hint text. Fields now have explicit names and described-by hints.
- P2: muted text/category chips failed contrast checks. Adjusted colors and visible select names; repeated axe checks pass.
- P2: an empty zero-income plan was celebrated as complete; an unread receipt with no amounts claimed totals matched. Empty states now ask for income/missing receipt data before showing success.
- P2: logout without a network rejected an unhandled promise. It now keeps the session and displays a readable error; browser regression covers it.
- P2: relative receipt storage depended on the shell working directory. Paths are resolved against the repository; existing generated local photos copied to the corrected directory. Nested private data is excluded from Docker context.
- P2: month controls/category chips were too small on touch devices. Expanded targets to 44 px and repeated viewport checks.
- P2: archiving a category with an active recurring payment broke later generation. Archival is blocked until the recurring payment is disabled; archived historical actual envelopes can retain a zero plan.
- P2: household-isolation E2E initially did not assert successful creation of the second household. Corrected setup and explicitly require 201 before testing denial.
- Development-only router exception occurred while source changes/hot reload overlapped a browser run. Final loops use an immutable production build and restart the server between builds.
- npm dependency audit: removed the unused Next ESLint preset containing vulnerable transitive dev dependencies; explicit React/hooks/accessibility/TypeScript lint rules remain. `artifacts/npm-native-audit.json`: zero vulnerabilities.

A remaining upstream P3 diagnostic: Starlette emits a deprecation warning about httpx in its TestClient; pinned versions pass the tests. No app behavior is affected, and the warning is retained in test evidence.

## Final senior engineering / product / QA review

Reviewed money/state boundaries, all household reads/writes, archive/history stability, receipt atomicity/retries/provider failures, pending receipt recovery, actual cache contents, keyboard focus, touch form sizing, readable financial hierarchy, and responsive empty/error states.

Additional repairs:
- P1: a cached-household switch could retain another household's unsaved form values. Household-scoped screens now remount on household change. Browser tests prime both cached households, edit one, switch, and assert the second form starts with its own values.
- P1: a cached-month switch in Add could keep the previous month's default date. The transaction form now remounts per month; browser tests switch September → October and assert the correct dates.
- P2: the keyboard skip link needed a focusable content target. Main has `tabIndex=-1`; `artifacts/keyboard-final.log` records first Tab → skip link → main → month control.
- P2: Polish counted labels had incorrect singular/few forms. Fixed Inbox counts, receipt item counts and the one-day forecast wording.
- P2: small touch form text could trigger automatic focus zoom on iOS. Touch viewports use 16 px form controls; repeated mobile/WebKit checks cover the forms.
- P2: an unknown image in fixture mode was correctly saved as an empty draft, but its provider metadata still showed the demo notice. Such drafts are now marked manual; an API regression asserts this and the unread-receipt screenshots show the honest missing-data state.
- P2: the empty budget's sticky save footer still celebrated a zero-income plan. The footer now requires positive planned income before showing completion; an empty plan explicitly says it can be finished later.

Tooling limitations verified rather than hidden:
- WebKit 1.63 offline emulation rejects even service-worker-provided responses: [upstream Playwright issue #42775](https://github.com/microsoft/playwright/issues/42775). HTTP error injection uses a context with SW disabled. Cache and registration checks remain in real-SW scenarios. `scripts/webkit-offline.mjs` shuts down a real loopback proxy and verifies the app's cached offline page with WebKit: HTTP 200, `fromServiceWorker=true`; screenshot `artifacts/ui-review/webkit-real-offline.png`.
- E2E dates are fixed to the October 2026 demo period, so results do not depend on the day tests run.
- A WebKit trace from `artifacts/e2e-done-1.log` showed native fetch diagnostics precisely when the test replaced the whole document (64,799 ms) during post-save refetches, immediately after the allocation save returned 200. E2E entry-URL document loads now wait for outgoing requests to settle before navigation. Initial blank pages do not wait for a nonexistent network-idle event. No errors are filtered or assertions removed; the final full suites still assert zero page errors.

Additional evidence:
- `artifacts/setup-reproduction.log`: README setup installs locked dependencies, starts PostgreSQL, migrates and re-seeds idempotently without deleting data.
- `artifacts/migrations-release.log`: upgrades 001–003, downgrades to base, upgrades again, metadata comparison shows no pending schema changes.
- `artifacts/lighthouse-dashboard.report.{html,json}`: authenticated production dashboard, simulated mobile; Performance **96**, Accessibility **100**, Best Practices **100**, no run warnings. CLS 0.086.
- `artifacts/ui-review/zoom-keyboard/`: ten principal screens at a 720×450 CSS viewport / device scale 2 (equivalent available layout width at 200% desktop zoom), no horizontal overflow.
- `artifacts/states-final.log`, `artifacts/ui-review/states/results.json`: 30 registration/onboarding, empty-data, invalid-money, offline-banner, unread-photo and API-error checks at mobile/desktop widths, zero axe violations and zero horizontal overflow. The changed empty-budget footer and manual receipt states were inspected visually.
- `artifacts/docker-release-smoke.log`: current production images have healthy services; web/proxied health 200, demo disabled 404, real registration/household creation 201, Secure/HttpOnly cookie, authorized overview 200 and household cleanup 200.

Only external live OCR requires a later API key. Its adapter/schema/error behavior and the complete fixture/manual flows are tested; no live-photo OCR claim is made.

## Exit verification — two consecutive clean loops

Both loops ran the same final application code against a production Next.js build, with the API and persistent development database running. No application changes were made between them.

| Gate | Clean loop 1 | Clean loop 2 |
| --- | --- | --- |
| Frontend/backend static checks and build | `artifacts/quality-release-1.log`, final E2E lint `artifacts/lint-final-1.log` | `artifacts/quality-final-2.log` |
| Unit/domain/provider tests | 6 Vitest + 28 pytest passed | 6 Vitest + 28 pytest passed |
| Chromium desktop/mobile + WebKit mobile E2E | `artifacts/e2e-final-1.log`: 9 passed | `artifacts/e2e-final-2.log`: 9 passed |
| All primary screens at four required viewports | `artifacts/ui-review/rc-1/`: 52 checks | `artifacts/ui-review/final-2/`: 52 checks |
| Page errors / axe violations / horizontal overflow | 0 / 0 / 0 | 0 / 0 / 0 |
| Actual WebKit origin outage | `artifacts/webkit-offline-release-1.log`: 200 from service worker | `artifacts/webkit-offline-final-2.log`: 200 from service worker |

Final visual review confirms the financial hierarchy, concise Polish labels, spacing, mobile navigation and receipt uncertainty treatment. Empty/error states, keyboard navigation, equivalent 200% zoom, README setup, clean migration round trip and production Docker behavior have the additional evidence recorded above.

Exit: **0 known open P0, 0 P1, 0 P2**. The documented upstream TestClient deprecation warning is the only retained low-impact P3 diagnostic. No untested live OCR behavior is represented as verified. The local optimized app remains available at `http://localhost:3000`, with Roch/Kaja demo data preserved.

## Gemini provider extension — 2026-10-05

Outcome: select Google Gemini for receipt extraction and item classification through the same provider interface, with independent server-only key/model settings. Existing validation, integer grosze, household rules, private images, review and atomic finalization remain common domain behavior.

Implementation: `GeminiProvider` sends a sanitized PNG and household categories to the official `generateContent` endpoint, requests structured JSON and validates it with Extraction. Only a complete STOP candidate is accepted; thought parts are excluded. Missing credentials, HTTP errors, blocked/truncated content and invalid output preserve manual recovery. Unknown provider names and unsafe model identifiers are rejected at configuration load. `/auth/me` exposes only a capability boolean, so upload copy reflects actual key availability for OpenAI or Gemini without exposing credentials. Added local/sample/production environment entries and documented activation. No dependencies or database migrations were needed.

Official contract checked against [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output) and [Generate Content API reference](https://ai.google.dev/api/generate-content). Live Gemini calls were not made: no Gemini key is configured. Controlled HTTP responses are used only at the external service boundary in adapter/API tests; visual capability scenarios simulate only public metadata, not extraction.

Defects in initial test setup were corrected before clean loops:
- Manual-recovery test fixtures lacked the editor's `reviewed` field; recovery input now supplies it.
- Onboarding and Home share a greeting. The old E2E selector could pass before household creation committed. The tests now require the household app shell after create/join before reading household data; no application assertion was removed.

Targeted tests cover request headers/image/schema, provider selection, monetary/date validation, missing keys without a network call, blocked/truncated responses, timeout and full successful upload/finalization or HTTP 429 → private image → manual completion. Upload notices are checked with/without credentials at all four required viewports.

Two consecutive clean loops after test repairs, on unchanged application code:

| Gate | Loop 1 | Loop 2 |
| --- | --- | --- |
| Lint/typecheck/unit/build/Ruff/migrations/pytest | `artifacts/quality-gemini-clean-1.log`, final test lint `artifacts/lint-gemini-onboarding.log` | `artifacts/quality-gemini-clean-2.log` |
| Unit/API/provider tests | 6 Vitest + 40 pytest passed | 6 Vitest + 40 pytest passed |
| Browser regression, including Gemini notices | `artifacts/e2e-gemini-clean-1.log`: 12 passed | `artifacts/e2e-gemini-clean-2.log`: 12 passed |
| Gemini upload availability, all four viewports | `artifacts/ui-review/gemini-1/`: 8 checks | `artifacts/ui-review/gemini-2/`: 8 checks |
| All principal screen regressions | `artifacts/ui-review/gemini-regression-1/`: 52 checks | `artifacts/ui-review/gemini-regression-2/`: 52 checks |
| Page errors / axe violations / overflow | 0 / 0 / 0 | 0 / 0 / 0 |

Upload layouts with and without a key were inspected visually on mobile and desktop; the primary scan action, spacing and fallback copy remain clear. `artifacts/docker-gemini-build.log` verifies current production images, and `artifacts/docker-gemini-smoke.log` verifies real production configuration with Gemini selected and no key: correct capability metadata, failed upload retained privately, extraction task, no premature transaction and successful cleanup. Smoke containers were stopped with their volumes preserved. The existing upstream TestClient deprecation warning is retained.

Extension exit: **0 known open P0/P1/P2**. The local app is running with existing demo configuration. Gemini can be activated by supplying its key, selecting `RECEIPT_PROVIDER=gemini` and restarting API; live external OCR remains unverified without that key.

## Independent release review — reproduced defects (2026-10-05)

Baseline: all 52 existing screen checks still passed, confirming that these gates alone missed functional defects. Real Chromium probes with an isolated household (`artifacts/release-probes-2.log`, `artifacts/ui-review/release-probes/*.png`) reproduced:

- P1: incomplete OCR corrections cannot be saved; draft PUT rejects null date/total and empty items. UI silently substitutes today's date.
- P1: retrying a receipt POST with the same idempotency key creates a second private receipt/task and reruns extraction.
- P1: choosing a different goal keeps the previous goal's suggested amount (100 instead of 250 PLN); same implementation affects pocket recipients.
- P1: receipt discounts cannot be represented (negative line rejected), blocking real receipt reconciliation.
- P2: negative opening balance rejected despite supported server model; sub-złoty negative money input loses its sign.
- P2: a saved empty zero-income plan claims “Plan gotowy”.
- P2/security correctness: registration strips password whitespace, accepting a different password and conflicting with password recovery.

Acceptance extension: discounts reduce their assigned purchase category; final category allocations remain positive and balance to the positive receipt total. Draft-only unknown amounts stay null and cannot enter financial transactions. Generic discount corrections must not become household classification rules.

Additional adversarial checks found avoidable per-record queries: 46 SELECTs for a 40-expense month and 406 for a 200-item receipt (`artifacts/release-query-baseline.log`). Fixed with one category-total query and receipt-scoped rule/category loading. Query-budget regression tests assert constant reads while verifying exact totals. Failed-login throttling now includes an account limit and a separate broader proxy/IP limit, avoiding lockout of an unrelated valid account after 15 wrong attempts on another account. Streamed JSON/multipart bodies are bounded independently of Content-Length. Exact grosze are also retained in compact goal/trend amounts; account transfer selectors automatically keep source and destination distinct.

Image validation previously caught DecompressionBombWarning as an exception without actually elevating that warning, allowing images above the advertised pixel bound. Fixed and tested with a small injected limit. Sanitized PNG output is now also bounded (a compressed JPEG can expand); resizing repeats only when necessary. Upload abuse limits include a service-wide 60/hour ceiling alongside 12/user/hour, so newly registered accounts cannot bypass the deployment's OCR budget. Explicit operation retries consume neither quota nor another provider call.

Test harness repairs during review: the new discount scenario initially addressed the second amount input globally after the first item had correctly collapsed; it now scopes the control to receipt row 2. WebKit's `route.fetch()` reconstruction corrupted binary multipart data (upstream Playwright #14624; native uploads already passed). Lost-response testing now calls the browser's native fetch with unchanged bytes, lets the real API commit and throws only before delivering that first response to the app. It asserts identical retry keys/receipt IDs and one persisted task in all engines. These failing preparatory runs do not count as clean loops.

The full check now owns its servers, refuses a build while the local server uses .next, and uses a fresh ephemeral browser database/private image directory with fixture explicitly selected. It performs all screen/state/probe checks before removing only those generated test resources. This prevents paid AI calls and avoids modifying the development household during regression.

Final wording review also corrected the Home badge for an oversubscribed plan (it previously said a negative amount was “Do podziału”), made schema-error copy compatible with signed account/receipt amounts, and gives explicit local feedback for a zero transaction amount. These changes reset the final clean-loop count. Nine independent probes now include the oversubscribed state with a real mobile screenshot.

Production smoke: built both release images and started a fresh, isolated four-service deployment on loopback HTTPS :8443. `scripts/production-review.mjs` exercised real UI registration/login, Secure/HttpOnly/SameSite=Strict cookies, plan/income/pocket, expense, manual private receipt with partial-save/reload/discount, goal contribution, recurring payment, second-member invitation/join, owner-only deletion, export and session revocation. Exact result: 27 PLN remaining in plan, 37 PLN across accounts; 26 mobile/desktop screen checks passed without page exceptions/axe violations/overflow. Evidence: `artifacts/release-production-{build,ui}.log` and `artifacts/ui-review/production-release/`. Local self-signed HTTPS is used only in this isolated smoke; public deployment uses Caddy certificates for the configured domain.

OCR integrity UX: a mismatched item sum must not be headed “Wszystko wygląda dobrze”. The editor now explicitly asks to fix amounts. A discount assigned to a category without sufficient purchases is highlighted for correction even when AI confidence is high; upload creates classification review and finalization still rejects the negative category net. Tests exercise the wrong assignment, visible warning, correction and exact budget result. A write-route matrix also verifies unrelated users receive 403 for every household mutation.

Live Gemini review (key became available during this task) exposed another P1 hidden by contract mocks: REST `TextResponseFormat.mimeType` requires the enum `APPLICATION_JSON`, not the guide's string `application/json`. The real API rejected the old request with HTTP 400/INVALID_ARGUMENT. Fixed against the authoritative REST reference, updated the contract assertion and README, and added redacted provider/type/status diagnostics without keys, images or model output. Restarted the isolated live browser flow; final clean loops must include this fix. Only the bundled synthetic receipt is sent externally.

The configured 2.5 Flash model then returned HTTP 404 for this key/project despite appearing in ListModels. Google's lifecycle documentation restricts 2.5 to projects that already used it and schedules shutdown on 2026-10-16; the current stable 3.8 Flash is returned by the authenticated ListModels endpoint. Updated the shipped default/configuration example to `gemini-3.8-flash` and replaced only the exact obsolete default model entry in local `.env`; the supplied API key and all other settings are preserved. No automatic provider/model fallback conceals failures. Sources: https://firebase.google.com/docs/ai-logic/models and https://ai.google.dev/gemini-api/docs/deprecations.

The live compiler also rejected the full Pydantic schema with generic HTTP 400. A controlled comparison accepted the structural schema (HTTP 200, STOP) after removing validation bounds/format metadata. The Gemini adapter now sends the structural JSON contract and retains **all** domain bounds in server-side Pydantic validation. Contract tests verify integer/null structure, required fields, rejected extra properties, and rejection of out-of-range amounts/long names/invalid dates. Subsequent image calls returned external HTTP 503; their private failed drafts and manual recovery remain intact. No successful live image extraction is claimed until one completes.

Partial-item UX: selecting a category before entering the amount previously collapsed the item to an apparent zero. Incomplete lines now stay highlighted and expanded even after classification. AI extraction can retain a readable item with a null price as an extraction draft; it never enters a financial transaction. The browser regression selects the category, saves/reloads an unknown amount, fills it and then completes a discounted receipt. A preparatory browser run targeted a now-collapsed category chip redundantly; repaired the selector to assert the existing category rather than click a hidden control. That preparatory run was stopped and does not count as clean.

Fresh README startup uncovered a further P1 after the first otherwise clean product loop: terminating the old dev launcher signaled the reloader twice without waiting, leaving API on :8000 and blocking optimized startup (`artifacts/release-bootstrap-reproduction.log`, dev/start server logs). Replaced duplicated shell traps with a small shared local supervisor: separate owned process groups, one shutdown sequence, bounded graceful shutdown, remaining-worker cleanup, and occupied-port refusal. Development retains API/frontend reload. Both launchers use it; Python script lint/format now joins the quality gate. A repeated setup/dev/stop/build/start run passed; a completely fresh source-only checkout is being verified with an explicit Ctrl+C/port-release assertion. This fix resets the two full clean-product passes again.

Final adversarial duplicate probe reproduced P1: a second photo with different bytes but the same corrected merchant/date/total was finalized as a second expense (HTTP 200 instead of 409; `artifacts/release-different-photo-reproduction.log`). Duplicate suspicion now matches household-scoped headers in addition to image hash, including after OCR correction. Finalization checks under the household lock, rejects the second expense until explicit separate-purchase acknowledgment, and the editor exposes that choice even if the match became known only at confirmation. Tests cover distinct images, simultaneous confirmations, review-task creation, acknowledgment and household isolation. No fuzzy merchant match or automatic deletion is introduced.

A WebKit preparatory trace also exposed a loading-state defect: after a false offline hint, auth fetched HTTP 200 but the household query stayed paused with an indefinite skeleton (`artifacts/e2e-results/...safari-mobile/trace.zip`, failed screenshot). Queries now use real fetch outcomes rather than blocking on the browser's connectivity hint; bounded retries end in the designed error/retry state. The banner says a save **may** fail instead of asserting a disconnected state from a hint alone. A new browser regression explicitly supplies a false hint with reachable API, then fails a real overview request and recovers through Retry. All engines run this scenario; no page errors or assertions are filtered.

The expanded end-to-end flow's final Home review found another P2 absent from the paid-pocket demo: the unpaid “Zaplanowane” label had contrast 4.14:1 on white. Replaced its hard-coded gray with the existing accessible muted token. The regression now evaluates Home with one unpaid and one paid recipient, so this state joins axe and responsive checks.

Visual review of the new duplicate state found contradictory copy: its headline still said everything looked good, and a fully corrected manual receipt retained the original missing-data notice. The headline now prioritizes duplicate review until separate-purchase acknowledgment; the original OCR notice appears only while data remains incomplete. Acknowledgment clears the duplicate error. Header correction saved as a draft updates duplicate Inbox tasks and removes obsolete suspicion; explicit tests cover both transitions. Duplicate screenshots are taken from the top before axe changes focus/scroll, preserving the intended mobile/desktop layout.

Receipt quantity review reproduced a P1: a fully readable item with null quantity was rejected by the extraction schema, while manual entry demanded inventing a value (`artifacts/release-quantity-reproduction.log`). Quantity is now optional information throughout extraction, draft saving and confirmation; unknown values remain empty, never assumed to be one. A real browser regression saves/reloads a blank quantity and confirms balanced purchase/discount lines. The API regression finalizes a priced, classified extracted item without quantity. The preceding preparatory E2E also expected the former all-good heading on an identical image; it now asserts the intended duplicate warning instead. That failed preparatory run is not counted.

Final human tablet review found P2 missed by axe/overflow: the monthly trend broke 3670,37 across two lines inside a narrow six-column chart (`artifacts/defects/trend-number-wrap.png`). Replaced cramped vertical columns with six simple horizontal month rows; exact amounts remain visible in one piece, without abbreviated/rounded values. Screen readers now receive actual month/amount list items instead of an image role with only a generic label. This resets the two final clean passes; prior passes are preparatory evidence.

A real mobile correction probe reproduced P2 after finalization returned 409: changing the shop back to a unique purchase and saving the draft removed all server duplicate tasks but left the old duplicate headline/checkbox in the editor (`artifacts/release-duplicate-correction-reproduction.log`, `artifacts/defects/stale-duplicate-after-correction.png`). Successful draft saving now clears the local fallback flag and prior acknowledgment; the refreshed server tasks still preserve genuine matches. Browser regression corrects the headers, checks that suspicion disappears without another expense, then reintroduces the true match and requires explicit acknowledgment. The preceding clean automated passes predate this discovered UX defect and are preparatory, not exit evidence.

Safari regression analysis found a reproducible interaction problem behind missed receipt clicks: the trace moved the category target through y=591 →640 →23 while global smooth scrolling continued, twice intercepting the fixed central Add navigation. The saved draft then had no category. Native Add-row stress alone passed 20/20, so it was insufficient to exclude this longer-flow defect. Removed global smooth scrolling and reserved scroll padding above/below fixed UI; kept all assertions and added immediate confirmation of the selected category before saving/reloading. Trace/screenshot evidence is retained in `artifacts/defects/safari-scroll-interception/`. No retries, forced clicks, error filters or motion-preference overrides were added. These failing preparatory passes do not count toward exit.

The final live 3.8 image attempt still returned external HTTP 503. Authenticated Google ListModels exposed stable `gemini-3.1-flash-lite`; testing that explicitly selected model succeeded with a real key: LIDL, 2026-10-04, 13975 grosze, six items summing to 13975, actual review/split/finalization/budget, zero page errors (`artifacts/release-live-ai-lite.log`, `artifacts/ui-review/live-ai/`). Updated only the local model entry (key and all other settings preserved), shipped config/sample/production defaults and README to this proven model. The existing mocked 3.8 test deliberately remains as a configurable-model contract. Final gates are repeated after this last default change; no live OCR failure is hidden by automatic provider/model fallback.

### Final release exit — 2026-10-05

The following two complete passes ran consecutively **after all repairs and the final Gemini default change**, against unchanged application/test/script source. Both exited successfully. Preparatory passes and failed reproductions above are not counted toward exit.

| Gate | `release-final-1` | `release-final-2` |
| --- | --- | --- |
| ESLint, TypeScript, production build, Python lint/format | Pass | Pass |
| Frontend unit tests | 7 passed | 7 passed |
| API tests and fresh migrations | 63 passed | 63 passed |
| Chromium desktop/mobile and iPhone WebKit critical E2E, retries 0 | 18 passed | 18 passed |
| Primary screens at all four required viewports | 52 clean checks | 52 clean checks |
| Empty/loading/error/receipt states | 32 clean checks | 32 clean checks |
| Independent financial/startup/auth probes | 9 passed | 9 passed |

Commands: `REVIEW_PASS=release-final-1 PLAYWRIGHT_DOCKER=1 WEBKIT=1 ./scripts/check.sh` and the same command with `REVIEW_PASS=release-final-2`. Evidence: `artifacts/release-final-{1,2}.log`; screenshots/results under `artifacts/ui-review/release-final-{1,2}/`, `release-final-{1,2}-states/` and `release-final-{1,2}-probes/`. Page exceptions, axe violations, horizontal overflow and broken monetary labels: zero. Source integrity is recorded in `artifacts/release-code-manifest.sha256` and `artifacts/release-source-check.log`.

Additional final verification:

- **Real Gemini, twice:** `artifacts/release-live-ai-lite.log` with `artifacts/ui-review/live-ai-lite-1/`, then `artifacts/release-live-ai-configured.log` with `artifacts/ui-review/live-ai/`. The second run used the saved configuration without a model override. Both extracted the bundled synthetic LIDL image into six items, exactly 13975 grosze, and completed real browser review, split transaction and budget update without page errors. Only this synthetic fixture was sent to Google; this does not establish accuracy for every real-world photo.
- **From-zero README startup:** `artifacts/release-bootstrap-final.log`, `artifacts/ui-review/bootstrap-{dev,optimized}.png`. A separate source-only copy completed setup, development startup, real browser login, Ctrl+C with both ports released, production build and optimized startup. Its QA database/files were removed afterward.
- **Migrations and data safety:** `artifacts/release-migrations-final.log` and `artifacts/release-downgrade-safety.log`: fresh upgrade, downgrade/upgrade and no pending schema changes; lossy downgrade refused for partial and negative receipt items without deleting them.
- **Actual production HTTPS stack:** `artifacts/release-production-final-build.log`, `artifacts/release-production-final-ui.log`, `artifacts/ui-review/production-release/`. Latest Docker images, four services, Secure/HttpOnly/Strict session cookies, signup/invitation/member permissions, budget/pocket/expense/receipt correction and duplicates, goals/recurring/export/deletion: 28 clean visual checks. Exact remaining plan 2700 grosze and account total 3700 grosze. The isolated QA stack and its own volumes were removed; original data was preserved (`artifacts/release-production-cleanup.log`).
- **Final optimized local application:** `artifacts/release-local-browser.log`, `artifacts/ui-review/release-local-final/`. All 13 primary routes checked with equivalent 200% desktop zoom, accessibility/overflow/amount checks and keyboard skip-link navigation. Existing Roch/Kaja demo still has two members and 432963 grosze remaining; Gemini availability is true. Final Home, Analytics, partial-receipt and live-extraction screenshots received human visual review.
- **Real offline PWA, twice:** `artifacts/release-webkit-outage-{1,2}.log`, `artifacts/ui-review/webkit-real-offline-release-{1,2}.png`: actual origin shutdown in WebKit returned the cached public offline page from the service worker. No private household data is cached there.

Exit verdict: **zero known open P0/P1/P2 in the reviewed V1 flows; two consecutive clean full passes completed**. One low-value P3 remains: the test-only Starlette TestClient/httpx deprecation warning; it does not affect runtime behavior. Physical phone hardware and arbitrary real receipt accuracy were not claimed. The normal optimized local app remains running at `http://localhost:3000`; original demo data and supplied secrets are preserved. README documents exact setup, operation and deployment requirements. No external production deployment was performed.

### Oracle production packaging — 2026-10-05

User requested a demo-free build for deployment to `finance.rochzaremba.com` on `ssh oracle`. Read-only inspection found Ubuntu ARM64 and an existing system Caddy serving other sites on 80/443. Added `compose.oracle.yaml` with native ARM64 images and loopback-only web port 8810, plus `deploy/finance.caddy`, a configuration-backup/validation activation script and exact `deploy/ORACLE.md` instructions. No running host Caddy configuration was changed. Production Docker images now omit API seed and the public demo receipt; development remains available locally. Environment files are excluded from build/archive contexts.

Release `20261005T133723Z` was built natively and staged at `~/finance/releases/20261005T133723Z` on Oracle. `finance-api` and `finance-web` images were confirmed ARM64 and free of seed/demo assets (`artifacts/oracle/arm64-build.log`, `image-integrity.log`). A secret-free source archive and ready-image archive are retained locally and remotely, with matching SHA-256 (`image-checksum.log`, `staging-integrity.log`). Separate mode-600 production environment contains a new random database password and configured Gemini credentials; no local household database or receipt data was copied.

Two consecutive real HTTPS browser passes on these native release images, each using fresh isolated QA volumes: `artifacts/oracle/production-pass-{1,2}.log`, screenshots/results `artifacts/oracle/pass-{1,2}/`. Each passed signup/login, Secure/HttpOnly/Strict cookies, household creation/invitation/join, plan/income/pocket, expense, partial receipt save/reload, signed discounts, corrected duplicate detection, savings goal, recurring payment, export, logout and owner deletion; **28 clean mobile/desktop visual checks per pass**, zero page exceptions/axe violations/overflow. Exact remaining budget 2700 grosze and accounts 3700 grosze. The second database contained zero users before the browser started. Production demo login returned 404 and configuration disabled demo.

Additional regression: ESLint/typecheck passed (`lint.log`, `typecheck.log`), 7 frontend tests (`unit.log`), 63 API tests (`backend-regression.log`), Python lint/format (`ruff.log`), shell syntax and candidate Caddy configuration including existing sites (`caddy-validation.log`). Human visual review checked the native-release Home on mobile and desktop. There were no application/UI source changes; the previously recorded four-viewport and WebKit regressions remain applicable.

Exit: zero known P0/P1/P2 in the changed production-packaging flow; two consecutive clean native production browser passes. QA project `finance_releaseqa` and its own volumes were removed (`qa-cleanup.log`), SSH QA tunnel closed, original server services preserved. Actual production project `finance` and domain have **not** been activated: the requested ready-to-deploy release is staged, and `./deploy/oracle-activate.sh` is the documented next deployment command.

CI/CD reproduction: the first real GitHub release workflow (37328230439, merged PR #8) passed full quality gates, native ARM64 build and production HTTPS smoke. Oracle deployment then failed before migrations: the receipt volume was mounted at `/data`, while tar expected `/data/receipts`. The empty storage reproduced `tar: receipts: Cannot stat`. The pipeline restored previous images, retained the private database snapshot, left current unchanged and skipped GitHub Release publication; public health remained OK. Fixed the mount at `/data/receipts` in a shared backup helper. Native production smoke now invokes this exact helper on both empty storage and a synthetic marker, verifying archive contents. This failed attempt does not count as a clean delivery loop.

### Hosted CI resilience and repository presentation — 2026-10-05

Run 37333109722 timed out while installing browser libraries from the runner's Ubuntu mirror, before any browser tests ran. Removed that network/package-install dependency by running E2E **and all visual/state/probe scripts** inside the official lockfile-matched Playwright image. Confirmed its AMD64 and ARM64 manifests. Production smoke uses the same browser approach.

Actual fixed PR CI [37338101231](https://github.com/RochZaremba/financialApp/actions/runs/37338101231) passed setup, lint, typecheck, production build, fresh migrations, 7 frontend tests, 63 API tests, 17 deployment tests and 18 Chromium/WebKit E2E tests. Downloaded evidence: `artifacts/github/fixed-ci.log`, `artifacts/github/fixed-ci-evidence/ui-review/github-ci{,-states,-probes}/` — 52 primary screens, 32 state checks and 9 independent probes. Additional local container review: `artifacts/github/local-docker-visual.log`, `artifacts/ui-review/ci-docker-local/`, 52 checks. Mobile and desktop Home screenshots received visual inspection. Public HTTPS login was checked on both widths with no demo button: `artifacts/github/live-site/`.

Publication review excluded the original private spreadsheet from all public Git ancestors, kept its local copy and a private history bundle, and checked tracked source against configured secrets without printing them. Environment, deployment keys, private data and generated artifacts are ignored. Repository metadata, protected main, production environment restrictions, security reporting, Dependabot and issue/PR templates are configured. README preview images contain synthetic seed data only. All local documentation links resolve; workflow actionlint, deployment Ruff/pytest and shell syntax pass. Manual Oracle commands now use current env/shared Compose, and receipt backups mount the actual storage path even while API is stopped.

Low-value P3: pinned Actions emit a Node 20 retirement notice while GitHub executes them on Node 24; all used operations passed. Dependency-update PRs remain separate, require the same quality gate and are not merged automatically. The existing test-only Starlette/httpx warning remains unchanged.

The next real deployment (37339000416, PR #9) passed fresh quality gates, native ARM64 build, real empty/populated receipt backups and 28 HTTPS production screen checks. Its public health probe then received Cloudflare 403 for Python's default User-Agent, although origin returned 200 and normal curl returned 200. Rollback restored the original images and publication was skipped. Added the explicit `finance-deploy/1.0` identifier to all receiver health/config/demo requests, retaining public health enforcement. Actual Oracle origin/public probes and the disabled-demo 404 passed with this identifier before retry. Regression now has **19 deployment tests**, including both-origin request headers and rejection of public failure even when origin is healthy. Retry uses **failed jobs only**, keeping the already verified image artifact. Failed attempts are not counted as clean loops.

First clean completed delivery: [37339000416, attempt 2](https://github.com/RochZaremba/financialApp/actions/runs/37339000416/attempts/2), [v0.1.2](https://github.com/RochZaremba/financialApp/releases/tag/v0.1.2). Exact merge bf78ce1d42afa3f4d78acc6cfa7126c96bd93315 was deployed on Oracle and published with the ARM64 archive/checksum. Real post-deploy verification confirmed original user/household/transaction identities remain present, the same named data volumes and private environment are retained, and both container revisions match the release. Private baseline/after snapshots remain outside Git in `artifacts/github/production-{before,after-first}.json`. Final docs/health-regression merge repeats full CI, native fresh production smoke, backup, deployment and publication; the milestone requires that second delivery to succeed as well. Actions/Release evidence is the authoritative record for that final regression, which necessarily runs after this document is committed.

Second completed delivery: [37342261637](https://github.com/RochZaremba/financialApp/actions/runs/37342261637), [v0.1.3](https://github.com/RochZaremba/financialApp/releases/tag/v0.1.3), merge e74ea36fdb4e2c6e7e6c5b18073cb86046ecb55f. PR CI 37341516942 and merged-commit quality gates passed 7 frontend, 63 API, **19 deployment**, 18 E2E and the full visual/state/probe suites. Native fresh HTTPS smoke, real receipt backups, actual Oracle deployment and automatic Release publication passed. Post-deploy checks again confirmed healthy exact image revisions, private configuration, valid database/receipt archives and preservation of original record identities/volumes (`artifacts/github/release-second.log`, `production-after-second.json`). Live HTTPS login checked; README rendered in an actual GitHub browser with both preview images loaded (`readme-review/readme.png`).

Final CI calendar review found a separate automation defect: visual/state/probe scripts had no fixed clock although plans are dated October 2026. With a future browser date, the uncorrected probe looked for an October plan in an empty future month and timed out. A focused real-browser reproduction then showed the same goal selector returning `0,00` in November 2030 and exactly `250,00` after restoring the fixture date. The product's period behavior was correct; the QA setup was inconsistent. Added the same fixed Europe/Warsaw date already used by E2E and production smoke to all three remaining scripts. Evidence: `artifacts/github/clock-review.log`, `clock-future-{before,after}.png`; no OCR calls or financial movements in the focused reproduction. Initial standalone harness attempts stopped on the designed no-budget empty state/missing idempotency header; these are not counted as successful regressions. Syntax and diff checks passed. The final protected PR and its merged-commit workflow must repeat the complete application/browser regression after this QA-only change; their Actions/Release evidence records the final result.

## 2026-10-05 — Monthly named income sources

Acceptance criteria were recorded in FEEDBACK_LOG/ACCEPTANCE before implementation. Added persisted monthly names/amounts/contributors, an atomic server-derived total, legacy-total migration/rollback compatibility, a responsive source editor/read summary, demo sources and export/deletion support.

Preparatory checks: 67 API tests pass, including old-plan migration with exact grosze, refusal of destructive downgrade, household/member authorization, duplicate names, bounded strict money, atomic failures, repeated PUTs, exports and independent months. The new real-browser flow exercises Roch/Kaja attribution, correction/deletion/reload and four viewport sizes in Chromium and WebKit.

Defects found and fixed: P2 duplicate-source validation returned an unhelpful generic form message; moved business validation to a clear Polish error. P2 budget-save errors appeared below the long form; moved alerts into the visible save bar and added an in-viewport assertion. Retained the failed preliminary browser evidence under `artifacts/income-loop-1.log`; it does not count as a clean final loop. A screenshot then exposed P2 overlap: the sticky plan-total banner covered part of the save alert. Raised the save bar above that banner and added a real hit-test of alert text, rather than treating DOM visibility as sufficient. Also corrected the save-bar helper so a validation failure asks for correction instead of claiming that the plan is ready. Final verification follows these fixes.

Final local evidence after the last UI fix:
- `artifacts/income-complete-loops.log`: lint, typecheck, production build, 7 frontend tests, 19 deployment tests and 67 API tests passed. Migration tests use only a disposable test database and preserve legacy period identity, amount and allocations.
- `artifacts/ui-review/income-complete-a/` and `income-complete-b/`: two consecutive clean complete income-source flows, each passing in desktop Chromium, mobile Chromium and mobile WebKit. Each pass includes 12 source-editor screenshots at 390/430/768/1440, 3 visible-error screenshots, accessibility/overflow checks, real text-occlusion checks, creation/invitation/attribution, exact totals, reload, corrections, deletion, empty sources and independent months. The flows resume the original mobile viewport after screenshots.
- Screenshots were inspected directly; save errors remain above the total banner and give correction guidance. No known P0/P1/P2 remains in the changed flows.
- `artifacts/ui-review/income-local-migrated/`: the normal app starts with migration 005, unchanged original period/amount fingerprints, four accessible responsive budget read views and a correct shared legacy source in the editor; no page errors. Its real AI configuration and original local data were preserved; these checks made no AI calls.
- The full protected [PR CI](https://github.com/RochZaremba/financialApp/pull/12/checks) repeats 21 E2E tests plus 52 primary views, 32 state views and 9 independent probes for the final commit. Merge delivery also runs the extended production HTTPS flow with multiple sources and a second contributor before deploying/publishing. Its actual results are retained with the Actions run and release.

Hosted CI follow-up: source CI 37354006276 passed all full gates. The documentation-only repeat 37354945502 exposed a timing-dependent QA failure: the faster shared-IP browser sequence exceeded the real 15/minute registration/demo limiter, then an unchecked second registration surfaced as a downstream 401. The application correctly returned 429. Browser projects now wait one limiter window between projects and explicitly assert second registration success; production limits are unchanged. The final protected CI repeats the complete suite after this harness repair. Earlier failed runs remain evidence, not clean exit passes.

Migration delivery review reproduced another release risk: an older image’s automatic Alembic bootstrap cannot locate revision 005 after the expansion. The receiver now overrides only the rollback API command to start Uvicorn directly, keeps the expanded database untouched, and waits for container health. Added a real old-revision-directory migration regression and a deployment-command regression. The trusted Oracle receiver must be updated atomically before this release; existing images, private configuration and volumes stay intact.

Production smoke follow-up: PR #12 merged as 688ee48 and complete merged-commit quality gates passed. Native ARM64 images built, but release run 37358239025 correctly stopped before deployment/publication: the added contributor check left the primary QA browser on Budget, while the subsequent export assertions expected Settings. “Kaja QA” consequently matched both an income source and pocket-money row. The harness now explicitly returns to Settings before checking membership/export; application behavior and production data remain unchanged. A follow-up protected PR verifies this navigation repair before a new release.

### Native account currencies and PLN valuation — 2026-10-08

Outcome: create an account with a native PLN/EUR/USD/GBP/CHF balance, retain integer minor units, and automatically include its NBP-valued PLN amount in “RAZEM NA WASZYCH KONTACH”. Rate/date and outage states are visible; existing budget transactions remain PLN. Acceptance criteria: `docs/quality/ACCEPTANCE.md`; decision: ADR-011.

Implementation evidence: migration 006 defaults existing accounts to PLN and rejects loss of foreign currency on downgrade. Decimal half-up conversion is server-owned. A bounded HTTPS NBP table-A request refreshes hourly; failed retries are throttled and retain last good rates. A missing rate prevents a misleading partial total. Foreign accounts are excluded from transaction/receipt/recurring selectors and rejected by server write rules. Export retains account currencies and declares minor units.

Automated verification: `artifacts/currency-final-check.log` passed lint, typecheck, build, 7 frontend tests, 77 API tests, 20 deployment tests, 14 desktop/mobile Chromium E2E flows, 52 primary-screen reviews, 32 state checks and 9 release probes. Ten new API tests cover provider precision/invalid data, positive/negative rounding, caching/refresh/failures, idempotency, authorization, PLN write boundaries, export and migration preservation/destructive downgrade rejection. A live HTTPS NBP probe validated the actual published table (2026-10-07).

Loop defect: both initial automated currency passes were green, but direct screenshot inspection found P2: on mobile, the new exchange-rate paragraph occupied the narrow icon grid column and wrapped vertically. Those runs do not count as clean visual exit loops. Fixed the paragraph's content-column placement and added bounding-box checks for readable width/height. Re-run evidence follows in `artifacts/currency-clean-loops.log` and `artifacts/ui-review/currency/`.

QA tooling note: an earlier full runner was edited while it was executing, causing an EOF at its end. The frozen final script was rerun from the beginning successfully; the interrupted runner is not exit evidence. All verification uses disposable databases and receipt paths; local household data is preserved.

Final exit evidence: `artifacts/currency-clean-loops.log` passed frontend lint/typecheck/unit/build and two consecutive complete currency loops at 390×844, 430×932, 768×1024 and 1440×900. Each loop checks persisted EUR creation/reload, the exact displayed total, native and PLN values, publication date, cached/unavailable states, meaningful paragraph bounding boxes, axe WCAG A/AA, overflow and foreign-account exclusion from income/expense/transfer/recurring forms. There are 32 final screenshots in `artifacts/ui-review/currency/`; rates are deterministic browser metadata for these state checks, while writes/persistence are real. The subsequent unmocked 52-screen review is in `artifacts/ui-review/currency-final/`, with no overflow or axe findings. Directly inspected final mobile account/error views and desktop account/form views. The actual NBP-backed mobile view shows 100 EUR → 437.97 PLN at 4.3797 (table dated 2026-10-07); eight such accounts plus 15179.63 PLN correctly total 18683.39 PLN. The rate paragraph now uses the readable full content width on all sizes. No known P0/P1/P2 remains in changed flows. No production deployment was performed.

### Dependency PR cleanup — 2026-10-08

User request: resolve all seven outstanding Dependabot PRs by closing incompatible updates or merging tested updates. PR #4 cannot install because Pydantic pins a different pydantic-core; #5 fails in eslint-plugin-react with ESLint 10. Closed both. Closed #1 after source inspection found checkout v7 refuses the fork merge SHA in the existing trusted post-merge pull_request_target delivery flow; a coordinated workflow migration is required before that upgrade.

Consolidated #2/#3/#6/#7 on current main into one reviewed update: setup-python 7.0.0, upload-artifact 7.0.1, Vitest 5.0.3 and lucide-react 1.50.0. Action commits remain SHA-pinned. Local lint, typecheck, seven exact-money unit tests and production build passed; npm audit found zero vulnerabilities. Hosted Quality gates must pass on this combined current-main branch before merge. Existing household/account code and database schema are unchanged by this dependency PR.

### Transaction editing — 2026-10-08

Outcome: open a saved movement from its expanded timeline row and correct its description, date, amount, accounts, category split or pocket/goal recipient. Type/identity and original creation-idempotency fingerprint remain stable. Receipt-generated movements retain their documentary amount/date/splits; description/account may be corrected. Historical archived category references can be retained. Each edit validates all household references, requires the revision read by the editor and records an audit event and idempotency marker.

Initial verification: lint/typecheck/build, seven frontend tests, 20 deployment tests and 82 API tests passed in `artifacts/editing-loop-1.log`. Five added integration tests cover exact account/goal/month/split recalculation, atomic validation failures, stale changes, idempotent retries/original creation replay, Inbox lifecycle, authorization and receipt evidence. Real-browser editing and stale-change flows include screenshots and axe/overflow checks at 390/430/768/1440; directly inspected mobile and desktop screenshots under `artifacts/ui-review/editing-loop-1/`. Full local/hosted regression is in progress; no milestone exit is claimed until both clean complete runs finish. The protected PR repeats the same frozen application and browser flow before merge.

Transaction-editing exit: local `editing-loop-1` completed all gates (82 API, 24 Chromium/WebKit E2E, 52 primary views, 32 states, nine probes and currency reviews). The independent frozen-commit [CI 37776777173](https://github.com/RochZaremba/financialApp/actions/runs/37776777173) also passed the complete suite. Screenshots were directly inspected; no known P0/P1/P2 remains in editing. [PR #16](https://github.com/RochZaremba/financialApp/pull/16) merged as `1aea154` after both complete clean passes. Merge-only delivery is tracked separately; a merged PR is not claimed as a successful deployment before the workflow finishes.

### Monthly plan copy — 2026-10-08

Outcome: select a source month inside the budget editor, inspect named incomes and allocations, then explicitly apply to the editable target draft and save. The server provides an authorized read-only preview, excludes archived/missing references and actual-only spending rows, reports omitted positions and never copies receipts, movements or envelope carryover. Source history stays unchanged. Plan writes now support idempotency and a captured editor revision, including changes to source names with unchanged income totals.

Evidence in progress: `artifacts/copy-loop-1.log` passes static/build/unit/deployment checks and 85 API tests. Added tests verify exact copied amounts, source/target independence, no fabricated income/transactions, omitted archived categories, household isolation and stale revisions. New real-browser preview/apply/save/reload/error flow captures all four exact required viewports with axe/overflow checks. The editing screenshot helper was also corrected to use 390×844 and 430×932 rather than taller screenshots. Protected CI provides the second complete frozen-source regression before merge.

Copy visual review found P2 despite green desktop/mobile flow checks: the fixed budget-save bar covered part of the expanded copy preview, and a redundant success toast competed with the apply action. Stopped the preparatory browser run; it is not a clean exit pass. Removed the read-only toast and hide the global save bar while the copy tool is open; applying the proposal closes the tool and restores save. Added an explicit save-bar absence assertion. `copy-clean-1` will restart from the beginning after the stopped QA servers release their ports; the initial occupied-port attempt is also not counted.
## 2026-10-08 — harmonogramy i przypomnienia

Kryteria: cykle tygodniowe/miesięczne/kwartalne/roczne, stabilne kotwice na końcu miesiąca i lata przestępne; jeden wydatek na potwierdzony termin; oczekiwania nigdy nie tworzą wydatków automatycznie; przypomnienia w aplikacji i prywatny plik kalendarza z alarmami.

Pierwsze testy wykryły P1: daty nowego harmonogramu nie serializowały się w odcisku idempotencji. Ujednolicono serializację wartości dat. Osiem celowanych testów przechodzi; pełna regresja po integracji z kopiowaniem jest wymagana. Dodano E2E: utworzenie rocznej płatności w UI, przypomnienie, pobranie kalendarza, zapłata i bezpieczne ponowienie, tygodniowe terminy, cztery viewporty oraz axe.

## 2026-10-08 — dokładniejsze wyszukiwanie (osobny branch)

Wynik: filtrowanie po koncie źródłowym/docelowym, kategorii, zakresie dat, dokładnych kwotach oraz sortowanie i wyszukiwanie nazw pozycji paragonów. Wszystkie filtry są autoryzowane na serwerze, a podział transakcji nie powiela wyników. Zwykłe wyszukiwanie tekstu nadal działa bez dodatkowego kliknięcia.

Kryteria: stabilna paginacja; dosłowne `%` i `_`; poprawne zakresy; historyczne kategorie; żadnych obcych kont/kategorii. Wstępnie: 85 testów API, lint, typecheck i build przeszły. Dodano przepływ E2E z przeglądem czterech wymaganych viewportów i axe. Pełne dwie pętle zostaną zapisane po weryfikacji PR.

Copy exit: corrected code passed 85 API tests and 27 full Chromium/WebKit E2E in `copy-clean-1`; this local run was interrupted during the additional state review, so it is not counted as a complete suite. Independent full [CI 37778709483](https://github.com/RochZaremba/financialApp/actions/runs/37778709483) passed all gates. Two consecutive clean runs of the changed primary flow are `copy-clean-1` and `copy-clean-2` (three browser projects, exact four viewport screenshots, axe, no overflow). Direct screenshot review found no remaining P0/P1/P2 after the save-bar fix. PR #17 merged as `3177dd4`.

Search visual review found P2 after the first green API/E2E pass: mobile advanced selects clipped their selected labels in two columns. Changed the advanced fields to one column below 600 px; screenshots now focus the search field after axe to avoid capturing axe's temporary skip-link focus. Stopped the old supplementary QA review. The first run is not counted as a clean final loop.
