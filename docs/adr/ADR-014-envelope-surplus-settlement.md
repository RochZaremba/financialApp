# ADR-014: Immutable monthly envelope surplus settlement

Status: Accepted

## Decision

A completed planned month can be settled once, after all expenses have categories and pocket-money/goal commitments have been paid or the plan has been corrected. Users select positive active-category envelope amounts. Their sum must fit both net plan money and actual recorded income plus incoming carry after all shared spending, pocket transfers and savings. Positive envelopes cannot bypass overspending elsewhere.

Carry creates a separate earmarked ledger into the immediately following month. It changes neither bank balances nor income sources nor actual income; edits of the target month's new plan cannot erase incoming funds. Distribution uses user percentages in integer basis points, exact largest-remainder grosze, a sufficiently funded PLN source and other PLN savings accounts with optional household goals. The user explicitly confirms performed transfers and their date in the following month. Recorded transfers affect account/goal balances while reserving source-month surplus; they do not consume next month's new income twice.

The server locks the household, validates every reference and requires a fingerprint of the reviewed plan, balances and choices. A unique household/source-month settlement plus the confirmed-request fingerprint makes retries safe. The settled source's plan and financial movements cannot subsequently change; target carry does not drift with later settings. Each source envelope displays the amount settled separately from actual spending. Transfers belonging to a settlement cannot be edited independently. Distribution proportions are remembered for the next settlement. Export and household deletion include both records.

## Consequences

Settlement explicitly closes the source month. This is stated before confirmation; ordinary ongoing-month planning and entry remain unaffected. The UI requests a final review because historical correction after closing is not currently supported. Surplus is based on recorded actual income; opening account balances alone are not treated as earned monthly income. Partial selected amounts may leave unselected money in the closed source. Schema downgrade refuses to discard settlements or saved ratios. The app records transfers, never instructs a bank to perform them.
