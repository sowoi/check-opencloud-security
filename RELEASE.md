## check-opencloud-security 1.3.0

### Added

- Itemized baseline diffs in text, Markdown, and Slack Block Kit JSON,
  covering CVEs, hardening and check changes, rating/lifecycle trends, and
  installed/update-version shifts. Webhooks now carry the structured diff.
- Native Prometheus text output and a lightweight `/metrics` exporter for
  Kubernetes and cloud-native monitoring. The exporter refreshes scans on
  demand with a configurable cache interval and requires no extra dependency.

### Changed

- Multi-host checks now run one worker per target, up to the configurable
  default ceiling of five. A single-host check remains single-threaded, and
  result blocks and Nagios perfdata remain isolated and ordered by input host.
