# Container files

Everything Docker for this project lives here: the plugin image, the web
application image, and the three Compose stacks they belong to.

| File | What it is |
|:-----|:-----------|
| [`Dockerfile`](Dockerfile) | The plugin and the scan service - the PyPI wheel and nothing else |
| [`Dockerfile.web`](Dockerfile.web) | The web application: the wheel plus the `web` extra, `webapp/` and `frontend/` |
| [`docker-compose.yml`](docker-compose.yml) | The locally built web stack: `web_app`, `arq_worker`, `redis` |
| [`docker-compose.dockerhub.yml`](docker-compose.dockerhub.yml) | The published-image web stack: `okxo/opencloud-scanner`, worker and Redis |
| [`dockerhub-readme.md`](dockerhub-readme.md) | The short description submitted to Docker Hub with every image publication |
| [`docker-compose.monitoring.yml`](docker-compose.monitoring.yml) | The plugin's own scan service, for monitoring hosts |

**The build context is the repository root, not this directory.** Both images
need files from above it, so build from the root with `-f`:

```bash
docker build -f docker/Dockerfile     -t check-opencloud-security .
docker build -f docker/Dockerfile.web -t check-opencloud-security-web .
```

`.dockerignore` stays in the repository root for the same reason: the daemon
reads it from the context, not from next to the Dockerfile.

Compose, on the other hand, is run **from this directory**, which is why the
paths inside those files point one level up (`../config`, `../secrets`).

## The web application

The whole service - the pages, the scanner behind them and the Redis between
them - from a local image build:

```bash
cd docker
docker compose up --build -d
# http://127.0.0.1:8080
docker compose logs -f web_app
docker compose down
```

To run the published image instead, while keeping the local-build Compose file
unchanged:

```bash
cd docker
docker compose -f docker-compose.dockerhub.yml up -d
# http://127.0.0.1:8080
```

`web_app` serves the pages and the API from `frontend/`; `arq_worker` runs the
scans; `redis` holds the state until its TTL runs out. Both application
services run the **same image** and differ only in the command - the code that
describes a result and the code that produces it can never drift apart between
deployments. The Docker Hub stack pulls
`okxo/opencloud-scanner:latest` before each start.

Two rules the compose file exists to enforce:

- **Concurrency is set here and nowhere else.** `COS_WEB_MAX_WORKERS` and
  `COS_WEB_SCAN_CONCURRENCY` are the whole of this service's load on other
  people's servers, and nothing a visitor sends can change them. When every
  worker is busy the next submission queues rather than being refused.
- **Redis is a cache, not a database.** No persistence, capped memory,
  `allkeys-lru`, and every key carries a TTL anyway. A dump file would be a
  copy of everybody's scans sitting on a disk.

Both application services run read-only, with `no-new-privileges`, all
capabilities dropped, an unprivileged uid and a 16 MB tmpfs for `/tmp`.

Common changes:

| Want | Do |
|:-----|:---|
| A different port | Change the `ports` mapping on `web_app`; `8080` inside the container is fixed |
| Reachable from outside | Drop the `127.0.0.1:` prefix and put a reverse proxy in front - see [`docs/webapp.md`](../docs/webapp.md#putting-it-behind-a-reverse-proxy) |
| Behind a proxy | Set `COS_WEB_TRUST_FORWARDED_FOR: "true"`, but only if the proxy **overwrites** `X-Forwarded-For` |
| More scans at once | Raise `COS_WEB_MAX_WORKERS` on `arq_worker`, and think about the instances on the other end |
| Swagger UI | `COS_WEB_ENABLE_DOCS: "true"` on `web_app`, then <http://127.0.0.1:8080/docs> |
| Scan your own network | `COS_WEB_ALLOW_PRIVATE_TARGETS: "true"` - only for a deployment nobody else can reach |
| Your own branding | Mount a frontend and set `COS_WEB_FRONTEND_DIR` to it |

Every setting is a `COS_WEB_*` environment variable, listed in full in
[`docs/webapp.md`](../docs/webapp.md#configuration) and explained from the
developer's side in [`webapp/README.md`](../webapp/README.md).

## The plugin image

For a monitoring host that would rather not install Python. The image runs as
an unprivileged user, exits with the usual Nagios codes, and carries a
`HEALTHCHECK` that verifies the image itself - the package imports, the
release schedule and the advisory database parse - so it passes on an
air-gapped host.

```bash
docker build -f docker/Dockerfile -t check-opencloud-security .

docker run --rm check-opencloud-security --host opencloud.example.com
docker run --rm -e COS_HOST=opencloud.example.com check-opencloud-security
```

The same image ships the scanner as a service, for sharing one cached result
between several monitoring consumers:

```bash
cd docker
cp ../secrets/scanner_token.example ../secrets/scanner_token
openssl rand -hex 32 > ../secrets/scanner_token

docker compose -f docker-compose.monitoring.yml up -d scanner
docker compose -f docker-compose.monitoring.yml run --rm check
```

Secrets are files under `secrets/`, mounted at `/run/secrets` and referenced
as `secret://name`; see [`secrets/README.md`](../secrets/README.md). Adjust
`COS_HOST` in the compose file, or pass `COS_*` variables per run - the full
list is in the [README](../README.md#environment-variables).

## Trademarks and affiliation

This is an independent community project. It is not affiliated with OpenCloud
GmbH and is neither recommended nor supported by the company. "OpenCloud", the
OpenCloud logo and all associated trademarks are the property of their
respective owners and are used here solely to indicate which software this
tool checks.
