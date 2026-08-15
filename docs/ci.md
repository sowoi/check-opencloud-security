# Running the check from CI

A scheduled pipeline is a reasonable place for this check when you have no
monitoring system, or when you want a second opinion that runs from outside
your own network. It is not a replacement for one: a pipeline that stops
running is silent, and silence is indistinguishable from a healthy instance.

Whatever the platform, three things decide whether it works:

- **The runner has to reach the instance.** A hosted runner cannot scan
  something behind your firewall - use a self-hosted runner for that.
- **The scan is from the runner's vantage point.** What it measures about TLS,
  enforced HTTPS and reachable debug ports is what an outsider on that network
  sees, which is usually the interesting answer.
- **The exit code is the result**: `0` OK, `1` WARNING, `2` CRITICAL, `3`
  UNKNOWN. A pipeline fails on anything non-zero, so `--warning` and
  `--critical` decide how strict it is.

## GitHub Actions

```yaml
name: OpenCloud security check

on:
  schedule:
    - cron: "0 6 * * *"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - name: Install the check
        run: pipx install check-opencloud-security==1.1.0

      - name: Scan the instance
        env:
          COS_HOST: opencloud.example.com
          COS_CHECK_HARDENING: "true"
          COS_UPDATE_WARNING: "true"
          # Raises GitHub's anonymous rate limit for the release feed. The
          # token GITHUB_TOKEN gives the job is enough; it needs no scopes.
          COS_RELEASES_TOKEN: ${{ github.token }}
        run: check-opencloud-security
```

Pin the version rather than tracking `latest`. The release schedule and the
newest known OpenCloud version ship inside the package, so which version you
install is part of the verdict - and an unpinned install turns an upstream
release into an unexplained pipeline failure.

`workflow_dispatch` is worth keeping: it is how you re-run the check after
fixing something without waiting for tomorrow.

### Reporting rather than failing

A failed scheduled workflow only notifies the person who last touched it. To
get the result somewhere people look, keep the job green and post the outcome:

```yaml
      - name: Scan the instance
        id: scan
        continue-on-error: true
        env:
          COS_HOST: opencloud.example.com
          COS_CHECK_HARDENING: "true"
        run: |
          set +e
          check-opencloud-security > result.txt
          state=$?
          set -e
          cat result.txt
          echo "state=$state" >> "$GITHUB_OUTPUT"

      - name: Summarise
        run: |
          {
            echo "### OpenCloud security check"
            echo '```'
            cat result.txt
            echo '```'
          } >> "$GITHUB_STEP_SUMMARY"
```

Or set `--webhook-url` and let the check report itself - see
[Webhook recipes](webhook-recipes.md). That route survives the workflow being
disabled after sixty days of repository inactivity, which the summary does
not.

### The JSON document instead

For anything that has to make a decision - a policy gate, a dashboard, an
issue filed automatically - use the scanner rather than the plugin. It prints
the full result document, and every field in it is documented in
[the library README](../opencloud_local_scan/README.md).

```yaml
      - name: Scan and keep the result
        run: |
          check-opencloud-scanner scan --compact opencloud.example.com > scan.json
          jq -e '.EOL == false' scan.json \
            || { echo "::error::The installed release no longer receives security fixes"; exit 1; }

      - uses: actions/upload-artifact@v4
        with:
          name: opencloud-scan
          path: scan.json
```

`jq -e` exits non-zero when the expression is false, which is what turns a
field of the document into a pipeline gate. `.EOL`, `.rating`,
`.updates.available` and `.lifecycle.daysRemaining` are the four worth gating
on.

## GitLab CI

```yaml
opencloud-security:
  image: python:3.13-slim
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
  variables:
    COS_HOST: opencloud.example.com
    COS_CHECK_HARDENING: "true"
  before_script:
    - pip install --no-cache-dir check-opencloud-security==1.1.0
  script:
    - check-opencloud-security
  # WARNING (1) is worth seeing without failing the pipeline outright.
  allow_failure:
    exit_codes: [1]
```

`allow_failure.exit_codes` maps the plugin's states onto GitLab's directly:
list `1` to tolerate WARNING, add `3` to tolerate a scan that could not
complete - though a scan that cannot complete is usually the thing you most
want to know about.

Add the schedule under *Build → Pipeline schedules*; the `rules` block above
keeps the job out of ordinary commit pipelines.

## Using the container image instead of installing

No image is published to a registry, so a container job builds it first. It
runs as an unprivileged user and carries a `HEALTHCHECK` - see
[Docker](../README.md#docker). Build it once, push it to your own registry,
and pin the tag:

```shell
docker build -f docker/Dockerfile \
  -t registry.example.com/check-opencloud-security:1.1.0 .
docker push registry.example.com/check-opencloud-security:1.1.0

docker run --rm \
  -e COS_HOST=opencloud.example.com \
  -e COS_CHECK_HARDENING=true \
  registry.example.com/check-opencloud-security:1.1.0
```

## Do not put the token on the command line

CI logs are readable by more people than you think, and `--release-token` on a
command line ends up in them. Pass secrets as environment variables
(`COS_RELEASES_TOKEN`, `COS_WEBHOOK_URL`) or as a
[secret reference](../README.md#configuration-file-and-secrets). The plugin
redacts tokens from its own debug output; it cannot redact your shell trace.

---

[Back to the documentation index](README.md) | [Back to the main README](../README.md)
