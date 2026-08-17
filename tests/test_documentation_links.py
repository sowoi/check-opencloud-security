"""
Tests for the documented-link check that runs after every merge into main.

The links this project publishes about OpenCloud - the release lifecycle page
the schedule is generated from, the configuration references a finding points
an operator at - rot without a commit landing here. These tests protect the
part that decides *what* gets checked; the network half belongs to the
workflow, not to the suite.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module():
    """Import the script by path; scripts/ is not a package."""
    path = REPO_ROOT / "scripts" / "check_documentation_links.py"
    spec = importlib.util.spec_from_file_location("check_documentation_links", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_documentation_links"] = module
    spec.loader.exec_module(module)
    return module


links = _load_module()


def test_only_opencloud_links_are_checked():
    """This project answers for the links it documents, not for the whole web.

    Checking everybody's links would make the workflow slow and flaky for
    failures nobody here can fix.
    """
    assert links.is_opencloud_link("https://docs.opencloud.eu/docs/admin/resources/lifecycle/")
    assert links.is_opencloud_link("https://github.com/opencloud-eu/opencloud/releases")
    assert links.is_opencloud_link("https://api.github.com/repos/opencloud-eu/opencloud")

    assert not links.is_opencloud_link("https://github.com/sowoi/check-opencloud-security")
    assert not links.is_opencloud_link("https://example.com/opencloud.eu")
    assert not links.is_opencloud_link("https://docs.opencloud.eu.evil.test/docs")


def test_the_webfinger_namespace_is_not_a_link():
    """OpenCloud puts namespace URIs in its responses; they are identifiers.

    Requesting one returns 404 and would fail the workflow forever.
    """
    assert not links.is_opencloud_link("http://webfinger.opencloud.eu/rel/server-instance")


def test_a_url_loses_the_punctuation_of_the_sentence_around_it():
    """Prose and Markdown wrap links; the address stops before the full stop."""
    assert links.clean("https://opencloud.eu/.") == "https://opencloud.eu/"
    assert (
        links.clean("https://docs.opencloud.eu/docs/admin/resources/lifecycle/)")
        == "https://docs.opencloud.eu/docs/admin/resources/lifecycle/"
    )
    # A closing parenthesis that belongs to the URL itself stays.
    assert links.clean("https://opencloud.eu/a_(b)") == "https://opencloud.eu/a_(b)"


def test_a_placeholder_is_not_collected(tmp_path):
    """An issue template showing the shape of a URL must not be requested."""
    (tmp_path / "template.yml").write_text(
        'placeholder: "https://github.com/opencloud-eu/opencloud/blob/main/..."\n',
        encoding="utf-8",
    )

    assert links.collect_links(tmp_path) == []


def test_links_are_collected_from_every_documented_file_type(tmp_path):
    """A link rots the same way in a Python docstring as in the README."""
    (tmp_path / "README.md").write_text(
        "See [the lifecycle](https://docs.opencloud.eu/docs/admin/resources/lifecycle/).\n",
        encoding="utf-8",
    )
    (tmp_path / "hardening.py").write_text(
        '"""https://docs.opencloud.eu/docs/admin/configuration/link-password-policy"""\n',
        encoding="utf-8",
    )
    (tmp_path / "unrelated.md").write_text("https://example.com/whatever\n", encoding="utf-8")
    binary = tmp_path / "image.png"
    binary.write_bytes(b"\x89PNG https://docs.opencloud.eu/nope")

    found = {link.url for link in links.collect_links(tmp_path)}

    assert found == {
        "https://docs.opencloud.eu/docs/admin/resources/lifecycle/",
        "https://docs.opencloud.eu/docs/admin/configuration/link-password-policy",
    }


def test_the_repository_itself_documents_links_worth_checking():
    """A collector that silently found nothing would pass forever."""
    found = links.collect_links(REPO_ROOT)

    assert len(found) >= 5
    assert any("docs.opencloud.eu" in link.url for link in found)


def test_the_test_suite_is_not_mistaken_for_documentation(tmp_path):
    """Fixtures hold addresses that only look like links, including dead ones.

    Requesting them would fail the workflow over URLs nobody publishes.
    """
    suite = tmp_path / "tests"
    suite.mkdir()
    (suite / "fixture.py").write_text(
        'URL = "https://docs.opencloud.eu/definitely-not-real"\n', encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("https://docs.opencloud.eu/real\n", encoding="utf-8")

    assert [link.url for link in links.collect_links(tmp_path)] == [
        "https://docs.opencloud.eu/real"
    ]


def test_a_rate_limited_answer_is_not_treated_as_rot(monkeypatch):
    """An anonymous GitHub API call is rate limited; that is not a dead link.

    Failing the merge over a 403 would make the check noise, and noise gets
    switched off.
    """
    link = links.Link("https://api.github.com/repos/opencloud-eu/opencloud", "config.yml")
    monkeypatch.setattr(links, "_check_once", lambda url, timeout: ("HTTP 403", False))
    assert links.check(link, attempts=1).broken is False

    monkeypatch.setattr(links, "_check_once", lambda url, timeout: ("HTTP 404", True))
    assert links.check(link, attempts=1).broken is True


@pytest.mark.parametrize(
    ("url", "final", "expected"),
    [
        ("https://opencloud.eu/", "https://opencloud.eu/", None),
        ("https://opencloud.eu/docs", "https://opencloud.eu/docs/", None),
        ("https://opencloud.eu/a", "https://opencloud.eu/b", "redirected to https://opencloud.eu/b"),
    ],
)
def test_only_a_redirect_that_moves_the_content_is_reported(url, final, expected):
    """A trailing slash is not a move; a different path is."""
    assert links._redirect_problem(url, final) == expected


def test_a_broken_link_fails_the_run_while_a_redirect_only_reports(monkeypatch, capsys):
    """The workflow must fail on rot and stay quiet-ish on a language redirect.

    opencloud.eu redirects to a locale, so failing on redirects would make the
    job fail every week and teach everybody to ignore it.
    """
    moved = links.Link("https://opencloud.eu/", "README.md")
    dead = links.Link("https://docs.opencloud.eu/gone", "README.md")
    monkeypatch.setattr(links, "collect_links", lambda root: [moved, dead])
    monkeypatch.setattr(
        links,
        "check",
        lambda link, **kwargs: links.Problem(link, "redirected to https://opencloud.eu/de", False)
        if link is moved
        else links.Problem(link, "HTTP 404", True),
    )

    assert links.main([]) == 1
    output = capsys.readouterr()
    assert "https://docs.opencloud.eu/gone" in output.err
    assert "https://opencloud.eu/" in output.out

    monkeypatch.setattr(links, "check", lambda link, **kwargs: None)
    assert links.main([]) == 0
