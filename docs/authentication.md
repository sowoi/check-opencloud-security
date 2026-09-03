# Authentication: what this scanner checks, and why

Ten checks look at how an instance authenticates requests: whether protected
endpoints actually demand a session, whether HTTP Basic auth is still
offered as a bypass around the identity provider, whether the documented demo
accounts still work, two properties OpenCloud's own capabilities document
publishes about account search and password strength, whether the identity
provider can be located at all, and four properties of the OpenID Connect
discovery document that provider publishes. None of them submit a guessed
credential anywhere - see [What the scan deliberately does not
answer](scanner-checks.md#what-the-scan-deliberately-does-not-answer) for what is
out of scope on principle, and the demo-account section below for the one
documented exception.

<!-- TOC -->
* [Authentication: what this scanner checks, and why](#authentication-what-this-scanner-checks-and-why)
  * [1. Do protected endpoints actually require a session: `authentication:<path>`](#1-do-protected-endpoints-actually-require-a-session-authenticationpath)
  * [2. Does the proxy still offer HTTP Basic authentication: `basicAuthDisabled`](#2-does-the-proxy-still-offer-http-basic-authentication-basicauthdisabled)
  * [3. Do the documented demo accounts still sign in: `demoUsersDisabled`](#3-do-the-documented-demo-accounts-still-sign-in-demousersdisabled)
  * [4. Is account search restricted to shared groups: `userEnumerationRestricted`](#4-is-account-search-restricted-to-shared-groups-userenumerationrestricted)
  * [5. Is the link password policy strong enough: `passwordPolicyEnforced`](#5-is-the-link-password-policy-strong-enough-passwordpolicyenforced)
  * [5a. Does it still ask for more than length: `passwordPolicyComplexity`](#5a-does-it-still-ask-for-more-than-length-passwordpolicycomplexity)
  * [6. Can the identity provider be found at all: `identityProviderDetected`](#6-can-the-identity-provider-be-found-at-all-identityproviderdetected)
  * [7. What the discovery document says about how sign-in is protected](#7-what-the-discovery-document-says-about-how-sign-in-is-protected)
  * [What else is in that document, and why none of it is checked](#what-else-is-in-that-document-and-why-none-of-it-is-checked)
  * [Severity and rating impact](#severity-and-rating-impact)
<!-- TOC -->


## 1. Do protected endpoints actually require a session: `authentication:<path>`

Three endpoints that must never answer an unauthenticated request with
content are requested without credentials:

| Path                          | Severity |
|:-------------------------------|:---------|
| `/remote.php/dav/files/`       | critical |
| `/graph/v1.0/users`             | critical |
| `/ocs/v1.php/cloud/user`        | high     |

An HTTP `401`, `403`, `405` or `501` response, a redirect to a login page, or
a `404` all count as "demanded authentication" - `405`/`501` show up when a
reverse proxy answers a `GET` on a WebDAV collection rather than OpenCloud
itself, and `404` covers a proxy that hides the path entirely rather than
challenging it. Anything else - most importantly a `200` carrying the data
that path is supposed to protect - fails the check. An endpoint that could
not be reached at all is treated as passing: a network failure is not
evidence that the endpoint is open, and this scanner would rather stay quiet
than manufacture a finding out of a timeout.

**If this fails:** request the reported path by hand and read what actually
answers it. A cache, CDN or misconfigured proxy rule serving its own error
page in front of OpenCloud is the usual explanation; an endpoint genuinely
reachable without a session is a live incident, not a hardening gap - rotate
anything the response exposed and fix the routing immediately.

## 2. Does the proxy still offer HTTP Basic authentication: `basicAuthDisabled`

The instance is asked for the `WWW-Authenticate` challenge on a protected
endpoint. A `Basic` challenge means `PROXY_ENABLE_BASIC_AUTH=true`: a
username and password can be replayed on every request without going through
the identity provider at all, bypassing single sign-on and any second factor
enforced there.

This is not treated as a plain mistake, because the alternative is often
worse in practice: CalDAV, CardDAV and most WebDAV clients cannot speak
OpenID Connect and have nothing else to authenticate with. That is why this
is rated `medium` rather than `critical` - and `low` once an external
identity provider is confirmed to handle the interactive login (see [Who
signs users in](scanner-checks.md#who-signs-users-in)), since the account
passwords those provider-backed logins protect are not the ones being
replayed here.

**Fix:** set `PROXY_ENABLE_BASIC_AUTH=false` (the default) if nothing needs
it. If a calendar, contacts or WebDAV client does, keep it on and issue those
clients app tokens rather than account passwords, so what gets replayed on
every request is revocable on its own and never the single sign-on
credential.

## 3. Do the documented demo accounts still sign in: `demoUsersDisabled`

`IDM_CREATE_DEMO_USERS=true` populates a fresh instance with five accounts -
one of them an administrator - whose names and passwords are printed in
[OpenCloud's own documentation][opencloud-demo-users]. This check only runs
once the scan has established that the instance's *own* identity provider
handles login (an external Keycloak, Authentik or Authelia has no such
accounts to test), and it sends exactly those published pairs to that
provider - nothing guessed, and nothing sent to a third party.

Left on past evaluation, this is a `critical` finding: it is an
administrator account whose password is public knowledge, and it caps the
rating at `D` on its own regardless of everything else the scan found.

**Fix:** set `IDM_CREATE_DEMO_USERS=false` **and** delete the accounts that
were already created - turning the setting off does not remove them.
Wherever this fails, treat the instance as compromised until the
administrator account is gone or has been given a real password: the
credentials are not secret, they are published.

## 4. Is account search restricted to shared groups: `userEnumerationRestricted`

OpenCloud's capabilities document reports whether user search is limited to
members of a shared group. The restricted state is hardcoded in current
releases, so this check passes on effectively every instance; it is kept so
that a future release that makes the setting configurable is caught the
moment it starts reporting something other than restricted.

**If this fails:** there is currently no setting to change - the finding
describes OpenCloud's own configuration, not something this scanner's
`--debug` remediation can point you at.

## 5. Is the link password policy strong enough: `passwordPolicyEnforced`

The capabilities document's `password_policy.min_characters` is read and
compared against 8. This governs the passwords a user can set on a **public
share link**, not identity-provider account passwords - see [Public link
sharing](sharing.md) for the checks that actually gate whether a link needs a
password at all.

**Fix:** set `OC_PASSWORD_POLICY_DISABLED=false` and
`OC_PASSWORD_POLICY_MIN_CHARACTERS` to `8` or higher (`8` is already the
default, so this usually means something explicitly lowered it).
`OC_PASSWORD_POLICY_MIN_{LOWERCASE,UPPERCASE,DIGITS,SPECIAL}_CHARACTERS` and a
banned-password list tighten it further - see [the link password policy
docs][link-password].

## 5a. Does it still ask for more than length: `passwordPolicyComplexity`

A minimum length is not a password policy on its own. OpenCloud's default
policy also requires **one lowercase letter, one uppercase letter, one digit
and one special character**, and each of those minimums is a setting somebody
can lower to zero. A twelve-character policy with all four lowered accepts
`aaaaaaaaaaaa`, which satisfies `passwordPolicyEnforced` and nothing else.

The four `min_*_characters` fields are read from the same capabilities
document, and the check passes when every one of them is at least 1.

**This is deliberately a second flag rather than a stricter
`passwordPolicyEnforced`.** The older flag answers "is there a policy, and is
it long enough"; this one answers "is it still the policy OpenCloud ships".
Folding them together would change what an existing alert means without
changing its name.

**Reported only when the instance publishes all four minimums.** A policy that
is switched off publishes none of them - that case is `passwordPolicyEnforced`
failing, not this one - and an absent measurement stays an unknown rather than
becoming a failure, as everywhere else in the scan.

**Fix:** set `OC_PASSWORD_POLICY_MIN_LOWERCASE_CHARACTERS`,
`OC_PASSWORD_POLICY_MIN_UPPERCASE_CHARACTERS`,
`OC_PASSWORD_POLICY_MIN_DIGITS` and
`OC_PASSWORD_POLICY_MIN_SPECIAL_CHARACTERS` back to `1` or more. Each already
defaults to `1`, so an instance that fails this had them lowered on purpose.

## 6. Can the identity provider be found at all: `identityProviderDetected`

Everything above asks whether a credential is accepted. This one asks the
prior question - *who issues the tokens?* - and answers it by reading
`/.well-known/openid-configuration` once, without following redirects:

- a `200` carrying JSON: the `issuer` field is taken;
- a redirect: the `Location` header is resolved against the instance and
  taken instead, which is how a proxy that hands the well-known path to an
  external provider is recognised;
- anything else, or an issuer that is not an absolute `http(s)` URL with a
  hostname: the flag fails.

Nothing is submitted to find this out. No login form is filled in and no
credential is sent - working out who signs users in must not become an
attempt to sign in.

A failure is far more often a **proxy not forwarding `/.well-known/`** than
an instance with no sign-in at all, which is why it never caps the rating.

The issuer that is found is also recorded as context rather than a verdict.
An issuer on a different host than the instance is reported as an
**external** provider - Keycloak, Authentik or Authelia in front of
OpenCloud - and the vendor is named so the result can point at that project's
security advisories. Using OpenCloud's own built-in provider is not a
finding: neither arrangement is required, and neither fails anything.

**If this fails:** confirm the reverse proxy forwards `/.well-known/` to
whatever issues tokens - see [Reverse proxies](reverse-proxy.md). If sign-in
genuinely is not configured, OpenCloud ships its own provider and can be
pointed at an external one.

## 7. What the discovery document says about how sign-in is protected

The request above is already paid for. The document it returns is public
evidence in the sense [ADR 0022](../adr/0022-identity-provider-versions-require-public-evidence.md)
means it - unauthenticated, read-only, published on purpose - and four of its
fields say something an operator can act on. Reading them costs **no extra
HTTP request**: the same response that yielded the issuer yields all four.

| Flag | Field | Fails when |
|:--|:--|:--|
| `oidcPkceSupported` | `code_challenge_methods_supported` [^rfc8414] | `S256` is not among the methods |
| `oidcImplicitFlowDisabled` | `response_types_supported` | a type returns a token from the authorization endpoint (`token`, `id_token`) |
| `oidcSigningAlgorithmStrong` | `id_token_signing_alg_values_supported` | it contains `none` or an `HS` algorithm |
| `oidcEndpointsUseHttps` | `issuer` and the endpoint URLs | any of them is an `http://` address |

[^rfc8414]: Providers publish it in the discovery document, but the field is
    defined by [OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html#section-2)
    rather than by OpenID Connect Discovery, which is why an OIDC-only provider
    may legitimately omit it.

**Every one of them is skipped when the document does not publish the field.**
That is the same rule as `passwordPolicyComplexity`: an absent measurement is
an unknown, never a failure. It matters more here than usual, because
OpenCloud's built-in provider omits `code_challenge_methods_supported`
entirely - rating that absence as "no PKCE" would fail every stock instance
for something its operator cannot change.

**`oidcImplicitFlowDisabled` is reported for an external provider only.**
OpenCloud's built-in provider ([libregraph/lico][lico]) publishes
`response_types_supported` as `id_token token`, `id_token`, `code id_token`
and `code id_token token` - implicit and hybrid, with no plain `code` - and
none of that is configurable. A finding an operator cannot act on is worse
than none, so it is raised only where it can be acted on: in front of
Keycloak, Authentik or Authelia, where the flows really are separate
switches. [Securing a deployment](secure-deployment.md#keycloak) already
tells you to require PKCE and the code flow there; this is what finally
checks that you did.

**`oidcEndpointsUseHttps` is measured only when the instance itself answered
over HTTPS.** An instance scanned over plain HTTP publishes `http://`
endpoints because that is how it was asked, and reporting that would restate
what `httpsEnforced` already says once, in the right place. The finding worth
having is the disagreement: an HTTPS instance whose provider still advertises
`http://`, which is a provider behind a terminating proxy that was never told
its public URL.

**Why these four and not the obvious fifth.** `none` in
`id_token_signing_alg_values_supported` means an unsigned ID token is
acceptable, so anybody can write one; an `HS` algorithm signs with the client
secret, and OpenCloud's clients are public clients that cannot keep a secret,
so every party holding it can mint a token for any user. OpenCloud's built-in
provider signs with `PS256` and passes.

## What else is in that document, and why none of it is checked

The discovery document publishes a good deal more than these four flags read.
Verified against [libregraph/lico][lico]'s `oidc/provider/provider.go`
(`InitializeMetadata`), which is what OpenCloud's built-in provider serves:

| Field | Why there is no check |
|:--|:--|
| `token_endpoint_auth_methods_supported` | The obvious candidate, and not a finding. Offering only `client_secret_basic` is not a weakness, and `none` - the value that looks alarming - is exactly what OpenCloud's public desktop, mobile and web clients need. lico publishes both. A flag here would either never fire or fire on every instance. |
| `request_object_signing_alg_values_supported` | lico lists `none` among them, but this governs signed *request objects*, not ID tokens. An unsigned request object is not an unsigned token, and OpenCloud's clients do not send request objects at all. |
| `scopes_supported`, `claims_supported` | Say what the provider can be asked for, not what it grants. Which scopes a *client* is allowed is per-client configuration the document does not show. |
| `subject_types_supported` | lico publishes `public` and nothing else. `pairwise` is a privacy feature for multi-tenant providers; requiring it of a single-tenant OpenCloud deployment would be noise. |
| `registration_endpoint` | Its presence does not mean open dynamic registration - whether registration needs an initial access token is not published. Guessing would be a confident claim from weak evidence, which is the thing [ADR 0022](../adr/0022-identity-provider-versions-require-public-evidence.md) exists to forbid. |

## Severity and rating impact

`authentication:<path>` and `demoUsersDisabled` are `extraChecks`, reported
and rating-capped whenever they run at all, at their own severities above -
see the extra-checks table in [the main
README](scanner-checks.md#what-the-scanner-checks). `basicAuthDisabled`,
`userEnumerationRestricted`, `passwordPolicyEnforced`,
`passwordPolicyComplexity`, `identityProviderDetected` and the four `oidc*`
flags are hardening flags,
reported only with `--check-hardening` (or always on the web result); a
failed hardening flag does not cap the rating by itself, it raises an
otherwise-`OK` Icinga result to `WARNING` and is listed in the
`hardenings_missing` line - see [Hardening
checks](../README.md#hardening-checks).

[opencloud-demo-users]: https://docs.opencloud.eu/docs/admin/resources/demo-user/
[link-password]: https://docs.opencloud.eu/docs/admin/configuration/link-password-policy
[lico]: https://github.com/libregraph/lico
