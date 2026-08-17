## check-opencloud-security 1.5.2

### Added

- `docker/dockerhub-readme.md`, the Docker Hub description for the web image.
  The publish workflow submits it after every image push, so release
  instructions for GitHub, Docker Compose and `docker pull` stay with the
  image.

### Changed

- The Docker Hub publishing workflow now uses the Node 24 Docker actions.
  Buildx publishes the existing max-level provenance and SBOM directly to
  Docker Hub, avoiding a second GitHub attestation request that could fail
  after the image was already published during a GitHub service outage.
