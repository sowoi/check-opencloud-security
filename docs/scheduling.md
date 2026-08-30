# Scheduling without Icinga2 / Nagios
If you don't run Icinga2/Nagios, you can still schedule regular scans with
systemd timers or cron. Ready-to-adapt example files live in
[`contrib/`](../contrib/):

- [`contrib/systemd/check-opencloud-security.service`](../contrib/systemd/check-opencloud-security.service)
  and [`.timer`](../contrib/systemd/check-opencloud-security.timer)
- [`contrib/systemd/check-opencloud-security.env.example`](../contrib/systemd/check-opencloud-security.env.example)

The separate
[`check-opencloud-security-refresh.timer`](../contrib/systemd/check-opencloud-security-refresh.timer)
keeps the scanner's release schedule and advisory database current. Configure
the scanner to read the two files under `/var/lib/check-opencloud-security`
before enabling it; the refresh command validates both documents and writes
them atomically.
- [`contrib/cron/check-opencloud-security.cron`](../contrib/cron/check-opencloud-security.cron)

<!-- TOC -->
* [Scheduling without Icinga2 / Nagios](#scheduling-without-icinga2--nagios)
  * [systemd timer](#systemd-timer)
  * [cron](#cron)
<!-- TOC -->


## systemd timer
```shell
sudo mkdir -p /etc/check-opencloud-security
sudo cp contrib/systemd/check-opencloud-security.env.example /etc/check-opencloud-security/env
sudo $EDITOR /etc/check-opencloud-security/env   # set COS_HOST (and any other options)

sudo cp contrib/systemd/check-opencloud-security.service /etc/systemd/system/
sudo cp contrib/systemd/check-opencloud-security.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now check-opencloud-security.timer

# Run it once immediately to verify the setup:
sudo systemctl start check-opencloud-security.service
journalctl -u check-opencloud-security.service
```

## cron
```shell
sudo cp contrib/cron/check-opencloud-security.cron /etc/cron.d/check-opencloud-security
sudo chmod 644 /etc/cron.d/check-opencloud-security
sudo $EDITOR /etc/cron.d/check-opencloud-security   # set COS_HOST (and any other options)
```

Both examples configure the check entirely through
[environment variables](../README.md#environment-variables), so the same binary
or Docker image is reused unmodified across hosts - only the environment file
or cron entry changes.

Two things catch people out here, and both are covered in
[Troubleshooting](troubleshooting.md): cron and systemd have neither a login
shell's `PATH` nor its environment, so use the full path to
`check-opencloud-security` and set `COS_HOST` explicitly.

On a cluster, the equivalent is a `CronJob` - see [Kubernetes](kubernetes.md).
For more than a handful of instances, see
[Checking a fleet of instances](many-instances.md).

---

[Back to the documentation index](README.md) | [Back to the main README](../README.md)
