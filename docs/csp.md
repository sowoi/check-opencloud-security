# Content-Security-Policy: what this scanner checks, and why

A `Content-Security-Policy` (CSP) header tells the browser which origins are
allowed to supply scripts, styles, frames and other active content for a
page. It is the browser-enforced backstop against cross-site scripting (XSS):
even if an attacker manages to inject markup into a page OpenCloud serves, a
correctly scoped CSP stops the browser from running it. This scanner checks
CSP in two independent places.

<!-- TOC -->
* [Content-Security-Policy: what this scanner checks, and why](#content-security-policy-what-this-scanner-checks-and-why)
  * [1. Is the header present at all](#1-is-the-header-present-at-all)
  * [2. Is the policy actually restrictive: `cspWithoutUnsafeInline`](#2-is-the-policy-actually-restrictive-cspwithoutunsafeinline)
  * [Fixing it](#fixing-it)
  * [Severity and rating impact](#severity-and-rating-impact)
<!-- TOC -->


## 1. Is the header present at all

`Content-Security-Policy` is one of the eight headers checked under
`setup.headers` (with `--check-hardening`, or always in the web result). Its
absence is a finding on its own:

> Nothing restricts where scripts, styles and frames may be loaded from.

OpenCloud ships a policy by default, so a missing header on a live instance
almost always means a reverse proxy in front of it stripped the header rather
than that OpenCloud failed to send it - see
[Reverse proxies](reverse-proxy.md) for the header set this check looks for,
written out for nginx, Apache, Caddy, Traefik and HAProxy.

## 2. Is the policy actually restrictive: `cspWithoutUnsafeInline`

Having *a* CSP header is not the same as having a useful one. The
`cspWithoutUnsafeInline` hardening check reads the `script-src` directive
(falling back to `default-src` when `script-src` is absent) and fails when it
contains `unsafe-inline` or `unsafe-eval`:

- **`unsafe-inline`** lets injected markup or an event handler execute
  outright - the exact thing a CSP exists to stop.
- **`unsafe-eval`** lets a gadget already present in loaded code turn
  attacker-controlled input into code via `eval()` or the `Function`
  constructor.

**This fails on a stock, unmodified OpenCloud instance.** The default
`csp.yaml` contains `unsafe-inline` in `script-src` and `style-src`, because
the web frontend currently depends on inline scripts and styles. The check
reports this rather than excusing it, but fixing it means shipping a custom
CSP and testing the UI against it - it is not evidence of misconfiguration by
itself, the way most other findings are.

One exception is built in: a policy that pairs `unsafe-inline` with a nonce or
a hash (the standard `strict-dynamic` rollout pattern) does **not** fail this
check. Every browser that understands nonces ignores `unsafe-inline` when one
is present, so the keyword is only a fallback for browsers too old to
understand the nonce either - keeping it in that shape is the standards-body
recommended way to support old and new browsers with the same header.

## Fixing it

Point `PROXY_CSP_CONFIG_FILE_LOCATION` at a `csp.yaml` without `unsafe-inline`
or `unsafe-eval`, or `PROXY_CSP_CONFIG_FILE_OVERRIDE_LOCATION` to replace the
default outright. To keep supporting older browsers, move to a nonce- or
hash-based policy with `strict-dynamic` instead of dropping `unsafe-inline`
outright. Test it first: the web interface currently relies on inline scripts
and styles, so a strict policy is likely to break the UI and any connected
office or IDP service before it is tuned.

Reference:
[OpenCloud proxy service environment variables](https://docs.opencloud.eu/docs/dev/server/services/proxy/environment-variables).

## Severity and rating impact

`cspWithoutUnsafeInline` is a hardening flag, reported only with
`--check-hardening` (or always on the web result), and does not on its own
cap the rating the way a failed `extraChecks` entry does - see
[Hardening checks](../README.md#hardening-checks) for how hardening flags and
capped findings differ. The missing-header finding is a `header:` extra check
and does cap the rating when `--check-hardening` is set - see the extra-checks
table in [the main README](scanner-checks.md#what-the-scanner-checks).
