## check-opencloud-security 1.11.0

### Added

- **Browser agents can use the page already in front of them.** The landing
  page registers a WebMCP scan tool, result pages register status and export
  tools for their current UUID, and `/llms.txt` maps the API, workflow, MCP,
  and WebMCP surfaces. Tool schemas come from the same server-side catalogues
  as the rendered controls, every execution uses the existing JSON API, and
  the front end's AI page documents the tools and their security boundary.
- **Deployments can add one optional landing-page meta tag.**
  `COS_WEB_INDEX_META_TAG=name=content` is passed through both Docker Compose
  stacks and rendered as escaped `name` and `content` attributes. Raw HTML,
  reserved page metadata, and named surveillance-platform tags are refused.
- **False results have a direct reporting path.** Completed result pages link
  to the repository issue tracker for false positives and false negatives,
  without putting the scan UUID or target into the URL.
- **Recognised identity providers link to their advisory database.** Scan
  overviews for Keycloak, Authelia and Authentik point to the provider's
  official GitHub Security Advisories page. The result reserves a version
  field but reports that it is unavailable rather than guessing, because none
  of the three exposes a product version without authentication.

### Changed

- **HTML action routes now negotiate structured responses.** A request for
  `application/json`, or a form choosing `output_format=json`, receives the
  same scan record or acceptance payload as the JSON API. The frontend CSS
  also drops selectors that no template or script can reach.
- **The MCP switch governs both browser and server tools.** Turning
  `COS_WEB_ENABLE_MCP` off now removes WebMCP registration from the landing
  and result pages as well as disabling `/mcp`.

### Security

- **Translated HTML now has an explicit trusted boundary.** Only
  source-controlled catalogue markup is treated as renderable HTML, while
  every interpolated placeholder is converted to text and escaped.
