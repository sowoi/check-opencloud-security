# ADR 0081: The bundled key-value store is Valkey

- Status: Proposed
- Date: 2026-11-10

## Context

Every stack this project ships - `docker/docker-compose*.yml`, the stack
`docker/setup-wizard.py` generates, the CI service behind
`tests/test_redis_contract.py` - ran
the `redis` image. Redis left the BSD licence in 7.4 for RSALv2/SSPL, and
since 8.0 offers the AGPLv3 beside them; which terms apply now depends on the
version and on how a deployment uses it. Valkey is the Linux Foundation's
BSD-licensed continuation of Redis 7.2, speaks the same protocol and is
served by the same `redis.asyncio` client and ARQ the web application already
uses.

## Decision

**The bundled server is `valkey/valkey`, pinned to a minor version
(`9.1-alpine`)**, wherever `redis:8.10-alpine` was: the three compose files,
`REDIS_IMAGE` in the wizard, the CI service in `run-tests.yml`, and every
command a document gives.

**Only the server changes.** The Python client (`redis`, via `arq`), the
service name `redis`, `COS_WEB_REDIS_URL` and its `redis://` scheme,
`COS_REDIS_PASSWORD` and every Python identifier stay as they are, so an
existing `.env` and any external Redis-compatible server keep working. "Redis"
in prose names the protocol.

**The container runs `valkey-server` and checks itself with `valkey-cli`**,
authenticated through `VALKEYCLI_AUTH`. The image's entrypoint drops root
only when the command is `valkey-server`; the `redis-server` symlink would
leave the server running as root.

## Consequences

The image runs as uid 999 with `/data` as its working directory, as the
Redis image did, so ownership commands and bind mounts are unchanged.

Valkey refuses a data file written by Redis 8 (RDB version 12 and later)
unless `rdb-version-check relaxed` is set. A stack generated with persistence
must empty its data directory or volume once before its first Valkey start.
The default stacks persist nothing and are unaffected. That step is
documented rather than automated, because everything in the store has a TTL.

## Alternatives considered

- **Stay on Redis.** It works, but its licence has changed twice in two
  years and asks every operator to work out which terms bind them; BSD-3
  asks nothing.
- **Rename the service, the variables and the scheme too.** It would break
  every existing `.env` for no functional gain; the protocol is still Redis's.
- **Set `rdb-version-check relaxed` to carry Redis 8 data across.** It loads
  data Valkey does not claim to understand, and the data is disposable.
