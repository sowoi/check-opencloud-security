# Embedding OpenCloud in an iframe: what this scanner checks, and why

OpenCloud's web client can be embedded in another site's page inside an
`iframe` - a file picker or a preview panel dropped into a third-party
application, for instance. That integration works by `postMessage`: the
embedding page and the framed OpenCloud client exchange messages across the
frame boundary, and optionally the parent can hand over an authenticated
session to the frame. Both checks read the public `/config.json` the web
client serves and ask the same question: **which origins is the embedded
client willing to trust?**

If `/config.json` cannot be read, or does not publish an `embed` block at
all, both checks pass - embedding is simply not configured, so there is
nothing for either origin restriction to fail.

<!-- TOC -->
* [Embedding OpenCloud in an iframe: what this scanner checks, and why](#embedding-opencloud-in-an-iframe-what-this-scanner-checks-and-why)
  * [1. Does the embed accept messages from any origin: `webEmbedMessageOriginRestricted`](#1-does-the-embed-accept-messages-from-any-origin-webembedmessageoriginrestricted)
  * [2. Does delegated authentication accept an unvalidated origin: `webEmbedDelegatedAuthenticationRestricted`](#2-does-delegated-authentication-accept-an-unvalidated-origin-webembeddelegatedauthenticationrestricted)
  * [Severity and rating impact](#severity-and-rating-impact)
<!-- TOC -->


## 1. Does the embed accept messages from any origin: `webEmbedMessageOriginRestricted`

`options.embed.messagesOrigin` in the public web configuration is read.
`WEB_OPTION_EMBED_MESSAGES_ORIGIN=*` means the embedded client will exchange
`postMessage` traffic with **any** page that frames it, not only the
integration it was set up for. Any site on the internet can then load
OpenCloud's web client in a hidden or disguised frame and start sending it
messages the client will treat as coming from a trusted parent.

**Fix:** set `WEB_OPTION_EMBED_MESSAGES_ORIGIN` to the exact origin of the
page that is allowed to embed the client (scheme, host and port - not a
wildcard or a path), or unset embedding entirely if nothing actually uses
it.

## 2. Does delegated authentication accept an unvalidated origin: `webEmbedDelegatedAuthenticationRestricted`

Delegated authentication lets the parent page hand its own session to the
embedded frame, so the visitor does not have to sign in twice. This check
fails only when **both** conditions hold: `delegateAuthentication` is `true`
*and* `delegateAuthenticationOrigin` is empty - meaning the client accepts a
delegated session from a parent frame without checking who that parent
actually is. Whoever can frame the page can hand it a session, which makes
this the more serious of the two checks: it is authentication bypass, not
message-passing overreach, which is why it is rated `critical` against the
`high` above.

**Fix:** set `WEB_OPTION_EMBED_DELEGATE_AUTHENTICATION_ORIGIN` to the exact
trusted parent origin, or disable delegated authentication outright if the
embedding integration does not need it. Delegated authentication with an
origin set is not itself a finding - only the combination of it being on and
unrestricted is.

## Severity and rating impact

Both are `extraChecks`, reported and rating-capped whenever `/config.json`
publishes an `embed` block - `webEmbedMessageOriginRestricted` at `high`
(caps the rating at `C`), `webEmbedDelegatedAuthenticationRestricted` at
`critical` (caps it at `D`) - see the extra-checks table in [the main
README](scanner-checks.md#what-the-scanner-checks). Neither requires
`--check-hardening`.
