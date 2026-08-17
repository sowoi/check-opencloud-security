import os

import pytest

from opencloud_local_scan import config as config_module
from opencloud_local_scan import wizard as wizard_module


@pytest.fixture(autouse=True)
def no_retry_sleep(monkeypatch):
    """
    Prevent the retry/backoff mechanism from actually sleeping during tests.

    Without this, tests that trigger retries (e.g. simulated network errors)
    would be slowed down by real time.sleep() calls.
    """
    monkeypatch.setattr("check_opencloud_security.time.sleep", lambda seconds: None)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """
    Ensure COS_-prefixed environment variables never leak into tests.

    Without this, a developer's local environment (or a previous test) could
    silently change argparse defaults and cause flaky test results.
    """
    for name in list(os.environ):
        if name.startswith("COS_"):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def clean_config_files(monkeypatch, tmp_path_factory):
    """
    Ensure no configuration file on this machine can reach the tests.

    ``load_configuration(None, ...)`` searches the working directory,
    ``~/.config/check-opencloud-security/.env.json`` and ``/etc``. A developer
    who has run ``--configure`` for a real instance therefore has a file that
    silently answers "what does the plugin see when nothing is configured?" -
    with their own host, their own track and their own waivers. That made four
    tests fail on their machine and pass in CI, and it printed a real hostname
    into the failure output, which this project never wants anywhere.

    So the search is redirected at an empty home and an empty working
    directory, both created per test. Discovery itself still works exactly as
    it does in production, and the test that covers it chdirs somewhere it
    controls.
    """
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))

    # '~' now expands into the empty home; the absolute paths cannot be
    # redirected that way and are dropped instead.
    isolated = tuple(
        path
        for path in config_module.DEFAULT_CONFIG_PATHS
        if not os.path.isabs(os.path.expanduser(path)) or path.startswith("~")
    )
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATHS", isolated)
    monkeypatch.setattr(wizard_module, "DEFAULT_CONFIG_PATHS", isolated)
