"""
The Arazzo description of the API.

A workflow document is only worth having if it stays true, so these tests
check it against the application's own OpenAPI schema rather than against a
copy of the paths written down twice.
"""

from __future__ import annotations

import re

from opencloud_local_scan import __version__
from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
    settings,
)
from webapp.arazzo import ARAZZO_VERSION, WORKFLOW_IDS, arazzo_document


def _referenced_paths(document) -> set[str]:
    """Every OpenAPI path an operationPath in the document points at."""
    found = set()
    for workflow in document["workflows"]:
        for step in workflow["steps"]:
            location = step.get("operationPath")
            if not location:
                continue
            pointer = location.split("#/paths/", 1)[1]
            path = pointer.rsplit("/", 1)[0].replace("~1", "/")
            found.add(re.sub(r"\{[a-zA-Z]+\}", "{}", path))
    return found


def test_the_document_describes_this_build_and_its_workflows():
    """A workflow file naming another version is a workflow file nobody trusts."""
    document = arazzo_document()

    assert document["arazzo"] == ARAZZO_VERSION
    assert document["info"]["version"] == __version__
    assert [item["workflowId"] for item in document["workflows"]] == list(WORKFLOW_IDS)
    assert document["sourceDescriptions"][0]["type"] == "openapi"


def test_every_workflow_step_points_at_a_route_this_application_serves():
    """The failure mode of a workflow document is describing an endpoint that moved."""
    schema = client(enable_docs=True).get("/openapi.json").json()
    served = {re.sub(r"\{[a-zA-Z]+\}", "{}", path) for path in schema["paths"]}

    referenced = _referenced_paths(arazzo_document())

    assert referenced, "the document must actually reference operations"
    assert referenced <= served, referenced - served
    # The negative half: a path this test would happily accept if the check
    # were removed does not exist.
    assert "/api/scans/{}/report" not in served


def test_the_asynchronous_shape_of_a_scan_is_written_down():
    """The thing callers get wrong is that a uuid is a promise, not a result."""
    scan = arazzo_document()["workflows"][0]
    submit, poll = scan["steps"]

    assert submit["successCriteria"] == [{"condition": "$statusCode == 202"}]
    assert scan["outputs"]["uuid"] == "$steps.submitScan.outputs.uuid"
    assert poll["parameters"][0]["value"] == "$steps.submitScan.outputs.uuid"
    # Polling has to be described as a retry, or a client hammers the endpoint.
    assert any(action["type"] == "retry" for action in poll["onFailure"])
    assert any(action["criteria"][0]["condition"] == "$statusCode == 404"
               for action in poll["onFailure"])


def test_the_batch_workflow_says_that_some_targets_can_be_refused():
    """Two lists, not one status: a caller reading only 202 loses half the answer."""
    batch = arazzo_document()["workflows"][1]

    outputs = batch["outputs"]
    assert set(outputs) == {"accepted", "rejected"}
    assert "cooldown" in batch["steps"][1]["description"]
    assert any(
        action["criteria"][0]["condition"] == "$statusCode == 429"
        for action in batch["steps"][0]["onFailure"]
    )


def test_the_export_workflow_waits_rather_than_giving_up_on_409():
    """409 means not yet; a client that treats it as failure loses the scan."""
    export = arazzo_document()["workflows"][2]
    step = export["steps"][0]

    retry = next(action for action in step["onFailure"] if action["type"] == "retry")
    assert retry["criteria"][0]["condition"] == "$statusCode == 409"
    end = next(action for action in step["onFailure"] if action["type"] == "end")
    assert end["criteria"][0]["condition"] == "$statusCode == 404"
    assert export["inputs"]["properties"]["format"]["enum"] == [
        "json",
        "csv",
        "sarif",
        "pdf",
    ]


def test_the_workflow_document_is_served_beside_the_schema_and_only_with_it():
    """It describes the schema, so it appears exactly where the schema does."""
    with_docs = client(enable_docs=True).get("/arazzo.json")
    without_docs = client(enable_docs=False).get("/arazzo.json")

    assert with_docs.status_code == 200
    assert with_docs.json()["arazzo"] == ARAZZO_VERSION
    assert without_docs.status_code == 404
