# Redis

Redis is the only moving part of the scan service that is not this project's
own code, and the only place a scan exists between the moment somebody submits
it and the moment it expires. This page is about running it: what goes in it,
how long any of it stays, how to give it a password, and what to do when it
stops answering.

It applies to the **web application** in [`webapp/`](../webapp/README.md).
The command line plugin does not use Redis at all: `check-opencloud-security`
talks to an OpenCloud instance, prints a line and exits.

> **Just want the fix for the warning?** Set `COS_REDIS_PASSWORD` in
> `docker/.env` and run `docker compose up -d`. The rest of this page explains
> what that changes and what else is worth doing.

## Table of contents

<!-- TOC -->
* [What Redis is used for](#what-redis-is-used-for)
* [What is stored, and for how long](#what-is-stored-and-for-how-long)
* [Configuring the connection](#configuring-the-connection)
* [Running without Redis](#running-without-redis)
* [The password](#the-password)
* [Network isolation](#network-isolation)
* [Persistence, or the deliberate lack of it](#persistence-or-the-deliberate-lack-of-it)
* [Memory and eviction](#memory-and-eviction)
* [An external or managed Redis](#an-external-or-managed-redis)
* [Kubernetes](#kubernetes)
* [Health and monitoring](#health-and-monitoring)
* [Troubleshooting](#troubleshooting)
* [Trademarks and affiliation](#trademarks-and-affiliation)
<!-- TOC -->

## What Redis is used for

Three jobs, and nothing else:

1. **The queue.** A submission is accepted, given a uuid and pushed onto a
   list. The ARQ worker pops from it. This is what makes an overloaded service
   queue rather than refuse: the submission past the last free worker waits its
   turn and is told its position.
2. **The scan's own state.** Its status, the result document once there is
   one, and what was asked for. The web application reads these to answer
   `GET /api/scans/{uuid}`; it never runs a scan itself.
3. **Shared reference data and counters.** The release schedule and the
   advisory database the worker re-reads once a day, the worker's heartbeat,
   and the rate limit counters.

What Redis is **not** here is a database. Nothing in it is authoritative,
nothing in it is worth recovering, and every key expires. A cold start with an
empty Redis loses nothing except results whose owners can run the scan again.

## What is stored, and for how long

| Key | What it holds | Lifetime |
|:----|:--------------|:---------|
| `scan:{uuid}:status` | `queued`, `running`, `completed` or `failed` | `COS_WEB_RESULT_TTL` (default 3600s) |
| `scan:{uuid}:result` | The result document the scanner produced | `COS_WEB_RESULT_TTL` |
| `scan:{uuid}:metadata` | The address submitted, the waivers, the release track, the timestamps | `COS_WEB_RESULT_TTL` |
| `cos:web:queue` | The FIFO list of uuids waiting for a worker | The result TTL, at least an hour |
| `cos:web:worker:heartbeat` | That a worker is alive, for `/healthz` | Refreshed by the worker |
| `cos:web:rl:client:{fingerprint}` | The per-client request count | `COS_WEB_IP_RATE_WINDOW` |
| `cos:web:rl:target:{fingerprint}` | The per-target cooldown | `COS_WEB_TARGET_COOLDOWN` |
| `cos:web:schedule:document`, `cos:web:schedule:checked` | The release lifecycle re-read once a day | Until the next refresh |
| `cos:web:advisories:document`, `cos:web:advisories:checked` | The advisory database re-read once a day | Until the next refresh |

Two things follow from that table, and both matter more than they look.

**A uuid is the whole of the authorisation.** Each scan owns its own
`scan:{uuid}:*` namespace and nothing lists them. Unknown, invalid and expired
uuids all answer with the same 404, so an expired result is indistinguishable
from one that never existed. There is no endpoint that enumerates scans, and
adding one would turn every result into a public document.

**The rate limit keys hold fingerprints, not addresses.** A client IP is
hashed with `COS_WEB_AUDIT_SALT` before it is counted, so a dump of Redis is
not a list of who scanned what. See [what gets logged](webapp.md#what-gets-logged).

Redis is therefore, for as long as a TTL lasts, a copy of the addresses people
submitted and the security findings for each. That is the reason for the two
sections below.

## Configuring the connection

One setting, `COS_WEB_REDIS_URL`, and both processes read it: the web
application opens it directly, and the worker hands the same URL to ARQ. A
password or a TLS scheme in the URL therefore configures the whole stack.

| Form | When |
|:-----|:-----|
| `redis://redis:6379/0` | The container next door, no password |
| `redis://:PASSWORD@redis:6379/0` | With `requirepass` set. The username is empty, hence the bare colon |
| `redis://user:PASSWORD@host:6379/0` | Redis 6+ ACL user |
| `rediss://user:PASSWORD@host:6380/0` | The same over TLS. Two `s`, and it is the scheme that turns encryption on |
| `memory://` | No Redis at all, see below |

Percent-encode a password containing `@`, `:`, `/` or `#`, or it will be
parsed as part of the host. The passwords generated by
[`docker/setup-wizard.py`](../docker/setup-wizard.py) and
[`docker/authentik-env.sh`](../docker/authentik-env.sh) use only characters
that are safe in a URL, which is why they are generated rather than asked for.

## Running without Redis

`COS_WEB_REDIS_URL=memory://` selects an in-process stand-in: the same
interface, backed by a dictionary in the web process. It exists for two
purposes.

- **The test suite.** No test needs a Redis server, which is why
  `tests/webapp_support.py` sets it.
- **Looking at the thing.** One process, one command, no infrastructure.

It is not a deployment option. There is no worker to queue to, the state dies
with the process, and a second process would not see the first one's scans.
Anything that serves more than yourself needs a real Redis.

## The password

Redis answers whoever reaches it. Out of the box it has no password, which is
what a security scan of the host reports as:

```
WARNING: Redis does not require authentication and is not protected by
network restriction
```

The finding is fair. "Only our own containers are on this network" is an
assumption about everything else that will ever run on that host, not a
control, and what is behind the assumption is every live scan and every result
still inside its TTL.

Set one:

```bash
cd docker
printf 'COS_REDIS_PASSWORD=%s\n' "$(openssl rand -base64 36 | tr -d '/+=')" >> .env
chmod 600 .env
docker compose up -d
```

The compose files read `${COS_REDIS_PASSWORD:-}` in two places: Redis takes it
as `--requirepass`, and both application containers get it in
`COS_WEB_REDIS_URL`. Leave the variable unset and the stack behaves exactly as
it did before, so this is safe to pull without editing anything - but do not
leave it unset on anything that is not a laptop.

Two commands do it for you:

- [`docker/setup-wizard.py`](../docker/setup-wizard.py) generates one for
  every deployment it writes, into a `.env` created `0600`. The compose file it
  writes refers to the name and never carries the value, so it stays something
  you can commit.
- [`docker/authentik-env.sh`](../docker/authentik-env.sh) writes one alongside
  the Authentik secrets, and leaves an existing value alone.

Verify it took effect:

```bash
docker compose exec -e REDISCLI_AUTH= redis redis-cli ping
# NOAUTH Authentication required.        <- what you want to see
docker compose exec redis redis-cli ping
# PONG                                   <- authenticated, via REDISCLI_AUTH
```

The health check inside the container reads `REDISCLI_AUTH` from the
environment rather than taking `-a` on the command line, so the password does
not appear in the container's own process list.

Changing the password later is a restart of all three services together, not a
rolling one: the application containers read the URL at startup.

## Network isolation

The password is one half of the answer to that warning. The other half is that
Redis has no reason to be reachable at all.

In the shipped compose files Redis publishes no port and sits alone on a
network marked `internal: true`:

```yaml
networks:
  scanner_internal:
    internal: true
```

`internal` means Docker gives that network no gateway, so nothing on it can
reach the outside world and nothing outside can route to it. The two
application containers are on it *and* on the default network, because a scan
is an outbound request and the web service is published on a port. Redis is
only on the internal one.

If you run Redis yourself rather than from these files, the equivalents are
`bind 127.0.0.1`, a firewall rule, or a private network segment. Never publish
6379 to a host interface, and never to the internet: an open Redis on a public
address is found by scanners within minutes.

## Persistence, or the deliberate lack of it

The shipped Redis runs with `--save ""` and `--appendonly no`. It writes
nothing to disk, on purpose.

A dump file would be a copy of everybody's scans sitting on a disk, surviving
the TTL that was supposed to have removed them, and turning up in whatever
backs that disk up. Nothing in Redis needs to survive a restart: a scan whose
result is gone can be run again in half a minute.

Do not add a volume to the `redis` service. If you are using a managed Redis
that persists by default, either accept that results outlive their TTL in
somebody else's backups or turn persistence off for that instance.

`docker/setup-wizard.py` will nonetheless generate a stack that persists, for
the one deployment where the trade is worth making: a private instance where
losing a queued scan to a restart matters more than the scans being on a disk
that somebody may back up. It is never the default, it warns when you choose
it, and it points at `COS_WEB_ENCRYPT_RESULTS` — with that on, what reaches
the disk is ciphertext and the key lives in `.env` rather than beside it. On
a deployment strangers can reach, the answer is still `none`.

## Memory and eviction

```
--maxmemory 256mb
--maxmemory-policy allkeys-lru
```

256 MB is generous for the shipped worker count. A result document is a few
kilobytes and every key already carries a TTL, so the cap is a backstop rather
than a working limit: it is what stops a queue that nobody is draining from
consuming the host.

`allkeys-lru` is the right policy here precisely because nothing is
authoritative. Under pressure Redis drops the least recently used key, which
is the oldest result nobody has come back for, and the visitor sees the same
404 they would have seen a few minutes later anyway.

Raise the cap if you raise `COS_WEB_RESULT_TTL` a long way, or run a fleet
scan of hundreds of instances. Watch `evicted_keys`:

```bash
docker compose exec redis redis-cli info stats | grep evicted_keys
```

Steady eviction while the TTL is short means the cap is too low, and people
are losing results before they read them.

## An external or managed Redis

Point `COS_WEB_REDIS_URL` at it and remove the `redis` service from the
compose file. Worth checking before you do:

- **Use TLS.** `rediss://`. The connection carries the result documents and
  the password.
- **Give it its own database number or its own instance.** The key names are
  namespaced (`scan:`, `cos:web:`) but the purge in
  `DELETE /api/purge` scans `scan:*:metadata`, and a busy shared instance
  makes that slower than it needs to be.
- **Check the eviction policy.** A managed Redis defaulting to `noeviction`
  will start refusing writes when it fills instead of dropping an old result,
  and a refused write is a submission that fails rather than queues.
- **Check what it persists.** See the section above.

## Kubernetes

The [Kubernetes guide](kubernetes.md) deploys the scan service; Redis there is
a `Deployment` and a `Service` of its own, or a managed instance. The same
rules apply, expressed differently:

- The password goes in a `Secret`, referenced from the URL through
  `COS_WEB_REDIS_URL`, not into a `ConfigMap`.
- A `NetworkPolicy` restricting ingress to the web and worker pods is the
  equivalent of the internal network.
- `ClusterIP` and no `Ingress`. Never a `LoadBalancer` or a `NodePort`.
- No `PersistentVolumeClaim`, for the reason in
  [Persistence](#persistence-or-the-deliberate-lack-of-it).

## Health and monitoring

`GET /healthz` answers `503` when the queue cannot be read or no worker has
sent a heartbeat, so a probe on it covers Redis without a second check. It
reports the queue depth and the state of the two daily refreshes, and says
nothing about any individual scan.

Worth an alert:

| Signal | Why |
|:-------|:----|
| `/healthz` returning 503 | Redis is unreachable or the worker is gone. Nothing can be scanned |
| Queue depth climbing and not falling | Workers are stuck or too few; submissions are waiting |
| `evicted_keys` rising | Results are being dropped before their TTL |
| `rejected_connections` | The connection limit, usually a leak somewhere |

## Troubleshooting

| What you see | What it means |
|:-------------|:--------------|
| `NOAUTH Authentication required` | Redis has a password and the URL does not. Add `:PASSWORD@` after the scheme |
| `WRONGPASS invalid username-password pair` | The URL and `--requirepass` disagree. Usually `.env` changed and only one container was restarted |
| `Connection refused` | Redis is not up, or not on the network the caller is on. Check `docker compose ps` and that both application services list `scanner_internal` |
| `Name or service not known: redis` | The application container is not on the internal network |
| `MISCONF Redis is configured to save RDB snapshots` | Persistence is on somewhere it should not be. See [Persistence](#persistence-or-the-deliberate-lack-of-it) |
| `OOM command not allowed when used memory > 'maxmemory'` | The cap is reached and the policy is `noeviction`. It should be `allkeys-lru` |
| `/healthz` says `unavailable` | Redis answers but no worker has sent a heartbeat. Look at the worker's logs, not Redis's |
| A result 404s early | The TTL expired, or a key was evicted. Both are by design; check `evicted_keys` if it is happening often |

The service logs lifecycle markers and a uuid, never a target address or a
result, so a Redis problem shows up in the logs as scans that never leave
`queued`. That is the intended trade: the logs are not a record of what
everybody scanned.

## Trademarks and affiliation

This is an independent community project. It is **not** affiliated with,
endorsed by, sponsored by or supported by OpenCloud GmbH, and nothing it
reports is an official statement about OpenCloud software. "OpenCloud" and all
related names and marks belong to their respective owners and are used here
only to identify the software being checked.
