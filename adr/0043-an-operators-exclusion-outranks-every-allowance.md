# ADR 0043: An operator's exclusion outranks every allowance

- Status: Accepted
- Date: 2026-09-13

## Context

`webapp/ssrf.py` decides what the public service may be pointed at, and every
rule in it is a property of the address: the scheme, the shape of the
hostname, whether every resolved address is public unicast, the metadata
endpoints named explicitly. Two settings loosen those rules for a deployment
that is not public — `COS_WEB_ALLOW_PRIVATE_TARGETS` turns the address rules
off wholesale, and `COS_WEB_ALLOWED_HOSTS` exempts named hosts from them.

What no rule could express is a decision somebody made. The instance owner who
writes and asks not to be scanned, the host being submitted repeatedly so that
this service hammers it, the range that is not a scanning target for this
deployment however public it looks — none of that is derivable from an
address, and until now an operator's only answer was a reverse proxy in front
or a patch on top.

Adding a list is the easy half. The question that needs a durable answer is
what happens when the list and the two loosening settings disagree about the
same host, because an operator will eventually configure both — an on-premise
deployment scanning its own estate is exactly the shape that has an allowlist
*and* a machine nobody may touch.

## Decision

`COS_WEB_BLOCKED_TARGETS` names hostnames, domain suffixes and CIDR ranges
this deployment will not scan, and it is checked **before** anything else is
decided and **outside** every exemption. An entry outranks
`COS_WEB_ALLOWED_HOSTS` and `COS_WEB_ALLOW_PRIVATE_TARGETS`.

The reasoning is that the two kinds of rule answer different questions. The
address rules answer *could this request be an attack*, and an operator who
knows their own network may reasonably say "not here". The exclusion answers
*does this service scan that address at all*, which is a promise made to
somebody outside the deployment. A promise that a local convenience setting
can reopen is not one worth making, and the failure is silent: nothing looks
wrong until the scan has already happened.

Three consequences follow from the same premise:

- **The name and the addresses are both checked.** A hostname entry matches
  the name; an address or range is matched against every address the name
  resolves to, v4-mapped and 6to4 forms unwrapped exactly as the public-address
  check unwraps them. An exclusion a second DNS record walks past is not one.
- **It is enforced everywhere a target enters**: at submission, again in the
  worker immediately before the scan — so a target excluded while its job sat
  in the queue is refused rather than scanned — and on every redirect hop, so
  a scanned host cannot name an excluded one in a `Location` header. MCP and
  WebMCP inherit it by calling the same API
  ([ADR 0011](0011-mcp-is-an-execution-layer-not-a-second-implementation.md)).
- **An entry that does not parse refuses startup**, in the web process and in
  the worker alike. A typo is otherwise invisible: the service comes up,
  answers normally, and scans what it was told to leave alone. This follows
  the reasoning of `ensure_encryption_ready`, where a setting that looked
  applied and was not is the failure worth booting loudly over.

The refusal a visitor sees says only that the service has been asked not to
scan that address. Which entry matched is operator configuration, and echoing
it would turn every refusal into a read of the list, one submission at a time.

## Consequences

- An operator can answer "please stop scanning us" in configuration, and can
  point at what the answer is: one variable, read at startup, visible in the
  compose file.
- The two loosening settings are now genuinely subordinate. Anyone adding a
  third one has a rule to follow rather than a precedent to guess at.
- A hostname entry is not an airtight exclusion, and the documentation says so:
  a second name pointing at the same machine is a different hostname. The range
  is the airtight form, and the cost of making a hostname entry airtight —
  resolving every configured name on every submission — buys a guarantee that
  a DNS change still expires.
- The list is refusal only. It cannot grant a scan, so a mistake in it fails
  closed, and nothing in a request can reach it.

## Alternatives considered

**Let `COS_WEB_ALLOWED_HOSTS` win, as the more specific setting.** It is the
more specific setting, and that is the trap: the exemption exists so an
internal instance can be reached at all, and it would silently cancel a
promise made to somebody who is not the operator. Two settings pointing at one
host have to resolve one way round, and refusing is the answer whose failure
mode is a scan that did not happen.

**Refuse quietly and log an unparseable entry.** A denylist that excludes
nothing looks identical to one that works until the day it matters, and
nobody reads a startup log in time. Startup is the one moment an operator is
watching.

**Name the matched entry in the refusal.** More useful to the one visitor who
mistyped their own address, and a configuration read for everybody else.

**Put the list in front of the service, in the reverse proxy.** It works for a
hostname and not for what the name resolves to, it is a second place to keep
the truth, and it leaves the worker — which resolves the target again — with
no knowledge of the exclusion at all.
