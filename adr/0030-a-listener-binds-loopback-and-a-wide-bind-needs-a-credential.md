# ADR 0030: A listener binds loopback, and a wide bind needs a credential

- Status: Accepted
- Date: 2026-08-31

## Context

[ADR 0001](0001-prometheus-exporter-loopback-default.md) moved the Prometheus
exporter to `127.0.0.1` because its default bound every interface and an
operator could expose deployment and lifecycle data by enabling it without
also planning network access control. That reasoning was recorded for the
exporter and applied to the exporter only.

The scan service in `opencloud_local_scan/service.py` still defaulted to
`0.0.0.0`, with `auth_token` defaulting to `None` - so `_authorized()`
returned `True` for everyone. It has strictly more to lose than the exporter:
`GET /api/scan?url=<host>` takes a hostname from the request and hands it
straight to `scan()`, which by design performs no target validation. The SSRF
guard lives in `webapp/ssrf.py`, which this path never reaches, and it belongs
there - the plugin's trust model is an operator naming their own instances,
and refusing private addresses here would break the service's main use, which
is monitoring internal instances.

That combination - bind every interface, no credential, no target validation -
is an open request forwarder into whatever network the monitoring host can
reach: the cloud metadata endpoint, a container runtime socket, an internal
admin panel, each returned to the caller as scan evidence.

The shipped `docker/docker-compose.monitoring.yml` already published on
loopback and set a token from a Docker secret, so the exposure belonged to
anyone following the documented `check-opencloud-scanner serve` invocation
rather than the compose file. A safe default that only the compose file
supplies is not a safe default.

## Decision

Two rules, for every listener this project ships rather than for one of them:

1. **A listener binds loopback unless an operator says otherwise.** Reaching
   it from elsewhere is a deployment decision, made explicitly.
2. **Binding anything but loopback requires a credential, and the process
   refuses to start without one.** Not a warning: an operator who published
   the port meant to publish the service, and would otherwise learn what they
   published from somebody else.

`service.DEFAULT_LISTEN` becomes `127.0.0.1` and `ensure_listen_is_safe()`
enforces the second rule from `build_server()`, so every caller meets it and
not only `serve()`. A bind address that cannot be classified - a hostname that
is not a known loopback name - counts as exposed, because the safe way to be
wrong about an address is to assume it reaches somebody.

The token requirement is what makes the missing target validation acceptable
rather than something to add: whoever holds the credential is the operator,
and an operator naming hosts is the plugin's model everywhere else.

## Consequences

A container publishing this service now sets `COS_SERVICE_LISTEN=0.0.0.0`
*and* `COS_SERVICE_TOKEN`, where before it set neither. That is a breaking
change for anyone running `check-opencloud-scanner serve` with a published
port and no token - deliberately, because that configuration is the one this
record exists to end. The failure is loud and the message names both settings.

`docker/docker-compose.monitoring.yml` already set both and is unchanged.
Local use - the common case, an operator on their own machine - needs no
credential and is unaffected.

ADR 0001 is not superseded. Its decision stands; this generalises the rule it
established, so the next listener added to this project inherits it instead of
re-deciding it.

## Alternatives considered

**Keep `0.0.0.0` and only require a token.** Closes the unauthenticated hole
but leaves a service reachable from every interface by default, which is the
half ADR 0001 already rejected for less.

**Validate targets in the service instead.** Reusing the private-address
refusal from `webapp/ssrf.py` would break the primary use - scanning internal
instances from a monitoring host - and would put a policy decision in a layer
whose job is to measure. The layer boundary in `AGENTS.md` puts judgement in
the caller, and the caller here is an authenticated operator.

**Warn loudly and serve anyway.** A warning in a container log is read after
the incident, not before it.
