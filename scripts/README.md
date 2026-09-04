# Repository scripts

These scripts maintain generated data, build release artifacts, and verify
published material. Run them from the repository root.

| Script | Purpose |
|:--|:--|
| `build_frontend_documentation.py` | Generates `frontend/templates/docs/` from operator Markdown. Use `--check` in CI. |
| `build_search_index.py` | Generates the localized public search indexes. It only reads the public-page manifest. |
| `build_distro_packages.py` | Builds the `.deb` and the `.rpm` from the already-built wheel, using `packaging/nfpm.yaml`. Needs `nfpm` on `PATH`. See [ADR 0039](../adr/0039-the-plugin-ships-as-a-distribution-package-built-from-the-wheel.md). |
| `build_web_bundle.py` | Builds `dist/check_opencloud_security_web.tar.gz` and its checksum for a web-service release. |
| `check_documentation_links.py` | Checks documented OpenCloud links after merges and on a schedule. |
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
