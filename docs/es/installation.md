# Instalar el complemento del escáner de seguridad de OpenCloud

Todas las formas de instalar `check-opencloud-security` en un host, y los
objetos de monitorización que lo llaman una vez instalado. El
[README principal](../../README.md#installation) recoge los dos comandos que
cubren el caso habitual; esta página contiene todo lo demás: mantener el
paquete al día, el autocompletado del shell, la instalación desde una copia del
repositorio, la construcción de la imagen por su cuenta y las definiciones de
objetos de Icinga2 y Nagios.

<!-- TOC -->
* [Instalar el complemento](#installing-the-plugin)
  * [Con pipx / uv / pip (recomendado)](#using-pipx--uv--pip-recommended)
  * [Debian, Ubuntu, RHEL, Fedora (.deb y .rpm)](#debian-ubuntu-rhel-fedora-deb-and-rpm)
  * [Docker](#docker)
  * [Icinga2 / Nagios](#icinga2--nagios)
<!-- TOC -->


## Con pipx / uv / pip (recomendado) {#using-pipx-uv-pip-recommended}
El paquete está publicado en
[PyPI](https://pypi.org/project/check-opencloud-security/) e instala dos
comandos en su `PATH`: `check-opencloud-security` (la comprobación en sí) y
`check-opencloud-scanner` (el mismo escáner como herramienta JSON de una sola
ejecución o como servicio permanente).

**[pipx](https://pipx.pypa.io/): recomendado para herramientas de línea de
comandos**; mantiene el complemento en su propio virtualenv:
```shell
pipx install check-opencloud-security
```

**[uv](https://docs.astral.sh/uv/)**: la misma idea, más rápido:
```shell
uv tool install check-opencloud-security
```

**pip**: en el sistema o en un virtualenv existente:
```shell
pip install check-opencloud-security
```

Cada versión incluye un SBOM CycloneDX y una certificación de procedencia de
Sigstore; consulte
[Verificar lo que ha descargado](../../SECURITY.md#verifying-what-you-downloaded)
si prefiere no fiarse del artefacto sin más.

Para instalar los últimos cambios sin publicar, apunte cualquiera de ellos al
repositorio: `pipx install git+https://github.com/sowoi/check-opencloud-security.git`
(y del mismo modo `uv tool install git+https://...` y
`pip install git+https://...`).

### Actualizar {#updating}
```shell
check-opencloud-security --upgrade-self
```

Este comando averigua cómo se instaló el complemento y ejecuta el comando
adecuado. Use `--upgrade-self=check` para ver qué ejecutaría sin ejecutarlo.
Una copia git se rechaza: actualícela con `git pull`.

Los comandos entre los que elige, si prefiere ejecutarlos usted mismo:

```shell
pipx upgrade check-opencloud-security          # pipx
pipx upgrade-all                               # ... or every pipx tool at once

uv tool upgrade check-opencloud-security       # uv
uv tool upgrade --all                          # ... or every uv tool at once

pip install --upgrade check-opencloud-security # pip
```

Compruebe qué versión ejecuta con `check-opencloud-security --version`, y
consulte [CHANGELOG.md](../../CHANGELOG.md) para ver qué ha cambiado. Una
instalación desde git se actualiza volviendo a ejecutar el mismo comando
`install` con `--force` (pipx/uv) o `--upgrade --force-reinstall` (pip).

Mantener el paquete al día importa aquí más que en un complemento que consulta
un servicio alojado: el calendario de versiones de OpenCloud y la versión más
reciente conocida van *dentro* del paquete (consulte
[Detección de fin de vida](../../README.md#end-of-life-detection)).

Para desinstalar el complemento: `pipx uninstall check-opencloud-security`,
`uv tool uninstall check-opencloud-security` o
`pip uninstall check-opencloud-security`.

**Desde una copia del repositorio (desarrollo o instalación sin conexión):**

El proyecto usa [uv](https://docs.astral.sh/uv/) como gestor de dependencias;
`uv.lock` fija todas las dependencias, así que una instalación es
reproducible:

```shell
git clone https://github.com/sowoi/check-opencloud-security.git
cd check-opencloud-security

uv sync                                       # create .venv from uv.lock
uv run check-opencloud-security --host opencloud.example.com
```

Sin `uv`, instale la copia con pip; las dependencias están declaradas en
`pyproject.toml` y no hace falta ningún archivo de requisitos aparte:

```shell
pip install .
# or, without installing, run the script in place:
pip install requests PyYAML
python3 check_opencloud_security.py --host opencloud.example.com
```

Si alguna de sus herramientas de despliegue exige un `requirements.txt`,
genérelo a partir del archivo de bloqueo en lugar de mantenerlo a mano:

```shell
uv export --no-dev --no-emit-project --format requirements.txt -o requirements.txt

# without the hashes, if your tooling cannot handle them:
uv export --no-dev --no-emit-project --no-hashes --format requirements.txt -o requirements.txt

# including the development and test dependencies:
uv export --no-emit-project --format requirements.txt -o requirements-dev.txt
```

Un archivo así es un artefacto de compilación: no lo confirme en el
repositorio, queda obsoleto en cuanto cambia `uv.lock`.

### Autocompletado del shell {#shell-completion}
El autocompletado es opcional y está desactivado por defecto; necesita una
dependencia adicional:

```shell
pipx install 'check-opencloud-security[completion]'
uv tool install 'check-opencloud-security[completion]'
# or, into an existing install:
pipx inject check-opencloud-security argcomplete
uv tool install --with argcomplete check-opencloud-security --force
```

Después, registre los dos comandos en su shell. Para **bash**, en
`~/.bashrc`:

```shell
eval "$(register-python-argcomplete check-opencloud-security)"
eval "$(register-python-argcomplete check-opencloud-scanner)"
```

Para **zsh**, las mismas dos líneas en `~/.zshrc`, precedidas una vez por
`autoload -U bashcompinit && bashcompinit`. Para **fish**, escriba la salida en
un archivo de autocompletado:

```shell
register-python-argcomplete --shell fish check-opencloud-security \
  > ~/.config/fish/completions/check-opencloud-security.fish
```

El autocompletado conoce los nombres de las opciones, los valores de las
opciones que admiten un conjunto fijo (`--webhook-on`, `--release-track`,
`--update-source`, `--upgrade-self`) y, lo que realmente ahorra escritura, los
identificadores de refuerzo que acepta `--ignore-hardening` con sus nombres
largos en camelCase.

Sin `argcomplete` instalado no se registra nada y el complemento se comporta
exactamente igual que antes; nunca es una dependencia obligatoria de un
complemento de monitorización.

## Debian, Ubuntu, RHEL, Fedora (.deb y .rpm) {#debian-ubuntu-rhel-fedora-deb-and-rpm}

Úselo en un host de monitorización, donde lo que interesa es que la
comprobación aparezca en la base de datos de paquetes como todo lo demás del
equipo: en el inventario, en las actualizaciones automáticas y en la respuesta
de `apt list --installed`. Cada versión incluye ambos paquetes como recursos.
Son independientes de la arquitectura (`all` / `noarch`), así que un único
archivo sirve para todos los hosts.

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

Cada paquete tiene al lado un `.sha256`, y ambos están cubiertos por la misma
certificación de procedencia de Sigstore que el wheel; consulte
[Verificar lo que ha descargado](../../SECURITY.md#verifying-what-you-downloaded).

### Qué instala {#what-it-installs}

| Ruta | |
|:--|:--|
| `/usr/bin/check-opencloud-security` | la comprobación |
| `/usr/bin/check-opencloud-scanner` | el mismo escáner como herramienta JSON |
| `/usr/lib/nagios/plugins/check_opencloud_security` | enlace simbólico a la comprobación (`/usr/lib64/...` en sistemas RPM) |
| `/usr/lib/check-opencloud-security/` | el código |
| `/etc/check-opencloud-security/` | se crea vacío y es donde se busca `config.yml` |
| `/usr/lib/systemd/system/` | cuatro unidades, ninguna activada |
| `/usr/share/doc/check-opencloud-security/` | la configuración de ejemplo, el archivo de entorno y la entrada de cron |

Como el directorio de complementos ya está poblado, un `CheckCommand` de
Icinga2 o Nagios que use `PluginDir + "/check_opencloud_security"` funciona sin
configurar más rutas; consulte [Icinga2 / Nagios](#icinga2--nagios) más abajo.

### Configurarlo {#configuring-it}

**El paquete no configura nada, a propósito.** La configuración de ejemplo
indica un host que no es el suyo, y `/etc/check-opencloud-security/config.yml`
es una ruta que el complemento lee de verdad, así que instalar allí el ejemplo
daría a cada ejecución en el host un destino predeterminado que nadie ha
elegido. Copie lo que necesite:

```shell
sudo cp /usr/share/doc/check-opencloud-security/config.example.yml \
        /etc/check-opencloud-security/config.yml

sudo cp /usr/share/doc/check-opencloud-security/env.example \
        /etc/check-opencloud-security/env      # for the systemd units
```

`check-opencloud-security --configure` hace las mismas preguntas de forma
interactiva.

Las unidades se instalan desactivadas y necesitan antes ese archivo `env`:

```shell
sudo systemctl enable --now check-opencloud-security.timer
sudo systemctl enable --now check-opencloud-security-refresh.timer
```

La segunda mantiene al día el calendario de versiones y la base de datos de
avisos de seguridad incluidos, lo que importa más de lo que parece: ambos van
*dentro* del paquete (consulte
[Detección de fin de vida](../../README.md#end-of-life-detection)).

### Actualizarlo y desinstalarlo {#updating-and-removing-it}

Con `apt` y `dnf`, como cualquier otra cosa del host. `--upgrade-self` detecta
un paquete de distribución y se niega a actuar en lugar de dejar que pip
instale una segunda copia al lado, una copia que los comandos instalados nunca
ejecutarían.

```shell
sudo apt install --only-upgrade check-opencloud-security   # or: dnf upgrade
sudo apt remove check-opencloud-security                   # or: dnf remove
```

La desinstalación no toca `/etc/check-opencloud-security/`: lo que haya puesto
allí es suyo.

### El intérprete que utiliza {#the-interpreter-it-uses}

Los comandos instalados son pequeños lanzadores de shell que buscan por sí
mismos un Python 3.11 o posterior: primero `$COS_PYTHON`, luego `python3` y
después de `python3.15` a `python3.11`, comprobando la versión de cada uno en
lugar de fiarse del nombre. Por eso el RPM no exige `python3 >= 3.11`: RHEL 9
responde 3.9 a `python3` e incluye 3.11 y 3.12 como paquetes aparte, y una
dependencia con versión impediría instalarlo en un host en el que funciona
perfectamente.

El `.deb`, en cambio, sí exige `python3 >= 3.11`, que Debian 12 y Ubuntu 24.04
cumplen. En Ubuntu 22.04, `python3` es la versión 3.10, sin soporte desde
octubre de 2026, así que apt rechaza el paquete; instale allí el complemento
con pipx sobre un Python más reciente.

Si no encuentra ninguno adecuado, la comprobación termina con **3 (UNKNOWN)**
en lugar de notificar un veredicto que nunca ha medido. Apunte `COS_PYTHON` a
un intérprete para resolverlo:

```shell
sudo dnf install python3.12
COS_PYTHON=/usr/bin/python3.12 check-opencloud-security --host opencloud.example.com
```

### Construir los paquetes usted mismo {#building-the-packages-yourself}

Se construyen a partir del wheel, así que una copia del repositorio produce lo
mismo que una publicación. Necesita [nfpm](https://nfpm.goreleaser.com/install/)
en el `PATH`:

```shell
uv build                                        # the wheel first
python scripts/build_distro_packages.py         # both, into distro-packages/
python scripts/build_distro_packages.py --packager deb
```

La estructura, las dependencias y todo lo demás que declaran los paquetes está
en [`packaging/nfpm.yaml`](../../packaging/nfpm.yaml). El motivo por el que se
construyen así está en
[ADR 0039](../../adr/0039-the-plugin-ships-as-a-distribution-package-built-from-the-wheel.md).

## Estaciones de trabajo macOS y Linux (Homebrew) {#macos-and-linux-workstations-homebrew}

Úselo en un portátil y no en un host de monitorización: alguien que prueba una
instancia a mano antes de integrar la comprobación en Icinga. El argumento es
el mismo que el de los `.deb` y `.rpm`, trasladado a otra plataforma: `brew` es
la base de datos de paquetes en estos equipos, y un `pip install --user` no
figura en ella y es invisible para `brew outdated`.

```shell
brew install sowoi/tap/check-opencloud-security
check-opencloud-security --host opencloud.example.com
```

La fórmula está en un tap y no en Homebrew core, que tiene requisitos de
notoriedad que este proyecto no pretende cumplir. `brew upgrade` la mantiene
al día; `--upgrade-self` se niega deliberadamente en una instalación de
Homebrew y lo indica, porque pip escribiría en el Cellar y la siguiente
operación de `brew` lo desharía sin avisar.

La propia fórmula se genera a partir de lo que se publicó en PyPI, mediante
[`scripts/build_homebrew_formula.py`](../../scripts/build_homebrew_formula.py);
consulte [`packaging/README.md`](../../packaging/README.md#homebrew) si mantiene
el tap en lugar de instalar desde él.

## Docker {#docker}
Úselo si prefiere no instalar nada en el host. La imagen incluye también el
servicio de análisis (consulte
[Ejecutar el escáner como servicio](../../README.md#running-the-scanner-as-a-service)).

La imagen publicada incluye ambos puntos de entrada, así que una comprobación
es un solo comando, sin construir ni instalar nada:
```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com
```

Esa línea, su variante JSON y las opciones útiles que la acompañan se reúnen
en [Analizar desde la línea de comandos, en una línea](../docker-oneliner.md).
El comando predeterminado de la imagen inicia la aplicación web, por eso el
complemento se selecciona con `--entrypoint`.

Construya la imagen usted mismo cuando quiera ejecutar su propia copia del
repositorio. Todo lo relacionado con Docker está en
[`docker/`](../../docker/), y el contexto de construcción es la raíz del
repositorio:
```shell
git clone https://github.com/sowoi/check-opencloud-security.git
cd check-opencloud-security
docker build -f docker/Dockerfile -t check-opencloud-security .
```

Ejecutar una comprobación:
```shell
docker run --rm check-opencloud-security --host opencloud.example.com
```

O configurarla por completo mediante
[variables de entorno](../../README.md#environment-variables) (práctico porque
no hay que editar el comando `docker run` para cada host):
```shell
docker run --rm -e COS_HOST=opencloud.example.com check-opencloud-security
```

La imagen incluye un `HEALTHCHECK` que verifica la imagen y no una instancia:
que el paquete se importa y que el calendario de versiones y la base de datos
de avisos incluida se pueden interpretar. No necesita red, así que también se
supera en un host aislado. Está pensado para el servicio de análisis
permanente; un contenedor de comprobación de una sola ejecución termina antes
de que Docker llegue a ejecutarlo. El servicio de
`docker/docker-compose.monitoring.yml` lo sustituye por la sonda HTTP
`/healthz`, que es la comprobación más útil cuando algo está realmente
escuchando.

El contenedor de comprobación no necesita puertos de red, pero sí tiene que
llegar a la propia instancia de OpenCloud. Si la instancia solo es accesible
en la red del propio host Docker, añada `--network host` o el `--add-host`
adecuado. Se ejecuta como el usuario sin privilegios `nagios` y termina con los
mismos códigos de estilo Nagios (`0`/`1`/`2`/`3`) que el script nativo, así que
puede incorporarse directamente a cualquier canalización de monitorización que
ya entienda `docker run` como comando de comprobación (consulte
[Icinga2 / Nagios](#icinga2--nagios) e [Icinga Director](../icinga-director.md)
más abajo).

Si prefiere no construirla localmente, suba la imagen construida a su propio
registro (p. ej. `docker tag check-opencloud-security registry.example.com/check-opencloud-security`
seguido de `docker push ...`) y use esa imagen en sus hosts de
monitorización.

## Icinga2 / Nagios {#icinga2-nagios}

El `CheckCommand` completo, con un argumento para cada opción útil en un servicio, se incluye como [`contrib/icinga2/check_opencloud_security.conf`](../../contrib/icinga2/check_opencloud_security.conf); el ejemplo de abajo muestra las más habituales.
- Si instaló el paquete con pipx/uv/pip, localice el ejecutable `check-opencloud-security` instalado (p. ej. `which check-opencloud-security`) y use esa ruta en `PluginDir`, o cópielo o enlácelo en su carpeta de complementos (normalmente `/usr/lib/nagios/plugins/`).
- Si ejecuta el script a mano, coloque `check_opencloud_security.py` en su carpeta de complementos.
- Cree un nuevo comando personalizado:

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
            description = "Perfil de umbrales con nombre - strict, ops o lenient - fija los ajustes de calificación no establecidos (opcional)"
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

- Cree un nuevo objeto Service.

```
object Service "Service: OpenCloud Security Scan" {
   import               "generic-service"
   host_name =          "YOUR OPENCLOUD HOST"
   check_command =      "check_opencloud_security"
   check_interval = 24h
}
```

El análisis solo se comunica con su propia instancia, así que no hay ningún
límite de frecuencia externo que respetar y un intervalo inferior a 24h es
técnicamente válido. Aun así, un análisis completo realiza unas cuantas
docenas de solicitudes más los sondeos de puertos de depuración, así que una
comprobación por hora es un mínimo razonable; y si la
[comprobación de actualizaciones](../../README.md#update-check) usa el canal de
GitHub, limítela a unas pocas veces al día o indique un token.

### Usar la imagen de Docker {#using-the-docker-image-instead}

Si instaló con [Docker](#docker), apunte el `CheckCommand` a `docker` y deje
que ejecute el contenedor bajo demanda en lugar de un binario local:

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
            description = "Perfil de umbrales con nombre - strict, ops o lenient - fija los ajustes de calificación no establecidos (opcional)"
            value = "$opencloud_profile$"
        }
        "--check-hardening" = {
            description = "Also check hardening measures and security headers (optional)"
            set_if = "$opencloud_check_hardening$"
        }
    }
}
```

Se asume que la imagen `check-opencloud-security` ya se ha construido (o
descargado) en el host de Icinga2, que el usuario que ejecuta el daemon de
Icinga2 tiene permiso para comunicarse con el socket de Docker y que el
contenedor puede llegar a la instancia de OpenCloud.
