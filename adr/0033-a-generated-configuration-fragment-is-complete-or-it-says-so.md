# ADR 0033: A generated configuration fragment is complete, or it says so

- Status: Accepted
- Date: 2026-08-31

## Context

Every finding already carried the answer in prose: *Set
`PROXY_ENABLE_BASIC_AUTH=false`*. An operator with eleven findings translated
eleven such sentences into one Compose file by hand, and the translation is
where the mistakes were - a variable mistyped, a value guessed, a fix applied
to the wrong service.

Rendering the fragment for them is obviously useful and has two ways of going
badly wrong.

**A fragment that is nearly right.** Some checks have no value that can be
written down in advance. `corsOriginRestricted` wants the origins this
deployment actually serves; `cspWithoutUnsafeInline` wants a path to a policy
file that does not exist yet. The helpful-looking move is to emit
`OC_CORS_ALLOW_ORIGINS: "https://cloud.example.com"` and trust the reader to
edit it. They will not always: a fragment offered under a heading saying
*paste this* looks finished, and the one that gets pasted unread is the one
with a placeholder in it.

**A fragment in the wrong file.** Environment assignments go on the OpenCloud
instance. Response headers go on whatever terminates TLS in front of it.
These are different files and usually different machines. A renderer that
folded both into whichever flavour was selected would put `add_header` lines
in a Compose file, or `X-Frame-Options` in an environment block - a line that
parses, deploys, and does nothing, in a file nobody reads twice.

There is a third temptation, in the browser: build the fragments from the
result document in JavaScript, so the picker needs no server round trip. That
is a second implementation of the one thing on the page that has to be exactly
right, in the language with no tests around it.

## Decision

**The fragment is rendered from the catalogue, by the library, and never
guesses.**

- `opencloud_local_scan/snippets.py` renders; it holds no configuration
  knowledge. Every name and value comes from two new fields on the catalogue
  entries, `Hardening.env_fix` and `Hardening.header_fix`. The prose an
  operator reads and the assignment they paste therefore have one source, and
  a test asserts each header value still appears in its own `remediation`
  sentence.
- A check whose correct value is **a decision about the deployment carries no
  pair at all**. It is reported in `Fragment.undecided` - *there is nothing to
  paste, the finding's own Fix line is the whole answer* - rather than given a
  placeholder.
- **A flavour expresses one kind of fix.** `compose` and `env` write
  environment assignments; `nginx`, `caddy` and `traefik` write response
  headers. Neither ever renders the other's. What the chosen flavour cannot
  express is named in `Fragment.elsewhere`, with the flavours that can.
- **Every flavour is rendered server-side**, all five, and a script collapses
  them into a picker. Nothing is generated in the browser.
- This stays in the library because it is still *measurement*: what the
  catalogue said, in another notation. It decides nothing about whether a
  finding is acceptable, which remains the plugin's ([AGENTS.md, the three
  layers]).

## Consequences

- A reader can paste a fragment without reading it and be no worse off than
  before, because everything in it is a value the check actually looks for.
  What needs judgement is visibly *not* in the fragment.
- Coverage is partial and will stay partial. Twelve catalogue entries carry an
  environment fix and ten headers carry a value; the TLS, cookie and lifecycle
  findings carry none, because their fixes are certificates, code paths and
  upgrades rather than assignments. The section says which findings it could
  not write, so partial coverage reads as partial rather than as complete.
- Adding a check with a mechanical fix now means adding the pair as well as
  the sentence, or the fragment silently omits it. The drift tests catch the
  reverse - a pair disagreeing with its own prose - but cannot catch an
  omission, which is the accepted gap.
- The five flavours are a maintenance surface: a syntax change in any of them
  is a change here. They are small, and the alternative was prose.
- The web application renders five fragments per report page rather than one.
  They are at most a dozen lines each, and it buys a picker with no round trip
  and no second implementation.

## Alternatives considered

**Emit placeholders for deployment-specific values.** Rejected: it is the one
failure mode that produces a *worse* outcome than the prose it replaced,
because it looks finished. A fragment that must be edited first cannot be told
apart from one that must not.

**One fragment carrying both kinds, with comments saying which file each part
belongs in.** Rejected: the parts that were in the wrong file would still be
pasted, and a comment is not a boundary.

**Build the fragments in the browser from the result JSON.** Rejected: a
second implementation of the module the library tests cover, in the place
where a mistake reaches an operator's production configuration.

**Put the renderer in `webapp/`.** Rejected: the plugin's `--debug` output and
`check-opencloud-scanner explain` want the same fragments, and a web-only
renderer would be reimplemented for them within a release or two.
