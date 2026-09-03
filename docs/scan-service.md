# Running the scanner as a service

The package ships a second entry point, `check-opencloud-scanner`, which runs
the very same scanner as a long-lived HTTP service so that several consumers
can share one cached result. The
[main README](../README.md#running-the-scanner-as-a-service) describes the
endpoints and the rule that a wide bind needs a credential; this page is the
deployment detail.

This is **not** the public web application - that is
[the scan service](webapp.md), which takes a URL from a stranger, queues it
and renders the answer.

<!-- TOC -->
* [Running the scanner as a service](#running-the-scanner-as-a-service)
  * [In a container](#in-a-container)
  * [The monitoring compose file](#the-monitoring-compose-file)
<!-- TOC -->


## In a container

The service refuses to bind anything but loopback without a token. In a
container that means two settings: bind the container's interfaces so the
published port reaches the process, and set the token that makes doing so
allowed.

```shell
docker run -d --name opencloud-scanner -p 127.0.0.1:8811:8811 \
  -e COS_SERVICE_LISTEN=0.0.0.0 \
  -e COS_SERVICE_TOKEN="$(openssl rand -hex 32)" \
  --entrypoint check-opencloud-scanner \
  check-opencloud-security serve

curl -H "Authorization: Bearer <token>" \
  'http://127.0.0.1:8811/api/scan?url=opencloud.example.com'
```

## The monitoring compose file

A ready-made [`docker/docker-compose.monitoring.yml`](../docker/docker-compose.monitoring.yml)
starts the scanner plus a check container, including a health check and Docker
secrets:

```shell
# 1. create the secret files from the templates
cp secrets/scanner_token.example  secrets/scanner_token
cp secrets/releases_token.example secrets/releases_token

# 2. fill them with real values
openssl rand -hex 32 > secrets/scanner_token          # protects the service
printf '%s' '<github-token>' > secrets/releases_token
chmod 600 secrets/scanner_token secrets/releases_token

# 3. adjust COS_HOST in docker/docker-compose.monitoring.yml, then:
cd docker
docker compose -f docker-compose.monitoring.yml up -d scanner
docker compose -f docker-compose.monitoring.yml run --rm check
```

The plain `docker compose up` in that directory is the public web application
instead - see [the web application](webapp.md). Set that one up with
**`docker/setup-wizard.py`** rather than by editing a compose file: it asks
what the service should be reachable at, how hard it may scan and who may
erase a result, then writes a commented compose file and a `.env` holding the
Redis password and every other credential that file refers to. It is one
stdlib-only Python file, so it runs on a host with Docker and nothing else -
see [`docker/README.md`](../docker/README.md#setting-up-the-whole-stack).

Everything in `secrets/` except the `*.example` templates is git-ignored - see
[`secrets/README.md`](../secrets/README.md).
