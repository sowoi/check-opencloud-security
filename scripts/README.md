# Repository scripts

These scripts maintain generated data, build release artifacts, and verify
published material. Run them from the repository root.

| Script | Purpose |
|:--|:--|
| `build_frontend_documentation.py` | Generates `frontend/templates/docs/` from operator Markdown. Use `--check` in CI. |
| `build_search_index.py` | Generates the localized public search indexes. It only reads the public-page manifest. |
| `build_web_bundle.py` | Builds `dist/check_opencloud_security_web.tar.gz` and its checksum for a web-service release. |
| `check_documentation_links.py` | Checks documented OpenCloud links after merges and on a schedule. |
| `release_notes.py` | Prepares release notes from the Unreleased changelog section. It rewrites release files, so use it on a scratch copy when previewing. |
| `update_release_schedule.py` | Reads the OpenCloud lifecycle page and updates the bundled schedule plus the generated README release table. |
| `update_vulnerability_db.py` | Reads OSV and adds advisory evidence to the bundled vulnerability database. |
| `verify_export.py` | Verifies signed scan exports. |

The release schedule and advisory scripts are conservative by design. Review
their pull requests and never edit their generated outputs by hand. See
[`ARCHITECTURE.md`](../ARCHITECTURE.md#updating-for-a-new-opencloud-release)
for the release-update procedure.

This project is independent and is not affiliated with, endorsed by, or
supported by OpenCloud GmbH. "OpenCloud" and related marks belong to their
owners and are used only to identify the software being checked.
