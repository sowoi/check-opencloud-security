# ADR 0025: The webhook can post a pre-formatted chat payload

- Status: Accepted
- Date: 2026-08-29

## Context

`docs/webhook-recipes.md` states a deliberate decision: the webhook posts the
plugin's own flat JSON document, and a receiver that wants Slack or Discord's
own shape gets there through a small adapter, documented as a standalone
Python script bound to localhost. That stance exists so the webhook payload
stays one thing - "the whole verdict, not a rendered sentence" - rather than
the plugin growing a format per chat provider.

In practice, the adapter is the same handful of lines every time: read the
JSON, pick a color for the status, build one Slack attachment or one Discord
embed, forward it. Nothing about that translation needs the general-purpose
HTTP server the recipe wraps it in, and running one is a second process to
keep alive next to every scheduled scan - real friction for what is, for the
two most common destinations, a fixed transformation.

## Decision

`--webhook-format` (default `generic`, unchanged) accepts `slack` or
`discord` and renders the payload in that shape before it is POSTed, instead
of the flat document. The default stays the generic document - nothing
changes for an existing deployment - so this adds to the adapter-based
stance rather than reversing it: the adapter script remains the answer for
anything the two built-in shapes do not cover (a custom field, a receiver
that is close to but not exactly Slack- or Discord-shaped).

Only two formats are implemented, not four. Mattermost already accepts
Slack's shape directly (this was already documented), and the common Matrix
webhook bridge, matrix-hookshot, accepts it too through its outbound webhook
connector - Matrix has no standard incoming-webhook contract of its own to
target, so a dedicated `matrix` format would mean inventing a shape nobody
else's bridge actually expects. `slack` covers all three destinations.

When `--webhook-secret` is set, the HMAC-SHA256 signature is computed over
whichever body is actually sent - the chat-formatted one when a format is
selected, the generic one otherwise. Signing the document that was never
transmitted would make the header not verify against the equally real POST
body a receiver sees.

## Consequences

An operator who only wants Slack or Discord no longer needs to run the
adapter as a second process. The color scheme (`OK`/`WARNING`/`CRITICAL`/
`UNKNOWN` mapped to the same four hex values) matches the adapter script
exactly, so migrating off it changes nothing a reader of the notification
would notice.

The generic document remains the only one carrying every field (rating,
vulnerabilities, hardening findings, update info); the chat-native formats
are intentionally a rendered summary, the same trade-off the adapter always
made.

## Alternatives considered

**A `matrix` format posting to the Matrix Client-Server API directly.** That
API needs a room ID and an access token in the request path plus a
transaction ID, which is nothing like "POST a JSON body to a URL" - it is not
a webhook in the sense every other format here is, and building it would
mean the plugin managing Matrix credentials rather than posting to a URL an
operator already controls.

**Make `slack`/`discord` the new default.** Would break every existing
`--webhook-url` integration expecting the documented flat document -
unacceptable for an opt-in notification feature with no version negotiation.

**Extend the adapter script instead of adding a CLI flag.** Keeps the
plugin's dependency and surface area exactly as small as before, but leaves
every operator running a second long-lived process for a fixed, one-shot
transformation - the friction this decision exists to remove.
