# Authentik in front of the MCP endpoint

The scan service answers anybody, and for the public deployment that is the
whole point of it. An estate running the service for itself usually wants the
opposite for the agent endpoint: `/mcp` executes the same workflows a browser
gets, and there are deployments where "the same workflows a browser gets"
should still mean "and only our agents". This page is that deployment, whole:
one compose file that brings up the scan service *and*
[Authentik](https://goauthentik.io), with `/mcp` requiring a token from the
first minute.

Two things it is *not*. It is not a login for the website - the pages and the
HTTP API are unchanged, and adding one is not what this is for. And it is not
a way to buy more scanning: **authentication decides who may ask, never how
hard**. An authenticated agent meets exactly the same client rate limit, the
same per-target cooldown, the same SSRF guard and the same queue as a stranger
with a browser. A sign-in that raised a limit would have turned itself into a
way around it.

<!-- TOC -->
* [Authentik in front of the MCP endpoint](#authentik-in-front-of-the-mcp-endpoint)
  * [How it works](#how-it-works)
  * [Running the stack](#running-the-stack)
  * [Sending mail](#sending-mail)
  * [What the blueprint created](#what-the-blueprint-created)
  * [Pointing the scanner at it](#pointing-the-scanner-at-it)
  * [Adding somebody who may use the endpoint](#adding-somebody-who-may-use-the-endpoint)
    * [A group, and the binding that makes it mean something](#a-group-and-the-binding-that-makes-it-mean-something)
    * [The person](#the-person)
    * [The agent that is nobody](#the-agent-that-is-nobody)
  * [Getting a token](#getting-a-token)
    * [As a service account](#as-a-service-account)
    * [Without naming an account at all](#without-naming-an-account-at-all)
    * [As a person](#as-a-person)
    * [Reading the token you got](#reading-the-token-you-got)
  * [Configuring an agent](#configuring-an-agent)
  * [Erasure, which is a different credential](#erasure-which-is-a-different-credential)
  * [Behind a reverse proxy](#behind-a-reverse-proxy)
  * [Backing it up](#backing-it-up)
  * [Restoring it](#restoring-it)
  * [When it does not work](#when-it-does-not-work)
  * [Using a provider that is not Authentik](#using-a-provider-that-is-not-authentik)
<!-- TOC -->

## How it works

This service is an OAuth 2.0 **resource server** and nothing more. It has no
login page, no session, no user table, no client secret and no way to issue a
token. What it does is check one:

1. An agent presents `Authorization: Bearer <token>` on its MCP requests.
2. The service fetches the provider's published signing keys - the JWKS - and
   verifies the token's signature against them.
3. It checks the issuer, the audience, the expiry, and any scopes the
   deployment requires.
4. Anything that fails any of those is not a token, and the request gets a
   **401** naming where to go for a real one.

Nothing is stored, nothing is logged, and no request is made to the provider
per token: the keys are cached, and verification is offline. A rotated signing
key is picked up without a restart.

An agent that arrives without a token gets the RFC 9728 treatment: a `401`
whose `WWW-Authenticate` header names
`/.well-known/oauth-protected-resource/mcp`, a public document naming the
authorisation server. `/.well-known/ai.json` says the same thing before the
first request, so a well-behaved agent knows it needs a token without
spending a round trip finding out.

## Running the stack

`docker/docker-compose.authentik.yml` is not an overlay on the ordinary stack;
it is the whole deployment in one file. Six services - the web application,
the worker, Redis, Authentik, its own PostgreSQL, and Authentik's worker - and
one command:

```bash
cd docker
./authentik-env.sh                                  # writes .env, once
docker compose -f docker-compose.authentik.yml up -d
```

Then open **<http://127.0.0.1:9000/if/flow/initial-setup/>** - the trailing
slash is required, without it you get a 404 - and set the password for the
`akadmin` account. That flow is offered once.

That is the whole setup. There is no provider to create, no client ID to copy
between two windows, and nothing to switch on afterwards: **the sign-in
follows the endpoint.** `COS_WEB_MCP_AUTH_ENABLED` in that file is
`${COS_WEB_ENABLE_MCP:-true}`, so bringing up this stack means `/mcp` requires
a token, and turning the endpoint off turns the sign-in off with it. There is
no combination of these two variables that leaves the endpoint open by
accident.

`authentik-env.sh` writes six secrets into `docker/.env` and never overwrites
one it finds, so running it twice is safe:

| Variable | What it is |
|:---------|:-----------|
| `COS_REDIS_PASSWORD` | The password Redis requires. It holds every live scan and every result still inside its TTL - see [Redis](redis.md) |
| `AUTHENTIK_SECRET_KEY` | Signs everything in Authentik's database |
| `AUTHENTIK_PG_PASS` | The password for Authentik's PostgreSQL |
| `AUTHENTIK_CLIENT_ID` | The OAuth client ID, and therefore the audience |
| `AUTHENTIK_CLIENT_SECRET` | The OAuth client secret |
| `COS_WEB_PURGE_TOKEN` | The operator credential for erasure, which is a different thing entirely |

Keep them somewhere you will still have them after the disk does not.
`AUTHENTIK_SECRET_KEY` signs everything in the database, so a database
restored next to a different key is an unusable database.

Reachable from somewhere other than your laptop? Two variables, and nothing
else changes:

```bash
AUTHENTIK_URL=https://sso.example.com \
COS_WEB_PUBLIC_BASE_URL=https://scanner.example.com \
  docker compose -f docker-compose.authentik.yml up -d
```

It is a separate file rather than a Compose profile because those secrets are
declared *required*, and Compose validates a required variable in **every file
it reads**, whether or not the service using it was selected. As a profile it
would break `docker compose up` for everybody who never wanted Authentik.

Notes on the stack, and where it differs from the upstream one:

- **Authentik needs no Redis.** It has kept sessions, caching and its task
  queue in PostgreSQL since 2025.10. The scanner's own Redis is a cache with
  no persistence and an eviction policy, and would be the wrong thing to point
  it at even if it did.
- **PostgreSQL is `postgres:18.6-alpine`**, pinned rather than floating, and
  separate from anything else you run. Authentik itself has **no Alpine
  image** - `ghcr.io/goauthentik/server` is published Debian-based only, and
  there is no variant to switch to.
- **The worker does not get the Docker socket.** Upstream mounts it so the
  worker can manage outpost containers; this stack runs no outposts, and
  handing a container the daemon socket is handing it the host.
- **State lives in named volumes** - `authentik_database`, `authentik_media`,
  `authentik_templates`, `authentik_certs` - rather than in bind mounts under
  `docker/`.
- **Do not mount `/etc/localtime` or `/etc/timezone`** into these containers.
  Authentik needs UTC internally, and mounting a timezone breaks OAuth.

## Sending mail

Authentik starts with exactly one account, and the way back into it is an
email. Until a mail server is configured it uses local delivery, which means
the message goes into the container and stays there: a forgotten `akadmin`
password is then a database edit rather than a link in an inbox. Configure it
before there is anything in Authentik worth keeping.

Every setting is a variable in `docker/.env`, and both Authentik services read
them - the server sends the test message, the worker sends everything else, so
configuring one and not the other works until the day it matters:

| Variable | Default | What it is |
|:---------|:--------|:-----------|
| `AUTHENTIK_EMAIL_HOST` | *(empty)* | The mail server. Empty leaves local delivery in place |
| `AUTHENTIK_EMAIL_PORT` | `587` | `587` for STARTTLS, `465` for implicit TLS, `25` for neither |
| `AUTHENTIK_EMAIL_USERNAME` | *(empty)* | The account it authenticates as, if it authenticates |
| `AUTHENTIK_EMAIL_PASSWORD` | *(empty)* | That account's password |
| `AUTHENTIK_EMAIL_USE_TLS` | `true` | STARTTLS on a plain connection |
| `AUTHENTIK_EMAIL_USE_SSL` | `false` | TLS from the first byte |
| `AUTHENTIK_EMAIL_TIMEOUT` | `10` | Seconds before it gives up |
| `AUTHENTIK_EMAIL_FROM` | `authentik@localhost` | The `From:` address recipients see |

**`USE_TLS` and `USE_SSL` are not two names for the same thing, and never both
`true`.** STARTTLS begins in the clear on 587 and upgrades; implicit TLS is
encrypted from the first byte on 465. Setting both leaves a session that
negotiates neither.

```bash
cat >> docker/.env <<'EOF'
AUTHENTIK_EMAIL_HOST=smtp.example.com
AUTHENTIK_EMAIL_PORT=587
AUTHENTIK_EMAIL_USERNAME=authentik@example.com
AUTHENTIK_EMAIL_PASSWORD=the-password
AUTHENTIK_EMAIL_USE_TLS=true
AUTHENTIK_EMAIL_USE_SSL=false
AUTHENTIK_EMAIL_FROM=authentik@example.com
EOF
docker compose -f docker-compose.authentik.yml up -d
```

`authentik-env.sh` writes these names into `docker/.env` commented out, so the
list is in front of you when you go looking, and it never uncomments or
overwrites what you put there. Check it worked from
**System → Settings → Email** in the Authentik interface, which sends a test
message through the server container, and read the worker's log for the rest:

```bash
docker compose -f docker-compose.authentik.yml logs -f authentik_worker
```

`docker/setup-wizard.py` asks all of this when it generates a stack of its
own, and takes the password from `AUTHENTIK_EMAIL_PASSWORD` in the environment
rather than from a flag - a password on a command line is a password in `ps`
and in the shell history.

## What the blueprint created

`authentik/blueprints/opencloud-scanner.yaml` is mounted into both Authentik
containers at `/blueprints/custom`, and the worker applies it on start. That
is what makes the setup above one command rather than a page of clicking: the
OAuth2 provider, its signing key, its scopes and the application whose slug
becomes the issuer all exist before you first log in.

It provisions **once**. Every entry is `state: created`, which means Authentik
creates what is missing and then leaves it alone - change a redirect URI, a
flow or a scope in the admin interface afterwards and it stays changed. The
blueprint will not put it back on the next start.

What it makes, under **Applications → Applications**:

| | Value |
|:--|:-----|
| **Application** | `OpenCloud security scanner`, slug `opencloud-scanner` |
| **Provider** | `check-opencloud-security`, OAuth2/OpenID Connect, confidential |
| **Client ID / secret** | `AUTHENTIK_CLIENT_ID` and `AUTHENTIK_CLIENT_SECRET` from `.env` |
| **Grant types** | `authorization_code`, `refresh_token`, `client_credentials` |
| **Signing key** | `authentik Self-signed Certificate` |
| **Scopes** | `openid`, `profile`, `email`, `offline_access` |
| **Issuer mode** | per-provider |

Two of those rows are worth dwelling on.

**The signing key is the setting that matters most on this page.** With one,
tokens are signed asymmetrically and verified against the published JWKS.
*Without* one, Authentik signs with the client secret (HS256), and no resource
server can verify such a token without being handed that secret - which this
service will not accept. The blueprint sets it; if you ever recreate the
provider by hand, set it too.

**The client ID is the audience.** It lives in `.env`, which is where the web
application reads it from as `COS_WEB_MCP_AUTH_AUDIENCE` - the two sides agree
because they read the same line, not because you copied one into the other.

Per-provider issuer mode gives:

| | Value |
|:--|:-----|
| **Issuer** | `https://sso.example.com/application/o/opencloud-scanner/` |
| **Discovery document** | `https://sso.example.com/application/o/opencloud-scanner/.well-known/openid-configuration` |
| **JWKS** | `https://sso.example.com/application/o/opencloud-scanner/jwks/` |
| **Token endpoint** | `https://sso.example.com/application/o/token/` |

The token endpoint is deliberately not per-application: Authentik routes it by
`client_id`. The discovery and JWKS endpoints are per-slug, and there is no
root-level discovery document.

Read the issuer out of the discovery document rather than typing it. It is
what the tokens will actually carry, and it is the value the scanner compares
against.

A blueprint that fails does **not** stop Authentik from starting - it records
the error against the blueprint instance instead. If `/mcp` refuses every
token on a fresh stack, look under **Customisation → Blueprints** before
looking anywhere else.

To do it by hand instead - against an Authentik you already run, say - the
wizard under **Applications → Applications → Create with wizard** asks for the
same things in the same order, and the table above is the answer sheet.

## Pointing the scanner at it

The stack above does this for you - the values below are already in
`docker-compose.authentik.yml`, read from `.env`. This section is for pointing
the service at an Authentik, or any other provider, that you already run. On
`web_app`, in `docker/docker-compose.yml` or in `docker/.env`:

```yaml
COS_WEB_PUBLIC_BASE_URL: "https://scanner.example.com"
COS_WEB_MCP_AUTH_ENABLED: "true"
COS_WEB_MCP_AUTH_ISSUER: "https://sso.example.com/application/o/opencloud-scanner/"
COS_WEB_MCP_AUTH_AUDIENCE: "<the provider's client ID>"
```

| Setting | Meaning |
|:--------|:--------|
| `COS_WEB_MCP_AUTH_ENABLED` | Whether `/mcp` requires a token. Off by default |
| `COS_WEB_MCP_AUTH_ISSUER` | The issuer, exactly as the discovery document spells it. A trailing slash is accepted either way |
| `COS_WEB_MCP_AUTH_AUDIENCE` | What a token's `aud` must contain. In Authentik that is the client ID. **Required** whenever the sign-in is on |
| `COS_WEB_MCP_AUTH_JWKS_URL` | Only when the keys are not at `<issuer>/jwks/` |
| `COS_WEB_MCP_AUTH_RESOURCE_URL` | Only when `/mcp` is not at `<public base URL>/mcp` |
| `COS_WEB_MCP_AUTH_SCOPES` | Scopes a token must carry, separated by `;`. Empty means any valid token from that issuer is enough |

Four misconfigurations **refuse to start** rather than serve `/mcp` open,
because an operator who believes the endpoint is protected while it is not is
the worst outcome available here:

- authentication on with no issuer - there would be nothing to check against;
- authentication on with no public base URL and no resource URL - the 401
  names that URL and the RFC 9728 metadata is published beneath it, so
  guessing it would send every client somewhere else;
- a resource URL that is neither HTTPS nor loopback - a bearer token on an
  unencrypted hop is a credential in the clear;
- authentication on with no audience - see below.

Asking for authentication while `COS_WEB_ENABLE_MCP` is `false` is *not* an
error. Turning the endpoint off is a perfectly good way to protect it, and
making the safest configuration the one that fails to boot would only teach
people to switch the guard off instead.

**The audience is required.** An Authentik that serves more than this
application mints tokens for all of them, with the same issuer and the same
signing key, so an `aud` that is never compared makes every one of those
tokens a key to `/mcp` - including one minted for an application anybody in
the directory may use. Leaving `COS_WEB_MCP_AUTH_AUDIENCE` empty therefore
stops the service rather than quietly widening it, and a token that carries
no `aud` at all is refused for the same reason. The stack in
`docker/docker-compose.authentik.yml` sets it from `AUTHENTIK_CLIENT_ID` and
will not start without it.

## Adding somebody who may use the endpoint

**Read this before the stack is reachable by anybody else.** The blueprint
provisions a provider and an application, and an application with no bindings
is one **every** account in this Authentik can use. On a stack that exists to
guard `/mcp` that is usually fine on the first day, when the only account is
the `akadmin` you created at first start, and rarely fine on the second.

Nothing about *who* a caller is reaches the scan service. It checks a
signature, an issuer, an audience, an expiry and the scopes it was told to
require - it never looks at the subject, the username or a group claim, and it
has no user table to look them up in. Who may hold a token is therefore
entirely Authentik's decision, made in the two steps below, and it is the only
place that decision exists.

### A group, and the binding that makes it mean something

Do this once, before the first user. A binding on a group is one thing to
review later; a binding per person is a list nobody prunes.

1. **Directory → Groups → Create**. Name it `opencloud-scanner`. Leave
   *Superuser privileges* off - this group is about one application, and an
   Authentik superuser is an Authentik administrator.
2. **Applications → Applications → OpenCloud security scanner**, the
   **Policy / Group / User Bindings** tab, **Bind existing Group/User**.
3. Choose the group, leave the policy engine mode at **any**, and create it.

From that moment the application is closed to everybody who is not in the
group, and a token request from anybody else fails at Authentik rather than at
`/mcp`. The failure is logged under **Events → Logs** as a denied
authorization, which is the page to check when somebody swears their password
is right.

Test the negative case rather than assuming it: an account outside the group
must *not* be able to get a token. An application that looks bound but is not
is the one failure mode worth spending two minutes on.

### The person

**Directory → Users → New User → Internal User.** Username and email are the
two fields that matter; the email is what a password recovery goes to, so an
account without one can only be recovered by an administrator.

Then, on the user's page:

- **Set password**, or **Email recovery link** if you configured
  [mail](#sending-mail) - the second is the better habit, because it means the
  password was never in your clipboard, your terminal or the chat message you
  sent it in. **Create recovery link** produces the same link to hand over by
  some other route when there is no mail server.
- **Groups → Add to existing group** → `opencloud-scanner`.

That is the whole of it for somebody who signs in through a browser: their MCP
client takes them through Authentik, they log in, and the client gets a token.
Nothing has to be copied, and there is no per-user configuration on the
scanner side at all.

**Multi-factor authentication is worth the two minutes here.** The endpoint
executes scans against systems the person is responsible for, and a password
alone is a password alone. The user enrols an authenticator from their own
settings page at `/if/user/#/settings`; requiring it for everybody is a
matter of adding an authenticator validation stage to the authentication
flow, which is Authentik's business rather than this project's.

### The agent that is nobody

A cron job, a CI pipeline or an assistant running on a server has no browser
to be taken through, and should not be holding a person's password. It gets a
**service account**: an account with credentials and no login.

**Directory → Users → New User → Service Account.** The confirmation screen
shows the username and an **app password**, once - that string is the
credential, and there is no second chance to read it. Add the account to
`opencloud-scanner` the same way as a person, because a binding does not care
which kind of account it is; *Create group* on the form does the equivalent
the other way round if you would rather bind one account on its own.

Two details worth writing down at the time rather than discovering later. The
app password **expires after 360 days** unless you clear *Expiring*, so an
agent that has worked all year is an agent that stops for no visible reason -
issue a new one from **Directory → Tokens and App passwords** before then. And
a service account cannot use the admin or user interface at all, which is the
point of it: it has credentials and no login.

Give one to each caller rather than sharing one. They cost nothing, and the
difference shows the day you need to revoke exactly one of them without
telephoning everybody else.

## Getting a token

Which credential a caller uses depends on what it is, and all three end at the
same token endpoint:

| The caller | What it presents | Where the credential comes from |
|:-----------|:-----------------|:--------------------------------|
| A person at a keyboard | The authorization code flow, in a browser | Their own password, and their second factor |
| An agent acting for a person | That person's username and an app password | **Directory → Tokens and App passwords** |
| An agent acting for nobody | A service account's username and app password | Shown once when the service account was created |

**Authentik does not do machine-to-machine with a client ID and a client
secret**, whatever the grant type is called. Identification is by *username*,
authentication is by an *app password*, and the client secret is only how the
request proves which provider it is asking. This trips up everybody who has
used another provider first.

### As a service account

The ordinary case for an agent, and the one to reach for:

```bash
curl -s https://sso.example.com/application/o/token/ \
  -d grant_type=client_credentials \
  -d client_id="$AUTHENTIK_CLIENT_ID" \
  -d client_secret="$AUTHENTIK_CLIENT_SECRET" \
  -d username="scanner-agent" \
  -d password="$APP_PASSWORD" \
  -d scope="openid" | jq -r .access_token
```

`username` is the service account, `password` is its app password, and
`client_id` and `client_secret` are the provider's, straight out of
`docker/.env`. Ask for the scopes the deployment requires - `openid` alone is
enough while `COS_WEB_MCP_AUTH_SCOPES` is empty, which is the default.

For a client that can only be given one secret, the same thing with the
username folded in:

```bash
curl -s https://sso.example.com/application/o/token/ \
  -d grant_type=client_credentials \
  -d client_id="$AUTHENTIK_CLIENT_ID" \
  -d client_secret="$(printf '%s:%s' scanner-agent "$APP_PASSWORD" | base64 -w0)" \
  -d scope="openid" | jq -r .access_token
```

### Without naming an account at all

Leave the username out and send only the provider's client ID and secret, and
Authentik issues the token against a service account it creates for the
purpose, named `ak-check-opencloud-security-client_credentials`:

```bash
curl -s https://sso.example.com/application/o/token/ \
  -d grant_type=client_credentials \
  -d client_id="$AUTHENTIK_CLIENT_ID" \
  -d client_secret="$AUTHENTIK_CLIENT_SECRET" \
  -d scope="openid" | jq -r .access_token
```

It is the shortest path to a working token and the right one for trying the
endpoint out. It is a poor one to leave in place: every caller using it is the
same account, so revoking one revokes all of them, and the credential it turns
on is the provider secret the scan service also reads. Once the binding above
exists, remember to add that generated account to the group as well, or this
stops working - which is the correct outcome, and the moment to switch to a
service account of your own.

### As a person

An MCP client that implements the OAuth flow needs nothing but the URL: it
meets the `401`, reads `/.well-known/oauth-protected-resource/mcp`, finds
Authentik, opens a browser and comes back with a token. The blueprint already
allows the loopback redirect such a client uses -
`http://127.0.0.1:<port>/...`, on 127.0.0.1 only - and the authorization flow
is the implicit-consent one, so there is no consent screen between logging in
and being connected.

If a client asks to be registered instead, register it by hand under
**Applications → Providers**: Authentik supports dynamic client registration,
but it is off by default and gated behind a registration token.

### Reading the token you got

Before wondering why `/mcp` refuses one, look at what is in it:

```bash
python -c 'import base64,json,sys;p=sys.argv[1].split(".")[1];print(json.dumps(json.loads(base64.urlsafe_b64decode(p+"="*(-len(p)%4))),indent=2))' "$TOKEN"
```

| Claim | What it must be |
|:------|:----------------|
| `iss` | `COS_WEB_MCP_AUTH_ISSUER`, give or take the trailing slash |
| `aud` | Contains `COS_WEB_MCP_AUTH_AUDIENCE`, which is the client ID |
| `exp` | In the future - Authentik's default access token lifetime is minutes, not days |
| `scope` | Contains everything in `COS_WEB_MCP_AUTH_SCOPES`, if anything is set |
| `sub` | Whatever Authentik decided. **The scan service does not read it** |

Then use it, which is the only step that involves this service at all:

```bash
curl -s https://scanner.example.com/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

A list of tools means the whole chain works. A `401` means the token was not
accepted, and the header on that response names the document that says why it
would be. A token, once minted, is good until it expires: mint one per run
rather than one per request.

Authentik always issues JWT access tokens, whichever way you asked for one, so
there is never an opaque string to introspect and the scan service never has
to ask Authentik anything.

## Configuring an agent

Most MCP clients accept a static header, which is the simplest thing that
works:

```json
{
  "servers": {
    "opencloud-scan": {
      "type": "http",
      "url": "https://scanner.example.com/mcp",
      "headers": { "Authorization": "Bearer ${input:token}" }
    }
  }
}
```

A client that implements the MCP authorization specification needs no
configuration beyond the URL: it will meet the 401, read
`/.well-known/oauth-protected-resource/mcp`, find Authentik and take the user
through the flow. Authentik does support dynamic client registration, but it
is disabled by default and gated behind a registration token, so registering
the client by hand in the admin interface is the path that always works.

See [the MCP guide](mcp.md) for the per-client configuration files; the only
addition here is the header.

## Erasure, which is a different credential

`erase_instance_data` needs the operator's purge credential -
`COS_WEB_PURGE_TOKEN` - and that has never been the same thing as an identity.
With the endpoint open it travels in `Authorization`, because nothing else is
using that header.

**With a sign-in configured, `Authorization` belongs to the identity provider,
and the purge credential moves to `X-Purge-Authorization`.** The fallback is
deliberately not kept: reading an agent's identity token as if it were an
operator credential is exactly the confusion worth refusing.

```json
"headers": {
  "Authorization": "Bearer ${input:token}",
  "X-Purge-Authorization": "Bearer ${input:purge_token}"
}
```

Neither ever reaches the model: the tool takes them from the request headers,
never as an argument.

## Behind a reverse proxy

Two hosts, two requirements.

**Authentik builds the issuer out of the `Host` header it is handed.** A proxy
that rewrites it gives every token an `iss` nobody will accept, and the
symptom is confusing because everything else works. Pass `Host` and
`X-Forwarded-Proto` through unchanged, and add the proxy's egress address to
`AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS` if it is outside the private ranges.
Authentik cannot run under a subpath; give it a hostname.

**The scanner needs to know its own address**, because that is what a token's
audience is checked against and what the metadata document publishes. Set
`COS_WEB_PUBLIC_BASE_URL`. [The reverse proxy guide](reverse-proxy.md) has
worked configuration for both.

## Backing it up

**Authentik has no built-in backup.** The one it used to have was removed
years ago, so this is yours to run. Four things matter, and the first two are
the ones that make a restore possible at all:

| What | Where | Why |
|:-----|:------|:----|
| `AUTHENTIK_SECRET_KEY` | `docker/.env` | Signs everything in the database. A different key makes a restored database unusable |
| PostgreSQL | the `authentik_database` volume | Users, groups, flows, policies, providers, tokens, certificates. Losing it is losing everything |
| Media | the `authentik_media` volume | Uploaded icons and backgrounds |
| Certificates and templates | `authentik_certs`, `authentik_templates` | Only if you put something there that is not in the database |

```bash
cd docker
stack="-f docker-compose.authentik.yml"
stamp=$(date +%F)

# The database, as SQL, with the drop-and-create statements a clean restore
# needs.
docker compose $stack exec -T authentik_postgresql \
  pg_dump -U authentik -d authentik --clean --create \
  > "authentik-db-$stamp.sql"

# The volumes that are not the database.
for volume in media templates certs; do
  docker run --rm \
    -v "$(basename "$PWD")_authentik_$volume:/from:ro" \
    -v "$PWD:/to" alpine \
    tar czf "/to/authentik-$volume-$stamp.tar.gz" -C /from .
done

# And the secrets, without which none of the above is worth anything.
cp .env "authentik-env-$stamp.backup"
```

The volume names are prefixed with the Compose project name, which is the
directory name unless you set `COMPOSE_PROJECT_NAME`. `docker volume ls` will
tell you what they actually came out as.

Treat the result as a credential store, because it is one: the dump contains
every token and every signing key Authentik holds, and `.env` contains the key
that makes them usable. Encrypt it, keep it off the machine that made it, and
test the restore - an untested backup is a belief, not a backup.

## Restoring it

```bash
cd docker
stack="-f docker-compose.authentik.yml"

# The secret key first, and it must be the one that was in use when the dump
# was taken.
cp authentik-env-2026-08-21.backup .env

docker compose $stack down
docker compose $stack up -d authentik_postgresql

docker compose $stack exec -T authentik_postgresql \
  psql -U authentik -d postgres < authentik-db-2026-08-21.sql

for volume in media templates certs; do
  docker run --rm \
    -v "$(basename "$PWD")_authentik_$volume:/to" \
    -v "$PWD:/from:ro" alpine \
    tar xzf "/from/authentik-$volume-2026-08-21.tar.gz" -C /to
done

docker compose $stack up -d
```

Restoring into a different major version is not supported; restore into the
version that made the dump, then upgrade.

Nothing on the scanner's side needs restoring. It holds no state about the
provider beyond the settings in the compose file, and the signing keys are
fetched again on the first request.

## When it does not work

| Symptom | Cause |
|:--------|:------|
| The service refuses to start naming `ISSUER`, `RESOURCE_URL` or `HTTPS` | Exactly what it says; see [pointing the scanner at it](#pointing-the-scanner-at-it) |
| Every request gets 401, and the token looks fine | `iss` in the token does not match `COS_WEB_MCP_AUTH_ISSUER`. Usually the proxy rewriting `Host`, or the application slug not being what you thought |
| Every request gets 401, `iss` is right | `aud` does not contain the audience. In Authentik it is the client ID, not the application name |
| 401 after a while, having worked | The token expired. Access tokens are short-lived by design; the client should refresh |
| 401 and the token has `"alg": "HS256"` | No signing key on the provider. Set one and issue a new token - a symmetrically signed token cannot be verified without the client secret, and this service will not take it |
| 401 and everything looks right | A required scope from `COS_WEB_MCP_AUTH_SCOPES` is missing from the token's `scope` claim |
| Anybody with an Authentik account can get a token | The application has no bindings, and that means everyone. See [adding somebody who may use the endpoint](#adding-somebody-who-may-use-the-endpoint) |
| The token request itself is refused, before `/mcp` is ever reached | The account is not bound to the application. **Events → Logs** records it as a denied authorization, naming the account |
| It worked until a group binding was added, using only the client secret | That path runs as the service account Authentik generated, `ak-check-opencloud-security-client_credentials`, and it is not in the group either. Add it, or move to a service account of your own |
| `invalid_grant` on a `client_credentials` request | The `password` is an **app password**, not the user's login password and not an API token. Create one under **Directory → Tokens and App passwords** |
| The password recovery mail never arrives | No mail server, so Authentik delivered it locally. See [sending mail](#sending-mail) |
| No `WWW-Authenticate` on the 401 | Something in front is stripping it. The header is how a client finds the provider |
| The endpoint is open when it should not be | `COS_WEB_MCP_AUTH_ENABLED` did not reach the container. `/.well-known/ai.json` reports what the service actually believes: `mcp.authentication.type` |
| 401, and the log says the JWKS could not be fetched | The URL resolves but Authentik answers **404**. A Compose service name with an underscore in it is not a legal host name, and Authentik refuses one; use the `authentik-server` alias, which is what the shipped stack does |
| The blueprint never appears under **Customisation → Blueprints** | Authentik reads it as uid 1000. A `authentik/blueprints` directory that is not world-readable - a restrictive `umask` when the repository was cloned - is skipped in silence. `chmod 755 authentik/blueprints && chmod 644 authentik/blueprints/*.yaml` |
| The database container is unhealthy, complaining about `/var/lib/postgresql/data` | PostgreSQL 18 mounts one level up, at `/var/lib/postgresql`, and refuses the old path rather than ignoring it. A volume from a 16 or 17 stack has to be `pg_upgrade`d, not remounted |
| Either Authentik container exits with `Address family not supported by protocol` | The host has no IPv6, and Authentik binds `[::]` by default. The three `AUTHENTIK_LISTEN__*` variables in the shipped stack pin it to IPv4 - including `__METRICS`, which is the one that is easy to forget and enough on its own to crash the worker |

The last one is worth checking after every change:

```bash
curl -s https://scanner.example.com/.well-known/ai.json | jq .mcp.authentication
curl -s https://scanner.example.com/.well-known/oauth-protected-resource/mcp | jq
curl -si https://scanner.example.com/mcp -X POST -d '{}' | grep -i www-authenticate
```

## Using a provider that is not Authentik

Nothing here is Authentik-specific. Any provider that issues signed JWT access
tokens and publishes a JWKS works: Keycloak, Zitadel, Authelia, Auth0, Okta.
Set the issuer to whatever its discovery
document says, the audience to whatever it puts in `aud`, and if it publishes
its keys somewhere other than `<issuer>/jwks/`, set
`COS_WEB_MCP_AUTH_JWKS_URL` to where it does. Only asymmetric algorithms are
accepted - RS256, RS384, RS512, ES256, ES384, ES512 - which rules out `HS256`
and, more importantly, `none`.

Authentik is what ships here because it is open source, self-hosted, runs in
two containers next to the stack, and does not require an account with anybody
to try.

---

This is an independent community project. It is not affiliated with, endorsed
by or supported by OpenCloud GmbH, or by Authentik Security, Inc. "OpenCloud"
and all related marks belong to their respective owners and are used here only
to identify the software this tool checks.
