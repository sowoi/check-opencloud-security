"""
The exports: one scan, four files.

A result a person can read on the dashboard is a result somebody else wants in
a ticket, a spreadsheet or a code-scanning tool, so this module renders the
same scan as CSV, SARIF and PDF. All three start from
:func:`webapp.catalog.summarise`, which is the regrouping the dashboard
already uses, so an export can never disagree with the page it was downloaded
from - and no export decides anything, because judging is the plugin's layer,
not this one's.

The PDF is written here, by hand, rather than by a reporting library. This
service ships nothing to the browser it did not write, and the same rule is
worth applying to a file it hands somebody: a few hundred lines of PDF
primitives are cheaper to audit than a rendering engine, and the web image
stays small enough to be worth reading.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from html import escape
from typing import Any

from opencloud_local_scan import __version__, describe_hardening
from opencloud_local_scan.provenance import provenance_of

from .catalog import rating_label, summarise

PROJECT_URL = "https://github.com/sowoi/check-opencloud-security"

EXPORT_FORMATS = (
    "json",
    "csv",
    "sarif",
    "pdf",
    "html",
    "remediation-md",
    "remediation-html",
)

MEDIA_TYPES = {
    "json": "application/json",
    "csv": "text/csv; charset=utf-8",
    "sarif": "application/sarif+json",
    "pdf": "application/pdf",
    "html": "text/html; charset=utf-8",
    "remediation-md": "text/markdown; charset=utf-8",
    "remediation-html": "text/html; charset=utf-8",
}

FILE_SUFFIXES = {
    "json": "json",
    "csv": "csv",
    "sarif": "sarif.json",
    "pdf": "pdf",
    "html": "html",
    "remediation-md": "remediation.md",
    "remediation-html": "remediation.html",
}

# A spreadsheet treats a cell starting with one of these as a formula, and
# `=cmd|' /C calc'!A0` in one is code execution on the machine of whoever
# opens the file. Half of what goes into a report is a string the *scanned*
# instance chose - its product name, a `WWW-Authenticate` challenge - so the
# hostile case here is a target that poisons the report of anybody who scans
# it, or who is handed the download link afterwards.
FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")

# Nothing a scanner reports needs more than this, and a product name is an
# unbounded string from somebody else's server.
MAX_CELL_LENGTH = 300


def _cell(value: object) -> str:
    """
    One CSV cell, neutralised.

    Quoting is not enough: `csv` escapes the quotes inside a value but leaves
    a leading `=` exactly where the spreadsheet will act on it. Prefixing an
    apostrophe is what actually disarms it, and it is what a reader sees as
    the literal text they expected.
    """
    text = "" if value is None else str(value)
    # A newline inside a quoted cell is legal CSV but splits the row for
    # anything reading the file line by line, so it goes too.
    text = text.replace("\r", " ").replace("\n", " ")
    if len(text) > MAX_CELL_LENGTH:
        text = f"{text[:MAX_CELL_LENGTH - 1]}…"
    if text.startswith(FORMULA_LEADS):
        text = f"'{text}"
    return text


def _write(writer: Any, *values: object) -> None:
    """Write one row with every cell neutralised, so no call site can forget."""
    writer.writerow([_cell(value) for value in values])

# SARIF has three levels that matter here. Anything the scanner rates below a
# warning is still worth reporting, so it arrives as a note rather than being
# dropped.
SARIF_LEVELS = {
    "critical": "error",
    "high": "error",
    "medium": "warning",
    "low": "note",
    "info": "note",
}

# The numeric score and the three-value scale GitHub code scanning sorts and
# filters alerts on. They are the dashboard's conventions rather than SARIF's,
# so they travel in `properties`: a reader that does not know them is
# unaffected. The plugin's own SARIF export uses the same two tables - see
# ADR 0026 on why the two renderers mirror each other rather than share code.
SARIF_SECURITY_SEVERITY = {
    "critical": "9.5",
    "high": "7.5",
    "medium": "5.0",
    "low": "3.0",
    "info": "1.0",
    "unknown": "5.0",
}
SARIF_PROBLEM_SEVERITY = {
    "error": "error",
    "warning": "warning",
    "note": "recommendation",
}


def _sarif_fingerprint(target: str, rule_id: str) -> str:
    """
    A stable identity for one finding on one instance.

    A code-scanning dashboard uses this to recognise the same finding across
    uploads, so a header that has been missing for a month stays one alert
    with a history. Only the target and the rule go in: the detail text
    carries measured values that change while the finding does not.
    """
    return hashlib.sha256(f"{target}\n{rule_id}".encode()).hexdigest()[:32]


def _sarif_ranges(advisory: Mapping[str, Any]) -> list[dict[str, str]]:
    """The release windows an advisory covers, as strings a dashboard can show."""
    ranges = []
    for item in advisory.get("affectedRanges") or []:
        if not isinstance(item, Mapping):
            continue
        introduced = str(item.get("introduced") or "")
        fixed = str(item.get("fixed") or "")
        ranges.append(
            {
                "introduced": introduced,
                "fixed": fixed,
                "range": (
                    f">= {introduced}, < {fixed}"
                    if introduced and fixed
                    else f"< {fixed}"
                    if fixed
                    else f">= {introduced}"
                    if introduced
                    else ""
                ),
            }
        )
    return ranges


def export_filename(identifier: str, fmt: str) -> str:
    """The download name for one export, built from the uuid and nothing else."""
    return f"scan-{identifier}.{FILE_SUFFIXES.get(fmt, 'txt')}"


def _scanned_at(result: dict[str, Any]) -> str:
    scanned = result.get("scannedAt")
    if isinstance(scanned, dict):
        return str(scanned.get("date") or scanned.get("iso") or "")
    return str(scanned or "")


def _advisory_rows(summary: dict[str, Any]) -> list[tuple[str, str, str]]:
    rows = []
    for advisory in summary.get("vulnerabilities") or []:
        if not isinstance(advisory, dict):
            continue
        rows.append(
            (
                str(advisory.get("id") or advisory.get("cve") or "advisory"),
                str(advisory.get("severity") or "unrated"),
                str(
                    advisory.get("summary")
                    or advisory.get("description")
                    or "No summary published."
                ),
            )
        )
    return rows


def _tls_lines(summary: Mapping[str, Any]) -> list[tuple[str, str]]:
    """
    The transport measurement as label/value pairs, for the flat formats.

    Every export shows the TLS *findings* already, through the failed checks.
    These are the numbers behind them - the negotiated version, the chain, the
    dates - which is what somebody reading the report a month later needs in
    order to tell whether anything actually changed.
    """
    tls = summary.get("tls") or {}
    if not tls.get("reachable"):
        return []
    certificate = tls.get("certificate") or {}
    protocol = str(tls.get("protocol") or "unknown")
    cipher = str(tls.get("cipher") or "")
    lines = [("TLS", f"{protocol}{', ' + cipher if cipher else ''}")]

    accepted = tls.get("deprecatedProtocolsAccepted") or []
    probed = tls.get("deprecatedProtocolsProbed") or []
    if probed:
        lines.append(
            (
                "Deprecated versions",
                "still accepted: " + ", ".join(accepted)
                if accepted
                else "refused: " + ", ".join(probed),
            )
        )

    trusted = tls.get("trusted")
    chain = "trusted" if trusted else ("not established" if trusted is None else "not trusted")
    if tls.get("chainComplete") is False:
        chain += ", no path to a public root"
    lines.append(("Certificate chain", chain))

    if certificate:
        days = certificate.get("daysRemaining")
        expiry = str(certificate.get("notAfter") or "unknown")
        if isinstance(days, int):
            expiry += (
                f" (expired {abs(days)} day(s) ago)"
                if days < 0
                else f" ({days} day(s) left)"
            )
        lines.append(("Certificate", f"{certificate.get('subject') or 'unnamed'}"))
        lines.append(("Issued by", str(certificate.get("issuer") or "unknown")))
        lines.append(("Expires", expiry))
    if tls.get("ocspStapled") is not None:
        lines.append(
            ("OCSP stapling", "stapled" if tls.get("ocspStapled") else "not stapled")
        )
    return lines


def csv_report(result: dict[str, Any]) -> str:
    """
    The scan as a spreadsheet.

    One header block, then one row per finding with a section column, so the
    file survives being sorted or filtered without losing what a row was
    about.
    """
    summary = summarise(result)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")

    _write(writer, "check-opencloud-security", __version__)
    _write(writer, "Instance", summary.get("domain") or "unknown")
    _write(writer, "Product", summary.get("product") or "unknown")
    _write(writer, "Version", summary.get("version") or "unknown")
    _write(writer, "Release track", summary.get("releaseType") or "unknown")
    _write(writer, "End of life", "yes" if summary.get("eol") else "no")
    # Written as a fact of its own rather than left to the fix steps, because
    # this file is also read back: `webapp.imports` compares a pending update
    # like any other finding, and a row that is simply absent cannot be told
    # apart from one that said "none". See ADR 0057.
    updates = summary.get("updates") or {}
    _write(
        writer,
        "Update available",
        str(updates.get("availableVersion") or "unknown")
        if updates.get("available")
        else "no",
    )
    # Written for the same reason, and it is the one finding the findings
    # table below cannot carry: "HTTPS is not enforced" is measured in
    # `setup.https`, not in the hardening block the rows are drawn from.
    https = summary.get("https") or {}
    _write(writer, "HTTPS enforced", "no" if https.get("enforced") is False else "yes")
    _write(
        writer, "Rating", f"{summary.get('rating')}", rating_label(summary.get("rating"))
    )
    _write(writer, "Scanned at", _scanned_at(result))
    for label, value in _tls_lines(summary):
        _write(writer, label, value)
    writer.writerow([])

    plan = summary.get("remediation") or {}
    if plan.get("summary"):
        _write(writer, "Remediation", plan["summary"])
        writer.writerow([])

    _write(writer, "Section", "ID", "Severity", "Detail", "Remediation")
    for step in plan.get("steps") or []:
        # The order is the whole value of the plan, so it is the first thing
        # in the row rather than something a reader has to reconstruct.
        _write(
            writer,
            f"fix step {step.get('order')}",
            step.get("id") or "",
            step.get("severity") or "",
            f"{step.get('title') or ''} (then {step.get('label')}, "
            f"{step.get('ratingAfter')}/5)",
            step.get("action") or "",
        )
    for identifier, severity, detail in _advisory_rows(summary):
        _write(writer, "advisory", identifier, severity, detail, "")
    for issue in summary.get("issues") or []:
        _write(
            writer,
            "failed check",
            issue.get("id") or "",
            issue.get("severity") or "",
            issue.get("detail") or issue.get("explanation") or "",
            issue.get("remediation") or "",
        )
    for item in summary.get("missingHardenings") or []:
        _write(
            writer,
            "missing hardening",
            item.get("id") or "",
            "hardening",
            item.get("title") or "",
            item.get("remediation") or "",
        )
    for item in summary.get("missingHeaders") or []:
        _write(
            writer,
            "missing header",
            item.get("id") or "",
            "header",
            item.get("title") or "",
            item.get("remediation") or "",
        )
    for item in summary.get("waived") or []:
        _write(
            writer,
            "waived",
            item.get("id") or "",
            item.get("severity") or "",
            item.get("detail") or "",
            "",
        )
    # Kept in the file for the same reason they are kept on the page: an
    # operator reading a report should not go looking for a fix that does not
    # exist.
    for name in summary.get("unfixable") or []:
        _write(writer, "not actionable", name, "", "OpenCloud hardcodes this flag", "")

    return output.getvalue()


def sarif_report(result: dict[str, Any]) -> dict[str, Any]:
    """
    The scan as SARIF 2.1.0, for a code-scanning dashboard.

    Every finding carries a rule with the catalogue's own explanation, because
    a SARIF result without a rule description is an identifier somebody has to
    look up somewhere else.
    """
    summary = summarise(result)
    target = summary.get("domain") or "the scanned instance"
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []

    def add(
        rule_id: str,
        level: str,
        text: str,
        help_text: str,
        uri: str | None,
        *,
        severity: str = "",
        category: str = "",
        kind: str = "",
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        tags = ["security", f"severity/{severity or 'unknown'}", f"kind/{kind or 'finding'}"]
        if category:
            tags.append(f"category/{category}")
        if rule_id not in rules:
            properties: dict[str, Any] = {
                "tags": tags,
                "security-severity": SARIF_SECURITY_SEVERITY.get(severity.lower(), "3.0"),
                "problem.severity": SARIF_PROBLEM_SEVERITY.get(level, "warning"),
                "severity": severity,
            }
            if category:
                properties["category"] = category
            properties.update(extra or {})
            rule: dict[str, Any] = {
                "id": rule_id,
                "name": rule_id,
                "shortDescription": {"text": text[:120]},
                "fullDescription": {"text": text},
                "defaultConfiguration": {"level": level},
                "properties": properties,
            }
            if help_text:
                rule["help"] = {
                    "text": help_text,
                    "markdown": (
                        f"{help_text}\n\n[Documentation]({uri})" if uri else help_text
                    ),
                }
            if uri:
                rule["helpUri"] = uri
            rules[rule_id] = rule
        result_properties: dict[str, Any] = {
            "severity": severity,
            "category": category,
            "kind": kind,
        }
        if help_text:
            result_properties["remediation"] = help_text
        if uri:
            result_properties["reference"] = uri
        result_properties.update(extra or {})
        results.append(
            {
                "ruleId": rule_id,
                "kind": "fail",
                "level": level,
                "message": {"text": text},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": str(target)}
                        }
                    }
                ],
                "partialFingerprints": {
                    "checkOpenCloudSecurity/v1": _sarif_fingerprint(str(target), rule_id)
                },
                "properties": result_properties,
            }
        )

    advisories = {
        str(entry.get("id") or entry.get("cve") or "advisory"): entry
        for entry in summary.get("vulnerabilities") or []
        if isinstance(entry, Mapping)
    }
    for identifier, severity, detail in _advisory_rows(summary):
        advisory = advisories.get(identifier, {})
        ranges = _sarif_ranges(advisory)
        extra: dict[str, Any] = {}
        if ranges:
            extra["affectedRanges"] = ranges
        if advisory.get("fixedIn"):
            extra["fixedIn"] = str(advisory["fixedIn"])
        add(
            identifier,
            SARIF_LEVELS.get(severity.lower(), "warning"),
            detail,
            (
                f"Upgrade to {advisory['fixedIn']}."
                if advisory.get("fixedIn")
                else ""
            ),
            str(advisory.get("url") or "") or None,
            severity=severity,
            category="lifecycle",
            kind="vulnerability",
            extra=extra,
        )

    for issue in summary.get("issues") or []:
        identifier = str(issue.get("id"))
        add(
            identifier,
            SARIF_LEVELS.get(str(issue.get("severity")).lower(), "warning"),
            str(issue.get("detail") or issue.get("explanation") or identifier),
            str(issue.get("remediation") or ""),
            str(issue.get("reference") or "") or None,
            severity=str(issue.get("severity") or ""),
            category=str(issue.get("category") or describe_hardening(identifier).category),
            kind="hardening",
        )

    for item in (summary.get("missingHardenings") or []) + (
        summary.get("missingHeaders") or []
    ):
        identifier = str(item.get("id"))
        add(
            identifier,
            "note",
            str(item.get("title") or identifier),
            str(item.get("remediation") or describe_hardening(identifier).remediation),
            str(item.get("reference") or "") or None,
            severity=str(item.get("severity") or "low"),
            category=str(item.get("category") or describe_hardening(identifier).category),
            kind="hardening",
        )

    return {
        "version": "2.1.0",
        "$schema": (
            "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/"
            "sarif-2.1/schema/sarif-schema-2.1.0.json"
        ),
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "check-opencloud-security",
                        # The version has one source, and a report that claims
                        # another is a report nobody can reproduce.
                        "version": __version__,
                        "informationUri": PROJECT_URL,
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
                "properties": {
                    "rating": summary.get("rating"),
                    "ratingLabel": summary.get("label"),
                    "endOfLife": bool(summary.get("eol")),
                    # The ordered fix list, so a dashboard consuming SARIF can
                    # say what to do first rather than only what is wrong.
                    "remediation": summary.get("remediation") or {},
                    # The transport measurement, unjudged, for a dashboard
                    # that wants to trend certificate expiry rather than only
                    # alert on it.
                    "tls": summary.get("tls") or {},
                },
            }
        ],
    }


# --------------------------------------------------------------------------
# The PDF. Nothing below needs a dependency: a PDF is a handful of objects, a
# cross-reference table and a byte offset per object.
# --------------------------------------------------------------------------

PAGE_WIDTH = 595  # A4 at 72 dpi, rounded to whole points.
PAGE_HEIGHT = 842
MARGIN = 56
LINE_HEIGHT = 14
BODY_SIZE = 10
HEADING_SIZE = 13
TITLE_SIZE = 18
# Helvetica at 10pt averages a little under 5pt per character. Wrapping on a
# character count rather than a font metric keeps this file free of a metrics
# table, at the cost of a ragged right edge nobody minds in a report.
BODY_COLUMNS = 92


def _escape(text: str) -> str:
    """Escape one string for a PDF text object."""
    cleaned = "".join(char if char.isprintable() else " " for char in text)
    # Latin-1 is what the standard fonts encode; anything else becomes a
    # question mark rather than a broken file.
    cleaned = cleaned.encode("latin-1", "replace").decode("latin-1")
    return cleaned.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _wrap(text: str, width: int) -> list[str]:
    words = str(text).split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


class _Document:
    """A stream of laid-out lines, broken into pages as it fills up."""

    def __init__(self) -> None:
        self.pages: list[list[str]] = [[]]
        self.y = PAGE_HEIGHT - MARGIN

    def _room_for(self, height: int) -> None:
        if self.y - height < MARGIN:
            self.pages.append([])
            self.y = PAGE_HEIGHT - MARGIN

    def text(self, value: str, size: int = BODY_SIZE, bold: bool = False,
             indent: int = 0) -> None:
        """One line of text, already wrapped by the caller."""
        self._room_for(size + 4)
        font = "F2" if bold else "F1"
        self.pages[-1].append(
            f"BT /{font} {size} Tf {MARGIN + indent} {self.y} Td ({_escape(value)}) Tj ET"
        )
        self.y -= size + 4

    def paragraph(self, value: str, indent: int = 0, size: int = BODY_SIZE,
                  bold: bool = False) -> None:
        for line in _wrap(value, BODY_COLUMNS - indent // 5):
            self.text(line, size=size, bold=bold, indent=indent)

    def heading(self, value: str) -> None:
        self.gap(6)
        self.text(value, size=HEADING_SIZE, bold=True)
        self.rule()

    def rule(self) -> None:
        self._room_for(8)
        self.pages[-1].append(
            f"{MARGIN} {self.y + 6} m {PAGE_WIDTH - MARGIN} {self.y + 6} l S"
        )
        self.y -= 6

    def gap(self, height: int = LINE_HEIGHT) -> None:
        self._room_for(height)
        self.y -= height

    def render(self) -> bytes:
        """Assemble the objects, the page tree and the cross-reference table."""
        objects: list[bytes] = []

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        font_regular = add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            b"/Encoding /WinAnsiEncoding >>"
        )
        font_bold = add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
            b"/Encoding /WinAnsiEncoding >>"
        )
        pages_id = len(objects) + 1
        objects.append(b"")  # Reserved: the page tree needs its children first.

        page_ids: list[int] = []
        for content in self.pages:
            stream = "\n".join(content).encode("latin-1", "replace")
            stream_id = add(
                b"<< /Length "
                + str(len(stream)).encode("ascii")
                + b" >>\nstream\n"
                + stream
                + b"\nendstream"
            )
            page_ids.append(
                add(
                    f"<< /Type /Page /Parent {pages_id} 0 R "
                    f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                    f"/Resources << /Font << /F1 {font_regular} 0 R "
                    f"/F2 {font_bold} 0 R >> >> "
                    f"/Contents {stream_id} 0 R >>".encode("ascii")
                )
            )

        kids = " ".join(f"{identifier} 0 R" for identifier in page_ids)
        objects[pages_id - 1] = (
            f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode("ascii")
        )
        catalog_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii"))

        out = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for index, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += f"{index} 0 obj\n".encode("ascii") + body + b"\nendobj\n"

        start_xref = len(out)
        out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
        out += b"0000000000 65535 f \n"
        for offset in offsets[1:]:
            out += f"{offset:010d} 00000 n \n".encode("ascii")
        out += (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{start_xref}\n%%EOF\n"
        ).encode("ascii")
        return bytes(out)


def pdf_report(result: dict[str, Any], *, identifier: str | None = None) -> bytes:
    """The scan as a printable report, in the order the dashboard shows it."""
    summary = summarise(result)
    doc = _Document()

    doc.text("OpenCloud security scan", size=TITLE_SIZE, bold=True)
    doc.rule()
    doc.paragraph(f"Instance: {summary.get('domain') or 'unknown'}")
    doc.paragraph(
        f"Product: {summary.get('product') or 'unknown'} "
        f"{summary.get('version') or ''}".strip()
    )
    doc.paragraph(
        f"Rating: {summary.get('label')} ({summary.get('rating')} out of 5)"
        + (" - end of life" if summary.get("eol") else "")
    )
    doc.paragraph(f"Release track: {summary.get('releaseType') or 'unknown'}")
    scanned = _scanned_at(result)
    if scanned:
        doc.paragraph(f"Scanned at: {scanned}")
    doc.paragraph(f"Report generated: {datetime.now(UTC).isoformat(timespec='seconds')}")
    if identifier:
        doc.paragraph(f"Scan reference: {identifier}")
    doc.paragraph(f"Produced by check-opencloud-security {__version__} - {PROJECT_URL}")

    explanation = (summary.get("explanation") or {}).get("reason")
    if explanation:
        doc.gap(4)
        doc.paragraph(f"Why this grade: {explanation}")

    counts = summary.get("counts") or {}
    doc.heading("Summary")
    doc.paragraph(
        f"Critical {counts.get('critical', 0)}   "
        f"Warning {counts.get('warning', 0)}   "
        f"Info {counts.get('info', 0)}   "
        f"Advisories {counts.get('vulnerabilities', 0)}   "
        f"Passed {summary.get('passedCount', 0)}"
    )

    plan = summary.get("remediation") or {}
    if plan.get("steps"):
        doc.heading(_plan_heading(plan, "the top grade"))
        doc.paragraph(str(plan.get("summary") or ""))
        doc.gap(4)
        for step in plan["steps"]:
            grade = "then" if (step.get("ratingGain") or 0) > 0 else "still"
            doc.paragraph(
                f"{step.get('order')}. {step.get('id')} [{step.get('severity')}] "
                f"- {grade} {step.get('label')}",
                bold=True,
            )
            doc.paragraph(str(step.get("title") or ""), indent=14)
            if step.get("action"):
                doc.paragraph(f"Fix: {step['action']}", indent=14)
            doc.gap(4)

    tls_lines = _tls_lines(summary)
    if tls_lines:
        doc.heading("Transport security")
        for label, value in tls_lines:
            doc.paragraph(f"{label}: {value}")
        doc.gap(6)

    advisories = _advisory_rows(summary)
    if advisories:
        doc.heading("Known advisories for this version")
        for advisory_id, severity, detail in advisories:
            doc.paragraph(f"{advisory_id} [{severity}]", bold=True)
            doc.paragraph(detail, indent=14)
            doc.gap(4)

    doc.heading("Checks that failed")
    issues = summary.get("issues") or []
    if not issues:
        doc.paragraph("Every check this scanner runs passed on this instance.")
    for issue in issues:
        doc.paragraph(f"{issue.get('id')} [{issue.get('severity')}]", bold=True)
        if issue.get("detail"):
            doc.paragraph(str(issue["detail"]), indent=14)
        if issue.get("explanation"):
            doc.paragraph(str(issue["explanation"]), indent=14)
        if issue.get("remediation"):
            doc.paragraph(f"Fix: {issue['remediation']}", indent=14)
        doc.gap(4)

    hardenings = (summary.get("missingHardenings") or []) + (
        summary.get("missingHeaders") or []
    )
    if hardenings:
        doc.heading("Hardening worth adding")
        for item in hardenings:
            doc.paragraph(f"{item.get('id')}", bold=True)
            doc.paragraph(str(item.get("title") or ""), indent=14)
            if item.get("remediation"):
                doc.paragraph(f"Fix: {item['remediation']}", indent=14)
            doc.gap(4)

    waived = summary.get("waived") or []
    unfixable = summary.get("unfixable") or []
    if waived or unfixable:
        doc.heading("Reported, but not counted")
        if waived:
            doc.paragraph("Waived at your request, and still failing:")
            doc.paragraph(", ".join(str(item.get("id")) for item in waived), indent=14)
        if unfixable:
            doc.paragraph("Hardcoded by OpenCloud, so the same on every instance:")
            doc.paragraph(", ".join(str(name) for name in unfixable), indent=14)

    doc.heading("About this report")
    doc.paragraph(
        "Everything above was read without logging in. Audit logging and the "
        "correctness of an office or calendar integration cannot be established "
        "from outside and are not checked."
    )
    doc.paragraph(
        "This project is not affiliated with, endorsed by or supported by "
        "OpenCloud GmbH. \"OpenCloud\" and all related marks belong to their "
        "respective owners and are used only to identify the software checked."
    )
    return doc.render()


# --------------------------------------------------------------- HTML report

#: The whole of the report's presentation. Inline because the file has to be
#: readable from a disk with no network and no neighbouring assets: a
#: stylesheet link would be a blank page for whoever opens it next year. Only
#: fonts the machine already has are named, for the same reason - a font
#: service would be a request to somebody else's server every time the report
#: is opened.
_REPORT_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  margin: 0 auto; padding: 24px 16px 64px; max-width: 52rem;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue",
    Arial, "Noto Sans", sans-serif;
  line-height: 1.55; color: #1b1f24; background: #ffffff;
}
h1 { font-size: 1.6rem; margin: 0 0 4px; }
h2 { font-size: 1.2rem; margin: 32px 0 8px; padding-bottom: 4px;
     border-bottom: 1px solid #d8dee4; }
h3 { font-size: 1rem; margin: 20px 0 4px; }
p, li { font-size: 0.95rem; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
       font-size: 0.87em; background: #f2f4f7; padding: 1px 4px;
       border-radius: 3px; overflow-wrap: anywhere; }
a { color: #0b5cad; }
.lede { color: #57606a; margin: 0 0 20px; }
.grade { display: inline-block; font-size: 1.05rem; font-weight: 600;
         border: 2px solid currentColor; border-radius: 6px;
         padding: 2px 10px; margin-right: 8px; }
.grade-good { color: #1a7f37; }
.grade-fair { color: #9a6700; }
.grade-poor { color: #b42318; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 4px; }
th, td { text-align: left; vertical-align: top; padding: 6px 8px;
         border-bottom: 1px solid #d8dee4; font-size: 0.92rem; }
th { background: #f6f8fa; font-weight: 600; }
td.wrap { overflow-wrap: anywhere; }
.tag { display: inline-block; font-size: 0.78rem; font-weight: 600;
       border-radius: 10px; padding: 1px 8px; border: 1px solid currentColor; }
.tag-critical { color: #b42318; }
.tag-warning { color: #9a6700; }
.tag-info { color: #0b5cad; }
.note { border-left: 3px solid #d8dee4; padding: 4px 0 4px 12px;
        color: #57606a; margin: 12px 0; }
.muted { color: #57606a; }
footer { margin-top: 40px; padding-top: 12px; border-top: 1px solid #d8dee4;
         color: #57606a; font-size: 0.85rem; }
@media (prefers-color-scheme: dark) {
  body { color: #e6edf3; background: #0d1117; }
  h2, th, td, footer, .note { border-color: #30363d; }
  th { background: #161b22; }
  code { background: #161b22; }
  a { color: #6cb6ff; }
  .lede, .muted, .note, footer { color: #9198a1; }
  .grade-good { color: #3fb950; }
  .grade-fair { color: #d29922; }
  .grade-poor { color: #ff7b72; }
}
@media print {
  body { max-width: none; padding: 0; color: #000; background: #fff; }
  h2 { break-after: avoid; }
  tr, li, .note { break-inside: avoid; }
  a[href^="http"]::after { content: " (" attr(href) ")"; font-size: 0.8em;
                           color: #444; word-break: break-all; }
  footer { break-before: avoid; }
}
"""

#: The grades that get each tone. The letters come from the plugin's RATE_MAP
#: through `summarise`; this only decides which of three colours to use.
_GRADE_TONES = {"good": "grade-good", "fair": "grade-fair", "poor": "grade-poor"}


def _plan_heading(plan: Mapping[str, Any], fallback: str) -> str:
    """
    The remediation plan's heading, which only promises a grade it can reach.

    A plan whose steps lift nothing - the instance already holds the top
    grade, or a fixed value holds it down - would otherwise read "What gets
    you to A+" under an A+.
    """
    label = plan.get("achievableLabel") or fallback
    if plan.get("raisesRating", True):
        return f"What gets you to {label}"
    return f"Still worth fixing, the grade stays {label}"


def _h(value: object) -> str:
    """
    One value, safe to put anywhere in the document.

    Half of what a report carries is a string the *scanned* instance chose -
    its product name, a `WWW-Authenticate` challenge, a certificate subject -
    and the other half is text an operator typed into a waiver. Neither is
    this project's, so neither is markup.
    """
    return escape("" if value is None else str(value), quote=True)


def _link(url: object, text: object = None) -> str:
    """
    A documentation link, or plain text when the address is not one.

    Only `http(s)` survives: a `javascript:` or `data:` address in a report
    that somebody opens from their own disk is the one place it would run
    with nothing to stop it.
    """
    address = str(url or "")
    label = _h(text if text is not None else address)
    if not address.startswith(("https://", "http://")):
        return label
    return f'<a href="{_h(address)}" rel="noopener noreferrer">{label}</a>'


def _rows(rows: Sequence[Sequence[str]], headers: tuple[str, ...]) -> str:
    """One table, or nothing at all when there is nothing to put in it."""
    if not rows:
        return ""
    head = "".join(f"<th scope=\"col\">{_h(name)}</th>" for name in headers)
    body = "".join(
        "<tr>" + "".join(f'<td class="wrap">{cell}</td>' for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _severity_tag(tag: object) -> str:
    name = str(tag or "info")
    known = name if name in {"critical", "warning", "info"} else "info"
    return f'<span class="tag tag-{known}">{_h(name)}</span>'


def html_report(result: dict[str, Any], *, identifier: str | None = None) -> str:
    """
    The scan as one file that still reads after the link has expired.

    A result link is a capability with a time limit (ADR 0007), which is the
    right behaviour for a page a stranger can reach and the wrong behaviour
    for the evidence somebody needs at the end of the quarter. This is the
    same report as the dashboard, in a file that outlives the service's TTL
    because it no longer depends on the service at all.

    What makes that true is what is *not* here: no stylesheet to fetch, no
    font service, no script, no image, no form, no rescan control, no polling
    and no erasure token. Opening the file makes no request to anybody. The
    documentation links are the only addresses in it, and they are followed
    only if the reader chooses to.

    Nothing is decided here either. Every grade, severity, order and
    remediation step is what `summarise` already read out of the scanner's
    own document.
    """
    summary = summarise(result)
    generated = datetime.now(UTC).isoformat(timespec="seconds")
    tone = _GRADE_TONES.get(str(summary.get("tone")), "grade-fair")
    sections: list[str] = []

    # --- what was scanned, and what it scored
    facts: list[tuple[str, str]] = [
        ("Instance", f"<code>{_h(summary.get('domain') or 'unknown')}</code>"),
        (
            "Product",
            _h(f"{summary.get('product') or 'unknown'} {summary.get('version') or ''}".strip()),
        ),
        ("Release track", _h(summary.get("releaseType") or "unknown")),
    ]
    scanned = _scanned_at(result)
    facts.append(("Scanned at", _h(scanned) if scanned else '<span class="muted">not recorded</span>'))
    if identifier:
        facts.append(("Scan reference", f"<code>{_h(identifier)}</code>"))
    sections.append(
        f"<h2>The scan</h2>{_rows(facts, ('Field', 'Value'))}"
    )

    reason = (summary.get("explanation") or {}).get("reason")
    if reason:
        sections.append(f'<p class="note">Why this grade: {_h(reason)}</p>')

    counts = summary.get("counts") or {}
    sections.append(
        "<h2>Summary</h2>"
        + _rows(
            [
                ("Critical findings", _h(counts.get("critical", 0))),
                ("Warnings", _h(counts.get("warning", 0))),
                ("Informational", _h(counts.get("info", 0))),
                ("Known advisories", _h(counts.get("vulnerabilities", 0))),
                ("Checks passed", _h(summary.get("passedCount", 0))),
            ],
            ("Count of", "Number"),
        )
    )

    # --- what to do about it
    plan = summary.get("remediation") or {}
    if plan.get("steps"):
        steps = [
            (
                _severity_tag(step.get("tag")),
                _h(step.get("check") or step.get("id")),
                _h(step.get("action") or step.get("detail") or ""),
                _h(f"{step.get('ratingAfter')} ({step.get('label')})"),
            )
            for step in plan["steps"]
        ]
        sections.append(
            f"<h2>{_h(_plan_heading(plan, 'a better grade'))}</h2>"
            + _rows(steps, ("Severity", "Check", "What to change", "Grade after"))
        )

    # --- what is wrong
    issues = summary.get("issues") or []
    if issues:
        rows = [
            (
                _severity_tag(issue.get("tag")),
                _h(issue.get("id")),
                _h(issue.get("detail") or issue.get("explanation") or ""),
                _link(issue.get("reference"), "documentation") if issue.get("reference") else "",
            )
            for issue in issues
        ]
        sections.append(
            "<h2>Findings</h2>" + _rows(rows, ("Severity", "Check", "What was observed", "More"))
        )
    else:
        sections.append("<h2>Findings</h2><p>No check failed in this scan.</p>")

    advisories = _advisory_rows(summary)
    if advisories:
        sections.append(
            "<h2>Known advisories for this version</h2>"
            + _rows(
                [tuple(_h(cell) for cell in row) for row in advisories],
                ("Advisory", "Severity", "Fixed in"),
            )
        )

    # --- what was accepted, and by whom
    waived = summary.get("waived") or []
    raw_waivers = result.get("waivers")
    waivers: list[Any] = raw_waivers if isinstance(raw_waivers, list) else []
    if waived or waivers:
        parts = ["<h2>Accepted, and not counted in the grade</h2>"]
        if waived:
            parts.append(
                _rows(
                    [
                        (_h(item.get("id")), _h(item.get("detail") or ""))
                        for item in waived
                    ],
                    ("Check", "What was observed"),
                )
            )
        records = [
            (
                f"<code>{_h(record.get('pattern'))}</code>",
                _h(record.get("reason") or ""),
                _h(record.get("expiresAt") or "no expiry"),
                _h(record.get("state") or ""),
            )
            for record in waivers
            if isinstance(record, Mapping)
        ]
        if records:
            parts.append("<h3>The waivers that were configured</h3>")
            parts.append(_rows(records, ("Pattern", "Reason", "Expires", "State")))
        sections.append("".join(parts))

    # --- what the scan could not see
    coverage = summary.get("coverage") or {}
    if not coverage.get("available"):
        sections.append(
            "<h2>What this scan did not measure</h2>"
            '<p class="note">This report does not record its coverage, so it '
            "cannot say which checks ran. That is not the same as a scan with "
            "no gaps.</p>"
        )
    else:
        gaps = coverage.get("gaps") or []
        totals = coverage.get("summary") or {}
        body = (
            f"<p>{_h(coverage.get('measured'))} of "
            f"{_h((coverage.get('counts') or {}).get('total'))} checks reached a "
            "conclusion.</p>"
            f"<p class=\"note\">{_h(totals.get('evaluated', 0))} checks evaluated, "
            f"{_h(totals.get('skipped', 0))} skipped, "
            f"{_h(totals.get('indeterminate', 0))} indeterminate, "
            f"{_h(totals.get('networkLimited', 0))} network-limited.</p>"
        )
        if gaps:
            body += _rows(
                [
                    (
                        _h(gap.get("groupLabel")),
                        _h(gap.get("id")),
                        _h(f"{gap.get('reasonLabel')}. {gap.get('detail')}".strip()),
                    )
                    for gap in gaps
                ],
                ("Area", "Check", "Why it did not conclude"),
            )
        sections.append("<h2>What this scan did not measure</h2>" + body)

    # --- whether the deployment itself changed
    fingerprint = summary.get("fingerprint") or {}
    if not fingerprint.get("available"):
        sections.append(
            "<h2>Has this deployment changed?</h2>"
            '<p class="note">This report records no configuration fingerprint, '
            "so it cannot say whether the deployment changed since an earlier "
            "scan. That is not the same as one that stayed the same.</p>"
        )
    else:
        fingerprint_rows: list[tuple[str, str]] = [
            (
                _h(group.get("label")),
                _h(group.get("digest")) if group.get("measured") else "not measured",
            )
            for group in fingerprint.get("groups") or []
        ]
        sections.append(
            "<h2>Has this deployment changed?</h2>"
            "<p>Each digest below stands for how this instance is configured, "
            "never for what it is configured to. Compare them with an earlier "
            "report: a group whose digest differs was set up differently, even "
            "where the grade did not move.</p>"
            + _rows(fingerprint_rows, ("Configuration", "Digest"))
            + f'<p class="note">Across all groups: {_h(fingerprint.get("digest"))}.</p>'
        )

    # --- what it was judged against
    provenance = provenance_of(result)
    if provenance is None:
        sections.append(
            "<h2>What this scan was judged against</h2>"
            '<p class="note">This report predates the record of its own '
            "conditions, so the scanner version and the reference data it used "
            "are not available.</p>"
        )
    else:
        advisory_data = provenance.get("advisoryData") or {}
        schedule_data = provenance.get("scheduleData") or {}
        sections.append(
            "<h2>What this scan was judged against</h2>"
            + _rows(
                [
                    ("Scanner version", _h(provenance.get("scannerVersion"))),
                    ("Release track asked for", _h(provenance.get("releaseTrack"))),
                    (
                        "Advisory data",
                        _h(f"{advisory_data.get('count', 0)} record(s), digest ")
                        + f"<code>{_h(str(advisory_data.get('digest'))[:16])}</code>",
                    ),
                    (
                        "Release schedule",
                        _h(f"generated {schedule_data.get('updated') or 'unknown'}, digest ")
                        + f"<code>{_h(str(schedule_data.get('digest'))[:16])}</code>",
                    ),
                ],
                ("Field", "Value"),
            )
        )

    body = "".join(sections)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>OpenCloud security scan - {_h(summary.get('domain') or 'report')}</title>
<style>{_REPORT_CSS}</style>
</head>
<body>
<main>
<h1>OpenCloud security scan</h1>
<p class="lede">
  <span class="grade {tone}">{_h(summary.get('label'))}</span>
  {_h(summary.get('rating'))} out of 5{' - end of life' if summary.get('eol') else ''}
  for <code>{_h(summary.get('domain') or 'unknown')}</code>
</p>
{body}
<footer>
<p>Generated {_h(generated)} by check-opencloud-security {_h(__version__)}.</p>
<p>This file is a copy. It stays readable after the result link on the service
has expired or been erased, because it no longer depends on the service - and
for the same reason it will not update, and deleting the scan there does not
delete this. Opening it makes no network request; the documentation links are
followed only if you choose to.</p>
<p>{_link(PROJECT_URL)}</p>
</footer>
</main>
</body>
</html>
"""

