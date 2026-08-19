# ADR 0007: Erasure on request, proved by a second look

- Status: Accepted
- Date: 2026-08-19

## Context

Every key the web application writes carries a TTL, so the data is gone within
the hour whether anybody asks or not. That answers storage limitation. It does
not answer Article 17: somebody who wants their instance forgotten *now*
cannot be told to wait, and an operator who honours that request needs
something to put in the file afterwards.

Two facts about the existing design make this awkward, and both are deliberate.

There is **no index from a target to its scans**. The uuid is a capability,
there is no listing endpoint, and nothing anywhere maps an instance back to
the scans run against it - because such a map is exactly the record of who
scanned what that the rest of the service is arranged not to keep.

And the **proof has to survive the evidence**. A receipt cannot point at a
record that no longer exists, so it cannot be a copy of what was deleted
without becoming a second copy of the thing that was supposed to go.

## Decision

`DELETE /api/purge?target=<host>` erases everything the service holds for one
instance: every `scan:{uuid}:*` namespace whose own metadata names that
hostname, that scan's entries in the shared queue, and the cooldown key
derived from the target.

**The purge walks the keyspace rather than an index.** `ScanStore.purge_target`
is the only method that lists keys, and `RedisBackend.keys_matching` exists for
it alone. A rare authenticated call pays with a scan over `scan:*:metadata`, so
that the request path never needs the index that would make it cheap.

**The proof is a second walk.** After deleting, the store is walked again and
the count of still-matching scans is reported as `remaining`; `complete` is
`remaining == 0`. That is the only honest evidence available once the data is
gone: not "we deleted it" but "we looked again and there is nothing there". The
receipt also carries counts, a fingerprint of the target, the issuing version,
and an HMAC signature when `COS_WEB_PURGE_SIGNING_KEY` is set, so it can be
checked long after the scans expired. `notes` names what the service cannot
reach - a result already downloaded, and the audit trail if one is kept.

**It is authorised, and absent until configured.** Without
`COS_WEB_PURGE_TOKEN` the endpoint answers 404 like any path that is not
there. The workflow is the one the regulation actually describes: the data
subject writes to the operator, and the operator - the controller - carries the
erasure out and hands back the receipt.

## Consequences

An erasure request can be answered in seconds and evidenced afterwards, and
the receipt is small enough to file and verifiable by anybody holding the key.

The cost is a keyspace walk, which is O(scans held) and runs twice per purge.
On a deployment holding an hour of scans that is small, and it is unreachable
from the request path, but it is a real operation on the same Redis the API
uses and belongs to the operator rather than to whoever can type a hostname.

A deployment that never sets a token has no erasure endpoint at all, and must
answer requests by waiting out the TTL. That is a defensible position - the
data expires anyway - and it stays the default.

## Alternatives considered

### 1. Maintain a target index so a purge is a lookup

Cheap, obvious, and it creates the one data structure this service exists
without: a list of which instances were scanned. It would also have to be kept
past the scans it refers to for a purge to catch anything the TTL had already
taken, which makes it more durable than the data it indexes.

### 2. Let anybody purge their own instance, unauthenticated

Attractive for self-service, and it is the friendly reading of "your data".
But a purge is destructive across visitors: it deletes results belonging to
whoever is reading them right now, and possession of a hostname proves nothing
about who runs it. An unauthenticated version is a denial-of-service tool with
a compliance label on it.

### 3. Store the receipts

A receipt kept server-side would answer "prove it" without the operator having
to file anything - and would be a permanent record of which instances asked to
be forgotten, which is a worse register than the one deleted. The receipt is
returned once, and keeping it is the controller's job.

### 4. Erase the audit trail too

The audit log is append-only text handled by whatever collects it, and a
service that edits its own audit records has no audit records. The receipt
names the log instead, and the log holds a fingerprint rather than a hostname
unless the operator chose otherwise.
