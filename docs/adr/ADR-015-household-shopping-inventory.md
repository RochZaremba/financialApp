# ADR-015: Shared shopping, purchase history and home inventory

Status: Accepted

## Decision

Household shopping is a separate module in the existing monolith. A pending shopping item plans a product and optional total estimated cost; confirming it records its purchase snapshot and may create an inventory batch. Neither operation creates a financial transaction. Users explicitly enter an expense or finalize a receipt through existing financial flows. Optional purchase prices are integer grosze; unknown prices remain null and estimates display the number of unpriced items.

Quantities use integer thousandths of the declared unit (pieces, packages, kg, g, l, ml), consistently in PostgreSQL, Python and TypeScript. Different declared units are not silently mixed or converted. Inventory batches retain their own expiry date and storage location: fridge, freezer, pantry or household cupboard. Consumption cannot underflow. Minimum-stock suggestions aggregate compatible batches, exclude expired quantities and products already on the pending list. The maximum minimum across compatible batches is the shared threshold rather than summing several copies of the same target.

Every route uses server membership authorization. Writes serialize on the household, use exact revision checks for edits/consumption and durable household-scoped idempotency for retries. Purchase confirmation, history and stock creation commit atomically. History snapshots stay after inventory deletion; purchased list entries cannot be independently edited as pending products. Reads bound the pending list and inventory to 500 entries each; history uses stable server pagination and literal date/text filters.

Receipt import is explicit and only accepts positive product lines from a confirmed receipt. Users supply quantity, unit, location and optional expiry; unreadable OCR quantity is never invented. A unique receipt-item reference prevents repeated replenishment. Users can explicitly link a current pending list item with its reviewed revision; import then completes that item instead of leaving a duplicate pending purchase. It leaves the existing receipt transaction and category allocations unchanged. The import screen warns against adding products already entered into stock manually.

Migration 009 is additive and compatible with the previous image. Export and household deletion include both new tables; downgrade refuses to discard real shopping or inventory records.

## Consequences

Shopping planning works without AI, bank connections, push notification services or a recipe database. Initial fridge contents may be entered without inventing purchase history or spending. Stock quantities reflect household confirmations and consumption; the application does not claim to know unrecorded physical changes. Expiry labels are reminders based on packaging dates. Imported receipt discounts stay in their existing financial allocation rather than becoming physical stock.
