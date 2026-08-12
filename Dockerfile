# syntax=docker/dockerfile:1
#
# Builds a self-contained image for check-opencloud-security.
# End users do not need Python, pip, or uv installed on the host -
# only Docker. See README.md for usage examples.

FROM python:3.13-slim AS builder

# uv is this project's dependency manager and build front end; the same
# command is used in CI (see .github/workflows/publish-pypi.yml).
COPY --from=ghcr.io/astral-sh/uv:0.11.31 /uv /uvx /bin/

WORKDIR /src

# Only copy what is needed to build the wheel, keeping the build cache-friendly.
COPY pyproject.toml README.md LICENSE ./
COPY check_opencloud_security.py ./
COPY opencloud_local_scan ./opencloud_local_scan

RUN uv build --wheel --out-dir /dist


FROM python:3.13-slim

LABEL org.opencontainers.image.title="check-opencloud-security" \
      org.opencontainers.image.description="Nagios/Icinga plugin and built-in scanner for OpenCloud instances" \
      org.opencontainers.image.source="https://github.com/sowoi/check-opencloud-security" \
      org.opencontainers.image.licenses="GPL-3.0-only"

COPY --from=ghcr.io/astral-sh/uv:0.11.31 /uv /bin/
COPY --from=builder /dist/*.whl /tmp/

# Dependencies are resolved from the wheel metadata (pyproject.toml);
# this project has no requirements.txt - generate one with `uv export`
# if some tool of yours needs it.
RUN uv pip install --system --no-cache /tmp/*.whl \
    && rm -rf /tmp/*.whl /bin/uv \
    && useradd --no-create-home --shell /usr/sbin/nologin nagios

USER nagios

# Port of the optional scan service (`check-opencloud-scanner serve`).
EXPOSE 8080

ENTRYPOINT ["check-opencloud-security"]
# No default CMD: with no arguments, the entrypoint relies entirely on
# COS_-prefixed environment variables (see README.md "Environment variables").
# Run `docker run --rm check-opencloud-security --help` explicitly for usage.
#
# The plugin always scans in process - OpenCloud has no scan API, so there is
# no remote backend to point it at. The same image also ships the scanner as a
# standalone service for scheduled scans and for reusing one cached result
# across several monitoring consumers:
#   docker run --rm -p 8080:8080 \
#     --entrypoint check-opencloud-scanner check-opencloud-security serve
# and a one-shot scan that prints the result document as JSON:
#   docker run --rm \
#     --entrypoint check-opencloud-scanner check-opencloud-security \
#     scan cloud.example.com
