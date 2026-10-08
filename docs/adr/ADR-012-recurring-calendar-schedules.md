# ADR-012: Date-based recurring expectations and reminders

Status: Accepted

## Decision

Recurring records support weekly, monthly, quarterly and yearly calendar schedules. Nonmonthly schedules require an anchor date. Month ends clamp to the last day without changing the original day; leap-year anniversaries retain their original anchor. Existing monthly rows retain their behavior.

Each occurrence remains an expectation until confirmed. Its stable household/record/date key makes payment confirmation idempotent. A legacy monthly key remains recognized. Forecasts count only occurrences within the selected month, and Home highlights unresolved approaching or overdue dates in Europe/Warsaw. The overdue list is bounded to the past year and never predates the explicit anchor or creation month.

Reminder lead time is configurable from 0 to 30 days. Private authorized calendar export enumerates dates for the coming year with RFC 5545 alarms and stable UIDs. Users import the file and reimport after schedule changes; the app does not claim to send background push notifications. The database downgrade refuses to discard configured schedules.

## Consequences

Annual records remain editable in months when they are not due. Weekly records can have several separately confirmed occurrences per month. Confirmation records the selected occurrence date, rather than silently moving all payments to the current day. Calendar files contain financial names and amounts and require household membership.
