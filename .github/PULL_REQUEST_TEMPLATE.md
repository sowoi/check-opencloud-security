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
- [ ] Web application or frontend
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

- [ ] `uv run pytest` passes, including `tests/test_webapp_*.py` if you
      touched `webapp/` or `frontend/`.
- [ ] `uvx ruff check .` passes. (`ruff format` is deliberately not run - do
      not reformat the tree.)
- [ ] `uv run mypy --config-file mypy.ini` passes.
- [ ] `ansible-lint` passes, run from inside `ansible/` - only if you touched
      that directory.
- [ ] I added an entry under `## [Unreleased]` in `CHANGELOG.md`.
- [ ] If that entry is under `### Security`, I added a matching record in
      `security/advisories/` and
      `python scripts/security_advisories.py --check` passes. I did **not**
      publish an advisory.
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

## For a change to the web application or the frontend

<!-- Delete this whole section if it does not apply. -->

- [ ] The web application still only accepts `target_url`,
      `ignore_hardenings`, `release_track` and `output_format`. Nothing new
      lets a request choose concurrency, timeouts or any other server-side
      setting.
- [ ] New settings are `COS_WEB_*` environment variables, with a row in
      [`docs/webapp.md`](../docs/webapp.md) and an entry in
      `docker/docker-compose.yml`.
- [ ] `webapp/` and `frontend/` are still excluded from the wheel and the
      sdist, and anything a deployment needs is in
      `scripts/build_web_bundle.py`.
- [ ] No third-party asset: no CDN, no font service, no analytics, nothing the
      browser fetches from another origin.
- [ ] No inline `style=`, `<style>`, `onclick` or `<script>` - the CSP has no
      `unsafe-inline`. One-off styles are classes or `[data-...]` rules in
      `app.css`.
- [ ] The markup is semantic and keyboard reachable: real labels, a visible
      focus ring, and `prefers-reduced-motion` honoured by anything that moves.
      The page still says something useful if JavaScript does not run.
- [ ] Nothing new is logged beyond a lifecycle marker and a scan uuid - no
      target URLs, no client addresses, no results.
- [ ] Every page still carries the version in the footer and the trademark
      notice from `base.html`.
- [ ] Screenshots of the before and after, if the change is visual.

## For a new or changed option

<!-- Delete this whole section if it does not apply. -->

- [ ] A row in the CLI option table in `README.md`, or in the settings table
      in `docs/webapp.md` for a web setting.
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
