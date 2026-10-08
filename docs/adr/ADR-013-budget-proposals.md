# ADR-013: Review-only budget proposals

Status: Accepted

## Decision

Budget assistance proposes allocations for every active household category, including zero allocations. The browser supplies its current unsaved draft; planned income, personal pocket money and savings-goal commitments are preserved. Only explicit application changes the draft; a separate ordinary save writes the plan.

The history option uses bounded six-month household aggregates, scheduled expenses and current weights, with integer largest-remainder allocation. It is clearly labeled as history, never AI. Sparse history and insufficient income for scheduled expenses produce explicit assumptions. AI uses the configured OpenAI or Gemini provider, receives category names, aggregate amounts and user preferences, and never receives receipts, item text, member identities or account details.

Structured provider output is validated again on the server: exact household category set, no duplicates, integer nonnegative grosze and exact sum. Invalid, incomplete or unavailable output cannot be applied or saved. Rate limits bound expensive calls. The UI rejects applying a proposal after the underlying draft changes. No provider is silently called by loading a screen, and the UI explains what will be sent before requesting AI.

## Consequences

No model advice is treated as certain or as an automatic bank movement. Automated verification uses mocked providers and deterministic history rather than paid calls. `BUDGET_AI_PROVIDER=auto` reuses the receipt provider; `history` disables model assistance while keeping history assistance available.

Incoming envelope carry is already earmarked money. Proposal allocations assign only new income. Scheduled-expense minimums subtract that category's carried amount, so a carried envelope is not funded twice; carry remains independent of applying or saving a proposal.
