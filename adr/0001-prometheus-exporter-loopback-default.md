# ADR 0001: Bind the Prometheus exporter to loopback by default

- Status: Accepted
- Date: 2026-08-18

## Context

The exporter exposes scan results and starts only when an operator supplies a
listen port, but its default address bound it to every network interface. An
operator could expose internal deployment and lifecycle data by enabling the
exporter without also planning network access control.

## Decision

Bind the exporter to `127.0.0.1` unless
`--prometheus-listen-addr` or `COS_PROMETHEUS_LISTEN_ADDR` explicitly selects
another address. Container and Kubernetes examples must opt in to `0.0.0.0`,
where their network boundary is intentionally managed by port publishing or a
Service and network policy.

## Consequences

Host-local Prometheus deployments work without extra configuration. Remote
scrapers require an explicit address and network access policy. Existing
container and Kubernetes deployments must set `0.0.0.0` when they expose the
exporter outside the container.

## Alternatives considered

Keeping `0.0.0.0` preserves remote reachability by default, but silently
exposes metrics on every interface. Removing the exporter would avoid that
risk but removes a supported monitoring integration.
