# ADR-026: Explicit bank balance alignment

Status: Accepted. Extends ADR-022's default of displaying genuine differences: the user now explicitly requests a reconciliation action.

The configured bank owner may align an application's mapped PLN account to a displayed booked bank snapshot. Show current bank/app values, the signed correction and snapshot time before confirmation. Serialize on the household and reject stale bank balance/time or app balance. Use normal request idempotency.

Append an immutable account adjustment containing account, signed difference, before/after values, bank snapshot time and author/timestamps. Add adjustments exactly once in account balance arithmetic; do not modify opening balances, insert expense/income, change categories or alter bank data. Expose adjustment history and export/delete it safely. Later financial entries still change the balance: the UI explicitly asks to review pending history before aligning and explains that posting history later can change it again. This is a deliberate correction of the currently recorded ledger, not a silent continuous auto-balancer.
