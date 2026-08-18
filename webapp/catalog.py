"""
The waivers a visitor is allowed to choose, and how a result is presented.

Two jobs, both about *not* duplicating what the scanner already knows:

- the waiver catalogue is an allow-list built from
  ``opencloud_local_scan.HARDENINGS`` and the header names the scanner
  reports, with every explanation coming from ``describe_hardening``. A
  visitor can only tick a box that is on this list, so no wildcard, no
  ``*`` and no unknown identifier ever reaches ``ScannerSettings``;
- the presentation helpers group a result document for the dashboard. They
  read the document, they never recompute a verdict - the rating, the caps
  and the pass/fail flags all come out of the scan exactly as the plugin
  sees them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from check_opencloud_security import RATE_MAP
from opencloud_local_scan import HARDENINGS, describe_hardening, failed_extra_checks
from opencloud_local_scan.hardening import is_actionable
from opencloud_local_scan.versions import RELEASE_TRACK_CHOICES, TRACK_AUTO

# Header names the scanner reports under setup.headers. They are waivable in
# the same namespace as the hardening flags.
HEADER_IDS: tuple[str, ...] = (
    "Strict-Transport-Security",
    "Content-Security-Policy",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "X-Permitted-Cross-Domain-Policies",
    "X-Robots-Tag",
    "X-XSS-Protection",
    "Referrer-Policy",
)

# Findings from the extra-check pass that an operator can legitimately accept.
# Deliberately narrow: 'exposed:*' and 'authentication:*' are per-path
# families whose members depend on the instance, and a public service offering
# to waive them by wildcard would be offering to hide them.
CHECK_IDS: tuple[str, ...] = (
    "tlsTrusted",
    "tlsProtocol",
    "tlsCertificate",
    "versionDisclosure:Server",
    "versionDisclosure:X-Powered-By",
    "webfingerVersionDisclosure",
    "directoryListing",
)

SEVERITY_TAGS: dict[str, str] = {
    "critical": "critical",
    "high": "critical",
    "medium": "warning",
    "low": "info",
}

SEVERITY_ORDER: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass(frozen=True)
class WaiverOption:
    """One tick box on the landing page."""

    id: str
    title: str
    meaning: str
    group: str


def waiver_options() -> list[WaiverOption]:
    """
    The complete allow-list, in the order the landing page shows it.

    Flags OpenCloud hardcodes are left out: waiving a finding nobody can fix
    would suggest it could be fixed.
    """
    options: list[WaiverOption] = []
    for name in HARDENINGS:
        if not is_actionable(name):
            continue
        entry = describe_hardening(name)
        options.append(
            WaiverOption(id=name, title=entry.title, meaning=entry.meaning, group="Hardening")
        )
    for name in HEADER_IDS:
        entry = describe_hardening(name)
        options.append(
            WaiverOption(id=name, title=entry.title, meaning=entry.meaning, group="Headers")
        )
    for name in CHECK_IDS:
        entry = describe_hardening(name)
        options.append(
            WaiverOption(id=name, title=entry.title, meaning=entry.meaning, group="Checks")
        )
    return options


def allowed_waivers() -> frozenset[str]:
    """Every identifier a request may ask to have waived."""
    return frozenset(option.id for option in waiver_options())


# Working the track out from the release the instance reports is right more
# often than any fixed guess, and it is the answer the schedule gives when
# nobody declares a track. A stranger's server is the case that matters here:
# assuming 'production' called a perfectly current rolling instance out of
# date, and assuming 'rolling' calls a supported production release end of
# life. Asking the schedule does neither.
DEFAULT_RELEASE_TRACK = TRACK_AUTO

TRACK_LABELS: dict[str, str] = {
    TRACK_AUTO: "Detect automatically",
    "rolling": "Rolling",
    "production": "Production",
    "lts": "LTS",
}

TRACK_DESCRIPTIONS: dict[str, str] = {
    TRACK_AUTO: "Work the track out from the release the instance reports.",
    "rolling": "A new release roughly every three weeks.",
    "production": "Supported for about six months. The usual choice.",
    "lts": "Supported for two years.",
}


@dataclass(frozen=True)
class TrackOption:
    """One release track, as offered on the form."""

    id: str
    label: str
    description: str
    default: bool


def release_track_options() -> tuple[TrackOption, ...]:
    """The tracks a visitor may pick, with the default one offered first."""
    ordered = (
        DEFAULT_RELEASE_TRACK,
        *(track for track in RELEASE_TRACK_CHOICES if track != DEFAULT_RELEASE_TRACK),
    )
    return tuple(
        TrackOption(
            id=track,
            label=TRACK_LABELS.get(track, track),
            description=TRACK_DESCRIPTIONS.get(track, ""),
            default=track == DEFAULT_RELEASE_TRACK,
        )
        for track in ordered
    )


def sanitize_release_track(value: object) -> str:
    """
    Reduce whatever arrived to one known track, or the default.

    Unlike a waiver this cannot be left unset: the track decides how long the
    instance's release is supported and which release it is told to upgrade
    to. The default detects it from the reported release rather than guessing
    a fixed one, because guessing 'rolling' for a production server would
    report an end of life that has not happened.
    """
    if not isinstance(value, str):
        return DEFAULT_RELEASE_TRACK
    candidate = value.strip().lower()
    return candidate if candidate in RELEASE_TRACK_CHOICES else DEFAULT_RELEASE_TRACK


def sanitize_waivers(values: object) -> tuple[str, ...]:
    """
    Reduce whatever arrived to identifiers from the allow-list.

    Unknown identifiers are dropped rather than rejected: a stale bookmark
    naming a check this build no longer has should still start a scan, and
    silently dropping it cannot widen what gets waived.
    """
    if values is None:
        return ()
    if isinstance(values, str):
        candidates = [values]
    elif isinstance(values, (list, tuple, set, frozenset)):
        candidates = [str(value) for value in values]
    else:
        return ()

    permitted = allowed_waivers()
    seen: list[str] = []
    for candidate in candidates:
        for part in candidate.replace(",", ";").split(";"):
            name = part.strip()
            if name in permitted and name not in seen:
                seen.append(name)
    return tuple(seen)


def rating_label(rating: object) -> str:
    """The letter grade for a 0-5 rating, using the plugin's own map."""
    try:
        return RATE_MAP[int(rating)]  # type: ignore[call-overload]
    except (TypeError, ValueError, KeyError):
        return "?"


def rating_tone(rating: object) -> str:
    """A coarse tone for the dashboard: good, fair or bad."""
    try:
        value = int(rating)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return "bad"
    if value >= 4:
        return "good"
    if value >= 3:
        return "fair"
    return "bad"


def summarise(result: Mapping[str, Any]) -> dict[str, Any]:
    """
    Regroup a result document for the dashboard.

    Everything returned is a rearrangement of what the scanner reported. No
    threshold is applied here; the letters and tones are labels for a number
    the scanner already decided.
    """
    rating = result.get("rating")
    checks = [entry for entry in result.get("extraChecks", []) if isinstance(entry, dict)]
    hardenings = result.get("hardenings") or {}
    headers = ((result.get("setup") or {}).get("headers")) or {}
    https = ((result.get("setup") or {}).get("https")) or {}

    failed = failed_extra_checks(result)
    issues = [
        {
            "id": entry.get("id"),
            "severity": entry.get("severity"),
            "tag": SEVERITY_TAGS.get(str(entry.get("severity")), "info"),
            "detail": entry.get("detail") or entry.get("message") or "",
            "explanation": describe_hardening(str(entry.get("id"))).meaning,
            "remediation": describe_hardening(str(entry.get("id"))).remediation,
            "reference": describe_hardening(str(entry.get("id"))).reference,
        }
        for entry in checks
        if str(entry.get("id")) in failed
    ]
    issues.sort(key=lambda item: SEVERITY_ORDER.get(str(item["severity"]), 9))

    waived = [
        {
            "id": entry.get("id"),
            "severity": entry.get("severity"),
            "detail": entry.get("detail") or "",
        }
        for entry in checks
        if entry.get("ignored")
    ]

    unfixable = [
        name
        for name, passed in _flags(hardenings)
        if not passed and not is_actionable(name)
    ]
    missing_hardenings = [
        {
            "id": name,
            "title": describe_hardening(name).title,
            "remediation": describe_hardening(name).remediation,
            "reference": describe_hardening(name).reference,
            "setting": describe_hardening(name).setting,
        }
        for name, passed in _flags(hardenings)
        if not passed and is_actionable(name)
    ]

    missing_headers = [
        {
            "id": name,
            "title": describe_hardening(name).title,
            "remediation": describe_hardening(name).remediation,
            "reference": describe_hardening(name).reference,
        }
        for name, passed in _flags(headers)
        if not passed
    ]

    passed_count = sum(1 for _, passed in _flags(hardenings) if passed)
    passed_count += sum(1 for _, passed in _flags(headers) if passed)

    return {
        "rating": rating,
        "label": rating_label(rating),
        "tone": rating_tone(rating),
        "eol": bool(result.get("EOL")),
        "domain": result.get("domain"),
        "product": result.get("product"),
        "version": result.get("version"),
        "releaseType": result.get("releaseType"),
        "lifecycle": result.get("lifecycle") or {},
        "updates": result.get("updates") or {},
        "explanation": result.get("ratingExplanation") or {},
        "vulnerabilities": result.get("vulnerabilities") or [],
        "issues": issues,
        "waived": waived,
        "unfixable": unfixable,
        "missingHardenings": missing_hardenings,
        "missingHeaders": missing_headers,
        "passedCount": passed_count,
        "https": https,
        "identityProvider": result.get("identityProvider") or {},
        "reverseProxy": result.get("reverseProxy") or {},
        "integrations": result.get("integrations") or {},
        "counts": {
            "critical": sum(1 for item in issues if item["tag"] == "critical"),
            "warning": sum(1 for item in issues if item["tag"] == "warning"),
            "info": sum(1 for item in issues if item["tag"] == "info"),
            "vulnerabilities": len(result.get("vulnerabilities") or []),
        },
    }


def _flags(mapping: object) -> list[tuple[str, bool]]:
    """Flatten a hardening or header map into (name, passed) pairs."""
    if not isinstance(mapping, Mapping):
        return []
    return [(str(name), bool(value)) for name, value in mapping.items()]


def csv_report(result: dict[str, Any]) -> str:
    """Generate a CSV report from a scan result."""
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(["Scan Report"])
    writer.writerow([])
    writer.writerow(["Instance", result.get("domain", "unknown")])
    writer.writerow(["Product", result.get("product", "unknown")])
    writer.writerow(["Version", result.get("version", "unknown")])
    writer.writerow(["Rating", str(result.get("rating", "unknown"))])
    writer.writerow(["Scanned At", result.get("scannedAt", {}).get("date", "unknown")])
    writer.writerow([])
    
    writer.writerow(["Vulnerabilities"])
    writer.writerow(["ID", "Severity", "Description"])
    for vuln in result.get("vulnerabilities") or []:
        writer.writerow([
            vuln.get("id", ""),
            vuln.get("severity", ""),
            vuln.get("description", ""),
        ])
    
    writer.writerow([])
    writer.writerow(["Missing Hardenings"])
    writer.writerow(["ID", "Description", "Actionable"])
    for hardening_id, passed in (result.get("hardenings") or {}).items():
        if not passed:
            writer.writerow([hardening_id, "", ""])
    
    return output.getvalue()


def sarif_report(result: dict[str, Any]) -> dict[str, Any]:
    """Generate a SARIF (Security Results Interchange Format) report."""
    runs = []
    results = []
    
    for vuln in result.get("vulnerabilities") or []:
        results.append({
            "ruleId": vuln.get("id", "unknown"),
            "message": {
                "text": vuln.get("description", ""),
            },
            "level": "error" if vuln.get("severity") == "critical" else "warning",
            "locations": [{
                "physicalLocation": {
                    "address": {
                        "relativeUrl": result.get("domain", ""),
                    }
                }
            }],
        })
    
    for hardening_id, passed in (result.get("hardenings") or {}).items():
        if not passed:
            results.append({
                "ruleId": hardening_id,
                "message": {
                    "text": f"Missing hardening: {hardening_id}",
                },
                "level": "warning",
                "locations": [{
                    "physicalLocation": {
                        "address": {
                            "relativeUrl": result.get("domain", ""),
                        }
                    }
                }],
            })
    
    runs.append({
        "tool": {
            "driver": {
                "name": "check-opencloud-security",
                "version": "1.5.5",
                "informationUri": "https://github.com/sowoi/check-opencloud-security",
            }
        },
        "results": results,
    })
    
    return {
        "version": "2.1.0",
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "runs": runs,
    }
