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

import hmac
import importlib.util
import json
import logging
import os
import uuid as uuid_module
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from opencloud_local_scan import __version__

from .advisories import advisory_catalogue, advisory_state, stored_database
from .arazzo import arazzo_document
from .audit import (
    REASON_BATCH_TOO_LARGE,
    REASON_PURGE_UNAUTHORISED,
    REASON_RATE_LIMIT_CLIENT,
    REASON_RATE_LIMIT_TARGET,
    REASON_TARGET_REJECTED,
    REASON_UNSUPPORTED_FIELDS,
    AuditLog,
    configure_audit_file,
)
from .catalog import (
    DEFAULT_RELEASE_TRACK,
    SEVERITY_TAGS,
    check_catalogue,
    grade_scale,
    release_track_options,
    sanitize_release_track,
    sanitize_waivers,
    severity_caps,
    summarise,
    waiver_options,
)
from .discovery import (
    ARAZZO_PATH,
    DISCOVERY_PATH,
    MCP_PATH,
    OPENAPI_MEDIA_TYPE,
    OPENAPI_PATH,
    discovery_document,
)
from .documentation import DOCUMENTATION_BY_SLUG, DOCUMENTATION_PAGES
from .encryption import ensure_encryption_ready
from .export_signing import SIGNATURE_HEADER, sign_bytes
from .i18n import (
    DEFAULT_LOCALE,
    LANGUAGE_COOKIE,
    LANGUAGE_COOKIE_MAX_AGE,
    LANGUAGE_PATH,
    Translator,
    locale_for_request,
    locale_options,
    normalise_locale,
    safe_next_path,
)
from .mcp_auth import (
    PROTECTED_RESOURCE_PATH,
    auth_required,
    discovery_authentication,
    ensure_mcp_auth_ready,
    protected_resource_metadata,
)
from .openapi import openapi_document
from .purge import PurgeRejected, build_receipt, normalise_target
from .queue import ScanQueue, create_queue
from .ratelimit import RateLimiter
from .redis_backend import RedisUnavailable, create_backend
from .reports import (
    EXPORT_FORMATS,
    MEDIA_TYPES,
    csv_report,
    export_filename,
    pdf_report,
    sarif_report,
)
from .schedule import schedule_state
from .seo import (
    AGENTS_JSON_PATH,
    AGENTS_TXT_PATH,
    LEGAL_NOTICE_PATH,
    LLMS_FULL_PATH,
    LLMS_PATH,
    OG_IMAGE_PATH,
    SECURITY_CONTACT_EMAIL,
    SECURITY_TXT_PATH,
    SITE_NAME,
    agents_txt,
    canonical_url,
    is_indexable,
    robots_txt,
    security_txt,
    serves_legal_notice,
    site_origin,
    sitemap_xml,
    validate_public_base_url,
    wants_robots_tag,
)
from .settings import WebSettings
from .ssrf import TargetRejected, validate_target
from .store import (
    QUEUE_KEY,
    STATE_COMPLETED,
    STATE_FAILED,
    WORKER_HEARTBEAT_KEY,
    ScanRecord,
    ScanStore,
)

LOGGER = logging.getLogger("check_opencloud.web")


def mcp_available() -> bool:
    """Whether the optional ``mcp`` extra is installed in this environment."""
    return importlib.util.find_spec("mcp") is not None

OUTPUT_FORMATS = ("dashboard", "json", "csv", "sarif", "pdf")

# Only these arrive from a form or a JSON body. Anything else is a request
# trying to reach a knob it is not allowed to touch, and saying so plainly is
# better than quietly scanning with settings the visitor thinks they chose.
ALLOWED_FIELDS = frozenset(
    {"target_url", "ignore_hardenings", "output_format", "release_track"}
)

# The batch endpoint swaps one target for many and changes nothing else: the
# same four facts about a scan, never a fifth about how hard to run it.
BATCH_ALLOWED_FIELDS = frozenset(
    {"targets", "ignore_hardenings", "output_format", "release_track"}
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
_LOCALE_FIELD = Form(default="")
_NEXT_FIELD = Form(default="/", alias="next")

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
        key: str = "",
        params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.retry_after = retry_after
        self.self_host = self_host
        """Whether to point the visitor at running the check themselves."""
        self.key = key
        """The catalogue identifier for the same sentence, for the page."""
        self.params = params or {}

    def translated(self, translate: Translator) -> str:
        """The message for a browser. The API keeps the English one."""
        if self.key and translate.has(self.key):
            return translate(self.key, **self.params)
        return self.message


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


def _default_locale_context() -> dict[str, Any]:
    """The English translator every template starts from.

    A page render supplies its own, negotiated for the visitor. These globals
    exist so a template rendered outside a request - a test, a preview, the
    search index generator - still has a working ``t``.
    """
    translate = Translator(DEFAULT_LOCALE)
    return {
        "t": translate,
        "locale": translate.locale,
        "locales": locale_options(translate.locale),
        "language_path": LANGUAGE_PATH,
        "language_next": "/",
    }


def build_templates(directory: Path | None = None) -> Jinja2Templates:
    """The Jinja environment the templates are written against.

    One place, so a render outside the application - a test, the search index
    generator - gets the same tests and the same English fallback the website
    does rather than a template that only works in one of them.
    """
    root = directory or (frontend_dir() / "templates")
    templates = Jinja2Templates(directory=str(root))
    templates.env.tests["safe_link"] = is_safe_link
    # English is what a render falls back to when nobody negotiated a
    # language, so a template is never one missing context variable away from
    # an exception.
    templates.env.globals.update(_default_locale_context())
    return templates


def create_app(settings: WebSettings | None = None) -> FastAPI:
    """Build the application. One call, one set of settings, no globals."""
    settings = settings or WebSettings.from_env()
    validate_public_base_url(settings.public_base_url)
    root = frontend_dir()
    templates = build_templates(root / "templates")
    llms_text = (root / "static" / "llms.txt").read_text(encoding="utf-8")
    llms_full_text = (root / "static" / "llms-full.txt").read_text(encoding="utf-8")
    # The MCP extra is optional: a deployment that only wants the website
    # should not be made to install an agent runtime, and one that installed
    # it should not have to remember a second switch.
    mcp_enabled = settings.enable_mcp and mcp_available()

    @asynccontextmanager
    async def lifespan(instance: FastAPI) -> AsyncIterator[None]:
        # A mounted sub-application's own lifespan is never run by Starlette,
        # so the MCP session manager is started here or not at all.
        manager = getattr(instance.state, "mcp_server", None)
        if manager is None:
            yield
        else:
            async with manager.session_manager.run():
                yield
        if instance.state.queue is not None:  # pragma: no cover - teardown
            await instance.state.queue.close()
        await instance.state.backend.close()

    # The machine-readable documents are always public. An agent handed only
    # this service's address has to be able to read what it can do, and a
    # contract nobody can fetch is not a contract. The two *browsable* pages
    # stay opt-in: they are a convenience for an operator, not part of the
    # service.
    app = FastAPI(
        title="check-opencloud-security",
        summary="Public security scan service for OpenCloud instances",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    # Written by hand in webapp/openapi.py, because the generated one
    # describes the browser form rather than the API: form fields where a
    # client sends JSON, 200 where the handler answers 202, and no shape at
    # all for a scan record.
    def _openapi(request: Request | None = None) -> dict[str, Any]:
        origin = (
            site_origin(str(request.base_url), settings.public_base_url)
            if request is not None
            else (settings.public_base_url or "")
        )
        return openapi_document(server_url=origin or None)

    app.openapi = _openapi  # type: ignore[method-assign]

    @app.get(OPENAPI_PATH, include_in_schema=False)
    async def openapi_schema(request: Request) -> Response:
        """The API contract. Public, because an agent has to read it."""
        return JSONResponse(
            _openapi(request),
            media_type=OPENAPI_MEDIA_TYPE,
            headers={"Cache-Control": "public, max-age=300"},
        )

    @app.get(ARAZZO_PATH, include_in_schema=False)
    async def arazzo(request: Request) -> Response:
        """The workflow description, next to the schema it builds on."""
        origin = site_origin(str(request.base_url), settings.public_base_url)
        return JSONResponse(
            arazzo_document(openapi_url=f"{origin}{OPENAPI_PATH}"),
            headers={"Cache-Control": "public, max-age=300"},
        )

    @app.get(DISCOVERY_PATH, include_in_schema=False)
    async def ai_discovery(request: Request) -> Response:
        """
        Where an agent that knows only the domain starts.

        Not a registered standard, and it does not pretend to be: an explicit
        application-level document naming the OpenAPI description, the Arazzo
        workflows and the MCP endpoint, so that none of the three has to be
        guessed at.
        """
        origin = site_origin(str(request.base_url), settings.public_base_url)
        return JSONResponse(
            discovery_document(
                origin,
                mcp_enabled=mcp_enabled,
                mcp_auth=discovery_authentication(settings),
            ),
            headers={"Cache-Control": "public, max-age=300"},
        )

    if auth_required(settings):

        @app.get(PROTECTED_RESOURCE_PATH, include_in_schema=False)
        async def protected_resource() -> Response:
            """
            RFC 9728: which authorisation server issues tokens for /mcp.

            Served here rather than only inside the mounted sub-application,
            because a client reads it at the origin - the path is derived
            from the resource URL, not from wherever this service happens to
            mount its endpoint.
            """
            return JSONResponse(
                protected_resource_metadata(settings),
                headers={"Cache-Control": "public, max-age=300"},
            )

    if settings.enable_docs:
        LOGGER.warning("api_docs_enabled")

        @app.get("/docs", include_in_schema=False)
        async def swagger_ui() -> Response:
            return HTMLResponse(SWAGGER_PAGE)

        @app.get("/redoc", include_in_schema=False)
        async def redoc_ui() -> Response:
            return get_redoc_html(
                openapi_url=OPENAPI_PATH,
                title="check-opencloud-security - API",
                redoc_js_url="/static/vendor/redoc.standalone.js",
                redoc_favicon_url="/static/img/logo.svg",
                with_google_fonts=False,
            )

    app.mount("/static", StaticFiles(directory=str(root / "static")), name="static")

    app.state.settings = settings
    app.state.backend = create_backend(settings.redis_url)
    # Before anything can be written: a deployment that asked for encryption
    # and cannot do it must fail here rather than store results in the clear.
    ensure_encryption_ready(settings)
    # And before anything can be served: a deployment that asked for a
    # sign-in on /mcp and cannot enforce one must not come up open.
    ensure_mcp_auth_ready(settings)
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
    app.state.audit = AuditLog.from_settings(settings)
    # And before the first record: a deployment that asked for the trail to
    # outlive the container must fail here rather than write it to a stream
    # that ends with the container.
    audit_file = configure_audit_file(settings)
    if settings.audit_log:
        LOGGER.info(
            "audit_log_enabled targets=%s file=%s",
            settings.audit_log_targets,
            audit_file or "-",
        )

    async def queue() -> ScanQueue:
        if app.state.queue is None:
            app.state.queue = await create_queue(settings)
        return app.state.queue

    @app.middleware("http")
    async def _security_headers(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        # The meta tag only covers a rendered page. A result export, a JSON
        # body or a redirect needs saying in the header, or a crawler that
        # reached a uuid would keep it.
        if wants_robots_tag(request.url.path, allow_indexing=settings.allow_indexing):
            response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        if settings.enable_docs and request.url.path in DOCS_PATHS:
            response.headers["Content-Security-Policy"] = DOCS_CSP
        return response

    def translator_for(request: Request) -> Translator:
        """The catalogue this visitor reads, cookie first, then the browser."""
        return Translator(locale_for_request(request))

    def page(request: Request, name: str, context: dict[str, Any], status: int = 200):
        origin = site_origin(str(request.base_url), settings.public_base_url)
        indexable = is_indexable(
            request.url.path, allow_indexing=settings.allow_indexing, status=status
        )
        translate = context.get("t")
        if not isinstance(translate, Translator):
            translate = translator_for(request)
        payload = {
            "version": __version__,
            "project_url": PROJECT_URL,
            "result_ttl_minutes": max(1, settings.result_ttl // 60),
            "docs_enabled": settings.enable_docs,
            "mcp_enabled": mcp_enabled,
            "mcp_url": f"{origin}{MCP_PATH}" if origin else MCP_PATH,
            "site_name": SITE_NAME,
            # The footer only offers the legal notice where the legal notice
            # is actually served.
            "legal_notice_path": (
                LEGAL_NOTICE_PATH
                if serves_legal_notice(request.url.hostname)
                else None
            ),
            # `max-image-preview:large`/`max-snippet:-1` opt back into the
            # full-size thumbnail and snippet length Google caps by default
            # since 2019 - no reason to take the smaller default on a page
            # that is indexable at all.
            "robots": (
                "index, follow, max-image-preview:large, max-snippet:-1"
                if indexable
                else "noindex, nofollow"
            ),
            # A canonical URL for a page nobody may index would only invite
            # one to be created.
            "canonical_url": (
                canonical_url(origin, request.url.path) if indexable else None
            ),
            "origin": origin,
            "og_image": f"{origin}{OG_IMAGE_PATH}",
            "limits": {
                "client": settings.ip_rate_limit,
                "window_minutes": max(1, settings.ip_rate_window // 60),
                "cooldown_minutes": max(1, settings.target_cooldown // 60),
                "cooldown": settings.target_cooldown,
            },
            "t": translate,
            "locale": translate.locale,
            "locales": locale_options(translate.locale),
            "language_path": LANGUAGE_PATH,
            # Where the switcher returns to. The path only, validated as a
            # local one: a result page keeps its uuid out of the query string
            # and therefore out of anybody's referrer.
            "language_next": safe_next_path(request.url.path),
            "webmcp_tools": (),
            **context,
        }
        response = templates.TemplateResponse(request, name, payload, status_code=status)
        # The same URL answers in four languages, chosen from a header and a
        # cookie. A cache that ignored either would serve one visitor's
        # language to the next.
        response.headers["Vary"] = "Accept-Language, Cookie"
        return response

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
        limiter: RateLimiter = app.state.limiter
        store: ScanStore = app.state.store
        audit: AuditLog = app.state.audit
        address = client_address(request, settings)

        if extra_fields:
            audit.submission_rejected(
                client=address,
                reason=REASON_UNSUPPORTED_FIELDS,
                status=422,
                fields=tuple(extra_fields),
            )
            raise _Rejected(
                "This service does not accept "
                f"{', '.join(sorted(extra_fields))}. The scan runs with "
                "server-side settings only.",
                status=422,
                key="error.unsupported_fields",
                params={"fields": ", ".join(sorted(extra_fields))},
            )

        client = await limiter.check_client(address)
        if not client.allowed:
            audit.rate_limited(
                client=address,
                scope=REASON_RATE_LIMIT_CLIENT,
                retry_after=client.retry_after,
            )
            raise _Rejected(
                "That is a lot of scans from your network in a short time. "
                "Give it a minute and try again.",
                status=429,
                retry_after=client.retry_after,
                self_host=True,
                key="error.rate_limit.client",
            )

        try:
            target = validate_target(
                target_url,
                allow_private=settings.allow_private_targets,
                allowed_hosts=settings.extra_hosts_allowed,
            )
        except TargetRejected as exc:
            audit.submission_rejected(
                client=address,
                reason=REASON_TARGET_REJECTED,
                status=400,
            )
            raise _Rejected(
                str(exc), status=400, key=getattr(exc, "key", "")
            ) from exc

        waivers = sanitize_waivers(ignore_hardenings)
        chosen_format = output_format if output_format in OUTPUT_FORMATS else "dashboard"
        chosen_track = sanitize_release_track(release_track)

        cooldown = await limiter.check_target(target.hostname)
        if not cooldown.allowed:
            audit.rate_limited(
                client=address,
                scope=REASON_RATE_LIMIT_TARGET,
                retry_after=cooldown.retry_after,
                target=target.hostname,
            )
            raise _Rejected(
                "That instance was scanned very recently. "
                "Please give it a few minutes.",
                status=429,
                retry_after=cooldown.retry_after,
                self_host=True,
                key="error.rate_limit.target",
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
        audit.scan_requested(
            identifier=identifier,
            client=address,
            target=target.hostname,
            output_format=chosen_format,
            release_track=chosen_track,
            waivers=len(waivers),
        )
        return identifier

    def index_context(
        translate: Translator,
        *,
        release_track: str = DEFAULT_RELEASE_TRACK,
        error: str | None = None,
        error_self_host: bool = False,
        target_url: str = "",
    ) -> dict[str, Any]:
        """The form and its WebMCP schema, both from the same catalogues."""
        waivers = waiver_options(translate)
        tracks = release_track_options(translate)
        return {
            "t": translate,
            "waivers": waivers,
            "tracks": tracks,
            "release_track": release_track,
            "error": error,
            "error_self_host": error_self_host,
            "target_url": target_url,
            "index_meta_tags": settings.index_meta_tags,
            "webmcp_tools": (
                {
                    "action": "scan",
                    "endpoint": "/api/scans",
                    "name": "scan_opencloud_security",
                    "title": "Scan OpenCloud security",
                    "description": (
                        "Queue a security scan for a public OpenCloud instance. "
                        "Returns a capability UUID and result-page URL; the scan "
                        "continues asynchronously."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["target_url"],
                        "properties": {
                            "target_url": {
                                "type": "string",
                                "description": "Public OpenCloud base URL or hostname.",
                            },
                            "release_track": {
                                "type": "string",
                                "enum": [track.id for track in tracks],
                                "default": DEFAULT_RELEASE_TRACK,
                            },
                            "output_format": {
                                "type": "string",
                                "enum": list(OUTPUT_FORMATS),
                                "default": "dashboard",
                            },
                            "ignore_hardenings": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "enum": [option.id for option in waivers],
                                },
                                "uniqueItems": True,
                                "default": [],
                            },
                        },
                    },
                    "annotations": {
                        "readOnlyHint": False,
                        "untrustedContentHint": True,
                    },
                },
            )
            if mcp_enabled
            else (),
        }

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Response:
        translate = translator_for(request)
        return page(request, "index.html", index_context(translate))

    # The landing page carries the form; the prose that used to sit under it
    # lives on these pages, so the first screen stays about scanning.
    @app.get("/how-it-works", response_class=HTMLResponse, include_in_schema=False)
    async def how_it_works(request: Request) -> Response:
        return page(request, "how-it-works.html", {})

    @app.get("/grades", response_class=HTMLResponse, include_in_schema=False)
    async def grades(request: Request) -> Response:
        translate = translator_for(request)
        return page(
            request,
            "grades.html",
            {
                "t": translate,
                "grades": grade_scale(translate),
                "caps": severity_caps(),
                "severity_tags": SEVERITY_TAGS,
            },
        )

    @app.get("/catalogue", response_class=HTMLResponse, include_in_schema=False)
    async def catalogue(request: Request) -> Response:
        translate = translator_for(request)
        database = await stored_database(app.state.backend, settings)
        return page(
            request,
            "catalogue.html",
            {
                "t": translate,
                "categories": check_catalogue(translate),
                "advisories": advisory_catalogue(database),
                "severity_tags": SEVERITY_TAGS,
            },
        )

    @app.get("/documentation", response_class=HTMLResponse, include_in_schema=False)
    async def documentation(request: Request) -> Response:
        return page(
            request,
            "documentation.html",
            {"documentation_pages": DOCUMENTATION_PAGES},
        )

    @app.get(
        "/documentation/{slug}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def documentation_page(request: Request, slug: str) -> Response:
        selected = DOCUMENTATION_BY_SLUG.get(slug)
        if selected is None:
            return not_found(request)
        return page(request, f"docs/{selected.slug}.html", {})

    @app.get("/search", response_class=HTMLResponse, include_in_schema=False)
    async def search_page(request: Request) -> Response:
        return page(request, "search.html", {})

    @app.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
    async def privacy(request: Request) -> Response:
        return page(request, "privacy.html", {})

    # Somebody else's deployment is not covered by this notice and must not
    # appear to be, so anywhere but the host it names, the page does not exist.
    @app.get(LEGAL_NOTICE_PATH, response_class=HTMLResponse, include_in_schema=False)
    async def legal_notice(request: Request) -> Response:
        if not serves_legal_notice(request.url.hostname):
            return not_found(request)
        return page(request, "legal-notice.html", {})

    @app.get("/api", response_class=HTMLResponse, include_in_schema=False)
    async def api_page(request: Request) -> Response:
        return page(request, "api.html", {})

    @app.get("/ai", response_class=HTMLResponse, include_in_schema=False)
    async def ai_page(request: Request) -> Response:
        return page(request, "ai.html", {})

    # The Docker page - for the visitor who would rather not hand an address
    # to a stranger's server at all - is now the first half of /documentation,
    # since somebody looking for how to run the check should not have to pick
    # between two tabs that both answer that. The path stays as a permanent
    # redirect: it is printed in released documentation and indexed.
    @app.get("/cli", include_in_schema=False)
    async def cli_page() -> Response:
        return RedirectResponse("/documentation#oneliner", status_code=301)

    @app.get("/about", response_class=HTMLResponse, include_in_schema=False)
    async def about(request: Request) -> Response:
        return page(request, "about.html", {})

    # The switcher is a form, so it works with JavaScript switched off, and it
    # is a POST, so no link anywhere can change somebody's language for them.
    # What comes back is a cookie and a redirect to the page they were on -
    # the path only, validated as a local one, with the query string dropped.
    # A scan uuid therefore never travels through here.
    @app.post(LANGUAGE_PATH, include_in_schema=False)
    async def choose_language(
        request: Request,
        locale: str = _LOCALE_FIELD,
        next_path: str = _NEXT_FIELD,
    ) -> Response:
        chosen = normalise_locale(locale)
        destination = safe_next_path(next_path)
        response = RedirectResponse(destination, status_code=303)
        if chosen is not None:
            response.set_cookie(
                LANGUAGE_COOKIE,
                chosen,
                max_age=LANGUAGE_COOKIE_MAX_AGE,
                path="/",
                httponly=True,
                samesite="lax",
                secure=request.url.scheme == "https",
            )
        # Which language somebody reads in is not a scan and not evidence:
        # it is written to their cookie and to nothing else here.
        return response

    # Two files a crawler asks for before anything else. Both are generated:
    # the sitemap from the page list in `seo.py` and the template mtimes, so
    # it cannot drift from the pages that actually exist.
    @app.get("/robots.txt", include_in_schema=False)
    async def robots(request: Request) -> Response:
        origin = site_origin(str(request.base_url), settings.public_base_url)
        return PlainTextResponse(
            robots_txt(origin, allow_indexing=settings.allow_indexing),
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @app.get(AGENTS_TXT_PATH, include_in_schema=False)
    async def agents(request: Request) -> Response:
        """Capability declaration for autonomous agents, per agents-txt.com."""
        origin = site_origin(str(request.base_url), settings.public_base_url)
        return PlainTextResponse(
            agents_txt(
                origin,
                allow_indexing=settings.allow_indexing,
                mcp_enabled=mcp_enabled,
                mcp_auth_required=mcp_enabled and auth_required(settings),
            ),
            headers={
                "Cache-Control": "public, max-age=3600",
                "Access-Control-Allow-Origin": "*",
            },
        )

    @app.get(AGENTS_JSON_PATH, include_in_schema=False)
    async def agents_json(request: Request) -> Response:
        """
        The structured sibling agents-txt.com recommends alongside the
        plain-text file - the same document `/.well-known/ai.json` serves,
        under the name that convention looks for.
        """
        origin = site_origin(str(request.base_url), settings.public_base_url)
        return JSONResponse(
            discovery_document(
                origin,
                mcp_enabled=mcp_enabled,
                mcp_auth=discovery_authentication(settings),
            ),
            headers={
                "Cache-Control": "public, max-age=300",
                "Access-Control-Allow-Origin": "*",
            },
        )

    @app.get(SECURITY_TXT_PATH, include_in_schema=False)
    async def security(request: Request) -> Response:
        """RFC 9116: how to report a flaw in this service, not in OpenCloud."""
        origin = site_origin(str(request.base_url), settings.public_base_url)
        contact = (
            SECURITY_CONTACT_EMAIL
            if serves_legal_notice(request.url.hostname)
            else None
        )
        return PlainTextResponse(
            security_txt(origin, operator_contact=contact),
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @app.get(LLMS_PATH, include_in_schema=False)
    async def llms() -> Response:
        """A short, stable map of the service for language-model clients."""
        return PlainTextResponse(
            llms_text,
            headers={"Cache-Control": "public, max-age=300"},
        )

    @app.get(LLMS_FULL_PATH, include_in_schema=False)
    async def llms_full() -> Response:
        return PlainTextResponse(
            llms_full_text,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @app.get("/sitemap.xml", include_in_schema=False)
    async def sitemap(request: Request) -> Response:
        if not settings.allow_indexing:
            return not_found(request)
        origin = site_origin(str(request.base_url), settings.public_base_url)
        return Response(
            sitemap_xml(origin, root / "templates"),
            media_type="application/xml",
            headers={"Cache-Control": "public, max-age=3600"},
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
        html_requested = wants_html(request)
        body: dict[str, Any] = {}
        if request.headers.get("content-type", "").startswith(
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
        if html_requested or not body:
            form = await _form_fields(request)
            extra |= form - ALLOWED_FIELDS
        html = html_requested and submitted_format != "json"

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
                translate = translator_for(request)
                response = page(
                    request,
                    "index.html",
                    index_context(
                        translate,
                        release_track=sanitize_release_track(submitted_track),
                        error=exc.translated(translate),
                        error_self_host=exc.self_host,
                        target_url=str(submitted_url),
                    ),
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

    # A batch is a convenience for a caller with an estate to check, never a
    # discount on the limits: every target in it is counted exactly as if it
    # had been submitted on its own, in the order it was written. The response
    # therefore has two lists rather than one status - some targets can start
    # while others wait for a cooldown they share with nobody.
    @app.post("/api/scans/batch")
    async def create_batch(request: Request) -> Response:
        try:
            parsed = await request.json()
        except ValueError:
            parsed = None
        body = parsed if isinstance(parsed, dict) else {}

        extra = set(body) - BATCH_ALLOWED_FIELDS
        if extra:
            return JSONResponse(
                {
                    "detail": "This service does not accept "
                    f"{', '.join(sorted(extra))}. The scan runs with "
                    "server-side settings only."
                },
                status_code=422,
            )

        raw_targets = body.get("targets")
        if not isinstance(raw_targets, list) or not raw_targets:
            return JSONResponse(
                {"detail": "Send a non-empty list of targets in 'targets'."},
                status_code=422,
            )
        if len(raw_targets) > settings.max_batch_targets:
            audit: AuditLog = app.state.audit
            audit.submission_rejected(
                client=client_address(request, settings),
                reason=REASON_BATCH_TOO_LARGE,
                status=422,
            )
            return JSONResponse(
                {
                    "detail": f"A batch may hold at most "
                    f"{settings.max_batch_targets} targets. Send the rest in "
                    "a second batch, or run the scanner yourself: "
                    f"{PROJECT_URL}.",
                    "maxTargets": settings.max_batch_targets,
                    "selfHostUrl": PROJECT_URL,
                },
                status_code=422,
            )

        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        retry_after = 0
        for raw in raw_targets:
            target_url = str(raw or "")
            try:
                identifier = await accept_submission(
                    request,
                    target_url,
                    body.get("ignore_hardenings"),
                    str(body.get("output_format") or "dashboard"),
                    body.get("release_track"),
                    set(),
                )
            except _Rejected as exc:
                entry: dict[str, Any] = {
                    "target": target_url,
                    "status": exc.status,
                    "detail": exc.message,
                }
                if exc.retry_after:
                    entry["retryAfter"] = exc.retry_after
                    retry_after = max(retry_after, exc.retry_after)
                if exc.self_host:
                    entry["selfHostUrl"] = PROJECT_URL
                rejected.append(entry)
                continue
            accepted.append(
                {
                    "uuid": identifier,
                    "target": target_url,
                    "state": "queued",
                    "url": f"/scan/{identifier}",
                }
            )

        payload = {
            "accepted": accepted,
            "rejected": rejected,
            "counts": {
                "submitted": len(raw_targets),
                "accepted": len(accepted),
                "rejected": len(rejected),
            },
        }
        # Something started means the batch worked, whatever else did not. A
        # batch where nothing started answers with the reason its first target
        # was refused, so a caller sees a status that matches what happened.
        if accepted:
            status = 202
        else:
            status = rejected[0]["status"] if rejected else 422
            if status == 429:
                payload["hint"] = SELF_HOST_HINT.format(url=PROJECT_URL)
                payload["selfHostUrl"] = PROJECT_URL
        response = JSONResponse(payload, status_code=status)
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response

    # Erasure on request. Authenticated, because the operation is destructive
    # in a way nothing else here is: it deletes results belonging to whoever
    # is reading them, and it is the only call that walks the keyspace. In
    # practice the data subject writes to the operator, and the operator - the
    # controller - runs this and hands back the receipt.
    @app.delete("/api/purge")
    async def purge_target_data(request: Request) -> Response:
        audit: AuditLog = app.state.audit
        address = client_address(request, settings)

        # No token configured means the feature is not deployed, and an
        # undeployed endpoint answers exactly like a nonexistent one.
        if not settings.purge_token:
            return not_found(request)

        presented = _presented_token(request)
        # Encoded on both sides: a header can carry bytes that are not ASCII,
        # and comparing those as str raises instead of answering 401.
        if not hmac.compare_digest(
            presented.encode("utf-8", "surrogateescape"),
            settings.purge_token.encode("utf-8", "surrogateescape"),
        ):
            audit.submission_rejected(
                client=address, reason=REASON_PURGE_UNAUTHORISED, status=401
            )
            LOGGER.info("purge_denied")
            return JSONResponse(
                {
                    "detail": "An erasure request has to be authorised. "
                    "Write to the operator of this service."
                },
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            hostname = normalise_target(request.query_params.get("target"))
        except PurgeRejected as exc:
            return JSONResponse({"detail": str(exc)}, status_code=422)

        store: ScanStore = app.state.store
        limiter: RateLimiter = app.state.limiter
        report = await store.purge_target(hostname)
        cooldown_keys = await limiter.forget_target(hostname)
        receipt = build_receipt(
            target=hostname,
            report=report,
            cooldown_keys=cooldown_keys,
            signing_key=settings.purge_signing_key,
            notes=_purge_notes(settings),
        )
        LOGGER.info(
            "purge_completed receipt=%s scans=%d remaining=%d",
            receipt.receipt_id,
            report.scans,
            report.remaining,
        )
        audit.data_purged(
            client=address,
            target=hostname,
            scans=report.scans,
            remaining=report.remaining,
            receipt=receipt.receipt_id,
        )
        return JSONResponse(receipt.as_dict(), status_code=200)

    @app.get("/scan/{identifier}", response_class=HTMLResponse)
    async def scan_page(request: Request, identifier: str) -> Response:
        json_requested = (
            request.query_params.get("output_format") == "json"
            or "application/json" in request.headers.get("accept", "")
        )
        record = await app.state.store.get(identifier)
        if record is None:
            if json_requested:
                return JSONResponse({"detail": "Not found."}, status_code=404)
            return page(request, "404.html", {}, status=404)
        if json_requested:
            return JSONResponse(_scan_payload(record))
        translate = translator_for(request)
        return page(
            request,
            "scan.html",
            {
                "t": translate,
                "scan": record.as_dict(),
                # The labels around the evidence are translated; the evidence
                # itself - versions, identifiers, what the host said - is not.
                "summary": (
                    summarise(record.result, translate) if record.result else None
                ),
                "webmcp_tools": (
                    {
                        "action": "status",
                        "endpoint": f"/scan/{identifier}?output_format=json",
                        "name": "get_scan_result",
                        "title": "Get scan result",
                        "description": (
                            "Read the current state and, when complete, the "
                            "structured result for the scan shown on this page."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {},
                        },
                        "annotations": {
                            "readOnlyHint": True,
                            "untrustedContentHint": True,
                        },
                    },
                    {
                        "action": "export",
                        "endpoint": f"/api/scans/{identifier}/export/",
                        "name": "export_scan_report",
                        "title": "Export scan report",
                        "description": (
                            "Download the completed scan shown on this page in "
                            "JSON, CSV, SARIF, or PDF format."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["format"],
                            "properties": {
                                "format": {
                                    "type": "string",
                                    "enum": list(EXPORT_FORMATS),
                                    "default": "json",
                                }
                            },
                        },
                        "annotations": {
                            "readOnlyHint": False,
                            "untrustedContentHint": True,
                        },
                    },
                )
                if mcp_enabled
                else (),
            },
        )

    @app.get("/api/scans/{identifier}/export/{fmt}")
    async def scan_export(request: Request, identifier: str, fmt: str) -> Response:
        """
        One finished scan as a file.

        The uuid is still the whole of the authorisation, so an unknown one
        answers 404 exactly as everywhere else. A scan that exists but has not
        finished answers 409: there is nothing to render yet, and pretending it
        is missing would send a caller into a retry loop against the wrong
        endpoint.
        """
        if fmt not in EXPORT_FORMATS:
            return JSONResponse({"detail": "Not found."}, status_code=404)
        record = await app.state.store.get(identifier)
        if record is None:
            return JSONResponse({"detail": "Not found."}, status_code=404)
        if record.state != STATE_COMPLETED or record.result is None:
            return JSONResponse(
                {"detail": "This scan has no result yet.", "state": record.state},
                status_code=409,
            )
        body = _render_export(record.result, fmt, identifier)
        raw_body = body.encode("utf-8") if isinstance(body, str) else body
        signature = sign_bytes(raw_body, settings.export_signing_key)
        headers = {
            "Content-Disposition": (
                f'attachment; filename="{export_filename(identifier, fmt)}"'
            )
        }
        if signature:
            headers[SIGNATURE_HEADER] = signature
        return Response(
            raw_body,
            media_type=MEDIA_TYPES[fmt],
            headers=headers,
        )

    @app.get("/api/scans/{identifier}")
    async def scan_state(request: Request, identifier: str) -> Response:
        record = await app.state.store.get(identifier)
        if record is None:
            return JSONResponse({"detail": "Not found."}, status_code=404)

        output_format = record.metadata.get("outputFormat", "json")

        if (
            record.state == STATE_COMPLETED
            and record.result is not None
            and output_format in {"csv", "sarif", "pdf"}
        ):
            return Response(
                _render_export(record.result, output_format, identifier),
                media_type=MEDIA_TYPES[output_format],
            )

        return JSONResponse(_scan_payload(record))

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
                # Dates, never a target: enough for an operator to see that
                # the daily lifecycle refresh is actually happening.
                "releaseSchedule": await schedule_state(app.state.backend, settings),
                "advisories": await advisory_state(app.state.backend, settings),
            }
        )

    # The agent-facing execution layer, mounted rather than reimplemented:
    # the tools call the routes above through the ordinary ASGI stack, so an
    # agent reaches exactly the rate limits, SSRF guard and authorisation a
    # browser does.
    app.state.mcp_server = None
    if mcp_enabled:
        from .mcp_server import McpPathNormaliser, build_mcp_server, mcp_app

        server = build_mcp_server(app, settings)
        app.state.mcp_server = server
        app.mount(MCP_PATH, mcp_app(server, settings))
        app.add_middleware(McpPathNormaliser, path=MCP_PATH)
        LOGGER.info(
            "mcp_enabled path=%s authenticated=%s",
            MCP_PATH,
            auth_required(settings),
        )

    @app.exception_handler(404)
    async def _handle_404(request: Request, exc: Exception) -> Response:
        return not_found(request)

    return app


def _scan_payload(record: ScanRecord) -> dict[str, Any]:
    """One scan record in the shared JSON shape used by both read routes."""
    payload = record.as_dict()
    if record.state == STATE_COMPLETED and record.result is not None:
        payload["summary"] = summarise(record.result)
        payload["exports"] = {
            name: f"/api/scans/{record.uuid}/export/{name}"
            for name in EXPORT_FORMATS
        }
    if record.state in {STATE_COMPLETED, STATE_FAILED}:
        payload["done"] = True
    return payload


def _render_export(result: dict[str, Any], fmt: str, identifier: str) -> bytes | str:
    """One finished result rendered as the file a caller asked for."""
    if fmt == "csv":
        return csv_report(result)
    if fmt == "sarif":
        return json.dumps(sarif_report(result), indent=2)
    if fmt == "pdf":
        return pdf_report(result, identifier=identifier)
    return json.dumps(result, indent=2)


def _presented_token(request: Request) -> str:
    """
    The secret an erasure request presented, or an empty string.

    Both ``Authorization: Bearer <token>`` and a bare header value are
    accepted; the comparison afterwards is constant time either way.
    """
    header = request.headers.get("authorization", "").strip()
    if not header:
        return ""
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer":
        return value.strip()
    return header


def _purge_notes(settings: WebSettings) -> tuple[str, ...]:
    """
    What the receipt has to admit about the data it does not control.

    A proof of deletion that quietly omits a log the operator still holds is
    worse than no proof at all, so the receipt names what remains.
    """
    notes = [
        (
            "Scan results already downloaded or exported by whoever ran the "
            "scan are outside the control of this service."
        ),
        "Lifecycle log entries carry scan identifiers and no target.",
    ]
    if settings.audit_log:
        notes.append(
            "An audit record of this erasure was written, carrying the "
            "receipt identifier and "
            + (
                "the hostname in the clear, because this deployment records "
                "targets; retention of that log is the operator's."
                if settings.audit_log_targets
                else "a fingerprint of the target rather than its name."
            )
        )
    return tuple(notes)


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
