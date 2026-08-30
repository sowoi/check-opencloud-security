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
from opencloud_local_scan import (
    CATEGORIES,
    HARDENINGS,
    all_checks,
    describe_hardening,
    failed_extra_checks,
)
from opencloud_local_scan.hardening import is_actionable
from opencloud_local_scan.remediation import SEVERITY_RATING_CAP
from opencloud_local_scan.versions import RELEASE_TRACK_CHOICES, TRACK_AUTO

from .i18n import Translator

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

# Headers reported under setup.advisoryHeaders. They are explained in the
# catalogue like any other check, but they are not offered as waivers: nothing
# alerts on them, so there would be nothing to waive. See ADR 0028.
ADVISORY_HEADER_IDS: tuple[str, ...] = (
    "Permissions-Policy",
    "Cross-Origin-Opener-Policy",
    "Cross-Origin-Resource-Policy",
)

# Findings from the extra-check pass that an operator can legitimately accept.
# Deliberately narrow: 'exposed:*' and 'authentication:*' are per-path
# families whose members depend on the instance, and a public service offering
# to waive them by wildcard would be offering to hide them.
CHECK_IDS: tuple[str, ...] = (
    "tlsTrusted",
    "tlsProtocol",
    "tlsDeprecatedProtocol",
    "tlsCertificate",
    "tlsCertificateLifetime",
    "tlsCipherSuite",
    "tlsCertificatePolicy",
    "tlsAddressParity",
    "cookieSecure",
    "cookieHttpOnly",
    "cookieSameSite",
    "cookiePrefix",
    "tlsChain",
    "tlsOcspStapling",
    "tlsCertificateTransparency",
    "tlsEarlyData",
    "corsOriginRestricted",
    "traceMethodDisabled",
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


# The three headings the tick boxes are gathered under. The heading is this
# layer's word for a group and is translated; the title and the explanation
# inside it are the scanner's description of a check, quoted as measured.
_WAIVER_GROUPS: tuple[tuple[str, str], ...] = (
    ("hardening", "waivers.group.hardening"),
    ("headers", "waivers.group.headers"),
    ("checks", "waivers.group.checks"),
)


def waiver_options(translate: Translator | None = None) -> list[WaiverOption]:
    """
    The complete allow-list, in the order the landing page shows it.

    Flags OpenCloud hardcodes are left out: waiving a finding nobody can fix
    would suggest it could be fixed.
    """
    t = translate or Translator()
    groups = {name: t(key) for name, key in _WAIVER_GROUPS}
    options: list[WaiverOption] = []
    for name in HARDENINGS:
        if not is_actionable(name):
            continue
        entry = describe_hardening(name)
        options.append(
            WaiverOption(
                id=name,
                title=entry.title,
                meaning=entry.meaning,
                group=groups["hardening"],
            )
        )
    for name in HEADER_IDS:
        entry = describe_hardening(name)
        options.append(
            WaiverOption(
                id=name,
                title=entry.title,
                meaning=entry.meaning,
                group=groups["headers"],
            )
        )
    for name in CHECK_IDS:
        entry = describe_hardening(name)
        options.append(
            WaiverOption(
                id=name,
                title=entry.title,
                meaning=entry.meaning,
                group=groups["checks"],
            )
        )
    return options


def allowed_waivers() -> frozenset[str]:
    """Every identifier a request may ask to have waived."""
    return frozenset(option.id for option in waiver_options())


@dataclass(frozen=True)
class CatalogueCheck:
    """One check the scanner can run, as the catalogue page lists it."""

    id: str
    title: str
    meaning: str
    remediation: str
    reference: str
    actionable: bool


@dataclass(frozen=True)
class CatalogueCategory:
    """One category of checks, with a translated label for its heading."""

    id: str
    label: str
    checks: tuple[CatalogueCheck, ...]


def check_catalogue(translate: Translator | None = None) -> tuple[CatalogueCategory, ...]:
    """
    Every check and hardening flag this build knows how to explain, grouped.

    This is the reference the dashboard's per-finding category badges point
    back to: the same :attr:`~opencloud_local_scan.hardening.Hardening.category`
    a failed check carries, gathered here into one page so a visitor can see
    the whole set the scanner runs rather than only the ones that failed on
    their instance. ``describe_hardening`` is the single source for every
    sentence, so this page can never disagree with a result page about what a
    check means.
    """
    t = translate or Translator()
    entries = list(all_checks())
    entries.extend(describe_hardening(name) for name in (*HEADER_IDS, *ADVISORY_HEADER_IDS))

    grouped: dict[str, list[CatalogueCheck]] = {}
    for entry in entries:
        grouped.setdefault(entry.category, []).append(
            CatalogueCheck(
                id=entry.id,
                title=entry.title,
                meaning=entry.meaning,
                remediation=entry.remediation,
                reference=entry.reference,
                actionable=entry.actionable,
            )
        )

    return tuple(
        CatalogueCategory(
            id=category,
            label=t(f"category.{category}"),
            checks=tuple(sorted(grouped[category], key=lambda item: item.id)),
        )
        for category in CATEGORIES
        if category in grouped
    )


# Working the track out from the release the instance reports is right more
# often than any fixed guess, and it is the answer the schedule gives when
# nobody declares a track. A stranger's server is the case that matters here:
# assuming 'production' called a perfectly current rolling instance out of
# date, and assuming 'rolling' calls a supported production release end of
# life. Asking the schedule does neither.
DEFAULT_RELEASE_TRACK = TRACK_AUTO

# The tracks are OpenCloud's names and stay as they are; how each one is
# introduced on the form is this layer's sentence, and lives in the
# catalogues under `track.<id>.label` and `track.<id>.description`.
TRACK_KEYS: dict[str, str] = {
    TRACK_AUTO: "auto",
    "rolling": "rolling",
    "production": "production",
    "lts": "lts",
}


@dataclass(frozen=True)
class TrackOption:
    """One release track, as offered on the form."""

    id: str
    label: str
    description: str
    default: bool


def release_track_options(translate: Translator | None = None) -> tuple[TrackOption, ...]:
    """The tracks a visitor may pick, with the default one offered first."""
    t = translate or Translator()
    ordered = (
        DEFAULT_RELEASE_TRACK,
        *(track for track in RELEASE_TRACK_CHOICES if track != DEFAULT_RELEASE_TRACK),
    )
    return tuple(
        TrackOption(
            id=track,
            label=t(f"track.{TRACK_KEYS.get(track, track)}.label"),
            description=t(f"track.{TRACK_KEYS.get(track, track)}.description"),
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


# What each number on the scale actually says about an instance, and what
# clears it. The letters and the numbers are not restated here: they come from
# the plugin's RATE_MAP and the scanner's own severity caps, so a change to
# either shows up on the page that explains them rather than drifting away
# from it. The prose is this layer's, because explaining a grade to a visitor
# is presentation - the judgement was made before the page was rendered - and
# it therefore lives in the string catalogues, under `grade.<rating>.*`.
GRADE_RATINGS: tuple[int, ...] = (5, 4, 3, 2, 1, 0)


@dataclass(frozen=True)
class Grade:
    """One step of the scale, as the page that explains it needs it."""

    rating: int
    label: str
    tone: str
    headline: str
    meaning: str
    improve: str


def grade_scale(translate: Translator | None = None) -> tuple[Grade, ...]:
    """The whole scale, best first, built from the plugin's own map."""
    t = translate or Translator()
    return tuple(
        Grade(
            rating=rating,
            label=rating_label(rating),
            tone=rating_tone(rating),
            headline=t(f"grade.{rating}.headline"),
            meaning=t(f"grade.{rating}.meaning"),
            improve=t(f"grade.{rating}.improve"),
        )
        for rating in GRADE_RATINGS
    )


def severity_caps() -> tuple[tuple[str, int, str], ...]:
    """
    What a failed check can do to a grade, worst first.

    The ceilings are the scanner's, imported rather than repeated: a page
    promising that a critical finding caps the grade at D has to be wrong the
    moment the library says otherwise, and this way it cannot be.
    """
    order = ("critical", "high", "medium", "low")
    return tuple(
        (severity, SEVERITY_RATING_CAP[severity], rating_label(SEVERITY_RATING_CAP[severity]))
        for severity in order
        if severity in SEVERITY_RATING_CAP
    )


def summarise(
    result: Mapping[str, Any], translate: Translator | None = None
) -> dict[str, Any]:
    """
    Regroup a result document for the dashboard.

    Everything returned is a rearrangement of what the scanner reported. No
    threshold is applied here; the letters and tones are labels for a number
    the scanner already decided.

    ``translate`` only reaches the handful of labels this layer writes itself,
    and defaults to English. Every export and the JSON API leave it unset, so
    what a machine reads is the same document in every language.
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
            "category": describe_hardening(str(entry.get("id"))).category,
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
            "category": describe_hardening(name).category,
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
            "category": describe_hardening(name).category,
        }
        for name, passed in _flags(headers)
        if not passed
    ]

    passed_checks = [name for name, passed in _flags(hardenings) if passed]
    passed_checks += [name for name, passed in _flags(headers) if passed]
    passed_count = len(passed_checks)

    return {
        "rating": rating,
        "label": rating_label(rating),
        "tone": rating_tone(rating),
        "remediation": _remediation(result),
        "eol": bool(result.get("EOL")),
        "domain": result.get("domain"),
        "addresses": _addresses(result),
        "ipv6Enabled": bool(result.get("ipv6Enabled", True)),
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
        "passedChecks": passed_checks,
        "https": https,
        "tls": result.get("tls") or {},
        "tlsOverview": _tls_overview(result, translate),
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


def _addresses(result: Mapping[str, Any]) -> dict[str, list[str]]:
    """
    The resolved addresses, as strings the template can print unchanged.

    A document from an older scanner has no ``addresses`` block at all, and a
    name that resolves to one family has an empty list for the other; both
    end up as an empty list rather than a missing key, so the template asks
    one question instead of three.
    """
    reported = result.get("addresses")
    if not isinstance(reported, Mapping):
        return {"ipv4": [], "ipv6": []}
    return {
        family: [str(entry) for entry in (reported.get(family) or [])]
        for family in ("ipv4", "ipv6")
    }


def _tls_outcomes(result: Mapping[str, Any]) -> dict[str, bool]:
    """Whether each TLS check passed, as the scanner decided it."""
    outcomes: dict[str, bool] = {}
    for entry in result.get("extraChecks", []):
        if isinstance(entry, Mapping) and str(entry.get("id")).startswith("tls"):
            outcomes[str(entry.get("id"))] = bool(entry.get("passed", True))
    return outcomes


def _tls_overview(
    result: Mapping[str, Any], translate: Translator | None = None
) -> list[dict[str, Any]]:
    """
    The few transport facts that belong beside the grade rather than below it.

    A certificate that expires on Friday, a chain that only resolves in a
    browser that has already cached the intermediate, and a protocol version
    nobody should still be offering are all things somebody scanning their own
    instance came to find out. They are shown at the top so that reading the
    page is not a prerequisite for noticing them.

    Nothing is judged here. Each fact takes its tone from the pass or fail the
    scanner already recorded for the check behind it, so the colour beside a
    certificate is the scanner's verdict on that certificate and not a second
    threshold invented in this layer.
    """
    tls = result.get("tls") or {}
    if not isinstance(tls, Mapping) or not tls.get("reachable"):
        return []

    t = translate or Translator()
    outcomes = _tls_outcomes(result)
    certificate = tls.get("certificate") or {}
    if not isinstance(certificate, Mapping):
        certificate = {}
    facts: list[dict[str, Any]] = []

    protocol = tls.get("protocol")
    if protocol:
        accepted = tls.get("deprecatedProtocolsAccepted") or []
        detail = (
            t(
                "tls.fact.protocol.detail",
                list=", ".join(str(name) for name in accepted),
            )
            if accepted
            else ""
        )
        facts.append(
            {
                "id": "protocol",
                "label": t("tls.fact.protocol"),
                "value": str(protocol),
                "detail": detail,
                "tone": _tone(
                    outcomes.get("tlsProtocol", True)
                    and outcomes.get("tlsDeprecatedProtocol", True)
                ),
            }
        )

    days = certificate.get("daysRemaining")
    not_after = certificate.get("notAfter")
    if not_after:
        if isinstance(days, int):
            detail = (
                t("tls.fact.expiry.expired", days=abs(days))
                if days < 0
                else t("tls.fact.expiry.remaining", days=days)
            )
        else:
            detail = ""
        facts.append(
            {
                "id": "expiry",
                "label": t("tls.fact.expiry"),
                "value": str(not_after),
                "detail": detail,
                "tone": _tone(outcomes.get("tlsCertificate", True)),
            }
        )

    complete = tls.get("chainComplete")
    trusted = tls.get("trusted")
    if complete is not None or trusted is not None:
        if complete is False:
            value = t("tls.fact.chain.incomplete")
            detail = t("tls.fact.chain.incomplete.detail")
        elif trusted is False:
            value = t("tls.fact.chain.untrusted")
            detail = t("tls.fact.chain.untrusted.detail")
        elif trusted is None:
            value = t("tls.fact.chain.unknown")
            detail = t("tls.fact.chain.unknown.detail")
        else:
            value = t("tls.fact.chain.ok")
            detail = ""
        facts.append(
            {
                "id": "chain",
                "label": t("tls.fact.chain"),
                "value": value,
                "detail": detail,
                "tone": _tone(
                    outcomes.get("tlsChain", True) and outcomes.get("tlsTrusted", True)
                ),
            }
        )

    return facts


def _tone(passed: bool) -> str:
    """The dashboard tone for a check the scanner has already judged."""
    return "good" if passed else "bad"


def _remediation(result: Mapping[str, Any]) -> dict[str, Any]:
    """
    The scanner's remediation plan, with the letters this layer knows about.

    The order, the predicted ratings and the wording all come from the
    library, which worked them out while it was rating the instance. The only
    thing added here is the label for each number, because a letter is a
    judgement and judgements live in the plugin's RATE_MAP - the same map the
    grade on the page comes from.
    """
    plan = result.get("remediationPlan")
    if not isinstance(plan, Mapping):
        return {}
    steps = [
        {
            **step,
            "label": rating_label(step.get("ratingAfter")),
            "tag": SEVERITY_TAGS.get(str(step.get("severity")), "info"),
        }
        for step in plan.get("steps") or []
        if isinstance(step, Mapping)
    ]
    return {
        **plan,
        "steps": steps,
        "currentLabel": rating_label(plan.get("currentRating")),
        "achievableLabel": rating_label(plan.get("achievableRating")),
    }


def _flags(mapping: object) -> list[tuple[str, bool]]:
    """Flatten a hardening or header map into (name, passed) pairs."""
    if not isinstance(mapping, Mapping):
        return []
    return [(str(name), bool(value)) for name, value in mapping.items()]
