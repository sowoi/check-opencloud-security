# Den OpenCloud Security Scanner als Webdienst betreiben

Der Webdienst führt den eingebauten Scanner aus und zeigt die Bewertung von
**A+** bis **F** im Browser. Ergebnisse bleiben standardmäßig eine Stunde in
Redis verfügbar. Der Scanner ist derselbe wie im Monitoring-Plugin.

Unter [scan.example.com](https://scan.example.com) steht eine öffentliche Installation
bereit. Eine eigene Installation erlaubt passende Netzwerkanbindung und selbst
gewählte Betriebsgrenzen. Du erhältst den Webdienst als Release-Archiv
`check_opencloud_security_web.tar.gz` oder als Container-Image. Das PyPI-Paket
enthält ausschließlich Plugin und Scanner-Bibliothek.

Der Stack besteht aus FastAPI, ARQ-Worker und Redis. Parallelität und Zeitlimits
legt der Betreiber fest. Besucher benötigen für öffentliche Scans kein Konto.

Die Oberfläche ist auf Deutsch, Englisch, Französisch und Spanisch verfügbar.
Die erste Auswahl folgt der Browsersprache; der Sprachschalter speichert eine
bewusste Auswahl in einem `HttpOnly`-/`SameSite=Lax`-Cookie. Die Leitfäden stehen
in allen vier Sprachen bereit. API-Dokumente, Exportdaten und
Scan-Befunde behalten ihre technischen Originalwerte.

## Inhalt {#contents}

Die Abschnitte behandeln Einrichtung, Konfiguration, Schutzmaßnahmen und die
HTTP-API. Das Inhaltsverzeichnis der Webansicht führt direkt zu jedem Abschnitt.

## Starten {#starting-it}

Der Setup-Assistent erstellt einen Stack aus Webanwendung, Worker und Redis.
Er benötigt nur Python mit Standardbibliothek und lässt sich ohne Checkout ausführen:

```bash
mkdir opencloud-scanner && cd opencloud-scanner

base=https://github.com/sowoi/check-opencloud-security/releases/latest/download
curl -fsSLO "$base/setup-wizard.py" -O "$base/setup-wizard.py.sha256"
sha256sum --check setup-wizard.py.sha256    # macOS: shasum -a 256 --check
chmod +x setup-wizard.py
./setup-wizard.py --version
./setup-wizard.py

docker compose up -d
# http://127.0.0.1:8811
```

Nicht geheime Einstellungen stehen kommentiert in der Compose-Datei.
Zugangsdaten schreibt der Assistent in eine nur für den Eigentümer lesbare `.env`.

### Mit den mitgelieferten Compose-Dateien {#or-the-compose-files-this-project-ships}

Für das veröffentlichte Image:

```bash
git clone https://github.com/sowoi/check-opencloud-security.git
cd check-opencloud-security/docker

printf 'COS_REDIS_PASSWORD=%s\n' "$(openssl rand -base64 36 | tr -d '/+=')" > .env
chmod 600 .env

docker compose -f docker-compose.dockerhub.yml up -d
# http://127.0.0.1:8811
```

Zum Bauen aus dem Checkout verwende `docker compose up --build -d` ohne
`-f`. Vor öffentlicher Nutzung prüfe insbesondere:

- `COS_WEB_PUBLIC_BASE_URL`: die tatsächliche öffentliche Adresse statt localhost.
- `COS_REDIS_PASSWORD`: Schutz des Speichers für laufende Scans und Ergebnisse.
- `COS_WEB_TRUST_FORWARDED_FOR`: nur hinter einem eigenen Proxy aktivieren und
  `COS_WEB_TRUSTED_PROXY_HOPS` passend setzen.

Das Image `okxo/opencloud-scanner` unterstützt amd64 und arm64. `latest` und
Versions-Tags folgen Releases; `edge` folgt `main`. Webanwendung und Worker
verwenden dasselbe Image mit unterschiedlichen Startbefehlen.
Ein einzelner Container benötigt die Adresse des gemeinsam genutzten Redis und
die öffentliche Basis-URL:

```bash
docker run --rm -p 8811:8811 \
    -e COS_WEB_REDIS_URL="redis://:PASSWORD@redis:6379/0" \
    -e COS_WEB_PUBLIC_BASE_URL=http://127.0.0.1:8811 \
    okxo/opencloud-scanner:latest
```

Weitere Varianten beschreibt die [Docker-Dokumentation](../../docker/README.md).

### Ohne Container {#without-containers}

Starte aus dem Checkout Redis, Webanwendung und Worker getrennt:

```bash
pip install ".[web,mcp]"    # the mcp extra is optional; it serves /mcp
valkey-server &
COS_WEB_REDIS_URL=redis://127.0.0.1:6379/0 python -m webapp.tasks &
COS_WEB_REDIS_URL=redis://127.0.0.1:6379/0 \
    uvicorn webapp.app:app --host 127.0.0.1 --port 8811
```

Ein eigenes Release-Archiv baue mit:

```bash
python scripts/build_web_bundle.py
# dist/check_opencloud_security_web.tar.gz  (+ .sha256)
```

### Eine eigene Installation konfigurieren {#a-deployment-of-your-own}

Der Assistent unterstützt unter anderem eigene Ports, interne Ziele,
Ergebnisverschlüsselung und MCP-Anmeldung:

```bash
cd docker
./setup-wizard.py --output-dir ~/opencloud-scanner
```

`generate` erzeugt benötigte Geheimnisse. `--preset private` wählt Vorgaben für
eine interne Installation, `--non-interactive` übernimmt die vorgegebenen Werte.

`--sign-in` aktiviert die Token-Prüfung auf `/mcp` und fragt Issuer, Audience und
Schlüsselquelle ab. `--with-authentik` stellt einen Provider samt Datenbank und
Blueprints bereit. Die Optionen sind unabhängig: Ein bereitgestellter Provider
aktiviert für sich allein noch keinen Zugriffsschutz. Wähle beide, wenn der
neue Provider MCP schützen soll, und teste die Token-Prüfung vor Freigabe.

Bei interaktiver Einrichtung bietet der Assistent Authentik an, wenn MCP-Anmeldung
oder Operator-Bereich gewünscht sind. Er fragt auch SMTP ab; das Passwort kommt
aus `AUTHENTIK_EMAIL_PASSWORD`. Die [Docker-Anleitung](../../docker/README.md#the-setup-wizard)
beschreibt alle Optionen. `check-opencloud-security --configure` richtet dagegen
einen Monitoring-Check ein.

## Zulässige Besuchereingaben {#what-a-visitor-can-ask-for}

| Feld | Bedeutung |
|:--|:--|
| `target_url` | Hauptadresse als Hostname oder HTTP(S)-URL, optional mit Port; erforderlich |
| `ignore_hardenings` | Ausnahmen aus dem vorgegebenen Katalog |
| `release_track` | `auto`, `rolling`, `production`, `lts`; Standard `auto` |
| `output_format` | `dashboard`, `json`, `csv`, `sarif`, `pdf` |

`auto` bestimmt den Kanal anhand des Release-Zeitplans. Ein unbekannter Wert
fällt auf den Standard zurück. Andere Felder werden mit **422** zurückgewiesen.
Parallelität, Worker-Zahl, Zeitlimits und TLS-Verifikation bleiben Betreiberoptionen.

Das Ziel darf keine Zugangsdaten, Query, Fragmente, Leer- oder Steuerzeichen
enthalten. Die Pfade der einzelnen Prüfungen bestimmt der Scanner.
Ausnahmen sind auf erlaubte Kennungen begrenzt; Wildcards wie `*` und
`debugPort:*` sowie nicht veränderbare Merkmale werden nicht angeboten.

## Konfiguration {#configuration}

Die Einstellungen werden beim Start aus Umgebungsvariablen gelesen.

| Variable | Standard | Bedeutung |
|:--|:--|:--|
| `COS_WEB_REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis-Adresse mit Zugangsdaten; memory:// nur zur Erprobung in einem Prozess |
| `COS_WEB_RESULT_TTL` | `3600` | Aufbewahrungszeit der Scan-Daten in Sekunden |
| `COS_WEB_COMPARISON_TTL` | `300` | Aufbewahrungszeit für Upload-Vergleiche; höchstens 300 Sekunden |
| `COS_WEB_MAX_WORKERS` | `5` | Gleichzeitig laufende Scans |
| `COS_WEB_SCAN_CONCURRENCY` | `4` | Gleichzeitige Prüfungen innerhalb eines Scans |
| `COS_WEB_SCAN_TIMEOUT` | `15` | Zeitlimit je HTTP-Prüfung in Sekunden |
| `COS_WEB_JOB_TIMEOUT` | `180` | Zeitlimit je vollständigem Scan in Sekunden |
| `COS_WEB_VERIFY_TLS` | `true` | Zertifikat prüfen; eine fehlende Vertrauenskette bleibt auch ohne Verifikation sichtbar |
| `COS_WEB_ALLOW_PRIVATE_TARGETS` | `false` | Interne Ziele zulassen; für entsprechend beschränkte eigene Installationen |
| `COS_WEB_ALLOWED_HOSTS` | *leer* | Ausnahmen vom SSRF-Schutz als Hostnamen, getrennt durch Semikolon |
| `COS_WEB_BLOCKED_TARGETS` | *leer* | Ausgeschlossene Namen, Domain-Suffixe oder CIDR-Netze; hat Vorrang vor Freigaben |
| `COS_WEB_CHECK_DEBUG_PORTS` | `false` | Zusätzliche Debug-Ports prüfen; für öffentliche Installationen standardmäßig aus |
| `COS_WEB_IPV6_ENABLED` | `false` | Ausgehendes IPv6 verwenden; nur aktivieren, wenn der Scan-Host IPv6 erreicht |
| `COS_WEB_IP_RATE_LIMIT` | `10` | Scans je Client und Zeitfenster; 0 deaktiviert das Limit |
| `COS_WEB_IP_RATE_WINDOW` | `60` | Dauer des Client-Zeitfensters in Sekunden |
| `COS_WEB_TARGET_COOLDOWN` | `300` | Mindestabstand zwischen Scans desselben Ziels; 0 deaktiviert ihn |
| `COS_WEB_PROBE_LIMIT` | `5` | Fehlversuche vor einer Netzsperre; in Webanwendung und Worker setzen; 0 deaktiviert |
| `COS_WEB_PROBE_WINDOW` | `300` | Zeitfenster für Fehlversuche in Sekunden |
| `COS_WEB_PROBE_BLOCK` | `3600` | Dauer der ersten Netzsperre in Sekunden |
| `COS_WEB_PROBE_BLOCK_MAX` | `86400` | Höchstdauer einer wiederholten Netzsperre |
| `COS_WEB_PROBE_REPEAT_WINDOW` | `86400` | Zeitraum nach Sperrende, in dem eine erneute Sperre verlängert wird; 0 deaktiviert die Verlängerung |
| `COS_WEB_PROBE_IPV4_PREFIX` | `24` | IPv4-Netzgröße für Probe-Sperren; 32 zählt Einzeladressen |
| `COS_WEB_CLIENT_IPV6_PREFIX` | `64` | IPv6-Netzgröße für alle Client-Limits |
| `COS_WEB_DAILY_SCAN_LIMIT` | `50` | Scans je Client und Tag; 0 deaktiviert das Tageslimit |
| `COS_WEB_DNS_CONSISTENCY_CHECK` | `true` | Zwei DNS-Antworten verlangen, die mindestens eine Adresse gemeinsam haben |
| `COS_WEB_REQUIRE_APPROVAL` | `false` | Nur ausdrücklich freigegebene Instanzen scannen |
| `COS_WEB_APPROVED_TARGETS` | *leer* | Freigegebene Hostnamen, Domain-Suffixe, IP-Adressen und CIDR-Netze, getrennt durch Semikolon |
| `COS_WEB_APPROVAL_DNS` | `true` | DNS-TXT-Freigabe für den Hostnamen dieses Scandienstes akzeptieren |
| `COS_WEB_MAX_BATCH_TARGETS` | `10` | Höchste Anzahl Ziele je Batch; jedes Ziel zählt einzeln gegen die Limits |
| `COS_WEB_TRUST_FORWARDED_FOR` | `false` | Client-Adresse aus X-Forwarded-For lesen; nur hinter einem eigenen Proxy |
| `COS_WEB_TRUSTED_PROXY_HOPS` | `1` | Anzahl eigener vorgeschalteter Proxys; Header wird von rechts gelesen |
| `COS_WEB_RATE_LIMIT_SALT` | *zufällig je Prozess* | Gemeinsames Geheimnis für Limit- und Cooldown-Schlüssel; bei mehreren Webprozessen überall identisch setzen |
| `COS_WEB_PUBLIC_BASE_URL` | *erforderlich* | Öffentliche Origin für kanonische Links, Sitemap und Discovery; erforderlich |
| `COS_WEB_INDEX_META_TAG` | *leer* | Bis zu zehn geprüfte name=content-Metadatenpaare, getrennt durch Semikolon |
| `COS_WEB_ALLOW_INDEXING` | `true` | Indexierung öffentlicher Inhaltsseiten erlauben; Ergebnisse bleiben ausgeschlossen |
| `COS_WEB_RELEASES_MODE` | `off` | Release-Feed-Modus: off, auto, feed oder bundled |
| `COS_WEB_RELEASES_TOKEN` | *nicht gesetzt* | GitHub-Token für ein höheres Feed-Abruflimit |
| `COS_WEB_SCHEDULE_REFRESH` | `true` | Release-Zeitplan beim Start und täglich aktualisieren |
| `COS_WEB_SCHEDULE_REFRESH_URL` | *OpenCloud-Lifecycle-Seite* | Quelle des Release-Zeitplans; ein eigener Spiegel ist möglich |
| `COS_WEB_SCHEDULE_REFRESH_HOUR` | `4` | UTC-Stunde der täglichen Aktualisierung |
| `COS_WEB_ADVISORY_REFRESH` | `true` | Sicherheitsmeldungen beim Start und täglich ergänzen |
| `COS_WEB_ADVISORY_REFRESH_URL` | `https://api.osv.dev/v1/query` | Quelle der Sicherheitsmeldungen |
| `COS_WEB_ADVISORY_REPOSITORY_URL` | `https://api.github.com/repos/opencloud-eu/opencloud/security-advisories` | OpenClouds Repository-Sicherheitsmeldungen, die OSV nie erreicht haben; `off` schaltet sie ab |
| `COS_WEB_FRONTEND_DIR` | *neben `webapp/`* | Verzeichnis der Templates und statischen Dateien |
| `COS_WEB_ENABLE_DOCS` | `false` | Interaktive API-Ansichten /docs und /redoc bereitstellen; maschinenlesbare Verträge bleiben öffentlich |
| `COS_WEB_ENABLE_MCP` | `true` | MCP und Browser-WebMCP aktivieren; erfordert das optionale MCP-Paket |
| `COS_WEB_MCP_ALLOWED_HOSTS` | *leer* | Erlaubte Host-Header für MCP, getrennt durch Semikolon; leer deaktiviert diese Prüfung |
| `COS_WEB_MCP_MAX_CONCURRENT_WAITS` | `8` | Gleichzeitig wartende MCP-Aufrufe; weitere Aufträge geben ihre UUID zum Abfragen zurück |
| `COS_WEB_MCP_AUTH_ENABLED` | `false` | Gültiges Provider-Token für /mcp verlangen |
| `COS_WEB_MCP_AUTH_ISSUER` | *leer* | Issuer aus der OIDC-Discovery; abschließender Schrägstrich wird toleriert |
| `COS_WEB_MCP_AUTH_AUDIENCE` | *leer* | Erwartete Audience; bei aktiver Anmeldung zwingend erforderlich |
| `COS_WEB_MCP_AUTH_JWKS_URL` | *abgeleitet* | Adresse der öffentlichen Signaturschlüssel; Standard ist <issuer>/jwks/ |
| `COS_WEB_MCP_AUTH_RESOURCE_URL` | *abgeleitet* | Öffentliche Adresse der geschützten MCP-Ressource; Standard ist <COS_WEB_PUBLIC_BASE_URL>/mcp |
| `COS_WEB_MCP_AUTH_SCOPES` | *leer* | Zusätzlich geforderte Scopes, getrennt durch Semikolon |
| `COS_WEB_ADMIN_ENABLED` | `false` | Operator-Bereich aktivieren; ausgeschaltet werden seine Routen nicht registriert |
| `COS_WEB_ADMIN_PROXY_SECRET` | *nicht gesetzt* | Gemeinsames Geheimnis für X-COS-Admin-Proxy; bei aktivem Bereich mindestens 32 Zeichen |
| `COS_WEB_ADMIN_USERS` | *leer* | Erlaubte Authentik-Benutzernamen, getrennt durch Semikolon; bei aktivem Bereich nicht leer |
| `COS_WEB_ADMIN_SIGN_OUT_URL` | *nicht gesetzt* | Abmeldepfad des vorgeschalteten Providers; lokaler Pfad oder HTTP(S)-URL |
| `COS_WEB_ADMIN_AUDIT_BUFFER` | `200` | Anzahl Audit-Einträge für die Liveansicht bei stdout-Protokollierung; 0 speichert keine |
| `COS_WEB_ADMIN_REFRESH_COOLDOWN` | `60` | Mindestabstand zwischen manuellen Aktualisierungen derselben Quelle; Testabruf hat einen eigenen Zähler |
| `COS_WEB_UPDATE_CHECK` | `true` | Fragt GitHub, ob es ein neueres Release dieses Dienstes gibt - nur für den Betreiberbereich und höchstens alle sechs Stunden. Ohne ausgehenden Zugang setzt du `false` |
| `COS_WEB_ADMIN_UPDATE_DIR` | *nicht gesetzt* | Ein beschreibbares tmpfs (die Compose-Dateien hängen eins unter `/var/lib/opencloud-scan/update` ein). Gesetzt, kannst du im Betreiberbereich ein neueres Release installieren: Das Web-Bundle wird von GitHub geladen, gegen seine Build-Attestierung geprüft, hier entpackt, und Web- und Worker-Prozesse starten damit neu - kurze Ausfallzeit, gültig bis zum Neustart der Container. Nicht gesetzt, zeigt der Bereich nur an, dass es ein Update gibt |
| `COS_WEB_AUDIT_LOG` | `false` | Separates Audit-Log für angenommene und abgewiesene Anfragen sowie Limits |
| `COS_WEB_AUDIT_LOG_TARGETS` | `false` | Zielhostnamen im Audit-Log im Klartext erfassen; für interne Installationen |
| `COS_WEB_AUDIT_SALT` | *zufällig je Prozess* | Geheimnis für Audit-Fingerabdrücke; fester Wert ermöglicht Zuordnung über Neustarts hinweg |
| `COS_WEB_AUDIT_LOG_FILE` | *Prozessausgabe* | Audit-Datei statt Prozessausgabe; Pfad muss beschreibbar sein |
| `COS_WEB_AUDIT_LOG_MAX_BYTES` | `10000000` | Dateigröße für Rotation; 0 deaktiviert Größenrotation |
| `COS_WEB_AUDIT_LOG_BACKUPS` | `5` | Anzahl aufbewahrter rotierter Dateien |
| `COS_WEB_AUDIT_LOG_ROTATION` | `service` | Rotation durch service oder external; bei external muss der Host sie einrichten |
| `COS_WEB_PURGE_TOKEN` | *nicht gesetzt* | Löschendpunkt aktivieren und schützen; mindestens 32 Zeichen; ohne Wert antwortet er 404 |
| `COS_WEB_PURGE_SIGNING_KEY` | *nicht gesetzt* | Geheimnis zum Signieren des Löschbelegs |
| `COS_WEB_EXPORT_SIGNING_KEY` | *nicht gesetzt* | HMAC-SHA256-Signatur als Header für JSON-, CSV-, SARIF- und PDF-Exporte |
| `COS_WEB_ENCRYPT_RESULTS` | `false` | Ergebnisdaten mit AES-256-GCM verschlüsseln; benötigt einen Schlüssel |
| `COS_WEB_WEBHOOK_SECRET` | *nicht gesetzt* | Wird eingelesen, aber vom Webdienst nicht verwendet; Webhooks gehören zum Plugin |
| `COS_WEB_ENCRYPTION_KEY_<n>` | *nicht gesetzt* | 32-Byte-Schlüssel als 64 Hexzeichen; höchste Nummer verschlüsselt, ältere entschlüsseln weiterhin |

Die Einzelabfrage des Release-Feeds ist standardmäßig aus. So entsteht nicht
für jeden öffentlichen Scan eine zusätzliche Feed-Anfrage. Der Release-Zeitplan
bleibt trotzdem Grundlage der EOL-Prüfung.

Der Worker aktualisiert Zeitplan und Sicherheitsmeldungen standardmäßig beim
Start und täglich. Ein Zeitplan darf keine bereits bekannten Release-Linien
verlieren. Sicherheitsmeldungen werden nur ergänzt; Einträge ohne Versionsgrenzen
und übermäßig große Antworten werden verworfen. Fehlgeschlagene Abrufe lassen
den letzten akzeptierten Stand bestehen. Neuere gebündelte Daten werden bei
einer erneuten Bereitstellung berücksichtigt.

Die aktualisierten Daten liegen in Redis; Repository-Dateien werden nicht
verändert. Installationen ohne ausgehenden Netzwerkzugriff können die beiden
Refresh-Funktionen abschalten. Hintergründe: [ADR 0016](../../adr/0016-the-release-schedule-refreshes-itself.md)
und [ADR 0017](../../adr/0017-the-advisory-database-refreshes-itself.md).

## Ablauf eines Scans {#how-a-scan-flows-through-it}

```text
POST /api/scans ──► client rate limit ──► SSRF guard ──► waiver allow-list
                                                              │
                          target cooldown ◄────────────────────┘
                                 │
                                 ▼
                    uuid4 ──► Redis (queued) ──► ARQ ──► 303 /scan/{uuid}
                                                          │
   worker: re-resolve ──► scan() ──► Redis (completed) ◄───┘
```

Das Client-Limit greift vor der Namensauflösung, um deren Missbrauch zu begrenzen.
Der Ziel-Cooldown wird erst nach der Validierung belegt, damit abgewiesene
Eingaben kein ungescanntes Ziel blockieren.

## Warteschlange {#queueing-rather-than-refusing}

Zulässige Aufträge erhalten eine UUID und **202**, beim Browserformular **303**.
Sind alle Worker beschäftigt, wartet der Auftrag in Eingabereihenfolge.
Die Ergebnisansicht zeigt seine Position und aktualisiert sie regelmäßig.
`COS_WEB_MAX_WORKERS` legt die gleichzeitig laufenden Scans fest; Besucher können
weder mehr Worker anfordern noch die Reihenfolge ändern.

## Trennung der Scans {#isolation-between-scans}

Jeder Scan erhält eine UUID4 und einen eigenen Namensraum:

```text
scan:{uuid}:status      queued | running | completed | failed
scan:{uuid}:result      the result document
scan:{uuid}:metadata    target, waivers, timestamps
```

Wer die UUID kennt, kann das zugehörige Ergebnis abrufen. Es gibt keine
Auflistung aller Scans. Unbekannte, ungültige und abgelaufene UUIDs liefern
dieselbe **404**. Auch während der Wartezeit erhalten die Scan-Schlüssel eine TTL.
Behandle Ergebnislinks deshalb als Zugang zum Bericht.

## Zwei Scans vergleichen {#comparing-two-scans}

`GET /compare?baseline=<uuid>&current=<uuid>` zeigt behobene, neue und weiterhin
offene Befunde sowie die Änderung der Note. Eine fertige Ergebnisseite trägt
ihre UUID bereits in den Vergleichslink ein.

Die Berechnung erfolgt über `opencloud_local_scan.baseline` und
`workflows.compare_documents`, wie beim CLI-Vergleich und MCP-Werkzeug
`compare_scans`. Solange beide Scans vorliegen, wird der Vergleich bei jedem
Aufruf neu berechnet und nicht gesondert gespeichert.

| Zustand | Antwort |
|:--|:--|
| Beide Scans abgeschlossen | 200 mit Vergleich |
| Ein Scan unbekannt oder abgelaufen | 404 mit Angabe der betroffenen Seite |
| Ein Scan noch nicht fertig | 409 |
| Zweimal dieselbe UUID | 422 |
| Unterschiedliche Instanzen | 200 mit ausdrücklichem Hinweis |

Die Seite wird nicht indexiert und bleibt außerhalb des OpenAPI-Schemas.
Siehe [ADR 0029](../../adr/0029-a-comparison-is-two-live-results-and-one-arithmetic.md).

## Vergleich mit einem hochgeladenen Bericht {#comparing-against-a-report-you-uploaded}

Mit `POST /compare` lade einen früher heruntergeladenen JSON- oder
CSV-Bericht als Ausgangsstand hoch. Die zweite Seite ist ein noch verfügbarer,
abgeschlossener Scan dieses Dienstes. Diese Funktion ist für den Browser
vorgesehen; sie besitzt keinen eigenen API- oder MCP-Aufruf.

Der Import rekonstruiert nur ausdrücklich zugelassene Felder nach Typ-, Längen-
und Strukturprüfung. Es gelten 256 KB Dateigröße, striktes UTF-8, höchstens
2.000 CSV-Zeilen, 20 JSON-Ebenen, 500 Listeneinträge und 300 Zeichen pro String.
Das Format wird am Inhalt erkannt; der Dateiname wird nicht übernommen.
Unbekannte Befundkennungen werden ausgelassen und gezählt. Cross-Site-POSTs
werden abgewiesen, Uploads haben ein eigenes Client-Limit.

Informationen, die ein älteres CSV nicht enthält, werden auf beiden Seiten vom
Vergleich ausgeschlossen und auf der Seite benannt. JSON erhält mehr Details
als das flache CSV-Format.

Die Datei bleibt nur während des Imports im Arbeitsspeicher. Der daraus
berechnete Vergleich wird unter einer neuen UUID im Namensraum `compare:{token}:*`
für höchstens fünf Minuten gespeichert. `COS_WEB_COMPARISON_TTL` kann die Frist
verkürzen. Ergebnisverschlüsselung gilt auch hier. Löschanforderungen erfassen
Vergleiche, die die Instanz auf einer der beiden Seiten nennen.

Ein erfolgreicher Upload führt per **303** zu `/compare/{token}`. Fehlende oder
ungeeignete Angaben ergeben **422**, zu große Uploads **413**, abgelaufene Scans
**404**, laufende Scans **409** und überschrittene Limits **429**. Nach Ablauf
liefert auch der Vergleichslink **404**. Siehe
[ADR 0057](../../adr/0057-an-uploaded-report-is-evidence-not-a-scan.md).

## Schutz vor SSRF {#the-ssrf-guard}

Der Dienst prüft Ziele vor jeder Verbindung. Zulässig sind HTTP und HTTPS;
Zugangsdaten, Querys und Fragmente werden abgewiesen. Öffentliche Installationen
verlangen, dass alle aufgelösten Adressen öffentliche Unicast-Adressen sind.
Interne Namen, Metadatenadressen sowie bekannte Wildcard- und Rebinding-DNS-Dienste
werden zusätzlich anhand des Namens gesperrt.

Mit `COS_WEB_DNS_CONSISTENCY_CHECK` erfolgen zwei Auflösungen. Ohne gemeinsame
Adresse wird das Ziel zurückgewiesen. Der Worker prüft es unmittelbar vor dem
Scan erneut; Verbindungen werden auf die geprüften Adressen festgelegt und
Weiterleitungen erneut validiert.

Für eine interne Installation können `COS_WEB_ALLOWED_HOSTS` gezielte Ausnahmen
oder `COS_WEB_ALLOW_PRIVATE_TARGETS` eine weitergehende Freigabe erlauben.
Die ausdrücklichen Ausschlüsse gelten weiterhin.

### Ziele ausschließen {#addresses-this-deployment-will-not-scan}

`COS_WEB_BLOCKED_TARGETS` sperrt Ziele unabhängig davon, ob sie sonst öffentlich
oder freigegeben wären:

```bash
COS_WEB_BLOCKED_TARGETS="opencloud.example.com;.example.org;203.0.113.0/24"
```

Erlaubt sind Hostnamen, Domain-Suffixe mit führendem Punkt oder `*.`, IP-Adressen
und CIDR-Netze. Suffixe schließen die Domain selbst ein. Namen werden als Namen
verglichen, Netze mit jeder aufgelösten Adresse. Verwende eine Netzsperre,
wenn auch andere Namen für dieselbe Adresse gesperrt sein sollen.

Die Prüfung erfolgt bei Annahme, vor dem Scan und bei Weiterleitungen.
Ungültige Einträge oder mehr als 253 Zeichen verhindern den Start.
Besucher erfahren nur, dass das Ziel ausgeschlossen wurde, nicht den passenden
Konfigurationseintrag. Siehe [ADR 0043](../../adr/0043-an-operators-exclusion-outranks-every-allowance.md).

Der Operator-Bereich kann weitere Einträge in Redis verwalten. Sie gelten ab der
nächsten Anfrage in allen Prozessen, auch für wartende Aufträge. Einträge aus
der Umgebung lassen sich dort nicht entfernen; äquivalente Schreibweisen werden
als derselbe Ausschluss behandelt. Dauerhafte Vorgaben gehören in die Umgebung,
da Redis-Einträge bei Verlust des Speichers verschwinden können.

Ist die Ausschlussliste nicht lesbar, wird die Anfrage mit **503** abgewiesen.
Siehe [ADR 0044](../../adr/0044-the-operator-area-may-write-the-exclusions.md) und
[Operator-Dokumentation](../../ADMIN.md#the-operators-area-at-admin).

## Nutzungsgrenzen {#rate-limiting}

Redis verwaltet drei Arten von Grenzen:

- Anfragen pro Client und Zeitfenster sowie ein Tageslimit.
- Einen Cooldown je Ziel, atomar belegt, damit gleichzeitige Anfragen nicht
  mehrere Scans derselben Instanz starten.
- Eine zeitweilige Netzsperre nach wiederholten ungeeigneten Zielen oder Scans,
  die kein OpenCloud finden beziehungsweise ihr Zeitlimit erreichen.

Überschreitungen liefern **429** mit `Retry-After`. Schlüssel enthalten
HMAC-Fingerabdrücke statt Client-Adressen. Für Minuten- und Tageslimits zählen
IPv4-Adressen einzeln; IPv6 wird standardmäßig als /64 zusammengefasst.
Die Probe-Sperre fasst IPv4 standardmäßig als /24 zusammen.

Als Fehlversuche zählen unter anderem nicht erlaubte interne Ziele,
Ausschlüsse, Rebinding-Namen, widersprüchliche DNS-Antworten und nicht genehmigte
Ziele im Freigabemodus. Wiederholte Versuche desselben Hosts zählen erneut.
Erfolgreiche Scans zählen unabhängig von ihrer Note nicht als Probe-Fehlversuch;
Tippfehler, fehlende DNS-Auflösung und unzulässige Schemata ebenfalls nicht.

Erneute Sperren innerhalb des Wiederholungsfensters dauern sechsmal länger,
bis zum eingestellten Maximum. Der Worker erhält dafür einen Fingerabdruck,
keine Client-Adresse. API und Worker verwenden dieselben Zähler. MCP-Workflows
können kurze `Retry-After`-Zeiten abwarten; längere Wartezeiten gib zurück.

Der Webdienst beendet den Scan, sobald eine Antwort ein anderes Produkt zeigt,
statt weitere Protokollvarianten zu versuchen. Bei fehlender Antwort bleiben
Wiederholungen möglich. Auch eine rechtmäßige Prüfung einer ausgefallenen
Instanz kann dadurch eine Sperre auslösen. Die Meldung verweist auf den lokal
nutzbaren Scanner. Der Operator-Bereich zeigt ausschließlich aggregierte Zahlen.

### Nur freigegebene Instanzen scannen {#approval-mode}

`COS_WEB_REQUIRE_APPROVAL=true` beschränkt Scans auf
`COS_WEB_APPROVED_TARGETS` oder eine DNS-Freigabe. Ohne Freigabe folgt **403**.
Bei aktiviertem `COS_WEB_APPROVAL_DNS` kann die Zielzone folgenden TXT-Eintrag
mit dem Hostnamen dieses Scandienstes veröffentlichen:

```text
_check-opencloud-security.opencloud.example.com. TXT "check-opencloud-security=scan.example.net"
```

Die Freigabe gilt für diese Installation. Die Abfrage verwendet den
Systemresolver; ein Fehler gilt nicht als Zustimmung. Ohne Liste und ohne
DNS-Freigabe startet ein freigabepflichtiger Dienst nicht.

Der Button **Erneut scannen** auf einem Bericht zeigt die längste noch geltende
Wartezeit aus Client-, Tages-, Ziel- und Probe-Limit. Das reine Anzeigen verbraucht
keine Freigabe. Der erneute Scan verwendet die ursprünglichen Optionen und
läuft durch dieselben Prüfungen wie eine neue Eingabe.

Ein Ziel-Cooldown verrät bei einer Ablehnung, dass diese Instanz kürzlich
geprüft wurde, jedoch nicht von wem. Wer diese Auskunft vermeiden möchte, kann
`COS_WEB_TARGET_COOLDOWN=0` setzen und sich auf Client-Limits stützen.

## Protokollierung {#what-gets-logged}

Das normale Log enthält Ablaufereignisse und UUIDs:

```text
scan_created 0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa
scan_started 0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa
scan_completed 0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa
```

Zieladressen, Client-Adressen und Ergebnisse werden dort nicht ausgegeben.

### Optionales Audit-Log {#the-optional-audit-trail}

`COS_WEB_AUDIT_LOG=true` aktiviert den separaten Logger
`check_opencloud.web.audit`, mit einem JSON-Objekt je Zeile:

```json
{"client": "9f2c1b7d4e6a0c58", "event": "scan_requested", "outputFormat": "dashboard", "releaseTrack": "production", "target": "1a4b9e0f7c23d865", "timestamp": "2026-08-19T10:14:02+00:00", "uuid": "0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa", "waivers": 0}
{"client": "9f2c1b7d4e6a0c58", "event": "rate_limited", "retryAfter": 42, "scope": "rate_limit_client", "timestamp": "2026-08-19T10:14:44+00:00"}
{"client": "3c80d5f21ab94e77", "event": "submission_rejected", "fields": ["workers"], "reason": "unsupported_fields", "status": 422, "timestamp": "2026-08-19T10:15:09+00:00"}
```

Er unterscheidet angenommene Scans (`scan_requested`), ausgelöste Limits
(`rate_limited`) und abgewiesene Eingaben (`submission_rejected`).
Client-Adressen sind stets Fingerabdrücke. Ziele ebenfalls, sofern nicht
`COS_WEB_AUDIT_LOG_TARGETS=true` für den internen Betrieb gesetzt wurde.

Ein zufälliger Salt gilt pro Prozess. `COS_WEB_AUDIT_SALT` ermöglicht die
Zuordnung über Neustarts hinweg; Rotation beendet diese Zuordnung. Schütze
einen festen Salt wie ein Geheimnis: Wer ihn kennt, kann vermutete Adressen
selbst hashen. Eingabefeldnamen werden begrenzt, von Steuerzeichen bereinigt
und als JSON maskiert.

#### Über die Container-Laufzeit hinaus aufbewahren {#keeping-the-trail-past-the-container}

Standardmäßig gehen Audit-Ereignisse an die Prozessausgabe. Für dauerhafte
Aufbewahrung verwende einen eingebundenen Speicherort:

```yaml
services:
  web_app:
    environment:
      COS_WEB_AUDIT_LOG: "true"
      COS_WEB_AUDIT_LOG_FILE: "/var/log/opencloud-scan/audit.log"
      # Rotated at this size, keeping this many generations. Together they are
      # the most the trail can ever occupy: an audit log nobody rotates fills
      # the volume it sits on and takes the service down with it.
      COS_WEB_AUDIT_LOG_MAX_BYTES: "10000000"
      COS_WEB_AUDIT_LOG_BACKUPS: "5"
    volumes:
      - audit_log:/var/log/opencloud-scan

volumes:
  audit_log:
```

Die Datei ersetzt die Audit-Ausgabe auf stdout; sie erzeugt keine zweite Kopie.
Datei und rotierte Generationen sind nur für den Eigentümer lesbar.
Ein nicht beschreibbarer Pfad verhindert den Start.

Ein benanntes Volume ist direkt verwendbar. Ein Host-Verzeichnis für einen
Bind-Mount muss vorher vorhanden und für Container-UID 10001 beschreibbar sein:

```bash
mkdir -p /srv/opencloud-scan/audit
sudo chown 10001 /srv/opencloud-scan/audit
```

Bei Rootless Docker setze die Eigentumsrechte innerhalb des User-Namespace:

```bash
docker run --rm --user 0 --entrypoint chown \
  -v /srv/opencloud-scan/audit:/target valkey/valkey:9.1-alpine 10001 /target
```

Verwende ein anderes Verzeichnis als für Redis, das mit anderer UID schreibt.

#### Rotation durch logrotate {#letting-the-hosts-logrotate-keep-it}

`COS_WEB_AUDIT_LOG_ROTATION=external` überlässt die Rotation dem Host.
Der Dienst erkennt ersetzte Dateien und öffnet sie erneut. Der Setup-Assistent
kann dazu eine Richtlinie schreiben:

```
/srv/opencloud-scan/audit/audit.log {
    daily
    rotate 30
    dateext
    missingok
    notifempty
    compress
    delaycompress
    create 0600 10001 10001
}
```

```bash
sudo install -m 0644 -o root -g root opencloud-scan-audit.logrotate \
    /etc/logrotate.d/opencloud-scan-audit
sudo logrotate --debug /etc/logrotate.d/opencloud-scan-audit   # changes nothing
```

`create 0600 10001 10001` hält die Ersatzdatei für den Container beschreibbar und
für andere unlesbar. Verwende kein `copytruncate`, da zwischen Kopieren und
Kürzen Einträge verloren gehen können. Genau eine Stelle darf rotieren:
entweder `service` oder eine installierte externe Richtlinie.

Anfragekörper sind vor dem Parsen auf 1 MiB und 30 Sekunden begrenzt.
Zu große Eingaben ergeben **413**, unvollständige **408**. Ergänzende
Verbindungs- und Bandbreitengrenzen gehören an den Proxy.

Jeder Scan läuft in einem Kindprozess. Bei Timeout oder Abbruch beendet der
Worker diesen samt Probe-Threads, bevor er einen weiteren Auftrag übernimmt.
Plane Speicher und PID-Limits für einen zusätzlichen Python-Prozess pro
aktivem Scan ein; siehe [ADR 0053](../../adr/0053-a-scan-timeout-ends-its-process.md).

## Reverse Proxy {#putting-it-behind-a-reverse-proxy}

Der [Proxy-Leitfaden](../reverse-proxy.md) enthält Konfigurationen für nginx,
Apache httpd, Caddy, Traefik und HAProxy. Der Assistent kann die ersten vier
erzeugen, einschließlich TLS, MCP-Streaming und gegebenenfalls Forward Auth.

Aktiviere `COS_WEB_TRUST_FORWARDED_FOR` nur hinter einem eigenen Proxy.
`COS_WEB_TRUSTED_PROXY_HOPS` zählt von rechts im `X-Forwarded-For`-Header.
Zu wenige Hops fassen Besucher unter einer Proxy-Adresse zusammen; zu viele
können einen vom Client vorgegebenen Wert als Adresse übernehmen.
Ungültige IP-Einträge werden ignoriert.

Die Anwendung liefert eigene Sicherheitsheader und lädt CSS, JavaScript,
Symbole und Schriften lokal. Eine zusätzliche Proxy-CSP muss damit vereinbar
sein; pauschale Freigaben für externe Ressourcen sind nicht erforderlich.

## HTTP-API {#the-http-api}

### `POST /api/scans` {#post-apiscans}

```bash
curl -sS -X POST http://127.0.0.1:8811/api/scans \
  -H 'Content-Type: application/json' \
  -d '{"target_url": "https://opencloud.example.com",
       "ignore_hardenings": ["cspWithoutUnsafeInline"]}'
```

```json
{"uuid": "0f4a1f22-...", "state": "queued", "url": "/scan/0f4a1f22-..."}
```

Ohne Schema gilt HTTPS. Antworten: **202** bei Annahme, **400** bei ungeeignetem
Ziel, **403** bei fehlender Freigabe, **422** bei unbekannten Feldern und **429**
bei Limits. Das Browserformular verwendet denselben Handler unter `/` und leitet
mit **303** auf `/scan/{uuid}` weiter. `Accept: text/html` wählt die HTML-Antwort.

### `GET /api/scans/{uuid}` {#get-apiscansuuid}

```json
{
  "uuid": "0f4a1f22-...",
  "state": "queued",
  "target": "https://opencloud.example.com",
  "expiresIn": 3574,
  "queue": {"position": 2, "length": 7}
}
```

Nach Abschluss enthält die Antwort `result` mit dem Scanner-Dokument und
`summary` für die Darstellung. Unbekannte oder abgelaufene UUIDs ergeben **404**.

### `POST /api/scans/batch` {#post-apiscansbatch}

```bash
curl -sS -X POST http://127.0.0.1:8811/api/scans/batch \
  -H 'Content-Type: application/json' \
  -d '{"targets": ["https://one.example.com", "https://two.example.com"]}'
```

```json
{
  "accepted": [
    {"uuid": "0f4a1f22-...", "target": "https://one.example.com",
     "state": "queued", "url": "/scan/0f4a1f22-..."}
  ],
  "rejected": [
    {"target": "https://two.example.com", "status": 429,
     "detail": "That instance was scanned very recently...", "retryAfter": 284}
  ],
  "counts": {"submitted": 2, "accepted": 1, "rejected": 1}
}
```

`targets` ersetzt `target_url`; die übrigen Eingabefelder bleiben gleich.
Jedes Ziel durchläuft einzeln Validierung, Limits und Cooldown. Ein Batch spart
keine Freigaben. Eine Liste über `COS_WEB_MAX_BATCH_TARGETS` wird vollständig
abgewiesen, bevor Aufträge entstehen.

Sobald mindestens ein Ziel angenommen wurde, lautet die Antwort **202**.
Andernfalls entspricht sie dem Ablehnungsgrund des ersten Ziels, gegebenenfalls
mit `Retry-After`.

### `GET /api/scans/{uuid}/export/{format}` {#get-apiscansuuidexportformat}

Einen abgeschlossenen Scan kannst du als `json`, `csv`, `sarif`, `pdf` oder
`html` herunterladen. Die Pakete `remediation-md` und `remediation-html`
enthalten nur offene, behebbare Befunde und vorgeschlagene
Konfigurationsausschnitte für nginx, Caddy, Traefik, Compose und `.env`.
Für die Note, bestandene Prüfungen und Sicherheitsmeldungen verwende einen
vollständigen Bericht.

```bash
curl -sS -OJ http://127.0.0.1:8811/api/scans/0f4a1f22-.../export/pdf
```

Der `html`-Bericht ist **eine eigenständige Datei** mit eingebundener
Formatierung. Beim Öffnen stellt er keine Netzwerkanfragen. Er enthält keine
Skripte, Bilder, externen Schriftarten oder Stylesheets. Dokumentationslinks
öffnen sich nur, wenn du ihnen folgst. Enthalten sind Befunde, ausgenommene
Befunde mit ihren Begründungen, der Behebungsplan, Lücken im Prüfumfang und
die für die Bewertung verwendeten Referenzdaten. Formulare, Bedienelemente
für erneute Scans, automatische Abfragen und Lösch-Token fehlen.

Vollständige Berichte enthalten den Behebungsplan: als Zusammenfassungs- und
Schrittzeilen in CSV, unter `runs[0].properties.remediation` in SARIF, als
Planabschnitt in PDF und HTML sowie unter `remediationPlan` in JSON.
TLS-Details stehen im CSV-Kopfblock, unter `runs[0].properties.tls` in SARIF,
in den Transportabschnitten von PDF und HTML sowie unter `tls` in JSON.
Dazu gehören Protokoll, Verschlüsselungsverfahren, Zertifikatsgültigkeit und
verbleibende Tage, Vollständigkeit der Zertifikatskette und OCSP-Stapling.
`null` bedeutet, dass der Wert nicht ermittelt werden konnte, nicht dass
die Prüfung bestanden wurde.

Downloads werden auf Anfrage aus dem gespeicherten Ergebnis erzeugt. Ihre
Links funktionieren nach Ablauf des Scans nicht mehr. Bereits gespeicherte
Dateien bleiben verfügbar, aktualisieren sich nicht und werden beim Löschen
des Scans nicht entfernt. Die Antwort von `GET /api/scans/{uuid}` für einen
abgeschlossenen Scan nennt die Download-URLs unter `exports`; die Ergebnisseite
bietet dieselben Formate als Download-Schaltflächen an.

#### Signierte Exporte {#signed-exports}

Mit `COS_WEB_EXPORT_SIGNING_KEY` enthält jede Exportantwort eine HMAC-SHA256-Signatur
über die tatsächlich gesendeten Bytes:

```text
X-COS-Signature: HMAC-SHA256=d68d9da7f04a4dcf38de5c64545141dc02c50c7476e76687e74c015383f34258
```

Die Prüfung benötigt dasselbe geheime Schlüsselmaterial. Das ist keine
öffentlich prüfbare Signatur; gib den Schlüssel nicht an Besucher weiter.
Erzeuge einen langen Zufallswert:

```bash
openssl rand -hex 32
```

Speichere den Header zusammen mit der Datei:

```bash
curl -sS -D headers.txt -o result.pdf \
  http://127.0.0.1:8811/api/scans/0f4a1f22-.../export/pdf
grep -i '^x-cos-signature' headers.txt
```

Prüfe die unveränderten Download-Bytes, nicht neu formatiertes JSON:

```bash
COS_WEB_EXPORT_SIGNING_KEY='<key-from-secret-store>' \
  uv run python scripts/verify_export.py result.pdf 'HMAC-SHA256=<hex-from-header>'
```

Erfolg ergibt Exitcode 0, eine ungültige Signatur Exitcode 1. `--key-env NAME`
wählt eine andere Schlüsselvariable. Alternativ berechnet OpenSSL denselben
Digest zum Vergleich mit dem Hexwert hinter `HMAC-SHA256=`:

```bash
openssl dgst -sha256 -hmac "$COS_WEB_EXPORT_SIGNING_KEY" -r result.pdf
```

Bei Schlüsselwechsel müssen alte Schlüssel für die Prüfung alter Dateien
aufbewahrt werden. Ohne Schlüssel fehlt der Signaturheader.
Downloads antworten mit **200**, laufende Scans mit **409**, unbekannte UUIDs
oder Formate mit **404**.

### `GET /api/scans/{uuid}/badge.svg` {#get-apiscansuuidbadgesvg}

Die Note als lokal erzeugtes SVG:

```bash
curl -sS http://127.0.0.1:8811/api/scans/0f4a1f22-.../badge.svg
```

```markdown
![OpenCloud security](https://scan.example.com/api/scans/0f4a1f22-.../badge.svg)
```

Das Badge enthält nur Note und zugehörige Farbe, keine Zieladresse oder
Versionsangaben. Es nutzt keine externen Badge-Dienste oder Schriften.
Es bleibt so lange abrufbar wie der Scan: **200** nach Abschluss,
**409** während des Scans, **404** nach Ablauf oder bei unbekannter UUID.
`Cache-Control: no-store` verhindert eine vorgesehene Zwischenspeicherung.

Damit eignet es sich für einen aktuell bearbeiteten Bericht oder ein Ticket.
Für dauerhaft eingebundene README-Badges ist die standardmäßig einstündige
Aufbewahrung zu kurz. Ein dauerhafter Badge-Endpunkt je Hostname existiert nicht.

### `DELETE /api/purge` {#delete-apipurge}

Ein Betreiber kann gespeicherte Daten zu einer Instanz löschen und erhält
einen Beleg über den Vorgang:

```bash
curl -sS -X DELETE \
  -H "Authorization: Bearer $COS_WEB_PURGE_TOKEN" \
  "http://127.0.0.1:8811/api/purge?target=opencloud.example.com"
```

```json
{
  "receiptId": "8f14e45f-...",
  "issuedAt": "2025-01-30T11:04:07+00:00",
  "target": "opencloud.example.com",
  "targetFingerprint": "6c1f...",
  "deleted": {"scans": 2, "keys": 5, "queueEntries": 1, "rateLimitKeys": 1},
  "remaining": 0,
  "complete": true,
  "statement": "All scan records held for this target were deleted ...",
  "notes": ["..."],
  "signature": {"algorithm": "HMAC-SHA256", "value": "b91c..."}
}
```

Gelöscht werden passende Scan-Namensräume, Warteschlangeneinträge, Cooldown und
zwischengespeicherte Upload-Vergleiche, die das Ziel nennen. `target` akzeptiert
Hostname oder vollständige URL. `deleted` zählt entfernte Schlüssel;
`remaining` stammt aus einer erneuten Prüfung danach. `complete` bedeutet
`remaining == 0`. Heruntergeladene Dateien und ein etwaiges Audit-Log liegen
außerhalb dieses Löschvorgangs und werden in `notes` genannt.

`targetFingerprint` ist nur mit `COS_WEB_PURGE_SIGNING_KEY` gesetzt.
Den signierten Beleg prüfe mit:

```python
from webapp.purge import verify
verify(receipt, key)      # the value of COS_WEB_PURGE_SIGNING_KEY
```

Ohne `COS_WEB_PURGE_TOKEN` antwortet der Endpunkt mit **404**. Ein falsches
Geheimnis ergibt **401**, ein ungültiges Ziel **422**, ein erfolgreicher Vorgang
**200**. Auch ohne vorhandene Daten gibt es 200 mit Null-Zählern; das beschreibt
den zum Prüfzeitpunkt vorgefundenen Zustand.

### `GET /llms.txt`, `GET /openapi.json`, `GET /arazzo.json`, `GET /.well-known/ai.json` {#get-llmstxt-get-openapijson-get-arazzojson-get-well-knownaijson}

Diese Beschreibungen sind stets öffentlich. `COS_WEB_ENABLE_DOCS` steuert nur
die interaktiven Ansichten `/docs` und `/redoc`.

OpenAPI beschreibt Eingaben und Antworten, Arazzo die zusammenhängenden Abläufe.
`/.well-known/ai.json` nennt die Dokumente, MCP, Nutzungsgrenzen und den Link zum
Selbstbetrieb. Diese Discovery-Datei folgt einer Anwendungskonvention.
`/llms.txt` bietet eine kurze Markdown-Übersicht ohne Scandaten oder Auflistung.

### `POST /mcp` {#post-mcp}

MCP verwendet zustandsloses Streamable HTTP mit JSON-Antworten. Die Werkzeuge
rufen die eigene HTTP-API im Prozess auf und unterliegen denselben Grenzen.
Verfügbar sind `scan_instance`, `scan_instances`, `get_scan_result`,
`plan_remediation`, `compare_scans`, `export_scan` und `erase_instance_data`.

Prompts unterstützen typische Aufgaben wie Ergebnis erklären, Befunde priorisieren
und Änderungen prüfen. Ressourcen unter `spec://` liefern OpenAPI, Arazzo,
Discovery, Prüfkatalog und Sicherheitsmeldungen aus denselben Datenquellen wie
die Website. Wartezeiten und Fehlerbehandlung stammen aus `webapp/workflows.py`.

Das als destruktiv markierte Löschwerkzeug liest seine Berechtigung aus Headern.
Bei aktiver MCP-Anmeldung steht das Provider-Token in `Authorization`, die
Löschberechtigung in `X-Purge-Authorization`.

MCP ist standardmäßig offen. Mit `COS_WEB_MCP_AUTH_ENABLED`, Issuer und Audience
prüft der Dienst JWTs gegen die Provider-Schlüssel. Fehlende oder ungeeignete
Tokens erhalten 401 mit Verweis auf die Resource-Metadaten. Der Dienst stellt
keine Tokens aus und verwaltet keine Konten. Anleitung: [Authentik](../authentik.md).
Client-Konfigurationen stehen im [MCP-Leitfaden](../mcp.md).

### `GET /scan/{uuid}`, `GET /`, `GET /healthz` {#get-scanuuid-get-get-healthz}

Die Ergebnisansicht zeigt Befunde, Exportlinks und einen erneuten Scan mit
Wartezeitanzeige. Konfigurationsvorschläge für Compose, `.env`, nginx, Caddy und
Traefik stammen aus `opencloud_local_scan.snippets`. Sie werden serverseitig
erzeugt und bleiben auch ohne JavaScript lesbar.

Die öffentlichen Erklärseiten umfassen `/how-it-works`, `/grades`,
`/documentation`, `/search`, `/api`, `/privacy` und `/about`. `/cli` leitet auf
`/documentation#oneliner` weiter. Ergebnis- und Vergleichsseiten werden nicht
indexiert und stehen nicht im OpenAPI-Schema.

`/healthz` liefert 200 erst, wenn Redis antwortet, die Queue lesbar ist und ein
aktueller Worker-Heartbeat vorliegt. Die Antwort enthält aggregierte Angaben;
bei einer fehlenden Abhängigkeit folgt eine detailarme 503.

Die Leitfäden unter `/documentation/{slug}` werden beim Build aus Markdown in
Templates für alle vier Sprachen umgewandelt. Der laufende Dienst benötigt
weder Markdown-Parser noch Quelldateien. Die Suche liest ein lokal ausgeliefertes
JSON-Register öffentlicher Seiten. Es enthält keine Ergebnisse, UUIDs oder
Zieladressen und wird durch die Build-Automation erneuert.

Bei aktiviertem MCP können unterstützende Browser zusätzlich WebMCP nutzen:
`scan_opencloud_security` auf der Startseite sowie `get_scan_result` und
`export_scan_report` für das angezeigte Ergebnis. Auch diese Aufrufe verwenden
die öffentliche API. Fehler enthalten `ok: false`, `status`, `error`, `retryable`
und gegebenenfalls `retryAfter`.

`POST /` und `GET /scan/{uuid}` liefern mit `Accept: application/json` oder
`output_format=json` strukturierte Antworten. Normale Navigation erhält HTML.
`COS_WEB_INDEX_META_TAG` erlaubt bis zu zehn geprüfte `name=content`-Paare auf
der Startseite. Rohes HTML, doppelte oder reservierte Namen werden abgewiesen;
Semikolons trennen Einträge und sind in Werten nicht möglich.

### `GET /advisories.atom`, `GET /release-schedule.atom` {#get-advisoriesatom-get-release-scheduleatom}

Die Referenzdaten stehen auch als Atom-1.0-Feeds bereit:

```bash
curl -sS http://127.0.0.1:8811/advisories.atom
```

`/advisories.atom` enthält je Sicherheitsmeldung einen Eintrag mit Schweregrad,
Versionsbereichen und Quellenlink. `/release-schedule.atom` beschreibt je
Release-Linie Datum, Kanäle und Supportende. Abonnenten können Änderungen an
der Bewertungsgrundlage verfolgen, ohne erneut zu scannen.

Die Feeds verwenden dieselben Daten wie die öffentlichen Seiten. Fremde Titel
und Beschreibungen werden als Text maskiert. Sie enthalten weder Instanzen
noch UUIDs und akzeptieren keine Filterparameter. Ein öffentlicher Cache darf
sie eine Stunde speichern. Stabile URN-Kennungen erhalten die Zuordnung auch
bei einem Umzug des Dienstes.

### `GET /robots.txt`, `GET /agents.txt`, `GET /sitemap.xml` {#get-robotstxt-get-agentstxt-get-sitemapxml}

Diese Antworten werden aus der Konfiguration erzeugt. Die Sitemap nennt
öffentliche Inhaltsseiten und Leitfäden, niemals Ergebnisse. `robots.txt`
schließt Ergebnis-, API- und weitere technische Pfade aus und nennt die Sitemap.

`agents.txt` beschreibt Fähigkeiten gemäß der agents-txt.com-Konvention.
MCP, WebMCP und OAuth erscheinen nur, wenn diese Installation sie anbietet.
`/agents.json` liefert dieselben strukturierten Angaben wie
`/.well-known/ai.json`. Maßgeblich bleiben die API- und MCP-Verträge.

`COS_WEB_PUBLIC_BASE_URL` bestimmt die öffentliche Origin.
`COS_WEB_ALLOW_INDEXING=false` deaktiviert die Sitemap und setzt `noindex`;
`agents.txt` enthält dann keine Fähigkeiten. Ergebnisansichten bleiben
unabhängig davon von der Indexierung ausgeschlossen.

## Aufbau {#layout}

```text
webapp/                 the service
├── app.py              routes, security headers, request validation
├── settings.py         every COS_WEB_* variable
├── ssrf.py             the target guard
├── ratelimit.py        the two limits
├── audit.py            the optional audit trail, pseudonymised
├── store.py            the per-scan Redis namespace
├── queue.py            handing a scan to the worker pool
├── tasks.py            the ARQ worker
├── runner.py           the seam where a request becomes ScannerSettings
├── redis_backend.py    Redis, and the in-process stand-in for tests
├── reports.py          the CSV, SARIF and PDF exports
├── arazzo.py           the API described as executable workflows
├── documentation.py    the manifest for the generated browser documentation
├── purge.py            erasure on request, and the signed receipt for it
├── seo.py              the public page list, robots.txt, agents.txt and sitemap.xml
└── catalog.py          the waiver allow-list and the dashboard grouping

frontend/
├── static/{css,js,img} vanilla CSS, small scripts, hand-drawn SVG
└── templates/          base, index, scan, 404, and the content pages

docker/
├── Dockerfile.web      the image both web_app and arq_worker run
├── docker-compose.yml            locally built frontend, worker and Redis
├── docker-compose.dockerhub.yml  published-image frontend, worker and Redis
├── Dockerfile                    the plugin image, unrelated to the web application
└── docker-compose.monitoring.yml the plugin's own stack, also unrelated
```

Die [Webapp-README](../../webapp/README.md) beschreibt API, Entwicklung und
Template-Vertrag. Die Zuständigkeiten bleiben getrennt: Die Bibliothek misst,
das Plugin bewertet für das Monitoring, die Webanwendung stellt die Ergebnisse dar.

## Marken und Unabhängigkeit

Dies ist ein unabhängiges Community-Projekt. Es ist nicht mit OpenCloud GmbH
verbunden und wird von ihr nicht unterstützt. OpenCloud und zugehörige Marken
gehören ihren jeweiligen Inhabern und benennen hier die geprüfte Software.
