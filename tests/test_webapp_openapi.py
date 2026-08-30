"""
The OpenAPI description, checked against the application it describes.

A specification is only useful if it is true, and the way it stops being true
is quietly: a handler starts answering 202 instead of 200, a field is renamed,
an endpoint learns to accept JSON. So these tests drive the real endpoints and
compare what came back with what the document promised, rather than reading
the document twice.
"""

from __future__ import annotations

import re

import pytest

from opencloud_local_scan.releases import ReleaseSettings
from opencloud_local_scan.scanner import ScannerSettings, scan
from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour
from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
    settings,
)
from webapp import workflows as wf
from webapp.arazzo import arazzo_document
from webapp.openapi import OPERATION_IDS, openapi_document

TARGET = "https://opencloud.example.com"


def _schema():
    return openapi_document()


def _operation(path: str, method: str):
    return _schema()["paths"][path][method]


def test_every_operation_the_document_names_is_actually_served():
    """A path in the schema that no route answers is a lie a client acts on."""
    served = client()
    schema = _schema()

    ids = {
        operation["operationId"]
        for item in schema["paths"].values()
        for operation in item.values()
    }
    assert ids == set(OPERATION_IDS)

    # Every documented path answers something other than "no such route".
    for path in schema["paths"]:
        probe = re.sub(r"\{[a-zA-Z]+\}", "unknown", path)
        for method in schema["paths"][path]:
            response = served.request(method.upper(), probe)
            assert response.status_code != 405, f"{method} {path}"


def test_submitting_a_scan_answers_the_status_and_body_the_document_promises():
    """202 with a uuid, not 200 with a rating. Getting this wrong breaks polling."""
    response = client().post("/api/scans", json={"target_url": TARGET})

    documented = _operation("/api/scans", "post")["responses"]
    assert str(response.status_code) in documented
    assert response.status_code == wf.SUBMIT_STATUS

    body = response.json()
    accepted = _schema()["components"]["schemas"]["ScanAccepted"]
    assert set(accepted["required"]) <= set(body)
    assert body["state"] == wf.STATE_QUEUED
    assert response.headers["Location"] == body["url"]
    # The negative half: nothing resembling a result is in the answer yet.
    assert "summary" not in body and "rating" not in body


def test_the_submission_endpoint_accepts_both_content_types_it_declares():
    """The browser posts a form and a client posts JSON, through one handler."""
    declared = set(_operation("/api/scans", "post")["requestBody"]["content"])
    assert declared == {"application/json", "application/x-www-form-urlencoded"}

    served = client()
    as_json = served.post("/api/scans", json={"target_url": TARGET})
    as_form = served.post(
        "/api/scans",
        data={"target_url": TARGET},
        headers={"Accept": "application/json"},
    )

    assert as_json.status_code == wf.SUBMIT_STATUS
    assert as_form.status_code == wf.SUBMIT_STATUS


def test_the_batch_endpoint_is_documented_as_json_only_and_is_json_only():
    """Declaring a form body a handler ignores sends a caller down a dead end."""
    declared = set(
        _operation("/api/scans/batch", "post")["requestBody"]["content"]
    )
    assert declared == {"application/json"}

    served = client()
    accepted = served.post("/api/scans/batch", json={"targets": [TARGET]})
    assert accepted.status_code == wf.SUBMIT_STATUS

    body = accepted.json()
    schema = _schema()["components"]["schemas"]["BatchAccepted"]
    assert set(schema["required"]) <= set(body)
    assert set(schema["properties"]["counts"]["properties"]) == set(body["counts"])
    entry = _schema()["components"]["schemas"]["BatchAcceptedTarget"]
    assert set(entry["required"]) <= set(body["accepted"][0])

    # The negative half: a form body is not quietly accepted.
    as_form = served.post("/api/scans/batch", data={"targets": TARGET})
    assert as_form.status_code == 422


def test_a_scan_record_carries_every_field_the_document_requires():
    """Polling reads these names; a rename that skips the schema breaks clients."""
    served = client()
    identifier = served.post("/api/scans", json={"target_url": TARGET}).json()["uuid"]

    state = served.get(f"/api/scans/{identifier}")
    assert state.status_code == 200

    schema = _schema()["components"]["schemas"]["ScanRecord"]
    body = state.json()
    assert set(schema["required"]) <= set(body)
    assert set(body) <= set(schema["properties"]), set(body) - set(schema["properties"])
    assert body["state"] in schema["properties"]["state"]["enum"]
    # The negative half: an unfinished scan says nothing about being done.
    assert "done" not in body


def test_an_unknown_uuid_answers_the_documented_404_everywhere_it_can_be_used():
    """Unknown, malformed and expired are one answer on purpose."""
    served = client()
    for path in (
        "/api/scans/not-a-uuid",
        "/api/scans/not-a-uuid/export/json",
        "/api/scans/00000000-0000-0000-0000-000000000000",
    ):
        response = served.get(path)
        assert response.status_code == 404, path
        assert set(response.json()) >= {"detail"}


def test_an_unfinished_export_answers_409_with_the_state_the_document_names():
    """409 is what tells a caller to wait rather than to give up on the uuid."""
    served = client()
    identifier = served.post("/api/scans", json={"target_url": TARGET}).json()["uuid"]

    response = served.get(f"/api/scans/{identifier}/export/json")

    assert response.status_code == wf.NOT_FINISHED_STATUS
    schema = _schema()["components"]["schemas"]["ExportConflict"]
    body = response.json()
    assert set(schema["required"]) <= set(body)
    assert body["state"] in schema["properties"]["state"]["enum"]


def test_an_unsupported_field_answers_the_documented_422():
    """A request may say what to scan, never how hard - and is told which field."""
    response = client().post(
        "/api/scans", json={"target_url": TARGET, "scan_concurrency": 50}
    )

    assert response.status_code == 422
    assert "422" in _operation("/api/scans", "post")["responses"]
    assert "scan_concurrency" in response.json()["detail"]


def test_erasure_is_the_only_operation_the_document_puts_behind_a_credential():
    """Everything else is open; saying so is what makes the one exception legible."""
    schema = _schema()
    assert schema["security"] == []

    purge = _operation("/api/purge", "delete")
    assert purge["security"] == [{"purgeToken": []}]
    assert "purgeToken" in schema["components"]["securitySchemes"]

    served = client(purge_token="s3cret")
    denied = served.request("DELETE", "/api/purge?target=opencloud.example.com")
    assert denied.status_code == 401
    assert denied.headers["WWW-Authenticate"] == "Bearer"

    allowed = served.request(
        "DELETE",
        "/api/purge?target=opencloud.example.com",
        headers={"Authorization": "Bearer s3cret"},
    )
    assert allowed.status_code == 200
    receipt = _schema()["components"]["schemas"]["PurgeReceipt"]
    assert set(receipt["required"]) <= set(allowed.json())
    # The negative half: the receipt does not carry what authorised it.
    assert "s3cret" not in allowed.text


def test_health_answers_one_of_the_two_documented_shapes():
    """A batch caller checks this first; an undocumented 503 body wastes that."""
    response = client().get("/healthz")

    documented = _operation("/healthz", "get")["responses"]
    assert str(response.status_code) in documented
    schema = _schema()["components"]["schemas"]["Health"]
    assert set(schema["required"]) <= set(response.json())
    assert response.json()["status"] in schema["properties"]["status"]["enum"]


def test_no_schema_in_the_document_is_left_empty():
    """An empty schema documents nothing while looking like documentation."""
    schema = _schema()

    for name, definition in schema["components"]["schemas"].items():
        assert definition, name
        assert "type" in definition or "oneOf" in definition, name

    for path, item in schema["paths"].items():
        for method, operation in item.items():
            for status, response in operation["responses"].items():
                for media, content in response.get("content", {}).items():
                    assert content.get("schema"), f"{method} {path} {status} {media}"


def test_the_html_only_routes_stay_out_of_the_api_description():
    """A form post described as an API operation sends a client to a redirect."""
    paths = set(_schema()["paths"])

    assert "/" not in paths
    assert "/scan/{identifier}" not in paths
    assert paths == {
        "/api/scans",
        "/api/scans/batch",
        "/api/scans/{identifier}",
        "/api/scans/{identifier}/export/{fmt}",
        "/api/purge",
        "/healthz",
    }


@pytest.mark.parametrize("workflow", arazzo_document()["workflows"])
def test_every_arazzo_step_resolves_to_an_operation_in_this_document(workflow):
    """A workflow pointing at an operation that moved is worse than no workflow."""
    schema = _schema()

    for step in workflow["steps"]:
        location = step.get("operationPath")
        if not location:
            assert step.get("workflowId"), step["stepId"]
            continue
        pointer = location.split("#/paths/", 1)[1]
        path, method = pointer.rsplit("/", 1)
        path = path.replace("~1", "/")
        assert path in schema["paths"], path
        assert method in schema["paths"][path], f"{method} {path}"


EXPORT_OPERATION = "/paths/~1api~1scans~1{identifier}~1export~1{fmt}/get"


def _scanner_document_fields() -> frozenset[str]:
    """
    The top-level keys the scanner's own result document carries.

    The export endpoint hands that document back untouched, so its OpenAPI
    response is a free-form object on purpose: ``opencloud_local_scan`` owns
    that shape and this service must not restate it. Nothing in
    ``components/schemas`` can therefore answer whether a pointer into that
    body resolves - only a real scan can, which is what this does.
    """
    with FakeOpenCloud(InstanceBehaviour()) as instance:
        document = scan(
            instance.host,
            settings=ScannerSettings(
                scheme="http", timeout=3, check_debug_ports=False, include_bundled_db=True
            ),
            release_settings=ReleaseSettings(mode="off"),
        )
    return frozenset(document)


def test_every_field_a_workflow_reads_exists_in_the_schema_it_reads_it_from():
    """An output pointing at a field nobody returns silently yields nothing."""
    schemas = _schema()["components"]["schemas"]
    record = schemas["ScanRecord"]["properties"]
    summary = schemas["ScanSummary"]["properties"]
    receipt = schemas["PurgeReceipt"]["properties"]
    accepted = schemas["ScanAccepted"]["properties"]
    batch = schemas["BatchAccepted"]["properties"]
    document = _scanner_document_fields()

    known = {
        "/uuid": accepted,
        "/state": record,
        "/done": record,
        "/target": record,
        "/exports": record,
        "/accepted": batch,
        "/rejected": batch,
        "/counts": batch,
        "/receiptId": receipt,
        "/issuedAt": receipt,
        "/deleted": receipt,
        "/remaining": receipt,
        "/complete": receipt,
        "/signature": receipt,
    }
    for workflow in arazzo_document()["workflows"]:
        for step in workflow["steps"]:
            reads_export = EXPORT_OPERATION in step.get("operationPath", "")
            for name, expression in step.get("outputs", {}).items():
                if not expression.startswith("$response.body#"):
                    continue
                pointer = expression.split("#", 1)[1]
                assert name
                if reads_export:
                    # The scanner document, not one of this service's schemas.
                    assert pointer.split("/")[1] in document, expression
                elif pointer.startswith("/summary/"):
                    assert pointer.split("/")[2] in summary, expression
                elif pointer.startswith("/accepted/"):
                    assert "accepted" in batch, expression
                else:
                    assert pointer in known, expression
                    assert pointer.lstrip("/") in known[pointer], expression


def test_a_workflow_reading_the_export_body_is_checked_against_a_real_scan():
    """
    The negative half: the free-form export schema must not wave anything through.

    A pointer at a field the scanner does not emit has to fail, or the branch
    above is a check that always passes.
    """
    document = _scanner_document_fields()

    assert "rating" in document
    assert "notAFieldTheScannerEmits" not in document
