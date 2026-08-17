## check-opencloud-security 1.5.2

### Added

- `docker/dockerhub-readme.md`, the Docker Hub description for the web image.
  The publish workflow submits it after every image push, so release
  instructions for GitHub, Docker Compose and `docker pull` stay with the
  image.

## check-opencloud-security 1.5.1

### Added

- `docker/docker-compose.dockerhub.yml`, a self-contained frontend scanner
  deployment that pulls `okxo/opencloud-scanner:latest` for the web service and
  ARQ worker while retaining the queued worker, hardened runtime and ephemeral
  Redis configuration. The existing local-build Compose files remain unchanged.
