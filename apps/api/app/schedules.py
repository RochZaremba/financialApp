"""Calendar-date schedules; month ends retain the original anchor day."""

import calendar
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_, select
from .config import WARSAW
from .models import Recurring, Transaction


def occurrence_dates(row, start: date, end: date):
    anchor = row.start_date
    if row.frequency == "weekly":
        if not anchor:
            return []
        cursor = anchor + timedelta(days=max(0, (start - anchor).days + 6) // 7 * 7)
        dates = []
        while cursor <= end:
            dates.append(cursor)
            cursor += timedelta(days=7)
        return dates
    stride = {"monthly": 1, "quarterly": 3, "yearly": 12}[row.frequency]
    anchor = anchor or date(start.year, start.month, 1)
    anchor_index = anchor.year * 12 + anchor.month - 1
    first = start.year * 12 + start.month - 1
    last = end.year * 12 + end.month - 1
    dates = []
    for index in range(max(first, anchor_index), last + 1):
        if (index - anchor_index) % stride:
            continue
        year, month0 = divmod(index, 12)
        due = date(year, month0 + 1, min(row.day, calendar.monthrange(year, month0 + 1)[1]))
        if start <= due <= end and (not row.start_date or due >= row.start_date):
            dates.append(due)
    return dates


def next_occurrence(row, after):
    limit = date(min(after.year + 2, 2101), 12, 31)
    return next(iter(occurrence_dates(row, after, limit)), None)


def period_rows(db, household_id, rows, start, end, now):
    transactions = list(
        db.execute(
            select(Transaction.source_id, Transaction.date, Transaction.idempotency_key).where(
                Transaction.household_id == household_id,
                Transaction.source == "recurring",
                or_(
                    Transaction.date.between(start, end),
                    *[
                        Transaction.idempotency_key.like(f"recurring:%:{index // 12:04d}-{index % 12 + 1:02d}%")
                        for index in range(start.year * 12 + start.month - 1, end.year * 12 + end.month)
                    ],
                ),
            )
        )
    )
    dates_paid = {(r[0], r[1]) for r in transactions}
    keys_paid = {r[2] for r in transactions}
    result = []
    for row in rows:
        due_dates = occurrence_dates(row, start, end)
        for due in due_dates or [next_occurrence(row, end + timedelta(days=1)) or end]:
            scheduled = bool(due_dates)
            paid = (
                (row.id, due) in dates_paid
                or f"recurring:{row.id}:{due.isoformat()}" in keys_paid
                or (row.frequency == "monthly" and f"recurring:{row.id}:{due:%Y-%m}" in keys_paid)
            )
            status = "overdue" if due < now else "upcoming" if due <= now + timedelta(days=row.reminder_days) else "later"
            result.append(
                dict(
                    id=row.id,
                    name=row.name,
                    amount=row.amount,
                    day=row.day,
                    frequency=row.frequency,
                    start_date=row.start_date,
                    reminder_days=row.reminder_days,
                    category_id=row.category_id,
                    account_id=row.account_id,
                    active=row.active,
                    paid=paid,
                    scheduled=scheduled,
                    due_date=due,
                    reminder_status=status if scheduled and row.active and not paid else None,
                )
            )
    return result


def unpaid_period(db, household_id, rows, month):
    """Unpaid expectations in one month, without the reminder UI's backlog limit."""
    from .domain import month_dates, today

    start, end = month_dates(month)
    earliest = {r.id: r.start_date or r.created_at.astimezone(WARSAW).date().replace(day=1) for r in rows}
    return [
        r
        for r in period_rows(db, household_id, rows, start, end, today())
        if r["active"] and r["scheduled"] and not r["paid"] and r["due_date"] >= earliest[r["id"]]
    ]


def reminders(db, household_id, now):
    rows = list(db.scalars(select(Recurring).where(Recurring.household_id == household_id, Recurring.active.is_(True))))
    result = []
    # Bound the backlog to the past year; never invent expectations before creation.
    for row in rows:
        start = max(now - timedelta(days=366), row.start_date or row.created_at.astimezone(WARSAW).date().replace(day=1))
        end = now + timedelta(days=row.reminder_days)
        result.extend(r for r in period_rows(db, household_id, [row], start, end, now) if r["scheduled"] and not r["paid"])
    return sorted(result, key=lambda r: (r["due_date"], r["id"]))[:100]


def calendar_text(rows, now):
    def escape(value):
        return str(value).replace("\\", "\\\\").replace("\r", "").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Razem//Platnosci//PL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Razem - płatności",
    ]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    end = min(date(2100, 12, 31), now + timedelta(days=366))
    for row in rows:
        if not row.active:
            continue
        for due in occurrence_dates(row, now, end):
            amount = f"{row.amount // 100},{row.amount % 100:02d} zł"
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{row.id}-{due.isoformat()}@razem.local",
                    f"DTSTAMP:{stamp}",
                    f"DTSTART;VALUE=DATE:{due:%Y%m%d}",
                    f"DTEND;VALUE=DATE:{due + timedelta(days=1):%Y%m%d}",
                    "SUMMARY:" + escape(row.name),
                    "DESCRIPTION:" + escape(f"{amount}. Po zapłacie potwierdź wydatek w Razem."),
                    "BEGIN:VALARM",
                    f"TRIGGER:-P{row.reminder_days}D" if row.reminder_days else "TRIGGER:PT0M",
                    "ACTION:DISPLAY",
                    "DESCRIPTION:" + escape("Płatność: " + row.name),
                    "END:VALARM",
                    "END:VEVENT",
                ]
            )
    lines.append("END:VCALENDAR")
    # RFC 5545 folding counts UTF-8 octets, preserving character boundaries.
    folded = []
    for line in lines:
        current = ""
        for character in line:
            if len((current + character).encode()) > 74:
                folded.append(current)
                current = " " + character
            else:
                current += character
        folded.append(current)
    return "\r\n".join(folded) + "\r\n"
