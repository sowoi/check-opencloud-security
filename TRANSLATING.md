# Translating this project

The frontend speaks English, German, French and Spanish. English is the
source; the other three are translations of it. This page is for anybody
adding or reviewing a string, and for reading the output of

```bash
uv run python scripts/check_translations.py
```

which is the tool that enforces what can be enforced here.

## Where the words live

| What | Where |
|:--|:--|
| Interface strings | `webapp/locales/{en,de,es,fr}.py` |
| Operator guides | `docs/*.md` (English) and `docs/{de,fr,es}/*.md` |
| Guide titles and summaries | `webapp/documentation.py`, translated in the catalogues |

Decision records in `adr/` are not on this list and never will be: they stay
in English, once, in every locale
([ADR 0077](adr/0077-decision-records-are-never-translated.md)). Only the
operator area's interface around them is translated.

The same holds for `CHANGELOG.md`, `RELEASE.md` and the operator area's
Releases tab built from them: English only, in every locale, and never a
`docs/<language>/operator/releases.md`
([ADR 0078](adr/0078-changelogs-and-release-notes-are-never-translated.md)).

A guide title a translation has not overridden falls back to English on
purpose (`webapp/locales/__init__.py`), so a new guide is reachable in every
language the day it is written. That fallback is a decision, not a gap, and
the checks know the difference.

After editing a guide source or a catalogue, regenerate what is built from
them:

```bash
python scripts/build_frontend_documentation.py
python scripts/update_page_revisions.py
python scripts/build_search_index.py
```

## How each language addresses the reader

| Language | Register | Marker of the register we do not use |
|:--|:--|:--|
| English | Plain, direct, second person | - |
| German | **Informal "du"** | `Sie`, `Ihnen`, `Ihr…` mid-sentence |
| French | **Polite "vous"** | `tu`, `toi`, `ton`, `ta`, `tes` |
| Spanish | **Polite "usted"** | `tú`, `tus`, `tuyo`, `vosotros` |

German is informal because that is this project's voice everywhere else;
`AGENTS.md` requires it and `tests/test_webapp_i18n.py` fails on a formal
string. French and Spanish were written polite throughout, and the value now
is consistency: a page that switches register mid-sentence reads as sloppy in
either direction, so the checks hold each language to the one it uses.

German is ambiguous at the start of a sentence, where `Sie` is as likely to
mean "they" as "you". Those positions are exempt: a detector that flagged
them would push translators into worse German to satisfy a machine.

## Terminology

One concept, one word per language. The checked terms:

| English | German | French | Spanish |
|:--|:--|:--|:--|
| hardening | Härtung | durcissement | refuerzo |
| instance | Instanz | instance | instancia |
| waiver | Ausnahme / ausgenommen | exemption / exclusion | exención / eximido |

Names are never translated: OpenCloud, Nagios, Icinga, Checkmk, Prometheus,
Redis, Ansible, Kubernetes, Docker, Keycloak, Authentik, Authelia, PyPI,
GitHub, OpenAPI, Arazzo, MCP, and the protocol and header abbreviations
(TLS, DNS, HSTS, CSP, SSRF, OIDC, IPv4, IPv6). A sentence may be rewritten
around a name, but dropping it costs the reader the one word they could have
searched for.

## Error messages and examples

- An error message says what happened and what to do next, in that order.
  Translate both halves; a translation that keeps only the diagnosis leaves
  the reader without the instruction.
- Scan evidence is quoted, never translated: a version string, a certificate
  subject or a header value from the scanned host is what the host said.
- Example hostnames stay `opencloud.example.com` and example addresses stay
  in `192.0.2.0/24`. Never write a real host into a string, a guide or a test
  (`AGENTS.md`, and the commit hook that enforces it).
- `{placeholders}` are variable names, not words. Keep the English name
  exactly; reorder them freely to suit the sentence.

## What the checks decide, and what they leave to you

`scripts/check_translations.py` separates the two on purpose.

**Structural errors fail the build.** Each one is a fact about the string,
not an opinion about the prose:

| Rule | What it means |
|:--|:--|
| `missing-key` / `extra-key` | A key English has and this language does not, or the reverse |
| `placeholder` | The `{names}` differ from English |
| `format-syntax` | The string cannot be formatted at all - write a literal brace as `{{` |
| `markup` | The inline elements differ, or are outside the allowed set |
| `link-target` | A translated `href`. Translate the words, never the address |
| `dead-link` | A relative link in a guide that leads to no file |

`dead-link` has one dominant cause worth naming: a guide under
`docs/<language>/` is one directory deeper than its English source, so a path
out of `docs/` needs `../../`, not `../`.

**Style warnings are a reviewer's list.** `register`, `untranslated`,
`protected-term` and `glossary` are heuristics. They name a key; a human
decides. They never fail the build unless you ask with `--strict`, because a
check that cries wolf is a check people learn to skip.

## Reviewing a translation change

1. `uv run python scripts/check_translations.py` and fix every error.
2. Read the warnings. Each names a file, a key, the rule and a suggested
   action. Fix the ones that are right.
3. For a warning that is not a defect, add an entry to `ACCEPTED` in the
   script with the reason. It stays visible under `--show-accepted`: a
   recorded decision, not a silenced check.
4. Regenerate the documentation templates and search indexes if you touched a
   guide source or a catalogue string, and commit the result.
5. `uv run pytest tests/test_translation_quality.py tests/test_webapp_i18n.py`.

What no check here can tell you is whether a sentence sounds like something a
person would write. That still needs somebody who speaks the language.

## Reviewing wording before a commit

Write the behavior first: what the component does, what the result means,
and what the reader can do next. Avoid metaphors that make a file, setting,
or queue sound like a person. Translate the meaning into natural sentences.
Preserve uncertainty and security limits. Do not turn a recommendation into
a requirement just to shorten a sentence.

When changing an English catalogue entry, read its German, Spanish and French
values beside it. Update all four in the same change. Check technical terms,
numbers, negation, form of address and instructions as well as placeholders.
Read translated table descriptions and headings too. Keep commands, measured
output and identifiers unchanged.

Run the wording regression tests before committing:

```bash
uv run pytest tests/test_translation_quality.py tests/test_frontend_documentation.py tests/test_webapp_i18n.py tests/test_documentation_style.py
```

These tests run in the existing CI test job. They reject known wording defects
in catalogues, current documentation, templates and Python product strings.
Phrase checks join wrapped lines, so formatting cannot hide a known defect.
The translation tests also reject guides that retain too much English prose
and require translated headings to preserve their section links. They compare
long table descriptions separately, so an untranslated settings row cannot
hide inside an otherwise translated guide. Commands, short labels and quoted
diagnostics remain verbatim. Catalogue tests also check duplicate keys in the
source and exercise placeholder formatting and HTML escaping in every language.
The sharing and error-page tests render all four languages, including email
drafts, clipboard summaries, rate limits and rejected uploads. Export-format
checks compare each translated guide with the formats the service supports.
Link diagnostics ignore code examples and retain the source line numbers.
Result-page tests also cover grouped fixes, upgrade estimates and expiry
warnings in every language. Test conditional content as well as the landing
page: a missing panel, a single finding or one minute remaining can expose
wording problems that a general page-rendering test misses.

Add a focused regression case when correcting a recurring wording defect.
Include an acceptable example when a rule could also match correct technical
language. Do not ban ordinary technical terms or change a correct sentence
only to satisfy a heuristic. Automated checks catch known patterns; a fluent
reviewer must still assess meaning and natural phrasing.

Operator architecture and operations sources live in
`docs/<language>/operator/architecture.md` and `operations.md`.
They use the same build-time pipeline and section anchors as the public guides.
Regenerate the documentation and operator search index after editing them.
Release-note bodies and ADRs remain English.
