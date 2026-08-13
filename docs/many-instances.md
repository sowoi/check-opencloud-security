# Checking a fleet of instances

One check per instance is simple until there are twenty of them, each with its
own port, its own release track and its own list of accepted findings. This
page covers the three shapes that scale, from smallest to largest.

## One command, several hosts

`--host` takes a comma-separated list. The plugin scans them in turn, prints a
one-line summary followed by a block per host, and exits with the worst state
it found - see [Checking multiple hosts](../README.md#checking-multiple-hosts).

```shell
check-opencloud-security --check-hardening \
  --host opencloud1.example.com,opencloud2.example.com:9200,[2001:db8::1]
```

This is the right answer when the instances are alike. Everything after
`--host` applies to all of them, so the moment one instance needs `--insecure`
or a waiver the others do not, you have outgrown it.

Aggregating also loses the per-host history your monitoring system would
otherwise keep. If you want one red service per broken instance rather than
one red service for the group, use one check per host instead.

## One configuration file per instance

Each instance gets a file, and the file carries everything that makes it
different. Nothing is repeated on the command line, so a change is a change in
one place.

```yaml
# /etc/check-opencloud-security/prod-eu.yml
host: opencloud-eu.example.com
check_hardening: true
update_warning: true

scanner:
  target_port: 9200
  release_track: production
  ignore_hardenings:
    # The reverse proxy owns this header; the instance cannot set it.
    - hstsPreload

releases:
  mode: auto
  token: secret://releases_token
```

```shell
check-opencloud-security --config /etc/check-opencloud-security/prod-eu.yml
```

Precedence is **command line > environment variable > configuration file >
default**, so a per-instance file can still be overridden for one run without
editing it. The full syntax, including `secret://`, is in
[Configuration file and secrets](../README.md#configuration-file-and-secrets).

Write the first file with `check-opencloud-security --configure --config
/etc/check-opencloud-security/prod-eu.yml` and copy it for the rest.

## A loop over the files

With one file per instance, scanning the fleet is a `for` loop, and the exit
codes are what you report on:

```shell
#!/bin/sh
# Scan every configured instance; exit with the worst state seen.
set -u

worst=0
rank() { case "$1" in 2) echo 3 ;; 1) echo 2 ;; 3) echo 1 ;; *) echo 0 ;; esac; }

for config in /etc/check-opencloud-security/*.yml; do
  check-opencloud-security --config "$config" || state=$?
  state="${state:-0}"
  [ "$(rank "$state")" -gt "$(rank "$worst")" ] && worst="$state"
  unset state
done

exit "$worst"
```

`rank` exists because Nagios exit codes are not ordered by severity:
`CRITICAL` (2) outranks `WARNING` (1), which outranks `UNKNOWN` (3), which
outranks `OK` (0). Sorting numerically would report a host that could not be
reached as worse than a host that is end-of-life.

## Where the checks should run from

The plugin scans over the network, from wherever it runs, so where you run it
decides what it can see:

- An instance behind a firewall needs a check running inside it, not a check
  on the monitoring server with a hole punched through.
- Whether HTTPS is enforced and whether the certificate is trusted depend on
  the path taken to the instance. Scanning through a load balancer that
  terminates TLS measures the load balancer.
- Debug-port probes only mean anything from a network that is *supposed* not
  to reach them. From inside the instance's own host they will find ports that
  no outsider could.

If several monitoring consumers need the same result, run the
[scan service](../README.md#running-the-scanner-as-a-service) close to the
instances and let them share its cache. The plugin itself never talks to it -
it always scans in process - so the service is for dashboards and scripts.

## Keeping the waivers honest

A fleet accumulates `ignore_hardenings` entries, and a waiver that is never
revisited is how a regression becomes invisible. Two things keep them honest:

- A waiver only ever suppresses the alert. The finding stays in the result
  document with `"ignored": true`, and `--debug` still explains it - see
  [Accepting a finding you are not going to fix](../README.md#accepting-a-finding-you-are-not-going-to-fix).
- Only a check that *actually failed* can be waived, so a waiver cannot
  silently cover a measure that later regresses into a different finding.

Review them by scanning with the waivers off and diffing:

```shell
for config in /etc/check-opencloud-security/*.yml; do
  echo "== $config"
  COS_SCANNER_IGNORE_HARDENINGS="" check-opencloud-security --config "$config" --debug \
    | grep -E 'ignored|waived|FAIL'
done
```

One identifier will never appear in that list, however many instances you
run: `publicLinkExpirationEnforced` is hardcoded by OpenCloud and fails on
every instance in existence, so it is recorded but deliberately kept out of
the alert, the `hardenings_missing` metric and the webhook. Waiving it would
be waiving nothing - see
[Measures that are not settings](../README.md#measures-that-are-not-settings).

## Only alerting on what changed

Twenty instances producing the same twenty findings every five minutes is how
a fleet trains its operators to stop reading the output. Give each host a
baseline and the check reports only regressions:

```shell
for config in /etc/check-opencloud-security/*.yml; do
  check-opencloud-security --config "$config" \
      --baseline /var/lib/check_opencloud/baseline.json \
      --warn-on-new
done
```

One file is enough for the whole fleet: it stores one entry per host, keyed by
the host as it was given on the command line. A comma-separated `--host` list
works the same way.

Two things to get right:

- The monitoring user must own the directory. The file is written atomically
  with owner-only permissions, and a baseline that cannot be written is
  reported as a line of output and nothing more - it never changes the verdict.
- Use the same spelling of the host everywhere. `opencloud.example.com` and
  `https://opencloud.example.com/` normalise to the same host, but
  `10.0.0.5` does not match the name that resolves to it, and the check would
  treat it as a host it has never seen.

A release past its end of life keeps alerting on every run regardless of the
baseline, which is the point: it receives no security fixes, so it gets worse
every day it stays up. See
[Reporting only what changed](../README.md#reporting-only-what-changed).

Add `--self-update-check` on one host in the fleet - not all of them - to be
told when a newer plugin version is published. It is cached for a day and
never changes the exit code.

## Scheduling the whole thing

- With Icinga2: one `Service` per host, applied from a host group - see
  [Icinga Director](icinga-director.md) or
  [Automated deployment with Ansible](ansible.md).
- Without it: a systemd timer or cron entry running the loop above, see
  [Scheduling](scheduling.md).
- On a cluster: a `CronJob`, see [Kubernetes](kubernetes.md).

Stagger the schedules. Twenty instances scanned at `0 6 * * *` means twenty
simultaneous scans from one address, and the update check will meet GitHub's
anonymous rate limit on the way.

---

[Back to the documentation index](README.md) | [Back to the main README](../README.md)
