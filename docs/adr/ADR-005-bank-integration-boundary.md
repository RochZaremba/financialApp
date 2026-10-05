# ADR-005: Bank integration boundary

Status: Accepted

## Context

Open Banking integration is desirable but should not block the first useful version.

## Decision

V1 works completely without a live bank connection.

The data model must support future imported bank transactions.
Future integration will treat bank feeds as one source of Transaction records.
Receipts will enrich/match those transactions rather than become a separate duplicate expense.

Likely matching signals:

- amount;
- date/time window;
- merchant text;
- account;
- optional user confirmation.

Do not tie domain entities to a specific PSD2 aggregator.

## Consequences

Receipt capture and budgeting can ship earlier, while later bank integration has a clean insertion point.
