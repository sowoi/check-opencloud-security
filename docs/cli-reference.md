# CLI option reference

Every command-line option the plugin accepts, what it defaults to, and the
environment variable that sets the same thing. This lives on its own page
because it is a lookup table rather than something to read: the
[main README](../README.md) is the guided tour, and this is the index at the
back.

Precedence between the three ways of setting anything is always the same:
**command-line flag > environment variable > configuration file > default.**
See [Configuration file and secrets](../README.md#configuration-file-and-secrets)
for the file, and [Environment variables](../README.md#environment-variables)
for the naming rules.

<!-- TOC -->
* [CLI option reference](#cli-option-reference)
  * [Command](#command)
  * [Options](#options)
  * [Settings with no flag of their own](#settings-with-no-flag-of-their-own)
  * [Where to go next](#where-to-go-next)
<!-- TOC -->


`check-opencloud-security -h` prints the same list in the terminal.

## Command
```shell
check-opencloud-security --host <Hostname> --check-hardening
```

## Options
| Option                        | Description                                                                                                                                  | Default                                         | Environment variable            |
|:------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------|:------------------------------------------------|:--------------------------------|
| `-H, --host`                  | OpenCloud server address(es): hostname, IP or URL, optionally with a port. Accepts a comma-separated list to check multiple hosts in one run | **required**                                    | `COS_HOST`                      |
| `-P, --proxy`                 | Proxy server address                                                                                                                         | *None*                                          | `COS_PROXY`                     |
| `-d, --debug`                 | Explain the rating and every finding; verbose logging                                                                                        | *False*                                         | `COS_DEBUG`                     |
| `-w, --warning`               | Rating (0-5) at or below which the check warns                                                                                               | `3` (`C`)                                       | `COS_WARNING`                   |
| `-c, --critical`              | Rating (0-5) at or below which the check is critical                                                                                         | `1` (`E`)                                       | `COS_CRITICAL`                  |
| `--check-hardening`           | Also report missing hardening measures and security headers                                                                                  | *False*                                         | `COS_CHECK_HARDENING`           |
| `--timeout`                   | HTTP timeout in seconds per request                                                                                                          | `10`                                            | `COS_TIMEOUT`                   |
| `--port`                      | Port the instance listens on (OpenCloud's own proxy uses `9200`)                                                                             | from `--host`, else `443`                       | `COS_SCANNER_TARGET_PORT`       |
| `--scheme`                    | `https` or `http`; `https` falls back to `http` automatically                                                                                | `https`                                         | `COS_SCANNER_SCHEME`            |
| `--insecure`                  | Do not verify the instance's TLS certificate                                                                                                 | *False*                                         | `COS_INSECURE`                  |
| `--ca-file`                   | PEM CA bundle used to verify an internal TLS certificate                                                                                     | *None* (system trust store)                     | `COS_SCANNER_TLS_CA_FILE`       |
| `--no-extra-checks`           | Only check product, version and security headers                                                                                             | *False*                                         | `COS_NO_EXTRA_CHECKS`           |
| `--no-debug-ports`            | Skip probing the OpenCloud debug ports                                                                                                       | *False*                                         | `COS_NO_DEBUG_PORTS`            |
| `--concurrency`               | Maximum parallel host workers; one is used per host up to this ceiling                                                                       | `5`                                             | `COS_CONCURRENCY`               |
| `--format`                    | One-shot output format: `nagios`, `prometheus`, `json`, `sarif` or `junit`                                                                   | `nagios`                                        | `COS_FORMAT`                    |
| `--prometheus-listen-port`    | Serve native `/metrics` on this port until stopped                                                                                           | disabled                                        | `COS_PROMETHEUS_LISTEN_PORT`    |
| `--prometheus-listen-addr`    | Bind address for the native Prometheus exporter                                                                                              | `127.0.0.1`                                     | `COS_PROMETHEUS_LISTEN_ADDR`    |
| `--scrape-interval`           | Seconds to cache exporter scan results (`0` scans on every scrape)                                                                           | `60`                                            | `COS_SCRAPE_INTERVAL`           |
| `--ignore-hardening`          | Hardening measure or check to accept, repeatable, comma-separated and wildcard capable                                                       | *None*                                          | `COS_SCANNER_IGNORE_HARDENINGS` |
| `--release-track`             | Release track this instance follows: `rolling`, `production`, `lts` or `auto`                                                                | `auto`                                          | `COS_SCANNER_RELEASE_TRACK`     |
| `--update-source`             | Where the newest release comes from: `auto`, `feed`, `pinned`, `bundled`, `off`                                                              | `auto`                                          | `COS_UPDATE_SOURCE`             |
| `--release-feed`              | URL of the release feed                                                                                                                      | GitHub releases API of `opencloud-eu/opencloud` | `COS_RELEASES_FEED_URL`         |
| `--release-token`             | Token for the release feed (raises GitHub's rate limit)                                                                                      | *None*                                          | `COS_RELEASES_TOKEN`            |
| `--latest-version`            | Newest release, given explicitly; implies `--update-source pinned`                                                                           | *None*                                          | `COS_RELEASES_LATEST_VERSION`   |
| `--no-update-check`           | Disable the update check (same as `--update-source off`)                                                                                     | *False*                                         | `COS_NO_UPDATE_CHECK`           |
| `--update-warning`            | Report WARNING when a newer release is available                                                                                             | *False*                                         | `COS_UPDATE_WARNING`            |
| `--baseline`                  | File that remembers the findings of the last run, one entry per host                                                                         | *None*                                          | `COS_BASELINE`                  |
| `--warn-on-new`               | Only alert on findings that are new or worse than the baseline; needs `--baseline`                                                           | *False*                                         | `COS_WARN_ON_NEW`               |
| `--diff-format`               | Render baseline changes as `text`, `markdown`, or Slack Block Kit `slack`/`json`                                                             | `text`                                          | `COS_DIFF_FORMAT`               |
| `--self-update-check`         | Note when a newer version of the plugin is published on PyPI; never changes the exit code                                                    | *False*                                         | `COS_SELF_UPDATE_CHECK`         |
| `--webhook-url`               | Optional endpoint notified when the check reaches the configured state                                                                       | *None* (disabled)                               | `COS_WEBHOOK_URL`               |
| `--webhook-on`                | Lowest state that triggers the webhook (`critical`, `warning`, `unknown`, `always`)                                                          | `critical`                                      | `COS_WEBHOOK_ON`                |
| `--webhook-format`            | Webhook body shape: `generic` (the plugin's own JSON), `slack`, `discord`, `ntfy`, or `gotify`                                                | `generic`                                       | `COS_WEBHOOK_FORMAT`            |
| `--webhook-header`            | Extra header for the webhook request, repeatable                                                                                             | *None*                                          | `COS_WEBHOOK_HEADERS`           |
| `--webhook-secret`            | Shared secret; signs each webhook body with HMAC-SHA256 in `X-COS-Signature`                                                                  | *None* (unsigned)                               | `COS_WEBHOOK_SECRET`            |
| `--webhook-timeout`           | HTTP timeout in seconds for the webhook call                                                                                                 | `10`                                            | `COS_WEBHOOK_TIMEOUT`           |
| `--allow-private-webhooks`    | Permit webhooks to private, loopback, or link-local addresses                                                                                | *False*                                         | `COS_ALLOW_PRIVATE_WEBHOOKS`    |
| `--webhook-digest`            | With several `--host` targets, send one combined webhook instead of one per host                                                            | *False*                                         | `COS_WEBHOOK_DIGEST`            |
| `--retries`                   | Retry attempts for transient network errors                                                                                                  | `2`                                             | `COS_RETRIES`                   |
| `--backoff-factor`            | Exponential backoff factor (seconds) between retries                                                                                         | `0.5`                                           | `COS_BACKOFF_FACTOR`            |
| `--config`                    | Path to the configuration file (`.json` as JSON, else YAML)                                                                                  | auto-discovered                                 | `COS_CONFIG_FILE`               |
| `--configure`                 | Ask for the settings interactively and save them, then exit                                                                                  | —                                               | —                               |
| `--upgrade-self [run\|check]` | Upgrade the plugin with pipx, uv or pip, then exit; `check` prints the command instead of running it                                         | `run` when given without a value                | —                               |
| `--check-only`                | Only with `--upgrade-self`: another spelling of `--upgrade-self check`                                                                       | —                                               | —                               |
| `-V, --version`               | Show the installed version and exit                                                                                                          | —                                               | —                               |
| `-h, --help`                  | Show help and exit                                                                                                                           | —                                               | —                               |

## Settings with no flag of their own

The TLS expiry window, the debug-port list and the advisory sources have no
command-line flag. They are configured through the
[configuration file](../README.md#configuration-file-and-secrets) or their
`COS_SCANNER_*` environment variables, and
[`config/check-opencloud-security.example.yml`](../config/check-opencloud-security.example.yml)
lists every one of them with a comment.

## Where to go next

| Page | Why |
|:-----|:----|
| [Main README](../README.md) | What each of these options is for, with worked examples |
| [Configuration file and secrets](../README.md#configuration-file-and-secrets) | Setting the same things in a file instead |
| [Machine-readable output](output-formats.md) | `--format json`, `sarif` and `junit` in depth |
| [Checking a fleet of instances](many-instances.md) | `--host` with many targets, and one config file per instance |
| [Troubleshooting](troubleshooting.md) | The exit-code reference |
