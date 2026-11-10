# Release tracks, end of life and the update recommendation

OpenCloud maintains rolling, production and LTS tracks in parallel. A version’s support
status therefore depends on its track as well as its number. This guide explains how the
scanner uses release lines and the bundled schedule, chooses an update and applies
`--release-track`.

The [main README](../README.md#end-of-life-detection) carries the current
state of each track and the settings that switch the check off.

<!-- TOC -->
* [Release tracks, end of life and the update recommendation](#release-tracks-end-of-life-and-the-update-recommendation)
  * [Why a version number is not an answer](#why-a-version-number-is-not-an-answer)
  * [What the bundled schedule can and cannot tell you](#what-the-bundled-schedule-can-and-cannot-tell-you)
  * [The recommended release follows your track](#the-recommended-release-follows-your-track)
  * [Declaring your release track](#declaring-your-release-track)
<!-- TOC -->


## Why a version number is not an answer

OpenCloud publishes rolling, production and LTS releases from the same version
sequence. The consequence for monitoring is that the *same* version can be perfectly
current or long dead depending on the track it was published on. `7.2.3` is the
current production release even though the rolling track is already at `7.4.0`,
while `7.3.0` - a *higher* version - stopped receiving fixes the day `7.4.0`
appeared.

The plugin therefore works in **release lines** (`MAJOR.MINOR`), which is the
unit OpenCloud maintains: `7.2.3` is a patch of the `7.2` line. A line can
belong to more than one track - `7.2` shipped as a rolling release before it
was promoted to production, and `4.0` is both the previous production line and
the current LTS line - and it is judged by whichever track supports it longest.

The schedule ships in `opencloud_local_scan/data/release_schedule.json` and is
scraped from the release dates in the OpenCloud admin documentation, the only
source that states the release *type*; the GitHub release list cannot tell a
rolling release from a production one. It is refreshed on every release and
weekly by a [scheduled workflow](../.github/workflows/release-schedule.yml), and
the same run rewrites the table above - so the versions quoted here are the
ones the plugin actually judges against, not the ones that were current when
this page was written. Everything else in this section, including the worked
examples below, is written by hand and may name older releases to make a
point.

## What the bundled schedule can and cannot tell you

The bundled schedule has these limits:

- **LTS releases are only available with a subscription**, so an LTS line is
  recognised from the documentation but its releases may never appear
  publicly. If your vendor has committed to a different window, point
  `release_schedule` at your own file rather than letting the bundled one
  decide.
- **A release newer than the schedule is never rated `F`, and never counted
  against the instance.** The file ages between updates of this package, so an
  instance that was patched promptly is routinely newer than the data it is
  compared against. It keeps its rating, gets no upgrade recommendation and is
  never called end of life for it.
- **The output reports when that happens.** A version ahead of the newest release
  recorded for its line - or on a line newer than every line on record - sets
  `lifecycle.scheduleStale` in the result document, fills in `scheduleNote`,
  `scheduleUpdated` and `scheduleSource`, and adds a line to the plugin's
  output:

  ```
  Release schedule: 7.4.1 is newer than anything in the bundled release schedule (generated 2026-08-12), so that schedule is probably out of date. This is not counted against the instance. Check the current support window at https://docs.opencloud.eu/docs/admin/resources/lifecycle/, and regenerate the schedule with scripts/update_release_schedule.py.
  ```

  The note concerns the bundled file and not the instance: the
  support window it worked out came from data older than the release it
  judged, so it is worth re-reading at the [source][lifecycle]. Upgrading the
  package, or running `python scripts/update_release_schedule.py`, clears it.
  A line that genuinely expired stays expired - patching inside a dead line
  does not reopen it, and the note explains the data rather than overturning
  the verdict.

## The recommended release follows your track

A release feed only knows the newest release *overall*, and on OpenCloud that
is always a rolling one. Recommending it to a production or LTS instance would
move it onto a track with a three-week support window, which an operator on
the production track did not choose.

The update check therefore uses the
[release schedule](../README.md#end-of-life-detection) to pick a target on the instance's
own track:

| Installed | Track      | Recommended | Why                                                           |
|:----------|:-----------|:------------|:--------------------------------------------------------------|
| `7.2.3`   | production | *nothing*   | Current production release, even though rolling is at `7.4.0` |
| `7.2.0`   | production | `7.2.3`     | The newest patch of the same line                             |
| `7.3.0`   | rolling    | `7.4.0`     | On rolling, the newest release is the right one               |
| `4.0.0`   | LTS        | `4.0.8`     | Where the backports are                                       |

The newest release overall is still reported, as `newestRelease` in the JSON
result and the webhook payload, so nothing is hidden - it is just not
presented as the thing to install. If the feed reports a newer patch of the
line you are already on, the feed wins, because it is fresher than the bundled
schedule.

## Declaring your release track

By default the release schedule works out which track a version belongs to and
judges it as generously as the truth allows: `7.2.3` appears on both the
rolling and the production track, so it is treated as a production release and
is current.

That is the right default when no track is declared, but it does not suit
every instance. If you deliberately follow the rolling track, then
`7.2.3` went out of support the day `7.4.0` shipped, and you want to be told
so. `--release-track` says which track you are on, and the version is then
judged on that track alone:

```bash
check-opencloud-security --host opencloud.example.com --release-track rolling
```

`--release-track auto` is the default: the release schedule is asked which
track the installed release belongs to. It is the same answer as leaving the
flag out, said out loud, and it is what keeps one configuration usable across
instances on different tracks:

```bash
check-opencloud-security --host opencloud.example.com --release-track auto
```

| Installed | Declared            | Verdict                                                                     |
|:----------|:--------------------|:----------------------------------------------------------------------------|
| `7.2.3`   | *nothing* or `auto` | Supported - current production release                                      |
| `7.2.3`   | `production`        | Supported - current production release                                      |
| `7.2.3`   | `rolling`           | **End of life** - superseded by `7.4.0`, upgrade to `7.4.0`                 |
| `7.4.0`   | `production`        | Supported - ahead of the production track, whose current release is `7.2.3` |
| `2.3.0`   | `production`        | **End of life** - behind the production track, upgrade to `7.2.3`           |
| `4.0.8`   | `lts`               | Supported until the two-year window closes                                  |

This has two consequences:

- **Being ahead of your track is not a finding.** A production instance that
  has moved on to the current rolling release has everything the production
  track ships and more, so it is reported as ahead of its track rather than
  rated `F`. Only a release *behind* the current release of your track is out
  of support.
- **The check never recommends a downgrade.** If your declared track has no
  release you could move *up* to, the update recommendation stays empty and
  the reason explains the situation instead. Moving from `7.4.0` back to
  `7.2.3` is a decision the plugin leaves to you.

The declared track also steers the update recommendation described in
[the section above](#the-recommended-release-follows-your-track), and the
output marks it as declared so it can be told apart from an inferred one:

```
Release lifecycle: 7.2 (rolling track declared), out of support since 2026-07-14, upgrade to 7.4.0
```

An unknown value is ignored rather than treated as an error, so a typo in a
config file degrades to the default behaviour instead of taking the check down.

## Warning before the end of life

End of life is `CRITICAL` on the day it arrives, which is too late to plan an
upgrade. `--eol-warning DAYS` (`COS_EOL_WARNING`, YAML `eol_warning`) turns an
otherwise `OK` result into `WARNING` once the running line has `DAYS` or fewer
days of support left:

```text
WARNING: The 7.2 release line reaches end of life on 2026-10-14 (20 days left). Upgrade to 7.4.0.
```

It only ever raises `OK`; a result that is already `WARNING` or `CRITICAL`
keeps its own line. A line without a published end-of-life date has nothing to
count down and never warns. `0`, the default, turns it off.

## Does the upgrade clear the advisories?

When the installed release carries known advisories, the scan records
`upgradePath`: what moving to the recommended release does about each one.

```json
{"upgradePath": {"target": "7.2.4", "fixes": ["GHSA-aaaa"],
  "stillAffected": ["GHSA-bbbb"], "safeVersion": "7.3.0"}}
```

Every range of an advisory is checked against the target, so a fix backported
to another line counts. `safeVersion` is the lowest release past every fix the
target still lacks, or `null` when one of them has no fix yet. The plugin
prints it as a detail line:

```text
Upgrade path: 7.2.4 fixes GHSA-aaaa but is still affected by GHSA-bbbb; 7.3.0 is the first release that clears them all.
```

## Rehearse every upgrade

`upgradePath` covers the one release the scan recommends. `upgradeRehearsal`
covers every release worth moving to: the newest patch of the installed line
and the newest release of each later line (only lines on the declared release
track, when the instance declares one). For each one it lists the advisories
the release `fixes`, those it is `stillAffected` by, any it `introduces`,
whether it is `endOfLife`, and the `rating` the scan would give it.

```json
{"upgradeRehearsal": [
  {"version": "7.2.4", "line": "7.2", "recommended": false,
   "fixes": ["GHSA-aaaa"], "stillAffected": ["GHSA-bbbb"], "introduces": [],
   "endOfLife": false, "versionRating": 2, "rating": 2}
]}
```

The rating uses the same version rules as the scan. The instance's failed
checks still cap it (`versionRating` is what the version alone would allow),
because an upgrade changes the release, not the proxy in front of it. The
plugin prints one detail line, graded with its own rating letters:

```text
Upgrade rehearsal: 7.2.4 fixes 1 finding, leaves 1, reaches rating D; 7.3.0 fixes 2 findings, leaves 0, reaches rating A+.
```

The rehearsal knows only the bundled or refreshed schedule and advisory
database. A release or advisory published later can change the answer.

The web application renders the same entries as **What upgrading would buy
you**, one row per candidate with the advisories it clears, the ones it
leaves and the grade it would reach. Where the version alone would rate
better than the row shows, the difference is this instance's own findings,
which an upgrade does not touch.
