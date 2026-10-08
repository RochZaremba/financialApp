# ADR-011: Native account balances and PLN valuation

Status: Accepted

User request extends V1 to foreign account balances (PLN, EUR, USD, GBP, CHF), without introducing multi-currency transaction accounting. Existing accounts default to PLN. Native balances remain integer minor units. Budget movements remain PLN and foreign accounts are excluded and rejected at server transaction/recurring boundaries.

The API values each native balance using the latest published NBP table A average rate, Decimal and half-up rounding to integer grosze. The total sums those valuations only if all accounts can be priced. Show rate/date and stale or unavailable states honestly. Fetch one HTTPS table with bounded timeout; cache for one hour, throttle failed retries, retain last good table in process. A restart during an NBP outage has no cached table and displays unavailable valuation. Rates do not rewrite history or account balances and are indicative, not bank execution rates. No credentials or household data are sent to NBP.

Migration is additive and refuses destructive downgrade with foreign accounts. Older images do not understand foreign accounts and must not process financial writes after these accounts are created; rollback requires maintenance until a compatible image is restored.
