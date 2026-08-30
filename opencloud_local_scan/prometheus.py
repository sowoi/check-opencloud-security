"""Prometheus text exposition for OpenCloud scan result documents."""

from __future__ import annotations

from collections import Counter
from typing import Any


def _escape_label(value: object) -> str:
    """Escape arbitrary scan values for a Prometheus label string."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )


def _labels(**values: object) -> str:
    """Render label values safely, including hostnames and scanner metadata."""
    return "{" + ",".join(
        f'{name}="{_escape_label(value)}"' for name, value in values.items()
    ) + "}"


def _family(name: str, help_text: str, samples: list[tuple[str, float]]) -> list[str]:
    """Render one Gauge metric family in Prometheus' text exposition format."""
    lines = [f"# HELP {name} {help_text}", f"# TYPE {name} gauge"]
    lines.extend(f"{name}{labels} {value:g}" for labels, value in samples)
    return lines


def render(
    host: str,
    result: dict[str, Any] | None,
    *,
    duration_seconds: float,
    success: bool,
) -> str:
    """
    Convert one scan outcome to Prometheus metrics.

    A failed scan emits only its duration and scrape-success samples. This
    prevents stale findings from being presented as current evidence.
    """
    outcome = result or {}
    product = outcome.get("product") or "unknown"
    domain = outcome.get("domain") or host
    version = outcome.get("version") or "unknown"
    base_labels = _labels(host=host)
    lines: list[str] = []

    if success:
        rating = outcome.get("rating")
        if isinstance(rating, int):
            lines.extend(
                _family(
                    "opencloud_security_rating_score",
                    "OpenCloud security rating score from zero to five.",
                    [
                        (
                            _labels(
                                host=host,
                                domain=domain,
                                product=product,
                                version=version,
                            ),
                            rating,
                        )
                    ],
                )
            )

        vulnerabilities = outcome.get("vulnerabilities")
        counts = Counter(
            str(entry.get("severity") or "unknown").lower()
            for entry in vulnerabilities if isinstance(entry, dict)
        ) if isinstance(vulnerabilities, list) else Counter()
        lines.extend(
            _family(
                "opencloud_security_vulnerabilities_total",
                "Known OpenCloud vulnerabilities by severity.",
                [
                    (_labels(host=host, severity=severity), count)
                    for severity, count in sorted(counts.items())
                ]
                or [(_labels(host=host, severity="unknown"), 0)],
            )
        )

        hardenings = outcome.get("hardenings")
        missing_hardenings = sum(not enabled for enabled in hardenings.values()) if isinstance(
            hardenings, dict
        ) else 0
        setup = outcome.get("setup")
        if isinstance(setup, dict):
            https = setup.get("https")
            if isinstance(https, dict) and not https.get("enforced", True):
                missing_hardenings += 1
            headers = setup.get("headers")
            if isinstance(headers, dict):
                missing_hardenings += sum(not enabled for enabled in headers.values())
        lines.extend(
            _family(
                "opencloud_security_hardenings_missing_total",
                "Missing OpenCloud hardening measures.",
                [(base_labels, missing_hardenings)],
            )
        )

        extra_checks = outcome.get("extraChecks")
        failed_checks = (
            sum(
                isinstance(check, dict) and check.get("passed") is False
                for check in extra_checks
            )
            if isinstance(extra_checks, list)
            else 0
        )
        lines.extend(
            _family(
                "opencloud_security_failed_extra_checks_total",
                "Failed additional OpenCloud security checks.",
                [(base_labels, failed_checks)],
            )
        )

        lifecycle = outcome.get("lifecycle")
        release_type = "unknown"
        if isinstance(lifecycle, dict) and lifecycle.get("releaseType"):
            release_type = str(lifecycle["releaseType"])
        # Deliberately its own family rather than a negative
        # `support_days_remaining`: a rolling or production release that has
        # not been dated yet reports no days at all, and "unknown" must not
        # read as "expiring today" in the one alert nobody may miss.
        lines.extend(
            _family(
                "opencloud_security_end_of_life",
                "Whether the OpenCloud release has reached end of life.",
                [
                    (
                        _labels(host=host, release_type=release_type),
                        int(bool(outcome.get("EOL"))),
                    )
                ],
            )
        )

        if isinstance(lifecycle, dict) and isinstance(lifecycle.get("daysRemaining"), int):
            lines.extend(
                _family(
                    "opencloud_security_support_days_remaining",
                    "Days remaining before the OpenCloud release reaches end of life.",
                    [
                        (
                            _labels(
                                host=host,
                                release_type=lifecycle.get("releaseType") or "unknown",
                            ),
                            lifecycle["daysRemaining"],
                        )
                    ],
                )
            )

        updates = outcome.get("updates")
        if isinstance(updates, dict):
            lines.extend(
                _family(
                    "opencloud_security_update_available",
                    "Whether an OpenCloud update is available.",
                    [
                        (
                            _labels(
                                host=host,
                                target_version=updates.get("availableVersion")
                                or updates.get("version")
                                or "unknown",
                            ),
                            int(bool(updates.get("available"))),
                        )
                    ],
                )
            )

    lines.extend(
        _family(
            "opencloud_security_scan_duration_seconds",
            "Duration of the OpenCloud security scan.",
            [(base_labels, duration_seconds)],
        )
    )
    lines.extend(
        _family(
            "opencloud_security_scrape_success",
            "Whether the OpenCloud security scan completed successfully.",
            [(base_labels, int(success))],
        )
    )
    return "\n".join(lines) + "\n"
