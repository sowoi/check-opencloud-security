# Putting an identity provider in front of OpenCloud, step by step

[Running OpenCloud in a secure infrastructure](secure-deployment.md#1-put-a-real-identity-provider-in-front)
argues *why* an external identity provider belongs in front of an OpenCloud
instance, and summarises what each of the three common ones needs. This page
is the long version of that summary: three complete tutorials, from nothing
to a working sign-in, for **Keycloak**, **Authentik** and **Authelia**.

Pick one. They do the same job, and running two is a way of having neither
configured properly.

> **This page changes who may sign in, not how OpenCloud is exposed.** An
> identity provider is one control among several. The firewall, the audit
> log, the reverse proxy and the release lifecycle are the rest of the job,
> and [Running OpenCloud in a secure
> infrastructure](secure-deployment.md) covers them together.

<!-- TOC -->
* [Putting an identity provider in front of OpenCloud, step by step](#putting-an-identity-provider-in-front-of-opencloud-step-by-step)
  * [Before you start](#before-you-start)
  * [What every provider has to produce](#what-every-provider-has-to-produce)
    * [The four clients](#the-four-clients)
    * [Why they are all public clients](#why-they-are-all-public-clients)
  * [What OpenCloud needs, whichever provider you pick](#what-opencloud-needs-whichever-provider-you-pick)
  * [Tutorial A: Keycloak](#tutorial-a-keycloak)
  * [Tutorial B: Authentik](#tutorial-b-authentik)
  * [Tutorial C: Authelia](#tutorial-c-authelia)
  * [Verifying it actually worked](#verifying-it-actually-worked)
  * [Moving an instance that already has accounts](#moving-an-instance-that-already-has-accounts)
  * [Troubleshooting](#troubleshooting)
  * [Where to go next](#where-to-go-next)
  * [Trademarks and affiliation](#trademarks-and-affiliation)
<!-- TOC -->

## Before you start

Three names, decided now and not changed later. Every URL below is built from
them, and an issuer that changes after people have signed in invalidates every
session and every desktop client's stored token at once:

| Name | Example | What it is |
|:-----|:--------|:-----------|
| The instance | `opencloud.example.com` | Where OpenCloud answers |
| The provider | `id.example.com` | Where the sign-in page lives |
| The realm or application slug | `opencloud` | The provider's own name for this application |

You also need:

- **A working OpenCloud instance over HTTPS.** Not an instance you are
  building at the same time. If sign-in breaks you want to know it was the
  provider, and a half-built instance takes that certainty away.
- **A real certificate on both names.** OpenID Connect discovery is an HTTPS
  request from OpenCloud to the provider; a self-signed certificate there
  fails in a way whose error message rarely says so.
- **Both names resolving from inside the container network as well as
  outside.** This is the single most common cause of "it works in the browser
  and the desktop client hangs" - see [Troubleshooting](#troubleshooting).
- **A way back in.** Keep one local OpenCloud administrator until the new
  sign-in is proven, and do not remove `idp` from the running services until
  then.

## What every provider has to produce

The clients, the redirect URIs and the scopes are properties of **OpenCloud's
own applications**, not of the provider. They are identical for Keycloak,
Authentik and Authelia, and getting one of them wrong produces the same
failure whichever provider you chose. Configure these four, every time.

### The four clients

| Client | Default client ID | Redirect URIs | Scopes |
|:-------|:------------------|:--------------|:-------|
| Web | `web` | `https://opencloud.example.com/`, `https://opencloud.example.com/oidc-callback.html`, `https://opencloud.example.com/oidc-silent-redirect.html` | `openid profile email groups` |
| Desktop | `OpenCloudDesktop` | `http://127.0.0.1`, `http://localhost` | `openid profile email groups offline_access` |
| Android | `OpenCloudAndroid` | `oc://android.opencloud.eu` | `openid profile email groups offline_access` |
| iOS | `OpenCloudIOS` | `oc://ios.opencloud.eu`, `oc.ios://ios.opencloud.eu` | `openid profile email groups offline_access` |

Three things in that table are load-bearing:

**The web client needs all three redirect URIs.** `oidc-callback.html` ends
the sign-in; `oidc-silent-redirect.html` is how the tab renews a token without
sending somebody back to a login screen mid-upload. Register only the first
and sign-in works, then sessions start dying at an interval nobody can
reproduce on purpose.

**Only the non-browser clients get `offline_access`.** That scope is what
issues the refresh token a desktop or mobile client needs to survive a
restart. The browser deliberately does not have one - a refresh token in a
tab is a credential sitting in a place that cannot protect it.

**The client IDs are configurable, and the two halves must agree.** The
provider knows them because you typed them there; OpenCloud publishes them to
its own clients through WebFinger, from
`WEBFINGER_WEB_OIDC_CLIENT_ID` and its `ANDROID`, `IOS` and `DESKTOP`
counterparts. Change one without the other and the desktop client asks the
provider for a client that does not exist.

### Why they are all public clients

Every OpenCloud client - the web app in a tab, the desktop app on a laptop,
the two mobile apps - runs entirely on somebody else's machine. None of them
can keep a secret, because anything shipped to all of them is a secret every
one of their users has a copy of.

So all four are **public clients using the authorization code flow with
PKCE**, and PKCE is not optional decoration: it is the thing that replaces
the client secret those clients cannot hold. Set the challenge method to
`S256`, never `plain`. Do not issue a client secret to any of them - a
provider that requires one for a public client is configured wrong, and
pasting a secret into a desktop app to satisfy it publishes that secret.

## What OpenCloud needs, whichever provider you pick

Set these on the OpenCloud side once the provider is up. The
[external IdP guide](https://docs.opencloud.eu/docs/admin/configuration/authentication-and-user-management/external-idp)
is the upstream reference; the notes here are the parts worth a second
thought.

```shell
# The provider, and turning the built-in one off.
OC_OIDC_ISSUER="https://id.example.com/realms/opencloud"
OC_EXCLUDE_RUN_SERVICES="idp"

# Verify tokens against the provider's published keys rather than asking it
# on every single request.
PROXY_OIDC_ACCESS_TOKEN_VERIFY_METHOD="jwt"
PROXY_OIDC_REWRITE_WELLKNOWN="true"

# Who a token belongs to, and the OpenCloud attribute it is matched against.
PROXY_USER_OIDC_CLAIM="preferred_username"
PROXY_USER_CS3_CLAIM="username"

# Create the account on first sign-in, and where its fields come from.
PROXY_AUTOPROVISION_ACCOUNTS="true"
PROXY_AUTOPROVISION_CLAIM_USERNAME="preferred_username"
PROXY_AUTOPROVISION_CLAIM_EMAIL="email"
PROXY_AUTOPROVISION_CLAIM_DISPLAYNAME="name"
PROXY_AUTOPROVISION_CLAIM_GROUPS="groups"

# Roles from a claim - and the default role switched off, or everybody gets
# that one as well.
PROXY_ROLE_ASSIGNMENT_DRIVER="oidc"
PROXY_ROLE_ASSIGNMENT_OIDC_CLAIM="roles"
GRAPH_ASSIGN_DEFAULT_USER_ROLE="false"

# The client IDs, published to OpenCloud's own clients through WebFinger.
WEBFINGER_WEB_OIDC_CLIENT_ID="web"
WEBFINGER_DESKTOP_OIDC_CLIENT_ID="OpenCloudDesktop"
WEBFINGER_ANDROID_OIDC_CLIENT_ID="OpenCloudAndroid"
WEBFINGER_IOS_OIDC_CLIENT_ID="OpenCloudIOS"
```

Two of those are access-control decisions wearing the clothes of
configuration, and both are covered at greater length in
[secure-deployment.md](secure-deployment.md#what-opencloud-needs-whichever-provider-you-pick):

- **`PROXY_AUTOPROVISION_ACCOUNTS=true` means anybody your provider will
  authenticate gets an OpenCloud account on first visit.** That is correct
  when the provider restricts this application to a group, and wrong when the
  provider authenticates your whole organisation. Restrict it on the provider
  side. Leaving autoprovisioning off and creating accounts by hand is not the
  fix; it is the same decision, made worse by being manual.
- **`PROXY_ROLE_ASSIGNMENT_DRIVER=oidc` with
  `GRAPH_ASSIGN_DEFAULT_USER_ROLE=true` is the misconfiguration that gives
  everybody a role you did not intend.** Setting the first means switching
  off the second.

Restart OpenCloud after changing any of these. `OC_EXCLUDE_RUN_SERVICES` in
particular is read once, at startup.

## Tutorial A: Keycloak

The most common choice where an organisation already runs one, and the
heaviest of the three. Pick it if you need a full realm - federation, identity
brokering, fine-grained role mapping - or if Keycloak is already there.

**1. Run it.** A minimal production-shaped compose service, behind whatever
reverse proxy already terminates TLS for you:

```yaml
services:
  keycloak:
    image: quay.io/keycloak/keycloak:latest
    command: ["start", "--optimized"]
    environment:
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://keycloak-db:5432/keycloak
      KC_DB_USERNAME: keycloak
      KC_DB_PASSWORD_FILE: /run/secrets/kc_db_password
      KC_HOSTNAME: https://id.example.com
      KC_PROXY_HEADERS: xforwarded
      KC_HTTP_ENABLED: "true"
      # Bootstrap only. Create a real administrator, then remove these two
      # and restart - they are a password in an environment variable.
      KC_BOOTSTRAP_ADMIN_USERNAME: admin
      KC_BOOTSTRAP_ADMIN_PASSWORD_FILE: /run/secrets/kc_bootstrap
    secrets: [kc_db_password, kc_bootstrap]
    depends_on: [keycloak-db]
```

`KC_PROXY_HEADERS: xforwarded` matters: without it Keycloak builds its issuer
and redirect URLs from the internal address and every one of them is wrong in
a way that only shows up at the redirect.

**2. Create the realm.** *Realms → Create realm*, named `opencloud`. Do not
use the `master` realm for applications - it is the realm that administers
Keycloak itself, and an application client there is an application client on
your administration plane.

Your issuer is now:

```
https://id.example.com/realms/opencloud
```

**3. Create the four clients.** *Clients → Create client*, four times, using
the IDs and redirect URIs from [the table above](#the-four-clients). For each
one:

- **Client type**: OpenID Connect.
- **Client authentication**: **off**. This is what makes it a public client.
- **Authentication flow**: *Standard flow* only. Turn off *Direct access
  grants* - it is the password grant, and it is a way around every second
  factor you are about to configure.
- **Valid redirect URIs**: from the table. The desktop client needs
  `http://127.0.0.1/*` and `http://localhost/*` - the port is chosen at
  runtime, so the wildcard is doing real work here rather than being
  laziness.
- **Web origins**: `https://opencloud.example.com` for the web client only.
- Under *Advanced → Advanced settings*, set **Proof Key for Code Exchange
  Code Challenge Method** to `S256`.

**4. Make the claims OpenCloud reads.** *Client scopes → `<client>-dedicated`
→ Add mapper → By configuration*:

- **Group Membership** mapper, token claim name `groups`, *Full group path*
  **off**. Without the last one your groups arrive as `/finance` and every
  comparison against `finance` fails.
- **User Client Role** mapper, token claim name `roles`, if you are assigning
  OpenCloud roles from Keycloak.

Add both to the **access token** and the **userinfo** response. OpenCloud
reads the token; a claim that exists only in the ID token is a claim it never
sees.

**5. Require a second factor.** *Authentication → Required actions* →
enable *Configure OTP*, then *Authentication → Flows* → bind a browser flow
that requires it. A provider without a second factor has moved your sign-in,
not improved it.

**6. Point OpenCloud at it** with the variables above, and restart.

## Tutorial B: Authentik

The middle weight, and the friendliest to configure from a file rather than by
clicking. Pick it if you want one provider in front of several applications
with per-application policies.

> This repository already ships an Authentik stack, but for a different
> purpose: it protects [the scan service's own MCP endpoint](authentik.md) and
> [operator's area](../ADMIN.md), not OpenCloud.
> [`authentik/blueprints/`](../authentik/blueprints/) is a worked example of
> provisioning a provider from a file, which is worth copying whatever you are
> configuring.

**1. Run it.** Authentik publishes a compose file and a generator for it;
follow [their installation
guide](https://docs.goauthentik.io/install-config/install/docker-compose)
rather than a copy of it that will be out of date here. What matters
afterwards is that `https://id.example.com` reaches it and that TLS is real.

**2. Create the scope mapping for groups.** *Customisation → Property
mappings → Create → Scope mapping*:

- **Name**: `OpenCloud groups`
- **Scope name**: `groups`
- **Expression**:
  ```python
  return {"groups": [group.name for group in request.user.ak_groups.all()]}
  ```

Authentik ships mappings for `openid`, `profile` and `email`; `groups` is the
one you usually have to add, and it is the one OpenCloud needs for roles.

**3. Create four providers.** *Applications → Providers → Create →
OAuth2/OpenID Provider*, once per client in
[the table above](#the-four-clients):

- **Client type**: **Public**.
- **Client ID**: from the table.
- **Redirect URIs**: from the table. Authentik matches these as regular
  expressions, so escape the dots - `http://127\.0\.0\.1(:[0-9]+)?` for the
  desktop client's loopback range.
- **Scopes**: the three built-in mappings plus `OpenCloud groups`.
- **Signing key**: your certificate, so tokens are signed rather than
  unsigned.
- **Authorization flow**: `implicit consent` for an internal application -
  people should not be asked to consent to your own file server on every
  sign-in.

**4. Create the application and bind it to a group.** *Applications →
Applications → Create*, slug `opencloud`, provider the web one from step 3.
Then bind it: *Policies / Group / User bindings* → bind the group that should
have OpenCloud.

**This binding is the access control that makes autoprovisioning safe.** With
it, `PROXY_AUTOPROVISION_ACCOUNTS=true` creates accounts only for people you
have already decided should have one.

**5. Read the issuer off the provider.** It is:

```
https://id.example.com/application/o/opencloud/
```

**The trailing slash is part of it.** OpenID Connect compares the issuer
string exactly, so an issuer configured without it fails validation against
tokens that carry it, and the error names neither the slash nor the issuer.

**6. Point OpenCloud at it** with the variables above, and restart.

## Tutorial C: Authelia

The lightest of the three, configured entirely in a file, and a good fit where
the reverse proxy is already doing forward authentication for other services.
Pick it if you want one small binary rather than a realm server.

**1. Run it**, alongside its session store:

```yaml
services:
  authelia:
    image: ghcr.io/authelia/authelia:latest
    volumes:
      - ./authelia:/config
    environment:
      AUTHELIA_IDENTITY_PROVIDERS_OIDC_HMAC_SECRET_FILE: /run/secrets/oidc_hmac
      AUTHELIA_IDENTITY_PROVIDERS_OIDC_ISSUER_PRIVATE_KEY_FILE: /run/secrets/oidc_key
    secrets: [oidc_hmac, oidc_key]
```

Generate the two secrets before first start - Authelia will not invent them
for you:

```shell
docker run --rm ghcr.io/authelia/authelia:latest \
    authelia crypto rand --length 64 --charset alphanumeric
docker run --rm -v "$PWD/authelia:/keys" ghcr.io/authelia/authelia:latest \
    authelia crypto pair rsa generate --bits 4096 --directory /keys
```

**2. Register the four clients** under
`identity_providers.oidc.clients` in `configuration.yml`. This is the whole
web client; the other three differ only in `client_id`, `redirect_uris` and
their lack of a browser:

```yaml
identity_providers:
  oidc:
    clients:
      - client_id: 'web'
        client_name: 'OpenCloud'
        public: true
        authorization_policy: 'two_factor'
        require_pkce: true
        pkce_challenge_method: 'S256'
        token_endpoint_auth_method: 'none'
        scopes: ['openid', 'profile', 'email', 'groups']
        redirect_uris:
          - 'https://opencloud.example.com/'
          - 'https://opencloud.example.com/oidc-callback.html'
          - 'https://opencloud.example.com/oidc-silent-redirect.html'
        response_types: ['code']
        grant_types: ['authorization_code']

      - client_id: 'OpenCloudDesktop'
        client_name: 'OpenCloud Desktop'
        public: true
        authorization_policy: 'two_factor'
        require_pkce: true
        pkce_challenge_method: 'S256'
        token_endpoint_auth_method: 'none'
        scopes: ['openid', 'profile', 'email', 'groups', 'offline_access']
        redirect_uris: ['http://127.0.0.1', 'http://localhost']
        response_types: ['code']
        grant_types: ['authorization_code', 'refresh_token']

      - client_id: 'OpenCloudAndroid'
        client_name: 'OpenCloud Android'
        public: true
        authorization_policy: 'two_factor'
        require_pkce: true
        pkce_challenge_method: 'S256'
        token_endpoint_auth_method: 'none'
        scopes: ['openid', 'profile', 'email', 'groups', 'offline_access']
        redirect_uris: ['oc://android.opencloud.eu']
        response_types: ['code']
        grant_types: ['authorization_code', 'refresh_token']

      - client_id: 'OpenCloudIOS'
        client_name: 'OpenCloud iOS'
        public: true
        authorization_policy: 'two_factor'
        require_pkce: true
        pkce_challenge_method: 'S256'
        token_endpoint_auth_method: 'none'
        scopes: ['openid', 'profile', 'email', 'groups', 'offline_access']
        redirect_uris: ['oc://ios.opencloud.eu', 'oc.ios://ios.opencloud.eu']
        response_types: ['code']
        grant_types: ['authorization_code', 'refresh_token']
```

`authorization_policy: 'two_factor'` is where the second factor is required,
per client, and it is the reason to prefer this over a global rule: the
desktop client and the browser can be held to the same standard without
depending on anybody remembering an access-control rule.

**3. Add the access-control rule** for the instance itself, so that anything
not covered by the OpenID Connect flow is also protected:

```yaml
access_control:
  default_policy: 'deny'
  rules:
    - domain: 'opencloud.example.com'
      policy: 'two_factor'
```

**4. The issuer is the bare host**, with no path and no trailing slash:

```
https://id.example.com
```

**5. Point OpenCloud at it** with the variables above, and restart.

## Verifying it actually worked

Four checks, in this order. Each one fails differently, so running them out of
order costs time.

**1. The provider publishes a discovery document.**

```shell
curl -fsS https://id.example.com/.well-known/openid-configuration | \
    python3 -m json.tool | head -20
```

The `issuer` field in the answer must be **byte-for-byte** what you put in
`OC_OIDC_ISSUER`. A trailing slash counts.

**2. OpenCloud points at it.** With `PROXY_OIDC_REWRITE_WELLKNOWN=true`,
asking OpenCloud gives the provider's document:

```shell
curl -fsS https://opencloud.example.com/.well-known/openid-configuration | \
    python3 -c 'import json,sys; print(json.load(sys.stdin)["issuer"])'
```

If that returns OpenCloud's own address, the built-in `idp` is still running -
`OC_EXCLUDE_RUN_SERVICES` did not take effect, or the container was not
restarted.

**3. A person can sign in.** In a private window, so you are not testing a
session you already had. Then check the account appeared, if you turned
autoprovisioning on.

**4. Scan it.** This is what the rest of this repository is for. The scanner
reports which provider it found and reads four properties of the discovery
document that provider publishes:

```shell
check-opencloud-security --host opencloud.example.com --check-hardening --debug
```

Look for `identityProviderDetected` passing, and for `oidcPkceSupported`,
`oidcImplicitFlowDisabled`, `oidcSigningAlgorithmStrong` and
`oidcEndpointsUseHttps`. [Authentication](authentication.md) explains what
each of them means and why it is checked. A provider that fails
`oidcImplicitFlowDisabled` is still offering a flow that puts tokens in a URL,
which is worth fixing before anybody uses it.

Note what this does **not** prove: the scanner reads what the provider
publishes without signing in, so it cannot tell you that your group mapping is
right or that your second factor is enforced. Those are the two things to test
by hand.

## Moving an instance that already has accounts

Switching an instance that people already use is a different job from
configuring a new one, and the difference is entirely about identity matching.

**The accounts have to line up.** `PROXY_USER_OIDC_CLAIM` and
`PROXY_USER_CS3_CLAIM` are what connects a person at the provider to their
existing OpenCloud account and everything in it. If `preferred_username` at
the provider does not equal `username` in OpenCloud, autoprovisioning creates
a *second*, empty account for somebody who already had one, and their files
are still in the first.

So, in order:

1. **Export the existing usernames** and compare them against the provider's,
   before changing anything. Reconcile the differences at the provider.
2. **Leave `idp` running** and configure the external provider alongside it.
3. **Test with one account** that exists in both, and confirm it lands in the
   existing space rather than a new one.
4. **Then** add `idp` to `OC_EXCLUDE_RUN_SERVICES` and restart.
5. **Keep `PROXY_ENABLE_BASIC_AUTH=false`.** WebDAV mounts, CalDAV clients and
   backup jobs authenticate with HTTP Basic and bypass the provider and every
   second factor on it. Where something genuinely needs it, the answer is app
   tokens rather than account passwords - see
   [secure-deployment.md](secure-deployment.md#basic-authentication-is-the-hole-in-all-of-this).

## Troubleshooting

| What you see | What it usually is |
|:-------------|:-------------------|
| `invalid issuer` or token validation failures | `OC_OIDC_ISSUER` does not match the provider's own `issuer` string exactly. Authentik needs the trailing slash; Authelia has none |
| Sign-in works in the browser, desktop client hangs | The provider's name does not resolve from inside the container network, or the desktop redirect URI has no port wildcard |
| Sign-in works, then sessions die at odd intervals | The web client is missing `oidc-silent-redirect.html` from its redirect URIs |
| The desktop client never stays signed in | `offline_access` is missing from that client's scopes, so no refresh token is issued |
| Everybody has more permission than intended | `GRAPH_ASSIGN_DEFAULT_USER_ROLE` is still `true` while roles come from a claim |
| A second, empty account for somebody who had one | The claim in `PROXY_USER_OIDC_CLAIM` does not equal the attribute in `PROXY_USER_CS3_CLAIM` |
| Groups arrive but never match | Keycloak's *Full group path* is on, so `finance` is arriving as `/finance` |
| Users authenticate who should not have accounts | Autoprovisioning is on and the application is not restricted to a group at the provider |
| Scanner still reports the built-in provider | `OC_EXCLUDE_RUN_SERVICES` does not include `idp`, or OpenCloud was not restarted |

## Where to go next

| Page | Why |
|:-----|:----|
| [Running OpenCloud in a secure infrastructure](secure-deployment.md) | The audit log, the firewall and the rest of the job this page is one part of |
| [Authentication](authentication.md) | Every authentication and OpenID Connect check the scanner runs, in detail |
| [Reverse proxies](reverse-proxy.md) | Terminating TLS in front of both names |
| [TLS and certificates](tls.md) | What a good certificate looks like, and every transport check |
| [Authentik in front of the MCP endpoint](authentik.md) | The same provider, protecting this scan service rather than OpenCloud |
| [Hardening measures](hardening.md) | What `basicAuthDisabled` and the rest actually mean |

## Trademarks and affiliation

This is an independent community project. It is **not** affiliated with,
endorsed by, sponsored by or supported by OpenCloud GmbH, and nothing on this
page is an official statement about OpenCloud software.

"OpenCloud", the OpenCloud logo and all related names and marks are the
property of their respective owners. Keycloak, Authentik and Authelia are the
property of their respective owners likewise. They appear here only to
identify the software this page describes. All rights in OpenCloud remain with
OpenCloud GmbH.
