## check-opencloud-security 1.32.0

### Added

- **Python 3.15 is supported and tested.** nox and the version matrix in CI
  run the suite on 3.11 to 3.15, and the packaged launchers try
  `python3.15` first after `python3`.

### Changed

- **The container images run Python 3.15.** Both images are built from
  `python:3.15-slim` and install with uv 0.13.1 instead of 0.11.31.

### Removed

- **Python 3.10 is no longer supported.** It reached end of life on
  1 October 2026 and receives no security fixes, so `requires-python` is now
  `>=3.11`; a `pip install` on 3.10 keeps the last release that supported it,
  1.31.3. The `.deb` depends on `python3 (>= 3.11)`, which Debian 12 and
  Ubuntu 24.04 meet; on Ubuntu 22.04, whose `python3` is 3.10, apt refuses it
  and the plugin installs with pipx on a newer Python instead. The RPM stays
  unversioned, and its launchers find RHEL 9's `python3.11` or `python3.12`.
  See [The interpreter it uses](docs/installation.md#the-interpreter-it-uses).
