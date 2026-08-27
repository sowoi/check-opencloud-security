## check-opencloud-security 1.11.4

## Changed
- **Security and release-data safeguards**: Kept advisory ranges and release
  support facts monotonic during refreshes, and validate refresh pull requests
  against their relevant regression tests before review.
- **Search and agent discovery**: Kept query pages out of the sitemap and
  index, emitted valid localized JSON-LD only on public pages, and aligned the
  extended agent guide and discovery capabilities with the implemented API.
- **Documentation search intent**: Made generated OpenCloud Security Scanner
  guide titles and descriptions self-describing when reached directly.
- **Deployment and compatibility evidence**: Require an explicit public origin,
  pin the scheduled OpenCloud integration baseline by digest, and document
  candidate-image review rules.
- **Release operations and metadata**: Added the architecture runbook for
  rolling, production, and LTS releases; `COS_WEB_INDEX_META_TAG` now accepts
  a bounded, validated list of landing-page metadata pairs.
- **Configuration and Authentik guides**: Added directory references for the
  example scanner configuration and the MCP Authentik blueprint.
- **Docker setup documentation**: The setup wizard now leads the Docker Hub
  description, `docker/README.md`, `docs/webapp.md` and `webapp/README.md`, and
  every documented stack recipe carries the now-required
  `COS_WEB_PUBLIC_BASE_URL`, the Redis password and the internal network.
- **Redis hardening**: The Docker setup wizard and every shipped compose stack
  now support `COS_REDIS_PASSWORD` and keep Redis on an internal network with
  no published port, answering the "Redis does not require authentication and
  is not protected by network restriction" finding.

## Fixed
- **The Python version matrix actually tested one version**: `nox` installed
  no test dependencies and ran the outer environment's `pytest`, so every
  session reported the same interpreter. Each session now syncs into its own
  environment and asserts the interpreter before running the suite.
- **Python 3.10 compatibility**: `scripts/release_notes.py` and its test
  imported `tomllib`, which does not exist before 3.11. Both now read the
  project version without it.

## Added
- **Redis operator guide**: `docs/redis.md` and `/documentation/redis` cover
  what the scan service keeps in Redis and for how long, authentication,
  network isolation, memory and eviction, health signals and troubleshooting.
- **`/.well-known/security.txt`**: An RFC 9116 document with a computed
  `Expires`, naming the project's security policy everywhere and an operator
  address only on the deployment the legal notice belongs to.
- **Legal Notice Badge**: Added an explicit Legal Notice link to the footer, 
  displayed exclusively when accessing the site via scan.okxo.de.
