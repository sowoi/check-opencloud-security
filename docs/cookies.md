# Cookie attributes: what this scanner checks, and why

Every `Set-Cookie` header the public response actually sends is inspected for
three attributes browsers use to limit what a cookie can be used for. Nothing
is guessed and no cookie value is retained - only the attributes on cookies
OpenCloud or its reverse proxy already sent are read.

If the scanned response sets no cookie at all, none of these three checks
appear in the result: there is nothing to grade, and a check that always
passed because it never ran would be misleading.

<!-- TOC -->
* [Cookie attributes: what this scanner checks, and why](#cookie-attributes-what-this-scanner-checks-and-why)
  * [1. Does the cookie require HTTPS: `cookieSecure`](#1-does-the-cookie-require-https-cookiesecure)
  * [2. Can page scripts read the cookie: `cookieHttpOnly`](#2-can-page-scripts-read-the-cookie-cookiehttponly)
  * [3. Is the cookie sent on cross-site requests: `cookieSameSite`](#3-is-the-cookie-sent-on-cross-site-requests-cookiesamesite)
  * [4. Does the cookie name carry a prefix: `cookiePrefix`](#4-does-the-cookie-name-carry-a-prefix-cookieprefix)
  * [Severity and rating impact](#severity-and-rating-impact)
<!-- TOC -->


## 1. Does the cookie require HTTPS: `cookieSecure`

A cookie without `Secure` will be sent over a plain HTTP connection if the
browser ever makes one to the same host - a stray `http://` link, a mixed
redirect, or a captive portal are all it takes. Once that happens, the cookie
crosses the network in clear text and can be replayed by anyone who saw it.

**Fix:** set `Secure` on every cookie the reverse proxy or application issues.
If the instance terminates TLS in a reverse proxy, this is usually the
proxy's own session or CSRF cookie rather than one OpenCloud itself sets - see
[Reverse proxies](reverse-proxy.md) for the header set this check reads.

## 2. Can page scripts read the cookie: `cookieHttpOnly`

Without `HttpOnly`, JavaScript running on the page can read the cookie
through `document.cookie`. A cookie that carries a session or CSRF token has
no legitimate reason to be readable by page scripts; being readable only
means that a single successful cross-site scripting injection can steal it
outright, turning what would otherwise be a contained UI bug into full
session theft.

**Fix:** set `HttpOnly` unless a browser script must deliberately read that
specific cookie - a genuine requirement for most consent or preference
cookies, but not for anything used to authenticate a request.

## 3. Is the cookie sent on cross-site requests: `cookieSameSite`

Without a `SameSite` attribute, a cookie is attached to requests that
originate from another site - the mechanism behind cross-site request
forgery (CSRF), where a page the victim never intended to trust triggers a
request that carries their OpenCloud session along with it.

**Fix:** set `SameSite=Lax` or `SameSite=Strict` unless a documented
cross-site flow genuinely needs `SameSite=None` (which additionally requires
`Secure`). `Lax` is right for most session cookies: it still allows a
top-level navigation such as clicking a shared link to arrive signed in.

## 4. Does the cookie name carry a prefix: `cookiePrefix`

The three attributes above all govern how a cookie is *read*. None of them
governs how one is *written*, and that is the gap the `__Host-` and
`__Secure-` name prefixes close. A cookie called `session` can be overwritten
by any sibling subdomain, or over plain HTTP on the same host, however
carefully its `Secure` and `HttpOnly` flags were set - the browser has no way
to know which of the two writers is the real application. A cookie called
`__Host-session` can only be set over HTTPS, with `Path=/` and no `Domain`,
so nothing but the exact origin can touch it. The prefix is enforced on the
name itself, before any attribute is consulted, which is what makes it the
one cookie protection an attacker on a neighbouring subdomain cannot work
around.

The check reports two different failures, because they have one fix:

- **A cookie that claims a prefix it does not honour** - `__Host-` with a
  `Domain` attribute, with a `Path` other than `/`, or without `Secure`. Every
  browser rejects such a cookie outright, so this is not a theoretical
  weakness: the session it carries silently does not work. The detail names
  which rule was broken.
- **No observed cookie carrying a prefix at all**, which is the ordinary
  state of an instance nobody has changed.

**Fix:** rename the session cookie to `__Host-<name>` and set it with
`Secure`, `Path=/` and no `Domain` attribute - or `__Secure-<name>` when it
genuinely has to be shared across subdomains. Where the cookie comes from a
reverse proxy or an identity provider rather than from OpenCloud, rename it
there.

## Severity and rating impact

All four are `extraChecks`, reported whenever a cookie is observed -
`cookieSecure` at `high`, `cookieHttpOnly` at `medium`, `cookieSameSite` and
`cookiePrefix` at `low` - and each caps the rating on its own the same way any
other failed extra check does (`high` -> `C`, `medium` -> `A`, `low` -> `A+`; see the
extra-checks table in [the main README](../README.md#what-the-scanner-checks)).
Set `scanner.extra_checks_rating: false` to report them without touching the
rating, or `--no-extra-checks` to skip them outright.
