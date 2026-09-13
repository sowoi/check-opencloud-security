# ADR 0044: The operator's area may write the exclusions, and nothing else

- Status: Accepted
- Date: 2026-09-13

## Context

[ADR 0035](0035-the-operator-area-is-guarded-by-a-proxy-and-authenticates-nobody.md)
established `/admin` as a window: it reads settings and counts, streams the
audit trail, and borrows the worker's two reference-data refreshes. It writes
nothing else, and that is most of what makes an area guarded by somebody
else's proxy safe to have at all - a console that cannot change anything is a
console whose compromise costs a reading.

[ADR 0043](0043-an-operators-exclusion-outranks-every-allowance.md) then added
`COS_WEB_BLOCKED_TARGETS`, the addresses a deployment will not scan. It is
read once at startup, which is right for a promise a deployment makes about
itself and wrong for the request that produces most exclusions: somebody
writes and asks not to be scanned, usually because something is already going
on. "Within the next deployment window" is not an answer to that, and the
workaround - an operator editing compose and restarting the stack, or dropping
a rule into the reverse proxy - either interrupts every scan in flight or puts
the exclusion somewhere the worker cannot see it.

So the question is not whether the list should be editable at runtime. It is
how to make the area able to write *this* without becoming an area that writes.

## Decision

`/admin` gains exactly one control that changes behaviour: adding and
withdrawing an exclusion. It is bounded by four properties, and each of them
is the reason the last one is acceptable.

**It can only ever refuse.** Nothing typed here can make this service scan
something it would otherwise decline, widen a limit, reach a target, or spend
anybody's allowance. The worst a stolen operator session achieves is a service
that scans less than it could - a denial of service against this deployment,
never a weapon pointed through it, which is the shape every other control in
the area was kept away from.

**The environment is a floor.** `COS_WEB_BLOCKED_TARGETS` entries are shown in
the area and cannot be withdrawn there; an attempt is refused with a sentence
saying where to remove it instead, rather than silently doing nothing, which
would read as "removed" on the next page load. So `docker compose up` remains
the truth about the exclusions a deployment declares, and a browser cannot
undo them.

**A change takes effect from the next request, everywhere.** The written half
lives in Redis, which both processes already share, and each reads it where it
acts: the API on every submission, the worker when a job starts - so a scan
accepted a moment before the entry is refused rather than run, and a
deployment behind several replicas does not have some processes honouring the
list and others not. Nothing is held from startup, and nothing needs a signal
or a restart to propagate.

**An unreadable store refuses the scan.** Every other reader of runtime state
here treats absence as "fall back to what shipped", because losing a release
line makes a rating *less* certain. This one falls the other way: a list that
cannot be read might contain the entry this target is on, so the submission
fails rather than proceeding without it. Malformed content - somebody else's
key, a corrupted value - is distinct and is treated as no stored entries, with
the environment's half still in force.

Two smaller choices follow. Entries are validated and normalised where they
are written, since the startup check cannot help an entry that arrives at
runtime, and a list holding something the guard ignores would show an operator
a promise nothing keeps. And the state document `/admin/state` answers with
carries *counts* of the two halves, never the entries: the page shows the
addresses to the operator reading their own configuration, while that document
is what gets pasted into an issue report.

## Consequences

- An operator can answer "please stop scanning us" in under a minute, from a
  browser, with no restart and no interrupted scans - which is the only
  version of that answer anybody actually gives.
- `/admin` is no longer read-only, and the sentence in `AGENTS.md` that said so
  has been amended rather than left to be discovered as false. The bar for the
  next control that writes is this ADR's four properties, not precedent.
- Exclusions added in the area are exactly as durable as Redis. The page says
  so, and points at the environment variable for anything that must outlive a
  flush. A deployment that treats Redis as disposable should keep its standing
  exclusions in compose.
- The area now has a control whose rate of use is unbounded (no cooldown),
  which is acceptable because it reaches nothing outside this deployment. The
  stored list is capped instead, so the control cannot be used to fill Redis.

## Alternatives considered

**Leave it to the environment and a restart.** Honest, and already possible.
It costs every scan in flight and a deployment window, which in practice means
the exclusion is applied late or not at all - and the reverse-proxy workaround
people reach for instead leaves the worker, which resolves the target again,
knowing nothing about it.

**A signed configuration file the operator edits and the processes reload.**
Keeps the area read-only, but the container filesystem is read-only by design,
a file needs a volume every deployment would have to add, and the worker and
the API would each need a watcher. It moves the write out of the area by
adding a second source of truth and a reload mechanism this service has
otherwise never needed.

**Let the area write settings generally, with this as the first one.** The
opposite decision, and the one this ADR exists to refuse. Concurrency, limits
and TLS policy in a browser-editable store would put the answer to "can a
visitor make this service noisier" behind somebody else's proxy - the exact
property `COS_WEB_*` being environment-only exists to hold.

**Cache the list per process for a few seconds to save a Redis read.** A
submission already performs several Redis operations, and a cache would make
"immediately" mean "within the cache window" - which is precisely the promise
an operator is relying on when they type the entry.
