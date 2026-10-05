# ADR-006: UX quality and Loop-Back Loop

Status: Accepted

## Context

The product will fail if entering data feels like bookkeeping. Visual quality, clarity, responsiveness, and friction are product requirements, not post-release polish.

## Decision

Every feature is developed through a mandatory Loop-Back Loop:

1. Define outcome and acceptance criteria.
2. Implement a complete vertical slice.
3. Run automated checks.
4. Exercise the flow in a running browser.
5. Capture mobile and desktop screenshots.
6. Review hierarchy, spacing, copy, states, responsiveness, and speed.
7. Record defects by severity.
8. Fix them.
9. Regression test.
10. Repeat until two consecutive clean loops.

Milestone exit rules:

- zero P0;
- zero P1;
- zero known P2 in primary flows;
- primary flows pass twice consecutively after fixes.

User feedback is also a loop input. It must be logged, translated into acceptance criteria, implemented, verified, and regression-tested.

## Consequences

The agent is not allowed to treat "build passes" as equivalent to "feature is done".
