"""
The suite on every Python the project claims to support.

`requires-python = ">=3.10"` is a promise, and the only thing that keeps it
honest is running the tests on each of those interpreters. The dependencies go
*into the session's own environment* rather than being borrowed from the outer
one: a `pytest` found on `PATH` runs on whatever interpreter created it, so
five sessions would agree with each other and tell you nothing.
"""

import nox

nox.options.default_venv_backend = "uv"

# A missing interpreter is a gap in the evidence, not a session to skip
# quietly. uv fetches the versions the machine does not already have.
nox.options.error_on_missing_interpreters = True

PYTHON_VERSIONS = ["3.10", "3.11", "3.12", "3.13", "3.14"]


@nox.session(python=PYTHON_VERSIONS)
def versions_check(session):
    """Install the locked test dependencies and run the suite on this Python."""
    session.run_install(
        "uv",
        "sync",
        "--locked",
        "--group",
        "test",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    # Four minutes of tests on the wrong interpreter is worse than no tests,
    # because it looks like coverage. Check first, cheaply.
    session.run(
        "python",
        "-c",
        "import sys;"
        f"expected = tuple(int(p) for p in '{session.python}'.split('.'));"
        "actual = sys.version_info[:len(expected)];"
        "assert actual == expected, f'expected {expected}, running {actual}';"
        "print('running on', sys.version)",
    )
    session.run("pytest")
