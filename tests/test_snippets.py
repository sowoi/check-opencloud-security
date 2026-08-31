"""
The fixes a report names, rendered as configuration.

The value of this module is entirely in it being right: a fragment somebody
pastes into a production Compose file and does not read is worse than no
fragment at all. So most of what follows guards the join between the prose an
operator reads and the assignment they paste - if those two ever say different
things, the sentence is what they will have believed.
"""

from __future__ import annotations

import pytest

from opencloud_local_scan import all_checks, describe_hardening
from opencloud_local_scan.scanner import PASSWORD_COMPLEXITY_KEYS
from opencloud_local_scan.snippets import (
    DEFAULT_FLAVOUR,
    FLAVOURS,
    KIND_ENV,
    KIND_HEADER,
    flavour,
    flavours_for,
    fragment,
)

# Two identifiers that between them exercise both kinds, chosen because they
# are the plainest of each: one boolean environment variable, one header with
# a fixed value.
AN_ENV_FINDING = "basicAuthDisabled"
A_HEADER_FINDING = "X-Frame-Options"


def _every_fix() -> list[tuple[str, tuple[str, str]]]:
    """Every mechanical fix in the catalogue, tagged with its identifier."""
    return [
        (entry.id, pair)
        for entry in all_checks()
        for pair in entry.env_fix + entry.header_fix
    ]


# --------------------------------------------------------------- drift guards


def test_a_headline_setting_is_also_named_in_the_assignments_it_stands_for():
    """
    The two ways of naming a variable must not drift apart.

    ``setting`` is what the catalogue prints as "the setting behind this"; the
    ``env_fix`` pairs are what gets pasted. An entry whose headline setting is
    absent from its own assignments would print one variable and set another.
    """
    for entry in all_checks():
        if not entry.env_fix:
            continue
        assert entry.setting, f"{entry.id} has assignments but names no setting"
        assert entry.setting in {name for name, _ in entry.env_fix}, (
            f"{entry.id} names {entry.setting} but its fragment never sets it"
        )


def test_every_header_value_still_appears_in_the_sentence_that_recommends_it():
    """
    A reader is given the sentence and the fragment; they must agree.

    The header values are quoted out of their own remediation text. Rewording
    that text without touching the value here is the exact way the two would
    come to say different things, and this is what notices.
    """
    for entry in all_checks():
        for name, value in entry.header_fix:
            assert value in entry.remediation, (
                f"{entry.id} would paste {name}: {value}, "
                f"which its own Fix line does not mention"
            )


def test_no_fix_value_can_break_out_of_the_quoting_every_flavour_uses():
    """
    Every renderer wraps values in double quotes and none of them escapes.

    That is fine for the values the catalogue holds and would be a broken -
    or, in a YAML file, a differently-shaped - fragment for a value carrying a
    quote or a newline. The constraint is cheap; discovering it in somebody's
    Caddyfile is not.
    """
    for identifier, (name, value) in _every_fix():
        assert '"' not in value, f"{identifier} sets {name} to a value with a quote"
        assert "\n" not in value, f"{identifier} sets {name} across two lines"
        assert value == value.strip(), f"{identifier} sets {name} with stray space"


def test_the_password_fragment_still_satisfies_the_check_it_is_offered_for():
    """
    The scanner passes ``min_characters`` at eight and every class at one.

    A fragment that set a lower value would be pasted, believed, and leave the
    finding exactly where it was - so the numbers are asserted against the
    thresholds rather than against themselves.
    """
    enforced = dict(describe_hardening("passwordPolicyEnforced").env_fix)
    assert int(enforced["OC_PASSWORD_POLICY_MIN_CHARACTERS"]) >= 8
    assert enforced["OC_PASSWORD_POLICY_DISABLED"] == "false"

    complexity = dict(describe_hardening("passwordPolicyComplexity").env_fix)
    for key in PASSWORD_COMPLEXITY_KEYS:
        variable = f"OC_PASSWORD_POLICY_{key.upper()}"
        assert int(complexity[variable]) >= 1, f"{variable} is not set high enough"


# ------------------------------------------------------------------ rendering


@pytest.mark.parametrize("chosen", [entry.id for entry in FLAVOURS])
def test_every_flavour_writes_something_for_the_kind_it_serves(chosen: str):
    """
    No flavour is decoration.

    A picker offering five buttons where one produces nothing would send the
    reader who runs Caddy away believing there was no fix for them.
    """
    rendered = fragment([AN_ENV_FINDING, A_HEADER_FINDING], chosen)

    assert rendered.text, f"{chosen} rendered nothing"
    assert not rendered.empty


def test_a_finding_is_covered_by_its_own_kind_and_pointed_elsewhere_by_the_other():
    """
    The two kinds go in different files, so neither may quietly absorb the other.

    A header rendered into a Compose environment block would be a line that
    does nothing, in a file nobody looks at twice.
    """
    env = fragment([AN_ENV_FINDING, A_HEADER_FINDING], "compose")
    assert env.covered == (AN_ENV_FINDING,)
    assert env.elsewhere == (A_HEADER_FINDING,)
    assert "X-Frame-Options" not in env.text

    headers = fragment([AN_ENV_FINDING, A_HEADER_FINDING], "nginx")
    assert headers.covered == (A_HEADER_FINDING,)
    assert headers.elsewhere == (AN_ENV_FINDING,)
    assert "PROXY_ENABLE_BASIC_AUTH" not in headers.text


def test_a_finding_with_no_mechanical_fix_is_named_rather_than_guessed_at():
    """
    ``corsOriginRestricted`` needs an origin only the deployment knows.

    Emitting a placeholder would produce a fragment that looks finished and
    is not, which is the one outcome worse than prose.
    """
    rendered = fragment(["corsOriginRestricted"], "compose")

    assert rendered.undecided == ("corsOriginRestricted",)
    assert rendered.covered == ()
    assert rendered.text == ""
    assert "OC_CORS_ALLOW_ORIGINS" not in rendered.text


def test_one_assignment_wanted_by_two_findings_is_written_once():
    """
    ``debugEndpoint`` and ``debugPort`` are one ``OC_DEBUG_ADDR`` between them.

    A fragment that set it twice is one somebody has to read twice to be sure
    the two lines agree.
    """
    rendered = fragment(["debugEndpoint:/debug/pprof", "debugPort:9205"], "env")

    assert rendered.text.count("OC_DEBUG_ADDR") == 1
    assert len(rendered.covered) == 2


def test_the_fragment_reads_in_the_order_the_report_does():
    """
    A fragment ordered differently from the findings above it is a fragment
    the reader has to re-match to the report by hand.
    """
    rendered = fragment(["demoUsersDisabled", AN_ENV_FINDING], "env")
    lines = rendered.text.splitlines()

    assert lines[0].startswith("IDM_CREATE_DEMO_USERS")
    assert lines[1].startswith("PROXY_ENABLE_BASIC_AUTH")


def test_nginx_headers_are_sent_on_error_responses_too():
    """
    Without ``always`` nginx omits the header on a 4xx or 5xx.

    An error page served without the security headers is precisely the page
    that needed them, and the omission is invisible in a normal test.
    """
    rendered = fragment([A_HEADER_FINDING], "nginx")

    assert rendered.text == 'add_header X-Frame-Options "SAMEORIGIN" always;'


def test_nothing_open_renders_nothing_rather_than_an_empty_shell():
    """A clean instance gets no fragment, not a Compose file with no keys."""
    rendered = fragment([], DEFAULT_FLAVOUR)

    assert rendered.empty
    assert rendered.text == ""
    assert rendered.covered == ()


# ------------------------------------------------------------------- flavours


def test_an_unknown_flavour_falls_back_rather_than_failing():
    """
    The flavour comes from a stored browser preference, so an old or edited
    value must land somewhere sensible instead of taking the page down.
    """
    assert flavour("nonesuch").id == DEFAULT_FLAVOUR
    assert fragment([AN_ENV_FINDING], "nonesuch").flavour.id == DEFAULT_FLAVOUR


def test_each_kind_names_the_flavours_that_can_actually_write_it():
    """
    The "this belongs elsewhere" note is built from this, so it must never
    point somebody at a flavour that cannot express what they are missing.
    """
    env_flavours = flavours_for(KIND_ENV)
    header_flavours = flavours_for(KIND_HEADER)

    assert "Docker Compose" in env_flavours
    assert "nginx" in header_flavours
    assert not set(env_flavours) & set(header_flavours)
