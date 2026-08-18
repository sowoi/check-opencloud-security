"""
The FastAPI application.

Three things a visitor may say - what to scan, what to waive, how to see the
answer - and nothing else. Everything about *how* the scan runs is server
side, and the request never gets a vote.

Requests are checked in this order:

1. the client rate limit, because it is one Redis ``INCR`` and it protects
   the resolver behind step 2 from being used as an amplifier;
2. the target itself, against the SSRF guard;
3. the waiver list, against the allow-list, dropping anything unknown;
4. the target cooldown, claimed with ``SET NX`` so two simultaneous requests
   for the same instance cannot both win.

Only then does a uuid exist. Overload never changes any of this: when every
worker is busy the job simply waits in the queue, and the visitor is told
where in the line they are. A public service that answers 503 under load is a
service that punishes people for being interested.
"""

from __future__ import annotations

import logging
import os
import uuid as uuid_module
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from opencloud_local_scan import __version__

from .catalog import (
    DEFAULT_RELEASE_TRACK,
    csv_report,
    release_track_options,
    sanitize_release_track,
    sanitize_waivers,
    sarif_report,
    summarise,
    waiver_options,
)
from .queue import ScanQueue, create_queue
from .ratelimit import RateLimiter
from .redis_backend import RedisUnavailable, create_backend
from .settings import WebSettings
from .ssrf import TargetRejected, validate_target
from .store import (
    QUEUE_KEY,
    STATE_COMPLETED,
    STATE_FAILED,
    WORKER_HEARTBEAT_KEY,
    ScanStore,
)

LOGGER = logging.getLogger("check_opencloud.web")

OUTPUT_FORMATS = ("dashboard", "json", "csv", "sarif")

# Only these arrive from a form or a JSON body. Anything else is a request
# trying to reach a knob it is not allowed to touch, and saying so plainly is
# better than quietly scanning with settings the visitor thinks they chose.
ALLOWED_FIELDS = frozenset(
    {"target_url", "ignore_hardenings", "output_format", "release_track"}
)

PROJECT_URL = "https://github.com/sowoi/check-opencloud-security"

# A rate limit is not a refusal, it is a queue nobody wants to stand in.
# Whoever hits one is exactly the person who should know the whole check is
# open source and runs happily on their own machine, against their own
# instance, with no limits at all.
SELF_HOST_HINT = (
    "No hard feelings - this is a small service and the limits keep it "
    "on its feet. The scanner is open source, so you can run exactly this "
    "check yourself, as often as you like: {url}."
)

# One marker per field rather than one shared instance: FastAPI attaches the
# parameter's name and annotation to whatever it is given.
_TARGET_URL_FIELD = Form(default=None)
_WAIVER_FIELD = Form(default=None)
_FORMAT_FIELD = Form(default=None)
_TRACK_FIELD = Form(default=None)

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; font-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'; "
        "object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(), interest-cohort=()",
    # Nothing here is worth a cache: a result page is somebody's scan.
    "Cache-Control": "no-store",
}

# Swagger UI and ReDoc load their bundle from jsDelivr. The relaxation is
# scoped to those two pages, applies only when an operator asked for them, and
# never touches the pages a visitor sees.
DOCS_PATHS = frozenset({"/docs", "/redoc"})
# Everything still comes from this origin. Swagger UI and ReDoc both write
# styles into the document as they render, and ReDoc builds its highlighter in
# a blob worker, which is the whole of the difference from the policy above.
DOCS_CSP = (
    "default-src 'self'; img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; script-src 'self'; "
    "worker-src 'self' blob:; connect-src 'self'; font-src 'self'; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
)


# FastAPI's own Swagger page starts the bundle from an inline <script>, which
# the policy above blocks - that is what left /docs blank. The same call lives
# in a served file instead, so nothing on this page is inline.
SWAGGER_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>check-opencloud-security - API</title>
<link rel="icon" href="/static/img/logo.svg" sizes="any" type="image/svg+xml">
<link rel="stylesheet" href="/static/vendor/swagger-ui.css">
</head>
<body>
<div id="swagger-ui" data-openapi-url="/openapi.json"></div>
<script src="/static/vendor/swagger-ui-bundle.js"></script>
<script src="/static/js/docs.js"></script>
</body>
</html>
"""


def frontend_dir() -> Path:
    """Where the templates and static assets live."""
    override = os.environ.get("COS_WEB_FRONTEND_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "frontend"


class _Rejected(Exception):
    """A submission that cannot become a scan, with the reason to show."""

    def __init__(
        self,
        message: str,
        status: int = 400,
        retry_after: int = 0,
        self_host: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.retry_after = retry_after
        self.self_host = self_host
        """Whether to point the visitor at running the check themselves."""


def client_address(request: Request, settings: WebSettings) -> str:
    """
    The address the client rate limit counts against.

    ``X-Forwarded-For`` is only believed when the deployment says it sits
    behind a proxy that overwrites it. Believing it by default would make the
    limit a suggestion.
    """
    if settings.trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def wants_html(request: Request) -> bool:
    """Whether this submission came from the form rather than from a client."""
    accept = request.headers.get("accept", "")
    return "text/html" in accept and "application/json" not in accept


def is_safe_link(value: Any) -> bool:
    """Whether a value may be rendered as an ``href``.

    Advisory URLs come from a database, and today that database is the
    bundled one. The day a remote feed is read instead, a
    ``javascript:`` URL in it would become stored cross-site scripting on
    somebody else's result page, so the scheme is checked rather than
    trusted.
    """
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    return candidate.lower().startswith(("https://", "http://"))


def create_app(settings: WebSettings | None = None) -> FastAPI:
    """Build the application. One call, one set of settings, no globals."""
    settings = settings or WebSettings.from_env()
    root = frontend_dir()
    templates = Jinja2Templates(directory=str(root / "templates"))
    templates.env.tests["safe_link"] = is_safe_link

    @asynccontextmanager
    async def lifespan(instance: FastAPI) -> AsyncIterator[None]:
        yield
        if instance.state.queue is not None:  # pragma: no cover - teardown
            await instance.state.queue.close()
        await instance.state.backend.close()

    # The schema, Swagger UI and ReDoc are opt-in. FastAPI's own pages load
    # their JavaScript from a CDN, which this service does not do and which
    # leaves a blank page anywhere that CDN is unreachable, so the two pages
    # below are served with the copies in frontend/static/vendor/ instead.
    app = FastAPI(
        title="check-opencloud-security",
        summary="Public security scan service for OpenCloud instances",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
        lifespan=lifespan,
    )
    if settings.enable_docs:
        LOGGER.warning("api_docs_enabled")

        @app.get("/docs", include_in_schema=False)
        async def swagger_ui() -> Response:
            return HTMLResponse(SWAGGER_PAGE)

        @app.get("/redoc", include_in_schema=False)
        async def redoc_ui() -> Response:
            return get_redoc_html(
                openapi_url="/openapi.json",
                title="check-opencloud-security - API",
                redoc_js_url="/static/vendor/redoc.standalone.js",
                redoc_favicon_url="/static/img/logo.svg",
                with_google_fonts=False,
            )

    app.mount("/static", StaticFiles(directory=str(root / "static")), name="static")

    app.state.settings = settings
    app.state.backend = create_backend(settings.redis_url)
    app.state.store = ScanStore(
        backend=app.state.backend,
        ttl=settings.result_ttl,
        encryption_config=settings if settings.encrypt_results else None,
    )
    app.state.limiter = RateLimiter(
        backend=app.state.backend,
        client_limit=settings.ip_rate_limit,
        client_window=settings.ip_rate_window,
        target_cooldown=settings.target_cooldown,
    )
    app.state.queue = None

    async def queue() -> ScanQueue:
        if app.state.queue is None:
            app.state.queue = await create_queue(settings)
        return app.state.queue

    @app.middleware("http")
    async def _security_headers(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if settings.enable_docs and request.url.path in DOCS_PATHS:
            response.headers["Content-Security-Policy"] = DOCS_CSP
        return response

    def page(request: Request, name: str, context: dict[str, Any], status: int = 200):
        payload = {
            "version": __version__,
            "project_url": PROJECT_URL,
            "result_ttl_minutes": max(1, settings.result_ttl // 60),
            "docs_enabled": settings.enable_docs,
            "limits": {
                "client": settings.ip_rate_limit,
                "window_minutes": max(1, settings.ip_rate_window // 60),
                "cooldown_minutes": max(1, settings.target_cooldown // 60),
                "cooldown": settings.target_cooldown,
            },
            **context,
        }
        return templates.TemplateResponse(request, name, payload, status_code=status)

    def not_found(request: Request) -> Response:
        if wants_html(request):
            return page(request, "404.html", {}, status=404)
        return JSONResponse({"detail": "Not found."}, status_code=404)

    async def accept_submission(
        request: Request,
        target_url: str,
        ignore_hardenings: object,
        output_format: str,
        release_track: object,
        extra_fields: set[str],
    ) -> str:
        """Validate, rate-limit, register and enqueue. Returns the new uuid."""
        if extra_fields:
            raise _Rejected(
                "This service does not accept "
                f"{', '.join(sorted(extra_fields))}. The scan runs with "
                "server-side settings only.",
                status=422,
            )

        limiter: RateLimiter = app.state.limiter
        store: ScanStore = app.state.store

        client = await limiter.check_client(client_address(request, settings))
        if not client.allowed:
            raise _Rejected(
                "That is a lot of scans from your network in a short time. "
                "Give it a minute and try again.",
                status=429,
                retry_after=client.retry_after,
                self_host=True,
            )

        try:
            target = validate_target(
                target_url,
                allow_private=settings.allow_private_targets,
                allowed_hosts=settings.extra_hosts_allowed,
            )
        except TargetRejected as exc:
            raise _Rejected(str(exc), status=400) from exc

        waivers = sanitize_waivers(ignore_hardenings)
        chosen_format = output_format if output_format in OUTPUT_FORMATS else "dashboard"
        chosen_track = sanitize_release_track(release_track)

        cooldown = await limiter.check_target(target.hostname)
        if not cooldown.allowed:
            raise _Rejected(
                "That instance was scanned very recently. "
                "Please give it a few minutes.",
                status=429,
                retry_after=cooldown.retry_after,
                self_host=True,
            )

        identifier = str(uuid_module.uuid4())
        await store.create(
            identifier,
            target=target.display,
            ignore_hardenings=waivers,
            output_format=chosen_format,
            release_track=chosen_track,
        )
        await (await queue()).enqueue(identifier)
        LOGGER.info("scan_created %s", identifier)
        return identifier

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Response:
        return page(
            request,
            "index.html",
            {
                "waivers": waiver_options(),
                "tracks": release_track_options(),
                "release_track": DEFAULT_RELEASE_TRACK,
                "error": None,
                "error_self_host": False,
                "target_url": "",
            },
        )

    # The browser form posts to "/" and the API to "/api/scans". They are the
    # same handler: a submission that fails validation is re-rendered at the
    # URL it was sent to, and a person who then reloads the page should get
    # the form back rather than a method-not-allowed from an API path.
    @app.post("/", response_class=HTMLResponse)
    @app.post("/api/scans")
    async def create_scan(
        request: Request,
        target_url: str | None = _TARGET_URL_FIELD,
        ignore_hardenings: list[str] | None = _WAIVER_FIELD,
        output_format: str | None = _FORMAT_FIELD,
        release_track: str | None = _TRACK_FIELD,
    ) -> Response:
        html = wants_html(request)
        body: dict[str, Any] = {}
        if not html and request.headers.get("content-type", "").startswith(
            "application/json"
        ):
            try:
                parsed = await request.json()
            except ValueError:
                parsed = None
            body = parsed if isinstance(parsed, dict) else {}

        submitted_url = body.get("target_url", target_url) or ""
        submitted_waivers: object = body.get("ignore_hardenings", ignore_hardenings)
        submitted_format = str(body.get("output_format", output_format) or "dashboard")
        submitted_track = body.get("release_track", release_track)
        extra = set(body) - ALLOWED_FIELDS
        if html or not body:
            form = await _form_fields(request)
            extra |= form - ALLOWED_FIELDS

        try:
            identifier = await accept_submission(
                request,
                str(submitted_url),
                submitted_waivers,
                submitted_format,
                submitted_track,
                extra,
            )
        except _Rejected as exc:
            if html:
                response = page(
                    request,
                    "index.html",
                    {
                        "waivers": waiver_options(),
                        "tracks": release_track_options(),
                        "release_track": sanitize_release_track(submitted_track),
                        "error": exc.message,
                        "error_self_host": exc.self_host,
                        "target_url": str(submitted_url),
                    },
                    status=exc.status,
                )
            else:
                detail: dict[str, Any] = {"detail": exc.message}
                if exc.self_host:
                    detail["hint"] = SELF_HOST_HINT.format(url=PROJECT_URL)
                    detail["selfHostUrl"] = PROJECT_URL
                response = JSONResponse(detail, status_code=exc.status)
            if exc.retry_after:
                response.headers["Retry-After"] = str(exc.retry_after)
            return response

        if html:
            return RedirectResponse(f"/scan/{identifier}", status_code=303)
        return JSONResponse(
            {"uuid": identifier, "state": "queued", "url": f"/scan/{identifier}"},
            status_code=202,
            headers={"Location": f"/scan/{identifier}"},
        )

    # Nothing is listed here - the uuid is the only way to reach a scan, and
    # there is no endpoint that enumerates them. This exists so that a browser
    # pointed at the API path lands on the form instead of a bare 405.
    @app.get("/api/scans")
    async def scans_entry_point() -> Response:
        return RedirectResponse("/", status_code=303)

    @app.get("/scan/{identifier}", response_class=HTMLResponse)
    async def scan_page(request: Request, identifier: str) -> Response:
        record = await app.state.store.get(identifier)
        if record is None:
            return page(request, "404.html", {}, status=404)
        return page(
            request,
            "scan.html",
            {
                "scan": record.as_dict(),
                "summary": summarise(record.result) if record.result else None,
            },
        )

    @app.get("/api/scans/{identifier}")
    async def scan_state(request: Request, identifier: str) -> Response:
        record = await app.state.store.get(identifier)
        if record is None:
            return JSONResponse({"detail": "Not found."}, status_code=404)
        
        output_format = record.metadata.get("outputFormat", "json")
        
        if record.state == STATE_COMPLETED and record.result is not None:
            if output_format == "csv":
                csv_content = csv_report(record.result)
                return Response(csv_content, media_type="text/csv")
            elif output_format == "sarif":
                sarif_data = sarif_report(record.result)
                return JSONResponse(sarif_data, media_type="application/sarif+json")
        
        payload = record.as_dict()
        if record.state == STATE_COMPLETED and record.result is not None:
            payload["summary"] = summarise(record.result)
        if record.state in {STATE_COMPLETED, STATE_FAILED}:
            payload["done"] = True
        return JSONResponse(payload)

    @app.get("/healthz")
    async def healthz() -> Response:
        try:
            health = await app.state.backend.health(QUEUE_KEY, WORKER_HEARTBEAT_KEY)
        except RedisUnavailable:
            health = None
        if health is None or not health.worker_alive:
            return JSONResponse(
                {"status": "unavailable", "version": __version__}, status_code=503
            )
        return JSONResponse(
            {
                "status": "ok",
                "version": __version__,
                "queueDepth": health.queue_depth,
                "worker": "ok",
            }
        )

    @app.exception_handler(404)
    async def _handle_404(request: Request, exc: Exception) -> Response:
        return not_found(request)

    return app


async def _form_fields(request: Request) -> set[str]:
    """The field names a form submission actually carried."""
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith(
        ("application/x-www-form-urlencoded", "multipart/form-data")
    ):
        return set()
    try:
        form = await request.form()
    except (ValueError, RuntimeError):  # pragma: no cover - malformed body
        return set()
    return set(form.keys())


def __getattr__(name: str) -> Any:
    """
    Build the ASGI application on first access to ``webapp.app:app``.

    Importing this module must not open a Redis connection or require the
    driver to be installed: the worker imports it for its job function, and
    the tests import it to build an app against ``memory://``. Only an ASGI
    server asking for ``app`` actually wires anything up.
    """
    if name == "app":
        instance = create_app()
        globals()["app"] = instance
        return instance
    raise AttributeError(name)
