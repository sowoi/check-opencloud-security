#!/usr/bin/env python3
"""Keep the Mermaid diagrams in ARCHITECTURE.md paired with a rendered PNG.

This script does the text half of the job only: it finds every ```mermaid
fence, writes its source to its own file for a renderer to pick up, and makes
sure a Markdown image line for the resulting PNG follows the fence. Actually
turning that source into a PNG needs a Mermaid renderer (`mmdc`, from
`@mermaid-js/mermaid-cli`), which is a Node tool this project has no other use
for - so it is not a dependency of this script or of `pyproject.toml`, only of
the CI job that calls both in turn. See
`.github/workflows/render-architecture-diagram.yml`.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = REPO_ROOT / "ARCHITECTURE.md"
IMAGE_DIR = "img"

FENCE_RE = re.compile(r"^```mermaid\s*$", re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
IMAGE_LINE_RE = re.compile(r"^!\[[^\]]*\]\(img/[^)]+\)\s*$")


@dataclass
class Diagram:
    index: int
    heading: str | None
    source: str
    fence_end: int  # index into the original text, just past the closing ```


def _slugify(text: str) -> str:
    """A filesystem-friendly slug - not the GitHub anchor algorithm, just a name."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "diagram"


def _nearest_heading(text: str, before: int) -> str | None:
    """The text of the last heading that starts before offset `before`."""
    heading = None
    for line in text[:before].splitlines():
        m = HEADING_RE.match(line)
        if m:
            heading = m.group(2)
    return heading


def find_diagrams(text: str) -> list[Diagram]:
    """Every ```mermaid ... ``` block, in document order."""
    diagrams = []
    index = 0
    pos = 0
    while True:
        start_match = FENCE_RE.search(text, pos)
        if start_match is None:
            break
        body_start = start_match.end() + 1
        end_match = re.search(r"^```\s*$", text[body_start:], re.MULTILINE)
        if end_match is None:
            raise ValueError("unterminated ```mermaid fence")
        index += 1
        source = text[body_start : body_start + end_match.start()].rstrip("\n")
        fence_end = body_start + end_match.end()
        heading = _nearest_heading(text, start_match.start())
        diagrams.append(Diagram(index, heading, source, fence_end))
        pos = fence_end
    return diagrams


def image_path(diagram: Diagram) -> str:
    name = _slugify(diagram.heading) if diagram.heading else f"diagram-{diagram.index}"
    return f"{IMAGE_DIR}/architecture-{name}.png"


def alt_text(diagram: Diagram) -> str:
    if diagram.heading:
        return f"{diagram.heading} architecture diagram"
    return "Architecture diagram"


def _has_image_line(text: str, fence_end: int) -> bool:
    """Whether an `img/...` Markdown image already immediately follows the fence."""
    rest = text[fence_end:].lstrip("\n")
    first_line = rest.split("\n", 1)[0] if rest else ""
    return bool(IMAGE_LINE_RE.match(first_line))


def ensure_image_references(text: str, diagrams: list[Diagram]) -> str:
    """Insert `![alt](img/...)` after any diagram that does not already have one.

    Processed back to front so earlier insertion points are not shifted by a
    later one.
    """
    for diagram in reversed(diagrams):
        if _has_image_line(text, diagram.fence_end):
            continue
        line = f"\n![{alt_text(diagram)}]({image_path(diagram)})\n"
        text = text[: diagram.fence_end] + line + text[diagram.fence_end :]
    return text


def write_diagram_sources(diagrams: list[Diagram], out_dir: Path) -> Path:
    """Write each diagram's source next to a manifest CI can render from.

    The manifest is TSV: the `.mmd` path CI should render, a tab, then the
    repository-relative PNG path `ensure_image_references` already pointed
    the Markdown at.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "manifest.tsv"
    with manifest.open("w", encoding="utf-8") as handle:
        for diagram in diagrams:
            mmd_path = out_dir / f"{diagram.index}.mmd"
            mmd_path.write_text(diagram.source + "\n", encoding="utf-8")
            handle.write(f"{mmd_path}\t{image_path(diagram)}\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path", nargs="?", type=Path, default=DEFAULT_TARGET, help="Markdown file to scan"
    )
    parser.add_argument(
        "--diagrams-dir",
        type=Path,
        default=REPO_ROOT / ".diagrams",
        help="where to write extracted .mmd sources and the render manifest",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the file is missing an image reference, without writing anything",
    )
    args = parser.parse_args()

    original = args.path.read_text(encoding="utf-8")
    diagrams = find_diagrams(original)
    if not diagrams:
        print(f"no ```mermaid fences found in {args.path}", file=sys.stderr)
        return 0

    updated = ensure_image_references(original, diagrams)

    if args.check:
        if updated != original:
            print(
                f"{args.path} is missing an image reference after a mermaid "
                "fence; run scripts/render_architecture_diagrams.py",
                file=sys.stderr,
            )
            return 1
        return 0

    if updated != original:
        args.path.write_text(updated, encoding="utf-8")

    manifest = write_diagram_sources(diagrams, args.diagrams_dir)
    print(f"wrote {len(diagrams)} diagram source(s), manifest at {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
