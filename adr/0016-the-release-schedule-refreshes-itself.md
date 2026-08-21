# ADR 0016: The release schedule refreshes itself, and only ever gains knowledge

- Status: Accepted
- Date: 2026-08-21

## Context

The lifecycle of an OpenCloud release is not something this project can work
out for itself. Which line is production and which is rolling, when a line
opened, which release supersedes which - all of it is stated once, on the
"Release Dates" tables in the admin documentation, and nowhere else in a form
a machine can read. `scripts/update_release_schedule.py` reads that page in CI
and commits the result as `opencloud_local_scan/data/release_schedule.json`,
which then ships in the wheel and in the container image.

For a monitoring plugin that is the right shape: the schedule is data, a
release ships it, and an operator who wants a newer one upgrades. For a
long-running public web service it is not. That service is a process that may
be up for months, and its schedule is frozen at the moment its image was
built. Every day that passes it drifts:

- A visitor scanning an instance on a release published last week is told the
  version is ahead of the schedule and that the database is probably out of
  date - correct, and useless, because it is *our* database.
- A line that expired since the image was built is still reported as
  supported, which is the failure direction that matters: an F reported as a
  pass.

Neither is fixed by shipping more often. The gap is between two releases of
this project, and it is unbounded.

The obvious answer - have the service read the same page - carries two risks
worth naming. The first is a second implementation: a parser in `webapp/`
that drifts from the one in `scripts/`, so that a scan run through the website
disagrees with the file in the repository. The second is trust: the schedule
decides whether an instance is end of life, and a fetched document that has
lost half its rows would quietly turn expired releases into unknown ones.

## Decision

**The worker re-reads the lifecycle page once a day, through the same parser
CI uses, and a refresh may only add knowledge.**

- The parser moves out of `scripts/` and into
  `opencloud_local_scan/schedule_source.py`, which is part of the wheel.
  `scripts/update_release_schedule.py` keeps only what is about the
  repository: the checked-in JSON, the generated README block and the CLI.
  There is one implementation of "what the lifecycle page says", and the web
  application and CI cannot disagree about it.
- `webapp/schedule.py` stores the fetched document in Redis under
  `cos:web:schedule:document`. It carries no TTL: a schedule is superseded,
  never expired, and expiring it would mean falling back to something older.
- Every queued scan reads it and passes it to the scanner as
  `ScannerSettings.release_schedule`. The scanner still decides nothing new -
  it is handed data, exactly as it is handed the bundled file today.
- A candidate document is accepted only when it contains **every line the
  bundled schedule knows about**, has at least the same number of lines the
  CI script demands of a page, and is not dated before the bundled file. A
  fetch that fails, a page that has been redesigned, a table that has lost
  rows: all of them leave the previous schedule exactly where it was.
- The job runs at startup as well as daily, because a deployment brought up
  the morning after a release should not wait until the small hours to learn
  about it, and `unique=True` keeps a horizontally scaled deployment to one
  fetch.
- Nothing is written to the repository. `README.md` and the bundled JSON stay
  CI's business; a running service has no opinion about either.

The refresh is **on by default**. It is one request a day for a whole
deployment, not one per visitor like the release feed, and a service that
tells strangers their instance is out of date should be able to say what it
is out of date *against*. `COS_WEB_SCHEDULE_REFRESH=false` turns it off for a
deployment with no outbound access, which then behaves exactly as before.

## Consequences

- A deployment learns about a new OpenCloud release within a day, without a
  pull request, a release or a redeployment.
- The stale-schedule notice a scan carries becomes meaningful: when it
  appears, the deployment really could not reach the documentation, rather
  than simply being old.
- The documentation site becomes something the web application depends on,
  once a day. It cannot fail a scan, and it cannot make a verdict worse: the
  only thing an unreachable page changes is that the schedule stays as it was.
- A compromised or badly edited lifecycle page could add lines that do not
  exist, and would then be believed - as CI would believe it today. What it
  cannot do is remove a line and turn an end-of-life instance into an unknown
  one, which is the failure that would matter.
- `/healthz` reports the schedule date and the time of the last successful
  read, so an operator can see the refresh working. Dates only; a health
  probe still says nothing about anybody's scan.
- The plugin is unchanged. A monitoring host runs the check every few minutes
  and must not turn that into a documentation fetch; it keeps the schedule
  that shipped with it, refreshed by upgrading.
