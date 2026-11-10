"""
The published guides state facts plainly, in all four languages.

``tests/test_translation_quality.py`` keeps marketing words out. This file
keeps out the sentence habits that made the guides read as generated text
and were removed from them in one pass: a closing aphorism, a punchline, a
lead-in that announces information instead of giving it, and adverbs that
only assert intent. Each rule below names a habit, shows what it looked
like, and says what to write instead - the failure message carries all
three, so whoever trips a rule can fix the sentence without opening this
file.

Two kinds of rule, because the habits are of two kinds:

* ``BANNED`` phrases carry no information in a guide. They occur nowhere,
  and a new occurrence fails.
* ``BUDGETS`` cover words that are sometimes a fact ("the scan deliberately
  does not follow that host") and sometimes padding ("that is deliberate").
  A machine cannot tell the two apart, so the count per language may fall
  and may not rise. A sentence that needs the word takes the place of one
  that did not.

Headings, tables of contents and code blocks are not checked: headings are
anchors other pages link to, and code is quoted, not written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from webapp.documentation import (
    DOCUMENTATION_PAGES,
    GUIDE_LANGUAGES,
    OPERATOR_DOCUMENTATION_PAGES,
    TRANSLATED_OPERATOR_SLUGS,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Rule:
    """One sentence habit: how to find it, and how to write the sentence instead."""

    name: str
    pattern: str
    instead: str


BANNED: dict[str, tuple[Rule, ...]] = {
    "en": (
        Rule(
            "closing aphorism",
            r"\bis noise\b|\bnobody (?:reads|prunes)\b|\bcries wolf\b|\bblindfold\b"
            r"|\bis a hypothesis\b|\btomorrow problem\b|\bthe honest way\b",
            "State the consequence: 'Nobody can clear these warnings, so alerting on "
            "them would only distract from findings that can be fixed.'",
        ),
        Rule(
            "summary flourish",
            r"\bthat is the whole\b|\bthe whole (?:point|thing|of it)\b"
            r"|\bis the point\b|\bthat is the trade\b",
            "Delete it and start with the next sentence, or name the purpose: "
            "'The discovery document exists for this.'",
        ),
        Rule(
            "announcing lead-in",
            r"\bworth (?:knowing|naming|noting|stating)\b",
            "Give the information: 'Three settings matter here:' or 'Two rules apply:'.",
        ),
        Rule(
            "asserted intent",
            r"\bon purpose\b|\b(?:is|are) deliberate\.|\bthat is deliberate\b",
            "Give the reason instead of saying there is one, or drop the phrase: "
            "'The package configures nothing.'",
        ),
        Rule(
            "negated flourish",
            r"\bnot (?:optional )?decoration\b",
            "Say what it is: 'PKCE is required: it replaces the client secret.'",
        ),
        Rule(
            "emphatic adverb",
            r"\bprecisely\b|\bwhich is exactly\b|\bis exactly the\b",
            "Drop the adverb. 'the same' or 'that' says as much.",
        ),
    ),
    "de": (
        Rule(
            "Aphorismus am Absatzende",
            r"\bist Rauschen\b|\bliest niemand\b|\bniemand liest\b|\bganze Stärke\b",
            "Nenne die Folge: 'also schützt es allein seine Länge.'",
        ),
        Rule(
            "behauptete Absicht",
            r"\bmit Absicht\b|\bDas ist bewusst\b|\bbewusst zurückhaltend\b",
            "Nenne den Grund oder streiche das Wort.",
        ),
        Rule(
            "Füllwort",
            r"\bschlicht\b|\bstillschweigend\b|\bgenau das\.",
            "Streiche das Wort; der Satz sagt ohne es dasselbe.",
        ),
    ),
    "fr": (
        Rule(
            "aphorisme final",
            r"\best une hypothèse\b|\bmanière honnête\b|\bbandeau sur les yeux\b"
            r"|\bque (?:plus )?personne ne (?:lit|nettoie)\b",
            "Énoncez la conséquence : 'l’on cesse de regarder un contrôle qui ne "
            "change jamais.'",
        ),
        Rule(
            "formule de synthèse",
            r"\bc.est tout(?: pour\b|\.)|\bc.est toute (?:la raison|l.affirmation)\b"
            r"|\btout l.intérêt\b|\bc.est le compromis\b",
            "Supprimez-la, ou nommez le but : 'Le document de découverte existe pour cela.'",
        ),
        Rule(
            "annonce sans contenu",
            r"\bbon(?:ne)?s? à (?:savoir|connaître)\b|\bméritent? d.être (?:dit|connu|su)",
            "Donnez l’information : 'Trois paramètres comptent ici :'.",
        ),
        Rule(
            "adverbe de remplissage",
            r"\btout simplement\b|\bdécoration\b",
            "Supprimez-le ; la phrase dit la même chose sans lui.",
        ),
    ),
    "es": (
        Rule(
            "aforismo final",
            r"\bes ruido\b|\bnadie (?:lee|depura)\b|\bes una hipótesis\b"
            r"|\bforma honesta\b|\bvenda en los ojos\b",
            "Indique la consecuencia: 'se deja de mirar una comprobación que nunca cambia.'",
        ),
        Rule(
            "fórmula de cierre",
            r"\beso es todo\b|\brazón de ser\b|\bese es el (?:objetivo|compromiso)\b",
            "Elimínela, o nombre la finalidad: 'El documento de descubrimiento "
            "existe para eso.'",
        ),
        Rule(
            "anuncio sin contenido",
            r"\bconviene (?:saber|conocer)\b|\bmerece decirse\b",
            "Dé la información: 'Aquí importan tres ajustes:'.",
        ),
        Rule(
            "relleno",
            r"\bun adorno\b|\bdecoración\b",
            "Diga qué es: 'PKCE es obligatorio: sustituye al secreto de cliente.'",
        ),
    ),
}

#: Words that are sometimes a fact and sometimes padding, with the number of
#: prose lines per language that carried one when this file was written.
#: Lower a ceiling when a pass removes more; never raise one to make room.
BUDGETS: dict[str, tuple[str, int]] = {
    "en": (r"\bdeliberate(?:ly)?\b|\bquietly\b|\bsimply\b|\bby design\b|\bsays so\b", 50),
    "de": (r"\bbewusst\w*|\babsichtlich\b|\bunbemerkt\b", 23),
    "fr": (
        (r"\bvolontairement\b|\bdélibér\w+|\bdiscrètement\b|\ben silence\b"
        r"|\bprécisément\b|\ble dit\b"),
        42,
    ),
    "es": (
        (r"\ba propósito\b|\bdeliberad\w+|\bsin avisar\b|\ben silencio\b"
        r"|\bsimplemente\b|\bprecisamente\b|\blo dice\b"),
        60,
    ),
}

_TOC_LINE = re.compile(r"\s*[-*] \[[^\]]+\]\(#[^)]+\)\s*$")


def _sources(language: str) -> list[tuple[Path, str | None, str | None]]:
    """The Markdown behind every published guide in ``language``, with its heading range."""
    if language == "en":
        pages = [
            page for page in (*DOCUMENTATION_PAGES, *OPERATOR_DOCUMENTATION_PAGES)
            # A changelog is a historical record and quotes what it replaced.
            if not page.latest_releases and page.source != "CHANGELOG.md"
        ]
        return [(REPO_ROOT / page.source, page.start_heading, page.end_heading) for page in pages]
    public: list[tuple[Path, str | None, str | None]] = [
        (REPO_ROOT / "docs" / language / f"{page.slug}.md", None, None)
        for page in DOCUMENTATION_PAGES
        if not page.latest_releases
    ]
    operator: list[tuple[Path, str | None, str | None]] = [
        (REPO_ROOT / "docs" / language / "operator" / f"{slug}.md", None, None)
        for slug in sorted(TRANSLATED_OPERATOR_SLUGS)
    ]
    return public + operator


def _prose_lines(text: str, start: str | None = None, end: str | None = None):
    """Numbered lines a person wrote as prose: no code, no headings, no contents list."""
    in_code = False
    inside = start is None
    for number, line in enumerate(text.split("\n"), 1):
        if not inside:
            inside = line == start
            continue
        if end is not None and line == end:
            return
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or line.startswith("#") or _TOC_LINE.match(line):
            continue
        yield number, line


def _guide_lines(language: str):
    for path, start, end in _sources(language):
        text = path.read_text(encoding="utf-8")
        for number, line in _prose_lines(text, start, end):
            yield path.relative_to(REPO_ROOT).as_posix(), number, line


LANGUAGES = ("en", *GUIDE_LANGUAGES)


def test_every_guide_language_has_style_rules():
    """A new guide language needs its own rules; English ones do not transfer."""
    assert set(BANNED) == set(LANGUAGES)
    assert set(BUDGETS) == set(LANGUAGES)


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_guides_of_a_language_are_found(language: str):
    """A rule that scans no file passes for the wrong reason."""
    paths = {path for path, _, _ in _guide_lines(language)}
    assert len(paths) >= len(DOCUMENTATION_PAGES) - 1


@pytest.mark.parametrize("language", LANGUAGES)
def test_guides_do_not_use_generated_sounding_constructs(language: str):
    """A banned construct adds no fact, so a reader gains nothing from it."""
    findings = [
        f"{path}:{number}: {rule.name}: '{match.group(0)}'. {rule.instead}"
        for path, number, line in _guide_lines(language)
        for rule in BANNED[language]
        for match in [re.search(rule.pattern, line, re.IGNORECASE)]
        if match
    ]

    assert findings == [], "\n" + "\n".join(findings)


@pytest.mark.parametrize("language", LANGUAGES)
def test_intent_and_filler_words_do_not_spread(language: str):
    """Words that are only sometimes padding may become rarer, never commoner."""
    pattern, ceiling = BUDGETS[language]
    hits = [
        f"{path}:{number}: {line.strip()[:110]}"
        for path, number, line in _guide_lines(language)
        if re.search(pattern, line, re.IGNORECASE)
    ]

    assert len(hits) <= ceiling, (
        f"\n{len(hits)} prose lines in the {language} guides use an intent or filler "
        f"word ({pattern}); the ceiling is {ceiling}. These words are fine where they "
        "state a fact and padding everywhere else. Reword the new sentence so that it "
        "gives the reason, or remove the word from another one - do not raise the "
        "ceiling.\n" + "\n".join(hits)
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_budget_is_not_looser_than_the_guides(language: str):
    """A ceiling above the real count is room for the habit to come back."""
    pattern, ceiling = BUDGETS[language]
    count = sum(
        1 for _, _, line in _guide_lines(language) if re.search(pattern, line, re.IGNORECASE)
    )
    assert count == ceiling, f"lower the {language} ceiling to {count}"


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        ("en", "A warning nobody can ever clear is noise, and noise is how findings get ignored."),
        ("en", "A check that is permanently yellow is a check nobody reads."),
        ("en", "That is the whole thing. The step installs the pinned release."),
        ("en", "It keeps alerting regardless of the baseline, which is the point."),
        ("en", "Three settings are worth knowing:"),
        ("en", "The package configures nothing on purpose."),
        ("en", "PKCE is not optional decoration: it is the thing that replaces the secret."),
        ("en", "Which is precisely the arrangement browsers refuse."),
        ("en", "A backup nobody has tested is a hypothesis."),
        ("de", "Eine Warnung, die niemand beheben kann, ist Rauschen."),
        ("de", "Das ist bewusst von der Bewertung getrennt."),
        ("de", "Das Dokument hat schlicht keinen Schlüssel."),
        ("fr", "C’est tout pour une personne qui se connecte dans un navigateur."),
        ("fr", "Trois paramètres sont bons à connaître :"),
        ("fr", "Un contrôle constamment jaune est un contrôle que plus personne ne lit."),
        ("fr", "Le document n’a tout simplement pas de clé."),
        ("es", "Eso es todo. El paso instala la versión fijada."),
        ("es", "Conviene conocer tres ajustes:"),
        ("es", "Una advertencia que nadie puede resolver es ruido."),
        ("es", "PKCE no es un adorno opcional: es lo que sustituye al secreto."),
    ],
)
def test_the_rules_catch_the_sentences_they_were_written_for(language: str, sentence: str):
    """Each rule exists because of a sentence the guides once carried."""
    assert any(
        re.search(rule.pattern, sentence, re.IGNORECASE) for rule in BANNED[language]
    ), sentence


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        ("en", "Nobody can clear these warnings, so they are left out of the alert."),
        ("en", "The step installs the pinned release and scans the instance."),
        ("en", "Three settings matter here:"),
        ("en", "PKCE is required: it replaces the client secret those clients cannot hold."),
        ("en", "The exit code is the same under every format."),
        ("en", "The upgrade point is where the plan starts to gain something."),
        ("de", "Niemand kann diese Warnungen beheben, deshalb fehlen sie im Alarm."),
        ("de", "Das ist von der Sicherheitsbewertung getrennt."),
        ("fr", "Trois paramètres comptent ici :"),
        ("fr", "Le document de découverte existe pour cela."),
        ("es", "Aquí importan tres ajustes:"),
        ("es", "El paso instala la versión fijada y analiza la instancia."),
    ],
)
def test_the_rules_leave_the_plain_rewrites_alone(language: str, sentence: str):
    """A rule that also fires on the recommended wording cannot be satisfied."""
    assert not any(
        re.search(rule.pattern, sentence, re.IGNORECASE) for rule in BANNED[language]
    ), sentence


def test_headings_code_and_contents_lists_are_not_checked():
    """Headings are link anchors and code is quoted; neither is prose to reword."""
    text = "## Points worth knowing\n* [Points worth knowing](#points-worth-knowing)\n```\necho on purpose\n```\nA sentence on purpose."

    assert [line for _, line in _prose_lines(text)] == ["A sentence on purpose."]


def test_only_the_published_range_of_a_document_is_checked():
    """The README publishes one heading range; the rest is not a guide."""
    text = "before on purpose\n# Start\ninside\n# End\nafter on purpose"

    assert [line for _, line in _prose_lines(text, "# Start", "# End")] == ["inside"]
