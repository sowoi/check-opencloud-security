# Analizar un conjunto de instancias con el escáner de seguridad de OpenCloud

Varias instancias suelen necesitar puertos, canales de publicación y
exclusiones distintos. Esta guía muestra cuándo usar un comando compartido,
cómo mantener un archivo de configuración por instancia y cómo programar las
comprobaciones resultantes.

<!-- TOC -->
* [Comprobar un conjunto de instancias](#checking-a-fleet-of-instances)
  * [Un comando, varios hosts](#one-command-several-hosts)
  * [Un archivo de configuración por instancia](#one-configuration-file-per-instance)
  * [Un bucle sobre los archivos](#a-loop-over-the-files)
  * [Desde dónde deben ejecutarse las comprobaciones](#where-the-checks-should-run-from)
  * [Revisar las exclusiones periódicamente](#keeping-the-waivers-honest)
  * [Alertar solo sobre lo que ha cambiado](#only-alerting-on-what-changed)
  * [Un panel para toda la flota](#one-dashboard-for-the-whole-fleet)
  * [Programarlo todo](#scheduling-the-whole-thing)
<!-- TOC -->


## Un comando, varios hosts {#one-command-several-hosts}

`--host` admite una lista separada por comas. El complemento analiza los hosts
uno tras otro, imprime un resumen de una línea seguido de un bloque por host y
termina con el peor estado encontrado; consulte
[Comprobar varios hosts](../../README.md#checking-multiple-hosts).

```shell
check-opencloud-security --check-hardening \
  --host opencloud1.example.com,opencloud2.example.com:9200,[2001:db8::1]
```

Es la respuesta adecuada cuando las instancias son parecidas. Todo lo que va
después de `--host` se aplica a todas, así que en cuanto una instancia necesita
`--insecure` o una exclusión que las demás no necesitan, esta forma se queda
corta.

Agrupar también hace perder el historial por host que conservaría su sistema de
monitorización. Si prefiere un servicio en rojo por cada instancia con
problemas en lugar de un único servicio en rojo para el grupo, use una
comprobación por host.

Si añade aquí `--webhook-digest`, el webhook se envía como máximo una vez para
toda la lista de `--host`, en lugar de una vez por cada host que cumpla
`--webhook-on`. Es útil cuando quien recibe el webhook es una persona que
prefiere un mensaje sobre tres instancias con problemas a tres avisos por
separado. Solo combina lo que ocurre *dentro de este único proceso*: al ser una
opción de un único `ScanContext`, no tiene efecto en los patrones "un archivo
de configuración por instancia" y "un bucle sobre los archivos" descritos más
abajo, en los que cada instancia se ejecuta como un proceso independiente sin
nada que combinar; cada uno sigue enviando su propio webhook por instancia,
exactamente igual que sin la opción.

## Un archivo de configuración por instancia {#one-configuration-file-per-instance}

Cada instancia tiene un archivo, y ese archivo contiene todo lo que la
diferencia. No se repite nada en la línea de comandos, así que un cambio se
hace en un único lugar.

```yaml
# /etc/check-opencloud-security/prod-eu.yml
host: opencloud-eu.example.com
check_hardening: true
update_warning: true

scanner:
  target_port: 9200
  release_track: production
  ignore_hardenings:
    # The reverse proxy owns this header; the instance cannot set it.
    - hstsPreload

releases:
  mode: auto
  token: secret://releases_token
```

```shell
check-opencloud-security --config /etc/check-opencloud-security/prod-eu.yml
```

La prioridad es **línea de comandos > variable de entorno > archivo de
configuración > valor predeterminado**, así que un archivo por instancia se
puede seguir sobrescribiendo en una ejecución concreta sin editarlo. La
sintaxis completa, incluido `secret://`, está en
[Archivo de configuración y secretos](../../README.md#configuration-file-and-secrets).

Escriba el primer archivo con `check-opencloud-security --configure --config /etc/check-opencloud-security/prod-eu.yml`
y cópielo para los demás.

## Un bucle sobre los archivos {#a-loop-over-the-files}

Con un archivo por instancia, analizar el conjunto es un bucle `for`, y lo que
se notifica son los códigos de salida:

```shell
#!/bin/sh
# Scan every configured instance; exit with the worst state seen.
set -u

worst=0
rank() { case "$1" in 2) echo 3 ;; 1) echo 2 ;; 3) echo 1 ;; *) echo 0 ;; esac; }

for config in /etc/check-opencloud-security/*.yml; do
  check-opencloud-security --config "$config" || state=$?
  state="${state:-0}"
  [ "$(rank "$state")" -gt "$(rank "$worst")" ] && worst="$state"
  unset state
done

exit "$worst"
```

`rank` existe porque los códigos de salida de Nagios no están ordenados por
gravedad: `CRITICAL` (2) está por encima de `WARNING` (1), que está por encima
de `UNKNOWN` (3), que está por encima de `OK` (0). Ordenarlos numéricamente
haría que un host inaccesible pareciera peor que un host sin soporte.

## Desde dónde deben ejecutarse las comprobaciones {#where-the-checks-should-run-from}

El complemento analiza a través de la red desde donde se ejecute, así que el
lugar de ejecución determina lo que puede ver:

- Una instancia detrás de un cortafuegos necesita una comprobación que se
  ejecute dentro, no una en el servidor de monitorización con un agujero
  abierto en el cortafuegos.
- Si se exige HTTPS y si el certificado es de confianza depende del camino que
  se recorre hasta la instancia. Analizar a través de un balanceador de carga
  que termina TLS mide el balanceador.
- Los sondeos de puertos de depuración solo tienen sentido desde una red que
  *no debería* llegar a ellos. Desde el propio host de la instancia
  encontrarán puertos a los que nadie de fuera podría llegar.

Si varios consumidores de monitorización necesitan el mismo resultado, ejecute
el [servicio de análisis](../../README.md#running-the-scanner-as-a-service)
cerca de las instancias y deje que compartan su caché. El complemento nunca se
comunica con él (siempre analiza dentro de su propio proceso), así que el
servicio está pensado para paneles y scripts.

## Revisar las exclusiones periódicamente {#keeping-the-waivers-honest}

Revise periódicamente las entradas `ignore_hardenings` para que los hallazgos
aceptados no oculten problemas nuevos. Las exclusiones tienen dos límites:

- Una exclusión solo suprime la alerta. El hallazgo permanece en el documento
  de resultado con `"ignored": true`, y `--debug` lo sigue explicando;
  consulte
  [Aceptar un hallazgo que no se va a corregir](../hardening.md#accepting-a-finding-you-are-not-going-to-fix).
- Solo se puede excluir una comprobación que *haya fallado realmente*, así que
  una exclusión no puede cubrir en silencio una medida que más tarde retroceda
  y dé lugar a otro hallazgo.

Revíselas analizando sin exclusiones y comparando:

```shell
for config in /etc/check-opencloud-security/*.yml; do
  echo "== $config"
  COS_SCANNER_IGNORE_HARDENINGS="" check-opencloud-security --config "$config" --debug \
    | grep -E 'ignored|waived|FAIL'
done
```

Hay un identificador que nunca aparecerá en esa lista, por muchas instancias
que ejecute: `publicLinkExpirationEnforced` está fijado en el código de
OpenCloud y falla en todas las instancias existentes, así que se registra pero
se excluye deliberadamente de la alerta, de la métrica `hardenings_missing` y
del webhook. Excluirlo no excluiría nada; consulte
[Medidas que no son ajustes](../hardening.md#measures-that-are-not-settings).

## Alertar solo sobre lo que ha cambiado {#only-alerting-on-what-changed}

Veinte instancias que producen los mismos veinte hallazgos cada cinco minutos
son la forma en que un conjunto de instancias enseña a sus operadores a dejar
de leer la salida. Dé a cada host una línea base y la comprobación solo
notificará regresiones:

```shell
for config in /etc/check-opencloud-security/*.yml; do
  check-opencloud-security --config "$config" \
      --baseline /var/lib/check_opencloud/baseline.json \
      --warn-on-new
done
```

Un solo archivo basta para todo el conjunto: guarda una entrada por host,
identificada por el host tal como se indicó en la línea de comandos. Una lista
de `--host` separada por comas funciona igual.

Hay dos cosas que conviene hacer bien:

- El usuario de monitorización debe ser el propietario del directorio. El
  archivo se escribe de forma atómica con permisos solo para el propietario, y
  una línea base que no se puede escribir se notifica con una línea de salida
  y nada más: nunca cambia el veredicto.
- Escriba el host igual en todas partes. `opencloud.example.com` y
  `https://opencloud.example.com/` se normalizan al mismo host, pero
  `10.0.0.5` no coincide con el nombre que se resuelve a esa dirección, y la
  comprobación lo trataría como un host que nunca ha visto.

Una versión que ha superado su fin de vida sigue generando alertas en cada
ejecución, sea cual sea la línea base, porque no recibe
correcciones de seguridad y el riesgo crece mientras sigue en marcha.
Consulte
[Notificar solo lo que ha cambiado](../../README.md#reporting-only-what-changed).

Añada `--self-update-check` en un solo host del conjunto (no en todos) para
recibir un aviso cuando se publique una versión más reciente del complemento.
Se guarda en caché durante un día y nunca cambia el código de salida.

## Un panel para toda la flota {#one-dashboard-for-the-whole-fleet}

La monitorización responde, host a host, si una instancia está fallando
ahora. Una revisión de la flota pregunta otra cosa: qué instancias ejecutan
una versión que ya no recibe parches, qué exenciones vencen este mes, qué
hallazgo falla en todas partes y qué instancia no ha revisado nadie
últimamente. Conserve los documentos de resultado que escribe `scan`, y
`fleet` responde a las cuatro preguntas solo a partir de los archivos:

```shell
dir="/var/lib/opencloud-reports/$(date +%F)"
mkdir -p "$dir"
for host in opencloud1.example.com opencloud2.example.com; do
  check-opencloud-scanner scan "$host" > "$dir/$host.json"
done
check-opencloud-scanner fleet /var/lib/opencloud-reports \
    --inventory /etc/check-opencloud-security/hosts.txt --format html > fleet.html
```

No analiza nada ni almacena nada; cuenta el informe más reciente de cada
host, y la versión y los plazos de las exenciones se evalúan respecto a hoy y
no al día del informe. Con un inventario, un host sin ningún informe aparece
como ausente. Consulte
[`fleet`: un panel a partir de resultados guardados](scanner-cli.md#fleet-a-dashboard-from-saved-results).

## Programarlo todo {#scheduling-the-whole-thing}

- Con Icinga2: un `Service` por host, aplicado desde un grupo de hosts;
  consulte [Icinga Director](../icinga-director.md) o
  [Despliegue automatizado con Ansible](../ansible.md).
- Sin Icinga2: un temporizador de systemd o una entrada de cron que ejecute el
  bucle anterior; consulte [Programación](../scheduling.md).
- En un clúster: un `CronJob`; consulte [Kubernetes](../kubernetes.md).

Escalone las programaciones. Veinte instancias analizadas a `0 6 * * *`
suponen veinte análisis simultáneos desde una misma dirección, y la
comprobación de actualizaciones chocará por el camino con el límite de
frecuencia anónimo de GitHub.

---

[Volver al índice de la documentación](../README.md) | [Volver al README principal](../../README.md)
