# ADR 0017: The advisory database refreshes itself, and only ever gains advisories

- Status: Accepted
- Date: 2026-08-21

## Context

[ADR 0016](0016-the-release-schedule-refreshes-itself.md) made the release
schedule refresh itself in a long-running deployment. The other half of what a
rating is made of has exactly the same problem, in a worse direction.

`opencloud_local_scan/data/vulnerabilities.json` decides whether a scanned
instance is reported as vulnerable. Until now nothing wrote it: it shipped
with no active advisory in it, there was no script to regenerate it and no
workflow to run one. Every advisory published against OpenCloud since the file
was written was invisible to every deployment of this project, and a visitor
scanning an affected instance was told it was fine.

That is the one failure a security check must not have. A missing hardening
finding is a smaller grade than deserved; a missing advisory is a **pass on a
live vulnerability**, and the visitor has no way to tell it apart from a real
one.

Adding a CI job that commits the file fixes the repository but not a running
service. The web application is a process that may be up for months, so the
gap between the day an advisory is published and the day this deployment hears
about it is bounded only by how often somebody rebuilds the image.

Three things make refreshing this file at runtime harder than refreshing the
schedule.

**It fails in both directions.** The schedule fails by losing a line. The
advisory database fails by losing an advisory *and* by gaining one: a bogus
entry reports every visitor's instance as critical, which is how a security
check loses the trust that makes anybody act on it.

**One advisory can affect several release lines.** `GHSA-vf5j-r2hw-2hrw` was
fixed in both `4.0.3` and `5.0.2`, as two disjoint ranges in one record.
Reading only the first of them - as the parser did - reports every `5.0.x`
instance as clean.

**A feed publishes advisories with no version bounds at all.** The Go
vulnerability database's alias of that same record carries
`events: [{introduced: "0"}]` and no fix. Parsed naively that becomes
`introduced=None, fixed=None`, and a range with no bounds at either end
matches *every version there has ever been*. A single such entry turns every
scan this project runs, anywhere, into a critical finding.

## Decision

**One reader, in the library.** `opencloud_local_scan/advisory_source.py`
asks the feed and returns a database document.
`scripts/update_vulnerability_db.py` uses it to commit the file, and
`webapp/advisories.py` uses it to refresh a running deployment. `scripts/` is
in neither the wheel nor the web image, so the reader could not have lived
there.

**A refresh only ever adds.** The fetched advisories are merged into the
document the deployment already has, which starts as the bundled file. A feed
answering with an empty list changes nothing, a feed that has forgotten an
advisory does not remove it, and a hand-written entry survives a refresh.
Removing an advisory is a deliberate edit to the file in the repository.

**Nothing unbounded is ever believed.** An advisory that names no version it
affects is dropped where the feed is parsed - so the guard covers a plugin
operator's `--vulnerability-feed` as much as this service - and refused again
when a stored document is read back. A feed answering with more than
`MAX_ADVISORIES` records is refused whole, on the grounds that OpenCloud has
not had two hundred advisories and something else is being served.

**Every affected range is kept.** An advisory carries `ranges`, and reports
the fix belonging to the line the scanned instance is actually on. A `5.0.1`
instance is told to upgrade to `5.0.2`, not to `4.0.3`.

**A failure changes nothing.** Unreachable, an error page, a timeout, a
surprise: each leaves the database exactly as it was, and says which in the
log. The scan is rated against yesterday's answer rather than against none.

**The refresh is on by default and can be turned off.**
`COS_WEB_ADVISORY_REFRESH=false` is for a deployment with no route to the
feed; it then rates against the bundled file, as the plugin does on a
monitoring host.

**The database is never written to disk.** It lives in Redis under its own
key, beside the schedule. A container image stays what it was built as, and a
deployment that loses its Redis falls back to the bundled file rather than to
nothing.

## Consequences

- A deployment reports an advisory published after it was built, which is the
  whole point.
- Two cron jobs rather than one, at different minutes: one source being slow
  or down has nothing to do with the other, and an operator reading the log
  can see which it was.
- `/healthz` reports how many advisories this deployment would rate against
  and when it last asked - counts and dates only, because nothing
  authenticates to read it.
- The result document names every feed a verdict came from, so a reader can
  check one.
- A deployment can now disagree with the file in the repository, in the
  direction of knowing more. That is the intended asymmetry.
- The feed is a third party this project depends on being honest about
  OpenCloud. The merge-only rule, the bounds guard and the count cap are what
  keep a bad day there from becoming a bad day for every visitor.
