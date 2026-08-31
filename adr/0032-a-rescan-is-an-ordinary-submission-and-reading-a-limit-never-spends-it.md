# ADR 0032: A rescan is an ordinary submission, and reading a limit never spends it

- Status: Accepted
- Date: 2026-08-31

## Context

The loop somebody actually runs against this service is scan, fix, scan again.
Only the first half of it was on the page. The second meant going back to the
front page, retyping the address, and re-picking the waivers and the release
track from memory - so the commonest outcome was a second report rated on
different terms from the first, which is not a comparison but two unrelated
reports. [ADR 0029](0029-a-comparison-is-two-live-results-and-one-arithmetic.md)
gave agents `compare_scans`; browsers had nothing to compare.

Adding a button raises two questions that look small and are not.

**Where does the submission go?** The obvious answer is a route that already
knows everything: `POST /api/scans/{uuid}/rescan` reads the record, copies its
fields, and enqueues. It is also a second write path. Every guard on the
existing one - the cross-site check, the client limit, the target cooldown,
the SSRF guard, the audit trail, the 422 on an unsupported field - would have
to be repeated there and kept in step forever, and the first one forgotten
would be a gap nobody could see from the page.

**How does the page know the wait?** A button that submits into a 429 is worse
than no button. But the two things that could refuse it are counters, and the
functions that read them are the functions that increment them:
`check_client` does an `INCR`, and `check_target` claims the slot with
`SET NX`. Calling either to answer "how long do I have to wait" would spend
the allowance being reported on - and `check_target` in particular would
answer "the full cooldown" every single time, because asking would have
started one.

## Decision

**The button is a form posting to `/`, and the countdown is read with
functions that count nothing.**

- The rescan control is an ordinary HTML form to `POST /`, carrying the first
  scan's `target_url`, `ignore_hardenings`, `release_track` and
  `output_format` as hidden fields. It is the same four fields any submission
  may carry and no fifth ([AGENTS.md, *a request may choose what to scan,
  never how hard*]), so **no new write endpoint exists** and every guard
  applies to it because it is not a special case of anything.
- `RateLimiter` gains `peek_client` and `peek_target`: the same decisions with
  the `INCR` and the `SET NX` left out. They are read-only by construction
  rather than by convention.
- The page shows **the longer of the two waits**. Either limit can be the one
  in the way, and a countdown driven by the target cooldown alone would expire
  into a refusal from the client limit.
- The target is taken from **the record the uuid already unlocked**, never
  from a request parameter. There is therefore no way to ask this service how
  recently an arbitrary host was scanned: you can only ask about a scan you
  hold the capability for, which you performed. The uuid remains the whole of
  the authorisation ([ADR 0007](0007-erasure-on-request.md)).
- The wait is rendered by the **server** into the first paint, and the script
  only counts it down. The button is rendered **enabled** and the script
  disables it.

## Consequences

- Anything added to the submission path - a new guard, a new refusal, a new
  audit event - applies to a rescan on the day it is written, with nobody
  having to remember that rescans exist.
- The countdown is a good-faith estimate, not a promise. It is the limits as
  they stood when the page was rendered, and another visitor may claim the
  instance's slot in between. Reaching zero re-enables the button; it does not
  guarantee acceptance, and the 429 is the friendly one that points at
  self-hosting.
- A reader without scripting gets a working button and a truthful sentence
  saying how long is left. They may meet the 429, which is a better outcome
  than a disabled control nothing on their page can release - the reason the
  enabled-by-default rendering is load-bearing rather than incidental.
- Two more limit-reading functions exist, and a future limit will need a third
  or the countdown will quietly stop accounting for it. The alternative was a
  countdown that lied, so this is the cost that was chosen.
- Nothing is stored. A rescan produces a new uuid with no link to the old one;
  comparing them is `compare_scans`' job, and the reader holds both addresses.

## Alternatives considered

**`POST /api/scans/{uuid}/rescan`.** Rejected: a second write path whose only
advantage is not having to render four hidden inputs, bought with a permanent
obligation to mirror every guard on the first one.

**Poll an endpoint for the remaining wait.** Rejected: it is arithmetic the
browser can do from one number, and a per-second request to ask whether a rate
limit has expired is a poor use of a service that has rate limits.

**Render the button disabled and let the script enable it.** Rejected: it
inverts who is harmed by the script failing to load. Disabled-by-default
punishes the reader with no JavaScript for a restriction that may not even
apply to them.

**Count the seconds down rather than measuring against a deadline.** Rejected
in the implementation: a laptop that sleeps through the wait would wake with a
timer minutes behind the truth, and the button would stay disabled long after
the limit had cleared.
