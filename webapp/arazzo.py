"""
The API described as workflows, in Arazzo 1.0.1.

OpenAPI says what each endpoint accepts. It cannot say that a scan is
asynchronous, that the uuid from the first call is the only way back to the
second, that a caller polls until ``done`` and only then asks for a file, or
that a batch answers with two lists rather than one status. Those are the
parts people get wrong, so they are written down here in a form a tool can
execute rather than in prose a reader has to reconstruct.

Every number in it - how long to wait between polls, how many times to retry
a rate limit, how long an export may keep answering 409 - comes from
:mod:`webapp.workflows`, which is also what the MCP tools execute. A workflow
an agent reads and a workflow an agent runs cannot describe different
behaviour if they read the same constants.

The document is built in Python rather than shipped as a static file for one
reason: it names this build's version and the real paths, and
``tests/test_webapp_arazzo.py`` checks it against the published OpenAPI
document, so a workflow describing an endpoint that no longer exists fails
the suite instead of misleading somebody.
"""

from __future__ import annotations

from typing import Any

from opencloud_local_scan import __version__

from . import workflows as wf

ARAZZO_VERSION = "1.0.1"

SOURCE_NAME = "checkOpenCloudSecurityApi"

WORKFLOW_SCAN = "scanOneInstance"
WORKFLOW_AWAIT = "awaitScanResult"
WORKFLOW_BATCH = "scanManyInstances"
WORKFLOW_PLAN = "planRemediation"
WORKFLOW_EXPORT = "exportFinishedScan"
WORKFLOW_PURGE = "eraseInstanceData"

WORKFLOW_IDS = (
    WORKFLOW_SCAN,
    WORKFLOW_AWAIT,
    WORKFLOW_BATCH,
    WORKFLOW_PLAN,
    WORKFLOW_EXPORT,
    WORKFLOW_PURGE,
)

_TRACKS = ["auto", "rolling", "production", "lts"]


def _operation(pointer: str) -> str:
    """A step's target, as a pointer into the OpenAPI document beside it."""
    return f"{{$sourceDescriptions.{SOURCE_NAME}.url}}#{pointer}"


def _identifier_input() -> dict[str, Any]:
    return {
        "type": "string",
        "format": "uuid",
        "description": "The uuid a scan submission returned. " + wf.UUID_NOTE,
    }


def _scan_one() -> dict[str, Any]:
    return {
        "workflowId": WORKFLOW_SCAN,
        "summary": "Scan one instance and wait for its rating.",
        "description": (
            "The whole task, end to end: submit a target, receive a uuid, "
            "poll while the scan is queued or running, detect completion and "
            "return the rating.\n\n" + wf.ASYNC_NOTE + "\n\n" + wf.UUID_NOTE
        ),
        "inputs": {
            "type": "object",
            "required": ["target_url"],
            "properties": {
                "target_url": {
                    "type": "string",
                    "description": (
                        "The instance to scan. Must be publicly resolvable; a "
                        "private or loopback address is refused with 400 and "
                        "must not be retried."
                    ),
                    "examples": ["https://opencloud.example.com"],
                },
                "ignore_hardenings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Hardening identifiers to waive. A waived finding is "
                        "still reported, it simply stops capping the rating."
                    ),
                },
                "release_track": {
                    "type": "string",
                    "enum": _TRACKS,
                    "description": (
                        "Which release line the version is judged against. "
                        "Changes the rating, never the probing."
                    ),
                },
            },
        },
        "steps": [
            {
                "stepId": "submitScan",
                "description": (
                    "A submission chooses what to scan, never how hard. Any "
                    "other field is a 422 naming it. The answer is "
                    f"{wf.SUBMIT_STATUS} Accepted with a uuid and no rating."
                ),
                "operationPath": _operation("/paths/~1api~1scans/post"),
                "requestBody": {
                    "contentType": "application/json",
                    "payload": {
                        "target_url": "$inputs.target_url",
                        "ignore_hardenings": "$inputs.ignore_hardenings",
                        "release_track": "$inputs.release_track",
                        "output_format": "json",
                    },
                },
                "successCriteria": [
                    {"condition": f"$statusCode == {wf.SUBMIT_STATUS}"}
                ],
                "outputs": {"uuid": "$response.body#/uuid"},
                "onFailure": [
                    {
                        "name": "waitOutTheRateLimit",
                        "type": "retry",
                        "retryAfter": wf.RATE_LIMIT_FALLBACK_SECONDS,
                        "retryLimit": wf.SUBMIT_MAX_ATTEMPTS,
                        "criteria": [{"condition": "$statusCode == 429"}],
                    },
                    {
                        "name": "targetRefused",
                        "type": "end",
                        "criteria": [{"condition": "$statusCode == 400"}],
                    },
                    {
                        "name": "requestNotAccepted",
                        "type": "end",
                        "criteria": [{"condition": "$statusCode == 422"}],
                    },
                ],
            },
            {
                "stepId": "awaitScan",
                "description": (
                    "Hand the uuid to the polling workflow and wait for it to "
                    "finish."
                ),
                "workflowId": WORKFLOW_AWAIT,
                "parameters": [
                    {
                        "name": "identifier",
                        "value": "$steps.submitScan.outputs.uuid",
                    }
                ],
                "outputs": {
                    "state": "$outputs.state",
                    "rating": "$outputs.rating",
                    "label": "$outputs.label",
                    "eol": "$outputs.eol",
                    "remediation": "$outputs.remediation",
                    "exports": "$outputs.exports",
                },
            },
        ],
        "outputs": {
            "uuid": "$steps.submitScan.outputs.uuid",
            "state": "$steps.awaitScan.outputs.state",
            "rating": "$steps.awaitScan.outputs.rating",
            "label": "$steps.awaitScan.outputs.label",
            "eol": "$steps.awaitScan.outputs.eol",
            "remediation": "$steps.awaitScan.outputs.remediation",
            "exports": "$steps.awaitScan.outputs.exports",
        },
    }


def _await_result() -> dict[str, Any]:
    return {
        "workflowId": WORKFLOW_AWAIT,
        "summary": "Poll one already-submitted scan until it finishes.",
        "description": (
            "The waiting half of every other workflow, so that a single scan "
            "and a batch wait in exactly the same way.\n\n"
            "Queued and running mean poll again in "
            f"{wf.POLL_INTERVAL_SECONDS} seconds; queueing is normal, because "
            "an overloaded service queues rather than refusing and the "
            "response says where in line the scan stands. 'done' becoming "
            "true is the signal to stop, and it appears for a failed scan as "
            "well as a completed one. 404 is final: unknown, malformed and "
            "expired uuids are deliberately indistinguishable, and polling "
            "one forever is how a client turns its own mistake into load."
        ),
        "inputs": {
            "type": "object",
            "required": ["identifier"],
            "properties": {"identifier": _identifier_input()},
        },
        "steps": [
            {
                "stepId": "readScanState",
                "description": (
                    "Succeeds only when the scan has finished. Anything else "
                    "is handled below: still working means retry, gone means "
                    "stop."
                ),
                "operationPath": _operation("/paths/~1api~1scans~1{identifier}/get"),
                "parameters": [
                    {
                        "name": "identifier",
                        "in": "path",
                        "value": "$inputs.identifier",
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
                "onFailure": [
                    {
                        "name": "stillQueuedOrRunning",
                        "type": "retry",
                        "retryAfter": wf.POLL_INTERVAL_SECONDS,
                        "retryLimit": wf.POLL_MAX_ATTEMPTS,
                        "criteria": [{"condition": "$statusCode == 200"}],
                    },
                    {
                        "name": "unknownOrExpired",
                        "type": "end",
                        "criteria": [{"condition": "$statusCode == 404"}],
                    },
                ],
                "outputs": {
                    "state": "$response.body#/state",
                    "done": "$response.body#/done",
                    "target": "$response.body#/target",
                    "rating": "$response.body#/summary/rating",
                    "label": "$response.body#/summary/label",
                    "eol": "$response.body#/summary/eol",
                    "explanation": "$response.body#/summary/explanation",
                    "remediation": "$response.body#/summary/remediation",
                    "exports": "$response.body#/exports",
                },
            }
        ],
        "outputs": {
            "state": "$steps.readScanState.outputs.state",
            "target": "$steps.readScanState.outputs.target",
            "rating": "$steps.readScanState.outputs.rating",
            "label": "$steps.readScanState.outputs.label",
            "eol": "$steps.readScanState.outputs.eol",
            "explanation": "$steps.readScanState.outputs.explanation",
            "remediation": "$steps.readScanState.outputs.remediation",
            "exports": "$steps.readScanState.outputs.exports",
        },
    }


def _scan_many() -> dict[str, Any]:
    return {
        "workflowId": WORKFLOW_BATCH,
        "summary": "Submit several instances at once and wait for the accepted ones.",
        "description": (
            "A batch is a convenience for a caller with an estate to check, "
            "not a discount on the limits: every target is counted against "
            "the client limit and claims its own target cooldown, in the "
            "order it was written.\n\n"
            "The answer is therefore two lists. Everything in 'accepted' "
            "already has a uuid and is waited for with the "
            f"{WORKFLOW_AWAIT} workflow. Everything in 'rejected' was refused "
            "with a status and a reason and must NOT be resubmitted by this "
            "workflow: 400 and 422 will not change, and 429 carries the "
            "number of seconds after which a new batch may be sent.\n\n"
            "Arazzo has no fan-out construct, so the second step waits for "
            "the first accepted uuid. A runner repeats that step - or the "
            f"{WORKFLOW_AWAIT} workflow on its own - once per entry of the "
            "accepted list, whose uuids are all in the batch response."
        ),
        "inputs": {
            "type": "object",
            "required": ["targets"],
            "properties": {
                "targets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "The instances to scan. Non-empty, and no longer than "
                        "the deployment's batch limit; either mistake is a "
                        "422 that must not be retried unchanged."
                    ),
                },
                "ignore_hardenings": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "release_track": {"type": "string", "enum": _TRACKS},
            },
        },
        "steps": [
            {
                "stepId": "submitBatch",
                "description": (
                    "JSON only. Succeeds when at least one target started; a "
                    "batch where nothing started answers with the reason its "
                    "first target was refused."
                ),
                "operationPath": _operation("/paths/~1api~1scans~1batch/post"),
                "requestBody": {
                    "contentType": "application/json",
                    "payload": {
                        "targets": "$inputs.targets",
                        "ignore_hardenings": "$inputs.ignore_hardenings",
                        "release_track": "$inputs.release_track",
                        "output_format": "json",
                    },
                },
                "successCriteria": [
                    {"condition": f"$statusCode == {wf.SUBMIT_STATUS}"}
                ],
                "outputs": {
                    "accepted": "$response.body#/accepted",
                    "rejected": "$response.body#/rejected",
                    "counts": "$response.body#/counts",
                    "firstAcceptedUuid": "$response.body#/accepted/0/uuid",
                },
                "onFailure": [
                    {
                        "name": "everyTargetRateLimited",
                        "type": "end",
                        "criteria": [{"condition": "$statusCode == 429"}],
                    },
                    {
                        "name": "everyTargetRefused",
                        "type": "end",
                        "criteria": [{"condition": "$statusCode == 400"}],
                    },
                    {
                        "name": "batchNotAccepted",
                        "type": "end",
                        "criteria": [{"condition": "$statusCode == 422"}],
                    },
                ],
            },
            {
                "stepId": "awaitAcceptedScan",
                "description": (
                    "Wait for one accepted uuid, using the same polling as a "
                    "single scan. Repeat for each further uuid in the "
                    "accepted list. Never feed a rejected target in here: it "
                    "has no uuid, and it was refused on purpose."
                ),
                "workflowId": WORKFLOW_AWAIT,
                "parameters": [
                    {
                        "name": "identifier",
                        "value": "$steps.submitBatch.outputs.firstAcceptedUuid",
                    }
                ],
                "outputs": {
                    "state": "$outputs.state",
                    "rating": "$outputs.rating",
                    "label": "$outputs.label",
                },
            },
        ],
        "outputs": {
            "accepted": "$steps.submitBatch.outputs.accepted",
            "rejected": "$steps.submitBatch.outputs.rejected",
            "counts": "$steps.submitBatch.outputs.counts",
            "firstRating": "$steps.awaitAcceptedScan.outputs.rating",
            "firstLabel": "$steps.awaitAcceptedScan.outputs.label",
        },
    }


def _plan_remediation() -> dict[str, Any]:
    return {
        "workflowId": WORKFLOW_PLAN,
        "summary": "Work out what would raise the grade, and in what order.",
        "description": (
            "The question a report does not answer: not what is wrong, but "
            "what to do first. The plan is the rating's own arithmetic "
            "replayed with one finding removed at a time, so every predicted "
            "grade is the grade the same scanner would award - a caller must "
            "not recompute or reorder it.\n\n"
            "The steps are already ordered by what pays off soonest. A step "
            "whose ratingGain is 0 is still necessary: findings of one "
            "severity share a single cap, so the grade moves only when the "
            "last of them is gone. When the instance is behind on releases "
            "the plan contains an 'upgrade' step, because fixing findings can "
            "never lift the rating above what the version allows.\n\n"
            "It waits for the scan the same way every other workflow does: "
            "queued and running mean poll again, 404 means the uuid is "
            "unknown or expired and is final."
        ),
        "inputs": {
            "type": "object",
            "required": ["identifier"],
            "properties": {"identifier": _identifier_input()},
        },
        "steps": [
            {
                "stepId": "awaitScan",
                "description": (
                    "There is no plan until there is a result, so this is the "
                    "same wait as everywhere else rather than a second one."
                ),
                "workflowId": WORKFLOW_AWAIT,
                "parameters": [
                    {"name": "identifier", "value": "$inputs.identifier"}
                ],
                "outputs": {
                    "state": "$outputs.state",
                    "rating": "$outputs.rating",
                    "label": "$outputs.label",
                    "remediation": "$outputs.remediation",
                },
            }
        ],
        "outputs": {
            "state": "$steps.awaitScan.outputs.state",
            "rating": "$steps.awaitScan.outputs.rating",
            "label": "$steps.awaitScan.outputs.label",
            "remediation": "$steps.awaitScan.outputs.remediation",
        },
    }


def _export() -> dict[str, Any]:
    return {
        "workflowId": WORKFLOW_EXPORT,
        "summary": "Download a finished scan as a file.",
        "description": (
            "JSON, CSV, SARIF and PDF are four renderings of the same "
            "finished result.\n\n" + wf.CONFLICT_NOTE + "\n\n" + wf.EXPIRY_NOTE
        ),
        "inputs": {
            "type": "object",
            "required": ["identifier"],
            "properties": {
                "identifier": _identifier_input(),
                "format": {
                    "type": "string",
                    "enum": list(wf.EXPORT_FORMATS),
                    "default": "pdf",
                },
            },
        },
        "steps": [
            {
                "stepId": "downloadExport",
                "description": (
                    "409 and 404 are different answers to different "
                    "questions, and the two failure actions below are the "
                    "whole point of this workflow: wait for the first, stop "
                    "on the second."
                ),
                "operationPath": _operation(
                    "/paths/~1api~1scans~1{identifier}~1export~1{fmt}/get"
                ),
                "parameters": [
                    {
                        "name": "identifier",
                        "in": "path",
                        "value": "$inputs.identifier",
                    },
                    {"name": "fmt", "in": "path", "value": "$inputs.format"},
                ],
                "successCriteria": [{"condition": "$statusCode == 200"}],
                "onFailure": [
                    {
                        "name": "existsButNotFinished",
                        "type": "retry",
                        "retryAfter": wf.EXPORT_RETRY_SECONDS,
                        "retryLimit": wf.EXPORT_MAX_ATTEMPTS,
                        "criteria": [
                            {
                                "condition": (
                                    f"$statusCode == {wf.NOT_FINISHED_STATUS}"
                                )
                            }
                        ],
                    },
                    {
                        "name": "unknownExpiredOrUnsupportedFormat",
                        "type": "end",
                        "criteria": [{"condition": "$statusCode == 404"}],
                    },
                ],
                "outputs": {
                    "contentType": "$response.header.content-type",
                    "disposition": "$response.header.content-disposition",
                },
            }
        ],
        "outputs": {
            "contentType": "$steps.downloadExport.outputs.contentType",
            "disposition": "$steps.downloadExport.outputs.disposition",
        },
    }


def _purge() -> dict[str, Any]:
    return {
        "workflowId": WORKFLOW_PURGE,
        "summary": "Erase everything held for one instance, and keep the proof.",
        "description": (
            "The erasure half of GDPR Article 17, for an operator answering a "
            "request about an instance they run. Destructive and "
            "irreversible: it deletes results belonging to whoever is "
            "currently reading them.\n\n"
            "It is authorised with the operator's purge credential, presented "
            "as a bearer token. There is no way to obtain one from this API. "
            "An automated caller that does not already hold it must stop and "
            "ask a human rather than retrying, and must never put the "
            "credential anywhere but the Authorization header.\n\n"
            "The answer is a receipt: counts of what was removed, a second "
            "pass confirming nothing matching was left, and an HMAC over the "
            "whole of it when the deployment configured a signing key. Keep "
            "it - the data it describes no longer exists to be shown. A "
            "deployment with no credential configured has no erasure endpoint "
            "at all and answers 404."
        ),
        "inputs": {
            "type": "object",
            "required": ["target", "authorization"],
            "properties": {
                "target": {
                    "type": "string",
                    "description": "The instance hostname, with or without a scheme.",
                    "examples": ["opencloud.example.com"],
                },
                "authorization": {
                    "type": "string",
                    "format": "password",
                    "writeOnly": True,
                    "description": (
                        "The operator's purge credential as a bearer token, "
                        "written 'Bearer <token>'. Supplied by the operator, "
                        "never echoed back, never logged."
                    ),
                },
            },
        },
        "steps": [
            {
                "stepId": "eraseTarget",
                "operationPath": _operation("/paths/~1api~1purge/delete"),
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
                    {
                        "name": "targetNotUsable",
                        "type": "end",
                        "criteria": [{"condition": "$statusCode == 422"}],
                    },
                ],
                "outputs": {
                    "receiptId": "$response.body#/receiptId",
                    "issuedAt": "$response.body#/issuedAt",
                    "target": "$response.body#/target",
                    "deleted": "$response.body#/deleted",
                    "remaining": "$response.body#/remaining",
                    "complete": "$response.body#/complete",
                    "signature": "$response.body#/signature",
                },
            }
        ],
        "outputs": {
            "receiptId": "$steps.eraseTarget.outputs.receiptId",
            "issuedAt": "$steps.eraseTarget.outputs.issuedAt",
            "target": "$steps.eraseTarget.outputs.target",
            "deleted": "$steps.eraseTarget.outputs.deleted",
            "remaining": "$steps.eraseTarget.outputs.remaining",
            "complete": "$steps.eraseTarget.outputs.complete",
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
                "account and no API key.\n\n"
                + wf.ASYNC_NOTE
                + "\n\n"
                + wf.RATE_LIMIT_NOTE
                + "\n\nThe same workflows are exposed to agents as MCP tools; "
                "both are listed in the discovery document at "
                "/.well-known/ai.json."
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
        "workflows": [
            _scan_one(),
            _await_result(),
            _scan_many(),
            _plan_remediation(),
            _export(),
            _purge(),
        ],
    }
