## check-opencloud-security 1.20.0

### Added

- **The collaboration backend beside an instance is now looked at, not just
  counted.** The scanner has always reported *that* an office integration
  exists, because the instance names its own app providers. It never asked
  what that second service publishes - and a document editor is a second HTTP
  server, with an administration console listing every open document session
  and a transport of its own. Where a reverse proxy serves that backend on the
  instance's own origin, two findings now follow: `companionAdminConsole`
  (high) when the editor's console answers from the internet, and
  `companionEditorHttps` (high) when the WOPI discovery document advertises
  editor addresses over plain HTTP, which sends the document and the token
  authorising the session unencrypted.

  The backend is detected by the `wopi-discovery` root element the WOPI
  protocol specifies rather than by a status code, because OpenCloud answers
  unknown paths with its own HTML shell and a check that trusted the code
  would find an editor on every instance in existence.

  **The scan asks the origin it was pointed at and nothing else.** It
  deliberately does not follow the editor host named inside the discovery
  document: that would let a scanned instance choose the next address the
  scanner connects to, walking straight past the SSRF pinning the public
  service depends on. A deployment serving its editor from a host of its own
  therefore gets neither finding rather than a pass, because nothing was
  measured - point a second scan at that host. See
  [ADR 0036](adr/0036-a-companion-service-is-probed-only-where-the-scan-was-pointed.md).

- **`tlsDnssec`: whether the zone answering for this name is signed.**
  Everything else the scan concludes about the transport starts from an
  address a resolver handed over. In an unsigned zone that answer carries no
  signature, so one forged on the way to the resolver cannot be told apart
  from the real one - and the CAA record restricting who may issue a
  certificate for the name arrives over the same channel and can be forged
  along with the address it protects.

  The check queries the resolver this machine already uses, read from
  `/etc/resolv.conf` and never a public one, for the same reason the CAA
  lookup does: asking 1.1.1.1 would hand a third party the hostname being
  scanned. It is a low finding, and a zone that is signed but read through a
  non-validating resolver passes - whether the operator signed their zone is
  the part this scan is entitled to judge.

  **A resolver that does not speak DNSSEC leaves the finding out of the result
  entirely**, rather than reporting the zone as unsigned. The two produce
  identical silence, and treating the second as the first would fail every
  scan run from behind such a resolver for a reason that has nothing to do
  with the instance being scanned. See
  [ADR 0038](adr/0038-a-dnssec-answer-nobody-could-have-given-is-not-a-finding.md).

- **`hstsPreloadEligible`: whether the `preload` directive would actually be
  honoured**, under `setup.advisoryChecks`. `hstsPreload` reports whether the
  header *asks* to be preloaded, which is an intention rather than a state - a
  host is protected before its first request only if it is really in the
  browser preload list, and the list only accepts a header carrying a max-age
  of at least a year, `includeSubDomains` and `preload` together.

  OpenCloud's own proxy sends ten years and `preload` but no
  `includeSubDomains`, so the header on every stock instance asks for
  something the list refuses. That makes the shortfall a fact about OpenCloud
  rather than about any one deployment, which is why it is an advisory
  observation - measured, explained by `--debug` and catalogued, never
  counted, never alerted on and never offered as a waiver.

  Membership of the list itself is deliberately not measured: the only ways to
  know are to ask a third party, which would leak the scanned hostname, or to
  ship tens of megabytes of the list in a plugin meant to stay small on a
  monitoring host. See
  [ADR 0037](adr/0037-preload-eligibility-is-measured-list-membership-is-not.md).

- **The plugin now ships as a `.deb` and an `.rpm`, built from the same wheel
  and attached to every release.** Its audience is monitoring hosts, and on
  those `apt install` and `dnf install` are how software arrives - a pip
  install has no entry in the package database, so it is absent from the
  inventory, missed by the unattended-upgrade job that patches everything else
  and unanswerable to whoever inherits the host. Both packages are
  architecture-independent, so one file fits every release of a distribution.

  The check lands on `PATH` and in the monitoring plugin directory
  (`/usr/lib/nagios/plugins` on Debian, `/usr/lib64/...` on RPM systems), so an
  Icinga2 `CheckCommand` built on `PluginDir` needs no path configuration.

  **The package configures nothing and enables nothing.** It creates
  `/etc/check-opencloud-security/` and leaves it empty, and the example
  configuration ships as documentation: that example names a host that is not
  yours, and the path it would occupy is one the plugin genuinely reads, so
  installing it would give every invocation on that host a default target
  nobody chose. The four systemd units install disabled for the same reason.

  The payload is the wheel unpacked into one private directory rather than
  files in the system's `site-packages`, which cannot then collide with a pip
  install of the same name on the same host. The two commands are small
  launchers that find a Python 3.10 or newer for themselves - RHEL 9 answers
  3.9 to `python3` and carries 3.11 and 3.12 beside it under their own names -
  and exit **3 (UNKNOWN)** rather than a verdict when none is usable, because
  a check that could not run has measured nothing.

  `--upgrade-self` now refuses on such an installation and names `apt` or
  `dnf`. That is not politeness: pip would appear to succeed, installing into
  a `site-packages` the launcher never reads, leaving two versions on the host
  and the old one still running. See
  [ADR 0039](adr/0039-the-plugin-ships-as-a-distribution-package-built-from-the-wheel.md)
  and [Installing the plugin](docs/installation.md#debian-ubuntu-rhel-fedora-deb-and-rpm).

### Changed

- The DNS wire format the CAA lookup speaks now lives in
  `opencloud_local_scan/dns.py`, where the DNSSEC lookup shares it rather than
  carrying a second copy of it. `caa.py` keeps its behaviour, its identifier
  and its refusal to query any resolver the operator did not already choose.

### Fixed

- **An advisory patched on two release lines is now matched on both of them,
  whichever format it arrives in.** The GitHub Advisory API writes one
  `vulnerabilities` entry per affected range, so an issue fixed in *both*
  `4.0.3` and `5.0.2` arrives as two entries for the same package. The
  converter stopped at the first one, which cleared every instance on the other
  line: a `5.0.1` server was told no advisory matched it, and the instances
  that *were* flagged were pointed at the fix for a line they are not on. Every
  bounded range is now kept, exactly as the OSV converter beside it already
  did, and `for_version` reports the fix belonging to the installed line. The
  bundled database is generated from OSV and is unaffected; this is the path an
  operator takes with `--vulnerability-db` or `--vulnerability-feed` pointed at
  a GitHub-format document.

- **An advisory whose lower bound is exclusive no longer reports the one release
  it excludes.** `>= 7.0.0` and `> 7.0.0` were read alike, so an advisory that
  went out of its way to say `7.0.0` is not affected produced a finding on
  exactly that release - one no upgrade can clear, because the installed
  version is already the one the advisory considers safe. The bound now moves
  just past the named release, the way an inclusive upper bound already moved
  just past its own.

- **An upgrade recommendation cannot point backwards.** A release line the
  schedule has no record of - dropped from the lifecycle page as it aged, or
  never published there - is judged end of life, and the release to move to was
  read off the declared track alone. The newest release recorded for a track can
  be *older* than a version that is not in the schedule at all, so an LTS
  instance on `5.0.0` was told to "upgrade" to `4.0.8`: advice that removes
  fixes rather than adding them. The verdict now names the newest release that
  is genuinely ahead of the installed one, and no arrow at all when there is
  none. Where the arrow already pointed forwards nothing changes.

- **A `q=nan` in `Accept-Language` no longer decides which language a page is
  written in.** It parses as a float and then compares false against every
  other weight, so the sort that orders a browser's language list - and with it
  the language served - followed whichever comparisons Python happened to make
  rather than the header. A weight that is not a weight is now dropped like an
  unparsable one, while a client that overshoots the range with `q=1.5` is
  still understood as meaning "this one first".

- **A `--webhook-url` the plugin cannot parse is refused instead of raising.**
  An unclosed IPv6 literal is a URL `urlsplit` rejects, and the rejection
  happened inside the log call that was explaining why the webhook had been
  blocked - so a typo in the flag replaced the check's own result with a
  traceback, which for a monitoring plugin is the one output that says nothing.
  Redaction now answers `<redacted>` for a URL it cannot read, the delivery
  fails as a delivery failure, and the scan result is still reported.
