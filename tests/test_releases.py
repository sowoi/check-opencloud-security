"""
Tests for the update check.

OpenCloud has no update API, so "is this instance current?" is answered by
comparing the detected release against the newest published one. This module
covers the four ways of finding that release - the GitHub feed, an explicitly
pinned version, the bundled data file, and 'off' - and the track awareness
that keeps a production or LTS instance off the rolling track.
"""

from datetime import date

import pytest
import requests

from opencloud_local_scan import releases, versions
from opencloud_local_scan.releases import ReleaseSettings, fetch_update_info

GITHUB_RELEASE = {
    "tag_name": "v7.4.0",
    "name": "OpenCloud 7.4.0",
    "draft": False,
    "prerelease": False,
    "published_at": "2026-05-01T10:00:00Z",
}


class _Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


@pytest.fixture
def feed(monkeypatch):
    """Serve a canned document to the release feed, and record the request."""
    calls = []

    def _get(url, **kwargs):
        calls.append((url, kwargs))
        return _Response(calls_payload["document"])

    calls_payload = {"document": GITHUB_RELEASE}
    monkeypatch.setattr(releases.requests, "get", _get)
    return calls, calls_payload


def test_effective_mode_resolves_auto():
    """'auto' means "use whatever is configured", most specific first."""
    assert ReleaseSettings().effective_mode() == "feed"
    assert ReleaseSettings(latest_version="7.4.0").effective_mode() == "pinned"
    assert ReleaseSettings(feed_url="").effective_mode() == "bundled"
    assert ReleaseSettings(mode="off", latest_version="7.4.0").effective_mode() == "off"


def test_off_reports_nothing():
    """An operator who turned the check off gets no update information."""
    info = fetch_update_info(ReleaseSettings(mode="off"), "7.2.0")

    assert info.known is False
    assert info.source == "disabled"
    assert info.summary() == "Update check not performed"


def test_missing_settings_are_treated_as_off():
    """A caller that passes no settings must not trigger a network request."""
    assert fetch_update_info(None, "7.2.0").known is False


def test_feed_detects_an_available_update(feed):
    """A newer tag than the installed release means an update is pending."""
    info = fetch_update_info(ReleaseSettings(mode="feed"), "7.2.0")

    assert info.available is True
    assert info.available_version == "7.4.0"
    assert info.released_at == "2026-05-01T10:00:00Z"
    assert info.source == "feed"
    assert "update available: 7.4.0" in info.summary()


def test_feed_reports_an_up_to_date_instance(feed):
    """Running the newest release is the normal case."""
    info = fetch_update_info(ReleaseSettings(mode="feed"), "7.4.0")

    assert info.available is False
    assert "up to date" in info.summary()


def test_a_newer_instance_than_the_feed_is_not_an_update(feed):
    """A nightly build must not be reported as being behind."""
    info = fetch_update_info(ReleaseSettings(mode="feed"), "7.5.0")

    assert info.available is False


def test_feed_token_is_sent_as_a_bearer_header(feed):
    """A token lifts GitHub's unauthenticated rate limit."""
    calls, _ = feed

    fetch_update_info(ReleaseSettings(mode="feed", token="s3cret"), "7.2.0")

    _, kwargs = calls[0]
    assert kwargs["headers"]["Authorization"].endswith("s3cret")


def test_feed_list_picks_the_newest_non_prerelease(feed):
    """/releases returns a list; drafts and release candidates do not count."""
    _, payload = feed
    payload["document"] = [
        {"tag_name": "v7.3.0", "published_at": "2026-02-01T00:00:00Z"},
        {"tag_name": "v7.9.0", "prerelease": True},
        {"tag_name": "v8.0.0", "draft": True},
        {"tag_name": "v7.4.0", "published_at": "2026-05-01T00:00:00Z"},
    ]

    info = fetch_update_info(ReleaseSettings(mode="feed"), "7.2.0")

    assert info.available_version == "7.4.0"


def test_feed_accepts_a_plain_version_document(feed):
    """A local mirror may serve nothing but the version."""
    _, payload = feed
    payload["document"] = {"version": "7.4.0"}

    assert fetch_update_info(ReleaseSettings(mode="feed"), "7.2.0").available_version == "7.4.0"


def test_feed_failure_is_reported_not_raised(monkeypatch):
    """A firewalled monitoring host still gets a security result."""

    def _boom(*args, **kwargs):
        raise requests.exceptions.ConnectionError("no route to host")

    monkeypatch.setattr(releases.requests, "get", _boom)

    info = fetch_update_info(ReleaseSettings(mode="feed"), "7.2.0")

    assert info.known is False
    assert "no route to host" in (info.error or "")
    assert "failed" in info.summary()


def test_auto_falls_back_to_the_bundled_release_data(monkeypatch):
    """
    Without network access the shipped release is a stale but usable answer.

    The feed error is kept so an operator can see why the answer is older
    than it should be.
    """

    def _boom(*args, **kwargs):
        raise requests.exceptions.ConnectionError("no route to host")

    monkeypatch.setattr(releases.requests, "get", _boom)

    info = fetch_update_info(ReleaseSettings(mode="auto"), "1.0.0")

    assert info.known is True
    assert info.source == "bundled release data"
    assert "no route to host" in (info.error or "")


def test_explicit_feed_mode_does_not_fall_back(monkeypatch):
    """Asking for the feed explicitly means the feed answer, or none."""

    def _boom(*args, **kwargs):
        raise requests.exceptions.ConnectionError("down")

    monkeypatch.setattr(releases.requests, "get", _boom)

    assert fetch_update_info(ReleaseSettings(mode="feed"), "1.0.0").known is False


def test_pinned_version_wins_without_any_request(monkeypatch):
    """An operator who states the expected release means it."""

    def _boom(*args, **kwargs):
        raise AssertionError("the feed must not be queried in pinned mode")

    monkeypatch.setattr(releases.requests, "get", _boom)

    info = fetch_update_info(ReleaseSettings(latest_version="7.4.0"), "7.2.0")

    assert info.source == "pinned"
    assert info.available is True


def test_bundled_mode_is_fully_offline(monkeypatch):
    """'bundled' is the mode for an air-gapped monitoring host."""

    def _boom(*args, **kwargs):
        raise AssertionError("bundled mode must not touch the network")

    monkeypatch.setattr(releases.requests, "get", _boom)

    info = fetch_update_info(ReleaseSettings(mode="bundled"), "1.0.0")

    assert info.available is True
    assert info.source == "bundled release data"


def test_unknown_instance_version_is_not_an_update(feed):
    """Without a detected version there is nothing to compare against."""
    info = fetch_update_info(ReleaseSettings(mode="feed"), None)

    assert info.known is False
    assert info.available_version == "7.4.0"
    assert info.error


def test_as_dict_shape_is_stable(feed):
    """The plugin reads these keys out of the scan result."""
    info = fetch_update_info(ReleaseSettings(mode="feed"), "7.2.0")

    assert set(info.as_dict()) == {
        "available",
        "version",
        "availableVersion",
        "releasedAt",
        "source",
        "error",
        "track",
        "newestRelease",
    }


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ({"tag_name": "v7.4.0"}, "7.4.0"),
        ({"name": "7.4.0"}, "7.4.0"),
        ({"version": "7.4.0"}, "7.4.0"),
        ({"tag_name": "v7.4.0", "draft": True}, None),
        ({"tag_name": "v7.4.0", "prerelease": True}, None),
        ({"releases": [{"tag_name": "v7.4.0"}]}, "7.4.0"),
        ("nonsense", None),
        ({}, None),
    ],
)
def test_parse_release_feed(document, expected):
    """Every document shape a release feed might realistically return."""
    assert releases.parse_release_feed(document)[0] == expected


# --- Track awareness ---
#
# The release feed only ever reports the newest release overall, and that is
# always a rolling one. Handing it to a production or LTS instance would move
# it onto a track with a three-week support window, so the release schedule
# decides the target for those instances instead.
TODAY = date(2026, 8, 12)

SCHEDULE = versions.ReleaseSchedule(
    [
        versions.ReleaseLine((7, 4), ("rolling",), date(2026, 8, 3), "7.4.0"),
        versions.ReleaseLine((7, 3), ("rolling",), date(2026, 7, 14), "7.3.0"),
        versions.ReleaseLine(
            (7, 2), ("production", "rolling"), date(2026, 6, 25), "7.2.3"
        ),
        versions.ReleaseLine((4, 0), ("lts", "production"), date(2025, 12, 1), "4.0.8"),
    ],
    latest_release={"rolling": "7.4.0", "production": "7.2.3"},
)


def lifecycle(version):
    """Lifecycle verdict used to steer the update check."""
    return SCHEDULE.status_for(version, TODAY)


def test_a_rolling_instance_is_offered_the_newest_release(feed):
    """On the rolling track the feed's answer is exactly the right one."""
    info = fetch_update_info(ReleaseSettings(mode="feed"), "7.3.0", lifecycle("7.3.0"))

    assert info.available is True
    assert info.available_version == "7.4.0"
    assert info.track == "rolling"


def test_a_production_instance_is_not_offered_a_rolling_release(feed):
    """7.2.3 is current on production; 7.4.0 would be a track change."""
    info = fetch_update_info(ReleaseSettings(mode="feed"), "7.2.3", lifecycle("7.2.3"))

    assert info.available is False
    assert info.available_version is None
    assert info.track == "production"
    # The rolling release is still reported, just not as the recommendation.
    assert info.newest_release == "7.4.0"


def test_a_production_instance_is_offered_its_own_patch_release(feed):
    """7.2.0 has to move to 7.2.3, not to 7.4.0."""
    info = fetch_update_info(ReleaseSettings(mode="feed"), "7.2.0", lifecycle("7.2.0"))

    assert info.available is True
    assert info.available_version == "7.2.3"
    assert info.newest_release == "7.4.0"


def test_an_lts_instance_stays_on_the_lts_line(feed):
    """4.0.0 gets 4.0.8, which is where the backports are."""
    info = fetch_update_info(ReleaseSettings(mode="feed"), "4.0.0", lifecycle("4.0.0"))

    assert info.available_version == "4.0.8"
    assert info.track == "lts"


def test_a_fresher_feed_wins_within_the_same_line(monkeypatch):
    """The bundled schedule ages; a newer patch of the same line is real."""
    monkeypatch.setattr(
        releases.requests,
        "get",
        lambda *args, **kwargs: _Response({**GITHUB_RELEASE, "tag_name": "v7.2.4"}),
    )

    info = fetch_update_info(ReleaseSettings(mode="feed"), "7.2.0", lifecycle("7.2.0"))

    assert info.available_version == "7.2.4"
    # It came from the feed, so its publication date still applies.
    assert info.released_at is not None


def test_a_disabled_update_check_stays_disabled(feed):
    """The schedule must not report updates the operator switched off."""
    info = fetch_update_info(ReleaseSettings(mode="off"), "7.2.0", lifecycle("7.2.0"))

    assert info.available is None
    assert info.source == "disabled"
    assert info.available_version is None


def test_the_summary_names_the_track(feed):
    """The plugin prints this line, so it has to say which track applies."""
    info = fetch_update_info(ReleaseSettings(mode="feed"), "7.2.0", lifecycle("7.2.0"))

    assert "on the production track" in info.summary()


def test_an_unknown_lifecycle_leaves_the_feed_answer_alone(feed):
    """Without a verdict there is nothing better than the newest release."""
    info = fetch_update_info(ReleaseSettings(mode="feed"), "7.3.0", lifecycle("nonsense"))

    assert info.available_version == "7.4.0"
    assert info.track is None
