"""
The MCP interface.

MCP is the third description of one service, and the risk it carries is
divergence: a tool that polls differently from the Arazzo document, or that
reaches the store directly and so slips past a rate limit a browser cannot.
These tests speak the actual protocol over the mounted endpoint, and they
check the two properties that matter - that the tools go through the ordinary
API, and that the destructive one still needs the operator's credential.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

pytest.importorskip("mcp", reason="the MCP extra is not installed")

from fastapi.testclient import TestClient

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    settings,
)
from webapp import workflows as wf
from webapp.app import create_app
from webapp.arazzo import arazzo_document
from webapp.mcp_server import ARAZZO_RESOURCE, OPENAPI_RESOURCE

TARGET = "https://opencloud.example.com"

_HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
}


@pytest.fixture(autouse=True)
def _instant_waits(monkeypatch):
    """
    Every wait the workflows take, taken instantly.

    A retry-after here is a real minute, and a poll interval is three real
    seconds. The behaviour under test is which call is refused and which is
    retried, never how long the process sat still for.
    """
    async def _now(_seconds: float) -> None:
        return None

    monkeypatch.setattr(wf, "default_sleep", _now)


@contextmanager
def client(**overrides):
    """
    A client with the application's lifespan actually running.

    The MCP session manager is started there, because a mounted sub-app never
    gets a lifespan of its own - which is exactly the mistake this helper
    exists to stop a test from making on the application's behalf.
    """
    with TestClient(create_app(settings(**overrides))) as served:
        yield served


def _call(served, method, params=None, headers=None):
    """One JSON-RPC call over the streamable HTTP transport."""
    response = served.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers={**_HEADERS, **(headers or {})},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _tools(served):
    return {
        tool["name"]: tool for tool in _call(served, "tools/list")["result"]["tools"]
    }


def _tool(served, name, arguments, headers=None):
    """One tool call, with the structured payload the tool returned."""
    answer = _call(
        served, "tools/call", {"name": name, "arguments": arguments}, headers=headers
    )
    return json.loads(answer["result"]["content"][0]["text"])


def test_the_endpoint_performs_a_protocol_level_initialisation():
    """An agent that cannot initialise cannot discover anything else."""
    with client() as served:
        answer = _call(
            served,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )

    result = answer["result"]
    assert result["serverInfo"]["name"] == "check-opencloud-security"
    assert "tools" in result["capabilities"]
    assert "resources" in result["capabilities"]
    assert "asynchronous" in result["instructions"].lower()


def test_the_published_path_answers_without_a_redirect():
    """A client that will not repeat a POST after a 307 must still reach it."""
    with client() as served:
        direct = served.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers=_HEADERS,
            follow_redirects=False,
        )

    assert direct.status_code == 200


def test_the_tools_are_user_level_tasks_rather_than_one_per_endpoint():
    """An agent asked to scan should call one tool, not orchestrate five."""
    with client() as served:
        tools = _tools(served)

    assert set(tools) == {
        "scan_instance",
        "scan_instances",
        "get_scan_result",
        "plan_remediation",
        "export_scan",
        "erase_instance_data",
    }
    # The negative half: the raw endpoints are not exposed one by one.
    assert "create_scan" not in tools
    assert "get_scan" not in tools


def test_every_tool_describes_its_inputs_outputs_and_when_to_stop():
    """A tool description is the only documentation the model ever reads."""
    with client() as served:
        tools = _tools(served)

    scan = tools["scan_instance"]
    assert "target_url" in scan["inputSchema"]["properties"]
    assert scan["inputSchema"]["required"] == ["target_url"]
    assert "rating" in scan["description"]
    assert "retryable" in scan["description"]

    erase = tools["erase_instance_data"]
    assert erase["annotations"]["destructiveHint"] is True
    assert "confirm" in erase["description"].lower()
    # The negative half: the credential is not a tool argument, so it can
    # never end up in the model's context.
    assert set(erase["inputSchema"]["properties"]) == {"target"}


def test_the_specifications_are_offered_as_resources_an_agent_can_read():
    """An agent that needs the raw contract should not have to leave the protocol."""
    with client() as served:
        resources = {
            item["uri"]
            for item in _call(served, "resources/list")["result"]["resources"]
        }
        read = _call(served, "resources/read", {"uri": ARAZZO_RESOURCE})

    assert {OPENAPI_RESOURCE, ARAZZO_RESOURCE} <= resources
    document = json.loads(read["result"]["contents"][0]["text"])
    assert document["arazzo"] == arazzo_document()["arazzo"]
    assert [w["workflowId"] for w in document["workflows"]] == [
        w["workflowId"] for w in arazzo_document()["workflows"]
    ]


def test_reading_an_unknown_scan_answers_a_refusal_the_model_can_act_on():
    """A 404 has to arrive as a decision, not as a traceback or an empty result."""
    with client() as served:
        result = _tool(served, "get_scan_result", {"uuid": "does-not-exist"})

    assert result["ok"] is False
    assert result["status"] == 404
    # The negative half: it is not marked retryable, or an agent will loop.
    assert result["retryable"] is False


def test_a_started_scan_is_reported_as_unfinished_with_a_wait():
    """Not done yet is an answer; an agent needs to be told how long to wait."""
    with client() as served:
        identifier = served.post(
            "/api/scans", json={"target_url": TARGET}
        ).json()["uuid"]
        result = _tool(served, "get_scan_result", {"uuid": identifier})

    assert result["done"] is False
    assert result["state"] in wf.PENDING_STATES
    assert result["retryAfterSeconds"] == wf.POLL_INTERVAL_SECONDS


def test_a_tool_goes_through_the_api_and_meets_the_same_rate_limit():
    """A second front door with its own rules is how a public service is abused."""
    with client(ip_rate_limit=1, ip_rate_window=60) as served:
        first = _tool(served, "scan_instance", {"target_url": TARGET, "wait": False})
        second = _tool(
            served,
            "scan_instance",
            {"target_url": "https://other.example.com", "wait": False},
        )

    # The first is accepted; the second meets the limit the HTTP API enforces,
    # after the polite retries, which an agent could not otherwise reach.
    assert first["ok"] is True
    assert second["ok"] is False
    assert second["status"] == 429
    assert second["retryable"] is True


def test_a_private_target_is_refused_by_the_same_guard_a_browser_meets():
    """MCP must not become the way to point the scanner at somebody's network."""
    with client() as served:
        result = _tool(served, "scan_instance", {"target_url": "http://127.0.0.1:8080"})

    assert result["ok"] is False
    assert result["status"] == 400
    assert result["retryable"] is False


def test_erasure_through_mcp_still_needs_the_operators_credential():
    """The destructive call must not be easier to make through an agent."""
    with client(purge_token="s3cret") as served:
        denied = _tool(
            served, "erase_instance_data", {"target": "opencloud.example.com"}
        )
        allowed = _tool(
            served,
            "erase_instance_data",
            {"target": "opencloud.example.com"},
            headers={"authorization": "Bearer s3cret"},
        )

    assert denied["ok"] is False
    assert denied["status"] == 401
    assert allowed["ok"] is True
    assert allowed["complete"] is True
    # The negative half: the credential is not handed back to the model.
    assert "s3cret" not in json.dumps(allowed)


def test_erasure_is_absent_in_practice_where_the_operator_did_not_deploy_it():
    """A deployment without the feature answers as if the endpoint never existed."""
    with client() as served:
        result = _tool(
            served,
            "erase_instance_data",
            {"target": "opencloud.example.com"},
            headers={"authorization": "Bearer anything"},
        )

    assert result["ok"] is False
    assert result["status"] == 404


def test_the_endpoint_disappears_when_an_operator_turns_it_off():
    """An operator who does not want an agent interface must be able to say so."""
    with client(enable_mcp=False) as served:
        response = served.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers=_HEADERS,
        )

    assert response.status_code == 404


def test_the_tools_and_the_workflow_document_share_their_semantics():
    """Two descriptions of one behaviour drift; one constant cannot."""
    poll = next(
        workflow
        for workflow in arazzo_document()["workflows"]
        if workflow["workflowId"] == "awaitScanResult"
    )["steps"][0]
    retry = next(a for a in poll["onFailure"] if a["type"] == "retry")

    assert retry["retryAfter"] == wf.POLL_INTERVAL_SECONDS
    assert retry["retryLimit"] == wf.POLL_MAX_ATTEMPTS

    with client() as served:
        tools = _tools(served)

    assert str(wf.MAX_SCAN_SECONDS // 60) in tools["scan_instance"]["description"]


def test_two_agents_at_different_addresses_do_not_share_one_rate_limit_bucket():
    """One bucket for the whole world is a rate limit that rations strangers by each other."""
    made = settings(ip_rate_limit=1, ip_rate_window=60)
    app = create_app(made)

    # One lifespan, three peers: the session manager may only be started once,
    # so the later clients ride the running application rather than restart it.
    with TestClient(app, client=("203.0.113.7", 1111)) as first_agent:
        first = _tool(
            first_agent, "scan_instance", {"target_url": TARGET, "wait": False}
        )
        second = _tool(
            TestClient(app, client=("198.51.100.9", 2222)),
            "scan_instance",
            {"target_url": "https://other.example.com", "wait": False},
        )
        third = _tool(
            TestClient(app, client=("203.0.113.7", 3333)),
            "scan_instance",
            {"target_url": "https://third.example.com", "wait": False},
        )

    assert first["ok"] is True
    # A different address is a different visitor, and gets its own allowance.
    assert second["ok"] is True
    # The negative half: the same address is still held to one request.
    assert third["ok"] is False
    assert third["status"] == 429


def test_a_service_already_full_of_waiting_scans_hands_back_a_uuid_instead_of_refusing():
    """Overload queues here; a tool call that cannot wait still starts the scan."""
    with client(mcp_max_concurrent_waits=0) as served:
        result = _tool(served, "scan_instance", {"target_url": TARGET, "wait": True})

    assert result["ok"] is True
    assert result["uuid"]
    # The negative half: nothing was refused, and the caller is told what to do.
    assert result["done"] is False
    assert "get_scan_result" in result["note"]


def test_the_planning_tool_tells_the_model_not_to_redo_the_arithmetic():
    """A model that recomputes the grades would contradict the scanner itself."""
    with client() as served:
        tools = _tools(served)

    planner = tools["plan_remediation"]
    assert set(planner["inputSchema"]["properties"]) == {"uuid"}
    assert planner["annotations"]["readOnlyHint"] is True
    description = planner["description"].lower()
    assert "order" in description
    assert "recalculate" in description or "recompute" in description
    # The negative half: the model is warned that a step gaining nothing is
    # still necessary, or it will drop exactly those steps as pointless.
    assert "ratinggain is 0" in description


def test_planning_an_unknown_scan_stops_instead_of_polling_forever():
    """The planner shares the workflow's refusals; a 404 is final there too."""
    with client() as served:
        result = _tool(served, "plan_remediation", {"uuid": "does-not-exist"})

    assert result["ok"] is False
    assert result["status"] == 404
    assert result["retryable"] is False
