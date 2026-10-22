# ADR-016: Administrator-assisted account recovery

Status: Accepted

## Decision

The deployment owner may provision an administrator from the trusted server with `python -m app.create_admin email@example.com`. The command creates an account with a hidden, confirmed password prompt or grants the role to an existing account without changing its password. Existing sessions are revoked when granting access. Public registration never accepts administrator status, and demo accounts cannot be provisioned or entered through passwordless demo login as administrators.

Administrators use `/administrator`, independently of household membership, to set an ordinary user's new password by exact email. Every request requires a current authenticated administrator session and verification of the administrator's password; attempts are rate-limited. Passwords retain whitespace and normal 10–128 character validation. Successful changes atomically replace the hash, revoke all target sessions, and persist actor/target/timestamp audit metadata without passwords. Login and reset serialize on the user row so a login with the old password cannot race session revocation. Existing household authorization remains in force; the role grants no direct financial-data access.

Administrator passwords continue to use owner-assisted server recovery (`app.reset_password`); the browser panel cannot reset another administrator or its own account. There is no public recovery token, automatic email delivery, hard-coded administrator password, or automatic promotion of a first/demo user.

## Consequences

This extends ADR-008 with a small recovery panel while keeping provisioning and recovery of the highest-privilege accounts on the trusted host. The administrator must verify the requester's identity and deliver the chosen password privately. The additive migration defaults every existing account to non-administrator and refuses to discard active administrator roles or recovery audit records on downgrade.
