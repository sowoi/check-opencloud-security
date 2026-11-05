# Repository scripts

These scripts maintain generated data, build release artifacts, and verify
published material. Run them from the repository root.

| Script | Purpose |
|:--|:--|
| `build_frontend_documentation.py` | Generates `frontend/templates/docs/` from English operator Markdown and `docs/de/`. Use `--check` in CI. |
| `build_search_index.py` | Generates the localized public search indexes. It only reads the public-page manifest. |
| `update_page_revisions.py` | Records each public page's `<lastmod>` for `sitemap.xml` next to a digest of its template, so a date moves only when the page really changed and not on every release. Use `--check` in CI. |
| `build_distro_packages.py` | Builds the `.deb` and the `.rpm` from the already-built wheel, using `packaging/nfpm.yaml`. Needs `nfpm` on `PATH`. See [ADR 0039](../adr/0039-the-plugin-ships-as-a-distribution-package-built-from-the-wheel.md). |
| `build_web_bundle.py` | Builds `dist/check_opencloud_security_web.tar.gz` and its checksum for a web-service release. |
| `check_pull_request.py` | Refuses a pull request without an Unreleased `CHANGELOG.md` entry, or with a version change that is not forward, already tagged or misnamed in its commit subject. A local check before opening a pull request; no workflow runs it. |
| `check_dependencies.py` | Refuses a Python dependency (in `pyproject.toml` or a workflow's `uvx`) without an approved record in `security/dependencies/`, and a grandfather list that grew (`--base`). `--list` shows every dependency's standing. CI runs it; see [ADR 0060](../adr/0060-a-new-dependency-is-justified-tested-and-reviewed-first.md). |
| `check_translations.py` | Compares the four frontend catalogues and the translated guides against English. Structural differences (keys, placeholders, markup, link targets, dead links) are errors; prose heuristics (register, untranslated, glossary) are warnings. `--check` in CI, `--strict` to fail on warnings too. See [`TRANSLATING.md`](../TRANSLATING.md). |
| `check_documentation_links.py` | Checks documented OpenCloud links after merges and on a schedule. |
| `check_tool_pins.py` | Compares the tool pins Dependabot does not update (`uvx`/`npx` versions, the downloaded binaries named by a `*_VERSION` variable, uv's `required-version`) with each tool's latest release. Exits 1 when one is behind; `--list` works offline. [`tool-pins.yml`](../.github/workflows/tool-pins.yml) runs it weekly and keeps one issue up to date. It only reports, because a binary pin needs a new SHA-256 checked by hand. |
| `release_notes.py` | Prepares release notes from the Unreleased changelog section. It rewrites release files, so use it on a scratch copy when previewing. |
| `security_advisories.py` | Checks that every `### Security` changelog entry has a decision recorded in `security/advisories/`, and drafts or publishes the GitHub advisories. Use `--check` in CI. |
| `render_architecture_diagrams.py` | Points every `` ```mermaid `` fence in `ARCHITECTURE.md` at a rendered PNG under `img/`. Use `--check` in CI; rendering itself needs `mmdc` from `@mermaid-js/mermaid-cli`, run separately - see [`render-architecture-diagram.yml`](../.github/workflows/render-architecture-diagram.yml). |
| `update_release_schedule.py` | Reads the OpenCloud lifecycle page and updates the bundled schedule plus the generated README release table. |
| `update_vulnerability_db.py` | Reads OSV and adds advisory evidence to the bundled vulnerability database. |
| `verify_export.py` | Verifies signed scan exports. |

The release schedule and advisory scripts are conservative by design. Review
their pull requests and never edit their generated outputs by hand.

`security_advisories.py` is the one script here that can act on the world
outside the repository. `--check` and `--list` only read; `--sync` creates
GitHub *draft* advisories, which are private to maintainers; `--publish` makes
one public and raises Dependabot alerts for every affected installation, and is
never run by CI. See [`AGENTS.md`](../AGENTS.md#security-advisories).

See
[`ARCHITECTURE.md`](../ARCHITECTURE.md#updating-for-a-new-opencloud-release)
for the release-update procedure.

This project is independent and is not affiliated with, endorsed by, or
supported by OpenCloud GmbH. "OpenCloud" and related marks belong to their
owners and are used only to identify the software being checked.
