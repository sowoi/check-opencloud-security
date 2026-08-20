"""
What it would take to reach the top rating, in the order worth doing it.

A report says what is wrong. It rarely says what to do first, and on an
instance with eleven findings that is the only question an operator actually
has. This module answers it without knowing anything new: the rating already
records which finding held it down and by how much, so replaying that
arithmetic over the result with one finding removed at a time gives an ordered
list of fixes and the rating each one would produce.

Two properties are deliberate.

**It measures, it does not judge.** The plan is expressed in the scanner's own
0-5 numbers. The letters (``A+``, ``F``) belong to the plugin's ``RATE_MAP``,
which is the layer that decides what a number is worth; putting them here
would move a judgement into the library.

**An upgrade comes first.** Fixing findings can only ever lift the rating back
to the *base* the version and the advisory database allowed - never above it.
An instance a release line behind is capped at 3 no matter how clean its
transport is, so a plan that lists eight header fixes and omits the update
would be advice that cannot work. When the base is below 5 the upgrade is step
one, and the findings follow.

The plan is derived, not stored: every number in it comes from
``ratingExplanation`` and ``updates`` in the document it was given.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .hardening import DOCS_UPDATE, describe

MIN_RATING = 0
MAX_RATING = 5

# What each severity allows a rating to be at most. The rating uses this to
# lower a rating; the planner uses it to work out what removing a finding
# would give back, and ``scanner`` re-exports it so the two cannot drift.
SEVERITY_RATING_CAP: dict[str, int] = {"critical": 2, "high": 3, "medium": 4, "low": 5}

# Which upgrade advice fits which starting point. The base rating is the
# scanner's own summary of the version evidence, so it is a better key than
# re-reading the advisories: 0 is out of support, 1 and 2 are advisories
# matching the installed version, 3 is a whole release line behind, 4 is a
# pending update on the same line.
_UPGRADE_TITLES: dict[int, str] = {
    0: "Move off the end-of-life release line",
    1: "Update away from a critical or high advisory",
    2: "Update away from the matching advisories",
    3: "Move up to the current release line",
    4: "Install the pending update",
}

_SEVERITY_ORDER: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _int(value: object, default: int) -> int:
    """Read a rating out of a document without trusting it to be a number."""
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return default


def _upgrade_target(result: Mapping[str, Any]) -> str:
    """
    Name the release to move to, using only what the scan already reported.

    Returns an empty string when the scan could not work one out. Inventing a
    version number here would be worse than saying nothing: an operator would
    go looking for a release that may not exist.
    """
    updates = result.get("updates")
    if isinstance(updates, Mapping):
        available = updates.get("availableVersion")
        if isinstance(available, str) and available:
            return available
    latest = result.get("latestVersionInBranch")
    if isinstance(latest, str) and latest:
        return latest
    return ""


def _upgrade_step(result: Mapping[str, Any], base_rating: int) -> dict[str, Any] | None:
    """Build the version step, or None when the version is already current."""
    if base_rating >= MAX_RATING:
        return None

    target = _upgrade_target(result)
    installed = str(result.get("version") or "")
    track = ""
    updates = result.get("updates")
    if isinstance(updates, Mapping) and isinstance(updates.get("track"), str):
        track = str(updates.get("track") or "")

    if target:
        where = f" on the {track} track" if track else ""
        action = (
            f"Update from {installed or 'the installed release'} to {target}"
            f"{where}, then scan again."
        )
    else:
        action = (
            "Update to a supported release. The scan could not name one, so "
            "check the OpenCloud release notes for the current release of the "
            "track this instance follows."
        )

    return {
        "id": "versionCurrent",
        "kind": "upgrade",
        "severity": "critical" if base_rating <= 1 else "high",
        "title": _UPGRADE_TITLES.get(base_rating, "Update the instance"),
        "action": action,
        "reference": DOCS_UPDATE,
        "detail": str(
            (result.get("ratingExplanation") or {}).get("base", {}).get("reason", "")
        ),
        "targetVersion": target,
    }


def _caps_from_findings(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Rebuild the caps the rating never got as far as recording."""
    entries: list[Mapping[str, Any]] = []
    for finding in result.get("extraChecks", []):
        if not isinstance(finding, Mapping):
            continue
        if finding.get("passed", True) or finding.get("ignored"):
            continue
        severity = str(finding.get("severity") or "")
        entries.append(
            {
                "check": str(finding.get("id")),
                "severity": severity,
                "cap": SEVERITY_RATING_CAP.get(severity, MAX_RATING),
                "detail": str(finding.get("detail") or ""),
            }
        )
    return entries


def _caps_of(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """
    The failed checks that held the rating down, strictest first.

    Read straight out of ``ratingExplanation``: those entries are exactly the
    findings the rating counted, which means the plan cannot drift away from
    the rating it is planning against. When extra checks are configured not to
    affect the rating there are no caps, and correctly there is nothing here
    to plan.
    """
    explanation = result.get("ratingExplanation")
    if not isinstance(explanation, Mapping):
        return []
    caps = explanation.get("caps")
    if not isinstance(caps, list):
        return []
    entries = [entry for entry in caps if isinstance(entry, Mapping)]
    if not entries and result.get("EOL"):
        # End of life short-circuits the rating, so no cap is ever recorded -
        # an F needs no further argument. The plan does need them: what the
        # instance would be worth after the upgrade depends on the findings
        # that are still open, and promising 5/5 while a critical one stands
        # would be the plan's one unforgivable lie.
        entries = _caps_from_findings(result)
    entries.sort(
        key=lambda entry: (
            _int(entry.get("cap"), MAX_RATING),
            _SEVERITY_ORDER.get(str(entry.get("severity")), 9),
            str(entry.get("check")),
        )
    )
    return [dict(entry) for entry in entries]


def _rating_with(ceiling: int, caps: list[dict[str, Any]]) -> int:
    """Replay the rating arithmetic over whatever findings are left."""
    rating = ceiling
    for entry in caps:
        rating = min(rating, _int(entry.get("cap"), MAX_RATING))
    return max(rating, MIN_RATING)


def _finding_step(
    entry: Mapping[str, Any], order: int, before: int, after: int
) -> dict[str, Any]:
    """Render one capping finding as a step, explained from the catalogue."""
    note = describe(str(entry.get("check")))
    return {
        "order": order,
        "id": str(entry.get("check")),
        "kind": "finding",
        "severity": str(entry.get("severity") or ""),
        "title": note.title,
        "action": note.remediation,
        "reference": note.reference,
        "setting": note.setting,
        "detail": str(entry.get("detail") or ""),
        "ratingBefore": before,
        "ratingAfter": after,
        "ratingGain": after - before,
    }


def _summarise(current: int, achievable: int, steps: list[dict[str, Any]]) -> str:
    """One sentence an operator - or an agent - can act on."""
    if not steps:
        return (
            f"Nothing to fix: the rating is {current}/5, the highest this scan "
            "can award."
        )
    if achievable <= current:
        count = len(steps)
        noun = "finding is" if count == 1 else "findings are"
        if current >= MAX_RATING:
            return (
                f"The rating is already {current}/5. {count} {noun} still worth "
                "fixing, but none of them can raise it any further."
            )
        return (
            f"{count} {noun} worth fixing, but none of them changes the rating "
            f"of {current}/5: something this plan cannot lift is holding it down."
        )

    first = next(step for step in steps if step["ratingAfter"] > current)
    count = steps.index(first) + 1
    lead = (
        "One fix raises"
        if count == 1
        else f"Fixing the first {count} steps raises"
    )
    sentence = f"{lead} the rating from {current}/5 to {first['ratingAfter']}/5"
    if achievable > first["ratingAfter"]:
        return f"{sentence}; all {len(steps)} reach {achievable}/5."
    return f"{sentence}, the most this plan can reach."


def _upgrade_position(
    base_rating: int, permanent: list[dict[str, Any]], fixable: list[dict[str, Any]]
) -> int:
    """
    Where in the fix list the update starts to be worth doing.

    Fixing findings can only ever lift the rating back to the base the
    version allows, and updating can only ever lift a ceiling that something
    else is not already sitting under. So the update belongs at the first
    point where it changes the answer - after the findings that cap below the
    base, before the ones that do not. Putting it first regardless would
    promise a gain it cannot deliver while a critical finding is open; putting
    it last would leave a plan whose every early step gains nothing.
    """
    for index in range(len(fixable) + 1):
        rest = permanent + fixable[index:]
        if _rating_with(MAX_RATING, rest) > _rating_with(base_rating, rest):
            return index
    return len(fixable)


def _add_upgrade(
    steps: list[dict[str, Any]],
    upgrade: dict[str, Any],
    before: int,
    rest: list[dict[str, Any]],
) -> int:
    """Append the update step and return the rating it produces."""
    after = _rating_with(MAX_RATING, rest)
    upgrade["order"] = len(steps) + 1
    upgrade["ratingBefore"] = before
    upgrade["ratingAfter"] = after
    upgrade["ratingGain"] = after - before
    steps.append(upgrade)
    return after


def plan(result: Mapping[str, Any]) -> dict[str, Any]:
    """
    Work out the ordered fix list for one scan result.

    The returned document is the ``remediationPlan`` key of a scan result:

    ``currentRating``
        Where the instance is now, 0-5.
    ``achievableRating``
        Where it would be with every step in the plan done. Never above 5,
        and never above what the version allows once the upgrade step - if
        there is one - has been taken.
    ``steps``
        In the order worth doing them, each with the rating that step
        produces. Steps that raise nothing on their own are still listed:
        four medium findings all cap at 4, so none of them lifts the rating
        until the last one is gone, and hiding the first three would make the
        plan impossible to finish.
    ``waived``
        Findings the operator asked to ignore. They are not in the plan
        because they do not hold the rating down, but a plan that silently
        dropped them would be hiding the reason a grade looks better than the
        findings suggest.
    ``blocked``
        Steps nobody can act on, when there are any. Empty for almost every
        instance; it exists so that an unfixable cap is stated rather than
        presented as a fix that does not work.
    ``summary``
        The same thing in one sentence.
    """
    explanation = result.get("ratingExplanation")
    explanation = explanation if isinstance(explanation, Mapping) else {}
    current = _int(result.get("rating"), _int(explanation.get("rating"), MIN_RATING))
    base = explanation.get("base")
    base_rating = _int(
        base.get("rating") if isinstance(base, Mapping) else None, current
    )

    caps = _caps_of(result)
    upgrade = _upgrade_step(result, base_rating)

    # A flag OpenCloud hardcodes is not a fix, and it never goes away, so it
    # stays in every simulated remainder below. Saying so is the whole point
    # of actionable=False.
    fixable = [entry for entry in caps if describe(str(entry.get("check"))).actionable]
    permanent = [entry for entry in caps if entry not in fixable]

    at = _upgrade_position(base_rating, permanent, fixable) if upgrade else len(fixable)

    steps: list[dict[str, Any]] = []
    running = current
    for index, entry in enumerate(fixable):
        if index == at and upgrade is not None:
            running = _add_upgrade(steps, upgrade, running, permanent + fixable[index:])
        # Until the upgrade is taken the version is still the ceiling, so a
        # finding fixed before it cannot promise more than the base allows.
        ceiling = MAX_RATING if index >= at else base_rating
        after = _rating_with(ceiling, permanent + fixable[index + 1 :])
        steps.append(_finding_step(entry, len(steps) + 1, running, after))
        running = after
    if at >= len(fixable) and upgrade is not None:
        running = _add_upgrade(steps, upgrade, running, permanent)

    blocked = [_finding_step(entry, 0, running, running) for entry in permanent]

    achievable = running
    waived = [
        str(entry.get("id"))
        for entry in result.get("extraChecks", [])
        if isinstance(entry, Mapping) and entry.get("ignored")
    ]

    return {
        "currentRating": current,
        "achievableRating": achievable,
        "steps": steps,
        "blocked": blocked,
        "waived": sorted(waived),
        "summary": _summarise(current, achievable, steps),
    }


__all__ = ["plan"]
