# Nur Änderungen melden

Mit `--baseline` speichert das Plugin die Befunde eines Durchlaufs und vergleicht den nächsten Scan damit. Zusammen mit `--warn-on-new` kannst du die Alarmierung auf neue oder verschlechterte Befunde beschränken. Bereits bekannte Probleme bleiben im Bericht sichtbar.

Eine Kurzfassung findest du im [Haupt-README](../../README.md#reporting-only-what-changed). Dieser Leitfaden erklärt die Vergleichsformate, die Kriterien für Verschlechterungen und den Umgang mit der Baseline-Datei.

## Baseline speichern und vergleichen {#writing-and-comparing-a-baseline}

Gib mit `--baseline` die Datei an, in der die Befunde gespeichert und beim nächsten Durchlauf zum Vergleich gelesen werden:

```bash
check-opencloud-security -H opencloud.example.com \
    --check-hardening \
    --baseline /var/lib/check_opencloud/baseline.json
```

Ohne weitere Optionen ergänzt das Plugin nur die Ausgabe um eine Zeile `Baseline: ...`. Mit `--warn-on-new` beeinflusst der Vergleich auch die Alarmierung:

```bash
check-opencloud-security -H opencloud.example.com \
    --check-hardening \
    --baseline /var/lib/check_opencloud/baseline.json \
    --warn-on-new
```

Solange keine neuen oder verschlechterten Befunde vorliegen, meldet das Plugin `OK`. Bei einer Verschlechterung gilt wieder der reguläre Status. Der vollständige Zustand wird in beiden Fällen ausgegeben:

```
OK: nothing new since the last run (WARNING state unchanged).
OpenCloud 7.2.3 on opencloud.example.com, rating: C, last scanned: 2026-01-14
Missing hardening: cspWithoutUnsafeInline (run with --debug for what each means and how to fix it)
Baseline: No new findings since 2026-01-14T09:00:00+00:00 (1 known issue(s) unchanged)
Suppressed by --warn-on-new: this run would otherwise be WARNING (WARNING: 1 hardening measure(s) missing, but no known vulnerabilities.)
```

Der Vergleich zeigt hinzugekommene und behobene CVEs, Änderungen an Härtungsmaßnahmen und zusätzlichen Prüfungen sowie Änderungen an Bewertung, Supportende, Supportzeitraum und installierter oder empfohlener Version. `text` eignet sich für Logs und ist der Standard. Für eine Zusammenfassung in GitHub Actions oder einen Pull-Request-Kommentar verwende Markdown:

```shell
check-opencloud-security -H opencloud.example.com \
  --baseline /var/lib/check_opencloud/baseline.json \
  --diff-format markdown >> "$GITHUB_STEP_SUMMARY"
```

`--diff-format slack` oder `json` erzeugt Slack-Block-Kit-JSON. Bei einem konfigurierten Webhook enthält `baseline_diff` jeden Vergleich. Das Slack-Format ergänzt auf oberster Ebene außerdem die Blöcke und das farbige Banner für eingehende Webhooks:

```shell
check-opencloud-security -H opencloud.example.com \
  --baseline /var/lib/check_opencloud/baseline.json \
  --diff-format slack --webhook-url 'https://hooks.slack.com/services/<token>' \
  --webhook-on always
```

## Was als Verschlechterung zählt {#what-counts-as-a-regression}

- Ein neuer Befund: etwa eine weitere Schwachstelle, eine weggefallene Schutzmaßnahme, eine erstmals fehlgeschlagene Zusatzprüfung oder ein neu verfügbares Update.
- Eine niedrigere Bewertung als beim vorherigen Durchlauf.
- **Eine Version nach ihrem Supportende, bei jedem Scan.** Da sie keine Sicherheitsupdates mehr erhält, unterdrückt eine Baseline diesen Alarm niemals.

## Konfigurationsänderungen {#configuration-drift}


Eine Baseline speichert auch den **Konfigurations-Fingerabdruck** des Scans:
Hashes für Transport, Header, Freigaben, Anmeldung und Proxy. Damit lassen
sich Konfigurationsänderungen erkennen, auch wenn Note und Befunde gleich
bleiben:

```text
Baseline: No new findings since 2026-09-14T06:00:00Z, but the configuration changed (headers, proxy)
```

Der Bericht nennt die Gruppen, deren Konfiguration sich geändert hat.
Baseline-Datei, Ausgabe und Webhook enthalten Hashes ohne die zugrunde
liegenden Konfigurationswerte.

Eine Änderung wird gemeldet, nicht bewertet: Sie erzeugt keinen Befund, macht
keinen Lauf zur Verschlechterung und ändert nie den Exit-Code. Eine Baseline
aus der Zeit vor den Fingerabdrücken kann Konfigurationsänderungen nicht
erkennen, weil ihr die Vergleichswerte fehlen. Sie meldet daher keine Änderung;
das belegt jedoch nicht, dass die Konfiguration unverändert ist.

## Verlorene Abdeckung {#coverage-regressions}


Eine Baseline merkt sich auch, zu welchen Prüfungen der Scan **ein Ergebnis
erreicht hat**. Ist eine Prüfung, die früher gemessen wurde, jetzt
`inconclusive` - sie lief, konnte aber nichts entscheiden, etwa weil eine
DNS-Abfrage nicht rechtzeitig antwortete -, meldet der Lauf das, auch wenn die
Note gleich bleibt:

```text
WARNING: 1 previously measured check(s) are now inconclusive; the rating is unchanged (Server is up to date. No known vulnerabilities.)
Coverage regressed (1): previously measured, now inconclusive: caaRecord (timeout) - the rating is unaffected.
```

Das ist von der Sicherheitsbewertung getrennt. Note, Perfdata und
Befunde bleiben, was die Messung ergeben hat; nur der Alarmstatus ändert sich,
und nur von `OK` auf `WARNING`. Ein Lauf, der schon `WARNING` oder `CRITICAL`
ist, behält seine Meldung und bekommt die Zeile dazu. `--warn-on-new`
unterdrückt sie nicht, denn ein Scan, der plötzlich weniger sieht, ist neu.

- Nur `inconclusive` zählt. Eine Prüfung, die zu `not_checked` wird - weil du
  sie abgeschaltet hast oder sie nicht mehr passt -, ist keine Verschlechterung
  des Scans.
- Eine verlorene Prüfung gilt so lange als „früher gemessen“, bis ein späterer
  Lauf sie wieder misst. Die Warnung hält also so lange wie die Lücke.
- Im Webhook steht die Liste als `coverage_regressed` in `baseline_diff`; der
  Vergleich zweier Dokumente meldet sie als `coverageRegressed`.
- Eine ältere Baseline ohne Abdeckung kann beim ersten Lauf nach dem Update
  keinen Verlust melden; sie speichert dann, was gemessen wurde.

## Prüfungen, die nur ein Lauf gemacht hat {#checks-only-one-run-made}

Ein Befund gilt nur dann als neu, wenn der vorige Lauf ihn hätte melden
können. Kommt eine Prüfung dazu - nach einem Update oder weil du die
zusätzlichen Prüfungen eingeschaltet hast -, war ein Fehler, den sie jetzt
findet, beim letzten Mal *nicht geprüft* und nicht bestanden. Der Lauf sagt
das so:

```text
Baseline: Newly measured (1): hardening:basicAuthDisabled - the last run did not check these
Hardening: + basicAuthDisabled (not checked before)
```

Er alarmiert trotzdem, und `--warn-on-new` unterdrückt ihn nicht: Von diesem
Fehler hat noch niemand erfahren. Umgekehrt steht ein Fehler, den der
aktuelle Lauf nicht mehr prüft, als `(not checked now)` da und nicht als
behoben.

- Was ein Lauf hätte melden können, kommt aus seinem Abdeckungsblock, nie aus
  einem fehlenden Schlüssel. Ein Bericht ohne Liste seiner Prüfungen wird wie
  bisher verglichen, eine echte Verschlechterung wird also nie umbenannt.
- Im Webhook stehen die Listen als `newly_measured` und `no_longer_measured`
  in `baseline_diff`, im Webvergleich als `newlyMeasured` und
  `noLongerMeasured`.
- Eine ältere Baseline kann nicht sagen, was sie geprüft hat; der erste Lauf
  nach dem Update vergleicht daher wie bisher.

## Verhalten und Dateirechte {#points-worth-knowing}

- Der erste Durchlauf meldet den regulären Status und legt die Baseline an. Ohne Vergleichsdaten wird nichts unterdrückt.
- Eine Datei enthält einen Eintrag pro Host und kann für eine kommagetrennte `--host`-Liste verwendet werden.
- Mit `--ignore-hardening` ausgenommene Befunde und von OpenCloud fest vorgegebene Maßnahmen bleiben wie in der Alarmzeile unberücksichtigt.
- `--warn-on-new` ohne `--baseline` wird abgelehnt, da der Vergleich eine gespeicherte Ausgangslage benötigt.
- Kann die Datei nicht geschrieben werden, erscheint ein Hinweis in der Ausgabe. Die Bewertung der Instanz bleibt davon unberührt.
- Die Datei wird atomar geschrieben und ist nur für den Eigentümer zugänglich. Verwende ein Verzeichnis des Monitoring-Benutzers, etwa `/var/lib/check_opencloud/`.

## Marken und Unabhängigkeit

Dies ist ein unabhängiges Community-Projekt. Es ist nicht mit OpenCloud GmbH
verbunden und wird von ihr nicht unterstützt. OpenCloud und zugehörige Marken
gehören ihren jeweiligen Inhabern und benennen hier die geprüfte Software.
