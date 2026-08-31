#!/usr/bin/env python3
"""Keep `### Security` changelog entries and GitHub Security Advisories in step.

Every bullet under a `### Security` heading in `CHANGELOG.md` is a claim that
something about this project's security changed. Some of those are fixed
vulnerabilities that shipped in a release, and every one of *those* owes the
people running that release an advisory. Others are hardening, or a defect
found and fixed inside one development cycle that no release ever carried.

The difference is not visible in the prose - the two read identically - so it
is recorded instead. `security/advisories/<slug>.yml` holds one record per
bullet: what was decided, and the evidence the decision rests on. `--check`
fails when a bullet has no record, which is what stops the question from being
skipped rather than answered.

Usage:

    python scripts/security_advisories.py --check       # CI: every bullet decided
    python scripts/security_advisories.py --list        # what is where
    python scripts/security_advisories.py --sync        # create missing drafts
    python scripts/security_advisories.py --publish SLUG  # publish one draft

Creating a draft is reversible and needs no ceremony. Publishing is neither:
a published advisory enters the GitHub Advisory Database and raises Dependabot
alerts for everyone on the affected range, so it stays a deliberate act naming
one record.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess  # nosec B404 - the GitHub CLI is invoked with a fixed argv
import sys
from typing import Any

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RECORD_DIR = REPO_ROOT / "security" / "advisories"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

#: The repository advisories are filed against.
REPO = "sowoi/check-opencloud-security"

#: Coverage is required from this release forward. Older sections predate the
#: record directory and pack several issues into one bullet; they were reviewed
#: once, by hand, and the records that came out of that review are kept. Raising
#: this line silently would drop that guarantee, so it is a constant with a name.
COVERAGE_BASELINE = (1, 14, 0)

#: What a record may say it is.
STATES = ("published", "draft", "declined")

#: Severity as the GitHub advisory API spells it.
SEVERITIES = ("low", "medium", "high", "critical")

#: The plugin and the scanner go to PyPI; the web application never does - it
#: ships as a release tarball, so an advisory about it must not raise Dependabot
#: alerts against the PyPI package. See AGENTS.md, "The web application".
PACKAGES = {
    "plugin": {"ecosystem": "pip", "name": "check-opencloud-security"},
    "web": {"ecosystem": "other", "name": "check-opencloud-security web application"},
}

REQUIRED_ALWAYS = ("slug", "state", "changelog_version", "changelog_entry", "shipped", "summary", "verified")
REQUIRED_ADVISORY = ("severity", "cwe_ids", "package", "introduced", "fixed", "description")


class RecordError(Exception):
    """A record is malformed, or contradicts the changelog it points at."""


def normalise(text: str) -> str:
    """Reduce a changelog phrase to something two spellings of it agree on."""
    text = re.sub(r"[*`]", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def parse_version(raw: str) -> tuple[int, ...]:
    return tuple(int(part) for part in raw.split("."))


def changelog_security_bullets() -> list[tuple[str, str]]:
    """Every `### Security` bullet of a released version, newest first.

    Returns (version, bullet text) pairs. `## [Unreleased]` is skipped: its
    entries have no release to be an advisory about yet, and the version they
    will land under is the user's decision.
    """
    bullets: list[tuple[str, str]] = []
    version: str | None = None
    in_security = False
    current: list[str] = []

    def flush() -> None:
        if current and version:
            bullets.append((version, " ".join(current).strip()))
        current.clear()

    for line in CHANGELOG.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"^## \[([^\]]+)\]", line)
        if heading:
            flush()
            raw = heading.group(1)
            version = None if raw.lower() == "unreleased" else raw
            in_security = False
            continue
        if line.startswith("###"):
            flush()
            in_security = line.strip().lower() == "### security"
            continue
        if not in_security or version is None:
            continue
        if line.startswith("- "):
            flush()
            current.append(line[2:])
        elif line.startswith("  ") and current:
            current.append(line.strip())
    flush()
    return bullets


def load_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(RECORD_DIR.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise RecordError(f"{path.name}: not a mapping")
        data["_path"] = path
        records.append(data)
    return records


def validate(records: list[dict[str, Any]]) -> list[str]:
    """Every way a record can be wrong on its own terms."""
    problems: list[str] = []
    seen: set[str] = set()
    for record in records:
        name = record["_path"].name
        for field in REQUIRED_ALWAYS:
            if record.get(field) in (None, ""):
                problems.append(f"{name}: missing required field '{field}'")
        slug = str(record.get("slug") or "")
        if slug and record["_path"].stem != slug:
            problems.append(f"{name}: slug '{slug}' does not match the filename")
        if slug in seen:
            problems.append(f"{name}: duplicate slug '{slug}'")
        seen.add(slug)

        state = record.get("state")
        if state not in STATES:
            problems.append(f"{name}: state '{state}' is not one of {STATES}")
            continue

        if state == "declined":
            if not record.get("declined_because"):
                problems.append(f"{name}: a declined record must say declined_because")
            if record.get("ghsa"):
                problems.append(f"{name}: declined but carries a ghsa id")
            continue

        for field in REQUIRED_ADVISORY:
            if record.get(field) in (None, ""):
                problems.append(f"{name}: missing required field '{field}'")
        if record.get("severity") not in SEVERITIES:
            problems.append(f"{name}: severity '{record.get('severity')}' is not one of {SEVERITIES}")
        if record.get("package") not in PACKAGES:
            problems.append(f"{name}: package '{record.get('package')}' is not one of {tuple(PACKAGES)}")
        if not record.get("shipped"):
            problems.append(f"{name}: an advisory needs shipped: true - a defect no release carried has nobody to warn")
        if state == "published" and not record.get("ghsa"):
            problems.append(f"{name}: published but carries no ghsa id")
        if record.get("fixed") and record.get("changelog_version") and record["fixed"] != record["changelog_version"]:
            problems.append(f"{name}: fixed {record['fixed']} but the changelog entry is under {record['changelog_version']}")
    return problems


def check_coverage(records: list[dict[str, Any]]) -> list[str]:
    """Every Security bullet from the baseline forward must have a record."""
    problems: list[str] = []
    claims = [(r["changelog_version"], normalise(str(r["changelog_entry"])), r) for r in records]
    matched: set[int] = set()

    for version, bullet in changelog_security_bullets():
        if parse_version(version) < COVERAGE_BASELINE:
            continue
        text = normalise(bullet)
        hits = [
            index
            for index, (claim_version, claim_text, _) in enumerate(claims)
            if claim_version == version and text.startswith(claim_text)
        ]
        if not hits:
            problems.append(
                f"CHANGELOG.md {version}: no record claims this Security entry -\n"
                f"    {bullet[:100]}...\n"
                f"    Decide whether it needs an advisory and write "
                f"security/advisories/<slug>.yml. See AGENTS.md, 'Security advisories'."
            )
        matched.update(hits)

    for index, (claim_version, _, record) in enumerate(claims):
        if index in matched or parse_version(claim_version) < COVERAGE_BASELINE:
            continue
        problems.append(
            f"{record['_path'].name}: claims a {claim_version} Security entry that "
            f"CHANGELOG.md does not have - has the wording changed?"
        )
    return problems


def gh_api(args: list[str], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    command = ["gh", "api", "-H", "Accept: application/vnd.github+json", *args]
    if payload is not None:
        command += ["--input", "-"]
    result = subprocess.run(  # nosec B603 - fixed argv, no shell
        command,
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RecordError(f"gh api failed: {result.stderr.strip()}")
    return dict(json.loads(result.stdout))


def advisory_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": " ".join(str(record["summary"]).split()),
        "description": record["description"],
        "severity": record["severity"],
        "cwe_ids": list(record["cwe_ids"]),
        "vulnerabilities": [
            {
                "package": PACKAGES[record["package"]],
                "vulnerable_version_range": f">= {record['introduced']}, < {record['fixed']}",
                "patched_versions": str(record["fixed"]),
            }
        ],
    }


def write_back(record: dict[str, Any], field: str, value: str) -> None:
    """Set one scalar field in the record file, leaving the rest byte for byte."""
    path: pathlib.Path = record["_path"]
    text = path.read_text(encoding="utf-8")
    if re.search(rf"^{field}:", text, flags=re.MULTILINE):
        text = re.sub(rf"^{field}:.*$", f"{field}: {value}", text, count=1, flags=re.MULTILINE)
    else:
        text = re.sub(r"^(state:.*)$", rf"\1\n{field}: {value}", text, count=1, flags=re.MULTILINE)
    path.write_text(text, encoding="utf-8")


def sync(records: list[dict[str, Any]]) -> int:
    """Create a GitHub draft for every drafted record that has no advisory yet."""
    pending = [r for r in records if r["state"] == "draft" and not r.get("ghsa")]
    if not pending:
        print("No records are waiting for a draft advisory.")
        return 0
    for record in pending:
        created = gh_api(
            ["--method", "POST", f"/repos/{REPO}/security-advisories"],
            advisory_payload(record),
        )
        write_back(record, "ghsa", created["ghsa_id"])
        print(f"drafted {created['ghsa_id']}  {record['slug']}")
    print(
        f"\n{len(pending)} draft advisory/advisories created and not published.\n"
        f"Review them at https://github.com/{REPO}/security/advisories, then\n"
        f"publish with: python scripts/security_advisories.py --publish <slug>"
    )
    return 0


def publish(records: list[dict[str, Any]], slug: str) -> int:
    matches = [r for r in records if r["slug"] == slug]
    if not matches:
        print(f"No record with slug '{slug}'.", file=sys.stderr)
        return 1
    record = matches[0]
    if record["state"] == "published":
        print(f"{slug} is already published as {record.get('ghsa')}.")
        return 0
    if record["state"] != "draft" or not record.get("ghsa"):
        print(f"{slug} has no draft advisory to publish - run --sync first.", file=sys.stderr)
        return 1
    result = gh_api(
        ["--method", "PATCH", f"/repos/{REPO}/security-advisories/{record['ghsa']}"],
        {"state": "published"},
    )
    write_back(record, "state", "published")
    print(f"published {record['ghsa']}  {slug}  ({result['state']})")
    return 0


def show(records: list[dict[str, Any]]) -> int:
    for record in sorted(records, key=lambda r: (parse_version(r["changelog_version"]), r["slug"]), reverse=True):
        ghsa = record.get("ghsa", "-")
        print(f"{record['state']:10} {ghsa:22} {record['changelog_version']:8} {record['slug']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="fail if a Security entry has no record")
    group.add_argument("--list", action="store_true", help="print every record and its state")
    group.add_argument("--sync", action="store_true", help="create a GitHub draft for each drafted record")
    group.add_argument("--publish", metavar="SLUG", help="publish one drafted advisory")
    args = parser.parse_args(argv)

    try:
        records = load_records()
    except (RecordError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.list:
        return show(records)

    problems = validate(records)
    if args.check:
        problems += check_coverage(records)
    if problems:
        print("Security advisory records need attention:\n", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    if args.check:
        covered = sum(1 for r in records if parse_version(r["changelog_version"]) >= COVERAGE_BASELINE)
        print(f"Every Security entry from {'.'.join(map(str, COVERAGE_BASELINE))} forward is accounted for ({covered} records).")
        return 0

    try:
        if args.sync:
            return sync(records)
        return publish(records, args.publish)
    except RecordError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
