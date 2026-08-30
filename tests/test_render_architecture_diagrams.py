"""The Mermaid-diagram-to-PNG pairing in ARCHITECTURE.md."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module():
    path = REPO_ROOT / "scripts" / "render_architecture_diagrams.py"
    spec = importlib.util.spec_from_file_location("render_architecture_diagrams", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_architecture_diagrams"] = module
    spec.loader.exec_module(module)
    return module


rad = _load_module()

SAMPLE = """# Architecture

## Three layers

Some prose.

```mermaid
flowchart TD
    a --> b
```

## Concurrency

More prose.
"""


def test_find_diagrams_captures_source_and_nearest_heading():
    diagrams = rad.find_diagrams(SAMPLE)

    assert len(diagrams) == 1
    assert diagrams[0].heading == "Three layers"
    assert diagrams[0].source == "flowchart TD\n    a --> b"


def test_image_path_is_derived_from_the_nearest_heading():
    diagrams = rad.find_diagrams(SAMPLE)

    assert rad.image_path(diagrams[0]) == "img/architecture-three-layers.png"


def test_image_path_falls_back_to_a_numbered_name_without_a_heading():
    headingless = "```mermaid\nflowchart TD\n    a --> b\n```\n"
    diagrams = rad.find_diagrams(headingless)

    assert rad.image_path(diagrams[0]) == "img/architecture-diagram-1.png"


def test_ensure_image_references_inserts_a_missing_image_line():
    diagrams = rad.find_diagrams(SAMPLE)

    updated = rad.ensure_image_references(SAMPLE, diagrams)

    assert "![Three layers architecture diagram](img/architecture-three-layers.png)" in updated
    # The heading that follows the diagram must not have moved.
    assert updated.index("## Concurrency") > updated.index("architecture-three-layers.png")


def test_ensure_image_references_is_idempotent():
    diagrams = rad.find_diagrams(SAMPLE)
    once = rad.ensure_image_references(SAMPLE, diagrams)

    diagrams_again = rad.find_diagrams(once)
    twice = rad.ensure_image_references(once, diagrams_again)

    assert once == twice


def test_ensure_image_references_handles_several_diagrams_without_shifting_offsets():
    text = (
        "# Doc\n\n"
        "## First\n\n```mermaid\nflowchart TD\n    a --> b\n```\n\n"
        "## Second\n\n```mermaid\nflowchart TD\n    c --> d\n```\n"
    )
    diagrams = rad.find_diagrams(text)

    updated = rad.ensure_image_references(text, diagrams)

    assert "![First architecture diagram](img/architecture-first.png)" in updated
    assert "![Second architecture diagram](img/architecture-second.png)" in updated
    assert updated.index("architecture-first.png") < updated.index("## Second")


def test_write_diagram_sources_writes_mmd_files_and_a_manifest(tmp_path):
    diagrams = rad.find_diagrams(SAMPLE)

    manifest = rad.write_diagram_sources(diagrams, tmp_path)

    mmd_path = tmp_path / "1.mmd"
    assert mmd_path.read_text(encoding="utf-8") == "flowchart TD\n    a --> b\n"
    assert manifest.read_text(encoding="utf-8") == f"{mmd_path}\timg/architecture-three-layers.png\n"


def test_architecture_md_already_has_an_image_for_every_diagram():
    """The checked-in file must already satisfy `--check` - see ARCHITECTURE.md."""
    text = (REPO_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    diagrams = rad.find_diagrams(text)

    assert diagrams, "expected at least one ```mermaid fence in ARCHITECTURE.md"
    assert rad.ensure_image_references(text, diagrams) == text
    for diagram in diagrams:
        image = REPO_ROOT / rad.image_path(diagram)
        assert image.is_file() and image.stat().st_size > 0
