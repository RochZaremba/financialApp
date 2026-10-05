# ADR-003: Transactions, receipts, and allocations

Status: Accepted

## Context

A bank transaction describes money movement. A receipt describes the goods/services purchased. One receipt can span multiple budget categories.

Future bank integration must not cause duplicate spending when a receipt already exists.

## Decision

Model these concepts separately:

- Transaction: financial movement.
- Receipt: documentary source.
- ReceiptItem: extracted line item.
- TransactionAllocation: split of a transaction into budget categories.

A receipt may link to a transaction.
A transaction may exist without a receipt.
A receipt may temporarily exist as a draft before its transaction is finalized.

The sum of allocations must equal the transaction amount before the transaction is fully categorized.

Use idempotency for receipt finalization.

## Consequences

This makes item-level categorization straightforward and allows future bank transaction matching without redesigning the budget model.

Release clarification (2026-10-05): draft receipt lines may retain unknown amounts as null; finalization requires complete financial fields. Quantity is optional documentary information: unreadable quantities stay empty and are never invented. Receipt discounts use signed integer grosze and reduce the associated purchase category. Final transaction allocations remain positive, omit zero-net categories and equal the positive total. Upload retries use household-scoped idempotency, with a per-operation PostgreSQL advisory lock so OCR does not block unrelated budget writes. Downgrades never discard partial/discount receipt data.
