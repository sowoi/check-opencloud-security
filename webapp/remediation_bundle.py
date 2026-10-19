"""
The work to do, on its own, in the syntax the files that have to change use.

The other exports answer "how is this instance doing": they carry the grade,
what passed, the advisories, the transport measurement, the provenance. That
is the right shape for a ticket or a quarterly record and the wrong shape for
the afternoon somebody actually sits down to fix it, because the fixes are
spread through a document that is mostly not about them.

A bundle is the complement. It contains **only what is still open and can be
acted on** - each finding, the evidence the scanner recorded for it, and the
nginx, Caddy, Traefik, Compose and ``.env`` fragments that satisfy it - and
nothing else. No grade, no passed checks, no advisory list: those are in the
report next to it, and repeating them here would bury the one thing this file
is for.

Three properties are deliberate.

**It selects, it does not judge.** Which findings are open is
:func:`webapp.catalog.open_findings`, the same list the dashboard's fragment
picker uses - failed checks, missing hardenings, missing headers, with waived
and unfixable entries already dropped. This module decides nothing about
severity, order or acceptability; it only leaves out what was never open.

**Every fragment is rendered, not one.** The dashboard picks a flavour because
a reader is looking at one screen. A file handed to somebody else has no
picker, and the person who opens it may well be the one running Caddy when
the scan was read by the one running Compose, so all five are written out and
each says which findings it covers. What a flavour cannot express is named
under it rather than silently missing, which is the same promise
:class:`opencloud_local_scan.snippets.Fragment` makes.

**Untrusted text stays text.** Part of the evidence is a string the *scanned*
instance chose - a product name, a ``WWW-Authenticate`` challenge, a directory
index. In the HTML bundle that is escaped exactly as the report escapes it; in
the Markdown one it is escaped as well, because a detail containing
``[click](javascript:...)`` would otherwise become a link in whatever renders
the file. The catalogue's own explanations are not escaped: they are this
repository's text, and defending them against ourselves would only fill every
sentence with backslashes.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from opencloud_local_scan import __version__, describe_hardening
from opencloud_local_scan.snippets import (
    FLAVOURS,
    KIND_ENV,
    KIND_HEADER,
    flavours_for,
)
from opencloud_local_scan.snippets import fragment as configuration_fragment

from .catalog import open_findings, summarise
from .reports import (
    _REPORT_CSS,
    MAX_CELL_LENGTH,
    PROJECT_URL,
    _h,
    _link,
    _scanned_at,
    _severity_tag,
)

#: The severity tag `summarise` gives a failed check. A missing hardening or
#: header has no severity of its own in the report - it is a check that is not
#: set rather than a check that failed - so it inherits this.
_DEFAULT_TAG = "info"

#: Which report list an identifier came from, for the one-line "what this is"
#: under each heading. Nothing is decided here; it is the heading the
#: dashboard already prints the entry under.
_SOURCE_LABELS = {
    "issues": "failed check",
    "missingHardenings": "hardening not set",
    "missingHeaders": "response header absent",
}

#: Markdown characters that would turn a value into markup if a scanned
#: instance put one in a string we inline. Escaped rather than stripped: the
#: point is to show the operator what was actually observed.
#:
#: Only the inline ones are here. ``#``, ``-`` and the rest matter at the
#: start of a line, and nothing untrusted is ever written at the start of one
#: - every such value is inlined after a label or inside a sentence.
_MARKDOWN_SPECIALS = "\\`*_[]<>|"


def _flat(value: object) -> str:
    """One value as a single line, whole."""
    return " ".join(("" if value is None else str(value)).split())


def _text(value: object) -> str:
    """
    One value the *scanned instance* chose, as a bounded single line.

    A product name or a ``WWW-Authenticate`` challenge is somebody else's
    string and has no length anybody agreed to, so it is cut to the same
    bound the CSV export uses.
    """
    flat = _flat(value)
    if len(flat) > MAX_CELL_LENGTH:
        flat = flat[: MAX_CELL_LENGTH - 1] + "…"
    return flat


def _md(value: object) -> str:
    """
    One value the scanned instance chose, safe to inline in Markdown.

    Catalogue prose does not come through here. It is this repository's own
    text, written to be read, and escaping it would litter every sentence
    with backslashes to defend against an author who is us - and truncate
    the explanations, which are longer than any evidence string.
    """
    return "".join(
        "\\" + char if char in _MARKDOWN_SPECIALS else char
        for char in _text(value)
    )


def _fence(text: str) -> str:
    """
    A fenced code block whose fence the content cannot end early.

    Every fragment here is the catalogue's own text, so today nothing in it
    contains a backtick run. The file is handed to somebody else, though, and
    a code block that ends where the snippet does not is a configuration file
    somebody pastes half of.
    """
    longest = 0
    run = 0
    for char in text:
        run = run + 1 if char == "`" else 0
        longest = max(longest, run)
    fence = "`" * max(3, longest + 1)
    return f"{fence}\n{text}\n{fence}"


def _findings(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    """
    Every open, actionable finding, in the report's own order, described once.

    ``open_findings`` decides membership and order; this only gathers what is
    known about each identifier. The evidence comes from the failed-check
    entry where there is one - that is the only list carrying what the scanner
    actually observed - and the rest from the catalogue, so a hardening that
    is merely unset still arrives with its title, fix and reference.
    """
    by_id: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for key in ("issues", "missingHardenings", "missingHeaders"):
        for entry in summary.get(key) or []:
            if not isinstance(entry, Mapping):
                continue
            identifier = str(entry.get("id") or "")
            if identifier and identifier not in by_id:
                by_id[identifier] = (key, entry)

    findings = []
    for name in open_findings(summary):
        source, entry = by_id.get(name, ("issues", {}))
        described = describe_hardening(name)
        findings.append(
            {
                "id": name,
                "source": _SOURCE_LABELS.get(source, ""),
                "tag": str(entry.get("tag") or _DEFAULT_TAG),
                "severity": str(entry.get("severity") or ""),
                "category": str(entry.get("category") or described.category),
                "title": _flat(described.title) if described.title != name else "",
                "observed": _text(entry.get("detail")),
                "meaning": _flat(described.meaning),
                "fix": _flat(entry.get("remediation") or described.remediation),
                "setting": described.setting,
                "reference": str(entry.get("reference") or described.reference),
            }
        )
    return findings


def _fragments(names: tuple[str, ...]) -> list[dict[str, Any]]:
    """
    All five flavours rendered for these findings, empty ones dropped.

    A flavour with nothing to write is left out rather than printed as an
    empty code block: on an instance whose only findings are headers, the
    Compose fragment would otherwise be a heading promising a fix and a blank
    block delivering none.
    """
    rendered = []
    for flavour in FLAVOURS:
        fragment = configuration_fragment(names, flavour.id)
        if fragment.empty:
            continue
        other = KIND_HEADER if flavour.kind == KIND_ENV else KIND_ENV
        rendered.append(
            {
                "label": flavour.label,
                "filename": flavour.filename,
                "text": fragment.text,
                "covered": fragment.covered,
                "elsewhere": fragment.elsewhere,
                "elsewhere_in": ", ".join(flavours_for(other)),
            }
        )
    return rendered


def _undecided(names: tuple[str, ...]) -> tuple[str, ...]:
    """
    The findings no flavour can write, from whichever flavour reports them.

    ``undecided`` is the same set whatever flavour is asked - it is the
    catalogue's "the right value is a decision about this deployment" - so one
    is enough, and this is only here so the bundle does not have to assume
    which flavour survived the filter above.
    """
    return configuration_fragment(names, FLAVOURS[0].id).undecided


def _header(summary: Mapping[str, Any], result: Mapping[str, Any], identifier: str | None) -> list[tuple[str, str]]:
    """What was scanned, so the bundle identifies its own subject."""
    facts = [
        ("Instance", str(summary.get("domain") or "unknown")),
        (
            "Product",
            f"{summary.get('product') or 'unknown'} {summary.get('version') or ''}".strip(),
        ),
    ]
    scanned = _scanned_at(dict(result))
    if scanned:
        facts.append(("Scanned at", scanned))
    if identifier:
        facts.append(("Scan reference", identifier))
    return facts


_LEDE = (
    "Everything below is still open and can be acted on. Passed checks, "
    "waived findings, checks OpenCloud hardcodes, the grade and the advisory "
    "list are deliberately not here - they are in the full report."
)

_FRAGMENT_LEDE = (
    "The same fixes as configuration. Each fragment is complete for the "
    "findings it lists: paste it into the file named above it and change "
    "nothing. Environment assignments belong on the OpenCloud instance; "
    "response headers belong on whatever terminates TLS in front of it, so "
    "you will normally need one fragment from each group, not all five."
)


_GROUPS_LEDE = (
    "The same findings, grouped by the system the change is made in. Where "
    "one change resolves several findings, it is listed once with all of "
    "them; the grade beside it is what that change alone would give."
)


def _groups(summary: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The plan's groups, as the dashboard labelled them."""
    plan = summary.get("remediation") or {}
    return [group for group in plan.get("groups") or [] if isinstance(group, Mapping)]


def remediation_markdown(
    result: dict[str, Any], *, identifier: str | None = None
) -> str:
    """The bundle as Markdown, for a pull request, a runbook or a ticket."""
    summary = summarise(result)
    findings = _findings(summary)
    names = open_findings(summary)
    generated = datetime.now(UTC).isoformat(timespec="seconds")

    lines = [f"# OpenCloud remediation bundle - {_md(summary.get('domain') or 'report')}", ""]
    for label, value in _header(summary, result, identifier):
        lines.append(f"- **{label}:** {_md(value)}")
    lines += ["", _LEDE, ""]

    if not findings:
        lines += [
            "## Nothing to do",
            "",
            "No open, actionable finding was recorded for this instance.",
            "",
        ]
    else:
        lines += [f"## Findings ({len(findings)})", ""]
        for finding in findings:
            heading = f"`{_md(finding['id'])}`"
            if finding["title"]:
                heading += f" - {finding['title']}"
            lines.append(f"### {heading}")
            lines.append("")
            facts = [("Severity", finding["severity"] or finding["tag"])]
            if finding["category"]:
                facts.append(("Category", finding["category"]))
            if finding["source"]:
                facts.append(("Reported as", finding["source"]))
            if finding["setting"]:
                facts.append(("Setting", finding["setting"]))
            for label, value in facts:
                lines.append(f"- **{label}:** {_flat(value)}")
            if finding["observed"]:
                lines.append(f"- **Observed:** {_md(finding['observed'])}")
            lines += ["", finding["meaning"], ""]
            lines += [f"**Fix.** {finding['fix']}", ""]
            if finding["reference"]:
                lines += [f"Documentation: <{finding['reference']}>", ""]

        groups = _groups(summary)
        if groups:
            lines += ["## Changes by where they are made", "", _GROUPS_LEDE, ""]
            plan = summary.get("remediation") or {}
            if plan.get("groupSummary"):
                lines += [str(plan["groupSummary"]), ""]
            for group in groups:
                heading = (
                    f"### {group['title']} ({group['findings']} finding(s), "
                    f"{group['label']} with every change here)"
                )
                lines += [heading, ""]
                for change in group["changes"]:
                    resolves = ", ".join(f"`{_md(name)}`" for name in change["findings"])
                    lines.append(
                        f"- **{change['title']}** - resolves {resolves}; "
                        f"this change alone: {change['label']}. {change['action']}"
                    )
                lines.append("")

        fragments = _fragments(names)
        if fragments:
            lines += ["## Configuration", "", _FRAGMENT_LEDE, ""]
            for fragment in fragments:
                lines.append(f"### {fragment['label']} - `{fragment['filename']}`")
                lines += ["", f"Covers: {', '.join(_md(name) for name in fragment['covered'])}", ""]
                lines += [_fence(fragment["text"]), ""]
                if fragment["elsewhere"]:
                    lines += [
                        "This flavour cannot express "
                        + ", ".join(f"`{_md(name)}`" for name in fragment["elsewhere"])
                        + f". Those belong in: {fragment['elsewhere_in']}.",
                        "",
                    ]

        undecided = _undecided(names)
        if undecided:
            lines += [
                "## No mechanical fix",
                "",
                (
                    "The right value for these depends on this deployment, so "
                    "the Fix line above is the whole answer and there is "
                    "nothing to paste:"
                ),
                "",
            ]
            lines += [f"- `{_md(name)}`" for name in undecided]
            lines.append("")

    lines += [
        "---",
        "",
        (
            f"Generated {generated} by check-opencloud-security {__version__}. "
            f"This file is a copy and will not update. <{PROJECT_URL}>"
        ),
        "",
    ]
    return "\n".join(lines)


def remediation_html(
    result: dict[str, Any], *, identifier: str | None = None
) -> str:
    """
    The bundle as one self-contained page.

    Same content and same rules as the HTML report next to it: no stylesheet
    to fetch, no font service, no script, no image, no form. Opening the file
    makes no request to anybody.
    """
    summary = summarise(result)
    findings = _findings(summary)
    names = open_findings(summary)
    generated = datetime.now(UTC).isoformat(timespec="seconds")
    sections: list[str] = []

    facts = "".join(
        f"<tr><th scope=\"row\">{_h(label)}</th>"
        f'<td class="wrap">{_h(value)}</td></tr>'
        for label, value in _header(summary, result, identifier)
    )
    sections.append(f"<h2>The scan</h2><table><tbody>{facts}</tbody></table>")

    if not findings:
        sections.append(
            "<h2>Nothing to do</h2><p>No open, actionable finding was "
            "recorded for this instance.</p>"
        )
    else:
        sections.append(f"<h2>Findings ({len(findings)})</h2>")
        for finding in findings:
            heading = (
                f"{_severity_tag(finding['tag'])} <code>{_h(finding['id'])}</code>"
            )
            if finding["title"]:
                heading += f" - {_h(finding['title'])}"
            parts = [f"<h3>{heading}</h3>"]
            meta = [finding["category"], finding["source"]]
            shown = " &middot; ".join(_h(item) for item in meta if item)
            if shown:
                parts.append(f'<p class="muted">{shown}</p>')
            parts.append(f"<p>{_h(finding['meaning'])}</p>")
            if finding["observed"]:
                parts.append(
                    f'<p class="note">Observed: {_h(finding["observed"])}</p>'
                )
            fix = f"<p><strong>Fix.</strong> {_h(finding['fix'])}"
            if finding["setting"]:
                fix += f" Setting: <code>{_h(finding['setting'])}</code>."
            if finding["reference"]:
                fix += " " + _link(finding["reference"], "Documentation") + "."
            parts.append(fix + "</p>")
            sections.append("".join(parts))

        groups = _groups(summary)
        if groups:
            plan = summary.get("remediation") or {}
            block = [f"<h2>Changes by where they are made</h2><p>{_h(_GROUPS_LEDE)}</p>"]
            if plan.get("groupSummary"):
                block.append(f"<p>{_h(plan['groupSummary'])}</p>")
            for group in groups:
                block.append(
                    f"<h3>{_h(group['title'])}</h3>"
                    f'<p class="muted">{_h(group["findings"])} finding(s), '
                    f"{_h(group['label'])} with every change here</p><ul>"
                )
                for change in group["changes"]:
                    resolves = ", ".join(
                        f"<code>{_h(name)}</code>" for name in change["findings"]
                    )
                    block.append(
                        f"<li><strong>{_h(change['title'])}</strong> - resolves "
                        f"{resolves}; this change alone: {_h(change['label'])}. "
                        f"{_h(change['action'])}</li>"
                    )
                block.append("</ul>")
            sections.append("".join(block))

        fragments = _fragments(names)
        if fragments:
            sections.append(f"<h2>Configuration</h2><p>{_h(_FRAGMENT_LEDE)}</p>")
            for fragment in fragments:
                block = [
                    (
                        f"<h3>{_h(fragment['label'])} - "
                        f"<code>{_h(fragment['filename'])}</code></h3>"
                    ),
                    '<p class="muted">Covers: '
                    + ", ".join(f"<code>{_h(name)}</code>" for name in fragment["covered"])
                    + "</p>",
                    f"<pre><code>{_h(fragment['text'])}</code></pre>",
                ]
                if fragment["elsewhere"]:
                    block.append(
                        '<p class="note">This flavour cannot express '
                        + ", ".join(
                            f"<code>{_h(name)}</code>" for name in fragment["elsewhere"]
                        )
                        + f". Those belong in: {_h(fragment['elsewhere_in'])}.</p>"
                    )
                sections.append("".join(block))

        undecided = _undecided(names)
        if undecided:
            sections.append(
                "<h2>No mechanical fix</h2><p>The right value for these depends "
                "on this deployment, so the Fix line above is the whole answer "
                "and there is nothing to paste.</p><ul>"
                + "".join(f"<li><code>{_h(name)}</code></li>" for name in undecided)
                + "</ul>"
            )

    body = "".join(sections)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>OpenCloud remediation bundle - {_h(summary.get('domain') or 'report')}</title>
<style>{_REPORT_CSS}
pre {{ background: #f6f8fa; border: 1px solid #d8dee4; border-radius: 6px;
      padding: 10px 12px; overflow-x: auto; }}
pre code {{ background: none; padding: 0; font-size: 0.85rem; }}
@media (prefers-color-scheme: dark) {{
  pre {{ background: #161b22; border-color: #30363d; }}
}}
@media print {{ pre {{ break-inside: avoid; }} }}
</style>
</head>
<body>
<main>
<h1>OpenCloud remediation bundle</h1>
<p class="lede">{_h(_LEDE)}</p>
{body}
<footer>
<p>Generated {_h(generated)} by check-opencloud-security {_h(__version__)}.</p>
<p>This file is a copy. It stays readable after the result link on the service
has expired, and for the same reason it will not update. Opening it makes no
network request; the documentation links are followed only if you choose to.</p>
<p>{_link(PROJECT_URL)}</p>
</footer>
</main>
</body>
</html>
"""
