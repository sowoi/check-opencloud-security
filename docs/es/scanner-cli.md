# El comando check-opencloud-scanner

El paquete instala dos comandos.

- **`check-opencloud-security`** es el complemento de monitorización. Analiza
  una instancia, *juzga* el resultado con umbrales y termina con `0`-`3` para
  Nagios o Icinga. Sus opciones están en la
  [referencia de opciones de la CLI](../cli-reference.md).
- **`check-opencloud-scanner`** es todo lo demás. Ofrece el documento de
  resultado sin procesar, compara dos de ellos, explica un hallazgo, actualiza
  los datos de referencia y ejecuta el servicio de análisis. Nunca aplica un
  umbral de advertencia ni crítico.

Esta página es la referencia del segundo.

<!-- TOC -->
* [El comando `check-opencloud-scanner`](#the-check-opencloud-scanner-command)
  * [Opciones globales](#global-options)
  * [`scan`: imprimir el documento de resultado](#scan---print-the-result-document)
  * [`diff`: qué ha cambiado entre dos resultados guardados](#diff---what-changed-between-two-saved-results)
  * [`fleet`: un panel a partir de resultados guardados](#fleet---a-dashboard-from-saved-results)
  * [`explain`: qué significa un hallazgo y cómo corregirlo](#explain---what-a-finding-means-and-how-to-fix-it)
  * [`review-waivers`: exenciones que requieren atención](#review-waivers---waivers-that-need-attention)
  * [`refresh-data`: actualizar el calendario de versiones y los avisos de seguridad](#refresh-data---update-the-release-schedule-and-advisories)
  * [`serve`: el servicio de análisis](#serve---the-scan-service)
  * [`configure`: escribir un archivo de configuración](#configure---write-a-configuration-file)
  * [Códigos de salida](#exit-codes)
<!-- TOC -->


## Opciones globales {#global-options}

Van **antes** del subcomando:

```bash
check-opencloud-scanner -c /etc/check-opencloud-security/config.yml -v scan opencloud.example.com
```

| Opción | Qué hace |
|:--|:--|
| `-c, --config` | Archivo de configuración. `.json` se lee como JSON, cualquier otra cosa como YAML |
| `-v, --verbose` | Más registro en stderr: `-v` para información, `-vv` para depuración |

Sin `-c`, se usa el primer archivo que exista, en este orden:

1. `./.env.json`
2. `./check-opencloud-security.yml`
3. `./check-opencloud-security.yaml`
4. `~/.config/check-opencloud-security/.env.json`
5. `/etc/check-opencloud-security/.env.json`
6. `/etc/check-opencloud-security/config.yml`
7. `/etc/check-opencloud-security/config.yaml`

Es la misma búsqueda que hace el complemento. Las variables de entorno `COS_`
se aplican por encima del archivo, y las opciones por encima de ambos.
Consulte [Secretos en la configuración](../configuration.md).

## `scan`: imprimir el documento de resultado {#scan-print-the-result-document}

```bash
check-opencloud-scanner scan opencloud.example.com
check-opencloud-scanner scan --compact opencloud.example.com > result.json
check-opencloud-scanner scan cloud1.example.com cloud2.example.com | jq '.[].rating'
```

Imprime el documento de resultado JSON del escáner: la nota y su explicación,
el ciclo de vida, cada comprobación, TLS y las coincidencias con avisos de
seguridad, todo con claves en camelCase. No imprime ningún veredicto. Un host
imprime un objeto. Varios hosts imprimen un array, en el orden indicado.

| Opción | Qué hace |
|:--|:--|
| `--compact` | Imprime el documento en una línea en lugar de con sangría |
| `--scheme {https,http}` | Cómo llegar a la instancia |
| `--port` | Sustituye el puerto |
| `--timeout` | Segundos permitidos para cada solicitud |
| `--insecure` | No verifica el certificado TLS de la instancia |
| `--ca-file` | Paquete de CA en PEM con el que verificar un certificado interno |
| `--no-extra-checks` | Solo producto, versión y cabeceras |
| `--no-debug-ports` | No sondea los puertos de depuración de OpenCloud |
| `--all-addresses` | Repite las comprobaciones clave en cada dirección a la que se resuelve el nombre |
| `--concurrency` | Sondeos en paralelo dentro de un análisis. Predeterminado `1` |
| `--no-update-check` | No busca la versión de OpenCloud más reciente |

Las exclusiones, el canal de publicación y las fuentes de avisos proceden del
archivo de configuración o del entorno, exactamente igual que en el
complemento.

Una instancia que no se puede analizar no interrumpe la ejecución. Su entrada
pasa a ser `{"host": ..., "error": ...}`, los demás hosts se siguen analizando
y el comando termina con `1`:

```json
{
  "host": "opencloud.example.com",
  "error": "https://opencloud.example.com/status.php is unreachable"
}
```

El documento es lo que consumen las [canalizaciones de CI](../ci.md) y
[Prometheus](../prometheus.md), y lo que compara `diff`, descrito más abajo. El
[README de la biblioteca del escáner](../../opencloud_local_scan/README.md)
describe sus campos.

## `diff`: qué ha cambiado entre dos resultados guardados {#diff-what-changed-between-two-saved-results}

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

Lee dos archivos y no analiza nada. `+` marca un hallazgo que ha aparecido,
`-` uno que se ha resuelto y `~` uno que sigue abierto pero cuya gravedad ha
cambiado. También notifica cualquier cambio en la nota, la
versión y el horizonte de soporte. Responde a "¿ha funcionado la corrección?"
y "¿qué ha cambiado la actualización?" sin mantener un archivo de línea base.
Para una comprobación que recuerda por sí misma su última ejecución, consulte
[Notificar solo lo que ha cambiado](../baseline.md).

| Opción | Qué hace |
|:--|:--|
| `--format text` | Líneas legibles, como arriba. Es el valor predeterminado |
| `--format markdown` | Una tabla Markdown, para una incidencia o un comentario en una pull request |
| `--format side-by-side` | Los dos análisis en dos columnas, un hallazgo por fila |
| `--format json` | La comparación estructurada que lleva el webhook del complemento |
| `--format slack` | JSON de Slack Block Kit |
| `--category NOMBRE` | Mostrar solo un área. Se puede repetir |
| `--all-findings` | Listar todos los hallazgos medidos, incluidos los que no han cambiado |
| `--exit-zero` | Termina siempre con `0` |
| `--allow-different-hosts` | Compara resultados de dos instancias distintas |

**Termina con `1` cuando el segundo resultado es peor**, así que una
canalización puede condicionarse a él. Termina con `0` cuando nada ha
empeorado, también cuando solo se han resuelto hallazgos. `--exit-zero`
desactiva ese control.

Termina con `2`, sin comparar los archivos, en estos casos:

- **los dos archivos describen instancias distintas.** "¿Ha funcionado la
  corrección?" es una pregunta sobre una sola instancia, y dos hosts comparados
  por error dan una respuesta equivocada que nadie nota. Use
  `--allow-different-hosts` si es lo que pretendía.
- **un archivo no es un documento de resultado** de `scan`. Por ejemplo, no
  tiene nota, o es la entrada de error de una instancia que no se pudo
  analizar.

### Severidad, hallazgo por hallazgo {#severity-finding-by-finding}

Cada comparación termina con los hallazgos fallidos contados por severidad:

```text
~ exposed:/config/opencloud.yaml [exposure]: severity high -> critical
Failing by severity: critical 0 -> 1, high 1 -> 1, medium 0 -> 1, low 1 -> 0
```

La línea `~` indica un cambio de gravedad en un hallazgo que sigue abierto.
Al pasar de `high` a `critical`, su identificador sigue en ambas listas de
comprobaciones fallidas. La comparación de conjuntos de
[la línea base](../baseline.md) no detecta un hallazgo nuevo, aunque el límite
de calificación más estricto puede empeorar la nota. La gravedad se lee de
los resultados guardados; las modificaciones posteriores del catálogo no
alteran esos valores históricos.

Un hallazgo exceptuado se cuenta aquí y se muestra como `waived`, porque una excepción es la decisión de no recibir alertas y no la afirmación de que el hallazgo haya desaparecido.

### Lado a lado {#side-by-side}

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

Cada fila indica ambos lados, de modo que quien lee no tiene que reconstruirlos a partir de una lista de cambios. `--all-findings` añade los hallazgos que no se movieron, lo que convierte la vista de «qué ha cambiado» en «qué encontraron los dos análisis».

`not measured` indica que no hay una medición para esa comprobación
([ADR 0064](https://github.com/sowoi/check-opencloud-security/blob/main/adr/0064-a-scan-records-what-it-did-not-measure.md)).
`not listed` indica que el aviso de seguridad no figura en el resultado.
Ninguno de estos estados se interpreta como una comprobación superada.

### Un área cada vez {#one-area-at-a-time}

`--category` acota la comparación y toma un valor de uno de dos espacios de nombres:

- **una categoría de hallazgo** - `cookies`, `authentication`, `sharing`, `exposure`, `embedding`, `lifecycle`, `proxy`, `headers`, `transport`, `advisory` - conserva solo los hallazgos sobre esa área de la instancia.
- **una categoría de cambio** - `instance`, `referenceData`, `scanner`, `policy`, `unknown` - conserva solo la explicación de *por qué* difieren los dos análisis. Véase [Datos de referencia](reference-data.md) para saber por qué una calificación puede moverse sin que la instancia haya cambiado.

```bash
check-opencloud-scanner diff before.json after.json --category transport
check-opencloud-scanner diff before.json after.json --category instance
```

Cada espacio de nombres se filtra solo cuando se le da un valor, así que `--category transport` deja intacta la explicación y `--category instance` deja intactos los hallazgos. La opción se puede repetir, y un valor desconocido se rechaza con el código de salida `2` en lugar de no mostrar nada: una errata que imprimiera una comparación vacía se leería como «no ha cambiado nada».

Una explicación filtrada omite las líneas `[limitation]`, porque estas matizan la comparación entera y no una de sus categorías.

## `fleet`: un panel a partir de resultados guardados {#fleet-a-dashboard-from-saved-results}

```bash
today="/var/lib/opencloud-reports/$(date +%F)"
mkdir -p "$today"
for host in cloud1.example.com cloud2.example.com cloud3.example.com; do
  check-opencloud-scanner scan "$host" > "$today/$host.json"
done
check-opencloud-scanner fleet /var/lib/opencloud-reports
check-opencloud-scanner fleet /var/lib/opencloud-reports --format html > fleet.html
```

Lee documentos de resultado escritos por `scan` (archivos, o directorios en
los que busca `*.json` de forma recursiva) y resume el **informe más reciente
de cada host**. No analiza nada ni almacena nada: la recopilación de los
informes, con una tarea cron, un almacén de artefactos de CI o un directorio
compartido, queda a cargo de lo que usted ya utilice.

| Sección | Qué muestra |
|:--|:--|
| Hosts | Una fila por host: versión, calificación, línea de versiones, hallazgos fallidos y exentos, huecos de cobertura y antigüedad del informe |
| Unsupported releases | Versiones sin soporte, versiones cuyo soporte termina dentro de la ventana y versiones que el calendario no conoce |
| Waiver deadlines | Exenciones temporales tras las cuales una comprobación fallida vuelve a alertar dentro de la ventana, o ya alerta |
| Common findings | Los hallazgos fallidos que comparten más hosts, primero los más graves |
| Missing coverage | Hosts esperados sin informe, hosts cuyo último análisis falló, informes antiguos e informes sin bloque de cobertura |
| Checks not evaluated | Comprobaciones que los análisis omitieron o no pudieron decidir, y en cuántos hosts |

Un informe describe el día en que se escribió, así que dos cosas se
vuelven a evaluar respecto a **hoy**:

- **La versión.** La versión registrada se sitúa de nuevo en el calendario de
  versiones de esta instalación: el incluido, o el archivo que indique la
  configuración, igual que en el complemento. Una línea cuyo soporte terminó
  después del informe aparece con la nota `since the scan`. El fin de vida es
  definitivo: un informe que ya lo indicaba siempre se lista.
- **El plazo de una exención.** Una exención activa en el informe puede haber
  vencido desde entonces. Solo se lista un plazo tras el cual una comprobación
  vuelve a alertar de verdad, con la misma regla que `--waiver-warning` del
  complemento.

Los hallazgos comunes omiten lo que ningún administrador puede cambiar: los
indicadores que OpenCloud fija en el código y las cabeceras que ningún
OpenCloud envía. Un hallazgo exento se cuenta, y la columna `Waived` indica en
cuántos hosts.

| Opción | Qué hace |
|:--|:--|
| `--format text` | Tablas alineadas. Es el valor predeterminado |
| `--format markdown` | Tablas Markdown, para un ticket o una wiki |
| `--format html` | Una página autónoma: sin scripts, sin fuentes, sin descargas, con modo claro y oscuro |
| `--format json` | El resumen estructurado, en camelCase como el documento de resultado |
| `--window DAYS` | Mostrar exenciones y periodos de soporte que terminan en `DAYS` días. Predeterminado `30` |
| `--stale-after DAYS` | Contar un host como no cubierto si su informe más reciente es más antiguo. Predeterminado `7`; `0` lo desactiva |
| `--top N` | Listar los `N` hallazgos más comunes. Predeterminado `10`; `0` los lista todos |
| `--expect HOST` | Un host que debería tener un informe. Repetible, o separado por comas |
| `--inventory FILE` | Hosts esperados desde un archivo, uno por línea; `#` inicia un comentario |

Un host se identifica por nombre y puerto: `https://opencloud.example.com/` y
`opencloud.example.com` son el mismo host, y `opencloud.example.com:9200` es
otro. Indique el puerto en `--expect` cuando la instancia se analice en uno
propio.

Termina con `0` siempre que haya impreso un resumen, por mal que esté la
flota. Termina con `2` cuando no encontró ningún documento de resultado y no
se esperaba ningún host. Un archivo que no es un documento de resultado no es
un error; se nombra en *Files skipped*.

## `explain`: qué significa un hallazgo y cómo corregirlo {#explain-what-a-finding-means-and-how-to-fix-it}

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

Busca los identificadores en el catálogo incluido en el paquete. Es el mismo
texto que muestran la salida `--debug` del complemento, el resultado del
análisis y la aplicación web. No lee ninguna configuración, no necesita red y
no analiza nada, así que funciona en cualquier host donde esté instalado el
paquete.

```bash
check-opencloud-scanner explain cspWithoutUnsafeInline Referrer-Policy   # several at once
check-opencloud-scanner explain exposed:/config/opencloud.yaml          # parameterised ids too
check-opencloud-scanner explain --list                                  # every identifier, one per line
check-opencloud-scanner explain --list --category cookies               # one category
check-opencloud-scanner explain --format json cookieSecure              # for a script
check-opencloud-scanner explain                                         # the whole catalogue
```

| Opción | Qué hace |
|:--|:--|
| `--list` | Imprime solo los identificadores en lugar de las explicaciones |
| `--category` | Solo una categoría: `cookies`, `authentication`, `sharing`, `exposure`, `embedding`, `lifecycle`, `proxy`, `headers` o `transport` |
| `--format {text,json}` | JSON devuelve `id`, `category`, `title`, `meaning`, `remediation`, `reference`, `setting` y `actionable` para cada entrada |

Un identificador que el catálogo no conoce termina con `1` y sugiere los más
parecidos:

```text
ERROR check_opencloud.cli: No catalogue entry for 'cookieSecur'. Did you mean: cookieSecure, cookieSameSite, cookiePrefix? Run `explain --list` for every identifier this build knows.
```

Los identificadores son los que llevan los hallazgos en la línea de alerta, en
`extraChecks[].id` y en `hardenings`, y los que nombra una exclusión. Para un
tratamiento más extenso, página a página, consulte
[Medidas de refuerzo, una por una](../hardening.md) y
[Qué lee el escáner](../scanner-checks.md).

## `review-waivers`: exenciones que requieren atención {#review-waivers-waivers-that-need-attention}

```bash
check-opencloud-scanner -c /etc/check-opencloud-security/config.yml review-waivers
```

Lee las exenciones que usaría el plugin - `scanner.ignore_hardenings` y `scanner.temporary_waivers` del archivo de configuración o sus variables de entorno `COS_` - y enumera las que necesitan revisión, cada una con una propuesta de limpieza. **Nunca modifica la configuración.** Decidir si un fallo sigue siendo aceptable corresponde a quien lo aceptó.

| Tipo | Significado |
|:--|:--|
| Expired | Una exención temporal cuyo plazo ha pasado. Indica si la comprobación vuelve a alertar o si otra exención más amplia la sigue ocultando. |
| Expiring soon | Una exención temporal que vence en menos de `--expiring-within` días: el `--waiver-warning` del plugin para todos los registros a la vez. |
| Unused | No coincide con ninguna comprobación fallida del documento `--result`. Sin `--result`: no coincide con ningún identificador conocido, normalmente una errata. Una exención para un indicador que OpenCloud fija en el código también cuenta, porque nunca alerta. |
| Overlapping | Otra exención activa ya la cubre: un duplicado, un patrón más estrecho bajo otro más amplio o, con `--result`, dos patrones para la misma comprobación fallida. Una exención temporal bajo una permanente se señala porque su plazo no cambia nada. |
| Permanent | Un patrón sin motivo ni plazo, con un registro `--waive-until` para copiar en su lugar. |

```bash
check-opencloud-scanner scan opencloud.example.com > result.json
check-opencloud-scanner review-waivers --result result.json          # tell used from unused
check-opencloud-scanner review-waivers --at 2026-12-01T00:00:00Z     # what will have expired by then
check-opencloud-scanner review-waivers --format json --exit-zero     # for a script
```

| Opción | Qué hace |
|:--|:--|
| `--result FILE` | Un documento de resultado de `scan`, para distinguir las exenciones usadas de las que no; también indica el próximo vencimiento que hará alertar una comprobación |
| `--ignore-hardening`, `--waive-until` | Revisar estos valores en lugar de los configurados, igual que los sustituyen las opciones homónimas del plugin |
| `--expiring-within DAYS` | Ventana de *Expiring soon*. Por defecto: el ajuste `waiver_warning`, o `14` si está desactivado; `0` desactiva la sección |
| `--at TIMESTAMP` | Revisar en otro momento; necesita zona horaria, como un plazo |
| `--format {text,json}` | JSON con `counts` por tipo y una entrada por elemento con `kind`, `pattern`, `reason`, `expiresAt`, `detail`, `suggestion` y `related` |
| `--exit-zero` | Terminar siempre con `0` |

Una exención puede aparecer en varios tipos; un patrón permanente mal escrito, por ejemplo, es *Unused* y *Permanent*.

## `refresh-data`: actualizar el calendario de versiones y los avisos de seguridad {#refresh-data-update-the-release-schedule-and-advisories}

```bash
check-opencloud-scanner refresh-data --output-dir /var/lib/check-opencloud-security
```

Descarga del repositorio de este proyecto el calendario de versiones y la
base de datos de avisos revisados, verifica su firma y los escribe en
`--output-dir`. Imprime las dos rutas y termina con `0`. Ante cualquier fallo
no escribe nada y termina con `1`.

| Opción | Valor predeterminado | Qué hace |
|:--|:--|:--|
| `--output-dir` | `~/.cache/check-opencloud-security` | Dónde se guardan los dos archivos |
| `--timeout` | `30` | Segundos permitidos para cada solicitud |
| `--schedule-url` | *(ninguno)* | Una página de ciclo de vida o réplica, descargada sin verificar |
| `--advisory-url` | *(ninguno)* | Un punto de acceso OSV o réplica, descargado sin verificar |

Los archivos no tienen efecto hasta que la configuración apunta a ellos. La
comprobación de firma necesita el extra `signing`. Hay una trampa fácil de
pasar por alto: un archivo de calendario que la comprobación no puede leer
desactiva la comprobación de fin de vida. Todo esto se explica en
[Mantener al día el calendario de versiones y los avisos de seguridad](../reference-data.md).

## `serve`: el servicio de análisis {#serve-the-scan-service}

```bash
check-opencloud-scanner serve
check-opencloud-scanner serve --listen 0.0.0.0 --token "$(cat /run/secrets/scanner_token)"
```

Ejecuta el escáner como un pequeño servicio HTTP, para que varios
consumidores compartan un resultado en caché por instancia en lugar de que
cada uno la vuelva a analizar.

| Opción | Valor predeterminado | Ajuste |
|:--|:--|:--|
| `--listen` | `127.0.0.1` | `service.listen` / `COS_SERVICE_LISTEN` |
| `--port` | `8811` | `service.port` / `COS_SERVICE_PORT` |
| `--cache-ttl` | `900` segundos | `service.cache_ttl` / `COS_SERVICE_CACHE_TTL` |
| `--token` | *(ninguno)* | `service.token` / `COS_SERVICE_TOKEN` |
| `--concurrency` | `1` | Sondeos en paralelo dentro de un análisis |
| `--insecure` | desactivado | No verifica los certificados de las instancias analizadas |

**Escuchar en cualquier interfaz que no sea loopback sin un token impide el
arranque.** Imprime `UNKNOWN: ...` en stderr y termina con `3`, un código que
un supervisor no reiniciará una y otra vez. Los puntos de acceso se enumeran
en el [README principal](../../README.md#running-the-scanner-as-a-service), y
su ejecución en un contenedor se explica en
[Ejecutar el escáner como servicio](../scan-service.md).

El token debe tener entonces al menos 32 caracteres y no ser el ejemplo de
`secrets/scanner_token.example`: nada limita cuántas veces puede adivinarse,
así que su longitud es su única protección. `openssl rand -hex 32` genera uno.

No es la aplicación web pública. Esa es
[el servicio público de análisis](../webapp.md).

## `configure`: escribir un archivo de configuración {#configure-write-a-configuration-file}

```bash
check-opencloud-scanner configure
check-opencloud-scanner -c /etc/check-opencloud-security/.env.json configure
```

Pide los ajustes de forma interactiva, explica cada uno y los guarda como
JSON, legible solo por el propietario. Ofrece `./.env.json`,
`~/.config/check-opencloud-security/.env.json` y
`/etc/check-opencloud-security/.env.json`, todos ellos lugares que la búsqueda
anterior encuentra automáticamente. `-c` indica otra ruta. Es el mismo
asistente que `check-opencloud-security --configure`.

| Opción | Qué hace |
|:--|:--|
| `--all` | Recorre los ajustes opcionales sin preguntar antes |
| `--force` | Sustituye un archivo existente sin pedir confirmación |
| `--no-test-scan` | No ofrece un análisis de prueba del host antes de guardar |
| `--export-monitoring` | Escribe también la comprobación programada: `icinga`, `systemd`, `both` o `none` |

Después ofrece escribir también la comprobación programada, junto a la
configuración que acaba de guardar:

```text
Also write a monitoring configuration (Icinga service, systemd timer)? [y/N]
```

`--export-monitoring` responde a esa pregunta de antemano, que es lo que
necesita un script de aprovisionamiento. Los archivos llevan los umbrales, la
serie de publicación y todas las demás respuestas recién dadas, de modo que la
comprobación que se ejecuta cada día es la que se configuró y no un ejemplo
ajustado de memoria:

```bash
check-opencloud-scanner configure --export-monitoring both
```

| Archivo | Qué es |
|:--|:--|
| `opencloud-security-<host>.conf` | Un objeto `Service` de Icinga 2. También necesita el `CheckCommand` de [`contrib/icinga2/`](../../contrib/icinga2/check_opencloud_security.conf): el servicio define variables y el comando las convierte en opciones |
| `check-opencloud-security.service` | Una unidad `oneshot`, con las mismas directivas de refuerzo que la de [`contrib/systemd/`](../../contrib/systemd/check-opencloud-security.service) |
| `check-opencloud-security.timer` | `OnCalendar=daily`, con un retardo aleatorio para que muchos hosts detrás de una misma dirección no alcancen el límite de peticiones del canal de publicaciones en el mismo segundo |
| `check-opencloud-security.env` | Las variables `COS_` de la unidad, escritas con lectura solo para el propietario |

Se aplican dos límites. **No se instala nada**: los archivos se escriben
donde fue la configuración y las órdenes que los instalarían se imprimen, así
que lo que llega a `/etc` es algo que ha leído antes. Y **no se escribe
ninguna credencial en ellos**: una URL de webhook o un token de publicación se
queda en el archivo de configuración, legible solo por el propietario,
mientras que un objeto de Icinga y un archivo de unidad no lo son. Ambos
artefactos apuntan a ese archivo en su lugar - `vars.opencloud_config` y
`COS_CONFIG_FILE` - y nombran los ajustes que retuvieron, para que un webhook
configurado nunca falte en silencio.

## Códigos de salida {#exit-codes}

**No** son los códigos de Nagios del complemento. Un `scan` que encuentra una
instancia con nota F sigue terminando con `0`, porque juzgar el resultado es
tarea del complemento.

| Subcomando | `0` | `1` | `2` | `3` |
|:--|:--|:--|:--|:--|
| `scan` | Se han analizado todos los hosts | Al menos un host no se pudo analizar | Configuración no válida | - |
| `diff` | Nada ha empeorado | El resultado posterior es peor | Los archivos no se pueden comparar | - |
| `fleet` | Resumen impreso | - | No se encontró ningún documento de resultado, o el inventario no se puede leer | - |
| `explain` | Impreso | Identificador desconocido o categoría vacía | - | - |
| `review-waivers` | Nada que limpiar | Al menos una exención listada | Exención, marca de tiempo o archivo `--result` no válidos | - |
| `refresh-data` | Se han escrito ambos archivos | No se ha escrito nada; consulte stderr | - | - |
| `serve` | Detenido con normalidad | - | Configuración no válida | Se negó a arrancar, p. ej. escucha amplia sin token |

Los argumentos de línea de comandos no válidos terminan con `2` en todos los
subcomandos, como es habitual en argparse.
