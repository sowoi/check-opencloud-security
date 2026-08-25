# ADR 0018: CLI documentation is generated at build time

- Status: Accepted
- Date: 2026-08-25

## Context

The web frontend needs a local copy of the CLI documentation rather than links
that send a visitor to Markdown files on GitHub. The source already exists in
`README.md`, `opencloud_local_scan/README.md` and `docs/`; copying it into
hand-written templates creates two manuals that drift, while rendering
Markdown at request time makes the deployed service depend on repository
files and a parser it otherwise does not need.

The web application and frontend also do not ship in the PyPI artefacts. A
runtime documentation dependency would therefore enlarge the separate web
deployment for work that can be completed before an image or release bundle is
built.

## Decision

`webapp/documentation.py` is the one manifest of browser-facing documents: the
source path, public slug, title, description and any selected heading range.
`scripts/build_frontend_documentation.py` reads that manifest and writes one
Jinja template per document under `frontend/templates/docs/`.

Markdown is a test/development dependency only. Production serves the
generated HTML and never imports the parser or reads the source Markdown.
Relative links between documents in the manifest are rewritten to local
`/documentation/{slug}` routes. The generator escapes Jinja delimiters from
source code examples before writing a template.

CI runs the generator in `--check` mode and fails when a checked-in page is
missing or stale. The release bundle therefore contains the generated
templates through the existing `frontend/` directory and does not need the
Markdown sources to render them.

## Consequences

Every selected source document gets a separate, indexable HTML page with the
same frontend, navigation, CSP and trademark notice as the rest of the site.
The Markdown remains the only prose an operator edits; regeneration is a
mechanical follow-up.

Adding a page requires one manifest entry rather than a route, template and
index card written independently. Changing the generator changes many
checked-in files, which is visible in review and reproducible locally.

The test environment gains the Python-Markdown package. The web runtime does
not. Markdown features outside the explicitly enabled extensions must either
be avoided in selected sources or added deliberately to the generator and its
tests.

## Alternatives considered

**Render Markdown at request time.** Rejected because the service would need a
parser and source files in every deployment, and a missing file could turn an
ordinary documentation request into a server error.

**Link to GitHub.** Rejected because the Docs tab is meant to keep the
documentation inside the frontend and usable without a second service.

**Maintain hand-written HTML copies.** Rejected because every CLI change would
require a semantic rewrite in two formats, with no reliable way for CI to
prove they still agree.
