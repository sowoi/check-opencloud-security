## check-opencloud-security 1.1.0

### Added

- **`--configure`**. An interactive setup that asks for the settings the check
  needs, explains what each one is for and shows an example, then saves them as
  JSON with mode `0600`. Only the host is required; the optional settings are
  offered group by group and skipped unless you ask for them. The file is found
  automatically from then on, so the check runs with no arguments at all.
  `check-opencloud-scanner configure` does the same for the scanner.
- **JSON configuration files.** A configuration file whose name ends in
  `.json` is read as JSON; anything else is still YAML. `./.env.json` and
  `~/.config/check-opencloud-security/.env.json` were added to the paths
  searched automatically.
- **`--upgrade-self`**. Works out whether the plugin was installed with pipx,
  uv or pip and runs the matching upgrade command. `--dry-run` prints the
  command instead. A git checkout is refused, since installing over a working
  copy would leave you editing files that are no longer executed.
- **`SECURITY.md`**, describing what is in scope, how to report a
  vulnerability privately, and what the plugin does with your data.
- **`CODE_OF_CONDUCT.md`**, including the rule this project cares about most:
  no credentials and no production hostnames in a public thread.
- Issue forms for a bug, a wrong finding or rating, and a feature request,
  plus a pull request template. The finding form asks for the `--debug` output
  and for whether the setting is one an operator can actually change, which is
  what deciding a hardening report usually turns on.
- README: how to feed the webhook into an Uptime Kuma Push monitor.
- **`--concurrency` / `COS_SCANNER_CONCURRENCY`**. Runs the scanner's probes in
  parallel instead of one after the other, which shortens a scan considerably -
  most of all when debug-port probing runs into a firewall. Defaults to `1`,
  meaning no multithreading and exactly the previous sequential behaviour;
  values above `32` are clamped. The setting changes only the timing: findings
  and their order are identical whatever it is set to.

### Changed

- **The version is now declared once, in `pyproject.toml`.**
  `opencloud_local_scan.__version__` derives it from the installed package
  metadata, or from `pyproject.toml` itself when running out of a checkout, and
  `check_opencloud_security.py` imports that instead of carrying its own
  literal. A release is still cut by editing `pyproject.toml` by hand, but the
  three numbers can no longer drift apart.
- Documentation now describes the scan backend simply as the built-in scanner.
- **Release notes are collected under `## [Unreleased]`.** Changes are written
  down as they are made; `scripts/release_notes.py` renames that heading to the
  version from `pyproject.toml` when a release is cut, writes the same body to
  `RELEASE.md` and leaves a fresh empty `## [Unreleased]` behind. The version
  itself is bumped by hand and is still the only thing that triggers a release.
  `--require-unreleased` refuses to fall back to generated commit-subject notes.
