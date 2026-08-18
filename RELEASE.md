## check-opencloud-security 1.6.1

### Fixed

- The ARQ worker Compose health check now verifies its process and Redis
  connection instead of probing the web server endpoint it does not run.
- The web application's `/healthz` probe now checks Redis and returns 503
  while its required state store is unavailable.
- The web application's `/healthz` probe now also reports aggregate queue
  depth and requires a short-lived Redis worker heartbeat.

## check-opencloud-security 1.6.0

### Added

- Webhook signature verification using HMAC-SHA256. When configured with
  `--webhook-secret` or `COS_WEB_WEBHOOK_SECRET` (for the web application),
  webhook payloads are signed with an `X-COS-Signature` header (format:
  `sha256=<hex>`). Receivers must share the same secret to verify signatures.
- Redis encryption with key rotation support (web application). When
  `COS_WEB_ENCRYPT_RESULTS=true` is set, scan results are encrypted at rest
  using AES-256-GCM. Encryption keys are configured via
  `COS_WEB_ENCRYPTION_KEY_<VERSION>` env vars (hex-encoded 256-bit keys).
  Key rotation is transparent: new encryptions use the highest version,
  old keys still decrypt existing data. Encryption defaults to off to maintain
  backward compatibility.
- Multiple report formats for web application scan results (API):
  - **CSV format**: Export findings as CSV with scan metadata headers
  - **SARIF format**: Security Results Interchange Format for integration with
    security dashboards and tools
  - Formats are selected via `output_format` query parameter in POST requests
  - Existing dashboard and JSON formats remain unchanged

### Fixed

- A time-of-check-time-of-use vulnerability in webhook URL validation
  allowed DNS rebinding attacks to bypass SSRF protection and target private
  addresses. Webhook DNS resolution is now re-validated immediately before
  delivery and blocked if the address has changed since submission.

### Documentation

- Added `adr/0002-no-scan-result-caching.md` explaining why scan results are
  not cached across requests and the data protection and security
  considerations behind that decision.
