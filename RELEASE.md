## check-opencloud-security 1.5.4

### Added

- `adr/`, with a decision-record template and lifecycle guidance. Future
  durable architecture changes now require an ADR, and agent guidance directs
  contributors to read and maintain the relevant records.

### Changed

- The Docker Hub README now includes complete `docker run` and standalone
  Docker Compose examples, so the frontend scanner can run without cloning the
  repository.

## check-opencloud-security 1.5.3

### Changed

- Docker Hub publication now documents that `DOCKERHUB_TOKEN` needs read,
  write and delete scopes and that its account needs Admin repository access,
  so image descriptions remain a required part of a successful publish.
