## check-opencloud-security 1.9.3

### Added

- **A real OpenGraph share image.** `og:image` now points at a hand-drawn
  1200x630 PNG (`frontend/static/img/og-image.png`, rendered from the
  `og-image.svg` beside it) with `og:image:type`, `og:image:width` and
  `og:image:height` metadata, because most crawlers and chat clients will not
  draw the SVG the pages previously shared.

### Changed

- **Body type is now Inter, self-hosted.** The web application serves the
  five weights it uses from `/static/fonts/` (SIL OFL 1.1, license beside the
  files) with the system sans as the fallback while the file arrives. The
  serif display face and the monospace dossier labels still come from the
  reader's own system stack, and nothing is fetched from a font service.
- **The accent colour is a warm ember in daylight.** The teal accent became a
  deep orange in the light scheme (`#c2410c`) and now carries the primary
  action button as well as the live marker and the assurance row, so the one
  thing a page wants done is the first thing the eye finds; the dark scheme
  keeps the clear teal (`#5eead4`) it always had. The logo, hero and expired
  artwork and the backdrop aurora were re-tinted to match.
