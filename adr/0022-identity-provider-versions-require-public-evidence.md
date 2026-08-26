# ADR 0022: Identity provider versions require public evidence

- Status: Accepted
- Date: 2026-08-26

## Context

The scanner can identify some external identity providers from the issuer in
OpenCloud's public OpenID Connect discovery response. A result is more useful
when an operator can compare the provider's installed version with current
security advisories.

Keycloak, Authelia and Authentik do not expose their product version through
an unauthenticated, default-enabled endpoint. Their OpenID Connect discovery
documents contain no version. Keycloak's `/admin/serverinfo` endpoint requires
an administrator token, Authentik's `/api/v3/admin/version/` endpoint requires
an authenticated user, and Authelia has no public version endpoint. Their
public health, realm and configuration endpoints also omit the version.

Inferring a version from an issuer path, supported algorithms, static asset
names or a proxy header would turn weak deployment details into a precise
claim. Calling an administrative endpoint would also cross the scanner's
read-only, unauthenticated boundary.

## Decision

The scanner reports an identity provider version only when a recognized
provider supplies trustworthy product-version evidence through a public,
unauthenticated, read-only endpoint. No such evidence currently exists for
Keycloak, Authelia or Authentik, so `identityProvider.version` is an empty
string for those providers.

The result document includes the `version` key now so reliable evidence can be
added later without changing its shape. The web overview prints the version
when the field is non-empty. Otherwise it says that the version is not exposed
rather than guessing.

Recognized Keycloak, Authelia and Authentik results include
`identityProvider.advisoryUrl`. It points to the provider's official GitHub
Security Advisories page:

- `https://github.com/keycloak/keycloak/security/advisories`
- `https://github.com/authelia/authelia/security/advisories`
- `https://github.com/goauthentik/authentik/security/advisories`

These links let an operator consult a current upstream database without making
the scanner fetch third-party advisory data or claim that the installed
version is known.

Version evidence remains a measurement-layer concern in
`opencloud_local_scan`. The web application renders the scanner's observation
and does not probe the provider or infer a version itself.

## Consequences

The overview is honest about what an unauthenticated scan can establish. It
still gives operators a direct route to current provider advisories.

Adding version detection later requires evidence that the endpoint is public,
read-only, enabled by default, and returns the provider's own product version.
Tests must cover the positive evidence and prove that missing or ambiguous
evidence leaves the version empty.

The advisory URL is a reference, not a vulnerability verdict. The scanner does
not download or interpret those databases and does not rate the identity
provider.

## Alternatives considered

**Call authenticated administration endpoints.** The scanner has no operator
credentials and must neither request nor discover them. A version check does
not justify expanding that trust boundary.

**Infer versions from URLs, assets or headers.** These values can come from a
reverse proxy, local branding or deployment choices. They are not reliable
product-version evidence.

**Maintain a second identity-provider vulnerability database.** Without a
known installed version, matching advisories would be misleading. It would
also add another refresh lifecycle to a scanner that currently needs only an
upstream link.

**Hide identity-provider security information until versions are detectable.**
That withholds a useful official reference merely because the scanner cannot
perform the comparison itself.
