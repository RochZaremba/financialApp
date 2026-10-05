# ADR-009: Merge-only delivery to Oracle

Status: Accepted

## Context

The private production application runs on an ARM64 Oracle host with existing system Caddy and persistent household data. The maintainer wants tested updates and GitHub Releases automatically after merging a PR into main, without deployment on direct pushes or unmerged contributions.

## Decision

- Protect main with a required full quality gate and PR-only squash merges.
- Verify contributions without production credentials. A closed-and-merged PR triggers delivery of its exact `merge_commit_sha`; never run an unmerged fork with secrets.
- Repeat quality gates, build native ARM64 API/web images, exercise a fresh HTTPS production stack and the actual receipt-backup helper, then package those tested images with metadata and checksums.
- Use a dedicated restricted SSH key and a trusted receiver installed on Oracle. Preserve the finance Compose project, private environment and PostgreSQL/receipt volumes. Infrastructure configuration remains administrator-managed.
- Serialize deployments, finish in-flight writes, stop web/API, take private database/receipt backups and check origin/public health before updating current.
- Publish a GitHub Release for that commit only after a successful deployment. Same-version retries are idempotent; older deliveries are refused.
- Restore previous images on failure. Never automatically downgrade the schema or replace production data. Migrations must remain compatible with the previous image.
- Run browser checks in the official Playwright image matching the lockfile version on AMD64 and ARM64; preserve screenshots and test evidence as temporary Actions artifacts.

## Consequences

Application updates do not require rebuilding on Oracle or changing its existing Caddy sites. Production database and AI secrets stay on the host; public release packages contain images and metadata only.

Updates have a brief maintenance window. Off-host backup retention and recovery drills remain operational responsibilities. Topology/receiver changes require a separate administrator update. Fast consecutive merges may replace an older pending Actions delivery with the newest one; active deployment is not canceled. Details and commands are maintained in [CI/CD](../CI_CD.md).
