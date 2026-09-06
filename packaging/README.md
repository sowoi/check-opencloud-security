# Distribution packaging

The `.deb` and the `.rpm`, for the monitoring hosts where software arrives
through `apt install` and `dnf install`. Why they exist and why they are built
this way is
[ADR 0039](../adr/0039-the-plugin-ships-as-a-distribution-package-built-from-the-wheel.md);
what an operator does with them is
[Installing the plugin](../docs/installation.md#debian-ubuntu-rhel-fedora-deb-and-rpm).

| File | |
|:--|:--|
| `nfpm.yaml` | The recipe. One file produces both packages; only what genuinely differs between the two ecosystems is an `overrides:` block or a `packager:` key. |
| `check-opencloud-security.sh` | Becomes `/usr/bin/check-opencloud-security`. |
| `check-opencloud-scanner.sh` | Becomes `/usr/bin/check-opencloud-scanner`. |
| `scripts/postinstall.sh`, `scripts/postremove.sh` | `systemctl daemon-reload`, and nothing else. |
| `homebrew/check-opencloud-security.rb` | The Homebrew formula, generated. See below. |

## Building

```shell
uv build                                        # the wheel comes first
python scripts/build_distro_packages.py         # both, into distro-packages/
python scripts/build_distro_packages.py --packager deb
```

[nfpm](https://nfpm.goreleaser.com/install/) has to be on `PATH`. The release
workflow installs it pinned by version and checked against the digest published
with that release.

## Homebrew

The workstation half of the same argument the `.deb` and the `.rpm` make. On
macOS, and on the Linux laptops that use it, `brew` is the package database: a
`pip install --user` is absent from it, invisible to `brew outdated`, and
unanswerable to whoever inherits the machine.

```shell
python scripts/build_homebrew_formula.py              # newest release on PyPI
python scripts/build_homebrew_formula.py --version 1.20.0
python scripts/build_homebrew_formula.py --check      # did a release get missed?
```

`--check` asks one question - does the committed formula pin the newest
release PyPI has - and deliberately not "would a regeneration produce this file
byte for byte". The second question answers *no* the moment any of the six
dependencies publishes anything, which has nothing to do with this project.
The resource pins move when the formula is regenerated, which is the point of
regenerating it.

**The formula describes a published release, not the working tree.** Every
URL and every `sha256` in it names an artifact PyPI already serves, so the
generator reads the index rather than `dist/`, and it defaults to the newest
version *published* rather than the one in `pyproject.toml` - a formula for a
version that has not gone out yet would pin a URL that answers 404.
Regenerate it after a release, not before one.

**It belongs in a tap, not in Homebrew core.** Core has notability
requirements this project does not claim to meet, and a formula there could
not be updated on this project's own schedule. Copy the generated file into
the `Formula/` directory of a tap repository (`sowoi/homebrew-tap`), from
which it installs as:

```shell
brew install sowoi/tap/check-opencloud-security
```

Nothing here pushes to that tap. A release workflow writing to a second
repository needs a token with write access to it, which is a decision about
credentials rather than about packaging.

**`--upgrade-self` refuses on a Homebrew installation** and names
`brew upgrade`, for the same reason it refuses on a `.deb`: Homebrew's formula
is a virtualenv under the Cellar, so pip finds it writable and appears to
succeed - and the next `brew` operation relinks the Cellar and puts the old
version back with no record that pip was ever there. See
`opencloud_local_scan/selfupdate.py`.

## Three things to know before changing anything here

**The packages are built from the wheel, not from the tree.**
`scripts/build_distro_packages.py` unpacks `dist/*.whl` into a staging tree and
refuses a wheel whose version does not match `pyproject.toml`. The `.dist-info`
goes into the package with the code, because that is what `importlib.metadata`
reads for `--version` - drop it and every installed host reports `0.0.0`.

**nfpm does not expand environment variables inside a content `src:`.** It does
expand them in scalar fields such as `version:`, which is how
`COS_PACKAGE_VERSION` gets in. The staging paths are therefore written out
literally as `build/distro-stage/...`, and nfpm has to run from the repository
root for them to resolve. `tests/test_distro_packaging.py` checks that every
one of those paths is something the build script actually writes, because nfpm
only discovers a missing one at build time - which, on the release path, is
after the wheel has gone to PyPI.

**The launchers hardcode `/usr/lib/check-opencloud-security`.** A shell script
on `PATH` has no way to discover where its payload was installed, so that path
appears in three places: the recipe, both launchers, and
`build_distro_packages.INSTALL_PREFIX`. If they drift, the package installs
cleanly and its commands then exit "no such file" on a host where nothing looks
wrong. There is a test for exactly that.
