# ADR 0005: Batch submission without a batch exemption

- Status: Accepted
- Date: 2026-08-19

## Context

An operator with an estate of instances has to submit them one at a time, and
a client wanting to check ten instances opens ten requests and reimplements
the same polling loop each time. The obvious remedy - one request carrying
several targets - is also the obvious way to smuggle load past the limits that
keep this service from becoming an amplifier: the client rate limit and the
per-target cooldown were both written for one submission at a time.

## Decision

`POST /api/scans/batch` accepts a `targets` list and the same three optional
fields a single submission accepts. Each target is put through the existing
pipeline once, in the order it was written: the client rate limit counts it,
the SSRF guard validates it, and it claims its own target cooldown. Nothing is
shared or discounted.

The response therefore carries two lists, `accepted` and `rejected`, rather
than one status, so a batch where the third instance is in cooldown and the
fourth is a typo still scans the rest. It is **202** when at least one target
started; when none did, the status is the reason the first was refused, with
`Retry-After` and the self-hosting pointer when that reason was a limit.

`COS_WEB_MAX_BATCH_TARGETS` (default 10) caps the list, and a longer batch is
refused as a whole before anything is queued, so no target pays a cooldown for
a batch that never ran.

Batching creates no new handle: each accepted scan is reachable only by its own
uuid, and there is still no endpoint that lists scans or groups them.

## Consequences

Ten targets spend ten scans from the client's window, which is the intended
cost and has to be documented plainly or it reads as a bug. A caller has to
handle a partial outcome, which is more work than a single status but is the
only honest answer.

The endpoint adds no queue semantics of its own: batched scans join the same
FIFO queue as everything else, so a large batch is fair to a visitor who
arrives in the middle of it rather than jumping ahead.

## Alternatives considered

### 1. One limit token per batch

It would make a batch cheaper than the submissions it replaces, which is
precisely the amplifier this service must not be.

### 2. Reject the whole batch when any target is refused

Simple, and it punishes nine correct targets for one typo or one cooldown -
which encourages callers to resubmit the whole batch, generating exactly the
load the limits exist to prevent.

### 3. A batch resource with its own uuid and status endpoint

It would create a handle that reaches several scans at once, weakening the
capability model for a convenience the two-list response already provides.
