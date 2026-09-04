"""Tests for version parsing, comparison and the release schedule."""

import json
from datetime import date

import pytest

from opencloud_local_scan import versions


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("7.2.0", (7, 2, 0)),
        ("v7.2.0", (7, 2, 0)),
        ("7.4.0+dev", (7, 4, 0)),
        ("7.4.0-rc.1", (7, 4, 0)),
        ("7", (7,)),
        ("", ()),
        (None, ()),
        ("not-a-version", ()),
    ],
)
def test_parse_version(raw, expected):
    """Release tags, development builds and release candidates all parse."""
    assert versions.parse_version(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("v7.2.0", "7.2.0"), ("7.2.0", "7.2.0"), ("", None), (None, None)],
)
def test_normalise_version(raw, expected):
    """A leading 'v' from a git tag is stripped."""
    assert versions.normalise_version(raw) == expected


def test_legacy_versions_are_recognised():
    """
    OpenCloud reports fixed legacy constants for old sync clients.

    'version' is always 0.1.0.0 and 'versionstring' always 0.1.0, no matter
    which release actually runs, so neither may ever be treated as a release.
    """
    assert versions.is_legacy_version("0.1.0.0") is True
    assert versions.is_legacy_version("0.1.0") is True
    assert versions.is_legacy_version("7.2.0") is False


def test_select_version_prefers_productversion():
    """The real release only appears in 'productversion'."""
    payload = {"version": "0.1.0.0", "versionstring": "0.1.0", "productversion": "7.2.0"}
    assert versions.select_version(payload) == "7.2.0"


def test_select_version_rejects_the_legacy_placeholder():
    """Without 'productversion' there is no usable version, not '0.1.0.0'."""
    assert versions.select_version({"version": "0.1.0.0", "versionstring": "0.1.0"}) is None


def test_select_version_handles_missing_input():
    """A missing or empty payload yields no version rather than an error."""
    assert versions.select_version(None) is None
    assert versions.select_version({}) is None


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("7.2.0", "7.2.0", 0),
        ("7.2.0", "7.3.0", -1),
        ("7.3.0", "7.2.0", 1),
        ("7.2", "7.2.0", 0),
        ("7.4.0+dev", "7.4.0", 0),
    ],
)
def test_compare_versions(left, right, expected):
    """Comparison ignores trailing zeros and build suffixes."""
    assert versions.compare_versions(left, right) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("7.2.3", (7, 2)), ("v7.2", (7, 2)), ("7", None), ("", None), (None, None)],
)
def test_release_line(raw, expected):
    """MAJOR.MINOR is the unit OpenCloud maintains, so it is what we key on."""
    assert versions.release_line(raw) == expected


@pytest.mark.parametrize(
    ("version", "introduced", "fixed", "expected"),
    [
        ("7.2.0", "7.0.0", "7.3.0", True),
        ("7.3.0", "7.0.0", "7.3.0", False),
        ("6.9.0", "7.0.0", "7.3.0", False),
        ("7.2.0", None, "7.3.0", True),
        ("7.2.0", "7.0.0", None, True),
        (None, "7.0.0", "7.3.0", False),
    ],
)
def test_is_in_range(version, introduced, fixed, expected):
    """Advisory ranges are half-open: [introduced, fixed)."""
    assert versions.is_in_range(version, introduced, fixed) is expected


def test_newest():
    """The highest version wins, regardless of input order."""
    assert versions.newest(["7.1.0", "7.10.0", "7.2.0"]) == "7.10.0"
    assert versions.newest([]) is None


# --- Release lifecycle ---
#
# The schedule below is a miniature of the real one and exercises every shape
# that occurs in practice: a rolling-only line, a line that was promoted from
# rolling to production, and a production line that later became the LTS line.
TODAY = date(2026, 8, 12)

SCHEDULE = versions.ReleaseSchedule(
    [
        versions.ReleaseLine((7, 4), ("rolling",), date(2026, 8, 3), "7.4.0"),
        versions.ReleaseLine((7, 3), ("rolling",), date(2026, 7, 14), "7.3.0"),
        versions.ReleaseLine((7, 2), ("production", "rolling"), date(2026, 6, 25), "7.2.3"),
        versions.ReleaseLine((7, 1), ("rolling",), date(2026, 6, 2), "7.1.0"),
        versions.ReleaseLine((4, 1), ("rolling",), date(2025, 12, 15), "4.1.0"),
        versions.ReleaseLine((4, 0), ("lts", "production"), date(2025, 12, 1), "4.0.8"),
        versions.ReleaseLine((2, 1), ("rolling",), date(2025, 4, 7), "2.1.0"),
        versions.ReleaseLine((2, 0), ("production", "rolling"), date(2025, 3, 26), "2.0.5"),
    ],
    latest_release={"rolling": "7.4.0", "production": "7.2.3"},
)


def status(version):
    """Lifecycle verdict for a version, evaluated on a fixed day."""
    return SCHEDULE.status_for(version, TODAY)


def test_the_newest_rolling_release_is_current():
    """Nothing has superseded it, so there is nothing to warn about."""
    verdict = status("7.4.0")

    assert verdict.release_type == "rolling"
    assert verdict.state == "supported"
    assert verdict.eol is False
    assert verdict.end_of_life is None
    assert verdict.upgrade_to is None


def test_a_superseded_rolling_release_is_end_of_life():
    """A rolling release lives about three weeks - until its successor lands."""
    verdict = status("7.3.0")

    assert verdict.release_type == "rolling"
    assert verdict.state == "endOfLife"
    assert verdict.eol is True
    # 7.4.0 took over on the day it was released.
    assert verdict.end_of_life == "2026-08-03"
    assert verdict.days_remaining == -9


def test_a_superseded_rolling_release_is_sent_to_the_newest_rolling_one():
    """The way back into support is the current release of the same track."""
    assert status("7.1.0").upgrade_to == "7.4.0"


def test_a_promoted_line_is_judged_by_its_production_track():
    """7.2 shipped as a rolling release and then became the production one.

    Judged as a rolling release it would already be dead, because 7.3 exists.
    Judged as the current production release it is perfectly fine, and that
    is the verdict the operator needs.
    """
    verdict = status("7.2.3")

    assert verdict.release_type == "production"
    assert verdict.state == "supported"
    assert verdict.reason == "current production release"


def test_a_supported_line_still_reports_its_pending_patch():
    """Being on a supported line is not the same as being up to date."""
    verdict = status("7.2.0")

    assert verdict.state == "supported"
    assert verdict.latest_on_line == "7.2.3"
    assert verdict.upgrade_to == "7.2.3"


def test_an_lts_line_outlives_its_production_window():
    """4.0 stopped being the production release when 7.2 arrived.

    As the LTS line it keeps receiving backports for two years from its first
    release, and the longer window is the one that counts.
    """
    verdict = status("4.0.8")

    assert verdict.release_type == "lts"
    assert verdict.state == "supported"
    assert verdict.end_of_life == "2027-12-01"
    assert verdict.days_remaining == 476


def test_lts_expires_on_the_clock_rather_than_on_a_successor():
    """Two years after 4.0.0 the backports stop, successor or not."""
    verdict = SCHEDULE.status_for("4.0.8", date(2027, 12, 2))

    assert verdict.state == "endOfLife"
    assert verdict.upgrade_to == "7.2.3"


def test_a_rolling_line_of_an_lts_major_gets_no_lts_treatment():
    """4.1 was a rolling release; sharing a major with 4.0 changes nothing."""
    verdict = status("4.1.0")

    assert verdict.release_type == "rolling"
    assert verdict.state == "endOfLife"


def test_an_expired_production_line_is_sent_to_the_current_production_release():
    """A production instance must never be pushed onto the rolling track."""
    verdict = status("2.0.5")

    assert verdict.release_type == "production"
    assert verdict.state == "endOfLife"
    assert verdict.end_of_life == "2025-12-01"
    assert verdict.upgrade_to == "7.2.3"


def test_a_release_newer_than_the_schedule_is_not_end_of_life():
    """The bundled schedule ages; a fresh release must not trip the alarm."""
    verdict = status("9.0.0")

    assert verdict.state == "supported"
    assert verdict.eol is False
    assert verdict.reason == "newer than every release in the bundled schedule"


def test_a_line_that_predates_the_schedule_is_end_of_life():
    """Anything older than the oldest recorded line is long gone."""
    assert status("1.0.0").state == "endOfLife"


@pytest.mark.parametrize("version", [None, "", "not-a-version", "7"])
def test_an_unreadable_version_stays_unknown(version):
    """A version we could not read must not be declared end of life."""
    verdict = status(version)

    assert verdict.state == "unknown"
    assert verdict.eol is None
    assert verdict.supported is None


def test_an_empty_schedule_answers_unknown():
    """Without local knowledge the check reports nothing rather than F."""
    verdict = versions.ReleaseSchedule().status_for("7.2.3", TODAY)

    assert verdict.state == "unknown"
    assert verdict.reason == "no release schedule available"


def test_latest_release_is_track_aware():
    """The newest production release is not the newest release overall."""
    assert SCHEDULE.latest_for("production") == "7.2.3"
    assert SCHEDULE.latest_for("rolling") == "7.4.0"
    assert SCHEDULE.latest_for() == "7.4.0"


def test_release_line_picks_the_track_with_the_longest_support():
    """A line on several tracks is judged by the most generous one."""
    assert SCHEDULE.lines[(4, 0)].release_type == "lts"
    assert SCHEDULE.lines[(7, 2)].release_type == "production"
    assert SCHEDULE.lines[(7, 4)].release_type == "rolling"


def test_successor_is_looked_up_per_track():
    """7.2 succeeds 7.1 on rolling, but nothing succeeds it on production."""
    line = SCHEDULE.lines[(7, 1)]

    assert SCHEDULE.successor(line, "rolling").name == "7.2"
    assert SCHEDULE.successor(SCHEDULE.lines[(7, 2)], "production") is None


# --- A schedule older than the instance it is judging ---
#
# The bundled file is a snapshot of a page that keeps moving, so an instance
# patched last week is routinely newer than the data it is compared against.
# The only correct response is to say so and stand back: the schedule is what
# is out of date, and an operator who patched promptly must not be marked
# down for it.


def test_a_patch_newer_than_the_record_marks_the_schedule_stale():
    """
    The everyday case: 7.2.4 ships, this copy of the schedule still says the
    7.2 line ends at 7.2.3. Saying nothing would leave an operator reading a
    support window worked out from data that predates their own instance.
    """
    verdict = status("7.2.4")

    assert verdict.schedule_stale is True
    assert "probably out of date" in (verdict.schedule_note or "")
    assert versions.LIFECYCLE_DOCUMENTATION_URL in (verdict.schedule_note or "")
    # The negative half, and the point of the whole thing: nothing about the
    # verdict got worse for it.
    assert verdict.state == "supported"
    assert verdict.eol is False
    assert verdict.upgrade_to is None
    assert verdict.latest_on_line is None


def test_a_release_line_newer_than_the_whole_schedule_says_so_too():
    """A new line is the same staleness one step larger, and it must not be
    read as a version nobody supports."""
    verdict = status("8.0.0")

    assert verdict.schedule_stale is True
    assert verdict.state == "supported"
    assert verdict.eol is False


def test_a_version_the_schedule_knows_exactly_is_not_called_stale():
    """
    The assertion that keeps the note honest.

    If every scan carried it, it would say nothing. It appears only when the
    instance is genuinely ahead of the file - not for the newest release on
    record, and not for an old one that simply never got updated.
    """
    assert status("7.4.0").schedule_stale is False
    assert status("7.4.0").schedule_note is None
    assert status("2.0.5").schedule_stale is False
    assert status("7.2.0").schedule_stale is False
    assert versions.ReleaseSchedule().status_for("7.2.4", TODAY).schedule_stale is False


def test_being_newer_than_the_schedule_never_costs_anything_on_any_track():
    """
    Whatever track an operator declared, a version ahead of the recorded one
    is supported, gets no upgrade arrow and is never end of life. A stale file
    turning a promptly patched instance into an F would be the worst failure
    this module has.
    """
    for track in ("rolling", "production", "lts", "auto", None):
        verdict = SCHEDULE.status_for("7.4.9", TODAY, track=track)

        assert verdict.schedule_stale is True, track
        assert verdict.eol is not True, track
        assert verdict.upgrade_to is None, track


def test_an_unrecorded_line_is_never_told_to_downgrade():
    """
    An upgrade arrow must only ever point forwards, on every track.

    A line missing from the schedule - dropped from the lifecycle page as it
    aged, or never published there - is judged end of life, and the release to
    move to was taken from the declared track alone. The newest release
    recorded for a track can be *older* than a version the schedule has no
    line for, and "upgrade to 4.0.8" told to a 5.0.0 instance is advice that
    removes fixes instead of adding them.
    """
    schedule = versions.ReleaseSchedule(
        [
            versions.ReleaseLine((7, 4), ("rolling",), date(2026, 8, 3), "7.4.0"),
            versions.ReleaseLine((4, 0), ("lts", "production"), date(2025, 12, 1), "4.0.8"),
        ],
        # The LTS track is named here, so nothing falls back to a newer track.
        latest_release={"rolling": "7.4.0", "lts": "4.0.8"},
    )

    verdict = schedule.status_for("5.0.0", TODAY, track="lts")

    assert verdict.state == "endOfLife"
    assert verdict.upgrade_to != "4.0.8"
    # Forwards or not at all: 7.4.0 is the only release ahead of 5.0.0.
    assert verdict.upgrade_to == "7.4.0"
    # And a version nothing on record is ahead of gets no arrow rather than a
    # backwards one.
    assert schedule.status_for("8.5.0", TODAY, track="lts").upgrade_to is None


def test_an_unrecorded_line_behind_the_schedule_is_still_sent_forwards():
    """
    The ordinary case the guard above must not break.

    A gap in the middle of the schedule is still an unsupported release, and
    an operator on one needs to be told where to go.
    """
    verdict = status("6.0.0")

    assert verdict.state == "endOfLife"
    assert verdict.upgrade_to == "7.4.0"
    assert SCHEDULE.status_for("6.0.0", TODAY, track="production").upgrade_to == "7.2.3"


def test_a_stale_schedule_does_not_rescue_a_line_that_really_expired():
    """
    The other side of the same coin, and the invariant it must not break.

    Support is granted per line, so patching inside a line whose window has
    closed does not reopen it. 2.0.6 would be newer than the record and still
    unsupported - the note explains the data, it does not overturn the
    verdict.
    """
    verdict = status("2.0.6")

    assert verdict.schedule_stale is True
    assert verdict.state == "endOfLife"


def test_the_schedule_says_where_it_came_from_and_when():
    """The note points at a page rather than at nothing, and the shipped file
    carries both, so a reader can check the verdict at its source."""
    bundled = versions.load_release_schedule()

    assert bundled.source == versions.LIFECYCLE_DOCUMENTATION_URL
    assert bundled.updated
    document = bundled.status_for("7.4.0").as_dict()
    assert document["scheduleSource"] == versions.LIFECYCLE_DOCUMENTATION_URL
    assert document["scheduleUpdated"] == bundled.updated


def test_lifecycle_status_is_serialisable():
    """The scanner puts this straight into its JSON result document."""
    document = status("7.2.3").as_dict()

    assert set(document) == {
        "line",
        "releaseType",
        "state",
        "released",
        "endOfLife",
        "daysRemaining",
        "latestOnLine",
        "upgradeTo",
        "reason",
        "declaredTrack",
        "scheduleStale",
        "scheduleUpdated",
        "scheduleSource",
        "scheduleNote",
    }
    assert document["line"] == "7.2"
    assert document["releaseType"] == "production"


# --- Loading the schedule from disk ---
def test_the_bundled_schedule_is_usable():
    """The file shipped with the package must parse and cover every track."""
    schedule = versions.load_release_schedule()

    assert schedule
    assert schedule.latest_for("production")
    assert schedule.latest_for("rolling")
    # Every line must name at least one known track and a real date.
    for line in schedule.lines.values():
        assert set(line.tracks) <= set(versions.RELEASE_TRACKS)
        assert isinstance(line.released, date)
        assert versions.parse_version(line.latest)


def test_the_bundled_schedule_knows_an_lts_line():
    """The two-year window is the whole reason the LTS track is scraped."""
    schedule = versions.load_release_schedule()

    assert any("lts" in line.tracks for line in schedule.lines.values())


def test_a_custom_schedule_can_be_loaded(tmp_path):
    """Operators can point the check at their own vendor's commitments."""
    path = tmp_path / "schedule.json"
    path.write_text(
        json.dumps(
            {
                "lifetime_days": {"lts": 1095},
                "latest_release": {"lts": "9.0.1"},
                "lines": [
                    {
                        "line": "9.0",
                        "tracks": ["lts"],
                        "released": "2026-01-01",
                        "latest": "9.0.1",
                    }
                ],
            }
        )
    )

    schedule = versions.load_release_schedule(path)

    assert schedule.lifetime_days["lts"] == 1095
    # Three years, not the two the public schedule promises.
    assert schedule.status_for("9.0.0", TODAY).end_of_life == "2028-12-31"


def test_unusable_entries_are_skipped_rather_than_fatal(tmp_path):
    """One malformed line must not discard the rest of the schedule."""
    path = tmp_path / "schedule.json"
    path.write_text(
        json.dumps(
            {
                "lines": [
                    {"line": "nonsense", "tracks": ["rolling"], "released": "2026-01-01"},
                    {"line": "7.2", "tracks": ["unknown-track"], "released": "2026-01-01"},
                    {"line": "7.3", "tracks": ["rolling"], "released": "not-a-date"},
                    {
                        "line": "7.4",
                        "tracks": ["rolling"],
                        "released": "2026-08-03",
                        "latest": "7.4.0",
                    },
                ]
            }
        )
    )

    schedule = versions.load_release_schedule(path)

    assert list(schedule.lines) == [(7, 4)]


def test_a_broken_file_falls_back_instead_of_raising(tmp_path):
    """A corrupted file must not take the whole check down."""
    path = tmp_path / "schedule.json"
    path.write_text("{not json")

    assert not versions.load_release_schedule(path)
    assert versions.load_latest_release(path=path) is None


def test_is_end_of_life_wraps_the_schedule():
    """The convenience wrapper agrees with the full verdict."""
    assert versions.is_end_of_life("2.0.5", SCHEDULE, TODAY) is True
    assert versions.is_end_of_life("7.2.3", SCHEDULE, TODAY) is False
    assert versions.is_end_of_life(None, SCHEDULE, TODAY) is None
