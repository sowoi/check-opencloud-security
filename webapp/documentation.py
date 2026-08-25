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
        "Complete CLI reference",
        "Installation, every CLI flag, configuration, ratings and worked examples.",
        start_heading="# Quick start",
        end_heading="# Contributing",
        demote_headings=True,
    ),
    DocumentationPage(
        "scanner",
        "opencloud_local_scan/README.md",
        "Scanner library and JSON CLI",
        "The result document, rating algorithm and direct scanner commands.",
    ),
    DocumentationPage(
        "docker",
        "docs/docker-oneliner.md",
        "Docker one-liner",
        "The published image, JSON output, private networks and shell shortcuts.",
    ),
    DocumentationPage(
        "scheduling",
        "docs/scheduling.md",
        "systemd and cron",
        "Run the check on a schedule without a monitoring server.",
    ),
    DocumentationPage(
        "many-instances",
        "docs/many-instances.md",
        "A fleet of instances",
        "Several hosts, one configuration per instance and honest waivers.",
    ),
    DocumentationPage(
        "ci",
        "docs/ci.md",
        "CI pipelines",
        "GitHub Actions, GitLab CI and reporting without failing.",
    ),
    DocumentationPage(
        "prometheus",
        "docs/prometheus.md",
        "Prometheus and Grafana",
        "Metrics, scrape patterns, dashboards and alerting rules.",
    ),
    DocumentationPage(
        "kubernetes",
        "docs/kubernetes.md",
        "Kubernetes",
        "A scheduled scan, metrics and a self-hosted web service.",
    ),
    DocumentationPage(
        "mcp",
        "docs/mcp.md",
        "AI agents and MCP",
        "Connect supported agents to the scanner's task-level tools.",
    ),
    DocumentationPage(
        "ansible",
        "docs/ansible.md",
        "Ansible",
        "Deploy the native check or its container and configure it consistently.",
    ),
    DocumentationPage(
        "authentik",
        "docs/authentik.md",
        "Authentik for the MCP endpoint",
        "Protect the agent endpoint with a self-hosted OAuth provider.",
    ),
    DocumentationPage(
        "icinga-director",
        "docs/icinga-director.md",
        "Icinga Director",
        "Import the command, fields and apply rules into Icinga Director.",
    ),
    DocumentationPage(
        "reverse-proxy",
        "docs/reverse-proxy.md",
        "Reverse proxies",
        "Headers and examples for nginx, Apache, Caddy, Traefik and HAProxy.",
    ),
    DocumentationPage(
        "webhooks",
        "docs/webhook-recipes.md",
        "Webhook recipes",
        "Receivers for common alerting systems and a safe local test.",
    ),
    DocumentationPage(
        "web-service",
        "docs/webapp.md",
        "The public scan service",
        "Deploy, configure and operate the browser, API and worker stack.",
    ),
    DocumentationPage(
        "troubleshooting",
        "docs/troubleshooting.md",
        "Troubleshooting",
        "The errors operators actually meet and the exit-code reference.",
    ),
)

DOCUMENTATION_BY_SLUG = {page.slug: page for page in DOCUMENTATION_PAGES}
