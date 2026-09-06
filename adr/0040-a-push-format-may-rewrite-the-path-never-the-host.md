# ADR 0040: A push format may rewrite the path, never the host

- Status: Accepted
- Date: 2026-09-05

## Context

[ADR 0025](0025-webhook-can-post-a-preformatted-chat-payload.md) established
that `--webhook-format` may render the payload in a receiver's own shape
before POSTing it, and implemented `slack` and `discord`. Both are ordinary
incoming webhooks: the operator configures a URL, a JSON body goes to exactly
that URL, and only the body differs between formats.

ntfy is not shaped like that. It publishes to a *topic*, and it reads a JSON
publication **only at the server root**, taking the topic from a field in the
document. Posting the same JSON to `https://ntfy.example.com/opencloud` does
not publish a structured notification there - ntfy treats the body as the
literal message text, so a subscriber receives a wall of JSON.

That leaves three ways to speak ntfy's contract, and every one of them breaks
something that currently holds:

1. Require the operator to configure the server root and name the topic in a
   new `--webhook-topic` flag. A flag that is meaningless for every other
   format, and a URL nobody has - the URL an ntfy user already possesses, and
   pastes, is the topic URL.
2. Send a plain-text body with the metadata in `Title:`/`Priority:` headers,
   which ntfy accepts at the topic URL. The sender posts pre-serialised JSON
   and signs those exact bytes; a second body type would fork the send path
   and the `--webhook-secret` contract with it.
3. Read the topic off the configured URL and post to that server's root.

Gotify, added in the same change, raises none of this: it takes a JSON body at
the URL the operator configures, with the application token in the URL or in
an `X-Gotify-Key` header. It needs no exception and gets none.

## Decision

**`ntfy` reads the topic from the configured URL's path and POSTs to the root
of that same server. No other format's URL is rewritten.**

The rewrite is bounded to the path, and that bound is the reason this is safe
rather than merely convenient. Scheme, host and port are carried over
untouched, so the URL that is posted to resolves to the same addresses as the
URL the operator configured - which means the SSRF guard, the DNS-rebinding
re-check before delivery, and the refusal to follow redirects are all
validating the address that is actually used. A rewrite that could reach a
different host would have to be validated separately, and would be a way for
a configuration mistake to become a request somewhere nobody chose.

**A URL naming no topic is refused when the check starts**, beside the other
argument validation, rather than at delivery time. A root URL names no
destination, so ntfy would answer 400 on every notification for the life of
that configuration - a silent channel is exactly the failure a monitoring
notification must not have, and it is knowable before the first scan runs.

The signature, when `--webhook-secret` is set, keeps covering whatever is
actually sent, as ADR 0025 requires - here that is the ntfy document including
the topic field.

## Consequences

An operator pastes the ntfy topic URL they already have and it works. The
plugin gains one special case in `_webhook_post_url`, which is one more than
it had; it is named, tested from both sides, and the test asserting that every
*other* format posts exactly where it was pointed is what stops the exception
spreading.

`--webhook-digest` renders for both push formats rather than falling back to
the flat document. The fallback is silent by construction - an unknown format
returns the generic payload - and for ntfy that document has no `topic`, so
the fallback would have produced a rejected notification rather than an
ugly one.

## Alternatives considered

**A `--webhook-topic` flag.** Honest, and wrong for the operator: it makes the
plugin ask for something in two pieces that ntfy's own documentation, and
every ntfy client, hands out as one URL. It also adds a flag that means
nothing for the four other formats.

**A plain-text body with ntfy's headers.** Works at the topic URL with no
rewrite at all, which is genuinely attractive. Rejected because the sender
serialises JSON once and signs those bytes deliberately, so that what a
receiver hashes is what was transmitted; a text body would mean a second send
path, and `--webhook-header` already lets anyone who wants this build it
outside the plugin.

**Leave ntfy to the wrapper script.** It was already documented in
`docs/webhook-recipes.md` and still is, for anyone wanting the plugin's full
output or their own priority scheme. But a `curl` wrapper is a second thing to
keep working next to every scheduled scan, which is the friction ADR 0025
exists to remove - and ntfy is, for self-hosted deployments, at least as
common a destination as Discord.

**Rewrite to a configured base URL rather than the same host.** Would let one
setting point the notification at an entirely different server. That is a
capability nobody asked for and a way for a typo to deliver an instance's
security posture somewhere unintended.
