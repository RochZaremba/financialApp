# ADR-010: Named monthly planned income sources

Status: Accepted

## Context

The household wants to plan multiple income streams and identify their contributors while retaining one shared budget. Existing periods contain a single planned-income amount; older release images must remain usable during rollback.

## Decision

Store ordered `IncomeSource` records per household budget period with a name, integer-grosze amount and optional household member. A null member denotes shared income. The budget write validates membership and unique normalized name/member pairs, replaces the source list atomically and derives the period total from the submitted sources. Sources belong only to their month and never create actual income transactions.

Retain `Period.planned_income` as the derived total for existing analytics and older application images. Migration 005 backfills each positive existing total as “Dochód wspólny” without guessing a contributor. Legacy API writes with an unchanged total preserve named sources; a changed legacy total replaces them with a shared source. If an older image updates the total during rollback, the read API exposes that amount as a shared source rather than displaying inconsistent personal income. The next source-list write reconciles the records.

## Consequences

Names and attribution stay independent across months. Export and household deletion include the new records. Repeated PUTs cannot append duplicates. The trusted deployment receiver starts rollback images directly with Uvicorn, bypassing the older image’s Alembic bootstrap, which cannot resolve revision 005. An image rollback does not require dropping the table; a schema downgrade refuses to discard existing sources. There is no new split/contribution model or automatic bookkeeping.
