# Qué lee el escáner de seguridad de OpenCloud y qué no

Este inventario describe todo lo que un análisis obtiene de una instancia: los
puntos de acceso que lee, cada comprobación adicional que ejecuta y su impacto,
qué observaciones se registran pero nunca se califican y las preguntas
que un análisis desde fuera no puede responder.

El [README principal](../../README.md#the-built-in-scanner) lo resume en un
párrafo; las comprobaciones concretas se explican grupo por grupo en
[TLS](../tls.md), [CSP](../csp.md), [cookies](../cookies.md),
[autenticación](../authentication.md), [uso compartido](../sharing.md),
[exposición](../exposure.md), [inserción](../embedding.md) y
[ciclo de vida](../lifecycle.md).

<!-- TOC -->
* [Qué lee el escáner y qué no lee deliberadamente](#what-the-scanner-reads-and-what-it-deliberately-does-not)
  * [Qué comprueba el escáner](#what-the-scanner-checks)
  * [Leer la versión correctamente](#reading-the-version-correctly)
  * [Puertos de depuración](#debug-ports)
  * [Todas las direcciones resueltas](#every-resolved-address)
<!-- TOC -->


## Qué comprueba el escáner {#what-the-scanner-checks}

Se lee de la propia instancia:

- el producto, `productversion` y la edición de `/status.php`. Otros productos
  se rechazan porque sus versiones y avisos de seguridad no corresponden a la
  base de datos de este escáner. OpenCloud tiene fijados en el código
  `maintenance`, `installed` y `needsDbUpgrade`, así que esos campos no se
  tratan como comprobaciones de estado reales; consulte
  [el punto de acceso de estado](../status-php.md).
- las direcciones IPv4 e IPv6 a las que se resolvió el nombre durante el
  análisis, notificadas como `addresses` en el documento de resultado y
  mostradas como **Resuelto a** en la página de resultados web: contexto,
  nunca un hallazgo, y vacío cuando un nombre no se resuelve o se analizó
  directamente una dirección
- las capacidades de `/ocs/v1.php/cloud/capabilities` (ambos puntos de acceso
  son públicos en OpenCloud)
- las cabeceras de seguridad `Strict-Transport-Security`,
  `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`,
  `X-Permitted-Cross-Domain-Policies`, `X-Robots-Tag`, `X-XSS-Protection` y
  `Referrer-Policy`, notificadas como `setup.headers`; consulte
  [`docs/csp.md`](../csp.md) para saber qué buscan las comprobaciones de
  `Content-Security-Policy` y por qué
- otras cuatro cabeceras que **ningún** OpenCloud envía
  (`Permissions-Policy`, `Cross-Origin-Opener-Policy`,
  `Cross-Origin-Resource-Policy` y `Cross-Origin-Embedder-Policy`),
  notificadas aparte como `setup.advisoryHeaders`. Un proxy inverso puede
  añadir las cuatro y la instancia sale ganando, pero su ausencia es el estado
  de serie de todo OpenCloud y no un dato sobre este despliegue, así que
  `--debug` las explica y nunca cuentan como refuerzo ausente, nunca generan
  alertas y nunca pueden cambiar un código de salida. Consulte
  [ADR 0028](../../adr/0028-headers-no-opencloud-sends-are-reported-but-never-alerted.md).
  Ensaye `Cross-Origin-Embedder-Policy: require-corp` antes de implantarla: una
  integración de ofimática que inserta Collabora o un host WOPI deja de cargar
  salvo que ese origen envíe su propia `Cross-Origin-Resource-Policy`
- si `/.well-known/security.txt` indica a quien encuentre un fallo dónde
  notificarlo, como `securityTxtPublished` en `setup.advisoryChecks`. Es el
  mismo trato que el de las cabeceras anteriores, para algo que no es una
  cabecera: OpenCloud no publica ninguno en ninguna instancia, así que se
  explica y nunca se cuenta. El archivo debe contener el campo `Contact` que
  exige la RFC 9116: un 200 por sí solo no significa nada en una instancia
  cuya interfaz responde a cualquier ruta desconocida con su propio armazón.
  Consulte
  [ADR 0034](../../adr/0034-an-advisory-observation-need-not-be-a-header.md)
- si la cabecera `Strict-Transport-Security` se aceptaría realmente para la
  precarga en navegadores, como `hstsPreloadEligible` en el mismo
  `setup.advisoryChecks`. `hstsPreload` ya indica si la cabecera *pide* la
  precarga; esta indica si la petición podría funcionar, lo que requiere a la
  vez un max-age de al menos un año, `includeSubDomains` y `preload`. El proxy
  propio de OpenCloud envía diez años y `preload`, pero no
  `includeSubDomains`, así que toda instancia estándar pide algo que la lista
  rechaza: un dato sobre OpenCloud y no sobre el despliegue, por eso se explica
  y nunca se cuenta. Deliberadamente no se mide si el dominio figura en la
  lista: las únicas formas de saberlo son preguntar a un tercero o distribuir
  decenas de megabytes de lista. Consulte
  [ADR 0037](../../adr/0037-preload-eligibility-is-measured-list-membership-is-not.md)
- `hardenings`, derivados de esas cabeceras y capacidades
- las vulnerabilidades conocidas según la
  [base de datos de avisos de seguridad](../../README.md#advisory-database) y
  la nota resultante (`0`-`5`)

Además, las comprobaciones adicionales (`extraChecks` en el JSON; se
desactivan con `--no-extra-checks`):

| Comprobación | Gravedad | Finalidad |
|:-------------|:--------------|:------------------------------------------|
| `httpsAvailable`, `tlsHandshake`, `tlsProtocol`                                                                                            | critical/high | Instancia accesible solo por HTTP, TLS roto o un protocolo anterior a TLS 1.2 |
| `tlsCertificate`, `tlsTrusted`                                                                                                             | high/medium   | Certificado caducado, que caduca dentro de `scanner.tls_min_days` o que no es de confianza |
| `tlsDeprecatedProtocol`                                                                                                                    | high          | El servidor sigue aceptando TLS 1.0 o 1.1 aunque con nosotros negoció algo más reciente |
| `tlsHostname`                                                                                                                              | high          | El certificado no cubre el nombre solicitado |
| `tlsChain`                                                                                                                                 | medium        | A la cadena le falta un intermedio, así que solo se valida en clientes que lo tengan en caché |
| `tlsCertificateLifetime`                                                                                                                   | low           | El certificado es válido durante más tiempo que el umbral de 398 días del escáner |
| `tlsCipherSuite`                                                                                                                           | medium        | El conjunto de cifrado que negoció este análisis es débil o carece de secreto perfecto hacia adelante |
| `tlsCertificatePolicy`                                                                                                                     | medium        | El certificado tiene una clave débil o una firma MD5/SHA-1 |
| `tlsAddressParity`                                                                                                                          | medium        | IPv4 e IPv6 presentan servicios TLS distintos, o uno no es accesible |
| `addressParity`                                                                                                                             | high/medium   | Con `--all-addresses`: las direcciones resueltas sirven una versión, cabeceras, refuerzo o estado de cuentas de demostración distintos, o una no responde |
| `tlsCaaRecord`                                                                                                                             | low           | Ningún registro DNS CAA restringe qué autoridades de certificación pueden emitir para este nombre |
| `tlsDnssec`                                                                                                                                | low           | La zona que responde por este nombre no está firmada, así que no se puede detectar una dirección falsificada; ausente, nunca fallida, cuando el resolvedor usado no admite DNSSEC |
| `companionAdminConsole`                                                                                                                    | high          | Un backend de colaboración publicado en este origen responde en la ruta de su consola de administración |
| `companionEditorHttps`                                                                                                                     | high          | Ese backend anuncia direcciones del editor por HTTP sin cifrar en su documento de descubrimiento WOPI |
| `cookieSecure`, `cookieHttpOnly`, `cookieSameSite`                                                                                        | high - low    | Una cookie observada carece de Secure, HttpOnly o SameSite |
| `cookiePrefix`                                                                                                                             | low           | Ninguna cookie observada usa el prefijo de nombre `__Host-`/`__Secure-`, o una declara un prefijo cuyas reglas no cumple |
| `tlsOcspStapling`                                                                                                                          | low           | No hay respuesta OCSP adjunta al handshake, aunque el certificado indica un servidor OCSP |
| `tlsCertificateTransparency`                                                                                                               | medium        | Un certificado de confianza pública no lleva marcas de tiempo de certificado firmadas incrustadas |
| `tlsEarlyData`                                                                                                                             | low           | Los tickets de sesión del servidor invitan a un envío 0-RTT de TLS 1.3, que no tiene protección contra la reproducción |
| `corsOriginRestricted`                                                                                                                     | critical/medium | Cualquier origen puede leer las respuestas de la API; crítico cuando además se permiten credenciales |
| `traceMethodDisabled`                                                                                                                      | medium        | El servidor responde a `TRACE` devolviendo la solicitud como eco |
| `forwardedHostIgnored`                                                                                                                     | medium        | Un nombre de host indicado por quien llama vuelve en el documento de descubrimiento, así que quien llama elige adónde va un inicio de sesión |
| `header:<name>`                                                                                                                            | high - low    | Una de las cabeceras anteriores falta o es demasiado débil |
| `authentication:/remote.php/dav/files/`, `/graph/v1.0/users`, `/ocs/v1.php/cloud/user`                                                     | critical/high | Un punto de acceso que debe exigir autenticación respondió igualmente |
| `exposed:/opencloud.yaml`, `/proxy/server.key`, `/idm/opencloud.boltdb`, `/.env`, `/docker-compose.yml`, `/storage/users/`, `/.git/config` | critical/high | Elementos internos del despliegue publicados por un proxy inverso mal configurado |
| `directoryListing`                                                                                                                         | critical      | Se sirve un índice de directorio en lugar de la interfaz web |
| `demoUsersDisabled`                                                                                                                        | critical      | El proveedor de identidad integrado sigue aceptando las cuentas de demostración documentadas, una de las cuales es de administrador |
| `debugEndpoint:/metrics`, `/config`, `/debug/pprof/`                                                                                       | critical/high | Manejadores de depuración accesibles en la dirección pública |
| `debugPort:<port>`                                                                                                                         | high          | Un puerto de depuración de un servicio responde desde fuera |
| `backendPortClosed`                                                                                                                        | high          | La misma instancia de OpenCloud es accesible directamente en el puerto de backend 9200, eludiendo su proxy inverso |
| `webEmbedDelegatedAuthenticationRestricted`                                                                                                | critical      | La autenticación delegada en iframe acepta mensajes sin un origen de confianza explícito |
| `webEmbedMessageOriginRestricted`                                                                                                          | high          | Los mensajes de inserción del cliente web confían en cualquier origen principal |
| `basicAuthDisabled`                                                                                                                        | medium        | El proxy sigue ofreciendo autenticación HTTP básica |
| `identityProviderDetected`                                                                                                                 | low           | No hay documento de descubrimiento de OpenID Connect ni redirección desde él, así que no se puede determinar quién inicia la sesión de los usuarios |
| `reverseProxyDetected`                                                                                                                     | low           | Nada indica que haya un proxy inverso delante de la instancia |
| `versionDisclosure:Server`, `webfingerVersionDisclosure`                                                                                   | low           | Versiones exactas reveladas a llamantes no autenticados |

Una comprobación adicional fallida limita la nota (critical -> `D`, high ->
`C`, medium -> `A`, low -> `A+`); defina `scanner.extra_checks_rating: false`
para notificarlas sin que afecten a la nota. Para el razonamiento de cada grupo
de comprobaciones anteriores, consulte [`docs/cookies.md`](../cookies.md),
[`docs/authentication.md`](../authentication.md),
[`docs/sharing.md`](../sharing.md), [`docs/exposure.md`](../exposure.md),
[`docs/embedding.md`](../embedding.md) y
[`docs/lifecycle.md`](../lifecycle.md), junto con
[`docs/csp.md`](../csp.md) y [`docs/tls.md`](../tls.md), ya mencionados.

OpenCloud es un único binario Go que sirve su interfaz web desde recursos
incrustados, y esa interfaz es una aplicación de una sola página: las rutas
desconocidas devuelven el armazón de la aplicación con HTTP 200 en lugar de un
404. Una comprobación ingenua del tipo "¿devuelve 200 `/opencloud.yaml`?"
marcaría por tanto todas las instancias sanas. El escáner sondea primero una
ruta que no puede existir, aprende cómo es la respuesta general y solo notifica
una ruta expuesta cuya respuesta difiera realmente de ella.

### Quién inicia la sesión de los usuarios {#who-signs-users-in}

El análisis también lee `/.well-known/openid-configuration` (el documento de
descubrimiento de OpenID Connect, o la redirección con la que responde la
instancia) para averiguar qué proveedor de identidad emite sus tokens. Un
emisor en otro host significa que delante de la instancia hay un proveedor
externo como Keycloak, Authentik o Authelia, y el documento de resultado lo
registra:

```json
{"identityProvider": {"detected": true, "external": true,
                      "issuer": "https://id.example.com", "vendor": "Keycloak"}}
```

Es contexto, nunca un veredicto: usar el proveedor integrado no hace fallar
nada y ninguna comprobación exige uno externo. Solo suaviza
`basicAuthDisabled`, que normalmente es `medium` y pasa a `low` cuando el
inicio de sesión interactivo pasa por un proveedor externo.

La detección del proveedor lee el documento de descubrimiento y su cabecera
`Location` sin enviar ningún inicio de sesión. La comprobación de cuentas de
demostración, descrita más abajo, es el único sondeo que envía credenciales.

Cuando no se encuentra ningún proveedor, `identityProviderDetected` falla con
gravedad `low` y `--debug` remite a la
[propia documentación de OpenCloud][opencloud-idp]; la causa habitual es un
proxy inverso que no reenvía `/.well-known/`.

### Las cuentas de demostración {#the-demo-accounts}

Cuando el documento de descubrimiento indica el proveedor *propio* de la
instancia (la gestión de identidades integrada, y no un Keycloak o Authentik
situado delante), el análisis comprueba además si los usuarios de
demostración siguen activos. `IDM_CREATE_DEMO_USERS=true` crea cinco cuentas
cuyos nombres y contraseñas aparecen en la
[documentación de OpenCloud][opencloud-demo-users], y `dennis` es
administrador. Si se deja activado en una instancia accesible, es una cuenta de
administrador cuya contraseña conoce todo el mundo, así que
`demoUsersDisabled` es un hallazgo `critical`: hace fallar la comprobación y
limita la nota a `D`.

Es el único lugar en el que el análisis envía una credencial, y lo hace porque
no hay otra forma de ver esas cuentas desde fuera: nada de lo que OpenCloud
expone sin autenticación enumera sus usuarios. Lo que se envía es un valor
predeterminado publicado y no un intento de adivinar la contraseña de nadie,
solo se prueban los pares documentados y solo se envían al proveedor propio de
la instancia: con un proveedor de identidad externo, las cuentas proceden de
él, la comprobación no se aplica y nunca se envía un inicio de sesión a un
tercero. Desactivar el ajuste no borra las cuentas que ya existen, así que en
una instancia que falla también hay que eliminarlas.

### Qué hay delante de la instancia {#what-is-in-front-of-the-instance}

`reverseProxy` registra si algo responde antes que OpenCloud: una cabecera
`Server` que menciona Nginx, Caddy, Cloudflare u otro proxy, o una cabecera
que solo añade un reenviador, como `Via`.

```json
{"reverseProxy": {"detected": true, "vendor": "Nginx", "evidence": "Server: nginx"}}
```

`reverseProxyDetected` falla cuando no se ha encontrado nada, y lo hace con
gravedad `low` únicamente: Traefik y HAProxy no anuncian nada por
defecto, y eliminar la cabecera `Server` es en sí una buena práctica, así que
un despliegue bien gestionado puede parecer desnudo desde fuera. El hallazgo
merece mostrarse, pero nunca merece restar nota.

`forwardedHostIgnored` hace la otra pregunta sobre la misma frontera: no si
hay algo delante, sino si la instancia deja que quien llama decida cuál cree
que es su propia dirección. El análisis solicita dos veces
`/.well-known/openid-configuration` con un host que no existe (una vez como
`Host` de la solicitud y otra como `X-Forwarded-Host`) y busca ese host en el
`Location` al que redirige o en el `issuer`, `authorization_endpoint`,
`token_endpoint`, `end_session_endpoint` o `jwks_uri` que publica el
documento.

```json
{"id": "forwardedHostIgnored", "severity": "medium", "passed": false,
 "detail": "A host name the caller supplied is published back: X-Forwarded-Host comes back as the issuer it publishes"}
```

Estas URL dirigen las solicitudes de autenticación. Un nombre de host
controlado por quien llama afecta en principio a la respuesta de ese llamante,
por eso el hallazgo es `medium`. Una caché compartida o un proxy que reenvía
valores `X-Forwarded-Host` no fiables pueden extender el efecto a otros
usuarios. Defina `OC_URL` y haga que el proxy aporte las cabeceras reenviadas
desde su propia configuración.

Cuando solo vuelve `Host`, como la dirección a la que redirige, revise el proxy
antes que la instancia: sin un servidor predeterminado, a un nombre para el que
el proxy no tiene sitio responde el primer sitio que cargó para ese puerto, y
una redirección construida allí con `$host` repite el host de prueba diga lo
que diga `OC_URL`. Un servidor predeterminado explícito que rechace los nombres
desconocidos lo resuelve; consulte
[Ningún servidor predeterminado](../reverse-proxy.md#mistakes-that-cost-a-grade).

Solo cuenta una URL a la que se *enviaría* a un cliente. Un host virtual
predeterminado que rechaza un nombre no reconocido suele mostrar ese nombre en
su página de error, y buscarlo en el cuerpo haría que el comportamiento
correcto se notificara como hallazgo. Una instancia que no publica ningún
documento de descubrimiento tampoco se evalúa en ningún sentido: con dos errores,
el análisis no tiene nada que evaluar.

### Servicios alternativos (HTTP/3) {#alternative-services-http3}

`alternativeServices` registra lo que la instancia anuncia en su cabecera
`Alt-Svc`. Una entrada `h3` indica a cada navegador que intente HTTP/3 sobre
**UDP** en el puerto indicado: un servicio que un cortafuegos escrito para TCP
443 puede no cubrir, y que un proxy inverso puede activar sin que nadie lo
decida.

```json
{"alternativeServices": {"advertised": true, "http3": true,
  "entries": [{"protocol": "h3", "host": "", "port": 443, "udp": true}],
  "header": "h3=\":443\"; ma=86400"}}
```

Es una observación y nunca se califica: HTTP/3 no es una debilidad, solo algo
que el cortafuegos debe tener en cuenta. El plugin muestra una línea
de detalle cuando lo ve. La dirección anunciada nunca se sondea: es la palabra
del objetivo, no un origen al que se apuntó el escaneo
([ADR 0036](../../adr/0036-a-companion-service-is-probed-only-where-the-scan-was-pointed.md)).
`Alt-Svc: clear` no registra nada como anunciado y, sin respuesta, la clave es
`null`.

### Inicios de sesión fallidos (opcional) {#failed-sign-ins-opt-in}

Con `--login-throttling` (`COS_LOGIN_THROTTLING` o
`scanner.check_login_throttling`) el escaneo envía seis inicios de sesión
fallidos seguidos para una cuenta aleatoria que no puede existir y registra si
la instancia los frenó: un HTTP `429` o una cabecera `Retry-After`:

```json
{"loginThrottling": {"tested": true, "attempts": 4, "throttled": true,
  "evidence": "HTTP 429, Retry-After: 30", "statuses": [401, 401, 401, 429]}}
```

Está desactivado por defecto, solo pregunta al proveedor de identidad
integrado, se ejecuta después de todas las demás pruebas para que un `429` no
oculte las cuentas de demostración y nunca se califica: muchas instalaciones
limitan en una ventana más larga o en una capa que una ráfaga corta no
alcanza, así que "sin límite" es un motivo para revisar, no un veredicto. El
servicio web público nunca lo envía
([ADR 0069](../../adr/0069-login-throttling-is-observed-only-when-the-operator-asks.md)).
Sin la opción, la clave es `null`.

### Integraciones de ofimática y calendario {#office-and-calendar-integrations}

Hay dos integraciones visibles sin iniciar sesión, y ambas se notifican como
observaciones y no como veredictos:

- `/app/list` no está protegida por la política del proxy propio de OpenCloud
  e indica los proveedores de aplicaciones realmente registrados en el
  registro de aplicaciones: Collabora, OnlyOffice y similares. El bloque
  `app_providers` del documento de capacidades está fijado en el código y no
  dice nada, así que no se usa.
- `/.well-known/caldav` responde con una redirección o una solicitud de
  autenticación solo cuando hay algo conectado a él; así aparece un Radicale
  detrás del proxy. Una instancia estándar responde 404.

```json
{"integrations": {"office": {"detected": true, "apps": ["Collabora"], "groupware": false},
                  "calendar": {"detected": true, "advertised": true}}}
```

Ninguna de las dos se convierte en una comprobación ni puede cambiar la nota.

Lo que *publica* el despliegue es otra cuestión, y esa sí se convierte en una
comprobación. Cuando un proxy inverso sirve el backend de colaboración en el
propio origen de la instancia, `/hosting/discovery` responde con el documento
que especifica el protocolo WOPI, y de él se derivan dos hallazgos: si la
consola de administración del editor es accesible (`companionAdminConsole`) y
si las direcciones del editor que anuncia usan HTTPS
(`companionEditorHttps`).

El escáner solo sondea el origen enviado. No sigue un nombre de host del
editor indicado en el documento de descubrimiento, porque eso permitiría que el
destino eligiera otro destino de conexión. Por tanto, un editor alojado aparte
no recibe ningún hallazgo de estas comprobaciones. Evalúe ese servicio con
herramientas adecuadas para el editor; consulte
[ADR 0036](../../adr/0036-a-companion-service-is-probed-only-where-the-scan-was-pointed.md).

### Lo que el análisis no responde deliberadamente {#what-the-scan-deliberately-does-not-answer}

- **El registro de auditoría.** El servicio de auditoría de OpenCloud solo
  consume el bus de eventos interno. No publica ningún punto de acceso y
  ningún documento público lo menciona, así que desde fuera no se puede saber
  si está activado. **No se comprueba**, y un informe limpio no dice nada
  sobre él.
- **Si una integración está configurada *correctamente*.** El análisis
  notifica que hay un proveedor de aplicaciones registrado o que algo responde
  en la ruta CalDAV. Los secretos WOPI, los permisos de uso compartido y la
  configuración propia del otro servicio están detrás de un inicio de sesión y
  no se comprueban.
- **Todo lo que requiere credenciales.** Nunca se envía un formulario de
  inicio de sesión ni se intenta adivinar una contraseña. La única excepción
  son las cuentas de demostración descritas arriba: las contraseñas que publica
  OpenCloud se envían, tal como se publican, al proveedor de identidad propio
  de la instancia, porque es la única forma de ver desde fuera si esas cuentas
  siguen existiendo.
- **Su cortafuegos, la política de su proveedor de identidad, sus copias de
  seguridad.** Todo eso importa más que varias de las cosas anteriores, y nada
  de ello es visible por HTTP.

[Ejecutar OpenCloud en una infraestructura segura](../secure-deployment.md)
trata estas comprobaciones operativas por separado: políticas del proveedor de
identidad, registro de auditoría, reglas de cortafuegos, orientación a los
usuarios y monitorización programada.

[opencloud-idp]: https://docs.opencloud.eu/docs/admin/configuration/authentication-and-user-management/external-idp
[opencloud-demo-users]: https://docs.opencloud.eu/docs/admin/resources/demo-user/

## Leer la versión correctamente {#reading-the-version-correctly}

`/status.php` notifica tres campos de versión, y dos de ellos son trampas:

```json
{"version":"0.1.0.0","versionstring":"0.1.0","productversion":"7.4.0"}
```

`version` y `versionstring` son valores de compatibilidad. La versión real es
`productversion`. El escáner prefiere ese campo, recurre a las capacidades si
falta y define `legacyVersion: true` si solo dispone de un marcador. Compruebe
también qué campo leen sus propios scripts de monitorización.

## Puertos de depuración {#debug-ports}

Cada servicio de OpenCloud tiene un servicio de depuración que sirve
`/healthz`, `/readyz`, `/metrics`, `/config` y `/debug/pprof`. `/metrics`
incluye `opencloud_proxy_build_info` (la versión exacta), `/config` vuelca la
configuración efectiva del servicio y `/debug/pprof` permite a cualquiera
lanzar un perfilado.

Estos servicios escuchan por defecto en loopback, así que un puerto de
depuración que responde desde su host de monitorización es un hallazgo real,
normalmente un contenedor que publicó todo el rango de puertos. El escáner
sondea los cinco más reveladores:

| Puerto | Servicio |
|:-----|:---------|
| 9205 | proxy    |
| 9141 | frontend |
| 9124 | graph    |
| 9134 | idp      |
| 9239 | idm      |

Cada sondeo es una única conexión TCP con un tiempo de espera de tres
segundos, así que un host protegido por cortafuegos cuesta hasta 15 segundos.
Desactive los sondeos con `--no-debug-ports`, ejecútelos en paralelo con
[`--concurrency`](#speeding-the-scan-up) o ajústelos:

```yaml
scanner:
  check_debug_ports: true
  debug_ports: [9205, 9141]
  debug_port_timeout: 1
```

### Acelerar el análisis {#speeding-the-scan-up}

Un análisis pasa casi todo su tiempo esperando a que responda la instancia:
unas veinte solicitudes HTTP y cinco conexiones TCP, una tras otra.
`scanner.concurrency` ejecuta esos sondeos en paralelo en el análisis de un
solo host; aumentarlo acorta mucho una ejecución a cambio de una ráfaga de
solicitudes en paralelo contra la instancia, y se nota sobre todo cuando el
sondeo de puertos de depuración choca con un cortafuegos que se traga las
conexiones. `--concurrency`, en cambio, controla el límite exterior de
trabajadores de host descrito en
[Comprobar varios hosts](../../README.md#checking-multiple-hosts).

El ajuste solo cambia los tiempos, nunca el veredicto: el documento de
resultado enumera los mismos hallazgos en el mismo orden sea cual sea el
valor. Los valores superiores a `32` se limitan. También se puede definir una
vez para todos los hosts:

```yaml
scanner:
  concurrency: 8
```

## Todas las direcciones resueltas {#every-resolved-address}

Un análisis marca el nombre una vez y ve la dirección que el resolvedor puso
primero. Para un nombre detrás de un grupo de nodos, eso es un solo nodo, y el
nodo al que no llegó una actualización de configuración (sin HSTS, con cuentas
de demostración que siguen iniciando sesión, con una versión más antigua) es
invisible. [`tlsAddressParity`](../tls.md) solo compara la identidad TLS de una
dirección IPv4 y una IPv6, que varios nodos detrás de un mismo certificado
comparten sirvan lo que sirvan.

`--all-addresses` (`COS_ALL_ADDRESSES`, `scanner.check_all_addresses`) repite
contra cada dirección resuelta, una tras otra, la parte del análisis que
cambia una actualización de configuración:

- la versión de `/status.php` (o del documento de capacidades),
- las cabeceras de seguridad calificadas, comparadas por veredicto y no por
  valor, para que un nonce de CSP no cuente como diferencia,
- las medidas de refuerzo leídas de la página raíz, las capacidades, la
  solicitud de autenticación y el proveedor de identidad,
- si una cuenta de demostración documentada puede iniciar sesión.

Lo que comparten los nodos (cadena de certificados, CAA, DNSSEC, puertos de
depuración) no se vuelve a preguntar. Cada solicitud mantiene el nombre de host
en `Host` y en SNI; solo cambia la dirección a la que va la conexión, y las
direcciones son la respuesta del resolvedor para ese nombre, nunca algo que
haya dicho la instancia. Las direcciones IPv6 se omiten cuando
`scanner.ipv6_enabled` está desactivado.

El resultado es `addressParity`, con la primera dirección como referencia:

| Diferencia en otra dirección                   | Gravedad                                  |
|:-----------------------------------------------|:------------------------------------------|
| Una cuenta de demostración inicia sesión donde antes no | la misma que `demoUsersDisabled` por sí sola |
| Una versión distinta                           | high                                      |
| Una cabecera o medida de refuerzo se supera/falla | medium                                 |
| La dirección se resuelve, pero no responde     | medium                                    |

Las cabeceras y comprobaciones excluidas no se comparan. Un nombre con una sola
dirección no recibe ningún hallazgo (una ausencia, no un aprobado) ni
solicitudes adicionales. Lo que sirvió cada dirección figura en el documento de
resultado como `addressObservations`.

Está desactivado por defecto: alrededor de una docena de solicitudes por
dirección, entre ellas un inicio de sesión de demostración. Ve lo que ve el
DNS: los nodos detrás de una única dirección de balanceador de carga, un
resolvedor que devuelve un subconjunto rotatorio o un GeoDNS que responde según
la ubicación del host de monitorización limitan lo que se puede comparar. El
servicio web público nunca lo ejecuta
([ADR 0042](../../adr/0042-every-resolved-address-is-compared-only-when-the-operator-asks.md)).
