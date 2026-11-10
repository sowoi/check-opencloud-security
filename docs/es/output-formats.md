# Salida legible por máquina del análisis de OpenCloud: JSON, SARIF y JUnit

La salida predeterminada del complemento es una línea de estado de Nagios con
datos de rendimiento. Use `--format` (`COS_FORMAT`) para elegir un formato de
documento o de métricas para scripts, paneles y canalizaciones de CI.

`--format json`, `--format sarif` y `--format junit` imprimen **un único
documento combinado para todos los hosts analizados**, nunca un documento por
host, aunque `--host` indique solo uno. Así, la salida es siempre JSON, SARIF o
XML válido, independientemente de cuántas direcciones se hayan indicado, y
nada posterior tiene que tratar de forma especial una ejecución con un solo
host.

**El código de salida conserva su significado de Nagios con cualquier
formato**: `0` (OK), `1` (WARNING), `2` (CRITICAL), `3` (UNKNOWN). Un paso de CI
se condiciona al código de salida igual que una comprobación de
Icinga; el documento que producen estas opciones es un artefacto adicional
y no lo sustituye. Los dos formatos de métricas, `prometheus` y
`otlp`, son la excepción: informan sobre un análisis en lugar de juzgarlo, así
que un hallazgo viaja como una muestra y el proceso termina con `0`.

<!-- TOC -->
* [Salida legible por máquina: `--format json`, `sarif`, `junit`](#machine-readable-output---format-json-sarif-junit)
  * [`json`](#json)
  * [`sarif`](#sarif)
  * [`junit`](#junit)
  * [`checkmk`](#checkmk)
  * [`otlp`](#otlp)
  * [Elegir un formato](#choosing-a-format)
<!-- TOC -->


## `json` {#json}

Un array JSON con el mismo documento de resultado descrito en
[Notificaciones por webhook](../../README.md#webhook-notifications): un objeto
por host, siempre dentro de un array aunque haya un solo host. Es el formato
adecuado cuando otro componente va a procesar el resultado mediante programa:
un script, el backend de un panel o un segundo sistema de monitorización con
el que este complemento no se comunica de forma nativa.

```shell
check-opencloud-security --host opencloud.example.com --format json
```

## `sarif` {#sarif}

[SARIF](https://sarifweb.azurewebsites.net/) 2.1.0, para un panel de análisis
de código, incluido el de GitHub. Los hallazgos proceden de los mismos hechos
que la salida de texto del complemento (medidas de refuerzo ausentes,
comprobaciones adicionales fallidas, vulnerabilidades y fin de vida): un
resultado SARIF nunca dice nada que no diga la línea de Nagios; solo cambia su
forma para que un panel de análisis lo muestre.

```shell
check-opencloud-security --host opencloud.example.com --format sarif \
  > opencloud-security.sarif
```

Cada hallazgo incluye lo que un panel necesita para actuar: la recomendación y
el enlace a la documentación del catálogo (`help`, `helpUri`), la gravedad y
la categoría (`security-severity`, `problem.severity`, `tags`), el intervalo
de versiones afectado por un aviso (`affectedRanges`, `fixedIn`) y una huella
estable (`partialFingerprints`), de modo que el mismo hallazgo siga siendo una
única alerta entre ejecuciones. `run.properties.hosts` indica la nota, la
versión y el estado de soporte de cada host analizado.

En GitHub Actions, súbalo al análisis de código. `continue-on-error: true` en
el paso de análisis evita que un código de salida distinto de cero haga fallar
el trabajo antes de que se ejecute el paso de subida; al analizar en CI, lo
habitual es querer ver los hallazgos incluso cuando el propio análisis
notifica una mala nota:

```yaml
- name: Scan OpenCloud
  run: |
    check-opencloud-security --host opencloud.example.com --format sarif \
      > opencloud-security.sarif
  continue-on-error: true
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: opencloud-security.sarif
```

## `junit` {#junit}

XML de JUnit con un `<testsuite>` por host analizado y un `<testcase>` por
hallazgo, más un **caso `rating` siempre presente**. Así, un host sin
problemas sigue apareciendo en el informe en lugar de aportar cero casos de
prueba, algo que la mayoría de las herramientas que leen JUnit interpretan como
"no se ejecutó nada" en vez de "no falló nada".

```shell
check-opencloud-security --host opencloud.example.com --format junit \
  > opencloud-security.xml
```

El mismo patrón sirve para cualquier sistema de CI que convierta un archivo
JUnit en un resumen de ejecución: basta con que el paso dirija su lector de
JUnit al archivo que produce este comando.

## `checkmk` {#checkmk}

Una línea de [comprobación local de Checkmk](../checkmk.md) por host
analizado, para que la lea el agente: el estado, el nombre del servicio entre
comillas, las métricas y el texto de detalle.

```shell
check-opencloud-security --host opencloud.example.com --format checkmk
```

Es el único formato que *no* es un documento combinado, porque el protocolo
que escribe usa una línea por servicio: varios hosts son varios servicios.
Además, solo hace falta para la vía del agente: un servidor Checkmk que ejecuta
el complemento como comprobación activa lee de forma nativa la salida
predeterminada `nagios`. [Checkmk](../checkmk.md) describe ambas vías y la
tabla de métricas.

## `otlp` {#otlp}

Las métricas que publica la exposición de Prometheus, en formato OTLP/JSON: un
`ExportMetricsServiceRequest` con todos los hosts analizados, que es el cuerpo
que un recolector de OpenTelemetry acepta en `POST /v1/metrics` mediante
OTLP/HTTP.

```shell
check-opencloud-security --host opencloud.example.com --format otlp \
  | curl -sf -X POST http://collector.example.com:4318/v1/metrics \
      -H 'Content-Type: application/json' --data-binary @-
```

El complemento imprime el documento y nunca contacta él mismo con el
recolector: adónde van las métricas, a través de qué proxy y con qué
credencial es configuración del recolector, no de un análisis. Enviar la
salida a `curl` desde el mismo temporizador que ya ejecuta la comprobación
mantiene esa separación y evita que el complemento arrastre una pila de
instrumentación que un host de monitorización nunca ha pedido.

Varios hosts se convierten en varios puntos de datos de las mismas métricas,
distinguidos por su atributo `host`, igual que se convierten en muestras
repetidas en un scrape. Todas las métricas son de tipo gauge (la lectura actual
de algo), y los nombres, atributos y valores son los de la exposición, así que
una misma consulta de panel funciona con cualquiera de las dos canalizaciones.
[Prometheus y Grafana](../prometheus.md#what-the-exporter-publishes) contiene
la tabla de métricas que comparten ambos formatos.

Al igual que `--format prometheus`, **este formato termina con `0` incluso
para una instancia que habría generado una alerta**, y notifica un análisis
fallido como `opencloud_security_scrape_success 0` en lugar de con un código
de salida. Una canalización de métricas no tiene otra forma de distinguir una
instancia inaccesible de un análisis que ha dejado de ejecutarse; cuando lo que
importa es el código de salida, use `nagios`, `json`, `sarif` o `junit`.

## Elegir un formato {#choosing-a-format}

| Formato    | Úselo cuando...                                                          |
|:-----------|:-------------------------------------------------------------------------|
| `nagios`   | Predeterminado. Un sistema de monitorización lee el código de salida y la salida de una línea |
| `prometheus` | Un destino de scrape o un recolector textfile quiere las métricas directamente; consulte [Prometheus y Grafana](../prometheus.md) |
| `otlp`     | Un recolector de OpenTelemetry debe recibir esas mismas métricas en `/v1/metrics` |
| `json`     | Otro componente procesa el resultado mediante programa                   |
| `sarif`    | Un panel de análisis de código (GitHub, GitLab) debe listar los hallazgos |
| `junit`    | Un sistema de CI muestra resultados de pruebas y debe mostrar los hallazgos de la misma forma |
| `checkmk`  | Un agente de Checkmk ejecuta el complemento como comprobación local; consulte [Checkmk](../checkmk.md) |

Consulte [Ejecutar la comprobación desde CI](../ci.md) para un recorrido más
completo por GitHub Actions y GitLab CI, que incluye cómo condicionar una
canalización a un campo del resultado JSON y no solo al código de salida.
