"""
Scanning the same instance again, and the wait before that is allowed.

Two properties carry this feature. The button must re-submit through the one
path every other submission uses - not a second write endpoint beside it - so
that the cross-site check, both limits, the SSRF guard and the audit trail
apply to it unchanged. And the countdown must be able to read a limit without
spending it: a page that told you how long to wait by using up your allowance
would be a page that caused the wait it reported.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour
from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    backend,
    settings,
)
from webapp.app import create_app
from webapp.ratelimit import RateLimiter, client_key, target_key
from webapp.tasks import run_scan

IDENTIFIER = "5a1d0e3c-9b2f-4c81-a7e6-2f0b4d9c1e73"
A_CLIENT = "203.0.113.55"
A_TARGET = "cloud.example.com"


def _report(**overrides) -> tuple[str, TestClient]:
    """One finished scan of the fake instance, and the client that rendered it."""
    configured = settings(
        allow_private_targets=True, verify_tls=False, scan_timeout=5, **overrides
    )
    app = create_app(configured)
    with TestClient(app) as test_client:
        store = app.state.store
        with FakeOpenCloud(InstanceBehaviour(basic_auth=True)) as instance:
            asyncio.run(
                store.create(
                    IDENTIFIER,
                    target=f"http://{instance.host}",
                    ignore_hardenings=("X-Robots-Tag",),
                    output_format="dashboard",
                    release_track="lts",
                )
            )
            asyncio.run(run_scan({"web_settings": configured, "store": store}, IDENTIFIER))
        return test_client.get(f"/scan/{IDENTIFIER}").text, test_client


# ------------------------------------------------------------- the peek itself


def _limiter(**kwargs) -> RateLimiter:
    return RateLimiter(backend=backend(), salt="a-fixed-salt", **kwargs)


def test_reading_the_client_allowance_does_not_spend_any_of_it():
    """
    The whole point of ``peek_client``: showing somebody their wait must not
    be the request that starts it. ``check_client`` counts, this must not.
    """
    limiter = _limiter(client_limit=2, client_window=60, target_cooldown=0)

    async def scenario() -> None:
        for _ in range(5):
            assert (await limiter.peek_client(A_CLIENT)).allowed
        assert (await limiter.check_client(A_CLIENT)).allowed
        assert (await limiter.check_client(A_CLIENT)).allowed
        # Only the two real submissions counted, so the third is the refusal.
        assert not (await limiter.check_client(A_CLIENT)).allowed
        refused = await limiter.peek_client(A_CLIENT)
        assert not refused.allowed
        assert refused.retry_after > 0
        assert refused.scope == "client"

    asyncio.run(scenario())


def test_reading_a_targets_cooldown_does_not_claim_the_slot():
    """
    ``check_target`` answers by taking the slot, which would make the answer
    "the full cooldown" every single time it was asked.
    """
    limiter = _limiter(client_limit=0, client_window=60, target_cooldown=120)

    async def scenario() -> None:
        # Nothing has scanned it, so nothing is owed - and asking must not
        # change that.
        assert (await limiter.peek_target(A_TARGET)).allowed
        assert (await limiter.peek_target(A_TARGET)).allowed
        assert (await limiter.check_target(A_TARGET)).allowed

        waiting = await limiter.peek_target(A_TARGET)
        assert not waiting.allowed
        assert 0 < waiting.retry_after <= 120
        assert waiting.scope == "target"

    asyncio.run(scenario())


def test_a_disabled_limit_is_never_a_wait():
    """An operator who turned a limit off must not be shown a countdown for it."""
    limiter = _limiter(client_limit=0, client_window=60, target_cooldown=0)

    async def scenario() -> None:
        assert (await limiter.peek_client(A_CLIENT)).retry_after == 0
        assert (await limiter.peek_target(A_TARGET)).retry_after == 0

    asyncio.run(scenario())


def test_the_peeks_read_the_same_keys_the_checks_write():
    """
    Two spellings of a key is two limits, and the countdown would then be
    reporting on a bucket nobody submits against.
    """
    limiter = _limiter(client_limit=1, client_window=60, target_cooldown=60)

    async def scenario() -> None:
        await limiter.check_client(A_CLIENT)
        await limiter.check_target(A_TARGET)
        assert await backend().get(client_key(A_CLIENT, "a-fixed-salt")) is not None
        assert await backend().get(target_key(A_TARGET, "a-fixed-salt")) is not None

    asyncio.run(scenario())


# ---------------------------------------------------------------- the button


def test_the_rescan_button_resubmits_through_the_ordinary_path():
    """
    It is a form posting to ``/``. Anything else would be a second write
    endpoint that the cross-site check, the limits and the audit log would
    each have to be taught about separately.
    """
    page, _ = _report()

    assert 'data-rescan-button' in page
    start = page.index("rescan-card")
    form = page[start:page.index("</section>", start)]
    assert 'method="post"' in form
    assert 'action="/"' in form


def test_a_rescan_carries_every_choice_the_first_scan_made():
    """
    Same target, same waivers, same track, same format - otherwise the second
    result is not comparable with the first, which is the only reason to
    offer the button in the first place.
    """
    page, _ = _report()
    start = page.index("rescan-card")
    form = page[start:page.index("</section>", start)]

    assert 'name="target_url"' in form
    assert 'name="ignore_hardenings" value="X-Robots-Tag"' in form
    assert 'name="release_track" value="lts"' in form
    assert 'name="output_format" value="dashboard"' in form


def test_the_button_is_offered_enabled_so_a_reader_without_scripting_can_use_it():
    """
    rescan.js disables it while the countdown runs. Rendering it disabled
    instead would leave anybody without that script holding a control nothing
    on the page can release - and the 429 they would otherwise meet is the
    friendly one that points at self-hosting.
    """
    page, _ = _report()
    start = page.index("data-rescan-button")
    button = page[start - 200:start + 100]

    assert "disabled" not in button


def test_the_page_carries_the_wait_this_targets_own_cooldown_imposes():
    """
    The countdown starts from a number the server measured for *this* target,
    not from a constant the script assumed - so an operator who changed the
    cooldown gets a page that agrees with their configuration, and a page for
    one instance never reports another's wait.
    """
    configured = settings(
        allow_private_targets=True, verify_tls=False, scan_timeout=5, target_cooldown=300
    )
    app = create_app(configured)
    with TestClient(app) as test_client:
        store = app.state.store
        with FakeOpenCloud(InstanceBehaviour()) as instance:
            asyncio.run(
                store.create(
                    IDENTIFIER,
                    target=f"http://{instance.host}",
                    ignore_hardenings=(),
                    output_format="dashboard",
                )
            )
            asyncio.run(run_scan({"web_settings": configured, "store": store}, IDENTIFIER))
            # What a real submission does on the way in, and what the page has
            # to notice: the target's slot is taken for the cooldown's length.
            hostname = instance.host.rsplit(":", 1)[0]
            asyncio.run(app.state.limiter.check_target(hostname))
            page = test_client.get(f"/scan/{IDENTIFIER}").text

    marker = 'data-rescan-after="'
    value = int(page[page.index(marker) + len(marker):].split('"')[0])
    assert 0 < value <= 300

    # And the first reading is the server's, not the script's: rendering
    # "ready" here would flash the wrong answer at everybody and would be the
    # only answer a reader without scripting ever got.
    note = page[page.index('id="rescan-note"'):]
    assert "Ready to scan again in" in note[:300]
    assert "Ready to scan this instance again." not in note[:300]


def test_no_countdown_is_shown_when_nothing_is_being_waited_for():
    """
    With both limits off there is no wait, and a timer counting down from
    zero would be inventing a restriction the service does not have.
    """
    page, _ = _report(target_cooldown=0, ip_rate_limit=0)

    assert 'data-rescan-after="0"' in page


def test_the_wait_is_the_longer_of_the_two_limits():
    """
    Either limit can be the one in the way. A countdown that tracked only the
    target cooldown would expire into a refusal from the client limit, which
    is worse than showing no countdown at all.
    """
    limiter = _limiter(client_limit=1, client_window=600, target_cooldown=30)

    async def scenario() -> None:
        await limiter.check_client(A_CLIENT)
        await limiter.check_target(A_TARGET)
        client = await limiter.peek_client(A_CLIENT)
        target = await limiter.peek_target(A_TARGET)
        # The client window is the longer of the two here, and it is the one a
        # page must report.
        assert client.retry_after > target.retry_after
        assert max(client.retry_after, target.retry_after) == client.retry_after

    asyncio.run(scenario())


def test_a_scan_still_running_is_offered_no_rescan_at_all():
    """
    There is nothing to compare against yet, and a countdown beside a progress
    bar answers a question the reader has not reached.
    """
    configured = settings(allow_private_targets=True)
    app = create_app(configured)
    with TestClient(app) as test_client:
        asyncio.run(
            app.state.store.create(
                IDENTIFIER,
                target="http://cloud.example.com",
                ignore_hardenings=(),
                output_format="dashboard",
            )
        )
        page = test_client.get(f"/scan/{IDENTIFIER}").text

    assert "data-rescan-button" not in page
    assert "rescan-card" not in page


def test_the_rescan_card_adds_no_inline_script_or_handler():
    """
    The policy has no 'unsafe-inline', so an inline handler here would be
    dropped by the browser and the button would silently stop working.
    """
    page, _ = _report()
    start = page.index("rescan-card")
    card = page[start:page.index("</section>", start)]

    assert "onclick" not in card
    assert "style=" not in card
    assert "<script" not in card


@pytest.mark.parametrize("locale", ["de", "fr", "es"])
def test_the_countdown_sentence_is_translated_and_keeps_its_placeholder(locale: str):
    """
    The script fills ``{countdown}`` into a sentence the server wrote. A
    translation that dropped the placeholder would leave a timer with no time
    in it.
    """
    from webapp.locales import CATALOGUES

    assert "{countdown}" in CATALOGUES[locale]["result.rescan.wait"]
    assert CATALOGUES[locale]["result.rescan"] != CATALOGUES["en"]["result.rescan"]
