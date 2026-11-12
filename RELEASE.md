## check-opencloud-security 1.33.2

### Changed

- **The advisory database knows GHSA-p6cc-4vh9-2hjq.** OpenCloud published
  it as "DDoS Attac Vector through Crash in Search Service": an
  authenticated user can crash the search service with a crafted search
  query. When OpenCloud runs as a single binary, that takes down the whole
  instance. It is rated medium and fixed in 4.0.9, 7.2.5 and 9.1.0, so the
  scanner reports it for releases before 4.0.9, from 4.1.0 up to (but not
  including) 7.2.5, and from 7.3.0 up to (but not including) 9.1.0.
- **The release schedule knows 9.1.0, 7.2.5 and 4.0.9.** OpenCloud
  published all three on 2026-11-11, but the lifecycle page does not list
  them yet, so the generator could not pick them up. They were added by
  hand: 9.1.0 opens the new rolling line 9.1, 7.2.5 is the current
  production release and 4.0.9 the current LTS release. An instance still
  on 9.0.0, 7.2.4 or 4.0.8 is now reported as behind its track.
- **A release no longer rolls back release-schedule entries the lifecycle
  page does not list yet.** The release workflow now runs
  `scripts/update_release_schedule.py --never-older`: when the page names an
  older current release for a track than the checked-in schedule, the file
  is kept. Without the flag, as in the weekly refresh, the page still wins.

### Fixed

- **A backport named only in an advisory's patched list is no longer
  reported as vulnerable.** OpenCloud wrote GHSA-p6cc-4vh9-2hjq as
  `< 9.1.0` and listed 7.2.5 and 4.0.9 only under patched versions. The
  repository advisory parser read those only when there was no range at
  all, so it would have reported the patched 7.2.5 and 4.0.9 as affected.
  A patched version below the upper bound now splits the range at its line,
  the same way `< 4.0.8, < 7.2.0` already did.
- **The daily advisory refresh no longer fails on a real advisory.** The
  refresh tests made up advisories for versions such as 9.0.1 and assumed no
  real advisory covered them. GHSA-p6cc-4vh9-2hjq did, so the refresh
  workflow failed before it could open its pull request. The tests now use
  versions far beyond any real release, and a new test fails with a clear
  message if a bundled advisory ever covers one of them.
- **The suite no longer grades the fake OpenCloud by this week's
  advisories.** The fake reports 7.2.3, which GHSA-p6cc-4vh9-2hjq covers, so
  about thirty tests about ratings, output formats and policies failed once
  the advisory was bundled. The plugin and scanner runs in those tests now
  leave the bundled database out (`COS_SCANNER_BUNDLED_DB=false`, or
  `include_bundled_db=False`), and the tests about advisories turn it on
  explicitly. The web report and browser tests run a release no advisory
  covers and fail with a clear message if one ever does.
