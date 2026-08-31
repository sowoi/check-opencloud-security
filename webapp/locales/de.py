"""The German translation of :mod:`webapp.locales.en`."""

from __future__ import annotations

MESSAGES: dict[str, str] = {
    # ---------------------------------------------------------------- site
    "site.og_image_alt": (
        "OpenCloud Security Scan - eine Instanz auf bekannte Schwachstellen, "
        "fehlende Härtung und schwache Sicherheits-Header prüfen"
    ),
    # ------------------------------------------------------- header chrome
    "chrome.skip_to_content": "Zum Inhalt springen",
    "chrome.brand": "Sicherheitsscan für OpenCloud",
    "chrome.menu": "Menü",
    "chrome.nav.primary": "Primär",
    "chrome.nav.secondary": "Sekundär",
    "chrome.search.label": "Dokumentation durchsuchen",
    "chrome.search.placeholder": "Suchen",
    "chrome.back_to_top": "Nach oben",
    "nav.new_scan": "Neuer Scan",
    "nav.how_it_works": "So funktioniert es",
    "nav.grades": "Noten",
    "nav.catalogue": "Katalog",
    "nav.docs": "Doku",
    "nav.search": "Suche",
    "nav.api": "API",
    "nav.ai": "KI",
    "nav.privacy": "Datenschutz",
    "nav.about": "Über",
    # --------------------------------------------------- language switcher
    "lang.region": "Sprache",
    "lang.label": "Seitensprache",
    "lang.apply": "Sprache ändern",
    "lang.note": "Der Scan selbst bleibt unverändert; nur diese Seite wird übersetzt.",
    # ------------------------------------------------------------- footer
    "footer.note.title": "Ein stiller Dienst, mit Absicht.",
    "footer.note.body": (
        "Scans laufen von diesem Server gegen die von dir eingegebene Adresse. "
        "Ergebnisse liegen {minutes} Minuten im Speicher und sind danach weg. "
        "Basiert auf dem <code>check-opencloud-security</code>-Scanner - kein "
        "Tracking, keine Konten, keine Analyse."
    ),
    "footer.note.run_yourself": "Selbst ausführen",
    "footer.version.title": "Die Scanner-Version, die dieses Ergebnis erzeugt hat",
    "footer.version.label": "Backend v{version}",
    "footer.legal.scope": (
        "<strong>Diese Prüfung ist nicht erschöpfend, und eine gute Note ist kein "
        "Zertifikat.</strong> Sie liest, was eine öffentlich erreichbare "
        "OpenCloud-Instanz einem anonymen Besucher zeigt: ihre Version, die "
        "Advisories zu dieser Version, ihren Transport, ihre Header und eine "
        "Reihe von Einstellungen, die ohne Anmeldung sichtbar sind. Ein "
        "&ldquo;A&rdquo; bedeutet, dass nichts davon fehlgeschlagen ist - nicht, "
        "dass die Instanz sicher ist. Alles hinter der Anmeldung, der Server, auf "
        "dem sie läuft, das Netzwerk drumherum, die Daten darin und die Personen "
        "mit Konten darauf liegen außerhalb dessen, was ein nicht angemeldeter "
        "Scan sehen kann. Behandle das Ergebnis als einen Faktor unter "
        "mehreren, niemals als Sicherheitsaudit oder Penetrationstest."
    ),
    "footer.legal.trademark": (
        "Dies ist ein unabhängiges Community-Projekt. Es steht in keiner "
        "Verbindung zur OpenCloud GmbH und wird von diesem Unternehmen weder "
        "empfohlen noch unterstützt. &ldquo;OpenCloud&rdquo;, das OpenCloud-Logo "
        "und alle zugehörigen Marken sind Eigentum ihrer jeweiligen Inhaber und "
        "werden hier ausschließlich verwendet, um zu kennzeichnen, welche "
        "Software dieses Werkzeug prüft."
    ),
    # --------------------------------------------------- the contents list
    "toc.heading": "Auf dieser Seite",
    "toc.aria": "Auf dieser Seite",
    # --------------------------------------------------------- cross-links
    "pagenav.kicker": "Weiterlesen",
    "pagenav.aria": "Mehr über diesen Dienst",
    "pagenav.how.title": "Wie der Scan funktioniert",
    "pagenav.how.blurb": (
        "Was getestet wird, und die vier Schritte zwischen dem Klick auf den "
        "Button und der Note."
    ),
    "pagenav.grades.title": "Was die Noten bedeuten",
    "pagenav.grades.blurb": (
        "Jede Stufe von A+ bis F, was eine Note nach unten drückt und wie man sie "
        "verbessert."
    ),
    "pagenav.catalogue.title": "Was der Scanner prüft",
    "pagenav.catalogue.blurb": (
        "Jedes Härtungsmerkmal, jeden Header- und TLS-Check und jede bekannte "
        "Sicherheitslücke - unabhängig von einem einzelnen Scan."
    ),
    "pagenav.docs.title": "CLI-Dokumentation",
    "pagenav.docs.blurb": (
        "Den Scanner von einem Terminal aus installieren, konfigurieren und "
        "automatisieren."
    ),
    "pagenav.api.title": "Scannen per Skript",
    "pagenav.api.blurb": "Die JSON-API, die Fair-Use-Grenzen und das OpenAPI-Schema.",
    "pagenav.ai.title": "Für KI-Agenten",
    "pagenav.ai.blurb": "Discovery, OpenAPI, Arazzo-Workflows und der MCP-Endpunkt.",
    "pagenav.privacy.title": "Was dieser Server speichert",
    "pagenav.privacy.blurb": (
        "Im Speicher, für {minutes} Minuten, und was das Log auslässt."
    ),
    "pagenav.about.title": "Über OpenCloud",
    "pagenav.about.blurb": (
        "Die Plattform, die hier geprüft wird, und warum dieses Projekt "
        "unabhängig davon ist."
    ),
    "pagenav.cta.title": "Eine Instanz scannen",
    "pagenav.cta.blurb": (
        "Zurück zum Formular. Dauert ein paar Sekunden, keine Anmeldung nötig."
    ),
    # ---------------------------------------------------------------- 404
    "notfound.title": "Hier ist nichts",
    "notfound.description": (
        "Die Adresse existiert nicht, oder der Scan, auf den sie zeigte, ist "
        "bereits abgelaufen."
    ),
    "notfound.kicker": "Nicht gefunden",
    "notfound.lede": (
        "Entweder existiert die Adresse nicht, oder es war ein Scan und dieser "
        "Scan ist verschwunden: Ergebnisse werden {minutes} Minuten gehalten und "
        "dann verworfen, sodass ein Link von heute Morgen nicht mehr öffnet. Eine "
        "Kennung, die nie existiert hat, sieht von hier aus genau gleich aus - "
        "dieser Dienst kann dir nicht sagen, welcher Fall vorliegt, und "
        "versucht es bewusst auch nicht."
    ),
    "notfound.action": "Neuen Scan starten",
    # ------------------------------------------------------- landing page
    "index.title": "Eine OpenCloud-Instanz scannen",
    "index.description": (
        "Eine OpenCloud-Instanz auf bekannte Schwachstellen, fehlende Härtung und "
        "schwache Sicherheits-Header prüfen. Kostenlos, unabhängig, und nichts "
        "wird gespeichert."
    ),
    "index.eyebrow": "Unabhängig &middot; air-gapped &middot; nichts wird gespeichert",
    "index.headline": (
        'Wie sicher ist deine <em class="swash">OpenCloud-Instanz</em>?'
    ),
    "index.lede": (
        "Gib die Adresse einer Instanz ein, für die du verantwortlich bist. "
        "Dieser Server spricht sie über HTTPS an, wie es jeder Besucher "
        "täte, liest, was sie ohne Anmeldung veröffentlicht, und benotet das "
        "Ergebnis von <strong>A+</strong> bis <strong>F</strong>."
    ),
    "index.form.kicker": "Scan-Anfrage",
    "index.form.hint": "Ein paar Sekunden &middot; keine Anmeldung",
    "index.error.self_host": (
        "Nichts für ungut - die Grenzen halten diesen kleinen Dienst am Laufen. "
        "Der Scanner ist Open Source, du kannst diese exakte Prüfung also selbst "
        "ausführen, so oft du möchtest:"
    ),
    "index.field.label": "Adresse der Instanz",
    "index.field.title": (
        "Die Basisadresse der Instanz: ein Hostname, optionaler Port und "
        "optionaler einfacher Unterordner. Keine Query, kein Fragment, keine "
        "Parameter, keine Escapes und keine Traversierung."
    ),
    "index.field.hint": (
        "Der Hostname allein genügt - <code>https://</code> wird angenommen. Ein "
        "Unterordner wie <code>/opencloud</code> wird unterstützt; Queries, "
        "Fragmente, Parameter und Pfad-Traversierung werden abgelehnt. Nur "
        "öffentliche Adressen, und nur Instanzen, die du betreibst oder für "
        "deren Test du eine Erlaubnis hast."
    ),
    "index.submit": "Prüfung starten",
    "index.submit.busy": "Prüfung wird gestartet...",
    "index.track.label": "Release-Track",
    "index.track.hint": (
        "Bestimmt, wie lange dieses Release unterstützt wird und auf welches "
        "Release es zum Upgrade rät."
    ),
    "index.format.label": "Anzeigen als",
    "index.format.dashboard": "Ein Dashboard",
    "index.format.json": "Das rohe JSON",
    "index.format.hint": "Beide stammen aus demselben Scan.",
    "index.waivers.summary": "Bestimmte Prüfungen ignorieren (optional)",
    "index.waivers.selected": "Bestimmte Prüfungen ignorieren ({count} ausgewählt)",
    "index.waivers.hint": (
        "Eine ausgesetzte Prüfung bleibt im Bericht und wird weiterhin angezeigt "
        "- sie hört nur auf, die Note nach unten zu drücken. Nur Prüfungen, die "
        "tatsächlich fehlgeschlagen sind, können ausgesetzt werden."
    ),
    "index.assurance.aria": "Wie dieser Dienst mit Ihren Daten umgeht",
    "index.assurance.airgapped.title": "100 % air-gapped",
    "index.assurance.airgapped.body": (
        "Jedes Byte stammt von diesem Ursprung. Kein CDN, kein Font-Dienst, "
        "keine Analyse."
    ),
    "index.assurance.nostore.title": "Keine Datenspeicherung",
    "index.assurance.nostore.body": (
        "Das Ergebnis liegt im Speicher und wird in dem Moment verworfen, in dem "
        "es abläuft."
    ),
    "index.assurance.noaccount.title": "Keine Registrierung nötig",
    "index.assurance.noaccount.body": (
        "Kein Konto, keine Anmeldung, keine E-Mail-Adresse, kein Warten."
    ),
    "index.assurance.ephemeral.title": "Flüchtige Ergebnisse",
    "index.assurance.ephemeral.body": (
        "Der Link funktioniert {minutes} Minuten nach dem Scan nicht mehr."
    ),
    # -------------------------------------------- release tracks and waivers
    "track.auto.label": "Automatisch erkennen",
    "track.auto.description": (
        "Den Track aus dem gemeldeten Release der Instanz ableiten."
    ),
    "track.rolling.label": "Rolling",
    "track.rolling.description": "Ungefähr alle drei Wochen ein neues Release.",
    "track.production.label": "Production",
    "track.production.description": (
        "Etwa sechs Monate unterstützt. Die übliche Wahl."
    ),
    "track.lts.label": "LTS",
    "track.lts.description": "Zwei Jahre unterstützt.",
    "waivers.group.hardening": "Härtung",
    "waivers.group.headers": "Header",
    "waivers.group.checks": "Prüfungen",
    # ------------------------------------------------------------ severity
    "severity.critical": "kritisch",
    "severity.high": "hoch",
    "severity.medium": "mittel",
    "severity.low": "niedrig",
    # ------------------------------------------------------------ category
    "category.transport": "Transport & TLS",
    "category.cookies": "Cookies",
    "category.headers": "Sicherheits-Header",
    "category.authentication": "Authentifizierung & Konten",
    "category.sharing": "Freigaben & Links",
    "category.exposure": "Netzwerk-Exposition",
    "category.embedding": "Einbettung",
    "category.lifecycle": "Version & Lebenszyklus",
    "category.proxy": "Identity-Provider & Proxy",
    # --------------------------------------------------------- grade scale
    "grade.5.headline": "Nichts gefunden",
    "grade.5.meaning": (
        "Das Release ist aktuell für seinen Track, keine Advisory trifft auf die "
        "Version zu, und jede Prüfung, die der Scan durchführen konnte, ist "
        "bestanden."
    ),
    "grade.5.improve": (
        "Hier bleiben: Achte auf das nächste Release auf deinem Track, und "
        "führe den Scan nach jeder Änderung am Reverse Proxy oder der "
        "Anmeldung erneut aus."
    ),
    "grade.4.headline": "Ein Update wartet",
    "grade.4.meaning": (
        "Es existiert ein neueres Patch-Release in derselben Release-Linie. An "
        "der installierten Version ist nichts bekanntermaßen falsch - sie ist "
        "einfach nicht die neueste."
    ),
    "grade.4.improve": (
        "Installiere das anstehende Update. Es ist dieselbe Release-Linie, "
        "also das kleinstmögliche Upgrade."
    ),
    "grade.3.headline": "Eine Release-Linie zurück",
    "grade.3.meaning": (
        "Die Instanz läuft auf einer älteren Linie als der aktuellen für ihren "
        "Track. Sie wird möglicherweise noch unterstützt, ist aber nicht mehr "
        "dort, wo Fixes zuerst ankommen."
    ),
    "grade.3.improve": (
        "Wechsle zur aktuellen Linie deines Tracks. Der Scan nennt, welche "
        "das ist, und weist nie auf einen Track hin, den du nicht gewählt hast."
    ),
    "grade.2.headline": "Advisories treffen auf diese Version zu",
    "grade.2.meaning": (
        "Die installierte Version erscheint in der Advisory-Datenbank. Keine der "
        "zutreffenden Advisories ist als kritisch oder hoch eingestuft, was der "
        "einzige Grund ist, warum es nicht niedriger ausfällt."
    ),
    "grade.2.improve": (
        "Aktualisiere auf die behobene Version für deine Release-Linie. Die "
        "Ergebnisseite nennt sie - eine Advisory kann auf mehreren Linien separat "
        "behoben werden."
    ),
    "grade.1.headline": "Eine kritische oder hohe Advisory trifft zu",
    "grade.1.meaning": (
        "Mindestens eine Advisory, die auf die installierte Version zutrifft, ist "
        "als kritisch oder hoch eingestuft. Dies ist ein bekannter, "
        "veröffentlichter und behobener Weg hinein."
    ),
    "grade.1.improve": (
        "Aktualisiere jetzt, vor allem anderen auf der Seite. Nichts anderes, "
        "was sich ändern lässt, hebt die Note über dieses Niveau."
    ),
    "grade.0.headline": "Nicht mehr unterstützt",
    "grade.0.meaning": (
        "Die Release-Linie erhält überhaupt keine Sicherheitsfixes mehr. Das "
        "überstimmt jedes andere Signal, einschließlich eines Waivers: Eine "
        "Instanz, die niemand patcht, kann nicht danach benotet werden, wie "
        "ordentlich ihre Header sind."
    ),
    "grade.0.improve": (
        "Wechsle zu einer unterstützten Release-Linie. Welche Linien wie "
        "lange unterstützt werden, steht im Release-Zeitplan, den der Scan liest."
    ),
    # ---------------------------------------------------------- grades page
    "grades.title": "Was die Noten bedeuten",
    "grades.description": (
        "A+, A, C, D, E und F: Was jede Note über eine OpenCloud-Instanz aussagt, "
        "was sie nach unten drückt, und der kürzeste Weg zur nächsthöheren."
    ),
    "grades.kicker": "Die Skala",
    "grades.lede": (
        "Jeder Scan endet in einem Buchstaben. Er ergibt sich aus zwei Dingen - "
        "welches Release die Instanz betreibt und welche Prüfungen "
        "fehlgeschlagen sind - und diese Seite ist die gesamte Rechnung dahinter, "
        "in der Reihenfolge, in der der Scanner sie ausführt."
    ),
    "grades.scale.kicker": "Sechs Stufen",
    "grades.scale.heading": "Die Skala, beste Note zuerst",
    "grades.scale.intro": (
        "Die <strong>0-5</strong>-Skala und ihre Buchstaben sind die, die "
        "<code>scan.nextcloud.com</code> bekannt gemacht hat, bewusst "
        "beibehalten, damit ein bestehender Schwellenwert, ein Graph oder eine "
        "Alarmregel ihre Bedeutung behalten. Das ist auch, warum es kein "
        "<strong>B</strong> gibt: Die Skala überspringt es, und eines hier zu "
        "erfinden würde zwei Zahlen dieselbe Note bedeuten lassen."
    ),
    "grades.row.prefix": "Note {label}: ",
    "grades.row.score": "{rating} von 5",
    "grades.row.improve": "Um aufzusteigen:",
    "grades.caps.kicker": "Die Obergrenze",
    "grades.caps.heading": "Was eine fehlgeschlagene Prüfung einer Note antun kann",
    "grades.caps.intro": (
        "Die Version legt die Startnote fest. Fehlgeschlagene Prüfungen können "
        "sie nicht anheben - sie können sie nur nach unten drücken, und wie weit, "
        "hängt vom Schweregrad der schlimmsten fehlgeschlagenen Prüfung ab:"
    ),
    "grades.caps.at_best": "bestenfalls",
    "grades.caps.shared": (
        "Befunde gleichen Schweregrads teilen sich eine Obergrenze, sodass das "
        "Beheben eines von drei mittleren Befunden nichts bewegt, bis auch der "
        "letzte verschwunden ist. Deshalb ordnet die Ergebnisseite den Plan so, "
        "wie sie es tut, und deshalb druckt sie die Note, die jeder Schritt "
        "tatsächlich erreichen würde."
    ),
    "grades.caps.rules": (
        "Zwei Regeln stehen über alldem. <strong>End of Life überstimmt "
        "alles</strong>, einschließlich eines Waivers: Eine Release-Linie, die "
        "keine Sicherheitsfixes mehr erhält, ist ein <strong>F</strong>, "
        "unabhängig davon, wie sauber der Rest des Berichts ist. Und "
        "<strong>vor seinem Track zu sein bedeutet nicht, dahinter zu "
        "sein</strong> - ein Release, das neuer ist als das aktuelle für den "
        "gewählten Track, wird als vorauslaufend gemeldet und nie als nicht "
        "unterstützt benotet."
    ),
    "grades.improve.kicker": "Der kürzeste Weg",
    "grades.improve.heading": "Wie dieser Scanner beim Aufsteigen hilft",
    "grades.improve.intro": (
        "Eine Note allein ist eine Punktetafel, was um vier Uhr nachmittags nicht "
        "viel nützt. Jede Ergebnisseite trägt außerdem die vier Dinge, die daraus "
        "die Arbeit eines Nachmittags machen:"
    ),
    "grades.improve.plan": (
        "<strong>Ein Sanierungsplan, in Reihenfolge des Nutzens.</strong> Jeder "
        "Schritt sagt, was zu ändern ist und welche Note die Instanz halten "
        "würde, sobald dieser Schritt und alles darüber erledigt ist - so kannst "
        "du aufhören, wo sich der Aufwand nicht mehr lohnt."
    ),
    "grades.improve.release": (
        '<strong>Das genaue Release, zu dem gewechselt werden sollte.</strong> '
        "Nicht \"aktualisieren\": die Version, die die Advisory <em>auf der "
        "Linie behebt, auf der du tatsächlich bist</em>, und nie ein Sprung auf "
        "einen Track, den du nicht gewählt hast."
    ),
    "grades.improve.explained": (
        "<strong>Jede fehlgeschlagene Prüfung, erklärt.</strong> Was gemessen "
        "wurde, warum es wichtig ist, und der Fix, mit einem Link zur "
        "OpenCloud-Dokumentation für die dahinterstehende Einstellung."
    ),
    "grades.improve.waiver": (
        "<strong>Ein Waiver für die, mit denen du zu leben entschieden "
        "hast.</strong> Eine ausgesetzte Prüfung bleibt im Bericht und bleibt "
        "sichtbar - sie hört nur auf, die Note zu deckeln, sodass eine bewusste "
        "Entscheidung nicht für immer wie ein Fehlschlag aussieht. Sie kann keine "
        "bestandene Prüfung verstecken und kein End-of-Life-Release retten."
    ),
    "grades.improve.rerun": (
        "Führe ihn danach erneut aus. Dieselbe Instanz, derselbe Scan, und "
        "der Buchstabe ändert sich - was der einzige Beweis ist, dass irgendetwas "
        "davon funktioniert hat."
    ),
    "grades.limits.kicker": "Ehrlichkeit",
    "grades.limits.heading": "Was eine gute Note nicht ist",
    "grades.limits.body": (
        "Ein <strong>A+</strong> bedeutet, dass nichts, was dieser Scan geprüft "
        "hat, fehlgeschlagen ist. Es ist kein Zertifikat, und es ist kein "
        "Penetrationstest. Alles hinter der Anmeldung, das Betriebssystem, die "
        "Container-Laufzeit, die Backups, die Konten und die Personen, die sie "
        "innehaben, liegen außerhalb dessen, was ein nicht angemeldeter Scan "
        "sehen kann. Behandle den Buchstaben als einen Faktor unter mehreren "
        '- <a href="/how-it-works">wie der Scan funktioniert</a> listet auf, was '
        "er liest, und jede Ergebnisseite wiederholt die Grenzen unterhalb der "
        "Note."
    ),
    # -------------------------------------------------------------- catalogue
    "catalogue.title": "Was der Scanner prüft",
    "catalogue.description": (
        "Jedes Härtungsmerkmal, jeden Sicherheits-Header, jeden TLS-Check und "
        "jede bekannte Sicherheitslücke, unabhängig von einem einzelnen "
        "Scan-Ergebnis."
    ),
    "catalogue.kicker": "Referenz",
    "catalogue.lede": (
        "Dies ist die vollständige Menge: Jeder Check unten kann auf einer "
        "Ergebnisseite erscheinen, und jede Sicherheitslücke unten ist eine, "
        "gegen die ein Scan bewertet wird. Nichts hier hängt von einer "
        "bestimmten Instanz ab."
    ),
    "catalogue.checks.kicker": "Checks",
    "catalogue.checks.heading": "Jeder Check, nach Kategorie",
    "catalogue.checks.lede": (
        "Gruppiert nach Thema statt nach Schweregrad - der Schweregrad hängt "
        "von der gescannten Instanz ab und wird hier deshalb nicht angezeigt."
    ),
    "catalogue.checks.not_configurable": "nicht konfigurierbar",
    "catalogue.advisories.kicker": "Sicherheitslücken",
    "catalogue.advisories.heading": "Bekannte Sicherheitslücken",
    "catalogue.advisories.lede": (
        "Jede Sicherheitslücke in der Datenbank, gegen die ein Scan bewertet "
        "wird, täglich aus dem öffentlichen Feed aktualisiert."
    ),
    "catalogue.advisories.empty.tag": "Keine bekannt",
    "catalogue.advisories.empty.body": (
        "Die Datenbank der Sicherheitslücken ist derzeit leer."
    ),
    "catalogue.advisories.fixed_in": "Behoben in {version}",
    "catalogue.advisories.unfixed": "Noch keine Korrektur veröffentlicht",
    # -------------------------------------------------- how the scan works
    "how.title": "Wie der Scan funktioniert",
    "how.description": (
        "Was dieser Scanner an einer OpenCloud-Instanz testet, und was zwischen "
        "dem Drücken des Buttons und dem Lesen der Note passiert."
    ),
    "how.kicker": "Die Methode",
    "how.lede": (
        "Alles, was dieser Dienst meldet, findet er selbst heraus, indem er die "
        "von dir eingegebene Adresse über HTTPS anspricht, wie es jeder "
        "Besucher täte. Niemand Drittes wird gefragt, und niemand meldet sich an."
    ),
    "how.tests.heading": "Was geprüft wird",
    "how.tests.version.title": "Version und Lebenszyklus",
    "how.tests.version.body": (
        "Welches Release läuft, ob es noch Sicherheitsfixes erhält, und ob eine "
        "veröffentlichte Advisory darauf zutrifft. Ein Release nach seinem End of "
        "Life ist ein F, egal was sonst stimmt."
    ),
    "how.tests.transport.title": "Transport und Header",
    "how.tests.transport.body": (
        "HTTPS-Erreichbarkeit, das Zertifikat und seine verbleibende Laufzeit, "
        "die angebotenen TLS-Versionen und die Sicherheits-Header, die einem "
        "Browser tatsächlich gesendet werden - HSTS, CSP, Frame- und "
        "Content-Type-Schutz."
    ),
    "how.tests.hardening.title": "Härtung und Exposition",
    "how.tests.hardening.body": (
        "Basic Authentication, Passwort- und Ablaufregeln für öffentliche Links, "
        "Passwortregeln, Verzeichnisauflistung, exponierte Endpunkte und alles, "
        "was der Welt die Version verkündet."
    ),
    "how.pipeline.kicker": "Die Pipeline",
    "how.pipeline.heading": "Was passiert, wenn du den Button drückst",
    "how.pipeline.lede": (
        "Vier Schritte, und beim dritten kommt die Warteschlange ins Spiel."
    ),
    "how.pipeline.step1": (
        "<strong>Deine Adresse wird geprüft.</strong> Private, lokale und "
        "Cloud-Metadaten-Adressen werden abgelehnt, bevor überhaupt eine "
        "Verbindung aufgebaut wird."
    ),
    "how.pipeline.step2": (
        "<strong>Ein Scan erhält eine zufällige Kennung.</strong> Diese Kennung "
        "ist der einzige Weg, das Ergebnis zu erreichen. Es gibt keine Liste der "
        "Scans, und keine Möglichkeit, eine zu erraten."
    ),
    "how.pipeline.step3": (
        "<strong>Er wartet, bis er an der Reihe ist.</strong> Eine feste Anzahl "
        "von Scans läuft gleichzeitig. Sind alle beschäftigt, reiht sich deiner "
        "ein, und dir wird deine Position in der Reihe genannt - nichts wird "
        "abgelehnt, nur weil der Dienst beliebt ist."
    ),
    "how.pipeline.step4": (
        "<strong>Das Ergebnis läuft ab.</strong> Nach {minutes} Minuten "
        "funktioniert die Kennung nicht mehr und das Ergebnis ist weg, ohne dass "
        "etwas auf Festplatte geschrieben wurde."
    ),
    "how.faq.kicker": "Fragen",
    "how.faq.heading": "Häufig gestellte Fragen",
    "how.faq.q1": "Ist das offizielle OpenCloud-Software?",
    "how.faq.a1": (
        "Nein. Dies ist ein unabhängiges Community-Projekt, das in keiner "
        "Verbindung zur OpenCloud GmbH steht und von diesem Unternehmen weder "
        'empfohlen noch unterstützt wird. "OpenCloud" und das zugehörige Logo '
        "sind Marken ihrer jeweiligen Inhaber und werden hier ausschließlich "
        "verwendet, um die geprüfte Software zu benennen."
    ),
    "how.faq.q2": "Bedeutet eine gute Note, dass eine Instanz sicher ist?",
    "how.faq.a2": (
        "Nein. Der Scan liest nur, was eine öffentlich erreichbare Instanz "
        "einem anonymen Besucher zeigt - ihre Version, die Advisories zu dieser "
        "Version, ihren Transport, ihre Header und eine Reihe von Einstellungen, "
        "die ohne Anmeldung sichtbar sind. Alles hinter dem Login, der Server, "
        "auf dem sie läuft, das Netzwerk drumherum und die Personen mit Konten "
        "darauf liegen außerhalb dessen, was ein nicht authentifizierter Scan "
        "sehen kann. Betrachte ein Ergebnis als einen Baustein unter "
        "mehreren, niemals als Sicherheitsaudit oder Penetrationstest."
    ),
    "how.faq.q3": "Wie lange bewahrst du das Ergebnis eines Scans auf?",
    "how.faq.a3": (
        "Nur im Speicher, für {minutes} Minuten, danach ist es weg. Keine "
        "Konten, keine Analyse, kein Tracking - den Rest liest du unter "
        '<a href="/privacy">Was dieser Server speichert</a>.'
    ),
    "how.faq.q4": "Gibt es ein Ratenlimit?",
    "how.faq.a4": (
        "Ja, pro Besucher und pro gescanntem Ziel, damit weder ein einzelner "
        "Besucher die Warteschlange blockiert noch dieselbe Instanz Schlag auf "
        "Schlag gescannt wird. Die genauen Werte für diese Installation stehen "
        '<a href="/api#api-limits">auf der API-Seite</a>.'
    ),
    "how.faq.q5": "Kann ich ohne Ratenlimit scannen?",
    "how.faq.a5": (
        "Ja - der Scanner ist Open Source. Führe ihn mit "
        '<a href="/cli">einem einzigen Docker-Befehl</a> auf deiner eigenen '
        "Maschine aus, ohne Limit und ohne Website dazwischen."
    ),
    "how.faq.q6": "Sagt mir ein Scan, ob ein OpenCloud-Update ansteht?",
    "how.faq.a6": (
        "Ja. Jeder Scan vergleicht die gemeldete Version mit dem "
        "OpenCloud-Release-Feed und meldet ein anstehendes Update oder eine "
        "nicht mehr unterstützte Version genauso wie einen fehlenden Header - "
        'sieh dir <a href="/documentation/reference#update-check">den '
        "Update-Check</a> an, um zu sehen, wie die empfohlene Version "
        "ermittelt wird."
    ),
    # --------------------------------------------------------------- privacy
    "privacy.title": "Was dieser Server speichert",
    "privacy.description": (
        "Was während eines Scans gespeichert wird, für wie lange, und was das "
        "Betriebslog aufzeichnet und was nicht."
    ),
    "privacy.kicker": "Datenschutz",
    "privacy.lede": "Kurze Antwort: der Scan, für {minutes} Minuten, im Speicher.",
    "privacy.retention.kicker": "Speicherdauer",
    "privacy.retention.heading": "Solange ein Scan lebt",
    "privacy.retention.body": (
        "Die von dir übermittelte Adresse, die Prüfungen, die du zu ignorieren "
        "wähltest, und das Ergebnis liegen {minutes} Minuten im Speicher, unter "
        "einem Schlüssel, der aus der zufälligen Kennung deines Scans abgeleitet "
        "ist, und werden dann vom Speicher selbst verworfen. Das Betriebslog "
        "vermerkt, dass ein Scan erstellt, gestartet und beendet wurde, "
        "ausschließlich anhand dieser zufälligen Kennung - nicht die Adresse, "
        "nicht das Ergebnis und nicht deine IP-Adresse, die nur als "
        "Einweg-Fingerabdruck für die Ratenbegrenzung gezählt wird."
    ),
    "privacy.self_host": (
        "Möchtest du es lieber selbst betreiben? Derselbe Scanner ist eine "
        "Kommandozeilenprüfung und ein Python-Paket. In keinem der beiden Fälle "
        "spricht hier irgendetwas mit einem Drittanbieterdienst."
    ),
    # ----------------------------------------------------------- legal notice
    "legal.title": "Impressum",
    "legal.description": (
        "Anbieterkennzeichnung, Kontaktdaten und Haftungshinweise des "
        "Betreibers dieser Installation."
    ),
    "legal.kicker": "Impressum",
    "legal.lede": (
        "Anbieterkennzeichnung nach deutschem Recht für den Betreiber dieser "
        "Installation."
    ),
    "legal.english_notice": (
        "Dieses Impressum ist der eigene Rechtstext des Betreibers und liegt "
        "nur auf Englisch vor. Die Seite darum herum ist übersetzt, der Text "
        "darunter nicht."
    ),
    # ----------------------------------------------------------------- about
    "about.title": "Über OpenCloud und diesen Scanner",
    "about.description": (
        "Was OpenCloud ist, wer es entwickelt, und warum dieser Scanner ein "
        "unabhängiges Community-Projekt ist."
    ),
    "about.kicker": "Über",
    "about.lede": (
        "Das eine ist eine Datei-, Sync- und Sharing-Plattform. Das andere ist "
        "eine Community-Prüfung, die sie von außen betrachtet."
    ),
    "about.platform.kicker": "Die Plattform",
    "about.platform.heading": "Über OpenCloud",
    "about.platform.body": (
        '<a href="https://opencloud.eu/" rel="noopener noreferrer">OpenCloud</a> '
        "ist die Datei-, Sync- und Sharing-Plattform, die dieses Werkzeug prüft - "
        "Open Source, in Deutschland entwickelt, und dokumentiert unter "
        '<a href="https://docs.opencloud.eu/" rel="noopener noreferrer">'
        "docs.opencloud.eu</a>, wo jeder von diesem Scanner vorgeschlagene Fix "
        "ordentlich beschrieben ist. Danke an die Menschen, die es machen."
    ),
    "about.platform.independent": (
        "Dieser Scanner ist ein unabhängiges Community-Projekt. Er steht in "
        "keiner Verbindung zur OpenCloud GmbH und wird von diesem Unternehmen "
        "weder empfohlen noch unterstützt. &ldquo;OpenCloud&rdquo;, das "
        "OpenCloud-Logo und alle zugehörigen Marken sind Eigentum ihrer "
        "jeweiligen Inhaber."
    ),
    "about.project.kicker": "Das Projekt",
    "about.project.heading": "Über diesen Scanner",
    "about.project.body": (
        "Alles, was du hier siehst, wird von <code>check-opencloud-security</code> "
        "erzeugt, einem Nagios- und Icinga-Plugin mit einer Scanner-Bibliothek "
        "dahinter. Diese Seite ist eine Möglichkeit, es zu nutzen; ein Befehl auf "
        "deiner eigenen Maschine, ohne Ratenlimit und ohne Warteschlange, ist die "
        "andere."
    ),
    "about.project.origin": (
        "Das Projekt wurde von <strong>Massoud Ahmed</strong> ins Leben gerufen, "
        "um OpenCloud-Nutzern eine unabhängige Alternative zu "
        "<code>scan.nextcloud.com</code> zu geben: einen Scanner, gebaut für "
        "OpenClouds Release-Tracks, Einstellungen und Deployment-Modell, der "
        'vollständig auf der eigenen Maschine des Betreibers laufen kann. '
        '<a href="{project}" rel="noopener noreferrer">Das Projekt ist auf '
        "GitHub</a>."
    ),
    # ------------------------------------------------------------------- API
    "api.title": "Scannen per Skript",
    "api.description": (
        "Die JSON-API hinter dem Formular: wie man einen Scan einreicht, ihn "
        "abfragt, und was dieser Server einem Aufrufer nicht zu entscheiden "
        "erlaubt."
    ),
    "api.kicker": "Die API",
    "api.lede": (
        "Das Formular ist eine von zwei Vordertüren; die andere ist JSON, und es "
        "ist derselbe Handler."
    ),
    "api.submit.kicker": "Einreichen & abfragen",
    "api.submit.heading": "Einreichen und abfragen",
    "api.submit.body": (
        "Eine Einreichung antwortet mit <code>202</code> und der Kennung des "
        "Scans; das Abfragen liefert <code>queued</code>, <code>running</code> "
        "oder das fertige Ergebnis, und <code>404</code>, sobald er abgelaufen "
        "ist. Nur vier Felder werden gelesen - die Adresse, die auszusetzenden "
        "Prüfungen, der Release-Track und das Ausgabeformat. Alles andere im "
        "Body, allen voran Nebenläufigkeit und Timeouts, wird abgelehnt: Wie "
        "hart dieser Server prüft, ist keine Entscheidung des Aufrufers."
    ),
    "api.limits.kicker": "Fair Use",
    "api.limits.heading": "Fair Use",
    "api.limits.enforced": (
        "Fair Use wird durchgesetzt statt nur erbeten: {client} Einreichungen "
        "pro {window} Minute(n) von einer Adresse, und {cooldown}, beide "
        "beantwortet mit <code>429</code> und einem <code>Retry-After</code>."
    ),
    "api.limits.cooldown": "ein Scan pro Ziel alle {minutes} Minute(n)",
    "api.limits.no_cooldown": "keine Abkühlzeit pro Ziel",
    "api.limits.none": "Dieses Deployment setzt kein Ratenlimit.",
    "api.limits.self_host": (
        "Wenn du eines triffst und lieber nicht warten möchtest: Das Ganze läuft "
        'auch auf deiner eigenen Maschine: <a href="{project}" '
        'rel="noopener noreferrer">das Projekt ist auf GitHub</a>.'
    ),
    "api.schema.kicker": "Das Schema",
    "api.schema.heading": "Das Schema",
    "api.schema.body": (
        "Die maschinenlesbaren Dokumente sind immer öffentlich, auf diesem "
        'Deployment wie auf jedem anderen: die <a href="/openapi.json">'
        "OpenAPI-3.1-Beschreibung</a> jeder Operation, und die "
        '<a href="/arazzo.json">Arazzo-1.0.1-Workflows</a>, die sagen, wie sich '
        "diese Operationen zum Einreichen eines Scans, Warten darauf und "
        "Abholen des Ergebnisses zusammenfügen."
    ),
    "api.schema.docs_on": (
        'Beide sind hier durchsuchbar als <a href="/docs">Swagger UI</a> und '
        '<a href="/redoc">ReDoc</a>, ausgeliefert von diesem Server wie alles '
        "andere - nichts wird von irgendwo anders geholt."
    ),
    "api.schema.docs_off": (
        "Die interaktiven Anzeigen (Swagger UI unter <code>/docs</code>, ReDoc "
        "unter <code>/redoc</code>) sind bei diesem Deployment abgeschaltet; ein "
        "Betreiber schaltet sie mit <code>COS_WEB_ENABLE_DOCS=true</code> ein."
    ),
    "api.agents.kicker": "Agenten",
    "api.agents.heading": "Für KI-Agenten",
    "api.agents.body": (
        "Software, die nicht für diesen Dienst geschrieben wurde, hat eine "
        'eigene Seite: <a href="/ai">für KI-Agenten</a> sammelt das '
        "Discovery-Dokument, das OpenAPI-Schema, die Arazzo-Workflows und den "
        "MCP-Endpunkt an einem Ort."
    ),
    # -------------------------------------------------------------------- AI
    "ai.title": "Für KI-Agenten",
    "ai.description": (
        "Alles, was Software braucht, um diesen Scanner zu nutzen, ohne dafür "
        "geschrieben worden zu sein: das Discovery-Dokument, das OpenAPI-Schema, "
        "die Arazzo-Workflows und der MCP-Endpunkt."
    ),
    "ai.kicker": "Maschinelle Gäste",
    "ai.lede": (
        "Dieser Dienst soll von Software nutzbar sein, die nicht für ihn "
        "geschrieben wurde. Alles, was ein Agent braucht, ist öffentlich "
        "verfügbar, ohne Konto: was die API kann, wie sich ihre Aufrufe zu einer "
        "Aufgabe zusammensetzen, und ein Weg, diese Aufgabe direkt auszuführen."
    ),
    "ai.discovery.kicker": "Discovery",
    "ai.discovery.heading": "Von einer Adresse aus starten",
    "ai.discovery.discovery": (
        "<strong>Discovery</strong> - "
        '<a href="/.well-known/ai.json">/.well-known/ai.json</a> nennt alles '
        "Folgende, mit absoluten URLs. Hier starten."
    ),
    "ai.discovery.openapi": (
        '<strong>OpenAPI</strong> - <a href="/openapi.json">/openapi.json</a>, '
        "jede Operation mit ihren echten Statuscodes und Antwortformen."
    ),
    "ai.discovery.arazzo": (
        '<strong>Arazzo-Workflows</strong> - <a href="/arazzo.json">'
        "/arazzo.json</a>, der Lebenszyklus eines Scans: einreichen, abfragen, "
        "Abschluss erkennen, exportieren."
    ),
    "ai.discovery.mcp": (
        "<strong>MCP</strong> - <code>{url}</code>, ein Model-Context-Protocol-"
        "Endpunkt über streambares HTTP. Werkzeuge: <code>scan_instance</code>, "
        "<code>scan_instances</code>, <code>get_scan_result</code>, "
        "<code>plan_remediation</code>, <code>export_scan</code> und "
        "<code>erase_instance_data</code>. <code>scan_instance</code> erledigt "
        "die ganze Aufgabe - Einreichung, Warten und Ergebnis - in einem Aufruf. "
        "Prompts benennen die Aufgaben selbst, etwa "
        "<code>audit_instance</code>, das eine Instanz prüft und den "
        "Sanierungsplan schreibt, und <code>review_transport_security</code>, "
        "das nur das Zertifikat und den Handshake betrachtet. Er beantwortet das "
        "Protokoll statt einen Browser, ist also eine Adresse zum Konfigurieren "
        "statt eine Seite zum Öffnen."
    ),
    "ai.discovery.summary": (
        "Die drei Dokumente beschreiben einen Dienst aus drei Blickwinkeln: "
        "OpenAPI sagt, was die API kann, und Arazzo sagt, wie sich diese "
        "Operationen zu einer Aufgabe zusammensetzen. Sie werden aus demselben "
        "Code erzeugt, den der Server ausführt, sodass keines von ihnen "
        "unbemerkt veralten kann."
    ),
    "ai.discovery.summary_mcp": (
        "Die drei Dokumente beschreiben einen Dienst aus drei Blickwinkeln: "
        "OpenAPI sagt, was die API kann, Arazzo sagt, wie sich diese Operationen "
        "zu einer Aufgabe zusammensetzen, und MCP übergibt diese Aufgabe einem "
        "Agenten als aufrufbares Werkzeug. Sie werden aus demselben Code erzeugt, "
        "den der Server ausführt, sodass keines von ihnen unbemerkt veralten "
        "kann."
    ),
    "ai.webmcp.kicker": "Im Browser",
    "ai.webmcp.heading": "Die Seite als Werkzeug verwenden",
    "ai.webmcp.intro": (
        "Ein Browser mit Unterstützung für den "
        '<a href="https://webmachinelearning.github.io/webmcp/" '
        'rel="noopener noreferrer">WebMCP-Entwurf</a> kann Aktionen direkt auf '
        "der geöffneten Seite entdecken. Ein separater Client ist nicht nötig."
    ),
    "ai.webmcp.landing": (
        "Auf der Startseite stellt <code>scan_opencloud_security</code> einen Scan "
        "in die Warteschlange. Das Schema enthält die Release-Tracks, "
        "Ausgabeformate und Ausnahmen, die diese Seite anbietet."
    ),
    "ai.webmcp.result": (
        "Auf einer Ergebnisseite liest <code>get_scan_result</code> den aktuellen "
        "Scan. <code>export_scan_report</code> lädt JSON, CSV, SARIF oder PDF für "
        "die bereits angezeigte UUID herunter."
    ),
    "ai.webmcp.boundary": (
        "Jedes Browser-Werkzeug verwendet dieselbe JSON-API mit "
        "<code>Accept: application/json</code>. SSRF-Schutz, Limits, Ziel-Wartezeit, "
        "Warteschlange und UUID-Isolierung bleiben wirksam."
    ),
    "ai.webmcp.support": (
        "WebMCP ist noch ein Entwurf und wird von Browsern ohne Unterstützung "
        "ignoriert. Wird MCP für diese Bereitstellung abgeschaltet, verschwinden "
        "auch die Browser-Werkzeuge."
    ),
    "ai.clients.kicker": "Konfiguration",
    "ai.clients.heading": "In einen Client einbinden",
    "ai.clients.intro": (
        "Die meisten Agenten-Werkzeuge nehmen eine URL und einen Transport. "
        "Dieser hier ist streambares HTTP, ohne Authentifizierung und ohne "
        "Konto:"
    ),
    "ai.clients.body": (
        "Ausgearbeitete Konfigurationen für Claude Code, Claude Desktop, GitHub "
        "Copilot in VS Code und der CLI, Cursor, Zed und Windsurf - gegen dieses "
        "Deployment oder ein eigenes - findest du in "
        '<a href="{project}/blob/main/docs/mcp.md" rel="noopener noreferrer">'
        "der MCP-Anleitung</a>."
    ),
    "ai.rules.kicker": "Die Regeln",
    "ai.rules.heading": "Dieselben Regeln wie für alle anderen",
    "ai.rules.body": (
        "Die Regeln sind für einen Agenten dieselben wie für jeden anderen. Ein "
        "Scan ist asynchron, und die UUID ist der einzige Weg zurück zu ihm; "
        "ein <code>429</code> ist eine Einladung, langsamer zu machen, keine "
        "Ablehnung; und wenn du mehr als eine Handvoll Instanzen prüfst, "
        'bitte <a href="{project}" rel="noopener noreferrer">führe den '
        "Scanner selbst aus</a> - es ist derselbe Code, auf deiner eigenen "
        "Maschine, ohne Grenzen."
    ),
    # -------------------------------- Docker one-liners, on /documentation
    "cli.lede": (
        "Einem fremden Server eine Adresse anzuvertrauen ist ein vernünftiger "
        "Grund zum Zögern. Du musst es nicht: Diese Seite ist dieselbe "
        "Prüfung, als ein Befehl auf deiner eigenen Maschine."
    ),
    "cli.oneliner.kicker": "Die Einzeiler",
    "cli.oneliner.heading": "Ein Befehl, nichts installiert",
    "cli.oneliner.body": (
        "Das ist die ganze Sache. Er gibt dasselbe Urteil aus, das diese "
        "Website zeichnet - die Note, den Release-Lebenszyklus, die Advisories "
        "und jede fehlgeschlagene Prüfung - und beendet sich mit dem "
        "Nagios-Statuscode, sodass dieselbe Zeile in einem Skript, einer "
        "Pipeline oder einem Cron-Job funktioniert. Nichts wird irgendwohin "
        "gesendet: Der Container spricht mit deiner Instanz und mit niemandem "
        "sonst."
    ),
    "cli.json.kicker": "Als JSON",
    "cli.json.heading": "Das gesamte Ergebnisdokument",
    "cli.json.body": (
        "Jede Zahl auf einer Ergebnisseite stammt aus diesem Dokument, "
        "einschließlich des <code>addresses</code>-Blocks hinter der Zeile "
        "<strong>Aufgelöst zu</strong> - die IPv4- und IPv6-Adressen, auf die "
        "der Name während des Scans zeigte."
    ),
    "cli.private.kicker": "Dein eigenes Netzwerk",
    "cli.private.heading": "Die Instanzen, die diese Website nicht scannt",
    "cli.private.body": (
        "Ein öffentlicher Dienst, der private Adressen scannen würde, ist ein "
        "öffentlicher Dienst, der auf das interne Netzwerk eines anderen "
        "gerichtet werden kann, deshalb lehnt dieser hier ab. Deine eigene "
        "Maschine hat dieses Problem nicht: eine Staging-Box, ein Name, den nur "
        "dein Resolver kennt, oder eine Instanz, die das LAN nie verlässt, "
        "funktionieren alle über die Kommandozeile."
    ),
    "cli.nodocker.kicker": "Kein Docker?",
    "cli.nodocker.heading": "Ohne Container",
    "cli.nodocker.body": (
        "Die Prüfung ist ein gewöhnliches Python-Programm auf PyPI, sodass "
        "<code>uv</code> oder <code>pipx</code> es holen und ausführen, ohne "
        "irgendetwas dauerhaft zu installieren."
    ),
    # ------------------------------------------------ CLI documentation index
    "docs.index.title": "CLI-Dokumentation",
    "docs.index.description": (
        "Die check-opencloud-security-CLI installieren, ausführen und "
        "konfigurieren, mit den vollständigen Betreiberanleitungen an einem Ort "
        "gesammelt."
    ),
    "docs.index.kicker": "Dokumentation",
    "docs.index.heading": "Den Scanner von deinem Terminal aus ausführen",
    "docs.index.lede": (
        "Die praktische CLI-Referenz, zusammengetragen aus dem "
        "Projekt-README und den Anleitungen unter <code>docs/</code>. Beginne "
        "mit einem Befehl; heb dir den Rest auf, bis die Prüfung Teil "
        "von Monitoring, CI oder einer Flotte wird."
    ),
    "docs.index.toc.quickstart": "Schnellstart",
    "docs.index.toc.commands": "Befehle",
    "docs.index.toc.options": "Nützliche Optionen",
    "docs.index.toc.configuration": "Konfiguration",
    "docs.index.toc.monitoring": "Monitoring",
    "docs.index.toc.guides": "Vollständige Anleitungen",
    "docs.index.quickstart.kicker": "Schnellstart",
    "docs.index.quickstart.heading": (
        "Eine Prüfung, ohne irgendetwas zu installieren"
    ),
    "docs.index.quickstart.container": (
        "Oder nutze den veröffentlichten Container. Er führt dasselbe "
        "Plugin aus und liefert denselben Nagios/Icinga-Exit-Code:"
    ),
    "docs.index.quickstart.note": (
        "Das Plugin spricht direkt mit der Instanz. Es sendet die Adresse weder "
        "an diese Website noch an einen entfernten Urteilsdienst."
    ),
    "docs.index.commands.kicker": "Zwei Einstiegspunkte",
    "docs.index.commands.heading": "Das Urteil und das Ergebnisdokument",
    "docs.index.commands.plugin": (
        "Das Monitoring-Plugin: eine Alarmzeile, Performance-Daten und die "
        "Standard-Exit-Codes <strong>OK</strong>, <strong>WARNING</strong>, "
        "<strong>CRITICAL</strong> und <strong>UNKNOWN</strong>."
    ),
    "docs.index.commands.scanner": (
        "Die Scanner-Bibliothek als CLI: das vollständige JSON-Ergebnisdokument "
        "für ein Skript, eine Pipeline oder eine Ad-hoc-Untersuchung."
    ),
    "docs.index.options.kicker": "Die alltäglichen Flags",
    "docs.index.options.heading": "Nützliche Optionen",
    "docs.index.option.host": (
        "Hostname, IP oder URL; durch Komma getrennt für mehrere Instanzen."
    ),
    "docs.index.option.check_hardening": (
        "Fehlende Härtungsmaßnahmen und Sicherheits-Header einbeziehen."
    ),
    "docs.index.option.release_track": (
        "<code>rolling</code>, <code>production</code>, <code>lts</code> oder "
        "<code>auto</code>."
    ),
    "docs.index.option.ignore_hardening": (
        "Einen Befund akzeptieren, ohne seinen Nachweis zu löschen; "
        "wiederholbar und mit Wildcard-Unterstützung."
    ),
    "docs.index.option.debug": (
        "Erklären, wo die Bewertung begann und was sie nach unten drückte."
    ),
    "docs.index.option.insecure": (
        "Zertifikatsprüfung für eine Instanz überspringen, die du kontrollierst."
    ),
    "docs.index.option.thresholds": (
        "Die Bewertungsschwellen wählen, die auf Monitoring-Zustände abbilden."
    ),
    "docs.index.option.format": "Nagios-Ausgabe oder Prometheus-Text drucken.",
    "docs.index.option.baseline": (
        "Nur bei Befunden alarmieren, die neu sind oder sich gegenüber dem "
        "letzten Lauf verschlechtert haben."
    ),
    "docs.index.option.webhook": (
        "Ein anderes System benachrichtigen, wenn der konfigurierte Zustand "
        "erreicht ist."
    ),
    "docs.index.options.manual": (
        "<code>check-opencloud-security --help</code> ist das installierte "
        'Handbuch. Die <a href="{project}#cli-usage" rel="noopener noreferrer">'
        "vollständige Optionstabelle</a> enthält jeden Standardwert und seine "
        "<code>COS_</code>-Umgebungsvariable."
    ),
    "docs.index.configuration.kicker": "Eine Richtung",
    "docs.index.configuration.heading": "Konfiguration und Rangfolge",
    "docs.index.configuration.intro": (
        "Einstellungen können aus einer YAML- oder JSON-Datei, der Umgebung "
        "oder der Kommandozeile stammen. Die Reihenfolge ist immer:"
    ),
    "docs.index.precedence.aria": "Konfigurationsrangfolge, höchste zuerst",
    "docs.index.precedence.cli": "CLI-Flag",
    "docs.index.precedence.cli.note": "die explizite Antwort für diesen Lauf",
    "docs.index.precedence.env": "Umgebung",
    "docs.index.precedence.env.note": (
        "<code>COS_*</code>, nützlich in Containern und Diensten"
    ),
    "docs.index.precedence.file": "Konfigurationsdatei",
    "docs.index.precedence.file.note": "die dauerhaften Standardwerte des Betreibers",
    "docs.index.precedence.default": "Eingebauter Standardwert",
    "docs.index.precedence.default.note": (
        "die sichere Antwort, wenn nichts angegeben wurde"
    ),
    "docs.index.configuration.wizard": (
        "Den Assistenten die erste Datei schreiben lassen:"
    ),
    "docs.index.configuration.note": (
        "Eine Datei, die auf <code>.json</code> endet, ist JSON; jede andere "
        "Endung ist YAML. Geheimnisse können in separaten Dateien statt auf der "
        "Kommandozeile liegen."
    ),
    "docs.index.monitoring.kicker": "Einsatzbereit machen",
    "docs.index.monitoring.heading": (
        "Monitoring, Automatisierung und mehrere Instanzen"
    ),
    "docs.index.monitoring.nagios": (
        "<strong>Nagios oder Icinga:</strong> die Plugin-Ausgabe direkt "
        "verwenden; der schlechteste konfigurierte Schwellenwert bestimmt den "
        "Exit-Code."
    ),
    "docs.index.monitoring.fleet": (
        "<strong>Mehrere Instanzen:</strong> eine durch Komma getrennte "
        "Host-Liste übergeben, oder eine Konfigurationsdatei pro Instanz "
        "verwenden, sobald sich ihre Einstellungen unterscheiden."
    ),
    "docs.index.monitoring.prometheus": (
        "<strong>Prometheus:</strong> einmal <code>--format=prometheus</code> "
        "verwenden, oder den eingebauten Exporter mit "
        "<code>--prometheus-listen-port</code> freigeben."
    ),
    "docs.index.monitoring.ci": (
        "<strong>CI:</strong> denselben Befehl in einer Pipeline ausführen; der "
        "Statuscode lässt eine fehlgeschlagene Richtlinie den Job ohne "
        "Wrapper scheitern lassen."
    ),
    "docs.index.monitoring.scheduled": (
        "<strong>Geplante Prüfungen:</strong> systemd, cron, Kubernetes und die "
        "Ansible-Rolle nutzen alle denselben CLI- und Konfigurationsablauf."
    ),
    "docs.index.guides.kicker": "Aus dem Repository",
    "docs.index.guides.heading": "Vollständige Betreiberanleitungen",
    "docs.index.guides.lede": (
        "Jedes Quelldokument hat hier seine eigene HTML-Seite, erzeugt aus dem "
        "Markdown des Repositorys und in der CI auf Abweichungen geprüft."
    ),
    # --------------------------------------------------- generated guide pages
    "docs.guide.kicker": "CLI-Dokumentation",
    "docs.guide.english_notice": (
        "Diese Anleitung wird aus der Dokumentation des Projekts erzeugt und ist "
        "nur auf Englisch verfügbar. Die Seite drumherum ist übersetzt; der Text "
        "unten ist es nicht."
    ),
    "docs.guide.toc.heading": "Auf dieser Seite",
    "docs.guide.toc.aria": "Auf dieser Seite",
    # ----------------------------------------------------------------- search
    "search.title": "Suche",
    "search.description": (
        "Die Scanner-Dokumentation und öffentliche Anleitungen durchsuchen. "
        "Scan-Ergebnisse werden nie indexiert."
    ),
    "search.eyebrow": "Statischer Release-Index",
    "search.heading": "Den Scanner durchsuchen",
    "search.lede": (
        "Nur Dokumentation und öffentliche Anleitungen. Der Index wird für "
        "Releases neu aufgebaut; er liest nie den Scan-Speicher, "
        "Ergebnisseiten, UUIDs oder übermittelte Adressen."
    ),
    "search.label": "Dokumentation durchsuchen",
    "search.placeholder": "TLS, Docker, Waiver...",
    "search.submit": "Suchen",
    "search.status.idle": (
        "Gib einen Begriff ein, um die Dokumentation dieses Releases zu "
        "durchsuchen."
    ),
    "search.status.results": "{count} Ergebnis(se) in diesem Release.",
    "search.status.empty": "Keine öffentliche Dokumentation passte zu dieser Suche.",
    "search.status.error": "Die Suche ist vorübergehend nicht verfügbar.",
    # The search manifest: the title and summary an index entry carries, as
    # opposed to the words on the page itself.
    "search.page.index.title": "Eine OpenCloud-Instanz scannen",
    "search.page.index.summary": (
        "Einen öffentlichen Sicherheitsscan gegen eine OpenCloud-Instanz "
        "ausführen."
    ),
    "search.page.how.title": "Wie der Scanner funktioniert",
    "search.page.how.summary": (
        "Was der Scanner misst, was er nicht sehen kann, und wie mit "
        "Ergebnissen umgegangen wird."
    ),
    "search.page.grades.title": "Was die Noten bedeuten",
    "search.page.grades.summary": (
        "Die Bewertungsskala von A+ bis F und die Fixes, die jede Note "
        "verbessern."
    ),
    "search.page.catalogue.title": "Was der Scanner prüft",
    "search.page.catalogue.summary": (
        "Jedes Härtungsmerkmal, jeden Header- und TLS-Check des Scanners, und "
        "jede bekannte Sicherheitslücke."
    ),
    "search.page.documentation.title": "CLI-Dokumentation",
    "search.page.documentation.summary": (
        "Kommandozeilen-Schnellstart, Konfiguration, Monitoring und "
        "Deployment-Anleitungen."
    ),
    "search.page.api.title": "API",
    "search.page.api.summary": (
        "Scans einreichen, Ergebnisse abfragen, Berichte exportieren und "
        "gespeicherte Daten löschen."
    ),
    "search.page.ai.title": "KI und MCP",
    "search.page.ai.summary": (
        "Maschinenlesbares OpenAPI, Arazzo, Discovery, MCP-Werkzeuge und "
        "Prompts."
    ),
    "search.page.privacy.title": "Datenschutz",
    "search.page.privacy.summary": (
        "Aufbewahrung von Ergebnissen, Anfrageprotokollierung, Ratenlimits und "
        "Drittanbieter-Richtlinie."
    ),
    "search.page.about.title": "Über dieses Projekt",
    "search.page.about.summary": (
        "Warum dieser unabhängige OpenCloud-Sicherheitsscanner existiert."
    ),
    # ------------------------------------------- what a submission is refused for
    # The API answers the English sentence these translate; a browser reads
    # the translation. The SSRF guard names the identifier, this names the
    # sentence, and neither is derived from the other.
    "error.unsupported_fields": (
        "Dieser Dienst akzeptiert {fields} nicht. Der Scan läuft ausschließlich "
        "mit serverseitigen Einstellungen."
    ),
    "error.rate_limit.client": (
        "Das sind viele Scans aus deinem Netzwerk in kurzer Zeit. Warte eine "
        "Minute und versuche es erneut."
    ),
    "error.rate_limit.target": (
        "Diese Instanz wurde erst vor kurzem gescannt. Bitte gib ihr ein "
        "paar Minuten."
    ),
    "error.target.invalid": "Diese Adresse kann nicht gescannt werden.",
    "error.target.empty": (
        "Gib die Adresse der zu scannenden OpenCloud-Instanz ein."
    ),
    "error.target.too_long": "Diese Adresse ist zu lang.",
    "error.target.characters": (
        "Diese Adresse enthält Zeichen, die ein Hostname nicht haben kann."
    ),
    "error.target.unparsed": "Diese Adresse konnte nicht verarbeitet werden.",
    "error.target.scheme": (
        "Nur http://- und https://-Ziele können gescannt werden."
    ),
    "error.target.credentials": (
        "Zugangsdaten in der Adresse werden nicht akzeptiert."
    ),
    "error.target.address_only": (
        "Gib nur die Basisadresse der Instanz ein. Ein einfacher "
        "Unterordner wird akzeptiert, Queries, Fragmente, Parameter und "
        "Pfad-Traversierung jedoch nicht."
    ),
    "error.target.port": "Diese Adresse hat einen ungültigen Port.",
    "error.target.no_host": "Diese Adresse hat keinen Hostnamen.",
    "error.target.hostname_shape": (
        "Das ist kein Hostname, den dieser Dienst scannen kann."
    ),
    "error.target.unresolved": "Dieser Hostname löst sich nicht auf.",
    "error.target.hostname_long": "Dieser Hostname ist zu lang.",
    "error.target.internal": (
        "Lokale und interne Adressen können nicht gescannt werden."
    ),
    "error.target.private": (
        "Diese Adresse zeigt in ein privates, lokales oder link-lokales "
        "Netzwerk, das dieser Dienst nicht scannt."
    ),
    # ----------------------------------------------------------- result page
    "result.title": "Scan-Ergebnisse",
    "result.description": (
        "Das Ergebnis eines öffentlichen Scans, lesbar nur mit seiner eigenen "
        "Kennung."
    ),
    "result.kicker": "Lagebericht",
    "result.heading": "Scan-Ergebnis",
    "result.track.title": (
        "Der Release-Track, gegen den dieser Scan bewertet wurde"
    ),
    "result.track.label": "{track}-Track",
    "result.another": "Eine weitere Instanz scannen",
    "result.progress.kicker": "In Bearbeitung",
    "result.progress.queued.title": "Wartet auf einen Scanner-Worker",
    "result.progress.queued.detail": (
        "Gerade sind alle Worker beschäftigt. Dein Scan behält seinen Platz in "
        "der Reihe und startet, sobald einer frei ist."
    ),
    "result.progress.running.title": "Die Instanz wird gescannt",
    "result.progress.running.detail": (
        "Liest, was die Instanz veröffentlicht: Version, Fähigkeiten, "
        "Zertifikat, Header und die Endpunkte, die sie ohne Anmeldung "
        "preisgibt."
    ),
    "result.progress.step.queued": "In Warteschlange",
    "result.progress.step.running": "Läuft",
    "result.progress.step.done": "Ergebnis",
    "result.progress.noscript": (
        "Diese Seite aktualisiert sich mit JavaScript. Ohne dieses lädst du "
        "die Seite in ein paar Sekunden neu, um das Ergebnis zu sehen."
    ),
    "result.progress.queue.position": (
        "Scan in Warteschlange. Position in der Reihe: #{position} von "
        "{length}."
    ),
    "result.progress.queue.next": (
        "Scan in Warteschlange. Du bist als Nächstes dran."
    ),
    "result.progress.queue.waiting": (
        "Wartet darauf, dass ein Scanner-Worker dies übernimmt."
    ),
    "result.progress.done.title": "Bericht fertig",
    "result.progress.done.detail": "Die Note steht fest. Der Bericht wird geöffnet.",
    "result.progress.failed.title": "Scan beendet",
    "result.progress.failed.detail": (
        "Der Scan konnte nicht abgeschlossen werden. Das Ergebnis wird geöffnet."
    ),
    "result.failed.fallback": "Der Scan konnte nicht abgeschlossen werden.",
    "result.failed.body": (
        "Es wurde nichts benotet, weil nichts Brauchbares zurückkam. Prüfe, "
        "ob die Adresse stimmt, ob die Instanz aus dem öffentlichen Internet "
        "erreichbar ist, und ob es sich um eine OpenCloud-Instanz handelt."
    ),
    "result.document.kicker": "Ergebnisdokument",
    "result.document.heading": "Ergebnisdokument",
    "result.document.lede": (
        "Dasselbe Dokument, das die Kommandozeilenprüfung und das Nagios-Plugin "
        "auswerten."
    ),
    "result.verdict.kicker": "Urteil",
    "result.verdict.heading": "Gesamtbewertung",
    "result.verdict.dial": "Note {label}, {rating} von 5",
    "result.facts.instance": "Instanz",
    "result.facts.resolved": "Aufgelöst zu",
    "result.facts.ipv6.heading": "IPv6-Erreichbarkeit",
    "result.facts.ipv6.note": (
        "Nicht geprüft - dieses Deployment hat keine ausgehende IPv6-"
        "Verbindung, daher wird dies nur vermerkt und nicht gegen die "
        "Instanz gewertet."
    ),
    "result.facts.product": "Produkt",
    "result.facts.track": "Release-Track",
    "result.facts.track.unknown": "unbekannt",
    "result.facts.eol_tag": "End of Life",
    "result.facts.schedule": "Release-Zeitplan",
    "result.facts.schedule.stale": (
        "{version} ist neuer als diese Kopie des OpenCloud-Release-Zeitplans, "
        "der Zeitplan ist also wahrscheinlich veraltet. Es wird der Instanz "
        "nicht angelastet -"
    ),
    "result.facts.schedule.stale_generated": (
        "{version} ist neuer als diese Kopie des OpenCloud-Release-Zeitplans, "
        "erzeugt am {generated}, der Zeitplan ist also wahrscheinlich veraltet. "
        "Es wird der Instanz nicht angelastet -"
    ),
    "result.facts.schedule.link": "die veröffentlichte Lebenszyklus-Seite prüfen",
    "result.facts.signin": "Anmeldung",
    "result.facts.signin.external": "Externer Anbieter",
    "result.facts.signin.upstream_tag": "vorgelagert",
    "result.facts.signin.version_unavailable": "Version nicht offengelegt",
    "result.facts.signin.advisories": "Sicherheitshinweise prüfen",
    "result.facts.signin.builtin": "Eingebauter Identity-Provider",
    "result.facts.signin.none": "Nicht erkannt -",
    "result.facts.signin.link": "wie die OpenCloud-Anmeldung eingerichtet wird",
    "result.facts.proxy": "Reverse Proxy",
    "result.facts.proxy.detected": "Erkannt",
    "result.facts.office": "Office",
    "result.facts.calendar": "Kalender",
    "result.facts.calendar.detected": "Etwas antwortet auf den CalDAV-Pfad",
    "result.facts.newest": "Neuestes Release",
    "result.facts.score": "Punktzahl",
    "result.facts.score.value": "{rating} von 5",
    "result.counter.critical": "Kritisch",
    "result.counter.warning": "Warnung",
    "result.counter.info": "Info",
    "result.counter.advisories": "Advisories",
    "result.counter.passed": "Bestanden",
    "result.verdict.why": "Warum diese Note:",
    "result.verdict.caveat": (
        "Eine Note sagt, dass die unten stehenden Prüfungen bestanden wurden, "
        "nicht, dass die Instanz sicher ist. Dieser Scan ist nicht erschöpfend: "
        "Er sieht nur, was die Instanz einem anonymen Besucher zeigt. "
        '<a href="#scan-limits">Was er nicht sehen kann</a>.'
    ),
    "result.fix": "Fix:",
    "result.documentation": "Dokumentation",
    "result.explain.title": "Was diese Prüfung bedeutet",
    "result.plan.kicker": "Sanierungsplan",
    "result.plan.heading": "Was dich zu {label} bringt",
    "result.plan.then": "dann {label}",
    "result.plan.still": "immer noch {label}",
    "result.plan.note": (
        "Die Reihenfolge ist die, die sich am schnellsten auszahlt, und die Note "
        "neben einem Schritt ist die Bewertung, die erreicht würde, sobald "
        "dieser Schritt und alles darüber erledigt ist. Befunde gleichen "
        "Schweregrads teilen sich eine Obergrenze, sodass sich die Note erst "
        "bewegt, wenn der letzte von ihnen verschwunden ist - deshalb kann ein "
        "Schritt notwendig sein und trotzdem für sich allein nichts versprechen."
    ),
    "result.plan.blocked.heading": (
        "Drückt die Note nach unten, und ist nicht behebbar"
    ),
    "result.plan.blocked.note": (
        "OpenCloud hat diese fest codiert, sodass keine Einstellung sie "
        "erreicht. Sie sind der Grund, warum der obige Plan dort endet, wo er "
        "endet."
    ),
    "result.eol.alert": (
        "Dieses Release erhält keine Sicherheitsfixes mehr. Nichts anderes auf "
        "dieser Seite kann die Note anheben, bis es aktualisiert wird."
    ),
    "result.advisories.kicker": "Advisories",
    "result.advisories.heading": "Bekannte Advisories für diese Version",
    "result.advisories.lede": (
        "Veröffentlichte Advisories, deren betroffener Bereich {version} "
        "einschließt."
    ),
    "result.advisories.fallback_id": "Advisory",
    "result.advisories.unrated": "unbewertet",
    "result.advisories.no_summary": "Keine Zusammenfassung veröffentlicht.",
    "result.advisories.read": "Die Advisory lesen",
    "result.findings.kicker": "Befunde",
    "result.findings.heading": "Fehlgeschlagene Prüfungen",
    "result.findings.lede": (
        "Jeder deckelt die Note auf dem Niveau, das sein Schweregrad zulässt. "
        "Behebe zuerst die kritischen: Sie drücken die Punktzahl am "
        "stärksten nach unten."
    ),
    "result.findings.allclear.tag": "Alles klar",
    "result.findings.allclear.body": (
        "Jede Prüfung, die dieser Scanner durchführt, wurde auf dieser Instanz "
        "bestanden."
    ),
    "result.hardening.kicker": "Härtung",
    "result.hardening.heading": "Härtung, die sich lohnt",
    "result.hardening.lede": (
        "Einstellungen, die nicht aktiviert sind. Keine davon ist eine aktive "
        "Schwachstelle; jede beseitigt einen Weg hinein."
    ),
    "result.hardening.tag": "Härtung",
    "result.header.tag": "Header",
    # ------------------------------------------------- configuration fragment
    "result.fragment.kicker": "Die Behebung, ausgeschrieben",
    "result.fragment.heading": "Das hier in Ihre Konfiguration einfügen",
    "result.fragment.lede": (
        "Die Befunde von oben, in der Syntax der Datei, die geändert werden "
        "muss. Wählen Sie, wo Ihre Instanz konfiguriert wird."
    ),
    "result.fragment.caution": (
        "Lesen Sie vor dem Einfügen die Zeile „Behebung“ jedes Befundes. Dies "
        "sind die Werte, nach denen die Prüfungen suchen, keine Bewertung "
        "dessen, was Ihre Installation braucht."
    ),
    "result.fragment.picker": "Konfigurationsformat",
    "result.fragment.file": "Gehört in {name}.",
    "result.fragment.copy": "Kopieren",
    "result.fragment.copied": "Kopiert",
    "result.fragment.copy_failed": "Kopieren fehlgeschlagen",
    "result.fragment.nothing": (
        "Hier wird nichts auf diese Weise gesetzt. Was offen ist, gehört "
        "nach {flavours}."
    ),
    "result.fragment.elsewhere": (
        "Diese werden woanders behoben - sie gehören nach {flavours}:"
    ),
    "result.fragment.undecided": (
        "Für diese gibt es keinen Wert zum Einfügen: der richtige ist eine "
        "Entscheidung über diese Installation, und die Zeile „Behebung“ des "
        "Befundes ist die ganze Antwort."
    ),
    # ------------------------------------------------------------ scan again
    "result.rescan": "Erneut scannen",
    "result.rescan.ready": "Diese Instanz kann erneut gescannt werden.",
    "result.rescan.wait": "Erneut scannen möglich in {countdown}.",
    "result.rescan.note": (
        "Gleiches Ziel, gleiche Ausnahmen, gleicher Release-Track - damit das "
        "nächste Ergebnis mit diesem vergleichbar ist. Die Wartezeit hält "
        "diesen kleinen Dienst am Laufen; der Scanner ist quelloffen und "
        "läuft auf Ihrem eigenen Rechner ganz ohne Limits:"
    ),
    "result.rescan.self_host": "selbst betreiben",
    "result.excluded.kicker": "Ausgeschlossen",
    "result.excluded.heading": "Gemeldet, aber nicht gezählt",
    "result.excluded.waived.heading": "Du batest darum, diese zu ignorieren",
    "result.excluded.waived.note": (
        "Sie sind trotzdem fehlgeschlagen. Sie haben die Note nur nicht mehr "
        "nach unten gedrückt."
    ),
    "result.excluded.unfixable.heading": "Niemand kann diese ändern",
    "result.excluded.unfixable.note": (
        "OpenCloud hat diese Flags fest codiert, sodass sie auf jeder "
        "existierenden Instanz gleich ausfallen. Sie werden der Vollständigkeit "
        "halber angezeigt und von der Note ausgeschlossen."
    ),
    "result.scope.kicker": "Umfang",
    "result.scope.heading": "Was dieser Scan nicht sehen kann",
    "result.scope.body": (
        "Alles oben wurde ohne Anmeldung gelesen, was der Sinn der Sache ist und "
        "zugleich die Grenze. <strong>Das Fehlen eines Befunds ist kein Beweis "
        "für Sicherheit</strong>, und die höchste Note, die diese Seite vergeben "
        "kann, ist keine Aussage darüber, dass die Instanz sicher ist - nur, "
        "dass nichts hier Geprüftes fehlgeschlagen ist. Ganze Kategorien liegen "
        "vollständig außerhalb dessen, was ein nicht angemeldeter Scan erreicht: "
        "das Betriebssystem und seine Pakete, die Container-Laufzeit, die "
        "eigene Konfiguration des Reverse Proxy, Backups und ihre "
        "Wiederherstellung, der Speicher hinter der Instanz, Geheimnisse und "
        "Schlüsselverwaltung, Konten, Passwörter und Multi-Faktor-Anmeldung, "
        "die Berechtigungen bestehender Freigaben, die Software-Lieferkette, "
        "und alles, was sich nur einem angemeldeten Benutzer zeigt. Ebenso "
        "diese zwei, die sichtbar sein sollten und es nicht sind:"
    ),
    "result.scope.audit": (
        "<strong>Audit-Protokollierung.</strong> Der Audit-Dienst von OpenCloud "
        "konsumiert nur den internen Event-Bus - er veröffentlicht keinen "
        "Endpunkt und erscheint in keinem nicht angemeldeten Dokument -, sodass "
        "von außen überhaupt nicht festgestellt werden kann, ob er läuft. Er "
        "wird nicht geprüft."
    ),
    "result.scope.integrations": (
        "<strong>Ob eine Office- oder Kalender-Integration <em>korrekt</em> "
        "eingerichtet ist.</strong> Diese Seite meldet nur, dass ein "
        "App-Provider registriert ist, oder dass etwas auf den CalDAV-Pfad "
        "antwortet. Freigaberegeln, WOPI-Geheimnisse und die eigene "
        "Konfiguration des zweiten Dienstes liegen alle hinter einer Anmeldung "
        "und werden nicht geprüft."
    ),
    "result.tls.kicker": "Transport",
    "result.tls.heading": "Transportsicherheit",
    "result.tls.lede": (
        "Was die TLS-Schicht sagte, bevor auch nur ein Byte HTTP ausgetauscht "
        "wurde. Die obigen Befunde beurteilen dies bereits; dies ist die "
        "Messung dahinter."
    ),
    "result.tls.protocol": "Protokoll",
    "result.tls.bits": "({bits} Bit)",
    "result.tls.deprecated": "Veraltete Versionen",
    "result.tls.deprecated.accepted": "Noch akzeptiert: {list}",
    "result.tls.deprecated.refused": "Abgelehnt: {list}",
    "result.tls.chain": "Kette",
    "result.tls.chain.trusted": "Vertrauenswürdig",
    "result.tls.chain.not_established": "Nicht hergestellt",
    "result.tls.chain.not_trusted": "Nicht vertrauenswürdig",
    "result.tls.chain.incomplete_note": "- kein Pfad zu einer öffentlichen Wurzel",
    "result.tls.issued_to": "Ausgestellt für",
    "result.tls.unnamed": "unbenannt",
    "result.tls.issued_by": "Ausgestellt von",
    "result.tls.unknown": "unbekannt",
    "result.tls.valid_for": "Gültig für",
    "result.tls.validity": "Gültigkeit",
    "result.tls.validity.range": "{start} bis {end}",
    "result.tls.validity.expired": "- vor {days} Tag(en) abgelaufen",
    "result.tls.validity.remaining": "- noch {days} Tag(e)",
    "result.tls.lifetime": "Ausgestellt für",
    "result.tls.lifetime.days": "{days} Tag(e)",
    "result.tls.ocsp": "OCSP-Stapling",
    "result.tls.ocsp.stapled": "Eine Widerrufsantwort ist angeheftet",
    "result.tls.ocsp.not_stapled": "Nicht angeheftet",
    "result.tls.ocsp.undetermined": "Nicht ermittelt",
    "result.raw.kicker": "Rohdaten",
    "result.raw.heading": "Technische Details",
    "result.raw.lede": (
        "Das vollständige Ergebnisdokument, genau so, wie das Plugin es sieht."
    ),
    "result.raw.summary": "Das rohe JSON anzeigen",
    "result.export.kicker": "Export",
    "result.export.heading": "Dieses Ergebnis mitnehmen",
    "result.export.lede": (
        "Derselbe Scan, auf vier Arten dargestellt. Jede wird erzeugt, wenn du "
        "danach fragst, und verschwindet mit dem Scan selbst."
    ),
    "result.export.pdf": "PDF-Bericht",
    "result.export.pdf.hint": "Für ein Ticket, eine Überprüfung oder einen Ausdruck.",
    "result.export.csv": "CSV",
    "result.export.csv.hint": "Eine Zeile pro Befund, für eine Tabellenkalkulation.",
    "result.export.sarif": "SARIF",
    "result.export.sarif.hint": "Für ein Code-Scanning-Dashboard.",
    "result.export.json": "JSON",
    "result.export.json.hint": "Das rohe Dokument, das das Plugin auswertet.",
    "result.export.passed.heading": "Was bereits bestanden hat",
    "result.export.passed.note": (
        "Diese Prüfungen waren unauffällig und stehen deshalb nicht im Plan oben."
    ),
    "result.share.kicker": "Teilen",
    "result.share.heading": "Diesen Bericht teilen",
    "result.share.lede": (
        "Per E-Mail oder über die eigene Zwischenablage. Nichts läuft über "
        "diesen Dienst, und kein anderes Unternehmen wird um Hilfe gebeten."
    ),
    "result.share.warning": (
        "Die Adresse dieser Seite ist das Einzige, was sie schützt: Wer sie "
        "hat, kann den Bericht lesen, bis er abläuft. Wer sie in einen Kanal "
        "stellt, teilt sie mit allen dort - und mit allem, was Links abruft, "
        "um eine Vorschau zu bauen. Kopiere stattdessen die Zusammenfassung, "
        "wenn es um die Befunde geht."
    ),
    "result.share.email": "Per E-Mail teilen",
    "result.share.email.hint": (
        "Öffnet dein eigenes Mailprogramm mit fertiger Nachricht. Bis du "
        "sendest, verlässt nichts deinen Browser."
    ),
    "result.share.email.subject": "OpenCloud-Sicherheitsbericht für {target}",
    "result.share.email.body": (
        "Hier ist der Sicherheitsbericht für unsere OpenCloud-Instanz:\n\n"
        "{url}\n\n"
        "Dieser Link gewährt den Zugang zum Bericht - behandle ihn wie ein "
        "Passwort. Er läuft von selbst ab, danach ist die Seite weg."
    ),
    "result.share.link": "Link kopieren",
    "result.share.link.hint": (
        "Die Adresse dieser Seite. Wer sie bekommt, kann den Bericht öffnen."
    ),
    "result.share.summary": "Zusammenfassung kopieren",
    "result.share.summary.hint": (
        "Die Befunde als Text, ohne Link darin. Das Sicherere zum Einfügen in "
        "einen Chat-Kanal."
    ),
    "result.share.summary.body": (
        "OpenCloud-Sicherheitsbericht - {domain}\n"
        "Note {label} ({rating} von 5)\n"
        "Kritisch {critical} | Warnung {warning} | Info {info} | "
        "Hinweise {advisories} | Bestanden {passed}\n"
        "Gemessen mit check-opencloud-security."
    ),
    "result.share.done": "Kopiert",
    "result.share.failed": "Kopieren nicht möglich",
    "result.share.fallback": "Die Adresse dieses Berichts:",
    "result.feedback.prompt": "Glaubst du, dass der Scan etwas falsch bewertet hat?",
    "result.feedback.link": "Falsch positives oder falsch negatives Ergebnis melden",
    "result.expiry.one": (
        "Diese Seite läuft in etwa 1 Minute ab, danach funktioniert der Link "
        "nicht mehr und das Ergebnis ist weg."
    ),
    "result.expiry.many": (
        "Diese Seite läuft in etwa {minutes} Minuten ab, danach funktioniert "
        "der Link nicht mehr und das Ergebnis ist weg."
    ),
    # ----------------------------------------- transport facts beside the grade
    "tls.fact.protocol": "TLS-Version",
    "tls.fact.protocol.detail": "akzeptiert auch {list}",
    "tls.fact.expiry": "Zertifikat läuft ab",
    "tls.fact.expiry.expired": "vor {days} Tag(en) abgelaufen",
    "tls.fact.expiry.remaining": "noch {days} Tag(e)",
    "tls.fact.chain": "Kette",
    "tls.fact.chain.incomplete": "Unvollständig",
    "tls.fact.chain.incomplete.detail": "kein Pfad zu einer öffentlichen Wurzel",
    "tls.fact.chain.untrusted": "Nicht vertrauenswürdig",
    "tls.fact.chain.untrusted.detail": (
        "selbstsigniert, oder eine unbekannte Zertifizierungsstelle"
    ),
    "tls.fact.chain.unknown": "Nicht hergestellt",
    "tls.fact.chain.unknown.detail": (
        "der Handshake hat das Zertifikat nie erreicht"
    ),
    "tls.fact.chain.ok": "Vollständig und vertrauenswürdig",
}
