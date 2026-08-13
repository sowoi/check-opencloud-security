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
    code = wizard.run(prompter, path=str(target), verify=False)

    assert code == 1
    assert not target.exists()


def test_an_existing_file_is_shown_and_confirmed_before_it_is_replaced(tmp_path):
    """A misremembered --configure must not quietly discard a working setup."""
    target = tmp_path / ".env.json"
    target.write_text(json.dumps({"host": "old.example.com"}))

    prompter, said = scripted(["opencloud.example.com", "n", "n"])
    code = wizard.run(prompter, path=str(target), verify=False)

    assert code == 1
    assert json.loads(target.read_text()) == {"host": "old.example.com"}
    assert any("old.example.com" in line for line in said)

    replacing, _ = scripted(["opencloud.example.com", "n", "y"])
    assert wizard.run(replacing, path=str(target), verify=False) == 0
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

    code = wizard.run(prompter, path=str(tmp_path / "settings.yml"), verify=False)

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


# --- Editing an existing configuration ---


def test_an_existing_value_is_offered_as_the_default(tmp_path):
    """Re-running --configure to change one setting must not retype the rest."""
    stored = {"host": "old.example.com", "scanner": {"target_port": 9200}}

    prompter, said = scripted(["", "n"])
    data = wizard.collect(prompter, existing=stored)

    assert data["host"] == "old.example.com", "Enter kept the configured host"
    assert data["scanner"]["target_port"] == 9200
    assert any("old.example.com" in line for line in said)
    assert any("Configured now" in line for line in said)


def test_a_configured_value_can_be_removed_on_purpose(tmp_path):
    """Enter has to mean 'keep', so removing needs a spelling of its own."""
    stored = {"host": "old.example.com", "webhook": {"url": "https://hooks.example.com/x"}}

    # host, review optional, skip Connection, skip Thresholds, enter Webhook,
    # clear the URL, keep the rest, skip the last two groups.
    prompter, said = scripted(
        ["new.example.com", "y", "n", "n", "y", "-", "", "", "n", "n"]
    )
    data = wizard.collect(prompter, existing=stored)

    assert data["host"] == "new.example.com"
    assert "url" not in data.get("webhook", {}), data
    assert any(wizard.CLEAR in line and "removes it" in line for line in said)


def test_hand_edited_keys_the_wizard_never_asks_about_survive(tmp_path):
    """--configure must not be a way to silently lose settings added by hand."""
    stored = {
        "host": "old.example.com",
        "scanner": {"user_agent": "custom/1.0"},
        "something_added_later": True,
    }

    prompter, _ = scripted(["", "n"])
    data = wizard.collect(prompter, existing=stored)

    assert data["something_added_later"] is True
    assert data["scanner"]["user_agent"] == "custom/1.0"


def test_the_existing_file_is_read_and_named(tmp_path):
    """An editor that silently starts from the wrong file is worse than none."""
    target = tmp_path / ".env.json"
    target.write_text(json.dumps({"host": "old.example.com"}))

    prompter, said = scripted(["", "n", "y"])
    code = wizard.run(prompter, path=str(target), verify=False)

    assert code == 0
    assert json.loads(target.read_text()) == {"host": "old.example.com"}
    assert any(str(target) in line for line in said)


def test_the_settings_are_offered_for_a_test_scan_before_saving(tmp_path):
    """A wizard that cannot tell you whether its output works is just a form."""
    from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour

    target = tmp_path / ".env.json"
    with FakeOpenCloud(InstanceBehaviour()) as instance:
        host, _, port = instance.host.partition(":")
        prompter, said = scripted(
            [
                host,
                "y",  # review the optional settings
                "y",  # connection group
                port,
                "http",  # scheme
                "",
                "",
                "n",  # skip the remaining groups
                "n",
                "n",
                "n",
                "n",
                "y",  # yes, test these settings
            ]
        )
        code = wizard.run(prompter, path=str(target))

    transcript = "\n".join(said)
    assert "Test these settings" in transcript
    assert code == 0, transcript
    assert "OpenCloud 7.2.3" in transcript
    assert "The settings work." in transcript


def test_a_failing_test_scan_still_lets_the_operator_save(tmp_path):
    """The file may well be written somewhere that cannot reach the instance."""
    target = tmp_path / ".env.json"
    prompter, said = scripted(
        [
            "127.0.0.1:1",  # nothing listens here
            "n",  # no optional settings
            "y",  # test the settings
            "y",  # save anyway
        ]
    )

    code = wizard.run(prompter, path=str(target))

    transcript = "\n".join(said)
    assert code == 0, transcript
    assert "test scan failed" in transcript.lower()
    assert target.exists()
