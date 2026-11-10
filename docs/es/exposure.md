# Comprobaciones de rutas expuestas y puntos de acceso de depuración

OpenCloud no publica normalmente por HTTP índices de directorios, archivos de
despliegue, claves privadas ni su base de datos de identidades. Estas
comprobaciones buscan un servidor web o proxy inverso que exponga esos
archivos, así como interfaces de depuración que deberían permanecer privadas.

Antes de ejecutar ninguna de ellas, el análisis solicita una ruta que no puede
existir y recuerda lo que recibe. La interfaz web de OpenCloud es una
aplicación de una sola página, y las rutas desconocidas devuelven el armazón de
la aplicación con HTTP `200` en lugar de un `404`: una comprobación ingenua del
tipo "¿devuelve esta ruta `200`?" marcaría todas las instancias sanas. En todas
las comprobaciones siguientes, solo cuenta como acierto una respuesta que
difiera realmente de esa línea base general.

<!-- TOC -->
* [Rutas expuestas y puntos de acceso de depuración: qué comprueba este escáner y por qué](#exposed-paths-and-debug-endpoints-what-this-scanner-checks-and-why)
  * [1. ¿Se está sirviendo un índice de directorio?: `directoryListing`](#1-is-a-directory-index-being-served-directorylisting)
  * [2. ¿Se puede leer un archivo de despliegue concreto?: `exposed:<path>`](#2-is-a-specific-deployment-file-readable-exposedpath)
  * [3. ¿Es público un punto de acceso de depuración?: `debugEndpoint:<path>`](#3-is-a-debug-endpoint-publicly-readable-debugendpointpath)
  * [4. ¿Es accesible un puerto de depuración de un servicio?: `debugPort:<port>`](#4-is-a-service-debug-port-reachable-debugportport)
  * [5. ¿Se puede llegar directamente al backend, eludiendo el proxy?: `backendPortClosed`](#5-is-the-backend-reachable-directly-bypassing-the-proxy-backendportclosed)
  * [6. ¿Quién puede leer una respuesta desde otro origen?: `corsOriginRestricted`](#6-who-may-read-a-response-cross-origin-corsoriginrestricted)
  * [7. ¿Se devuelve la solicitud como eco?: `traceMethodDisabled`](#7-is-the-request-echoed-back-tracemethoddisabled)
  * [8. ¿Se publica junto a la instancia la consola de un segundo servicio?: `companionAdminConsole`](#8-is-a-second-services-console-published-beside-the-instance-companionadminconsole)
  * [Gravedad y efecto en la nota](#severity-and-rating-impact)
<!-- TOC -->


## 1. ¿Se está sirviendo un índice de directorio?: `directoryListing` {#1-is-a-directory-index-being-served-directorylisting}

Se ha devuelto una página del tipo `Index of /`. OpenCloud nunca genera una,
así que solo puede proceder de un servidor web simple que apunta directamente
al directorio de despliegue; es la misma configuración errónea que, si pasa
desapercibida, también sirve todo lo que la siguiente comprobación busca por
nombre.

**Corrección:** deje de servir el directorio de despliegue como archivos
estáticos. Configure el servidor web como proxy inverso hacia la dirección
propia de OpenCloud en lugar de hacia una ruta del sistema de archivos, y
desactive explícitamente los índices de directorio (Nginx `autoindex off`,
Apache `Options -Indexes`) como segunda capa; consulte
[Proxies inversos](../reverse-proxy.md).

## 2. ¿Se puede leer un archivo de despliegue concreto?: `exposed:<path>` {#2-is-a-specific-deployment-file-readable-exposedpath}

Se solicita por su nombre una lista fija de rutas que nunca deben responder por
HTTP:

| Ruta                                  | Gravedad |
|:---------------------------------------|:---------|
| `/opencloud.yaml`                      | critical |
| `/config/opencloud.yaml`               | critical |
| `/.opencloud/config/opencloud.yaml`    | critical |
| `/proxy/server.key`                    | critical |
| `/idm/opencloud.boltdb`                | critical |
| `/.env`                                 | critical |
| `/docker-compose.yml`                  | high     |
| `/storage/users/`                       | high     |
| `/.git/config`                          | high     |

Son configuración, material de claves y una base de datos, más o menos en el
orden de lo que entrega su lectura: `opencloud.yaml` y `.env` contienen
secretos y ajustes, `proxy/server.key` es material de clave privada TLS e
`idm/opencloud.boltdb` es el almacén de identidades. Un acierto en cualquiera
de ellas significa que el directorio de despliegue (o una copia git de él) es
accesible, exactamente igual que con `directoryListing`.

**Corrección:** deje de servir el directorio de despliegue (haga de proxy hacia
la dirección propia de OpenCloud en lugar de exponer el sistema de archivos
desde el que se ejecuta) y confirme después que cada ruta notificada responde
`404`. Trate todo lo que *fue* legible como divulgado: rote la clave TLS y
cualquier credencial de `opencloud.yaml` o `.env`, y revise en el almacén de
identidades las cuentas creadas mientras estuvo expuesto.

## 3. ¿Es público un punto de acceso de depuración?: `debugEndpoint:<path>` {#3-is-a-debug-endpoint-publicly-readable-debugendpointpath}

Se comprueban `/metrics`, `/config` y `/debug/pprof/` en la dirección pública.
Pertenecen al servicio de depuración de OpenCloud que solo escucha en
loopback, nunca detrás de un proxy inverso: `/metrics` y `/config` entregan a
un tercero la configuración en ejecución y el estado interno, y
`/debug/pprof/`, cuando está activado, permite ordenar al proceso que se
perfile a sí mismo, lo que es a la vez una fuga de información y una forma de
hacerle realizar trabajo costoso a demanda.

**Corrección:** no reenvíe las rutas `/debug` a la dirección pública y deje
los servicios de depuración escuchando en `127.0.0.1`, como están por defecto
(`OC_DEBUG_ADDR` y las variables `*_DEBUG_ADDR` de cada servicio). Si un
recolector de métricas los necesita realmente, acceda a ellos por la red
interna en lugar de enrutarlos por la misma dirección que usa internet.

## 4. ¿Es accesible un puerto de depuración de un servicio?: `debugPort:<port>` {#4-is-a-service-debug-port-reachable-debugportport}

Además de las rutas HTTP anteriores, cada servicio de OpenCloud escucha
también en su propio **puerto** de depuración, vinculado por defecto a
`127.0.0.1`. Esta comprobación se conecta directamente a los puertos
predeterminados (o a los configurados en `scanner.debug_ports`); poder llegar a
uno significa que se ha publicado, casi siempre mediante un mapeo de puertos
del contenedor y no mediante un ajuste deliberado de OpenCloud.

**Corrección:** elimine el mapeo de puertos que lo publica y deje los
servicios de depuración en `127.0.0.1`. Como con los puntos de acceso de
depuración HTTP, acceda a ellos por la red interna si algo los necesita.

## 5. ¿Se puede llegar directamente al backend, eludiendo el proxy?: `backendPortClosed` {#5-is-the-backend-reachable-directly-bypassing-the-proxy-backendportclosed}

El puerto `9200` sirve la misma instancia de OpenCloud que la dirección
pública, pero sin lo que añada el proxy inverso situado delante. Cuando un
proxy está delante de OpenCloud (para terminar TLS, añadir cabeceras de
seguridad, limitar la frecuencia o las tres cosas), un cliente que llega
directamente a `9200` no obtiene nada de eso: ni política TLS, ni refuerzo de
cabeceras, ni ninguna de las comprobaciones que el resto de este escáner
notifica como superadas se aplica realmente a una solicitud que llega por esta
vía.

**Corrección:** elimine el mapeo de puerto público de `9200` y vincule el
backend a loopback o a la red privada del contenedor, para que solo el proxy
inverso pueda llegar a él.

## 6. ¿Quién puede leer una respuesta desde otro origen?: `corsOriginRestricted` {#6-who-may-read-a-response-cross-origin-corsoriginrestricted}

Las demás comprobaciones de esta página preguntan si algo es accesible. Esta
pregunta quién puede *leer la respuesta* una vez que lo es, que es otra
cuestión y, en una instancia estándar, la más alarmante.

La política del mismo origen del navegador es lo que normalmente impide que
una página de `attacker.example` lea una respuesta enviada por su OpenCloud.
Cross-Origin Resource Sharing es la forma en que un servidor desactiva esa
protección para orígenes concretos. OpenCloud viene con ella desactivada para
*todos*:
[`OC_CORS_ALLOW_ORIGINS` vale por defecto `*` y `OC_CORS_ALLOW_CREDENTIALS`
vale `true`](https://docs.opencloud.eu/docs/dev/server/services/graph/environment-variables),
y un middleware con ambos valores suele devolver el `Origin` que se le haya
enviado en lugar del literal `*`, que es la combinación que los
navegadores rechazan cuando se declara abiertamente.

El análisis envía una solicitud a `/graph/v1.0/me` con un `Origin` que no
puede pertenecer a nadie
(`https://cors-probe.check-opencloud-security.invalid`; `.invalid` está
reservado por la RFC 2606 y no se resuelve a ningún sitio) y lee la respuesta:

| Lo que responde la instancia | Veredicto |
|:--------------------------|:--------|
| Devuelve el origen de prueba, **con** `Access-Control-Allow-Credentials: true` | **critical**: cualquier sitio puede hacer que el navegador de un visitante adjunte su sesión de OpenCloud y le entregue la respuesta |
| `Access-Control-Allow-Origin: null`, con credenciales | **critical**: `null` es lo que envía un iframe en sandbox, y cualquier página puede meterse en uno |
| Devuelve el origen de prueba, sin credenciales | **medium**: expone lo que un llamante no autenticado ya podía obtener |
| Un `*` literal, con o sin credenciales | **medium**: los navegadores rechazan la combinación con credenciales, así que la solicitud falla en lugar de tener éxito de forma peligrosa |
| Otro origen concreto | **superada**: es la configuración que pide la comprobación |
| Ningún `Access-Control-Allow-Origin` | **superada** |

**Corrección:** defina `OC_CORS_ALLOW_ORIGINS` con los orígenes exactos que
deben llegar a la API (el origen propio de la interfaz web, más cualquier
aplicación de ofimática o cliente alojada deliberadamente en otro lugar) y
defina `OC_CORS_ALLOW_CREDENTIALS=false` salvo que alguno necesite realmente
enviar la sesión. Las formas por servicio (`GRAPH_CORS_ALLOW_ORIGINS`,
`OCS_CORS_ALLOW_ORIGINS`, etc.) sustituyen al nombre compartido cuando un
servicio necesita una lista más amplia.

## 7. ¿Se devuelve la solicitud como eco?: `traceMethodDisabled` {#7-is-the-request-echoed-back-tracemethoddisabled}

`TRACE` pide al servidor que devuelva la solicitud como cuerpo de la
respuesta, cabeceras incluidas. Todo lo que el navegador haya añadido por el
camino (la cookie de sesión, una cabecera `Authorization`, una cabecera
añadida por el proxy inverso) llega entonces como texto normal, legible por un
script que nunca habría podido leer esas cabeceras directamente.

OpenCloud no implementa `TRACE`, así que una instancia que lo responde tiene
delante un proxy inverso o un servidor de aplicaciones que sí lo hace. Como en
todas las comprobaciones de esta página, un `200` por sí solo no demuestra
nada en una aplicación de una sola página: la respuesta solo cuenta como eco
cuando el cuerpo se parece realmente a la solicitud enviada
(`Content-Type: message/http`, o la línea de solicitud repetida).

Sondearlo no cuesta nada en el sentido que importa: la RFC 9110 define `TRACE`
como un método seguro (devuelve un eco y no cambia nada), por eso un
complemento que puede ejecutarse cada minuto puede preguntarlo.

**Corrección:** rechace `TRACE` en lo que esté delante de la instancia. Apache
necesita `TraceEnable off`; nginx ya devuelve `405` salvo que se haya escrito
una location que reenvíe todos los métodos; Traefik y Caddy necesitan una regla
que limite los métodos reenviados.

## 8. ¿Se publica junto a la instancia la consola de un segundo servicio?: `companionAdminConsole` {#8-is-a-second-services-console-published-beside-the-instance-companionadminconsole}

Un editor de documentos compatible con WOPI (Collabora Online, OnlyOffice) es el
segundo servicio habitual en un despliegue de OpenCloud, y un proxy inverso que
reenvía `/hosting` y `/browser` hacia él publica ese editor en el propio origen
de la instancia. Es un segundo servidor HTTP, y su consola de administración
enumera todas las sesiones de documentos abiertas y sus usuarios, muestra la
configuración del propio servidor y puede terminar sesiones. La protege una
única contraseña compartida sin ninguna limitación de frecuencia delante.

El análisis detecta el backend solicitando `/hosting/discovery` y exigiendo el
elemento raíz `wopi-discovery` que especifica el protocolo WOPI; un código de
estado por sí solo encontraría un editor en todas las instancias, ya que
OpenCloud responde a las rutas desconocidas con su propio armazón HTML. Solo
después de que ese documento haya respondido se solicita la ruta de la
consola, y solo entonces se puede notificar el hallazgo. Un segundo hallazgo,
`companionEditorHttps`, lee las direcciones del editor que anuncia ese
documento: una dirección `http://` significa que el documento y el token que
autoriza la sesión viajan sin cifrar, y un navegador en una página HTTPS
bloquea directamente el marco.

**Si en este origen no hay ningún backend publicado, ninguno de los dos
hallazgos aparece**, ni siquiera como superado. La mayoría de los despliegues
sirven el editor desde un host propio, y el análisis no sigue deliberadamente
el host indicado en el documento de descubrimiento, porque eso permitiría que
una instancia analizada eligiera la siguiente dirección a la que se conecta el
escáner. Lance un segundo análisis contra ese host. Consulte
[ADR 0036](../../adr/0036-a-companion-service-is-probed-only-where-the-scan-was-pointed.md).

**Corrección:** bloquee la ruta de la consola en el proxy inverso que publica
el backend, para que solo lleguen a internet las rutas propias del editor.
Definir una contraseña para la consola es la opción más débil de las dos,
porque esa única credencial protege todas las sesiones de documentos del
servidor.

## Gravedad y efecto en la nota {#severity-and-rating-impact}

Todas las comprobaciones de este grupo son entradas de `extraChecks`, que se
notifican y limitan la nota siempre que se ejecuta el análisis: los hallazgos
críticos limitan la nota a `D` y los altos a `C`; consulte la tabla de
comprobaciones adicionales en
[la guía de comprobaciones](../scanner-checks.md#what-the-scanner-checks).
Ninguna es un indicador de refuerzo y ninguna requiere `--check-hardening`: un
archivo de configuración expuesto o un puerto de depuración abierto es un
hallazgo que se notifica en cada análisis.
