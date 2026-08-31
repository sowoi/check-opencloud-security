"""
Looking a finding identifier up without scanning anything.

A monitoring system prints ``cspWithoutUnsafeInline`` and nothing else. Before
this command the three ways to find out what that meant were to run a scan
that fails the same check, open the web application, or read the source - all
of which need something the person woken up at three in the morning may not
have. So the two properties worth protecting are that it answers from the
catalogue every other layer already reads, and that it needs nothing else: no
configuration file, no network, no instance.
"""

from __future__ import annotations

import json

from opencloud_local_scan.cli import main
from opencloud_local_scan.hardening import CATEGORIES, all_checks


def test_it_explains_one_identifier(capsys):
    assert main(["explain", "cspWithoutUnsafeInline"]) == 0

    out = capsys.readouterr().out

    assert "cspWithoutUnsafeInline" in out
    assert "unsafe-inline" in out
    # The explanation is the point, not the echo of the name: a reader gets
    # what to change, not just what broke.
    assert "Fix:" in out


def test_it_needs_no_configuration_file(monkeypatch, tmp_path, capsys):
    """
    The command that answers 'what is this identifier' must not fail because
    a configuration file is missing or malformed - that would leave the
    operator reading a second error instead of their answer.
    """
    unreadable = tmp_path / "broken.yml"
    unreadable.write_text("this: [is not: valid", encoding="utf-8")

    assert main(["--config", str(unreadable), "explain", "basicAuthDisabled"]) == 0

    assert "basicAuthDisabled" in capsys.readouterr().out


def test_a_header_name_is_explained_too(capsys):
    """
    Headers are the identifiers most likely to be pasted in from an alert,
    and they live in a namespace ``all_checks`` deliberately leaves out - so
    they are the case most likely to be forgotten.
    """
    assert main(["explain", "Referrer-Policy"]) == 0

    assert "Referrer-Policy" in capsys.readouterr().out


def test_a_per_path_finding_resolves_to_its_family(capsys):
    """
    A result names ``exposed:/config/opencloud.yaml``; the catalogue lists
    only ``exposed``. Pasting what the alert actually said has to work.
    """
    assert main(["explain", "exposed:/config/opencloud.yaml"]) == 0

    out = capsys.readouterr().out

    assert "/config/opencloud.yaml" in out


def test_an_unknown_identifier_fails_and_suggests(caplog):
    """
    ``describe`` never fails - it names the unknown rather than swallowing it
    - so without an explicit check this command would print a confident
    placeholder for a typo and exit 0.
    """
    assert main(["explain", "cspWithoutUnsafeInlin"]) == 1

    assert "cspWithoutUnsafeInline" in caplog.text


def test_it_prints_the_whole_catalogue_when_given_nothing(capsys):
    assert main(["explain", "--list"]) == 0

    listed = capsys.readouterr().out.split()

    for entry in all_checks():
        assert entry.id in listed, entry.id
    assert "Referrer-Policy" in listed


def test_a_category_narrows_the_catalogue(capsys):
    assert main(["explain", "--list", "--category", "cookies"]) == 0

    listed = capsys.readouterr().out.split()

    assert "cookieSecure" in listed
    # The negative case: a category filter that returned everything would
    # pass the assertion above.
    assert "basicAuthDisabled" not in listed


def test_json_output_carries_the_whole_entry(capsys):
    assert main(["explain", "--format", "json", "cookieSecure"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert len(payload) == 1
    entry = payload[0]
    assert entry["id"] == "cookieSecure"
    assert entry["category"] in CATEGORIES
    assert entry["meaning"] and entry["remediation"]
    assert entry["actionable"] is True
