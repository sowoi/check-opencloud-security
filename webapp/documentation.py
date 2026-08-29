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
        "reference",
        "README.md",
        "OpenCloud Security Scanner CLI reference",
        "Install, configure, rate, and automate the OpenCloud Security Scanner CLI.",
        start_heading="# Quick start",
        end_heading="# Contributing",
        demote_headings=True,
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
