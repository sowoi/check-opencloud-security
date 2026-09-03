"""The Markdown documents published as local frontend pages."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentationPage:
    """One source document and its stable browser address."""

    slug: str
    source: str
    title: str
    description: str
    start_heading: str | None = None
    end_heading: str | None = None
    demote_headings: bool = False


DOCUMENTATION_PAGES: tuple[DocumentationPage, ...] = (
    DocumentationPage(
        "what-is-opencloud",
        "docs/what-is-opencloud.md",
        "What OpenCloud is, and how it differs from ownCloud and Nextcloud",
        "The fork history behind OpenCloud, ownCloud and Nextcloud, and the architecture, storage and release differences between them.",
    ),
    DocumentationPage(
        "secure-deployment",
        "docs/secure-deployment.md",
        "Running OpenCloud in a secure infrastructure",
        "Put OpenCloud behind Keycloak, Authentik or Authelia, enable and ship the audit log, firewall the debug ports, and monitor it continuously.",
    ),
    DocumentationPage(
        "cli-reference",
        "docs/cli-reference.md",
        "OpenCloud Security Scanner CLI option reference",
        "Every command-line flag, its default, and the environment variable that sets the same thing.",
    ),
    DocumentationPage(
        "reference",
        "README.md",
        "OpenCloud Security Scanner CLI reference",
        "Install, configure, rate, and automate the OpenCloud Security Scanner CLI.",
        start_heading="# Quick start",
        end_heading="# Contributing",
        demote_headings=True,
    ),
    DocumentationPage(
        "installation",
        "docs/installation.md",
        "Installing the OpenCloud Security Scanner plugin",
        "Install with pipx, uv, pip or Docker, keep it current, and wire it into Icinga2 or Nagios.",
    ),
    DocumentationPage(
        "examples",
        "docs/examples.md",
        "OpenCloud Security Scanner worked examples",
        "Copy-and-paste invocations for release tracks, waivers, private instances, thresholds and notifications.",
    ),
    DocumentationPage(
        "scanner-checks",
        "docs/scanner-checks.md",
        "What the OpenCloud Security Scanner reads, and what it does not",
        "Every endpoint read, every additional check and its severity, and the questions a scan from outside cannot answer.",
    ),
    DocumentationPage(
        "release-lifecycle",
        "docs/release-lifecycle.md",
        "OpenCloud release tracks, end of life and update recommendations",
        "Why the same version can be current on one track and dead on another, and what --release-track changes.",
    ),
    DocumentationPage(
        "hardening",
        "docs/hardening.md",
        "OpenCloud hardening measures, one by one",
        "What each hardening identifier means, which OpenCloud setting changes it, and how to waive one.",
    ),
    DocumentationPage(
        "configuration",
        "docs/configuration.md",
        "Secrets in the OpenCloud Security Scanner configuration",
        "Resolve credentials from Docker secrets, files, the environment or a command instead of writing them down.",
    ),
    DocumentationPage(
        "baseline",
        "docs/baseline.md",
        "Report only what changed between OpenCloud scans",
        "Use --baseline and --warn-on-new to alert on new or worse findings rather than the same one every run.",
    ),
    DocumentationPage(
        "scan-service",
        "docs/scan-service.md",
        "Run the OpenCloud scanner as a local HTTP service",
        "Share one cached scan result between consumers with check-opencloud-scanner serve.",
    ),
    DocumentationPage(
        "scanner",
        "opencloud_local_scan/README.md",
        "OpenCloud Security Scanner library and JSON CLI",
        "Use the OpenCloud Security Scanner library, JSON result document, and direct CLI.",
    ),
    DocumentationPage(
        "docker",
        "docs/docker-oneliner.md",
        "Run the OpenCloud Security Scanner with Docker",
        "Run OpenCloud security scans in Docker, including JSON output and private networks.",
    ),
    DocumentationPage(
        "scheduling",
        "docs/scheduling.md",
        "Schedule OpenCloud security scans with systemd and cron",
        "Run the OpenCloud Security Scanner on a schedule without a monitoring server.",
    ),
    DocumentationPage(
        "many-instances",
        "docs/many-instances.md",
        "Scan a fleet with the OpenCloud Security Scanner",
        "Scan multiple OpenCloud instances with per-instance configuration and visible waivers.",
    ),
    DocumentationPage(
        "ci",
        "docs/ci.md",
        "OpenCloud security checks in CI pipelines",
        "Run the OpenCloud Security Scanner in GitHub Actions and GitLab CI.",
    ),
    DocumentationPage(
        "prometheus",
        "docs/prometheus.md",
        "OpenCloud security metrics for Prometheus and Grafana",
        "Expose OpenCloud Security Scanner metrics, dashboards, and alerting rules.",
    ),
    DocumentationPage(
        "kubernetes",
        "docs/kubernetes.md",
        "Run the OpenCloud Security Scanner on Kubernetes",
        "Deploy scheduled scans, metrics, and the self-hosted web service on Kubernetes.",
    ),
    DocumentationPage(
        "mcp",
        "docs/mcp.md",
        "OpenCloud Security Scanner for AI agents and MCP",
        "Connect agents to the OpenCloud Security Scanner task-level MCP tools.",
    ),
    DocumentationPage(
        "ansible",
        "docs/ansible.md",
        "Deploy the OpenCloud Security Scanner with Ansible",
        "Deploy the native OpenCloud security check or its container with Ansible.",
    ),
    DocumentationPage(
        "authentik",
        "docs/authentik.md",
        "Protect OpenCloud Security Scanner MCP with Authentik",
        "Protect the scanner's agent endpoint with a self-hosted OAuth provider.",
    ),
    DocumentationPage(
        "icinga-director",
        "docs/icinga-director.md",
        "OpenCloud Security Scanner in Icinga Director",
        "Import OpenCloud security check commands, fields, and apply rules into Icinga Director.",
    ),
    DocumentationPage(
        "reverse-proxy",
        "docs/reverse-proxy.md",
        "Reverse proxy the OpenCloud Security Scanner",
        "Configure scanner reverse-proxy headers for nginx, Apache, Caddy, Traefik, and HAProxy.",
    ),
    DocumentationPage(
        "webhooks",
        "docs/webhook-recipes.md",
        "OpenCloud security scanner webhook recipes",
        "Connect OpenCloud security results to alerting systems and test them safely.",
    ),
    DocumentationPage(
        "web-service",
        "docs/webapp.md",
        "Deploy the OpenCloud Security Scanner web service",
        "Deploy, configure, and operate the OpenCloud security scan browser, API, and worker stack.",
    ),
    DocumentationPage(
        "redis",
        "docs/redis.md",
        "Redis behind the OpenCloud Security Scanner web service",
        "Secure, size, and operate the Redis instance that queues OpenCloud security scans.",
    ),
    DocumentationPage(
        "output-formats",
        "docs/output-formats.md",
        "Machine-readable OpenCloud scan output: JSON, SARIF and JUnit",
        "Compare --format json, sarif and junit and wire each into a CI pipeline or dashboard.",
    ),
    DocumentationPage(
        "csp",
        "docs/csp.md",
        "Content-Security-Policy checks explained",
        "What the OpenCloud Security Scanner's two CSP checks look for, and why unsafe-inline fails.",
    ),
    DocumentationPage(
        "tls",
        "docs/tls.md",
        "TLS and certificate checks explained",
        "Every TLS and certificate check the OpenCloud Security Scanner runs, and why each one matters.",
    ),
    DocumentationPage(
        "status-php",
        "docs/status-php.md",
        "Why OpenCloud still answers /status.php",
        "The PHP-era compatibility endpoint OpenCloud still serves, its hardcoded fields, and what this scanner reads from it.",
    ),
    DocumentationPage(
        "cookies",
        "docs/cookies.md",
        "Cookie attribute checks explained",
        "The Secure, HttpOnly and SameSite checks the OpenCloud Security Scanner runs against observed cookies.",
    ),
    DocumentationPage(
        "authentication",
        "docs/authentication.md",
        "Authentication checks explained",
        "How the OpenCloud Security Scanner tests protected endpoints, HTTP Basic auth, demo accounts and password policy.",
    ),
    DocumentationPage(
        "sharing",
        "docs/sharing.md",
        "Public link sharing checks explained",
        "The password and expiration checks the OpenCloud Security Scanner runs against public share links.",
    ),
    DocumentationPage(
        "exposure",
        "docs/exposure.md",
        "Exposed path and debug endpoint checks explained",
        "The deployment files, debug endpoints and ports the OpenCloud Security Scanner checks are not publicly reachable.",
    ),
    DocumentationPage(
        "embedding",
        "docs/embedding.md",
        "Iframe embedding checks explained",
        "The origin-restriction checks the OpenCloud Security Scanner runs against embedding OpenCloud's web client in an iframe.",
    ),
    DocumentationPage(
        "lifecycle",
        "docs/lifecycle.md",
        "Version and lifecycle disclosure checks explained",
        "How the OpenCloud Security Scanner checks that a version was determined at all, and whether it leaks in a header or webfinger.",
    ),
    DocumentationPage(
        "troubleshooting",
        "docs/troubleshooting.md",
        "Troubleshoot the OpenCloud Security Scanner",
        "Resolve OpenCloud security scan errors and interpret the exit-code reference.",
    ),
)

DOCUMENTATION_BY_SLUG = {page.slug: page for page in DOCUMENTATION_PAGES}
