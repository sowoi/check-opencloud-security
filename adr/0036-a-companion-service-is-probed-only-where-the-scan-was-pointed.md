# ADR 0036: A companion service is probed only where the scan was pointed

- Status: Accepted
- Date: 2026-09-04

## Context

A real OpenCloud deployment is rarely one service. A document editor
(Collabora Online, OnlyOffice) speaking WOPI is the usual second one, and
`_integrations` has reported its presence since the app-provider check
landed: the instance names its own app providers in `/app/list`, and the
capabilities document says whether groupware is on.

Presence was as far as it went. That editor is a second HTTP server with an
administration console listing every open document session, a transport of
its own, and a discovery document advertising the addresses a browser is sent
to - none of which the scan looked at, on an instance whose own findings were
examined in detail. A deployment can have an immaculate OpenCloud and publish
its editor's admin console to the internet.

The obvious way to reach that editor is the obvious mistake. The WOPI
discovery document names the host the editor is served from, and following it
would let the scan probe an address chosen by the thing being scanned. In the
web application that is precisely what `webapp/ssrf.py` exists to prevent: a
stranger submits a URL, the guard resolves and pins it, and every request the
scan makes goes to the address that was vetted. A probe aimed at a hostname
read out of the target's own response would walk straight past that guard -
one `urlsrc` pointing at `169.254.169.254` or an internal address, and the
public service becomes a request forwarder. The pinning would not even fail
loudly; it would simply be bypassed for that one request.

## Decision

The scan probes the origin it was pointed at, and no other. A collaboration
backend is measured where a reverse proxy publishes it beside OpenCloud on
that same origin, and nowhere else.

`/hosting/discovery` is the detector, and it is the only path asked for
unconditionally. It is identified by shape rather than by status code: the
body must contain the `wopi-discovery` root element the WOPI protocol
specifies. OpenCloud's frontend answers unknown paths with its single-page
shell and HTTP 200, so a check that trusted the code would find a
collaboration backend on every instance in existence - the same trap
`securityTxtPublished` was written around (ADR 0034).

Two findings follow, and only once that document has proved a backend is
there:

- `companionAdminConsole` (`high`) - the editor's administration console
  answers at `/browser/dist/admin/admin.html`. The catch-all comparison here
  is response length alone; the second rule `_looks_like_catch_all` applies -
  that an HTML answer is the frontend rather than the file - is right for the
  deployment files it guards and wrong here, where the console *is* HTML.
- `companionEditorHttps` (`high`) - every `urlsrc` the discovery document
  advertises uses HTTPS. Read with a regular expression rather than an XML
  parser: the document comes from a host the scan has no reason to trust, the
  attribute is named by the WOPI specification, and a scheme is all that is
  wanted from it.

**Where no backend is published on this origin, neither finding is emitted at
all.** Not a pass - an absence. The common deployment puts the editor on a
host of its own, where this scan has no business probing, and a pass there
would tell an operator their console is protected when nothing checked it.

## Consequences

The findings are available exactly where the scan can honestly reach: a
single-origin deployment, which is what `docker compose` produces and what
the reverse-proxy guides describe. A deployment that serves its editor from
`collabora.example.com` gets no companion findings, and that gap is
deliberate - the operator can point a second scan at that host, which is a
scan they asked for rather than one the target arranged.

The common case costs one extra request. The discovery document is fetched on
its own first, and the console and catch-all control are only asked for once
it has answered as a WOPI document, so an instance with no backend on its
origin pays one request rather than three.

`_integrations` is unchanged and still reports what the instance says about
itself. These findings say what the deployment publishes, which is a
different question with a different source.

## Alternatives considered

**Follow the editor host named in the discovery document.** The only way to
reach the majority of real deployments, and the reason it is refused is in
the Context: it makes the scanner probe an address the scanned host chose,
which defeats the SSRF pinning the public service depends on. A scanner that
can be aimed by its target is not a scanner anybody should run against a
stranger's URL.

**Take an explicit `--companion-url` flag.** Honest about where the second
service is, and it moves the choice back to the operator - but it is a new
setting on every layer (plugin flag, subcommand, wizard, web request field,
documentation), and the web application would have to refuse it anyway, since
a request there chooses *what* to scan and never gains a second target. If
the demand appears, a second scan aimed at that host is already the answer.

**Match the console by a branding string in its body.** Would catch a console
served on a path this ADR does not name, but it means asserting what a body
contains for software whose exact response cannot be verified here - and a
signature that is subtly wrong produces a check that silently never fires,
which is worse than not having one. Length against the catch-all control is
measurable from what the instance actually returns.

**Probe OnlyOffice's `/info/info.json` and similar vendor endpoints too.**
Same objection: their response shapes are vendor details rather than protocol
guarantees. `/hosting/discovery` is specified by WOPI and implemented by both
editors, so one spec-grounded detector covers them where four guessed ones
would not.
