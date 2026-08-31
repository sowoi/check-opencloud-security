"""
What the hardening flags mean, and how to act on them.

A scan result is a list of camel-case identifiers: ``basicAuthDisabled``,
``cspWithoutUnsafeInline``, ``publicLinkPasswordEnforced``. On their own they
say nothing about what is wrong or what to change, which turns an alert into a
research task. This module is the missing half: for every flag the scanner can
report, a plain sentence, the OpenCloud setting behind it, and a link to the
official documentation.

Three namespaces share one lookup, because a reader does not care which of
them an identifier came from:

- ``HARDENINGS`` - the capability and header flags OpenCloud itself controls;
- ``CHECKS`` and ``_CHECK_FAMILIES`` - the findings of the extra-check pass,
  which are the ones that actually cap a rating, including the per-path and
  per-port families written ``exposed:/config/opencloud.yaml`` or
  ``debugPort:9205``;
- ``_HEADER_NOTES`` - the security response headers.

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
DOCS_WEB = "https://docs.opencloud.eu/docs/dev/server/services/web/environment-variables"
DOCS_SHARING = (
    "https://docs.opencloud.eu/docs/dev/server/services/sharing/environment-variables"
)
DOCS_LINK_PASSWORD = "https://docs.opencloud.eu/docs/admin/configuration/link-password-policy"

# CORS is configured per service with a shared OC_-prefixed override, and the
# graph service is where the defaults are spelled out most plainly.
DOCS_GRAPH = "https://docs.opencloud.eu/docs/dev/server/services/graph/environment-variables"

# Security headers are an HTTP-level concern rather than an OpenCloud setting.
DOCS_MDN_HEADERS = "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers"

# So is the transport underneath them: OpenCloud terminates TLS in its proxy
# service, but in a real deployment something in front of it usually does.
DOCS_TLS = "https://developer.mozilla.org/en-US/docs/Web/Security/Transport_Layer_Security"

# Setting an instance up in front of an identity provider and behind a reverse
# proxy is deployment guidance rather than a per-setting question.
DOCS_IDP = (
    "https://docs.opencloud.eu/docs/admin/configuration/"
    "authentication-and-user-management/external-idp"
)
DOCS_REVERSE_PROXY = (
    "https://docs.opencloud.eu/docs/admin/getting-started/container/"
    "docker-compose/external-proxy"
)

# The OpenID Connect provider metadata the discovery document publishes is
# specified by OpenID Connect Discovery 1.0 rather than by OpenCloud, and what
# to do about a weak value is a question for whoever runs the provider.
DOCS_OIDC_DISCOVERY = (
    "https://openid.net/specs/openid-connect-discovery-1_0.html#ProviderMetadata"
)

# PKCE is not part of OpenID Connect Discovery: providers publish
# code_challenge_methods_supported in the same document, but the field is
# defined by OAuth 2.0 Authorization Server Metadata.
DOCS_OAUTH_METADATA = "https://www.rfc-editor.org/rfc/rfc8414.html#section-2"

# Keeping the instance current is the one fix that raises the rating rather
# than merely stopping it being lowered, so the remediation planner names it.
DOCS_UPDATE = "https://docs.opencloud.eu/docs/admin/maintenance/upgrade/upgrade-guide"


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

    category: str = ""
    """
    Which area of the instance this belongs to, one of :data:`CATEGORIES`.

    This is what groups a finding on the dashboard and in the check
    catalogue - "transport", "cookies" and so on - independent of severity,
    which says how bad a failure is rather than what it is about.
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


# Every category a check can belong to, in the order the catalogue and the
# dashboard show them. A category groups checks by subject - what they are
# about - which is orthogonal to severity, which says how bad a failure is.
# OpenCloud's own hardening - what an administrator can actually configure on
# the instance - leads; the generic web checks that apply to any HTTPS service
# follow, headers (including CSP) before transport/TLS.
CATEGORIES: tuple[str, ...] = (
    "cookies",
    "authentication",
    "sharing",
    "exposure",
    "embedding",
    "lifecycle",
    "proxy",
    "headers",
    "transport",
)


HARDENINGS: dict[str, Hardening] = {
    "basicAuthDisabled": Hardening(
        id="basicAuthDisabled",
        category="authentication",
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
        category="headers",
        title="The Content-Security-Policy allows inline scripts or eval",
        meaning=(
            "The script-src directive (or default-src, when script-src is "
            "absent) contains 'unsafe-inline' or 'unsafe-eval', which removes "
            "most of the protection a CSP gives against cross-site scripting: "
            "'unsafe-inline' lets injected markup or an event handler execute "
            "outright, and 'unsafe-eval' lets a gadget already in loaded code "
            "turn attacker-controlled input into code via eval() or the "
            "Function constructor. Note that 'unsafe-inline' is OpenCloud's "
            "shipped default, so an instance failing this check on that "
            "keyword alone is not misconfigured - it is unmodified. A policy "
            "that pairs 'unsafe-inline' with a nonce or a hash (the standard "
            "'strict-dynamic' rollout pattern) does not fail this check: every "
            "browser that understands nonces ignores 'unsafe-inline' in that "
            "case, so the keyword is only a fallback for browsers old enough "
            "to ignore the nonce too."
        ),
        remediation=(
            "Point PROXY_CSP_CONFIG_FILE_LOCATION at a csp.yaml without "
            "'unsafe-inline' or 'unsafe-eval' (or "
            "PROXY_CSP_CONFIG_FILE_OVERRIDE_LOCATION to replace the default "
            "outright) - or, to keep supporting older browsers, move to a "
            "nonce- or hash-based policy with 'strict-dynamic' instead of "
            "dropping 'unsafe-inline' outright. Test it first: the web "
            "interface currently relies on inline scripts and styles, so a "
            "strict policy is likely to break the UI and any connected office "
            "or IDP service."
        ),
        reference=DOCS_PROXY,
        setting="PROXY_CSP_CONFIG_FILE_LOCATION",
    ),
    "publicLinkPasswordEnforced": Hardening(
        id="publicLinkPasswordEnforced",
        category="sharing",
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
        category="sharing",
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
        category="authentication",
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
        category="authentication",
        title="The password policy is disabled or allows short passwords",
        meaning=(
            "The public capabilities show that the policy is disabled or its "
            "minimum length is below 8 characters. This governs public link "
            "passwords, not identity-provider account passwords."
        ),
        remediation=(
            "Set OC_PASSWORD_POLICY_DISABLED=false and "
            "OC_PASSWORD_POLICY_MIN_CHARACTERS to 8 or more (8 is the default). "
            "OC_PASSWORD_POLICY_MIN_{LOWERCASE,UPPERCASE,DIGITS,SPECIAL}_"
            "CHARACTERS and a banned-password list tighten it further."
        ),
        reference=DOCS_LINK_PASSWORD,
        setting="OC_PASSWORD_POLICY_MIN_CHARACTERS",
    ),
    "passwordPolicyComplexity": Hardening(
        id="passwordPolicyComplexity",
        category="authentication",
        title="The password policy no longer requires mixed characters",
        meaning=(
            "OpenCloud requires at least one lowercase letter, one uppercase "
            "letter, one digit and one special character in a public link "
            "password by default. The capabilities document reports at least "
            "one of those minimums as zero, so somebody lowered it - a "
            "twelve-character policy that accepts 'aaaaaaaaaaaa' is a length "
            "requirement rather than a password policy. Reported only when "
            "the instance publishes the minimums at all, which a disabled "
            "policy does not: that case is passwordPolicyEnforced's."
        ),
        remediation=(
            "Set OC_PASSWORD_POLICY_MIN_LOWERCASE_CHARACTERS, "
            "OC_PASSWORD_POLICY_MIN_UPPERCASE_CHARACTERS, "
            "OC_PASSWORD_POLICY_MIN_DIGITS and "
            "OC_PASSWORD_POLICY_MIN_SPECIAL_CHARACTERS back to 1 or more. "
            "Each defaults to 1, so an instance that fails this had them "
            "lowered deliberately."
        ),
        reference=DOCS_LINK_PASSWORD,
        setting="OC_PASSWORD_POLICY_MIN_SPECIAL_CHARACTERS",
    ),
    "hstsLongMaxAge": Hardening(
        id="hstsLongMaxAge",
        category="transport",
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
        category="transport",
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
        category="transport",
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
        reference=DOCS_REVERSE_PROXY,
    ),
    "identityProviderDetected": Hardening(
        id="identityProviderDetected",
        category="proxy",
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
    # The four below are read from the same discovery document
    # identityProviderDetected already fetches, so they cost no extra request.
    # Each is reported only when the document actually publishes the field it
    # reads: an absent measurement stays an unknown here as everywhere else,
    # and OpenCloud's built-in provider omits several of them outright.
    "oidcPkceSupported": Hardening(
        id="oidcPkceSupported",
        category="authentication",
        title="The identity provider does not offer PKCE with S256",
        meaning=(
            "The discovery document publishes code_challenge_methods_supported "
            "without S256, so the authorization code flow runs without Proof "
            "Key for Code Exchange. OpenCloud's desktop, mobile and web clients "
            "are public clients that cannot keep a secret, and without PKCE an "
            "authorization code intercepted on the redirect - by another app "
            "registered for the same loopback port, or out of a proxy log - can "
            "be exchanged for tokens by whoever took it. Reported only when the "
            "provider publishes the field at all: OpenCloud's built-in provider "
            "omits it, and an absent answer is not a failing one."
        ),
        remediation=(
            "Require PKCE with S256 on the provider. In Keycloak the client's "
            "Proof Key for Code Exchange setting is S256; in Authentik the "
            "client type is public with PKCE required; in Authelia the client "
            "carries require_pkce: true and pkce_challenge_method: S256."
        ),
        reference=DOCS_OAUTH_METADATA,
    ),
    "oidcImplicitFlowDisabled": Hardening(
        id="oidcImplicitFlowDisabled",
        category="authentication",
        title="The identity provider still offers the implicit flow",
        meaning=(
            "response_types_supported offers a response type that returns a "
            "token straight from the authorization endpoint ('token' or "
            "'id_token'), which is the implicit flow. It puts access tokens in "
            "the URL fragment, where they reach the browser history, the "
            "Referer header and any script on the page; OAuth 2.1 removes it "
            "for that reason. Reported only for an external provider: "
            "OpenCloud's built-in provider offers these response types and "
            "cannot be reconfigured, so the finding would name something its "
            "operator cannot change."
        ),
        remediation=(
            "Restrict the client to the authorization code flow. Keycloak's "
            "client has Implicit flow and Standard flow as separate switches - "
            "leave only Standard on; Authentik and Authelia list the allowed "
            "response types or grant types per client."
        ),
        reference=DOCS_OIDC_DISCOVERY,
    ),
    "oidcSigningAlgorithmStrong": Hardening(
        id="oidcSigningAlgorithmStrong",
        category="authentication",
        title="ID tokens may be signed with a weak or absent algorithm",
        meaning=(
            "id_token_signing_alg_values_supported offers 'none' or a symmetric "
            "HMAC algorithm (HS256 and its siblings). 'none' means an unsigned "
            "ID token is acceptable, so anybody can write one. An HMAC "
            "algorithm signs with the client secret rather than a private key, "
            "so every party holding that secret - including a public client "
            "that cannot keep it - can forge a token for any user. OpenCloud's "
            "built-in provider signs with PS256 and passes this."
        ),
        remediation=(
            "Offer only asymmetric signing algorithms (RS256, PS256, ES256 or "
            "EdDSA) for ID tokens and remove 'none' and the HS family from the "
            "provider's list."
        ),
        reference=DOCS_OIDC_DISCOVERY,
    ),
    "oidcEndpointsUseHttps": Hardening(
        id="oidcEndpointsUseHttps",
        category="authentication",
        title="The identity provider publishes an endpoint on plain HTTP",
        meaning=(
            "At least one URL in the discovery document - the issuer, or the "
            "authorization, token, userinfo or JWKS endpoint - is an http:// "
            "address. Every one of them carries either a credential, an "
            "authorization code or the keys tokens are verified against, so a "
            "plaintext hop is enough to read or rewrite a sign-in. OpenID "
            "Connect requires TLS for these endpoints."
        ),
        remediation=(
            "Publish the provider over HTTPS and set its issuer to the https:// "
            "address. An http:// issuer usually means the provider is behind a "
            "terminating proxy but has not been told its public URL."
        ),
        reference=DOCS_OIDC_DISCOVERY,
    ),
    "reverseProxyDetected": Hardening(
        id="reverseProxyDetected",
        category="proxy",
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


# The findings of the extra-check pass. They are not hardening flags - nothing
# in OpenCloud switches them on - but they are the checks that actually cap a
# rating, so leaving them unexplained meant the one part of a report an
# operator has to act on was the one part that said nothing. They share the
# shape of the hardenings above so that one lookup explains all three
# namespaces.
CHECKS: dict[str, Hardening] = {
    "tlsHandshake": Hardening(
        id="tlsHandshake",
        category="transport",
        title="The TLS handshake failed",
        meaning=(
            "No TLS connection could be established at all, even with "
            "certificate verification switched off. Everything the scan says "
            "about the transport below rests on a connection that was never "
            "made, so the instance is either not serving TLS on this port or is "
            "serving something the client could not negotiate."
        ),
        remediation=(
            "Check that the port really terminates TLS, that the certificate "
            "and key load, and that the server offers a protocol version and "
            "cipher suite a current client accepts."
        ),
        reference=DOCS_TLS,
    ),
    "tlsTrusted": Hardening(
        id="tlsTrusted",
        category="transport",
        title="The certificate chain is not trusted",
        meaning=(
            "The certificate does not validate against the public trust store: "
            "it is self-signed, issued by an unknown authority, or served "
            "without its intermediate certificates. 'opencloud init' generates a "
            "self-signed certificate unless real ones are configured, so this is "
            "the most common finding on a fresh deployment - and it means every "
            "client either sees a warning or has been taught to ignore one."
        ),
        remediation=(
            "Issue a certificate from a public authority - Let's Encrypt through "
            "the reverse proxy is the usual route - and serve the full chain, "
            "intermediates included. An internal authority is fine as long as it "
            "is in the trust store of every client, but it will still fail this "
            "check, which is measured from outside."
        ),
        reference=DOCS_TLS,
    ),
    "tlsProtocol": Hardening(
        id="tlsProtocol",
        category="transport",
        title="An outdated TLS protocol version was negotiated",
        meaning=(
            "The connection came up on something older than TLS 1.2. TLS 1.0 and "
            "1.1 have been deprecated since 2021 and are refused outright by "
            "current browsers, so this both weakens the transport and is on its "
            "way to breaking access entirely."
        ),
        remediation=(
            "Set the minimum protocol version to TLS 1.2 - preferably 1.3 - in "
            "whatever terminates TLS, and remove the older versions from the "
            "offered set rather than merely preferring the newer ones."
        ),
        reference=DOCS_TLS,
    ),
    "tlsCertificate": Hardening(
        id="tlsCertificate",
        category="transport",
        title="The certificate expires soon, or has expired",
        meaning=(
            "The remaining validity is below the configured threshold "
            "(--tls-min-days, 14 by default). An expired certificate stops "
            "clients dead, and unlike most findings this one has a date on it: "
            "it will fail whether or not anybody acts."
        ),
        remediation=(
            "Renew the certificate, and fix the renewal rather than the "
            "certificate: an automated issuer that has stopped renewing is the "
            "usual cause. Check that the reload after renewal actually reaches "
            "the process serving TLS."
        ),
        reference=DOCS_TLS,
    ),
    "tlsDeprecatedProtocol": Hardening(
        id="tlsDeprecatedProtocol",
        category="transport",
        title="TLS 1.0 or TLS 1.1 is still accepted",
        meaning=(
            "The server negotiated a current protocol with this scan and then "
            "completed a second handshake pinned to a deprecated one, so both "
            "are on offer. The version a modern browser gets says nothing about "
            "the version an attacker can force: it is the oldest version "
            "accepted that decides what the transport is worth. RFC 8996 "
            "deprecated TLS 1.0 and 1.1 in 2021, and both carry cipher suites "
            "with no modern replacement."
        ),
        remediation=(
            "Set the minimum protocol version to TLS 1.2 in whatever terminates "
            "TLS and reload it. Preferring newer versions is not enough - the "
            "old ones have to be removed from the offered set."
        ),
        reference=DOCS_TLS,
    ),
    "tlsHostname": Hardening(
        id="tlsHostname",
        category="transport",
        title="The certificate does not cover the name it is served for",
        meaning=(
            "No subject alternative name in the certificate matches the host "
            "that was scanned - a certificate for a different domain, for "
            "'localhost', or one with no alternative names at all, which every "
            "client has rejected for years. Clients cannot tell this apart from "
            "an interception, so they are right to refuse the connection."
        ),
        remediation=(
            "Issue the certificate for the name users actually type, including "
            "every alias the instance answers to, and put each of them in the "
            "subject alternative name extension rather than only in the common "
            "name."
        ),
        reference=DOCS_TLS,
    ),
    "tlsChain": Hardening(
        id="tlsChain",
        category="transport",
        title="The server does not send a complete certificate chain",
        meaning=(
            "The certificates the server sent do not reach a root in the public "
            "trust store. An intermediate is missing, or the issuing authority "
            "is private. This is the classic finding that looks fine in a "
            "desktop browser - browsers cache intermediates they have seen "
            "elsewhere and fetch missing ones - and fails on mobile clients, "
            "command-line tools and anything doing machine-to-machine calls."
        ),
        remediation=(
            "Serve the full chain: the leaf certificate followed by every "
            "intermediate, in order, and without the root. Most issuers publish "
            "a 'fullchain' file for exactly this."
        ),
        reference=DOCS_TLS,
    ),
    "tlsCertificateLifetime": Hardening(
        id="tlsCertificateLifetime",
        category="transport",
        title="The certificate was issued for an unusually long time",
        meaning=(
            "Its validity period is longer than the 398 days the CA/Browser "
            "Forum allows for publicly trusted certificates, which points at a "
            "private authority or a hand-made certificate. The risk is the key: "
            "a certificate valid for years stays valid for years after the key "
            "behind it leaks, and nothing forces the rotation that would "
            "otherwise happen on its own."
        ),
        remediation=(
            "Move to short-lived, automatically renewed certificates. If a "
            "private authority has to stay, shorten its validity period and "
            "automate the renewal rather than lengthening the certificate to "
            "avoid the work."
        ),
        reference=DOCS_TLS,
    ),
    "tlsCipherSuite": Hardening(
        id="tlsCipherSuite",
        category="transport",
        title="The negotiated TLS cipher suite is weak",
        meaning=(
            "The TLS connection completed with a cipher suite that uses a "
            "legacy primitive or does not provide forward secrecy. A modern "
            "protocol version alone does not protect a connection whose normal "
            "cipher selection is weak. This finding judges the suite this scan "
            "actually negotiated; it does not claim to enumerate every suite "
            "the server might offer."
        ),
        remediation=(
            "Configure the TLS terminator to use TLS 1.2+ cipher suites with "
            "AEAD encryption and ephemeral ECDHE or DHE key exchange, then "
            "reload it. Remove NULL, RC4, DES/3DES, MD5, SHA-1 and static-RSA "
            "suites rather than merely preferring stronger ones."
        ),
        reference=DOCS_TLS,
    ),
    "tlsCertificatePolicy": Hardening(
        id="tlsCertificatePolicy",
        category="transport",
        title="The certificate uses a weak key or signature",
        meaning=(
            "The presented certificate has an RSA key below 2048 bits, an EC "
            "key below 256 bits, or an MD5/SHA-1 signature. Those parameters "
            "are no longer an adequate protection for an internet-facing "
            "certificate, even if the certificate has not expired."
        ),
        remediation=(
            "Issue a replacement certificate with at least a 2048-bit RSA key "
            "or a 256-bit EC key and a SHA-256-or-stronger signature. Update "
            "the issuing CA template as well, so the next renewal does not "
            "restore the weak parameters."
        ),
        reference=DOCS_TLS,
    ),
    "tlsCaaRecord": Hardening(
        id="tlsCaaRecord",
        category="transport",
        title="No CAA record restricts who may issue a certificate",
        meaning=(
            "The domain has no CAA (Certification Authority Authorization) "
            "record naming an 'issue' or 'issuewild' property, so any "
            "publicly trusted certificate authority can be asked to issue a "
            "certificate for it - not just the one actually used. This "
            "checks only the exact name scanned, not the RFC 8659 "
            "parent-domain fallback chain, and it never judges which CA a "
            "record names, only whether one restricts issuance at all."
        ),
        remediation=(
            "Add a CAA record at the DNS zone naming the certificate "
            "authority already in use, e.g. "
            "'example.com. CAA 0 issue \"letsencrypt.org\"'. This is a DNS "
            "change at the domain's own zone, not an OpenCloud setting."
        ),
        reference=DOCS_TLS,
    ),
    "tlsAddressParity": Hardening(
        id="tlsAddressParity",
        category="transport",
        title="IPv4 and IPv6 do not present the same TLS service",
        meaning=(
            "The hostname publishes both address families, but their TLS "
            "endpoints differ or one cannot complete a handshake. Visitors may "
            "reach either address, so an old IPv6 listener can bypass the TLS "
            "configuration maintained on IPv4."
        ),
        remediation=(
            "Deploy the same TLS terminator configuration and certificate on "
            "both address families, or remove the stale DNS record until it is "
            "ready."
        ),
        reference=DOCS_TLS,
    ),
    "cookieSecure": Hardening(
        id="cookieSecure",
        category="cookies",
        title="An observed cookie can travel over HTTP",
        meaning="A cookie sent by the public response lacks the Secure attribute.",
        remediation="Set Secure on every cookie the reverse proxy or application issues.",
        reference=DOCS_REVERSE_PROXY,
    ),
    "cookieHttpOnly": Hardening(
        id="cookieHttpOnly",
        category="cookies",
        title="An observed cookie is readable by page scripts",
        meaning="A cookie sent by the public response lacks the HttpOnly attribute.",
        remediation="Set HttpOnly unless a browser script must deliberately read that cookie.",
        reference=DOCS_REVERSE_PROXY,
    ),
    "cookieSameSite": Hardening(
        id="cookieSameSite",
        category="cookies",
        title="An observed cookie has no cross-site policy",
        meaning="A cookie sent by the public response lacks a SameSite attribute.",
        remediation="Set SameSite=Lax or Strict unless a documented cross-site flow needs None.",
        reference=DOCS_REVERSE_PROXY,
    ),
    "cookiePrefix": Hardening(
        id="cookiePrefix",
        category="cookies",
        title="An observed cookie carries no name prefix, or breaks the one it claims",
        meaning=(
            "The '__Host-' and '__Secure-' name prefixes are the only cookie "
            "protection a browser enforces on the name itself, which is what "
            "makes them survive the things the attributes do not: a sibling "
            "subdomain, or plain HTTP on the same host, can overwrite an "
            "ordinary session cookie however carefully its Secure and HttpOnly "
            "flags were set, because neither attribute stops a cookie from "
            "being *written*. A '__Host-' cookie may only be set over HTTPS, "
            "with Path=/ and no Domain, so nothing but the exact origin can "
            "touch it. A cookie that names a prefix without honouring its rules "
            "is worse than one that never claimed it: every browser rejects it "
            "outright, so the session silently does not work."
        ),
        remediation=(
            "Rename the session cookie to '__Host-<name>' and set it with "
            "Secure, Path=/ and no Domain attribute - or '__Secure-<name>' when "
            "it genuinely has to be shared across subdomains. Where the cookie "
            "comes from a reverse proxy or an identity provider rather than "
            "from OpenCloud, rename it there."
        ),
        reference=f"{DOCS_MDN_HEADERS}/Set-Cookie#cookie_prefixes",
    ),
    "tlsOcspStapling": Hardening(
        id="tlsOcspStapling",
        category="transport",
        title="No OCSP response is stapled to the handshake",
        meaning=(
            "The certificate names an OCSP responder, so revocation can be "
            "checked - but the server does not attach the answer to the "
            "handshake. Each client then has to ask the authority itself, which "
            "tells that authority who visits this instance and, when it is slow "
            "or unreachable, is usually skipped rather than treated as a "
            "failure. Stapling makes revocation actually work. It is a low "
            "finding because most current authorities, Let's Encrypt among them, "
            "no longer publish a responder at all - the check simply does not "
            "apply to those certificates."
        ),
        remediation=(
            "Switch on OCSP stapling in whatever terminates TLS and give it a "
            "writable cache directory, so a slow responder degrades into a "
            "stale answer rather than into none."
        ),
        reference=DOCS_TLS,
    ),
    "tlsCertificateTransparency": Hardening(
        id="tlsCertificateTransparency",
        category="transport",
        title="The certificate carries no Certificate Transparency proof",
        meaning=(
            "No signed certificate timestamps are embedded in the certificate, "
            "so it was never published to a Certificate Transparency log. Chrome "
            "and Safari refuse a publicly trusted certificate without them "
            "outright - this is an outage waiting for the next browser release, "
            "not only a transparency gap. The logs are also what lets a domain "
            "owner find out that somebody else was issued a certificate for "
            "their name; a certificate outside them cannot be noticed that way. "
            "Only checked for a certificate that chains to a public root: a "
            "private or self-signed CA cannot log anything and is not expected "
            "to."
        ),
        remediation=(
            "Reissue through a certificate authority that embeds signed "
            "certificate timestamps - every public one has done so for years, "
            "Let's Encrypt included. A certificate that lacks them was almost "
            "certainly issued by a private CA that is nonetheless in the client "
            "trust store."
        ),
        reference=DOCS_TLS,
    ),
    "tlsEarlyData": Hardening(
        id="tlsEarlyData",
        category="transport",
        title="The server accepts TLS 1.3 early data",
        meaning=(
            "The session tickets this server issues permit early data, so a "
            "resuming client may send its first request in the 0-RTT flight. "
            "That flight has no replay protection at the TLS layer by design: "
            "anyone who can record it can send it again, and the server cannot "
            "tell the copy from the original. For a file service that is a "
            "request to move, copy or delete replayed at a moment of somebody "
            "else's choosing. It is a low finding because exploiting it needs a "
            "network position, and because a correct server restricts 0-RTT to "
            "idempotent requests - but nothing on the wire proves it does."
        ),
        remediation=(
            "Switch early data off in whatever terminates TLS (Nginx "
            "'ssl_early_data off', the default; Caddy and Traefik do not enable "
            "it), unless a measured latency problem justifies it and the "
            "application is known to reject replayed non-idempotent requests."
        ),
        reference=DOCS_TLS,
    ),
    "corsOriginRestricted": Hardening(
        id="corsOriginRestricted",
        category="exposure",
        title="Cross-origin requests are accepted from any site",
        meaning=(
            "The instance answered a request carrying an arbitrary Origin with "
            "an Access-Control-Allow-Origin that permits it. When "
            "Access-Control-Allow-Credentials is also true, any page on the "
            "internet can make a visitor's browser send its OpenCloud session "
            "cookie to this instance and then read the reply - the whole file "
            "listing, the user directory, the contents of a share - with no "
            "interaction beyond visiting that page. This is OpenCloud's "
            "shipped default rather than a mistake somebody made: "
            "OC_CORS_ALLOW_ORIGINS defaults to '*' and OC_CORS_ALLOW_CREDENTIALS "
            "to true, and a middleware asked for both commonly reflects the "
            "requesting origin back, which is exactly the combination browsers "
            "were meant to forbid."
        ),
        remediation=(
            "Set OC_CORS_ALLOW_ORIGINS to the exact origins that must reach the "
            "API - the web interface's own origin, and any office or client "
            "application deliberately hosted elsewhere - rather than leaving it "
            "at '*'. Set OC_CORS_ALLOW_CREDENTIALS=false unless one of those "
            "origins genuinely needs to send the session. The per-service forms "
            "(GRAPH_CORS_ALLOW_ORIGINS, OCS_CORS_ALLOW_ORIGINS, and so on) "
            "override the shared name where one service needs a wider list."
        ),
        reference=DOCS_GRAPH,
        setting="OC_CORS_ALLOW_ORIGINS",
    ),
    "traceMethodDisabled": Hardening(
        id="traceMethodDisabled",
        category="exposure",
        title="The server answers the HTTP TRACE method",
        meaning=(
            "TRACE makes the server echo the request back, headers included. "
            "Anything the browser attached on the way - the session cookie, an "
            "Authorization header, a header a reverse proxy added - comes back "
            "inside the response body, where a script that could never read "
            "those directly can read them as text. OpenCloud does not implement "
            "TRACE, so an instance answering it has a reverse proxy or an "
            "application server in front that does."
        ),
        remediation=(
            "Refuse TRACE in whatever fronts the instance: Apache "
            "'TraceEnable off', Nginx returns 405 for it already unless a "
            "location was written to pass every method through, and Traefik or "
            "Caddy need a rule limiting the methods forwarded upstream."
        ),
        reference=DOCS_REVERSE_PROXY,
    ),
    "httpsAvailable": Hardening(
        id="httpsAvailable",
        category="transport",
        title="The instance is only reachable over plain HTTP",
        meaning=(
            "HTTPS could not be used at all, so the scan fell back to http://. "
            "Credentials, session cookies and every file travel unencrypted and "
            "can be read or altered by anything on the path."
        ),
        remediation=(
            "Terminate TLS in front of OpenCloud and serve the instance over "
            "HTTPS only. Nothing else on this report matters as much."
        ),
        reference=DOCS_REVERSE_PROXY,
    ),
    "directoryListing": Hardening(
        id="directoryListing",
        category="exposure",
        title="A web server is serving a directory index",
        meaning=(
            "An 'Index of /' page was returned. OpenCloud serves its own assets "
            "from the binary and never generates one, so this can only come from "
            "a web server pointed at the deployment directory - which then also "
            "serves opencloud.yaml, the boltdb files and anything else in it."
        ),
        remediation=(
            "Stop serving the deployment directory as static files. Point the "
            "web server at OpenCloud's own address as a reverse proxy instead, "
            "and switch directory indexing off (Nginx 'autoindex off', Apache "
            "'Options -Indexes')."
        ),
        reference=DOCS_REVERSE_PROXY,
    ),
    "webfingerVersionDisclosure": Hardening(
        id="webfingerVersionDisclosure",
        category="lifecycle",
        title="The webfinger document publishes the exact version",
        meaning=(
            "The unauthenticated webfinger response contains the running "
            "version. It does not create a vulnerability, but it saves an "
            "attacker the work of finding out which advisories apply."
        ),
        remediation=(
            "Strip the version from the webfinger response in the reverse proxy, "
            "or accept the disclosure: it only matters while a known advisory is "
            "unpatched, so keeping the instance current is the real fix."
        ),
        reference=DOCS_PROXY,
    ),
    "demoUsersDisabled": Hardening(
        id="demoUsersDisabled",
        category="authentication",
        title="The documented demo accounts still sign in",
        meaning=(
            "IDM_CREATE_DEMO_USERS populates the built-in identity management "
            "with five accounts - dennis, margaret, alan, lynn and mary - whose "
            "passwords are published in the OpenCloud documentation, and dennis "
            "is an administrator. The scan asked the account endpoint with one "
            "of those documented pairs and was let in, so anybody who has read "
            "the manual can sign in as well. Nothing was guessed: only the "
            "published defaults were sent, and only to the instance's own "
            "identity provider."
        ),
        remediation=(
            "Turn the demo users off (IDM_CREATE_DEMO_USERS=false) and delete "
            "the accounts that were already created - switching the setting off "
            "does not remove them. Treat the instance as compromised until the "
            "administrator account 'dennis' is gone or has a real password."
        ),
        reference="https://docs.opencloud.eu/docs/admin/resources/demo-user/",
        setting="IDM_CREATE_DEMO_USERS",
    ),
    "versionDetection": Hardening(
        id="versionDetection",
        category="lifecycle",
        title="The running version could not be determined",
        meaning=(
            "status.php returned only the legacy compatibility version, without "
            "'productversion'. Without a real version no advisory can be matched "
            "and no release state worked out, so the checks that depend on it "
            "are not merely passing - they did not run."
        ),
        remediation=(
            "Check whether something in front of the instance rewrites "
            "status.php, and whether the release is old enough not to publish "
            "'productversion' yet. Until it reports one, treat the version part "
            "of this report as unknown rather than as good."
        ),
        reference=DOCS_PROXY,
    ),
}


# Finding identifiers that carry the thing they are about after a colon:
# 'exposed:/config/opencloud.yaml', 'debugPort:9205'. The explanation belongs
# to the family, the path or port belongs in the detail the scanner recorded.
_CHECK_FAMILIES: dict[str, Hardening] = {
    "exposed": Hardening(
        id="exposed",
        category="exposure",
        title="A deployment file is publicly readable",
        meaning=(
            "A path that should never be served over HTTP answered with content. "
            "These are configuration files, databases and key material: reading "
            "them can hand over credentials, tokens or the whole data store."
        ),
        remediation=(
            "Stop serving the deployment directory. Proxy to OpenCloud's own "
            "address rather than exposing the filesystem, and confirm each "
            "reported path answers 404 afterwards. Treat anything that was "
            "readable as disclosed and rotate it."
        ),
        reference=DOCS_REVERSE_PROXY,
    ),
    "authentication": Hardening(
        id="authentication",
        category="authentication",
        title="A protected endpoint answered without demanding authentication",
        meaning=(
            "An endpoint that should require a session returned neither 401, 403 "
            "nor a redirect to the login page. Something in front of OpenCloud "
            "may be answering the request itself, or the endpoint really is open."
        ),
        remediation=(
            "Request the reported path by hand and see what answers it. A cache "
            "or error page in front of OpenCloud is the usual explanation; an "
            "endpoint genuinely reachable without a session is an incident."
        ),
        reference=DOCS_PROXY,
    ),
    "debugEndpoint": Hardening(
        id="debugEndpoint",
        category="exposure",
        title="A debug endpoint is publicly readable",
        meaning=(
            "A service debug path answered on the public address. Those "
            "endpoints expose Prometheus metrics, a configuration dump and, when "
            "pprof is on, the ability to make the process profile itself."
        ),
        remediation=(
            "Do not proxy /debug paths to the public address, and leave the "
            "debug services bound to 127.0.0.1 as they are by default "
            "(OC_DEBUG_ADDR and the per-service *_DEBUG_ADDR variables)."
        ),
        reference=DOCS_PROXY,
        setting="OC_DEBUG_ADDR",
    ),
    "debugPort": Hardening(
        id="debugPort",
        category="exposure",
        title="A service debug port is reachable",
        meaning=(
            "One of OpenCloud's per-service debug listeners accepted a "
            "connection from outside. They are bound to 127.0.0.1 by default, so "
            "reaching one means it was published - by a container port mapping, "
            "as a rule."
        ),
        remediation=(
            "Remove the port mapping that publishes it and leave the debug "
            "listeners on 127.0.0.1. If a metrics scraper needs them, reach them "
            "over the internal network rather than the public address."
        ),
        reference=DOCS_PROXY,
        setting="OC_DEBUG_ADDR",
    ),
    "backendPortClosed": Hardening(
        id="backendPortClosed",
        category="exposure",
        title="The direct OpenCloud backend port is publicly reachable",
        meaning=(
            "Port 9200 serves the same OpenCloud instance as the public address. "
            "When a reverse proxy fronts OpenCloud, publishing that listener "
            "lets clients bypass the proxy's TLS and security policy."
        ),
        remediation=(
            "Remove the public port mapping for 9200 and bind the backend to "
            "loopback or the private container network. Let only the reverse "
            "proxy reach it."
        ),
        reference=DOCS_REVERSE_PROXY,
        setting="PROXY_HTTP_ADDR",
    ),
    "webEmbedMessageOriginRestricted": Hardening(
        id="webEmbedMessageOriginRestricted",
        category="embedding",
        title="Embedded web messages trust every parent origin",
        meaning=(
            "The public web configuration sets the embed message origin to '*'. "
            "Any site can then host the web client in a frame and exchange "
            "messages with it."
        ),
        remediation=(
            "Set WEB_OPTION_EMBED_MESSAGES_ORIGIN to the exact trusted parent "
            "origin, or disable the embed integration."
        ),
        reference=DOCS_WEB,
        setting="WEB_OPTION_EMBED_MESSAGES_ORIGIN",
    ),
    "webEmbedDelegatedAuthenticationRestricted": Hardening(
        id="webEmbedDelegatedAuthenticationRestricted",
        category="embedding",
        title="Delegated iframe authentication accepts an unvalidated origin",
        meaning=(
            "Delegated authentication is enabled without naming the parent "
            "origin allowed to send credentials to the embedded web client."
        ),
        remediation=(
            "Set WEB_OPTION_EMBED_DELEGATE_AUTHENTICATION_ORIGIN to the exact "
            "trusted parent origin, or disable delegated authentication."
        ),
        reference=DOCS_WEB,
        setting="WEB_OPTION_EMBED_DELEGATE_AUTHENTICATION_ORIGIN",
    ),
    "versionDisclosure": Hardening(
        id="versionDisclosure",
        category="lifecycle",
        title="A response header publishes a software version",
        meaning=(
            "The Server or X-Powered-By header carries a version number. It is "
            "not a vulnerability by itself; it tells whoever is looking which "
            "advisories to try first."
        ),
        remediation=(
            "Strip or flatten the header in the reverse proxy - Nginx "
            "'server_tokens off', Apache 'ServerTokens Prod', or unset it "
            "outright."
        ),
        reference=DOCS_REVERSE_PROXY,
    ),
}


# The security headers checked under 'setup.headers' and 'setup.advisoryHeaders'.
# They share the shape of the hardenings above so that both can be explained by
# one lookup; which of the two blocks a name belongs to is the scanner's
# business, not this catalogue's.
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
    "Permissions-Policy": (
        (
            "Nothing restricts which browser features embedded content may use, "
            "so a framed document or an injected script can ask for the camera, "
            "the microphone or the visitor's location under this origin's name."
        ),
        (
            "Send 'Permissions-Policy: camera=(), microphone=(), geolocation=()', "
            "adding back only what a media or collaboration integration needs."
        ),
    ),
    "Cross-Origin-Opener-Policy": (
        (
            "A window this instance opened, or one that opened it, keeps a "
            "handle on this document, which is what side-channel attacks in the "
            "Spectre family need to reach data in this origin's process."
        ),
        (
            "Send 'Cross-Origin-Opener-Policy: same-origin'. Use "
            "'same-origin-allow-popups' if an OpenID Connect or office "
            "integration signs in through a popup."
        ),
    ),
    "Cross-Origin-Resource-Policy": (
        (
            "Nothing stops another site from loading this instance's responses "
            "as a subresource, so a file, a thumbnail or an avatar can be "
            "embedded elsewhere and read there."
        ),
        (
            "Send 'Cross-Origin-Resource-Policy: same-origin', or 'same-site' "
            "when a sibling subdomain has to embed OpenCloud content."
        ),
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
        category="headers",
        title=f"The {name} header is missing or too weak",
        meaning=meaning,
        remediation=remediation,
        reference=f"{DOCS_MDN_HEADERS}/{name}",
    )


def _family_hardening(family: Hardening, subject: str) -> Hardening:
    """Explain one member of a per-path or per-port finding family."""
    return Hardening(
        id=f"{family.id}:{subject}",
        title=f"{family.title} ({subject})",
        meaning=family.meaning,
        remediation=family.remediation,
        reference=family.reference,
        setting=family.setting,
        actionable=family.actionable,
        category=family.category,
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
    check = CHECKS.get(name)
    if check is not None:
        return check
    if name in _HEADER_NOTES:
        return _header_hardening(name)
    family, _, subject = name.partition(":")
    if subject and family in _CHECK_FAMILIES:
        return _family_hardening(_CHECK_FAMILIES[family], subject)
    return Hardening(
        id=name,
        title=name,
        meaning="No description is available for this identifier.",
        remediation="See the scan result for the raw finding.",
    )


def catalogue_id(name: str) -> str | None:
    """
    The identifier of the entry that *explains* this one, or ``None``.

    ``describe`` answers "what does this mean" and always answers something.
    This answers the narrower question behind a link: which entry in the
    published catalogue is the explanation, given that a reader clicking a
    finding expects to land on the paragraph about it.

    The two differ for the per-path and per-port families. A result names
    ``exposed:/config/opencloud.yaml``, and ``describe`` builds a sentence
    about that exact path, but the catalogue lists the family root
    ``exposed`` once rather than every path an instance might serve - so that
    is where the link has to go.

    ``None`` means this build cannot explain the identifier, and a caller
    should render it as plain text. A link to an anchor that does not exist
    leaves a reader on an unfamiliar page with nothing highlighted, which is
    worse than not offering the link.
    """
    if (
        name in HARDENINGS
        or name in CHECKS
        or name in _HEADER_NOTES
        # The bare family root is itself a catalogue entry - it is what
        # `all_checks` lists - so it resolves to itself, while a member of the
        # family resolves up to it.
        or name in _CHECK_FAMILIES
    ):
        return name
    family, _, subject = name.partition(":")
    if subject and family in _CHECK_FAMILIES:
        return family
    return None


def is_actionable(name: str) -> bool:
    """Whether an administrator can change the outcome of this flag."""
    return describe(name).actionable


def all_checks() -> tuple[Hardening, ...]:
    """
    Every hardening flag and scan check this build knows how to explain.

    This is the family entries themselves - ``exposed``, ``debugPort`` - not
    every ``family:subject`` finding a scan could ever report, since the
    subjects are open-ended paths and ports rather than a fixed catalogue.
    Header names are not included: :data:`_HEADER_NOTES` has no ``Hardening``
    of its own until :func:`_header_hardening` builds one, so callers that
    want those too should also describe each name in it.
    """
    return (*HARDENINGS.values(), *CHECKS.values(), *_CHECK_FAMILIES.values())


def explain(names: list[str]) -> list[str]:
    """Render explanations for several flags, in the order given."""
    return [describe(name).describe() for name in names]
