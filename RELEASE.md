## check-opencloud-security 1.14.0

### Added

- **CAA record check (`tlsCaaRecord`)**: The built-in scanner now reports
  whether the scanned name has a DNS CAA record restricting which
  certificate authorities may issue for it. The lookup is dependency-free
  and only ever queries the system's own configured resolver - never a
  public one - so nothing new is sent to a third party.
- **Native Slack and Discord webhook formats**: `--webhook-format slack`
  (also accepted by Mattermost and the common Matrix webhook bridges) or
  `--webhook-format discord` posts the result already shaped for that
  receiver, so the adapter script in `docs/webhook-recipes.md` is no longer
  required for the common case. The default is unchanged.
- **`--format json`/`sarif`/`junit`**: one combined machine-readable document
  for every scanned host, for CI pipelines - a JSON array of the existing
  webhook payload shape, SARIF 2.1.0 for a code-scanning dashboard, or JUnit
  XML with one testsuite per host. The exit code keeps its Nagios meaning
  under every format.
- **IPv6 connectivity in the Docker setup wizard**: `docker/setup-wizard.py`
  now asks whether the deployment's containers have outbound IPv6
  connectivity (`COS_WEB_IPV6_ENABLED`, off by default, since Docker's
  default network has none). Left off, the built-in scanner still lists an
  instance's IPv6 addresses but skips dialling them for the IPv4/IPv6
  TLS-parity check, and the dashboard notes why instead of reporting the
  instance's IPv6 side as unreachable for a limitation of the deployment
  rather than of the instance.
- **The MCP endpoint is now a knowledge base as well as an execution layer**:
  two new resources, `catalogue` and `advisories`, publish the same
  hardening/check explanations and advisory database the `/catalogue` page
  renders - built from the same functions, so a resource can never disagree
  with the page about what a check id means. An agent can now explain a
  finding, or see what the scanner would catch, without submitting a scan.
- **`GET /agents.txt`**: a capability declaration in the
  [agents-txt.com](https://agents-txt.com) format, published under the
  filename some agent frameworks look for by convention. It names the MCP
  and WebMCP endpoints, declares `Authorization`/`Identity` only when the
  MCP endpoint itself requires a bearer token, and points at the discovery
  document and the OpenAPI/Arazzo contracts.
- **`GET /agents.json`**: the structured sibling the agents-txt.com
  convention recommends alongside `agents.txt` - the same document
  `/.well-known/ai.json` already serves, published again under the name the
  convention looks for.
- **`SearchAction` structured data on the homepage**: names the existing
  `/search` form so Google can offer a sitelinks search box, and
  **`BreadcrumbList` structured data on every `/documentation/{slug}` page**:
  draws the real home / documentation / guide trail those pages already sit
  in.
- **A short FAQ on `/how-it-works`**, in all four languages, with matching
  `FAQPage` structured data generated from the same catalogue keys the
  visible answers render from, so the two can never disagree.
- **`max-image-preview:large, max-snippet:-1`** added to the `robots` meta
  tag on every indexable page, opting back into the full-size thumbnail and
  snippet length Google has capped by default since 2019.

### Security

- **Stored XSS on the public `/catalogue` page via a feed-supplied advisory
  URL.** `catalogue.html` rendered `advisory.url` as an `href` with only a
  truthiness check, while the sibling `scan.html` template already guarded
  the same field with the `is safe_link` scheme check added when the daily
  OSV advisory refresh was wired in. A `javascript:` URL from a malicious or
  malformed upstream advisory entry could therefore execute in the page's
  own origin for any unauthenticated visitor who clicked the advisory link.
  `catalogue.html` now applies the same `is safe_link` guard.

### Fixed

- **`cspWithoutUnsafeInline` now also catches `unsafe-eval`**, and no longer
  mistakes a `style-src 'unsafe-inline'` for a script-execution weakness. The
  check used to fall back to a substring search over the *entire*
  `Content-Security-Policy` header when no `script-src` directive was
  present, so a policy with only `style-src 'unsafe-inline'` was wrongly
  flagged; it now reads `default-src` specifically, per CSP's own fallback
  rule, and also flags `'unsafe-eval'` in `script-src`/`default-src`, which
  undermines a CSP's XSS protection just as much as `'unsafe-inline'` does.
- **The `X-Frame-Options` check now accepts a CSP `frame-ancestors`
  directive as the alternative it already claimed to be**: the hardening
  catalogue's remediation text has always said "Send 'X-Frame-Options:
  SAMEORIGIN', or a CSP 'frame-ancestors' directive", but the scanner only
  ever checked the header, so an instance protected purely through
  `frame-ancestors` (the modern, browser-preferred mechanism) was reported
  as vulnerable to clickjacking. A wildcard `frame-ancestors *` still fails
  the check, since it does not restrict framing at all.
- **`cspWithoutUnsafeInline` no longer flags the standard `strict-dynamic`
  rollout pattern.** A `script-src` that pairs `'unsafe-inline'` with a nonce
  or a hash (e.g. `script-src 'nonce-xyz' 'strict-dynamic' 'unsafe-inline'
  https:;`) was reported as unsafe, but every browser that understands
  nonces ignores `'unsafe-inline'` in that case per the CSP spec - the
  keyword is only a fallback for browsers too old to understand the nonce.
  `'unsafe-eval'` gets no such exemption, since nothing about a nonce or hash
  makes `eval()` safe again.
