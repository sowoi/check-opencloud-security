"""
Erasure on request, and a receipt that survives the data it describes.

Everything this service keeps about a scan already expires on its own, which
answers storage limitation but not Article 17: somebody who wants their
instance forgotten *now* cannot wait an hour, and an operator answering that
request needs something to put in the file afterwards.

Two things make that awkward here, and both are deliberate features of the
rest of the design:

- **There is no index from a target to its scans.** Building one would create
  exactly the database this service refuses to keep. So a purge walks the
  keyspace once, reads each scan's own metadata and matches on the hostname -
  slow, rare, and impossible to reach from the request path.
- **The data is gone before the proof is written.** A receipt cannot point at
  a record that no longer exists, so it carries counts, a fingerprint of the
  target and a second pass that confirms nothing matched any more. That
  second pass is the evidence: not "we deleted it" but "we looked again and
  there is nothing there".

The receipt is signed when the deployment configures a signing key, so a data
subject can be handed a document the operator cannot quietly rewrite later.
The signature covers the receipt exactly as it is returned, minus the
signature block itself.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import uuid as uuid_module
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from opencloud_local_scan import __version__

from .store import PurgeReport

SIGNATURE_ALGORITHM = "HMAC-SHA256"

# One key signs receipts and fingerprints targets, so each use labels its own
# input. Without that, the two are only kept apart by the accident that a
# hostname can never look like a canonical receipt.
SIGNATURE_DOMAIN = b"cos:purge:receipt\x00"
FINGERPRINT_DOMAIN = b"cos:purge:target\x00"

MAX_TARGET_LENGTH = 253

_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOSTNAME = re.compile(rf"^{_LABEL}(?:\.{_LABEL})*$")

# Said in the receipt itself, because a receipt that only carries numbers
# leaves the reader to guess what was in scope.
STATEMENT = (
    "All scan records held for this target were deleted at the time stated "
    "below. A second pass over the store after the deletion found the number "
    "of remaining records given as 'remaining'. Scan records expire by "
    "themselves as well; this receipt records a deletion that was asked for."
)


#: The shortest credential this endpoint will accept at startup. The wizard
#: generates 64 hex characters; anything under this is a token somebody typed,
#: and a token somebody typed is one that can be guessed.
MIN_TOKEN_LENGTH = 32


class PurgeRejected(ValueError):
    """The target of an erasure request could not be understood."""


def ensure_purge_token_ready(token: str | None) -> None:
    """
    Refuse to start when the erasure credential is weak enough to guess.

    The endpoint answers 404 without a token at all, which is the safe state.
    *With* one, that single string is the whole of the authorisation for the
    one call that walks the keyspace and deletes results belonging to whoever
    is currently reading them - so a memorable one is worse than none, and the
    same reasoning that makes ``ensure_encryption_ready`` refuse to store
    plaintext applies here.
    """
    if not token:
        return
    if len(token) < MIN_TOKEN_LENGTH:
        raise ValueError(
            f"COS_WEB_PURGE_TOKEN must be at least {MIN_TOKEN_LENGTH} characters. "
            "It is the entire authorisation for an endpoint that deletes other "
            "people's results; generate one with "
            "`python -c 'import secrets; print(secrets.token_hex(32))'`."
        )


def normalise_target(raw: str | None) -> str:
    """
    Turn what an erasure request names into the hostname it means.

    ``instance.example.com``, ``https://instance.example.com/`` and
    ``INSTANCE.example.com:9200`` all name the same instance, and a person
    writing to an operator will use whichever they have to hand.
    """
    candidate = (raw or "").strip()
    if not candidate:
        raise PurgeRejected("Name the instance to erase in the 'target' parameter.")
    if "//" not in candidate:
        candidate = f"//{candidate}"
    try:
        parsed = urlsplit(candidate if "://" in candidate else f"http:{candidate}")
        hostname = (parsed.hostname or "").strip().lower()
        # Reading the port validates it. ``scan:*`` otherwise parses as the
        # host ``scan``, and a purge should refuse what it does not understand
        # rather than delete under a hostname nobody named.
        _port = parsed.port
    except ValueError as exc:
        raise PurgeRejected("That is not a hostname this service could hold.") from exc
    if not hostname or len(hostname) > MAX_TARGET_LENGTH:
        raise PurgeRejected("That is not a hostname this service could hold.")
    if _HOSTNAME.match(hostname):
        return hostname
    try:
        return str(ipaddress.ip_address(hostname))
    except ValueError as exc:
        raise PurgeRejected("That is not a hostname this service could hold.") from exc


def fingerprint(target: str, key: str | None) -> str | None:
    """
    A pseudonym for the erased target, safe to keep in a compliance file.

    The receipt is handed to somebody who already knows which instance they
    asked about, so it names the target in the clear. The fingerprint is what
    an operator can file, quote in a register or hand to an auditor without
    the file itself becoming another record of who was scanned.

    That only holds with a key. An unkeyed hash of a hostname is not a
    pseudonym - the space of hostnames is small enough to enumerate on a
    laptop - so without a signing key there is no fingerprint rather than a
    false one. The label in front of the target keeps this value in a
    different domain from a receipt signature computed under the same key.
    """
    if not key:
        return None
    message = FINGERPRINT_DOMAIN + target.encode("utf-8")
    digest = hmac.new(key.encode("utf-8"), message, hashlib.sha256)
    return digest.hexdigest()[:32]


@dataclass(frozen=True)
class PurgeReceipt:
    """Proof that an erasure request was carried out, and how completely."""

    receipt_id: str
    issued_at: str
    target: str
    target_fingerprint: str | None
    report: PurgeReport
    cooldown_keys: int
    signature: str | None
    notes: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        """Whether the verification pass found nothing left."""
        return self.report.remaining == 0

    def unsigned(self) -> dict[str, Any]:
        """The receipt body the signature is computed over."""
        return {
            "receiptId": self.receipt_id,
            "issuedAt": self.issued_at,
            "target": self.target,
            "targetFingerprint": self.target_fingerprint,
            "deleted": {
                "scans": self.report.scans,
                "keys": self.report.keys_deleted,
                "queueEntries": self.report.queue_entries,
                "rateLimitKeys": self.cooldown_keys,
            },
            "remaining": self.report.remaining,
            "complete": self.complete,
            "statement": STATEMENT,
            "notes": list(self.notes),
            "service": "check-opencloud-security",
            "version": __version__,
        }

    def as_dict(self) -> dict[str, Any]:
        """The JSON body of ``DELETE /api/purge``."""
        payload = self.unsigned()
        payload["signature"] = (
            {"algorithm": SIGNATURE_ALGORITHM, "value": self.signature}
            if self.signature
            else None
        )
        return payload


def canonical(payload: dict[str, Any]) -> str:
    """
    The exact bytes a signature covers.

    Sorted keys and no incidental whitespace, so a verifier reproduces the
    string from the parsed JSON rather than from however it was transmitted.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sign(payload: dict[str, Any], key: str | None) -> str | None:
    """Sign a receipt body, or return ``None`` when no key is configured."""
    if not key:
        return None
    message = SIGNATURE_DOMAIN + canonical(payload).encode("utf-8")
    return hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify(receipt: dict[str, Any], key: str) -> bool:
    """
    Check a receipt against the signing key. Written for whoever is handed one.

    Used by the tests, and by an operator or auditor with three lines of
    Python months after the data itself stopped existing.
    """
    signature = receipt.get("signature")
    if not isinstance(signature, dict):
        return False
    value = signature.get("value")
    if not isinstance(value, str):
        return False
    body = {name: item for name, item in receipt.items() if name != "signature"}
    expected = sign(body, key)
    return expected is not None and hmac.compare_digest(expected, value)


def build_receipt(
    *,
    target: str,
    report: PurgeReport,
    cooldown_keys: int,
    signing_key: str | None,
    notes: tuple[str, ...] = (),
) -> PurgeReceipt:
    """Assemble and sign the receipt for one completed purge."""
    receipt = PurgeReceipt(
        receipt_id=str(uuid_module.uuid4()),
        issued_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        target=target,
        target_fingerprint=fingerprint(target, signing_key),
        report=report,
        cooldown_keys=cooldown_keys,
        signature=None,
        notes=notes,
    )
    return PurgeReceipt(
        receipt_id=receipt.receipt_id,
        issued_at=receipt.issued_at,
        target=receipt.target,
        target_fingerprint=receipt.target_fingerprint,
        report=report,
        cooldown_keys=cooldown_keys,
        signature=sign(receipt.unsigned(), signing_key),
        notes=notes,
    )
