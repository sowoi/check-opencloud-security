"""
Public discovery.

An agent that knows only this service's address has to be able to find the
contract, and it will not guess ``/arazzo.json``. These tests hold the
discovery path, the documents it names and the hints in the markup to that
promise - including the part that matters most, which is that none of it
depends on an operator having switched something on.
"""

from __future__ import annotations

import re

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
    settings,
)
from webapp.discovery import DISCOVERY_PATH, discovery_document

ORIGIN = "https://scan.example.com"


def test_an_unauthenticated_client_can_read_the_discovery_document():
    """The whole point is that nobody has to be let in first."""
    response = client().get(DISCOVERY_PATH)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")

    document = response.json()
    assert document["name"] == "check-opencloud-security"
    assert document["api"]["openapi"].endswith("/openapi.json")
    assert document["api"]["arazzo"].endswith("/arazzo.json")
    assert document["mcp"]["url"].endswith("/mcp")


def test_agents_json_serves_the_same_document_under_the_name_agents_txt_com_wants():
    """
    agents-txt.com recommends a structured sibling next to `agents.txt`.

    Rather than maintain a second document, `/agents.json` serves exactly
    what `/.well-known/ai.json` already does, so the two can never disagree.
    """
    served = client()

    discovery = served.get(DISCOVERY_PATH)
    agents_json = served.get("/agents.json")

    assert agents_json.status_code == 200
    assert agents_json.headers["content-type"].startswith("application/json")
    assert agents_json.headers["access-control-allow-origin"] == "*"
    assert agents_json.json() == discovery.json()


def test_the_discovery_document_names_absolute_urls_that_this_service_serves():
    """A relative path in a document that got copied elsewhere is a dead end."""
    served = client(public_base_url=ORIGIN)
    document = served.get(DISCOVERY_PATH).json()

    named = [document["api"]["openapi"], document["api"]["arazzo"]]
    assert all(url.startswith(ORIGIN) for url in named), named

    for url in named:
        assert served.get(url.removeprefix(ORIGIN)).status_code == 200
    # The negative half: a deployment that did not configure an origin still
    # gets absolute URLs, built from the request rather than left relative.
    fallback = client().get(DISCOVERY_PATH).json()
    assert fallback["api"]["openapi"].startswith("http")


def test_the_discovery_document_explains_the_rules_an_agent_has_to_follow():
    """Discovering an endpoint is not enough; the semantics decide correctness."""
    document = discovery_document(ORIGIN)

    usage = document["usage"]
    assert "asynchronous" in usage and "identifiers" in usage
    assert usage["pollIntervalSeconds"] > 0
    assert "429" in usage["rateLimits"]
    assert {capability["name"] for capability in document["capabilities"]} == {
        "scan_instance",
        "scan_instances",
        "get_scan_result",
        "plan_remediation",
        "export_scan",
        "erase_instance_data",
    }


def test_the_discovery_document_does_not_claim_to_be_a_standard():
    """Claiming a registry entry that does not exist misleads whoever trusts it."""
    document = discovery_document(ORIGIN)

    assert "not a registered standard" in document["notes"]
    assert "OpenCloud GmbH" in document["trademarks"]


def test_the_document_omits_mcp_when_the_endpoint_is_not_there():
    """Advertising an endpoint a deployment does not serve is worse than silence."""
    without = discovery_document(ORIGIN, mcp_enabled=False)
    assert "mcp" not in without

    served = client(enable_mcp=False).get(DISCOVERY_PATH).json()
    assert "mcp" not in served


def test_every_page_carries_the_machine_readable_discovery_hints():
    """A crawler reading the markup should not have to be told where to look."""
    body = client().get("/").text

    links = dict(
        re.findall(r'<link rel="([^"]+)"[^>]*href="([^"]+)"', body)
    )
    assert links["service-desc"] == "/openapi.json"
    assert links["arazzo"] == "/arazzo.json"
    assert links["ai-discovery"] == DISCOVERY_PATH


def test_the_agent_page_points_a_human_at_the_same_three_documents():
    """A page people can read is also the page a crawler indexes."""
    body = client().get("/ai").text

    assert "For AI agents" in body
    for href in ("/openapi.json", "/arazzo.json", DISCOVERY_PATH):
        assert f'href="{href}"' in body, href
    assert "scan_instance" in body


def test_robots_allows_the_machine_readable_documents_and_still_hides_results():
    """The contract is meant to be found; a result is meant not to be."""
    body = client().get("/robots.txt").text

    assert f"Allow: {DISCOVERY_PATH}" in body
    assert "Allow: /openapi.json" in body
    assert "Allow: /arazzo.json" in body
    # The negative half: opening the specifications did not open the scans.
    assert "Disallow: /scan/" in body
    assert "Disallow: /api/" in body


def test_the_specifications_are_not_told_to_stay_out_of_an_index():
    """A noindex header on the contract contradicts the robots.txt beside it."""
    served = client()

    for path in ("/openapi.json", "/arazzo.json", DISCOVERY_PATH):
        assert "X-Robots-Tag" not in served.get(path).headers, path
    # The negative half: a result still carries it.
    identifier = served.post(
        "/api/scans", json={"target_url": "https://opencloud.example.com"}
    ).json()["uuid"]
    assert "X-Robots-Tag" in served.get(f"/api/scans/{identifier}").headers
