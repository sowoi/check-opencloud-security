## check-opencloud-security 1.3.0

### Documentation

- Required agent and Copilot instructions to record every change in both
  `CHANGELOG.md` and `RELEASE.md` under the version declared in `pyproject.toml`.

### Changed

- Multi-host checks run one worker per target, up to the configurable default
  ceiling of five, while single-host checks remain single-threaded.

### Added

- Itemized baseline diffs in text, Markdown, and Slack Block Kit JSON,
  including structured webhook payloads.
- Native Prometheus text output and a lightweight `/metrics` exporter for
  Kubernetes and cloud-native monitoring.

