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
from webapp import workflows as wf
from webapp.arazzo import (
    ARAZZO_VERSION,
    WORKFLOW_AWAIT,
    WORKFLOW_IDS,
    arazzo_document,
)


def _workflow(document, workflow_id):
    """One workflow by id, so a reordering does not silently retarget a test."""
    return next(
        item for item in document["workflows"] if item["workflowId"] == workflow_id
    )


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
    schema = client(enable_docs=False).get("/openapi.json").json()
    served = {re.sub(r"\{[a-zA-Z]+\}", "{}", path) for path in schema["paths"]}

    referenced = _referenced_paths(arazzo_document())

    assert referenced, "the document must actually reference operations"
    assert referenced <= served, referenced - served
    # The negative half: a path this test would happily accept if the check
    # were removed does not exist.
    assert "/api/scans/{}/report" not in served


def test_the_asynchronous_shape_of_a_scan_is_written_down():
    """The thing callers get wrong is that a uuid is a promise, not a result."""
    document = arazzo_document()
    scan = _workflow(document, "scanOneInstance")
    submit, wait = scan["steps"]

    assert submit["successCriteria"] == [
        {"condition": f"$statusCode == {wf.SUBMIT_STATUS}"}
    ]
    assert scan["outputs"]["uuid"] == "$steps.submitScan.outputs.uuid"
    # The uuid the submission produced is what the waiting half is given, and
    # it is handed to the shared polling workflow rather than polled twice.
    assert wait["workflowId"] == WORKFLOW_AWAIT
    assert wait["parameters"] == [
        {"name": "identifier", "value": "$steps.submitScan.outputs.uuid"}
    ]
    # A workflow-typed step must not name a location: there is no query
    # string on a workflow.
    assert "in" not in wait["parameters"][0]


def test_polling_retries_a_running_scan_and_stops_on_an_expired_one():
    """Retry while it works, stop when it is gone - confusing the two is the bug."""
    poll = _workflow(arazzo_document(), WORKFLOW_AWAIT)["steps"][0]

    assert {"context": "$response.body", "condition": "$.done == true",
            "type": "jsonpath"} in poll["successCriteria"]
    retry = next(a for a in poll["onFailure"] if a["type"] == "retry")
    assert retry["criteria"][0]["condition"] == "$statusCode == 200"
    assert retry["retryAfter"] == wf.POLL_INTERVAL_SECONDS
    assert retry["retryLimit"] == wf.POLL_MAX_ATTEMPTS
    # The negative half: an unknown uuid ends the workflow instead of joining
    # the retry loop, or a typo becomes a hundred requests.
    ends = [a for a in poll["onFailure"] if a["type"] == "end"]
    assert any(a["criteria"][0]["condition"] == "$statusCode == 404" for a in ends)
    assert not any(
        a["type"] == "retry" and a["criteria"][0]["condition"] == "$statusCode == 404"
        for a in poll["onFailure"]
    )


def test_the_batch_workflow_waits_on_uuids_and_never_resubmits_a_target():
    """A uuid is not a target: feeding one back into a scan is the old bug here."""
    batch = _workflow(arazzo_document(), "scanManyInstances")
    submit, wait = batch["steps"]

    assert "accepted" in batch["outputs"] and "rejected" in batch["outputs"]
    # The waiting step polls an identifier it was given, rather than starting
    # a second scan of something the batch already submitted.
    assert wait["workflowId"] == WORKFLOW_AWAIT
    assert wait["parameters"] == [
        {
            "name": "identifier",
            "value": "$steps.submitBatch.outputs.firstAcceptedUuid",
        }
    ]
    assert submit["outputs"]["firstAcceptedUuid"] == "$response.body#/accepted/0/uuid"
    # The negative half: nothing in the batch feeds a target_url into a scan
    # submission, which is what made the old version unrunnable.
    assert "target_url" not in str(wait)
    assert any(
        action["criteria"][0]["condition"] == "$statusCode == 429"
        for action in submit["onFailure"]
    )
    assert "rejected" in submit["outputs"]


def test_a_rejected_target_is_described_as_something_not_to_retry():
    """The service refused it on purpose; a retry loop turns that into abuse."""
    batch = _workflow(arazzo_document(), "scanManyInstances")

    assert "must NOT be resubmitted" in batch["description"]
    assert "cooldown" in batch["description"]


def test_the_export_workflow_waits_rather_than_giving_up_on_409():
    """409 means not yet; a client that treats it as failure loses the scan."""
    export = _workflow(arazzo_document(), "exportFinishedScan")
    step = export["steps"][0]

    retry = next(action for action in step["onFailure"] if action["type"] == "retry")
    assert retry["criteria"][0]["condition"] == (
        f"$statusCode == {wf.NOT_FINISHED_STATUS}"
    )
    assert retry["retryAfter"] == wf.EXPORT_RETRY_SECONDS
    end = next(action for action in step["onFailure"] if action["type"] == "end")
    assert end["criteria"][0]["condition"] == "$statusCode == 404"
    # The negative half: 404 is never retried, however long a caller waits.
    assert not any(
        action["type"] == "retry"
        and action["criteria"][0]["condition"] == "$statusCode == 404"
        for action in step["onFailure"]
    )
    assert export["inputs"]["properties"]["format"]["enum"] == list(wf.EXPORT_FORMATS)


def test_the_purge_workflow_documents_the_receipt_without_the_credential():
    """A receipt proves an erasure; it must not carry what authorised it."""
    purge = _workflow(arazzo_document(), "eraseInstanceData")
    step = purge["steps"][0]

    assert purge["inputs"]["properties"]["authorization"]["writeOnly"] is True
    header = next(p for p in step["parameters"] if p["name"] == "Authorization")
    assert header["in"] == "header"
    assert set(purge["outputs"]) >= {
        "receiptId", "deleted", "remaining", "complete", "signature"
    }
    # The negative half: the credential is nowhere in what the workflow hands
    # back, however convenient that would be for a caller chaining calls.
    assert "authorization" not in purge["outputs"]
    assert any(
        action["criteria"][0]["condition"] == "$statusCode == 401"
        for action in step["onFailure"]
    )


def test_every_retry_and_wait_comes_from_the_shared_workflow_semantics():
    """MCP executes these numbers; a document with its own is a document that lies."""
    document = arazzo_document()
    poll = _workflow(document, WORKFLOW_AWAIT)["steps"][0]
    submit = _workflow(document, "scanOneInstance")["steps"][0]

    retry = next(a for a in poll["onFailure"] if a["type"] == "retry")
    limit = next(a for a in submit["onFailure"] if a["type"] == "retry")

    assert (retry["retryAfter"], retry["retryLimit"]) == (
        wf.POLL_INTERVAL_SECONDS,
        wf.POLL_MAX_ATTEMPTS,
    )
    assert (limit["retryAfter"], limit["retryLimit"]) == (
        wf.RATE_LIMIT_FALLBACK_SECONDS,
        wf.SUBMIT_MAX_ATTEMPTS,
    )


def test_the_workflow_document_is_public_whatever_the_docs_switch_says():
    """An agent that cannot read the contract has to guess at it."""
    with_docs = client(enable_docs=True).get("/arazzo.json")
    without_docs = client(enable_docs=False).get("/arazzo.json")

    assert with_docs.status_code == 200
    assert with_docs.json()["arazzo"] == ARAZZO_VERSION
    # The negative half: turning the browsable pages off must not take the
    # machine-readable document with them.
    assert without_docs.status_code == 200
    assert without_docs.json()["arazzo"] == ARAZZO_VERSION
