# Container files

Everything Docker for this project lives here: the plugin image, the web
application image, and the three Compose stacks they belong to.

| File | What it is |
|:-----|:-----------|
| [`Dockerfile`](Dockerfile) | The plugin and the scan service - the PyPI wheel and nothing else |
| [`Dockerfile.web`](Dockerfile.web) | The web application: the wheel plus the `web` extra, `webapp/` and `frontend/` |
| [`docker-compose.yml`](docker-compose.yml) | The locally built web stack: `web_app`, `arq_worker`, `redis` |
| [`setup-wizard.py`](setup-wizard.py) | Asks what a deployment needs and writes a compose file and its `.env` |
| [`docker-compose.dockerhub.yml`](docker-compose.dockerhub.yml) | The published-image web stack: `okxo/opencloud-scanner`, worker and Redis |
| [`dockerhub-readme.md`](dockerhub-readme.md) | The short description submitted to Docker Hub with every image publication |
| [`docker-compose.authentik.yml`](docker-compose.authentik.yml) | The whole thing with a sign-in: the web stack *and* Authentik, in one file |
| [`authentik-env.sh`](authentik-env.sh) | Writes the secrets that stack needs into `.env`, once |
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
# http://127.0.0.1:8811
docker compose logs -f web_app
docker compose down
```

To run the published image instead, while keeping the local-build Compose file
unchanged:

```bash
cd docker
docker compose -f docker-compose.dockerhub.yml up -d
# http://127.0.0.1:8811
```

`web_app` serves the pages and the API from `frontend/`; `arq_worker` runs the
scans; `redis` holds the state until its TTL runs out. Both application
services run the **same image** and differ only in the command - the code that
describes a result and the code that produces it can never drift apart between
deployments. The Docker Hub stack pulls
`okxo/opencloud-scanner:latest` before each start.

## Real-container integration test

The scanner has an opt-in integration test that initializes and scans a real
OpenCloud container. It does not run as part of the normal suite and creates
only disposable Docker volumes and a container:

```bash
COS_INTEGRATION_IMAGE=opencloudeu/opencloud-rolling:latest \
  uv run pytest -q -rs tests/integration/test_real_opencloud.py
```

The test pulls the selected image first and skips clearly when Docker, the
image, or the image's `init` workflow is unavailable. The weekly
`real OpenCloud container` workflow runs the same check; set
`COS_INTEGRATION_IMAGE` to a compatible pinned image when the rolling image is
not available.

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
| A different port | Change the `ports` mapping on `web_app`; `8811` inside the container is fixed |
| Reachable from outside | Drop the `127.0.0.1:` prefix and put a reverse proxy in front - see [`docs/webapp.md`](../docs/webapp.md#putting-it-behind-a-reverse-proxy) |
| Behind a proxy | Set `COS_WEB_TRUST_FORWARDED_FOR: "true"`, but only if the proxy **overwrites** `X-Forwarded-For` |
| More scans at once | Raise `COS_WEB_MAX_WORKERS` on `arq_worker`, and think about the instances on the other end |
| Swagger UI | `COS_WEB_ENABLE_DOCS: "true"` on `web_app`, then <http://127.0.0.1:8811/docs> |
| The schema, the workflows and the discovery document | Already public: `/openapi.json`, `/arazzo.json`, `/.well-known/ai.json` |
| An AI agent to use it | The MCP endpoint at `/mcp`, on by default in the web image. `COS_WEB_ENABLE_MCP=false docker compose up -d` turns it off without editing the file; [the MCP guide](../docs/mcp.md) has the client configuration |
| Scan your own network | `COS_WEB_ALLOW_PRIVATE_TARGETS: "true"` - only for a deployment nobody else can reach |
| A sign-in on the MCP endpoint | [`docker-compose.authentik.yml`](docker-compose.authentik.yml) - the whole stack, sign-in included |
| Your own branding | Mount a frontend and set `COS_WEB_FRONTEND_DIR` to it |

Every setting is a `COS_WEB_*` environment variable, listed in full in
[`docs/webapp.md`](../docs/webapp.md#configuration) and explained from the
developer's side in [`webapp/README.md`](../webapp/README.md).

## The setup wizard

The compose files here are the two shapes this service usually takes. A
deployment that is neither - a different port, an on-premise instance behind
the SSRF guard, encryption at rest, a sign-in on `/mcp` - can be answered for
rather than edited into place:

```bash
cd docker
./setup-wizard.py
```

It asks one question at a time, explains what each setting does and shows an
example answer, then writes into whichever directory you point it at:

- a **compose file** with every non-secret answer inline and commented, so it
  stays something you can commit, diff and paste into a ticket;
- a **`.env`** holding the credentials it refers to as `${NAME}`, created
  owner-readable only. A purge token or an encryption key never reaches the
  compose file.

- and, when you ask it to bring an identity provider, the **Authentik
  blueprint**, in `authentik/blueprints/` beside the compose file that mounts
  it.

It generates the credentials nobody should invent by hand - answer `generate`
at the erasure token, the signing key, the audit salt or the encryption key -
and warns before writing about the combinations the service itself refuses to
start on, such as a sign-in on `/mcp` with a provider it was told nothing
about.

| Flag | What it does |
|:-----|:-------------|
| `--output-dir DIR` | Where the generated files go. Default: the current directory |
| `--compose-file NAME` | Name of the generated compose file |
| `--env-file NAME` | Name of the generated secrets file |
| `--preset public\|private` | Starting answers: open to anybody, or scanning your own network |
| `--sign-in` | Require a sign-in on `/mcp`, against a provider you already run |
| `--with-authentik` | Add Authentik to the stack, provisioned to issue those tokens. Does not require one by itself |
| `--smtp-host HOST` | Mail server Authentik sends from. Empty leaves it on local delivery |
| `--smtp-port PORT` | Default: `587` |
| `--smtp-username NAME` | The account it authenticates as |
| `--smtp-from ADDRESS` | The `From:` address, for example `authentik@example.com` |
| `--smtp-security starttls\|ssl\|none` | Default: `starttls` |
| `--smtp-timeout SECONDS` | Default: `10` |
| `--non-interactive` | Ask nothing, take every default, generate the credentials |
| `--force` | Overwrite existing files without asking |

There is deliberately no `--smtp-password`: a password on a command line is a
password in `ps` and in the shell history. The wizard takes it from
`AUTHENTIK_EMAIL_PASSWORD` in the environment, or asks for it, and writes it
into `.env` alone.

**A sign-in and an identity provider are two answers, not one**, and neither
implies the other:

- `--sign-in` requires a token on `/mcp` and asks for the issuer, the audience
  and the keys of the provider the estate already runs, which is the usual
  case and adds no containers.
- `--with-authentik` provisions one: Authentik and its database join the
  generated stack, those three values are derived rather than asked for, the
  credentials are generated into `.env` and the blueprint is written beside
  the compose file. It leaves `/mcp` **open**, which is the point - bring the
  provider up, log in, try a token, and switch the guard on when it works.

Both together is the deployment that is guarded from the first `up`. Neither
is the default: `/mcp` stays open unless somebody asks for a sign-in, and
nothing of Authentik reaches a deployment that did not ask for it. Its mail
settings are asked for when it *is* provisioned, because an identity provider
with no way to send a password recovery locks out the one account it starts
with. See [`../docs/authentik.md`](../docs/authentik.md).

The `private` preset is the estate deployment: private targets allowed, the
debug ports probed, search engines refused and an audit log that names its own
targets. `public` is what `docker-compose.yml` already is.

It runs on the standard library alone, so it works on a host that has Docker
and nothing else installed yet, and it refuses to write over the compose files
that ship here - the next `git pull` would take a hand-made deployment with
it. Use `--compose-file` or `--output-dir` for a deployment of your own.

**This is not `check-opencloud-security --configure`.** That wizard sets up a
monitoring check against one instance and writes a scanner configuration file;
this one configures a container deployment of the web service. They share no
code and no configuration.

## Authentik, for a sign-in on the MCP endpoint

The public deployment answers anybody, and that is the point of it. An estate
running this service for itself usually wants the opposite for the agent
endpoint, and `docker-compose.authentik.yml` is that deployment whole: the web
application, the worker, Redis, Authentik, and Authentik's PostgreSQL, in one
file and one command.

```bash
cd docker
./authentik-env.sh                                  # writes .env, once
docker compose -f docker-compose.authentik.yml up -d
# http://127.0.0.1:9000/if/flow/initial-setup/      (the trailing slash matters)
```

It replaces `docker-compose.yml` rather than layering on top of it. Bring it
up and `/mcp` requires a bearer token; there is nothing further to switch on,
because the sign-in follows the endpoint: `COS_WEB_MCP_AUTH_ENABLED` is
`${COS_WEB_ENABLE_MCP:-true}`, so turning the endpoint off turns the sign-in
off with it, and there is no way to end up with the endpoint open by accident.

It is a separate file rather than a Compose profile because the secrets it
needs are declared *required*, and Compose checks a required variable in every
file it reads, whether or not the service using it was selected. As a profile
it would break `docker compose up` for everybody who never wanted Authentik.

**The provider provisions itself.** `authentik/blueprints/opencloud-scanner.yaml`
is mounted into both Authentik containers, and the worker applies it on the
first start: the OAuth2 provider, its signing key, the scopes, and the
application whose slug becomes the issuer. The client ID and secret in `.env`
are the same ones the web application checks tokens against, so the two sides
agree without anything being copied between them. The blueprint provisions
once (`state: created`) and then leaves your edits alone.

Authentik brings its own PostgreSQL - `postgres:18.6-alpine` - and needs no
Redis of its own; it has kept sessions, caching and its task queue in the
database since 2025.10. The scanner's Redis is a cache with no persistence and
an eviction policy, and is not a substitute for it. Authentik itself has no
Alpine image and is not going to: `ghcr.io/goauthentik/server` is published
Debian-based only. The worker here does **not** get the Docker socket the
upstream compose file mounts, because this stack runs no outposts and handing
a container the daemon socket is handing it the host.

Reachable from elsewhere than your laptop? Two variables, and nothing else
changes:

```bash
AUTHENTIK_URL=https://sso.example.com \
COS_WEB_PUBLIC_BASE_URL=https://scanner.example.com \
  docker compose -f docker-compose.authentik.yml up -d
```

The scanner never talks to Authentik on a visitor's behalf, never redirects
anybody to it and holds no account in it: it fetches the published signing
keys and checks a token against them. Get the configuration wrong and the
service refuses to start rather than serve `/mcp` open.
[`docs/authentik.md`](../docs/authentik.md) walks through what the blueprint
created, how to change it, how an agent gets a token, and the backup - which
is yours to run, because Authentik has no built-in one.

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
