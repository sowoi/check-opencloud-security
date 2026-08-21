# ADR 0015: The MCP endpoint may require a sign-in, and this service is only ever a resource server

- Status: Accepted
- Date: 2026-08-21

## Context

The scan service answers anybody. That is deliberate and it is the reason the
public deployment exists: somebody responsible for an OpenCloud instance can
paste an address and get an answer with no account, no key and no record of
them anywhere. Nothing on this page is meant to change that.

But the same code is run privately. An estate hosting this for itself gets an
MCP endpoint that executes the same workflows a browser gets, reachable by
anything that can open a socket to it, and for some of those deployments
"anything" is the wrong answer. The requests that have come in are consistent:
not a login for the website, not a paywall, not an API key this project would
have to issue - a way to put the organisation's existing identity provider in
front of `/mcp`.

Doing that wrongly has three recognisable shapes. A service that issues its
own tokens becomes an identity store, with a user table, a password reset and
a breach worth having. A sign-in that also raises a limit turns authentication
into the way around the rate limit rather than a guard in front of it. And a
sign-in that fails open - a missing issuer, an unverifiable key, a token
nobody checked the audience of - leaves an operator believing the endpoint is
protected while it is not, which is worse than never having offered it.

## Decision

**The endpoint is open unless an operator says otherwise.** `false` is the
default of `COS_WEB_MCP_AUTH_ENABLED`, the hosted deployment does not set it,
and a deployment that never reads this page is unaffected.

**When it is on, this service is an OAuth 2.0 resource server and nothing
else.** It has no login page, no session, no user record, no client secret and
no way to issue a token. `webapp/mcp_auth.py` verifies a bearer token offline
against the provider's published JWKS - signature, issuer, audience, expiry
and any required scopes - and asymmetric algorithms only, which rules out both
`HS256` and `none`. Nothing is stored and no request is made per token.

**Authentication decides who may ask, never how hard.** The client rate limit,
the per-target cooldown, the SSRF guard, the queue and the concurrent-wait
ceiling are identical for an authenticated agent. This is the same rule that
already says a request may choose *what* to scan and never *how hard*.

**A deployment that cannot enforce the sign-in it asked for refuses to
start**, exactly as one asked to encrypt without a usable key does
([ADR 0008](0008-refuse-to-start-without-the-encryption-key.md)): no issuer,
no resource URL to check an audience against, or a resource URL that is
neither HTTPS nor loopback. Asking for authentication with the endpoint
switched off is *not* an error - turning it off is a good way to protect it,
and making the safest configuration the one that fails to boot would teach
operators to switch the guard off instead.

**The state is public, and so is the way in.** The RFC 9728 metadata at
`/.well-known/oauth-protected-resource/mcp` names the authorisation server,
the `401` names that document, and `/.well-known/ai.json` says the same before
an agent connects - consistent with
[ADR 0010](0010-machine-readable-descriptions-are-always-public.md). Knowing
where to ask for a token has never been the secret part, and an agent that
cannot discover it is an agent that retries.

**The operator's purge credential moves out of the way.** With the endpoint
open it travels in `Authorization`; with a sign-in configured that header
belongs to the identity provider and the credential is read from
`X-Purge-Authorization` instead, with no fallback. Reading an agent's identity
token as if it were an operator credential is a confusion worth refusing
outright rather than resolving by precedence.

**Authentik ships as a whole stack, not as a dependency.** A compose file of
its own rather than an overlay or a profile, because Compose validates a
required variable in every file it reads and a profile would break
`docker compose up` for everybody who never wanted it. In that stack the
sign-in follows the endpoint - `COS_WEB_MCP_AUTH_ENABLED` is
`${COS_WEB_ENABLE_MCP:-true}` - so an operator who brings up Authentik cannot
end up with `/mcp` open, and a blueprint provisions the provider so that the
client ID both sides agree on is never copied by hand. Any provider publishing
signed JWTs and a JWKS works; nothing in the code knows the name Authentik.

## Consequences

- An estate can put its own identity provider in front of the agent endpoint
  without this project learning anything about identity.
- A provider that signs symmetrically, or one that publishes no JWKS, is not
  supported. That is a real limitation and a deliberate one: verifying such a
  token would mean holding the client secret.
- The 401/`WWW-Authenticate`/metadata chain has to keep working, because a
  client that implements the MCP authorization specification recovers through
  it and has no other way in.
- A second header now carries the purge credential, and which one is correct
  depends on a setting. It is documented in three places for that reason.
- The default path gains a code branch that is off, and the tests have to keep
  proving both sides of it - that the endpoint is open when nothing was asked
  for, and that it is genuinely shut when something was.
