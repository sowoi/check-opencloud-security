## check-opencloud-security 1.18.1

### Added

- The severity counters on a report are now the filter for its findings:
  pressing `Critical`, `Warning` or `Info` narrows the list to that severity,
  pressing it again restores it, and a sentence beside the heading says which
  filter is on with a way out. A counter at zero is disabled, no count is ever
  rewritten, and without scripting the counters are the readings they were.
- A switch between the light and dark themes in the header. The operating
  system still decides until somebody presses it, the choice lives in that
  browser alone, and it is applied before the first paint so an override never
  opens with a flash of the other scheme.
- The waiver picker can be searched by identifier or title, hiding a group
  whose entries have all gone. Ticked boxes stay ticked and stay submitted:
  filtering only ever sets `hidden`.
- An address that will not do says so under the field once the visitor has
  typed and left, so the red bar no longer carries a meaning nothing spells
  out.

### Changed

- The progress card says how long the wait has run and how long a scan usually
  takes. The clock is measured against a wall-clock instant, so a laptop that
  sleeps wakes with the right answer rather than a tally of missed ticks.

### Documentation

- `ADMIN.md` collects the operational knowledge a system administrator needs:
  refreshing the vulnerability database and release schedule by hand, pulling
  the reviewed and attested data onto a monitoring host, regenerating the
  frontend documentation, search index and web bundle, raising a disposable
  local stack with `docker/setup-wizard.py` to test the frontend in a
  browser, what the daily runtime
  refresh keeps in Redis and how `/healthz` reflects it, the log markers worth
  grepping for and what the logs deliberately never contain, and what to do
  when OpenCloud moves a documented link. It is internal, and excluded from
  every artefact that ships.

### Changed

- The rescan button sits next to "scan another instance" in the report's
  head, rather than in a card of its own further down the page - the two
  actions a reader reaches for once a result is in, grouped together.
- The documentation and advisory links inside a finding's fix line now read
  as a small chip, in the same shape as the severity and category tags above
  them, instead of as a sentence of body text that happened to be blue.
  Shared by `scan.html` and `catalogue.html`, so both pages pick it up.

### Fixed

- **`tests/test_data_signing.py`'s tests against a real Sigstore bundle now
  actually run in CI.** `sigstore` is an optional extra kept out of the
  `test` dependency group on purpose, so the two tests that exercise
  `_verify_one_bundle` - a malformed bundle skipped in favour of the next,
  and a readable bundle that fails the identity pin raising
  `SignatureInvalid` - marked themselves `@needs_sigstore` and quietly
  skipped whenever it was missing. No workflow ever installed both the
  `test` group and the `signing` extra together: `run-tests.yml` synced only
  `--group test`, and `supply-chain.yml` installed `--all-extras` but never
  ran pytest. The verification logic that decides whether a fetched
  vulnerability database or release schedule really carries this project's
  own attestation had therefore never executed in automation, only ever on a
  developer's own machine with `sigstore` installed by hand.
  `run-tests.yml` now syncs and runs with `--extra signing` alongside
  `--group test`, so both tests run on every push and pull request.

- **A flaky advisory-feed test no longer races a real socket close against a
  megabyte of unread data.** `read_capped` reads at most `MAX_DOCUMENT_BYTES
  + 1` bytes and the response is closed right after; the test built a body
  roughly twice that size to prove the size guard fires before the
  `MAX_ADVISORIES` count guard even gets a chance to. Closing a socket with
  over a megabyte still incoming makes the kernel send a reset instead of a
  clean close, which occasionally raced the fake server's single write and
  surfaced as a `ConnectionResetError` where the test expected the guard's
  own `AdvisoryFetchError`. The body is now padded to just past the cap, the
  same way the sibling schedule-page test already did, leaving nothing sized
  enough to race over.
