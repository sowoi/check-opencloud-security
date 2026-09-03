# Worked examples

Complete, copy-and-paste invocations for the situations that come up most
often. Every example uses `opencloud.example.com` as the host - substitute
your own, and scan only instances you are responsible for.

Longer, platform-specific examples have pages of their own:
[Kubernetes](kubernetes.md), [CI pipelines](ci.md),
[Prometheus and Grafana](prometheus.md),
[webhook adapters](webhook-recipes.md) and
[fleets of instances](many-instances.md).

<!-- TOC -->
* [Worked examples](#worked-examples)
  * [The basics](#the-basics)
  * [Release track examples](#release-track-examples)
  * [Accepting findings you are not going to fix](#accepting-findings-you-are-not-going-to-fix)
  * [Both together, in a configuration file](#both-together-in-a-configuration-file)
  * [Instances that are not on the public internet](#instances-that-are-not-on-the-public-internet)
  * [Thresholds and notifications](#thresholds-and-notifications)
  * [Icinga2 command definition](#icinga2-command-definition)
  * [The scanner on its own](#the-scanner-on-its-own)
<!-- TOC -->


## The basics

```bash
# The smallest useful check
check-opencloud-security --host opencloud.example.com

# Include hardening measures and security headers in the report
check-opencloud-security --host opencloud.example.com --check-hardening

# Explain the verdict: where the rating started, what pulled it down,
# and what every identifier in the output means
check-opencloud-security --host opencloud.example.com --check-hardening --debug

# Several instances in one run; the worst state is reported
check-opencloud-security --host cloud-a.example.com --host cloud-b.example.com
```

## Release track examples

```bash
# You follow the production track: only production releases and their
# patches count, and you are never sent to a rolling release
check-opencloud-security --host opencloud.example.com --release-track production

# You follow the rolling track: a release is out of support as soon as the
# next one ships, and you want to know about it the same day
check-opencloud-security --host opencloud.example.com --release-track rolling

# An LTS instance, where two years of backports are the whole point
check-opencloud-security --host opencloud.example.com --release-track lts

# You do not want to say: the release schedule works the track out from the
# version the instance reports
check-opencloud-security --host opencloud.example.com --release-track auto

# Warn as soon as an update is available on your track, rather than only
# when support has actually run out
check-opencloud-security --host opencloud.example.com \
    --release-track production --update-warning
```

Remember that a *newer* version is not automatically a *better* supported one:
declaring `production` on an instance running a rolling release reports it as
*ahead* of its track, not as current on it - and never as end of life, which
is reserved for a release behind the current one of your track.

## Accepting findings you are not going to fix

```bash
# The reverse proxy owns the HSTS header, and the default CSP cannot be
# tightened without breaking the web UI
check-opencloud-security --host opencloud.example.com --check-hardening \
    --ignore-hardening cspWithoutUnsafeInline \
    --ignore-hardening hstsPreload

# The same thing as a single comma-separated value, which is what you want
# in an Icinga command definition or an environment variable
check-opencloud-security --host opencloud.example.com --check-hardening \
    --ignore-hardening 'cspWithoutUnsafeInline,hstsPreload'

# Wildcards, for the identifiers that carry a path or a port
check-opencloud-security --host opencloud.example.com \
    --ignore-hardening 'debugPort:*'

# Basic auth is deliberately enabled for a migration tool, and the rating
# should reflect that decision rather than stay red for weeks
check-opencloud-security --host opencloud.example.com --check-hardening \
    --ignore-hardening basicAuthDisabled

# Check what a waiver is actually doing before you commit to it: --debug
# lists every waived finding and marks it in the explanation
check-opencloud-security --host opencloud.example.com --check-hardening \
    --ignore-hardening basicAuthDisabled --debug
```

## Both together, in a configuration file

This is the form to prefer for anything permanent, because a waiver can carry
a comment explaining why it exists and when it should be revisited:

```yaml
# /etc/check-opencloud-security/config.yml
host: opencloud.example.com
check_hardening: true
update_warning: true

scanner:
  release_track: production
  ignore_hardenings:
    - cspWithoutUnsafeInline   # default csp.yaml; tightening it breaks the web UI
    - hstsPreload              # the reverse proxy sets its own HSTS header
    - 'debugPort:*'            # debug ports are firewalled at the perimeter
```

```bash
check-opencloud-security --config /etc/check-opencloud-security/config.yml
```

The same settings as environment variables, for a container or a systemd unit:

```bash
export COS_HOST=opencloud.example.com
export COS_CHECK_HARDENING=1
export COS_SCANNER_RELEASE_TRACK=production
export COS_SCANNER_IGNORE_HARDENINGS='cspWithoutUnsafeInline;hstsPreload'
check-opencloud-security
```

## Instances that are not on the public internet

```bash
# OpenCloud's own proxy, with a self-signed certificate
check-opencloud-security --host 10.0.0.5 --port 9200 --insecure

# Plain HTTP behind a terminating load balancer
check-opencloud-security --host opencloud.internal --scheme http

# An IPv6 address
check-opencloud-security --host '[2001:db8::1]'

# Air-gapped: no release feed, verdicts from the bundled schedule only
check-opencloud-security --host opencloud.example.com --update-source bundled

# Rate-limited by GitHub, or simply offline: pin the newest release yourself
check-opencloud-security --host opencloud.example.com --latest-version 7.2.3

# Skip the debug-port probes, which cost up to 15 seconds on a firewalled host
check-opencloud-security --host opencloud.example.com --no-debug-ports --timeout 5
```

## Thresholds and notifications

```bash
# Stricter than the default: warn at A, go critical at C
check-opencloud-security --host opencloud.example.com --warning 4 --critical 3

# Post to a webhook when the check goes critical
check-opencloud-security --host opencloud.example.com \
    --webhook-url https://hooks.example.com/opencloud \
    --webhook-header 'Authorization: Bearer secret://webhook_token'

# A production instance, hardening reported, two findings accepted,
# notified on anything worse than OK - a realistic complete invocation
check-opencloud-security --host opencloud.example.com \
    --release-track production \
    --check-hardening \
    --ignore-hardening 'cspWithoutUnsafeInline,hstsPreload' \
    --update-warning \
    --warning 4 --critical 2 \
    --webhook-url https://hooks.example.com/opencloud \
    --webhook-on warning
```

## Icinga2 command definition

```
apply Service "opencloud-security" {
  import "generic-service"
  check_command = "check_opencloud_security"

  vars.opencloud_host           = host.address
  vars.opencloud_check_hardening = true
  vars.opencloud_release_track  = "production"
  vars.opencloud_ignore_hardening = "cspWithoutUnsafeInline,hstsPreload"

  assign where host.vars.opencloud == true
}
```

## The scanner on its own

```bash
# One-shot JSON, for a script or an ad-hoc look at the raw result
check-opencloud-scanner scan opencloud.example.com | jq '.rating, .lifecycle'

# Which findings were waived, and which are recorded but not alerted on
check-opencloud-scanner scan opencloud.example.com | jq '.ignored, .extraChecks'
```
