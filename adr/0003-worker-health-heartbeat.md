# ADR 0003: Redis worker health heartbeat

- Status: Accepted
- Date: 2026-08-18

## Context

The web service can accept a scan only when Redis, its queue and an ARQ worker
are available. A process-only health check cannot distinguish a running web
server from one whose worker has stopped.

## Decision

Each worker writes a fixed Redis key with a 30-second expiry at startup and
refreshes it every 10 seconds. `GET /healthz` verifies Redis, reads the
aggregate queue depth and requires the key before returning 200.

The key contains no target, scan UUID, requester or result. It is deleted on
a clean worker shutdown and expires after an unclean one.

## Consequences

The web service remains unready for up to 10 seconds while a worker starts,
and becomes unready within 30 seconds after its heartbeat stops. Health
responses reveal aggregate queue depth but no individual scan information.

## Alternatives considered

### 1. Probe the worker over HTTP

The worker deliberately has no HTTP listener, so adding one would expand its
attack surface and duplicate the web service.

### 2. Treat a Redis connection as worker availability

Redis can be healthy while every worker is stopped, leaving accepted scans
queued indefinitely.

