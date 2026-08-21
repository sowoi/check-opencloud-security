"""Opt-in integration coverage against a real OpenCloud container."""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid

import pytest

from opencloud_local_scan.scanner import ScannerSettings, scan

IMAGE = "COS_INTEGRATION_IMAGE"
STARTUP_TIMEOUT = 180

pytestmark = pytest.mark.integration


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=check,
        capture_output=True,
        text=True,
        timeout=STARTUP_TIMEOUT,
    )  # nosec B603 - arguments are fixed docker subcommands and test inputs


def _wait_for_status(url: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(2)
    raise AssertionError("OpenCloud container did not expose /status.php in time")


def test_scanner_rates_a_real_opencloud_container() -> None:
    """The scanner must work against the vendor container, not only a fixture."""
    image = os.environ.get(IMAGE)
    if not image:
        pytest.skip(f"set {IMAGE} to run the real-container integration test")
    if shutil.which("docker") is None:
        pytest.skip("Docker is not available")

    pulled = _docker("pull", image, check=False)
    if pulled.returncode:
        pytest.skip(f"OpenCloud image is unavailable: {image}")

    suffix = uuid.uuid4().hex[:12]
    config_volume = f"cos-integration-config-{suffix}"
    data_volume = f"cos-integration-data-{suffix}"
    container = f"cos-integration-{suffix}"
    password = secrets.token_urlsafe(24)

    try:
        _docker("volume", "create", config_volume)
        _docker("volume", "create", data_volume)
        initialized = _docker(
            "run",
            "--rm",
            "-e",
            f"IDM_ADMIN_PASSWORD={password}",
            "-v",
            f"{config_volume}:/etc/opencloud",
            "-v",
            f"{data_volume}:/var/lib/opencloud",
            image,
            "init",
            check=False,
        )
        if initialized.returncode:
            pytest.skip(
                "OpenCloud image does not support the expected init workflow; "
                "set COS_INTEGRATION_IMAGE to a compatible version"
            )

        started = _docker(
            "run",
            "-d",
            "--name",
            container,
            "-e",
            "OC_INSECURE=true",
            "-e",
            "PROXY_HTTP_ADDR=0.0.0.0:9200",
            "-e",
            "OC_URL=http://127.0.0.1:9200",
            "-v",
            f"{config_volume}:/etc/opencloud",
            "-v",
            f"{data_volume}:/var/lib/opencloud",
            "-p",
            "127.0.0.1::9200",
            image,
        )
        assert started.stdout.strip()

        published = _docker("port", container, "9200/tcp").stdout.strip()
        port = published.rsplit(":", 1)[-1]
        _wait_for_status(f"http://127.0.0.1:{port}/status.php")

        result = scan(
            f"127.0.0.1:{port}",
            settings=ScannerSettings(
                scheme="http",
                timeout=10,
                verify_tls=False,
                check_debug_ports=False,
                concurrency=2,
                use_release_schedule=False,
            ),
        )

        assert result["product"].lower() == "opencloud"
        assert result["version"]
        assert 0 <= result["rating"] <= 5
    finally:
        _docker("rm", "--force", container, check=False)
        _docker("volume", "rm", config_volume, data_volume, check=False)
