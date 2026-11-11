"""Derived earmarking: reserve covers overruns without duplicating spending."""

from .money import divide_money


def buffer_data(allocations, category_id, planned_income):
    buffer = next((a for a in allocations if a["kind"] == "category" and a["reference_id"] == category_id), None)
    if not buffer:
        return None
    # The monthly buffer gets whatever remains after every other planned commitment.
    automatic = max(0, planned_income - sum(a["amount"] for a in allocations if a is not buffer))
    buffer["amount"] = automatic
    buffer["remaining"] = automatic + buffer.get("carry_in", 0) - buffer["spent"] - buffer.get("reserved_out", 0)
    recipients = sorted((a for a in allocations if a is not buffer and a["remaining"] < 0), key=lambda a: (a["kind"], a["reference_id"]))
    deficits = [-a["remaining"] for a in recipients]
    needed = sum(deficits)
    pool = max(0, buffer["remaining"])
    covered = min(pool, needed)
    shares = divide_money(covered, deficits)
    details = []
    for row, deficit, share in zip(recipients, deficits, shares, strict=True):
        row["raw_remaining"] = row["remaining"]
        row["buffer_received"] = share
        row["remaining"] += share
        details.append(
            dict(
                kind=row["kind"],
                reference_id=row["reference_id"],
                label=row["label"],
                overrun=deficit,
                covered=share,
                uncovered=deficit - share,
            )
        )
    buffer["remaining"] -= covered
    buffer["buffer_used"] = covered
    return dict(
        category_id=category_id,
        label=buffer["label"],
        planned=automatic,
        direct_spent=buffer["spent"],
        available_before_cover=pool,
        covered=covered,
        uncovered=needed - covered,
        remaining=buffer["remaining"],
        recipients=details,
    )
