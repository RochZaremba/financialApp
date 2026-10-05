# AGENTS.md - Home Budget App

This file is the authoritative working contract for coding agents in this repository.
Read it before changing code. Also read every accepted ADR in `docs/adr/`.

## 1. Product mission

Build a private household-budget application for two people, designed first for Roch and Kaja, but with a data model that can support more household members later.

The application must be exceptionally simple to use, visually calm, polished, and trustworthy. It is not a generic accounting suite. It is a household money operating system.

Core principle:

> The household receives income, gives every shared złoty a job, and makes shared spending nearly effortless to capture.

Primary household model:

- All household income can be treated as shared income.
- A monthly plan allocates shared money into budget envelopes/categories.
- Each person may receive fixed monthly personal pocket money.
- Pocket money is a terminal transfer from the household perspective. The person may spend it however they want. Tracking what happens after the transfer is optional and must never be required for the shared budget to work.
- Shared expenses are tracked and categorized.
- A single store receipt may contain items from multiple categories, so classification happens per receipt item, not merely per merchant.

The app must also keep the architecture flexible enough to support other split models later, such as 50/50 or proportional contributions. Do not make those models part of the first-version UI unless they are already cheap to support.

## 2. First-version scope

### Must ship

- Authentication.
- Household creation and invitation/join flow for a second member.
- Monthly budget planning.
- Planned income.
- Budget categories and monthly allocations.
- Pocket-money allocations for household members.
- Manual income and expense entry.
- Receipt image upload/camera capture from the PWA.
- Receipt extraction into merchant, date, total, line items, quantities when available, and prices.
- AI-assisted item-by-item categorization.
- Confidence score for AI classification.
- Review Inbox for ambiguous items and failed/uncertain extraction.
- User correction of category assignments.
- Remembered household classification rules so repeated items become easier to classify.
- Shared transaction timeline.
- Savings goals.
- Recurring expected expenses.
- Simple analytics and monthly forecast.
- Responsive PWA that works well on Android, iPhone, tablet, and desktop.
- Polish user interface and PLN formatting.
- Time zone: Europe/Warsaw.

### Not required for V1

- Live Open Banking / PSD2 integration.
- Automatic bank transaction import.
- Credit scoring.
- Tax accounting.
- Investments and brokerage aggregation.
- Multi-currency accounting.
- Complex debt tracking.
- Social features.
- Native iOS/Android apps.

The V1 architecture must leave a clear seam for future bank integrations without coupling the budget model to a bank provider.

## 3. Canonical money model

Never use floating-point values for money.

Use either:

- integer grosze in application logic, or
- PostgreSQL `NUMERIC` plus Decimal in backend code.

Whichever representation is selected must be consistent and covered by tests.

Important entities:

- User
- Household
- HouseholdMember
- Account
- BudgetPeriod
- BudgetCategory
- BudgetAllocation
- Transaction
- TransactionAllocation
- Receipt
- ReceiptItem
- Merchant
- ClassificationRule
- SavingsGoal
- RecurringTransaction
- ReviewTask
- BankConnection (future-facing interface/table only if useful)

A `Transaction` represents money movement.
A `Receipt` represents documentary evidence and item-level detail.
A `TransactionAllocation` assigns all or part of a transaction to one or more categories.
A receipt may be linked to a transaction, but it must not be the transaction itself.

Critical invariant:

> The sum of transaction allocations must equal the transaction amount before the transaction is considered fully categorized.

A receipt from one merchant may produce multiple category allocations.

Example:

- merchant: Lidl
- transaction total: 139.75 PLN
- food: 38.78 PLN
- entertainment: 17.99 PLN
- home: 12.99 PLN
- Roch hobby: 69.99 PLN

## 4. Pocket-money semantics

Pocket money must not be implemented as a normal category that later demands itemized expense tracking.

From the shared household perspective:

- household -> Roch pocket money: 600 PLN
- household -> Kaja pocket money: 600 PLN

After this transfer, downstream private spending is outside the shared budget unless the user explicitly enables personal tracking.

The dashboard must therefore be able to say that pocket money has been allocated/paid without asking for private receipt details.

## 5. Receipt flow

The ideal user flow is:

1. User taps the central Add button.
2. User chooses Scan receipt.
3. User takes or uploads a photo.
4. The app uploads the image and starts extraction.
5. The system extracts merchant, date, total, and receipt items.
6. Each item is normalized and classified.
7. High-confidence items are preselected silently.
8. Low-confidence items are highlighted for quick review.
9. User confirms or adjusts the ambiguous items.
10. The app saves the receipt, transaction, and allocations atomically/idempotently.
11. The budget dashboard updates immediately.

The interface must never force a user to classify every item if the model is already highly confident.

### Confidence policy

Use configurable thresholds rather than hard-coded UI logic.

Recommended starting behavior:

- >= 0.90: auto-accept classification.
- 0.60 to 0.89: show selected category but make review easy.
- < 0.60: create a Review Inbox task and make uncertainty obvious.

If extraction is incomplete, save the receipt as a draft rather than silently inventing data.

## 6. Classification and learning

Classification priority should be deterministic before it is generative:

1. Exact household rule.
2. Normalized item rule.
3. Merchant/category rule when appropriate.
4. AI classifier using available receipt context.
5. User review.

When a user corrects a category, create or update a household-specific rule when safe to do so.

Examples:

- "Desperados" -> Entertainment / Alcohol.
- "toilet paper" -> Home.
- "Parkside soldering iron" -> Hobby / Roch, if the household has chosen that mapping.

Do not leak one household's rules into another household.

## 7. UX and visual design principles

The application should feel closer to a premium personal-finance tool than to an admin dashboard.

Required characteristics:

- simple hierarchy;
- calm visual language;
- generous spacing;
- very clear typography;
- restrained use of color;
- one obvious primary action per screen;
- fast paths for the common flows;
- no clutter for features that are not used daily;
- no unnecessary modals;
- no data-dense enterprise tables on mobile;
- important numbers are visible before charts;
- charts support decisions rather than decorate the page.

Avoid:

- excessive gradients;
- glassmorphism everywhere;
- multiple competing accent colors;
- huge hero sections inside the authenticated app;
- cryptic icons without labels;
- nested settings that hide core functionality;
- unnecessary financial jargon.

Default visual direction:

- modern neutral surfaces;
- subtle borders and shadows;
- rounded components, but not cartoonish;
- positive state: emerald/green family;
- warnings: amber;
- destructive/over-budget: red;
- category colors may vary, but category color is secondary to labels and icons;
- use a single type system and consistent spacing tokens.

The Polish UI copy should be short and conversational, not formal banking language.

## 8. Core screens

### Mobile navigation

Bottom navigation:

- Home
- Budzet
- central Add button
- Transakcje
- Wiecej

`Wiecej` may contain Cele, Analiza, Do sprawdzenia, Konta, and Ustawienia.

On desktop, use a left sidebar with direct entries for the major areas.

### Home dashboard

Show, in this order:

1. Current month.
2. Remaining household budget.
3. Spent vs planned.
4. A concise list of main budget envelopes with progress.
5. Any Review Inbox count.
6. Recent transactions.
7. One or two useful insights only.

Do not overload Home with every analytics widget.

### Budget screen

Show:

- planned income;
- amount still unassigned;
- groups such as Needs, Lifestyle, Pocket money, Future;
- each category with planned, spent, and remaining;
- ability to edit allocations;
- strong zero-based budget feedback when unassigned amount reaches 0.

### Add screen

Prioritize:

1. Scan receipt.
2. Add expense.
3. Add income.
4. Transfer.
5. Optional document/future actions.

### Receipt review screen

Show:

- merchant;
- date;
- total;
- each item;
- current category;
- confidence/uncertainty only when useful;
- quick category chips for ambiguous items;
- final confirmation button.

The user must be able to edit OCR mistakes before confirmation.

### Transactions screen

Chronological timeline with filters.
A transaction may expand to show its allocation breakdown.

### Review Inbox

Contains only unresolved items:

- ambiguous category;
- extraction error;
- duplicate suspicion;
- unallocated transaction;
- future bank match conflict.

Every task should be resolvable in a few taps.

### Goals screen

Each goal shows:

- name;
- current amount;
- target;
- progress;
- monthly planned contribution;
- estimated target date when enough data exists.

### Analytics screen

Keep it compact.
Useful outputs:

- spending by category;
- monthly trend;
- planned vs actual;
- savings rate;
- recurring-spend trend;
- forecast to end of current month;
- a very small number of high-value insights.

Do not generate pseudo-advice with false certainty.

## 9. Technology baseline

Use a modular monolith.

Recommended repository shape:

```text
/apps
  /web        Next.js + TypeScript PWA
  /api        FastAPI
/packages
  /ui         shared design-system components/tokens if helpful
  /contracts  generated/shared schemas if useful
/docs
  /adr
  /feedback
```

Preferred frontend:

- Next.js with TypeScript.
- Tailwind CSS.
- Accessible component primitives such as shadcn/ui or equivalent.
- React Hook Form + schema validation or equivalent.
- PWA manifest/service-worker support.
- Server state handled consistently; avoid ad-hoc duplicated fetch state.

Preferred backend:

- FastAPI.
- Pydantic models.
- SQLAlchemy 2.x style or equivalent mature ORM.
- Alembic migrations.
- PostgreSQL.

Auth/storage:

- Supabase Auth is acceptable and preferred for fast delivery.
- Private S3-compatible or Supabase Storage for receipt images.
- If using Supabase Auth, API must verify tokens server-side and enforce household authorization.

AI/receipt extraction:

- Provider abstraction.
- Prefer a multimodal model that can return strict structured JSON.
- Validate all model output with schemas.
- Never trust model output directly.
- Keep a deterministic fallback/manual edit path.

Do not introduce microservices, Kafka, Kubernetes, Celery, or distributed event systems unless there is a proven need in the actual repository.

## 10. Security and privacy

Financial and receipt data is sensitive.

Required rules:

- Every data query that returns household data must be authorized against household membership.
- Never trust household_id supplied by the browser without authorization checks.
- Receipt files must be private by default.
- Use signed URLs or backend-mediated access.
- Do not log raw authentication tokens.
- Do not log full receipt images or unnecessary OCR payloads in production.
- Secrets only via environment variables/secret manager.
- Validate file type and file size.
- Protect write endpoints from duplicate submissions.
- Use idempotency for receipt finalization and future bank imports.
- Apply rate limits to expensive AI endpoints where practical.
- Add audit timestamps and creator/updater identity to important financial records.
- Provide deletion/export paths at least at a basic household-data level.

## 11. Data integrity

Add constraints and tests for:

- money precision;
- transaction allocation totals;
- household authorization;
- duplicate receipt finalization;
- duplicate/manual double submission;
- category deletion when historical transactions reference it;
- recurring transaction generation;
- budget period boundaries;
- Europe/Warsaw date handling;
- pocket-money transfer semantics.

Do not silently mutate historical months when category settings change in a later month.

## 12. Empty, loading, and error states

Every primary screen must have designed states for:

- empty household;
- no budget yet;
- no transactions;
- receipt processing;
- receipt parsing failed;
- offline/poor network;
- API error;
- expired session;
- no analytics data yet.

Use skeletons or stable loading layouts where appropriate. Avoid layout jumps.

## 13. Accessibility and responsive requirements

Minimum expectations:

- keyboard navigable desktop interface;
- visible focus states;
- labels for icon-only controls;
- semantic form labels;
- touch targets generally >= 44 px;
- no horizontal page scroll at common mobile sizes;
- color is never the only state indicator;
- contrast should meet WCAG AA for normal text;
- money values and status text remain legible at 200% browser zoom.

Required viewport checks:

- 390 x 844 mobile;
- 430 x 932 large mobile;
- 768 x 1024 tablet;
- 1440 x 900 desktop.

## 14. Tests and quality gates

The agent owns quality. A feature is not finished because it compiles.

Required before calling a milestone complete:

Frontend:

- lint passes;
- typecheck passes;
- unit/component tests pass;
- production build passes;
- Playwright critical flows pass.

Backend:

- formatting/linting passes;
- type checks if configured;
- pytest passes;
- migrations apply cleanly to a fresh database;
- API contract tests for critical routes pass.

Critical E2E flows:

1. create/login user;
2. create household and second member path;
3. create monthly budget;
4. allocate income and categories;
5. allocate pocket money;
6. add manual expense;
7. upload a receipt fixture;
8. review ambiguous receipt item;
9. confirm receipt and see budget update;
10. create/update savings goal;
11. resolve Review Inbox task;
12. verify user cannot access another household's data.

## 15. The Loop-Back Loop - mandatory feedback protocol

This project must use a closed-loop improvement cycle. Do not implement a feature once and move on blindly.

### Loop A - Internal implementation loop

For every vertical slice:

1. Define the exact user outcome and acceptance criteria.
2. Implement the smallest complete slice.
3. Run static checks and tests.
4. Launch the app locally.
5. Exercise the flow as a real user.
6. Capture screenshots for the required mobile and desktop viewports.
7. Review the result against the UX checklist below.
8. Record defects by severity.
9. Fix defects.
10. Re-run tests and re-check visuals.
11. Repeat until the slice completes two consecutive clean loops.

Severity:

- P0: broken, unsafe, data-loss/security issue.
- P1: primary flow blocked or misleading.
- P2: visible UX defect, responsiveness problem, confusing wording, inconsistent spacing, poor state handling.
- P3: minor polish improvement.

Exit rule for a milestone:

- 0 open P0;
- 0 open P1;
- 0 known P2 in primary flows;
- P3 items may remain only if explicitly documented and genuinely low value;
- two consecutive clean loop runs for the changed primary flows.

### UX review checklist used in every loop

Ask and verify:

- Is the primary action obvious within 2 seconds?
- Is there unnecessary information competing with it?
- Is the screen understandable without reading documentation?
- Can the common action be completed in <= 3 meaningful taps/clicks from Home?
- Are financial numbers visually prioritized correctly?
- Is spacing consistent?
- Are headings and body text clearly differentiated?
- Are destructive actions unmistakable?
- Is the mobile layout as intentional as desktop?
- Are loading, empty, success, and error states polished?
- Are ambiguous AI results honest about uncertainty?
- Are Polish labels concise and natural?
- Is there any horizontal overflow or clipped text?
- Are button states, disabled states, and validation feedback obvious?
- Is there any avoidable cognitive load?

### Loop B - User feedback loop

Maintain `docs/feedback/FEEDBACK_LOG.md`.

Whenever the user gives feedback:

1. Copy the feedback into the log in concise form.
2. State the product interpretation.
3. Identify affected screens/domain rules.
4. Update acceptance criteria before editing code.
5. Implement the change.
6. Run targeted tests plus regression tests for affected primary flows.
7. Re-run visual checks on relevant viewports.
8. Record what changed and how it was verified.
9. If feedback conflicts with an ADR, do not ignore it: either update/supersede the ADR or explain the conflict and ask only if the choice is materially irreversible.

If the user is not currently available, do not stall. Continue the internal loop using the product principles and accepted ADRs.

### Do not game the loop

Do not satisfy the loop by merely writing that a review was performed.
Evidence should include test output, screenshot paths, or a concise defect list and fixes.

## 16. Performance targets

For a personal two-user app, optimize for perceived speed and simplicity rather than theoretical scale.

Targets:

- authenticated page transitions feel instant after initial load;
- no obvious layout shift;
- manual transaction save should feel immediate;
- receipt upload gives progress feedback immediately;
- receipt parsing may take longer, but must expose a clear processing state;
- no unbounded queries on transaction history;
- images should be resized/compressed before or during upload when practical.

Where Lighthouse is available, aim for:

- Accessibility >= 95;
- Best Practices >= 95;
- Performance >= 85 on realistic mobile conditions for the core dashboard;
- installable PWA behavior.

These are quality targets, not excuses to hide functional regressions.

## 17. Engineering behavior

- Prefer boring, mature technology.
- Prefer vertical slices over giant refactors.
- Keep domain rules on the server, not only in UI code.
- Avoid premature abstractions.
- Do not duplicate calculation logic between frontend and backend if it can drift.
- Add migrations for schema changes.
- Seed realistic development data, but never hard-code production credentials.
- Keep `.env.example` current.
- Update documentation when architecture changes.
- Remove dead code and placeholder TODOs from primary flows before declaring completion.
- Never claim the whole product is finished after only scaffolding or mock screens.

## 18. Definition of done for V1

V1 is complete only when a user can, on both mobile and desktop:

- sign in;
- enter a shared monthly income;
- allocate all planned money including pocket money;
- see remaining amounts by category;
- add expenses manually;
- photograph/upload a mixed-category receipt;
- review only uncertain items;
- confirm the receipt;
- immediately see category budgets updated;
- browse transaction history;
- resolve review tasks;
- track at least one savings goal;
- understand current-month status from Home without reading help text.

And the repository passes the quality gates and Loop-Back Loop exit rules above.
