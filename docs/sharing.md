# Public link sharing: what this scanner checks, and why

A public link turns "who has the URL" into the entire access control model
for whatever it points at. Two checks read OpenCloud's public capabilities
document to see what a link is allowed to do without a password, and whether
it can be made to expire.

<!-- TOC -->
* [Public link sharing: what this scanner checks, and why](#public-link-sharing-what-this-scanner-checks-and-why)
  * [1. Can a public link be created without a password: `publicLinkPasswordEnforced`](#1-can-a-public-link-be-created-without-a-password-publiclinkpasswordenforced)
  * [2. Do public links expire automatically: `publicLinkExpirationEnforced`](#2-do-public-links-expire-automatically-publiclinkexpirationenforced)
  * [Severity and rating impact](#severity-and-rating-impact)
<!-- TOC -->


## 1. Can a public link be created without a password: `publicLinkPasswordEnforced`

The capabilities document reports, per share type, whether a password is
required: read-only, upload-only and editable links are each covered by
their own `enforced_for` flag. This check passes only when **all** of them
require a password - if even one share type can be created without one,
anybody holding that URL has the data behind it, indefinitely, with no
credential involved at all.

**This is a common near-miss rather than an all-or-nothing failure.**
OpenCloud enforces a password on read-only links by default but not on
writable ones, so the usual reason this fails is that upload-only or
editable links were left at their default. A writable link without a
password is the more serious gap of the two: it lets an anonymous visitor
add or overwrite files, not merely read them.

**Fix:** set `OC_SHARING_PUBLIC_SHARE_MUST_HAVE_PASSWORD=true` and
`OC_SHARING_PUBLIC_WRITEABLE_SHARE_MUST_HAVE_PASSWORD=true`. Prefer these
global `OC_SHARING_*` names over the deprecated `FRONTEND_OCS_*` forms still
referenced in some older guides. Whatever password ends up being set on a
link is itself governed by `passwordPolicyEnforced` - see [Authentication:
is the link password policy strong
enough](authentication.md#5-is-the-link-password-policy-strong-enough-passwordpolicyenforced).

## 2. Do public links expire automatically: `publicLinkExpirationEnforced`

The capabilities document's `files_sharing.public.expire_date.enabled` field
is read directly. In current OpenCloud releases this is a hardcoded `false`
in the frontend service - a constant, not a setting - so every instance
reports the same value regardless of how it is configured. **This check is
never alerted on** for exactly that reason: it is left out of the "Missing
hardening" line, the `hardenings_missing` metric and the webhook payload,
because a warning nobody can ever clear is noise, and noise is how genuine
findings get ignored - see [Measures that are not
settings](../README.md#measures-that-are-not-settings). `--debug` still
prints it, with the explanation.

It is kept in the catalogue rather than removed so that a future OpenCloud
release that makes automatic expiry configurable is caught the moment the
capabilities document starts reporting something other than `false` - the
same reasoning documented for `userEnumerationRestricted` in
[Authentication](authentication.md#4-is-account-search-restricted-to-shared-groups-userenumerationrestricted).

**If expiry genuinely matters for a deployment today:** there is no setting
to change. An expiry has to be set per share at creation time, or the link's
effective lifetime governed by something outside OpenCloud entirely - for
example a reverse-proxy rule or an external process that revokes shares on a
schedule.

## Severity and rating impact

Both are hardening flags, reported only with `--check-hardening` (or always
on the web result). `publicLinkPasswordEnforced` behaves like any other
hardening flag: a failure does not cap the rating on its own, but raises an
otherwise-`OK` Icinga result to `WARNING` and is listed in the "Missing
hardening" line. `publicLinkExpirationEnforced` is excluded from that line
entirely, for the reason above - see [Hardening
checks](../README.md#hardening-checks) for the full table and the general
rule.
