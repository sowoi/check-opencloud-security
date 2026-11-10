## check-opencloud-security 1.33.0

### Changed

- **The bundled stacks run Valkey instead of Redis.** Every compose file, the
  stack `docker/setup-wizard.py` generates and the CI test service now use
  `valkey/valkey:9.1-alpine` in place of `redis:8.10-alpine`, start
  `valkey-server` and check their health with `valkey-cli` through
  `VALKEYCLI_AUTH`. Valkey is the BSD-licensed continuation of Redis and
  speaks the same protocol, so the service name `redis`, `COS_WEB_REDIS_URL`,
  `COS_REDIS_PASSWORD` and the Python client are unchanged and an existing
  `.env` keeps working. **Upgrade note:** a stack generated with persistence
  (`volume` or `filesystem`) must empty its data directory or volume once
  before the first start, because Valkey refuses a data file written by
  Redis 8. The default stacks persist nothing. See
  [ADR 0081](adr/0081-the-bundled-key-value-store-is-valkey.md) and
  [`docs/redis.md`](docs/redis.md).
- **The CI tools are current again.** On its first run,
  `scripts/check_tool_pins.py` found six pins behind their latest release.
  All six are raised wherever they are written (workflows, `CLAUDE.md`,
  `AGENTS.md`, `CONTRIBUTING.md`, the preflight skill):
  - ruff 0.17.1 → 0.17.4
  - zizmor 1.30.1 → 1.32.0
  - Biome 2.5.13 → 2.6.6, including the schema in `biome.jsonc`
  - mermaid-cli 12.0.0 → 12.2.0
  - nfpm 2.47.0 → 2.48.0, with the SHA-256 of its Linux tarball from the
    release's `checksums.txt`, checked against the downloaded file
  - uv 0.13.1 → 0.13.7, as `required-version` and in the `docker/` images
    alike
  - its second weekly run (#174) found ruff and Biome a patch behind again,
    and both were raised once more

  The new ruff, zizmor and Biome find nothing in the repository. nfpm 2.48.0
  replaces its RPM writer, so the `.rpm` built on the pull request is
  installed on Fedora before a release relies on it. A local uv older than
  0.13.7 now refuses to run here.
- **The signed-in stack runs authentik 2026.8.5.** The setup wizard and
  `docker/docker-compose.authentik.yml` pinned 2026.8.4; `AUTHENTIK_TAG`
  still overrides it. A stack the wizard generated earlier keeps the tag it
  wrote until that is changed; authentik runs its own migrations on the next
  start, as a step from 2026.8.2 did without trouble. Redis 8.10 and
  Postgres 18.6 are still current.

### Fixed

- **The WebKit browser tests start again on Ubuntu 26.04.** The browser build
  cache in `browser-tests.yml` was keyed on the OS family, not the Ubuntu
  release, so after `ubuntu-latest` moved to 26.04 it restored the WebKit
  built for 24.04, which could not load `libicudata.so.74`. The key now
  carries the runner image, as the system package cache's already did.

### Documentation

- **`/preflight` runs zizmor online, as CI does.** Offline, zizmor skips the
  audit that compares a pin comment with where its tag points now. A
  `# v4` that upstream had moved therefore passed locally and failed only in
  CI. The preflight skill, `CLAUDE.md` and `AGENTS.md` now pass
  `GH_TOKEN="$(gh auth token)"`. Without a signed-in `gh`, preflight reports
  a warning that the online audits did not run.
- **`CLAUDE.md` says Firefox does not start inside Claude Code's sandbox.**
  It fails with `Could not find profile folder`, which looked like a broken
  browser build. Outside the sandbox the Firefox browser tests pass.
