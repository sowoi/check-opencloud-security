# OpenCloud Scanner

Run your own web frontend for the OpenCloud security scanner. It checks a URL
you submit, shows the security rating in the browser, and keeps the result only
until its TTL runs out. Try the hosted service at <https://scan.okxo.de>.

Source, deployment files and issue tracking:
<https://github.com/sowoi/check-opencloud-security>

![The hosted scanner's landing page](https://raw.githubusercontent.com/sowoi/check-opencloud-security/refs/heads/main/img/opencloud-scan-landing.png)

![A completed scan of the OpenCloud demonstration instance](https://raw.githubusercontent.com/sowoi/check-opencloud-security/refs/heads/main/img/opencloud-demo-scan-result.png)

## Start here: the setup wizard

The service is three containers with about thirty settings between them, and
several of those settings are credentials nobody should invent by hand.
Instead of copying a compose file and editing it, answer the questions and let
the wizard write both files for you.

It is one Python file, uses the standard library alone, and needs no checkout:

```bash
mkdir opencloud-scanner && cd opencloud-scanner

curl -fsSLO https://raw.githubusercontent.com/sowoi/check-opencloud-security/main/docker/setup-wizard.py
chmod +x setup-wizard.py
./setup-wizard.py

docker compose up -d
# http://127.0.0.1:8811
```

It asks one question at a time, explains what each setting does, shows an
example answer, and then writes two files into the directory you point it at:

- a **compose file** with every non-secret answer inline and commented, so it
  stays something you can commit, diff and paste into a ticket;
- a **`.env`**, created owner-readable only, holding every credential the
  compose file refers to as `${NAME}`. The Redis password, the erasure token,
  the signing key, the audit salt and the encryption key never reach the
  compose file.

Answer `generate` at any credential and it creates one. The wizard also warns,
before writing anything, about the combinations the service itself refuses to
start on.

In a hurry, or installing unattended:

```bash
./setup-wizard.py --non-interactive     # every default, credentials generated
./setup-wizard.py --preset private      # scanning instances only you can reach
./setup-wizard.py --with-authentik      # bring an identity provider for /mcp
```

| Flag | What it does |
|:-----|:-------------|
| `--output-dir DIR` | Where the generated files go. Default: the current directory |
| `--compose-file NAME` | Name of the generated compose file. Default: `docker-compose.yml` |
| `--env-file NAME` | Name of the generated secrets file. Default: `.env` |
| `--preset public\|private` | Open to anybody, or scanning instances only you can reach |
| `--sign-in` | Require a bearer token on `/mcp`, against a provider you already run |
| `--with-authentik` | Add Authentik to the stack, provisioned to issue those tokens |
| `--non-interactive` | Ask nothing, take every default, generate the credentials |
| `--force` | Overwrite existing files without asking |

The full flag list, including the Authentik mail settings, is in
[`docker/README.md`](https://github.com/sowoi/check-opencloud-security/blob/main/docker/README.md#the-setup-wizard).

## Pull the image

```bash
docker pull okxo/opencloud-scanner:latest
```

`latest` and `MAJOR.MINOR.PATCH` follow the released version, `MAJOR.MINOR`
follows the line, and `edge` is the current `main`. The image carries
`linux/amd64` and `linux/arm64`, and the same image runs both the web service
and the worker: they differ only in the command.

## Run the maintained Compose file

If you would rather have the file the project itself ships:

```bash
git clone https://github.com/sowoi/check-opencloud-security.git
cd check-opencloud-security/docker

printf 'COS_REDIS_PASSWORD=%s\n' "$(openssl rand -base64 36 | tr -d '/+=')" > .env
chmod 600 .env

docker compose -f docker-compose.dockerhub.yml up -d
# http://127.0.0.1:8811
```

That file defaults `COS_WEB_PUBLIC_BASE_URL` to `http://localhost:8811` so the
first `up` works. Put the address visitors actually use in `.env` before
letting anybody else reach it.

## Write the compose file yourself

Save this as `compose.yaml`, put a `COS_REDIS_PASSWORD` in a `.env` beside it,
and run `docker compose up -d`. Three things in it are load-bearing, and they
are most of the reason the wizard exists:

- **`COS_WEB_PUBLIC_BASE_URL` is required.** Canonical URLs, the sitemap and
  the agent discovery document must not be built from an incoming `Host`
  header, so the service refuses to start without one. Set it to the address
  visitors actually use.
- **Redis holds every live scan and every result still inside its TTL.** It
  gets a password and an `internal` network with no route off the host, and
  publishes no port.
- **Concurrency is set here and nowhere else.** `COS_WEB_MAX_WORKERS` and
  `COS_WEB_SCAN_CONCURRENCY` are the whole of this service's load on other
  people's servers, and nothing a visitor submits can change them.

```yaml
services:
  redis:
    image: redis:8.10-alpine
    command: >
      redis-server --save "" --appendonly no
      --maxmemory 256mb --maxmemory-policy allkeys-lru
      --requirepass "${COS_REDIS_PASSWORD:-}"
    environment:
      REDISCLI_AUTH: "${COS_REDIS_PASSWORD:-}"
    networks: [scanner_internal]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  worker:
    image: okxo/opencloud-scanner:latest
    pull_policy: always
    command: ["python", "-m", "webapp.tasks"]
    depends_on:
      redis:
        condition: service_healthy
    networks: [default, scanner_internal]
    environment:
      COS_WEB_REDIS_URL: "redis://:${COS_REDIS_PASSWORD:-}@redis:6379/0"
      COS_WEB_PUBLIC_BASE_URL: "${COS_WEB_PUBLIC_BASE_URL:-http://127.0.0.1:8811}"
      COS_WEB_RESULT_TTL: "3600"
      COS_WEB_MAX_WORKERS: "5"
      COS_WEB_SCAN_CONCURRENCY: "4"
      COS_WEB_SCAN_TIMEOUT: "15"
      COS_WEB_JOB_TIMEOUT: "180"
      COS_WEB_ALLOW_PRIVATE_TARGETS: "false"
      COS_WEB_CHECK_DEBUG_PORTS: "false"
      COS_WEB_RELEASES_MODE: "off"
    healthcheck:
      test:
        [
          "CMD",
          "python",
          "-c",
          "import os; from redis import Redis; os.kill(1, 0); Redis.from_url(os.environ['COS_WEB_REDIS_URL']).ping()",
        ]
      interval: 30s
      timeout: 5s
      start_period: 10s
      retries: 3
    read_only: true
    tmpfs:
      - /tmp:size=16m
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL

  web:
    image: okxo/opencloud-scanner:latest
    pull_policy: always
    depends_on:
      redis:
        condition: service_healthy
    ports: ["127.0.0.1:8811:8811"]
    networks: [default, scanner_internal]
    environment:
      COS_WEB_REDIS_URL: "redis://:${COS_REDIS_PASSWORD:-}@redis:6379/0"
      COS_WEB_PUBLIC_BASE_URL: "${COS_WEB_PUBLIC_BASE_URL:-http://127.0.0.1:8811}"
      COS_WEB_RESULT_TTL: "3600"
      COS_WEB_IP_RATE_LIMIT: "10"
      COS_WEB_IP_RATE_WINDOW: "60"
      COS_WEB_TARGET_COOLDOWN: "300"
      COS_WEB_TRUST_FORWARDED_FOR: "false"
      COS_WEB_RELEASES_MODE: "off"
    read_only: true
    tmpfs:
      - /tmp:size=16m
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL

networks:
  default:
  scanner_internal:
    internal: true
```

## Run with plain Docker

Two networks, because the application containers make outbound requests and
Redis must not be able to:

```bash
docker network create opencloud-scanner
docker network create --internal opencloud-scanner-internal

REDIS_PASSWORD="$(openssl rand -base64 36 | tr -d '/+=')"

docker run -d --name opencloud-scanner-redis \
  --network opencloud-scanner-internal \
  redis:8.10-alpine redis-server --save "" --appendonly no \
  --maxmemory 256mb --maxmemory-policy allkeys-lru \
  --requirepass "$REDIS_PASSWORD"

docker run -d --name opencloud-scanner-worker \
  --network opencloud-scanner-internal \
  --read-only --tmpfs /tmp:size=16m \
  --security-opt no-new-privileges:true --cap-drop ALL \
  -e COS_WEB_REDIS_URL="redis://:$REDIS_PASSWORD@opencloud-scanner-redis:6379/0" \
  -e COS_WEB_PUBLIC_BASE_URL=http://127.0.0.1:8811 \
  -e COS_WEB_MAX_WORKERS=5 -e COS_WEB_SCAN_CONCURRENCY=4 \
  -e COS_WEB_SCAN_TIMEOUT=15 -e COS_WEB_JOB_TIMEOUT=180 \
  -e COS_WEB_ALLOW_PRIVATE_TARGETS=false \
  -e COS_WEB_CHECK_DEBUG_PORTS=false \
  okxo/opencloud-scanner:latest python -m webapp.tasks
docker network connect opencloud-scanner opencloud-scanner-worker

docker run -d --name opencloud-scanner-web \
  --network opencloud-scanner-internal \
  -p 127.0.0.1:8811:8811 \
  --read-only --tmpfs /tmp:size=16m \
  --security-opt no-new-privileges:true --cap-drop ALL \
  -e COS_WEB_REDIS_URL="redis://:$REDIS_PASSWORD@opencloud-scanner-redis:6379/0" \
  -e COS_WEB_PUBLIC_BASE_URL=http://127.0.0.1:8811 \
  -e COS_WEB_IP_RATE_LIMIT=10 -e COS_WEB_IP_RATE_WINDOW=60 \
  -e COS_WEB_TARGET_COOLDOWN=300 \
  -e COS_WEB_TRUST_FORWARDED_FOR=false \
  okxo/opencloud-scanner:latest
docker network connect opencloud-scanner opencloud-scanner-web
```

Open <http://127.0.0.1:8811>. To stop and remove this stack:

```bash
docker rm -f opencloud-scanner-web opencloud-scanner-worker opencloud-scanner-redis
docker network rm opencloud-scanner opencloud-scanner-internal
```

## Where to go next

| Question | Where it is answered |
|:---------|:---------------------|
| Every `COS_WEB_*` setting, the request pipeline, the isolation model, the HTTP API | [`docs/webapp.md`](https://github.com/sowoi/check-opencloud-security/blob/main/docs/webapp.md) |
| What Redis holds, and how to secure and size it | [`docs/redis.md`](https://github.com/sowoi/check-opencloud-security/blob/main/docs/redis.md) |
| Putting it behind nginx, Apache, Caddy, Traefik or HAProxy | [`docs/reverse-proxy.md`](https://github.com/sowoi/check-opencloud-security/blob/main/docs/reverse-proxy.md) |
| A sign-in on the `/mcp` agent endpoint | [`docs/authentik.md`](https://github.com/sowoi/check-opencloud-security/blob/main/docs/authentik.md) |
| Running it on Kubernetes | [`docs/kubernetes.md`](https://github.com/sowoi/check-opencloud-security/blob/main/docs/kubernetes.md) |
| Using the scanner from the command line instead | [the README](https://github.com/sowoi/check-opencloud-security#readme) |

## Trademarks and affiliation

This is an independent community project. It is not affiliated with, endorsed
by or supported by OpenCloud GmbH. "OpenCloud" and all related names and marks
belong to their respective owners and are used here only to identify the
software being checked.
