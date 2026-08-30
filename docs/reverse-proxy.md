# Reverse proxies

Two different machines in this project sit behind a reverse proxy, and they
want opposite things from it.

- **In front of an OpenCloud instance**, the proxy is the thing this check
  grades. Most of the findings under *headers* are decided there, and a proxy
  that strips a header OpenCloud sent will cost an instance a grade it had
  earned. → [In front of OpenCloud](#in-front-of-opencloud)
- **In front of the scan service** from this repository, the proxy decides
  whether the rate limit works at all, and whether a scan that takes a minute
  survives long enough to be read. → [In front of the scan
  service](#in-front-of-the-scan-service)

Both sections carry worked configuration for nginx, Apache httpd, Caddy,
Traefik and HAProxy. Replace `opencloud.example.com` and
`scan.example.com` with your own names; no real hostname appears anywhere in
this repository.

<!-- TOC -->
* [Reverse proxies](#reverse-proxies)
  * [In front of OpenCloud](#in-front-of-opencloud)
    * [The headers this check looks for](#the-headers-this-check-looks-for)
    * [Two findings decided here that are not headers](#two-findings-decided-here-that-are-not-headers)
    * [nginx](#nginx)
    * [Apache httpd](#apache-httpd)
    * [Caddy](#caddy)
    * [Traefik](#traefik)
    * [HAProxy](#haproxy)
    * [Mistakes that cost a grade](#mistakes-that-cost-a-grade)
  * [In front of the scan service](#in-front-of-the-scan-service)
    * [What the service needs from a proxy](#what-the-service-needs-from-a-proxy)
    * [nginx](#nginx-1)
    * [Apache httpd](#apache-httpd-1)
    * [Caddy](#caddy-1)
    * [Traefik](#traefik-1)
    * [HAProxy](#haproxy-1)
    * [Checking the result](#checking-the-result)
<!-- TOC -->

## In front of OpenCloud

OpenCloud's own proxy service already sends a full set of security headers. A
finding under *headers* therefore almost always means one of two things:
something in front of it removed them, or something in front of it answers
before OpenCloud does. Adding them again in the proxy fixes both.

### The headers this check looks for

| Header | What this check accepts |
|:-------|:------------------------|
| `Strict-Transport-Security` | Any `max-age`. A year or more also passes `hstsLongMaxAge`, and `preload` passes `hstsPreload` |
| `Content-Security-Policy` | Any non-empty policy. A policy containing `unsafe-inline` fails `cspWithoutUnsafeInline` separately |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `SAMEORIGIN` |
| `X-Permitted-Cross-Domain-Policies` | `none` |
| `X-Robots-Tag` | Any non-empty value |
| `X-XSS-Protection` | Any non-empty value. Modern browsers ignore it; it is checked because OpenCloud sends it |
| `Referrer-Policy` | Any non-empty value |

Send them on the HTTPS listener only. `Strict-Transport-Security` on a plain
HTTP response is ignored by browsers and tells an attacker nothing useful.

### Two findings decided here that are not headers

Both are hardening flags rather than extra checks, so neither lowers the
grade on its own - they raise the state to WARNING and are waivable with
`--ignore-hardening`.

| Flag | What has to be true to pass |
|:-----|:----------------------------|
| `httpsEnforced` | A request to `http://` on port 80 answers with a redirect whose `Location` starts with `https://` - or port 80 does not answer at all |
| `reverseProxyDetected` | Something in the response looks like a proxy: a proxy-style `Server` header, or any `Via` header |

**`httpsEnforced`** is measured without following redirects: the scan asks
port 80 for `/` once and reads the `Location` it gets back. A redirect to
another plain-HTTP address, a `200` that serves the interface, and a
redirect chain that reaches HTTPS only on its second hop all fail. A closed
or filtered port 80 **passes** - plain HTTP cannot be spoken at all, which is
the stronger version of enforcing it.

**`reverseProxyDetected`** is deliberately best-effort and never changes the
rating, because Traefik and HAProxy announce nothing by default. A
well-configured deployment can fail it with nothing wrong; treat it as a
prompt to confirm there is something in front, not as a defect. If there is
not, the configuration below is the usual way to put one there.

### nginx

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

`add_header` in nginx is **not** additive across levels: one `add_header` in a
`location` discards every `add_header` from the `server` block. If you add one
inside a `location`, repeat the whole set there.

`Content-Security-Policy` is deliberately absent above. OpenCloud sends its
own, and a policy written by hand in the proxy is how an instance ends up with
a broken web interface. Only set one here if the check reports it missing and
you have established that nothing behind the proxy sends it.

### Apache httpd

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

Needs `mod_headers`, `mod_proxy`, `mod_proxy_http` and `mod_ssl`. Apache sets
`X-Forwarded-For` itself and appends the client to it; do not also set it by
hand, or the instance sees the address twice.

### Caddy

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

Caddy terminates TLS and redirects port 80 by itself, and it sets
`X-Forwarded-For`, `X-Forwarded-Proto` and `X-Forwarded-Host` without being
asked. Its `header` directive replaces a header the backend already sent, so
this is safe to leave in place even once OpenCloud sends its own again.

### Traefik

As labels on the OpenCloud container:

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

`stsSeconds` is the only way to get HSTS out of Traefik's headers middleware -
setting `Strict-Transport-Security` through `customResponseHeaders` is
overwritten. Traefik only sends HSTS on a TLS router, which is what you want.

### HAProxy

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

`set-header` replaces; `add-header` would append a second copy, and two
`Strict-Transport-Security` headers are worse than none.

### Mistakes that cost a grade

- **A header set only on `200`.** nginx's `add_header` without `always`, and
  Apache's `Header set` without `always`, both skip error responses. This
  check reads the headers of whatever the instance answers, so a redirect or
  a 401 without them is a finding.
- **A proxy that answers first.** A maintenance page, an authentication
  gateway or a CDN error page is what gets scanned, and none of them look like
  OpenCloud. If the check reports the wrong product or no version at all,
  something in front is answering. See
  [Troubleshooting](troubleshooting.md).
- **`X-Forwarded-For` appended from a client-supplied value.** Not a finding
  here, but it makes every rate limit and every audit log behind the proxy
  guesswork. Overwrite it at the edge.
- **HTTP left open.** A redirect is enough; this check follows it and grades
  the destination. What it will not forgive is a plain-HTTP listener that
  serves the interface as well - that is the `httpsEnforced` flag
  [above](#two-findings-decided-here-that-are-not-headers).
- **A self-signed or expired certificate.** The scan refuses to establish a
  version over an untrusted connection, and no header can make up for that.

## In front of the scan service

The web application in this repository - [`docs/webapp.md`](webapp.md) - is a
plain ASGI service on one port. It sends its own security headers, including a
`Content-Security-Policy` with no `unsafe-inline`, so a proxy has nothing to
add. What it does need is the truth about who is calling and enough patience
for a scan to finish.

### What the service needs from a proxy

- **A real client address.** The rate limit and the target cooldown are the
  only things standing between a public scanner and being used as an
  amplifier, and both key off the client address. Overwrite `X-Forwarded-For`
  at the edge and set `COS_WEB_TRUST_FORWARDED_FOR=true`; without the
  overwrite, a client can pick its own bucket by sending the header itself.
- **Timeouts longer than a scan.** A scan takes seconds to a minute; a PDF
  export and an MCP `scan_instance` call can hold a response for minutes. 120
  seconds is a sensible floor and the MCP endpoint wants more.
- **No response buffering on `/mcp`.** The Model Context Protocol endpoint
  answers with an event stream. A proxy that buffers it turns a working
  session into a client that waits for ever.
- **No rewriting of the discovery paths.** `/.well-known/ai.json`,
  `/openapi.json`, `/arazzo.json`, `/robots.txt` and `/sitemap.xml` are served
  by the application and must reach it unchanged. A proxy that answers
  `/.well-known/` itself - some ACME setups do - has to exclude that file.
- **The public origin, once.** Set `COS_WEB_PUBLIC_BASE_URL` to the address
  visitors use. Canonical links, the sitemap and the absolute URLs in the
  discovery document are built from it, and behind a proxy the application
  cannot work it out on its own.

### nginx

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

Then:

```bash
COS_WEB_TRUST_FORWARDED_FOR=true
COS_WEB_PUBLIC_BASE_URL=https://scan.example.com
COS_WEB_MCP_ALLOWED_HOSTS=scan.example.com
```

`COS_WEB_MCP_ALLOWED_HOSTS` is the MCP endpoint's DNS-rebinding protection. It
is safe to leave empty behind a proxy that already fixes the host, and worth
setting anyway - it costs nothing and it is one `Host` header away from being
the only check.

### Apache httpd

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

Order matters: the `<Location "/mcp">` block has to come before the catch-all
`ProxyPass /`, or the catch-all wins and the stream is buffered again.

### Caddy

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

`flush_interval -1` disables buffering, which is what the event stream needs.
Caddy writes `X-Forwarded-For` from the connection and drops what the client
sent, so `COS_WEB_TRUST_FORWARDED_FOR=true` is safe with no extra
configuration.

### Traefik

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

with, on the static configuration:

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

Traefik overwrites `X-Real-Ip` and appends to `X-Forwarded-For`; the
application reads the **first** entry, which is the client, so
`COS_WEB_TRUST_FORWARDED_FOR=true` is correct here as long as Traefik is the
only proxy and is not itself behind one it trusts blindly.

### HAProxy

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

`timeout tunnel` is what keeps the MCP stream alive; `timeout server` alone
closes it mid-session.

### Checking the result

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

The rate limit is the one thing worth testing from somewhere else: submit more
scans than `COS_WEB_IP_RATE_LIMIT` allows from one machine and confirm the
**429**, then repeat from a second address and confirm it is *not* refused. If
the second machine is limited too, the proxy is not passing the address on and
every visitor is sharing one bucket.

---

This is an independent community project. It is not affiliated with, endorsed
by or supported by OpenCloud GmbH. "OpenCloud" and all related marks belong to
their respective owners and are used here only to identify the software this
tool checks.
