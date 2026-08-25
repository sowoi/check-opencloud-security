## check-opencloud-security 1.9.3

### Added

- **The resolved addresses are part of the result.** Every scan now records
  the IPv4 and IPv6 the instance's name pointed at while it ran, as
  `addresses` in the result document, and a web result page prints them under
  **Resolved to** in the overview. A name that does not resolve, or a scan of
  a bare address, reports empty lists rather than an error, and the block
  never moves the rating - it is there because "it answers on the address you
  retired last month" explains a surprising number of surprising results. The
  addresses the web application already validated are reported unchanged, so
  the document names what the scan actually dialled rather than a second
  lookup's answer.
- **A one-liner for whoever would rather not use the website.** The published
  image `okxo/opencloud-scanner` carries both entry points, so
  `docker run --rm --entrypoint check-opencloud-security
  okxo/opencloud-scanner:latest --host opencloud.example.com` runs the same
  check on your own machine, with no rate limit, no queue and nobody else
  learning which instance you look after.
  [`docs/docker-oneliner.md`](docs/docker-oneliner.md) collects the JSON
  variant, waivers, release tracks, private networks, a shell function and
  the container-free `uvx` form.
- **A "Docker" tab in the web interface.** The new page at `/cli` shows that
  one-liner where the hesitation actually happens - in the primary
  navigation, on the site being asked for an address - and links the full
  documentation. It is a public, indexable page like the other explanations.
- **A "Grades" tab explains the real rating scale.** The new `/grades` page
  takes its letters from the plugin's `RATE_MAP` and its finding ceilings
  from the scanner, explains why the 0-5 scale has no `B`, and shows what
  `A+`, `A`, `C`, `D`, `E` and `F` mean, what holds each one down and how the
  ordered remediation plan helps move an instance upward.
- **A local "Docs" tab for the CLI.** `/documentation` collects the quick
  start, the two entry points, everyday flags, configuration precedence and
  monitoring patterns in the web interface. Every full operator guide below
  it is a separate local HTML page generated from `README.md`,
  `opencloud_local_scan/README.md` or `docs/`; CI rejects stale generated
  pages, while production serves plain checked-in templates and carries no
  Markdown parser.
- **A small static search now reaches all public guidance.** The header field
  opens `/search`, where a same-origin release index is filtered in the
  browser. The manifest can read public templates only, and the release
  workflow is the sole automatic writer, so result pages, UUIDs, submitted
  addresses and exports have no path into the index.
- **The complete web interface now speaks four languages.** Stable string
  catalogues cover English, German, Spanish and French across navigation,
  forms, progress, results, grades, search and page metadata. The browser's
  weighted language preference is selected automatically, while an accessible
  switcher stores an explicit choice in an `HttpOnly`, `SameSite=Lax` cookie
  and works without JavaScript. Generated guide bodies remain English with a
  localized notice; their chrome and release-built search indexes follow the
  selected language. API, MCP and export contracts remain English, and remote
  scan evidence remains verbatim.

### Changed

- **The frontend header stays on one line.** Its brand is now the shorter
  *Security scan for OpenCloud*, controls and links do not wrap, and the
  compact menu takes over at tablet and narrower desktop widths before the
  translated navigation can split across lines. The landing-page and
  completed-result screenshots now show this header and the language switcher.
- **The web interface now uses the Halo design system.** Space Grotesk,
  Inter and JetBrains Mono are self-hosted with their licences; cold frosted
  panes float over an iris-and-magenta aurora, the target address is a
  full-width command bar, and every transition has a reduced-motion answer.
  Light and dark schemes use separate contrast-checked tokens, the artwork
  and OpenGraph image match them, and `DESIGN.md` explains how to extend the
  system without turning it into a collection of one-off styles.
- **Build contexts and source archives carry less development material.**
  Docker now excludes ADRs, guides, screenshots, deployment sources and
  maintainer-only files that neither image copies or runs; Git archives omit
  ADRs, screenshots and agent/design guidance as well. Both Dockerfiles still
  use explicit `COPY` lists, and the web release bundle remains an explicit
  allow-list, so runtime templates, generated Docs pages and licences stay in
  their intended artefacts.

### Security

- **A scan submission is now a constrained instance base address.** The
  browser gives immediate feedback and the server enforces the boundary: a
  target may have an `http` or `https` scheme, a hostname, an optional port
  and a plain subfolder path, but no query string, fragment, credentials,
  path parameters, escapes, traversal, whitespace or request-control
  characters. The scanner chooses every OpenCloud endpoint itself, so
  nothing appended by a visitor can become an
  outgoing payload or parameter. Redirects sent by the instance remain
  usable and are independently revalidated before they are followed.
- **The documented demo accounts are now a critical finding.**
  `IDM_CREATE_DEMO_USERS` fills OpenCloud's built-in identity management with
  five accounts - `dennis`, `margaret`, `alan`, `lynn`, `mary` - whose
  passwords are printed in OpenCloud's own documentation, and `dennis` is an
  administrator. When the instance signs users in with its *own* provider, the
  scan now asks `/ocs/v1.php/cloud/user` with each documented pair;
  `demoUsersDisabled` fails at severity `critical` when one is accepted, which
  caps the rating at `D` and puts the account names in the alert line.
  Nothing is guessed - only the published defaults are sent, and only to the
  instance's own provider, never to an external Keycloak or Authentik - and an
  endpoint answering unauthenticated requests reports nothing rather than
  inventing a demo user. `--debug` and `describe_hardening()` explain the
  finding and name `IDM_CREATE_DEMO_USERS=false`, along with the fact that
  turning it off does not delete accounts that already exist.
- **The admin documentation now drives three more remote checks and closes a
  password-policy blind spot.** Wildcard iframe message origins are `high`,
  delegated authentication without a trusted origin is `critical`, and a
  matching OpenCloud listener exposed directly on port 9200 is `high`.
  Capabilities that explicitly show a disabled password policy now fail
  `passwordPolicyEnforced` instead of silently omitting it. A Let's Encrypt
  staging issuer also names the exact production-certificate fix in the
  existing `tlsTrusted` finding. The audit deliberately does not guess admin
  passwords, probe sibling products or penalise OpenCloud endpoints that are
  public by design.

### Fixed

- **Signed reports are deployable from every supported setup path.** The
  Docker stacks and setup wizard now expose `COS_WEB_EXPORT_SIGNING_KEY`, the
  unattended wizard generates it, PDF/SARIF/JSON signatures are each tested
  against their exact downloaded bytes, MCP export results retain the
  signature header, and the release bundle now includes
  `scripts/verify_export.py`.

### Added

- **A real OpenGraph share image.** `og:image` now points at a hand-drawn
  1200x630 PNG (`frontend/static/img/og-image.png`, rendered from the
  `og-image.svg` beside it) with `og:image:type`, `og:image:width` and
  `og:image:height` metadata, because most crawlers and chat clients will not
  draw the SVG the pages previously shared.

### Changed

- **Body type is now Inter, self-hosted.** The web application serves the
  five weights it uses from `/static/fonts/` (SIL OFL 1.1, license beside the
  files) with the system sans as the fallback while the file arrives. The
  serif display face and the monospace dossier labels still come from the
  reader's own system stack, and nothing is fetched from a font service.
- **The accent colour is a warm ember in daylight.** The teal accent became a
  deep orange in the light scheme (`#c2410c`) and now carries the primary
  action button as well as the live marker and the assurance row, so the one
  thing a page wants done is the first thing the eye finds; the dark scheme
  keeps the clear teal (`#5eead4`) it always had. The logo, hero and expired
  artwork and the backdrop aurora were re-tinted to match.
