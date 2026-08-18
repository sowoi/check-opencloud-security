## check-opencloud-security 1.6.1

### Fixed

- The ARQ worker Compose health check now verifies its process and Redis
  connection instead of probing the web server endpoint it does not run.
- The web application's `/healthz` probe now checks Redis and returns 503
  while its required state store is unavailable.
- The web application's `/healthz` probe now also reports aggregate queue
  depth and requires a short-lived Redis worker heartbeat.
