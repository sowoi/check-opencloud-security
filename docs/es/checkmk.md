# El escáner de seguridad de OpenCloud en Checkmk

Checkmk puede leer directamente la salida de Nagios de este complemento. Puede
ejecutarlo como comprobación activa en el servidor Checkmk o como comprobación
local en un host con agente. Elija el equipo que llegue a la instancia desde la
red que quiere probar.

| | [Comprobación activa](#1-an-active-check-on-the-checkmk-server) | [Comprobación local](#2-a-local-check-on-an-agent-host) |
|:--|:--|:--|
| Se ejecuta en | el servidor Checkmk | un host con el agente de Checkmk |
| Llega a la instancia desde | la red de monitorización | donde esté ese host |
| Requiere el complemento instalado en | el servidor Checkmk | el host con agente |
| Se configura en | la interfaz web | un archivo que ejecuta el agente |
| Formato de salida | `nagios` (el predeterminado) | `--format checkmk` |

Use la **comprobación activa** salvo que la instancia no sea accesible desde el
servidor Checkmk. Se configura en un solo lugar, no necesita nada en ningún
otro equipo y Checkmk interpreta por sí mismo la salida normal del complemento.

Todo lo que sigue usa `opencloud.example.com`. Sustitúyalo por su propia
instancia y analice solo instancias de las que sea responsable.

## 1. Una comprobación activa en el servidor Checkmk {#1-an-active-check-on-the-checkmk-server}

Instale el complemento en el servidor Checkmk, como usuario del sitio:

```shell
pipx install check-opencloud-security
```

[Instalar el complemento](../installation.md) cubre uv, pip y una copia del
repositorio; `check-opencloud-security --version` confirma cuál tiene.

Después, en la interfaz web: **Setup > Services > Other services > Integrate
Nagios plugins**, y cree una regla con

- **Service description**: `OpenCloud security opencloud.example.com`
- **Command line**:
  `check-opencloud-security --host opencloud.example.com --check-hardening`

Asígnela al host en el que quiere que aparezca el servicio. Ese host solo
indica en qué host se ejecuta el *servicio*, no cuál se analiza: el análisis siempre
va a `--host`.

Checkmk toma el estado del código de salida, el resumen de la primera línea de
la salida, el resto de la salida como detalles del servicio y todo lo que
sigue a `|` como métricas. No hay que convertir nada: los
[datos de rendimiento](../../README.md#performance-data) que ya escribe este
complemento (`rating`, `vulnerabilities`, `hardenings_missing`,
`extra_checks_failed`, `update_available`, `support_days_left`,
`cert_days_left`, `upgrade_path_complete`, `waiver_days_left`, `coverage_inconclusive`,
`coverage_not_checked`, `time`) están en el formato de Nagios que Checkmk sabe leer,
umbrales incluidos.

Una advertencia sobre la programación: el intervalo de comprobación
predeterminado es de un minuto, y un análisis realiza unas veinte solicitudes
HTTP y cinco conexiones TCP a la instancia. Defina un intervalo razonable para
el servicio (cada hora es más que suficiente para una nota que cambia cuando
alguien modifica un archivo de configuración) en **Setup > Services > Service
monitoring rules > Normal check interval for service checks**.

## 2. Una comprobación local en un host con agente {#2-a-local-check-on-an-agent-host}

Cuando el servidor Checkmk no llega a la instancia, el análisis tiene que
partir de un lugar que sí llegue. Una comprobación local es un script que
ejecuta el agente; su salida se convierte en un servicio del host del agente.

`--format checkmk` escribe exactamente lo que espera el agente:

```shell
check-opencloud-security --host opencloud.example.com --format checkmk
```

```text
0 "OpenCloud_Security_opencloud.example.com" rating=5|vulnerabilities=0|hardenings_missing=0|extra_checks_failed=0|update_available=0|support_days_left=284|cert_days_left=67|execution_time=4.120 OK: Server is up to date. No known vulnerabilities.
```

Cuatro campos separados por un espacio: el estado, el nombre del servicio
entre comillas, las métricas y el texto de detalle. Con varios hosts en
`--host` se obtienen varias líneas, es decir, varios servicios: uno por
instancia.

### Instalación {#installing-it}

[`contrib/checkmk/opencloud_security`](../../contrib/checkmk/opencloud_security)
es esa llamada envuelta en un script, configurado con las mismas variables de
entorno `COS_` que los [ejemplos de cron y systemd](../scheduling.md) que lo
acompañan, así que no hay que editarlo para apuntarlo a su instancia:

```shell
sudo install -m 0755 contrib/checkmk/opencloud_security \
    /usr/lib/check_mk_agent/local/3600/opencloud_security
```

**Lo importante es el `3600`.** Un script situado directamente en `local/` se
ejecuta cada vez que se llama al agente, es decir, una vez por minuto, lo que
analizaría una instancia de producción cada minuto. El
subdirectorio numérico es el intervalo de caché del agente en segundos: así el
análisis se ejecuta como mucho una vez por hora, y cada llamada intermedia se
responde con la línea guardada en caché. Elija el intervalo que realmente
quiera; `3600` es un buen valor predeterminado para una nota.

Si se instala desde el `.deb` o el `.rpm`, el mismo script está en
`/usr/share/doc/check-opencloud-security/checkmk-local-check.sh`, como ejemplo:
un paquete no tiene por qué escribir en el directorio del agente, así que no lo
instala allí a propósito.

Defina el destino en el script o en un archivo de entorno que lea el agente:

```shell
COS_HOST=opencloud.example.com
# OpenCloud self-signs its certificate unless a proxy terminates TLS for it.
#COS_SCANNER_VERIFY_TLS=false
```

Después, descubra el nuevo servicio en ese host: **Setup > Hosts**, la página
*Services* del host, *Full service scan*.

### Qué significan los estados {#what-the-states-mean}

El estado de la línea es el del complemento, sin cambios: el mismo
`0`/`1`/`2`/`3` que lleva el código de salida, decidido por los mismos
[umbrales de nota](../../README.md#rating-thresholds), exclusiones y reglas de
fin de vida que en cualquier otro lugar. A Checkmk no se le pide que juzgue
nada:

- `0` OK: la nota está por encima de `--warning` y no ha aparecido nada nuevo
- `1` WARN: igual o inferior a `--warning`, o falta alguna medida de refuerzo
- `2` CRIT: igual o inferior a `--critical`, o aplica una vulnerabilidad conocida
- `3` UNKNOWN: el análisis no se pudo completar

Este último es el motivo por el que el script incluido siempre imprime una
línea, incluso cuando falta el complemento o el tiempo de espera del agente lo
ha interrumpido. Una comprobación local que no imprime nada no pasa a UNKNOWN:
*elimina su servicio del host*, lo que parece una comprobación que alguien
ha desactivado, aunque en realidad se ha roto.

### Las métricas {#the-metrics}

Las mismas mediciones que los datos de rendimiento de Nagios, con los mismos
nombres y dos diferencias que exige el formato:

- **Sin umbrales.** Los niveles de una comprobación local solo se evalúan
  cuando el campo de estado es `P`, lo que deja el veredicto en manos de
  Checkmk. Decidir es tarea de este complemento, así que envía el estado al que
  ha llegado y las métricas solo llevan valores.
- **Sin sufijo de unidad.** Cada valor debe poder interpretarse como número,
  así que el `time=4.120s` de Nagios aquí es `execution_time=4.120`.

| Métrica | Qué es |
|:-------|:-----------|
| `rating` | De `0` a `5`, donde `5` es A+. Ausente cuando no se pudo establecer una nota |
| `vulnerabilities` | Avisos de seguridad conocidos que coinciden con la versión detectada |
| `hardenings_missing` | Medidas que faltan en la instancia. **Ausente sin `--check-hardening`**, porque de lo contrario una lista vacía no se distinguiría de una perfecta |
| `extra_checks_failed` | Comprobaciones adicionales fallidas: TLS, rutas expuestas, cookies, cabeceras |
| `update_available` | `1` cuando existe una versión más reciente. Ausente cuando la comprobación de actualizaciones está desactivada |
| `support_days_left` | Días hasta que la línea de versiones deja de recibir correcciones; negativo si ya ha ocurrido |
| `cert_days_left` | Días hasta que caduca el certificado; negativo si ya ha caducado |
| `upgrade_path_complete` | `1` si la actualización recomendada corrige todos los avisos conocidos, `0` si no; ausente sin avisos |
| `waiver_days_left` | Días hasta que termina una exención `--waive-until` y una comprobación fallida vuelve a alertar; ausente si ninguna comprobación fallida depende de un plazo |
| `coverage_inconclusive` | Comprobaciones que el análisis ejecutó sin llegar a una conclusión; ausente sin bloque de cobertura |
| `coverage_not_checked` | Comprobaciones que el análisis no ejecutó; ausente sin bloque de cobertura |
| `execution_time` | Duración del análisis, en segundos |

Una métrica que no se ha medido se omite en lugar de enviarse como cero, para
que un gráfico nunca muestre un cero rotundo para algo que nadie ha examinado.

## Alertas {#alerting-on-it}

Ambas vías generan un servicio normal de Checkmk, así que las notificaciones,
los periodos de mantenimiento y los reconocimientos funcionan como para
cualquier otro. Conviene configurar dos reglas:

- Alertar de inmediato en **CRIT**: una vulnerabilidad conocida o una versión
  sin soporte no son un problema para mañana.
- Representar `support_days_left` en un gráfico y fijarle un nivel. Baja aunque
  nada cambie en la instancia, y cuando pasa a
  negativo la nota cae a F.

`--baseline` y `--warn-on-new`
([Notificar solo lo que ha cambiado](../baseline.md)) funcionan con ambas vías
y merece la pena usarlos en una comprobación que se ejecuta sin supervisión:
así el estado refleja lo *nuevo* en lugar de repetir un hallazgo con el que
alguien ya ha decidido convivir. Una versión sin soporte y una nota que sigue
bajando nunca se perdonan de esta forma, así que no puede silenciar los dos
hallazgos más importantes.

## Véase también {#see-also}

- [Instalar el complemento](../installation.md), con las definiciones de
  objetos de Icinga2/Nagios, si Checkmk no es lo único que utiliza
- [Salida legible por máquina](../output-formats.md): comparación de todos los
  valores de `--format`
- [Programación](../scheduling.md): el temporizador de systemd y el archivo de
  cron de los que proceden las variables de entorno de la comprobación local
- [Prometheus y Grafana](../prometheus.md): la otra vía basada en consultas,
  si prefiere representar esto en gráficos fuera de Checkmk
