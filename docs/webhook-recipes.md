# Webhook recipes

The [webhook](../README.md#webhook-notifications) posts the plugin's own JSON
document by default. That is deliberate: it carries the whole verdict, not a
rendered sentence. `--webhook-format` can render it as Slack or Discord's own
shape directly (see [below](#slack-mattermost-discord)); anything else still
wants the generic document, and needs a few lines of translation in between.

Two rules apply to every recipe here:

- **A failing webhook never changes the check result.** The plugin appends
  `Webhook delivery failed` and still exits with the state it measured, so a
  broken notification channel can neither hide nor fake a vulnerable instance.
- **Never put the URL on the command line.** It usually *is* the credential.
  Use `COS_WEBHOOK_URL`, or `secret://` in the configuration file - see
  [Configuration file and secrets](../README.md#configuration-file-and-secrets).

## The payload, in short

The fields most receivers care about, from the full example in
[Webhook notifications](../README.md#webhook-notifications):

| Field | Use it for |
|:------|:-----------|
| `status`, `exit_code` | `OK` / `WARNING` / `CRITICAL` / `UNKNOWN` and `0`-`3` |
| `message` | The one-line reason, already written for a human |
| `rating`, `rating_label` | The `0`-`5` score and its `A+`-`F` label |
| `host`, `product_version` | Which instance, and which release |
| `eol` | Whether that release still receives security fixes |
| `update.availableVersion` | What to upgrade to |
| `failed_extra_checks`, `missing_hardenings` | The findings themselves |

A scan that failed outright carries only `plugin`, `plugin_version`,
`timestamp`, `host`, `status`, `exit_code` and `message`. Any receiver that
reaches for `rating` must tolerate its absence.

## A generic receiver

Anything that accepts arbitrary JSON - a log pipeline, a webhook collector, an
n8n or Node-RED flow - takes the payload unchanged:

```shell
export COS_WEBHOOK_URL='https://collector.example.com/hooks/opencloud'
export COS_WEBHOOK_HEADERS='Authorization: Bearer abc123; X-Env: prod'
check-opencloud-security --host opencloud.example.com --webhook-on warning
```

`--webhook-on` decides how much you hear. Each level includes the more severe
ones: `critical`, `warning`, `unknown`, `always`.

## Uptime Kuma

Covered in full in [Uptime Kuma](../README.md#uptime-kuma), because its Push
monitor is the one receiver that takes the payload as-is *and* treats silence
as a failure - which makes a check that stopped running visible.

## Slack, Mattermost, Discord

These expect their own JSON. For the common case, `--webhook-format slack`
or `--webhook-format discord` posts it directly - no adapter needed:

```shell
check-opencloud-security --host opencloud.example.com \
  --webhook-url https://hooks.slack.com/services/... \
  --webhook-format slack
```

Mattermost accepts the `slack` format too, and so does the outbound webhook
connector in the common Matrix bridge, [matrix-hookshot](https://matrix-org.github.io/matrix-hookshot/) -
there is no separate `matrix` format because none of these has its own
distinct webhook contract worth targeting instead. Discord also accepts the
`slack` format at `<webhook-url>/slack`, if a plain attachment is preferred
over an embed.

The adapter below is for anything the built-in formats do not cover - a
custom color scheme, extra fields, or a receiver that is *almost* Slack- or
Discord-shaped but not quite:

```python
#!/usr/bin/env python3
"""Forward a check-opencloud-security notification to a Slack-style webhook."""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SLACK_URL = os.environ["SLACK_WEBHOOK_URL"]
COLOURS = {"OK": "#2eb886", "WARNING": "#daa038", "CRITICAL": "#a30200", "UNKNOWN": "#767676"}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        text = f"*{payload['host']}* - {payload['status']}\n{payload['message']}"
        if payload.get("rating_label"):
            text += f"\nRating {payload['rating_label']}, OpenCloud {payload.get('product_version', '?')}"

        body = json.dumps({
            "attachments": [{
                "color": COLOURS.get(payload["status"], "#767676"),
                "text": text,
            }]
        }).encode()
        request = urllib.request.Request(
            SLACK_URL, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=10):
            pass

        self.send_response(204)
        self.end_headers()


HTTPServer(("127.0.0.1", 8099), Handler).serve_forever()
```

Bind it to localhost and run it next to the check. An adapter that is
reachable from elsewhere is an open relay into your chat system.

Discord accepts a compatible payload at `<webhook-url>/slack`. Mattermost
accepts Slack's format directly.

## ntfy

ntfy takes a plain body plus headers, so `curl` in a wrapper is simpler than a
webhook receiver. This shape also works for any "notify me if it fails"
service:

```shell
#!/bin/sh
set -eu
output="$(check-opencloud-security --host opencloud.example.com --check-hardening)" || state=$?
state="${state:-0}"

case "$state" in
  0) exit 0 ;;                       # nothing to say
  1) priority=default ;;
  2) priority=urgent ;;
  *) priority=high ;;
esac

printf '%s' "$output" | curl -sS \
  -H "Title: OpenCloud security check" \
  -H "Priority: $priority" \
  -H "Tags: warning" \
  -d @- https://ntfy.example.com/opencloud
```

Note `|| state=$?` - the plugin's exit code *is* the result, and `set -e`
would otherwise abandon the script exactly when there is something to report.

## Alertmanager

Alertmanager's v2 API wants a list of alerts, and it wants them to stop
arriving before it resolves them:

```shell
check-opencloud-security --host opencloud.example.com --webhook-url \
  http://127.0.0.1:8098/  # an adapter that posts to /api/v2/alerts
```

```json
[{
  "labels": {
    "alertname": "OpenCloudSecurity",
    "instance": "opencloud.example.com",
    "severity": "critical"
  },
  "annotations": {"summary": "<message from the payload>"},
  "startsAt": "<timestamp from the payload>"
}]
```

Send an alert only for a state you want paged, and let it time out rather than
trying to resolve it by hand - the next scan is up to a day away, and an alert
resolved early is an alert that silently un-pages a still-vulnerable server.
If you already push metrics, [Prometheus and Grafana](prometheus.md) is the
better route to Alertmanager.

## Testing a receiver without an instance

`--webhook-on always` plus a host that does not exist produces a real
delivery of the failure-shaped payload, which is the case receivers usually
get wrong:

```shell
check-opencloud-security --host does-not-exist.example.com \
  --webhook-url http://127.0.0.1:8099/ --webhook-on always
```

For the healthy shape, point it at a real instance you own. `--debug` logs
that a webhook was posted and to where, but not the body - to see the body,
point the webhook at something that echoes it, such as
`python3 -m http.server` or a one-line receiver of your own.

---

[Back to the documentation index](README.md) | [Back to the main README](../README.md)
