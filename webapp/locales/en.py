"""
The English source strings.

This catalogue is the original: every other language is a translation of what
is written here, and a key that does not exist here does not exist at all.
The identifiers read ``page.element`` so that a template says what it wants
rather than what it says, and so that a sentence can be rewritten without
touching markup in four places.

A value may contain the inline markup that belongs to the sentence -
emphasis, a code span, a link - and templates render those with ``t.html``.
Anything interpolated into one is escaped on the way in.

What is deliberately *not* here: identifiers, versions, certificate subjects,
error text from a scanned host and every other piece of measured evidence.
The scanner reports those, this layer only labels them.
"""

from __future__ import annotations

MESSAGES: dict[str, str] = {
    # ---------------------------------------------------------------- site
    # ------------------------------------------------- the operator's area
    # Served only where COS_WEB_ADMIN_ENABLED asked for it, behind an
    # authentik sign-in, and never indexed. Kept in the catalogue like every
    # other page so the area is translated rather than the one English
    # corner of a localized service.
    "admin.title": "Operator area",
    "admin.description": "Service state, reference data and the audit trail.",
    "admin.kicker": "Operations",
    "admin.band": "Operator area - signed in as {user}",
    # Shown only where COS_WEB_ADMIN_SIGN_OUT_URL named where the provider in
    # front ends its session. This service has none of its own to end.
    "admin.band.signout": "Sign out",
    "admin.lede": (
        "What this deployment is doing, what it knows, and the two refreshes "
        "the worker otherwise runs once a day. Nothing here can be asked about "
        "a particular scan."
    ),
    "admin.noscript": (
        "The readings above are filled in by JavaScript. Without it, reload the "
        "page to see the current ones; both refresh buttons still work."
    ),
    "admin.state.kicker": "Now",
    "admin.state.heading": "Service state",
    "admin.state.lede": (
        "Counts and configured limits. No target, uuid or client address "
        "appears here, because none of them is kept where this could read it."
    ),
    "admin.state.worker": "Worker",
    "admin.state.worker.up": "Running",
    "admin.state.worker.down": "Not answering",
    "admin.state.queue": "{depth} queued, {workers} workers",
    "admin.state.ratelimit": "Rate limit",
    "admin.state.ratelimit.value": "{limit} per {window}s",
    "admin.state.cooldown.value": "{seconds}s per target",
    "admin.state.schedule": "Release schedule",
    "admin.state.advisories": "Advisories",
    "admin.state.checked": "checked {when}",
    "admin.state.never": "never",
    "admin.state.unknown": "unknown",
    "admin.state.age.seconds": "Read {seconds}s ago",
    "admin.state.age.minutes": "Read {minutes}m ago",
    "admin.state.age.waiting": "Waiting for the first reading",
    "admin.state.stale": (
        "The service has not answered for a while. What is above is the last "
        "reading it gave, not necessarily what is true now."
    ),
    "admin.state.refresh": "Read again",
    "admin.state.copy": "Copy diagnostics",
    "admin.state.copy.done": "Copied",
    "admin.state.copy.failed": "Could not copy",
    "admin.actions.kicker": "Reference data",
    "admin.actions.heading": "Refresh what the scanner rates against",
    "admin.actions.lede": (
        "The same two refreshes the worker runs daily, with the same rules: a "
        "schedule that lost a release line is refused, an advisory database "
        "only ever gains entries, and a failed fetch changes nothing."
    ),
    "admin.actions.schedule": "Sync release schedule",
    "admin.actions.schedule.hint": "Re-reads the published lifecycle page.",
    "admin.actions.advisories": "Check for advisories",
    "admin.actions.advisories.hint": "Asks the advisory feed for new entries.",
    "admin.outcome.updated": "Updated. The new document is in use.",
    "admin.outcome.unchanged": "Already current - nothing changed.",
    "admin.outcome.rejected": (
        "Refused: what was fetched did not pass the guards, so the previous "
        "data is still in use."
    ),
    "admin.outcome.failed": "Could not be fetched. Nothing changed.",
    "admin.outcome.disabled": "That refresh is switched off in this deployment's settings.",
    "admin.outcome.cooldown": "Just ran. Try again in {seconds}s.",
    "admin.probe.action": "Test the sources",
    "admin.probe.hint": (
        "Reads both sources and reports what a refresh would make of them. "
        "Nothing is stored."
    ),
    "admin.probe.schedule": "Release schedule: {answer}",
    "admin.probe.advisories": "Advisories: {answer}",
    "admin.probe.usable": "read, and a refresh would accept it",
    "admin.probe.rejected": "read, but the guards would refuse it",
    "admin.probe.unreadable": "could not be read - unreachable, or no longer in the expected shape",
    "admin.probe.disabled": "not checked - this refresh is switched off",
    "admin.search.kicker": "Search index",
    "admin.search.heading": "Is the shipped index still current",
    "admin.search.lede": (
        "The index is built at release time and shipped read-only, so this "
        "reports rather than rebuilds. It compares the pages, the languages "
        "and the release it was generated for - not the body text, which only "
        "the generator can extract."
    ),
    "admin.search.fresh": "Current",
    "admin.search.stale": "Out of date",
    "admin.search.detail.ok": "Every page and language is indexed for this release.",
    "admin.search.detail.release": "Built for {built}, running {running}.",
    "admin.search.detail.missing": "Not indexed: {list}.",
    "admin.search.detail.changed": "{count} page titles or summaries have changed since it was built.",
    "admin.search.detail.unreadable": "The index could not be read.",
    "admin.search.fix": (
        "A stale index is refreshed by the release workflow, which regenerates "
        "it and commits it. There is nothing to press here."
    ),
    "admin.audit.kicker": "Audit",
    "admin.audit.heading": "The trail, as it is written",
    "admin.audit.lede": (
        "Scan requests, rejections and triggered limits, arriving as they "
        "happen. Following starts a connection; nothing is streamed until you "
        "ask for it."
    ),
    "admin.audit.privacy": (
        "A client address is a truncated HMAC under a salt this process holds, "
        "and nothing maps one back to an address. This view cannot show more "
        "than the audit log already decided to write down."
    ),
    "admin.audit.replicas": (
        "This deployment keeps no audit file, so these records come from the "
        "memory of the one process that answered - behind more than one "
        "replica, that is a part of the trail rather than all of it."
    ),
    "admin.audit.follow": "Follow",
    "admin.audit.stop": "Stop",
    "admin.audit.clear": "Clear",
    "admin.audit.empty": "Nothing yet.",
    "admin.audit.closed": (
        "The connection reached its {minutes}-minute limit and was closed by "
        "the service. Nothing was missed before that; press Follow to start "
        "another."
    ),
    "admin.audit.disabled": (
        "This deployment does not keep an audit trail, so there is nothing to "
        "follow. COS_WEB_AUDIT_LOG switches it on."
    ),
    "admin.audit.state.off": "Not following",
    "admin.audit.state.live": "Live",
    "admin.audit.state.reconnecting": "Reconnecting",
    "admin.audit.state.unsupported": "Not supported by this browser",
    "admin.audit.state.closed": "Closed by the service",
    "admin.audit.state.disabled": "Not kept",
    "site.og_image_alt": (
        "OpenCloud Security Scan - check an instance for known vulnerabilities, "
        "missing hardening and weak security headers"
    ),
    # ------------------------------------------------------- header chrome
    "chrome.skip_to_content": "Skip to content",
    "chrome.brand": "Security scan for OpenCloud",
    "chrome.menu": "Menu",
    "chrome.nav.primary": "Primary",
    "chrome.nav.secondary": "Secondary",
    "chrome.search.label": "Search documentation",
    "chrome.search.placeholder": "Search",
    "chrome.theme.toggle": "Toggle colour theme",
    "chrome.back_to_top": "Back to top",
    "nav.new_scan": "New scan",
    "nav.how_it_works": "How it works",
    "nav.grades": "Grades",
    "nav.catalogue": "Catalogue",
    "nav.docs": "Docs",
    "nav.search": "Search",
    "nav.api": "API",
    "nav.ai": "AI",
    "nav.privacy": "Privacy",
    "nav.about": "About",
    # --------------------------------------------------- language switcher
    "lang.region": "Language",
    "lang.label": "Page language",
    "lang.apply": "Change language",
    "lang.note": "The scan itself is unchanged; only this page is translated.",
    # ------------------------------------------------------------- footer
    "footer.note.title": "A quiet service, by design.",
    "footer.note.body": (
        "Scans run from this server against the address you enter. Results live "
        "in memory for {minutes} minutes and are then gone. Built on the "
        "<code>check-opencloud-security</code> scanner - no trackers, no "
        "accounts, no analytics."
    ),
    "footer.note.run_yourself": "Run it yourself",
    "footer.version.title": "The scanner version that produced these results",
    "footer.version.label": "Backend v{version}",
    "footer.legal.scope": (
        "<strong>This check is not exhaustive, and a good grade is not a "
        "certificate.</strong> It reads what a publicly reachable OpenCloud "
        "instance shows an anonymous visitor: its version, the advisories "
        "against that version, its transport, its headers and a set of "
        "settings that are visible without logging in. An &ldquo;A&rdquo; "
        "means none of those went wrong - not that the instance is secure. "
        "Everything behind the login, the server it runs on, the network "
        "around it, the data in it and the people with accounts on it are "
        "outside what any unauthenticated scan can see. Treat the result as "
        "one input among several, never as a security audit or a penetration "
        "test."
    ),
    "footer.legal.trademark": (
        "This is an independent community project. It is not affiliated with "
        "OpenCloud GmbH and is neither recommended nor supported by the "
        "company. &ldquo;OpenCloud&rdquo;, the OpenCloud logo and all "
        "associated trademarks are the property of their respective owners and "
        "are used here solely to indicate which software this tool checks."
    ),
    # --------------------------------------------------- the contents list
    "toc.heading": "On this page",
    "toc.aria": "On this page",
    # --------------------------------------------------------- cross-links
    "pagenav.kicker": "Read on",
    "pagenav.aria": "More about this service",
    "pagenav.how.title": "How the scan works",
    "pagenav.how.blurb": (
        "What gets tested, and the four steps between the button and the grade."
    ),
    "pagenav.grades.title": "What the grades mean",
    "pagenav.grades.blurb": (
        "Every step from A+ to F, what holds a grade down and how to move it up."
    ),
    "pagenav.catalogue.title": "What the scanner checks",
    "pagenav.catalogue.blurb": (
        "Every hardening flag, header and TLS check, and every known advisory - "
        "independent of any one scan."
    ),
    "pagenav.docs.title": "CLI documentation",
    "pagenav.docs.blurb": "Install, configure and automate the scanner from a terminal.",
    "pagenav.api.title": "Scanning from a script",
    "pagenav.api.blurb": "The JSON API, the fair use limits and the OpenAPI schema.",
    "pagenav.ai.title": "For AI agents",
    "pagenav.ai.blurb": "Discovery, OpenAPI, Arazzo workflows and the MCP endpoint.",
    "pagenav.privacy.title": "What this server keeps",
    "pagenav.privacy.blurb": (
        "In memory, for {minutes} minutes, and what the log leaves out."
    ),
    "pagenav.about.title": "About OpenCloud",
    "pagenav.about.blurb": (
        "The platform this checks, and why this project is independent of it."
    ),
    "pagenav.cta.title": "Scan an instance",
    "pagenav.cta.blurb": "Back to the form. Takes a few seconds, no sign-up.",
    # ---------------------------------------------------------------- 404
    "notfound.title": "Nothing here",
    "notfound.description": (
        "The address does not exist, or the scan it pointed at has already "
        "expired."
    ),
    "notfound.kicker": "Not found",
    "notfound.lede": (
        "Either the address does not exist, or it was a scan and that scan is "
        "gone: results are held for {minutes} minutes and then dropped, so a "
        "link from earlier today will not open. An identifier that never "
        "existed looks exactly the same from here - this service cannot tell "
        "you which, and deliberately does not try."
    ),
    "notfound.action": "Run a new scan",
    # ------------------------------------------------------- landing page
    "index.title": "OpenCloud Security Scanner",
    "index.description": (
        "Check an OpenCloud instance for known vulnerabilities, missing "
        "hardening, weak security headers, and a pending update. Free, "
        "independent and nothing is stored."
    ),
    "index.eyebrow": "Independent &middot; air-gapped &middot; nothing stored",
    "index.headline": 'OpenCloud <em class="swash">Security Scanner</em>',
    "index.lede": (
        "Enter the address of an instance you are responsible for. This server "
        "talks to it over HTTPS the way any visitor would, reads what it "
        "publishes without logging in, and grades the result from "
        "<strong>A+</strong> to <strong>F</strong>."
    ),
    "index.form.kicker": "Scan request",
    "index.form.hint": "A few seconds &middot; no sign-up",
    "index.error.self_host": (
        "No hard feelings - the limits are what keep this small service on its "
        "feet. The scanner is open source, so you can run this exact check "
        "yourself, as often as you like:"
    ),
    "index.field.label": "Address of the instance",
    "index.field.title": (
        "The instance base address: a hostname, optional port, and optional "
        "plain subfolder. No query, fragment, parameters, escapes or traversal."
    ),
    "index.field.hint": (
        "Just the hostname is enough - <code>https://</code> is assumed. A "
        "subfolder such as <code>/opencloud</code> is supported; queries, "
        "fragments, parameters and path traversal are refused. Public addresses "
        "only, and only instances you run or have permission to test."
    ),
    "index.field.invalid": (
        "Not a valid address: a hostname, optional port and a plain subfolder - "
        "no query, fragment or parameters."
    ),
    "index.submit": "Start audit",
    "index.submit.busy": "Starting audit...",
    "index.track.label": "Release track",
    "index.track.hint": (
        "Decides how long this release is supported and which one it is told to "
        "upgrade to."
    ),
    "index.format.label": "Show me",
    "index.format.dashboard": "A dashboard",
    "index.format.json": "The raw JSON",
    "index.format.hint": "Both come from the same scan.",
    "index.waivers.summary": "Ignore specific checks (optional)",
    "index.waivers.selected": "Ignore specific checks ({count} selected)",
    "index.waivers.hint": (
        "A waived check stays in the report and is still shown - it just stops "
        "holding the grade down. Only checks that actually failed can be waived."
    ),
    "index.waivers.search.label": "Filter checks",
    "index.waivers.search.placeholder": "Search by name...",
    "index.waivers.search.empty": "No checks match your search.",
    "index.assurance.aria": "How this service handles your data",
    "index.assurance.airgapped.title": "100% air-gapped",
    "index.assurance.airgapped.body": (
        "Every byte comes from this origin. No CDN, no font service, no analytics."
    ),
    "index.assurance.nostore.title": "No data stored",
    "index.assurance.nostore.body": (
        "The result lives in memory and is dropped the moment it expires."
    ),
    "index.assurance.noaccount.title": "No registration needed",
    "index.assurance.noaccount.body": (
        "No account, no sign-up, no email address, no waiting."
    ),
    "index.assurance.ephemeral.title": "Ephemeral results",
    "index.assurance.ephemeral.body": (
        "The link stops working {minutes} minutes after the scan."
    ),
    # -------------------------------------------- release tracks and waivers
    "track.auto.label": "Detect automatically",
    "track.auto.description": (
        "Work the track out from the release the instance reports."
    ),
    "track.rolling.label": "Rolling",
    "track.rolling.description": "A new release roughly every three weeks.",
    "track.production.label": "Production",
    "track.production.description": (
        "Supported for about six months. The usual choice."
    ),
    "track.lts.label": "LTS",
    "track.lts.description": "Supported for two years.",
    "waivers.group.hardening": "Hardening",
    "waivers.group.headers": "Headers",
    "waivers.group.checks": "Checks",
    # ------------------------------------------------------------ severity
    "severity.critical": "critical",
    "severity.high": "high",
    "severity.medium": "medium",
    "severity.low": "low",
    # ------------------------------------------------------------ category
    "category.transport": "Transport & TLS",
    "category.cookies": "Cookies",
    "category.headers": "Security headers",
    "category.authentication": "Authentication & accounts",
    "category.sharing": "Sharing & links",
    "category.exposure": "Network exposure",
    "category.embedding": "Embedding",
    "category.lifecycle": "Version & lifecycle",
    "category.proxy": "Identity provider & proxy",
    # --------------------------------------------------------- grade scale
    "grade.5.headline": "Nothing found",
    "grade.5.meaning": (
        "The release is current for its track, no advisory matches the version, "
        "and every check the scan could run passed."
    ),
    "grade.5.improve": (
        "Keep it here: watch for the next release on your track, and re-run the "
        "scan after any change to the reverse proxy or the sign-in."
    ),
    "grade.4.headline": "An update is waiting",
    "grade.4.meaning": (
        "A newer patch release exists on the same release line. Nothing is known "
        "to be wrong with the installed one - it is simply not the latest."
    ),
    "grade.4.improve": (
        "Install the pending update. It is the same release line, so it is the "
        "smallest upgrade there is."
    ),
    "grade.3.headline": "A release line behind",
    "grade.3.meaning": (
        "The instance runs an older line than the current one for its track. It "
        "may still be supported, but it is no longer where the fixes land first."
    ),
    "grade.3.improve": (
        "Move up to the current line for your track. The scan names which one "
        "that is, and never points at a track you did not choose."
    ),
    "grade.2.headline": "Advisories match this version",
    "grade.2.meaning": (
        "The installed version appears in the advisory database. None of the "
        "matching advisories is rated critical or high, which is the only reason "
        "this is not lower."
    ),
    "grade.2.improve": (
        "Upgrade to the fixed version for your release line. The result page "
        "names it - one advisory can be patched separately on several lines."
    ),
    "grade.1.headline": "A critical or high advisory matches",
    "grade.1.meaning": (
        "At least one advisory matching the installed version is rated critical "
        "or high. This is a known way in, published and fixed."
    ),
    "grade.1.improve": (
        "Upgrade now, before anything else on the page. Nothing else that can be "
        "changed will raise the grade above this."
    ),
    "grade.0.headline": "Out of support",
    "grade.0.meaning": (
        "The release line receives no security fixes at all. This overrides every "
        "other signal, including a waiver: an instance nobody patches cannot be "
        "graded on how tidy its headers are."
    ),
    "grade.0.improve": (
        "Move to a supported release line. Which lines are supported, and for how "
        "long, is on the release schedule the scan reads."
    ),
    # ---------------------------------------------------------- grades page
    "grades.title": "What the grades mean",
    "grades.description": (
        "A+, A, C, D, E and F: what each grade says about an OpenCloud instance, "
        "what holds one down, and the shortest way to the next one up."
    ),
    "grades.kicker": "The scale",
    "grades.lede": (
        "Every scan ends in one letter. It is worked out from two things - which "
        "release the instance runs, and which checks failed - and this page is "
        "the whole of that arithmetic, in the order the scanner does it."
    ),
    "grades.scale.kicker": "Six steps",
    "grades.scale.heading": "The scale, best first",
    "grades.scale.intro": (
        "The <strong>0-5</strong> scale and its letters are the ones "
        "<code>scan.nextcloud.com</code> made familiar, kept deliberately so that "
        "an existing threshold, graph or alert rule keeps its meaning. That is "
        "also why there is no <strong>B</strong>: the scale skips it, and "
        "inventing one here would make two numbers mean the same grade."
    ),
    "grades.row.prefix": "Grade {label}: ",
    "grades.row.score": "{rating} out of 5",
    "grades.row.improve": "To move up:",
    "grades.caps.kicker": "The ceiling",
    "grades.caps.heading": "What a failed check can do to a grade",
    "grades.caps.intro": (
        "The version sets the starting grade. Failed checks cannot raise it - "
        "they can only hold it down, and how far depends on the severity of the "
        "worst one that failed:"
    ),
    "grades.caps.at_best": "at best",
    "grades.caps.shared": (
        "Findings of the same severity share one ceiling, so fixing one of three "
        "medium findings moves nothing until the last of them is gone. That is "
        "why the result page orders the plan the way it does, and why it prints "
        "the grade each step would actually reach."
    ),
    "grades.caps.rules": (
        "Two rules sit above all of this. <strong>End of life overrides "
        "everything</strong>, including a waiver: a release line that receives no "
        "security fixes is an <strong>F</strong> no matter how clean the rest of "
        "the report is. And <strong>being ahead of your track is not being behind "
        "it</strong> - a release newer than the current one for the track you "
        "declared is reported as ahead and never graded as unsupported."
    ),
    "grades.improve.kicker": "The shortest route",
    "grades.improve.heading": "How this scanner helps you climb",
    "grades.improve.intro": (
        "A grade on its own is a scoreboard, which is not much use at four in the "
        "afternoon. Every result page also carries the four things that turn it "
        "into an afternoon's work:"
    ),
    "grades.improve.plan": (
        "<strong>A remediation plan, in payoff order.</strong> Each step says what "
        "to change and which grade the instance would hold once that step and "
        "everything above it is done - so you can stop where the return does."
    ),
    "grades.improve.release": (
        "<strong>The exact release to move to.</strong> Not \"upgrade\": the "
        "version that fixes the advisory <em>on the line you are actually on</em>, "
        "and never a jump onto a track you did not choose."
    ),
    "grades.improve.explained": (
        "<strong>Every failed check, explained.</strong> What was measured, why it "
        "matters and the fix, with a link to the OpenCloud documentation for the "
        "setting behind it."
    ),
    "grades.improve.waiver": (
        "<strong>A waiver for the ones you have decided to live with.</strong> A "
        "waived check stays in the report and stays visible - it simply stops "
        "capping the grade, so a considered decision does not read as a failure "
        "for ever. It cannot hide a check that is passing, and it cannot rescue an "
        "end-of-life release."
    ),
    "grades.improve.rerun": (
        "Run it again afterwards. The same instance, the same scan, and the letter "
        "moves - which is the only proof that any of it worked."
    ),
    "grades.limits.kicker": "Honesty",
    "grades.limits.heading": "What a good grade is not",
    "grades.limits.body": (
        "An <strong>A+</strong> means nothing this scan looked at went wrong. It "
        "is not a certificate, and it is not a penetration test. Everything behind "
        "the login, the operating system, the container runtime, the backups, the "
        "accounts and the people who hold them are outside what an unauthenticated "
        "scan can see. Treat the letter as one input among several - "
        '<a href="/how-it-works">how the scan works</a> lists what it reads, and '
        "every result page repeats the limits underneath the grade."
    ),
    # -------------------------------------------------------------- catalogue
    "catalogue.title": "What the scanner checks",
    "catalogue.description": (
        "Every hardening flag, security header, TLS check and known advisory "
        "this scanner can report, independent of any single scan result."
    ),
    "catalogue.kicker": "Reference",
    "catalogue.lede": (
        "This is the whole set: every check below can appear on a result page, "
        "and every advisory below is one a scan is rated against. Nothing here "
        "depends on a particular instance."
    ),
    "catalogue.checks.kicker": "Checks",
    "catalogue.checks.heading": "Every check, by category",
    "catalogue.checks.lede": (
        "Grouped by what they are about rather than how badly they can fail - "
        "severity depends on the instance being scanned, so it is not shown here."
    ),
    "catalogue.checks.not_configurable": "not configurable",
    "catalogue.advisories.kicker": "Advisories",
    "catalogue.advisories.heading": "Known advisories",
    "catalogue.advisories.lede": (
        "Every advisory in the database a scan is rated against, refreshed "
        "daily from the public feed."
    ),
    "catalogue.advisories.empty.tag": "None known",
    "catalogue.advisories.empty.body": "The advisory database is currently empty.",
    "catalogue.advisories.fixed_in": "Fixed in {version}",
    "catalogue.advisories.unfixed": "No fix published yet",
    # -------------------------------------------------- how the scan works
    "how.title": "How the scan works",
    "how.description": (
        "What this scanner tests on an OpenCloud instance, and what happens "
        "between pressing the button and reading the grade."
    ),
    "how.kicker": "The method",
    "how.lede": (
        "Everything this service reports it works out itself, by talking to the "
        "address you enter over HTTPS the way any visitor would. Nothing is asked "
        "of a third party, and nothing is logged in."
    ),
    "how.tests.heading": "What gets tested",
    "how.tests.version.title": "Version and lifecycle",
    "how.tests.version.body": (
        "Which release is running, whether it still receives security fixes, and "
        "whether any published advisory matches it. A release past its end of "
        "life is an F, whatever else is right."
    ),
    "how.tests.transport.title": "Transport and headers",
    "how.tests.transport.body": (
        "HTTPS reachability, the certificate and its remaining life, the TLS "
        "versions on offer, and the security headers a browser is actually sent - "
        "HSTS, CSP, frame and content-type protection."
    ),
    "how.tests.hardening.title": "Hardening and exposure",
    "how.tests.hardening.body": (
        "Basic authentication, public link password and expiry policy, password "
        "rules, directory listing, exposed endpoints and anything announcing the "
        "version to the world."
    ),
    "how.pipeline.kicker": "The pipeline",
    "how.pipeline.heading": "What happens when you press the button",
    "how.pipeline.lede": "Four steps, and the third one is where the queue comes in.",
    "how.pipeline.step1": (
        "<strong>Your address is checked.</strong> Private, loopback and cloud "
        "metadata addresses are refused before anything connects."
    ),
    "how.pipeline.step2": (
        "<strong>A scan gets a random identifier.</strong> That identifier is the "
        "only way to reach the result. There is no list of scans, and no way to "
        "guess one."
    ),
    "how.pipeline.step3": (
        "<strong>It waits its turn.</strong> A fixed number of scans run at once. "
        "If they are all busy yours queues and you are told where you are in line "
        "- nothing is rejected because the service is popular."
    ),
    "how.pipeline.step4": (
        "<strong>The result expires.</strong> After {minutes} minutes the "
        "identifier stops working and the result is gone, with nothing written to "
        "disk."
    ),
    "how.faq.kicker": "Questions",
    "how.faq.heading": "Frequently asked",
    "how.faq.q1": "Is this official OpenCloud software?",
    "how.faq.a1": (
        "No. This is an independent community project, not affiliated with "
        "OpenCloud GmbH and neither recommended nor supported by that company. "
        '"OpenCloud" and its logo are trademarks of their respective owners, '
        "used here solely to name the software this tool checks."
    ),
    "how.faq.q2": "Does a good grade mean an instance is secure?",
    "how.faq.a2": (
        "No. The scan reads only what a publicly reachable instance shows an "
        "anonymous visitor - its version, the advisories against that version, "
        "its transport, its headers and a set of settings visible without "
        "logging in. Everything behind the login, the server it runs on, the "
        "network around it and the people with accounts on it are outside what "
        "any unauthenticated scan can see. Treat a result as one input, never "
        "as a security audit or a penetration test."
    ),
    "how.faq.q3": "How long do you keep a scan's result?",
    "how.faq.a3": (
        "In memory only, for {minutes} minutes, and then it is gone. No "
        "accounts, no analytics, no trackers - see "
        '<a href="/privacy">what this server keeps</a> for the rest.'
    ),
    "how.faq.q4": "Is there a rate limit?",
    "how.faq.a4": (
        "Yes, per visitor and per scanned target, so one busy visitor cannot "
        "crowd out another and the same instance is not scanned back to back. "
        'The exact numbers for this deployment are on the '
        '<a href="/api#api-limits">API page</a>.'
    ),
    "how.faq.q5": "Can I scan without a rate limit?",
    "how.faq.a5": (
        "Yes - the scanner is open source. Run it yourself with "
        '<a href="/cli">one Docker command</a> on your own machine, with no '
        "limit and no third party in the middle."
    ),
    "how.faq.q6": "Does a scan tell me about a pending OpenCloud update?",
    "how.faq.a6": (
        "Yes. Every scan compares the reported release against the OpenCloud "
        "release feed and reports a pending update or an unsupported release "
        "the same way it reports a missing header - see "
        '<a href="/documentation/reference#update-check">the update check</a> '
        "for how the recommended release is worked out."
    ),
    # --------------------------------------------------------------- privacy
    "privacy.title": "What this server keeps",
    "privacy.description": (
        "What is stored while a scan runs, for how long, and what the operational "
        "log does and does not record."
    ),
    "privacy.kicker": "Privacy",
    "privacy.lede": "Short answer: the scan, for {minutes} minutes, in memory.",
    "privacy.retention.kicker": "Retention",
    "privacy.retention.heading": "While a scan is alive",
    "privacy.retention.body": (
        "The address you submit, the checks you chose to waive and the result live "
        "in memory for {minutes} minutes, under a key derived from your scan's "
        "random identifier, and are then dropped by the store itself. The "
        "operational log records that a scan was created, started and finished, "
        "identified by that random identifier alone - not the address, not the "
        "result and not your IP address, which is only ever counted as a one-way "
        "fingerprint for rate limiting."
    ),
    "privacy.self_host": (
        "Prefer to run it yourself? The same scanner is a command line check and a "
        "Python package. Nothing here talks to a third-party service in either "
        "case."
    ),
    # ----------------------------------------------------------- legal notice
    "legal.title": "Legal Notice",
    "legal.description": (
        "Provider identification, contact details and disclaimers for the "
        "operator of this deployment."
    ),
    "legal.kicker": "Imprint",
    "legal.lede": (
        "Provider identification under German law, for the operator of this "
        "deployment."
    ),
    "legal.english_notice": (
        "This notice is the operator's own legal text and is available in "
        "English only. The page around it is translated; the text below is not."
    ),
    # ----------------------------------------------------------------- about
    "about.title": "About OpenCloud and this scanner",
    "about.description": (
        "What OpenCloud is, who makes it, and why this scanner is an independent "
        "community project."
    ),
    "about.kicker": "About",
    "about.lede": (
        "One is a file, sync and share platform. The other is a community check "
        "that looks at it from the outside."
    ),
    "about.platform.kicker": "The platform",
    "about.platform.heading": "About OpenCloud",
    "about.platform.body": (
        '<a href="https://opencloud.eu/" rel="noopener noreferrer">OpenCloud</a> '
        "is the file, sync and share platform this tool checks - open source, "
        "built in Germany, and documented at "
        '<a href="https://docs.opencloud.eu/" rel="noopener noreferrer">'
        "docs.opencloud.eu</a>, which is where every fix this scanner suggests is "
        "written up properly. Thanks to the people who make it."
    ),
    "about.platform.independent": (
        "This scanner is an independent community project. It is not affiliated "
        "with OpenCloud GmbH and is neither recommended nor supported by the "
        "company. &ldquo;OpenCloud&rdquo;, the OpenCloud logo and all associated "
        "trademarks are the property of their respective owners."
    ),
    "about.project.kicker": "The project",
    "about.project.heading": "About this scanner",
    "about.project.body": (
        "Everything you see here is produced by "
        "<code>check-opencloud-security</code>, a Nagios and Icinga plugin with a "
        "scanner library behind it. This page is one way to use it; a command on "
        "your own machine, with no rate limit and no queue, is the other."
    ),
    "about.project.origin": (
        "The project was created by <strong>Massoud Ahmed</strong> to give "
        "OpenCloud users an independent alternative to "
        "<code>scan.nextcloud.com</code>: a scanner built for OpenCloud's release "
        "tracks, settings and deployment model, which can run entirely on the "
        'operator\'s own machine. <a href="{project}" rel="noopener noreferrer">'
        "The project is on GitHub</a>."
    ),
    # ------------------------------------------------------------------- API
    "api.title": "Scanning from a script",
    "api.description": (
        "The JSON API behind the form: how to submit a scan, poll it, and what "
        "this server refuses to let a caller decide."
    ),
    "api.kicker": "The API",
    "api.lede": (
        "The form is one of two front doors; the other is JSON, and it is the same "
        "handler."
    ),
    "api.submit.kicker": "Submit & poll",
    "api.submit.heading": "Submit and poll",
    "api.submit.body": (
        "A submission answers <code>202</code> with the scan's identifier; polling "
        "it returns <code>queued</code>, <code>running</code> or the finished "
        "result, and <code>404</code> once it has expired. Only four fields are "
        "read - the address, the checks to waive, the release track and the output "
        "format. Anything else in the body, concurrency and timeouts above all, is "
        "rejected: how hard this server probes is not a caller's decision."
    ),
    "api.limits.kicker": "Fair use",
    "api.limits.heading": "Fair use",
    "api.limits.enforced": (
        "Fair use is enforced rather than requested: {client} submissions per "
        "{window} minute(s) from one address, and {cooldown}, both answered with "
        "<code>429</code> and a <code>Retry-After</code>."
    ),
    "api.limits.cooldown": "one scan per target every {minutes} minute(s)",
    "api.limits.no_cooldown": "no per-target cooldown",
    "api.limits.none": "This deployment sets no rate limit.",
    "api.limits.self_host": (
        "If you meet one and would rather not wait, the whole thing runs on your "
        'own machine: <a href="{project}" rel="noopener noreferrer">the project is '
        "on GitHub</a>."
    ),
    "api.schema.kicker": "The schema",
    "api.schema.heading": "The schema",
    "api.schema.body": (
        "The machine-readable documents are always public, on this deployment and "
        'on every other: the <a href="/openapi.json">OpenAPI 3.1 description</a> '
        'of every operation, and the <a href="/arazzo.json">Arazzo 1.0.1 '
        "workflows</a> that say how those operations combine into submitting a "
        "scan, waiting for it and taking the result away."
    ),
    "api.schema.docs_on": (
        'Both are browsable here as <a href="/docs">Swagger UI</a> and '
        '<a href="/redoc">ReDoc</a>, served from this server like everything else '
        "- nothing is fetched from anywhere."
    ),
    "api.schema.docs_off": (
        "The interactive viewers (Swagger UI at <code>/docs</code>, ReDoc at "
        "<code>/redoc</code>) are switched off on this deployment; an operator "
        "turns them on with <code>COS_WEB_ENABLE_DOCS=true</code>."
    ),
    "api.agents.kicker": "Agents",
    "api.agents.heading": "For AI agents",
    "api.agents.body": (
        "Software that was not written for this service has a page of its own: "
        '<a href="/ai">for AI agents</a> collects the discovery document, the '
        "OpenAPI schema, the Arazzo workflows and the MCP endpoint in one place."
    ),
    # -------------------------------------------------------------------- AI
    "ai.title": "For AI agents",
    "ai.description": (
        "Everything software needs to use this scanner without being written for "
        "it: the discovery document, the OpenAPI schema, the Arazzo workflows and "
        "the MCP endpoint."
    ),
    "ai.kicker": "Machine guests",
    "ai.lede": (
        "This service is meant to be usable by software that was not written for "
        "it. Everything an agent needs is published, in the open, without an "
        "account: what the API can do, how its calls combine into a task, and a "
        "way to run that task directly."
    ),
    "ai.discovery.kicker": "Discovery",
    "ai.discovery.heading": "Start from one address",
    "ai.discovery.discovery": (
        "<strong>Discovery</strong> - "
        '<a href="/.well-known/ai.json">/.well-known/ai.json</a> names all of the '
        "below, with absolute URLs. Start here."
    ),
    "ai.discovery.openapi": (
        '<strong>OpenAPI</strong> - <a href="/openapi.json">/openapi.json</a>, '
        "every operation with its real status codes and response shapes."
    ),
    "ai.discovery.arazzo": (
        '<strong>Arazzo workflows</strong> - <a href="/arazzo.json">/arazzo.json'
        "</a>, the lifecycle of a scan: submit, poll, detect completion, export."
    ),
    "ai.discovery.mcp": (
        "<strong>MCP</strong> - <code>{url}</code>, a Model Context Protocol "
        "endpoint over streamable HTTP. Tools: <code>scan_instance</code>, "
        "<code>scan_instances</code>, <code>get_scan_result</code>, "
        "<code>plan_remediation</code>, <code>export_scan</code> and "
        "<code>erase_instance_data</code>. <code>scan_instance</code> does the "
        "whole task - submission, waiting and result - in one call. Prompts name "
        "the jobs themselves, such as <code>audit_instance</code>, which audits an "
        "instance and writes the remediation plan, and "
        "<code>review_transport_security</code>, which looks only at the "
        "certificate and the handshake. It answers the protocol rather than a "
        "browser, so it is an address to configure rather than a page to open."
    ),
    "ai.discovery.summary": (
        "The three documents describe one service from three angles: OpenAPI says "
        "what the API can do, and Arazzo says how those operations combine into a "
        "task. They are generated from the same code the server runs, so none of "
        "them can quietly go out of date."
    ),
    "ai.discovery.summary_mcp": (
        "The three documents describe one service from three angles: OpenAPI says "
        "what the API can do, Arazzo says how those operations combine into a "
        "task, and MCP hands that task to an agent as a tool it can call. They are "
        "generated from the same code the server runs, so none of them can quietly "
        "go out of date."
    ),
    "ai.webmcp.kicker": "In the browser",
    "ai.webmcp.heading": "Use the page as a tool",
    "ai.webmcp.intro": (
        "A browser that supports the "
        '<a href="https://webmachinelearning.github.io/webmcp/" '
        'rel="noopener noreferrer">WebMCP draft</a> can discover actions from the '
        "page already open. There is no separate client to configure."
    ),
    "ai.webmcp.landing": (
        "On the landing page, <code>scan_opencloud_security</code> queues a scan. "
        "Its schema contains the release tracks, output formats and waiver "
        "identifiers offered by that page."
    ),
    "ai.webmcp.result": (
        "On a result page, <code>get_scan_result</code> reads the current scan and "
        "<code>export_scan_report</code> downloads JSON, CSV, SARIF or PDF for the "
        "uuid already being viewed."
    ),
    "ai.webmcp.boundary": (
        "Every browser tool calls the same JSON API with "
        "<code>Accept: application/json</code>. It keeps the SSRF guard, rate "
        "limits, target cooldown, queue and uuid isolation in place."
    ),
    "ai.webmcp.support": (
        "WebMCP is still a draft and is ignored by browsers that do not implement "
        "it. Turning MCP off for this deployment removes the browser tools too."
    ),
    "ai.clients.kicker": "Configuration",
    "ai.clients.heading": "Wiring it into a client",
    "ai.clients.intro": (
        "Most agent tools take a URL and a transport. This one is streamable HTTP, "
        "with no authentication and no account:"
    ),
    "ai.clients.body": (
        "Worked configuration for Claude Code, Claude Desktop, GitHub Copilot in "
        "VS Code and the CLI, Cursor, Zed and Windsurf - against this deployment or "
        'one of your own - is in <a href="{project}/blob/main/docs/mcp.md" '
        'rel="noopener noreferrer">the MCP guide</a>.'
    ),
    "ai.rules.kicker": "The rules",
    "ai.rules.heading": "The same rules as everybody else",
    "ai.rules.body": (
        "The rules are the same for an agent as for anybody else. A scan is "
        "asynchronous and the uuid is the only way back to it; a <code>429</code> "
        "is an invitation to slow down rather than a refusal; and if you are "
        "checking more than a handful of instances, please "
        '<a href="{project}" rel="noopener noreferrer">run the scanner yourself</a> '
        "- it is the same code, on your machine, with no limits."
    ),
    # -------------------------------- Docker one-liners, on /documentation
    "cli.lede": (
        "Handing an address to a stranger's server is a reasonable thing to "
        "hesitate over. You do not have to: this page is the same check, as one "
        "command on your own machine."
    ),
    "cli.oneliner.kicker": "The one-liner",
    "cli.oneliner.heading": "One command, nothing installed",
    "cli.oneliner.body": (
        "That is the whole thing. It prints the same verdict this site draws - the "
        "grade, the release lifecycle, the advisories and every failed check - and "
        "exits with the Nagios status code, so the same line works in a script, a "
        "pipeline or a cron job. Nothing is sent anywhere: the container talks to "
        "your instance and to nobody else."
    ),
    "cli.json.kicker": "As JSON",
    "cli.json.heading": "The whole result document",
    "cli.json.body": (
        "Every number on a result page comes out of this document, including the "
        "<code>addresses</code> block behind the <strong>Resolved to</strong> line "
        "- the IPv4 and IPv6 the name pointed at while the scan ran."
    ),
    "cli.private.kicker": "Your own network",
    "cli.private.heading": "The instances this site will not scan",
    "cli.private.body": (
        "A public service that would scan private addresses is a public service "
        "that can be pointed at somebody else's internal network, so this one "
        "refuses. Your own machine has no such problem: a staging box, a name only "
        "your resolver knows or an instance that never leaves the LAN all work from "
        "the command line."
    ),
    "cli.nodocker.kicker": "No Docker?",
    "cli.nodocker.heading": "Without a container",
    "cli.nodocker.body": (
        "The check is an ordinary Python program on PyPI, so <code>uv</code> or "
        "<code>pipx</code> will fetch and run it without installing anything "
        "permanently."
    ),
    # ------------------------------------------------ CLI documentation index
    "docs.index.title": "CLI documentation",
    "docs.index.description": (
        "Install, run and configure the check-opencloud-security CLI, with the "
        "complete operator guides collected in one place."
    ),
    "docs.index.kicker": "Documentation",
    "docs.index.heading": "Run the scanner from your terminal",
    "docs.index.lede": (
        "The practical CLI reference, collected from the project README and the "
        "guides under <code>docs/</code>. Start with one command; keep the rest "
        "for when the check becomes part of monitoring, CI or a fleet."
    ),
    "docs.index.toc.quickstart": "Quick start",
    "docs.index.toc.commands": "Commands",
    "docs.index.toc.options": "Useful options",
    "docs.index.toc.configuration": "Configuration",
    "docs.index.toc.monitoring": "Monitoring",
    "docs.index.toc.guides": "Full guides",
    "docs.index.quickstart.kicker": "Quick start",
    "docs.index.quickstart.heading": "One check, without installing anything",
    "docs.index.quickstart.container": (
        "Or use the published container. It runs the same plugin and returns the "
        "same Nagios/Icinga exit code:"
    ),
    "docs.index.quickstart.note": (
        "The plugin talks directly to the instance. It does not send the address "
        "to this website or to a remote verdict service."
    ),
    "docs.index.commands.kicker": "Two entry points",
    "docs.index.commands.heading": "The verdict and the result document",
    "docs.index.commands.plugin": (
        "The monitoring plugin: one alert line, performance data and the standard "
        "exit codes <strong>OK</strong>, <strong>WARNING</strong>, "
        "<strong>CRITICAL</strong> and <strong>UNKNOWN</strong>."
    ),
    "docs.index.commands.scanner": (
        "The scanner library as a CLI: the complete JSON result document for a "
        "script, a pipeline or an ad-hoc investigation."
    ),
    "docs.index.options.kicker": "The everyday flags",
    "docs.index.options.heading": "Useful options",
    "docs.index.option.host": (
        "Hostname, IP or URL; comma-separated for several instances."
    ),
    "docs.index.option.check_hardening": (
        "Include missing hardening measures and security headers."
    ),
    "docs.index.option.release_track": (
        "<code>rolling</code>, <code>production</code>, <code>lts</code> or "
        "<code>auto</code>."
    ),
    "docs.index.option.ignore_hardening": (
        "Accept one finding without erasing its evidence; repeatable and wildcard "
        "capable."
    ),
    "docs.index.option.debug": (
        "Explain where the rating started and what held it down."
    ),
    "docs.index.option.insecure": (
        "Skip certificate verification for an instance you control."
    ),
    "docs.index.option.thresholds": (
        "Choose the rating thresholds that map to monitoring states."
    ),
    "docs.index.option.format": "Print Nagios output or Prometheus text.",
    "docs.index.option.baseline": (
        "Alert only on findings that are new or worse than the last run."
    ),
    "docs.index.option.webhook": (
        "Notify another system when the configured state is reached."
    ),
    "docs.index.options.manual": (
        "<code>check-opencloud-security --help</code> is the installed manual. The "
        '<a href="{project}#cli-usage" rel="noopener noreferrer">complete option '
        "table</a> includes every default and its <code>COS_</code> environment "
        "variable."
    ),
    "docs.index.configuration.kicker": "One direction",
    "docs.index.configuration.heading": "Configuration and precedence",
    "docs.index.configuration.intro": (
        "Settings may come from a YAML or JSON file, the environment or the "
        "command line. The order is always:"
    ),
    "docs.index.precedence.aria": "Configuration precedence, highest first",
    "docs.index.precedence.cli": "CLI flag",
    "docs.index.precedence.cli.note": "the explicit answer for this run",
    "docs.index.precedence.env": "Environment",
    "docs.index.precedence.env.note": (
        "<code>COS_*</code>, useful in containers and services"
    ),
    "docs.index.precedence.file": "Configuration file",
    "docs.index.precedence.file.note": "the durable operator defaults",
    "docs.index.precedence.default": "Built-in default",
    "docs.index.precedence.default.note": (
        "the safe answer when nothing was specified"
    ),
    "docs.index.configuration.wizard": "Let the wizard write the first file:",
    "docs.index.configuration.note": (
        "A file ending in <code>.json</code> is JSON; every other suffix is YAML. "
        "Secrets may live in separate files rather than on the command line."
    ),
    "docs.index.monitoring.kicker": "Put it to work",
    "docs.index.monitoring.heading": (
        "Monitoring, automation and several instances"
    ),
    "docs.index.monitoring.nagios": (
        "<strong>Nagios or Icinga:</strong> use the plugin output directly; the "
        "worst configured threshold determines the exit code."
    ),
    "docs.index.monitoring.fleet": (
        "<strong>Several instances:</strong> pass a comma-separated host list, or "
        "use one configuration file per instance once their settings diverge."
    ),
    "docs.index.monitoring.prometheus": (
        "<strong>Prometheus:</strong> use <code>--format=prometheus</code> once, "
        "or expose the built-in exporter with "
        "<code>--prometheus-listen-port</code>."
    ),
    "docs.index.monitoring.ci": (
        "<strong>CI:</strong> run the same command in a pipeline; the status code "
        "makes a failed policy fail the job without a wrapper."
    ),
    "docs.index.monitoring.scheduled": (
        "<strong>Scheduled checks:</strong> systemd, cron, Kubernetes and the "
        "Ansible role all use the same CLI and configuration flow."
    ),
    "docs.index.guides.kicker": "From the repository",
    "docs.index.guides.heading": "Full operator guides",
    "docs.index.guides.lede": (
        "Every source document has its own HTML page here, generated from the "
        "repository Markdown and checked for drift in CI."
    ),
    # --------------------------------------------------- generated guide pages
    "docs.guide.kicker": "CLI documentation",
    "docs.guide.english_notice": (
        "This guide is generated from the project's documentation and is "
        "available in English only. The page around it is translated; the text "
        "below is not."
    ),
    "docs.guide.toc.heading": "On this page",
    "docs.guide.toc.aria": "On this page",
    # ----------------------------------------------------------------- search
    "search.title": "Search",
    "search.description": (
        "Search the scanner documentation and public guidance. Scan results are "
        "never indexed."
    ),
    "search.eyebrow": "Static release index",
    "search.heading": "Search the scanner",
    "search.lede": (
        "Documentation and public guidance only. The index is rebuilt for "
        "releases; it never reads the scan store, result pages, UUIDs, or "
        "submitted addresses."
    ),
    "search.label": "Search documentation",
    "search.placeholder": "TLS, Docker, waivers...",
    "search.submit": "Search",
    "search.status.idle": "Enter a term to search this release's documentation.",
    "search.status.results": "{count} result(s) in this release.",
    "search.status.empty": "No public documentation matched that search.",
    "search.status.error": "Search is temporarily unavailable.",
    # The search manifest: the title and summary an index entry carries, as
    # opposed to the words on the page itself.
    "search.page.index.title": "Scan an OpenCloud instance",
    "search.page.index.summary": (
        "Run a public security scan against an OpenCloud instance."
    ),
    "search.page.how.title": "How the scanner works",
    "search.page.how.summary": (
        "What the scanner measures, what it cannot see, and how results are "
        "handled."
    ),
    "search.page.grades.title": "What the grades mean",
    "search.page.grades.summary": (
        "The A+ to F rating scale and the fixes that improve each grade."
    ),
    "search.page.catalogue.title": "What the scanner checks",
    "search.page.catalogue.summary": (
        "Every hardening flag, header and TLS check the scanner runs, and "
        "every known advisory."
    ),
    "search.page.documentation.title": "CLI documentation",
    "search.page.documentation.summary": (
        "Command-line quick start, configuration, monitoring, and deployment "
        "guides."
    ),
    "search.page.api.title": "API",
    "search.page.api.summary": (
        "Submit scans, poll results, export reports, and erase retained data."
    ),
    "search.page.ai.title": "AI and MCP",
    "search.page.ai.summary": (
        "Machine-readable OpenAPI, Arazzo, discovery, MCP tools, and prompts."
    ),
    "search.page.privacy.title": "Privacy",
    "search.page.privacy.summary": (
        "Result retention, request logging, rate limits, and third-party policy."
    ),
    "search.page.about.title": "About this project",
    "search.page.about.summary": (
        "Why this independent OpenCloud security scanner exists."
    ),
    # ------------------------------------------- what a submission is refused for
    # The API answers the English sentence these translate; a browser reads
    # the translation. The SSRF guard names the identifier, this names the
    # sentence, and neither is derived from the other.
    "error.unsupported_fields": (
        "This service does not accept {fields}. The scan runs with server-side "
        "settings only."
    ),
    "error.rate_limit.client": (
        "That is a lot of scans from your network in a short time. Give it a "
        "minute and try again."
    ),
    "error.rate_limit.target": (
        "That instance was scanned very recently. Please give it a few minutes."
    ),
    "error.target.invalid": "That address cannot be scanned.",
    "error.target.empty": "Enter the address of the OpenCloud instance to scan.",
    "error.target.too_long": "That address is too long.",
    "error.target.characters": (
        "That address contains characters a hostname cannot have."
    ),
    "error.target.unparsed": "That address could not be parsed.",
    "error.target.scheme": "Only http:// and https:// targets can be scanned.",
    "error.target.credentials": "Credentials in the address are not accepted.",
    "error.target.address_only": (
        "Enter the instance base address only. A plain subfolder is accepted, "
        "but queries, fragments, parameters and path traversal are not."
    ),
    "error.target.port": "That address has an invalid port.",
    "error.target.no_host": "That address has no hostname.",
    "error.target.hostname_shape": (
        "That is not a hostname this service can scan."
    ),
    "error.target.unresolved": "That hostname does not resolve.",
    "error.target.hostname_long": "That hostname is too long.",
    "error.target.internal": "Local and internal addresses cannot be scanned.",
    "error.target.private": (
        "That address points into a private, loopback or link-local network, "
        "which this service will not scan."
    ),
    # ----------------------------------------------------------- result page
    "result.title": "Scan results",
    "result.description": (
        "The result of one public scan, readable only with its own identifier."
    ),
    "result.kicker": "Field report",
    "result.heading": "Scan result",
    "result.track.title": "The release track this scan was rated against",
    "result.track.label": "{track} track",
    "result.another": "Scan another instance",
    "result.progress.kicker": "In progress",
    "result.progress.queued.title": "Waiting for a scanner worker",
    "result.progress.queued.detail": (
        "Every worker is busy right now. Your scan keeps its place in line and "
        "starts as soon as one is free."
    ),
    "result.progress.running.title": "Scanning the instance",
    "result.progress.running.detail": (
        "Reading what the instance publishes: version, capabilities, certificate, "
        "headers and the endpoints it exposes without a login."
    ),
    "result.progress.step.queued": "Queued",
    "result.progress.step.running": "Running",
    "result.progress.step.done": "Result",
    "result.progress.estimate": "Most scans finish in under a minute.",
    "result.progress.elapsed": "{duration} elapsed",
    "result.progress.noscript": (
        "This page updates itself with JavaScript. Without it, reload the page in "
        "a few seconds to see the result."
    ),
    "result.progress.queue.position": (
        "Scan queued. Position in line: #{position} of {length}."
    ),
    "result.progress.queue.next": "Scan queued. You are next in line.",
    "result.progress.queue.waiting": "Waiting for a scanner worker to pick this up.",
    "result.progress.done.title": "Report ready",
    "result.progress.done.detail": "The grade is in. Opening the report.",
    "result.progress.failed.title": "Scan finished",
    "result.progress.failed.detail": (
        "The scan could not be completed. Opening what came back."
    ),
    "result.failed.fallback": "The scan could not be completed.",
    "result.failed.body": (
        "Nothing was graded, because nothing usable came back. Check that the "
        "address is right, that the instance is reachable from the public "
        "internet, and that it is an OpenCloud instance."
    ),
    "result.document.kicker": "Result document",
    "result.document.heading": "Result document",
    "result.document.lede": (
        "The same document the command line check and the Nagios plugin evaluate."
    ),
    "result.verdict.kicker": "Verdict",
    "result.verdict.heading": "Overall rating",
    "result.verdict.dial": "Rating {label}, {rating} out of 5",
    "result.facts.instance": "Instance",
    "result.facts.resolved": "Resolved to",
    "result.facts.ipv6.heading": "IPv6 reachability",
    "result.facts.ipv6.note": (
        "Not checked - this deployment has no outbound IPv6 connectivity, so "
        "it is noted here rather than counted against the instance."
    ),
    "result.facts.product": "Product",
    "result.facts.track": "Release track",
    "result.facts.track.unknown": "unknown",
    "result.facts.eol_tag": "End of life",
    "result.facts.schedule": "Release schedule",
    "result.facts.schedule.stale": (
        "{version} is newer than this copy of the OpenCloud release schedule, so "
        "the schedule is probably out of date. It is not counted against the "
        "instance -"
    ),
    "result.facts.schedule.stale_generated": (
        "{version} is newer than this copy of the OpenCloud release schedule, "
        "generated {generated}, so the schedule is probably out of date. It is not "
        "counted against the instance -"
    ),
    "result.facts.schedule.link": "check the published lifecycle page",
    "result.facts.signin": "Sign-in",
    "result.facts.signin.external": "External provider",
    "result.facts.signin.upstream_tag": "upstream",
    "result.facts.signin.version_unavailable": "version not exposed",
    "result.facts.signin.advisories": "check security advisories",
    "result.facts.signin.builtin": "Built-in identity provider",
    "result.facts.signin.none": "Not detected -",
    "result.facts.signin.link": "how OpenCloud sign-in is set up",
    "result.facts.proxy": "Reverse proxy",
    "result.facts.proxy.detected": "Detected",
    "result.facts.office": "Office",
    "result.facts.calendar": "Calendar",
    "result.facts.calendar.detected": "Something answers the CalDAV path",
    "result.facts.newest": "Newest release",
    "result.facts.score": "Score",
    "result.facts.score.value": "{rating} out of 5",
    "result.counter.critical": "Critical",
    "result.counter.warning": "Warning",
    "result.counter.info": "Info",
    "result.counter.advisories": "Advisories",
    "result.counter.passed": "Passed",
    "result.verdict.why": "Why this grade:",
    "result.verdict.caveat": (
        "A grade says the checks below passed, not that the instance is secure. "
        "This scan is not exhaustive: it sees only what the instance shows an "
        'anonymous visitor. <a href="#scan-limits">What it cannot see</a>.'
    ),
    "result.fix": "Fix:",
    "result.documentation": "Documentation",
    "result.explain.title": "What this check means",
    "result.plan.kicker": "Remediation plan",
    "result.plan.heading": "What gets you to {label}",
    "result.plan.then": "then {label}",
    "result.plan.still": "still {label}",
    "result.plan.note": (
        "The order is the one that pays off soonest, and the grade beside a step "
        "is what the rating would be once that step and everything above it is "
        "done. Findings of the same severity share one cap, so the grade moves "
        "only when the last of them is gone - which is why a step can be necessary "
        "and still promise nothing on its own."
    ),
    "result.plan.blocked.heading": "Holding the grade down, and not fixable",
    "result.plan.blocked.note": (
        "OpenCloud hardcodes these, so no setting reaches them. They are the "
        "reason the plan above stops where it does."
    ),
    "result.eol.alert": (
        "This release no longer receives security fixes. Nothing else on this page "
        "can lift the grade until it is upgraded."
    ),
    "result.advisories.kicker": "Advisories",
    "result.advisories.heading": "Known advisories for this version",
    "result.advisories.lede": (
        "Published advisories whose affected range includes {version}."
    ),
    "result.advisories.fallback_id": "advisory",
    "result.advisories.unrated": "unrated",
    "result.advisories.no_summary": "No summary published.",
    "result.advisories.read": "Read the advisory",
    "result.findings.kicker": "Findings",
    "result.findings.heading": "Checks that failed",
    "result.findings.lede": (
        "Each one caps the grade at the level its severity allows. Fix the "
        "critical ones first: they are the ones holding the score down hardest."
    ),
    "result.findings.filter.aria": "Filter findings by severity",
    "result.findings.filter.active": "Showing {severity} findings only.",
    "result.findings.filter.clear": "Show all findings",
    "result.findings.allclear.tag": "All clear",
    "result.findings.allclear.body": (
        "Every check this scanner runs passed on this instance."
    ),
    "result.hardening.kicker": "Hardening",
    "result.hardening.heading": "Hardening worth adding",
    "result.hardening.lede": (
        "Settings that are not switched on. None of these is an active "
        "vulnerability; each one removes a way in."
    ),
    "result.hardening.tag": "hardening",
    "result.header.tag": "header",
    # ------------------------------------------------- configuration fragment
    "result.fragment.kicker": "The fix, written out",
    "result.fragment.heading": "Paste this into your configuration",
    "result.fragment.lede": (
        "The findings above, in the syntax of the file that has to change. "
        "Pick where your instance is configured."
    ),
    "result.fragment.caution": (
        "Read each finding's Fix line before you paste. These are the values "
        "the checks look for, not a review of what your deployment needs."
    ),
    "result.fragment.picker": "Configuration format",
    "result.fragment.file": "Goes in {name}.",
    "result.fragment.copy": "Copy",
    "result.fragment.copied": "Copied",
    "result.fragment.copy_failed": "Could not copy",
    "result.fragment.nothing": (
        "Nothing here is set this way. What is open belongs in {flavours}."
    ),
    "result.fragment.elsewhere": (
        "These are fixed somewhere else - they belong in {flavours}:"
    ),
    "result.fragment.undecided": (
        "These have no value to paste: the right one is a decision about this "
        "deployment, and the finding's own Fix line is the whole answer."
    ),
    # ------------------------------------------------------------ scan again
    "result.rescan": "Scan again",
    "result.rescan.ready": "Ready to scan this instance again.",
    "result.rescan.wait": "Ready to scan again in {countdown}.",
    "result.rescan.note": (
        "Same target, same waivers, same release track - so the next result "
        "is comparable with this one. The wait is what keeps this small "
        "service on its feet; the scanner is open source and runs on your own "
        "machine with no limits at all:"
    ),
    "result.rescan.self_host": "run it yourself",
    "result.excluded.kicker": "Excluded",
    "result.excluded.heading": "Reported, but not counted",
    "result.excluded.waived.heading": "You asked to ignore these",
    "result.excluded.waived.note": (
        "They still failed. They just did not hold the grade down."
    ),
    "result.excluded.unfixable.heading": "Nobody can change these",
    "result.excluded.unfixable.note": (
        "OpenCloud hardcodes these flags, so they read the same on every instance "
        "in existence. They are shown for completeness and excluded from the grade."
    ),
    "result.scope.kicker": "Scope",
    "result.scope.heading": "What this scan cannot see",
    "result.scope.body": (
        "Everything above was read without logging in, which is the point and also "
        "the limit. <strong>The absence of a finding is not evidence of "
        "safety</strong>, and the highest grade this page can give is not a "
        "statement that the instance is secure - only that nothing checked here "
        "went wrong. Whole categories are outside an unauthenticated scan "
        "altogether: the operating system and its packages, the container runtime, "
        "the reverse proxy's own configuration, backups and their restores, the "
        "storage behind the instance, secrets and key handling, accounts, "
        "passwords and multi-factor sign-in, the permissions on existing shares, "
        "the software supply chain, and anything that only shows itself to a "
        "logged-in user. So are these two, which look like they should be visible "
        "and are not:"
    ),
    "result.scope.audit": (
        "<strong>Audit logging.</strong> OpenCloud's audit service only consumes "
        "the internal event bus - it publishes no endpoint and appears in no "
        "unauthenticated document - so whether it runs cannot be established from "
        "outside at all. It is not checked."
    ),
    "result.scope.integrations": (
        "<strong>Whether an office or calendar integration is set up "
        "<em>correctly</em>.</strong> This page reports only that an app provider "
        "is registered, or that something answers the CalDAV path. Sharing rules, "
        "WOPI secrets and the second service's own configuration all live behind a "
        "login and are not checked."
    ),
    "result.tls.kicker": "Transport",
    "result.tls.heading": "Transport security",
    "result.tls.lede": (
        "What the TLS layer said before a single byte of HTTP was exchanged. The "
        "findings above already judge these; this is the measurement behind them."
    ),
    "result.tls.protocol": "Protocol",
    "result.tls.bits": "({bits} bit)",
    "result.tls.deprecated": "Deprecated versions",
    "result.tls.deprecated.accepted": "Still accepted: {list}",
    "result.tls.deprecated.refused": "Refused: {list}",
    "result.tls.chain": "Chain",
    "result.tls.chain.trusted": "Trusted",
    "result.tls.chain.not_established": "Not established",
    "result.tls.chain.not_trusted": "Not trusted",
    "result.tls.chain.incomplete_note": "- no path to a public root",
    "result.tls.issued_to": "Issued to",
    "result.tls.unnamed": "unnamed",
    "result.tls.issued_by": "Issued by",
    "result.tls.unknown": "unknown",
    "result.tls.valid_for": "Valid for",
    "result.tls.validity": "Validity",
    "result.tls.validity.range": "{start} to {end}",
    "result.tls.validity.expired": "- expired {days} day(s) ago",
    "result.tls.validity.remaining": "- {days} day(s) left",
    "result.tls.lifetime": "Issued for",
    "result.tls.lifetime.days": "{days} day(s)",
    "result.tls.ocsp": "OCSP stapling",
    "result.tls.ocsp.stapled": "A revocation answer is stapled",
    "result.tls.ocsp.not_stapled": "Not stapled",
    "result.tls.ocsp.undetermined": "Not determined",
    "result.raw.kicker": "Raw data",
    "result.raw.heading": "Technical details",
    "result.raw.lede": "The full result document, exactly as the plugin sees it.",
    "result.raw.summary": "Show the raw JSON",
    "result.export.kicker": "Export",
    "result.export.heading": "Take this result with you",
    "result.export.lede": (
        "The same scan, rendered four ways. Each one is generated when you ask for "
        "it and disappears with the scan itself."
    ),
    "result.export.pdf": "PDF report",
    "result.export.pdf.hint": "For a ticket, a review or a printout.",
    "result.export.csv": "CSV",
    "result.export.csv.hint": "One row per finding, for a spreadsheet.",
    "result.export.sarif": "SARIF",
    "result.export.sarif.hint": "For a code-scanning dashboard.",
    "result.export.json": "JSON",
    "result.export.json.hint": "The raw document the plugin evaluates.",
    "result.export.passed.heading": "What already passed",
    "result.export.passed.note": (
        "These checks came back clean, so they are not in the plan above."
    ),
    "result.share.kicker": "Share",
    "result.share.heading": "Share this report",
    "result.share.lede": (
        "By email, or on your own clipboard. Nothing is sent through this "
        "service and no other company is asked to help."
    ),
    "result.share.warning": (
        "The address of this page is the only thing protecting it: anyone who "
        "has it can read the report until it expires. Posting it in a channel "
        "shares it with everyone in that channel, and with whatever fetches "
        "links there to build a preview. Copy the summary instead where the "
        "findings are the point."
    ),
    "result.share.email": "Share by email",
    "result.share.email.hint": (
        "Opens your own mail client with the message ready. Nothing leaves "
        "your browser until you send it."
    ),
    "result.share.email.subject": "OpenCloud security report for {target}",
    "result.share.email.body": (
        "Here is the security report for our OpenCloud instance:\n\n"
        "{url}\n\n"
        "This link is what grants access to the report, so treat it as a "
        "password. It expires on its own, after which the page is gone."
    ),
    "result.share.link": "Copy link",
    "result.share.link.hint": (
        "The address of this page. Anyone you give it to can open the report."
    ),
    "result.share.summary": "Copy summary",
    "result.share.summary.hint": (
        "The findings as text, with no link in it. The safer thing to paste "
        "into a chat channel."
    ),
    "result.share.summary.body": (
        "OpenCloud security report - {domain}\n"
        "Grade {label} ({rating} out of 5)\n"
        "Critical {critical} | Warning {warning} | Info {info} | "
        "Advisories {advisories} | Passed {passed}\n"
        "Measured by check-opencloud-security."
    ),
    "result.share.done": "Copied",
    "result.share.failed": "Could not copy",
    "result.share.fallback": "The address of this report:",
    "result.feedback.prompt": "Think the scan got something wrong?",
    "result.feedback.link": "Report a false positive or false negative",
    "result.expiry.one": (
        "This page expires in about 1 minute, after which the link stops working "
        "and the result is gone."
    ),
    "result.expiry.many": (
        "This page expires in about {minutes} minutes, after which the link stops "
        "working and the result is gone."
    ),
    # ----------------------------------------- transport facts beside the grade
    "tls.fact.protocol": "TLS version",
    "tls.fact.protocol.detail": "also accepts {list}",
    "tls.fact.expiry": "Certificate expires",
    "tls.fact.expiry.expired": "expired {days} day(s) ago",
    "tls.fact.expiry.remaining": "{days} day(s) left",
    "tls.fact.chain": "Chain",
    "tls.fact.chain.incomplete": "Incomplete",
    "tls.fact.chain.incomplete.detail": "no path to a public root",
    "tls.fact.chain.untrusted": "Not trusted",
    "tls.fact.chain.untrusted.detail": "self-signed, or an unknown authority",
    "tls.fact.chain.unknown": "Not established",
    "tls.fact.chain.unknown.detail": "the handshake never reached the certificate",
    "tls.fact.chain.ok": "Complete and trusted",
}
