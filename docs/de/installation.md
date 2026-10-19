# Installation und Monitoring-Anbindung

Dieser Leitfaden beschreibt die Installation, Aktualisierung und Shell-Vervollständigung sowie die Einbindung in Icinga2 und Nagios. Die beiden häufigsten Installationswege findest du auch im [Haupt-README](../../README.md#installation).

## pipx, uv oder pip {#using-pipx-uv-pip-recommended}

Das Paket auf [PyPI](https://pypi.org/project/check-opencloud-security/) installiert `check-opencloud-security` für Monitoring und `check-opencloud-scanner` für JSON-Ausgabe und den HTTP-Dienst.

**[pipx](https://pipx.pypa.io/)** installiert CLI-Werkzeuge in einer eigenen virtuellen Umgebung:

```shell
pipx install check-opencloud-security
```

**[uv](https://docs.astral.sh/uv/)** bietet ebenfalls eine isolierte Werkzeuginstallation:

```shell
uv tool install check-opencloud-security
```

**pip** installiert in eine vorhandene Python-Umgebung, vorzugsweise ein virtualenv:

```shell
pip install check-opencloud-security
```

Releases enthalten eine CycloneDX-SBOM und eine Sigstore-Herkunftsattestierung. [Downloads prüfen](../../SECURITY.md#verifying-what-you-downloaded) erklärt die Verifikation.

Für unveröffentlichte Änderungen kannst du direkt aus dem Repository installieren: `pipx install git+https://github.com/sowoi/check-opencloud-security.git`. Entsprechende Aufrufe sind auch mit `uv tool install` und `pip install` möglich.

### Aktualisieren {#updating}

```shell
check-opencloud-security --upgrade-self
```

Der Befehl erkennt den Installationsweg und wählt den passenden Paketmanager. `--upgrade-self=check` zeigt den vorgesehenen Befehl nur an. Aktualisiere einen Git-Checkout selbst mit `git pull`.

Die Paketmanager kannst du auch direkt aufrufen:

```shell
pipx upgrade check-opencloud-security          # pipx
pipx upgrade-all                               # ... or every pipx tool at once

uv tool upgrade check-opencloud-security       # uv
uv tool upgrade --all                          # ... or every uv tool at once

pip install --upgrade check-opencloud-security # pip
```

`check-opencloud-security --version` zeigt den installierten Stand, [CHANGELOG.md](../../CHANGELOG.md) die Änderungen. Erneuere eine Installation aus einer Git-URL mit `--force` bei pipx/uv oder `--upgrade --force-reinstall` bei pip.

Halte das Paket aktuell: Es enthält auch den Release-Zeitplan und die Referenzdaten für die [End-of-Life-Erkennung](../../README.md#end-of-life-detection).

Zum Entfernen verwende `pipx uninstall check-opencloud-security`, `uv tool uninstall check-opencloud-security` oder `pip uninstall check-opencloud-security`.

**Installation aus einem Checkout:**

`uv.lock` legt die Abhängigkeiten für eine reproduzierbare Entwicklungsumgebung fest:

```shell
git clone https://github.com/sowoi/check-opencloud-security.git
cd check-opencloud-security

uv sync                                       # create .venv from uv.lock
uv run check-opencloud-security --host opencloud.example.com
```

Alternativ installiere den Checkout mit pip anhand von `pyproject.toml`:

```shell
pip install .
# or, without installing, run the script in place:
pip install requests PyYAML
python3 check_opencloud_security.py --host opencloud.example.com
```

Falls ein Bereitstellungswerkzeug eine `requirements.txt` benötigt, erzeuge diese aus der Lockdatei:

```shell
uv export --no-dev --no-emit-project --format requirements.txt -o requirements.txt

# without the hashes, if your tooling cannot handle them:
uv export --no-dev --no-emit-project --no-hashes --format requirements.txt -o requirements.txt

# including the development and test dependencies:
uv export --no-emit-project --format requirements.txt -o requirements-dev.txt
```

Diese Datei ist ein abgeleitetes Build-Artefakt und sollte nicht separat im Repository gepflegt werden.

### Shell-Vervollständigung {#shell-completion}

Die optionale Vervollständigung benötigt eine zusätzliche Abhängigkeit:

```shell
pipx install 'check-opencloud-security[completion]'
uv tool install 'check-opencloud-security[completion]'
# or, into an existing install:
pipx inject check-opencloud-security argcomplete
uv tool install --with argcomplete check-opencloud-security --force
```

Registriere für **bash** beide Befehle in `~/.bashrc`:

```shell
eval "$(register-python-argcomplete check-opencloud-security)"
eval "$(register-python-argcomplete check-opencloud-scanner)"
```

Unter **zsh** verwende dieselben Zeilen in `~/.zshrc` und führe davor einmal `autoload -U bashcompinit && bashcompinit` aus. Unter **fish** schreibe die Ausgabe in eine Completion-Datei:

```shell
register-python-argcomplete --shell fish check-opencloud-security \
  > ~/.config/fish/completions/check-opencloud-security.fish
```

Die Vervollständigung kennt Optionen, feste Auswahlwerte und die Kennungen für `--ignore-hardening`. Ohne `argcomplete` bleibt sie deaktiviert; das Plugin benötigt sie nicht für den normalen Betrieb.

## Debian, Ubuntu, RHEL und Fedora: .deb und .rpm {#debian-ubuntu-rhel-fedora-deb-and-rpm}

Die Distributionspakete integrieren den Check in die Paketverwaltung des Monitoring-Hosts. Jedes Release stellt architekturunabhängige Pakete (`all` beziehungsweise `noarch`) bereit:

```shell
VERSION=$(curl -fsSL https://api.github.com/repos/sowoi/check-opencloud-security/releases/latest \
          | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p')
BASE=https://github.com/sowoi/check-opencloud-security/releases/download/v$VERSION

# Debian, Ubuntu
curl -fsSLO "$BASE/check-opencloud-security_${VERSION}_all.deb"
sudo apt install "./check-opencloud-security_${VERSION}_all.deb"

# RHEL, Rocky, Alma, Fedora, openSUSE
curl -fsSLO "$BASE/check-opencloud-security-${VERSION}-1.noarch.rpm"
sudo dnf install "./check-opencloud-security-${VERSION}-1.noarch.rpm"
```

Zu jedem Paket gehört eine `.sha256`-Datei. Die Pakete werden wie das Wheel attestiert; siehe [Downloads prüfen](../../SECURITY.md#verifying-what-you-downloaded).

### Installierte Dateien {#what-it-installs}

| Pfad | Inhalt |
|:--|:--|
| `/usr/bin/check-opencloud-security` | Monitoring-Plugin |
| `/usr/bin/check-opencloud-scanner` | Scanner-CLI |
| `/usr/lib/nagios/plugins/check_opencloud_security` | Symlink zum Plugin; bei RPM unter `/usr/lib64/...` |
| `/usr/lib/check-opencloud-security/` | Programmcode |
| `/etc/check-opencloud-security/` | Leeres Konfigurationsverzeichnis; `config.yml` wird dort gesucht |
| `/usr/lib/systemd/system/` | Vier zunächst deaktivierte Units |
| `/usr/share/doc/check-opencloud-security/` | Beispielkonfiguration, Umgebungsdatei und Cron-Eintrag |

Ein CheckCommand mit `PluginDir + "/check_opencloud_security"` kann den vorhandenen Symlink verwenden; siehe [Icinga2 / Nagios](#icinga2--nagios).

### Konfiguration {#configuring-it}

Das Paket legt kein Standardziel fest. Kopiere die benötigten Beispiele und trage deine eigenen Werte ein:

```shell
sudo cp /usr/share/doc/check-opencloud-security/config.example.yml \
        /etc/check-opencloud-security/config.yml

sudo cp /usr/share/doc/check-opencloud-security/env.example \
        /etc/check-opencloud-security/env      # for the systemd units
```

Alternativ führt dich `check-opencloud-security --configure` durch die Einstellungen.

Die Units benötigen vor dem Aktivieren die konfigurierte `env`-Datei:

```shell
sudo systemctl enable --now check-opencloud-security.timer
sudo systemctl enable --now check-opencloud-security-refresh.timer
```

Der zweite Timer aktualisiert Release-Zeitplan und Schwachstellendaten getrennt vom installierten Paket. Konfiguriere den Scanner so, dass er die erzeugten Dateien liest; siehe [Referenzdaten](../reference-data.md).

### Aktualisieren und entfernen {#updating-and-removing-it}

Verwende `apt` oder `dnf`. `--upgrade-self` erkennt eine Distributionsinstallation und verweigert eine zusätzliche Installation über pip.

```shell
sudo apt install --only-upgrade check-opencloud-security   # or: dnf upgrade
sudo apt remove check-opencloud-security                   # or: dnf remove
```

Eigene Dateien unter `/etc/check-opencloud-security/` bleiben beim Entfernen erhalten.

### Python-Interpreter {#the-interpreter-it-uses}

Die Startskripte suchen nach Python 3.11 oder neuer: zuerst über `$COS_PYTHON`, dann `python3`, anschließend `python3.15` bis `python3.11`. Jeder Kandidat wird anhand seiner tatsächlichen Version geprüft. So können etwa auf RHEL zusätzliche Python-Versionen verwendet werden, auch wenn `python3` noch auf eine ältere Version zeigt.

Das `.deb` verlangt dagegen `python3 >= 3.11`; Debian 12 und Ubuntu 24.04 erfüllen das. Unter Ubuntu 22.04 ist `python3` die Version 3.10, die seit Oktober 2026 keine Updates mehr bekommt – apt lehnt das Paket dort ab. Installiere das Plugin dort mit pipx auf einem neueren Python.

Ohne geeigneten Interpreter endet der Check mit **3 (UNKNOWN)**. Über `COS_PYTHON` kannst du einen Pfad vorgeben:

```shell
sudo dnf install python3.12
COS_PYTHON=/usr/bin/python3.12 check-opencloud-security --host opencloud.example.com
```

### Pakete selbst bauen {#building-the-packages-yourself}

Die Pakete werden aus dem Wheel erzeugt. Dafür muss [nfpm](https://nfpm.goreleaser.com/install/) im `PATH` verfügbar sein:

```shell
uv build                                        # the wheel first
python scripts/build_distro_packages.py         # both, into distro-packages/
python scripts/build_distro_packages.py --packager deb
```

Layout und Abhängigkeiten stehen in [`packaging/nfpm.yaml`](../../packaging/nfpm.yaml), die Begründung in [ADR 0039](../../adr/0039-the-plugin-ships-as-a-distribution-package-built-from-the-wheel.md).

## macOS und Linux mit Homebrew {#macos-and-linux-workstations-homebrew}

Homebrew eignet sich für Arbeitsrechner, auf denen du den Scanner manuell verwenden und mit `brew` verwalten möchtest:

```shell
brew install sowoi/tap/check-opencloud-security
check-opencloud-security --host opencloud.example.com
```

Die Formel liegt in einem eigenen Tap. Aktualisiere sie mit `brew upgrade`; `--upgrade-self` verweigert Änderungen an einer Homebrew-Installation, damit die Paketverwaltung zuständig bleibt.

Die Formel wird aus dem veröffentlichten PyPI-Paket erzeugt. Hinweise für die Pflege des Taps stehen im [Packaging-README](../../packaging/README.md#homebrew) und in [`scripts/build_homebrew_formula.py`](../../scripts/build_homebrew_formula.py).

## Docker {#docker}

Das veröffentlichte Image enthält Plugin und Scanner-CLI:

```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com
```

Da der Standardbefehl die Webanwendung startet, wählt `--entrypoint` hier das Plugin. Weitere Varianten stehen unter [Scanner mit Docker](../docker-oneliner.md).

Für einen eigenen Checkout baue mit dem Repository-Stamm als Build-Kontext:

```shell
git clone https://github.com/sowoi/check-opencloud-security.git
cd check-opencloud-security
docker build -f docker/Dockerfile -t check-opencloud-security .
```

Einen Check ausführen:

```shell
docker run --rm check-opencloud-security --host opencloud.example.com
```

Oder über [Umgebungsvariablen](../../README.md#environment-variables) konfigurieren:

```shell
docker run --rm -e COS_HOST=opencloud.example.com check-opencloud-security
```

Der Image-`HEALTHCHECK` prüft lokal, ob Paket, Zeitplan und Advisory-Datenbank lesbar sind. Er benötigt kein Netzwerk. Ein einmaliger Check-Container beendet sich meist vor dem ersten Healthcheck. Die Monitoring-Compose-Datei verwendet für den dauerhaften Dienst stattdessen `/healthz`.

Der Check-Container muss keine Ports veröffentlichen, benötigt aber Zugriff auf die Instanz. Passe bei Bedarf das Netzwerk mit `--network host` oder `--add-host` an. Er läuft als unprivilegierter Benutzer `nagios` und liefert dieselben Exitcodes wie die native Installation.

Du kannst ein selbst gebautes Image in deine Registry übertragen, etwa mit `docker tag check-opencloud-security registry.example.com/check-opencloud-security` und anschließendem `docker push`, und auf den Monitoring-Hosts verwenden.

## Icinga2 / Nagios {#icinga2-nagios}

Das vollständige `CheckCommand` mit einem Argument für jede Option, die auf einem Service sinnvoll ist, liegt in [`contrib/icinga2/check_opencloud_security.conf`](../../contrib/icinga2/check_opencloud_security.conf); das Beispiel unten zeigt die gängigen.

- Suche bei pipx, uv oder pip den installierten Programmpfad, etwa mit `which check-opencloud-security`, und verwende ihn direkt oder über einen Symlink im Plugin-Verzeichnis.
- Bei direkter Verwendung des Skripts lege `check_opencloud_security.py` im Plugin-Verzeichnis ab.
- Erstelle den CheckCommand:

```
object CheckCommand "check_opencloud_security" {
    import "plugin-check-command"
    command = [ PluginDir + "/check-opencloud-security" ]

    arguments += {
        "--host" = {
            description = "OpenCloud hostname, IP or URL"
            required = true
            value = "$address$"
        }

        "--port" = {
            description = "Port the instance listens on, e.g. 9200 (optional)"
            value = "$opencloud_port$"
        }

        "--proxy" = {
            description = "HTTP/HTTPS proxy (optional)"
            required = false
        }

        "--insecure" = {
            description = "Do not verify the instance's TLS certificate (optional)"
            set_if = "$opencloud_insecure$"
        }

        "--no-debug-ports" = {
            description = "Skip probing the OpenCloud debug ports (optional)"
            set_if = "$opencloud_no_debug_ports$"
        }

        "--debug" = {
            description = "Enable debugging output (optional)"
            set_if = "$opencloud_debug$"
        }

        "--warning" = {
            description = "Rating (0-5) at or below which the check warns (optional)"
            value = "$opencloud_warning$"
        }

        "--critical" = {
            description = "Rating (0-5) at or below which the check is critical (optional)"
            value = "$opencloud_critical$"
        }

        "--profile" = {
            description = "Benanntes Schwellenwertprofil - strict, ops oder lenient - legt nicht selbst gesetzte Bewertungseinstellungen fest (optional)"
            value = "$opencloud_profile$"
        }

        "--check-hardening" = {
            description = "Also check hardening measures and security headers (optional)"
            set_if = "$opencloud_check_hardening$"
        }

        "--update-source" = {
            description = "Where the newest release is looked up: auto, feed, pinned, bundled, off"
            value = "$opencloud_update_source$"
        }
    }
}
```

Lege anschließend den Service an:

```
object Service "Service: OpenCloud Security Scan" {
   import               "generic-service"
   host_name =          "YOUR OPENCLOUD HOST"
   check_command =      "check_opencloud_security"
   check_interval = 24h
}
```

Ein vollständiger Scan erzeugt mehrere HTTP-Anfragen und Debug-Port-Verbindungen. Wähle ein zur Änderungsfrequenz passendes Intervall; stündliche oder tägliche Prüfungen reichen häufig aus. Die optionale GitHub-Update-Abfrage unterliegt zusätzlich dem Kontingent der Quelle.

### Docker im CheckCommand verwenden {#using-the-docker-image-instead}

Für die [Docker-Variante](#docker) startet der CheckCommand den Container bei Bedarf:

```
object CheckCommand "check_opencloud_security_docker" {
    import "plugin-check-command"
    command = [ "/usr/bin/docker" ]

    arguments += {
        "run" = {
            order = -5
            value = "run"
        }
        "--rm" = {
            order = -4
            value = "--rm"
        }
        "image" = {
            order = -3
            skip_key = true
            value = "check-opencloud-security"
        }
        "--host" = {
            description = "OpenCloud hostname, IP or URL"
            required = true
            value = "$address$"
        }
        "--port" = {
            description = "Port the instance listens on, e.g. 9200 (optional)"
            value = "$opencloud_port$"
        }
        "--proxy" = {
            description = "HTTP/HTTPS proxy (optional)"
            required = false
        }
        "--insecure" = {
            description = "Do not verify the instance's TLS certificate (optional)"
            set_if = "$opencloud_insecure$"
        }
        "--debug" = {
            description = "Enable debugging output (optional)"
            set_if = "$opencloud_debug$"
        }
        "--warning" = {
            description = "Rating (0-5) at or below which the check warns (optional)"
            value = "$opencloud_warning$"
        }
        "--critical" = {
            description = "Rating (0-5) at or below which the check is critical (optional)"
            value = "$opencloud_critical$"
        }
        "--profile" = {
            description = "Benanntes Schwellenwertprofil - strict, ops oder lenient - legt nicht selbst gesetzte Bewertungseinstellungen fest (optional)"
            value = "$opencloud_profile$"
        }
        "--check-hardening" = {
            description = "Also check hardening measures and security headers (optional)"
            set_if = "$opencloud_check_hardening$"
        }
    }
}
```

Das Image muss auf dem Icinga2-Host vorhanden sein. Der Icinga2-Benutzer benötigt Zugriff auf den Docker-Socket, und der Container muss die Instanz erreichen können.

## Marken und Unabhängigkeit

Dies ist ein unabhängiges Community-Projekt. Es ist nicht mit OpenCloud GmbH
verbunden und wird von ihr nicht unterstützt. OpenCloud und zugehörige Marken
gehören ihren jeweiligen Inhabern und benennen hier die geprüfte Software.
