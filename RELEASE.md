## check-opencloud-security 1.5.0

### Added

- **A hosted instance to try, at <https://scan.okxo.de>.** The web application
  from this repository, running: paste an address, read the grade, install
  nothing. It is now the first thing the README offers, linked from
  `docs/README.md`, `docs/webapp.md` and `webapp/README.md`, and listed on PyPI
  as the project's "Live demo". The README says plainly what using it means -
  the scan runs from that server, so it sees only what the public internet
  sees, and anything private still wants the plugin or your own deployment.
- **`--release-track auto`**, and `auto` as a value of
  `scanner.release_track`, `COS_SCANNER_RELEASE_TRACK` and the web form. It
  asks the release schedule which track the installed release belongs to,
  which is the same answer as leaving the track unset - said out loud, so one
  configuration can cover instances on different tracks without declaring a
  track that is wrong for half of them.
- A workflow that re-checks the OpenCloud links this project documents after
  every merge into `main`, and once a week.
  `scripts/check_documentation_links.py` collects every link to
  `opencloud.eu`, `docs.opencloud.eu` and the OpenCloud repositories from the
  documentation, the code and the configuration and requests it. A dead link
  fails the run; a redirect is reported but does not, because `opencloud.eu`
  redirects to a language version and a job that always fails is a job nobody
  reads. A finding that explains itself with a link nobody can follow is a
  finding nobody can act on.
- The web application is published to Docker Hub as **`opencloud-scanner`**,
  built for `linux/amd64` and `linux/arm64` from `docker/Dockerfile.web` with
  provenance and an SBOM attached. `edge` follows `main`; `latest` and the
  version tags only move when the version in `pyproject.toml` names an image
  that does not exist yet, so a documentation commit cannot republish
  `latest` from a tree that is not the released one. The account, the token
  and the optional namespace come from repository secrets - nothing in the
  repository names an account, and the job skips itself rather than failing
  when they are absent, so a fork does not go red over a credential it was
  never given.

### Changed

- **`auto` is now the default release track**, on the command line, in the
  configuration file and on the web form. It is the verdict an undeclared
  track always received, so nothing is rated differently - it is now recorded
  as `auto` rather than left blank, which is the difference between a result
  that says "the schedule worked this out" and one that says nothing. The web
  form previously defaulted to `production`, where any fixed guess is wrong
  for somebody: `production` calls a current rolling instance out of date and
  `rolling` reports an end of life a production instance has not reached.
  Naming a track still overrides it everywhere.
- **The setup wizard asks for the release track on its own**, with a note on
  what auto-detection does. It used to sit inside the update check group, so
  an operator who declined that group - reasonably, having no interest in
  where the newest release is looked up - was never asked about the setting
  that decides every lifecycle verdict.
- **The palette is brighter, and now readable where it was not.** Each status
  colour became three tokens instead of one: `--x` paints the dial, the rules
  and the borders, `--x-soft` is the tint behind them, and the new `--x-ink`
  is the tone that carries text on that tint. The single tone had to be both
  at once, which is why the amber and green tags sat at 2.9:1 - below WCAG AA,
  on the two labels that say a check passed or nearly did. Every text pair in
  both light and dark mode now clears 4.5:1 and every graphic tone 3:1, while
  the surfaces, the brand blue and the teal accent all moved lighter. The
  hard-coded glows and the white button label became tokens as well
  (`--brand-glow`, `--accent-wash`, `--on-brand`), so the palette has one
  source again - the button label is dark in dark mode, where its gradient is
  the light brand tone.
- The header says what the page is rather than what the package is called:
  the brand line is now just *Security scan for OpenCloud instances*. The
  package name sat above that same sentence in smaller type, so a first-time
  visitor read a repository name before they read what the site does. It is
  still named in the footer and linked from the source line.
- **A release ahead of its declared track is no longer end of life.** Running
  the current rolling release while declaring the production track rated the
  instance `F` and alerted `CRITICAL` - about a machine running the newest
  OpenCloud there is, with everything the production track ships and more. Such
  an instance is now reported as *ahead of* its track, with the current release
  of that track named. The `F` is kept for what it was meant for: a release
  *behind* the current one of the declared track, which really is missing
  fixes. The upgrade recommendation still never points backwards.

### Fixed

- The test suite no longer reads the configuration of the machine it runs on.
  A developer who had run `--configure` for a real instance had
  `~/.config/check-opencloud-security/.env.json`, and the tests that ask "what
  does the plugin see when nothing is configured?" saw their host, their track
  and their waivers instead of nothing - four failures locally, none in CI, and
  a real hostname printed into the failure output. Discovery is now pointed at
  an empty home and an empty working directory, created per test.
- The web application tests no longer warn on every run. Starlette 1.6
  deprecated driving `TestClient` with `httpx`, so the test group asks for
  `httpx2` instead. A warning that is printed on every green run is a warning
  nobody reads when it finally matters.

### Security

- **A server that reports ownCloud or Nextcloud in `status.php` is no longer
  scanned as OpenCloud.** All three serve the same endpoint - OpenCloud
  inherited it from them - so the document alone never said what was running,
  and the scan happily rated an ownCloud instance against OpenCloud's release
  schedule, advisories and hardening defaults. That is a confident answer about
  the wrong software, which is worse than no answer: the scan now stops with an
  error naming the product it found.
