# Running OpenCloud in a secure infrastructure

This scanner grades what an OpenCloud instance shows the internet. That is a
useful thing to know and it is not the whole of security. Everything on this
page is the part a scan cannot see: who your identity provider is, whether
anybody would notice a break-in, what the firewall allows, and what the people
using the instance have been told.

Read it as the companion to the check, not as a replacement for it. The last
section explains where the two meet - what continuous monitoring with this
plugin actually buys you once the rest is in place.

> Every setting below is quoted from OpenCloud's own documentation and links
> to it. OpenCloud moves fast; when a variable here disagrees with the linked
> page, the linked page is right, and
> [an issue](https://github.com/sowoi/check-opencloud-security/issues) is
> welcome.

<!-- TOC -->
* [Running OpenCloud in a secure infrastructure](#running-opencloud-in-a-secure-infrastructure)
  * [The shape of a defensible deployment](#the-shape-of-a-defensible-deployment)
  * [1. Put a real identity provider in front](#1-put-a-real-identity-provider-in-front)
    * [Why, before how](#why-before-how)
    * [What OpenCloud needs, whichever provider you pick](#what-opencloud-needs-whichever-provider-you-pick)
    * [Keycloak](#keycloak)
    * [Authentik](#authentik)
    * [Authelia](#authelia)
    * [Basic authentication is the hole in all of this](#basic-authentication-is-the-hole-in-all-of-this)
  * [2. Turn the audit log on, then read it](#2-turn-the-audit-log-on-then-read-it)
    * [The audit service does not run by default](#the-audit-service-does-not-run-by-default)
    * [Getting the log off the box](#getting-the-log-off-the-box)
    * [What to actually alert on](#what-to-actually-alert-on)
    * [Retention, and the law](#retention-and-the-law)
  * [3. Firewall it properly](#3-firewall-it-properly)
    * [The ports, and which of them belong on the internet](#the-ports-and-which-of-them-belong-on-the-internet)
    * [A host firewall that works with Docker](#a-host-firewall-that-works-with-docker)
    * [Egress matters too](#egress-matters-too)
  * [4. Underneath it all: the host and the data](#4-underneath-it-all-the-host-and-the-data)
  * [5. What the people using it should know](#5-what-the-people-using-it-should-know)
    * [For everybody with an account](#for-everybody-with-an-account)
    * [For administrators](#for-administrators)
  * [6. Where this scanner fits: continuous monitoring](#6-where-this-scanner-fits-continuous-monitoring)
    * [What a scheduled scan catches that a one-off audit does not](#what-a-scheduled-scan-catches-that-a-one-off-audit-does-not)
    * [A monitoring setup that is worth having](#a-monitoring-setup-that-is-worth-having)
    * [What it deliberately will not tell you](#what-it-deliberately-will-not-tell-you)
  * [Checklist](#checklist)
  * [Where to go next](#where-to-go-next)
  * [Trademarks and affiliation](#trademarks-and-affiliation)
<!-- TOC -->


## The shape of a defensible deployment

```
                    internet
                        │
                   443/tcp only
                        │
              ┌─────────▼─────────┐
              │   reverse proxy   │  TLS, HSTS, security headers,
              │  (nginx/Caddy/…)  │  rate limits, TRACE refused
              └─────────┬─────────┘
                        │  private network, no published ports
         ┌──────────────┼──────────────┐
         │              │              │
  ┌──────▼─────┐ ┌──────▼─────┐ ┌──────▼──────┐
  │ OpenCloud  │ │  identity  │ │    audit    │
  │   :9200    │ │  provider  │ │   service   │
  └──────┬─────┘ └────────────┘ └──────┬──────┘
         │                             │
   ┌─────▼──────┐               ┌──────▼──────┐
   │  storage   │               │  log sink   │  off-host, append-only
   └────────────┘               └─────────────┘
```

Three properties of that diagram are what the rest of this page is about: only
one thing is reachable from the internet, sign-in happens somewhere that can
enforce a second factor, and what happens inside gets written down somewhere
the instance itself cannot rewrite.

## 1. Put a real identity provider in front

### Why, before how

OpenCloud ships with a built-in identity provider (`idp`) and identity
management (`idm`). They are there so that `opencloud init` produces something
that works, and for a single-user instance that may be all you ever need. They
are not where you want your organisation's accounts to live, for reasons that
have nothing to do with their quality:

- **Second factors.** An external provider gives you TOTP, WebAuthn or
  passkeys across every application you run, configured once.
- **Lifecycle.** Somebody leaves and you disable one account, not one account
  per service.
- **Session policy.** Lockout after failed attempts, session lifetime,
  device trust, conditional access - all of it belongs in the provider.
- **Audit.** Sign-in attempts are recorded in the place that handles sign-ins,
  which is where an investigator will look for them.

This scanner reports which provider it found under `identityProvider`, and
softens the HTTP Basic authentication finding from medium to low when an
external one is detected - see
[Authentication](authentication.md#6-can-the-identity-provider-be-found-at-all-identityproviderdetected).

### What OpenCloud needs, whichever provider you pick

The variables are the same for all three; only the issuer URL and the way you
create the client differ. From
[OpenCloud's external IdP guide](https://docs.opencloud.eu/docs/admin/configuration/authentication-and-user-management/external-idp):

| Variable | What it does |
|:---------|:-------------|
| `OC_OIDC_ISSUER` | The provider's issuer URL, e.g. `https://id.example.com/realms/opencloud` |
| `OC_EXCLUDE_RUN_SERVICES` | Add `idp` so the built-in provider does not start |
| `PROXY_OIDC_ACCESS_TOKEN_VERIFY_METHOD` | `jwt`, so tokens are verified against the provider's published keys rather than by asking it on every request |
| `PROXY_OIDC_REWRITE_WELLKNOWN` | `true`, so clients discovering `/.well-known/openid-configuration` on the OpenCloud host are pointed at the real provider |
| `PROXY_USER_OIDC_CLAIM` | The claim that identifies a user, commonly `preferred_username` |
| `PROXY_USER_CS3_CLAIM` | The OpenCloud attribute it is matched against, commonly `username` |
| `PROXY_AUTOPROVISION_ACCOUNTS` | `true` creates an account on first sign-in |
| `PROXY_ROLE_ASSIGNMENT_DRIVER` | `oidc` to take roles from a claim, `default` to give everybody the same role |
| `PROXY_ROLE_ASSIGNMENT_OIDC_CLAIM` | Which claim carries them; `roles` by default |
| `GRAPH_ASSIGN_DEFAULT_USER_ROLE` | `false` when roles come from the provider, or every user quietly gets the default one as well |

Two decisions in that table deserve more thought than they usually get:

**Autoprovisioning is an access-control decision.** With
`PROXY_AUTOPROVISION_ACCOUNTS=true`, anybody your provider will authenticate
gets an OpenCloud account the first time they visit. That is right when the
provider's OpenCloud application is restricted to a group, and wrong when the
provider authenticates your whole organisation - restrict it on the provider
side, not by leaving autoprovisioning off and creating accounts by hand.

**Role assignment from a claim needs the default role switched off.** Setting
`PROXY_ROLE_ASSIGNMENT_DRIVER=oidc` while leaving
`GRAPH_ASSIGN_DEFAULT_USER_ROLE=true` is the misconfiguration that gives
everyone a role you did not intend.

### Keycloak

The most common choice where an organisation already runs one. Create a realm
(or reuse yours), then a client:

- **Client type** OpenID Connect, **Client ID** `OpenCloudDesktop` for the
  desktop and mobile clients, plus a web client for the browser.
- **Public client** with PKCE - OpenCloud's clients are public clients and
  cannot keep a secret. Set *Proof Key for Code Exchange* to `S256`.
- **Valid redirect URIs** must include the desktop client's loopback
  (`http://127.0.0.1:*` and `http://localhost:*`) and your web address.
- **Issuer**: `https://id.example.com/realms/opencloud`.

For roles, add a *User Client Role* mapper putting the client roles into a
`roles` claim, then set `PROXY_ROLE_ASSIGNMENT_OIDC_CLAIM=roles`. Give the
realm a password policy and require OTP for the administrator role at minimum.

### Authentik

This repository already ships an Authentik stack, though for a different
purpose - it protects [the scan service's own MCP endpoint](authentik.md), not
OpenCloud. The provider configuration is the same shape:

- Create an **OAuth2/OpenID Provider**, authorization flow `implicit consent`
  for a trusted internal application.
- **Client type** public, with PKCE required.
- Set the redirect URIs as above, using regex for the loopback range.
- The issuer is `https://id.example.com/application/o/<application-slug>/`.
  The trailing slash matters.
- Bind the application to a group so that not every Authentik user gets an
  OpenCloud account, then turn `PROXY_AUTOPROVISION_ACCOUNTS` on.

[`authentik/blueprints/`](../authentik/blueprints/) in this repository is a
worked example of provisioning a provider from a file rather than by clicking,
which is worth copying whatever you are configuring.

### Authelia

The lightest of the three, and a good fit where the reverse proxy is already
doing forward authentication. Authelia's OpenID Connect provider is configured
in `configuration.yml` rather than a UI:

- Register a client under `identity_providers.oidc.clients` with
  `public: true`, `require_pkce: true` and `pkce_challenge_method: S256`.
- Scopes `openid`, `profile`, `email`, `groups`.
- The issuer is `https://auth.example.com`.
- Map groups to OpenCloud roles with `PROXY_ROLE_ASSIGNMENT_OIDC_CLAIM=groups`.

Authelia's access control rules are the natural place to require two factors
for OpenCloud specifically:

```yaml
access_control:
  rules:
    - domain: opencloud.example.com
      policy: two_factor
```

### Basic authentication is the hole in all of this

None of the above applies to a client that cannot speak OpenID Connect -
CalDAV and CardDAV calendars, WebDAV mounts, backup jobs. Those authenticate
with HTTP Basic, and `PROXY_ENABLE_BASIC_AUTH=true` re-opens a path that
bypasses your provider and every second factor on it.

Leave it `false` if nothing needs it. If something does, the answer is **app
tokens, not account passwords**: what can be replayed is then revocable and is
never the credential your identity provider protects. This scanner reports
`basicAuthDisabled` as medium, or low when it can see an external provider,
precisely because the trade is sometimes deliberate - see
[Authentication](authentication.md).

## 2. Turn the audit log on, then read it

### The audit service does not run by default

OpenCloud has an
[audit service](https://docs.opencloud.eu/docs/dev/server/services/audit/), and
it is not in the default run set. Nothing is recording who shared what until
you start it:

```bash
# Add it to the services that run, alongside the default set.
OC_ADD_RUN_SERVICES=audit
```

It records three things worth having:

- **File system operations** - create, delete, move, including the trash bin
  and versioning.
- **User management** - accounts created and deleted.
- **Sharing** - user and group shares, public links, permission changes, and
  calls to the sharing API from clients.

That third category is the one that matters most here. This scanner can tell
you that public links may be created without a password
([`publicLinkPasswordEnforced`](sharing.md)); only the audit log can tell you
that somebody created 4,000 of them last Tuesday.

Configure it with the variables from
[the audit service reference](https://docs.opencloud.eu/docs/dev/server/services/audit/environment-variables):

| Variable | Default | What to set it to |
|:---------|:--------|:------------------|
| `AUDIT_LOG_TO_CONSOLE` | `true` | Leave on when a container log driver ships stdout somewhere |
| `AUDIT_LOG_TO_FILE` | `false` | `true` if you would rather write a file |
| `AUDIT_FILEPATH` | *(empty)* | Required when logging to a file |
| `AUDIT_FORMAT` | `json` | Keep `json`; the minimal format is for reading by eye, not by a collector |
| `AUDIT_LOG_LEVEL` | `error` | Raise it, or you will record almost nothing |
| `OC_EVENTS_ENDPOINT` | `127.0.0.1:9233` | The event broker the service reads from |
| `AUDIT_EVENTS_AUTH_USERNAME` / `_PASSWORD` | *(empty)* | Set both once the broker is not on loopback |
| `AUDIT_EVENTS_ENABLE_TLS` | `false` | `true` when the broker is reached over a network |

`AUDIT_LOG_LEVEL` defaulting to `error` is the detail that catches people out:
starting the service and leaving the level alone produces a log that is
technically running and practically empty.

### Getting the log off the box

An audit log stored only on the machine being audited is evidence an attacker
can edit. Ship it:

```yaml
# docker-compose fragment: hand stdout to the host's journal, which a
# collector then forwards off the machine.
services:
  opencloud:
    logging:
      driver: journald
      options:
        tag: opencloud
```

Whatever collector you use - Loki, Elasticsearch, a syslog server, a managed
service - the properties to insist on are the same: **append-only from the
sender's point of view, on a different trust domain from the instance, with
its own retention.** A collector that OpenCloud's own credentials can delete
from is not much better than a local file.

### What to actually alert on

Alerting on everything means alerting on nothing. A short list that has earned
its place:

- A **public link created with no password or no expiry**, especially on a
  space that is not usually shared.
- **Share permissions widened** on anything, particularly to a group.
- **An account created or given an administrative role** outside your normal
  provisioning process.
- **Bulk download or deletion** - a volume of file operations from one account
  well above its own baseline.
- **Sign-in anomalies**, which come from your identity provider rather than
  from OpenCloud: impossible travel, a spike in failures, a first sign-in from
  a new country.

### Retention, and the law

An audit log of a file service is a record of who accessed which documents,
which in most jurisdictions is personal data with a retention limit rather
than something to keep forever. Decide the period deliberately, write it down,
and make the collector enforce it. If you are subject to GDPR, this log is in
scope for your record of processing activities.

## 3. Firewall it properly

### The ports, and which of them belong on the internet

| Port | What it is | Exposed to the internet? |
|:-----|:-----------|:-------------------------|
| 443 | The reverse proxy | **Yes** - this one, and only this one |
| 80 | Plain HTTP | Only to redirect to 443, or not at all |
| 9200 | OpenCloud's own proxy service | **No.** Publishing it lets clients bypass your TLS and header policy entirely |
| 9233 | The events broker (NATS) | **No** |
| 9205, 9141, 9124, 9134, 9239 | Per-service debug listeners - metrics, a config dump, optionally pprof | **No.** They bind to `127.0.0.1` by default; reaching one from outside means a container port mapping published it |
| 22 | SSH | Management network or VPN only, never the open internet |

This scanner checks the bottom three rows from the outside -
`backendPortClosed`, `debugPort:*` and `debugEndpoint:*`, described in
[Exposed paths and debug endpoints](exposure.md). It is checking your firewall
for you, from the one vantage point that counts.

### A host firewall that works with Docker

The usual mistake is worth stating plainly: **Docker writes its own iptables
rules and they are evaluated before UFW's.** A container started with
`-p 9200:9200` is reachable from the internet no matter what `ufw status`
says. Two ways out, and you want one of them:

**Publish to loopback only.** The simplest fix, and it needs no firewall at
all:

```yaml
services:
  opencloud:
    ports:
      # Not "9200:9200" - that binds 0.0.0.0.
      - "127.0.0.1:9200:9200"
```

Better still, publish nothing and let the reverse proxy reach OpenCloud over a
Docker network by service name. A port that is not published cannot be
misconfigured.

**Or make Docker respect the host firewall.** In `/etc/docker/daemon.json`:

```json
{
  "iptables": true,
  "ip-forward": true
}
```

and then filter in `DOCKER-USER`, which is the one chain Docker leaves for
you:

```bash
# Everything reaching a container from outside must come via the proxy.
iptables -I DOCKER-USER -i eth0 -p tcp --dport 9200 -j DROP
```

The [nftables](https://nftables.org/) equivalent, if that is your generation:

```
table inet filter {
  chain input {
    type filter hook input priority 0; policy drop;
    ct state established,related accept
    iif lo accept
    tcp dport { 80, 443 } accept
    tcp dport 22 ip saddr 10.0.0.0/8 accept
  }
}
```

Whichever you use, verify from somewhere else rather than believing the
config. `nmap -Pn -p 9200,9205,9233 opencloud.example.com` from off the host,
or simply run this scanner, which probes exactly those ports:

```bash
check-opencloud-security --host opencloud.example.com --check-hardening --debug
```

### Egress matters too

Inbound rules are the ones people write. Outbound rules are the ones that
limit what a compromise can do - exfiltration, a reverse shell, joining a
botnet. An OpenCloud host needs remarkably little: DNS, NTP, the ACME
directory if it issues its own certificates, your package mirror, and
whatever storage or mail backend you have deliberately configured. Default to
denying the rest.

## 4. Underneath it all: the host and the data

Briefly, because none of it is OpenCloud-specific and all of it is load-bearing:

- **Unattended security updates** on the host, and a real update process for
  the OpenCloud release itself. This scanner grades the release you are on
  ([lifecycle](lifecycle.md)); it cannot install anything.
- **Full-disk encryption** on whatever the storage lives on, so that a
  decommissioned or stolen disk is not a data breach.
- **Backups you have restored from.** A backup nobody has tested is a
  hypothesis. Keep one copy offline or on write-once storage - ransomware
  looks for the backup first.
- **Least privilege for the service account.** The systemd units in
  [`contrib/systemd/`](../contrib/systemd/) show the pattern:
  `DynamicUser=yes`, `ProtectSystem=strict`, `NoNewPrivileges=yes`, an empty
  `CapabilityBoundingSet=`. Run `systemd-analyze security <unit>` on yours.
- **Separate the reverse proxy from OpenCloud**, on different hosts or at
  least different containers, so that a proxy compromise is not immediately a
  storage compromise.

## 5. What the people using it should know

Most real incidents at a file service are not exploits. Somebody shares the
wrong folder with a public link, or reuses a password that was in a breach
dump. That is a documentation and defaults problem, not a patching problem.

### For everybody with an account

- **A public link is a password.** Anyone who has the URL has the data -
  forwarded, pasted into a ticket, or sitting in a mail archive. Put a
  password on it and set an expiry.
- **Check what you are sharing before you share it.** Sharing a parent folder
  shares everything below it, including what gets added later.
- **Enrol a second factor**, and prefer a passkey or a hardware key over TOTP.
- **App passwords are for apps.** Your calendar client gets its own
  revocable token; it never gets your account password.
- **Removing a share is not the same as un-sending a file.** Assume anything
  shared has been downloaded.
- **Report a mistaken share immediately.** The window in which an
  administrator can revoke a link and read the audit log is short, and nobody
  is in trouble for reporting it fast.

### For administrators

- **Review shares periodically.** Public links accumulate; almost none of them
  are ever deliberately deleted.
- **Have an offboarding runbook** that covers the identity provider, the app
  tokens, and the shares that person created.
- **Know your instance's normal.** The alert list above only works against a
  baseline.
- **Write down who to call.** An incident at 03:00 is not the time to discover
  nobody knows who owns the storage.

## 6. Where this scanner fits: continuous monitoring

### What a scheduled scan catches that a one-off audit does not

A security review is a photograph. Infrastructure is a film. Everything on
this page can be true on Monday and false on Thursday, and the ways that
happens are mundane rather than dramatic:

- A **certificate expires**, or renews to one that does not cover every name.
- A **reverse proxy is reconfigured** for an unrelated service and stops
  sending `Strict-Transport-Security`, or starts answering `TRACE`.
- Somebody **publishes a debug port** while chasing a performance problem and
  does not unpublish it.
- A **release goes end of life**, which is a change in the world rather than a
  change in your deployment - the instance that was fully supported last month
  now receives no security fixes, and nothing on your host changed to tell
  you.
- An **advisory is published** for the version you are running.
- A **new deployment** is stood up from a copied compose file that still
  publishes 9200.

Running this plugin on a schedule turns each of those into an alert on the day
it happens, from outside the instance, which is the same vantage point an
attacker has. That is the argument for continuous monitoring in one sentence:
**the gap between a deployment breaking and somebody noticing is where
incidents live, and the only thing that shortens it is something that looks
every few minutes.**

### A monitoring setup that is worth having

Start here, then read [Scheduling](scheduling.md) or
[Icinga2 / Nagios](../README.md#icinga2--nagios) for your platform:

```bash
check-opencloud-security \
  --host opencloud.example.com \
  --check-hardening \
  --baseline /var/lib/check-opencloud-security/baseline.json \
  --warn-on-new \
  --webhook-url https://hooks.example.com/opencloud \
  --webhook-on warning
```

Four choices in there, each earning its place:

- **`--check-hardening`** includes the headers and hardening measures, not
  only the rating.
- **`--baseline` with `--warn-on-new`** alerts on what *changed* rather than
  on the accepted state of the world. An instance with one finding you have
  consciously decided to live with stays quiet until a second one appears -
  see [Reporting only what changed](../README.md#reporting-only-what-changed).
- **A webhook** so the alert reaches a human rather than a dashboard nobody
  opens.
- **Findings you accept are waived explicitly**, with
  `--ignore-hardening`, which keeps them in the result document and in the
  report while taking them out of the alert. A waiver is a decision with a
  name on it, not a silenced check - see
  [Accepting a finding you are not going to fix](../README.md#accepting-a-finding-you-are-not-going-to-fix).

For a fleet, [Checking a fleet of instances](many-instances.md) covers one
configuration file per instance and keeping the waivers honest across all of
them. For graphs and long-run trends, [Prometheus and
Grafana](prometheus.md) - the rating as a time series is a surprisingly good
summary to put in front of people who do not read alerts.

### What it deliberately will not tell you

Being clear about this is what makes the rest of the report trustworthy:

- **Nothing behind a login.** The scan never authenticates, so it sees what an
  anonymous visitor sees and nothing more. Your permission model, your space
  layout and the contents of your shares are all invisible to it.
- **Nothing about your identity provider's configuration.** It detects that
  one is there and names the vendor; whether you require a second factor is
  between you and the provider.
- **Nothing about your audit log.** Whether the service is running, whether
  anyone reads it, and whether it leaves the host are all outside what an
  HTTP scan can observe.
- **Nothing about your firewall's rules**, only about their effect on the
  handful of ports it probes.
- **No exploitation.** It never tries a payload, never guesses a password, and
  the one credential probe it does make uses only the demo passwords
  OpenCloud publishes in its own documentation.

[What the scan deliberately does not
answer](../README.md#what-the-scan-deliberately-does-not-answer) is the full
version of this list.

## Checklist

Print it, argue with it, cross off what does not apply:

- [ ] Only 443 (and 80, redirecting) reachable from the internet
- [ ] 9200 and every `92xx` debug port unreachable from outside - verified
      from another host, not from the config
- [ ] Outbound traffic restricted to what the instance actually needs
- [ ] An external identity provider handles sign-in
- [ ] Second factor required, at minimum for administrators
- [ ] `PROXY_ENABLE_BASIC_AUTH=false`, or app tokens issued for the clients
      that need it
- [ ] `GRAPH_ASSIGN_DEFAULT_USER_ROLE=false` if roles come from a claim
- [ ] Autoprovisioning scoped by a group on the provider side
- [ ] `OC_ADD_RUN_SERVICES=audit` and `AUDIT_LOG_LEVEL` raised above `error`
- [ ] Audit log shipped off the host, with a deliberate retention period
- [ ] Alerts defined for public links, share widening and role changes
- [ ] TLS from a public CA, renewing automatically, with a CAA record
- [ ] Security headers set at the proxy - see [reverse proxies](reverse-proxy.md)
- [ ] `OC_CORS_ALLOW_ORIGINS` narrowed from its `*` default
- [ ] Public links require a password and an expiry
- [ ] Backups exist, leave the host, and have been restored from
- [ ] Host patched automatically; OpenCloud release inside its support window
- [ ] This check runs on a schedule, with a baseline, alerting a human

## Where to go next

| Page | Why |
|:-----|:----|
| [Reverse proxies](reverse-proxy.md) | The nginx, Apache, Caddy, Traefik and HAProxy configuration behind most of section 3 |
| [TLS and certificates](tls.md) | Every transport check, and what a good certificate looks like |
| [Exposed paths and debug endpoints](exposure.md) | What the firewall section is checked against |
| [Authentication](authentication.md) | The identity-provider and Basic-auth findings in detail |
| [Public link sharing](sharing.md) | The sharing policy your users are working within |
| [Scheduling](scheduling.md) | systemd timers and cron for the monitoring in section 6 |
| [Checking a fleet of instances](many-instances.md) | Once there is more than one |
| [Prometheus and Grafana](prometheus.md) | The rating as a time series |
| [What OpenCloud is](what-is-opencloud.md) | Background, if you arrived here from ownCloud or Nextcloud |

## Trademarks and affiliation

This is an independent community project. It is **not** affiliated with,
endorsed by, sponsored by or supported by OpenCloud GmbH, and nothing on this
page is an official statement about OpenCloud software.

"OpenCloud", the OpenCloud logo and all related names and marks are the
property of their respective owners. They appear here only to identify the
software this tool checks. All rights in OpenCloud remain with OpenCloud GmbH.
