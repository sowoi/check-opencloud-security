"""
What the hardening flags mean, and how to act on them.

A scan result is a list of camel-case identifiers: ``basicAuthDisabled``,
``cspWithoutUnsafeInline``, ``publicLinkPasswordEnforced``. On their own they
say nothing about what is wrong or what to change, which turns an alert into a
research task. This module is the missing half: for every flag the scanner can
report, a plain sentence, the OpenCloud setting behind it, and a link to the
official documentation.

Three of the flags are not settings at all, and saying so matters more than
listing them:

- ``publicLinkExpirationEnforced`` is reported ``false`` by *every* OpenCloud
  instance. The capability is a hardcoded constant in the frontend service,
  not a configuration value, so no administrator can turn it on.
- ``userEnumerationRestricted`` is the mirror image: hardcoded to the
  restricted state, so it always passes.
- ``hstsLongMaxAge`` and ``hstsPreload`` are emitted by OpenCloud's own proxy
  with a ten-year max-age and ``preload``. When they fail, the cause is in
  front of OpenCloud - a reverse proxy rewriting the header - not in
  OpenCloud.

Flags marked ``actionable=False`` are still recorded in the result document,
because the observation is real, but they are kept out of alert summaries and
counts. A permanent warning that no one can clear is noise, and noise is how
real findings get ignored.
"""

from __future__ import annotations

from dataclasses import dataclass

# Official OpenCloud documentation. The docs site is a rendered SPA, so these
# are page-level links rather than per-setting anchors.
DOCS_PROXY = "https://docs.opencloud.eu/docs/dev/server/services/proxy/environment-variables"
DOCS_FRONTEND = (
    "https://docs.opencloud.eu/docs/dev/server/services/frontend/environment-variables"
)
DOCS_SHARING = (
    "https://docs.opencloud.eu/docs/dev/server/services/sharing/environment-variables"
)
DOCS_LINK_PASSWORD = "https://docs.opencloud.eu/docs/admin/configuration/link-password-policy"

# Security headers are an HTTP-level concern rather than an OpenCloud setting.
DOCS_MDN_HEADERS = "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers"

# Setting an instance up in front of an identity provider and behind a reverse
# proxy is deployment guidance rather than a per-setting question.
DOCS_IDP = "https://docs.opencloud.eu/docs/admin/getting-started/container/external-idm"
DOCS_REVERSE_PROXY = (
    "https://docs.opencloud.eu/docs/admin/getting-started/container/basic-setup"
)


@dataclass(frozen=True)
class Hardening:
    """One hardening measure, explained."""

    id: str
    title: str
    """A short phrase an operator can read in a notification."""

    meaning: str
    """What the scanner observed, and why it is worth observing."""

    remediation: str
    """What to change. Names the setting where a setting exists."""

    reference: str = ""
    """Official documentation for the setting."""

    setting: str = ""
    """The environment variable that controls this, if any."""

    actionable: bool = True
    """
    Whether an administrator can influence the outcome at all.

    ``False`` marks a flag that OpenCloud hardcodes. It stays in the result
    document but is excluded from alert summaries and counts.
    """

    def describe(self) -> str:
        """Render the full explanation as a single indented block."""
        lines = [f"{self.id}: {self.title}", f"    {self.meaning}"]
        if self.setting:
            lines.append(f"    Setting: {self.setting}")
        lines.append(f"    Fix: {self.remediation}")
        if self.reference:
            lines.append(f"    Docs: {self.reference}")
        return "\n".join(lines)


HARDENINGS: dict[str, Hardening] = {
    "basicAuthDisabled": Hardening(
        id="basicAuthDisabled",
        title="HTTP Basic authentication is enabled",
        meaning=(
            "The instance answers with a 'WWW-Authenticate: Basic' challenge, so "
            "usernames and passwords can be replayed on every request without "
            "going through the identity provider, bypassing single sign-on and "
            "any second factor enforced there. It is often deliberate: CalDAV, "
            "CardDAV and WebDAV clients cannot speak OpenID Connect and have "
            "nothing else to authenticate with, which is why this counts as a "
            "medium finding rather than a serious one - and as a low one when "
            "an external identity provider handles the interactive login."
        ),
        remediation=(
            "Set PROXY_ENABLE_BASIC_AUTH=false (the default) if nothing needs "
            "it. If calendar, contact or WebDAV clients do, keep it on and give "
            "them app tokens rather than account passwords, so that what can be "
            "replayed is revocable and never the single sign-on credential."
        ),
        reference=DOCS_PROXY,
        setting="PROXY_ENABLE_BASIC_AUTH",
    ),
    "cspWithoutUnsafeInline": Hardening(
        id="cspWithoutUnsafeInline",
        title="The Content-Security-Policy allows inline scripts",
        meaning=(
            "The policy contains 'unsafe-inline', which removes most of the "
            "protection a CSP gives against cross-site scripting: injected "
            "markup may execute. Note that this is OpenCloud's shipped default, "
            "so an instance failing this check is not misconfigured - it is "
            "unmodified."
        ),
        remediation=(
            "Point PROXY_CSP_CONFIG_FILE_LOCATION at a csp.yaml without "
            "'unsafe-inline' (or PROXY_CSP_CONFIG_FILE_OVERRIDE_LOCATION to "
            "replace the default outright). Test it first: the web interface "
            "currently relies on inline scripts and styles, so a strict policy "
            "is likely to break the UI and any connected office or IDP service."
        ),
        reference=DOCS_PROXY,
        setting="PROXY_CSP_CONFIG_FILE_LOCATION",
    ),
    "publicLinkPasswordEnforced": Hardening(
        id="publicLinkPasswordEnforced",
        title="Public links can be created without a password",
        meaning=(
            "At least one kind of public link - read-only, upload-only or "
            "editable - may be shared without a password, so anyone holding the "
            "URL has the data. OpenCloud enforces a password on read-only links "
            "by default but not on writable ones, which is the usual reason this "
            "check fails."
        ),
        remediation=(
            "Set OC_SHARING_PUBLIC_SHARE_MUST_HAVE_PASSWORD=true and "
            "OC_SHARING_PUBLIC_WRITEABLE_SHARE_MUST_HAVE_PASSWORD=true. Prefer "
            "these global names over the deprecated FRONTEND_OCS_* forms."
        ),
        reference=DOCS_SHARING,
        setting="OC_SHARING_PUBLIC_WRITEABLE_SHARE_MUST_HAVE_PASSWORD",
    ),
    "publicLinkExpirationEnforced": Hardening(
        id="publicLinkExpirationEnforced",
        title="Public links do not expire automatically (not configurable)",
        meaning=(
            "OpenCloud reports 'files_sharing.public.expire_date.enabled' as a "
            "hardcoded false in the frontend service: it is a constant, not a "
            "setting. Every instance reports it, so this says nothing about how "
            "this particular server is configured."
        ),
        remediation=(
            "Nothing to change - OpenCloud offers no setting for this. If public "
            "links must expire, the expiry has to be set per share, or the link "
            "lifetime governed outside OpenCloud."
        ),
        reference=DOCS_SHARING,
        actionable=False,
    ),
    "userEnumerationRestricted": Hardening(
        id="userEnumerationRestricted",
        title="Account search is not restricted to shared groups",
        meaning=(
            "User search would let any account enumerate the whole directory. "
            "OpenCloud hardcodes this to the restricted state (search limited to "
            "group members), so in practice this check passes everywhere."
        ),
        remediation=(
            "Nothing to change - OpenCloud offers no setting for this and "
            "already restricts the search."
        ),
        reference=DOCS_FRONTEND,
        actionable=False,
    ),
    "passwordPolicyEnforced": Hardening(
        id="passwordPolicyEnforced",
        title="The password policy allows passwords shorter than 8 characters",
        meaning=(
            "The minimum password length is below 8 characters. This policy "
            "governs public link passwords, not account passwords - account "
            "passwords belong to the identity provider."
        ),
        remediation=(
            "Set OC_PASSWORD_POLICY_MIN_CHARACTERS to 8 or more (8 is the "
            "default, so a lower value was configured deliberately). "
            "OC_PASSWORD_POLICY_MIN_{LOWERCASE,UPPERCASE,DIGITS,SPECIAL}_"
            "CHARACTERS and a banned-password list tighten it further."
        ),
        reference=DOCS_LINK_PASSWORD,
        setting="OC_PASSWORD_POLICY_MIN_CHARACTERS",
    ),
    "hstsLongMaxAge": Hardening(
        id="hstsLongMaxAge",
        title="Strict-Transport-Security has a short max-age",
        meaning=(
            "The HSTS max-age is under a year, so a browser stops enforcing "
            "HTTPS for this host sooner than it should. OpenCloud's own proxy "
            "sends ten years, so a short value means something in front of it - "
            "a reverse proxy or CDN - is rewriting the header."
        ),
        remediation=(
            "OpenCloud has no setting for this; the header is fixed in the proxy "
            "service. Fix the reverse proxy in front of OpenCloud, or let "
            "OpenCloud's header through unmodified."
        ),
        reference=f"{DOCS_MDN_HEADERS}/Strict-Transport-Security",
    ),
    "hstsPreload": Hardening(
        id="hstsPreload",
        title="Strict-Transport-Security has no preload directive",
        meaning=(
            "Without 'preload' the host cannot enter the browser preload list, "
            "so the very first request to it is still unprotected. OpenCloud's "
            "proxy sets the directive itself, so its absence points at a reverse "
            "proxy rewriting the header."
        ),
        remediation=(
            "OpenCloud has no setting for this; fix the reverse proxy in front "
            "of it. Only add preload once every subdomain is HTTPS-only - the "
            "list is slow to leave."
        ),
        reference="https://hstspreload.org/",
    ),
    "httpsEnforced": Hardening(
        id="httpsEnforced",
        title="Plain HTTP is not redirected to HTTPS",
        meaning=(
            "The instance answers on http:// without redirecting, so a client "
            "that omits the scheme can be served - and credentials or session "
            "cookies sent - over an unencrypted connection."
        ),
        remediation=(
            "Redirect every http:// request to https:// in the reverse proxy, or "
            "stop serving plain HTTP entirely."
        ),
        reference=DOCS_PROXY,
    ),
    "identityProviderDetected": Hardening(
        id="identityProviderDetected",
        title="No identity provider could be found",
        meaning=(
            "The instance publishes no OpenID Connect discovery document at "
            "/.well-known/openid-configuration and does not redirect that "
            "request anywhere, so the scan cannot tell who issues its tokens. "
            "That is usually a proxy not forwarding the well-known path, and "
            "occasionally an instance whose sign-in is not configured at all. "
            "Nothing is submitted to find this out - only the document and the "
            "redirect are read."
        ),
        remediation=(
            "Check how sign-in is set up: OpenCloud ships its own identity "
            "provider and can be pointed at an external one such as Keycloak, "
            "Authentik or Authelia. If an external provider is already in use, "
            "make sure the reverse proxy forwards /.well-known/ to it."
        ),
        reference=DOCS_IDP,
    ),
    "reverseProxyDetected": Hardening(
        id="reverseProxyDetected",
        title="No reverse proxy could be detected in front of the instance",
        meaning=(
            "Nothing in the response suggests a reverse proxy - no proxy-style "
            "Server or Via header. An instance exposed directly has no place to "
            "terminate TLS for other services, rate-limit an abusive client, or "
            "add a header OpenCloud does not send itself. The detection is "
            "deliberately best-effort: Traefik and HAProxy announce nothing by "
            "default, so a well-run deployment can land here, which is why this "
            "never changes the rating."
        ),
        remediation=(
            "If there is a proxy, nothing needs doing. If there is not, putting "
            "Nginx, Traefik, Caddy or HAProxy in front is the usual way to run "
            "OpenCloud on a public address."
        ),
        reference=DOCS_REVERSE_PROXY,
    ),
}


# The security headers checked under 'setup.headers'. They share the shape of
# the hardenings above so that both can be explained by one lookup.
_HEADER_NOTES: dict[str, tuple[str, str]] = {
    "Strict-Transport-Security": (
        "Browsers may fall back to plain HTTP for this host.",
        "Send 'Strict-Transport-Security: max-age=63072000; includeSubDomains; preload'.",
    ),
    "Content-Security-Policy": (
        "Nothing restricts where scripts, styles and frames may be loaded from.",
        "OpenCloud ships a policy by default; if it is missing, a proxy stripped it.",
    ),
    "X-Content-Type-Options": (
        "Browsers may guess a response's content type and run it as script.",
        "Send 'X-Content-Type-Options: nosniff'.",
    ),
    "X-Frame-Options": (
        "The interface may be embedded in a foreign frame and clickjacked.",
        "Send 'X-Frame-Options: SAMEORIGIN', or a CSP 'frame-ancestors' directive.",
    ),
    "X-Permitted-Cross-Domain-Policies": (
        "Legacy plugins may request a cross-domain policy from this host.",
        "Send 'X-Permitted-Cross-Domain-Policies: none'.",
    ),
    "X-Robots-Tag": (
        "Search engines are not told to leave the instance out of their index.",
        "Send 'X-Robots-Tag: noindex, nofollow'.",
    ),
    "X-XSS-Protection": (
        "The legacy XSS filter of older browsers is not switched on.",
        "Send 'X-XSS-Protection: 1; mode=block'. Modern browsers ignore it.",
    ),
    "Referrer-Policy": (
        "Full URLs may leak to third-party sites through the Referer header.",
        "Send 'Referrer-Policy: no-referrer' or 'strict-origin-when-cross-origin'.",
    ),
}


def _header_hardening(name: str) -> Hardening:
    """Build the explanation for a missing security response header."""
    meaning, remediation = _HEADER_NOTES.get(
        name,
        (
            "The instance does not send this security header.",
            "Set the header in OpenCloud's proxy or the reverse proxy in front of it.",
        ),
    )
    return Hardening(
        id=name,
        title=f"The {name} header is missing or too weak",
        meaning=meaning,
        remediation=remediation,
        reference=f"{DOCS_MDN_HEADERS}/{name}",
    )


def describe(name: str) -> Hardening:
    """
    Explain one hardening flag, header name or scan finding.

    Always returns something: an identifier this build does not know about is
    still better presented as a named unknown than swallowed.
    """
    known = HARDENINGS.get(name)
    if known is not None:
        return known
    if name in _HEADER_NOTES:
        return _header_hardening(name)
    return Hardening(
        id=name,
        title=name,
        meaning="No description is available for this identifier.",
        remediation="See the scan result for the raw finding.",
    )


def is_actionable(name: str) -> bool:
    """Whether an administrator can change the outcome of this flag."""
    return describe(name).actionable


def explain(names: list[str]) -> list[str]:
    """Render explanations for several flags, in the order given."""
    return [describe(name).describe() for name in names]
