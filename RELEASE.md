## check-opencloud-security 1.5.5

### Added

- Live screenshots of the hosted scanner and a completed scan of the OpenCloud
  demonstration instance in `img/`, shown in the main and Docker Hub READMEs.

### Fixed

- `ProductName: Infinite Scale` now identifies ownCloud's renamed product and
  stops the scanner before it rates a non-OpenCloud instance against OpenCloud
  lifecycle data, advisories and hardening defaults.
- The Prometheus exporter now binds to `127.0.0.1` by default rather than all
  network interfaces. Remote scrapes require an explicit listen address.
