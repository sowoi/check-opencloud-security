## check-opencloud-security 1.18.2

### Added

- **The severity counters on a report are the filter for its findings.**
  Pressing `Critical`, `Warning` or `Info` narrows the list below to that
  severity, pressing it again gives the whole list back, and a sentence
  beside the heading says which filter is on with a way out of it. The
  counters already counted exactly those entries, so the shortest way to ask
  "show me only those" is the number itself. A counter standing at zero is
  disabled - there is nothing behind it - and the advisories and passed
  counts stay readings, because neither has a list on this page to narrow.
  Nothing is fetched and no count is ever rewritten: every entry is already
  on the page tagged with the severity the server gave it, so the filter only
  sets `hidden`. Without scripting the counters are five readings, which is
  what they were.
- **A switch between the light and dark themes, in the header.** The
  operating system still decides on a first visit and on every visit after
  it; only pressing the switch writes anything down, and it is remembered in
  that browser alone. `theme.js` applies a stored choice before the first
  paint - the one script on the site that is not deferred - so an override
  never opens with a flash of the other scheme, and the `theme-color` meta
  tags are re-pointed so the browser's own chrome does not frame a dark page
  in a light bar. Which icon the button shows is decided in CSS from the same
  two questions the colour tokens ask, so it is never briefly wrong, and the
  control is hidden until scripting marks the document rather than being
  offered to a reader who cannot use it.
- **The waiver picker can be searched.** The catalogue lists every check the
  scanner runs, which is thorough and, past a screenful, hard to read;
  somebody who came to waive one identifier can now type it instead of
  hunting for it. Matching is against the identifier and the title the server
  already wrote into each row, a group whose entries have all gone is hidden
  with them, and a box that was typed in and emptied leaves the list exactly
  as it found it - including anything already ticked, because filtering only
  ever sets `hidden`. The field is revealed by its script, so a reader
  without one gets the full list rather than a search box that does nothing.
- **An address that will not do says so before the form is submitted.** The
  sentence under the field appears on `:user-invalid` - once the visitor has
  typed and left, never while they are still typing - so the red bar stops
  being a colour that carries a meaning nothing spells out. It is CSS that
  reveals it, so a browser without scripting corrects a typo just as readily.

### Changed

- **The progress card says how long the wait has run, and how long it usually
  takes.** The estimate is the server's sentence and is there without
  scripting; the clock beside it is measured against a wall-clock instant
  rather than counted up, so a laptop that sleeps wakes with the right answer
  instead of a tally of missed ticks. It starts when the page did, which is
  the wait the reader is actually sitting through, and it is `aria-live="off"`
  inside a card that is otherwise polite - a reading that changed every second
  would be announced every second, which is the difference between telling
  somebody where they are and talking over them.

### Documentation

- **`ADMIN.md` collects the operational knowledge a system administrator
  needs and a developer document never states.** How to refresh the
  vulnerability database and the release schedule by hand and what the
  guards refuse; how a monitoring host pulls the reviewed, attested data with
  `check-opencloud-scanner refresh-data` and which configuration keys make it
  count; how to regenerate `/documentation`, the search index and the web
  bundle; how to raise a disposable local stack from the working tree with
  `docker/setup-wizard.py` to look at the frontend in a browser, why
  `--preset private` is the one that lets a scan of a local instance complete
  at all, and the bind mount that turns a CSS change into a page reload
  rather than an image rebuild; what the daily runtime refresh keeps in Redis
  and how `/healthz`
  shows whether it happened; every logger name and log marker worth grepping
  for, and what the logs deliberately never contain; what to do when
  OpenCloud moves a documented link, including why a status code alone is not
  enough for a single-page documentation site. It stays internal: it is
  absent from the wheel, the sdist, the web bundle, `webapp/documentation.py`
  and `webapp/search.py`, so nothing publishes it.

### Fixed

- **The reference-data test fixture no longer leaves its own request body
  unread.** `fetch_records` POSTs a small JSON query; the fake HTTP server in
  `tests/test_reference_data_limits.py` answered without ever reading that
  body off the socket, then closed the connection (it runs HTTP/1.0, so it
  closes after every request). Closing a socket with an unread request body
  still sitting in the kernel's receive buffer makes it send a reset instead
  of a clean close, and that reset could land on the client mid-read of the
  *response* - intermittently surfacing as a `ConnectionResetError` in
  `test_an_oversized_advisory_answer_is_refused_before_it_is_parsed` instead
  of the `AdvisoryFetchError` the test asserts on, regardless of how large the
  response body was. Only the advisory test could ever hit this: the
  schedule/lifecycle fetch this fixture also serves is a plain GET with no
  request body to leave unread. The handler now drains `Content-Length` bytes
  of the request before replying.

- **The self-hosting note under a rescan lost its breathing room when the
  rescan card merged into the report's head.** `section-gap` moved from the
  self-host paragraph onto the rescan status line above it instead of
  staying on both, so the two unrelated sentences - "ready to scan again" and
  "you can self-host this" - sat almost flush against each other (.4rem
  apart instead of the 1.25rem every other section boundary on the page
  uses). `frontend/templates/scan.html` now keeps `section-gap` on the
  self-host paragraph as well.
