# Authentication: what this scanner checks, and why

Five checks look at how an instance authenticates requests: whether protected
endpoints actually demand a session, whether HTTP Basic auth is still
offered as a bypass around the identity provider, whether the documented demo
accounts still work, and two properties OpenCloud's own capabilities document
publishes about account search and password strength. None of them submit a
guessed credential anywhere - see [What the scan deliberately does not
answer](../README.md#what-the-scan-deliberately-does-not-answer) for what is
out of scope on principle, and the demo-account section below for the one
documented exception.

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
signs users in](../README.md#who-signs-users-in)), since the account
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

## Severity and rating impact

`authentication:<path>` and `demoUsersDisabled` are `extraChecks`, reported
and rating-capped whenever they run at all, at their own severities above -
see the extra-checks table in [the main
README](../README.md#what-the-scanner-checks). `basicAuthDisabled`,
`userEnumerationRestricted` and `passwordPolicyEnforced` are hardening flags,
reported only with `--check-hardening` (or always on the web result); a
failed hardening flag does not cap the rating by itself, it raises an
otherwise-`OK` Icinga result to `WARNING` and is listed in the
`hardenings_missing` line - see [Hardening
checks](../README.md#hardening-checks).

[opencloud-demo-users]: https://docs.opencloud.eu/docs/admin/resources/demo-user/
[link-password]: https://docs.opencloud.eu/docs/admin/configuration/link-password-policy
