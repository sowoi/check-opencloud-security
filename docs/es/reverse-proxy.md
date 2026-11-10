# Proxy inverso para el escáner de seguridad de OpenCloud

En este proyecto hay dos equipos distintos que se sitúan detrás de un proxy
inverso, y cada uno necesita de él lo contrario que el otro.

- **Delante de una instancia de OpenCloud**, el proxy es lo que califica esta
  comprobación. La mayoría de los hallazgos de *cabeceras* se deciden ahí, y un
  proxy que elimina una cabecera enviada por OpenCloud le costará a una
  instancia una nota que se había ganado.
  → [Delante de OpenCloud](#in-front-of-opencloud)
- **Delante del servicio de análisis** de este repositorio, el proxy decide si
  el límite de frecuencia funciona y si un análisis que tarda un minuto
  sobrevive lo suficiente para poder leerse.
  → [Delante del servicio de análisis](#in-front-of-the-scan-service)

Ambas secciones incluyen configuraciones completas para nginx, Apache httpd,
Caddy, Traefik y HAProxy. Sustituya `opencloud.example.com` y
`scan.example.com` por sus propios nombres; en este repositorio no aparece
ningún nombre de host real.

<!-- TOC -->
* [Proxies inversos](#reverse-proxies)
  * [Delante de OpenCloud](#in-front-of-opencloud)
    * [Las cabeceras que busca esta comprobación](#the-headers-this-check-looks-for)
    * [Dos hallazgos que se deciden aquí y no son cabeceras](#two-findings-decided-here-that-are-not-headers)
    * [nginx](#nginx)
    * [Apache httpd](#apache-httpd)
    * [Caddy](#caddy)
    * [Traefik](#traefik)
    * [HAProxy](#haproxy)
    * [Errores que cuestan nota](#mistakes-that-cost-a-grade)
  * [Delante del servicio de análisis](#in-front-of-the-scan-service)
    * [Qué necesita el servicio de un proxy](#what-the-service-needs-from-a-proxy)
    * [nginx](#nginx-1)
    * [Apache httpd](#apache-httpd-1)
    * [Caddy](#caddy-1)
    * [Traefik](#traefik-1)
    * [HAProxy](#haproxy-1)
    * [Comprobar el resultado](#checking-the-result)
<!-- TOC -->

## Delante de OpenCloud {#in-front-of-opencloud}

El servicio proxy propio de OpenCloud ya envía un conjunto completo de
cabeceras de seguridad. Por eso, un hallazgo de *cabeceras* casi siempre
significa una de dos cosas: algo situado delante las ha eliminado, o algo
situado delante responde antes que OpenCloud. Volver a añadirlas en el proxy
resuelve ambos casos.

### Las cabeceras que busca esta comprobación {#the-headers-this-check-looks-for}

| Cabecera | Qué acepta esta comprobación |
|:-------|:------------------------|
| `Strict-Transport-Security` | Cualquier `max-age`. Un año o más supera también `hstsLongMaxAge`, y `preload` supera `hstsPreload` |
| `Content-Security-Policy` | Cualquier política no vacía. Una política que contenga `unsafe-inline` falla por separado en `cspWithoutUnsafeInline` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `SAMEORIGIN` |
| `X-Permitted-Cross-Domain-Policies` | `none` |
| `X-Robots-Tag` | Cualquier valor no vacío |
| `X-XSS-Protection` | Cualquier valor no vacío. Los navegadores modernos la ignoran; se comprueba porque OpenCloud la envía |
| `Referrer-Policy` | Cualquier valor no vacío |

Envíelas solo en el servicio HTTPS. Los navegadores ignoran
`Strict-Transport-Security` en una respuesta HTTP sin cifrar, y no le dice nada
útil a un atacante.

### Dos hallazgos que se deciden aquí y no son cabeceras {#two-findings-decided-here-that-are-not-headers}

Ambos son indicadores de refuerzo y no comprobaciones adicionales, así que
ninguno reduce la nota por sí solo: elevan el estado a WARNING y se pueden
excluir con `--ignore-hardening`.

| Indicador | Qué tiene que cumplirse para superarlo |
|:-----|:----------------------------|
| `httpsEnforced` | Una solicitud a `http://` en el puerto 80 responde con una redirección cuyo `Location` empieza por `https://`, o el puerto 80 no responde |
| `reverseProxyDetected` | Algo en la respuesta parece un proxy: una cabecera `Server` de estilo proxy o cualquier cabecera `Via` |

**`httpsEnforced`** se mide sin seguir redirecciones: el análisis pide `/` una
vez al puerto 80 y lee el `Location` que recibe. Fallan una redirección a otra
dirección HTTP sin cifrar, un `200` que sirve la interfaz y una cadena de
redirecciones que solo llega a HTTPS en el segundo salto. Un puerto 80 cerrado
o filtrado **se supera**: no se puede hablar HTTP sin cifrar, que es la versión
más estricta de exigir HTTPS.

**`reverseProxyDetected`** es aproximado y nunca cambia la
nota, porque Traefik y HAProxy no anuncian nada por defecto. Un despliegue bien
configurado puede fallarlo sin que haya nada mal; tómelo como una invitación a
confirmar que hay algo delante. Si no lo hay, la
configuración siguiente es la forma habitual de ponerlo.

### nginx {#nginx}

```nginx
server {
    listen 443 ssl http2;
    server_name opencloud.example.com;

    ssl_certificate     /etc/ssl/opencloud/fullchain.pem;
    ssl_certificate_key /etc/ssl/opencloud/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    # always: also on 4xx and 5xx, which is where a missing header hides.
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Permitted-Cross-Domain-Policies "none" always;
    add_header X-Robots-Tag "noindex, nofollow" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    client_max_body_size 0;          # uploads are not the proxy's business
    proxy_request_buffering off;

    location / {
        proxy_pass http://127.0.0.1:9200;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $remote_addr;   # overwrite, never append
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        $connection_upgrade;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}

server {
    listen 80;
    server_name opencloud.example.com;
    return 308 https://$host$request_uri;
}
```

En nginx, `add_header` **no** se acumula entre niveles: un solo `add_header` en
una `location` descarta todos los `add_header` del bloque `server`. Si añade uno
dentro de una `location`, repita allí el conjunto completo.

`Content-Security-Policy` falta deliberadamente arriba. OpenCloud envía la
suya, y una política escrita a mano en el proxy es la forma en que una
instancia acaba con una interfaz web rota. Defina una aquí solo si la
comprobación indica que falta y ha confirmado que nada detrás del proxy la
envía.

### Apache httpd {#apache-httpd}

```apache
<VirtualHost *:443>
    ServerName opencloud.example.com

    SSLEngine on
    SSLCertificateFile      /etc/ssl/opencloud/fullchain.pem
    SSLCertificateKeyFile   /etc/ssl/opencloud/privkey.pem
    SSLProtocol             -all +TLSv1.2 +TLSv1.3

    # 'always' is the condition, not the flag: it covers error responses too.
    Header always set Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
    Header always set X-Content-Type-Options "nosniff"
    Header always set X-Frame-Options "SAMEORIGIN"
    Header always set X-Permitted-Cross-Domain-Policies "none"
    Header always set X-Robots-Tag "noindex, nofollow"
    Header always set X-XSS-Protection "1; mode=block"
    Header always set Referrer-Policy "strict-origin-when-cross-origin"

    ProxyPreserveHost On
    ProxyPass        / http://127.0.0.1:9200/ timeout=3600
    ProxyPassReverse / http://127.0.0.1:9200/
    RequestHeader set X-Forwarded-Proto "https"
</VirtualHost>
```

Necesita `mod_headers`, `mod_proxy`, `mod_proxy_http` y `mod_ssl`. Apache
define `X-Forwarded-For` por sí mismo y le añade el cliente; no lo defina
también a mano, o la instancia verá la dirección dos veces.

### Caddy {#caddy}

```caddyfile
opencloud.example.com {
    encode zstd gzip

    header {
        Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        X-Permitted-Cross-Domain-Policies "none"
        X-Robots-Tag "noindex, nofollow"
        X-XSS-Protection "1; mode=block"
        Referrer-Policy "strict-origin-when-cross-origin"
    }

    reverse_proxy 127.0.0.1:9200 {
        transport http {
            read_timeout 1h
        }
    }
}
```

Caddy termina TLS y redirige el puerto 80 por sí mismo, y define
`X-Forwarded-For`, `X-Forwarded-Proto` y `X-Forwarded-Host` sin que se le pida.
Su directiva `header` sustituye una cabecera que el backend ya haya enviado,
así que es seguro dejarla aunque OpenCloud vuelva a enviar las suyas.

### Traefik {#traefik}

Como etiquetas en el contenedor de OpenCloud:

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.opencloud.rule=Host(`opencloud.example.com`)"
  - "traefik.http.routers.opencloud.entrypoints=websecure"
  - "traefik.http.routers.opencloud.tls.certresolver=letsencrypt"
  - "traefik.http.services.opencloud.loadbalancer.server.port=9200"
  - "traefik.http.routers.opencloud.middlewares=opencloud-headers"
  - "traefik.http.middlewares.opencloud-headers.headers.stsSeconds=63072000"
  - "traefik.http.middlewares.opencloud-headers.headers.stsIncludeSubdomains=true"
  - "traefik.http.middlewares.opencloud-headers.headers.stsPreload=true"
  - "traefik.http.middlewares.opencloud-headers.headers.contentTypeNosniff=true"
  - "traefik.http.middlewares.opencloud-headers.headers.frameDeny=false"
  - "traefik.http.middlewares.opencloud-headers.headers.customFrameOptionsValue=SAMEORIGIN"
  - "traefik.http.middlewares.opencloud-headers.headers.referrerPolicy=strict-origin-when-cross-origin"
  - "traefik.http.middlewares.opencloud-headers.headers.customResponseHeaders.X-Permitted-Cross-Domain-Policies=none"
  - "traefik.http.middlewares.opencloud-headers.headers.customResponseHeaders.X-Robots-Tag=noindex, nofollow"
  - "traefik.http.middlewares.opencloud-headers.headers.customResponseHeaders.X-XSS-Protection=1; mode=block"
```

`stsSeconds` es la única forma de obtener HSTS del middleware de cabeceras de
Traefik: definir `Strict-Transport-Security` mediante `customResponseHeaders`
se sobrescribe. Traefik solo envía HSTS en un router TLS, que es lo que se
busca.

### HAProxy {#haproxy}

```haproxy
frontend https-in
    bind :443 ssl crt /etc/ssl/opencloud/opencloud.pem alpn h2,http/1.1
    http-request redirect scheme https unless { ssl_fc }

    http-response set-header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
    http-response set-header X-Content-Type-Options "nosniff"
    http-response set-header X-Frame-Options "SAMEORIGIN"
    http-response set-header X-Permitted-Cross-Domain-Policies "none"
    http-response set-header X-Robots-Tag "noindex, nofollow"
    http-response set-header X-XSS-Protection "1; mode=block"
    http-response set-header Referrer-Policy "strict-origin-when-cross-origin"

    default_backend opencloud

backend opencloud
    option forwardfor
    http-request set-header X-Forwarded-Proto https
    timeout server 1h
    server oc1 127.0.0.1:9200 check
```

`set-header` sustituye; `add-header` añadiría una segunda copia, y dos
cabeceras `Strict-Transport-Security` son peores que ninguna.

### Errores que cuestan nota {#mistakes-that-cost-a-grade}

- **Una cabecera definida solo en respuestas `200`.** `add_header` de nginx
  sin `always` y `Header set` de Apache sin `always` omiten las respuestas de
  error. Esta comprobación lee las cabeceras de lo que responda la instancia,
  así que una redirección o un 401 sin ellas es un hallazgo.
- **Un proxy que responde primero.** Lo que se analiza es una página de
  mantenimiento, una pasarela de autenticación o una página de error de una
  CDN, y ninguna se parece a OpenCloud. Si la comprobación notifica un producto
  equivocado o ninguna versión, algo situado delante está respondiendo.
  Consulte [Solución de problemas](../troubleshooting.md).
- **`X-Forwarded-For` añadido a partir de un valor enviado por el cliente.**
  Aquí no es un hallazgo, pero convierte en conjeturas todos los límites de
  frecuencia y registros de auditoría detrás del proxy. Sobrescríbalo en el
  proxy que recibe las solicitudes externas.
- **`X-Forwarded-Host` reenviado tal como lo envía el cliente.** Esto *sí* es
  un hallazgo, `forwardedHostIgnored`, cuando la instancia construye después
  sus URL públicas a partir de él. El análisis pide el documento de
  descubrimiento indicando un host que no existe y lo busca en el `issuer` y en
  los puntos de acceso, porque es ahí adonde se envía el siguiente inicio de
  sesión. Defina `OC_URL` para que la instancia conozca su propia dirección, y
  defina la cabecera desde la configuración del propio proxy
  (`proxy_set_header X-Forwarded-Host $host;`) en lugar de reenviar lo que
  llegue. Un host virtual predeterminado que rechace los nombres que no
  reconoce impide el mismo problema con la cabecera `Host`.
- **Ningún servidor predeterminado.** Sin uno, nginx responde a un `Host` para
  el que no tiene `server_name` desde el primer bloque `server` que cargó para
  ese puerto (a menudo otra aplicación del mismo equipo), y Apache desde el
  primer `<VirtualHost>`. Cuando ese sitio redirige con `$host`, el host de
  prueba vuelve en el `Location`, y `forwardedHostIgnored` falla con
  `Host comes back as the address it redirects to` aunque OpenCloud nunca vio
  la solicitud y `OC_URL` esté bien definido. La pista es un certificado o un
  conjunto de cabeceras distinto en una solicitud con un `Host` inventado:

  ```bash
  curl -sI -H "Host: unknown.invalid" https://opencloud.example.com/.well-known/openid-configuration
  ```

  Dé al proxy un servidor predeterminado explícito que rechace todos los
  nombres que no sirve, y escriba las redirecciones de los demás sitios con su
  propio nombre en lugar de `$host`:

  ```nginx
  server {
      listen 80 default_server;
      listen [::]:80 default_server;
      listen 443 ssl default_server;
      listen [::]:443 ssl default_server;
      server_name _;
      ssl_reject_handshake on;   # nginx 1.19.4 and later; no certificate needed
      return 444;
  }
  ```

  En Apache, haga que el primer `<VirtualHost>` de cada puerto sea uno que no
  sirva nada (`Redirect 403 /`). Caddy y Traefik responden a un nombre
  desconocido sin enrutarlo a ningún sitio, así que aquí no necesitan nada.
- **HTTP abierto.** Basta con una redirección; esta comprobación la sigue y
  califica el destino. Lo que no perdona es un servicio HTTP sin cifrar que
  también sirva la interfaz: eso es el indicador `httpsEnforced` descrito
  [más arriba](#two-findings-decided-here-that-are-not-headers).
- **Un certificado autofirmado o caducado.** El análisis se niega a
  establecer una versión a través de una conexión no fiable, y ninguna
  cabecera puede compensarlo.

## Delante del servicio de análisis {#in-front-of-the-scan-service}

La aplicación web de este repositorio ([`docs/webapp.md`](../webapp.md)) es un
servicio ASGI simple en un puerto. Envía sus propias cabeceras de seguridad,
incluida una `Content-Security-Policy` sin `unsafe-inline`, así que un proxy
no tiene nada que añadir. El proxy debe transmitir la dirección real del cliente y
permitir que la conexión dure lo suficiente para completar un análisis.

**No tiene que copiar nada de esto a mano.**
[`docker/setup-wizard.py`](../../docker/setup-wizard.py) escribe la
configuración de nginx, Apache, Caddy o Traefik para un despliegue generado,
siguiendo las notas siguientes y rellenando el nombre de host, el puerto y,
cuando la pila incluye su propio proveedor de identidad, la autenticación
delegada delante de `/admin` y un sitio para el propio Authentik en el nombre de
host de su dirección pública. Estas secciones son lo que genera, y la
referencia para un despliegue que no haya escrito el asistente.

### Qué necesita el servicio de un proxy {#what-the-service-needs-from-a-proxy}

- **Una dirección de cliente real.** El límite de frecuencia y el tiempo de
  espera por destino son lo único que impide que un escáner público se use
  como amplificador, y ambos se basan en la dirección del cliente. Reenvíe
  `X-Forwarded-For` y defina `COS_WEB_TRUST_FORWARDED_FOR=true`, además de
  `COS_WEB_TRUSTED_PROXY_HOPS` si hay más de un proxy suyo en el camino.

  La cabecera se lee desde la **derecha**, tantas entradas como se indique, así
  que un proxy que añade es tan seguro como uno que sobrescribe: lo que envía
  un cliente queda a la izquierda de la entrada que escribió su propio proxy y
  nunca se alcanza. Defina el número de saltos como el número de proxies *que
  usted gestiona*: si se queda corto, se toma un proxy en lugar del visitante,
  lo que es inofensivo, pero si se pasa, se entra en la parte de la cabecera que
  controla el cliente.
- **Tiempos de espera más largos que un análisis.** Un análisis tarda entre
  unos segundos y un minuto; una exportación a PDF y una llamada MCP a
  `scan_instance` pueden mantener una respuesta durante minutos. 120 segundos
  es un mínimo razonable, y el punto de acceso MCP necesita más.
- **Sin búfer de respuestas en `/mcp`.** El punto de acceso del Model Context
  Protocol responde con un flujo de eventos. Un proxy que lo almacena en búfer
  convierte una sesión que funciona en un cliente que espera eternamente.
- **Sin reescritura de las rutas de descubrimiento.**
  `/.well-known/ai.json`, `/openapi.json`, `/arazzo.json`, `/robots.txt` y
  `/sitemap.xml` los sirve la aplicación y deben llegarle sin cambios. Un proxy
  que responde él mismo a `/.well-known/` (algunas configuraciones ACME lo
  hacen) tiene que excluir ese archivo.
- **El origen público, una vez.** Defina `COS_WEB_PUBLIC_BASE_URL` con la
  dirección que usan los visitantes. Los enlaces canónicos, el mapa del sitio y
  las URL absolutas del documento de descubrimiento se construyen a partir de
  ella, y detrás de un proxy la aplicación no puede deducirla por sí sola.

### nginx {#nginx_1}

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl http2;
    server_name scan.example.com;

    ssl_certificate     /etc/ssl/scan/fullchain.pem;
    ssl_certificate_key /etc/ssl/scan/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8811;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        # Overwrite. Appending would let a client choose its own rate limit.
        proxy_set_header X-Forwarded-For   $remote_addr;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_read_timeout 300s;
    }

    # The MCP endpoint streams. Buffering it breaks every agent session.
    location /mcp {
        proxy_pass http://127.0.0.1:8811;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For   $remote_addr;
        proxy_set_header Connection        "";
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding off;
        proxy_read_timeout 3600s;
    }

    location /static/ {
        proxy_pass http://127.0.0.1:8811;
        proxy_cache_valid 200 1h;
        expires 1h;
    }
}
```

Después:

```bash
COS_WEB_TRUST_FORWARDED_FOR=true
COS_WEB_TRUSTED_PROXY_HOPS=1
COS_WEB_PUBLIC_BASE_URL=https://scan.example.com
COS_WEB_MCP_ALLOWED_HOSTS=scan.example.com
```

`COS_WEB_MCP_ALLOWED_HOSTS` es la protección del punto de acceso MCP contra
DNS rebinding. Es seguro dejarla vacía detrás de un proxy que ya fija el host,
y conviene definirla de todos modos: no cuesta nada y está a una cabecera
`Host` de ser la única comprobación.

### Apache httpd {#apache-httpd_1}

```apache
<VirtualHost *:443>
    ServerName scan.example.com

    SSLEngine on
    SSLCertificateFile    /etc/ssl/scan/fullchain.pem
    SSLCertificateKeyFile /etc/ssl/scan/privkey.pem

    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "https"

    # The client, and only the client. mod_remoteip first if you are behind
    # another proxy, so that %a is the address you actually want to forward.
    RequestHeader set X-Forwarded-For "%{REMOTE_ADDR}e"

    # The event stream must not be buffered or the session never starts.
    <Location "/mcp">
        ProxyPass        http://127.0.0.1:8811/mcp flushpackets=on timeout=3600
        ProxyPassReverse http://127.0.0.1:8811/mcp
        SetEnv proxy-sendchunked 1
        SetEnv no-gzip 1
    </Location>

    ProxyPass        / http://127.0.0.1:8811/ timeout=300
    ProxyPassReverse / http://127.0.0.1:8811/
</VirtualHost>
```

El orden importa: el bloque `<Location "/mcp">` tiene que ir antes del
`ProxyPass /` general, o este prevalece y el flujo vuelve a almacenarse en
búfer.

### Caddy {#caddy_1}

```caddyfile
scan.example.com {
    encode zstd gzip

    # Streaming, and a timeout long enough for a scan to finish.
    reverse_proxy /mcp* 127.0.0.1:8811 {
        flush_interval -1
        transport http {
            read_timeout 1h
        }
    }

    reverse_proxy 127.0.0.1:8811 {
        transport http {
            read_timeout 5m
        }
    }
}
```

`flush_interval -1` desactiva el búfer, que es lo que necesita el flujo de
eventos. Caddy escribe `X-Forwarded-For` a partir de la conexión y descarta lo
que envió el cliente, así que `COS_WEB_TRUST_FORWARDED_FOR=true` es seguro con
el valor predeterminado `COS_WEB_TRUSTED_PROXY_HOPS=1`.

### Traefik {#traefik_1}

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.scan.rule=Host(`scan.example.com`)"
  - "traefik.http.routers.scan.entrypoints=websecure"
  - "traefik.http.routers.scan.tls.certresolver=letsencrypt"
  - "traefik.http.services.scan.loadbalancer.server.port=8811"
  # Do not buffer the MCP event stream; Traefik streams by default, so the
  # only thing to get right is the timeout on the entrypoint.
  - "traefik.http.services.scan.loadbalancer.responseForwarding.flushInterval=1ms"
```

y, en la configuración estática:

```yaml
entryPoints:
  websecure:
    address: ":443"
    transport:
      respondingTimeouts:
        readTimeout: 0        # a submission may hold the connection
        writeTimeout: 0       # a scan may take a minute, an MCP call longer
        idleTimeout: 300s
```

Traefik sobrescribe `X-Real-Ip` y *añade* a `X-Forwarded-For`. La aplicación
lee la cabecera desde la derecha, así que la entrada que toma es la que
escribió Traefik y no lo que el cliente pusiera delante:
`COS_WEB_TRUST_FORWARDED_FOR=true` con el valor predeterminado
`COS_WEB_TRUSTED_PROXY_HOPS=1` es correcto aquí. Si además hay una CDN
delante, cuente ambos y defina `2`.

### HAProxy {#haproxy_1}

```haproxy
frontend scan-in
    bind :443 ssl crt /etc/ssl/scan/scan.pem alpn h2,http/1.1
    http-request set-header X-Forwarded-Proto https
    # set-header, not add-header: the client does not get a vote.
    http-request set-header X-Forwarded-For %[src]
    default_backend scan

backend scan
    option http-server-close
    no option http-buffer-request
    timeout server 1h
    timeout tunnel 1h
    server scan1 127.0.0.1:8811 check
```

`timeout tunnel` es lo que mantiene vivo el flujo MCP; `timeout server` por sí
solo lo cierra en mitad de la sesión.

### Comprobar el resultado {#checking-the-result}

```bash
# The client address the service actually sees, through the proxy.
curl -sS https://scan.example.com/healthz

# Discovery must be reachable, unauthenticated, and JSON.
curl -sS https://scan.example.com/.well-known/ai.json | head -c 200
curl -sSo /dev/null -w '%{http_code}\n' https://scan.example.com/openapi.json
curl -sSo /dev/null -w '%{http_code}\n' https://scan.example.com/arazzo.json

# The absolute URLs in the discovery document must be the public ones, not
# 127.0.0.1 - if they are wrong, COS_WEB_PUBLIC_BASE_URL is not set.
curl -sS https://scan.example.com/.well-known/ai.json | grep -o 'https://[^"]*' | head

# MCP: an initialise that answers is a proxy that is not buffering.
curl -sS -X POST https://scan.example.com/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":"2025-06-18","capabilities":{},
        "clientInfo":{"name":"curl","version":"1"}}}'
```

El límite de frecuencia es lo único que merece la pena probar desde otro
lugar: envíe desde un equipo más análisis de los que permite
`COS_WEB_IP_RATE_LIMIT` y confirme el **429**; después repita desde una segunda
dirección y confirme que *no* se rechaza. Si el segundo equipo también queda
limitado, el proxy no está reenviando la dirección y todos los visitantes
comparten el mismo cupo.

---

Este es un proyecto comunitario independiente. No está afiliado a OpenCloud
GmbH, ni respaldado ni apoyado por ella. "OpenCloud" y todas las marcas
relacionadas pertenecen a sus respectivos titulares y aquí solo se utilizan
para identificar el software que comprueba esta herramienta.
