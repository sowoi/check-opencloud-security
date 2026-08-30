# Documentation

The [main README](../README.md) is the reference: every option, every setting
and what the scanner actually checks. These pages are the longer material that
was crowding it out - the deployment guides, and worked examples for the
places this check tends to end up.

> **Just want a scan?** [scan.okxo.de](https://scan.okxo.de) runs the web
> application from this repository - paste an address and read the result, no
> installation. [The public scan service](webapp.md) explains how to run your
> own, without a rate limit.

<!-- TOC -->
* [Documentation](#documentation)
  * [Background](#background)
  * [Deploying it](#deploying-it)
  * [Feeding the result somewhere](#feeding-the-result-somewhere)
  * [What the scanner checks, in depth](#what-the-scanner-checks-in-depth)
  * [Running it at scale](#running-it-at-scale)
  * [Elsewhere in the repository](#elsewhere-in-the-repository)
  * [Trademarks and affiliation](#trademarks-and-affiliation)
<!-- TOC -->


## Background

| Page | What it covers |
|:-----|:---------------|
| [What OpenCloud is, and how it differs from ownCloud and Nextcloud](what-is-opencloud.md) | The fork history behind all three projects, and the architecture, storage and release differences that follow from it |

## Deploying it

| Page | What it covers |
|:-----|:---------------|
| [Icinga Director](icinga-director.md) | Creating the `CheckCommand`, data fields, service template and apply rule through the web UI |
| [Automated deployment with Ansible](ansible.md) | The native and Docker roles, the variables, and deploying the Icinga2 objects without clicking |
| [Scanning from the command line, in one line](docker-oneliner.md) | The published image as a single `docker run`, for whoever would rather not use the website: JSON output, private networks, waivers and a shell function |
| [Scheduling](scheduling.md) | systemd timer and cron, for hosts with no Icinga2 or Nagios |
| [Kubernetes](kubernetes.md) | A `CronJob` for scheduled scans, and the scan service as a `Deployment` with probes |
| [Running the check from CI](ci.md) | GitHub Actions and GitLab CI, and gating a pipeline on a field of the result document |
| [Using the scanner from an AI agent](mcp.md) | The MCP endpoint at `/mcp`: worked configuration for Claude Code, Claude Desktop, GitHub Copilot in VS Code and the CLI, Cursor, Zed and Windsurf, against [scan.okxo.de](https://scan.okxo.de) or your own deployment - and how to turn it off |
| [A sign-in on the MCP endpoint](authentik.md) | One compose file with Authentik in it, the provider a blueprint creates for you, the `COS_WEB_MCP_AUTH_*` settings, adding the people and service accounts allowed to use it, how each of them gets a token, and the backup Authentik does not do for you |
| [Reverse proxies](reverse-proxy.md) | Worked nginx, Apache, Caddy, Traefik and HAProxy configuration - the headers this check grades in front of OpenCloud, and what the scan service needs from a proxy |
| [The public scan service](webapp.md) | The self-hosted web application: FastAPI, an ARQ worker and Redis, with queueing, SSRF and rate limits. Running at [scan.okxo.de](https://scan.okxo.de) |
| [Redis behind the scan service](redis.md) | The one piece of infrastructure that stack needs: what it holds and for how long, giving it a password, keeping it off the network, memory and eviction, and what to alert on |

## Feeding the result somewhere

| Page | What it covers |
|:-----|:---------------|
| [Prometheus and Grafana](prometheus.md) | Textfile collector, Pushgateway, alerting rules and what to graph |
| [Webhook recipes](webhook-recipes.md) | The payload, and adapters for Slack, Discord, ntfy and Alertmanager |
| [Machine-readable output](output-formats.md) | `--format json`, `sarif` and `junit`: one document per run, and how each shape is meant to be consumed |
| [Uptime Kuma](../README.md#uptime-kuma) | The webhook as a Push monitor - in the main README |

## What the scanner checks, in depth

| Page | What it covers |
|:-----|:---------------|
| [Content-Security-Policy](csp.md) | The two independent CSP checks, why `unsafe-inline` fails on a stock instance, and how to fix it |
| [TLS and certificates](tls.md) | Every transport and certificate check: protocol version, trust, chain, lifetime, cipher suite, CAA, OCSP stapling, and self-signed handling |
| [Why OpenCloud still answers `/status.php`](status-php.md) | The PHP-era compatibility endpoint, its hardcoded fields, and what this scanner reads from it |
| [Cookie attributes](cookies.md) | The Secure, HttpOnly and SameSite checks run against every cookie actually observed on the public response |
| [Authentication](authentication.md) | Protected-endpoint probes, HTTP Basic auth, the documented demo accounts, account search and the link password policy |
| [Public link sharing](sharing.md) | The password and expiration checks run against OpenCloud's public capabilities document |
| [Exposed paths and debug endpoints](exposure.md) | Deployment files, directory listings, debug endpoints and ports that must never answer on the public address |
| [Embedding in an iframe](embedding.md) | The origin-restriction checks behind embedding OpenCloud's web client in a third-party page |
| [Version and lifecycle disclosure](lifecycle.md) | Whether a real version could be determined at all, and where it leaks besides `/status.php` |

## Running it at scale

| Page | What it covers |
|:-----|:---------------|
| [Checking a fleet of instances](many-instances.md) | One file per instance, looping over them, keeping waivers honest, and alerting only on what changed |
| [Troubleshooting](troubleshooting.md) | The errors people actually hit, and the exit code reference |

## Elsewhere in the repository

- [`ARCHITECTURE.md`](../ARCHITECTURE.md) - how the repository fits together:
  the three layers, how settings reach the scanner, how OpenAPI, Arazzo and
  MCP describe one workflow layer between them, what ships where, and where a
  new check, setting, endpoint or MCP tool belongs.
- [`adr/README.md`](../adr/README.md) - the architectural decision records,
  and the format a new one follows.
- [`opencloud_local_scan/README.md`](../opencloud_local_scan/README.md) - the
  scanner library: what it reads from an instance, how the rating is worked
  out, and how end of life is decided.
- [`webapp/README.md`](../webapp/README.md) - the web application for whoever
  changes it or writes a client: the API, the OpenAPI and Arazzo documents,
  the MCP endpoint for AI agents, the restrictions and what can be
  configured.
- [`frontend/README.md`](../frontend/README.md) - the pages: the rules, the
  design tokens, the template contract and how to run a frontend of your own.
- [`docker/README.md`](../docker/README.md) - what each container file builds,
  and how to run either stack.
- [`ansible/README.md`](../ansible/README.md) - the full variable reference for
  the roles.
- [`config/check-opencloud-security.example.yml`](../config/check-opencloud-security.example.yml) -
  every setting, commented.
- [`contrib/`](../contrib/) - the systemd unit, timer and cron files the
  scheduling page refers to.
- [`SECURITY.md`](../SECURITY.md) - reporting a vulnerability, and verifying
  what you downloaded.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) - how to propose a change.

Every example uses `opencloud.example.com` as the instance. Substitute your
own, and scan only instances you are responsible for.

## Trademarks and affiliation

This is an independent community project. It is **not** affiliated with,
endorsed by, sponsored by or supported by OpenCloud GmbH, and nothing it
reports is an official statement about OpenCloud software.

"OpenCloud", the OpenCloud logo and all related names and marks are the
property of their respective owners. They appear here only to identify the
software this tool checks, which is nominative use and implies no
relationship. All rights in OpenCloud remain with OpenCloud GmbH.
