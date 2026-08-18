# ADR 0002: No cross-request scan result caching

- Status: Accepted
- Date: 2026-08-18

## Context

The web application could improve performance by caching scan results and
returning them to subsequent requests for the same instance (or instance URL)
within a configurable window (e.g. 5-10 minutes). This would reduce load on
the scanner and the instance being scanned.

However, this decision must account for data protection regulations, security
principles, and audit trail requirements that apply to security scan results.

## Decision

Scan results are **not** cached or reused across requests. Each submission
receives its own UUID and initiates a fresh scan, even if an identical target
was scanned moments before. The `target_cooldown` mechanism (configured via
`COS_WEB_TARGET_COOLDOWN`, default 5 minutes) prevents rapid re-scanning of
the same hostname to protect instances from DOS-like request storms, but does
not attempt to share results.

Every scan is independent, isolated under its own UUID namespace in Redis,
and expires in full when its TTL elapses.

## Consequences

**Performance**: Repeated scans of the same instance require repeated work.
High-traffic instances (in shared environments) may see elevated resource use.
The cost is accepted as the price of correct data protection and security.

**Audit trail**: Each scan has a unique UUID and its own lifecycle record,
making it clear who scanned what and when, even if the target is identical.
This supports compliance audits and incident investigation.

**Freshness**: Every scan reflects the current state of the instance. A
vulnerability discovered between scans will be found by the next scan, not
hidden behind a cached result from before the discovery.

**Isolation**: Scan results never cross user boundaries. A request for
`instance-a.example.com` cannot receive the cached result of another user's
scan of the same instance, even if that result would be technically correct
and current enough.

## Alternatives considered

### 1. Cache with explicit consent
Offer caching as an opt-in parameter (`?use_cache=true`). The request chooses
to accept stale data in exchange for faster response. This was rejected because:
- A public service should not place the burden of security trade-offs on the
  user; security defaults must be conservative.
- Without documentation of when the result was generated, users may not
  understand the risk of relying on a cached scan.
- Even with consent, sharing scan results across different network sources
  raises GDPR and privacy questions (see below).

### 2. Cache for the same user/source IP
Store the requestor's IP/fingerprint alongside the result and serve it back
only to the same source. This was rejected because:
- IP addresses are personally identifiable information under GDPR and should
  not be stored alongside security findings.
- Source IP may change between legitimate requests from the same organization
  (mobile workers, failover, VPN).
- Still does not address the instance owner's rights over their scan data.

### 3. Cache with instance owner's consent
Require the instance to serve a `/.well-known/cos-scan-cache-consent` token
that authorizes caching. This was rejected because:
- Adds complexity and a new security boundary.
- Still does not ensure that the person requesting the scan has authority to
  see it, or that the cached result is visible only to authorized parties.
- Deployment burden on operators who might not understand the implications.

### 4. Server-side caching of intermediate steps
Cache the results of individual probes or findings (e.g. certificate checks,
version detection) but assemble a fresh result document for each request. This
was rejected because:
- Intermediate results are just as sensitive as the final rating.
- Implementation adds significant complexity to maintain consistency across
  cache boundaries.
- Still requires a decision about TTL and freshness that ultimately falls back
  to the same principles as full caching.

## Data protection and security rationale

**Privacy (GDPR Article 5, data minimization)**
Scan results contain security findings, configuration details, and version
information about an OpenCloud instance. Sharing this data across different
requesters without explicit consent from the instance owner violates the
principle of data minimization. The requestor is an unauthenticated stranger;
there is no reason they should access another user's scan results, even if
those results are factually correct.

**Purpose limitation (GDPR Article 5)**
The data collected by a scan is collected for a specific request's purpose.
Re-serving it to a different request (even to the same target) changes the
purpose without re-seeking consent, and often without the instance owner's
knowledge.

**No listing endpoint, UUIDs as capabilities**
The API design deliberately provides no way to enumerate scans or discover
another user's UUID. Every response must be individually authorized. Result
caching would require either:
- A way to predict or enumerate other scans (breaking the security model), or
- Attaching identity information to cached results (requiring identity
  infrastructure).

Neither is acceptable.

**Audit and compliance**
Security scan results must be traceable to who requested them and when, for
the purposes of incident investigation and compliance audits. If a result is
cached, the audit trail shows the original scan but not the subsequent
requests that relied on it. This obscures who acted on what information and
when, which is required for security investigations.

**Freshness and confidence**
A security scan is a point-in-time assertion about the state of an instance.
Returning a result from 5 minutes ago to a request received now is still
returning something that was once true, but the instance's administrator has
no way to know whether it still is. Even a short TTL risks hiding
vulnerability disclosures made between the original scan and the cached
request. The only correct answer is a fresh scan.
