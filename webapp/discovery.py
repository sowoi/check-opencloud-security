"""
Public, machine-readable discovery.

An agent that knows only the domain has to be able to find the contract. It
will not guess ``/arazzo.json``, and naming a file after a specification is
not a discovery mechanism, so this module publishes one document that names
all of them: the OpenAPI description, the Arazzo workflows, the MCP endpoint
and the human-readable page beside them.

``/.well-known/ai.json`` is *this application's* discovery document, not a
registered standard. It is placed under ``/.well-known/`` because that is
where a well-behaved client looks for site-level metadata, and it is
deliberately small and explicit rather than clever: a name, a description,
and absolute URLs for everything an agent might want next.
"""

from __future__ import annotations

from typing import Any

from opencloud_local_scan import __version__

from . import workflows as wf
from .prompts import prompt_capabilities
from .seo import SITE_NAME

#: Where the document lives. Public, unauthenticated, and stable.
DISCOVERY_PATH = "/.well-known/ai.json"

OPENAPI_PATH = "/openapi.json"
ARAZZO_PATH = "/arazzo.json"
MCP_PATH = "/mcp"
API_PAGE_PATH = "/api"
#: The page written for agents rather than about the API in general.
AGENT_PAGE_PATH = "/ai"

#: The media type an OpenAPI document is served as, and the link relation a
#: client that understands one looks for.
OPENAPI_MEDIA_TYPE = "application/vnd.oai.openapi+json"
OPENAPI_LINK_REL = "service-desc"


def discovery_document(
    origin: str,
    *,
    mcp_enabled: bool = True,
    mcp_auth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    What this service is, and where to read the rest of it.

    Absolute URLs throughout: an agent may have been handed this document by
    something that did not keep the origin, and a relative path it cannot
    resolve is a dead end.
    """
    base = origin.rstrip("/")
    document: dict[str, Any] = {
        "name": "check-opencloud-security",
        "title": SITE_NAME,
        "version": __version__,
        "description": (
            "Public security scanning service for OpenCloud instances. Give "
            "it the URL of a publicly reachable instance and it answers with "
            "a rating from 0 to 5, the findings behind that rating, and "
            "exports in JSON, CSV, SARIF and PDF. No account, no API key, no "
            "registration."
        ),
        "documentation": f"{base}{AGENT_PAGE_PATH}",
        "apiDocumentation": f"{base}{API_PAGE_PATH}",
        "termsOfService": f"{base}/privacy",
        "sourceCode": wf.SELF_HOST_URL,
        "api": {
            "openapi": f"{base}{OPENAPI_PATH}",
            "arazzo": f"{base}{ARAZZO_PATH}",
            "baseUrl": f"{base}/api",
            "authentication": (
                "None. Scanning is open to anyone. Only the erasure endpoint "
                "requires the operator's bearer credential, which this "
                "service does not issue."
            ),
        },
        "usage": {
            "asynchronous": wf.ASYNC_NOTE,
            "identifiers": wf.UUID_NOTE,
            "rateLimits": wf.RATE_LIMIT_NOTE,
            "expiry": wf.EXPIRY_NOTE,
            "inputs": wf.INPUT_NOTE,
            "pollIntervalSeconds": wf.POLL_INTERVAL_SECONDS,
            "maxScanSeconds": wf.MAX_SCAN_SECONDS,
        },
        "capabilities": [
            {
                "name": "scan_instance",
                "description": "Scan one OpenCloud instance and return its rating.",
                "workflow": "scanOneInstance",
            },
            {
                "name": "scan_instances",
                "description": "Scan several instances in one submission.",
                "workflow": "scanManyInstances",
            },
            {
                "name": "get_scan_result",
                "description": "Read one scan by uuid without waiting for it.",
                "workflow": "awaitScanResult",
            },
            {
                "name": "plan_remediation",
                "description": (
                    "Turn one finished scan into its rating-preserving, "
                    "ordered remediation plan."
                ),
                "workflow": "planRemediation",
            },
            {
                "name": "compare_scans",
                "description": (
                    "Compare two finished scans of the same instance and say "
                    "what the changes between them achieved."
                ),
                "workflow": "compareScans",
            },
            {
                "name": "export_scan",
                "description": "Render a finished scan as JSON, CSV, SARIF or PDF.",
                "workflow": "exportFinishedScan",
            },
            {
                "name": "erase_instance_data",
                "description": (
                    "Delete every stored scan of one instance. Destructive, "
                    "and authorised by the operator's credential."
                ),
                "workflow": "eraseInstanceData",
            },
        ],
        "selfHost": {
            "url": wf.SELF_HOST_URL,
            "note": (
                "The whole scanner is open source and runs locally with no "
                "rate limits at all. An agent scanning more than a handful of "
                "instances should use it rather than this service."
            ),
        },
        "trademarks": (
            "Not affiliated with, endorsed by or supported by OpenCloud GmbH. "
            "'OpenCloud' and related marks belong to their owners and are "
            "used only to identify the software being checked."
        ),
        "notes": (
            "This document is an application-level convention of this "
            "service, not a registered standard. The URLs it names are the "
            "contract; the shape of this file may change."
        ),
    }
    if mcp_enabled:
        document["mcp"] = {
            "url": f"{base}{MCP_PATH}",
            "transport": "streamable-http",
            "protocol": "https://modelcontextprotocol.io",
            "description": (
                "Model Context Protocol endpoint. Initialize against this URL "
                "and use the protocol's own tools/list, prompts/list and "
                "resources/list to discover what it offers; the tools execute "
                "the workflows described in the Arazzo document, and two of "
                "the resources are a knowledge base - the check catalogue and "
                "the advisory database - readable without submitting a scan."
            ),
            "prompts": prompt_capabilities(),
            "authentication": mcp_auth
            or {
                "type": "none",
                "note": "No token required. Connect and initialize.",
            },
        }
    return document
