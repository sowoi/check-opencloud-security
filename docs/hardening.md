# Hardening measures, one by one

The hardening identifiers are terse because they end up in alert text. This
page says what each one means, what a failure actually indicates and which
OpenCloud setting changes it - then covers the two measures nobody can
influence, and how to accept a finding you are not going to fix.

`--debug` prints the same explanation next to each finding. The
[main README](../README.md#hardening-checks) covers how the measures reach
the output and the metrics.

<!-- TOC -->
* [Hardening measures, one by one](#hardening-measures-one-by-one)
  * [What each measure means](#what-each-measure-means)
  * [Measures that are not settings](#measures-that-are-not-settings)
  * [Accepting a finding you are not going to fix](#accepting-a-finding-you-are-not-going-to-fix)
<!-- TOC -->


## What each measure means

| Hardening                      | What a failure means                                                                                                                                                                                                                                                                                                                             | Setting to change                                                                                                                                              |
|:-------------------------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `basicAuthDisabled`            | The instance offers HTTP Basic auth, so credentials can be replayed on every request and single sign-on (with any second factor) is bypassed. Often deliberate: CalDAV, CardDAV and WebDAV clients cannot speak OpenID Connect, which is why this is rated `medium`, and `low` when an external identity provider handles the interactive login. | [`PROXY_ENABLE_BASIC_AUTH=false`][proxy-env] if nothing needs it; otherwise keep it and hand those clients app tokens rather than account passwords.           |
| `cspWithoutUnsafeInline`       | The `Content-Security-Policy` contains `'unsafe-inline'`, so injected markup may execute. **This is OpenCloud's shipped default** - see the note below.                                                                                                                                                                                          | [`PROXY_CSP_CONFIG_FILE_LOCATION`][proxy-env] pointing at your own `csp.yaml` (or `PROXY_CSP_CONFIG_FILE_OVERRIDE_LOCATION` to replace the default outright).  |
| `publicLinkPasswordEnforced`   | Public links may be created without a password, so the URL alone grants access. OpenCloud enforces a password on read-only links but not on writable ones.                                                                                                                                                                                       | [`OC_SHARING_PUBLIC_SHARE_MUST_HAVE_PASSWORD=true`][sharing-env] and `OC_SHARING_PUBLIC_WRITEABLE_SHARE_MUST_HAVE_PASSWORD=true`.                              |
| `passwordPolicyEnforced`       | Public link passwords may be shorter than 8 characters. (This policy covers link passwords, not account passwords - those belong to your identity provider.)                                                                                                                                                                                     | [`OC_PASSWORD_POLICY_MIN_CHARACTERS`][link-password] (default `8`), plus the `MIN_LOWERCASE`/`MIN_UPPERCASE`/`MIN_DIGITS`/`MIN_SPECIAL_CHARACTERS` companions. |
| `passwordPolicyComplexity`     | The link password policy no longer requires a lowercase letter, an uppercase letter, a digit and a special character. Each defaults to `1`, so a failure means somebody lowered one; a policy that is switched off reports this as unknown rather than failed.                                                                                     | [`OC_PASSWORD_POLICY_MIN_LOWERCASE_CHARACTERS`][link-password] and its `MIN_UPPERCASE`/`MIN_DIGITS`/`MIN_SPECIAL_CHARACTERS` companions, back to `1` or more.                |
| `hstsLongMaxAge`               | `Strict-Transport-Security` carries a `max-age` below a year.                                                                                                                                                                                                                                                                                    | None in OpenCloud - its proxy sends ten years, so a short value comes from a reverse proxy in front of it.                                                     |
| `hstsPreload`                  | The same header has no `preload` directive, so the very first request to the host is unprotected.                                                                                                                                                                                                                                                | None in OpenCloud - again a reverse proxy rewriting the header. Only add `preload` once every subdomain is HTTPS-only.                                         |
| `publicLinkExpirationEnforced` | Nothing about your instance: OpenCloud hardcodes this capability to `false`. **Never alerted on** - see below.                                                                                                                                                                                                                                   | None exists.                                                                                                                                                   |
| `userEnumerationRestricted`    | Account search is not limited to shared groups. OpenCloud hardcodes the restricted state, so this passes everywhere.                                                                                                                                                                                                                             | None exists.                                                                                                                                                   |
| `oidcPkceSupported`            | The identity provider's discovery document publishes `code_challenge_methods_supported` without `S256`, so the authorization code flow runs without PKCE. Only reported when the provider publishes the field - OpenCloud's built-in provider omits it, and an absent answer is not a failing one.                                                | Require PKCE with `S256` on the provider: Keycloak's *Proof Key for Code Exchange*, Authentik's public client with PKCE required, Authelia's `require_pkce`.   |
| `oidcImplicitFlowDisabled`     | `response_types_supported` still offers a type that returns a token from the authorization endpoint (`token` or `id_token`), i.e. the implicit flow. **External providers only** - OpenCloud's built-in provider offers these and cannot be reconfigured.                                                                                         | Restrict the client to the authorization code flow; in Keycloak, Standard flow on and Implicit flow off.                                                       |
| `oidcSigningAlgorithmStrong`   | `id_token_signing_alg_values_supported` offers `none` (an unsigned ID token anybody can write) or an `HS` algorithm (signed with the client secret, which a public client cannot keep). OpenCloud's built-in provider signs with `PS256` and passes.                                                                                              | Offer only asymmetric algorithms - `RS256`, `PS256`, `ES256` or `EdDSA` - and remove `none` and the `HS` family.                                               |
| `oidcEndpointsUseHttps`        | An endpoint in the discovery document is an `http://` address. Only checked when the instance itself answered over HTTPS: an instance scanned over plain HTTP publishes `http://` because that is how it was asked, which `httpsEnforced` already reports.                                                                                        | Publish the provider over HTTPS and set its issuer to the `https://` address; an `http://` issuer is usually a provider behind a terminating proxy that was never told its public URL. |

[proxy-env]: https://docs.opencloud.eu/docs/dev/server/services/proxy/environment-variables
[sharing-env]: https://docs.opencloud.eu/docs/dev/server/services/sharing/environment-variables
[frontend-env]: https://docs.opencloud.eu/docs/dev/server/services/frontend/environment-variables
[link-password]: https://docs.opencloud.eu/docs/admin/configuration/link-password-policy

## Measures that are not settings

Two of the rows above cannot be influenced by anyone:

- **`publicLinkExpirationEnforced`** is reported as `false` by *every*
  OpenCloud instance. The capability is a hardcoded constant in the frontend
  service, not a configuration value, so there is no variable to set and no
  version that passes.
- **`userEnumerationRestricted`** is the same story with the opposite sign:
  hardcoded to the restricted state, so it always passes.

They are still recorded in the result document, because the observation is
real, but they are **left out of the "Missing hardening" line, out of the
`hardenings_missing` metric and out of the webhook**. A warning nobody can
ever clear is noise, and noise is how genuine findings get ignored. `--debug`
still lists them, with the explanation.

`cspWithoutUnsafeInline` is a milder version of the same problem: OpenCloud's
**default CSP contains `'unsafe-inline'`**, so it fails on a stock instance.
That one *is* changeable, so it is reported rather than excused - but be aware
that the web interface currently relies on inline scripts and styles, so a
strict policy is likely to break the UI and any connected office or IDP
service. Test before rolling it out. See [`docs/csp.md`](csp.md) for the
full explanation of both CSP checks.

The capability-derived rows only appear when the instance actually reports the
corresponding capability, so an older release does not accumulate phantom
findings.

## Accepting a finding you are not going to fix

Some findings are real but not actionable in your environment: a CSP you
cannot tighten without breaking the web UI, an HSTS header your reverse proxy
owns, or basic auth you genuinely need for a migration tool. Left alone they
keep the rating down and the check yellow, and a check that is permanently
yellow is a check nobody reads.

`--ignore-hardening` accepts a finding by name. The rating is recalculated
without it, so accepting a finding really does change the grade:

```bash
check-opencloud-security --host opencloud.example.com --check-hardening \
    --ignore-hardening cspWithoutUnsafeInline \
    --ignore-hardening basicAuthDisabled
```

The option is repeatable, also takes a comma-separated list, and understands
shell-style wildcards for the identifiers that carry a path or a port:

```bash
--ignore-hardening 'debugPort:*,exposed:/status.php'
```

It matches hardening measures, security header names, `httpsEnforced` and the
ids of the additional checks - one option for all of them, because
`basicAuthDisabled` is both a hardening measure and an additional check, and
accepting it in one place but not the other would be surprising.

A waived finding:

- no longer lowers the rating,
- no longer appears in `Missing hardening:` or `Additional checks failed`,
- no longer counts towards the `hardenings_missing` and `extra_checks_failed`
  metrics,
- is left out of the webhook payload,
- but **stays in the JSON result document**, flagged with `"ignored": true`,
  and is listed in the plugin output as `Ignored by configuration (n): ...`.

That last point is deliberate. A waiver suppresses an alert, not the evidence:
the scan still records what it saw, `--debug` still explains it, and anyone
reading the output can see exactly what is being skipped.

Two things a waiver will not do:

- **It cannot waive something that passes.** A waiver is only applied to a
  finding that actually failed, so it cannot quietly turn into a blind spot the
  day the measure regresses.
- **It cannot waive an end-of-life release.** Running a version that receives
  no security fixes overrides every other signal, including
  `--ignore-hardening '*'`.

Waivers are a good fit for a config file, where they can carry a comment
explaining why each one is there:

```yaml
scanner:
  release_track: production
  ignore_hardenings:
    - cspWithoutUnsafeInline   # default csp.yaml, tightening it breaks the web UI
    - hstsPreload              # the reverse proxy sets its own HSTS header
```
