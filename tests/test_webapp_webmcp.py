"""Browser WebMCP registration and the public LLM discovery file."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
)
from webapp.catalog import release_track_options, waiver_options
from webapp.reports import EXPORT_FORMATS
from webapp.settings import IndexMetaTag, WebSettings

ROOT = Path(__file__).resolve().parent.parent


def _tool_config(markup: str) -> list[dict[str, object]]:
    match = re.search(r'data-tools="([^"]+)"', markup)
    assert match is not None
    return json.loads(html.unescape(match.group(1)))


def test_the_landing_page_registers_a_scan_tool_from_its_real_options():
    """An agent sees the same tracks and waivers as the form, not a copied list."""
    page = client().get("/")

    assert '<script src="/static/js/webmcp.js" defer></script>' in page.text
    tools = _tool_config(page.text)
    assert [tool["name"] for tool in tools] == ["scan_opencloud_security"]

    schema = tools[0]["inputSchema"]
    properties = schema["properties"]
    assert properties["release_track"]["enum"] == [
        option.id for option in release_track_options()
    ]
    assert properties["ignore_hardenings"]["items"]["enum"] == [
        option.id for option in waiver_options()
    ]
    assert properties["output_format"]["enum"] == [
        "dashboard",
        "json",
        "csv",
        "sarif",
        "pdf",
    ]
    assert "concurrency" not in properties
    assert "timeout" not in properties


def test_a_result_page_registers_read_and_export_tools_only_for_its_uuid():
    """Page tools may address the current capability but never list other scans."""
    served = client()
    identifier = served.post(
        "/api/scans", json={"target_url": "https://opencloud.example.com"}
    ).json()["uuid"]

    page = served.get(f"/scan/{identifier}")
    tools = _tool_config(page.text)

    assert [tool["name"] for tool in tools] == [
        "get_scan_result",
        "export_scan_report",
    ]
    assert tools[0]["endpoint"] == f"/scan/{identifier}?output_format=json"
    assert tools[1]["endpoint"] == f"/api/scans/{identifier}/export/"
    assert tools[1]["inputSchema"]["properties"]["format"]["enum"] == list(
        EXPORT_FORMATS
    )
    assert "/api/scans" not in client().get("/privacy").text
    assert "webmcp-config" not in client().get("/privacy").text


def test_webmcp_disappears_with_the_mcp_endpoint():
    """One operator switch disables both browser and server MCP surfaces."""
    served = client(enable_mcp=False)
    identifier = served.post(
        "/api/scans", json={"target_url": "https://opencloud.example.com"}
    ).json()["uuid"]

    for path in ("/", f"/scan/{identifier}"):
        page = served.get(path)
        assert "webmcp-config" not in page.text
        assert "/static/js/webmcp.js" not in page.text


def test_webmcp_uses_feature_detection_and_the_existing_json_api():
    """Browser tools stay inert without WebMCP and use no privileged backend path."""
    script = client().get("/static/js/webmcp.js").text

    assert 'if ("modelContext" in navigator)' in script
    assert 'else if ("modelContext" in document)' in script
    assert 'document.addEventListener("DOMContentLoaded"' in script
    assert '"Accept": "application/json"' in script
    assert '"Content-Type": "application/json"' in script
    assert "fetch(endpoint" in script
    assert "/internal" not in script
    assert "unsafe-inline" not in client().get("/").headers[
        "content-security-policy"
    ]


def test_json_output_overrides_a_browser_html_accept_header():
    """Choosing JSON returns structured acceptance instead of an HTML redirect."""
    response = client().post(
        "/",
        data={
            "target_url": "https://opencloud.example.com",
            "output_format": "json",
        },
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code == 202
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["state"] == "queued"
    assert "location" in response.headers


def test_a_result_page_negotiates_the_same_scan_record_as_the_api():
    """Accept and output_format provide JSON without changing capability checks."""
    served = client()
    identifier = served.post(
        "/api/scans", json={"target_url": "https://opencloud.example.com"}
    ).json()["uuid"]

    api = served.get(f"/api/scans/{identifier}")
    by_accept = served.get(
        f"/scan/{identifier}", headers={"Accept": "application/json"}
    )
    by_query = served.get(f"/scan/{identifier}?output_format=json")

    assert by_accept.status_code == 200
    assert by_accept.json() == api.json()
    assert by_query.json() == api.json()
    assert "<html" not in by_accept.text

    missing = served.get(
        "/scan/not-a-uuid", headers={"Accept": "application/json"}
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Not found."}


def test_llms_txt_maps_the_public_agent_surfaces_without_exposing_a_scan():
    """Discovery may name contracts and tools but must never enumerate capabilities."""
    served = client()
    identifier = served.post(
        "/api/scans", json={"target_url": "https://opencloud.example.com"}
    ).json()["uuid"]

    response = served.get("/llms.txt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    for path in (
        "/llms.txt",
        "/.well-known/ai.json",
        "/openapi.json",
        "/arazzo.json",
        "/mcp",
        "/api/scans/{uuid}",
    ):
        assert path in response.text
    assert "scan_opencloud_security" in response.text
    assert "Massoud Ahmed" in response.text
    assert "not affiliated with" in response.text
    assert identifier not in response.text
    assert "Allow: /llms.txt" in served.get("/robots.txt").text


def test_optional_index_meta_tags_are_typed_escaped_and_landing_page_only():
    """Compose metadata cannot become raw markup or leak onto result pages."""
    served = client(
        index_meta_tags=(
            IndexMetaTag(
                name="fediverse:creator",
                content='@scanner@social.example.com"><script>',
            ),
            IndexMetaTag(name="custom-verification", content="verification-token"),
        )
    )
    identifier = served.post(
        "/api/scans", json={"target_url": "https://opencloud.example.com"}
    ).json()["uuid"]

    landing = served.get("/").text
    assert 'name="fediverse:creator"' in landing
    assert (
        'content="@scanner@social.example.com&#34;&gt;&lt;script&gt;"' in landing
    )
    assert "<script>" not in landing
    assert 'name="custom-verification" content="verification-token"' in landing
    assert "fediverse:creator" not in served.get(f"/scan/{identifier}").text
    assert "fediverse:creator" not in client().get("/").text


def test_the_index_meta_environment_value_accepts_a_bounded_tag_list(
    monkeypatch,
):
    """The environment may provide bounded inert tags, not rewrite the document head."""
    monkeypatch.setenv(
        "COS_WEB_INDEX_META_TAG",
        "custom-verification=verification-token",
    )
    configured = WebSettings.from_env()
    assert configured.index_meta_tags == (
        IndexMetaTag(name="custom-verification", content="verification-token"),
    )
    monkeypatch.setenv(
        "COS_WEB_INDEX_META_TAG",
        "custom-verification=first;fediverse:creator=@scanner@social.example.com",
    )
    assert WebSettings.from_env().index_meta_tags == (
        IndexMetaTag(name="custom-verification", content="first"),
        IndexMetaTag(name="fediverse:creator", content="@scanner@social.example.com"),
    )

    for invalid in (
        "<script>",
        "robots=noindex",
        "google-site-verification=token",
        "twitter:card=summary",
        "custom-verification=first;custom-verification=second",
    ):
        monkeypatch.setenv("COS_WEB_INDEX_META_TAG", invalid)
        with pytest.raises(ValueError):
            WebSettings.from_env()


def test_both_compose_stacks_pass_the_optional_index_meta_setting():
    """A setting documented for Compose must reach either shipped web stack."""
    for name in ("docker-compose.yml", "docker-compose.authentik.yml"):
        compose = (ROOT / "docker" / name).read_text(encoding="utf-8")
        assert 'COS_WEB_INDEX_META_TAG: "${COS_WEB_INDEX_META_TAG:-}"' in compose
