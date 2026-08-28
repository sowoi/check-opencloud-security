"""
The OpenAPI description, written by hand against the implementation.

FastAPI can generate a schema from the signatures, and for this application
it generates a misleading one: the two submission endpoints share a handler
with the browser form, so the generator sees form fields where an API client
sends JSON, sees 200 where the handler returns 202, and has nothing at all to
say about the shape of a scan record. A specification that is *almost* right
is worse than none, because a client - or an agent - trusts it.

So the paths below are written out. Every status code, content type and field
here corresponds to a branch in :mod:`webapp.app`, and
``tests/test_webapp_openapi.py`` drives the real endpoints and fails if the
two ever disagree.

The descriptions are aimed at an agent rather than at a reader who already
knows the service: what is asynchronous, what a uuid is worth, when to wait,
when to retry and when to stop. Those sentences live in
:mod:`webapp.workflows` so that the Arazzo document and the MCP tools say the
same thing.
"""

from __future__ import annotations

from typing import Any

from opencloud_local_scan import __version__

from . import workflows as wf

OPENAPI_VERSION = "3.1.0"

#: Operations, by the id both Arazzo and the tests refer to them by.
OPERATION_IDS = (
    "createScan",
    "createScanBatch",
    "getScan",
    "exportScan",
    "eraseInstanceData",
    "healthCheck",
)

_TRACKS = ["auto", "rolling", "production", "lts"]
_FORMATS = ["dashboard", "json", "csv", "sarif", "pdf"]


def _problem(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/Problem"}
            }
        },
    }


def _rate_limited() -> dict[str, Any]:
    return {
        "description": (
            "Rate limited, and not refused. Either this client has submitted "
            "too many scans, or this target was scanned very recently and is "
            "in its cooldown. Read Retry-After, wait that many seconds and "
            f"try the same call again - at most {wf.SUBMIT_MAX_ATTEMPTS} "
            "times. The whole scanner is open source and runs locally with "
            f"no limits: {wf.SELF_HOST_URL}"
        ),
        "headers": {
            "Retry-After": {
                "description": "Seconds to wait before repeating the request.",
                "schema": {"type": "integer", "minimum": 1},
            }
        },
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/RateLimited"}
            }
        },
    }


def _schemas() -> dict[str, Any]:
    return {
        "Problem": {
            "type": "object",
            "description": "Every error this service returns, in one shape.",
            "required": ["detail"],
            "properties": {
                "detail": {
                    "type": "string",
                    "description": "What went wrong, in a sentence meant to be shown.",
                }
            },
        },
        "RateLimited": {
            "type": "object",
            "description": (
                "A 429 body. The hint and the link are deliberate: whoever "
                "hits a limit is exactly the person who should know the check "
                "runs on their own machine without one."
            ),
            "required": ["detail"],
            "properties": {
                "detail": {"type": "string"},
                "hint": {"type": "string"},
                "selfHostUrl": {"type": "string", "format": "uri"},
            },
        },
        "ScanRequest": {
            "type": "object",
            "description": wf.INPUT_NOTE,
            "additionalProperties": False,
            "required": ["target_url"],
            "properties": {
                "target_url": {
                    "type": "string",
                    "description": (
                        "The OpenCloud instance to scan, as a URL or a bare "
                        "hostname. Must be publicly resolvable: private, "
                        "loopback and link-local addresses are refused with "
                        "400."
                    ),
                    "examples": ["https://opencloud.example.com"],
                },
                "ignore_hardenings": {
                    "type": "array",
                    "description": (
                        "Hardening identifiers to waive. A waived finding "
                        "stays in the result marked as waived; it simply "
                        "stops capping the rating. Unknown identifiers are "
                        "dropped rather than rejected."
                    ),
                    "items": {"type": "string"},
                },
                "release_track": {
                    "type": "string",
                    "description": (
                        "Which release line the version is judged against. "
                        "Changes how a version is rated, never how hard the "
                        "instance is probed. Unknown values fall back to "
                        "'production'."
                    ),
                    "enum": _TRACKS,
                    "default": "production",
                },
                "output_format": {
                    "type": "string",
                    "description": (
                        "How the *result page* is rendered later. API clients "
                        "should send 'json'; the file formats make "
                        "GET /api/scans/{identifier} return the rendered file "
                        "instead of the scan record."
                    ),
                    "enum": _FORMATS,
                    "default": "dashboard",
                },
            },
        },
        "ScanAccepted": {
            "type": "object",
            "description": (
                "A scan was registered and queued. There is no rating yet - "
                "the uuid is how to come back for it."
            ),
            "required": ["uuid", "state", "url"],
            "properties": {
                "uuid": {
                    "type": "string",
                    "format": "uuid",
                    "description": (
                        "The identifier every subsequent call needs. " + wf.UUID_NOTE
                    ),
                },
                "state": {
                    "type": "string",
                    "enum": [wf.STATE_QUEUED],
                    "description": "Always 'queued' at this point.",
                },
                "url": {
                    "type": "string",
                    "description": "The human-readable result page for this scan.",
                },
            },
        },
        "BatchRequest": {
            "type": "object",
            "description": (
                "Several targets in one submission. Every target is counted "
                "against the client limit and claims its own cooldown exactly "
                "as if it had been sent alone: a batch is a convenience, not "
                "a discount."
            ),
            "additionalProperties": False,
            "required": ["targets"],
            "properties": {
                "targets": {
                    "type": "array",
                    "description": (
                        "The instances to scan, in order. Must be non-empty "
                        "and no longer than the deployment's batch limit; "
                        "either mistake answers 422."
                    ),
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "ignore_hardenings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Applied to every target in the batch.",
                },
                "release_track": {"type": "string", "enum": _TRACKS},
                "output_format": {"type": "string", "enum": _FORMATS},
            },
        },
        "BatchAcceptedTarget": {
            "type": "object",
            "description": "One target that was accepted and now has a uuid.",
            "required": ["uuid", "target", "state", "url"],
            "properties": {
                "uuid": {"type": "string", "format": "uuid"},
                "target": {"type": "string"},
                "state": {"type": "string", "enum": [wf.STATE_QUEUED]},
                "url": {"type": "string"},
            },
        },
        "BatchRejectedTarget": {
            "type": "object",
            "description": (
                "One target that was not accepted, and why. Do not resubmit "
                "it inside a retry loop: 400 and 422 will not change, and 429 "
                "says when to come back in retryAfter."
            ),
            "required": ["target", "status", "detail"],
            "properties": {
                "target": {"type": "string"},
                "status": {
                    "type": "integer",
                    "description": "The status this target would have had on its own.",
                    "enum": [400, 422, 429],
                },
                "detail": {"type": "string"},
                "retryAfter": {
                    "type": "integer",
                    "description": "Seconds to wait, present only on 429.",
                },
                "selfHostUrl": {"type": "string", "format": "uri"},
            },
        },
        "BatchAccepted": {
            "type": "object",
            "description": (
                "Two lists, never one status: some targets can start while "
                "others wait for a cooldown they share with nobody. Poll the "
                "accepted uuids; leave the rejected ones alone."
            ),
            "required": ["accepted", "rejected", "counts"],
            "properties": {
                "accepted": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/BatchAcceptedTarget"},
                },
                "rejected": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/BatchRejectedTarget"},
                },
                "counts": {
                    "type": "object",
                    "required": ["submitted", "accepted", "rejected"],
                    "properties": {
                        "submitted": {"type": "integer"},
                        "accepted": {"type": "integer"},
                        "rejected": {"type": "integer"},
                    },
                },
                "hint": {"type": "string"},
                "selfHostUrl": {"type": "string", "format": "uri"},
            },
        },
        "QueuePosition": {
            "type": "object",
            "description": (
                "Where this scan stands in line. Overload queues here, it "
                "never refuses, so a position is normal rather than a warning."
            ),
            "properties": {
                "position": {"type": "integer"},
                "length": {"type": "integer"},
            },
        },
        "RemediationStep": {
            "type": "object",
            "description": (
                "One fix, and the rating the instance would have once this "
                "step and every step before it is done. Steps are already in "
                "the order worth doing them; do not reorder them."
            ),
            "properties": {
                "order": {"type": "integer", "minimum": 1},
                "id": {
                    "type": "string",
                    "description": (
                        "The finding this step clears, or 'versionCurrent' "
                        "for the step that updates the instance."
                    ),
                },
                "kind": {"type": "string", "enum": ["upgrade", "finding"]},
                "severity": {"type": "string"},
                "title": {"type": "string"},
                "action": {
                    "type": "string",
                    "description": "What to change, in plain words.",
                },
                "reference": {"type": "string"},
                "setting": {
                    "type": "string",
                    "description": "The environment variable behind it, if any.",
                },
                "detail": {
                    "type": "string",
                    "description": (
                        "What the scanner observed. Taken from the scanned "
                        "instance, so it is somebody else's text."
                    ),
                },
                "ratingBefore": {"type": "integer", "minimum": 0, "maximum": 5},
                "ratingAfter": {"type": "integer", "minimum": 0, "maximum": 5},
                "ratingGain": {
                    "type": "integer",
                    "description": (
                        "0 means this step alone changes nothing and is still "
                        "necessary: findings of one severity share a cap, so "
                        "the rating only moves when the last of them is gone."
                    ),
                },
                "label": {"type": "string", "examples": ["A+", "C"]},
                "tag": {"type": "string", "enum": ["critical", "warning", "info"]},
            },
        },
        "RemediationPlan": {
            "type": "object",
            "description": (
                "What would raise the grade, in the order that pays off "
                "soonest. Derived from the rating while the scan ran - the "
                "same arithmetic replayed with one finding removed at a time "
                "- so a client never has to simulate anything itself."
            ),
            "properties": {
                "currentRating": {"type": "integer", "minimum": 0, "maximum": 5},
                "currentLabel": {"type": "string"},
                "achievableRating": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 5,
                    "description": "Where every step in the plan would leave it.",
                },
                "achievableLabel": {"type": "string"},
                "summary": {
                    "type": "string",
                    "description": "The plan in one sentence.",
                },
                "steps": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/RemediationStep"},
                },
                "blocked": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/RemediationStep"},
                    "description": (
                        "Findings holding the rating down that no setting "
                        "changes. Report them, never present them as fixes."
                    ),
                },
                "waived": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Findings the requester asked to ignore. They failed; "
                        "they simply did not count."
                    ),
                },
            },
        },
        "ScanSummary": {
            "type": "object",
            "description": (
                "The verdict, already computed. rating is the 0-5 scale the "
                "monitoring plugin uses, where 5 is best and 0 worst, and "
                "label is its letter. Nothing about it is recomputed by a "
                "client: this is the answer."
            ),
            "properties": {
                "rating": {"type": "integer", "minimum": 0, "maximum": 5},
                "label": {"type": "string", "examples": ["A", "F"]},
                "tone": {"type": "string"},
                "eol": {
                    "type": "boolean",
                    "description": (
                        "The release no longer receives security fixes. This "
                        "overrides everything else, including waivers."
                    ),
                },
                "domain": {"type": "string"},
                "product": {"type": "string"},
                "version": {"type": "string"},
                "releaseType": {"type": "string"},
                "lifecycle": {"type": "object", "additionalProperties": True},
                "updates": {"type": "object", "additionalProperties": True},
                "explanation": {
                    "type": "string",
                    "description": "Why the rating is what it is.",
                },
                "vulnerabilities": {"type": "array", "items": {"type": "object"}},
                "issues": {"type": "array", "items": {"type": "object"}},
                "waived": {"type": "array", "items": {"type": "object"}},
                "unfixable": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": (
                        "Findings an operator cannot change because OpenCloud "
                        "hardcodes them. Reported, never counted against the "
                        "instance."
                    ),
                },
                "missingHardenings": {"type": "array", "items": {"type": "object"}},
                "missingHeaders": {"type": "array", "items": {"type": "object"}},
                "remediation": {"$ref": "#/components/schemas/RemediationPlan"},
                "passedCount": {"type": "integer"},
                "https": {"type": "object", "additionalProperties": True},
                "tls": {"$ref": "#/components/schemas/TlsDetail"},
                "identityProvider": {"type": "object", "additionalProperties": True},
                "reverseProxy": {"type": "object", "additionalProperties": True},
                "integrations": {"type": "array", "items": {"type": "object"}},
                "counts": {
                    "type": "object",
                    "properties": {
                        "critical": {"type": "integer"},
                        "warning": {"type": "integer"},
                        "info": {"type": "integer"},
                        "vulnerabilities": {"type": "integer"},
                    },
                },
            },
        },
        "TlsDetail": {
            "type": "object",
            "description": (
                "What the TLS layer itself reported, measured before any HTTP "
                "request. The findings in 'issues' already judge these values; "
                "this is the evidence behind them, for a caller that needs the "
                "certificate dates or the negotiated cipher rather than a "
                "verdict. Absent when the instance was scanned over plain HTTP. "
                "Every 'null' here means 'not determined', never 'fine': a "
                "handshake that failed before the certificate was judged leaves "
                "'trusted' null rather than false."
            ),
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer"},
                "reachable": {"type": "boolean"},
                "error": {"type": "string"},
                "protocol": {
                    "type": "string",
                    "description": "The version negotiated, such as 'TLSv1.3'.",
                    "examples": ["TLSv1.3", "TLSv1.2"],
                },
                "cipher": {"type": "string"},
                "cipherBits": {"type": ["integer", "null"]},
                "trusted": {
                    "type": ["boolean", "null"],
                    "description": (
                        "Whether the chain validates against the public trust "
                        "store. Null when the handshake never reached the "
                        "certificate."
                    ),
                },
                "verifyError": {"type": "string"},
                "verifyCode": {"type": ["integer", "null"]},
                "hostnameMatch": {
                    "type": ["boolean", "null"],
                    "description": (
                        "Whether a subject alternative name covers the scanned "
                        "host. Checked independently of trust, because an "
                        "untrusted chain stops verification before the name is "
                        "ever compared."
                    ),
                },
                "chainComplete": {
                    "type": ["boolean", "null"],
                    "description": (
                        "Whether the certificates the server sent reach a "
                        "public root. Null for a self-signed certificate, where "
                        "the question does not apply."
                    ),
                },
                "chainLength": {"type": ["integer", "null"]},
                "deprecatedProtocolsAccepted": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Deprecated versions the server still completes a "
                        "handshake with. The negotiated version says nothing "
                        "about this: it is the oldest version accepted that "
                        "decides what an attacker can force."
                    ),
                },
                "deprecatedProtocolsProbed": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Which deprecated versions were actually asked about. A "
                        "version missing from this list was not tested and "
                        "nothing may be concluded about it."
                    ),
                },
                "ocspStapled": {
                    "type": ["boolean", "null"],
                    "description": (
                        "Whether a revocation answer is stapled to the "
                        "handshake. Null when the certificate names no "
                        "responder, which is now the norm, or when stapling "
                        "could not be checked - see ocspNote."
                    ),
                },
                "ocspNote": {"type": "string"},
                "certificate": {
                    "type": ["object", "null"],
                    "properties": {
                        "subject": {"type": "string"},
                        "issuer": {"type": "string"},
                        "serialNumber": {"type": "string"},
                        "notBefore": {"type": "string"},
                        "notAfter": {"type": "string"},
                        "daysRemaining": {
                            "type": ["integer", "null"],
                            "description": "Negative once the certificate has expired.",
                        },
                        "lifetimeDays": {"type": ["integer", "null"]},
                        "altNames": {"type": "array", "items": {"type": "string"}},
                        "ocspResponders": {"type": "array", "items": {"type": "string"}},
                        "selfSigned": {"type": "boolean"},
                        "keyType": {
                            "type": "string",
                            "description": "The public-key algorithm, when OpenSSL could inspect it.",
                        },
                        "keyBits": {"type": ["integer", "null"]},
                        "signatureAlgorithm": {"type": "string"},
                    },
                },
            },
        },
        "ScanRecord": {
            "type": "object",
            "description": (
                "The whole of what is known about one scan. " + wf.ASYNC_NOTE
            ),
            "required": ["uuid", "state", "target"],
            "properties": {
                "uuid": {"type": "string", "format": "uuid"},
                "state": {
                    "type": "string",
                    "description": (
                        "'queued' and 'running' mean poll again in "
                        f"{wf.POLL_INTERVAL_SECONDS} seconds. 'completed' and "
                        "'failed' are final."
                    ),
                    "enum": list(wf.PENDING_STATES + wf.TERMINAL_STATES),
                },
                "done": {
                    "type": "boolean",
                    "description": (
                        "Present and true once the state is terminal. The one "
                        "field to poll on; absent while the scan is running."
                    ),
                },
                "target": {"type": "string"},
                "ignoreHardenings": {"type": "array", "items": {"type": "string"}},
                "outputFormat": {"type": "string", "enum": _FORMATS},
                "releaseTrack": {"type": "string", "enum": _TRACKS},
                "createdAt": {"type": "string"},
                "startedAt": {"type": "string"},
                "finishedAt": {"type": "string"},
                "expiresIn": {
                    "type": "integer",
                    "description": (
                        "Seconds left before this scan is deleted. "
                        + wf.EXPIRY_NOTE
                    ),
                },
                "queue": {"$ref": "#/components/schemas/QueuePosition"},
                "summary": {
                    "$ref": "#/components/schemas/ScanSummary",
                    "description": "Present once the state is 'completed'.",
                },
                "exports": {
                    "type": "object",
                    "description": (
                        "Where to fetch this finished scan as a file, by "
                        "format. Present once the state is 'completed'."
                    ),
                    "properties": {
                        name: {"type": "string"} for name in wf.EXPORT_FORMATS
                    },
                },
                "result": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": (
                        "The raw scan document the scanner produced. Present "
                        "once the state is 'completed'."
                    ),
                },
                "error": {
                    "type": "string",
                    "description": "Present when the state is 'failed'.",
                },
            },
        },
        "PurgeReceipt": {
            "type": "object",
            "description": (
                "Proof that an erasure happened, for the operator to keep: "
                "the data it describes no longer exists to be shown. It never "
                "contains the credential that authorised it."
            ),
            "required": ["receiptId", "issuedAt", "target", "deleted", "complete"],
            "properties": {
                "receiptId": {"type": "string"},
                "issuedAt": {"type": "string", "format": "date-time"},
                "target": {"type": "string"},
                "targetFingerprint": {
                    "type": "string",
                    "description": "A hash of the target, so the receipt can be filed.",
                },
                "deleted": {
                    "type": "object",
                    "description": "What was removed, counted by kind.",
                    "properties": {
                        "scans": {"type": "integer"},
                        "keys": {"type": "integer"},
                        "queueEntries": {"type": "integer"},
                        "rateLimitKeys": {"type": "integer"},
                    },
                },
                "remaining": {
                    "type": "integer",
                    "description": (
                        "What a second pass still found. Zero is the point of "
                        "the receipt."
                    ),
                },
                "complete": {"type": "boolean"},
                "statement": {"type": "string"},
                "notes": {"type": "array", "items": {"type": "string"}},
                "service": {"type": "string"},
                "version": {"type": "string"},
                "signature": {
                    "description": (
                        "An HMAC over the receipt when the deployment "
                        "configured a signing key, otherwise null. The key "
                        "itself is never disclosed."
                    ),
                    "oneOf": [
                        {
                            "type": "object",
                            "properties": {
                                "algorithm": {"type": "string"},
                                "value": {"type": "string"},
                            },
                        },
                        {"type": "null"},
                    ],
                },
            },
        },
        "Health": {
            "type": "object",
            "description": (
                "Liveness of the whole stack. 503 means the queue backend or "
                "the worker is not answering and a submission would sit "
                "forever; wait and try again."
            ),
            "required": ["status", "version"],
            "properties": {
                "status": {"type": "string", "enum": ["ok", "unavailable"]},
                "version": {"type": "string"},
                "queueDepth": {"type": "integer"},
                "worker": {"type": "string"},
            },
        },
        "ExportConflict": {
            "type": "object",
            "description": wf.CONFLICT_NOTE,
            "required": ["detail", "state"],
            "properties": {
                "detail": {"type": "string"},
                "state": {
                    "type": "string",
                    "enum": list(wf.PENDING_STATES + (wf.STATE_FAILED,)),
                },
            },
        },
    }


def _paths() -> dict[str, Any]:
    identifier_param = {
        "name": "identifier",
        "in": "path",
        "required": True,
        "description": "The uuid returned when the scan was created.",
        "schema": {"type": "string", "format": "uuid"},
    }
    return {
        "/api/scans": {
            "post": {
                "operationId": "createScan",
                "tags": ["scans"],
                "summary": "Submit one instance for scanning.",
                "description": (
                    "Registers a scan and returns immediately.\n\n"
                    + wf.ASYNC_NOTE
                    + "\n\n"
                    + wf.UUID_NOTE
                    + "\n\n"
                    + wf.RATE_LIMIT_NOTE
                    + "\n\nSend JSON. The same path also accepts a form body, "
                    "which is how the browser form on the landing page posts; "
                    "an HTML client is answered with a 303 redirect to the "
                    "result page rather than with the JSON below."
                ),
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ScanRequest"}
                        },
                        "application/x-www-form-urlencoded": {
                            "schema": {"$ref": "#/components/schemas/ScanRequest"}
                        },
                    },
                },
                "responses": {
                    "202": {
                        "description": (
                            "Accepted and queued. Poll the uuid; the rating "
                            "does not exist yet."
                        ),
                        "headers": {
                            "Location": {
                                "description": "The result page for this scan.",
                                "schema": {"type": "string"},
                            }
                        },
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/ScanAccepted"
                                }
                            }
                        },
                    },
                    "400": _problem(
                        "The target was refused: not resolvable, or an "
                        "address this service will not probe. Do not retry."
                    ),
                    "422": _problem(
                        "The body carried a field this service does not "
                        "accept. The message names it. Do not retry."
                    ),
                    "429": _rate_limited(),
                },
            }
        },
        "/api/scans/batch": {
            "post": {
                "operationId": "createScanBatch",
                "tags": ["scans"],
                "summary": "Submit several instances in one call.",
                "description": (
                    "JSON only.\n\n"
                    "The answer separates what started from what did not. "
                    "Poll each accepted uuid exactly as for a single scan, "
                    "and do not resubmit a rejected target: it was refused "
                    "for a reason that says whether and when to come back."
                    "\n\n" + wf.RATE_LIMIT_NOTE
                ),
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/BatchRequest"}
                        }
                    },
                },
                "responses": {
                    "202": {
                        "description": (
                            "At least one target started. Some may still have "
                            "been rejected - read both lists."
                        ),
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/BatchAccepted"
                                }
                            }
                        },
                    },
                    "400": {
                        "description": (
                            "No target was accepted and the first refusal was "
                            "an unusable target."
                        ),
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/BatchAccepted"
                                }
                            }
                        },
                    },
                    "422": {
                        "description": (
                            "The batch itself was malformed - an unknown "
                            "field, an empty list, or more targets than this "
                            "deployment allows - or no target was accepted "
                            "and the first refusal was a 422."
                        ),
                        "content": {
                            "application/json": {
                                "schema": {
                                    "oneOf": [
                                        {"$ref": "#/components/schemas/Problem"},
                                        {
                                            "$ref": "#/components/schemas/BatchAccepted"
                                        },
                                    ]
                                }
                            }
                        },
                    },
                    "429": {
                        "description": (
                            "No target was accepted and the first refusal was "
                            "a rate limit. Retry-After says when."
                        ),
                        "headers": {
                            "Retry-After": {
                                "description": "Seconds to wait.",
                                "schema": {"type": "integer"},
                            }
                        },
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/BatchAccepted"
                                }
                            }
                        },
                    },
                },
            }
        },
        "/api/scans/{identifier}": {
            "get": {
                "operationId": "getScan",
                "tags": ["scans"],
                "summary": "Read the state, and then the result, of one scan.",
                "description": (
                    "The polling endpoint.\n\n"
                    + wf.ASYNC_NOTE
                    + "\n\n"
                    + wf.UUID_NOTE
                    + "\n\n"
                    + wf.EXPIRY_NOTE
                    + "\n\nWhen the scan was submitted with output_format set "
                    "to csv, sarif or pdf and has completed, this endpoint "
                    "returns that rendered file instead of the JSON record."
                ),
                "parameters": [identifier_param],
                "responses": {
                    "200": {
                        "description": (
                            "The scan record. 'done' is true once it has "
                            "finished; 'summary' and 'exports' appear when it "
                            "completed."
                        ),
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ScanRecord"}
                            },
                            "text/csv": {"schema": {"type": "string"}},
                            "application/sarif+json": {
                                "schema": {"type": "object"}
                            },
                            "application/pdf": {
                                "schema": {"type": "string", "format": "binary"}
                            },
                        },
                    },
                    "404": _problem(
                        "Unknown, malformed or expired uuid - the three are "
                        "deliberately indistinguishable. Final: do not retry."
                    ),
                },
            }
        },
        "/api/scans/{identifier}/export/{fmt}": {
            "get": {
                "operationId": "exportScan",
                "tags": ["scans"],
                "summary": "Download one finished scan as a file.",
                "description": (
                    "JSON, CSV, SARIF and PDF are four renderings of the same "
                    "finished result.\n\n" + wf.CONFLICT_NOTE
                ),
                "parameters": [
                    identifier_param,
                    {
                        "name": "fmt",
                        "in": "path",
                        "required": True,
                        "description": "Which rendering to produce.",
                        "schema": {
                            "type": "string",
                            "enum": list(wf.EXPORT_FORMATS),
                        },
                    },
                ],
                "responses": {
                    "200": {
                        "description": "The rendered file, as an attachment.",
                        "headers": {
                            "Content-Disposition": {
                                "description": "attachment, with a filename.",
                                "schema": {"type": "string"},
                            }
                        },
                        "content": {
                            "application/json": {"schema": {"type": "object"}},
                            "text/csv": {"schema": {"type": "string"}},
                            "application/sarif+json": {
                                "schema": {"type": "object"}
                            },
                            "application/pdf": {
                                "schema": {"type": "string", "format": "binary"}
                            },
                        },
                    },
                    "404": _problem(
                        "Unknown or expired uuid, or a format this service "
                        "does not render. Final: do not retry."
                    ),
                    "409": {
                        "description": (
                            "The scan exists but has not finished. Wait "
                            f"{wf.EXPORT_RETRY_SECONDS} seconds and ask again."
                        ),
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/ExportConflict"
                                }
                            }
                        },
                    },
                },
            }
        },
        "/api/purge": {
            "delete": {
                "operationId": "eraseInstanceData",
                "tags": ["erasure"],
                "summary": "Erase everything stored about one instance.",
                "description": (
                    "Destructive, authorised and irreversible. It deletes "
                    "every scan of one instance, including results other "
                    "people may currently be reading, and returns a receipt "
                    "rather than the data.\n\n"
                    "Present the operator's purge credential as a bearer "
                    "token. There is no way to obtain one from this API: an "
                    "agent that does not already hold it must stop and ask "
                    "the operator. Confirm with a human before calling this."
                    "\n\nWhen the deployment has no purge credential "
                    "configured the feature is not present and the endpoint "
                    "answers 404, exactly like a path that does not exist."
                ),
                "security": [{"purgeToken": []}],
                "parameters": [
                    {
                        "name": "target",
                        "in": "query",
                        "required": True,
                        "description": (
                            "The instance hostname, with or without a scheme."
                        ),
                        "schema": {"type": "string"},
                        "examples": {
                            "hostname": {"value": "opencloud.example.com"}
                        },
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Everything matching was deleted. Keep the receipt.",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/PurgeReceipt"
                                }
                            }
                        },
                    },
                    "401": {
                        "description": (
                            "The credential was missing or wrong. Do not "
                            "retry, and do not guess: ask the operator."
                        ),
                        "headers": {
                            "WWW-Authenticate": {
                                "description": "Bearer.",
                                "schema": {"type": "string"},
                            }
                        },
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Problem"}
                            }
                        },
                    },
                    "404": _problem(
                        "This deployment has no erasure endpoint configured."
                    ),
                    "422": _problem("The target was not a usable hostname."),
                },
            }
        },
        "/healthz": {
            "get": {
                "operationId": "healthCheck",
                "tags": ["service"],
                "summary": "Whether the service can currently run a scan.",
                "description": (
                    "Cheap and unauthenticated. Worth calling before a batch: "
                    "503 means a submission would be queued behind a worker "
                    "that is not running."
                ),
                "responses": {
                    "200": {
                        "description": "The queue backend and a worker are both answering.",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Health"}
                            }
                        },
                    },
                    "503": {
                        "description": (
                            "The backend or the worker is not answering. "
                            "Retryable: wait and ask again."
                        ),
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Health"}
                            }
                        },
                    },
                },
            }
        },
    }


def openapi_document(*, server_url: str | None = None) -> dict[str, Any]:
    """The API description this service publishes at ``/openapi.json``."""
    document: dict[str, Any] = {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": "check-opencloud-security",
            "summary": "Public security scan service for OpenCloud instances.",
            "description": (
                "Scans a publicly reachable OpenCloud instance and rates it "
                "from 0 to 5, the way the monitoring plugin of the same name "
                "does. No account, no API key, no registration.\n\n"
                + wf.ASYNC_NOTE
                + "\n\n"
                + wf.UUID_NOTE
                + "\n\n"
                + wf.RATE_LIMIT_NOTE
                + "\n\nWorkflows combining these operations are published as "
                "an Arazzo 1.0.1 document at /arazzo.json, and the same "
                "capabilities are available to agents over MCP. Both are "
                "listed in the discovery document at /.well-known/ai.json.\n\n"
                "This service is not affiliated with, endorsed by or "
                "supported by OpenCloud GmbH."
            ),
            "version": __version__,
            "license": {
                "name": "AGPL-3.0-or-later",
                "identifier": "AGPL-3.0-or-later",
            },
            "contact": {"name": "check-opencloud-security", "url": wf.SELF_HOST_URL},
        },
        "tags": [
            {
                "name": "scans",
                "description": (
                    "Submitting scans and reading them back. Asynchronous "
                    "throughout."
                ),
            },
            {
                "name": "erasure",
                "description": "Deleting stored results. Authorised and destructive.",
            },
            {"name": "service", "description": "Whether the service is up."},
        ],
        "paths": _paths(),
        # Nothing is authenticated. Saying so explicitly, rather than by
        # omission, is what lets a client tell "open to anyone" apart from
        # "the specification forgot to mention the credential".
        "security": [],
        "components": {
            "schemas": _schemas(),
            "securitySchemes": {
                "purgeToken": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": (
                        "The operator's erasure credential. Only the erasure "
                        "endpoint uses it; everything else is unauthenticated."
                    ),
                }
            },
        },
    }
    if server_url:
        document["servers"] = [{"url": server_url}]
    return document
