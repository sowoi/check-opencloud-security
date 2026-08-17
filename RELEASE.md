## check-opencloud-security 1.5.5

### Added

- Live screenshots of the hosted scanner and a completed scan of the OpenCloud
  demonstration instance in `img/`, shown in the main and Docker Hub READMEs.

### Fixed

- `ProductName: Infinite Scale` now identifies ownCloud's renamed product and
  stops the scanner before it rates a non-OpenCloud instance against OpenCloud
  lifecycle data, advisories and hardening defaults.

## check-opencloud-security 1.5.4

### Added

- `adr/`, with a decision-record template and lifecycle guidance. Future
  durable architecture changes now require an ADR, and agent guidance directs
  contributors to read and maintain the relevant records.

### Changed

- The Docker Hub README now includes complete `docker run` and standalone
  Docker Compose examples, so the frontend scanner can run without cloning the
  repository.
