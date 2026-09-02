"""
Who is allowed into the operator's area, and why this service believes them.

The admin area is the one surface here that can change what the service
knows - it refreshes the release schedule and the advisory database - and the
one that can read the audit trail. So the question it has to answer is not
"is this request signed in" but "did this request come through the thing that
signs people in".

**This service authenticates nobody.** It has no login page, no session, no
cookie of its own and no password to check, exactly as
:mod:`webapp.mcp_auth` has none. An authentik proxy provider stands in front
of ``/admin``, and a request only reaches this process after the outpost has
already established who is making it. What arrives here is that outpost's
account of the person, in ordinary HTTP headers.

Which is the whole problem, because a header is a thing anybody can send. The
identity headers are worth exactly as much as the certainty that they came
from the outpost, and that certainty is a shared secret the outpost adds and
nobody else knows. Four rules follow, and each of them is a refusal:

- **No secret, no area.** A deployment that enables the admin area without
  ``COS_WEB_ADMIN_PROXY_SECRET`` does not start. Serving an unauthenticated
  console to an operator who believes it is protected is the worst outcome
  available, and it is the one that happens by default if this is a warning
  instead of an error.
- **No list, no area.** ``COS_WEB_ADMIN_USERS`` has to name somebody.
  Treating an empty list as "anybody authentik authenticated" would hand the
  console to every account in a directory that may well exist to let
  strangers sign in to something else entirely.
- **A mismatch is a 404, not a 403.** Whoever reaches this without the secret
  is not an operator who mistyped something; they are somebody finding out
  whether the area exists. They get the answer every other unknown path
  gives.
- **The way out is a link, so it has to be one.** ``COS_WEB_ADMIN_SIGN_OUT_URL``
  is rendered as an ``href`` on a page whose content policy exists to keep
  script off it, and ``javascript:`` in a link is script by another name. A
  local path or an ordinary web address is accepted and anything else is
  refused at startup, where an operator is looking, rather than served.

Nothing here is written down. The identity is used to decide the request and
to name the actor in an audit record, and is then gone - there is no admin
account in this service, and no way to make one.

**Signing out is somebody else's to do.** This service has no session to end,
so the area cannot offer an exit of its own; the only honest one is the
provider's, and only the deployment knows where that is. Unset means the band
names the operator and offers no way out, which is better than a control that
appears to sign somebody out and does not.
"""

from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass

from starlette.requests import Request

from .settings import (
    ADMIN_EMAIL_HEADER,
    ADMIN_GROUPS_HEADER,
    ADMIN_PROXY_HEADER,
    ADMIN_PROXY_SECRET_MINIMUM,
    ADMIN_USER_HEADER,
    WebSettings,
)

LOGGER = logging.getLogger("check_opencloud.web.admin.auth")


@dataclass(frozen=True)
class Operator:
    """The person the outpost says is making this request."""

    username: str
    email: str | None
    groups: tuple[str, ...]


def ensure_admin_ready(settings: WebSettings) -> None:
    """Refuse to start a deployment whose admin area could not be protected.

    Every branch is an operator who believes ``/admin`` is behind a sign-in.
    A console served open is worse than one that fails to boot, and unlike a
    boot failure it is not noticed.
    """
    if not settings.admin_enabled:
        return

    secret = (settings.admin_proxy_secret or "").strip()
    if not secret:
        raise ValueError(
            "COS_WEB_ADMIN_ENABLED is on but COS_WEB_ADMIN_PROXY_SECRET is not "
            "set. The identity headers the authentik outpost sends would be "
            "headers anybody could send, and /admin would be an "
            "unauthenticated console."
        )
    if len(secret) < ADMIN_PROXY_SECRET_MINIMUM:
        raise ValueError(
            "COS_WEB_ADMIN_PROXY_SECRET is shorter than "
            f"{ADMIN_PROXY_SECRET_MINIMUM} characters. It is the only thing "
            "separating an operator from anybody who can reach this container."
        )
    if not settings.admin_users:
        raise ValueError(
            "COS_WEB_ADMIN_ENABLED is on but COS_WEB_ADMIN_USERS names nobody. "
            "An empty list is not read as 'anybody the provider authenticated' "
            "- that would hand the area to every account in the directory."
        )

    exit_url = sign_out_url(settings)
    if exit_url is not None and not _linkable(exit_url):
        raise ValueError(
            "COS_WEB_ADMIN_SIGN_OUT_URL is not an address this page may link "
            "to. Give it a local path such as /outpost.goauthentik.io/sign_out "
            "or an http(s) URL: the value is rendered as an href, and a scheme "
            "like javascript: there is script on a page whose content policy "
            "exists to forbid it."
        )


def sign_out_url(settings: WebSettings) -> str | None:
    """Where this deployment says the sign-in is ended, if it says.

    ``None`` covers both an unset value and one that is only whitespace: a
    deployment that set the variable to nothing did not name an address, and
    the band shows no link rather than an empty one.
    """
    return (settings.admin_sign_out_url or "").strip() or None


def _linkable(url: str) -> bool:
    """Whether a configured sign-out address is one this page may put in an href.

    A local path, or an ordinary web address, and nothing else. Refusing by
    naming what is allowed rather than listing what is not is what makes this
    hold for the next scheme somebody thinks of. ``//host/path`` is refused
    with them: it reads as a path and is not one, it is whatever scheme the
    page happens to be on pointed at somebody else's host.
    """
    if url.startswith("/"):
        return not url.startswith("//")
    return url.lower().startswith(("http://", "https://"))


def _from_proxy(request: Request, settings: WebSettings) -> bool:
    """Whether the shared secret the outpost adds is present and correct."""
    expected = (settings.admin_proxy_secret or "").strip()
    if not expected:  # pragma: no cover - startup refuses this combination
        return False
    presented = request.headers.get(ADMIN_PROXY_HEADER, "")
    # Constant time, because this is a secret being compared and the answer
    # is worth guessing at.
    return hmac.compare_digest(presented, expected)


def _permitted(username: str, settings: WebSettings) -> bool:
    """Whether the signed-in name is one this deployment lets in.

    Compared case-insensitively: authentik will happily sign somebody in as
    the name they typed, and an operator who wrote their username in a
    different case in the compose file did not mean to lock themselves out.
    """
    wanted = username.strip().casefold()
    if not wanted:
        return False
    return any(wanted == allowed.strip().casefold() for allowed in settings.admin_users)


def operator_for(request: Request, settings: WebSettings) -> Operator | None:
    """The operator this request belongs to, or ``None`` if it belongs to none.

    ``None`` covers every failure the same way on purpose - no secret, a
    wrong secret, no name, a name nobody put on the list - because the caller
    turns all of them into the same 404 and the difference between them is
    only useful to somebody probing.
    """
    if not settings.admin_enabled:
        return None
    if not _from_proxy(request, settings):
        # Deliberately not warning: an unauthenticated probe is not an
        # operator's mistake, and a log line per probe is a log somebody can
        # fill up from outside.
        LOGGER.debug("admin_request_not_from_proxy")
        return None

    username = request.headers.get(ADMIN_USER_HEADER, "").strip()
    if not _permitted(username, settings):
        # This one *is* worth a line: the request carried the outpost's
        # secret, so it really did come through the sign-in, and somebody
        # authenticated is being turned away. That is either a list that
        # needs an entry or an account that should not have got this far.
        LOGGER.info("admin_user_not_permitted")
        return None

    groups = tuple(
        part.strip()
        for part in request.headers.get(ADMIN_GROUPS_HEADER, "").split("|")
        if part.strip()
    )
    return Operator(
        username=username,
        email=request.headers.get(ADMIN_EMAIL_HEADER, "").strip() or None,
        groups=groups,
    )
