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
import io
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from opencloud_local_scan import __version__, describe_hardening

from .catalog import rating_label, summarise

PROJECT_URL = "https://github.com/sowoi/check-opencloud-security"

EXPORT_FORMATS = ("json", "csv", "sarif", "pdf")

MEDIA_TYPES = {
    "json": "application/json",
    "csv": "text/csv; charset=utf-8",
    "sarif": "application/sarif+json",
    "pdf": "application/pdf",
}

FILE_SUFFIXES = {"json": "json", "csv": "csv", "sarif": "sarif.json", "pdf": "pdf"}

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

    def add(rule_id: str, level: str, text: str, help_text: str, uri: str | None) -> None:
        if rule_id not in rules:
            rule: dict[str, Any] = {
                "id": rule_id,
                "name": rule_id,
                "shortDescription": {"text": text[:120]},
                "fullDescription": {"text": text},
                "defaultConfiguration": {"level": level},
            }
            if help_text:
                rule["help"] = {"text": help_text}
            if uri:
                rule["helpUri"] = uri
            rules[rule_id] = rule
        results.append(
            {
                "ruleId": rule_id,
                "level": level,
                "message": {"text": text},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": str(target)}
                        }
                    }
                ],
            }
        )

    for identifier, severity, detail in _advisory_rows(summary):
        add(identifier, SARIF_LEVELS.get(severity.lower(), "warning"), detail, "", None)

    for issue in summary.get("issues") or []:
        identifier = str(issue.get("id"))
        add(
            identifier,
            SARIF_LEVELS.get(str(issue.get("severity")).lower(), "warning"),
            str(issue.get("detail") or issue.get("explanation") or identifier),
            str(issue.get("remediation") or ""),
            str(issue.get("reference") or "") or None,
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
    doc.paragraph(f"Report generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
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
        doc.heading(f"What gets you to {plan.get('achievableLabel') or 'the top grade'}")
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
