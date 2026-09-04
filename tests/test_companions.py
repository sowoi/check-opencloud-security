"""
The collaboration backend, where a deployment publishes one on this origin.

The scanner already reported *that* an office integration exists, because the
instance says so in its own capabilities. What it never asked was what that
second service publishes - and a document editor is a second HTTP server,
with an administration console and a transport of its own.

Two things these tests exist to hold down. The first is that an instance with
no backend on this origin gets no finding at all rather than a passing one,
because the common deployment puts the editor on a host of its own and a pass
there would be a claim nobody measured. The second is that OpenCloud's
single-page shell - which answers 200 for every unknown path - is never
mistaken for either the discovery document or the console.
"""

from __future__ import annotations

import pytest

from opencloud_local_scan import hardening
from opencloud_local_scan.releases import ReleaseSettings
from opencloud_local_scan.scanner import ScannerSettings, scan
from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour

SETTINGS = ScannerSettings(
    scheme="http", timeout=3, check_debug_ports=False, include_bundled_db=True
)
NO_UPDATES = ReleaseSettings(mode="off")

HTTPS_EDITOR = "https://collabora.example.com/browser/abc/cool.html?"
HTTP_EDITOR = "http://collabora.example.com/browser/abc/cool.html?"


def run_scan(behaviour: InstanceBehaviour) -> dict:
    with FakeOpenCloud(behaviour) as instance:
        return scan(instance.host, settings=SETTINGS, release_settings=NO_UPDATES)


def findings(result: dict) -> dict[str, dict]:
    return {check["id"]: check for check in result["extraChecks"]}


def test_no_backend_on_this_origin_is_left_unmeasured():
    """
    An observation nobody made is not an observation that passed. Most
    deployments put the editor on a host of its own, where this scan has no
    business probing, and reporting a pass would tell an operator their
    console is protected when nothing checked it.
    """
    checks = findings(run_scan(InstanceBehaviour(catch_all=True)))
    assert "companionAdminConsole" not in checks
    assert "companionEditorHttps" not in checks


def test_the_single_page_shell_is_not_mistaken_for_a_discovery_document():
    """
    OpenCloud answers unknown paths with its own HTML shell and HTTP 200. A
    check that trusted the status code would report a collaboration backend on
    every instance in existence, and then two findings about a service that is
    not there.
    """
    checks = findings(run_scan(InstanceBehaviour(catch_all=True, wopi_urlsrc=None)))
    assert "companionEditorHttps" not in checks


def test_a_backend_serving_https_editors_passes_both_checks():
    behaviour = InstanceBehaviour(
        catch_all=True, wopi_urlsrc=HTTPS_EDITOR, wopi_admin_console=False
    )
    checks = findings(run_scan(behaviour))

    assert checks["companionEditorHttps"]["passed"] is True
    assert checks["companionAdminConsole"]["passed"] is True


def test_an_editor_advertised_over_plain_http_fails():
    """
    The document and the access token authorising the session travel
    unencrypted, and a browser on an HTTPS page blocks the frame outright - so
    the editor does not load either.
    """
    checks = findings(run_scan(InstanceBehaviour(wopi_urlsrc=HTTP_EDITOR)))

    check = checks["companionEditorHttps"]
    assert check["passed"] is False
    assert check["severity"] == "high"
    assert "collabora.example.com" in check["detail"]


def test_a_reachable_admin_console_fails():
    """The console lists every open document session and can end them, behind
    one shared password with no rate limiting in front of it."""
    behaviour = InstanceBehaviour(wopi_urlsrc=HTTPS_EDITOR, wopi_admin_console=True)
    checks = findings(run_scan(behaviour))

    check = checks["companionAdminConsole"]
    assert check["passed"] is False
    assert check["severity"] == "high"
    assert "publicly readable" in check["detail"]


def test_the_catch_all_shell_is_not_mistaken_for_the_console():
    """
    The console is an HTML document, so the rule that saves the exposed-path
    checks - an HTML answer is the frontend, not the file - cannot be used
    here. What separates them is that the shell is byte-identical for every
    unknown path, and this is the test that keeps that distinction working.
    """
    behaviour = InstanceBehaviour(
        catch_all=True, wopi_urlsrc=HTTPS_EDITOR, wopi_admin_console=False
    )
    check = findings(run_scan(behaviour))["companionAdminConsole"]

    assert check["passed"] is True
    assert "catch-all" in check["detail"]


def test_a_reachable_console_caps_the_rating():
    """A finding that does not move the rating is a finding an operator never
    sees in a monitoring line."""
    exposed = run_scan(
        InstanceBehaviour(wopi_urlsrc=HTTPS_EDITOR, wopi_admin_console=True)
    )
    protected = run_scan(
        InstanceBehaviour(wopi_urlsrc=HTTPS_EDITOR, wopi_admin_console=False)
    )

    assert exposed["rating"] < protected["rating"]
    assert any(
        cap["check"] == "companionAdminConsole"
        for cap in exposed["ratingExplanation"]["caps"]
    )


def test_a_companion_finding_can_be_waived():
    """An operator who has accepted a finding must be able to silence the
    alert without losing the evidence."""
    settings = ScannerSettings(
        scheme="http",
        timeout=3,
        check_debug_ports=False,
        include_bundled_db=True,
        ignore_hardenings=("companionAdminConsole",),
    )
    with FakeOpenCloud(
        InstanceBehaviour(wopi_urlsrc=HTTPS_EDITOR, wopi_admin_console=True)
    ) as instance:
        result = scan(instance.host, settings=settings, release_settings=NO_UPDATES)

    check = findings(result)["companionAdminConsole"]
    assert check["passed"] is False
    assert check["ignored"] is True
    assert "companionAdminConsole" in result["ignored"]


@pytest.mark.parametrize("name", ["companionAdminConsole", "companionEditorHttps"])
def test_both_findings_are_registered_in_the_hardening_catalogue(name):
    """An identifier the catalogue cannot explain reaches an operator as a
    bare string with no remediation and no category."""
    described = hardening.describe(name)
    assert described.id == name
    assert described.remediation
    assert described.category in {"exposure", "transport"}
