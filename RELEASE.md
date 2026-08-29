## check-opencloud-security 1.14.1

### Changed

- **Check catalogue order**: The catalogue page now lists OpenCloud's own
  hardening categories first, security headers (including CSP) after, and
  transport/TLS last.

### Removed

- **`installed`, `maintenanceMode` and `databaseUpgrade` checks**: Dropped
  the findings derived from `/status.php`'s `installed`, `maintenance` and
  `needsDbUpgrade` fields. OpenCloud's handler for that endpoint returns
  those three fields as hardcoded `true`/`false`/`false` literals rather than
  reading any live state, so none of the checks could ever fire - see [Why
  OpenCloud still answers `/status.php`](docs/status-php.md).

### Fixed

- **`actions/upload-artifact` in `supply-chain.yml`** was still pinned to
  v4.6.2, the last release built on GitHub's now-deprecated Node 20 runtime.
  Bumped to v7.0.1 (Node 24), pinned to its commit the same way every other
  action in the workflows already is. Every other pinned action was already
  on a Node 24 release.
