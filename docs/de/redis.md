# Redis für den Scan-Webdienst

Redis speichert Warteschlange, Scanstatus, Ergebnisse und gemeinsam genutzte Betriebsdaten des Webdienstes. Dieser Leitfaden beschreibt Verbindung, Zugriffsschutz, Speicherbedarf und Fehlersuche.

Er gilt für die [Webanwendung](../../webapp/README.md). Das CLI-Plugin benötigt kein Redis; es verbindet sich direkt mit OpenCloud und beendet sich nach dem Scan.

Die mitgelieferten Stacks nutzen **Valkey** (`valkey/valkey:9.1-alpine`), die BSD-lizenzierte Weiterführung von Redis. Das Protokoll ist dasselbe: Der Dienst heißt weiterhin `redis`, und `COS_WEB_REDIS_URL` behält das Schema `redis://`. Hast du mit dem Wizard Persistenz eingeschaltet, leere das Datenverzeichnis oder Volume einmal vor dem ersten Valkey-Start, denn Valkey lädt keine Datendatei von Redis 8.

Für den Passwortschutz der mitgelieferten Compose-Bereitstellung setze `COS_REDIS_PASSWORD` in `docker/.env` und wende die Konfiguration mit `docker compose up -d` an.

## Inhaltsübersicht {#table-of-contents}

Die folgenden Abschnitte behandeln Datenhaltung, Verbindung, Schutz und Betrieb.

## Aufgaben von Redis {#what-redis-is-used-for}

1. **Warteschlange:** Eingereichte Scans erhalten eine UUID und warten auf einen ARQ-Worker. Zusätzliche Anfragen werden auch bei ausgelasteten Workern angenommen.
2. **Scanstatus und Ergebnisse:** Die Webanwendung liest daraus Fortschritt, Metadaten und fertige Berichte für `GET /api/scans/{uuid}`.
3. **Gemeinsame Betriebsdaten:** Dazu gehören aktualisierte Referenzdaten, Worker-Heartbeat und Zähler für Ratenlimits.

Ein Neustart eines nicht persistenten Redis entfernt diesen Zustand. Neben noch verfügbaren Scans können dadurch auch temporäre Begrenzungen und über den Betreiberbereich ergänzte Ausschlüsse verloren gehen. Dauerhaft benötigte Ausschlüsse gehören in `COS_WEB_BLOCKED_TARGETS`.

## Gespeicherte Daten und Fristen {#what-is-stored-and-for-how-long}

| Schlüssel | Inhalt | Dauer |
|:--|:--|:--|
| `scan:{uuid}:status` | queued, running, completed oder failed | `COS_WEB_RESULT_TTL`, standardmäßig 3600 Sekunden |
| `scan:{uuid}:result` | Scanner-Ergebnis | `COS_WEB_RESULT_TTL` |
| `scan:{uuid}:metadata` | Ziel, Ausnahmen, Kanal und Zeitstempel | `COS_WEB_RESULT_TTL` |
| `cos:web:queue` | Wartende UUIDs | Ergebnis-TTL, mindestens eine Stunde |
| `cos:web:worker:heartbeat` | Lebenszeichen des Workers | Wird regelmäßig erneuert |
| `cos:web:rl:client:{fingerprint}` | Client-Anfragen | `COS_WEB_IP_RATE_WINDOW` |
| `cos:web:rl:target:{fingerprint}` | Zielpause | `COS_WEB_TARGET_COOLDOWN` |
| `scan:{uuid}:prober` | Zuordnung eines Scan-Ausgangs zum Client-Fingerabdruck | Höchstens Ergebnis-TTL, bis zum Start |
| `cos:web:rl:probe:{fingerprint}` | Verstöße eines Netzes | `COS_WEB_PROBE_WINDOW` |
| `cos:web:rl:blocked:{fingerprint}` | Netzsperre | `COS_WEB_PROBE_BLOCK` bis `COS_WEB_PROBE_BLOCK_MAX` |
| `cos:web:rl:blocks:{fingerprint}` | Wiederholte Sperren | Letzte Sperre plus `COS_WEB_PROBE_REPEAT_WINDOW` |
| `cos:web:rl:daily:{fingerprint}` | Tageszähler | Ein Tag |
| `cos:web:stats:{blocks,strikes,daily}:{YYYYMMDD}` | Tageszahlen für den Betreiberbereich | Acht Tage |
| `cos:web:schedule:document`, `cos:web:schedule:checked` | Aktualisierter Release-Zeitplan | Bis zur nächsten Aktualisierung |
| `cos:web:advisories:document`, `cos:web:advisories:checked` | Aktualisierte Advisory-Datenbank | Bis zur nächsten Aktualisierung |

Die UUID berechtigt zum Abruf eines Scans. Ungültige, unbekannte und abgelaufene UUIDs erhalten denselben `404`; es gibt keine öffentliche Scanliste.

Ratenlimit-Schlüssel verwenden mit `COS_WEB_AUDIT_SALT` abgeleitete Fingerabdrücke statt Klartext-Client-Adressen. Scanmetadaten enthalten während ihrer Lebensdauer jedoch die eingereichten Ziele. Schütze daher den Zugriff auf Redis. Siehe [Protokollierung](../webapp.md#what-gets-logged).

## Verbindung konfigurieren {#configuring-the-connection}

Webanwendung und Worker lesen dieselbe `COS_WEB_REDIS_URL`:

| Form | Verwendung |
|:--|:--|
| `redis://redis:6379/0` | Container ohne Passwort |
| `redis://:PASSWORD@redis:6379/0` | Passwort über `requirepass`, ohne Benutzernamen |
| `redis://user:PASSWORD@host:6379/0` | ACL-Benutzer ab Redis 6 |
| `rediss://user:PASSWORD@host:6380/0` | TLS-Verbindung |
| `memory://` | Prozessinterner Testersatz |

Kodiere Sonderzeichen wie `@`, `:`, `/` und `#` im Passwort für URLs. Die Generatoren [`docker/setup-wizard.py`](../../docker/setup-wizard.py) und [`docker/authentik-env.sh`](../../docker/authentik-env.sh) erzeugen URL-taugliche Werte.

## Ohne Redis testen {#running-without-redis}

`COS_WEB_REDIS_URL=memory://` verwendet einen Speicher im Webprozess. Er eignet sich für Tests und zum Ansehen der Oberfläche ohne zusätzliche Infrastruktur.

Dieser Modus ersetzt keine produktive Warteschlange: Ein anderer Prozess kann den Zustand nicht sehen, und ein Neustart löscht ihn. Für Webanwendung und getrennten Worker verwende Redis.

## Passwortschutz {#the-password}

Ein erreichbarer Redis ohne Zugangsschutz kann seine Daten unberechtigten Clients bereitstellen. Ein Hostscan kann dies beispielsweise so melden:

```
WARNING: Redis does not require authentication and is not protected by
network restriction
```

Setze ein Passwort:

```bash
cd docker
printf 'COS_REDIS_PASSWORD=%s\n' "$(openssl rand -base64 36 | tr -d '/+=')" >> .env
chmod 600 .env
docker compose up -d
```

Die Compose-Dateien verwenden `COS_REDIS_PASSWORD` für `--requirepass` und für die Verbindungs-URLs der beiden Anwendungscontainer. Ohne Wert bleibt der Passwortschutz aus. Für einen regulären Betrieb sollte er gesetzt sein.

Der Setup-Assistent erzeugt das Passwort in einer `.env` mit Modus `0600`. Auch `authentik-env.sh` ergänzt einen fehlenden Wert und erhält einen bereits vorhandenen.

Prüfe die wirksame Einstellung:

```bash
docker compose exec -e VALKEYCLI_AUTH= redis valkey-cli ping
# NOAUTH Authentication required.        <- what you want to see
docker compose exec redis valkey-cli ping
# PONG                                   <- authenticated, via VALKEYCLI_AUTH
```

Der Container-Healthcheck liest das Passwort über `VALKEYCLI_AUTH`, damit es nicht als `-a`-Argument in der Prozessliste erscheint.

Bei einem Passwortwechsel müssen Redis, Webanwendung und Worker dieselbe neue Konfiguration übernehmen. Deine Verbindungsdaten werden beim Start gelesen.

## Netzwerkzugriff begrenzen {#network-isolation}

Die mitgelieferten Compose-Dateien veröffentlichen keinen Redis-Port. Redis liegt nur im internen Netzwerk:

```yaml
networks:
  scanner_internal:
    internal: true
```

Webanwendung und Worker sind zusätzlich mit dem Netz für ihre ausgehenden Verbindungen verbunden. Redis benötigt diesen Zugang nicht.

Bei einer eigenen Installation begrenze den Zugriff durch Bind-Adresse, Firewall und private Netzsegmente. Veröffentliche Port 6379 nicht im Internet.

## Persistenz {#persistence-or-the-deliberate-lack-of-it}

Standardmäßig läuft Redis mit `--save ""` und `--appendonly no`. Scanergebnisse werden damit nicht durch Redis auf Datenträger geschrieben.

Snapshots und Backups können Ergebnisse über ihre TTL hinaus aufbewahren. Aktiviere Persistenz nur mit einer bewussten Entscheidung zu Aufbewahrung und Zugriffsschutz.

Der Setup-Assistent bietet Persistenz für private Bereitstellungen an, etwa wenn wartende Scans einen Neustart überstehen sollen. Standard bleibt keine Persistenz. Bei aktivierter Ergebnisverschlüsselung enthält der gespeicherte Ergebnisinhalt Chiffretext; den Schlüssel musst du getrennt schützen. Nicht alle Betriebsmetadaten werden dadurch verschlüsselt.

## Speicher und Verdrängung {#memory-and-eviction}

```
--maxmemory 256mb
--maxmemory-policy allkeys-lru
```

Das Speicherlimit begrenzt den Verbrauch bei wachsenden Warteschlangen und vielen Ergebnissen. Passe es an Workerzahl, Ergebnisgröße und TTL an.

`allkeys-lru` kann unter Speicherdruck beliebige wenig genutzte Schlüssel entfernen, auch bevor deren TTL abläuft. Dadurch können Ergebnisse früher verschwinden; auch andere Redis-Zustände können betroffen sein. Beobachte die Verdrängungszähler:

```bash
docker compose exec redis valkey-cli info stats | grep evicted_keys
```

Regelmäßige Verdrängung ist ein Anlass, Kapazität, Last und Aufbewahrungsdauer zu prüfen.

## Externes oder verwaltetes Redis {#an-external-or-managed-redis}

Trage die externe Adresse in `COS_WEB_REDIS_URL` ein und entferne gegebenenfalls den lokalen Redis-Service aus Compose.

- Verwende `rediss://` für TLS.
- Trenne die Daten dieser Anwendung über eine eigene Instanz oder geeignete Datenbankzuordnung.
- Prüfe die Verdrängungsregeln. Bei `noeviction` scheitern neue Schreibvorgänge, sobald das Limit erreicht ist.
- Prüfe Snapshots, Backups und die tatsächliche Löschdauer.

## Kubernetes {#kubernetes}

Für die Webanwendung benötigen Web-Pods und Worker eine eigene Redis-Bereitstellung oder einen externen Dienst. Der [Kubernetes-Leitfaden](../kubernetes.md) behandelt zusätzlich den davon unabhängigen lokalen Scan-Dienst.

- Zugangsdaten gehören in ein `Secret`, nicht in eine `ConfigMap`.
- Eine `NetworkPolicy` sollte nur den vorgesehenen Web- und Worker-Pods Zugriff erlauben.
- Verwende einen internen `ClusterIP`-Service statt `LoadBalancer`, `NodePort` oder öffentlichem Ingress.
- Richte persistente Volumes nur ein, wenn die oben beschriebene Aufbewahrung bewusst gewünscht ist.

## Zustand überwachen {#health-and-monitoring}

`GET /healthz` liefert `503`, wenn die Warteschlange nicht gelesen werden kann oder kein aktueller Worker-Heartbeat vorliegt. Es zeigt Warteschlangentiefe und Zustand der Referenzdatenaktualisierung, aber keine einzelnen Scans.

| Signal | Mögliche Ursache |
|:--|:--|
| `/healthz` mit 503 | Redis oder Worker nicht verfügbar |
| Dauerhaft wachsende Warteschlange | Zu wenig Verarbeitungskapazität oder blockierte Worker |
| Steigende `evicted_keys` | Schlüssel werden vorzeitig entfernt |
| `rejected_connections` | Verbindungslimit erreicht |

## Fehlersuche {#troubleshooting}

| Meldung | Prüfen |
|:--|:--|
| `NOAUTH Authentication required` | Passwort fehlt in der Verbindungs-URL |
| `WRONGPASS invalid username-password pair` | Benutzer oder Passwort stimmen nicht; eventuell nur ein Container neu gestartet |
| `Connection refused` | Redis läuft nicht oder ist aus dem Anwendungsnetz nicht erreichbar |
| `Name or service not known: redis` | Container nicht mit dem passenden internen Netz verbunden |
| `MISCONF Redis is configured to save RDB snapshots` | Aktivierte Persistenz und deren Schreibfehler prüfen |
| `OOM command not allowed when used memory > 'maxmemory'` | Speicherlimit und `noeviction` prüfen |
| Fehlender Worker-Heartbeat | Workerprozess und dessen Logs prüfen |
| Ergebnis frühzeitig mit 404 | TTL, Neustart und Verdrängungszähler prüfen |

Die Anwendungslogs nennen Lebenszyklusereignisse und UUIDs, keine Zieladressen oder Ergebnisse. Untersuche deshalb insbesondere Scans, deren Verarbeitung nicht über `queued` hinauskommt, und die allgemeinen Dienstzustände.

## Marken und Unabhängigkeit

Dies ist ein unabhängiges Community-Projekt. Es ist nicht mit OpenCloud GmbH
verbunden und wird von ihr nicht unterstützt. OpenCloud und zugehörige Marken
gehören ihren jeweiligen Inhabern und benennen hier die geprüfte Software.
