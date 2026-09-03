# Version and lifecycle disclosure: what this scanner checks, and why

Three checks are about the running version: whether one could be determined
at all, and whether it leaks somewhere it does not need to. They are
distinct from [end-of-life detection](../README.md#end-of-life-detection) and
the update check, which decide whether a *known* version is still supported -
these three exist upstream of that, because both depend on actually having a
real version to reason about.

<!-- TOC -->
* [Version and lifecycle disclosure: what this scanner checks, and why](#version-and-lifecycle-disclosure-what-this-scanner-checks-and-why)
  * [1. Could the running version be determined at all: `versionDetection`](#1-could-the-running-version-be-determined-at-all-versiondetection)
  * [2. Does a response header publish the version: `versionDisclosure:<header>`](#2-does-a-response-header-publish-the-version-versiondisclosureheader)
  * [3. Does the webfinger document publish the version: `webfingerVersionDisclosure`](#3-does-the-webfinger-document-publish-the-version-webfingerversiondisclosure)
  * [Severity and rating impact](#severity-and-rating-impact)
<!-- TOC -->


## 1. Could the running version be determined at all: `versionDetection`

`/status.php` reports up to three version-shaped fields, and only one of
them is the real release - see [Reading the version
correctly](scanner-checks.md#reading-the-version-correctly) for what the other
two are and why they exist, and [Why OpenCloud still answers
`/status.php`](status-php.md) for where the endpoint and its hardcoded
fields come from. This check fails when `productversion` is missing and
only the legacy compatibility `version`/`versionstring` fields came back.

This matters beyond the finding itself: without a real version, no advisory
can be matched and no end-of-life or update state can be worked out. A
result missing this field is not merely incomplete - the checks that depend
on the version did not run at all, and a report that read them as passing
would be claiming to have verified something it never saw.

**If this fails:** check whether something in front of the instance rewrites
or strips fields from the `/status.php` response, and whether the release is
old enough that it genuinely predates `productversion` being reported at
all. Until a real version comes back, treat every version-dependent part of
the result as unknown rather than as clean.

## 2. Does a response header publish the version: `versionDisclosure:<header>`

The `Server` and `X-Powered-By` response headers are each checked for
anything that looks like a version number (a digit, a dot, another digit).
Neither is a vulnerability by itself - it tells whoever is looking which
advisories to try first, nothing more - which is why both are rated `low`
rather than anything higher.

**Fix:** strip or flatten the header in the reverse proxy - `server_tokens
off` in Nginx, `ServerTokens Prod` in Apache - or unset it outright. See
[Reverse proxies](reverse-proxy.md) for the equivalent directive on Caddy,
Traefik and HAProxy.

## 3. Does the webfinger document publish the version: `webfingerVersionDisclosure`

`/.well-known/webfinger` is requested unauthenticated (as any federation
client would) and its response is checked for the running version, the same
way the two response headers above are. It is the same class of finding as
`versionDisclosure` - low-severity information disclosure, not a
vulnerability - just read from a JSON document instead of a header.

**Fix:** strip the version from the webfinger response in the reverse proxy,
or accept the disclosure and prioritise keeping the instance current
instead: the version only matters as intelligence while a known advisory
against that exact release is still unpatched.

## Severity and rating impact

All three are `extraChecks`, reported and rating-capped on every scan -
`versionDetection` at `medium` (caps the rating at `A`), the two disclosure
checks at `low` (caps it at `A+`) - see the extra-checks table in [the main
README](scanner-checks.md#what-the-scanner-checks). None require
`--check-hardening`, and none of them are the same thing as the [end-of-life
rating](../README.md#end-of-life-detection): a current, fully disclosed
version and an end-of-life, well-hidden one are graded on entirely different
axes.
