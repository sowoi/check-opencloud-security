# Recetas de webhooks del escáner de seguridad de OpenCloud

El [webhook](../../README.md#webhook-notifications) envía por defecto el
documento JSON propio del complemento. Es deliberado: contiene el veredicto
completo, no una frase ya redactada. `--webhook-format` puede generarlo
directamente con el formato de Slack o Discord (consulte
[más abajo](#slack-mattermost-discord)), o como notificación push para
[ntfy o Gotify](#ntfy-and-gotify); cualquier otro receptor sigue necesitando el
documento genérico y unas pocas líneas de traducción entre medias.

Hay dos reglas que se aplican a todas las recetas de esta página:

- **Un webhook que falla nunca cambia el resultado de la comprobación.** El
  complemento añade `Webhook delivery failed` y sigue terminando con el estado
  que midió, así que un canal de notificación roto no puede ocultar ni simular
  una instancia vulnerable.
- **Nunca ponga la URL en la línea de comandos.** Normalmente *es* la
  credencial. Use `COS_WEBHOOK_URL`, o `secret://` en el archivo de
  configuración; consulte
  [Archivo de configuración y secretos](../../README.md#configuration-file-and-secrets).

<!-- TOC -->
* [Recetas de webhooks](#webhook-recipes)
  * [La carga útil, en resumen](#the-payload-in-short)
  * [La carga útil completa](#the-full-payload)
  * [Un receptor genérico](#a-generic-receiver)
  * [Verificar la firma](#verifying-the-signature)
  * [Uptime Kuma](#uptime-kuma)
  * [Slack, Mattermost, Discord](#slack-mattermost-discord)
  * [ntfy](#ntfy)
  * [Alertmanager](#alertmanager)
  * [Probar un receptor sin una instancia](#testing-a-receiver-without-an-instance)
<!-- TOC -->


## La carga útil, en resumen {#the-payload-in-short}

Los campos que interesan a la mayoría de los receptores, tomados de
[la carga útil completa](#the-full-payload) que aparece más abajo:

| Campo | Para qué sirve |
|:------|:-----------|
| `status`, `exit_code` | `OK` / `WARNING` / `CRITICAL` / `UNKNOWN` y `0`-`3` |
| `message` | El motivo en una línea, ya redactado para una persona |
| `rating`, `rating_label` | La puntuación de `0` a `5` y su etiqueta de `A+` a `F` |
| `host`, `product_version` | Qué instancia y qué versión |
| `eol` | Si esa versión sigue recibiendo correcciones de seguridad |
| `update.availableVersion` | A qué versión actualizar |
| `failed_extra_checks`, `missing_hardenings` | Los hallazgos en sí |

Un análisis que ha fallado por completo solo lleva `plugin`,
`plugin_version`, `timestamp`, `host`, `status`, `exit_code` y `message`.
Cualquier receptor que use `rating` debe tolerar su ausencia.

## La carga útil completa {#the-full-payload}

Todo lo que contiene el documento `generic`, de una ejecución que encontró una
versión sin soporte:

```json
{
  "plugin": "check-opencloud-security",
  "plugin_version": "1.0.0",
  "timestamp": "2026-08-07T10:12:33.123456+00:00",
  "host": "opencloud.example.com",
  "status": "CRITICAL",
  "exit_code": 2,
  "message": "CRITICAL: The 7.3 rolling release line is end-of-life and has no security fixes. Upgrade to 7.4.0.",
  "rating": 0,
  "rating_label": "F",
  "product": "OpenCloud",
  "product_version": "7.3.0",
  "domain": "opencloud.example.com",
  "scanned_at": "2026-08-12 15:24:13.978540",
  "eol": true,
  "release_type": "rolling",
  "lifecycle": {
    "line": "7.3",
    "releaseType": "rolling",
    "state": "endOfLife",
    "released": "2026-07-14",
    "endOfLife": "2026-08-03",
    "daysRemaining": -9,
    "latestOnLine": null,
    "upgradeTo": "7.4.0",
    "reason": "rolling release, unsupported since 2026-08-03",
    "scheduleStale": false,
    "scheduleUpdated": "2026-08-12",
    "scheduleSource": "https://docs.opencloud.eu/docs/admin/resources/lifecycle/",
    "scheduleNote": null
  },
  "vulnerability_count": 0,
  "vulnerabilities": [],
  "missing_hardenings": [],
  "failed_extra_checks": ["exposed:/opencloud.yaml"],
  "scan_backend": "local",
  "scan_uuid": "6a1d1bd0-...",
  "update": {"available": true, "version": "7.3.0", "availableVersion": "7.4.0", "releasedAt": "2026-08-03", "source": "feed", "error": null, "track": "rolling", "newestRelease": null},
  "duration_seconds": 1.234
}
```

`scan_backend` siempre es `"local"`: registra cómo se obtuvo el resultado,
para que un receptor que también procesa cargas de escáneres con backend
remoto pueda distinguirlas sin tratar de forma especial el nombre del
complemento.

Las notificaciones enviadas por un análisis fallido solo llevan los campos
comunes (`plugin`, `plugin_version`, `timestamp`, `host`, `status`,
`exit_code`, `message`).

## Un receptor genérico {#a-generic-receiver}

Todo lo que acepte JSON arbitrario (una canalización de registros, un
recolector de webhooks, un flujo de n8n o Node-RED) recibe la carga útil sin
cambios:

```shell
export COS_WEBHOOK_URL='https://collector.example.com/hooks/opencloud'
export COS_WEBHOOK_HEADERS='Authorization: Bearer abc123; X-Env: prod'
check-opencloud-security --host opencloud.example.com --webhook-on warning
```

`--webhook-on` decide cuánto recibe. Cada nivel incluye los más graves:
`critical`, `warning`, `unknown`, `always`.

## Verificar la firma {#verifying-the-signature}

Una URL de webhook suele ser lo único que separa un punto de acceso de
cualquiera que la adivine. `--webhook-secret` (o `COS_WEBHOOK_SECRET`) añade
una firma con secreto compartido para que el receptor pueda distinguir una
notificación real de una inventada:

```shell
export COS_WEBHOOK_SECRET='a-long-random-string'
check-opencloud-security --host opencloud.example.com --webhook-on warning
```

Cada POST lleva entonces

```
X-COS-Signature: sha256=<hex>
```

donde `<hex>` es el **HMAC-SHA256 del cuerpo de la solicitud sin procesar**,
con el secreto como clave. El complemento serializa el cuerpo una sola vez y
envía exactamente esos bytes, así que el receptor verifica los bytes que ha
recibido: no debe volver a codificar antes el documento procesado, porque
cualquier diferencia en el orden de las claves o en los espacios cambia el
hash.

```python
import hashlib
import hmac

def verify(raw_body: bytes, header: str, secret: str) -> bool:
    """raw_body must be the untouched request body, not a re-serialised dict."""
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header or "")
```

Use `hmac.compare_digest` en lugar de `==`; comparar resúmenes hexadecimales
con una comparación que se detiene en la primera diferencia revela qué parte
de un intento era correcta.

En un receptor Flask o FastAPI, use el cuerpo sin procesar en lugar del JSON
procesado: `await request.body()` en FastAPI, `request.get_data()` en Flask.
Los frameworks que solo entregan un objeto ya procesado no pueden verificar
esta firma. Lea el cuerpo sin procesar antes de convertirlo en un objeto.

Tres notas:

- **La firma cubre lo que se haya enviado**, incluidos los documentos de chat
  y push que producen `--webhook-format slack`, `discord`, `ntfy` y `gotify`.
  Esos servicios ignoran la cabecera; está ahí para los receptores que la
  comprueban.
- **Si no hay secreto definido, no se envía cabecera de firma.** Un receptor
  que la exija debe rechazar la solicitud en lugar de dar por válida una
  cabecera ausente.
- **El secreto es una credencial.** Manténgalo fuera de la línea de comandos,
  igual que la URL; consulte
  [Archivo de configuración y secretos](../../README.md#configuration-file-and-secrets).

## Uptime Kuma {#uptime-kuma}
Uptime Kuma no tiene sistema de complementos, pero su monitor **Push** es una
URL que espera recibir llamadas periódicas, y el webhook las
hace. La comprobación se convierte en un monitor en tres pasos.

**1. Cree el monitor.** En Uptime Kuma elija *Add New Monitor*, tipo de
monitor **Push**, y póngale el nombre de la instancia. Uptime Kuma muestra una
*Push URL* con la forma `https://kuma.example.com/api/push/<token>`. Defina un
*Heartbeat Interval* algo mayor que el intervalo con el que ejecutará la
comprobación (300 segundos para una comprobación cada cuatro minutos), para
que un único análisis lento no cuente ya como caída.

**2. Apunte el webhook a ella** y defina `--webhook-on always` para que un
resultado sano también informe. Sin eso, Uptime Kuma solo recibiría noticias
de la comprobación cuando algo va mal y trataría el silencio como caída:

```shell
check-opencloud-security --host opencloud.example.com \
  --webhook-url 'https://kuma.example.com/api/push/<token>' \
  --webhook-on always
```

O en el archivo de configuración, para que el token no aparezca en la lista de
procesos:

```yaml
host: opencloud.example.com
webhook:
  url: secret://kuma_push_url
  on: always
```

**3. Ejecútelo de forma programada**; consulte
[temporizador de systemd](../scheduling.md#systemd-timer) o
[cron](../scheduling.md#cron). Uptime Kuma se pone en rojo cuando no llega
ningún push dentro del intervalo de latido, así que también se detecta un
complemento que no puede ejecutarse.

Un monitor Push registra el estado que se le comunica mediante su propio
protocolo. No confíe en que interprete el JSON genérico del complemento como
un veredicto sobre OpenCloud. Para notificar el estado medido, traduzca el
resultado del complemento a los parámetros `status` y `msg` de la Push URL.
Estos campos de la carga útil son útiles al escribir un adaptador:

| Campo de la carga útil    | Qué le indica en Uptime Kuma                             |
|:--------------------------|:---------------------------------------------------------|
| `status` / `exit_code`    | `OK`, `WARNING`, `CRITICAL` o `UNKNOWN`                  |
| `message`                 | El motivo en una línea, listo para pegar en una alerta   |
| `rating`, `rating_label`  | La puntuación de `0` a `5` y su etiqueta de `A` a `F`    |
| `product_version`, `eol`  | Qué versión de OpenCloud y si sigue recibiendo correcciones |
| `update.availableVersion` | A qué versión actualizar                                 |
| `duration_seconds`        | Cuánto duró el análisis                                  |

Para marcar como caído cualquier resultado del complemento distinto de OK, use
un envoltorio que envíe el estado Push adecuado:

```shell
check-opencloud-security --host opencloud.example.com \
  && curl -fsS 'https://kuma.example.com/api/push/<token>?status=up' \
  || curl -fsS 'https://kuma.example.com/api/push/<token>?status=down&msg=opencloud'
```

Use el latido directo para detectar ejecuciones programadas que no se han
producido. Use el envoltorio o un adaptador que entienda el resultado cuando
el monitor deba reflejar también el estado de la comprobación de seguridad.

## Slack, Mattermost, Discord {#slack-mattermost-discord}

Esperan su propio JSON. Para el caso habitual, `--webhook-format slack` o
`--webhook-format discord` lo envían directamente, sin necesidad de adaptador:

```shell
check-opencloud-security --host opencloud.example.com \
  --webhook-url https://hooks.slack.com/services/... \
  --webhook-format slack
```

Mattermost también acepta el formato `slack`, igual que el conector de webhooks
salientes del puente de Matrix más común,
[matrix-hookshot](https://matrix-org.github.io/matrix-hookshot/); no hay un
formato `matrix` aparte porque ninguno de ellos tiene un contrato de webhook
propio que merezca la pena usar en su lugar. Discord también acepta el formato
`slack` en `<webhook-url>/slack`, si se prefiere un adjunto simple a un embed.

El adaptador siguiente es para todo lo que no cubren los formatos
incorporados: un esquema de colores propio, campos adicionales o un receptor
que tiene *casi* la forma de Slack o Discord, pero no del todo:

```python
#!/usr/bin/env python3
"""Forward a check-opencloud-security notification to a Slack-style webhook."""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SLACK_URL = os.environ["SLACK_WEBHOOK_URL"]
COLOURS = {"OK": "#2eb886", "WARNING": "#daa038", "CRITICAL": "#a30200", "UNKNOWN": "#767676"}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        text = f"*{payload['host']}* - {payload['status']}\n{payload['message']}"
        if payload.get("rating_label"):
            text += f"\nRating {payload['rating_label']}, OpenCloud {payload.get('product_version', '?')}"

        body = json.dumps({
            "attachments": [{
                "color": COLOURS.get(payload["status"], "#767676"),
                "text": text,
            }]
        }).encode()
        request = urllib.request.Request(
            SLACK_URL, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=10):
            pass

        self.send_response(204)
        self.end_headers()


HTTPServer(("127.0.0.1", 8099), Handler).serve_forever()
```

Vincúlelo a localhost y ejecútelo junto a la comprobación. Un adaptador
accesible desde otros equipos es un relé abierto hacia su sistema de chat.

Discord acepta una carga útil compatible en `<webhook-url>/slack`. Mattermost
acepta directamente el formato de Slack.

## ntfy y Gotify {#ntfy-and-gotify}

Ambos están incorporados y ninguno necesita adaptador:

```shell
check-opencloud-security --host opencloud.example.com \
  --webhook-url https://ntfy.example.com/opencloud \
  --webhook-format ntfy

check-opencloud-security --host opencloud.example.com \
  --webhook-url https://gotify.example.com/message \
  --webhook-header 'X-Gotify-Key: ...' \
  --webhook-format gotify
```

**Para ntfy, indique la URL del tema.** ntfy solo lee una publicación JSON en
la raíz de su servidor y toma el tema del documento, no de la ruta, así que el
complemento lee el tema de la URL configurada y envía a la raíz de ese mismo
servidor. El esquema, el host y el puerto no se modifican, de modo que la
dirección que comprueba la protección contra SSRF es la dirección a la que se
envía. Una URL que no indica ningún tema se rechaza al iniciar la comprobación,
en lugar de devolver un 400 en cada notificación mientras dure la
configuración. Es el único formato cuya URL se reescribe, y solo en su ruta;
consulte
[ADR 0040](../../adr/0040-a-push-format-may-rewrite-the-path-never-the-host.md).

**Para Gotify, mantenga el token fuera de la URL si puede.** `?token=...`
funciona y se oculta en los registros del propio complemento, pero
`--webhook-header 'X-Gotify-Key: ...'` lo mantiene totalmente fuera de la URL,
y fuera de cualquier registro de proxy entre ambos hosts. En cualquier caso,
`--webhook-secret` sigue firmando el cuerpo, así que un receptor que verifique
`X-COS-Signature` puede hacerlo aquí igual que en cualquier otro lugar.

Las prioridades siguen el estado: CRITICAL llega a ntfy como `urgent` y a
Gotify como 8, WARNING como `default` y 5, UNKNOWN como `high` y 5, y un OK
(que solo envía `--webhook-on always`) con el valor más discreto de cada
servicio, para que un interruptor de hombre muerto no moleste a nadie cada
noche para decir que no pasa nada.

### Hacerlo con un envoltorio {#doing-it-in-a-wrapper-instead}

Merece la pena si quiere el texto completo del complemento en lugar de su
resumen, o un esquema de prioridades propio. Esta forma también sirve para
cualquier otro servicio del tipo "avísame si falla":

```shell
#!/bin/sh
set -eu
output="$(check-opencloud-security --host opencloud.example.com --check-hardening)" || state=$?
state="${state:-0}"

case "$state" in
  0) exit 0 ;;                       # nothing to say
  1) priority=default ;;
  2) priority=urgent ;;
  *) priority=high ;;
esac

printf '%s' "$output" | curl -sS \
  -H "Title: OpenCloud security check" \
  -H "Priority: $priority" \
  -H "Tags: warning" \
  -d @- https://ntfy.example.com/opencloud
```

Fíjese en `|| state=$?`: el código de salida del complemento *es* el
resultado, y de lo contrario `set -e` abandonaría el script justo cuando hay
algo que notificar.

## Alertmanager {#alertmanager}

La API v2 de Alertmanager espera una lista de alertas, y espera que dejen de
llegar antes de resolverlas:

```shell
check-opencloud-security --host opencloud.example.com --webhook-url \
  http://127.0.0.1:8098/  # an adapter that posts to /api/v2/alerts
```

```json
[{
  "labels": {
    "alertname": "OpenCloudSecurity",
    "instance": "opencloud.example.com",
    "severity": "critical"
  },
  "annotations": {"summary": "<message from the payload>"},
  "startsAt": "<timestamp from the payload>"
}]
```

Envíe una alerta solo para los estados por los que quiera que se avise a
alguien, y deje que caduque en lugar de intentar resolverla a mano: el
siguiente análisis puede tardar hasta un día, y una alerta resuelta antes de
tiempo deja de avisar sobre un servidor que
sigue siendo vulnerable. Si ya envía métricas,
[Prometheus y Grafana](../prometheus.md) es la mejor vía hacia Alertmanager.

## Probar un receptor sin una instancia {#testing-a-receiver-without-an-instance}

`--webhook-on always` junto con un host que no existe produce una entrega real
de la carga útil de fallo, que es el caso que los receptores suelen gestionar
mal:

```shell
check-opencloud-security --host does-not-exist.example.com \
  --webhook-url http://127.0.0.1:8099/ --webhook-on always
```

Para la forma sana, apúntelo a una instancia real de su propiedad. `--debug`
registra que se ha enviado un webhook y adónde, pero no el cuerpo; para ver el
cuerpo, apunte el webhook a algo que lo devuelva, como
`python3 -m http.server` o un receptor propio de una línea.

---

[Volver al índice de la documentación](../README.md) | [Volver al README principal](../../README.md)
