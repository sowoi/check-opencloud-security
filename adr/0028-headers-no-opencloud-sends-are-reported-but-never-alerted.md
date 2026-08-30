# ADR 0028: Headers no OpenCloud sends are reported but never alerted on

- Status: Accepted
- Date: 2026-08-30

## Context

`setup.headers` grades eight security response headers against what
OpenCloud's proxy service sets by default. That comparison is what gives a
missing header its meaning: `X-Frame-Options` absent means something in front
of *this* instance stripped a header OpenCloud sends, which is a fact about
this deployment and worth an operator's attention.

Three modern headers are worth having and OpenCloud sets none of them on any
instance: `Permissions-Policy`, `Cross-Origin-Opener-Policy` and
`Cross-Origin-Resource-Policy`. Each is genuinely actionable - a reverse proxy
can add it - so `actionable=False`, the mechanism that keeps
`publicLinkExpirationEnforced` out of alerts, does not describe them
honestly.

Adding them to `setup.headers` would work mechanically and fail in practice.
`--check-hardening` turns any missing hardening measure into a WARNING, so
every instance in existence would gain three findings on upgrade, and every
operator using that flag would get an alert that no configuration change on
their side ever clears. AGENTS.md already names that failure mode: a permanent
warning nobody can clear is noise, and noise is how real findings get ignored.
Leaving the headers unmeasured avoids the noise by giving up the information.

## Decision

The scanner reports them in a block of their own, `setup.advisoryHeaders`,
measured from the same response as `setup.headers` and carrying the same
`{name: bool}` shape.

An **advisory header** is measured, explained and published, and never
counted:

- It is absent from `_collect_missing_hardenings`, so it cannot reach the
  alert line, the `hardenings_missing` metric, the webhook payload or the exit
  code.
- It does not participate in the rating, which `setup.headers` never did
  either.
- It is not offered as a waiver. Nothing alerts on it, so there is nothing to
  accept, and offering the tick box would imply otherwise.
- It **is** explained by `--debug`, under a heading that says plainly it is not
  counted against the instance, and it **is** listed in the web catalogue
  through the same `describe_hardening` every other check uses.

A value that restricts nothing does not count as present:
`Cross-Origin-Opener-Policy: unsafe-none` and
`Cross-Origin-Resource-Policy: cross-origin` are the browser defaults written
out, and crediting them would let a deployment pass by sending a header that
changes nothing.

A header moves out of this block and into `setup.headers` when, and only when,
OpenCloud starts sending it by default - at which point its absence becomes a
fact about the deployment and the comparison that gives `setup.headers` its
meaning holds again.

## Consequences

The result document grows one key under `setup`. Consumers that iterate
`setup.headers` are unaffected, and the plugin reads a result without the new
key as having nothing to say, so a document produced by an older scanner still
explains correctly.

Three checks are published that can never change an exit code. That is the
point: the report gains information an operator can act on without the alert
gaining a finding they cannot clear. The risk is the mirror image of the one
avoided - an advisory header is easy to ignore precisely because nothing
forces attention onto it - which is why `--debug` names them explicitly rather
than leaving them to the JSON.

## Alternatives considered

**Put them in `setup.headers` and accept the new WARNING.** Correct by the
letter of the existing model and wrong in effect: it would alert every
existing user about the shipped state of the software rather than about their
deployment.

**Mark them `actionable=False`.** That mechanism exists for flags OpenCloud
hardcodes, where no administrator can change the outcome. These can be
changed, and saying they cannot would be false in the catalogue as well as in
the alert.

**Add a `--check-advisory-headers` flag.** A fourth setting to document,
default off, that most operators would never discover - and the information is
worth having in the report whether or not somebody opted in. The flag can
still be added later if operators ask to alert on them; nothing here forecloses
it.

**Leave them unmeasured.** The status quo, and the reason the gap existed. It
keeps the alert clean by giving up three improvements an operator would act on
if told about them.
