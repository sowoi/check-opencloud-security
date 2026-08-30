"""
The audit trail of a public deployment.

An operator running this service for other people eventually has to answer a
question the lifecycle log cannot: was this instance scanned repeatedly from
one network, did the limits actually hold, is somebody probing the submission
endpoint with fields it does not accept. That is an audit question, and it
needs a record with a timestamp.

It also collides with the rule the rest of the service lives by - a log of
what everybody scanned *is* a database of what everybody scanned - so this
module is built around that collision rather than against it:

- **Off unless asked for.** Without ``COS_WEB_AUDIT_LOG`` nothing here emits a
  single line, and the ordinary lifecycle log is unchanged.
- **Pseudonyms, not identities.** A client address and, by default, a target
  are recorded as a truncated HMAC under a salt. Two requests from the same
  network share a fingerprint, which is what an audit needs; nothing in the
  log maps a fingerprint back to an address. That last part depends on the
  salt staying secret - an address space is small enough to hash exhaustively -
  so a salt an operator pins is a secret, and the default is a random one
  nobody holds.
- **A salt that expires with the process** unless the operator sets
  ``COS_WEB_AUDIT_SALT``. Correlating across a restart is a deliberate choice
  somebody has to make and can undo by rotating the salt.
- **Cleartext targets are a separate switch.** ``COS_WEB_AUDIT_LOG_TARGETS``
  records the hostname, which a private deployment scanning its own estate may
  well want and a public one should leave alone.

Records go to the ``check_opencloud.web.audit`` logger, one JSON object per
line, so a deployment can route, retain or discard them separately from
everything else it logs. By default that is the process output, which a
container keeps for exactly as long as the container exists;
``COS_WEB_AUDIT_LOG_FILE`` points the logger at a file instead, for a
deployment that mounted somewhere for it to survive in.
``COS_WEB_AUDIT_LOG_ROTATION`` then says who keeps that file from growing
without limit: this process, or logrotate on the host.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import logging.handlers
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .settings import (
    AUDIT_ROTATION_EXTERNAL,
    AUDIT_ROTATION_SERVICE,
    WebSettings,
)

AUDIT_LOGGER = logging.getLogger("check_opencloud.web.audit")

# Events, named so a grep for one of them finds every occurrence.
EVENT_SCAN_REQUESTED = "scan_requested"
EVENT_SUBMISSION_REJECTED = "submission_rejected"
EVENT_RATE_LIMITED = "rate_limited"
EVENT_DATA_PURGED = "data_purged"

REASON_UNSUPPORTED_FIELDS = "unsupported_fields"
REASON_TARGET_REJECTED = "target_rejected"
REASON_RATE_LIMIT_CLIENT = "rate_limit_client"
REASON_RATE_LIMIT_TARGET = "rate_limit_target"
REASON_BATCH_TOO_LARGE = "batch_too_large"
REASON_PURGE_UNAUTHORISED = "purge_unauthorised"
REASON_RATE_LIMIT_PURGE = "rate_limit_purge"

# Field names come from a stranger's request body. They are worth recording -
# a probe for "workers" or "timeout" is exactly what an audit trail is for -
# but only as much of them as identifies the attempt.
MAX_FIELD_NAMES = 10
MAX_FIELD_LENGTH = 40

_FINGERPRINT_LENGTH = 16

# The audit file is owner-only. Fingerprints are pseudonyms rather than
# addresses, but a deployment that also records targets in the clear has
# written down who scanned what, and a mounted volume is readable by whoever
# reaches the host.
_AUDIT_FILE_MODE = 0o600


class _OwnerOnly:
    """Keeps the audit file owner-readable every time it is opened.

    A mixin rather than a chmod at setup time: both handlers below open a
    fresh file after a rotation, and one created under the container's umask
    would quietly widen the permissions of every generation after the first.
    """

    def _open(self):  # type: ignore[no-untyped-def]
        stream = super()._open()  # type: ignore[misc]
        try:
            os.chmod(self.baseFilename, _AUDIT_FILE_MODE)  # type: ignore[attr-defined]
        except OSError:  # pragma: no cover - a filesystem that has no modes
            pass
        return stream


class _RotatingAuditFile(_OwnerOnly, logging.handlers.RotatingFileHandler):
    """The trail rotated by this process, by size, needing nothing installed."""


class _WatchedAuditFile(_OwnerOnly, logging.handlers.WatchedFileHandler):
    """The trail rotated by something else on the host.

    logrotate moves the file aside and creates a new one; a writer holding the
    old descriptor would go on filling a file nobody can find any more, and
    the trail would appear to stop the first night it ran. This handler checks
    the inode before each record and reopens when it changed, which is the
    half of the arrangement that lives in this process - the other half is the
    ``create`` line in the logrotate policy, which is what makes the new file
    writable by the container.
    """


# What the two names in COS_WEB_AUDIT_LOG_ROTATION mean, in one place.
_HANDLERS = {
    AUDIT_ROTATION_SERVICE: _RotatingAuditFile,
    AUDIT_ROTATION_EXTERNAL: _WatchedAuditFile,
}


def configure_audit_file(settings: WebSettings) -> str | None:
    """
    Point the audit logger at a file, or back at the process output.

    Called once at startup and safe to call again: the previous handler is
    removed and closed, so a second application in the same process does not
    write every record twice.

    A file that cannot be opened stops the process. The alternative is a
    service that reports an audit trail it is not keeping, and an operator
    only finds out when somebody asks for the records - which is precisely the
    moment the answer has to already exist. It follows the same reasoning as
    refusing to start without the encryption key a deployment asked for.
    """
    for existing in list(AUDIT_LOGGER.handlers):
        if isinstance(existing, _OwnerOnly):
            AUDIT_LOGGER.removeHandler(existing)
            existing.close()
    AUDIT_LOGGER.propagate = True

    if not settings.audit_log or not settings.audit_log_file:
        return None

    rotation = settings.audit_log_rotation
    if rotation not in _HANDLERS:
        raise ValueError(
            f"COS_WEB_AUDIT_LOG_ROTATION is {rotation!r}, which is neither "
            f"{AUDIT_ROTATION_SERVICE!r} nor {AUDIT_ROTATION_EXTERNAL!r}. "
            "Guessing would mean either two rotators on one file or none."
        )

    path = Path(settings.audit_log_file)
    if not path.parent.is_dir():
        raise ValueError(
            f"COS_WEB_AUDIT_LOG_FILE is {path}, but {path.parent} is not a directory. "
            "Mount a volume there, or point it at a path that exists."
        )
    try:
        if rotation == AUDIT_ROTATION_EXTERNAL:
            handler: logging.Handler = _WatchedAuditFile(str(path), encoding="utf-8")
        else:
            handler = _RotatingAuditFile(
                str(path),
                maxBytes=settings.audit_log_max_bytes,
                backupCount=settings.audit_log_backups,
                encoding="utf-8",
            )
    except OSError as error:
        raise ValueError(
            f"COS_WEB_AUDIT_LOG_FILE {path} cannot be written to: {error}. "
            "The container runs as uid 10001; a bind-mounted directory has to "
            "be owned by it."
        ) from error
    # The record is already one complete JSON object, and the point of the
    # format is that a line is parseable on its own.
    handler.setFormatter(logging.Formatter("%(message)s"))
    AUDIT_LOGGER.addHandler(handler)
    AUDIT_LOGGER.setLevel(logging.INFO)
    # The file *is* the audit trail now. Leaving propagation on would copy
    # every record into the ordinary log as well, which is the one place this
    # service deliberately keeps free of targets and client fingerprints.
    AUDIT_LOGGER.propagate = False
    return str(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_field(name: str) -> str:
    """One submitted field name, shortened and stripped of control characters."""
    printable = "".join(char for char in str(name) if char.isprintable())
    return printable[:MAX_FIELD_LENGTH]


@dataclass(frozen=True)
class AuditLog:
    """Writes audit records, or nothing at all when it is disabled."""

    enabled: bool = False
    record_targets: bool = False
    """Record the target hostname in the clear rather than as a fingerprint."""

    salt: bytes = b""

    @classmethod
    def from_settings(cls, settings: WebSettings) -> AuditLog:
        """Build the audit log a deployment's settings ask for."""
        if not settings.audit_log:
            return cls(enabled=False)
        configured = settings.audit_salt
        salt = configured.encode("utf-8") if configured else os.urandom(32)
        return cls(
            enabled=True,
            record_targets=settings.audit_log_targets,
            salt=salt,
        )

    def fingerprint(self, value: str) -> str:
        """A stable pseudonym for one value under this deployment's salt."""
        digest = hmac.new(self.salt, value.encode("utf-8"), hashlib.sha256)
        return digest.hexdigest()[:_FINGERPRINT_LENGTH]

    def _emit(self, event: str, **fields: object) -> None:
        if not self.enabled:
            return
        record: dict[str, object] = {"event": event, "timestamp": _now()}
        record.update({key: value for key, value in fields.items() if value is not None})
        # json.dumps escapes newlines, which is what keeps a submitted value
        # from forging a second line of the audit trail.
        AUDIT_LOGGER.info(json.dumps(record, sort_keys=True))

    def _client(self, client: str) -> str:
        return self.fingerprint(client)

    def _target(self, target: str | None) -> str | None:
        if target is None:
            return None
        if self.record_targets:
            return target
        return self.fingerprint(target.lower())

    def scan_requested(
        self,
        *,
        identifier: str,
        client: str,
        target: str,
        output_format: str,
        release_track: str,
        waivers: int,
    ) -> None:
        """An accepted submission, at the moment it became a scan."""
        self._emit(
            EVENT_SCAN_REQUESTED,
            uuid=identifier,
            client=self._client(client),
            target=self._target(target),
            outputFormat=output_format,
            releaseTrack=release_track,
            waivers=waivers,
        )

    def submission_rejected(
        self,
        *,
        client: str,
        reason: str,
        status: int,
        target: str | None = None,
        fields: tuple[str, ...] = (),
    ) -> None:
        """A submission that never became a scan, and why."""
        names = [_clean_field(name) for name in sorted(fields)[:MAX_FIELD_NAMES]]
        self._emit(
            EVENT_SUBMISSION_REJECTED,
            client=self._client(client),
            reason=reason,
            status=status,
            target=self._target(target),
            fields=names or None,
        )

    def rate_limited(
        self,
        *,
        client: str,
        scope: str,
        retry_after: int,
        target: str | None = None,
    ) -> None:
        """A limit that actually triggered, and the cooldown it imposed."""
        self._emit(
            EVENT_RATE_LIMITED,
            client=self._client(client),
            scope=scope,
            retryAfter=retry_after,
            target=self._target(target),
        )

    def data_purged(
        self,
        *,
        client: str,
        target: str,
        scans: int,
        remaining: int,
        receipt: str,
    ) -> None:
        """
        An erasure request that was carried out.

        This one record is worth keeping even in a deployment that logs
        nothing else about targets: an erasure the controller cannot show it
        performed is an erasure that will be asked about twice. It follows the
        same rule as every other record here - the target is a fingerprint
        unless the operator asked for hostnames in the clear - and the receipt
        identifier ties it to the document the data subject was handed.
        """
        self._emit(
            EVENT_DATA_PURGED,
            client=self._client(client),
            target=self._target(target),
            scans=scans,
            remaining=remaining,
            receipt=receipt,
        )
