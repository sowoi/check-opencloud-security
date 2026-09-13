"""The hand-maintained indexes agree with what they index.

AGENTS.md asks for three of them to be kept in sync by hand: the table of
contents at the top of README.md, the page index in docs/README.md, and the
manifest in webapp/documentation.py that makes a guide browsable under
/documentation. Each drifts silently - a renamed heading leaves a dead link, a
new guide is simply unreachable - so each is asserted here rather than left to
the pull request checklist.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDES = sorted(p for p in (ROOT / "docs").glob("*.md") if p.name != "README.md")


def _headings(markdown: str) -> list[tuple[int, str]]:
    """Every ATX heading outside a fenced code block, with its level."""
    found, fenced = [], False
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        match = None if fenced else re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if match:
            found.append((len(match.group(1)), match.group(2)))
    return found


def _anchor(heading: str) -> str:
    """The anchor GitHub gives a heading: lower case, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", re.sub(r"<[^>]+>", "", heading))
    return re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")


def _readme_contents() -> tuple[list[str], list[tuple[int, str]]]:
    """The anchors the README's table of contents links to, and the README's headings."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    contents = readme.split("\n# ", 1)[0]
    return re.findall(r"\]\(#([^)]+)\)", contents), _headings(readme)


def test_the_readme_has_a_table_of_contents():
    """The guard on the two tests below: an empty list passes both."""
    links, headings = _readme_contents()

    assert links and headings


def test_every_readme_contents_entry_leads_to_a_heading() -> None:
    """A renamed heading leaves an entry that scrolls nowhere."""
    links, headings = _readme_contents()
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for _, heading in headings:
        anchor = _anchor(heading)
        anchors.add(anchor if anchor not in seen else f"{anchor}-{seen[anchor]}")
        seen[anchor] = seen.get(anchor, 0) + 1

    assert [link for link in links if link not in anchors] == []


def test_every_top_level_readme_section_is_in_the_contents():
    """A new `#` or `##` section nobody added to the contents is one nobody finds."""
    links, headings = _readme_contents()

    missing = [text for level, text in headings if level <= 2 and _anchor(text) not in links]

    assert missing == []


def test_every_guide_is_listed_in_the_docs_index():
    """docs/README.md is where a reader looks for a guide; an unlisted one is invisible."""
    index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")

    assert GUIDES
    assert [guide.name for guide in GUIDES if f"{guide.name})" not in index] == []


def test_every_guide_is_browsable_under_documentation():
    """A guide absent from the manifest is never rendered and never searchable."""
    manifest = (ROOT / "webapp" / "documentation.py").read_text(encoding="utf-8")

    assert [guide.name for guide in GUIDES if guide.name not in manifest] == []
