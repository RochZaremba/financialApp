# ADR-021: Measurement time and household context

Status: Accepted. Extends ADR-019's daily readings without changing their uniqueness.

Readings optionally carry a Warsaw wall-clock measurement time (HH:MM), four explicit boolean activity answers (cooking, oven, washing machine, dishwasher) and a note of at most 240 characters. Missing activity means unknown, distinct from false. Activities describe the interval since the previous reading; they do not establish which appliance consumed the measured energy. The UI pre-fills the current Warsaw clock, offers clearable yes/no choices, resets context after save and preserves it on correction. Creation date/time is displayed separately from measurement date/time.

Migration 014 is additive: old rows receive no measurement clock, empty activities and an empty note. Existing creation timestamps are not relabelled as measurements. Old clients may omit new fields on edits without erasing their values; explicit null/empty values clear them. Existing images can continue inserting through database defaults. A downgrade refuses to discard populated context.

When both neighboring clocks are known, convert their local date/time to UTC and divide consumption by actual elapsed seconds for the daily average, rounding half-up to thousandths. This handles 23/25-hour daylight-saving days. If either clock is unknown, retain the previous calendar-day approximation and label it accordingly. Nonexistent/ambiguous transition times and future times are rejected with a clear message; users may omit an unknown clock. One cumulative reading per meter/day and all monotonicity, authorization, revision and idempotency rules remain in force.

History/chart details, household export and existing MCP tools expose the same context. No device-level energy estimate, causal assertion or financial entry is generated.
