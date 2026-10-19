# syntax=docker/dockerfile:1
#
# Builds a self-contained image for check-opencloud-security.
# End users do not need Python, pip, or uv installed on the host -
# only Docker. See README.md for usage examples.
#
# The build context is the repository root, not this directory:
#
#   docker build -f docker/Dockerfile -t check-opencloud-security .

FROM python:3.15-slim AS builder

# uv is this project's dependency manager and build front end; the same
# command is used in CI (see .github/workflows/publish-pypi.yml).
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

WORKDIR /src

# Only copy what is needed to build the wheel, keeping the build cache-friendly.
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY check_opencloud_security.py ./
COPY opencloud_local_scan ./opencloud_local_scan

# The dependencies come from uv.lock, with their hashes: the set CI tested and
# pip-audit checked, not whatever PyPI serves on the day the image is built.
RUN uv build --wheel --out-dir /dist \
    && uv export --frozen --no-default-groups --no-emit-project \
        --format requirements-txt --output-file /dist/requirements.txt


FROM python:3.15-slim

LABEL org.opencontainers.image.title="check-opencloud-security" \
      org.opencontainers.image.description="Nagios/Icinga plugin and built-in scanner for OpenCloud instances" \
      org.opencontainers.image.source="https://github.com/sowoi/check-opencloud-security" \
      org.opencontainers.image.licenses="GPL-3.0-only"

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/
COPY --from=builder /dist/*.whl /dist/requirements.txt /tmp/

# The locked set first, every hash checked, then the wheel with --no-deps, so
# nothing this step installs was resolved here.
RUN uv pip install --system --no-cache --require-hashes -r /tmp/requirements.txt \
    && uv pip install --system --no-cache --no-deps /tmp/*.whl \
    && rm -rf /tmp/*.whl /tmp/requirements.txt /bin/uv \
    && useradd --no-create-home --shell /usr/sbin/nologin --uid 1000 nagios

# Numeric, so a runtime that checks runAsNonRoot can tell without reading
# /etc/passwd. 1000 is the uid useradd already assigned here, so files an
# existing deployment mounted in keep their owner.
USER 1000

# Port of the optional scan service (`check-opencloud-scanner serve`).
EXPOSE 8811

# The image is normally a one-shot check, so this verifies the image itself
# rather than any instance: the package imports, and the two data files it
# rates against - the release schedule and the bundled advisory database -
# parse. That is what a truncated layer or a botched build actually breaks.
# It touches no network, so it stays honest on an air-gapped host.
#
# Containers running `check-opencloud-scanner serve` want the HTTP liveness
# probe instead - see the healthcheck on the 'scanner' service in
# docker/docker-compose.monitoring.yml, which overrides this one.
HEALTHCHECK --interval=5m --timeout=15s --start-period=10s --retries=2 \
    CMD ["python", "-c", "import opencloud_local_scan as s; s.load_release_schedule(); s.load_database()"]

ENTRYPOINT ["check-opencloud-security"]
# No default CMD: with no arguments, the entrypoint relies entirely on
# COS_-prefixed environment variables (see README.md "Environment variables").
# Run `docker run --rm check-opencloud-security --help` explicitly for usage.
#
# The plugin always scans in process with its built-in scanner, so there is no
# remote backend to point it at. The same image also ships the scanner as a
# standalone service for scheduled scans and for reusing one cached result
# across several monitoring consumers:
# It listens on loopback unless told otherwise, so reaching it from outside the
# container means binding the container's own interfaces - and that needs a
# token, because the service scans whatever host a request names:
#   docker run --rm -p 127.0.0.1:8811:8811 \
#     -e COS_SERVICE_LISTEN=0.0.0.0 \
#     -e COS_SERVICE_TOKEN="$(openssl rand -hex 32)" \
#     --entrypoint check-opencloud-scanner check-opencloud-security serve
# and a one-shot scan that prints the result document as JSON:
#   docker run --rm \
#     --entrypoint check-opencloud-scanner check-opencloud-security \
#     scan opencloud.example.com
