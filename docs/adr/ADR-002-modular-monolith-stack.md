# ADR-002: Modular monolith and technology stack

Status: Accepted

## Context

The application is initially for two users. The main complexity is product polish, financial data integrity, receipt processing, and AI classification, not distributed scale.

## Decision

Use a modular monolith with a separate web frontend and API in one repository.

Preferred stack:

- Web: Next.js + TypeScript + Tailwind CSS.
- UI primitives: accessible headless/shadcn-style components.
- API: FastAPI + Pydantic.
- Persistence: PostgreSQL.
- ORM/migrations: SQLAlchemy + Alembic or equivalent mature tooling.
- Authentication: Supabase Auth is preferred for fast delivery.
- Receipt storage: private Supabase Storage or other S3-compatible object storage.
- PWA support for Android and iOS home-screen usage.

## Rejected

- Native mobile apps for V1.
- Microservices.
- Kubernetes.
- Event streaming infrastructure.
- Splitting receipt AI into a separate deployed service before there is evidence it is needed.

## Consequences

The product remains simple to run and deploy while preserving a clean service boundary between UI and business logic.
