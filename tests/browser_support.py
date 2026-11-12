"""
Shared plumbing for the browser tests of the web application.

The ASGI test client renders templates but never runs them: no script
executes, no stylesheet applies, and the Content-Security-Policy is a header
nobody enforces. These tests drive a real browser engine through Playwright
against the real application, served over HTTP from a background thread, with
an in-process stand-in for the ARQ worker so a submitted scan really finishes,
and fake OpenCloud instances as the targets.

Browsers: WebKit by default; ``PLAYWRIGHT_BROWSER=firefox`` or ``chromium``
picks another engine. Chromium's builds are Google's, which ADR 0061 refused
and ADR 0068 accepted for the Blink coverage - on the condition below, which
applies to every engine alike. Every browser is launched behind a proxy that does not exist, with
only loopback bypassing it, so nothing a page or the engine itself asks for
can leave the machine; a test that needed the network would fail rather than
quietly reach out.

The whole module skips when Playwright, the web extra or the browser build
is missing - unless ``PLAYWRIGHT_TESTS_REQUIRED=1``, which is how the CI job
makes a missing browser a failure instead of a silent pass.
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_REQUIRED = os.environ.get("PLAYWRIGHT_TESTS_REQUIRED") == "1"


def _require(module: str, reason: str) -> Any:
    if _REQUIRED:
        return __import__(module, fromlist=["_"])
    return pytest.importorskip(module, reason=reason)


_require("fastapi", "the web application extra is not installed")
sync_api = _require("playwright.sync_api", "playwright is not installed (dependency group `test`)")

import uvicorn

from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour
from webapp import tasks
from webapp.app import create_app
from webapp.redis_backend import reset_memory_backends
from webapp.settings import WebSettings

BROWSERS = ("webkit", "firefox", "chromium")
BROWSER = os.environ.get("PLAYWRIGHT_BROWSER", "webkit")

#: Where a failed test's Playwright trace goes. Unset - the default, and every
#: local run - records nothing. The CI job sets it and uploads the directory
#: when a test fails, so a page that hung on the runner can be replayed with
#: `playwright show-trace` instead of guessed at.
TRACE_DIR = os.environ.get("PLAYWRIGHT_TRACE_DIR", "")
MEMORY_URL = "memory://browser-tests"
# Nothing listens on the discard port; only loopback bypasses the proxy.
DEAD_PROXY = {"server": "http://127.0.0.1:9", "bypass": "127.0.0.1,localhost,[::1]"}
DESKTOP = {"width": 1280, "height": 900}
PHONE = {"width": 390, "height": 844}


# The hardened and the weak profile must differ by their configuration alone,
# and the bundled advisory database only ever grows: the fake's stock 7.2.3
# gained one in November 2026, which capped both at the same grade. They run
# a release no bundled advisory covers; test_webapp_browser_e2e checks it.
UNAFFECTED_RELEASE = "9.1.0"


def instance(profile: str) -> FakeOpenCloud:
    """A fake OpenCloud instance playing a named profile (not started)."""
    behaviour = InstanceBehaviour()
    behaviour.status_payload["productversion"] = UNAFFECTED_RELEASE
    if profile == "eol":
        behaviour.status_payload["productversion"] = "2.3.0"
    elif profile == "weak":
        behaviour.headers = {"Content-Type": "text/html"}
        behaviour.demo_users = True
        behaviour.debug_endpoints = True
        behaviour.directory_listing = True
        behaviour.trace_enabled = True
        behaviour.disclose_server = "nginx/1.18.0"
    elif profile != "hardened":
        raise ValueError(profile)
    return FakeOpenCloud(behaviour)


class LiveSite:
    """
    The web application, a worker and fake targets, served from one thread.

    The worker drains the ``memory://`` queue - which otherwise keeps every
    scan ``queued`` forever - into :func:`webapp.tasks.run_scan` with the
    application's own store, exactly as the ARQ worker would.
    """

    def __init__(self, profiles: tuple[str, ...] = ("hardened", "weak", "eol"), **overrides: Any) -> None:
        self._fakes = {name: instance(name) for name in profiles}
        self._overrides = overrides
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None
        self._started = threading.Event()
        self._failure: BaseException | None = None
        self.base = ""
        self.targets: dict[str, str] = {}
        # Cleared, the worker leaves jobs queued, so a test can watch the
        # waiting page before letting the scan run.
        self.worker_open = threading.Event()
        self.worker_open.set()

    def __enter__(self) -> LiveSite:  # noqa: PYI034 - Self needs 3.11
        for name, fake in self._fakes.items():
            fake.__enter__()
            self.targets[name] = f"http://{fake.host}"
        reset_memory_backends()
        self._thread = threading.Thread(target=self._run, name="live-site", daemon=True)
        self._thread.start()
        if not self._started.wait(30) or self._failure:
            self.__exit__(None, None, None)
            raise RuntimeError(f"the live site did not start: {self._failure!r}")
        return self

    def _run(self) -> None:
        try:
            asyncio.run(self._serve())
        except BaseException as error:  # noqa: BLE001 - reported to the waiting test
            self._failure = error
            self._started.set()

    async def _serve(self) -> None:
        import socket

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        options: dict[str, Any] = {
            "redis_url": MEMORY_URL,
            "allow_private_targets": True,
            "ip_rate_limit": 0,
            "target_cooldown": 0,
            "probe_limit": 0,
            "daily_scan_limit": 0,
            "result_ttl": 3600,
            "public_base_url": self.base,
        }
        options.update(self._overrides)
        app = create_app(WebSettings(**options))
        self._server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="on"))
        worker = asyncio.create_task(self._work(app))
        serve = asyncio.create_task(self._server.serve(sockets=[listener]))
        while not self._server.started and not serve.done():
            await asyncio.sleep(0.02)
        self._started.set()
        await serve
        worker.cancel()

    async def _work(self, app: Any) -> None:
        while True:
            await asyncio.sleep(0.1)
            jobs = getattr(app.state.queue, "jobs", None)
            while jobs and self.worker_open.is_set():
                uuid = jobs.pop(0)
                await tasks.run_scan({"web_settings": app.state.settings, "store": app.state.store}, uuid)

    def __exit__(self, *exc: object) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(15)
        for fake in self._fakes.values():
            fake.__exit__(None, None, None)
        reset_memory_backends()


# Every Content-Security-Policy violation, reported by the page itself through
# the standard event, so it is seen the same way in every engine.
_CSP_RECORDER = """
document.addEventListener('securitypolicyviolation', (event) => {
  window.__cspViolations = window.__cspViolations || [];
  window.__cspViolations.push(event.effectiveDirective + ' blocked ' + (event.blockedURI || 'inline'));
});
"""


#: NS_BINDING_ABORTED, as Firefox prints it in a failed font download.
_ABORTED = "status=2152398850"


def aborted_font_download(text: str) -> bool:
    """
    Firefox reporting a font download that a navigation cut short.

    A web font is fetched when text first needs it, which can be after the
    load event. A test that reloads or moves on in that moment aborts the
    download, and Firefox logs it as an error. It is the test leaving, not
    the page failing - a font that does not load at all still fails with
    another status and is still reported.
    """
    return "downloadable font: download failed" in text and _ABORTED in text


@dataclass
class PageWatch:
    """What a page said while a test used it: console errors, crashes, CSP violations, stray requests."""

    console_errors: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    foreign_requests: list[str] = field(default_factory=list)
    pages: list[Any] = field(default_factory=list)

    def attach(self, page: Any) -> None:
        self.pages.append(page)
        page.on("console", self._console)
        page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        page.on("request", self._request)

    def _console(self, message: Any) -> None:
        if message.type == "error" and not aborted_font_download(message.text):
            self.console_errors.append(message.text)

    def _request(self, request: Any) -> None:
        url = request.url
        if not url.startswith(("http://127.0.0.1:", "data:", "blob:", "about:")):
            self.foreign_requests.append(url)

    def csp_violations(self) -> list[str]:
        """The violations the current document of every watched page reported."""
        found: list[str] = []
        for page in self.pages:
            if not page.is_closed():
                found += page.evaluate("() => window.__cspViolations || []")
        return found

    def assert_clean(self) -> None:
        """No script error, no CSP violation, no request that left loopback."""
        assert self.page_errors == []
        assert self.console_errors == []
        assert self.csp_violations() == []
        assert self.foreign_requests == []


def launch(playwright: Any) -> Any:
    """The configured browser behind the dead proxy; skips when it is not installed."""
    if BROWSER not in BROWSERS:
        raise pytest.UsageError(f"PLAYWRIGHT_BROWSER must be one of {BROWSERS}, not {BROWSER!r}")
    try:
        return getattr(playwright, BROWSER).launch(proxy=DEAD_PROXY)
    except sync_api.Error as error:
        message = str(error).splitlines()[0]
        if _REQUIRED:
            raise
        pytest.skip(f"{BROWSER} cannot be launched here ({message}); run `playwright install {BROWSER}`")


@contextmanager
def dark_system_browser(browser: Any) -> Iterator[tuple[Any, dict[str, Any]]]:
    """A browser whose operating system prefers dark, and the context options that keep it so.

    Playwright's Firefox drops an emulated colour scheme once a response sends
    `Cross-Origin-Opener-Policy: same-origin`, as every page here does, so
    Firefox gets its own instance with a dark system theme instead.
    """
    if browser.browser_type.name != "firefox":
        yield browser, {"color_scheme": "dark"}
        return
    dark = browser.browser_type.launch(proxy=DEAD_PROXY, firefox_user_prefs={"ui.systemUsesDarkTheme": 1})
    try:
        yield dark, {"color_scheme": "no-override"}
    finally:
        dark.close()


@pytest.fixture(scope="module", name="site")
def site_fixture() -> Iterator[LiveSite]:
    """One live site per test module, with a hardened, a weak and an end-of-life target."""
    with LiveSite() as live:
        yield live


@pytest.fixture(scope="module", name="browser")
def browser_fixture() -> Iterator[Any]:
    """One browser per test module."""
    with sync_api.sync_playwright() as playwright:
        engine = launch(playwright)
        yield engine
        engine.close()


def new_page(browser: Any, watch: PageWatch, **options: Any) -> Any:
    """A page in a fresh context: no stored theme, no cookies, reduced motion unless asked."""
    options.setdefault("viewport", DESKTOP)
    options.setdefault("reduced_motion", "reduce")
    options.setdefault("locale", "en-GB")
    context = browser.new_context(**options)
    context.add_init_script(_CSP_RECORDER)
    page = context.new_page()
    page.set_default_timeout(15_000)
    watch.attach(page)
    return page


@pytest.fixture(name="watch")
def watch_fixture() -> PageWatch:
    """A fresh watch for the ``page`` fixture."""
    return PageWatch()


def trace_path(directory: str, nodeid: str) -> Path:
    """One file per test, named after it, safe on any file system."""
    return Path(directory) / (re.sub(r"[^\w.-]+", "_", nodeid).strip("_") + ".zip")


@pytest.fixture(name="page")
def page_fixture(browser: Any, watch: PageWatch, request: pytest.FixtureRequest) -> Iterator[Any]:
    """A desktop page whose console, errors and requests are watched."""
    page = new_page(browser, watch)
    # The call phase's report is logged before teardown runs, so a failure of
    # this test has already been counted when the trace is stopped below.
    failures_before = request.session.testsfailed
    if TRACE_DIR:
        page.context.tracing.start(screenshots=True, snapshots=True)
    yield page
    if TRACE_DIR:
        if request.session.testsfailed > failures_before:
            path = trace_path(TRACE_DIR, request.node.nodeid)
            path.parent.mkdir(parents=True, exist_ok=True)
            page.context.tracing.stop(path=str(path))
        else:
            page.context.tracing.stop()
    page.context.close()


SHOWN_BUT_HIDDEN = """() => [...document.querySelectorAll('[hidden]')]
    .filter(el => el.getClientRects().length > 0)
    .map(el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className ? '.' + el.className : ''))"""


def shown_but_hidden(page: Any) -> list[str]:
    """Elements carrying `hidden` that a stylesheet still renders."""
    return page.evaluate(SHOWN_BUT_HIDDEN)


def submit_scan(page: Any, site: LiveSite, target: str, **form: Any) -> str:
    """Submit the landing form for ``target`` and return the result page's uuid once it is final."""
    page.goto(site.base + "/")
    page.fill("#target_url", target)
    for name, value in form.items():
        page.select_option(f"#{name}", value)
    page.click("form.scan-form button[type=submit]")
    page.wait_for_url("**/scan/**")
    uuid = page.url.rsplit("/scan/", 1)[1].split("?")[0]
    wait_until_final(page)
    return uuid


def wait_for_visible_findings(page: Any, count: int, timeout: int = 10_000) -> None:
    """Wait until exactly ``count`` findings on the result page carry no ``hidden``.

    Pressing a severity counter both hides most of the list and reveals the
    status line above it, so the page it leaves behind is a different height
    from the one that was pressed. Reading the count back with a single
    `locator.count()` samples that page while it is still settling, and the
    press that follows lands on a control that has moved - which WebKit on CI
    drops rather than delivers, leaving the filter on and the next assertion
    counting the wrong list. Waiting for the count the press asked for is what
    makes the next press land where the reader would have aimed it.
    """
    page.wait_for_function(
        "expected => document.querySelectorAll("
        "'[data-findings-list] .finding:not([hidden])').length === expected",
        arg=count,
        timeout=timeout,
    )


def wait_until_final(page: Any, timeout: int = 60_000) -> None:
    """Wait for the result page to reload into its finished state."""
    # The poll can land between the reload and the new document's <body>
    # (Firefox), so a missing body counts as "not yet", not as an error.
    page.wait_for_function(
        "() => ['completed', 'failed'].includes(document.body?.getAttribute('data-scan-state'))",
        timeout=timeout,
    )
    page.wait_for_load_state("load")
