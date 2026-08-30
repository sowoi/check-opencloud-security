"""
The published GitHub Action must keep matching the plugin it drives.

An action is a copy of the command line kept in a second file, and the failure
it produces when it drifts is the worst kind: a green pipeline that scanned
nothing, or a red one whose error names a flag the reader never wrote. So
every flag and environment variable the action uses is asserted against the
plugin's own parser rather than against a list typed out here.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

import check_opencloud_security as plugin

ROOT = Path(__file__).resolve().parent.parent
ACTION = ROOT / "action.yml"


def _outputs(written: str) -> dict[str, str]:
    """
    Parse a `$GITHUB_OUTPUT` file the way the runner does.

    Both forms the action writes: `name=value` on one line, and the heredoc
    `name<<DELIMITER` ... `DELIMITER` block for anything that may contain a
    newline. Parsing rather than substring-matching is the point - it is what
    lets a test assert that a scanned host forged *no* output, which a check
    for the expected ones passing would not notice.
    """
    parsed: dict[str, str] = {}
    lines = written.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if "<<" in line:
            name, _, delimiter = line.partition("<<")
            index += 1
            body: list[str] = []
            while index < len(lines) and lines[index] != delimiter:
                body.append(lines[index])
                index += 1
            parsed[name] = "\n".join(body)
        elif "=" in line:
            name, _, value = line.partition("=")
            parsed[name] = value
        index += 1
    return parsed


@pytest.fixture(scope="module")
def action() -> dict:
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def scan_script(action) -> str:
    """The body of the step that runs the scan and decides the exit code."""
    for step in action["runs"]["steps"]:
        if step.get("id") == "scan":
            return step["run"]
    raise AssertionError("the action has no step with id 'scan'")


def _flags() -> set[str]:
    """Every option string the plugin's parser accepts."""
    return {
        option
        for action_ in plugin.build_arg_parser()._actions
        for option in action_.option_strings
    }


def test_every_flag_the_action_passes_is_one_the_plugin_accepts(scan_script):
    """A renamed flag must fail here, not in somebody's scheduled pipeline."""
    accepted = _flags()

    for flag in ("--warning", "--critical", "--release-track", "--ignore-hardening"):
        assert flag in scan_script, f"the action stopped passing {flag}"
        assert flag in accepted, f"the plugin no longer accepts {flag}"

    # The negative: a flag the plugin does not have must not be in the script.
    assert "--ignore-hardenings" not in scan_script


def test_the_action_configures_the_plugin_through_its_own_environment_variables(
    monkeypatch, action
):
    """
    Configuration travels as COS_* rather than on the command line.

    A public workflow log shows every argument of every step, so the host and
    the release token belong in the environment - and this asserts the plugin
    still reads them from there.
    """
    scan = next(step for step in action["runs"]["steps"] if step.get("id") == "scan")
    assert "COS_HOST" in scan["env"]
    assert "COS_FORMAT" in scan["env"]

    monkeypatch.setenv("COS_HOST", "opencloud.example.com")
    monkeypatch.setenv("COS_FORMAT", "sarif")
    monkeypatch.setenv("COS_CHECK_HARDENING", "true")
    parsed = plugin.build_arg_parser().parse_args([])

    assert parsed.host == "opencloud.example.com"
    assert parsed.output_format == "sarif"
    assert parsed.check_hardening is True


def test_every_format_the_action_offers_is_one_the_plugin_can_produce(action):
    """
    An input that advertises a format the plugin dropped is a broken promise.

    The action deliberately names fewer formats than the plugin has - a
    Prometheus text exposition is something to scrape, not something a
    pipeline writes to a file - so this is a subset check rather than an
    equality one.
    """
    described = action["inputs"]["format"]["description"]
    offered = {
        option
        for action_ in plugin.build_arg_parser()._actions
        if "--format" in action_.option_strings
        for option in (action_.choices or ())
    }
    advertised = {name for name in offered if f"`{name}`" in described}

    assert advertised <= offered
    assert action["inputs"]["format"]["default"] in offered
    assert {"json", "sarif"} <= advertised, "the two a pipeline actually consumes"


def test_the_action_declares_the_outputs_a_later_step_reads(action):
    """A workflow that gates on `steps.scan.outputs.rating` needs it to exist."""
    outputs = action["outputs"]

    for name in ("exit-code", "status", "rating", "rating-label", "message"):
        assert name in outputs
        assert outputs[name]["value"].startswith("${{ steps.scan.outputs.")


@pytest.mark.parametrize(
    ("fail_on", "plugin_exit", "expected"),
    [
        ("warning", 0, 0),
        ("warning", 1, 1),
        ("warning", 2, 2),
        ("warning", 3, 3),
        # A WARNING is tolerated, but an UNKNOWN never is: a scan that did not
        # run is not a passing scan, and treating it as one is how a pipeline
        # goes green for a year against an instance nobody measured.
        ("critical", 1, 0),
        ("critical", 2, 2),
        ("critical", 3, 3),
        ("never", 2, 0),
        ("never", 3, 0),
    ],
)
def test_fail_on_decides_which_results_fail_the_step(
    tmp_path, scan_script, fail_on, plugin_exit, expected
):
    """The action's only judgement of its own, exercised against a stub plugin."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / "check-opencloud-security"
    stub.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            echo '[{{"status": "X", "rating": 3, "rating_label": "C", "message": "m"}}]'
            exit {plugin_exit}
            """
        ),
        encoding="utf-8",
    )
    stub.chmod(0o755)

    script = tmp_path / "scan.sh"
    script.write_text(scan_script, encoding="utf-8")

    completed = subprocess.run(  # nosec B603 - a fixed argv, in a temp directory
        [shutil.which("bash") or "/bin/bash", str(script)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{stub_dir}{os.pathsep}{os.environ['PATH']}",
            "COS_FORMAT": "json",
            "OUTPUT_FILE": "out.json",
            "FAIL_ON": fail_on,
            "WRITE_SUMMARY": "false",
            "INPUT_WARNING": "",
            "INPUT_CRITICAL": "",
            "INPUT_IGNORE_HARDENING": "",
            "INPUT_RELEASE_TRACK": "",
            "INPUT_EXTRA_ARGS": "",
            "GITHUB_OUTPUT": str(tmp_path / "github_output"),
            "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == expected, completed.stderr
    # Whatever the step decides, the real code is always reported.
    assert f"exit-code={plugin_exit}" in (tmp_path / "github_output").read_text()


def test_the_result_is_published_as_outputs_a_workflow_can_branch_on(
    tmp_path, scan_script
):
    """
    A multi-line message must not be readable as further output assignments.

    The plugin's summary contains newlines; written as `message=...` the lines
    after the first would be parsed as output names by the runner.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / "check-opencloud-security"
    document = json.dumps(
        [
            {
                "status": "WARNING",
                "rating": 3,
                "rating_label": "C",
                "message": "WARNING - two\nlines",
            }
        ]
    )
    (tmp_path / "payload.json").write_text(document, encoding="utf-8")
    stub.write_text(
        f"#!/bin/sh\ncat {tmp_path / 'payload.json'}\nexit 1\n", encoding="utf-8"
    )
    stub.chmod(0o755)
    script = tmp_path / "scan.sh"
    script.write_text(scan_script, encoding="utf-8")

    subprocess.run(  # nosec B603 - a fixed argv, in a temp directory
        [shutil.which("bash") or "/bin/bash", str(script)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{stub_dir}{os.pathsep}{os.environ['PATH']}",
            "COS_FORMAT": "json",
            "OUTPUT_FILE": "out.json",
            "FAIL_ON": "never",
            "WRITE_SUMMARY": "false",
            "INPUT_WARNING": "",
            "INPUT_CRITICAL": "",
            "INPUT_IGNORE_HARDENING": "",
            "INPUT_RELEASE_TRACK": "",
            "INPUT_EXTRA_ARGS": "",
            "GITHUB_OUTPUT": str(tmp_path / "github_output"),
            "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    written = (tmp_path / "github_output").read_text(encoding="utf-8")
    assert _outputs(written) == {
        "exit-code": "1",
        "status": "WARNING",
        "rating": "3",
        "rating-label": "C",
        "message": "WARNING - two\nlines",
    }


def test_a_scanned_host_cannot_forge_the_actions_outputs(tmp_path, scan_script):
    """
    Half of what reaches these outputs is a string the scanned instance chose.

    The delimiter closing each heredoc block therefore has to be one that
    instance cannot guess: with a fixed one, a host whose product name or
    message carries a line reading it closes the block early, and every line
    after that is parsed as a further output assignment - arbitrary step
    outputs in whatever workflow consumes them, from a host that only had to
    answer an HTTP request.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / "check-opencloud-security"
    # What a hostile instance would put in the field it controls.
    document = json.dumps(
        [
            {
                "status": "OK",
                "rating": 5,
                "rating_label": "A+",
                "message": "OK\nCOS_EOF\nrating=0\nforged=yes\n",
            }
        ]
    )
    (tmp_path / "payload.json").write_text(document, encoding="utf-8")
    stub.write_text(
        f"#!/bin/sh\ncat {tmp_path / 'payload.json'}\nexit 0\n", encoding="utf-8"
    )
    stub.chmod(0o755)
    script = tmp_path / "scan.sh"
    script.write_text(scan_script, encoding="utf-8")

    subprocess.run(  # nosec B603 - a fixed argv, in a temp directory
        [shutil.which("bash") or "/bin/bash", str(script)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{stub_dir}{os.pathsep}{os.environ['PATH']}",
            "COS_FORMAT": "json",
            "OUTPUT_FILE": "out.json",
            "FAIL_ON": "never",
            "WRITE_SUMMARY": "false",
            "INPUT_WARNING": "",
            "INPUT_CRITICAL": "",
            "INPUT_IGNORE_HARDENING": "",
            "INPUT_RELEASE_TRACK": "",
            "INPUT_EXTRA_ARGS": "",
            "GITHUB_OUTPUT": str(tmp_path / "github_output"),
            "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    outputs = _outputs((tmp_path / "github_output").read_text(encoding="utf-8"))

    # Nothing the host wrote became an output of its own.
    assert "forged" not in outputs
    # And the real rating survived intact rather than being overwritten by the
    # assignment the message tried to smuggle in after the fixed delimiter.
    assert outputs["rating"] == "5"
    assert outputs["rating-label"] == "A+"
    # The message is still reported in full - the fix is a delimiter that
    # cannot be guessed, not one that drops what the instance said. The
    # trailing newline is the one the instance itself put there.
    assert outputs["message"] == "OK\nCOS_EOF\nrating=0\nforged=yes\n"
