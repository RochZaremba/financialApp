# ADR-004: AI receipt extraction and classification

Status: Accepted

## Context

The most valuable interaction is taking a receipt photo and having the system understand mixed purchases with minimal manual work.

AI output can be wrong and must not be treated as trusted database input.

## Decision

Use a structured, validated receipt-processing pipeline:

1. Upload private image.
2. Extract structured receipt data with a multimodal AI provider or equivalent OCR+LLM flow.
3. Validate output against a strict schema.
4. Normalize item names.
5. Apply household-specific deterministic rules first.
6. Use AI classification for unresolved items.
7. Attach confidence.
8. Auto-accept high-confidence items.
9. Send ambiguous items to Review Inbox.
10. Allow user correction.
11. Learn safe household-specific rules from corrections.

The AI provider must be behind an interface so models/providers can change without rewriting the domain.

## Consequences

The app can feel automatic while preserving an explicit human correction path and preventing silent fabrication.
