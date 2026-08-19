# ADR 0004: Pseudonymised, opt-in audit logging in the web application

- Status: Accepted
- Date: 2026-08-19

## Context

The web application logs lifecycle markers and a scan uuid, deliberately and
nothing else: a log of what everybody scanned is a database of what everybody
scanned. An operator running the service for other people still has questions
that log cannot answer - whether one network is submitting scans continuously,
whether the client limit and the target cooldown actually trigger, and whether
somebody is probing the submission endpoint with fields it does not accept.

Recording requests answers those questions and creates exactly the database
the current rule exists to prevent. The decision is how to have both.

## Decision

A separate audit log on the `check_opencloud.web.audit` logger, one JSON
object per line, disabled unless `COS_WEB_AUDIT_LOG` turns it on. It records
three events - `scan_requested`, `rate_limited` and `submission_rejected` -
each with a UTC timestamp.

Identifiers are pseudonyms, not identities:

- A client address is always a truncated HMAC under an audit salt. No setting
  writes an address, and the audit log has no access to one afterwards.
- The target is a fingerprint under the same salt unless
  `COS_WEB_AUDIT_LOG_TARGETS` is set, which a deployment scanning its own
  estate may want and a public one should not.
- The salt is random per process unless `COS_WEB_AUDIT_SALT` is set, so
  correlation across a restart is a deliberate act that rotating the salt
  reverses.
- A rejected submission records a fixed reason code and, for unsupported
  fields, the submitted names shortened, stripped of control characters and
  JSON-escaped, so a request body cannot forge a record.

## Consequences

The default deployment is unchanged and still logs lifecycle markers and
uuids only. An operator who turns the audit log on can correlate requests
within one process lifetime, measure their limits and see rejected probes,
without holding addresses. Retention becomes their responsibility: the audit
log is the one part of this service that outlives Redis' TTLs.

Fingerprints are not reversible, so an audit record cannot be used to answer a
question about a specific named requester or, by default, a specific named
instance. That is the trade being made rather than a gap to close later.

## Alternatives considered

### 1. Keep logging lifecycle markers only

It leaves an operator unable to tell abuse from popularity, and unable to
verify that the limits do anything. The questions do not go away; they get
answered by adding `print` statements to a fork.

### 2. Log addresses and targets in the clear behind one switch

Simple, and it makes the service's central promise conditional on a setting
nobody reviewing a deployment can see. Fingerprints answer the operational
questions - repetition, correlation, limits - without keeping the identity.

### 3. Store the audit trail in Redis alongside the scans

It would inherit the TTLs, but a uuid namespace is a capability handed to a
visitor, and an operator's audit trail with a one-hour lifetime is not an
audit trail. Logs are already routed, rotated and retained by the platform.
