# Documentation

The [main README](../README.md) is the reference: every option, every setting
and what the scanner actually checks. These pages are the longer material that
was crowding it out - the deployment guides, and worked examples for the
places this check tends to end up.

> **Just want a scan?** [scan.okxo.de](https://scan.okxo.de) runs the web
> application from this repository - paste an address and read the result, no
> installation. [The public scan service](webapp.md) explains how to run your
> own, without a rate limit.

## Deploying it

| Page | What it covers |
|:-----|:---------------|
| [Icinga Director](icinga-director.md) | Creating the `CheckCommand`, data fields, service template and apply rule through the web UI |
| [Automated deployment with Ansible](ansible.md) | The native and Docker roles, the variables, and deploying the Icinga2 objects without clicking |
| [Scheduling](scheduling.md) | systemd timer and cron, for hosts with no Icinga2 or Nagios |
| [Kubernetes](kubernetes.md) | A `CronJob` for scheduled scans, and the scan service as a `Deployment` with probes |
| [Running the check from CI](ci.md) | GitHub Actions and GitLab CI, and gating a pipeline on a field of the result document |
| [Using the scanner from an AI agent](mcp.md) | The MCP endpoint at `/mcp`: worked configuration for Claude Code, Claude Desktop, GitHub Copilot in VS Code and the CLI, Cursor, Zed and Windsurf, against [scan.okxo.de](https://scan.okxo.de) or your own deployment - and how to turn it off |
| [Reverse proxies](reverse-proxy.md) | Worked nginx, Apache, Caddy, Traefik and HAProxy configuration - the headers this check grades in front of OpenCloud, and what the scan service needs from a proxy |
| [The public scan service](webapp.md) | The self-hosted web application: FastAPI, an ARQ worker and Redis, with queueing, SSRF and rate limits. Running at [scan.okxo.de](https://scan.okxo.de) |

## Feeding the result somewhere

| Page | What it covers |
|:-----|:---------------|
| [Prometheus and Grafana](prometheus.md) | Textfile collector, Pushgateway, alerting rules and what to graph |
| [Webhook recipes](webhook-recipes.md) | The payload, and adapters for Slack, Discord, ntfy and Alertmanager |
| [Uptime Kuma](../README.md#uptime-kuma) | The webhook as a Push monitor - in the main README |

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
