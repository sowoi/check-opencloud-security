"""Browser WebMCP registration and the public LLM discovery file."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

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


def _record_without_the_countdown(document: dict[str, Any]) -> dict[str, Any]:
    """
    The scan record minus ``expiresIn``.

    That field is the key's remaining TTL read as the request is served, so two
    responses fetched a moment apart legitimately differ by a second. Comparing
    it between requests tests the clock; every other field is the record.
    """
    return {key: value for key, value in document.items() if key != "expiresIn"}


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
    assert _record_without_the_countdown(by_accept.json()) == _record_without_the_countdown(
        api.json()
    )
    assert _record_without_the_countdown(by_query.json()) == _record_without_the_countdown(
        api.json()
    )
    # The countdown is still part of every one of the three answers, and still
    # a retention window rather than an arbitrary number - it is only its exact
    # value that must not be compared across requests.
    for negotiated in (api, by_accept, by_query):
        assert 0 < negotiated.json()["expiresIn"] <= 3600
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


# ------------------------------------- what a browser tool does when it fails


def _script() -> str:
    return (ROOT / "frontend" / "static" / "js" / "webmcp.js").read_text(encoding="utf-8")


def _tool(markup: str, name: str) -> dict[str, Any]:
    for tool in _tool_config(markup):
        if tool["name"] == name:
            return tool
    raise AssertionError(f"no tool named {name}")


def test_a_browser_tool_carries_the_retry_policy_the_workflow_layer_decided():
    """
    Whether an answer may be repeated is one decision, and it is not JavaScript's.

    A copy of these numbers in the script is a copy that drifts. The two would
    then disagree exactly where it matters: a 429 an agent reads as fatal is a
    scan nobody runs, and a 404 it reads as retryable is a loop against a scan
    that no longer exists.
    """
    from webapp.workflows import (
        EXPORT_RETRY_SECONDS,
        NOT_FINISHED_STATUS,
        RATE_LIMIT_FALLBACK_SECONDS,
        RETRYABLE_STATUSES,
    )

    served = client()
    identifier = served.post(
        "/api/scans", json={"target_url": "https://opencloud.example.com"}
    ).json()["uuid"]

    scan = _tool(served.get("/").text, "scan_opencloud_security")
    assert scan["retry"]["retryableStatuses"] == list(RETRYABLE_STATUSES)
    assert scan["retry"]["fallbackRetrySeconds"] == RATE_LIMIT_FALLBACK_SECONDS

    page = served.get(f"/scan/{identifier}").text
    export = _tool(page, "export_scan_report")
    # An export answers 409 while the scan is still running: the one status
    # worth repeating that is not a failure of the service.
    assert export["retry"]["notFinishedStatus"] == NOT_FINISHED_STATUS
    assert export["retry"]["notFinishedRetrySeconds"] == EXPORT_RETRY_SECONDS

    # The negative half, and the point of the exercise: the script holds no
    # copy of any of it. Comments may name a status while explaining why it is
    # handled - what must not exist is a number the code compares against.
    code = re.sub(r"/\*.*?\*/", "", _script(), flags=re.DOTALL)
    for number in (*RETRYABLE_STATUSES, NOT_FINISHED_STATUS, RATE_LIMIT_FALLBACK_SECONDS):
        assert str(number) not in code


def test_a_failed_browser_tool_answers_rather_than_throws():
    """
    The server-side tools promise ok: false with a retryable flag; these now do too.

    A thrown Error carries a sentence and nothing else - not the status, not
    the Retry-After the service sent - so an agent meeting a per-target
    cooldown cannot tell "wait forty seconds" from "this will never work".
    That is the loop the workflow layer was written to prevent, and a browser
    agent was outside it.
    """
    script = _script()

    assert "return failure(response, payload" in script
    assert 'answer.retryAfter = retryAfter' in script
    assert "retryable:" in script
    # A request that never reached the service is an answer too, not a throw.
    assert "function unreachable(error)" in script
    assert "AbortError" in script
    # The only throw left is a config this service never renders.
    assert script.count("throw ") == 1
    assert "Unknown WebMCP action" in script


def test_the_failure_shape_is_described_to_the_agent_that_will_meet_it():
    """A contract no tool description states is one an agent has to discover by failing."""
    served = client()
    identifier = served.post(
        "/api/scans", json={"target_url": "https://opencloud.example.com"}
    ).json()["uuid"]

    pages = [served.get("/").text, served.get(f"/scan/{identifier}").text]
    tools = [tool for page in pages for tool in _tool_config(page)]
    assert len(tools) == 3

    for tool in tools:
        description = tool["description"]
        assert "does not throw" in description
        assert "retryable false means stop" in description


def test_every_browser_tool_repeats_the_workflow_layers_own_guidance():
    """
    The notes exist once in workflows.py; the browser tools used to paraphrase them badly.

    Each of these answers a question an agent otherwise gets wrong: that a
    rating does not exist at submission time, that 429 is not a refusal, that
    a uuid is the whole of the authorisation, and that a result expires.
    """
    from webapp import workflows as wf

    served = client()
    identifier = served.post(
        "/api/scans", json={"target_url": "https://opencloud.example.com"}
    ).json()["uuid"]

    scan = _tool(served.get("/").text, "scan_opencloud_security")
    for note in (wf.ASYNC_NOTE, wf.INPUT_NOTE, wf.RATE_LIMIT_NOTE, wf.UUID_NOTE):
        assert note in scan["description"]

    page = served.get(f"/scan/{identifier}").text
    status = _tool(page, "get_scan_result")
    assert wf.EXPIRY_NOTE in status["description"]
    assert wf.CONFLICT_NOTE in _tool(page, "export_scan_report")["description"]


def test_a_tool_that_returns_a_scanned_hosts_words_says_where_they_came_from():
    """
    A scan result is text a stranger's server chose, arriving in an agent's context.

    The annotation is the machine-readable half and the note is the half a
    model actually reads. Both are needed: an agent that treats a product
    name as an instruction is the whole prompt-injection surface of this
    service.
    """
    from webapp import workflows as wf

    served = client()
    identifier = served.post(
        "/api/scans", json={"target_url": "https://opencloud.example.com"}
    ).json()["uuid"]

    page = served.get(f"/scan/{identifier}").text
    assert wf.REMOTE_NOTE in _tool(page, "get_scan_result")["description"]
    assert wf.EXPORT_NOTE in _tool(page, "export_scan_report")["description"]

    for tool in _tool_config(page) + _tool_config(served.get("/").text):
        assert tool["annotations"]["untrustedContentHint"] is True


def test_the_browser_tools_declare_the_same_hints_the_server_side_ones_do():
    """
    An agent decides whether to confirm with the user from these.

    The one deliberate difference is the export: the server-side tool is
    read-only, and this one writes a file into the visitor's downloads, which
    is a change to their machine even though the service is only read.
    """
    served = client()
    identifier = served.post(
        "/api/scans", json={"target_url": "https://opencloud.example.com"}
    ).json()["uuid"]

    scan = _tool(served.get("/").text, "scan_opencloud_security")
    assert scan["annotations"]["openWorldHint"] is True, "it reaches a host the caller names"
    assert scan["annotations"]["idempotentHint"] is False, "two calls are two scans"
    assert scan["annotations"]["destructiveHint"] is False

    page = served.get(f"/scan/{identifier}").text
    status = _tool(page, "get_scan_result")
    assert status["annotations"]["readOnlyHint"] is True
    assert status["annotations"]["openWorldHint"] is False

    export = _tool(page, "export_scan_report")
    assert export["annotations"]["readOnlyHint"] is False


def test_an_export_comes_back_as_something_the_agent_can_read():
    """
    A download alone leaves an agent holding a file it has no way to open.

    The text formats are the ones it can act on, so they are returned as
    content as well as saved; a PDF is reported as its size, because a model
    cannot read one. The bound is the server-side export's own, so neither
    surface pours more of a scanned host's words into a reader than the other.
    """
    from webapp.workflows import EXPORT_CONTENT_LIMIT

    served = client()
    identifier = served.post(
        "/api/scans", json={"target_url": "https://opencloud.example.com"}
    ).json()["uuid"]

    export = _tool(served.get(f"/scan/{identifier}").text, "export_scan_report")
    assert export["contentLimit"] == EXPORT_CONTENT_LIMIT

    script = _script()
    assert 'input.format !== "pdf"' in script
    assert "config.contentLimit" in script
    assert "answer.truncated = true" in script


def test_the_landing_page_sends_an_agent_to_where_the_reading_tool_lives():
    """
    Page-scoped tools mean the page that submits a scan cannot read one.

    ADR 0021 decided that deliberately, which leaves an agent holding a uuid
    and no tool - unless the tool that gave it the uuid says where to go. It
    does not gain a reader here: that would be a tool taking a uuid, which is
    a way to reach scans this visitor was never given.
    """
    scan = _tool(client().get("/").text, "scan_opencloud_security")

    assert "get_scan_result" in scan["description"]
    assert "Open the returned url" in scan["description"]
    assert scan["inputSchema"]["properties"].keys() == {
        "target_url",
        "release_track",
        "output_format",
        "ignore_hardenings",
    }
    assert "uuid" not in scan["inputSchema"]["properties"]


def test_no_browser_tool_accepts_a_uuid():
    """The negative half of page scoping, asserted where it would be lost."""
    served = client()
    identifier = served.post(
        "/api/scans", json={"target_url": "https://opencloud.example.com"}
    ).json()["uuid"]

    for tool in _tool_config(served.get(f"/scan/{identifier}").text):
        assert "uuid" not in tool["inputSchema"].get("properties", {})
        assert identifier in tool["endpoint"], "the page's own scan, fixed server side"


def test_the_registration_survives_one_tool_the_browser_will_not_take():
    """
    A result page registers two tools; one rejected must not cost the other.

    Promise.all rejects as a group, which on a result page would mean a bad
    export schema silently taking the reader with it.
    """
    script = _script()

    assert "Promise.allSettled" in script
    assert "Promise.all(" not in script


def test_the_declarative_shape_of_the_draft_is_used_where_a_browser_offers_it():
    """
    provideContext states the page's whole tool set; registerTool accumulates one.

    Both are the same draft and browsers differ on which they ship. Preferring
    the declarative one keeps a page's offer to an agent equal to what the
    page actually rendered.
    """
    script = _script()

    assert 'typeof modelContext.provideContext === "function"' in script
    assert 'typeof modelContext.registerTool !== "function"' in script
    # Still inert where the browser has neither, which is every browser today.
    assert 'if ("modelContext" in navigator)' in script
    assert 'else if ("modelContext" in document)' in script
