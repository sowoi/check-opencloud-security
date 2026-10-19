---
name: add-setting
description: Add a new configuration setting to the check-opencloud-security plugin and scanner end to end - factory, plugin flag, scan subcommand, setup wizard, README option table, CLI reference, example YAML, web application pinning, tests and changelog. Use when asked to add an option, flag, setting or COS_ environment variable to the plugin or scanner (not a COS_WEB_* web setting).
argument-hint: <setting name, type, default and what it does>
---

# Add a setting

Request: $ARGUMENTS

A setting flows one way: file / environment / CLI flag → `config.Configuration`
(flat `COS_` names) → `factory.py` → frozen `*Settings` → scanner. Precedence
is **CLI flag > environment > file > default**. Missing one place is the usual
bug, so work through every step and say explicitly when one does not apply.

## 0. Decide before editing

- **Name** it three ways, following the nearest existing setting:
  - YAML key: `scanner.<snake_name>` (or the section it belongs to)
  - Flat config name: `SCANNER_<UPPER_NAME>`, read from the environment as
    `COS_SCANNER_<UPPER_NAME>`
  - Plugin flag: `--kebab-name`, whose own environment default uses the
    shorter `COS_<NAME>` through `_env_bool` / `_env_*` in
    `check_opencloud_security.py`
- **Type and default.** Lists are `;`-joined in the environment
  (`config.get_list`).
- **Layer.** A setting that decides WARNING/CRITICAL belongs to the plugin
  only; a setting that changes what is measured belongs to `ScannerSettings`.
  The library never learns about exit codes.
- **Does it need an ADR?** Only if it changes a layer boundary, public
  interface or security model (use `/new-adr`).

Use a recent real example as the template - `git show bb2d9e1` added
`check_all_addresses` and touched every place below.

## 1. The places to change

1. **`opencloud_local_scan/scanner.py`** - the field on the frozen
   `ScannerSettings` dataclass, with its default and a docstring, and the code
   that uses it.
2. **`opencloud_local_scan/factory.py`** - read it in
   `scanner_settings_from_config` (or the matching builder) with
   `config.get_bool` / `get_int` / `get_list` / `get` and the default.
3. **`opencloud_local_scan/config.py`** - only if the setting needs a new
   default path.
4. **`check_opencloud_security.py`** - the flag in `build_arg_parser()` in the
   right argument group, help text ending in
   `Default: ... (env: {ENV_PREFIX}<NAME>).`, and passed through
   `_build_context` into `ScanContext` as `None` when not given, so the file
   and environment still apply.
5. **`opencloud_local_scan/cli.py`** - the same option on the `scan`
   subcommand (`default=None`, `dest=` the settings field) and passed in
   `main()`.
6. **`opencloud_local_scan/wizard.py`** - a `Question` with `key`, `prompt`,
   `explain`, `example`, `default`, `validate`, `cast`, in the right group.
7. **`README.md`** - a row in the option table under `## Options` (keep the
   table of contents in sync if a heading changes), and
   **`docs/cli-reference.md`** - the flag with its default and environment
   variable.
8. **`config/check-opencloud-security.example.yml`** - the key, commented out
   with its default, preceded by a comment explaining *why* one would change it.
9. **`webapp/runner.py`** - if it is a `ScannerSettings` field, decide the web
   application's value and **pin it explicitly** there. A request may choose
   what to scan, never how hard: never add it as a request field. If the
   operator area documents rules for it, update `webapp/rules.py` too.
10. **`CHANGELOG.md`** - an entry under `## [Unreleased]` (`### Added` for a
    new option), naming the flag, the environment variable and the YAML key.

## 2. Tests

Name tests as sentences with a one-line docstring, and assert the negative case
as well as the positive one. Cover at least:

- the default when nothing is set;
- file, environment and flag each setting it, and the precedence between them
  (`tests/test_config.py`, `tests/test_env_config.py`);
- the behaviour itself, against `tests/fake_opencloud.py` rather than mocked
  `requests`;
- the wizard question (`tests/test_wizard.py`);
- for a scanner field, that the web application pins it
  (`tests/test_webapp_api.py`).

## 3. Regenerate and verify

```bash
python scripts/build_frontend_documentation.py   # README/docs changed
python scripts/build_search_index.py
uv run pytest tests/test_config.py tests/test_env_config.py tests/test_wizard.py -q
uv run pytest -q
uvx ruff check .
uv run mypy --config-file mypy.ini
```

Remember `requires-python >= 3.11`: no 3.12+ syntax. Only
`ruff check`, never `ruff format`.

Finish by listing every file touched against the ten places above, marking any
that were deliberately skipped and why.
