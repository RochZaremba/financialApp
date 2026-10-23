# ADR-018: Single-account emergency recovery grants

Status: Accepted

## Context

The deployment owner cannot reach the trusted host and no application administrator has been provisioned. A universal password would expose every account, including administrators. The owner requested immediate recovery for one ordinary account through the existing tested delivery pipeline.

## Decision

Extend ADR-008/016 with explicit, individually reviewed emergency grants. Each grant contains only a random identifier, an exact normalized email digest, an Ed25519 verification public key and an absolute validity interval of at most 24 hours. There is no universal signing authority: every grant has its own ephemeral private key, used once by the maintainer's local issuance tool and then discarded. The tool writes the signed bearer token only to a private file outside the repository. Tokens and private keys never enter source control, images or release artifacts.

Public grant metadata is reviewed and delivered as application configuration through the protected PR/release pipeline. By default the grant list is empty. A grant authorizes setting a new password only for its bound ordinary account; it cannot create a user, grant a role, reset administrators or act as a login password. A public recovery form accepts the email, token and a confirmed new password. Tokens are submitted in the request body, never a query parameter. Signature, exact target, absolute expiration, CSRF and rate limits are checked server-side.

The user row is locked; consumption, password replacement, session revocation and audit commit atomically. A durable unique grant-use record prevents replay after restart, rollout or image rollback. Consumption records survive account deletion, and downgrade refuses to discard them. Success requires a normal login with the new password. Errors do not disclose account existence. Expiration and consumption invalidate a token independently of a later cleanup release.

## Consequences

The repository maintainer remains a trusted deployment authority. Recovery requires a new reviewed delivery for a specific account, not knowledge of a master password. Remove expired public grants in a subsequent release; removal does not replace the mandatory expiration and replay protections. This incident mechanism does not claim to implement email ownership verification or a self-service email reset service.
