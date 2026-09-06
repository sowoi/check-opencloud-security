## check-opencloud-security 1.21.0

### Added

- **Three step-by-step identity-provider tutorials, in
  [`docs/identity-providers.md`](docs/identity-providers.md).** Putting
  Keycloak, Authentik or Authelia in front of an instance was one section of
  [Running OpenCloud in a secure
  infrastructure](docs/secure-deployment.md#1-put-a-real-identity-provider-in-front),
  which argued the case and then summarised each provider in a screenful.
  This is the other half: installing each one, the provider configuration in
  full, verifying it worked, and moving an instance that already has accounts
  without stranding anybody's files in an account they can no longer reach.

  The part worth having is the section none of the three vendors can write,
  because it is not about them: **the four clients, their redirect URIs and
  their scopes are properties of OpenCloud's own applications** and are
  identical whichever provider you pick. The web client needs
  `oidc-silent-redirect.html` registered or sessions start dying at an
  interval nobody can reproduce; only the non-browser clients get
  `offline_access`, because a refresh token in a browser tab is a credential
  in a place that cannot protect it; and all four are public clients with
  PKCE, because everything OpenCloud ships runs on somebody else's machine
  and cannot keep a secret. Each provider tutorial is then only what that
  provider calls those things.

  The troubleshooting table is the failures in order of how often they are
  the answer, and the verification section ends where this repository begins:
  a scan, and the four OpenID Connect properties it reads from the discovery
  document - plus a note on the two things it deliberately cannot tell you,
  which are your group mapping and whether your second factor is enforced.

- **The operator's area has a Documentation tab.** `/admin` gained a tab
  strip, and beside the overview it now renders the two repository documents
  somebody running this service actually needs while running it:
  `ARCHITECTURE.md` at `/admin/docs/architecture`, and the operations notes in
  `ADMIN.md` at `/admin/docs/operations`. Reaching for either used to mean
  leaving the service and finding the repository.

  They are generated at build time into `frontend/templates/admin-docs/` by
  the same pipeline the public guides use ([ADR
  0018](adr/0018-cli-documentation-is-generated-at-build-time.md)), so nothing
  parses Markdown at runtime and the web application still has no Markdown
  dependency. English only, with a line above each saying which repository
  file it came from - a half-translated operations note is worse than an
  English one that says so.

  **They come from a manifest of their own**, `OPERATOR_DOCUMENTATION_PAGES`,
  deliberately separate from the one that feeds `/documentation`. That is what
  keeps `ADMIN.md`'s own promise about itself intact: the pages are absent
  from the public documentation index, the sitemap, `robots.txt` and the
  search index, they answer **404** to anybody the outpost did not authorise,
  and `tests/test_webapp_admin.py` holds them to every one of those. The one
  thing that did change is recorded in `ADMIN.md` itself: the rendered page
  travels inside the web bundle and the container image, which is acceptable
  only because that file is already world-readable in the public repository
  and contains operations notes rather than credentials.

### Fixed

- **The hero instrument follows the scheme a visitor chose, not only the one
  their operating system reports.** It was `<img src="hero.svg">`, and an
  `<img>` is a separate document: it can read `prefers-color-scheme` but never
  the `data-theme` this page writes on the root element when somebody presses
  the header switch. So the drawing answered the system while everything
  around it answered the toggle, and pressing the switch left a daylight
  instrument on a midnight page - or a midnight one on a daylight page, which
  is the same bug from the other side.

  It is now inline in `index.html`, with its styles in `app.css` under all
  three of the states the rest of the page already handles. That ends the
  second palette it was carrying: the markers are the page's own `--good`,
  `--fair`, `--info` and `--bad` rather than a hand-copy that had already
  drifted in the light scheme, and only the three colours genuinely its own -
  the sweep's magenta, the lit top of the shield, the static - are still
  written down. `hero.svg` is gone rather than left unreferenced beside it.

  The `<style>` block could not come along: `style-src 'self'` carries no
  `unsafe-inline`, so a `<style>` element in the markup is dropped by the
  browser and caught by `tests/test_webapp_api.py`. The drawing is also
  explicitly decorative now - inline, its `<title>` *would* be announced, and
  what it would announce is the headline directly above it, a second time.

- **On a phone the hero puts the field before the picture.** Stacked into one
  column, a full-width 480×300 illustration sat between the headline and the
  one field this service exists for, so the first gesture on a small screen
  was a scroll looking for something the page had just promised. The column is
  reordered rather than the artwork dropped: the wrapper dissolves with
  `display: contents` so copy, form and instrument become siblings in one
  flex column, and the drawing keeps its place underneath at a size that looks
  deliberate. The markup is untouched, so a reader without CSS still meets
  them in the order it states.

- **The lock file no longer pins a package its own maintainers withdrew.**
  `securesystemslib` 1.5.0 was yanked from PyPI as incompatible with sigstore,
  which is the only reason it is here at all: the `signing` extra pulls
  sigstore, sigstore pulls tuf, and tuf pulls securesystemslib. A resolve from
  scratch would have skipped a yanked release, but the version was already
  written down, so every `uv lock` re-pinned it and said so in a warning. The
  pin moves to 1.5.1, the release that restores the compatibility, and no
  constraint is left behind to remove later.

### Security

- **`--configure` no longer writes the configuration world-readable before
  narrowing it.** The file it saves may hold a release token, a service token
  or a webhook URL with a credential in it - the wizard says so - and it was
  written with `write_text` and only then `chmod`ed to `0600`. On a monitoring
  host with more than one account, any local user could read the token in the
  window between the two, and a descriptor opened in that window stays
  readable after the `chmod`.

  The window was not the whole of it. Where the destination **already existed**
  at `0644` - an earlier run, an editor, `touch` - the write went through that
  same inode, so the token sat world-readable for the entire write rather than
  for an instant. Re-running `--configure` to *rotate* a token is exactly that
  path.

  The configuration is now written to a `mkstemp` file, which is owner-only
  from the moment it exists, and moved into place. The secret is therefore
  never on disk under a wider mode, and the move being atomic means a save
  that fails leaves the previous configuration intact instead of a truncated
  one. This is the rule `docker/setup-wizard.py` already held its `.env` to and
  `baseline.py` already held its state file to; the plugin's own wizard was the
  one place that did not.
