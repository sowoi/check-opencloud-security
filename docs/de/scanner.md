# Bibliothek und JSON-CLI des OpenCloud Security Scanners

`opencloud_local_scan` ist die Scanner-Bibliothek hinter
`check-opencloud-security` und dem Dienst `check-opencloud-scanner`. Sie ruft die
Instanz direkt über HTTP(S) auf, prüft öffentlich sichtbare Einstellungen und
liefert ein Ergebnisdokument mit einer Bewertung von `0` bis `5`.

Die Skala entspricht der Nextcloud-Scan-API, damit vorhandene Schwellenwerte,
Metriken und Dashboards ihre Bedeutung behalten. Der Scan selbst läuft lokal.

| Modul | Aufgabe |
|:--|:--|
| `scanner.py` | Prüfablauf und Ergebnisdokument |
| `releases.py` | Update-Abgleich mit dem OpenCloud-Release-Feed |
| `vulndb.py`, `data/` | Sicherheitsmeldungen und Versionsbereiche |
| `versions.py` | Versionsvergleich und Release-Unterstützung |
| `config.py`, `secrets.py` | Konfigurationsdateien, Umgebungsvariablen und Geheimnisse |
| `service.py`, `cli.py` | HTTP-Scandienst und Scanner-Befehl |
| `factory.py` | Einstellungen aus einer `Configuration` aufbauen |
| `tls.py` | TLS-Verbindung, Zertifikat, Kette und Stapling |

## Welche Daten von der Instanz gelesen werden {#what-it-reads-from-the-instance}

Zwei ohne Anmeldung erreichbare Endpunkte bilden die Grundlage:

- **`/status.php`:** Produkt, Edition und `productversion`. Die fest
  vorgegebenen Felder `maintenance`, `installed` und `needsDbUpgrade` eignen
  sich nicht als Zustandsprüfung; siehe [Status-Endpunkt](../status-php.md).
- **`/ocs/v1.php/cloud/capabilities`:** Funktions- und Schutzmerkmale.

Weitere Informationen stammen aus HTTP-Antworten und TCP-Verbindungen.
Ein vorhandener `/status.php`-Endpunkt allein weist OpenCloud nicht nach.
Nennt das Dokument ein anderes Produkt, bricht der Scanner mit `ScanError` ab,
statt dessen Version mit OpenCloud-Sicherheitsmeldungen zu vergleichen.

### Die tatsächliche Version bestimmen {#the-version-trap}

`/status.php` enthält drei Versionsfelder:

```json
{"version": "0.1.0.0", "versionstring": "0.1.0", "productversion": "7.4.0"}
```

`version` und `versionstring` sind Kompatibilitätswerte aus `pkg/version`.
Nur `productversion` bezeichnet das installierte Release.
`versions.select_version()` bevorzugt dieses Feld, fragt ersatzweise die
Capabilities ab und verwirft bekannte Platzhalter. Ist keine verwertbare
Version vorhanden, enthält das Ergebnis `legacyVersion`; EOL-, Update- und
Schwachstellenprüfungen entfallen. Verwende auch in eigenen Skripten
`productversion`.

## Wie die Bewertung entsteht {#rating-algorithm}

Der Scanner wertet diese Bedingungen in der angegebenen Reihenfolge aus:

| Wert | Note | Bedingung |
|:--:|:--:|:--|
| 0 | F | Release wird nicht mehr unterstützt |
| 1 | E | Bekannte kritische oder hoch eingestufte Schwachstelle |
| 2 | D | Andere bekannte Schwachstelle |
| 3 | C | Eine ganze Release-Linie zurück |
| 4 | A | Update innerhalb der Release-Linie verfügbar |
| 5 | A+ | Aktuell |

Anschließend begrenzen fehlgeschlagene Zusatzprüfungen den Wert: kritisch auf
`2` (`D`), hoch auf `3` (`C`), mittel auf `4` (`A`), niedrig auf `5` (`A+`).
Eine solche Grenze verbessert niemals eine bereits schlechtere Bewertung.

Beachte die Monitoring-Schwellen: Ein kritischer Einzelbefund mit Note `D`
führt beim Standard `--critical 1` zu WARNING. Wähle `--critical 2`, wenn
dieser Befund CRITICAL auslösen soll. Um Zusatzbefunde ohne Einfluss auf die
Note zu erfassen:

```yaml
scanner:
  extra_checks_rating: false
```

`--no-extra-checks` schaltet diese Prüfungen vollständig ab.
`ratingExplanation` erklärt die Berechnung:

```json
{
  "rating": 4,
  "base": {"rating": 5, "reason": "the installed release is current and no advisory matches this version"},
  "caps": [
    {"check": "basicAuthDisabled", "severity": "medium", "cap": 4,
     "detail": "PROXY_ENABLE_BASIC_AUTH is on", "applied": true}
  ]
}
```

`base` ist die Bewertung aus Version und Sicherheitsmeldungen. `caps` enthält
alle fehlgeschlagenen Zusatzprüfungen mit ihrer Obergrenze. `applied: false`
bedeutet, dass der Befund die endgültige Bewertung nicht begrenzt hat. Die
Sortierung nach Schweregrad hält die Erklärung unabhängig von der
Ausführungsreihenfolge.

## Welche Änderungen die Bewertung verbessern {#what-would-raise-the-rating}

`remediation.py` erstellt aus dem Ergebnis einen `remediationPlan`. Dieser
ordnet die nächsten Schritte und zeigt die jeweils erwartete Bewertung:

```json
{
  "currentRating": 3,
  "achievableRating": 5,
  "summary": "Two fixes would raise this instance from 3/5 to 5/5.",
  "steps": [
    {"order": 1, "id": "exposed:/opencloud.yaml", "kind": "finding",
     "severity": "high", "title": "A deployment file is publicly readable",
     "action": "Stop serving the deployment directory ...",
     "ratingBefore": 3, "ratingAfter": 4, "ratingGain": 1}
  ],
  "blocked": [],
  "waived": []
}
```

Der Plan verwendet dieselbe Berechnung wie `_compute_rating` und entfernt
für die Vorhersage schrittweise Befunde. Er benötigt keinen eigenen Speicher.

- Die Reihenfolge richtet sich nach Bewertungsgrenze, Schweregrad und Kennung.
  Ein Schritt ohne unmittelbaren Notengewinn bleibt mit `ratingGain: 0` sichtbar,
  etwa wenn mehrere Befunde dieselbe Obergrenze verursachen.
- Ein Update erscheint an der ersten Stelle, an der es die Note verbessert.
  Offene Konfigurationsbefunde können den Nutzen eines Updates zunächst begrenzen.
- Nicht veränderbare Merkmale (`actionable: false`) stehen unter `blocked` und
  bleiben in der Simulation bestehen. Das begrenzt `achievableRating`.

Bei einem abgelaufenen Release ergibt sich sofort `0`, ohne gespeicherte
Bewertungsgrenzen. Für diesen Fall rekonstruiert der Plan sie aus `extraChecks`,
damit er nach einem Update keine Verbesserung trotz offener Befunde verspricht.

## Unbekannte Pfade und die Weboberfläche {#the-single-page-application-problem}

OpenClouds eingebettete Single-Page-Anwendung liefert für unbekannte Pfade
häufig ihre Startseite mit HTTP 200. Der Statuscode allein würde deshalb
fälschlich offengelegte Konfigurationsdateien melden.

Der Scanner ruft zunächst `/check-opencloud-security-probe-404` ab. Ein
geprüfter Dateipfad gilt nur dann als offengelegt, wenn seine Antwort von dieser
Vergleichsantwort abweicht. Das berücksichtigt auch pauschale Proxy-Fallbacks.

## Ende der Release-Unterstützung {#end-of-life-detection}

OpenCloud pflegt mehrere Release-Kanäle parallel:

| Kanal | Rhythmus | Unterstützung bis |
|:--|:--|:--|
| `rolling` | etwa alle drei Wochen | zum Nachfolger |
| `production` | etwa alle sechs Monate | zum nächsten Production-Release |
| `lts` | ausgewählte Production-Linie | zwei Jahre nach Beginn der Linie |

Entscheidend ist die **Release-Linie** (`MAJOR.MINOR`). Eine Linie kann mehreren
Kanälen angehören; bei automatischer Erkennung zählt der längste passende
Supportzeitraum. Die Versionsnummer allein reicht deshalb nicht aus.

Ein Beispiel aus dem Release-Verlauf: `7.2.3` kann als Production-Release noch
unterstützt sein, während die neuere Rolling-Version `7.3.0` bereits durch
`7.4.0` abgelöst wurde. Ebenso kann die Linie `4.0` ihren Production-Zeitraum
beendet haben und weiterhin LTS-Updates erhalten.

`schedule_source.py` liest Typ und Datum aus der
[OpenCloud-Lifecycle-Seite][lifecycle]. `scripts/update_release_schedule.py`
schreibt daraus in CI die mitgelieferte Datei `data/release_schedule.json`:

[lifecycle]: https://docs.opencloud.eu/docs/admin/resources/lifecycle/

```json
{
  "lifetime_days": {"rolling": 21, "production": 183, "lts": 730},
  "latest_release": {"production": "7.2.3", "rolling": "7.4.0"},
  "lines": [
    {"line": "7.4", "tracks": ["rolling"], "released": "2026-08-03", "latest": "7.4.0"},
    {"line": "7.2", "tracks": ["production", "rolling"], "released": "2026-06-25", "latest": "7.2.3"},
    {"line": "4.0", "tracks": ["lts", "production"], "released": "2025-12-01", "latest": "4.0.8"}
  ]
}
```

Rolling und Production enden mit dem Nachfolger desselben Kanals.
`lifetime_days` beschreibt die zeitliche Grenze im Zeitplan, insbesondere das
LTS-Fenster. Ein nicht mehr unterstütztes Release erhält `EOL: true` und `F`.

Eine Version vor dem mitgelieferten Wissensstand wird nicht allein deshalb als
abgelaufen gewertet: Das gilt sowohl für unbekannte neuere Versionen als auch
für die neueste Linie eines Kanals ohne bekannten Nachfolger.

Ist die Instanz neuer als der Zeitplan, nennt das Ergebnis `scheduleStale`,
`scheduleUpdated`, `scheduleSource` und `scheduleNote`. Dieser Hinweis auf die
Datenbasis verändert die Bewertung nicht. `ReleaseSchedule.is_behind()` stellt
denselben Vergleich direkt bereit.

Das Plugin aktualisiert den gebündelten Zeitplan mit dem Paket. Der dauerhaft
laufende Webdienst kann ihn täglich über
`schedule_source.fetch_schedule_document()` nachladen und als
`ScannerSettings.release_schedule` übergeben. Der Scanner wertet den
übergebenen Zeitplan unabhängig von seiner Herkunft aus:

```yaml
scanner:
  use_release_schedule: true       # false skips the EOL check entirely
  # release_schedule: /etc/check-opencloud-security/release_schedule.json
```

`lifecycle` enthält Linie, Kanal, Veröffentlichungsdatum, Supportende,
Restlaufzeit, Update-Ziel und Angaben zum verwendeten Zeitplan.

## Verfügbare Updates {#update-check}

OpenCloud veröffentlicht über die geprüften Endpunkte keine ausstehenden
Updates. Der Scanner vergleicht daher `productversion` mit einem Release-Feed
oder den konfigurierten Referenzdaten.

Die Empfehlung bleibt im Release-Kanal. Production- und LTS-Instanzen erhalten
kein Rolling-Release als reguläres Update-Ziel. Das insgesamt neueste Release
steht zusätzlich unter `newestRelease`.

| Modus | Verhalten |
|:--|:--|
| `auto` | Feed abfragen; bei Fehler auf gebündelte Daten zurückfallen |
| `feed` | Nur Feed verwenden; Fehler als unbekannt melden |
| `pinned` | Konfiguriertes `latest_version` ohne Netzwerkabfrage verwenden |
| `bundled` | Mitgeliefertes `latest_release` verwenden |
| `off` | Update-Prüfung auslassen |

Standard ist `auto`. Bei einem nicht erreichbaren Feed bleibt die Prüfung mit
den Daten des installierten Pakets möglich. Wähle `feed`, wenn du einen
fehlgeschlagenen Abruf ausdrücklich sehen möchtest.

Standardquelle ist die GitHub-Releases-API. `parse_release_feed()` versteht
auch ein einzelnes `{"tag_name": ...}`-Dokument und Release-Listen. Entwürfe
und Vorabversionen werden ausgelassen; interne Spiegel können diese Formate
übernehmen.

## Sicherheitsmeldungen {#vulnerabilities}

### Referenzdaten auf dem Monitoring-Host aktualisieren {#refreshing-reference-data-on-a-monitoring-host}

`refresh-data` aktualisiert die Daten unabhängig von einem Paket-Upgrade:

```console
$ check-opencloud-scanner refresh-data \
    --output-dir /var/lib/check-opencloud-security
/var/lib/check-opencloud-security/release_schedule.json
/var/lib/check-opencloud-security/vulnerabilities.json
```

Der Befehl lädt die im Projekt-Repository geprüften Dateien und versucht, ihre
Sigstore-Attestierung zu verifizieren. Er verwirft Zeitpläne, die gebündelte
Release-Linien verlieren, sowie Sicherheitsmeldungen ohne Versionsgrenzen.
Die Zieldateien werden atomar ersetzt; das installierte Paket bleibt unverändert.
Verweise mit `scanner.release_schedule` und `scanner.vulnerability_db`
auf diese Dateien. Der mitgelieferte
[systemd-Timer](../../contrib/systemd/check-opencloud-security-refresh.timer)
kann den Abruf täglich ausführen.

Für die Signaturprüfung benötigst du das Extra `signing`:

```console
$ pip install 'check-opencloud-security[signing]'
```

Ohne dieses Extra gelten nur die Strukturprüfungen; der Befehl warnt davor.
Auch mit installiertem Extra sind drei Fälle zu unterscheiden:

- Erfolgreiche Verifikation: Die geprüften Daten werden übernommen.
- Verifikation nicht möglich, etwa wegen fehlender Attestierung oder
  unerreichbarer Vertrauensdaten: Warnung und Rückfall auf Strukturprüfungen.
- Vorhandene, ungültige Signatur: Abbruch; vorhandene Dateien bleiben erhalten.

Eigene Quellen über `--schedule-url` oder `--advisory-url` werden ohne diese
Attestierungsprüfung abgerufen. Der Befehl weist im Log darauf hin; siehe
[ADR 0027](../../adr/0027-refreshed-reference-data-is-attested-not-merely-fetched.md).

`.github/workflows/vulnerability-db.yml` fragt täglich über
`scripts/update_vulnerability_db.py` die OSV-API ab und öffnet bei Änderungen
einen Pull Request für `data/vulnerabilities.json`. Dabei kommen nur Einträge
hinzu. Eine Meldung wird nur von Hand entfernt.

Eine leere Liste `vulnerabilities` bedeutet, dass keine geladene Meldung zur
Version passt. Sie bestätigt nicht die Vollständigkeit der Quellen. Eigene
Datenbanken lassen sich ergänzen:

```yaml
scanner:
  vulnerability_db: /etc/check-opencloud-security/advisories.json
  vulnerability_feed: https://api.osv.dev/v1/query
```

Unterstützt werden das native Format mit `advisories`, das GitHub-Advisory-Format
und OSV. Versionsbereiche gelten als `[introduced, fixed)`, also bis
unmittelbar vor die korrigierte Version. Gleiche Kennungen werden über Quellen
hinweg zusammengeführt. `advisorySources` nennt die tatsächlich geladenen Quellen.

Eine Meldung kann mehrere getrennt korrigierte Release-Linien betreffen.
Dafür gibt es `ranges`:

```json
{
  "id": "GHSA-vf5j-r2hw-2hrw",
  "severity": "high",
  "ranges": [
    {"introduced": "4.0.0", "fixed": "4.0.3"},
    {"introduced": "5.0.0", "fixed": "5.0.2"}
  ]
}
```

Das Ergebnis nennt die Korrekturversion für den passenden Bereich. Bei
`GHSA-vf5j-r2hw-2hrw` erhält etwa `5.0.1` die Empfehlung `5.0.2` statt einer
Korrektur aus der Linie `4.0`. `introduced` und `fixed` bleiben als Darstellung
des ersten Bereichs erhalten.

Meldungen ohne jede Versionsgrenze werden verworfen. Ein nach beiden Seiten
offener Bereich würde sonst jede OpenCloud-Version als betroffen melden.

## Schutzmaßnahmen {#hardenings}

Die Bibliothek leitet aktivierte Maßnahmen aus beobachtbaren Einstellungen ab,
nicht aus der Versionsnummer:

| Kennung | Nachweis |
|:--|:--|
| `hstsLongMaxAge` | HSTS mit mindestens einem Jahr `max-age` |
| `hstsPreload` | HSTS enthält `preload` |
| `cspWithoutUnsafeInline` | CSP ohne `'unsafe-inline'` |
| `basicAuthDisabled` | Anmeldeaufforderung eines geschützten Endpunkts bietet kein `Basic` |
| `publicLinkPasswordEnforced` | Capabilities verlangen Passwörter für öffentliche Links |
| `publicLinkExpirationEnforced` | Capabilities verlangen Ablaufdaten für öffentliche Links |
| `userEnumerationRestricted` | Capabilities melden eingeschränkte Benutzersuche |
| `passwordPolicyEnforced` | Aktive Passwortrichtlinie mit mindestens acht Zeichen |
| `passwordPolicyComplexity` | Klein- und Großbuchstaben, Ziffern und Sonderzeichen gefordert |
| `oidcPkceSupported` | Discovery nennt `S256` unter `code_challenge_methods_supported` |
| `oidcImplicitFlowDisabled` | Keine Token-Ausgabe vom Authorization-Endpunkt laut Discovery; nur externe Provider |
| `oidcSigningAlgorithmStrong` | Weder `none` noch ein `HS`-Algorithmus in `id_token_signing_alg_values_supported` |
| `oidcEndpointsUseHttps` | Alle veröffentlichten OIDC-Endpunkte nutzen HTTPS; nur bei HTTPS-Instanzen geprüft |

Fehlt die für eine Maßnahme benötigte Information, entfällt deren Schlüssel.
`capabilitiesAvailable` zeigt, ob die entsprechenden Daten abrufbar waren.
Zusatzprüfungen erfassen außerdem Wildcards bei Embed-Origins, delegierte
iframe-Anmeldung ohne ausdrückliche Origin und einen direkt erreichbaren
OpenCloud-Backend-Port.

Vor dem Aktivieren von `--check-hardening` sind drei Besonderheiten relevant:

- OpenClouds Standard-CSP enthält `'unsafe-inline'`. Eine eigene CSP muss die
  Anforderungen der Weboberfläche berücksichtigen und getestet werden.
- `basicAuthDisabled` liest die angebotenen Authentifizierungsverfahren aus
  `WWW-Authenticate`. Basic Auth kann für bestimmte DAV-Clients erforderlich
  sein. Der Schweregrad beträgt `medium`, bei externem Identity Provider `low`.
- `publicLinkExpirationEnforced` und `userEnumerationRestricted` sind fest
  vorgegebene Capabilities. `actionable=False` nimmt sie aus Alarmen und Zählern,
  behält sie aber im Ergebnis.

### Beobachtungen ohne Einfluss auf die Bewertung {#observations-that-are-not-findings}

`integrations` enthält Angaben zu erkennbaren Anbindungen:

| Schlüssel | Nachweis |
|:--|:--|
| `integrations.office.detected` | `/app/list` nennt mindestens einen registrierten Provider |
| `integrations.office.apps` | Zurückgegebene Namen, etwa `Collabora` |
| `integrations.office.groupware` | Capability `groupware.enabled` |
| `integrations.calendar.detected` | `/.well-known/caldav` leitet weiter oder verlangt Anmeldung |
| `integrations.calendar.advertised` | `core.support_radicale`; wegen Standardwert `true` nur ergänzender Hinweis |

Die fest vorgegebene Capability `files.app_providers` wird nicht verwendet.
Unter `setup.advisoryChecks` stehen zwei weitere Hinweise ohne Noteneinfluss:

- `securityTxtPublished`: Ein `Contact`-Feld in `/.well-known/security.txt`,
  nicht bloß HTTP 200.
- `hstsPreloadEligible`: Mindestens ein Jahr HSTS sowie `includeSubDomains`
  und `preload`. Das prüft die Header-Anforderungen, nicht die tatsächliche
  Aufnahme in eine Browserliste; siehe [ADR 0037](../../adr/0037-preload-eligibility-is-measured-list-membership-is-not.md).

OpenCloud erfüllt diese Anforderungen standardmäßig nicht. Deshalb werden sie
erklärt, ohne jede Installation dafür abzuwerten. Bei ausgeschalteten
Zusatzprüfungen bleibt der Block `{}`; siehe [ADR 0034](../../adr/0034-an-advisory-observation-need-not-be-a-header.md).

`identityProvider` nennt einen erkannten externen Provider. Für Keycloak,
Authelia und Authentik verweist `advisoryUrl` auf dessen offizielle
Sicherheitsmeldungen. `version` bleibt leer, solange kein verlässlicher,
öffentlich erreichbarer Versionsnachweis vorliegt. URL-Pfade, Assets und
Proxy-Header werden nicht als Versionsbeleg verwendet.

### Grenzen der Prüfung {#what-the-scanner-cannot-measure}

Audit-Protokollierung lässt sich von außen nicht erkennen, da der Audit-Dienst
keinen entsprechenden HTTP-Endpunkt veröffentlicht. Ebenso belegt eine
registrierte Office-Integration weder korrekte WOPI-Geheimnisse noch passende
Freigaberechte.

Der Scanner verwendet keine normalen Benutzerzugänge. Als ausdrücklich
begrenzte Ausnahme prüft `_demo_user_finding` am eingebauten Provider die
veröffentlichten Konten `dennis`, `margaret`, `alan`, `lynn` und `mary` über
`/ocs/v1.php/cloud/user`. Eine erfolgreiche Anmeldung ergibt den kritischen
Befund `demoUsersDisabled`; externe Provider erhalten diese Zugangsdaten nicht.
Eine abgewiesene Demo-Anmeldung bestätigt nur, dass diese Zugangsdaten nicht
funktionieren, nicht die Sicherheit der gesamten Anmeldung.

### Kennungen erklären {#explaining-the-flags}

`hardening.py` verbindet jede Kennung mit einer Erklärung, den relevanten
OpenCloud-Variablen und der offiziellen Dokumentation:

```python
from opencloud_local_scan import describe_hardening

print(describe_hardening("basicAuthDisabled").describe())
```

```text
basicAuthDisabled: HTTP Basic authentication is enabled
    The instance answers with a 'WWW-Authenticate: Basic' challenge, so ...
    Setting: PROXY_ENABLE_BASIC_AUTH
    Fix: Set PROXY_ENABLE_BASIC_AUTH=false (the default). ...
    Docs: https://docs.opencloud.eu/docs/dev/server/services/proxy/environment-variables
```

Der Katalog umfasst auch Sicherheitsheader, ergänzende Beobachtungen und
`httpsEnforced`. Unbekannte Kennungen erhalten in Berichten einen benannten
Platzhalter. Ein Test stellt sicher, dass alle vom Testserver erzeugten
Kennungen dokumentiert sind.

Auf der Kommandozeile ist derselbe Katalog direkt verfügbar:

```shell
$ check-opencloud-scanner explain basicAuthDisabled
$ check-opencloud-scanner explain exposed:/config/opencloud.yaml
$ check-opencloud-scanner explain --category transport
$ check-opencloud-scanner explain --list
$ check-opencloud-scanner explain --format json cookieSecure
```

Der Befehl benötigt weder Konfiguration noch Netzwerkzugriff. Er akzeptiert
Headernamen und pfadbezogene Befunde wie `exposed:/config/opencloud.yaml`.
Ohne Kennung zeigt er den gesamten Katalog; bei unbekannter Kennung endet er
mit Exitcode 1 und schlägt ähnliche Namen vor.

### Konfigurationsvorschläge aus dem Katalog {#the-same-fix-as-configuration}

`snippets.py` erzeugt aus den Einträgen `env_fix` und `header_fix`
Konfigurationsausschnitte:

```python
from opencloud_local_scan import configuration_fragment

print(configuration_fragment(["basicAuthDisabled", "demoUsersDisabled"], "compose").text)
```

```yaml
services:
  opencloud:
    environment:
      PROXY_ENABLE_BASIC_AUTH: "false"
      IDM_CREATE_DEMO_USERS: "false"
```

Verfügbar sind `compose`, `env`, `nginx`, `caddy` und `traefik`. Einstellungen
für OpenCloud und Header am TLS-Proxy gehören in unterschiedliche Dateien.
`Fragment.elsewhere` nennt deshalb Maßnahmen, die das gewählte Format nicht
darstellen kann; `flavours_for` nennt passende Formate.

Werte stammen ausschließlich aus dem Katalog. Erfordert eine Maßnahme eine
Entscheidung über die konkrete Installation, etwa eine erlaubte CORS-Origin
oder einen CSP-Dateipfad, erscheint sie unter `Fragment.undecided` statt als
scheinbar fertiger Konfigurationswert.

## Was der Scan abgedeckt hat {#what-the-scan-covered}

Eine bestandene Prüfung und eine Prüfung, die nie gelaufen ist, hinterlassen
in diesem Dokument dieselbe Spur: nichts. In `coverage` steht der Unterschied.
Siehe [ADR 0064](../../adr/0064-a-scan-records-what-it-did-not-measure.md).

```json
{
  "coverage": {
    "schema": 1,
    "counts": {"passed": 49, "failed": 10, "not_checked": 12, "inconclusive": 0, "total": 71},
    "checks": [
      {"id": "Content-Security-Policy", "group": "header", "state": "passed"},
      {"id": "directoryListing", "group": "extraCheck", "state": "failed"},
      {"id": "tlsInspection", "group": "tls", "state": "not_checked",
       "reason": "not_applicable", "detail": "The instance answered over plain HTTP."}
    ]
  }
}
```

Jede Prüfung, die der Scan vorgesehen hat, steht genau einmal darin, in einem
von vier Zuständen:

| Zustand | Bedeutung |
|:--|:--|
| `passed` | Die Prüfung lief und die Instanz hat sie erfüllt |
| `failed` | Die Prüfung lief und die Instanz hat sie nicht erfüllt |
| `not_checked` | Der Scanner hat die Prüfung nicht ausgeführt |
| `inconclusive` | Der Scanner hat geprüft und konnte nicht entscheiden |

`passed` und `failed` tragen keinen Grund - eine Messung, die stattgefunden
hat, braucht keine Entschuldigung. Die beiden anderen tragen immer einen, aus
einer festen Menge:

| Grund | Bedeutung |
|:--|:--|
| `not_applicable` | Die Prüfung kann auf diese Bereitstellung nicht zutreffen - kein Zertifikat bei einer Instanz über HTTP, keine zweite Adresse zum Vergleich |
| `probe_disabled` | Eine Einstellung hat die Prüfung für diesen Scan abgeschaltet |
| `prerequisite_missing` | Die Instanz hat nicht veröffentlicht, was die Prüfung liest |
| `timeout` | Nichts hat rechtzeitig geantwortet |
| `unreadable` | Etwas hat geantwortet und war nicht zu verstehen |
| `no_route` | Von dort, wo der Scan lief, gibt es keine Route zu dieser Adressfamilie |

Auf zwei Eigenschaften kannst du dich verlassen:

- **Die Gesamtzahl ist das, was dieser Scan vorgesehen hat**, keine Konstante.
  Die Prüfungen sind dynamisch - welche Pfade geprüft, welche Debug-Ports
  gewählt und welche Adressen verglichen werden, hängt von der Instanz und den
  Einstellungen ab -, also gibt es keinen festen Nenner.
- **Abdeckung ändert nie eine Note.** Nichts in diesem Block erreicht die
  Bewertung, die Schweregrade, die Alarmzeile, den Exit-Code oder die
  Webhook-Nutzlast. Ein ausgenommener Fehlschlag bleibt hier `failed`; die
  Annahme steht in `extraChecks[].ignored`, denn eine Ausnahme ist eine
  Entscheidung über Alarme und nicht über Belege.

Ein Dokument, das vor diesem Block entstanden ist, hat keinen
Schlüssel `coverage` - ein Bericht, der nicht sagt, was er abgedeckt hat, und
nicht ein Scan ohne Lücken. Lies ihn mit `coverage.coverage_of(result)`, das
sowohl für einen fehlenden als auch für einen fehlerhaften Block `None`
zurückgibt.

### Die Zusammenfassung in einer Zeile {#the-one-line-summary}

`coverage.summary(result)` verdichtet den Block auf die vier Zahlen, die eine
Leserin braucht, und `coverage.summary_line(result)` schreibt sie als einen
englischen Satz:

```
84 checks evaluated, 6 skipped, 2 indeterminate, 1 network-limited
```

Jede Prüfung steckt in genau einer der vier Zahlen. `evaluated` ist ein
Ergebnis, bestanden oder nicht; `skipped` ist eine Prüfung, die der Scanner
nicht ausgeführt hat; `indeterminate` ist eine, die lief und nichts entscheiden
konnte; `networkLimited` ist aus den beiden letzten herausgelöst, weil eine
Zeitüberschreitung oder eine fehlende Route - DNSSEC, ein externer
Identitätsanbieter, ein optionaler Endpunkt - die Lücke ist, die ein anderer
Standort schließen könnte. Nullen lässt der Satz weg, die Zahl der
ausgewerteten Prüfungen nennt er immer. Beide Funktionen geben für ein Dokument
ohne Abdeckungsblock `None` beziehungsweise `""` zurück, damit "nichts wurde
übersehen" und "dieser Bericht sagt es nicht" nie gleich klingen.

Das Plugin gibt den Satz als Detailzeile `Coverage:` aus, die Webhook-Nutzlast
trägt dieselben Zahlen unter `coverage`, und die Weboberfläche zeigt sie unter
*Was dieser Scan nicht gemessen hat*.

## Unter welchen Bedingungen ein Scan lief {#the-conditions-a-scan-ran-under}

Zwei Scans derselben Instanz können sich unterscheiden, ohne dass sich die
Instanz geändert hat: Die Advisory-Datenbank enthält eine neue CVE, ein
Supportzeitraum ist abgelaufen, der Scanner wurde aktualisiert, eine Ausnahme
ist verfallen. `provenance` hält fest, was zum Zeitpunkt des Scans bekannt war,
damit ein Vergleich das von einer echten Verschlechterung unterscheiden kann.
Siehe [ADR 0066](../../adr/0066-a-result-records-the-conditions-it-was-produced-under.md).

```json
{
  "provenance": {
    "schema": 1,
    "scannerVersion": "1.25.0",
    "scannedAt": "2026-09-17T19:56:35.852320+00:00",
    "releaseTrack": "auto",
    "advisoryData": {"digest": "7ffa242f...", "count": 1},
    "scheduleData": {"digest": "6e9468bf...", "updated": "2026-09-15"},
    "waivers": {"active": [], "expired": []},
    "coverage": {"measured": 59, "total": 71}
  }
}
```


`digest` ist ein SHA-256 über die kennzeichnenden Felder der Referenzdaten in
kanonischer Form: Dieselben Advisories ergeben denselben Wert, egal wie sie
serialisiert, zusammengeführt oder sortiert wurden. Es ist eine Prüfsumme und
keine Kopie - die Datenbank einzubetten würde Megabyte fremder Advisories in
jeden Bericht schreiben - und auch kein Dateipfad, der verraten würde, wo die
Maschine ihre Dateien ablegt. `scheduleData.updated` ist der Zeitpunkt, zu dem
der Zeitplan *erzeugt* wurde, nicht der, zu dem er gelesen wurde; `scannedAt`
ist der Scan.

`waivers` hält Muster und Zustände fest, nie den Begründungstext: Eine
Begründung ist Prosa für einen Menschen, und ein Vergleich, der sie
gegenüberstellt, würde einen korrigierten Tippfehler als Richtlinienänderung
melden.

### Zwei Ergebnisse vergleichen {#comparing-two-results}

`check-opencloud-scanner diff` gibt die beitragenden Änderungen unter der
bisherigen Zusammenfassung aus, und `--format json` liefert sie als
`explanation`:

| Kategorie | Was sich geändert hat |
|:--|:--|
| `instance` | Die Version, oder eine Prüfung, die zu scheitern begann oder aufhörte |
| `referenceData` | Die Advisories, der Zeitplan, der Track, oder ein abgelaufener Supportzeitraum |
| `scanner` | Die Version des Scanners, oder wie viele Prüfungen zu einem Ergebnis kamen |
| `policy` | Eine Ausnahme ist verfallen, kam hinzu oder fiel weg |
| `unknown` | Etwas hat sich bewegt und nichts Aufgezeichnetes erklärt es |

Die Formulierungen sind zurückhaltend. Eine geänderte Prüfsumme belegt,
dass sich die Referenzdaten unterschieden; sie belegt nicht, dass dadurch eine
bestimmte Note gefallen ist, und der Satz behauptet es auch nicht. Mehrere Änderungen
können beitragen, ohne dass eine davon zur Ursache erklärt wird.

`limitations` listet auf, was der Vergleich nicht feststellen konnte - meist,
dass einer der beiden Berichte älter als diese Blöcke ist und deshalb nicht
sagen kann, wogegen er geprüft wurde oder wie viel davon lief. Das wird
berichtet und nicht angenommen.

## Hat sich die Installation geändert? {#has-the-deployment-changed}

Eine Note sagt, ob eine Instanz in gutem Zustand ist. Sie sagt nicht, ob es
noch dieselbe Instanz wie letzte Woche ist. Eine neu geschriebene Richtlinie
ohne `unsafe-inline`, ein ausgetauschter Proxy, der dieselben Header setzt,
öffentliche Links, die erst kein Passwort mehr verlangen und dann wieder, ein
Zertifikat bei einem anderen Aussteller - nichts davon muss eine Note bewegen,
und wer nur auf die Note schaut, sieht nichts davon.

`configuration` enthält **Fingerabdrücke** der gemessenen Konfiguration,
nach Bereichen gruppiert und ohne die ursprünglichen Einstellungswerte. Siehe
[ADR 0073](../../adr/0073-a-result-fingerprints-the-configuration-it-measured.md).

```json
{
  "configuration": {
    "schema": 1,
    "digest": "9e3c4428...",
    "groups": {
      "tls": {"digest": "89a97538...", "scope": "1d0f4b77...", "facts": 12},
      "headers": {"digest": "cb25144c...", "scope": "b8e1a930...", "facts": 13},
      "sharing": {"digest": "7b8a1ced...", "scope": "44c0ae51...", "facts": 3},
      "authentication": {"digest": "588d045f...", "scope": "0a7be2cc...", "facts": 6},
      "proxy": {"digest": "b7db6daf...", "scope": "ff31c084...", "facts": 5}
    }
  }
}
```

Zwei Scans mit demselben Gruppen-Digest haben dieselbe Konfiguration gesehen,
zwei mit verschiedenen nicht. Mehr wird nicht behauptet, und diese Regeln
machen die Aussage brauchbar:

- **Nur Digests, nie die Konfiguration.** Eine Content-Security-Policy nennt
  die Herkünfte, denen eine Installation vertraut; ein Discovery-Dokument kann
  einen Mandanten nennen; ein Server-Banner nennt einen internen Build. Jede
  Tatsache wird in ihre Gruppe gehasht und verworfen. Man erfährt, *dass*
  Freigaben sich geändert haben, nie *worauf* sie stehen.
- **Gruppen sind die Fragen, die Betreiber stellen.** "Hat sich TLS geändert?"
  ist nützlich, "hat sich Tatsache 37 geändert?" nicht.
- **Nur, was die Installation entscheidet.** Die Transportgruppe hasht
  Aussteller, Schlüssel, Signaturverfahren und ausgehandelte Protokolle - nicht
  Seriennummer, Gültigkeitsdaten oder Zertifikats-Fingerabdruck, denn eine
  Erneuerung ist Routine. Die Proxy-Gruppe hasht das Produkt, nicht das Banner
  mit seiner Build-Nummer.
- **Was die Scan-Einstellungen entscheiden, ist nie eine Tatsache.** `scope`
  ist ein Digest darüber, *welche* Tatsachen eine Gruppe ansehen konnte, ohne
  deren Werte. Zwei Gruppen werden nur bei gleichem Scope verglichen, also
  meldet ein Lauf, der TLS nicht mehr inspiziert, "nicht vergleichbar" statt
  einer Änderung. Eine Gruppe ohne jede Tatsache ist `none`.
- **Die Note ändert sich dadurch nie.** Nichts davon erreicht Bewertung,
  Schweregrade, Alarmzeile oder Exit-Code.

Lies den Block mit `fingerprint.fingerprint_of(result)`, das für einen
fehlenden wie für einen fehlerhaften Block `None` zurückgibt - ein Bericht,
der es nicht sagen kann, ist keine Installation, die sich nicht geändert hat.
`fingerprint.digests(result)` macht daraus eine undurchsichtige Zeichenkette
`scope:digest` je Gruppe, und `fingerprint.drift(before, after)` nennt die
Gruppen, die sich unterscheiden.

Das Plugin gibt bei jedem Scan `Configuration fingerprint: 9e3c4428` aus, und
`--baseline` macht daraus `No new findings, but the configuration changed
(headers)`.

## Debug-Ports {#debug-ports}

Debug-Listener liefern unter anderem `/healthz`, `/readyz`, `/metrics`,
`/config` und `/debug/pprof`. Diese Endpunkte können Versionen und Konfigurationen
offenlegen und Profiling erlauben. Standardmäßig sind die Listener an Loopback gebunden, sofern
`<SERVICE>_DEBUG_ADDR` nichts anderes festlegt.

| Port | Dienst |
|:--|:--|
| 9205 | proxy |
| 9141 | frontend |
| 9124 | graph |
| 9134 | idp |
| 9239 | idm |

Standardmäßig erfolgt pro Port ein TCP-Verbindungsversuch mit drei Sekunden
Timeout. `check_debug_ports`, `debug_port_timeout`, `debug_ports` und
`concurrency` steuern diese Prüfung. Auf der Hauptadresse werden zusätzlich
die HTTP-Debug-Pfade geprüft; entsprechende Befunde beginnen mit `debugEndpoint:`.

## Alle aufgelösten Adressen {#every-resolved-address}

`check_all_addresses=True` beziehungsweise `scan --all-addresses` wiederholt die
vom jeweiligen Server abhängigen Prüfungen für jede aufgelöste Adresse:
Version, bewertete Header, Capabilities, Anmeldeaufforderung, Provider und
Demo-Konten. Das Ergebnis steht unter `addressParity`.

`Host` und SNI behalten den Namen der Instanz. Jede Verbindung nutzt eine
eigene, auf die Adresse festgelegte Sitzung. Bei `pinned_addresses` bleiben die
Prüfungen auf diese bereits zugelassenen Adressen beschränkt. Ohne
`ipv6_enabled` entfallen IPv6-Adressen. Einzelmessungen:

```json
{"addressObservations": [
  {"address": "198.51.100.1", "reachable": true, "version": "7.2.3",
   "headers": {"Strict-Transport-Security": true}, "hardenings": {},
   "demoUsersDisabled": true, "error": ""}
]}
```

Die erste Adresse dient als Vergleich. Der schwerste Unterschied bestimmt den
Schweregrad: Demo-Konten wie `demoUsersDisabled`, andere Version `high`, sonstige
Abweichungen `medium`. Ausgenommene Prüfungen entfallen. Bei einer Adresse oder
ausgeschalteter Funktion gibt es keinen Befund und keine Beobachtungsliste;
siehe [ADR 0042](../../adr/0042-every-resolved-address-is-compared-only-when-the-operator-asks.md).

## Parallelität {#concurrency}

`concurrency` führt unabhängige Prüfungen einer Instanz parallel aus:

```python
result = scan("opencloud.example.com", settings=ScannerSettings(concurrency=8))
```

Der Standard `1` benötigt keine Threads. Werte über `32` werden begrenzt.
Jeder Worker erhält eine eigene `requests.Session`. Die Ergebnisse werden in
der ursprünglichen Reihenfolge zusammengeführt; Bewertung und Reihenfolge
bleiben dadurch gleich.

## TLS {#tls}

OpenClouds Proxy kann TLS selbst auf Port 9200 beenden; `opencloud init`
erzeugt dafür ein selbst signiertes Zertifikat. Der Scanner versucht:

1. HTTPS mit Zertifikatsprüfung.
2. HTTPS ohne Verifikation; `tlsTrusted` schlägt fehl.
3. HTTP; `httpsAvailable` schlägt mit kritisch fehl.

`verify_tls: false` oder `--insecure` beginnt mit Schritt 2. Die fehlende
Vertrauenskette bleibt sichtbar, zählt dann aber nicht gegen die Note.
Für eine interne CA ist `scanner.tls_ca_file` beziehungsweise
`COS_SCANNER_TLS_CA_FILE` mit einem PEM-Bundle vorzuziehen. Der Befehl
`check-opencloud-scanner scan` akzeptiert außerdem `--ca-file`.

### Messungen {#what-is-measured}

`tls.py` liefert die Messwerte und Prüfungen; die Bewertung erfolgt im Scanner.

| Kennung | Fragestellung |
|:--|:--|
| `tlsProtocol` | Mindestens TLS 1.2 ausgehandelt? |
| `tlsDeprecatedProtocol` | Werden TLS 1.0 oder 1.1 weiterhin angenommen? |
| `tlsHostname` | Passt das Zertifikat zum angefragten Namen oder zur IP-Adresse? |
| `tlsChain` | Werden die benötigten Zwischenzertifikate mitgesendet? |
| `tlsCertificate` | Ist das Zertifikat abgelaufen oder innerhalb von `tls_min_days` fällig? |
| `tlsCertificateLifetime` | Überschreitet die Laufzeit den Prüfgrenzwert von 398 Tagen? |
| `tlsCipherSuite` | Ist die ausgehandelte Cipher Suite ausreichend stark und bietet sie Forward Secrecy? |
| `tlsCertificatePolicy` | Sind Schlüsselgröße und Signaturverfahren ausreichend? |
| `tlsAddressParity` | Liefern IPv4 und IPv6 dieselbe nutzbare TLS-Identität? |
| `tlsCaaRecord` | Nennt ein CAA-Eintrag mindestens einen erlaubten Aussteller? |
| `tlsDnssec` | Ist die Zone signiert? Ohne auswertbare Resolver-Antwort entfällt der Befund |
| `cookieSecure`, `cookieHttpOnly`, `cookieSameSite` | Enthalten beobachtete Cookies diese Attribute? |
| `tlsOcspStapling` | Wird eine OCSP-Antwort mitgesendet? |

Der Block `tls` enthält Protokoll, Cipher Suite, Zertifikatsinhaber, Aussteller,
Gültigkeit, Restlaufzeit, Namen, Kettenlänge und weitere Messwerte:

```json
{
  "host": "opencloud.example.com",
  "port": 443,
  "reachable": true,
  "protocol": "TLSv1.3",
  "cipher": "TLS_AES_256_GCM_SHA384",
  "cipherBits": 256,
  "trusted": true,
  "hostnameMatch": true,
  "chainComplete": true,
  "chainLength": 2,
  "deprecatedProtocolsProbed": ["TLSv1", "TLSv1.1"],
  "deprecatedProtocolsAccepted": [],
  "ocspStapled": false,
  "ocspNote": "the certificate names no OCSP responder",
  "certificate": {
    "subject": "opencloud.example.com",
    "issuer": "Example CA R3",
    "serialNumber": "03A1...",
    "notBefore": "2026-06-01T00:00:00+00:00",
    "notAfter": "2026-08-30T00:00:00+00:00",
    "daysRemaining": 9,
    "lifetimeDays": 90,
    "altNames": ["opencloud.example.com"],
    "ocspResponders": [],
    "selfSigned": false,
    "keyType": "RSA",
    "keyBits": 2048,
    "signatureAlgorithm": "sha256WithRSAEncryption"
  }
}
```

`null` bedeutet „nicht ermittelt“. Fehlende Laufzeitunterstützung, ein nicht
vorhandenes `openssl` oder ein fehlender OCSP-Responder können einzelne
Prüfungen verhindern. Sie werden dann nicht als bestanden ausgewiesen; siehe
[ADR 0013](../../adr/0013-transport-security-is-measured-not-assumed.md).

Auch ein nicht vertrauenswürdiges Zertifikat wird auf Ablauf, Namen und
Laufzeit untersucht. `probe_deprecated` öffnet zusätzliche Handshakes für alte
Protokolle. `check_stapling` verwendet `openssl s_client` mit festen Argumenten
und ohne Shell.

## Aufgaben außerhalb der Bibliothek {#what-this-package-does-not-do}

- Der Scanner arbeitet direkt gegen die Instanz. Es gibt keinen auswählbaren
  entfernten Bewertungsdienst und keinen Ergebnis-Cache.
- Audit-Protokollierung und geschützte Anwendungseinstellungen benötigen eine
  gesonderte Prüfung mit geeigneten Zugriffsrechten.
- Maßnahmen werden beobachtet und nicht aus einer Versionsmatrix abgeleitet.
- Reguläre Benutzerzugänge sind nicht erforderlich. Die einzige
  Zugangsdatenprüfung betrifft die dokumentierten Demo-Konten.
- Die Prüfpfade entsprechen OpenClouds Architektur: Graph- und OCS-API,
  Debug-Ports, `opencloud.yaml`, `proxy/server.key` und IDM-Datenbank.

## Direkte Verwendung {#using-it-directly}

```python
from opencloud_local_scan import ScannerSettings, scan

result = scan("opencloud.example.com", settings=ScannerSettings(timeout=10))
print(result["rating"], result["version"], result["extraChecks"])
```

`scan()` wirft `ScanError`, wenn sich die Instanz nicht als OpenCloud erkennen
lässt: etwa bei fehlender Erreichbarkeit, ungültigem JSON, fehlenden
Versionsfeldern oder einem anderen Produkt. Antwortet ein Dienst, ist dafür die
Unterklasse `NotOpenCloud` vorgesehen.

Standardmäßig versucht der Scanner nach einer ungeeigneten HTTPS-Antwort auch
HTTPS ohne Verifikation und anschließend HTTP.
`ScannerSettings(stop_when_not_opencloud=True)` beendet den Versuch nach der
ersten solchen Antwort. Der öffentliche Webdienst verwendet diese Einstellung.

`addresses` enthält die während des Scans aufgelösten Adressen:

```json
{"addresses": {"ipv4": ["198.51.100.7"], "ipv6": ["2001:db8::7"]}}
```

Die Liste ist Kontext und verändert die Note nicht. Bei `pinned_addresses`
werden genau die zugelassenen Adressen ausgegeben, ohne erneute Auflösung.

`ScannerSettings` und `ReleaseSettings` lassen sich aus YAML, JSON,
Umgebungsvariablen und Secret-Providern aufbauen. Siehe
[Beispielkonfiguration](../../config/check-opencloud-security.example.yml) und
[Konfiguration](../../README.md#configuration-file-and-secrets).
`check-opencloud-scanner configure` unterstützt die Einrichtung interaktiv.

Ein Scan ohne Netzwerkabrufe außerhalb der Instanz:

```python
from opencloud_local_scan import ReleaseSettings, ScannerSettings, scan

result = scan(
    "opencloud.example.com",
    settings=ScannerSettings(verify_tls=False, vulnerability_feed=None),
    release_settings=ReleaseSettings(mode="bundled"),
)
```

## Eine Korrektur ohne vollen Scan prüfen {#verifying-a-fix-without-a-full-scan}

`opencloud_local_scan.verification.verify` misst nur die übergebenen Befunde
neu und führt dafür ausschließlich die Proben des Scanners aus, die sie
erzeugen. Darauf baut `--verify-remediation` auf (siehe [ADR 0072](../../adr/0072-remediation-verification-re-measures-named-findings-without-a-full-scan.md)).

```python
from opencloud_local_scan.verification import verify

document = verify(
    "opencloud.example.com",
    ["Strict-Transport-Security", "exposed"],
)
for entry in document["results"]:
    print(entry["id"], entry["passed"], entry["reason"])
```

Das Dokument enthält `domain`, `url`, `verifiedAt`, `probeGroups` (die
tatsächlich gelaufenen Gruppen) und `results` mit einem Eintrag pro ID:
`id`, `verifiable` (false für IDs, die nur ein voller Scan klären kann, etwa
`eol` oder `vulnerability:...`), `passed` (`None`, wenn nichts gemessen
wurde), `group`, `checks` in der Form der `extraChecks`-Einträge und
`reason`. Wie `scan()` misst die Funktion nur und bewertet nicht: keine
Bewertung, keine Waivers. `probe_group(id)` sagt dir vorab, welche Gruppe
eine ID misst.

## Vergleich mit dem letzten Scan {#comparing-a-scan-with-the-last-one}

`opencloud_local_scan.baseline` speichert pro Host die vergleichbaren Befunde:
Schwachstellen, veränderbare und nicht ausgenommene Schutzmaßnahmen,
fehlgeschlagene Zusatzprüfungen sowie ein ausstehendes Update.
Darauf beruhen `--baseline` und `--warn-on-new`:

```python
from opencloud_local_scan import load_baseline, scan, snapshot_of

result = scan("opencloud.example.com")
store = load_baseline("/var/lib/check_opencloud/baseline.json")
comparison = store.compare("opencloud.example.com", snapshot_of(result))

if comparison.regressed:
    print(comparison.summary())

store.record("opencloud.example.com", snapshot_of(result))
store.save()
```

`Comparison.regressed` ist beim ersten Lauf, bei neuen Befunden, bei einer
schlechteren Note und bei einem abgelaufenen Release wahr. Ein abgelaufenes
Release bleibt damit auch nach mehreren unveränderten Scans ein Alarmgrund.

Zeitstempel, Laufzeit und Versionszeichenfolge gehören nicht zum Vergleich.
Die Datei wird atomar und nur für den Eigentümer lesbar geschrieben.
Beschädigte oder unbekannte Formate gelten als fehlende Baseline; die normale
Prüfung bleibt möglich.

## Marken und Unabhängigkeit

Dies ist ein unabhängiges Community-Projekt. Es ist nicht mit OpenCloud GmbH
verbunden und wird von ihr nicht unterstützt. OpenCloud und zugehörige Marken
gehören ihren jeweiligen Inhabern und benennen hier die geprüfte Software.
