# Referencia de la CLI del escáner de seguridad de OpenCloud

## Inicio rápido {#quick-start}
Instale el complemento y ejecute una comprobación, un comando para cada cosa:

```shell
pipx install check-opencloud-security     # or: uv tool install / pip install
check-opencloud-security --host opencloud.example.com
```

Una instancia de OpenCloud recién creada con `opencloud init` sirve TLS en el
puerto 9200 con un certificado autofirmado. Apunte la comprobación a ella e
indíquele que no penalice a la instancia por el certificado:

```shell
check-opencloud-security --host opencloud.example.com:9200 --insecure
```

Para una configuración permanente (Icinga2, temporizador de systemd, cron,
Docker, ...) consulte [Instalación](#installation) más abajo.

## Funciones {#features}
- **Sin API y sin terceros.** Todas las comprobaciones se ejecutan en el
  proceso del complemento, contra su instancia. Funcionan las direcciones IP,
  los puertos personalizados y los nombres de host internos, y no hay límites
  de frecuencia
- **Detección de actualizaciones pendientes y de fin de vida** con el
  [canal de versiones de OpenCloud](#update-check): si hay una versión más
  reciente en su canal y si la que se ejecuta sigue recibiendo correcciones de
  seguridad, con modos sin conexión `pinned` y `bundled` para monitorización
  aislada
- **Comprobaciones específicas de OpenCloud**: puntos de acceso Graph/WebDAV/OCS
  sin autenticación, archivos `opencloud.yaml`, `proxy/server.key` y boltdb
  expuestos, puertos de depuración de servicios accesibles (`/metrics`,
  `/config`, `/debug/pprof`), autenticación básica activada y divulgación de la
  versión
- **Inspección TLS**: handshake, versión del protocolo, caducidad y confianza
  del certificado, además de un paso automático de HTTPS a HTTP que notifica
  la degradación en lugar de ocultarla; consulte
  [TLS y certificados](../tls.md)
- **Refuerzo derivado de lo que la instancia notifica realmente**, no adivinado
  a partir de su número de versión: fortaleza de HSTS, calidad de la CSP,
  obligatoriedad de contraseña y caducidad en enlaces públicos, y ajustes de
  enumeración de usuarios y de política de contraseñas
- Configuración desde un archivo YAML, variables de entorno o un proveedor de
  secretos (secretos de Docker/Kubernetes, archivos, entorno, comandos)
- Códigos de salida estándar de Nagios/Icinga (OK, WARNING, CRITICAL, UNKNOWN)
  y datos de rendimiento (nota, número de vulnerabilidades, duración del
  análisis)
- Umbrales de nota configurables para WARNING y CRITICAL
- Comprobaciones opcionales de refuerzo y de cabeceras de seguridad
  (`--check-hardening`)
- Notificación opcional por webhook cuando una comprobación pasa a crítica
- Reintento automático con espera exponencial ante errores de red transitorios
- Compatibilidad con proxies web, depuración y ejecuciones con varios hosts
- Instalable con pipx/uv/pip, o como imagen de Docker lista para usar

## Requisitos previos {#prerequisites}
- Python 3.11 o posterior, o Docker si prefiere la vía de contenedores.
- `requests` y `PyYAML`, que pipx/uv/pip instalan automáticamente.
- Acceso de red desde el host de monitorización a la instancia de OpenCloud. A
  diferencia de un escáner alojado, este complemento necesita llegar a la
  propia instancia, y eso es precisamente lo que le permite funcionar con
  instancias que no están en internet.

## Instalación {#installation}
Dos comandos cubren el caso habitual. Todo lo demás (mantener el paquete al
día, el autocompletado del shell, instalar desde una copia del repositorio,
construir la imagen usted mismo y las definiciones de objetos de
Icinga2/Nagios) está en **[Instalar el complemento](../installation.md)**.

```shell
pipx install check-opencloud-security          # or: uv tool install / pip install
check-opencloud-security --host opencloud.example.com
```

En un host de monitorización, donde se espera que el software llegue mediante
el gestor de paquetes y aparezca en el inventario, cada versión incluye además
un `.deb` y un `.rpm`:

```shell
sudo apt install ./check-opencloud-security_<version>_all.deb       # Debian, Ubuntu
sudo dnf install ./check-opencloud-security-<version>-1.noarch.rpm  # RHEL, Fedora
```

Ambos instalan la comprobación en `/usr/lib/nagios/plugins/`. La configuración
de la monitorización es un paso aparte; consulte
[Instalar el complemento](../installation.md#debian-ubuntu-rhel-fedora-deb-and-rpm).

¿Prefiere no poner Python en el host? La imagen publicada incluye ambos puntos
de entrada:

```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com
```

Esa línea, su variante JSON y las opciones útiles que la acompañan se reúnen en
[Analizar desde la línea de comandos, en una línea](../docker-oneliner.md). El
comando predeterminado de la imagen inicia la aplicación web, por eso el
complemento se selecciona con `--entrypoint`.

| Vía | Dónde se describe |
|:------|:-----------------------|
| pipx / uv / pip, y `--upgrade-self` | [Instalar el complemento](../installation.md#using-pipx--uv--pip-recommended) |
| `.deb` y `.rpm`, para un host de monitorización | [Instalar el complemento](../installation.md#debian-ubuntu-rhel-fedora-deb-and-rpm) |
| Autocompletado del shell | [Instalar el complemento](../installation.md#shell-completion) |
| Docker, y la construcción de la imagen | [Instalar el complemento](../installation.md#docker) |
| Objetos de Icinga2 y Nagios | [Instalar el complemento](../installation.md#icinga2--nagios) |
| Icinga Director, desde la interfaz web | [Icinga Director](../icinga-director.md) |
| Ansible, systemd, cron, Kubernetes | [Guías de despliegue](../README.md#deploying-it) |

Cada versión incluye un SBOM CycloneDX y una certificación de procedencia de
Sigstore; consulte
[Verificar lo que ha descargado](../../SECURITY.md#verifying-what-you-downloaded)
si prefiere no fiarse del artefacto sin más.

Mantener el paquete al día importa aquí más que en un complemento que consulta
un servicio alojado: el calendario de versiones de OpenCloud y la versión más
reciente conocida van *dentro* del paquete (consulte
[Detección de fin de vida](#end-of-life-detection)).

## Uso de la CLI {#cli-usage}
- `check-opencloud-security -h` muestra un manual.

### Comando {#command}
```shell
check-opencloud-security --host <Hostname> --check-hardening
```

### Opciones {#options}

La [referencia de opciones de la CLI](../cli-reference.md) enumera todas las
opciones, sus valores predeterminados y la variable de entorno
correspondiente. Use `--help` para ver las mismas opciones agrupadas por tarea.

Los grupos principales cubren destinos, sondeos, umbrales de nota, información
de versiones, comparaciones, ejecución, salida y notificaciones.

Las pocas que escribirá casi a diario:

| Opción | Descripción |
|:-------|:------------|
| `-H, --host` | La instancia que se comprueba. Nombre de host, IP o URL, opcionalmente con puerto; separadas por comas si son varias |
| `-d, --debug` | Explica en detalle la nota y cada hallazgo |
| `--check-hardening` | Notifica también las medidas de refuerzo y cabeceras de seguridad ausentes |
| `-w, --warning` / `-c, --critical` | Las notas (0-5) iguales o inferiores a las cuales la comprobación avisa o pasa a crítica |
| `--format` | `nagios`, `prometheus`, `otlp`, `checkmk`, `json`, `sarif` o `junit` |
| `--ignore-hardening` | Acepta por su nombre un hallazgo que no se va a corregir |
| `--baseline` / `--warn-on-new` | Alerta solo sobre hallazgos nuevos o peores que en la ejecución anterior |
| `--verify-remediation` | Tras una corrección, vuelve a medir solo los hallazgos indicados en lugar de un escaneo completo |

La prioridad es siempre **opción de línea de comandos > variable de entorno >
[archivo de configuración](#configuration-file-and-secrets) > valor
predeterminado**.

## Verificar una corrección {#verifying-a-fix}

Después de cambiar un solo ajuste - una cabecera en el proxy inverso, una ruta
que ya no debe servir - no hace falta esperar a un escaneo completo.
`--verify-remediation` toma los identificadores de hallazgo de la salida
normal y ejecuta solo las sondas que los miden:

```shell
check-opencloud-security --host opencloud.example.com \
  --verify-remediation Strict-Transport-Security,corsOriginRestricted
```

La opción se puede repetir y acepta identificadores separados por comas. Una
familia como `exposed`, `authentication`, `debugEndpoint` o
`versionDisclosure` comprueba todos sus miembros. `OK` significa que todos
pasan ya; `WARNING` o `CRITICAL` (con gravedad alta o crítica), que alguno
sigue fallando; `UNKNOWN`, que solo un escaneo completo puede decidirlo
(`eol`, `vulnerability:...`, `httpsAvailable`, paridad de direcciones). No hay
calificación, línea base, webhook ni exenciones. `--format json` imprime el
documento de medición.

## Comprobar varios hosts {#checking-multiple-hosts}
`--host` (y `COS_HOST`) admite una lista de nombres de host separados por
comas, por ejemplo:

```shell
check-opencloud-security --host opencloud1.example.com,opencloud2.example.com
```

Los hosts se procesan en paralelo: el complemento crea un trabajador por host,
hasta el límite predeterminado de cinco. Una comprobación de un solo host sigue
siendo estrictamente de un solo hilo, sin grupo de trabajadores. Defina
`--concurrency` o `COS_CONCURRENCY` para bajar o subir el límite (hasta 32),
por ejemplo `--concurrency 2` para un máximo de dos hosts a la vez. Cada
trabajador mantiene por separado su resultado y sus datos de rendimiento de
Nagios; la salida empieza con un resumen de una línea (p. ej.
`Checked 2 host(s): overall CRITICAL (1 CRITICAL, 1 OK)`), seguido de un
bloque de resultado por host en el mismo orden que la entrada. El complemento
termina con el peor estado encontrado entre todos los hosts, según la
prioridad habitual de Nagios/Icinga: `CRITICAL` > `WARNING` > `UNKNOWN` >
`OK`. Un solo host sigue produciendo la salida y el código de salida
originales de un único bloque, así que las configuraciones existentes de un
solo host no se ven afectadas. Cuando las instancias dejan de parecerse, un
archivo de configuración por instancia escala mejor; consulte
[Comprobar un conjunto de instancias](../many-instances.md).

Se ignoran los espacios alrededor de cada nombre de host y se descartan las
entradas vacías (p. ej. por una coma final). Como no interviene ninguna API
alojada, cada entrada puede ser un nombre de host, una dirección IPv4, una
dirección IPv6 entre corchetes o una URL completa, con o sin puerto:
`--host 10.0.0.5:9200,[2001:db8::1],https://cloud.example.com/`.

## Toda la flota en una tabla {#reading-a-fleet-in-one-table}

Los bloques de resultados por host están escritos para un sistema de
monitorización, y una docena de ellos cuesta leer. `--format summary` imprime
la misma ejecución como una fila alineada por host:

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

Las columnas son la nota que decidió este complemento, la versión que midió el
análisis, el estado del ciclo de vida, cuántos avisos aplican y cuánto se ha
movido desde la referencia. Las filas conservan el orden en que se indicaron
los hosts, y la última línea es el mismo recuento con el que empieza la salida
de Nagios. El código de salida no cambia - el peor estado de la flota -, así
que sigue sirviendo desde una tarea cron que envía su salida por correo.

`EOL` muestra `YES` pasado el fin de vida, `soon` dentro de la ventana de
[`--eol-warning-days`](#options) y `no` en los demás casos. `NEW` necesita
[`--baseline`](#options): sin referencia es `-`, porque "nada nuevo" y "no hay
forma de saberlo" son respuestas distintas. Con ella es `new` en la ejecución
que registra la referencia y `+n` después, para los hallazgos que antes no
estaban. Un host cuyo análisis falló no tiene nota, así que su celda `GRADE`
lleva el estado de Nagios (`UNKNOWN`).

Este formato es para personas. Para una máquina usa
[`json`, `sarif` o `junit`](#machine-readable-output-for-ci-jsonsarifjunit),
que llevan los mismos hallazgos en una forma analizable.

## Modo de política de CI {#ci-policy-mode}

`-w`/`-c` y `--profile` juzgan una instancia por su **nota**, un único número
que representa todo lo que el escaneo midió. Esa es la forma correcta para un
sistema de monitorización y la equivocada para una barrera de despliegue: un
equipo que exige HTTPS forzado y ningún usuario de demostración no puede
expresarlo como una nota.

`--policy` apunta a un archivo que lo dice explícitamente:

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

Las tres claves son opcionales: `minimum_rating` es un mínimo para la nota, de
`0` (F) a `5` (A+), `required_hardenings` nombra las medidas que deben estar
en su sitio y `forbidden` nombra los identificadores de hallazgos que no deben
estar presentes: una protección ausente, una comprobación fallida o un
identificador de vulnerabilidad.

Los identificadores son los que el propio escaneo informa; `--format json` los
enumera para una instancia y `--debug` explica cada uno. Un archivo `.json` se
lee como JSON y cualquier otro como YAML, y
[`config/policy.example.yml`](../../config/policy.example.yml) es un punto de
partida comentado.

Una infracción es **CRITICAL**, porque de poco sirve hacer fallar una
canalización con un estado que quizá esté configurada para tolerar. Una
política solo empeora un veredicto, nunca lo mejora: una instancia que cumple
todos los requisitos conserva el que ya decidieron los umbrales, la
protección, el ciclo de vida y la referencia, y la salida indica
`Policy: every requirement met`. La carga del webhook y `--format json`
llevan el mismo veredicto bajo `policy`.

Conviene conocer dos reglas antes de escribir una:

* **Una exención no disculpa un requisito.** `--ignore-hardening` y
  `--waive-until` son el operador local aceptando un hallazgo; una política es
  la organización diciendo que no puede aceptarse. Si una exención pudiera
  silenciar una medida exigida, una política no describiría nada exigible.
* **Una errata es un error de uso, no una aprobación silenciosa.** Una clave
  desconocida, una nota fuera de `0`-`5` o una medida que el catálogo no
  conoce terminan la ejecución en `UNKNOWN` con el motivo. Una política existe
  para hacer fallar despliegues: una regla que en silencio no exige nada sería
  el peor resultado posible.

## Integración con Prometheus y Kubernetes {#prometheus-kubernetes-integration}

`--format=prometheus` produce una carga de texto de una sola ejecución; el
exportador incorporado sirve `/metrics` para monitorización por consulta,
actualizando cada destino configurado en el primer scrape y después cada
`--scrape-interval` (60 segundos por defecto):

```shell
check-opencloud-security --host opencloud.example.com --format=prometheus

check-opencloud-security --host opencloud.example.com \
  --prometheus-listen-port 9102
```

Por defecto, el exportador solo escucha en `127.0.0.1`. Defina
`--prometheus-listen-addr 0.0.0.0` solo cuando un cortafuegos o una política de
red limite quién puede consultarlo; eso es también lo que necesitan un
contenedor o un Deployment de Kubernetes, además de publicar el puerto `9102`.

Publica `opencloud_security_rating_score`,
`opencloud_security_vulnerabilities_total`,
`opencloud_security_hardenings_missing_total`,
`opencloud_security_failed_extra_checks_total`,
`opencloud_security_support_days_remaining`,
`opencloud_security_update_available`,
`opencloud_security_scan_duration_seconds` y
`opencloud_security_scrape_success`. La etiqueta `host` identifica el destino
configurado; la nota lleva además `domain`, `product` y `version`.

`--format=otlp` notifica esas mismas métricas en OTLP/JSON: un
`ExportMetricsServiceRequest` para todos los hosts analizados, que es lo que
acepta un recolector de OpenTelemetry en `/v1/metrics`:

```shell
check-opencloud-security --host opencloud.example.com --format=otlp \
  | curl -sf -X POST http://collector.example.com:4318/v1/metrics \
      -H 'Content-Type: application/json' --data-binary @-
```

Ambos formatos de métricas notifican un análisis fallido como
`opencloud_security_scrape_success 0` y terminan con `0`, porque un recolector
que deja de recibir muestras no puede distinguir una instancia inaccesible de
una tarea de cron que nadie se dio cuenta de que se había detenido. Use
`--format nagios` cuando lo que importa es el código de salida.

La [guía de Prometheus y Grafana](../prometheus.md) contiene el
ServiceMonitor, las reglas de alerta, qué representar en gráficos, la receta
OTLP y los patrones heredados de textfile/Pushgateway;
[Kubernetes](../kubernetes.md) contiene los manifiestos y el chart de Helm.

## Salida legible por máquina para CI (json/sarif/junit) {#machine-readable-output-for-ci-jsonsarifjunit}

`--format json`, `--format sarif` o `--format junit` imprimen un único
documento combinado para todos los hosts analizados, nunca uno por host,
aunque solo haya uno, así que la salida es siempre JSON/SARIF/XML válido.
**El código de salida conserva su significado de Nagios con cualquier
formato** (`0`/`1`/`2`/`3`), así que un paso de CI puede condicionarse a él
exactamente igual que una comprobación de Icinga; el documento es un artefacto
adicional e independiente.

- `json` es un array JSON con el mismo documento descrito en
  [Notificaciones por webhook](#webhook-notifications), un objeto por host.
- `sarif` es SARIF 2.1.0, para un panel de análisis de código. Sus hallazgos
  proceden de los mismos hechos que la salida de texto del complemento, así que
  un resultado SARIF nunca dice nada que no diga la línea de Nagios.
- `junit` es XML de JUnit con un `<testsuite>` por host y un `<testcase>` por
  hallazgo, más un caso `rating` siempre presente para que un host sin
  problemas también aparezca.

```shell
check-opencloud-security --host opencloud.example.com --format sarif \
  > opencloud-security.sarif
```

[`docs/output-formats.md`](../output-formats.md) compara todos los valores de
`--format`, incluidos `nagios` y `prometheus`, y
[Ejecutar la comprobación desde CI](../ci.md) contiene los pasos de GitHub
Actions y GitLab CI que suben el archivo.

## Checkmk {#checkmk}

Checkmk puede ejecutar este complemento de dos formas, y cuál le conviene
depende de desde dónde deba ejecutarse:

- **Como comprobación activa en el servidor Checkmk.** No hace falta nada de
  esto: Checkmk lee de forma nativa la línea de Nagios y sus datos de
  rendimiento. Añada la línea de comandos en *Setup > Services > Other
  services > Integrate Nagios plugins*.
- **Como comprobación local en un host con agente**, que es lo que necesita
  cuando la instancia solo es accesible desde dentro de una red en la que no
  está el servidor Checkmk. `--format checkmk` escribe la línea propia del
  agente (estado, nombre del servicio, métricas, detalle), una por cada host de
  `--host`:

  ```shell
  check-opencloud-security --host opencloud.example.com --format checkmk
  ```

  ```text
  0 "OpenCloud_Security_opencloud.example.com" rating=5|vulnerabilities=0|… OK: Server is up to date…
  ```

  [`contrib/checkmk/opencloud_security`](../../contrib/checkmk/opencloud_security)
  es esa llamada como script listo para instalar.

El nombre del servicio lo da la instancia analizada, porque el host que ejecuta
el agente rara vez es la instancia que se analiza. **Instale la comprobación
local en un subdirectorio numérico** (`local/3600/`), o se ejecutará en cada
llamada al agente, una vez por minuto, contra la instancia de producción de
alguien. [`docs/checkmk.md`](../checkmk.md) describe ambas vías por completo,
las métricas y el significado de los estados.

## GitHub Action {#github-action}

[`action.yml`](../../action.yml) ejecuta la misma comprobación como paso, para
que un flujo de trabajo pueda analizar una instancia de forma programada sin
instalar nada por su cuenta. **El runner tiene que poder llegar a la
instancia**: un runner alojado no ve nada que esté detrás de su cortafuegos,
para eso está un runner propio, y lo que el análisis mide sobre TLS, la
obligatoriedad de HTTPS y los puertos de depuración accesibles es lo que ve
alguien de fuera en la red del runner.

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

**Fije la etiqueta.** El calendario de versiones y la versión de OpenCloud más
reciente conocida van *dentro* del paquete, así que la versión que se ejecuta
forma parte del veredicto: `@v1.18.2` instala la 1.18.2, mientras que una rama
o un SHA de commit instala la versión más reciente que haya el día en que se
ejecuta el flujo de trabajo, y lo indica en una anotación de advertencia.

| Entrada | Valor predeterminado | Qué hace |
| --- | --- | --- |
| `target` | *obligatorio* | La instancia que se analiza, como nombre de host o URL. |
| `version` | la etiqueta fijada | La versión de la comprobación que se instala. |
| `format` | `json` | `json`, `sarif`, `junit` o `nagios`. |
| `output-file` | `opencloud-security.json` | Dónde se escribe la salida. |
| `fail-on` | `warning` | `warning`, `critical` o `never`. |
| `warning` | valor predeterminado del complemento | Nota igual o inferior a la cual el resultado es WARNING. |
| `critical` | valor predeterminado del complemento | Nota igual o inferior a la cual el resultado es CRITICAL. |
| `check-hardening` | `true` | Tiene en cuenta las medidas de refuerzo en el resultado. |
| `ignore-hardening` | ninguno | Identificadores de refuerzo que se excluyen, separados por comas. |
| `release-track` | `auto` | `auto`, `rolling`, `production` o `lts`. |
| `releases-token` | ninguno | Un token para el límite de frecuencia del canal de versiones; no necesita ámbitos. |
| `summary` | `true` | Escribe el resultado en el resumen del trabajo. |
| `extra-args` | ninguno | Otras opciones del complemento, pasadas tal cual. |

Por defecto, el paso falla con cualquier resultado peor que OK.
`fail-on: critical` tolera un WARNING pero sigue fallando con CRITICAL y con
UNKNOWN, porque un análisis que no se ha ejecutado no es un aprobado;
`fail-on: never` siempre tiene éxito y deja la decisión a un paso posterior
que lea las salidas:

| Salida | Qué contiene |
| --- | --- |
| `exit-code` | El código de salida de Nagios: `0` OK, `1` WARNING, `2` CRITICAL, `3` UNKNOWN. |
| `status` | `OK`, `WARNING`, `CRITICAL` o `UNKNOWN`. Solo con `format: json`. |
| `rating` | La nota, de 0 a 5. Solo con `format: json`. |
| `rating-label` | La letra: `A+`, `A`, `C`, `D`, `E` o `F`. Solo con `format: json`. |
| `message` | El resumen de una línea. Solo con `format: json`. |
| `result-file` | El archivo en el que se escribió la salida. |

La configuración llega al complemento como variables de entorno `COS_*` y no
en la línea de comandos, para que un destino no acabe en un registro público.

[Ejecutar la comprobación desde CI](../ci.md) contiene el resto: enviar
`format: sarif` al panel de análisis de código, informar sin hacer fallar el
trabajo y el equivalente en GitLab CI.

## Variables de entorno {#environment-variables}
Cada opción tiene una variable de entorno equivalente con el prefijo `COS_`
(consulte la tabla anterior). Esto es especialmente útil con Docker, systemd y
cron, donde definir variables de entorno suele ser más cómodo que editar una
línea de comandos. **Una opción explícita en la línea de comandos siempre
prevalece sobre su variable de entorno.**

```shell
export COS_HOST=opencloud.example.com
export COS_PROXY=http://proxy.example.com:3128
check-opencloud-security
```

Los análisis no leen `.netrc`, `HTTP_PROXY`, `HTTPS_PROXY` ni las variables de
entorno del paquete de CA de Requests. Configure un proxy explícitamente con
`--proxy`/`COS_PROXY` y una CA privada con `--ca-file`/`COS_SCANNER_TLS_CA_FILE`.
La entrega restringida de webhooks fija sus direcciones validadas y no puede
usar un proxy que resuelva nombres; enviar un webhook a través de un proxy
requiere la exención explícita `--allow-private-webhooks`.

Las variables booleanas (`COS_DEBUG`, `COS_CHECK_HARDENING`, `COS_INSECURE`,
...) aceptan `1`, `true`, `yes` u `on` (sin distinguir mayúsculas) para activar
la opción correspondiente; cualquier otro valor (incluido no definida o vacía)
se trata como desactivado.

Los mismos valores pueden proceder también de un archivo YAML o de un
proveedor de secretos; consulte
[Archivo de configuración y secretos](#configuration-file-and-secrets).

## El escáner incorporado {#the-built-in-scanner}
El complemento tiene **un solo** backend: el escáner de
[`opencloud_local_scan/`](../../opencloud_local_scan/README.md), que se ejecuta
en el proceso del complemento y calcula el veredicto por sí mismo.

El escáner se conecta desde el host en el que ejecuta el complemento. Por eso
puede comprobar direcciones privadas y nombres de host internos sin enviar el
destino ni sus resultados a un servicio de análisis alojado.

No hay nada que activar ni ninguna opción `--scan-backend` que indicar. Todo lo
que sigue describe qué hace el escáner incorporado y cómo ajustarlo.

### Qué comprueba el escáner {#what-the-scanner-checks}

El escáner lee `/status.php`, las capacidades, las cabeceras de seguridad y el
descubrimiento OIDC, y después sondea rutas y puertos que deberían exigir
autenticación o permanecer privados. Las comprobaciones adicionales cubren TLS,
DNS, cookies, CORS, TRACE, archivos expuestos, servicios de depuración y
ajustes de iframe. También prueba las credenciales de demostración publicadas
contra el proveedor de identidad propio de la instancia. Use
`--no-extra-checks` para desactivar los sondeos adicionales.

Una comprobación adicional fallida limita la nota (critical -> `D`, high ->
`C`, medium -> `A`, low -> `A+`); defina `scanner.extra_checks_rating: false`
para notificarlas sin que afecten a la nota.

**[Qué lee el escáner y qué no lee deliberadamente](../scanner-checks.md)** es
el inventario completo: cada punto de acceso, cada comprobación y su gravedad,
las observaciones que se registran pero nunca se califican (quién inicia la
sesión de los usuarios, qué hay delante de la instancia, qué integraciones de
ofimática y calendario son visibles), cómo se lee correctamente la versión, qué
puertos de depuración se sondean y las preguntas que un análisis desde fuera no
puede responder.

El razonamiento de cada grupo de comprobaciones tiene su propia página:
[`docs/csp.md`](../csp.md), [`docs/tls.md`](../tls.md),
[`docs/cookies.md`](../cookies.md),
[`docs/authentication.md`](../authentication.md),
[`docs/sharing.md`](../sharing.md), [`docs/exposure.md`](../exposure.md),
[`docs/embedding.md`](../embedding.md),
[`docs/lifecycle.md`](../lifecycle.md) y
[`docs/status-php.md`](../status-php.md).

Todo lo que un análisis no puede ver (el registro de auditoría, el
cortafuegos, la política de su proveedor de identidad, sus copias de
seguridad) está en
**[Ejecutar OpenCloud en una infraestructura segura](../secure-deployment.md)**.

### TLS y certificados autofirmados {#tls-and-self-signed-certificates}

El proxy de OpenCloud termina él mismo TLS en el puerto 9200, y
`opencloud init` genera para él un certificado autofirmado. Muchos despliegues
ponen después delante un proxy inverso con un certificado real; muchos otros
no. Consulte [`docs/tls.md`](../tls.md) para ver todas las comprobaciones de TLS
y certificados que ejecuta este escáner y por qué importa cada una.

El escáner gestiona ambos casos sin necesidad de que se le indique ante cuál
está:

1. HTTPS con verificación de certificado. Si funciona, todo está bien.
2. HTTPS sin verificación. El análisis continúa y notifica `tlsTrusted` como
   comprobación fallida: se sigue obteniendo el resultado completo, junto con
   el hecho de que la cadena no es de confianza.
3. HTTP sin cifrar, notificado como `httpsAvailable` (critical).

`--insecure` (`COS_INSECURE`) omite el paso 1. La cadena no fiable se sigue
mostrando en la salida; simplemente deja de restar en la nota. Úselo para una
instancia que sabe que es autofirmada, para que un certificado realmente
defectuoso en otro lugar siga destacando.

### Puertos de depuración {#debug-ports}

Cada servicio de OpenCloud tiene un servicio de depuración que sirve
`/healthz`, `/readyz`, `/metrics`, `/config` y `/debug/pprof`. Escuchan por
defecto en loopback, así que un puerto de depuración que responde desde su host
de monitorización es un hallazgo real, normalmente un contenedor que publicó
todo el rango de puertos. El escáner sondea los cinco más reveladores (9205,
9141, 9124, 9134, 9239), cada uno con una única conexión TCP y un tiempo de
espera de tres segundos, así que un host protegido por cortafuegos cuesta hasta
15 segundos.

```yaml
scanner:
  check_debug_ports: true
  debug_ports: [9205, 9141]
  debug_port_timeout: 1
  concurrency: 8            # run the probes in parallel instead
```

Desactívelos por completo con `--no-debug-ports`. Qué puerto corresponde a qué
servicio, y cómo `scanner.concurrency` acorta una ejecución sin cambiar el
veredicto, se explica en
[Puertos de depuración](../scanner-checks.md#debug-ports).

### Todas las direcciones resueltas {#every-resolved-address}

Un análisis marca el nombre una vez y ve la dirección que el resolvedor puso
primero. Detrás de un grupo de nodos, eso es un solo nodo: el que no recibió
una actualización de configuración (sin HSTS, con cuentas de demostración que
siguen iniciando sesión, con una versión más antigua) atiende a parte de sus
visitantes y a ninguno de sus análisis. `tlsAddressParity` tampoco lo ve,
porque solo compara la identidad TLS de los puntos de acceso IPv4 e IPv6.

`--all-addresses` (`COS_ALL_ADDRESSES`, `scanner.check_all_addresses`) repite
las comprobaciones de versión, cabeceras, refuerzo y cuentas de demostración
contra cada dirección a la que se resuelve el nombre, y notifica
`addressParity` cuando no coinciden:

```
addressParity (high): Differs from 198.51.100.1 - 198.51.100.4: version 7.1.0 (expected 7.2.3); headers Strict-Transport-Security fails
```

Cada solicitud sigue llevando su nombre de host en `Host` y en SNI; solo cambia
la dirección a la que va la conexión, y las direcciones proceden de la
respuesta del resolvedor para ese nombre y de nada más. La primera dirección es
la referencia. El hallazgo tiene la gravedad de la peor diferencia (unas
cuentas de demostración que inician sesión en un nodo tienen la gravedad de ese
hallazgo, otra versión es `high` y cualquier otra divergencia es `medium`), y
una dirección que se resuelve pero no responde también lo hace fallar. Las
cabeceras y comprobaciones excluidas quedan fuera de la comparación.

Está desactivado por defecto: cuesta alrededor de una docena de solicitudes por
dirección, entre ellas un inicio de sesión de demostración, y un nombre con una
sola dirección (la mayoría de los despliegues) no tiene nada que comparar y no
recibe ningún hallazgo. Ve lo que ve el DNS: los nodos detrás de una única
dirección de balanceador de carga, o un resolvedor que devuelve un subconjunto
rotatorio del grupo, quedan fuera de su alcance. Las direcciones IPv6 se
omiten cuando `scanner.ipv6_enabled` está desactivado. El servicio web público
nunca lo ofrece; consulte
[ADR 0042](../../adr/0042-every-resolved-address-is-compared-only-when-the-operator-asks.md).

### Detección de fin de vida {#end-of-life-detection}

Un número de versión por sí solo no indica si una instancia de OpenCloud sigue
recibiendo correcciones de seguridad, porque OpenCloud mantiene a la vez tres
tipos de versiones:

| Canal          | Frecuencia                     | Con soporte hasta                  | Soporte      |
|:---------------|:-------------------------------|:-----------------------------------|:-------------|
| **Rolling**    | aproximadamente cada 3 semanas | que se publica su sucesora         | comunidad    |
| **Production** | aproximadamente cada 6 meses   | la siguiente versión production    | profesional  |
| **LTS**        | una línea production           | 2 años después de abrirse la línea | profesional  |

Consulte el [ciclo de vida de versiones de OpenCloud][lifecycle] para la
descripción oficial.

[lifecycle]: https://docs.opencloud.eu/docs/admin/resources/lifecycle/

El estado actual de cada canal, según el calendario incluido, está en la
versión en inglés de esta página, que la publicación de versiones regenera
automáticamente, y en la [página oficial de ciclo de vida][lifecycle].

Una línea sin soporte recibe la nota `F` y se notifica como `CRITICAL`:

```
CRITICAL: The 7.3 rolling release line is end-of-life and has no security fixes. Upgrade to 7.4.0.
OpenCloud 7.3.0 on cloud.example.com, rating: F, last scanned: 2026-08-12 15:18:08.839323
Release lifecycle: 7.3 (rolling), out of support since 2026-08-03, upgrade to 7.4.0
```

Una línea con soporte indica cuánto tiempo le queda, que es lo que hace que
merezca la pena monitorizar una instancia LTS:

```
Release lifecycle: 4.0 (lts), supported until 2027-12-01 (476 days left)
```

El periodo restante se publica también como el valor de rendimiento
`support_days_left`, para que un gráfico muestre cómo disminuye y pasa a
negativo cuando la línea ha vencido.

```yaml
scanner:
  use_release_schedule: true      # false disables the EOL check entirely
  # release_schedule: /etc/check-opencloud-security/schedule.json
```

O mediante el entorno: `COS_SCANNER_USE_RELEASE_SCHEDULE`,
`COS_SCANNER_RELEASE_SCHEDULE`.

Por qué la *misma* versión puede estar actualizada en un canal y llevar mucho
tiempo sin soporte en otro, cómo se construye y actualiza el calendario y qué
ocurre cuando una instancia es más reciente que el archivo con el que se
evalúa, se explica en
**[Canales de publicación, fin de vida y recomendación de actualización](../release-lifecycle.md)**.

### Base de datos de avisos de seguridad {#advisory-database}
Las vulnerabilidades conocidas se comparan con el rango de versiones
`[introduced, fixed)` de una base de datos local de avisos. Las fuentes se
combinan en este orden y se deduplican por identificador:

1. el archivo incluido en el paquete,
2. cada archivo de `scanner.vulnerability_db`,
3. el canal JSON de `scanner.vulnerability_feed`.

Se entienden el formato nativo
(`{"advisories": [{"id": ..., "introduced": ..., "fixed": ...}]}`), el formato
de la GitHub Advisory API y los documentos OSV, así que una instalación aislada
puede replicar un canal en un archivo sin conversión. Un canal inaccesible se
registra y se ignora: nunca convierte una instancia sana en `UNKNOWN`.

> **La base de datos incluida solo es tan completa como los avisos
> publicados.** Hasta ahora se han publicado pocos para OpenCloud.
> `GHSA-vf5j-r2hw-2hrw` (corregido en 4.0.3 y 5.0.2) es uno de ellos, y la base
> de datos se regenera desde OSV a medida que aparecen otros nuevos. Por eso
> `vulnerabilities: []` significa "nada de la base de datos que ha configurado
> coincide", no "se sabe que esta versión es segura". La mayor parte de la nota
> procede de las comprobaciones de configuración anteriores. Para incorporar
> avisos publicados después de construir su paquete, consulte
> [Mantener al día el calendario de versiones y los avisos de seguridad](../reference-data.md),
> o apunte `scanner.vulnerability_feed` a OSV o a su propia réplica de avisos.

### Ejecutar el escáner como servicio {#running-the-scanner-as-a-service}

El paquete incluye un segundo punto de entrada, `check-opencloud-scanner`.
Ejecuta exactamente el mismo escáner, una vez o como servicio:

```shell
## one-shot: print the full result document as JSON
check-opencloud-scanner scan opencloud.example.com

## as a service, on this machine only
check-opencloud-scanner serve --port 8811
```

| Punto de acceso                    | Comportamiento                              |
|:-----------------------------------|:--------------------------------------------|
| `POST /api/queue` (`url=<host>`)   | Analiza el host y devuelve `{"uuid": ...}`  |
| `GET /api/result/<uuid>`           | Devuelve el resultado guardado              |
| `POST /api/requeue` (`url=<host>`) | Descarta la caché y vuelve a analizar       |
| `GET /api/scan?url=<host>`         | Atajo: analiza y devuelve el documento      |
| `GET /healthz`                     | Sonda de actividad                          |

El complemento **no** se comunica con este servicio: no tiene backend remoto y
siempre analiza dentro de su propio proceso. El servicio existe para que varios
consumidores (un panel, un script, un segundo sistema de monitorización)
compartan un mismo resultado en caché, y para que los análisis puedan
ejecutarse desde un host más cercano a la instancia que el servidor de
monitorización. Los resultados se guardan en caché por host durante
`service.cache_ttl` segundos, 15 minutos por defecto.

**Escucha en `127.0.0.1` salvo que indique otra cosa, y cualquier otra
dirección requiere un token.** El servicio analiza el host que indique una
solicitud y no lo valida contra nada: es el modelo de confianza del
complemento, en el que un operador indica sus propias instancias. Accesible por
desconocidos y sin autenticación, esa misma propiedad lo convierte en una forma
de leer el interior de la red en la que se ejecuta. Por eso
`--listen`/`COS_SERVICE_LISTEN` en cualquier dirección que no sea loopback sin
`--token`/`COS_SERVICE_TOKEN` se niega a arrancar en lugar de servir sin
protección. Consulte
[ADR 0030](../../adr/0030-a-listener-binds-loopback-and-a-wide-bind-needs-a-credential.md).

Su ejecución en un contenedor, y el archivo ya preparado
[`docker/docker-compose.monitoring.yml`](../../docker/docker-compose.monitoring.yml),
que inicia el escáner y un contenedor de comprobación con secretos de Docker,
se describen en
**[Ejecutar el escáner como servicio](../scan-service.md)**.

En cambio, un simple `docker compose up` en ese directorio inicia la aplicación
web pública; consulte [la aplicación web](../webapp.md).

## Comprobación de actualizaciones {#update-check}
Una instancia de OpenCloud no tiene punto de acceso de actualización, así que
la pregunta "¿es esta la versión más reciente?" se responde comparando el
`productversion` que notifica la instancia con el canal de versiones de
OpenCloud en GitHub. `--update-source` elige de dónde procede ese número:

| Modo                        | Comportamiento                                                                  |
|:----------------------------|:--------------------------------------------------------------------------------|
| `auto` (predeterminado)     | Prueba el canal; ante cualquier fallo recurre a la versión incluida en el paquete |
| `feed`                      | Solo el canal. Un fallo se notifica como desconocido en lugar de ignorarse      |
| `pinned`                    | Usa `--latest-version`. Sin acceso a la red                                     |
| `bundled`                   | Usa la versión registrada en el archivo de datos incluido. Sin acceso a la red  |
| `off`                       | Omite por completo la comprobación de actualizaciones (igual que `--no-update-check`) |

```shell
## ask GitHub, with a token to stay clear of the anonymous rate limit
check-opencloud-security --host opencloud.example.com \
  --release-token 'secret://releases_token'

## fully offline: compare against a version you control
check-opencloud-security --host opencloud.example.com --latest-version 7.4.0
```

La API anónima de GitHub permite sesenta solicitudes por hora y dirección IP,
compartidas con todo lo demás que use esa dirección. Un token (basta uno de
permisos detallados sin ningún permiso) eleva mucho ese límite. En modo `auto`,
una consulta limitada por frecuencia no es un error: la comprobación recurre a
la versión incluida, que es tan reciente como el paquete instalado.

El resultado se notifica como una línea adicional de salida y como la métrica
de rendimiento `update_available`; con `--update-warning`, una actualización
pendiente convierte en `WARNING` un resultado que de otro modo sería `OK`. Un
fallo en la comprobación de actualizaciones nunca interrumpe la comprobación
de seguridad.

**Las recomendaciones de actualización se mantienen en su canal de
publicación.** A las instalaciones production y LTS se les ofrece una versión
de su propio canal, mientras que la versión más reciente en general se
notifica aparte. Defina `--release-track` para sustituir la detección
automática. Consulte
[Canales de publicación, fin de vida y recomendación de actualización](../release-lifecycle.md).

## Archivo de configuración y secretos {#configuration-file-and-secrets}
Todos los ajustes pueden estar en un archivo en lugar de en la línea de
comandos, y la forma más rápida de escribirlo es dejar que el complemento
pregunte:

```shell
check-opencloud-security --configure
```

El asistente pide el único ajuste obligatorio (el host), explica para qué
sirve y muestra un ejemplo. Todo lo demás tiene un valor predeterminado que
funciona, así que los ajustes opcionales se ofrecen grupo por grupo y solo se
piden si responde que sí. El resultado se escribe como JSON con modo `0600`, y
a partir de entonces se encuentra automáticamente:

```shell
check-opencloud-security          # no arguments needed any more
```

Use `--config` para indicar dónde guardarlo, p. ej.
`--configure --config /etc/check-opencloud-security/.env.json`. Un archivo
existente se muestra y se pide confirmación antes de sustituirlo. El
equivalente para el escáner por sí solo es `check-opencloud-scanner configure`.

El archivo se lee de `--config`, `COS_CONFIG_FILE`, `./.env.json`,
`./check-opencloud-security.yml`,
`~/.config/check-opencloud-security/.env.json` o
`/etc/check-opencloud-security/` (gana la primera coincidencia). Un sufijo
`.json` se lee como JSON, cualquier otro como YAML; ambos son
intercambiables. Consulte
[`config/check-opencloud-security.example.yml`](../../config/check-opencloud-security.example.yml)
para un ejemplo comentado por completo.

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

Las claves anidadas se corresponden una a una con las variables de entorno:
`scanner.target_port` es `COS_SCANNER_TARGET_PORT`, `releases.token` es
`COS_RELEASES_TOKEN`, `scanner.tls_min_days` es `COS_SCANNER_TLS_MIN_DAYS`. La
prioridad es **línea de comandos > variable de entorno > archivo de
configuración > valor predeterminado**.

**Los secretos nunca tienen que escribirse en el archivo ni en el entorno del
proceso.** Cualquier valor puede ser en su lugar una referencia `secret://`,
`file://`, `env://` o `exec://`, o nombrarse con un sufijo `_file` que apunte a
un archivo; consulte
**[Secretos en la configuración](../configuration.md)**.

## Umbrales de nota {#rating-thresholds}
El escáner califica una instancia desde `A+` (la mejor) hasta `F`. El
complemento convierte esa letra en una nota numérica y la compara con dos
umbrales inclusivos:

| Nota   | 5    | 4   | 3   | 2   | 1   | 0   |
|:-------|:-----|:----|:----|:----|:----|:----|
| Letra  | `A+` | `A` | `C` | `D` | `E` | `F` |

- `-c, --critical` / `COS_CRITICAL` (predeterminado `1`, es decir, `E`): una
  nota igual o inferior a este valor es `CRITICAL`.
- `-w, --warning` / `COS_WARNING` (predeterminado `3`, es decir, `C`): una nota
  igual o inferior a este valor es `WARNING`.

Además de los umbrales, siempre se aplican dos reglas:

- **Las vulnerabilidades conocidas elevan el estado al menos a `WARNING`**,
  aunque la nota general siga pareciendo aceptable. Los identificadores
  notificados aparecen en la salida.
- **Una versión sin soporte es siempre `CRITICAL`**, porque no recibe ninguna
  corrección de seguridad.

> **Un único hallazgo crítico no genera un aviso urgente por defecto.** El peor
> hallazgo limita la nota en lugar de fijarla: critical la limita a `2` (`D`),
> que el valor predeterminado `--critical 1` sigue notificando como `WARNING`.
> Es deliberado: evita que una sola ruta expuesta sea indistinguible de una
> instancia sin soporte. Si un hallazgo crítico debe despertar a alguien,
> ejecute con `--critical 2`.

Una nota fuera del rango documentado `0-5` da `UNKNOWN`. `--critical` no puede
ser mayor que `--warning`, y ambos deben estar dentro de `0-5`; de lo
contrario, el complemento se niega a ejecutarse.

```shell
## Only alert once the instance is actually end-of-life
check-opencloud-security --host opencloud.example.com --warning 1 --critical 0

## Page on any critical finding
check-opencloud-security --host opencloud.example.com --warning 4 --critical 2
```

### Perfiles de umbrales {#threshold-profiles}

`--profile` / `COS_PROFILE` nombra un conjunto ya preparado en lugar de
escribir siempre los mismos cinco indicadores:

| Perfil | `--warning` | `--critical` | `--check-hardening` | `--update-warning` | `--eol-warning` |
|:--|:--|:--|:--|:--|:--|
| `strict` | `4` (`A`) | `2` (`D`) | sí | sí | `90` |
| `ops` | `3` (`C`) | `1` (`E`) | sí | no | `30` |
| `lenient` | `2` (`D`) | `0` (`F`) | no | no | `0` |

Un perfil decide **cómo se juzgan las mismas mediciones, nunca con cuánta
intensidad se sondea la instancia**. Sin `--profile` nada cambia, y lo que
usted fije - indicador, variable de entorno o archivo - siempre gana.

## Comprobaciones de refuerzo {#hardening-checks}
Además de las comprobaciones de superado/fallido anteriores, el escáner
notifica qué medidas de refuerzo tiene la instancia. Con `--check-hardening` /
`COS_CHECK_HARDENING` también se evalúan.

Los nombres son escuetos porque acaban en el texto de las alertas. Ejecute el
complemento con `--debug` para que la explicación se imprima junto al
hallazgo, o léalas todas de una vez:
**[Medidas de refuerzo, una por una](../hardening.md)** explica qué significa
cada identificador, qué indica realmente un fallo y qué variable de entorno de
OpenCloud lo cambia, junto con las dos medidas en las que nadie puede influir y
cómo aceptar con `--ignore-hardening` un hallazgo que no se va a corregir.

En la línea "Missing hardening" pueden aparecer dos entradas más:
`httpsEnforced` cuando la instancia no exige HTTPS, y el nombre de cualquier
cabecera de seguridad de `setup.headers` que falte o sea demasiado débil (p.
ej. `Strict-Transport-Security`). `--debug` también las explica.

Todo lo que se notifica como ausente aparece en la salida y se exporta como la
métrica de rendimiento `hardenings_missing`. Un resultado que de otro modo
sería `OK` se eleva a `WARNING`; un `WARNING`/`CRITICAL` existente nunca se
rebaja.

```shell
check-opencloud-security --host opencloud.example.com --check-hardening
```

Algunos hallazgos son reales pero no se pueden resolver en su entorno: una CSP
que no puede endurecer sin romper la interfaz web, una cabecera HSTS que
controla su proxy inverso. `--ignore-hardening` acepta uno por su nombre, y la
nota se vuelve a calcular sin él; pero el hallazgo permanece en el resultado
JSON, marcado con `"ignored": true`, porque una exclusión suprime una alerta,
no la evidencia:

```bash
check-opencloud-security --host opencloud.example.com --check-hardening \
    --ignore-hardening 'cspWithoutUnsafeInline,hstsPreload'
```

Consulte
[Aceptar un hallazgo que no se va a corregir](../hardening.md#accepting-a-finding-you-are-not-going-to-fix)
para los comodines, lo que no hace una exclusión y por qué un archivo de
configuración es el mejor lugar para ella.

## Explicar una nota {#explaining-a-rating}
Use `--debug` (`COS_DEBUG=1`) para ver cómo se calculó la nota y qué significa
cada hallazgo. La explicación incluye la puntuación inicial y cada comprobación
que la limita.

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

El punto de partida es lo que darían solo la versión y la base de datos de
avisos: `5` actualizada, `4` una actualización de parche pendiente, `3` una
línea de versiones completa por detrás, `2` vulnerabilidades conocidas, `1`
vulnerabilidades críticas o altas, `0` fin de vida. Después, las
comprobaciones adicionales fallidas la limitan según su gravedad: `critical` a
`2`, `high` a `3`, `medium` a `4`, `low` a `5`. Una comprobación que falló pero
no decidió el resultado se sigue mostrando, marcada como tal, para que nada
parezca descartado en silencio.

Sin `--debug`, la salida mantiene el tamaño que quiere un sistema de
monitorización. El mismo desglose está siempre presente en el resultado del
análisis como `ratingExplanation`, así que se puede leer sin volver a ejecutar
la comprobación:

```shell
python -m opencloud_local_scan.cli scan opencloud.example.com | jq .ratingExplanation
```

Tenga en cuenta que `--debug` también cambia el registro a `DEBUG`, así que el
detalle a nivel HTTP va a stderr mientras la explicación va a stdout con el
resto de la salida del complemento.

## Qué subiría la nota {#what-would-raise-the-rating}

El plan de corrección enumera los cambios que mejorarían la nota, en el orden
en que el escáner calcula su efecto.

Cada resultado incluye `remediationPlan`, calculado con la misma función de
calificación tras eliminar los hallazgos paso a paso. El plan se deriva del
resultado y no necesita almacenamiento aparte.

```shell
python -m opencloud_local_scan.cli scan opencloud.example.com | jq .remediationPlan
```

`--debug` imprime la misma lista debajo de la explicación:

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

Conviene saber tres cosas sobre esa lista antes de actuar:

- **El orden no es arbitrario.** Los hallazgos de la misma gravedad comparten
  un mismo techo, así que corregir el primero de tres hallazgos medium no
  cambia nada. Los pasos que por sí solos no aportan nada se siguen mostrando
  (con `still 4/5` en lugar de `then 5/5`), porque omitirlos daría a entender
  que se pueden saltar.
- **Una actualización puede ser uno de los pasos.** Corregir hallazgos nunca
  puede elevar una nota por encima de lo que permite la versión instalada, así
  que el plan inserta la actualización en el punto en que empieza realmente a
  aportar algo.
- **Algunos hallazgos no se pueden corregir nunca.** Los indicadores que
  OpenCloud fija en el código se enumeran aparte como bloqueados, y acotan
  hasta dónde puede llegar el plan. Consulte
  [Medidas que no son ajustes](../hardening.md#measures-that-are-not-settings).

También se enumeran los hallazgos excluidos, marcados como tales: una
exclusión silencia una alerta, no corrige nada, y el plan lo dice.

El mismo plan aparece en el panel web, en las exportaciones JSON, CSV, SARIF y
PDF, y como la herramienta MCP `plan_remediation`.

### Agrupado por configuración {#grouped-by-where-the-change-is-made}

`remediationPlan.groups` agrupa los hallazgos abiertos según el sistema que
usted edita para corregirlos: **proxy inverso**, **proveedor de identidad**,
**OpenCloud** o **zona DNS**. También incluye los hallazgos que no limitan la
calificación, como una cabecera ausente.

Los hallazgos que resuelve un único cambio forman un solo cambio: todas las
cabeceras de seguridad ausentes son un bloque de cabeceras, varios problemas de
certificado un certificado nuevo, todas las rutas `exposed:/...` una
corrección, y la actualización cierra todos los avisos correspondientes. Cada
cambio indica sus hallazgos, `resolvesSeveral` y la calificación que daría por
sí solo, recalculada con la misma función de calificación. `groupSummary`
nombra los cambios que resuelven varios hallazgos a la vez. Los hallazgos
omitidos o fijados en el código no se ofrecen como cambios. `--debug`, el
panel web, el paquete de corrección y `plan_remediation` muestran también los
grupos.

## Notificaciones por webhook {#webhook-notifications}
El complemento puede enviar una notificación JSON a un punto de acceso
HTTP(S) cuando una comprobación alcanza un nivel crítico. La función es
**opcional y está desactivada por defecto**: solo se activa cuando se define
`--webhook-url` (o `COS_WEBHOOK_URL`).

```shell
check-opencloud-security --host opencloud.example.com \
  --webhook-url https://hooks.example.com/opencloud
```

- `--webhook-on` / `COS_WEBHOOK_ON` (predeterminado `critical`) elige el estado
  mínimo que desencadena una notificación. Cada nivel incluye los más graves:
  `critical`, `warning` (WARNING + CRITICAL), `unknown` (UNKNOWN + WARNING +
  CRITICAL) y `always`.
- `--webhook-format` / `COS_WEBHOOK_FORMAT` (predeterminado `generic`) envía
  el cuerpo como adjunto de Slack Block Kit (`slack`, que también aceptan
  Mattermost y los puentes de webhooks de Matrix más comunes), como embed de
  Discord (`discord`), o como notificación push para un servidor
  [ntfy](https://ntfy.sh) (`ntfy`) o [Gotify](https://gotify.net) (`gotify`),
  en lugar del documento plano propio del complemento. El valor
  predeterminado no cambia, así que es totalmente opcional:
  ```shell
  check-opencloud-security --host opencloud.example.com \
    --webhook-url https://hooks.slack.com/services/... \
    --webhook-format slack

  check-opencloud-security --host opencloud.example.com \
    --webhook-url https://ntfy.example.com/opencloud \
    --webhook-format ntfy
  ```
  Con `ntfy`, apunte `--webhook-url` a la URL del **tema**: el tema se lee de
  ella y la publicación en sí va a la raíz del servidor, que es el único lugar
  donde ntfy lee JSON. Una URL que no indica ningún tema se rechaza al
  arrancar en lugar de fallar en cada notificación.
  Todo lo demás (Alertmanager, un receptor propio) sigue necesitando el
  documento `generic`; [Recetas de webhooks](../webhook-recipes.md) tiene una
  para cada uno.
- `--webhook-header` / `COS_WEBHOOK_HEADERS` añade cabeceras a la solicitud,
  p. ej. para la autenticación. Repita la opción, o separe las entradas con
  `;` en la variable de entorno:
  `COS_WEBHOOK_HEADERS="X-Auth-Token: abc; X-Env: prod"`.
- `--webhook-timeout` / `COS_WEBHOOK_TIMEOUT` (predeterminado `10`) limita la
  llamada al webhook; es independiente del `--timeout` del análisis.
- Los destinos de webhook que se resuelven a direcciones privadas, de loopback
  o de enlace local se bloquean para evitar la falsificación de solicitudes del
  lado del servidor. Defina `--allow-private-webhooks` o
  `COS_ALLOW_PRIVATE_WEBHOOKS=true` solo para un receptor interno intencionado.

La entrega reutiliza `--retries` / `--backoff-factor`. **Un webhook que falla
nunca cambia el resultado de la comprobación**: el complemento añade
`Webhook delivery failed` a su salida y sigue terminando con el estado que
midió, así que un canal de notificación roto no puede ocultar (ni simular) una
instancia vulnerable.

Cuando se comprueban varios hosts en una ejecución, cada host que alcanza el
estado configurado genera su propia notificación. Los análisis que fallan por
completo (host inaccesible, TLS roto) también notifican cuando `--webhook-on`
es `unknown` o `always`.

> **Nota:** trate el webhook como un complemento de su sistema de
> monitorización, no como un sustituto. Se envía y se olvida, y no se reintenta
> más allá del presupuesto de reintentos configurado.

**[Recetas de webhooks](../webhook-recipes.md)** contiene la carga útil
completa campo por campo, cómo verificar su firma y un adaptador para cada
receptor que quiere su propio JSON (Slack, Discord, ntfy, Alertmanager), además
de [Uptime Kuma](../webhook-recipes.md#uptime-kuma), cuyo monitor Push acepta
el documento tal cual y trata el silencio como un fallo, así que también se
detecta una comprobación que ha dejado de ejecutarse.

## Notificar solo lo que ha cambiado {#reporting-only-what-changed}
Use `--baseline` para guardar los hallazgos de cada ejecución y comparar con
ellos la siguiente. Con `--warn-on-new`, un resultado sin cambios notifica OK;
un hallazgo nuevo o una nota más baja restablecen el estado de alerta normal.

```bash
check-opencloud-security -H opencloud.example.com \
    --check-hardening \
    --baseline /var/lib/check_opencloud/baseline.json \
    --warn-on-new
```

El estado completo se imprime en cualquier caso: solo se suprime la alerta,
nunca la evidencia. **Una versión sin soporte siempre genera una alerta**, por
mucho tiempo que lleve en la línea base.

**[Notificar solo lo que ha cambiado](../baseline.md)** contiene los formatos
de comparación (`text`, `markdown`, `slack`, `json`), qué cuenta como
regresión y las reglas que impiden que una línea base oculte algo.

## ¿Está actualizado el propio complemento? {#is-the-plugin-itself-up-to-date}
`--self-update-check` consulta PyPI como mucho una vez al día y añade una nota
cuando hay un complemento más reciente. Actualizar el complemento actualiza
también sus datos incluidos de versiones y avisos de seguridad.

```
Plugin update available: check-opencloud-security 1.2.0 is published, this is 1.1.0 (upgrade with --upgrade-self)
```

Está desactivado por defecto, se guarda en caché en
`${XDG_CACHE_HOME:-~/.cache}/check-opencloud-security/` y **nunca cambia el
código de salida**: que PyPI haya respondido o no no dice nada del estado de la
instancia monitorizada. Todos los fallos (sin red, un proxy de por medio, PyPI
caído) son silenciosos.

Actualice con [`--upgrade-self`](../installation.md#updating), o vea antes qué
haría con `--upgrade-self check` (`--upgrade-self --check-only` es lo mismo).

## Reintentos y espera {#retries-and-backoff}
Los errores de red transitorios (tiempos de espera agotados, conexiones
restablecidas, respuestas `5xx` de la instancia) se reintentan automáticamente
con espera exponencial antes de que la comprobación se rinda y notifique
`UNKNOWN`.

- `--retries` / `COS_RETRIES` (predeterminado `2`): número de reintentos tras
  el primer intento (así que el valor predeterminado hace hasta 3 intentos en
  total).
- `--backoff-factor` / `COS_BACKOFF_FACTOR` (predeterminado `0.5`): espera base
  en segundos; la espera antes de cada reintento se duplica
  (`backoff_factor * 2^attempt`), p. ej. `0.5s`, `1s`, `2s`, ...
- `--timeout` / `COS_TIMEOUT` (predeterminado `10`): cuánto puede tardar una
  sola solicitud antes de contar como fallo. Auméntelo en enlaces lentos o al
  analizar a través de un proxy.

Defina `--retries 0` para desactivar por completo los reintentos y fallar
rápido. Un reintento vuelve a ejecutar todo el análisis, así que un número
alto de reintentos contra un host inaccesible hace que la comprobación tarde
bastante más de lo que sugiere el tiempo de espera por sí solo.

## Datos de rendimiento {#performance-data}
La salida incluye datos de rendimiento estándar de Nagios/Icinga después de un
carácter `|`, para que Icinga2, Grafana, etc. puedan representar los
resultados a lo largo del tiempo:

```
rating=5;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=1.234s;;;0;
```

La métrica `rating` lleva los umbrales WARNING y CRITICAL configurados en la
sintaxis de rangos de Nagios (`@0:3` significa "avisar dentro de 0-3"), así que
Icinga2 los dibuja en el gráfico sin configuración adicional.

| Métrica               | Significado                                                        |
|:----------------------|:-------------------------------------------------------------------|
| `rating`              | Nota numérica del análisis, `0`-`5` (`5`=A+ ... `0`=F), `U` si es desconocida |
| `vulnerabilities`     | Número de vulnerabilidades conocidas notificadas para la versión analizada |
| `time`                | Tiempo dedicado al análisis, en segundos                           |
| `hardenings_missing`  | Medidas de refuerzo ausentes (solo con `--check-hardening`)        |
| `extra_checks_failed` | Número de comprobaciones adicionales fallidas                      |
| `update_available`    | `1` cuando existe una versión de OpenCloud más reciente            |
| `support_days_left`   | Días hasta que la línea de versiones pierde el soporte (negativo si ha vencido) |
| `cert_days_left`      | Días hasta que caduca el certificado TLS (negativo si ya ha caducado) |
| `upgrade_path_complete` | `1` cuando la actualización recomendada corrige todos los avisos conocidos, `0` cuando deja alguno abierto; ausente sin avisos |
| `waiver_days_left`    | Días hasta que termina una exención `--waive-until` y una comprobación fallida vuelve a alertar; ausente si ninguna depende de un plazo |
| `coverage_inconclusive` | Comprobaciones que el análisis ejecutó sin llegar a una conclusión |
| `coverage_not_checked` | Comprobaciones que el análisis no ejecutó |

`cert_days_left` se omite, en lugar de valer cero, cuando no se midió nada: un
análisis por HTTP sin cifrar, un host que rechazó el handshake o un certificado
cuyas fechas no se pudieron interpretar. Lleva los umbrales del propio análisis
y no una segunda opinión inventada para el gráfico: aviso igual o por debajo de
`scanner.tls_min_days`, el mismo margen con el que salta el hallazgo
`tlsCertificate`, y crítico cuando el certificado ya ha caducado.

`waiver_days_left` cuenta desde el análisis hasta el próximo momento en que una
exención temporal deja de ocultar una comprobación fallida. Con
`--waiver-warning DÍAS`, el valor lleva esa ventana como rango de aviso.
`coverage_inconclusive` y `coverage_not_checked` explican la nota sin cambiarla
nunca, por eso no llevan umbrales.

Fuera de Icinga2, los mismos números llegan a Prometheus mediante el textfile
collector de node_exporter o una Pushgateway; consulte
[Prometheus y Grafana](../prometheus.md).

## Caché {#caching}
El complemento no guarda ninguna caché: cada ejecución vuelve a analizar la
instancia, así que no hay nada que invalidar ni ninguna opción para forzar un
análisis nuevo.

El único lugar donde sí hay caché es el
[servicio de análisis](#running-the-scanner-as-a-service) opcional, que
reutiliza un resultado durante `service.cache_ttl` segundos.
`POST /api/requeue` lo descarta y vuelve a analizar.

## Ejemplos de salida {#example-output}

Una instancia sana:

```Shell
$ check-opencloud-security -H opencloud.example.com
OK: Server is up to date. No known vulnerabilities.
OpenCloud 7.4.0 on opencloud.example.com, rating: A+, last scanned: 2026-05-29 08:50:58.000000
Additional checks: all passed
Coverage: 84 checks evaluated, 6 skipped, 2 indeterminate, 1 network-limited | rating=5;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=0.731s;;;0; extra_checks_failed=0;;;0;
```

Entre las líneas de detalle y los datos de rendimiento, una línea `Coverage:`
dice cuánto de la comprobación llegó realmente a una conclusión - `84 checks
evaluated, 6 skipped, 2 indeterminate, 1 network-limited`. Una comprobación
correcta y otra que nunca se ejecutó dejan por lo demás el mismo rastro, así
que la línea nombra las lagunas: `skipped` es una prueba que el análisis no
ejecutó, `indeterminate` una que se ejecutó sin decidir y `network-limited`
una que agotó el tiempo o no tenía ruta - DNSSEC, un proveedor de identidad
externo, un extremo opcional -, algo que otro punto de observación podría
responder. No cambia la nota ni el código de salida, y un documento anterior
al bloque de cobertura no imprime ninguna línea, porque "este informe no lo
dice" no es "no se pasó nada por alto".

Una versión mayor que ya no recibe correcciones, siempre CRITICAL,
independientemente de los umbrales:

```Shell
$ check-opencloud-security -H opencloud.example.com
CRITICAL: The 7.3 rolling release line is end-of-life and has no security fixes. Upgrade to 7.4.0.
OpenCloud 1.0.0 on opencloud.example.com, rating: F, last scanned: 2026-05-30 07:48:58.000000
Additional checks: all passed | rating=0;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=0.842s;;;0; extra_checks_failed=0;;;0;
```

Un único hallazgo crítico limita la nota a `D`, que los umbrales
predeterminados notifican como WARNING; consulte
[Umbrales de nota](#rating-thresholds):

```Shell
$ check-opencloud-security -H opencloud.example.com
WARNING: Rating D is at or below the warning threshold C, but no known vulnerabilities.
OpenCloud 7.4.0 on opencloud.example.com, rating: D, last scanned: 2026-05-29 08:51:33.000000
Additional checks failed (1): exposed:/opencloud.yaml | rating=2;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=0.860s;;;0; extra_checks_failed=1;;;0;
```

Con `--check-hardening` en una instancia production cuyo proxy sigue
ofreciendo autenticación HTTP Basic:

```Shell
$ check-opencloud-security -H opencloud.example.com --check-hardening
WARNING: 3 hardening measure(s) missing, but no known vulnerabilities.
OpenCloud 7.2.3 on opencloud.example.com, rating: B, last scanned: 2026-08-12 15:58:04.138671
Release lifecycle: 7.2 (production), current release
Missing hardening: basicAuthDisabled, cspWithoutUnsafeInline, publicLinkPasswordEnforced (run with --debug for what each means and how to fix it)
Additional checks failed (1): basicAuthDisabled
Update check (feed, installed 7.2.3): up to date | rating=4;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=1.835s;;;0; hardenings_missing=3;;;0; extra_checks_failed=1;;;0; update_available=0;;;0;1
```

La comprobación `medium` fallida limita la nota a `4` (`A`). Una medida que
solo evalúa `--check-hardening` puede elevar el estado de monitorización a
WARNING sin cambiar la letra. Use `--debug` para ver qué regla se aplica;
consulte [Explicar una nota](#explaining-a-rating).

## Guías de despliegue {#deployment-guides}
El [índice de la documentación](../README.md) agrupa las instrucciones de
despliegue y los ejemplos prácticos por tarea. Estos son los puntos de partida
más habituales:

| Guía | Qué trata |
|:------|:---------------|
| [Ejecutar OpenCloud en una infraestructura segura](../secure-deployment.md) | Todo lo que un análisis no puede ver: un proveedor de identidad externo, el registro de auditoría, el cortafuegos y dónde encaja la monitorización continua |
| [Instalar el complemento](../installation.md) | pipx/uv/pip, actualizaciones, autocompletado del shell, Docker y los objetos de Icinga2 y Nagios |
| [Referencia de opciones de la CLI](../cli-reference.md) | Cada opción, su valor predeterminado y la variable de entorno que define lo mismo |
| [Ejemplos prácticos](../examples.md) | Invocaciones completas para las situaciones más habituales |
| [El servicio público de análisis](../webapp.md) | La aplicación web: FastAPI, un worker de ARQ y Redis, con cola, protección contra SSRF y límites de frecuencia |
| [Usar el escáner desde un agente de IA](../mcp.md) | El punto de acceso MCP, configurado para Claude Code, Claude Desktop, Copilot, Cursor, Zed y Windsurf |
| [Solución de problemas](../troubleshooting.md) | Los errores con los que se encuentra realmente la gente, y la referencia de códigos de salida |

¿Algo no funciona? Empiece por
[Solución de problemas](../troubleshooting.md), que también contiene la
referencia de códigos de salida.

## Ejemplos {#examples}
Las invocaciones completas, listas para copiar y pegar, para las situaciones
más habituales (lo básico, canales de publicación, exclusiones, instancias que
no están en internet, umbrales y notificaciones, una regla apply de Icinga2 y
el escáner por sí solo) están en
**[Ejemplos prácticos](../examples.md)**.

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
