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

## Building

```shell
uv build                                        # the wheel comes first
python scripts/build_distro_packages.py         # both, into distro-packages/
python scripts/build_distro_packages.py --packager deb
```

[nfpm](https://nfpm.goreleaser.com/install/) has to be on `PATH`. The release
workflow installs it pinned by version and checked against the digest published
with that release.

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
