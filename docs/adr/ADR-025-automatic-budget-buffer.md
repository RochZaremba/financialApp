# ADR-025: Monthly automatic budget buffer

Status: Accepted. Extends ADR-001/014.

A monthly plan may nominate one category as its buffer. Existing open plans with exactly one envelope labelled Bufor are initialized to that category; closed months are untouched. A new plan can select it explicitly. Save the monthly category identity rather than infer from a later rename. After other commitments the buffer receives the remaining nonnegative planned income; an overallocated plan never invents reserve money.

Derive cover from actual net category/pocket/goal overruns and the buffer's available allocation/carry after direct spending/reserved surplus. Cover only available funds; split shortage fairly using deterministic largest remainders in integer grosze. Keep original plan and actual spending intact, expose raw overrun, covered and still-uncovered amounts per envelope, and subtract total cover from remaining buffer. The buffer detail lists each recipient and amount. Refunds/corrections automatically release unnecessary cover. This is earmarking within a plan, never another financial transaction or income. Totals conserve money and closed history remains based on its immutable plan/movements.
