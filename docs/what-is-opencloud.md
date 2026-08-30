# What OpenCloud is, and how it differs from ownCloud and Nextcloud

This scanner checks [OpenCloud](https://opencloud.eu/) instances specifically
- not any server that happens to answer `/status.php` the same way. This page
is the background for why that distinction exists: what OpenCloud is, where
it came from, and what actually changed compared to ownCloud and Nextcloud.

<!-- TOC -->
* [What OpenCloud is, and how it differs from ownCloud and Nextcloud](#what-opencloud-is-and-how-it-differs-from-owncloud-and-nextcloud)
  * [Where OpenCloud comes from](#where-opencloud-comes-from)
  * [How it differs from ownCloud and Nextcloud](#how-it-differs-from-owncloud-and-nextcloud)
  * [Why this matters for a security scan](#why-this-matters-for-a-security-scan)
<!-- TOC -->


## Where OpenCloud comes from

All three projects trace back to one codebase. [ownCloud](https://owncloud.com/)
was created in 2010 as a self-hosted alternative to Dropbox. In 2016 its
founder, Frank Karlitschek, left the company and forked that code to start
Nextcloud, which has been developed independently ever since. ownCloud itself
continued under new ownership and, starting in 2018, rewrote its server from
PHP into a Go codebase named ownCloud Infinite Scale (oCIS) - a clean-slate
rewrite, not a refactor of the PHP server.

OpenCloud is a fork of that oCIS codebase. In late 2024 and early 2025, after
ownCloud GmbH was acquired by Kiteworks, a large part of the oCIS engineering
team - including developers who had worked on it since 2018 - left and
founded [OpenCloud GmbH](https://opencloud.eu/en/press/heinlein-group-strengthens-open-source-ecosystem-germany-founding-opencloud-gmbh),
backed by the Berlin-based [Heinlein Group](https://www.heinlein-support.de/)
(which also runs mailbox.org and OpenTalk). OpenCloud's own material describes
the project as "based on a fork of the open source software 'ownCloud
Infinite Scale (OCIS)'"; it is candid about the fork existing and vague about
the circumstances of it, for reasons connected to Kiteworks - this page keeps
to the same restraint and reports only what OpenCloud states publicly.

The practical result: OpenCloud and oCIS share a Go server, the same
[CS3 APIs](https://github.com/cs3org) and [Reva](https://github.com/cs3org/reva)
storage layer, and - inherited from further back, through ownCloud's original
PHP server - a `/status.php` endpoint that Nextcloud also still serves. See
[Why OpenCloud still answers `/status.php`](status-php.md) for what that
endpoint actually returns today. OpenCloud's own roadmap since the fork has
diverged from oCIS: a `PosixFS` storage layer for human-readable data on disk,
and independent calendar backend work, among other changes - development
happens under Apache License 2.0, in three-week release cycles.

## How it differs from ownCloud and Nextcloud

The three projects now differ in more than name:

| | OpenCloud | Nextcloud | ownCloud (Infinite Scale) |
|:--|:--|:--|:--|
| Language | Go | PHP | Go |
| Architecture | Independent services (CS3/Reva) | Monolithic PHP application | Independent services (CS3/Reva) |
| Metadata storage | Filesystem, alongside file data | Relational database (MySQL/PostgreSQL/SQLite) | Filesystem, alongside file data |
| App ecosystem | Small, focused on file sharing | Large - calendar, chat, office, and more | Small, focused on file sharing |
| Release cadence | Frequent, three-week cycles | Continuous, weekly feature releases | Scheduled major releases |
| License | Apache License 2.0 | AGPLv3 | AGPLv3 / proprietary editions |

The storage difference matters operationally, not just architecturally:
OpenCloud (like oCIS before it) has no schema-migrated SQL database to
upgrade, back up, or restore - see the "no database" discussion in
[Why OpenCloud still answers `/status.php`](status-php.md#what-the-handler-actually-returns)
for why the `needsDbUpgrade` field in that endpoint's response is always
`false`. Nextcloud, built on PHP and a relational database, does not share
that property.

Feature scope is the other clear split. OpenCloud, like ownCloud before it,
positions itself around doing file sharing and collaboration well rather than
being a full application platform; Nextcloud's ecosystem of bundled apps -
calendar, mail, chat, office document editing, and dozens more - is one of
its main selling points. Neither approach is strictly better; they are
different bets about what a self-hosted file platform should be.

## Why this matters for a security scan

Because all three still answer `/status.php` compatibly, a scan of the wrong
software could produce a confident-looking result about the wrong product:
different release schedules mean a version string that looks current for one
project can be years end-of-life for another, and hardening defaults differ
between them too. This scanner reads the `product`/`productname` field from
that endpoint and refuses to rate an instance that identifies as ownCloud or
Nextcloud rather than OpenCloud, instead of guessing - see
[Troubleshooting](troubleshooting.md) for what that refusal looks like and why
the fix is pointing the scan at the right host, not overriding the check.

"OpenCloud", "ownCloud" and "Nextcloud" are the property of their respective
owners; this page names them only to identify and compare the software, per
the affiliation notice in [the documentation index](README.md).
