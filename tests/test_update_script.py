"""Tests for scripts/update_release_schedule.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "update_release_schedule", REPO_ROOT / "scripts" / "update_release_schedule.py"
)
assert SPEC and SPEC.loader
script = importlib.util.module_from_spec(SPEC)
sys.modules["update_release_schedule"] = script
SPEC.loader.exec_module(script)


def tab(label: str) -> str:
    """One tab header, as Docusaurus renders it."""
    return f'<li role="tab" class="tabs__item">{label}</li>'


def panel(rows: list[tuple[str, str]]) -> str:
    """One release table, as Docusaurus renders it."""
    body = "".join(
        f'<tr><td style="text-align:left">{version}</td>'
        f'<td style="text-align:left">{released}</td>'
        f'<td style="text-align:left"><a href="https://example.invalid/{version}">'
        "Details · Download</a></td></tr>"
        for version, released in rows
    )
    return (
        '<div role="tabpanel" class="tabItem"><table><thead><tr>'
        "<th>Version</th><th>Release Date</th><th>Release Notes</th>"
        f"</tr></thead><tbody>{body}</tbody></table></div>"
    )


ROLLING = [
    ("v7.5.0", "TBD"),
    ("v7.4.0", "2026 August 3"),
    ("v7.3.0", "2026 July 14"),
    ("v7.2.0", "2026 June 25"),
    ("v4.1.0", "2025 December 15"),
    ("v2.0.0", "2025 March 26"),
]
PRODUCTION = [
    ("-", "2026 October 26"),
    ("v7.2.3", "2026 August 6"),
    ("v7.2.0", "2026 June 25"),
    ("v4.0.8", "2026 June 25"),
    ("v4.0.0", "2025 December 1"),
    ("v2.0.0", "2025 March 26"),
]
LTS = [("v4.0.9", "TBD")]

PAGE = (
    "<html><body><div class='tabs-container'><ul role='tablist'>"
    + tab("Rolling")
    + tab("Production")
    + tab("LTS")
    + "</ul>"
    + panel(ROLLING)
    + panel(PRODUCTION)
    + panel(LTS)
    + "</div></body></html>"
)


@pytest.fixture
def schedule():
    """The schedule extracted from the sample page."""
    return script.extract(PAGE)


def line_of(schedule_document, name):
    """Look one release line up by name."""
    return next(entry for entry in schedule_document["lines"] if entry["line"] == name)


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("v7.2.3", (7, 2, 3)),
        ("7.2.3", (7, 2, 3)),
        ("v7.2", (7, 2, 0)),
        ("-", None),
        ("TBD", None),
        ("", None),
        ("v0.9.0", None),
    ],
)
def test_parse_version(cell, expected):
    """Announced-but-unnamed and out-of-range rows are rejected."""
    assert script._parse_version(cell) == expected


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("2026 August 3", "2026-08-03"),
        ("2025 April 07", "2025-04-07"),
        ("2026 Aug 3", "2026-08-03"),
        ("TBD", None),
        ("", None),
    ],
)
def test_parse_date(cell, expected):
    """The page writes dates as 'YEAR MONTH DAY', occasionally zero padded."""
    assert script._parse_date(cell) == expected


def test_releases_are_grouped_into_lines(schedule):
    """A line is MAJOR.MINOR, because that is what OpenCloud maintains."""
    names = [entry["line"] for entry in schedule["lines"]]

    assert names == ["7.4", "7.3", "7.2", "4.1", "4.0", "2.0"]


def test_a_line_records_its_first_release_and_its_newest_patch(schedule):
    """7.2 opened on the day 7.2.0 shipped and is now at 7.2.3."""
    line = line_of(schedule, "7.2")

    assert line["released"] == "2026-06-25"
    assert line["latest"] == "7.2.3"


def test_a_line_can_belong_to_several_tracks(schedule):
    """7.2 shipped as a rolling release and was promoted to production."""
    assert line_of(schedule, "7.2")["tracks"] == ["production", "rolling"]
    assert line_of(schedule, "4.1")["tracks"] == ["rolling"]


def test_an_undated_row_still_marks_the_track(schedule):
    """The LTS tab announces 4.0.9 long before it exists.

    That row carries no date, but it is the only place the page states that
    4.0 is the LTS line, so the track membership has to survive.
    """
    line = line_of(schedule, "4.0")

    assert line["tracks"] == ["lts", "production"]
    # The announced release must not become the recommended upgrade target.
    assert line["latest"] == "4.0.8"


def test_an_undated_line_keeps_the_date_of_its_other_track(schedule):
    """4.0 is dated from the production tab, not from the LTS placeholder."""
    assert line_of(schedule, "4.0")["released"] == "2025-12-01"


def test_a_line_with_no_date_at_all_is_dropped():
    """7.5 is announced on the rolling tab but has no date yet."""
    schedule = script.extract(
        "<ul role='tablist'>"
        + tab("Rolling")
        + tab("Production")
        + "</ul>"
        + panel([("v7.5.0", "TBD"), ("v7.4.0", "2026 August 3")] + ROLLING[3:])
        + panel(PRODUCTION)
    )

    assert "7.5" not in [entry["line"] for entry in schedule["lines"]]


def test_the_newest_release_is_reported_per_track(schedule):
    """Recommending the newest release overall would be a track change."""
    assert schedule["latest_release"] == {"production": "7.2.3", "rolling": "7.4.0"}


def test_unnamed_rows_are_ignored(schedule):
    """The production tab announces the next release as '-'."""
    assert all(entry["latest"] != "-" for entry in schedule["lines"])


def test_a_page_without_the_expected_tables_is_rejected():
    """Better to keep the checked-in file than to write nonsense."""
    with pytest.raises(script.ExtractionError, match="rolling and a production"):
        script.extract("<html><body><p>Nothing to see here</p></body></html>")


def test_an_implausibly_short_schedule_is_rejected():
    """A page that renders only a stub must not wipe the schedule."""
    with pytest.raises(script.ExtractionError, match="release lines"):
        script.extract(
            "<ul role='tablist'>"
            + tab("Rolling")
            + tab("Production")
            + "</ul>"
            + panel([("v7.4.0", "2026 August 3")])
            + panel([("v7.2.3", "2026 August 6")])
        )


def test_unknown_tabs_are_ignored():
    """The page may grow tabs that are none of our business."""
    schedule = script.extract(
        "<ul role='tablist'>"
        + tab("Rolling")
        + tab("Nightly")
        + tab("Production")
        + "</ul>"
        + panel(ROLLING)
        + panel([("v9.9.9", "2026 August 10")])
        + panel(PRODUCTION)
    )

    assert "9.9" not in [entry["line"] for entry in schedule["lines"]]


def test_build_document_is_self_describing(schedule):
    """The file is read by humans as often as by the scanner."""
    document = script.build_document(schedule, "https://example.invalid/lifecycle")

    assert document["source"] == "https://example.invalid/lifecycle"
    assert document["lifetime_days"] == {"rolling": 21, "production": 183, "lts": 730}
    assert "_comment" in document
    assert document["lines"] == schedule["lines"]


def test_fetch_refuses_a_non_http_url():
    """Guards against a redirected or misconfigured source."""
    with pytest.raises(script.ExtractionError, match="non-HTTP URL"):
        script.fetch("file:///etc/passwd")


def _offline(monkeypatch, tmp_path, page=PAGE, error=None):
    """Point the script at a temporary file and a canned page."""
    target = tmp_path / "release_schedule.json"
    monkeypatch.setattr(script, "TARGET", target)

    def fake_fetch(url, timeout=30):
        if error:
            raise error
        return page

    monkeypatch.setattr(script, "fetch", fake_fetch)
    return target


def test_main_writes_the_schedule(monkeypatch, tmp_path, capsys):
    """The ordinary run."""
    target = _offline(monkeypatch, tmp_path)

    assert script.main([]) == 0
    document = json.loads(target.read_text())
    assert document["latest_release"]["production"] == "7.2.3"
    assert "Updated release schedule" in capsys.readouterr().out


def test_main_is_idempotent(monkeypatch, tmp_path, capsys):
    """A second run must not churn the file."""
    _offline(monkeypatch, tmp_path)
    script.main([])
    capsys.readouterr()

    assert script.main([]) == 0
    assert "unchanged" in capsys.readouterr().out


def test_check_mode_reports_without_writing(monkeypatch, tmp_path):
    """The scheduled workflow uses this to decide whether to open a PR."""
    target = _offline(monkeypatch, tmp_path)

    assert script.main(["--check"]) == 1
    assert not target.exists()


def test_check_mode_succeeds_when_current(monkeypatch, tmp_path):
    """Nothing to do is not a failure."""
    _offline(monkeypatch, tmp_path)
    script.main([])

    assert script.main(["--check"]) == 0


def test_a_failed_fetch_is_an_error_by_default(monkeypatch, tmp_path, capsys):
    """Silence about a broken source would be worse than a red build."""
    _offline(monkeypatch, tmp_path, error=OSError("boom"))

    assert script.main([]) == 1
    assert "Could not determine the release schedule" in capsys.readouterr().err


def test_allow_failure_keeps_a_release_going(monkeypatch, tmp_path):
    """A release must not fail because the documentation site is down."""
    target = _offline(monkeypatch, tmp_path, error=OSError("boom"))

    assert script.main(["--allow-failure"]) == 0
    assert not target.exists()


def test_a_broken_existing_file_is_replaced(monkeypatch, tmp_path):
    """Corruption on disk must not be mistaken for 'up to date'."""
    target = _offline(monkeypatch, tmp_path)
    target.write_text("{not json")

    assert script.main([]) == 0
    assert json.loads(target.read_text())["lines"]


def test_the_checked_in_schedule_matches_the_script():
    """The bundled file must be something this script could have written."""
    document = json.loads(script.TARGET.read_text(encoding="utf-8"))

    assert set(document) >= {"lines", "latest_release", "lifetime_days", "source", "updated"}
    assert document["lifetime_days"] == {"rolling": 21, "production": 183, "lts": 730}
    for entry in document["lines"]:
        assert set(entry) == {"line", "tracks", "released", "latest"}
        assert entry["tracks"]
