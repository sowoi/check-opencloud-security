# Mantener al día el calendario de versiones y los avisos de seguridad de OpenCloud

El escáner usa un calendario de versiones para determinar el estado de soporte
y una base de datos de avisos de seguridad para identificar vulnerabilidades
conocidas. Ambos se incluyen en el paquete y pueden quedar desactualizados
entre actualizaciones del paquete. Actualizarlos por separado permite que el
escáner reconozca versiones y avisos más recientes.

`check-opencloud-scanner refresh-data` cubre ese hueco sin actualizar el
paquete. Esta página explica qué descarga y cómo comprueba los datos, cómo
ejecutarlo a diario y cómo indicar a la comprobación que use el resultado.

<!-- TOC -->
* [Mantener al día el calendario de versiones y los avisos de seguridad](#keeping-the-release-schedule-and-advisories-current)
  * [Cuándo lo necesita](#when-you-need-it)
  * [Ejecutar una actualización](#running-a-refresh)
  * [De dónde proceden los datos y cómo se comprueban](#where-the-data-comes-from-and-how-it-is-checked)
    * [Verificación de firmas](#signature-verification)
    * [Las comprobaciones que se aplican en todos los casos](#the-checks-that-apply-either-way)
  * [Usar los archivos actualizados](#using-the-refreshed-files)
  * [Ejecutarlo a diario con systemd](#running-it-daily-with-systemd)
  * [Réplicas y hosts sin acceso a internet](#mirrors-and-hosts-without-internet-access)
  * [Sus propios avisos de seguridad](#your-own-advisories)
  * [Aspectos que conviene conocer](#points-worth-knowing)
<!-- TOC -->


## Cuándo lo necesita {#when-you-need-it}

- **Un análisis menciona una versión que el calendario no conoce.** La línea
  de ciclo de vida indica entonces que la versión es más reciente que todo lo
  que contiene el calendario de versiones incluido, y el documento de
  resultado lleva `"scheduleStale": true`. Consulte
  [Canales de publicación, fin de vida y recomendación de actualización](../release-lifecycle.md).
- **Se publicó un aviso de seguridad después de construir su paquete.** La
  base de datos incluida no puede relacionarlo, así que el análisis no
  notifica vulnerabilidades conocidas para una versión que sí tiene una.
- **Fija la versión del paquete** y lo actualiza según su propio calendario, no
  cada vez que aparece una versión.

Un host que actualiza el paquete con prontitud obtiene así los mismos datos y
no necesita nada de esto. El [servicio público de análisis](../webapp.md)
actualiza su propia copia en tiempo de ejecución y tampoco lo necesita.

## Ejecutar una actualización {#running-a-refresh}

```bash
check-opencloud-scanner refresh-data --output-dir /var/lib/check-opencloud-security
```

Si tiene éxito, imprime los dos archivos que ha escrito y termina con `0`:

```text
/var/lib/check-opencloud-security/release_schedule.json
/var/lib/check-opencloud-security/vulnerabilities.json
```

| Opción | Valor predeterminado | Qué hace |
|:--|:--|:--|
| `--output-dir` | `~/.cache/check-opencloud-security` | Directorio en el que se escriben los dos archivos. Se crea si no existe |
| `--timeout` | `30` | Segundos permitidos para cada solicitud |
| `--schedule-url` | *(ninguno)* | Lee el calendario de versiones de esta página de ciclo de vida o réplica, **sin verificar**. Consulte [Réplicas](#mirrors-and-hosts-without-internet-access) |
| `--advisory-url` | *(ninguno)* | Consulta este punto de acceso OSV o réplica, **sin verificar** |

Cualquier fallo termina con `1` y el motivo en stderr: un error de red, un
documento que no supera una comprobación o una firma que no coincide. No se
escribe nada salvo que ambos documentos sean correctos, así que los archivos
anteriores se quedan exactamente donde estaban. Por eso una tarea de cron o un
temporizador pueden ejecutarlo sin supervisión. Un mal día en el origen nunca
sustituye datos buenos por otros peores.

Añada `-vv` para ver cómo se verifica cada firma:

```bash
check-opencloud-scanner -vv refresh-data --output-dir /var/lib/check-opencloud-security
```

## De dónde proceden los datos y cómo se comprueban {#where-the-data-comes-from-and-how-it-is-checked}

De forma predeterminada, la actualización **no** consulta en directo OSV ni la
página de ciclo de vida de OpenCloud. Lee `release_schedule.json` y
`vulnerabilities.json` de la rama `main` del repositorio de este proyecto. Son
los archivos que una persona encargada del mantenimiento ya ha revisado e
integrado, en las pull requests que abren los flujos de trabajo diarios de
datos del proyecto. A su host no llega nada que no haya revisado una persona.
Consulte
[ADR 0027](../../adr/0027-refreshed-reference-data-is-attested-not-merely-fetched.md).

### Verificación de firmas {#signature-verification}

Cada cambio en esos dos archivos en `main` se certifica con
[Sigstore](https://www.sigstore.dev/) mediante el flujo de trabajo
`attest-security-data.yml` de este repositorio. La actualización descarga esa
certificación y comprueba que la firmó ese flujo de trabajo concreto, en
`main`, en este repositorio. Una firma de cualquier otra ejecución de GitHub
Actions no cuenta.

La verificación necesita el extra `signing`, que es opcional porque añade
alrededor de una docena de paquetes más:

```bash
pipx install 'check-opencloud-security[signing]'
```

Para añadir el extra a una instalación existente con pipx, vuelva a ejecutar
ese comando con `--force`. [Instalar el complemento](../installation.md)
contiene los equivalentes para uv y pip.

Hay tres resultados posibles:

| Resultado | Qué ocurre |
|:--|:--|
| La firma se verifica | Se usa el documento |
| No se pudo *comprobar* la firma | Una advertencia y, después, solo las comprobaciones estructurales descritas más abajo. Causas: el extra no está instalado, GitHub o la raíz de confianza de Sigstore no están accesibles, o todavía no se ha publicado una certificación para ese contenido |
| Hay una firma y es **incorrecta** | La actualización se detiene, termina con `1` y no escribe nada |

Sin el extra, cada ejecución registra esto para cada archivo y aun así tiene
éxito:

```text
WARNING check_opencloud.refresh_data: Refreshing the release schedule without verifying its signature: the 'signing' extra (sigstore) is not installed. Install the 'signing' extra (pip install check-opencloud-security[signing]) to verify it.
```

Un host que muestra esta advertencia no está comprobando de dónde proceden sus
datos. Instale el extra en todos los lugares donde la actualización importe.

### Las comprobaciones que se aplican en todos los casos {#the-checks-that-apply-either-way}

Una firma verificada demuestra de dónde procede un documento, no que tenga
sentido. Por eso estas comprobaciones se ejecutan en cada actualización, con
firma o sin ella:

- **El calendario de versiones no puede perder ninguna línea de versiones.**
  Todas las líneas del calendario incluido en el paquete instalado deben seguir
  presentes. Una página de ciclo de vida truncada o reescrita no puede hacer
  que una versión antigua parezca tener soporte sin que se note.
- **La base de datos de avisos debe tener entradas utilizables.** Debe
  contener al menos un aviso, y cada aviso necesita un límite de versión. Un
  aviso abierto por ambos extremos coincidiría con todas las versiones de
  OpenCloud que han existido.
- **Cada archivo se sustituye de forma atómica.** Un lector nunca ve medio
  archivo.

## Usar los archivos actualizados {#using-the-refreshed-files}

La actualización solo escribe archivos. Nunca escribe en el paquete instalado,
así que nada cambia hasta que se indica a la comprobación dónde buscar:

```yaml
scanner:
  release_schedule: /var/lib/check-opencloud-security/release_schedule.json
  vulnerability_db:
    - /var/lib/check-opencloud-security/vulnerabilities.json
```

O mediante el entorno:

```bash
COS_SCANNER_RELEASE_SCHEDULE=/var/lib/check-opencloud-security/release_schedule.json
COS_SCANNER_VULNERABILITY_DB=/var/lib/check-opencloud-security/vulnerabilities.json
```

Los dos ajustes se comportan de forma distinta:

- `release_schedule` **sustituye** al calendario incluido.
- `vulnerability_db` **se añade** a la base de datos incluida. Las entradas se
  deduplican por identificador, así que es seguro indicar el archivo
  actualizado junto al incluido.

Tanto el complemento como `check-opencloud-scanner scan` leen los mismos
ajustes. Confirme que se han aplicado con la salida JSON del escáner:

```bash
check-opencloud-scanner -c /etc/check-opencloud-security/config.yml \
    scan opencloud.example.com | jq '.advisorySources, .lifecycle.scheduleUpdated'
```

`scheduleUpdated` debería ser la fecha del calendario actualizado, y
`advisorySources` debería incluir el archivo actualizado.

**Compruebe ambos después de cualquier cambio de ruta o de usuario, porque
ninguno de los dos fallos es visible:**

- **Un archivo de calendario ausente o ilegible desactiva la comprobación de
  fin de vida.** La comprobación no recurre al calendario incluido. La línea de
  ciclo de vida dice `Release lifecycle: unknown (no release schedule available)`,
  `scheduleUpdated` es `null` y no se registra nada por debajo de `-vv`. Una
  versión sin soporte se evalúa entonces solo por su configuración. En las
  pruebas, una instancia 2.3.0 que de otro modo sería CRITICAL obtuvo `OK` y
  `A+`.
- **Un archivo de avisos ausente o ilegible se omite con una advertencia** en
  stderr (`Advisory file ... does not exist`, o
  `Ignoring advisory file ...: Permission denied`). Un archivo ilegible sigue
  apareciendo en `advisorySources`, así que lea la advertencia y no la lista.

## Ejecutarlo a diario con systemd {#running-it-daily-with-systemd}

[`contrib/systemd/`](../../contrib/systemd/) contiene un servicio oneshot
reforzado y un temporizador para él:
[`check-opencloud-security-refresh.service`](../../contrib/systemd/check-opencloud-security-refresh.service)
y
[`check-opencloud-security-refresh.timer`](../../contrib/systemd/check-opencloud-security-refresh.timer).
El servicio escribe en `/var/lib/check-opencloud-security` mediante
`StateDirectory=` y no puede escribir en ningún otro lugar. El temporizador lo
ejecuta a diario, con una variación aleatoria de hasta una hora, y recupera las
ejecuciones perdidas tras una interrupción.

```bash
sudo cp contrib/systemd/check-opencloud-security-refresh.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now check-opencloud-security-refresh.timer
sudo systemctl start check-opencloud-security-refresh.service   # a first run now
journalctl -u check-opencloud-security-refresh.service
```

**Ejecútelo con el mismo usuario que la comprobación.** Ambos archivos se
escriben con permisos de lectura solo para su propietario (modo `0600`). La
unidad incluye `User=check-opencloud-security`, así que una comprobación que se
ejecuta como `nagios` o `icinga` no puede leer lo que ha escrito, y eso
desactiva en silencio la comprobación de fin de vida. Consulte
[Usar los archivos actualizados](#using-the-refreshed-files). Ejecute la
comprobación con ese usuario o cambie el usuario de la actualización con un
archivo drop-in:

```bash
sudo systemctl edit check-opencloud-security-refresh.service
# [Service]
# User=nagios
```

`ExecStart=` espera `/usr/bin/check-opencloud-scanner`, que es donde lo
instalan los paquetes `.deb` y `.rpm`. Ajuste la ruta para una instalación con
pipx o pip. Sin systemd, una línea diaria de cron hace el mismo trabajo.
Consulte [Programación](../scheduling.md).

## Réplicas y hosts sin acceso a internet {#mirrors-and-hosts-without-internet-access}

Una actualización predeterminada necesita acceso HTTPS a
`raw.githubusercontent.com` y, para la verificación, a la API de
certificaciones de GitHub y a la raíz de confianza de Sigstore. Hay dos formas
de atender a un host que no tiene nada de eso.

**Actualizar en otro lugar y copiar los archivos.** Ejecute la actualización
verificada en un equipo conectado con el extra `signing` y copie después los
dos archivos a las mismas rutas del host aislado. Los archivos son
autónomos, y la copia conserva la verificación que usted ha hecho.

**Apuntar la actualización a una réplica.** `--schedule-url` acepta una copia
de la página de ciclo de vida de OpenCloud. `--advisory-url` acepta un punto de
acceso de consulta compatible con OSV, cuya respuesta se combina con la base
de datos incluida:

```bash
check-opencloud-scanner refresh-data \
    --output-dir /var/lib/check-opencloud-security \
    --schedule-url https://mirror.example.com/opencloud/lifecycle/ \
    --advisory-url https://mirror.example.com/osv/v1/query
```

Nadie firma una réplica, así que ambas opciones omiten la verificación de
firmas y lo indican en cada ejecución. Las comprobaciones estructurales
anteriores se siguen aplicando. Úselo para una réplica interna que usted
controle, no como forma de eludir un fallo de firma.

## Sus propios avisos de seguridad {#your-own-advisories}

`scanner.vulnerability_db` admite una lista, así que un archivo propio puede
estar junto al actualizado. Se entienden tres formatos sin conversión: el
documento nativo `{"advisories": [...]}`, el formato de la GitHub Advisory API
y los documentos OSV. El [README principal](../../README.md#advisory-database)
describe los formatos y cómo se relacionan las entradas con una versión.
`scanner.vulnerability_feed` consulta un canal en directo en cada análisis en
lugar de leer un archivo.

## Aspectos que conviene conocer {#points-worth-knowing}

- **Una actualización solo cambia datos, nunca código.** Por esta vía no
  llega ninguna comprobación, hallazgo ni regla de calificación nueva; para eso
  sigue haciendo falta actualizar el paquete.
- **Una lista `vulnerabilities` vacía no es un certificado de buena salud.**
  Significa que nada de las bases de datos configuradas coincide con esta
  versión. Las comprobaciones de configuración siguen determinando la mayor
  parte de la nota.
- **Actualice los archivos que realmente lee la comprobación.** El directorio
  de salida predeterminado está en el directorio personal de quien ejecuta la
  actualización, así que una actualización ejecutada como root no sirve de
  nada a una comprobación que se ejecuta como `nagios`.
- **La aplicación web no usa este comando.** Actualiza su calendario y su base
  de datos de avisos en tiempo de ejecución, y solo puede ganar conocimiento.
  Consulte [el servicio público de análisis](../webapp.md).
