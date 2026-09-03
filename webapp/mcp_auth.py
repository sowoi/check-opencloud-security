"""
Optional sign-in for the MCP endpoint, against an OpenID Connect provider.

The default deployment is open: scanning is a public act, the rate limits are
what protect it, and an account would only make an agent identifiable without
making anybody safer. An operator running the service *inside* an
organisation wants the opposite - a colleague's agent should be able to scan
the estate, and a stranger's should not - and that is what
``COS_WEB_MCP_AUTH_ENABLED`` is for.

Three rules shape this module.

**It is a resource server and nothing else.** No login page, no session, no
consent screen, no client registry, no token endpoint. The identity provider
does all of it; this service only checks the token an agent already holds,
against the provider's published signing keys. Which is why it works with
authentik, Keycloak, Entra or anything else that publishes a JWKS - and why
none of them can turn this into a service that stores who anybody is.

**Authentication is not authorisation to work harder.** A signed-in agent
meets the same client rate limit, the same target cooldown and the same SSRF
guard as an anonymous browser, because those protect the *scanned instance*
rather than this service. Sign-in decides who may ask, never how much.

**A service told to require a token and unable to check one refuses to
start.** The alternative is an endpoint the operator believes is protected
and is not, which is the one failure worth crashing over - the same reasoning
that makes ``ensure_encryption_ready`` refuse to store plaintext.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from .workflows import SELF_HOST_URL

LOGGER = logging.getLogger("check_opencloud.web.mcp.auth")

#: Where the resource metadata for the MCP endpoint is published, as RFC 9728
#: derives it: the well-known prefix, then the resource's own path.
PROTECTED_RESOURCE_PATH = "/.well-known/oauth-protected-resource/mcp"

#: The path an OpenID provider publishes its configuration at, appended to
#: the issuer. Used only to *tell* an operator where to look and to derive a
#: JWKS URL that was not configured; nothing here fetches it at startup.
OPENID_CONFIGURATION_PATH = ".well-known/openid-configuration"

#: How long a fetched key set is reused before it is fetched again. Long
#: enough that a busy endpoint is not a load generator against the identity
#: provider, short enough that a rotated key is picked up without a restart.
JWKS_CACHE_SECONDS = 300

#: The shortest gap between two key fetches provoked by a token naming a key
#: this service has not got.
#:
#: A published key set is looked up by the ``kid`` in the token, and the client
#: below refetches whenever that name is not in the set - which is exactly how
#: a rotated key starts working without a restart, and also how one
#: unauthenticated request becomes one request to somebody's identity
#: provider. ``/mcp`` is reachable by anybody the deployment lets near it, a
#: ``kid`` is two lines of JSON to invent, and neither the signature nor the
#: audience has been looked at by the time the fetch happens. Without a floor
#: here, a stream of tokens signed by nobody is a load generator aimed at the
#: provider and a queue of blocking fetches in front of every other caller.
JWKS_MISS_REFETCH_SECONDS = 60

#: The signature algorithms accepted. Deliberately asymmetric only: a shared
#: secret would mean this service holds a key that can *mint* tokens, and it
#: has no business being able to.
ALLOWED_ALGORITHMS = ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512")


class AuthConfig(Protocol):
    """The settings this module reads. A narrow view of ``WebSettings``."""

    @property
    def enable_mcp(self) -> bool: ...

    @property
    def mcp_auth_enabled(self) -> bool: ...

    @property
    def mcp_auth_issuer(self) -> str | None: ...

    @property
    def mcp_auth_jwks_url(self) -> str | None: ...

    @property
    def mcp_auth_audience(self) -> str | None: ...

    @property
    def mcp_auth_scopes(self) -> tuple[str, ...]: ...

    @property
    def mcp_auth_resource_url(self) -> str | None: ...

    @property
    def public_base_url(self) -> str | None: ...


def auth_required(config: AuthConfig) -> bool:
    """Whether the MCP endpoint asks for a token at all."""
    return bool(config.enable_mcp and config.mcp_auth_enabled)


def issuer_url(config: AuthConfig) -> str:
    """The issuer, without a trailing slash, as it appears in a token."""
    return (config.mcp_auth_issuer or "").strip().rstrip("/")


def jwks_url(config: AuthConfig) -> str:
    """
    Where the signing keys are published.

    Derived from the issuer when it was not configured, which is what every
    provider that follows the discovery specification will answer with
    anyway. An operator whose provider puts them somewhere else says so
    explicitly rather than being told their provider is unsupported.
    """
    configured = (config.mcp_auth_jwks_url or "").strip()
    if configured:
        return configured
    base = issuer_url(config)
    return f"{base}/jwks/" if base else ""


def openid_configuration_url(config: AuthConfig) -> str:
    """The provider's discovery document, for an operator to check against."""
    base = issuer_url(config)
    return f"{base}/{OPENID_CONFIGURATION_PATH}" if base else ""


def resource_url(config: AuthConfig) -> str:
    """
    The identifier this service claims as the protected resource.

    It has to be the URL an agent actually calls, because RFC 9728 metadata
    is looked up beneath it and a 401 names it. A deployment behind a proxy
    therefore needs ``COS_WEB_PUBLIC_BASE_URL`` set, or this value given
    outright.
    """
    configured = (config.mcp_auth_resource_url or "").strip()
    if configured:
        return configured.rstrip("/")
    base = (config.public_base_url or "").strip().rstrip("/")
    return f"{base}/mcp" if base else ""


def ensure_mcp_auth_ready(config: AuthConfig) -> None:
    """
    Refuse to start when sign-in was asked for and cannot be enforced.

    Every branch here is a deployment whose operator believes the endpoint is
    protected. Serving it open would be the worst of the available outcomes,
    and a token that cannot be checked is not a smaller version of a token
    that can.
    """
    if not config.mcp_auth_enabled:
        return
    if not config.enable_mcp:
        # Not an error: switching the endpoint off is a perfectly good way to
        # protect it, and complaining would make the safest configuration the
        # one that fails to boot.
        LOGGER.info("mcp_auth_configured_but_endpoint_disabled")
        return
    if not issuer_url(config):
        raise ValueError(
            "COS_WEB_MCP_AUTH_ENABLED is on but COS_WEB_MCP_AUTH_ISSUER is not "
            "set. There would be nothing to check a token against, and /mcp "
            "would be served without authentication."
        )
    if not jwks_url(config):  # pragma: no cover - unreachable with an issuer
        raise ValueError(
            "COS_WEB_MCP_AUTH_ENABLED is on but no signing keys can be found. "
            "Set COS_WEB_MCP_AUTH_JWKS_URL."
        )
    provider_issuer = issuer_url(config)
    provider_jwks = jwks_url(config)
    for label, url in (("issuer", provider_issuer), ("JWKS", provider_jwks)):
        if not _is_https(url) and not _is_loopback(url):
            raise ValueError(
                f"COS_WEB_MCP_AUTH_{label.upper()} must use HTTPS. "
                "Only loopback URLs are allowed over HTTP for local development."
            )
    if not resource_url(config):
        raise ValueError(
            "COS_WEB_MCP_AUTH_ENABLED is on but this service does not know its "
            "own public address. Set COS_WEB_PUBLIC_BASE_URL, or "
            "COS_WEB_MCP_AUTH_RESOURCE_URL, to the URL agents reach /mcp at: "
            "RFC 9728 metadata is published beneath it and a 401 names it."
        )
    if not _is_https(resource_url(config)) and not _is_loopback(resource_url(config)):
        raise ValueError(
            "COS_WEB_MCP_AUTH_ENABLED is on but the resource URL is not HTTPS. "
            "A ****** over plain HTTP is a credential in the clear."
        )
    if not (config.mcp_auth_audience or "").strip():
        raise ValueError(
            "COS_WEB_MCP_AUTH_ENABLED is on but COS_WEB_MCP_AUTH_AUDIENCE is "
            "not set. Without it any unexpired token the issuer minted for any "
            "other application would open /mcp, which is the whole of a "
            "shared provider's user base rather than this endpoint's. Set it "
            "to the client ID agents authenticate as."
        )


def protected_resource_metadata(config: AuthConfig) -> dict[str, Any]:
    """
    RFC 9728 metadata: which provider issues tokens for this endpoint.

    An MCP client that meets a 401 reads this to find out where to send its
    user. It is public and unauthenticated, like every other description this
    service publishes - it names an authorisation server, and knowing where
    to ask for a token has never been the secret part.
    """
    document: dict[str, Any] = {
        "resource": resource_url(config),
        "authorization_servers": [issuer_url(config)],
        "bearer_methods_supported": ["header"],
        "resource_name": "check-opencloud-security MCP endpoint",
    }
    if config.mcp_auth_scopes:
        document["scopes_supported"] = list(config.mcp_auth_scopes)
    return document


def discovery_authentication(config: AuthConfig) -> dict[str, Any]:
    """
    What ``/.well-known/ai.json`` says about getting into the MCP endpoint.

    An agent should learn that it needs a token before it spends a round trip
    finding out with a 401, and it should learn where to get one from the
    same document that told it the endpoint exists.
    """
    if not auth_required(config):
        return {
            "type": "none",
            "note": "No token required. Connect and initialize.",
        }
    document: dict[str, Any] = {
        "type": "oauth2",
        "scheme": "bearer",
        "issuer": issuer_url(config),
        "resource": resource_url(config),
        "protectedResourceMetadata": (
            f"{resource_url(config).rsplit('/mcp', 1)[0]}{PROTECTED_RESOURCE_PATH}"
        ),
        "openidConfiguration": openid_configuration_url(config),
        "note": (
            "This deployment requires a bearer token from the named "
            "authorisation server. Scanning is not open here; the operator "
            "decides who may ask. The scanner itself is open source and runs "
            "locally with no sign-in at all."
        ),
        "selfHostUrl": SELF_HOST_URL,
    }
    if config.mcp_auth_scopes:
        document["scopes"] = list(config.mcp_auth_scopes)
    return document


@dataclass
class _KeySet:
    """One fetched JWKS, and when it stops being trusted to be current."""

    keys: Any
    fetched_at: float


class UnknownSigningKey(LookupError):
    """The token names a signing key the provider has not published to us."""


class OidcTokenVerifier:
    """
    Checks a bearer token against the provider's published signing keys.

    Verification is offline: the token is a JWT, the provider publishes the
    public half of the key that signed it, and this service checks the
    signature, the issuer, the audience and the expiry itself. No
    introspection call, so an agent's request does not wait on a second
    service, and this service never holds a credential of its own to make one
    with.

    A token that fails any check is simply not a token. The reason is logged
    at debug level and never returned: telling a caller *which* claim was
    wrong is how a token is guessed at one field at a time.
    """

    def __init__(
        self,
        *,
        jwks_uri: str,
        issuer: str,
        audience: str | None = None,
        required_scopes: tuple[str, ...] = (),
        cache_seconds: int = JWKS_CACHE_SECONDS,
    ):
        self._jwks_uri = jwks_uri
        # Providers disagree about the trailing slash - Authentik's
        # per-provider issuer ends in one, most others do not - and an
        # operator copying the value out of a discovery document should not
        # have to know which. Both spellings of the same issuer are accepted;
        # a *different* issuer still is not.
        trimmed = issuer.rstrip("/")
        self._issuer = [trimmed, f"{trimmed}/"] if trimmed else []
        self._audience = (audience or "").strip() or None
        self._required = tuple(required_scopes)
        self._cache_seconds = cache_seconds
        self._cached: _KeySet | None = None
        # When a token naming an unknown key was last allowed to provoke a
        # fetch. Never, to start with, so the first rotation is picked up at
        # once. Guarded by a lock because verification runs in a worker
        # thread and several may be holding a forged token at the same
        # moment - which is the whole point of the floor.
        self._last_miss_refetch = float("-inf")
        self._miss_lock = threading.Lock()

    async def verify_token(self, token: str) -> Any:
        """The ``TokenVerifier`` protocol: an access token, or ``None``."""
        from mcp.server.auth.provider import AccessToken

        try:
            claims = await self._claims(token)
        except Exception as exc:  # noqa: BLE001 - every failure is "not a token"
            LOGGER.debug("mcp_token_rejected reason=%s", type(exc).__name__)
            return None
        if claims is None:
            return None

        scopes = _scopes(claims)
        if not set(self._required) <= set(scopes):
            LOGGER.debug("mcp_token_rejected reason=missing_scope")
            return None

        expires = claims.get("exp")
        return AccessToken(
            token=token,
            client_id=str(claims.get("azp") or claims.get("client_id") or ""),
            scopes=list(scopes),
            expires_at=int(expires) if isinstance(expires, (int, float)) else None,
        )

    async def _claims(self, token: str) -> dict[str, Any] | None:
        """The verified claims of one token, or ``None`` if it is not valid."""
        if self._audience is None:
            # Startup refuses this configuration, so reaching here means the
            # verifier was built some other way. An audience that is not
            # compared is not a weaker check than one that is - on a provider
            # that serves more than this endpoint it is no check at all - so
            # nothing verifies rather than everything doing.
            LOGGER.debug("mcp_token_rejected reason=no_audience_configured")
            return None
        keys = await self._key_set()
        # Off the event loop. Both halves of this block - fetching a key set
        # and checking a signature - are work somebody who has authenticated
        # to nothing can ask for, and neither should be able to stop this
        # process answering everybody else while it happens.
        return await asyncio.to_thread(self._verified_claims, keys, token)

    def _verified_claims(self, keys: Any, token: str) -> dict[str, Any]:
        """Check one token against the published keys. Raises if it is not one."""
        import jwt

        signing_key = self._signing_key(keys, token)
        options: Any = {
            "verify_aud": True,
            "require": ["exp", "iss", "aud"],
        }
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=list(ALLOWED_ALGORITHMS),
            issuer=self._issuer or None,
            audience=self._audience,
            options=options,
        )
        return dict(claims)

    def _signing_key(self, keys: Any, token: str) -> Any:
        """The published key this token names, without letting it order a fetch.

        The client refetches the key set whenever a token names a key it has
        not got. That is how a rotated key works without a restart, and it is
        also how a token signed by nobody turns into a request to somebody's
        identity provider - so a miss may provoke one at most every
        :data:`JWKS_MISS_REFETCH_SECONDS`. The rest are simply not tokens,
        which is what they were anyway.

        The header is read without verifying it, which is safe for exactly one
        use: choosing which *published* key to check the signature against. A
        forged ``kid`` selects a key the token was not signed with, and the
        signature check that follows is what refuses it.
        """
        import jwt

        kid = jwt.get_unverified_header(token).get("kid")
        for key in keys.get_signing_keys():
            if key.key_id == kid:
                return key
        if not self._may_refetch():
            LOGGER.debug("mcp_token_rejected reason=unknown_key_id")
            raise UnknownSigningKey(str(kid))
        for key in keys.get_signing_keys(refresh=True):
            if key.key_id == kid:
                return key
        raise UnknownSigningKey(str(kid))

    def _may_refetch(self) -> bool:
        """Whether an unknown key name may cost a fetch right now."""
        now = time.monotonic()
        with self._miss_lock:
            if now - self._last_miss_refetch < JWKS_MISS_REFETCH_SECONDS:
                return False
            self._last_miss_refetch = now
            return True

    async def _key_set(self) -> Any:
        """
        The provider's signing keys, refetched when the cache has aged out.

        A rotated key must be picked up without a restart, and a busy
        endpoint must not turn every tool call into a request to the identity
        provider. The client below caches internally as well; this only
        governs how long a *failed* lookup keeps the old set in use.
        """
        import jwt

        now = time.monotonic()
        cached = self._cached
        if cached is not None and now - cached.fetched_at < self._cache_seconds:
            return cached.keys
        client = jwt.PyJWKClient(self._jwks_uri, cache_keys=True)
        self._cached = _KeySet(keys=client, fetched_at=now)
        return client


def build_token_verifier(config: AuthConfig) -> OidcTokenVerifier:
    """The verifier for one deployment's settings."""
    return OidcTokenVerifier(
        jwks_uri=jwks_url(config),
        issuer=issuer_url(config),
        audience=config.mcp_auth_audience,
        required_scopes=config.mcp_auth_scopes,
    )


def auth_settings(config: AuthConfig) -> Any:
    """
    The SDK's ``AuthSettings`` for this deployment, or ``None``.

    Returning ``None`` is what leaves the endpoint open, and it is deliberate
    that the only way to reach that from an enabled configuration is for
    ``ensure_mcp_auth_ready`` to have let it through.
    """
    if not auth_required(config):
        return None
    from mcp.server.auth.settings import AuthSettings

    return AuthSettings(
        issuer_url=issuer_url(config),  # type: ignore[arg-type]
        resource_server_url=resource_url(config),  # type: ignore[arg-type]
        required_scopes=list(config.mcp_auth_scopes) or None,
    )


def _scopes(claims: dict[str, Any]) -> tuple[str, ...]:
    """
    The scopes a token carries, however its provider chose to write them.

    ``scope`` as a space-separated string is the specification; ``scp`` as
    either a string or a list is what several large providers actually send.
    Reading only the first would reject a valid token from the second.
    """
    for name in ("scope", "scp"):
        value = claims.get(name)
        if isinstance(value, str):
            return tuple(part for part in value.split() if part)
        if isinstance(value, (list, tuple)):
            return tuple(str(part) for part in value if str(part))
    return ()


def _is_https(url: str) -> bool:
    return urlsplit(url).scheme == "https"


def _is_loopback(url: str) -> bool:
    """
    Whether a URL points at this machine.

    A developer trying the flow on ``http://127.0.0.1:8811`` is not sending a
    credential across anybody's network, and refusing to start there would
    mean the only way to try authentication is to have already deployed it.
    """
    host = urlsplit(url).hostname or ""
    return host in {"127.0.0.1", "::1", "localhost"}


def normalise_base_url(url: str) -> str:
    """A base URL with no trailing slash and no query or fragment."""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
