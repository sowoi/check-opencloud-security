"""
The API described as workflows, in Arazzo 1.0.1.

OpenAPI says what each endpoint accepts. It cannot say that a scan is
asynchronous, that the uuid from the first call is the only way back to the
second, that a caller polls until ``done`` and only then asks for a file, or
that a batch answers with two lists rather than one status. Those are the
parts people get wrong, so they are written down here in a form a tool can
execute rather than in prose a reader has to reconstruct.

The document is built in Python rather than shipped as a static file for one
reason: it names this build's version and the real paths, and
``tests/test_webapp_arazzo.py`` checks it against the application's own routes,
so a workflow describing an endpoint that no longer exists fails the suite
instead of misleading somebody.
"""

from __future__ import annotations

from typing import Any

from opencloud_local_scan import __version__

ARAZZO_VERSION = "1.0.1"

SOURCE_NAME = "checkOpenCloudSecurityApi"

WORKFLOW_SCAN = "scanOneInstance"
WORKFLOW_BATCH = "scanManyInstances"
WORKFLOW_EXPORT = "exportFinishedScan"
WORKFLOW_PURGE = "eraseInstanceData"

WORKFLOW_IDS = (WORKFLOW_SCAN, WORKFLOW_BATCH, WORKFLOW_EXPORT, WORKFLOW_PURGE)


def _scan_one() -> dict[str, Any]:
    return {
        "workflowId": WORKFLOW_SCAN,
        "summary": "Scan one instance and wait for its result.",
        "description": (
            "Submit a target, poll the scan until it reports done, and read "
            "the summary. The uuid returned by the first step is the only "
            "way to reach the scan: there is no listing endpoint, and the "
            "result expires with its TTL."
        ),
        "inputs": {
            "type": "object",
            "required": ["target_url"],
            "properties": {
                "target_url": {"type": "string", "format": "uri"},
                "ignore_hardenings": {"type": "array", "items": {"type": "string"}},
                "release_track": {
                    "type": "string",
                    "enum": ["auto", "rolling", "production", "lts"],
                },
                "output_format": {
                    "type": "string",
                    "enum": ["dashboard", "json", "csv", "sarif", "pdf"],
                },
            },
        },
        "steps": [
            {
                "stepId": "submitScan",
                "description": (
                    "A submission chooses what to scan, never how hard. Any "
                    "other field is a 422 naming it."
                ),
                "operationPath": f"{{$sourceDescriptions.{SOURCE_NAME}.url}}#/paths/~1api~1scans/post",
                "requestBody": {
                    "contentType": "application/json",
                    "payload": {
                        "target_url": "$inputs.target_url",
                        "ignore_hardenings": "$inputs.ignore_hardenings",
                        "release_track": "$inputs.release_track",
                        "output_format": "$inputs.output_format",
                    },
                },
                "successCriteria": [{"condition": "$statusCode == 202"}],
                "outputs": {"uuid": "$response.body#/uuid"},
                "onFailure": [
                    {
                        "name": "retryAfterRateLimit",
                        "type": "retry",
                        "retryAfter": 60,
                        "retryLimit": 3,
                        "criteria": [{"condition": "$statusCode == 429"}],
                    }
                ],
            },
            {
                "stepId": "awaitResult",
                "description": (
                    "Poll until the scan is finished. Queueing is normal: an "
                    "overloaded service queues rather than refusing, and the "
                    "response carries the position in line."
                ),
                "operationPath": f"{{$sourceDescriptions.{SOURCE_NAME}.url}}#/paths/~1api~1scans~1{{identifier}}/get",
                "parameters": [
                    {
                        "name": "identifier",
                        "in": "path",
                        "value": "$steps.submitScan.outputs.uuid",
                    }
                ],
                "successCriteria": [
                    {"condition": "$statusCode == 200"},
                    {
                        "context": "$response.body",
                        "condition": "$.done == true",
                        "type": "jsonpath",
                    },
                ],
                "onSuccess": [
                    {
                        "name": "finished",
                        "type": "end",
                        "criteria": [
                            {
                                "context": "$response.body",
                                "condition": "$.state == 'completed'",
                                "type": "jsonpath",
                            }
                        ],
                    }
                ],
                "onFailure": [
                    {
                        "name": "keepPolling",
                        "type": "retry",
                        "retryAfter": 2,
                        "retryLimit": 90,
                        "criteria": [{"condition": "$statusCode == 200"}],
                    },
                    {
                        "name": "expiredOrUnknown",
                        "type": "end",
                        "criteria": [{"condition": "$statusCode == 404"}],
                    },
                ],
                "outputs": {
                    "state": "$response.body#/state",
                    "rating": "$response.body#/summary/rating",
                    "label": "$response.body#/summary/label",
                    "exports": "$response.body#/exports",
                },
            },
        ],
        "outputs": {
            "uuid": "$steps.submitScan.outputs.uuid",
            "rating": "$steps.awaitResult.outputs.rating",
            "label": "$steps.awaitResult.outputs.label",
        },
    }


def _scan_many() -> dict[str, Any]:
    return {
        "workflowId": WORKFLOW_BATCH,
        "summary": "Submit several instances at once.",
        "description": (
            "A batch is a convenience for a caller with an estate to check, "
            "not a discount on the limits: every target is counted against "
            "the client limit and claims its own target cooldown, in the "
            "order it was written. The answer is therefore two lists - what "
            "started, and what did not - and each accepted uuid is followed "
            "with the single-scan workflow."
        ),
        "inputs": {
            "type": "object",
            "required": ["targets"],
            "properties": {
                "targets": {
                    "type": "array",
                    "items": {"type": "string", "format": "uri"},
                },
                "ignore_hardenings": {"type": "array", "items": {"type": "string"}},
                "release_track": {
                    "type": "string",
                    "enum": ["auto", "rolling", "production", "lts"],
                },
                "output_format": {
                    "type": "string",
                    "enum": ["dashboard", "json", "csv", "sarif", "pdf"],
                },
            },
        },
        "steps": [
            {
                "stepId": "submitBatch",
                "operationPath": f"{{$sourceDescriptions.{SOURCE_NAME}.url}}#/paths/~1api~1scans~1batch/post",
                "requestBody": {
                    "contentType": "application/json",
                    "payload": {
                        "targets": "$inputs.targets",
                        "ignore_hardenings": "$inputs.ignore_hardenings",
                        "release_track": "$inputs.release_track",
                        "output_format": "$inputs.output_format",
                    },
                },
                "successCriteria": [{"condition": "$statusCode == 202"}],
                "outputs": {
                    "accepted": "$response.body#/accepted",
                    "rejected": "$response.body#/rejected",
                },
                "onFailure": [
                    {
                        "name": "everyTargetRefused",
                        "type": "end",
                        "criteria": [{"condition": "$statusCode == 429"}],
                    },
                    {
                        "name": "batchNotAccepted",
                        "type": "end",
                        "criteria": [{"condition": "$statusCode == 422"}],
                    },
                ],
            },
            {
                "stepId": "awaitEachAcceptedScan",
                "description": (
                    "One uuid at a time, using the same polling as a single "
                    "scan. A rejected target is never retried automatically: "
                    "its entry says why, and a cooldown is a reason to come "
                    "back later rather than to try harder."
                ),
                "workflowId": WORKFLOW_SCAN,
                "parameters": [
                    {
                        "name": "identifier",
                        "in": "path",
                        "value": "$steps.submitBatch.outputs.accepted",
                    }
                ],
                "successCriteria": [{"condition": "$statusCode == 200"}],
            },
        ],
        "outputs": {
            "accepted": "$steps.submitBatch.outputs.accepted",
            "rejected": "$steps.submitBatch.outputs.rejected",
        },
    }


def _export() -> dict[str, Any]:
    return {
        "workflowId": WORKFLOW_EXPORT,
        "summary": "Download a finished scan as a file.",
        "description": (
            "JSON, CSV, SARIF and PDF are renderings of the same finished "
            "result. A scan that has not finished answers 409 rather than "
            "404, so a caller knows to keep waiting instead of assuming the "
            "uuid is wrong."
        ),
        "inputs": {
            "type": "object",
            "required": ["identifier"],
            "properties": {
                "identifier": {"type": "string", "format": "uuid"},
                "format": {
                    "type": "string",
                    "enum": ["json", "csv", "sarif", "pdf"],
                    "default": "pdf",
                },
            },
        },
        "steps": [
            {
                "stepId": "downloadExport",
                "operationPath": (
                    f"{{$sourceDescriptions.{SOURCE_NAME}.url}}"
                    "#/paths/~1api~1scans~1{identifier}~1export~1{fmt}/get"
                ),
                "parameters": [
                    {"name": "identifier", "in": "path", "value": "$inputs.identifier"},
                    {"name": "fmt", "in": "path", "value": "$inputs.format"},
                ],
                "successCriteria": [{"condition": "$statusCode == 200"}],
                "onFailure": [
                    {
                        "name": "notFinishedYet",
                        "type": "retry",
                        "retryAfter": 5,
                        "retryLimit": 36,
                        "criteria": [{"condition": "$statusCode == 409"}],
                    },
                    {
                        "name": "goneOrUnknown",
                        "type": "end",
                        "criteria": [{"condition": "$statusCode == 404"}],
                    },
                ],
                "outputs": {"contentType": "$response.header.content-type"},
            }
        ],
        "outputs": {"contentType": "$steps.downloadExport.outputs.contentType"},
    }


def _purge() -> dict[str, Any]:
    return {
        "workflowId": WORKFLOW_PURGE,
        "summary": "Erase everything held for one instance, and keep the proof.",
        "description": (
            "The erasure half of GDPR Article 17, for an operator answering a "
            "request about an instance they run. It is authorised, because it "
            "deletes results belonging to whoever is currently reading them, "
            "and it answers with a receipt: counts of what was removed and a "
            "second pass confirming nothing matching was left. Keep the "
            "receipt - the data it describes no longer exists to be shown."
        ),
        "inputs": {
            "type": "object",
            "required": ["target", "authorization"],
            "properties": {
                "target": {
                    "type": "string",
                    "description": "The instance hostname, with or without a scheme.",
                },
                "authorization": {
                    "type": "string",
                    "description": "The purge credential, as 'Bearer <secret>'.",
                },
            },
        },
        "steps": [
            {
                "stepId": "eraseTarget",
                "operationPath": f"{{$sourceDescriptions.{SOURCE_NAME}.url}}#/paths/~1api~1purge/delete",
                "parameters": [
                    {"name": "target", "in": "query", "value": "$inputs.target"},
                    {
                        "name": "Authorization",
                        "in": "header",
                        "value": "$inputs.authorization",
                    },
                ],
                "successCriteria": [
                    {"condition": "$statusCode == 200"},
                    {
                        "context": "$response.body",
                        "condition": "$.complete == true",
                        "type": "jsonpath",
                    },
                ],
                "onFailure": [
                    {
                        "name": "notAuthorised",
                        "type": "end",
                        "criteria": [{"condition": "$statusCode == 401"}],
                    },
                    {
                        "name": "purgeNotDeployed",
                        "type": "end",
                        "criteria": [{"condition": "$statusCode == 404"}],
                    },
                ],
                "outputs": {
                    "receiptId": "$response.body#/receiptId",
                    "deleted": "$response.body#/deleted",
                    "remaining": "$response.body#/remaining",
                    "signature": "$response.body#/signature",
                },
            }
        ],
        "outputs": {
            "receiptId": "$steps.eraseTarget.outputs.receiptId",
            "deleted": "$steps.eraseTarget.outputs.deleted",
            "signature": "$steps.eraseTarget.outputs.signature",
        },
    }


def arazzo_document(*, openapi_url: str = "/openapi.json") -> dict[str, Any]:
    """The Arazzo description of this API's workflows."""
    return {
        "arazzo": ARAZZO_VERSION,
        "info": {
            "title": "check-opencloud-security scan workflows",
            "summary": (
                "Submitting scans, waiting for them, taking the result away, "
                "and erasing it on request."
            ),
            "description": (
                "Every workflow here runs against a public deployment with no "
                "account and no API key. The limits are part of the contract: "
                "a 429 is an invitation to slow down or to run the scanner "
                "yourself, which is open source and has no limits at all - "
                "https://github.com/sowoi/check-opencloud-security."
            ),
            "version": __version__,
        },
        "sourceDescriptions": [
            {
                "name": SOURCE_NAME,
                "url": openapi_url,
                "type": "openapi",
            }
        ],
        "workflows": [_scan_one(), _scan_many(), _export(), _purge()],
    }
