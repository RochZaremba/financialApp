# ADR-019: Optional utility meters and reviewed vision readings

Status: Accepted

## Decision

Keep household utility meters separate from financial transactions and receipts. A named meter declares kWh, m³ or GJ and an optional reading interval (0 disables in-app reminders). Cumulative readings use integer thousandths of that declared unit. Readings are dated, unique per meter/day and must fit monotonically between adjacent readings; replacements/reset counters use a new named meter. Arbitrary calendar gaps are allowed. Consumption is the difference between adjacent confirmed readings; average daily usage divides by actual elapsed days and rounds half-up to a thousandth. Never interpolate daily measurements or invent a zero baseline from a lone reading.

Members may privately upload a sanitized image and explicitly request the configured Gemini/OpenAI vision provider. A validated structured proposal is documentary evidence, never an automatic saved reading. Users confirm/correct its numeric value and date. Failures preserve the saved photo and a manual path, with safe provider/HTTP error codes. Paid uploads are rate-limited and durably idempotent. Provider fixtures recognize only the exact synthetic fixture in non-production. Images are served only after household/meter authorization and share the already backed-up private image volume; export and household deletion include the records/files.

Writes serialize household then meter and protect edits/deletes with revisions. Original recorder audit metadata is retained. Histories are bounded to 500 recent readings for display (older records remain exportable); charts show the latest six actual intervals with explicit units and an accessible numerical history. Plans are reminders on the meter screen, not background emails or push notifications. No bill, price estimate, budget movement, cross-meter unit conversion or paid automatic polling is introduced.

## Consequences

The module works manually without AI credentials and is optional in household navigation. Meter units cannot change after creation. Changing/deleting a reading recalculates adjacent intervals without touching finances. An additive migration preserves previous images; schema downgrade refuses to discard meter data. Public delivery uses the existing protected PR/release process.
