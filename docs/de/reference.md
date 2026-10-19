# CLI-Referenz des OpenCloud Security Scanners

## Schnellstart {#quick-start}

Installiere das Plugin und prüfe deine Instanz:

```shell
pipx install check-opencloud-security     # or: uv tool install / pip install
check-opencloud-security --host opencloud.example.com
```

Eine mit `opencloud init` eingerichtete Instanz verwendet auf Port 9200 zunächst
ein selbst signiertes Zertifikat. Mit `--insecure` bleibt die fehlende
Vertrauenskette sichtbar, beeinflusst aber die Bewertung nicht:

```shell
check-opencloud-security --host opencloud.example.com:9200 --insecure
```

Für den dauerhaften Einsatz findest du unten Installations- und Monitoring-Anleitungen.

## Funktionen {#features}

- Direkte Prüfung der Instanz im Plugin-Prozess, auch mit internen Hostnamen,
  IP-Adressen und eigenen Ports.
- Release-Kanal, ausstehende Updates und Supportende; Offline-Betrieb mit
  `pinned` oder `bundled`.
- Prüfung von TLS, Sicherheitsheadern, Cookies, Anmeldung, öffentlichen
  Konfigurationsdateien, Debug-Ports und weiteren OpenCloud-Einstellungen.
- Schutzmaßnahmen anhand der tatsächlich veröffentlichten Konfiguration.
- YAML/JSON, Umgebungsvariablen und Secret-Provider zur Konfiguration.
- Nagios-/Icinga-Zustände, Metriken und einstellbare Alarmschwellen.
- JSON, SARIF, JUnit, Checkmk, Prometheus und OTLP für andere Werkzeuge.
- Optionale Webhooks, Wiederholungen bei Netzwerkfehlern und mehrere Hosts pro Lauf.
- Installation über pipx, uv, pip, Systempaket oder Docker.

## Voraussetzungen {#prerequisites}

Du benötigst Python ab 3.11 oder Docker. `requests` und `PyYAML` werden bei der
Python-Installation automatisch mitinstalliert. Der Monitoring-Host muss die
OpenCloud-Instanz erreichen können; diese muss dafür nicht öffentlich sein.

## Installation {#installation}

Die [Installationsanleitung](../installation.md) behandelt auch Updates,
Shell-Vervollständigung, eigene Images und Icinga-/Nagios-Objekte.

```shell
pipx install check-opencloud-security          # or: uv tool install / pip install
check-opencloud-security --host opencloud.example.com
```

Für Monitoring-Hosts stehen außerdem `.deb`- und `.rpm`-Pakete bereit:

```shell
sudo apt install ./check-opencloud-security_<version>_all.deb       # Debian, Ubuntu
sudo dnf install ./check-opencloud-security-<version>-1.noarch.rpm  # RHEL, Fedora
```

Die Pakete installieren das Plugin unter `/usr/lib/nagios/plugins/`, ohne eine
Monitoring-Konfiguration zu aktivieren. Alternativ enthält das Docker-Image
beide Kommandozeilenprogramme:

```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com
```

Da das Image standardmäßig den Webdienst startet, wähle das Plugin mit
`--entrypoint`. Weitere Varianten stehen unter [Scannen mit Docker](../docker-oneliner.md).

| Einrichtung | Anleitung |
|:--|:--|
| pipx, uv, pip und Updates | [Installation](../installation.md) |
| `.deb` und `.rpm` | [Systempakete](../installation.md#debian-ubuntu-rhel-fedora-deb-and-rpm) |
| Shell-Vervollständigung | [Shell completion](../installation.md#shell-completion) |
| Docker | [Containerbetrieb](../installation.md#docker) |
| Icinga2 und Nagios | [Monitoring-Objekte](../installation.md#icinga2--nagios) |
| Icinga Director | [Director-Anleitung](../icinga-director.md) |
| Ansible, systemd, cron, Kubernetes | [Leitfäden](../README.md#deploying-it) |

Releases enthalten eine CycloneDX-SBOM und eine Sigstore-Attestierung; siehe
[Downloads prüfen](../../SECURITY.md#verifying-what-you-downloaded).
Halte auch das Plugin aktuell: Sein Paket enthält Release-Zeitplan und
Sicherheitsmeldungen.

## Kommandozeile {#cli-usage}

`check-opencloud-security --help` zeigt die verfügbaren Optionen.

### Aufruf {#command}

```shell
check-opencloud-security --host <Hostname> --check-hardening
```

### Optionen {#options}

Die [CLI-Referenz](../cli-reference.md) nennt alle Optionen, Standardwerte und
zugehörigen Umgebungsvariablen. Häufig verwendet werden:

| Option | Zweck |
|:--|:--|
| `-H`, `--host` | Hostname, IP oder URL, optional mit Port; mehrere Ziele mit Komma trennen |
| `-d`, `--debug` | Bewertung und Befunde ausführlich erklären |
| `--check-hardening` | Fehlende Schutzmaßnahmen und Sicherheitsheader melden |
| `-w`, `--warning` / `-c`, `--critical` | Inklusive Alarmschwellen von 0 bis 5 |
| `--format` | `nagios`, `prometheus`, `otlp`, `checkmk`, `json`, `sarif`, `junit` |
| `--ignore-hardening` | Befund anhand seiner Kennung ausnehmen |
| `--baseline` / `--warn-on-new` | Mit vorherigem Lauf vergleichen und nur bei Verschlechterung alarmieren |
| `--verify-remediation` | Nach einer Korrektur nur die genannten Befunde neu messen statt eines vollen Scans |

Es gilt: **Kommandozeile > Umgebungsvariable > Konfigurationsdatei > Standard**.

## Eine Korrektur prüfen {#verifying-a-fix}

Wenn du eine einzelne Einstellung geändert hast - einen Header im Reverse
Proxy, einen Pfad, den er nicht mehr ausliefern soll -, musst du nicht auf
einen vollen Scan warten. `--verify-remediation` nimmt die Befund-IDs aus der
normalen Ausgabe und führt nur die Proben aus, die sie messen:

```shell
check-opencloud-security --host opencloud.example.com \
  --verify-remediation Strict-Transport-Security,corsOriginRestricted
```

Die Option ist wiederholbar und nimmt kommaseparierte IDs. Eine Familie wie
`exposed`, `authentication`, `debugEndpoint` oder `versionDisclosure` prüft
alle ihre Mitglieder. `OK` heißt, jede ID besteht jetzt; `WARNING` bzw.
`CRITICAL` (bei hoher oder kritischer Schwere), dass eine noch scheitert;
`UNKNOWN`, dass nur ein voller Scan sie klären kann (`eol`,
`vulnerability:...`, `httpsAvailable`, Adressparität). Es gibt keine
Bewertung, keine Baseline, keinen Webhook und keine Ausnahmen (Waivers).
`--format json` gibt das Messdokument aus.

## Mehrere Hosts prüfen {#checking-multiple-hosts}

`--host` und `COS_HOST` akzeptieren eine kommaseparierte Liste:

```shell
check-opencloud-security --host opencloud1.example.com,opencloud2.example.com
```

Standardmäßig laufen bis zu fünf Hosts parallel. `--concurrency` beziehungsweise
`COS_CONCURRENCY` begrenzt die Host-Worker auf einen Wert bis 32. Ein einzelner
Host benötigt keinen solchen Worker-Pool. Die Ausgabe enthält zunächst eine
Zusammenfassung, danach je Host einen Block in Eingabereihenfolge. Der Exitcode
folgt dem höchsten Zustand: `CRITICAL` vor `WARNING`, `UNKNOWN` und `OK`.

Leerzeichen um Einträge und leere Einträge werden ignoriert. Hostnamen, IPv4,
eingeklammerte IPv6-Adressen und vollständige URLs sind möglich. Bei
unterschiedlichen Einstellungen je Instanz empfehlen sich getrennte
[Konfigurationsdateien](../many-instances.md).

## Eine Flotte in einer Tabelle {#reading-a-fleet-in-one-table}

Die Ergebnisblöcke je Host sind für ein Monitoring-System geschrieben, und ein
Dutzend davon liest sich mühsam. `--format summary` gibt denselben Lauf
stattdessen als eine ausgerichtete Zeile je Host aus:

```shell
check-opencloud-security \
  --host opencloud1.example.com,opencloud2.example.com \
  --format summary
```

```text
HOST                    GRADE  VERSION  EOL   VULNS  NEW
opencloud1.example.com  A+     7.2.4    no    0      -
opencloud2.example.com  F      6.9.1    YES   3      -

Checked 2 host(s): overall CRITICAL (1 CRITICAL, 1 OK)
```

Die Spalten zeigen die Note, die gemessene Version, den Supportstatus, die
Anzahl zutreffender Sicherheitsmeldungen und neue Befunde seit der
Referenzaufnahme. Die Zeilen folgen der Reihenfolge der angegebenen Hosts. Die
letzte Zeile enthält dieselbe Zusammenfassung wie der Beginn der Nagios-Ausgabe.
Der Exitcode entspricht weiterhin dem schlechtesten Status aller geprüften
Hosts. Das Format eignet sich daher auch für einen Cronjob, der die Ausgabe
versendet.

`EOL` steht auf `YES` nach dem Support-Ende, auf `soon` innerhalb des Fensters
von [`--eol-warning-days`](#options) und sonst auf `no`. `NEW` braucht
[`--baseline`](#options): ohne Referenz steht dort `-`, denn "nichts Neues" und
"nicht feststellbar" sind verschiedene Antworten. Mit Referenz steht dort `new`
im Lauf, der die Referenz aufnimmt, und danach `+n` für Befunde, die vorher
nicht da waren. Ein Host, dessen Scan fehlgeschlagen ist, hat keine Note; in
seiner Spalte `GRADE` steht stattdessen der Nagios-Status (`UNKNOWN`).

Dieses Format ist für Menschen. Für Maschinen gibt es
[`json`, `sarif` oder `junit`](#machine-readable-output-for-ci-jsonsarifjunit)
mit denselben Befunden in auswertbarer Form.

## CI-Richtlinienmodus {#ci-policy-mode}

`-w`/`-c` und `--profile` beurteilen eine Instanz anhand ihrer **Note**, also
anhand einer einzigen Zahl, die die Messergebnisse zusammenfasst. Für das
Monitoring ist das nützlich. Als Freigabekriterium für eine Bereitstellung
reicht die Note aber nicht immer aus: Wenn dein Team erzwungenes HTTPS und keine Demo-Konten verlangt,
lässt sich das nicht als Note ausdrücken.

`--policy` verweist auf eine Datei, die das ausdrücklich festhält:

```yaml
minimum_rating: 4
required_hardenings:
  - httpsEnforced
  - corsOriginRestricted
forbidden:
  - demoUsersDisabled
```

```shell
check-opencloud-security --host opencloud.example.com --policy policy.yml
```

```text
CRITICAL: 2 policy violation(s) - required hardening 'httpsEnforced' is not in place (+1 more)
OpenCloud 7.2.4 on opencloud.example.com, rating: A, last scanned: ...
Policy violations (2):
  - required hardening 'httpsEnforced' is not in place
  - forbidden finding 'demoUsersDisabled' is present
```

Alle drei Schlüssel sind optional: `minimum_rating` ist eine Untergrenze für
die Note von `0` (F) bis `5` (A+), `required_hardenings` nennt Maßnahmen, die
vorhanden sein müssen, und `forbidden` nennt Befund-IDs, die nicht auftreten
dürfen - eine fehlende Härtung, eine fehlgeschlagene Prüfung oder eine
Schwachstellen-ID.

Die Bezeichner sind dieselben, die der Scan selbst meldet; `--format json`
listet sie für eine Instanz auf und `--debug` erklärt jeden einzelnen. `.json`
wird als JSON gelesen, alles andere als YAML, und
[`config/policy.example.yml`](../../config/policy.example.yml) ist ein
kommentierter Ausgangspunkt.

Ein Verstoß setzt den Status auf **CRITICAL**. Eine Richtlinie kann den
Status verschlechtern, aber nicht verbessern. Erfüllt die Instanz alle
Anforderungen, bleibt der anhand von Schwellenwerten, Härtung, Lebenszyklus und
Referenzaufnahme ermittelte Status erhalten. In der Ausgabe steht
`Policy: every requirement met`. Webhook-Payload und `--format json` führen
dasselbe Urteil unter `policy`.

Zwei Regeln solltest du kennen, bevor du eine Richtlinie schreibst:

* **Ausnahmen setzen die Richtlinie nicht außer Kraft.** Mit
  `--ignore-hardening` und `--waive-until` akzeptierte Befunde bleiben für die
  Richtlinienprüfung relevant. Eine ausdrücklich verlangte Maßnahme muss
  weiterhin erfüllt sein.
* **Ungültige Regeln führen zu `UNKNOWN`.** Ein unbekannter Schlüssel, eine
  Note außerhalb von `0`-`5` oder eine unbekannte Maßnahme beenden den Lauf
  mit einer Begründung. So kann ein Tippfehler nicht unbemerkt eine Anforderung
  außer Kraft setzen.

## Prometheus und Kubernetes {#prometheus-kubernetes-integration}

`--format=prometheus` erzeugt eine einmalige Textausgabe. Der Exporter stellt
`/metrics` bereit und aktualisiert Ziele beim ersten Abruf sowie danach gemäß
`--scrape-interval`, standardmäßig alle 60 Sekunden:

```shell
check-opencloud-security --host opencloud.example.com --format=prometheus

check-opencloud-security --host opencloud.example.com \
  --prometheus-listen-port 9102
```

Er bindet standardmäßig an `127.0.0.1`. Für Container oder Kubernetes verwende bei Bedarf `--prometheus-listen-addr 0.0.0.0` und beschränke Port 9102 per
Firewall oder NetworkPolicy.

Die Metriken erfassen Bewertung, Schwachstellen, fehlende Schutzmaßnahmen,
fehlgeschlagene Zusatzprüfungen, verbleibenden Support, Updates, Laufzeit und
Scan-Erfolg. `host` bezeichnet das Ziel; die Bewertungsmetrik enthält außerdem
`domain`, `product` und `version`.

`--format=otlp` liefert dieselben Werte als OTLP/JSON für `/v1/metrics` eines
OpenTelemetry-Collectors:

```shell
check-opencloud-security --host opencloud.example.com --format=otlp \
  | curl -sf -X POST http://collector.example.com:4318/v1/metrics \
      -H 'Content-Type: application/json' --data-binary @-
```

Beide Metrikformate geben bei einem fehlgeschlagenen Scan
`opencloud_security_scrape_success 0` aus und enden mit Exitcode 0.
Für eine Überwachung über Exitcodes verwende `nagios`.
Die Leitfäden zu [Prometheus](../prometheus.md) und [Kubernetes](../kubernetes.md)
enthalten Alarmregeln, ServiceMonitor, OTLP-Beispiele und Helm-Chart.

## Maschinenlesbare Ausgabe für CI {#machine-readable-output-for-ci-jsonsarifjunit}

`json`, `sarif` und `junit` erzeugen jeweils ein gemeinsames Dokument für alle
Hosts. Diese drei Formate behalten die Nagios-Exitcodes `0` bis `3` bei.

- JSON: Array mit einem Ergebnis pro Host.
- SARIF 2.1.0: Befunde für Code-Scanning-Werkzeuge.
- JUnit XML: Eine Testsuite pro Host und ein Testfall pro Befund; der
  Bewertungsfall erscheint auch bei einem fehlerfreien Ergebnis.

```shell
check-opencloud-security --host opencloud.example.com --format sarif \
  > opencloud-security.sarif
```

Siehe [Ausgabeformate](../output-formats.md) und [CI-Anleitung](../ci.md).

## Checkmk {#checkmk}

Auf dem Checkmk-Server lässt sich das Plugin als aktiver Nagios-Check unter
**Setup → Services → Other services → Integrate Nagios plugins** einbinden.

Alternativ führe es als lokalen Check auf einem Agent-Host aus, der die
Instanz erreichen kann:

```shell
check-opencloud-security --host opencloud.example.com --format checkmk
```

```text
0 "OpenCloud_Security_opencloud.example.com" rating=5|vulnerabilities=0|… OK: Server is up to date…
```

[Das mitgelieferte Skript](../../contrib/checkmk/opencloud_security) verwendet diesen
Aufruf. Installiere es in einem Intervallverzeichnis wie `local/3600/`,
damit nicht jeder Agent-Abruf einen neuen Scan auslöst. Der Dienstname enthält
die geprüfte Instanz. Einzelheiten: [Checkmk](../checkmk.md).

## GitHub Action {#github-action}

[`action.yml`](../../action.yml) führt den Check als Workflow-Schritt aus. Der Runner
muss die Instanz erreichen können; für interne Ziele benötigst du einen
passend angebundenen eigenen Runner. Die Befunde gelten für dessen Netzwerksicht.

```yaml
name: OpenCloud security check

on:
  schedule:
    - cron: "0 6 * * *"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: sowoi/check-opencloud-security@v1.18.2
        with:
          target: opencloud.example.com
          # Raises GitHub's anonymous rate limit for the release feed. The
          # token the job already has is enough; it needs no scopes.
          releases-token: ${{ github.token }}
```

Wähle einen Release-Tag oder setze `version` ausdrücklich. Ein
Versions-Tag installiert das entsprechende Paket; bei Branch- oder
Commit-Referenzen ohne Versionsvorgabe wird das neueste Release installiert
und eine Warnung ausgegeben.

| Eingabe | Standard | Bedeutung |
|:--|:--|:--|
| `target` | erforderlich | Instanz als Hostname oder URL |
| `version` | Release-Tag | Zu installierende Plugin-Version |
| `format` | `json` | `json`, `sarif`, `junit`, `nagios` |
| `output-file` | `opencloud-security.json` | Zieldatei |
| `fail-on` | `warning` | `warning`, `critical`, `never` |
| `warning`, `critical` | Plugin-Standard | Bewertungsgrenzen |
| `check-hardening` | `true` | Schutzmaßnahmen berücksichtigen |
| `ignore-hardening` | leer | Ausgenommene Kennungen, kommasepariert |
| `release-track` | `auto` | `auto`, `rolling`, `production`, `lts` |
| `releases-token` | leer | Token für den Release-Feed |
| `summary` | `true` | Ergebnis in die Job-Zusammenfassung schreiben |
| `extra-args` | leer | Weitere Plugin-Argumente |

Standardmäßig schlägt der Schritt bei jedem Zustand außer OK fehl.
`fail-on: critical` toleriert WARNING, aber weder CRITICAL noch UNKNOWN.
`fail-on: never` überlässt die Entscheidung einem späteren Schritt.

Die Ausgaben `exit-code` und `result-file` stehen für alle Formate bereit.
Bei JSON kommen `status`, `rating`, `rating-label` und `message` hinzu.
Einstellungen werden als `COS_*`-Umgebungsvariablen übergeben, damit das Ziel
nicht in der protokollierten Kommandozeile steht. Weitere Beispiele: [CI](../ci.md).

## Umgebungsvariablen {#environment-variables}

Die Optionen besitzen Entsprechungen mit dem Präfix `COS_`; die
[CLI-Referenz](../cli-reference.md) nennt die Zuordnung. Ausdrückliche
Kommandozeilenargumente haben Vorrang.

```shell
export COS_HOST=opencloud.example.com
export COS_PROXY=http://proxy.example.com:3128
check-opencloud-security
```

Scans lesen weder `.netrc` noch `HTTP_PROXY`, `HTTPS_PROXY` oder die
CA-Bundle-Variablen von Requests. Setze einen Proxy über `--proxy`/
`COS_PROXY` und eine eigene CA über `--ca-file`/`COS_SCANNER_TLS_CA_FILE`.
Ein auf geprüfte Adressen beschränkter Webhook kann keinen auflösenden Proxy
verwenden; dafür ist die ausdrückliche Freigabe `--allow-private-webhooks` nötig.

Boolesche Variablen akzeptieren `1`, `true`, `yes` oder `on` ohne Beachtung der
Großschreibung. Andere Werte schalten die jeweilige Option aus.

## Der eingebaute Scanner {#the-built-in-scanner}

Das Plugin verwendet [`opencloud_local_scan`](../../opencloud_local_scan/README.md)
im eigenen Prozess. Es fragt keinen entfernten Dienst nach einer Bewertung.
Dadurch sind auch interne Ziele und eigene Ports erreichbar, sofern der
Monitoring-Host darauf zugreifen kann.

### Umfang der Prüfungen {#what-the-scanner-checks}

Grundlage sind `/status.php`, Capabilities, Header, OIDC-Discovery und öffentlich
erreichbare Pfade und Ports. Zusatzprüfungen untersuchen unter anderem TLS,
DNS, Cookies, CORS, TRACE, geschützte APIs, offengelegte Dateien, Office-Dienste
auf derselben Origin, Demo-Konten, Debug-Zugänge und iframe-Einbettung.

Fehlgeschlagene Zusatzprüfungen begrenzen die Note: kritisch auf `D`, hoch auf
`C`, mittel auf `A`, niedrig auf `A+`. `scanner.extra_checks_rating: false`
erfasst sie ohne Einfluss auf die Note; `--no-extra-checks` lässt sie aus.

Der [Prüfkatalog](../scanner-checks.md) erklärt jeden Befund, dessen Schweregrad
und nicht bewertete Beobachtungen. Die thematischen Leitfäden behandeln
[TLS](../tls.md), [CSP](../csp.md), [Cookies](../cookies.md),
[Anmeldung](../authentication.md), [Freigaben](../sharing.md),
[öffentliche Zugänge](../exposure.md), [Einbettung](../embedding.md) und
[Release-Unterstützung](../lifecycle.md).
Audit-Logs, Firewall, Anmelderichtlinien und Backups behandelt
[OpenCloud sicher betreiben](../secure-deployment.md).

### TLS und selbst signierte Zertifikate {#tls-and-self-signed-certificates}

Der Scanner versucht HTTPS mit Zertifikatsprüfung, anschließend HTTPS ohne
Verifikation und zuletzt HTTP. Fehlende Vertrauenswürdigkeit wird als
`tlsTrusted` gemeldet; reines HTTP ergibt den kritischen Befund `httpsAvailable`.

`--insecure` beginnt ohne Verifikation und nimmt die fehlende Vertrauenskette
aus der Bewertung. Andere Zertifikatsprüfungen bleiben bestehen. Für interne
Zertifizierungsstellen verwende möglichst ein eigenes CA-Bundle.

### Debug-Ports {#debug-ports}

Die Debug-Listener veröffentlichen unter anderem `/healthz`, `/readyz`,
`/metrics`, `/config` und `/debug/pprof`. Standardmäßig prüft der Scanner
9205, 9141, 9124, 9134 und 9239 mit je drei Sekunden Verbindungs-Timeout:

```yaml
scanner:
  check_debug_ports: true
  debug_ports: [9205, 9141]
  debug_port_timeout: 1
  concurrency: 8            # run the probes in parallel instead
```

`--no-debug-ports` schaltet diese Prüfung aus. Portzuordnung und Parallelität
sind unter [Debug-Ports](../scanner-checks.md#debug-ports) beschrieben.

### Alle aufgelösten Adressen {#every-resolved-address}

`--all-addresses` beziehungsweise `scanner.check_all_addresses` vergleicht
Version, Header, Schutzmaßnahmen und Demo-Konten an jeder aufgelösten Adresse:

```
addressParity (high): Differs from 198.51.100.1 - 198.51.100.4: version 7.1.0 (expected 7.2.3); headers Strict-Transport-Security fails
```

`Host` und SNI behalten den Namen der Instanz. Die erste Adresse dient als
Vergleich; ausgenommene Prüfungen werden ausgelassen. Andere Versionen sind
`high`, sonstige Abweichungen oder unerreichbare Adressen `medium`; erfolgreiche
Demo-Anmeldungen behalten ihren eigenen Schweregrad.

Die Funktion ist standardmäßig aus und verursacht zusätzliche Anfragen je
Adresse. Eine einzelne Adresse ergibt keinen Vergleichsbefund. Server hinter
einer gemeinsamen Loadbalancer-Adresse oder außerhalb der DNS-Antwort bleiben
unberücksichtigt. Ohne `scanner.ipv6_enabled` entfallen IPv6-Adressen.
Der öffentliche Webdienst bietet diese Option nicht an; siehe
[ADR 0042](../../adr/0042-every-resolved-address-is-compared-only-when-the-operator-asks.md).

### Ende der Release-Unterstützung {#end-of-life-detection}

OpenCloud pflegt Rolling, Production und LTS parallel. Rolling endet mit dem
nächsten Rolling-Release, Production mit dem nächsten Production-Release.
LTS-Linien erhalten zwei Jahre Unterstützung ab Beginn der Linie.
Die [offizielle Lifecycle-Seite][lifecycle] beschreibt die Kanäle.

[lifecycle]: https://docs.opencloud.eu/docs/admin/resources/lifecycle/

Den aktuellen Veröffentlichungsstand findest du auf der offiziellen
[Lifecycle-Seite][lifecycle]. Die folgenden Ausgaben
zeigen Beispiele für ein abgelaufenes und ein noch unterstütztes Release:

```
CRITICAL: The 7.3 rolling release line is end-of-life and has no security fixes. Upgrade to 7.4.0.
OpenCloud 7.3.0 on cloud.example.com, rating: F, last scanned: 2026-08-12 15:18:08.839323
Release lifecycle: 7.3 (rolling), out of support since 2026-08-03, upgrade to 7.4.0
```

```
Release lifecycle: 4.0 (lts), supported until 2027-12-01 (476 days left)
```

`support_days_left` enthält die Restlaufzeit, nach Ablauf als negativen Wert.
Ein eigener Zeitplan kann konfiguriert werden:

```yaml
scanner:
  use_release_schedule: true      # false disables the EOL check entirely
  # release_schedule: /etc/check-opencloud-security/schedule.json
```

Die Umgebungsvariablen heißen `COS_SCANNER_USE_RELEASE_SCHEDULE` und
`COS_SCANNER_RELEASE_SCHEDULE`. Details zur Zuordnung, Aktualisierung und zu
neueren unbekannten Versionen: [Release-Lifecycle](../release-lifecycle.md).

### Datenbank der Sicherheitsmeldungen {#advisory-database}

Versionsbereiche gelten als `[introduced, fixed)`. Die Quellen werden in dieser
Reihenfolge nach Kennung zusammengeführt: gebündelte Datenbank, Dateien aus
`scanner.vulnerability_db`, Feed aus `scanner.vulnerability_feed`.
Unterstützt werden das native Format, GitHub Advisories und OSV.
Ein nicht erreichbarer Zusatzfeed wird protokolliert und übersprungen.

Eine leere Liste bedeutet, dass keine geladene Meldung passt. Sie bestätigt
nicht, dass die Version frei von Schwachstellen ist. Für neuere Meldungen siehe
[Referenzdaten aktualisieren](../reference-data.md).

### Scanner als Dienst {#running-the-scanner-as-a-service}

`check-opencloud-scanner` führt denselben Scanner einmalig oder als HTTP-Dienst aus:

```shell
## one-shot: print the full result document as JSON
check-opencloud-scanner scan opencloud.example.com

## as a service, on this machine only
check-opencloud-scanner serve --port 8811
```

| Endpunkt | Funktion |
|:--|:--|
| `POST /api/queue` mit `url=<host>` | Scan starten und UUID zurückgeben |
| `GET /api/result/<uuid>` | Ergebnis lesen |
| `POST /api/requeue` mit `url=<host>` | Cache ersetzen und erneut scannen |
| `GET /api/scan?url=<host>` | Scan und Ergebnis in einem Aufruf |
| `GET /healthz` | Erreichbarkeit des Dienstes |

Das Plugin selbst verwendet diesen Dienst nicht. Andere Verbraucher können
seinen Ergebnis-Cache nutzen; `service.cache_ttl` beträgt standardmäßig
15 Minuten. Standardadresse ist `127.0.0.1`; jede andere Bindung erfordert ein
Token über `--token` oder `COS_SERVICE_TOKEN`. Der Dienst folgt dem
Vertrauensmodell eines Operators und prüft die von ihm benannten Ziele.

Die [Dienst-Anleitung](../scan-service.md) beschreibt Containerbetrieb und
`docker-compose.monitoring.yml`. Der normale Compose-Stack startet dagegen den
[öffentlichen Webdienst](../webapp.md).

## Updates prüfen {#update-check}

Der Scanner vergleicht `productversion` mit der gewählten Release-Quelle:

| Modus | Verhalten |
|:--|:--|
| `auto` | Feed, bei Fehler gebündelte Daten |
| `feed` | Nur Feed; Fehler als unbekannt |
| `pinned` | `--latest-version` ohne Abruf |
| `bundled` | Mitgelieferte Daten ohne Abruf |
| `off` | Prüfung auslassen |

```shell
## ask GitHub, with a token to stay clear of the anonymous rate limit
check-opencloud-security --host opencloud.example.com \
  --release-token 'secret://releases_token'

## fully offline: compare against a version you control
check-opencloud-security --host opencloud.example.com --latest-version 7.4.0
```

Ein Token kann das Abruflimit des GitHub-Feeds erhöhen. Bei `auto` fällt ein
fehlgeschlagener Abruf auf den Paketstand zurück. Das Ergebnis erscheint als
Zusatzzeile und Metrik `update_available`. `--update-warning` hebt ein sonstiges
OK bei ausstehendem Update auf WARNING an; ein Abruffehler bricht den Scan nicht ab.

Die Empfehlung bleibt im passenden Release-Kanal. Mit `--release-track` lege diesen ausdrücklich fest; siehe [Release-Lifecycle](../release-lifecycle.md).

## Konfigurationsdatei und Geheimnisse {#configuration-file-and-secrets}

Der Assistent schreibt eine Konfiguration:

```shell
check-opencloud-security --configure
```

Nur der Host ist zwingend erforderlich. Weitere Gruppen sind optional.
Die JSON-Datei erhält Modus `0600` und wird anschließend automatisch gefunden:

```shell
check-opencloud-security          # no arguments needed any more
```

Mit `--configure --config <pfad>` wähle den Speicherort. Vor dem Ersetzen
einer vorhandenen Datei zeigt der Assistent sie an und verlangt Bestätigung.
Für den Scanner lautet der entsprechende Befehl `check-opencloud-scanner configure`.

Gesucht wird zuerst nach `--config`, dann `COS_CONFIG_FILE`, `./.env.json`,
`./check-opencloud-security.yml`,
`~/.config/check-opencloud-security/.env.json` und den vorgesehenen Dateien in
`/etc/check-opencloud-security/`. Der erste Treffer gilt. `.json` wird als JSON,
anderes als YAML gelesen:

```yaml
host: opencloud.example.com
check_hardening: true

scanner:
  verify_tls: false        # self-signed instance
  target_port: 9200
  tls_min_days: 21
  check_debug_ports: true

releases:
  mode: auto
  token: secret://releases_token
```

Verschachtelte Schlüssel entsprechen den Umgebungsvariablen, etwa
`scanner.tls_min_days` und `COS_SCANNER_TLS_MIN_DAYS`. Geheimnisse können über
`secret://`, `file://`, `env://`, `exec://` oder `_file`-Schlüssel referenziert
werden; siehe [Konfiguration](../configuration.md).

## Alarmschwellen {#rating-thresholds}

| Wert | 5 | 4 | 3 | 2 | 1 | 0 |
|:--|:--|:--|:--|:--|:--|:--|
| Note | A+ | A | C | D | E | F |

`--critical` ist standardmäßig `1`, `--warning` `3`. Werte auf oder unter der
jeweiligen Grenze lösen den Zustand aus. Bekannte Schwachstellen ergeben
mindestens WARNING; ein abgelaufenes Release immer CRITICAL.

Ein kritischer Zusatzbefund begrenzt die Note auf `D` (`2`) und ergibt daher
standardmäßig WARNING. Setze `--critical 2`, wenn er CRITICAL auslösen soll.
Beide Schwellen müssen zwischen 0 und 5 liegen; `critical` darf `warning` nicht
überschreiten. Eine unbekannte Bewertung ergibt UNKNOWN.

```shell
## Only alert once the instance is actually end-of-life
check-opencloud-security --host opencloud.example.com --warning 1 --critical 0

## Page on any critical finding
check-opencloud-security --host opencloud.example.com --warning 4 --critical 2
```

### Schwellenwertprofile {#threshold-profiles}

`--profile` / `COS_PROFILE` benennt einen fertigen Satz, statt dass du
jedes Mal dieselben fünf Flags schreibst:

| Profil | `--warning` | `--critical` | `--check-hardening` | `--update-warning` | `--eol-warning` |
|:--|:--|:--|:--|:--|:--|
| `strict` | `4` (`A`) | `2` (`D`) | an | an | `90` |
| `ops` | `3` (`C`) | `1` (`E`) | an | aus | `30` |
| `lenient` | `2` (`D`) | `0` (`F`) | aus | aus | `0` |

Ein Profil entscheidet, **wie dieselben Messungen bewertet werden, nie wie
hart die Instanz geprüft wird**. Ohne `--profile` bleibt alles wie zuvor, und
alles, was du selbst setzt - Flag, Umgebungsvariable oder Datei - gewinnt.

## Schutzmaßnahmen bewerten {#hardening-checks}

`--check-hardening` berücksichtigt fehlende Maßnahmen und Sicherheitsheader.
Ein sonstiges OK wird bei fehlenden Maßnahmen zu WARNING; höhere Zustände
bleiben erhalten. Die Anzahl steht unter `hardenings_missing`.
`--debug` und der [Leitfaden](../hardening.md) erklären die Kennungen,
Konfigurationsmöglichkeiten und nicht veränderbaren Merkmale.

```shell
check-opencloud-security --host opencloud.example.com --check-hardening
```

`--ignore-hardening` nimmt einen fehlgeschlagenen Befund aus Alarm und Bewertung.
Er bleibt im Ergebnis mit `ignored: true` erhalten:

```bash
check-opencloud-security --host opencloud.example.com --check-hardening \
    --ignore-hardening 'cspWithoutUnsafeInline,hstsPreload'
```

Details zu Wildcards und Grenzen: [Ausnahmen](../hardening.md#accepting-a-finding-you-are-not-going-to-fix).

## Eine Bewertung nachvollziehen {#explaining-a-rating}

`--debug` zeigt die Ausgangsbewertung, die wirksamen Grenzen und die Bedeutung
jedes Befunds:

```shell
check-opencloud-security --host opencloud.example.com --check-hardening --debug
```

```text
--- Why this rating ---
Starting point: 5/5 - the installed release is current and no advisory matches this version
Failed check basicAuthDisabled [medium] caps the rating at 4/5 - WWW-Authenticate: Basic realm="..."
Final rating: 4/5 (B). WARNING at or below C, CRITICAL at or below E.

--- Missing hardening measures ---
basicAuthDisabled: HTTP Basic authentication is enabled
    The instance answers with a 'WWW-Authenticate: Basic' challenge, so usernames
    and passwords can be replayed on every request without going through the
    identity provider ... It is often deliberate: CalDAV, CardDAV and WebDAV
    clients cannot speak OpenID Connect and have nothing else to authenticate
    with, which is why this counts as a medium finding rather than a serious one.
    Setting: PROXY_ENABLE_BASIC_AUTH
    Fix: Set PROXY_ENABLE_BASIC_AUTH=false (the default) if nothing needs it. If
    calendar, contact or WebDAV clients do, keep it on and give them app tokens
    rather than account passwords.
    Docs: https://docs.opencloud.eu/docs/dev/server/services/proxy/environment-variables
--- end of explanation ---
```

Version und Sicherheitsmeldungen bestimmen die Basis. Zusatzbefunde begrenzen
sie nach Schweregrad. Auch fehlgeschlagene Prüfungen, die die endgültige Note
nicht verändern, bleiben in der Erklärung sichtbar.

`ratingExplanation` enthält diese Angaben immer im Ergebnisdokument:

```shell
python -m opencloud_local_scan.cli scan opencloud.example.com | jq .ratingExplanation
```

`--debug` aktiviert zusätzlich DEBUG-Logs auf stderr; die Berichtserklärung
steht mit der übrigen Ausgabe auf stdout.

## Schritte zur besseren Bewertung {#what-would-raise-the-rating}

`remediationPlan` berechnet mit derselben Bewertungslogik, welche Note nach den
aufgelisteten Änderungen erreichbar wäre:

```shell
python -m opencloud_local_scan.cli scan opencloud.example.com | jq .remediationPlan
```

`--debug` zeigt den Plan ebenfalls:

```text
--- What would raise the rating ---
Two fixes would raise this instance from 3/5 to 5/5.
1. exposed:/opencloud.yaml [high] - then 4/5 (B)
    A deployment file is publicly readable (/opencloud.yaml)
    Observed: HTTP 200 with 4.1 kB of YAML
    Fix: Stop serving the deployment directory. Proxy to OpenCloud's own
    address rather than exposing the filesystem ...
2. basicAuthDisabled [medium] - then 5/5 (A+)
    HTTP Basic authentication is enabled
    Fix: Set PROXY_ENABLE_BASIC_AUTH=false (the default) if nothing needs it ...
```

Mehrere Befunde können dieselbe Obergrenze verursachen. Deshalb bleibt auch ein
Schritt ohne unmittelbaren Notengewinn erhalten. Ein Update wird dort eingefügt,
wo es die Note verbessert. Fest vorgegebene, nicht veränderbare Merkmale stehen
unter den blockierten Maßnahmen und begrenzen das erreichbare Ergebnis.
Ausnahmen bleiben als solche sichtbar; sie beheben den Befund nicht.

Derselbe Plan erscheint im Webbericht, in den Exporten und im MCP-Werkzeug
`plan_remediation`.

### Nach Konfiguration gruppiert {#grouped-by-where-the-change-is-made}

`remediationPlan.groups` ordnet die offenen Befunde dem System zu, das du zur
Behebung bearbeitest: **Reverse Proxy**, **Identitätsanbieter**, **OpenCloud**
oder **DNS-Zone**. Auch Befunde, die die Note nicht begrenzen, etwa ein
fehlender Header, sind enthalten.

Befunde, die eine einzige Änderung behebt, bilden eine Änderung: alle
fehlenden Sicherheits-Header ein Header-Block, mehrere Zertifikatsprobleme ein
neues Zertifikat, alle `exposed:/...`-Pfade eine Korrektur und das Update alle
passenden Advisories. Jede Änderung nennt ihre Befunde, `resolvesSeveral` und
die Note, die sie allein ergäbe – nachgerechnet mit derselben
Bewertungsfunktion. `groupSummary` nennt die Änderungen, die mehrere Befunde
auf einmal beheben. Ausnahmen und fest vorgegebene Merkmale erscheinen nicht
als Änderung. `--debug`, der Webbericht, das Maßnahmenpaket und
`plan_remediation` zeigen die Gruppen ebenfalls.

## Webhook-Benachrichtigungen {#webhook-notifications}

Mit `--webhook-url` oder `COS_WEBHOOK_URL` aktiviere Benachrichtigungen:

```shell
check-opencloud-security --host opencloud.example.com \
  --webhook-url https://hooks.example.com/opencloud
```

- `--webhook-on`: `critical` (Standard), `warning`, `unknown` oder `always`.
  Jede Schwelle schließt die schwereren Zustände ein.
- `--webhook-format`: `generic`, `slack`, `discord`, `ntfy` oder `gotify`.
  Für ntfy muss die URL ein Topic enthalten; veröffentlicht wird am Server-Root.
- `--webhook-header`: zusätzliche Header; mehrfach nutzbar. In
  `COS_WEBHOOK_HEADERS` werden Einträge mit `;` getrennt.
- `--webhook-timeout`: eigenes Zeitlimit, standardmäßig zehn Sekunden.
- `--allow-private-webhooks`: ausdrückliche Freigabe interner Empfänger;
  private, Loopback- und Link-Local-Adressen sind sonst gesperrt.

Die Zustellung verwendet `--retries` und `--backoff-factor`. Bei Fehlern wird
`Webhook delivery failed` angehängt; der gemessene Zustand und Exitcode bleiben
erhalten. Mehrere Hosts erzeugen getrennte Nachrichten. Fehlgeschlagene Scans
lösen bei `unknown` oder `always` ebenfalls eine Benachrichtigung aus.

Verwende Webhooks ergänzend zur Überwachung. Nach ausgeschöpften
Wiederholungen erfolgt keine spätere Zustellung. Die [Webhook-Anleitung](../webhook-recipes.md)
erklärt Payload, Signaturprüfung und Empfängeradapter einschließlich
Uptime-Kuma-Push-Monitoren.

## Nur Änderungen melden {#reporting-only-what-changed}

`--baseline` speichert Befunde und vergleicht den nächsten Lauf damit.
`--warn-on-new` unterdrückt unveränderte Alarme und meldet neue oder schlechtere
Ergebnisse mit ihrem normalen Zustand:

```bash
check-opencloud-security -H opencloud.example.com \
    --check-hardening \
    --baseline /var/lib/check_opencloud/baseline.json \
    --warn-on-new
```

Die vollständigen Befunde bleiben sichtbar. Ein abgelaufenes Release löst immer
einen Alarm aus. Vergleichsformate und Regeln: [Baseline](../baseline.md).

## Plugin-Updates anzeigen {#is-the-plugin-itself-up-to-date}

`--self-update-check` fragt höchstens einmal täglich PyPI ab und ergänzt einen
Hinweis auf ein neueres Plugin:

```
Plugin update available: check-opencloud-security 1.2.0 is published, this is 1.1.0 (upgrade with --upgrade-self)
```

Die Funktion ist standardmäßig aus. Der Cache liegt unter
`${XDG_CACHE_HOME:-~/.cache}/check-opencloud-security/`. Abruffehler bleiben ohne
Meldung; der Exitcode ändert sich nicht. `--upgrade-self check` zeigt ein
mögliches Upgrade, `--upgrade-self` führt es aus; siehe [Installation](../installation.md#updating).

## Wiederholungen und Wartezeiten {#retries-and-backoff}

Vorübergehende Netzwerkfehler werden erneut versucht:

- `--retries`: zusätzliche Versuche nach dem ersten, standardmäßig zwei.
- `--backoff-factor`: anfängliche Wartezeit von standardmäßig 0,5 Sekunden;
  sie verdoppelt sich je Wiederholung.
- `--timeout`: Zeitlimit einer Anfrage, standardmäßig zehn Sekunden.

`--retries 0` deaktiviert Wiederholungen. Jeder neue Versuch wiederholt den
Scan; die Gesamtlaufzeit kann daher deutlich über einem einzelnen Timeout liegen.

## Nagios-Performancedaten {#performance-data}

Nach `|` folgen die Metriken:

```
rating=5;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=1.234s;;;0;
```

| Metrik | Bedeutung |
|:--|:--|
| `rating` | Wert 0–5, `U` bei unbekannter Bewertung |
| `vulnerabilities` | Passende bekannte Sicherheitsmeldungen |
| `time` | Scan-Dauer in Sekunden |
| `hardenings_missing` | Fehlende Maßnahmen bei `--check-hardening` |
| `extra_checks_failed` | Fehlgeschlagene Zusatzprüfungen |
| `update_available` | 1 bei verfügbarem Update |
| `support_days_left` | Tage bis Supportende, danach negativ |
| `cert_days_left` | Tage bis Zertifikatsablauf, danach negativ |
| `upgrade_path_complete` | `1`, wenn das empfohlene Upgrade alle bekannten Hinweise behebt, sonst `0`; fehlt ohne Hinweise |
| `waiver_days_left` | Tage, bis eine `--waive-until`-Ausnahme endet und eine fehlgeschlagene Prüfung wieder alarmiert; fehlt, wenn keine an einer Frist hängt |
| `coverage_inconclusive` | Prüfungen, die der Scan ausgeführt, aber nicht entschieden hat |
| `coverage_not_checked` | Prüfungen, die der Scan nicht ausgeführt hat |

`rating` enthält die konfigurierten Nagios-Schwellen, etwa `@0:3`.
`cert_days_left` fehlt, wenn keine verlässliche Messung möglich war. Seine
Warnschwelle entspricht `scanner.tls_min_days`; nach Ablauf gilt kritisch.
`waiver_days_left` zählt vom Scan bis zum nächsten Moment, an dem eine befristete
Ausnahme eine fehlgeschlagene Prüfung nicht mehr verdeckt. Mit `--waiver-warning TAGE`
trägt der Wert dieses Fenster als Warnbereich. `coverage_inconclusive` und
`coverage_not_checked` erklären die Bewertung, ändern sie aber nie, und haben
deshalb keine Schwellen.
Die [Prometheus-Anleitung](../prometheus.md) zeigt weitere Auswertungen.

## Cache {#caching}

Das Plugin scannt bei jedem Lauf neu. Der optionale
[Scandienst](#running-the-scanner-as-a-service) speichert Ergebnisse für
`service.cache_ttl` Sekunden; `POST /api/requeue` erzwingt dort einen neuen Scan.

## Beispielausgaben {#example-output}

Aktuelle Instanz:

```Shell
$ check-opencloud-security -H opencloud.example.com
OK: Server is up to date. No known vulnerabilities.
OpenCloud 7.4.0 on opencloud.example.com, rating: A+, last scanned: 2026-05-29 08:50:58.000000
Additional checks: all passed
Coverage: 84 checks evaluated, 6 skipped, 2 indeterminate, 1 network-limited | rating=5;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=0.731s;;;0; extra_checks_failed=0;;;0;
```

Zwischen den Detailzeilen und den Leistungsdaten sagt eine Zeile `Coverage:`,
wie viel der Prüfung tatsächlich zu einem Ergebnis kam - `84 checks evaluated,
6 skipped, 2 indeterminate, 1 network-limited`. Eine bestandene Prüfung und
eine, die nie lief, hinterlassen sonst dieselbe Spur, also benennt die Zeile
die Lücken: `skipped` ist eine Prüfung, die der Scan nicht ausgeführt hat,
`indeterminate` eine, die lief und nichts entscheiden konnte, und
`network-limited` eine, die in eine Zeitüberschreitung lief oder keine Route
hatte - DNSSEC, ein externer Identitätsanbieter, ein optionaler Endpunkt -,
was ein anderer Standort beantworten könnte. Die Zeile ändert weder die Note
noch den Exit-Code, und ein Ergebnisdokument von vor diesem Block bekommt gar
keine Zeile, denn "dieser Bericht sagt es nicht" ist nicht "nichts wurde
übersehen".

Abgelaufenes Release, unabhängig von den Schwellen CRITICAL:

```Shell
$ check-opencloud-security -H opencloud.example.com
CRITICAL: The 7.3 rolling release line is end-of-life and has no security fixes. Upgrade to 7.4.0.
OpenCloud 1.0.0 on opencloud.example.com, rating: F, last scanned: 2026-05-30 07:48:58.000000
Additional checks: all passed | rating=0;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=0.842s;;;0; extra_checks_failed=0;;;0;
```

Kritischer Zusatzbefund mit Standard-Schwellen:

```Shell
$ check-opencloud-security -H opencloud.example.com
WARNING: Rating D is at or below the warning threshold C, but no known vulnerabilities.
OpenCloud 7.4.0 on opencloud.example.com, rating: D, last scanned: 2026-05-29 08:51:33.000000
Additional checks failed (1): exposed:/opencloud.yaml | rating=2;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=0.860s;;;0; extra_checks_failed=1;;;0;
```

Zusätzliche Hardening-Auswertung bei angebotener HTTP-Basic-Anmeldung:

```Shell
$ check-opencloud-security -H opencloud.example.com --check-hardening
WARNING: 3 hardening measure(s) missing, but no known vulnerabilities.
OpenCloud 7.2.3 on opencloud.example.com, rating: B, last scanned: 2026-08-12 15:58:04.138671
Release lifecycle: 7.2 (production), current release
Missing hardening: basicAuthDisabled, cspWithoutUnsafeInline, publicLinkPasswordEnforced (run with --debug for what each means and how to fix it)
Additional checks failed (1): basicAuthDisabled
Update check (feed, installed 7.2.3): up to date | rating=4;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=1.835s;;;0; hardenings_missing=3;;;0; extra_checks_failed=1;;;0; update_available=0;;;0;1
```

Ein fehlgeschlagener Befund mit Schweregrad `medium` begrenzt die Bewertung auf
`4` (`A`). Eine reine Hardening-Maßnahme kann dagegen WARNING auslösen, ohne die
Note zu senken. `--debug` erklärt den jeweiligen Zusammenhang.

## Anleitungen zum Betrieb {#deployment-guides}

Der [Dokumentationsindex](../README.md) ordnet alle Anleitungen nach Aufgabe.
Häufige Einstiegspunkte sind [Installation](../installation.md),
[CLI-Referenz](../cli-reference.md), [Beispiele](../examples.md),
[Webdienst](../webapp.md), [MCP](../mcp.md) und
[Fehlersuche](../troubleshooting.md).
Für die übrige Infrastruktur siehe [OpenCloud sicher betreiben](../secure-deployment.md).

## Beispiele {#examples}

Die [Beispielsammlung](../examples.md) enthält vollständige Aufrufe für
Release-Kanäle, Ausnahmen, interne Instanzen, Alarmschwellen, Webhooks und Icinga2:

```bash
## A production instance, hardening reported, two findings accepted,
## notified on anything worse than OK - a realistic complete invocation
check-opencloud-security --host opencloud.example.com \
    --release-track production \
    --check-hardening \
    --ignore-hardening 'cspWithoutUnsafeInline,hstsPreload' \
    --update-warning \
    --warning 4 --critical 2 \
    --webhook-url https://hooks.example.com/opencloud \
    --webhook-on warning
```

## Marken und Unabhängigkeit

Dies ist ein unabhängiges Community-Projekt. Es ist nicht mit OpenCloud GmbH
verbunden und wird von ihr nicht unterstützt. OpenCloud und zugehörige Marken
gehören ihren jeweiligen Inhabern und benennen hier die geprüfte Software.
