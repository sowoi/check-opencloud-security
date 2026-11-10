# Die Befehle von check-opencloud-scanner

Das Paket installiert zwei Programme:

- **`check-opencloud-security`** führt Scans aus und liefert anhand der Schwellwerte Nagios-/Icinga-Statuscodes von `0` bis `3`. Seine Optionen stehen in der [CLI-Referenz](../cli-reference.md).
- **`check-opencloud-scanner`** gibt das vollständige Ergebnis aus, vergleicht gespeicherte Scans, erklärt Befunde, aktualisiert Referenzdaten und betreibt den HTTP-Dienst. Es wendet keine WARNING- oder CRITICAL-Schwellwerte an.

Diese Seite beschreibt das zweite Programm.

## Globale Optionen {#global-options}

Globale Optionen stehen **vor** dem Unterbefehl:

```bash
check-opencloud-scanner -c /etc/check-opencloud-security/config.yml -v scan opencloud.example.com
```

| Option | Funktion |
|:--|:--|
| `-c, --config` | Konfigurationsdatei; `.json` wird als JSON, andere Endungen als YAML gelesen |
| `-v, --verbose` | Zusätzliche Meldungen auf stderr: `-v` für Info, `-vv` für Debug |

Ohne `-c` wird die erste vorhandene Datei aus dieser Reihenfolge verwendet:

1. `./.env.json`
2. `./check-opencloud-security.yml`
3. `./check-opencloud-security.yaml`
4. `~/.config/check-opencloud-security/.env.json`
5. `/etc/check-opencloud-security/.env.json`
6. `/etc/check-opencloud-security/config.yml`
7. `/etc/check-opencloud-security/config.yaml`

Das Plugin verwendet dieselbe Suche. `COS_`-Umgebungsvariablen überschreiben Dateieinstellungen; Kommandozeilenoptionen haben die höchste Priorität. Siehe [Zugangsdaten in der Konfiguration](../configuration.md).

## `scan`: Ergebnisdokument ausgeben {#scan-print-the-result-document}

```bash
check-opencloud-scanner scan opencloud.example.com
check-opencloud-scanner scan --compact opencloud.example.com > result.json
check-opencloud-scanner scan cloud1.example.com cloud2.example.com | jq '.[].rating'
```

Der Befehl gibt das JSON-Dokument mit Bewertung, Begründung, Lebenszyklus, Prüfungen, TLS-Messungen und Sicherheitshinweisen aus. Die Schlüssel verwenden camelCase. Ein Host ergibt ein Objekt, mehrere Hosts ein Array in der angegebenen Reihenfolge. Es wird kein Nagios-Status daraus abgeleitet.

| Option | Funktion |
|:--|:--|
| `--compact` | JSON ohne Einrückung in einer Zeile ausgeben |
| `--scheme {https,http}` | Protokoll für den Verbindungsaufbau |
| `--port` | Port überschreiben |
| `--timeout` | Zeitlimit pro Anfrage in Sekunden |
| `--insecure` | TLS-Zertifikatsprüfung deaktivieren |
| `--ca-file` | PEM-CA-Bundle für interne Zertifikate |
| `--no-extra-checks` | Nur Produkt, Version und Header prüfen |
| `--no-debug-ports` | Debug-Port-Prüfungen überspringen |
| `--all-addresses` | Wesentliche Prüfungen auf allen aufgelösten Adressen wiederholen |
| `--concurrency` | Parallele Anfragen innerhalb eines Scans; Standard `1` |
| `--no-update-check` | Neueste OpenCloud-Version nicht abfragen |

Ausnahmen, Release-Kanal und Advisory-Quellen werden wie beim Plugin über Konfiguration oder Umgebung festgelegt.

Ein nicht scanbarer Host erhält den Eintrag `{"host": ..., "error": ...}`. Weitere Hosts werden trotzdem geprüft; der Befehl endet dann mit `1`:

```json
{
  "host": "opencloud.example.com",
  "error": "https://opencloud.example.com/status.php is unreachable"
}
```

Das Dokument eignet sich für [CI-Pipelines](../ci.md), [Prometheus](../prometheus.md) und den Vergleich mit `diff`. Das [Bibliotheks-README](../../opencloud_local_scan/README.md) beschreibt die Felder.

## `diff`: gespeicherte Ergebnisse vergleichen {#diff-what-changed-between-two-saved-results}

```bash
check-opencloud-scanner scan opencloud.example.com > before.json
# ... change something on the instance ...
check-opencloud-scanner scan opencloud.example.com > after.json
check-opencloud-scanner diff before.json after.json
```

```text
opencloud.example.com: 2026-09-15 17:42:21.524291 -> 2026-09-15 17:42:22.737103
New since last run (15): check:debugEndpoint:/config, check:debugEndpoint:/debug/pprof/, check:debugEndpoint:/metrics, check:demoUsersDisabled, check:directoryListing (+10 more)
Security check: + debugEndpoint:/config
Security check: + demoUsersDisabled
...
Hardening: + Content-Security-Policy
...
Rating: A+ (5) -> D (2)
```

Der Befehl liest zwei Dateien und führt keinen Scan aus. `+` kennzeichnet neue, `-` behobene und `~` weiterhin offene Befunde mit geändertem Schweregrad. Er zeigt außerdem Änderungen an Bewertung, Version und Supportzeitraum. Für einen automatisch gespeicherten Vergleich mit dem letzten Lauf verwende stattdessen eine [Baseline](../baseline.md).

| Option | Funktion |
|:--|:--|
| `--format text` | Lesbare Textzeilen; Standard |
| `--format markdown` | Markdown-Tabelle für Tickets oder Kommentare |
| `--format side-by-side` | Beide Scans als zwei Spalten, ein Befund je Zeile |
| `--format json` | Strukturierter Vergleich wie im Plugin-Webhook |
| `--format slack` | Slack-Block-Kit-JSON |
| `--category NAME` | Nur einen Bereich zeigen; mehrfach angebbar |
| `--all-findings` | Alle gemessenen Befunde auflisten, nicht nur die veränderten |
| `--exit-zero` | Erfolgreiche Vergleiche unabhängig von Verschlechterungen mit `0` beenden |
| `--allow-different-hosts` | Ergebnisse unterschiedlicher Instanzen vergleichen |

Bei einer Verschlechterung im zweiten Ergebnis ist der Exitcode `1`, andernfalls `0`. `--exit-zero` unterdrückt diesen Fehlerstatus für Vergleiche.

Exitcode `2` bedeutet, dass kein Vergleich möglich ist:

- Die Dateien stammen von unterschiedlichen Instanzen und `--allow-different-hosts` wurde nicht gesetzt.
- Eine Datei ist kein verwertbares Ergebnis von `scan`, etwa weil die Bewertung fehlt oder sie nur einen Scanfehler enthält.

### Schweregrad, Befund für Befund {#severity-finding-by-finding}

Jeder Vergleich endet mit einer Zählung der fehlgeschlagenen Befunde nach Schweregrad:

```text
~ exposed:/config/opencloud.yaml [exposure]: severity high -> critical
Failing by severity: critical 0 -> 1, high 1 -> 1, medium 0 -> 1, low 1 -> 0
```

Die `~`-Zeile zeigt einen geänderten Schweregrad bei einem weiterhin offenen
Befund. Bei einem Wechsel von `high` zu `critical` bleibt die Kennung in
beiden Listen fehlgeschlagener Prüfungen enthalten. Der Mengenvergleich der
[Baseline](../baseline.md) erkennt daher keinen neuen Befund; die strengere
Bewertungsobergrenze kann jedoch die Note verschlechtern. Der Vergleich liest
die Schweregrade aus den gespeicherten Ergebnissen. Spätere Änderungen am
Katalog verändern diese historischen Werte nicht.

Ein per Waiver ausgenommener Befund wird hier mitgezählt und als `waived` dargestellt, denn ein Waiver ist die Entscheidung, nicht alarmiert zu werden, und keine Aussage darüber, dass der Befund weg ist.

### Nebeneinander {#side-by-side}

```bash
check-opencloud-scanner diff before.json after.json --format side-by-side
```

```text
opencloud.example.com
Rating: A+ (5) -> C (3)
Lifecycle: EOL: False -> True
Version: 3.4.0 -> 3.3.0

Finding                           2026-09-15T17:42:21+00:00  2026-09-22T09:03:11+00:00
--------------------------------  -------------------------  -------------------------
+ CVE-2026-0001                   not listed                 FAIL high
+ cspWithoutUnsafeInline          ok                         FAIL medium
~ exposed:/config/opencloud.yaml  FAIL high                  FAIL critical
- Referrer-Policy                 FAIL low                   ok
```

Jede Zeile zeigt den Befund in beiden Scans. Mit `--all-findings` erscheinen
auch unveränderte Befunde.

`not measured` bedeutet, dass für die Prüfung kein Messwert vorliegt
([ADR 0064](https://github.com/sowoi/check-opencloud-security/blob/main/adr/0064-a-scan-records-what-it-did-not-measure.md)).
`not listed` bedeutet, dass der Sicherheitshinweis im Ergebnis nicht aufgeführt
ist. Keiner dieser Zustände wird als bestandene Prüfung gewertet.

### Ein Bereich nach dem anderen {#one-area-at-a-time}

`--category` schränkt den Vergleich ein und nimmt einen Wert aus einem von zwei Namensräumen:

- **eine Befundkategorie** - `cookies`, `authentication`, `sharing`, `exposure`, `embedding`, `lifecycle`, `proxy`, `headers`, `transport`, `advisory` - behält nur die Befunde zu diesem Bereich der Instanz.
- **eine Änderungskategorie** - `instance`, `referenceData`, `scanner`, `policy`, `unknown` - behält nur die Erklärung, *warum* sich die beiden Scans unterscheiden. Siehe [Referenzdaten](reference-data.md) dazu, warum sich eine Note ändern kann, ohne dass sich die Instanz verändert hat.

```bash
check-opencloud-scanner diff before.json after.json --category transport
check-opencloud-scanner diff before.json after.json --category instance
```

Jeder Namensraum wird nur gefiltert, wenn du einen Wert dafür angibst: `--category transport` lässt die Erklärung unangetastet, `--category instance` die Befunde. Du kannst die Option mehrfach angeben. Ein unbekannter Wert führt zu Exitcode `2`. So entsteht bei einem Tippfehler kein leerer Vergleich, der fälschlich den Eindruck erweckt, es habe sich nichts geändert.

Eine gefilterte Erklärung lässt die `[limitation]`-Zeilen weg, weil diese den gesamten Vergleich einschränken und nicht eine einzelne Kategorie davon.

## `fleet`: Übersicht aus gespeicherten Ergebnissen {#fleet-a-dashboard-from-saved-results}

```bash
today="/var/lib/opencloud-reports/$(date +%F)"
mkdir -p "$today"
for host in cloud1.example.com cloud2.example.com cloud3.example.com; do
  check-opencloud-scanner scan "$host" > "$today/$host.json"
done
check-opencloud-scanner fleet /var/lib/opencloud-reports
check-opencloud-scanner fleet /var/lib/opencloud-reports --format html > fleet.html
```

`fleet` liest Ergebnisdokumente von `scan` – einzelne Dateien oder Verzeichnisse, die rekursiv nach `*.json` durchsucht werden – und fasst den **neuesten Bericht jedes Hosts** zusammen. Es scannt nichts und speichert nichts. Wie du die Berichte sammelst, per Cronjob, CI-Artefakt oder gemeinsamem Verzeichnis, bleibt dir überlassen.

| Abschnitt | Inhalt |
|:--|:--|
| Hosts | Eine Zeile pro Host: Version, Bewertung, Release-Linie, offene und ausgenommene Befunde, Abdeckungslücken und Alter des Berichts |
| Unsupported releases | Releases ohne Support, Releases, deren Support innerhalb des Zeitfensters endet, und Versionen, die der Zeitplan nicht kennt |
| Waiver deadlines | Befristete Ausnahmen, nach deren Ablauf eine fehlgeschlagene Prüfung innerhalb des Zeitfensters wieder alarmiert – oder schon alarmiert |
| Common findings | Die fehlgeschlagenen Befunde, die die meisten Hosts teilen, schwerste zuerst |
| Missing coverage | Erwartete Hosts ohne Bericht, Hosts mit fehlgeschlagenem letzten Scan, veraltete Berichte und Berichte ohne Abdeckungsblock |
| Checks not evaluated | Prüfungen, die die Scans übersprungen oder nicht entscheiden konnten, und auf wie vielen Hosts |

Ein Bericht belegt den Tag, an dem er entstand. Zwei Dinge werden deshalb gegen **heute** neu bewertet:

- **Das Release.** Die gespeicherte Version wird erneut im Release-Zeitplan dieser Installation eingeordnet – dem mitgelieferten oder dem in der Konfiguration genannten, wie beim Plugin. Eine Linie, deren Support nach dem Bericht endete, erscheint mit dem Hinweis `since the scan`. End of Life ist endgültig; ein Bericht, der es schon meldete, wird immer aufgeführt.
- **Die Frist einer Ausnahme.** Eine im Bericht aktive Ausnahme kann inzwischen abgelaufen sein. Aufgeführt wird nur eine Frist, nach der eine Prüfung wirklich wieder alarmiert – nach derselben Regel wie `--waiver-warning` des Plugins.

Häufige Befunde lassen weg, was niemand ändern kann: Flags, die OpenCloud fest vorgibt, und Header, die kein OpenCloud sendet. Ausgenommene Befunde werden mitgezählt; die Spalte `Waived` zeigt, auf wie vielen Hosts.

| Option | Funktion |
|:--|:--|
| `--format text` | Ausgerichtete Tabellen; Standard |
| `--format markdown` | Markdown-Tabellen für ein Ticket oder ein Wiki |
| `--format html` | Eine eigenständige Seite ohne Skripte, Schriften oder externe Abrufe, mit hellem und dunklem Modus |
| `--format json` | Die strukturierte Zusammenfassung in camelCase wie das Ergebnisdokument |
| `--window DAYS` | Ausnahmen und Support-Zeiträume zeigen, die innerhalb von `DAYS` Tagen enden; Standard `30` |
| `--stale-after DAYS` | Einen Host als nicht abgedeckt zählen, wenn sein neuester Bericht älter ist; Standard `7`, `0` schaltet das ab |
| `--top N` | Die `N` häufigsten Befunde auflisten; Standard `10`, `0` listet alle |
| `--expect HOST` | Ein Host, für den ein Bericht vorliegen sollte; mehrfach oder kommagetrennt angebbar |
| `--inventory FILE` | Erwartete Hosts aus einer Datei, einer pro Zeile, `#` leitet einen Kommentar ein |

Hosts werden über Name und Port zugeordnet: `https://opencloud.example.com/` und `opencloud.example.com` sind derselbe Host, `opencloud.example.com:9200` ist ein anderer. Gib den Port bei `--expect` an, wenn die Instanz auf einem eigenen Port gescannt wird.

Der Exitcode ist `0`, sobald eine Zusammenfassung ausgegeben wurde, egal wie schlecht die Flotte aussieht. `2` bedeutet, dass kein Ergebnisdokument gefunden und kein Host erwartet wurde. Eine Datei, die kein Ergebnisdokument ist, ist kein Fehler; sie erscheint unter *Files skipped*.

## `explain`: Befunde erklären {#explain-what-a-finding-means-and-how-to-fix-it}

```bash
check-opencloud-scanner explain basicAuthDisabled
```

```text
basicAuthDisabled: HTTP Basic authentication is enabled
    The instance answers with a 'WWW-Authenticate: Basic' challenge, so usernames and passwords can be replayed on every request without going through the identity provider, ...
    Setting: PROXY_ENABLE_BASIC_AUTH
    Fix: Set PROXY_ENABLE_BASIC_AUTH=false (the default) if nothing needs it. ...
    Docs: https://docs.opencloud.eu/docs/dev/server/services/proxy/environment-variables
```

Der Befehl sucht Kennungen im mitgelieferten Katalog und zeigt dieselben Erklärungen wie `--debug` und die Webanwendung. Er liest keine Konfiguration, benötigt kein Netzwerk und führt keinen Scan aus.

```bash
check-opencloud-scanner explain cspWithoutUnsafeInline Referrer-Policy   # several at once
check-opencloud-scanner explain exposed:/config/opencloud.yaml          # parameterised ids too
check-opencloud-scanner explain --list                                  # every identifier, one per line
check-opencloud-scanner explain --list --category cookies               # one category
check-opencloud-scanner explain --format json cookieSecure              # for a script
check-opencloud-scanner explain                                         # the whole catalogue
```

| Option | Funktion |
|:--|:--|
| `--list` | Nur Kennungen ausgeben |
| `--category` | Auf `cookies`, `authentication`, `sharing`, `exposure`, `embedding`, `lifecycle`, `proxy`, `headers` oder `transport` beschränken |
| `--format {text,json}` | JSON mit `id`, `category`, `title`, `meaning`, `remediation`, `reference`, `setting` und `actionable` ausgeben |

Bei einer unbekannten Kennung endet der Befehl mit `1` und schlägt ähnliche Kennungen vor:

```text
ERROR check_opencloud.cli: No catalogue entry for 'cookieSecur'. Did you mean: cookieSecure, cookieSameSite, cookiePrefix? Run `explain --list` for every identifier this build knows.
```

Die Kennungen entsprechen den Werten in der Alarmzeile, in `extraChecks[].id`, in `hardenings` und in den Ausnahmelisten. Ausführlichere Erklärungen stehen unter [Härtungsmaßnahmen](../hardening.md) und [Prüfumfang](../scanner-checks.md).

## `review-waivers`: Ausnahmen überprüfen {#review-waivers-waivers-that-need-attention}

```bash
check-opencloud-scanner -c /etc/check-opencloud-security/config.yml review-waivers
```

Der Befehl liest die Ausnahmen, die auch das Plugin verwenden würde - `scanner.ignore_hardenings` und `scanner.temporary_waivers` aus der Konfigurationsdatei oder die passenden `COS_`-Umgebungsvariablen -, und listet jede auf, um die du dich kümmern solltest, jeweils mit einem Vorschlag zum Aufräumen. **Er ändert die Konfiguration nie.** Ob ein Befund weiter akzeptabel ist, entscheidest du selbst.

| Art | Bedeutung |
|:--|:--|
| Expired | Eine befristete Ausnahme, deren Frist abgelaufen ist. Die Ausgabe sagt, ob die Prüfung wieder alarmiert oder eine breitere Ausnahme sie weiter verdeckt. |
| Expiring soon | Eine befristete Ausnahme, die innerhalb von `--expiring-within` Tagen abläuft - `--waiver-warning` des Plugins für alle Einträge auf einmal. |
| Unused | Trifft auf keine Prüfung, die im `--result`-Dokument fehlschlägt. Ohne `--result`: trifft auf keine Kennung, die dieser Build kennt, meist ein Tippfehler. Eine Ausnahme für ein von OpenCloud fest eingestelltes Flag zählt ebenfalls, weil dieses nie alarmiert. |
| Overlapping | Eine andere aktive Ausnahme deckt sie schon ab: ein Duplikat, ein engeres Muster unter einem breiteren oder - mit `--result` - zwei Muster für dieselbe fehlschlagende Prüfung. Eine befristete Ausnahme unter einer dauerhaften fällt auf, weil ihre Frist nichts bewirkt. |
| Permanent | Ein Muster ohne Begründung und ohne Frist, mit einem `--waive-until`-Eintrag zum Übernehmen. |

```bash
check-opencloud-scanner scan opencloud.example.com > result.json
check-opencloud-scanner review-waivers --result result.json          # tell used from unused
check-opencloud-scanner review-waivers --at 2026-12-01T00:00:00Z     # what will have expired by then
check-opencloud-scanner review-waivers --format json --exit-zero     # for a script
```

| Option | Funktion |
|:--|:--|
| `--result FILE` | Ergebnisdokument von `scan`, um genutzte von ungenutzten Ausnahmen zu unterscheiden; nennt außerdem den nächsten Ablauf, nach dem eine Prüfung alarmiert |
| `--ignore-hardening`, `--waive-until` | Diese Werte statt der konfigurierten prüfen, so wie die gleichnamigen Plugin-Optionen sie ersetzen |
| `--expiring-within DAYS` | Zeitfenster für *Expiring soon*. Standard: die Einstellung `waiver_warning`, sonst `14`; `0` schaltet den Abschnitt ab |
| `--at TIMESTAMP` | Zu einem anderen Zeitpunkt prüfen; braucht wie eine Frist eine Zeitzone |
| `--format {text,json}` | JSON mit `counts` je Art und einem Eintrag je Befund mit `kind`, `pattern`, `reason`, `expiresAt`, `detail`, `suggestion` und `related` |
| `--exit-zero` | Immer mit `0` enden |

Eine Ausnahme kann unter mehreren Arten erscheinen, ein falsch geschriebenes dauerhaftes Muster etwa als *Unused* und *Permanent*.

## `refresh-data`: Referenzdaten aktualisieren {#refresh-data-update-the-release-schedule-and-advisories}

```bash
check-opencloud-scanner refresh-data --output-dir /var/lib/check-opencloud-security
```

Der Befehl lädt Release-Zeitplan und Schwachstellendatenbank aus dem Projekt-Repository, prüft sie und schreibt sie nach `--output-dir`. Die Signaturprüfung benötigt das Extra `signing`; nicht prüfbare Signaturen führen zu einer Warnung, ungültige Signaturen zum Abbruch. Bei Erfolg werden beide Pfade ausgegeben und der Exitcode ist `0`. Ein abgelehnter Refresh schreibt nichts und endet mit `1`.

| Option | Standard | Funktion |
|:--|:--|:--|
| `--output-dir` | `~/.cache/check-opencloud-security` | Zielverzeichnis |
| `--timeout` | `30` | Zeitlimit pro Anfrage in Sekunden |
| `--schedule-url` | keine | Alternative Lebenszyklusseite ohne Signaturprüfung |
| `--advisory-url` | keine | Alternativer OSV-Endpunkt ohne Signaturprüfung |

Trage die Dateien anschließend in die Konfiguration ein und prüfe ihre Lesbarkeit unter dem Benutzer des Checks. Eine unlesbare eigene Zeitplandatei deaktiviert die End-of-Life-Prüfung. Details stehen unter [Referenzdaten aktualisieren](../reference-data.md).

## `serve`: HTTP-Dienst betreiben {#serve-the-scan-service}

```bash
check-opencloud-scanner serve
check-opencloud-scanner serve --listen 0.0.0.0 --token "$(cat /run/secrets/scanner_token)"
```

Der HTTP-Dienst stellt mehreren Verbrauchern ein zwischengespeichertes Ergebnis pro Instanz bereit.

| Option | Standard | Einstellung |
|:--|:--|:--|
| `--listen` | `127.0.0.1` | `service.listen` / `COS_SERVICE_LISTEN` |
| `--port` | `8811` | `service.port` / `COS_SERVICE_PORT` |
| `--cache-ttl` | `900` Sekunden | `service.cache_ttl` / `COS_SERVICE_CACHE_TTL` |
| `--token` | keines | `service.token` / `COS_SERVICE_TOKEN` |
| `--concurrency` | `1` | Parallele Anfragen innerhalb eines Scans |
| `--insecure` | aus | Zertifikatsprüfung der gescannten Instanzen deaktivieren |

Außerhalb von Loopback verlangt der Dienst ein Token. Fehlt es, erscheint `UNKNOWN: ...` auf stderr und der Prozess endet mit `3`. Die Endpunkte stehen im [Haupt-README](../../README.md#running-the-scanner-as-a-service), Containerbeispiele unter [Scan-Dienst](../scan-service.md).

Das Token muss dann mindestens 32 Zeichen lang sein und darf nicht der Platzhalter aus `secrets/scanner_token.example` sein: Nichts begrenzt, wie oft es geraten werden kann, also schützt es allein seine Länge. `openssl rand -hex 32` erzeugt dir eins.

Die [öffentliche Webanwendung](../webapp.md) mit Browseroberfläche und Warteschlange ist ein separater Dienst.

## `configure`: Konfigurationsdatei erstellen {#configure-write-a-configuration-file}

```bash
check-opencloud-scanner configure
check-opencloud-scanner -c /etc/check-opencloud-security/.env.json configure
```

Der Assistent erklärt die Einstellungen und speichert sie als JSON mit Dateirechten nur für den Eigentümer. Er bietet `./.env.json`, `~/.config/check-opencloud-security/.env.json` und `/etc/check-opencloud-security/.env.json` an; über `-c` kannst du einen anderen Pfad wählen. Es ist derselbe Assistent wie bei `check-opencloud-security --configure`.

| Option | Funktion |
|:--|:--|
| `--all` | Optionale Einstellungen ohne vorherige Auswahl durchgehen |
| `--force` | Vorhandene Datei ohne Rückfrage ersetzen |
| `--no-test-scan` | Vor dem Speichern keinen Testscan anbieten |
| `--export-monitoring` | Zusätzlich die geplante Prüfung schreiben: `icinga`, `systemd`, `both` oder `none` |

Danach bietet er an, auch die geplante Prüfung zu schreiben, neben die gerade gespeicherte Konfiguration:

```text
Also write a monitoring configuration (Icinga service, systemd timer)? [y/N]
```

`--export-monitoring` beantwortet diese Frage vorab und eignet sich damit für die automatische Bereitstellung. Die erzeugten Dateien übernehmen die Schwellenwerte, den Release-Kanal und die übrigen gewählten Einstellungen:

```bash
check-opencloud-scanner configure --export-monitoring both
```

| Datei | Was sie ist |
|:--|:--|
| `opencloud-security-<host>.conf` | Ein Icinga-2-`Service`-Objekt. Es braucht zusätzlich das `CheckCommand` aus [`contrib/icinga2/`](../../contrib/icinga2/check_opencloud_security.conf) - der Service setzt Variablen, das Kommando macht Flags daraus |
| `check-opencloud-security.service` | Eine `oneshot`-Unit mit denselben Härtungsdirektiven wie die in [`contrib/systemd/`](../../contrib/systemd/check-opencloud-security.service) |
| `check-opencloud-security.timer` | `OnCalendar=daily`, mit zufälliger Verzögerung, damit viele Hosts hinter einer Adresse nicht in derselben Sekunde das Ratelimit des Release-Feeds treffen |
| `check-opencloud-security.env` | Die `COS_`-Variablen für die Unit, nur für den Eigentümer lesbar geschrieben |

**Der Assistent installiert die Dateien nicht.** Er speichert sie neben der Konfiguration und zeigt die Installationsbefehle an. Prüfe die Dateien, bevor du sie nach `/etc` kopierst.

**Zugangsdaten bleiben in der geschützten Konfigurationsdatei.** Eine Webhook-URL oder ein Release-Token wird nicht in das Icinga-Objekt oder die Unit-Datei übernommen, da diese Dateien auch für andere Benutzer lesbar sein können. Stattdessen verweisen `vars.opencloud_config` und `COS_CONFIG_FILE` auf die nur für den Eigentümer lesbare Konfigurationsdatei. Die Ausgabe nennt die dort verbleibenden Einstellungen, damit du ihre Übernahme prüfen kannst.

## Exitcodes {#exit-codes}

Die Scanner-CLI verwendet eigene Exitcodes. Ein erfolgreich gescannter Host mit Note F führt bei `scan` weiterhin zu `0`; die Nagios-Bewertung übernimmt das Plugin.

| Unterbefehl | `0` | `1` | `2` | `3` |
|:--|:--|:--|:--|:--|
| `scan` | Alle Hosts gescannt | Mindestens ein Host nicht scanbar | Ungültige Konfiguration | – |
| `diff` | Keine Verschlechterung | Zweites Ergebnis schlechter | Dateien nicht vergleichbar | – |
| `fleet` | Zusammenfassung ausgegeben | – | Kein Ergebnisdokument gefunden oder Inventar nicht lesbar | – |
| `explain` | Ausgabe erstellt | Unbekannte Kennung oder leere Kategorie | – | – |
| `review-waivers` | Nichts aufzuräumen | Mindestens eine Ausnahme gelistet | Ungültige Ausnahme, Zeitangabe oder `--result`-Datei | – |
| `refresh-data` | Beide Dateien geschrieben | Nichts geschrieben; siehe stderr | – | – |
| `serve` | Regulär beendet | – | Ungültige Konfiguration | Start verweigert, etwa ohne Token außerhalb von Loopback |

Ungültige Kommandozeilenargumente führen bei allen Unterbefehlen zu Exitcode `2`.

## Marken und Unabhängigkeit

Dies ist ein unabhängiges Community-Projekt. Es ist nicht mit OpenCloud GmbH
verbunden und wird von ihr nicht unterstützt. OpenCloud und zugehörige Marken
gehören ihren jeweiligen Inhabern und benennen hier die geprüfte Software.
