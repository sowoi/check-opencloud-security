# Métricas de seguridad de OpenCloud para Prometheus y Grafana

El complemento incluye un exportador nativo de Prometheus. Ejecútelo con
`--prometheus-listen-port 9102` para servir `/metrics`; guarda un análisis en
caché durante `--scrape-interval` segundos (60 por defecto), así que los
scrapes normales no lanzan otro análisis; defínalo como `0` solo si cada scrape
debe analizar. Por defecto escucha en `127.0.0.1`; defina
`--prometheus-listen-addr 0.0.0.0` solo cuando un cortafuegos o una política de
red limite los recolectores remotos, que es también lo que necesita un
contenedor, además de publicar el puerto:

```shell
docker run --rm -p 9102:9102 check-opencloud-security \
  --host opencloud.example.com --prometheus-listen-port 9102 \
  --prometheus-listen-addr 0.0.0.0
```

Para un trabajo por lotes, `--format=prometheus` imprime una carga de
exposición en texto y termina, y `--format=otlp` imprime las mismas métricas
como el cuerpo OTLP/JSON que acepta un recolector de OpenTelemetry. Ningún
modo requiere dependencias adicionales.

Los patrones de textfile collector y Pushgateway descritos más abajo siguen
siendo útiles cuando un análisis programado encaja mejor que un exportador en
ejecución permanente.

Si ya utiliza Icinga2, no necesita nada de esto: los
[datos de rendimiento](../../README.md#performance-data) que imprime el
complemento los recogen directamente los escritores Graphite/InfluxDB de
Icinga2.

<!-- TOC -->
* [Prometheus y Grafana](#prometheus-and-grafana)
  * [Los archivos que hay que copiar](#the-files-to-copy)
  * [Qué publica el exportador](#what-the-exporter-publishes)
  * [Qué se puede representar en gráficos](#what-there-is-to-graph)
  * [node_exporter textfile collector](#node_exporter-textfile-collector)
  * [Pushgateway](#pushgateway)
  * [Recolector de OpenTelemetry](#opentelemetry-collector)
  * [Reglas de alerta](#alerting-rules)
  * [Grafana](#grafana)
<!-- TOC -->


## Los archivos que hay que copiar {#the-files-to-copy}

Son dos, ambos en [`contrib/`](../../contrib/README.md), y ambos leen los
nombres de métricas que publica el exportador nativo:

| Archivo | Qué hacer con él |
|:--|:--|
| [`contrib/prometheus/alerts.yml`](../../contrib/prometheus/alerts.yml) | Cópielo en `/etc/prometheus/rules/` y añádalo a `rule_files:` |
| [`contrib/grafana/dashboard.json`](../../contrib/grafana/dashboard.json) | Grafana - Dashboards - New - Import, y después elija la fuente de datos |

```shell
cp contrib/prometheus/alerts.yml /etc/prometheus/rules/opencloud-security.yml
promtool check rules /etc/prometheus/rules/opencloud-security.yml
```

El selector `Instance` del panel permite que un solo panel cubra varios
destinos. Defina los retrasos de las alertas según el tiempo de respuesta que
necesite y tenga en cuenta con qué frecuencia se actualiza el análisis
subyacente. Varios scrapes pueden contener el mismo análisis en caché.

Las secciones que siguen a la próxima describen la *otra* forma de hacerlo: un
análisis programado cuyo JSON transforma `jq` en nombres de métricas propios.
Esos nombres son más cortos y deliberadamente distintos, y los dos archivos
incluidos no coinciden con ellos.


## Qué publica el exportador {#what-the-exporter-publishes}

| Métrica | Etiquetas | Significado |
|:--|:--|:--|
| `opencloud_security_rating_score` | `host`, `domain`, `product`, `version` | La nota, de `0` a `5`, donde `5` es la mejor |
| `opencloud_security_end_of_life` | `host`, `release_type` | `1` cuando la versión ya no recibe correcciones |
| `opencloud_security_support_days_remaining` | `host`, `release_type` | Días de soporte restantes; **ninguna muestra** cuando el fin de vida aún no tiene fecha |
| `opencloud_security_vulnerabilities_total` | `host`, `severity` | Avisos de seguridad que coinciden con la versión notificada |
| `opencloud_security_hardenings_missing_total` | `host` | Medidas de refuerzo ausentes |
| `opencloud_security_failed_extra_checks_total` | `host` | Comprobaciones adicionales fallidas |
| `opencloud_security_update_available` | `host`, `target_version` | `1` cuando existe una versión más reciente |
| `opencloud_security_certificate_days_remaining` | `host` | Días hasta que caduca el certificado presentado; negativo después, sin muestra por HTTP sin cifrar |
| `opencloud_security_upgrade_path_complete` | `host`, `target_version` | `1` cuando la actualización recomendada corrige todas las vulnerabilidades conocidas; sin muestra si no hay ruta |
| `opencloud_security_waiver_days_remaining` | `host` | Días hasta que termina una exención `--waive-until` y una comprobación fallida vuelve a alertar; sin muestra si ninguna comprobación fallida depende de un plazo |
| `opencloud_security_coverage_inconclusive_total` | `host` | Comprobaciones que el análisis ejecutó sin llegar a una conclusión |
| `opencloud_security_coverage_not_checked_total` | `host` | Comprobaciones que el análisis no ejecutó |
| `opencloud_security_scan_duration_seconds` | `host` | Duración del análisis |
| `opencloud_security_scrape_success` | `host` | `0` cuando ha fallado el análisis del que proceden los números |

Un análisis fallido solo publica las dos últimas. Los hallazgos anteriores al
fallo **no** se vuelven a publicar, así que una instancia cuyo análisis falla
no tiene veredicto en lugar de tener uno obsoleto; por eso
`opencloud_security_scrape_success` es lo primero que muestra el panel.

`opencloud_security_end_of_life` es una familia aparte, y no un número
negativo de días. Una versión rolling o production cuyo fin de
vida aún no se ha anunciado no notifica ningún día, y "desconocido" no debe
leerse como "caduca hoy" en una alerta tan importante.


## Qué se puede representar en gráficos {#what-there-is-to-graph}

Cada ejecución imprime datos de rendimiento después de un `|`:

```
rating=5;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=1.234s;;;0;
```

| Métrica | Significado |
|:-------|:--------|
| `rating` | De `0` a `5`; `5` es A+ y `0` es F; `U` cuando el análisis ha fallado |
| `vulnerabilities` | Vulnerabilidades conocidas de la versión instalada |
| `time` | Segundos que ha durado el análisis |
| `hardenings_missing` | Medidas de refuerzo ausentes, solo con `--check-hardening` |
| `extra_checks_failed` | Comprobaciones adicionales fallidas |
| `update_available` | `1` cuando existe una versión más reciente |
| `support_days_left` | Días de soporte restantes; negativo cuando ya ha vencido |
| `waiver_days_left` | Días hasta que termina una exención temporal; ausente si ninguna oculta una comprobación fallida |
| `coverage_inconclusive` | Comprobaciones que el análisis no pudo decidir |
| `coverage_not_checked` | Comprobaciones que el análisis no ejecutó |

`support_days_left` es la que merece una alerta. Pasa a negativo *antes* de
que nadie se dé cuenta de que la instancia ha dejado de recibir correcciones.

## node_exporter textfile collector {#node_exporter-textfile-collector}

El JSON del escáner es más fácil de procesar que la línea de datos de
rendimiento, así que aquí se usa `check-opencloud-scanner` en lugar del
complemento, y `jq` para darle forma. Escriba en un archivo temporal y
renómbrelo, o node_exporter leerá de vez en cuando un archivo a medio escribir.

```shell
#!/bin/sh
# /usr/local/bin/opencloud-metrics - run from a systemd timer, see scheduling.md
set -eu

HOST="opencloud.example.com"
OUT="/var/lib/node_exporter/textfile_collector/opencloud_security.prom"
TMP="$(mktemp "${OUT}.XXXXXX")"

check-opencloud-scanner scan --compact "$HOST" > /tmp/opencloud-scan.json || true

jq -r --arg host "$HOST" '
  if .error then
    "opencloud_scan_success{host=\"\($host)\"} 0"
  else
    "opencloud_scan_success{host=\"\($host)\"} 1",
    "opencloud_security_rating{host=\"\($host)\"} \(.rating)",
    "opencloud_end_of_life{host=\"\($host)\"} \(if .EOL then 1 else 0 end)",
    "opencloud_vulnerabilities{host=\"\($host)\"} \(.vulnerabilities | length)",
    "opencloud_update_available{host=\"\($host)\"} \(if .updates.available then 1 else 0 end)",
    "opencloud_support_days_left{host=\"\($host)\"} \(.lifecycle.daysRemaining // 0)",
    "opencloud_failed_checks{host=\"\($host)\"} \([.extraChecks[] | select(.passed == false and .ignored == false)] | length)",
    "opencloud_version_info{host=\"\($host)\",version=\"\(.version)\",track=\"\(.releaseType)\"} 1"
  end' /tmp/opencloud-scan.json > "$TMP"

mv "$TMP" "$OUT"
chmod 644 "$OUT"
```

Conserve `opencloud_scan_success`. Sin ella, un análisis fallido parece
una instancia sana, porque las demás métricas
conservan su último valor hasta que se sobrescribe el archivo.

`lifecycle.daysRemaining` es `null` para una versión cuyo fin de vida aún no
tiene fecha, es decir, una versión rolling o production actual, que caduca
cuando se publica su sucesora y no en una fecha concreta. El `// 0` anterior lo
convierte en `0`; si en sus alertas eso se lee como "caduca hoy", elimine la
línea con `select(.lifecycle.daysRemaining != null)`.

## Pushgateway {#pushgateway}

El mismo JSON, otro destino. Use una clave de agrupación por host para que un
análisis que deja de ejecutarse mantenga visible su último valor en lugar de
mezclar hosts.

```shell
check-opencloud-scanner scan --compact opencloud.example.com \
  | jq -r '
      "# TYPE opencloud_security_rating gauge",
      "opencloud_security_rating \(.rating)",
      "# TYPE opencloud_support_days_left gauge",
      "opencloud_support_days_left \(.lifecycle.daysRemaining // 0)"' \
  | curl -sS --data-binary @- \
      http://pushgateway.example.com:9091/metrics/job/opencloud_security/instance/opencloud.example.com
```

Pushgateway nunca olvida una métrica. Borre el grupo cuando retire una
instancia, o seguirá generando alertas sobre un servidor que ya no existe:

```shell
curl -X DELETE http://pushgateway.example.com:9091/metrics/job/opencloud_security/instance/opencloud.example.com
```

## Recolector de OpenTelemetry {#opentelemetry-collector}

`--format otlp` genera las métricas de esta tabla como un único
`ExportMetricsServiceRequest` en OTLP/JSON, que es lo que acepta un recolector
en `/v1/metrics` mediante OTLP/HTTP. El complemento lo imprime y `curl` lo
envía, desde el mismo [temporizador de systemd o tarea de cron](../scheduling.md)
que ya ejecuta el análisis:

```shell
check-opencloud-security --host opencloud.example.com,other.example.com \
  --format otlp \
  | curl -sf -X POST http://collector.example.com:4318/v1/metrics \
      -H 'Content-Type: application/json' --data-binary @-
```

Los nombres de las métricas y el atributo `host` son los del exportador, así
que una consulta escrita para un scrape funciona también con la salida de un
recolector, y las reglas de alerta siguientes no necesitan más traducción que
las convenciones de etiquetas de su backend. Dónde está el recolector, qué
proxy llega a él y qué credencial pide son asuntos del recolector y se quedan
en los argumentos de `curl` en lugar de convertirse en ajustes del escáner.

Un análisis fallido también informa: `opencloud_security_scrape_success`
llega como `0`, con la duración al lado y sin ningún hallazgo, así que una
instancia inaccesible se ve como tal en lugar de conservar los números de la
última ejecución que funcionó.

## Reglas de alerta {#alerting-rules}

Para el exportador nativo, copie
[`contrib/prometheus/alerts.yml`](../../contrib/prometheus/alerts.yml) en lugar
del bloque siguiente: se mantiene con los nombres de métricas reales y se
prueba con ellos.

Las reglas siguientes corresponden a los nombres **generados con `jq`** de las
dos recetas anteriores, que son más cortos y distintos:

```yaml
groups:
  - name: opencloud-security
    rules:
      - alert: OpenCloudEndOfLife
        expr: opencloud_end_of_life == 1
        for: 1h
        labels: {severity: critical}
        annotations:
          summary: "{{ $labels.host }} runs an OpenCloud release with no security fixes"

      - alert: OpenCloudSupportRunningOut
        expr: opencloud_support_days_left < 30 and opencloud_support_days_left > 0
        for: 6h
        labels: {severity: warning}
        annotations:
          summary: "{{ $labels.host }} loses support in {{ $value }} days"

      - alert: OpenCloudRatingDropped
        expr: opencloud_security_rating <= 3
        for: 1h
        labels: {severity: warning}
        annotations:
          summary: "{{ $labels.host }} is rated {{ $value }}/5"

      - alert: OpenCloudScanFailing
        # A scan that no longer runs is the failure mode that hides all others.
        expr: opencloud_scan_success == 0 or absent(opencloud_scan_success)
        for: 2h
        labels: {severity: warning}
        annotations:
          summary: "The OpenCloud security scan has not produced a result"
```

`for:` de Prometheus mide cuánto tiempo sigue siendo verdadera una expresión a
lo largo de las evaluaciones de reglas. No cuenta análisis nuevos. Con datos
de análisis diarios, `for: 5m` espera cinco minutos mientras sigue visible el
mismo fallo en caché; no espera a un segundo análisis diario.

## Grafana {#grafana}

Importe [`contrib/grafana/dashboard.json`](../../contrib/grafana/dashboard.json)
y elija su fuente de datos de Prometheus. Muestra primero el estado del
análisis, con la nota y el ciclo de vida al lado, y después la nota a lo largo
del tiempo, los hallazgos abiertos, los avisos de seguridad por gravedad y una
tabla con lo que se ejecuta en cada lugar.

Si prefiere crear el suyo: la nota es una puntuación de `0` a `5` en la que
más es mejor, así que un panel de tipo stat con umbrales en `3` (amarillo) y
`1` (rojo) reproduce los valores predeterminados del complemento. Asigne a los
valores las letras que usa el resto de la salida: `5 → A+`, `4 → A`, `3 → C`,
`2 → D`, `1 → E`, `0 → F`; una nota sin su letra se lee como una puntuación
sobre cinco.

Ponga la versión en un panel de tabla al lado. La nota indica que algo va mal;
la versión es lo que indica si la solución es actualizar.

---

[Volver al índice de la documentación](../README.md) | [Volver al README principal](../../README.md)
