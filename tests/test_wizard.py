"""Tests for the interactive setup behind ``--configure``."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from opencloud_local_scan import config as config_module
from opencloud_local_scan import wizard
from opencloud_local_scan.factory import (
    release_settings_from_config,
    scanner_settings_from_config,
)


def scripted(answers, out=None):
    """A prompter that replays fixed answers and records everything it says."""
    remaining = list(answers)
    recorded = out if out is not None else []

    def read(prompt: str) -> str:
        recorded.append(prompt)
        if not remaining:
            return ""
        return remaining.pop(0)

    return wizard.Prompter(input=read, output=recorded.append), recorded


def test_the_wizard_asks_only_for_the_host_when_optional_settings_are_declined():
    """An operator who wants a working setup should have to answer one question."""
    prompter, said = scripted(["opencloud.example.com", "n"])

    data = wizard.collect(prompter)

    assert data == {"host": "opencloud.example.com"}
    assert "port" not in "\n".join(said).lower().split("optional")[0]


def test_optional_settings_are_only_asked_for_when_the_operator_says_so():
    """Optional questions must not appear unless they were explicitly requested."""
    declined, said_no = scripted(["opencloud.example.com", "n"])
    wizard.collect(declined)

    accepted, said_yes = scripted(
        ["opencloud.example.com", "y", "y", "9200", "", "", "", ""]
    )
    result = wizard.collect(accepted)

    assert "Configure Connection" not in "\n".join(said_no)
    assert "Configure Connection" in "\n".join(said_yes)
    assert result["scanner"]["target_port"] == 9200


def test_every_question_explains_itself_and_shows_an_example():
    """A prompt the operator cannot act on is worse than no prompt at all."""
    questions = list(wizard.required_questions())
    for group in wizard.optional_groups():
        questions.extend(group.questions)

    assert questions
    for question in questions:
        assert len(question.explain.split()) >= 8, question.key
        assert question.example.strip(), question.key
        assert question.prompt.strip(), question.key


def test_a_declined_optional_group_leaves_its_keys_out_of_the_file():
    """Skipping a group must mean defaults apply, not that empty values are written."""
    prompter, _ = scripted(["opencloud.example.com", "y", "n", "n", "n", "n", "n"])

    data = wizard.collect(prompter)

    assert data == {"host": "opencloud.example.com"}


def test_an_answer_that_does_not_validate_is_asked_again():
    """A rejected answer must not be silently written into the configuration."""
    prompter, said = scripted(
        ["opencloud.example.com", "y", "y", "99999", "8443", "", "", "", ""]
    )

    data = wizard.collect(prompter)

    assert data["scanner"]["target_port"] == 8443
    assert any("1 and 65535" in line for line in said)


def test_the_saved_file_is_read_back_by_the_normal_configuration_loader(tmp_path):
    """The point of the wizard is that the check then finds the settings by itself."""
    prompter, _ = scripted(
        ["opencloud.example.com", "y", "y", "9200", "", "n", "", "", "n", "n", "n", "n"]
    )
    data = wizard.collect(prompter)
    target = tmp_path / ".env.json"

    wizard.save(data, target)
    config = config_module.load_configuration(str(target))
    settings = scanner_settings_from_config(config)

    assert config.get("HOST") == "opencloud.example.com"
    assert settings.port == 9200
    assert settings.verify_tls is False
    assert release_settings_from_config(config) is not None


def test_the_saved_file_is_json_and_readable_only_by_its_owner(tmp_path):
    """It can hold a webhook URL or a release token, so it must not be world-readable."""
    target = tmp_path / ".env.json"

    wizard.save({"host": "opencloud.example.com"}, target)

    assert json.loads(target.read_text()) == {"host": "opencloud.example.com"}
    mode = stat.S_IMODE(os.stat(target).st_mode)
    assert mode & (stat.S_IRGRP | stat.S_IROTH) == 0
    assert mode == 0o600


def test_aborting_the_wizard_writes_nothing(tmp_path):
    """Ctrl-C during setup must not leave a half-written configuration behind."""
    target = tmp_path / ".env.json"

    def read(prompt: str) -> str:
        raise KeyboardInterrupt

    prompter = wizard.Prompter(input=read, output=lambda _: None)
    code = wizard.run(prompter, path=str(target))

    assert code == 1
    assert not target.exists()


def test_an_existing_file_is_shown_and_confirmed_before_it_is_replaced(tmp_path):
    """A misremembered --configure must not quietly discard a working setup."""
    target = tmp_path / ".env.json"
    target.write_text(json.dumps({"host": "old.example.com"}))

    prompter, said = scripted(["opencloud.example.com", "n", "n"])
    code = wizard.run(prompter, path=str(target))

    assert code == 1
    assert json.loads(target.read_text()) == {"host": "old.example.com"}
    assert any("old.example.com" in line for line in said)

    replacing, _ = scripted(["opencloud.example.com", "n", "y"])
    assert wizard.run(replacing, path=str(target)) == 0
    assert json.loads(target.read_text()) == {"host": "opencloud.example.com"}


def test_a_list_answer_becomes_a_list_the_scanner_understands(tmp_path):
    """Waivers are entered as one line but must reach the scanner as separate ids."""
    prompter, _ = scripted(
        [
            "opencloud.example.com",
            "y",
            "n",
            "n",
            "n",
            "n",
            "y",
            "",
            "",
            "hsts:missing, basic-auth",
        ]
    )
    data = wizard.collect(prompter)
    target = tmp_path / ".env.json"
    wizard.save(data, target)

    settings = scanner_settings_from_config(config_module.load_configuration(str(target)))

    assert data["scanner"]["ignore_hardenings"] == ["hsts:missing", "basic-auth"]
    assert set(settings.ignore_hardenings) == {"hsts:missing", "basic-auth"}


def test_a_non_json_filename_is_offered_a_json_suffix_instead(tmp_path):
    """Saving JSON under a .yml name would produce a file the loader cannot parse."""
    prompter, said = scripted(["opencloud.example.com", "n", "", "n"])

    code = wizard.run(prompter, path=str(tmp_path / "settings.yml"))

    assert code == 0
    assert (tmp_path / "settings.json").exists()
    assert not (tmp_path / "settings.yml").exists()
    assert any("not a .json file" in line for line in said)


@pytest.mark.parametrize(
    ("bad", "good"),
    [("maybe", "y"), ("7", "3"), ("nine", "4")],
)
def test_validators_reject_before_they_accept(bad, good):
    """A validator that never rejects anything is the same as no validator."""
    checks = {
        "maybe": wizard._choice(("y", "n")),
        "7": wizard._rating,
        "nine": wizard._concurrency,
    }
    check = checks[bad]

    assert check(bad) is not None
    assert check(good) is None


def test_the_wizard_writes_keys_the_loader_actually_maps(tmp_path):
    """A typo in a key would produce a file that looks right and changes nothing."""
    keys = [question.key for question in wizard.required_questions()]
    for group in wizard.optional_groups():
        keys.extend(question.key for question in group.questions)

    document: dict = {}
    for key in keys:
        wizard._assign(document, key, "x")
    target = tmp_path / ".env.json"
    target.write_text(json.dumps(document))

    config = config_module.load_configuration(str(target))

    for key in keys:
        env_name = key.replace(".", "_").upper()
        assert config.get(env_name) == "x", key


def test_the_configuration_file_is_found_without_being_named(tmp_path, monkeypatch):
    """After setup the check must run with no arguments at all."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("COS_CONFIG_FILE", raising=False)
    monkeypatch.delenv("COS_HOST", raising=False)
    wizard.save({"host": "opencloud.example.com"}, Path(wizard.DEFAULT_CONFIG_NAME))

    config = config_module.load_configuration(None)

    assert config.get("HOST") == "opencloud.example.com"
