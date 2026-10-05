# ADR-001: Product and budgeting model

Status: Accepted

## Context

The first real users are a couple managing a shared household budget. Their preferred model is to treat household income as shared, allocate it to monthly purposes, and give each member a fixed personal pocket-money amount.

Private spending after pocket-money transfer should not be required for household reporting.

## Decision

Use a zero-based monthly household budget as the primary V1 model.

- Income enters the household budget.
- Money is allocated to categories/envelopes.
- Savings contributions are valid allocations, not leftovers.
- Pocket money is a terminal household transfer to a member.
- Shared spending is tracked against budget categories.
- Mixed receipts are allocated per item.

The domain model should not prevent future 50/50 or proportional-contribution modes, but those modes are not required in the initial UX.

## Consequences

Positive:

- Simple mental model.
- Household and private spending are clearly separated.
- Monthly planning can drive a clear "unassigned = 0" state.

Trade-off:

- Users wanting detailed personal accounting need an optional later mode.
