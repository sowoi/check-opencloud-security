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

<!-- TOC -->
* [Running the check from CI](#running-the-check-from-ci)
  * [GitHub Actions](#github-actions)
    * [The action](#the-action)
    * [Feeding the code-scanning dashboard](#feeding-the-code-scanning-dashboard)
    * [Installing it yourself instead](#installing-it-yourself-instead)
    * [OpenCloud compatibility evidence](#opencloud-compatibility-evidence)
    * [Reporting rather than failing](#reporting-rather-than-failing)
    * [The JSON document instead](#the-json-document-instead)
  * [GitLab CI](#gitlab-ci)
  * [Using the container image instead of installing](#using-the-container-image-instead-of-installing)
  * [Do not put the token on the command line](#do-not-put-the-token-on-the-command-line)
<!-- TOC -->


## GitHub Actions

### The action

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
      - uses: sowoi/check-opencloud-security@v1.16.0
        with:
          target: opencloud.example.com
          # Raises GitHub's anonymous rate limit for the release feed. The
          # token the job already has is enough; it needs no scopes.
          releases-token: ${{ github.token }}
```

That is the whole thing. The step installs the pinned release, scans the
instance, writes `opencloud-security.json`, puts the result in the job
summary, and fails the job on WARNING, CRITICAL or UNKNOWN.

**Pin the tag.** The release schedule and the newest known OpenCloud version
ship *inside* the package, so which release runs is part of the verdict.
`@v1.16.0` installs exactly 1.16.0; a branch or SHA ref installs the newest
release and says so in a warning annotation.

| Input | Default | What it does |
|:--|:--|:--|
| `target` | *required* | The instance, as a hostname or URL |
| `version` | the pinned tag | Which release of the check to install |
| `format` | `json` | `json`, `sarif`, `junit` or `nagios` |
| `output-file` | `opencloud-security.json` | Where the output is written |
| `fail-on` | `warning` | `warning`, `critical` or `never` |
| `warning` / `critical` | plugin defaults | Rating thresholds |
| `check-hardening` | `true` | Count hardening measures towards the result |
| `ignore-hardening` | *none* | Identifiers to waive, comma-separated |
| `release-track` | `auto` | `auto`, `rolling`, `production` or `lts` |
| `releases-token` | *none* | A token for the release feed's rate limit |
| `summary` | `true` | Write the result to the job summary |
| `extra-args` | *none* | Any other flag, passed verbatim |

The outputs are `exit-code`, `status`, `rating`, `rating-label`, `message` and
`result-file`. All but the first two are empty unless `format` is `json`,
because they are read out of that document:

```yaml
      - uses: sowoi/check-opencloud-security@v1.16.0
        id: scan
        with:
          target: opencloud.example.com
          fail-on: never

      - name: Open an issue when the grade drops below A
        if: steps.scan.outputs.rating < 4
        run: gh issue create --title "OpenCloud is rated ${{ steps.scan.outputs.rating-label }}"
        env:
          GH_TOKEN: ${{ github.token }}
```

`fail-on: never` is what makes that possible: the step succeeds, and the
decision moves to a later step that can do something more useful than turning
the run red.

Note that the runner has to be able to reach the instance. A hosted runner
cannot see anything behind your firewall - use a self-hosted one for that, or
scan from the network the instance actually publishes to.

### Feeding the code-scanning dashboard

`format: sarif` writes SARIF 2.1.0, which is what GitHub's Security tab
ingests. The findings then live where the rest of your security findings do,
with their own history, rather than in a log nobody opens:

```yaml
permissions:
  contents: read
  security-events: write

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: sowoi/check-opencloud-security@v1.16.0
        with:
          target: opencloud.example.com
          format: sarif
          output-file: opencloud-security.sarif
          # Upload the findings even when they are bad enough to fail a build.
          fail-on: never

      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: opencloud-security.sarif
          category: opencloud-security
```

Keep `fail-on: never` here and gate on the uploaded findings instead. A step
that fails before the upload throws away the very findings that failed it.

### Installing it yourself instead

Nothing about the action is privileged - it installs the same package and runs
the same command. Do it by hand when you need a step the action does not
model, or when you would rather not depend on an action at all.

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

### OpenCloud compatibility evidence

The repository's **real OpenCloud container** workflow keeps one reviewed,
immutable rolling-image digest as its baseline and runs the scanner against it
weekly. It verifies that the container still initializes, exposes the expected
public status endpoint, identifies itself as OpenCloud, reports a version, and
produces a bounded rating. The image reports its exact OpenCloud version during
the test; the workflow intentionally does not claim compatibility for a new
release until that evidence has been reviewed.

| Evidence | Baseline | Compatible when | Review path |
|:--|:--|:--|:--|
| Vendor container integration | `opencloudeu/opencloud-rolling@sha256:0bb9038f4c01ab187a014e97550435f5d45630731aed9341d87a0b40fe72fe3d` | The complete integration test passes and its reported version and externally observable behaviour are reviewed | Dispatch the workflow with `candidate_image`; update the baseline only in a reviewed pull request |
| Release lifecycle | Bundled schedule plus the daily conservative refresh | New or changed lines retain existing support facts and pass lifecycle regressions | Review the release-schedule refresh PR |
| Advisories | Bundled database plus the daily conservative refresh | New advisories add evidence without removing known affected ranges | Review the advisory-database refresh PR |

The automation never rewrites fixtures, grades, or security expectations to
turn a candidate green. A changed response, header, endpoint, or security
property must have release evidence and a reviewable test change naming that
evidence.

The repository's `Supply-chain checks` workflow runs on pull requests, pushes
to `main` and weekly. It exports the fully resolved `uv.lock` dependency set,
runs `pip-audit` over core, web and MCP dependencies, and publishes a
CycloneDX SBOM as a workflow artifact. Pushes and scheduled runs also receive
a GitHub Sigstore attestation, so the SBOM can be verified with
`gh attestation verify`. The release workflow repeats this for the exact
runtime environment shipped with each package and attests the package files
and web bundle.

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
[Docker](installation.md#docker). Build it once, push it to your own registry,
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
