## check-opencloud-security 1.33.1

### Changed

- **The guides read more plainly.** Around 300 sentences in the public and
  operator documentation - English, German, French and Spanish - lost
  rhetorical habits that added no information: closing aphorisms ("a warning
  nobody can ever clear is noise"), "X, not Y" punchlines, "on purpose",
  "that is the whole thing" and "worth knowing" lead-ins. The facts, option
  names, headings and anchors are unchanged.
- **A test keeps the guides plain.** `tests/test_documentation_style.py`
  fails on those constructs in any of the four languages and names the plain
  rewrite in its message. Words that are padding only some of the time have a
  per-language count that may fall and may not rise.

### Fixed

- **Dependabot no longer fails every month on `redis`.** It kept trying to
  raise the Python client to 8.x, which `arq` forbids (`redis<6`), so the uv
  update job failed each run. `.github/dependabot.yml` now ignores `redis`
  6 and later, beside the existing `playwright` rule.
