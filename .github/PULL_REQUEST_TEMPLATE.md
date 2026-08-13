<!--
Thanks for contributing. Delete any section that does not apply - an honest
short description beats a fully filled-in template.

Security fixes are not submitted as a public pull request. See SECURITY.md.
-->

## What this changes

<!-- What it does and, more usefully, why. One or two sentences is fine. -->

Fixes #

## Type of change

- [ ] Bug fix
- [ ] New or changed check
- [ ] New or changed option
- [ ] Documentation
- [ ] Packaging, CI or deployment
- [ ] Refactoring, no behaviour change

## Behaviour

<!-- Skip this if nothing an operator can observe has changed. -->

- **Does it change an exit code, a rating or an output line for an instance
  that is not modified?** <!-- yes/no, and which -->
- **Does it break an existing configuration, flag or environment variable?**
  <!-- yes/no. If yes, say what an operator has to do. -->

## Checks

- [ ] `uv run pytest` passes.
- [ ] `uvx ruff check .` passes. (`ruff format` is deliberately not run - do
      not reformat the tree.)
- [ ] `uv run mypy --config-file mypy.ini` passes.
- [ ] `ansible-lint` passes, run from inside `ansible/` - only if you touched
      that directory.
- [ ] I added an entry under `## [Unreleased]` in `CHANGELOG.md`.
- [ ] I did **not** touch the `version` in `pyproject.toml`, and did not create
      a tag or a release. That is the maintainer's call, and a bump publishes
      to PyPI as soon as it lands.
- [ ] No real hostname, IP address, token or password appears anywhere in this
      change - including tests, fixtures and commit messages.
      `opencloud.example.com` is the placeholder.

## Tests

<!--
Which tests you added, and what they would catch. An assertion that would
still pass with the feature removed is worse than no assertion - please assert
the negative case as well as the positive one.
-->

- [ ] I added tests, or this change cannot be tested (say why below).

## For a new or changed check

<!-- Delete this whole section if it does not apply. -->

- [ ] I verified against the OpenCloud source that an operator can actually
      change this setting. If they cannot, it is `actionable=False` and stays
      out of the alert line, the `hardenings_missing` metric and the webhook.
- [ ] The identifier is explained in `opencloud_local_scan/hardening.py`, so
      that `--debug` can tell an operator what to do about it.
- [ ] The severity matches what an attacker actually gains, and therefore how
      far it caps the rating.

## For a new or changed option

<!-- Delete this whole section if it does not apply. -->

- [ ] A row in the CLI option table in `README.md`.
- [ ] An entry in `config/check-opencloud-security.example.yml`.
- [ ] A line in `CHANGELOG.md`.
- [ ] The README table of contents still matches its headings.
- [ ] The default preserves the previous behaviour.

## Anything else

<!--
Trade-offs you made, things you were unsure about, or parts you would like
looked at closely. Saying "I am not sure this is the right place for it" is
useful, not a weakness.
-->
