# Redis detrás del servicio web del escáner de seguridad de OpenCloud

Redis guarda la cola del servicio web, los resultados temporales de los
análisis, los datos de referencia y el estado operativo compartido. Esta guía
trata la autenticación, el acceso de red, la retención, los límites de memoria
y la recuperación ante fallos de conexión.

Se aplica a la **aplicación web** de [`webapp/`](../../webapp/README.md). El
complemento de línea de comandos no usa Redis en absoluto:
`check-opencloud-security` se comunica con una instancia de OpenCloud, imprime
una línea y termina.

Las pilas incluidas usan **Valkey** (`valkey/valkey:9.1-alpine`), la
continuación con licencia BSD de Redis. El protocolo es el mismo: el servicio
sigue llamándose `redis` y `COS_WEB_REDIS_URL` conserva el esquema `redis://`.
Si activó la persistencia con el asistente, vacíe una vez el directorio o el
volumen de datos antes del primer arranque de Valkey, que rechaza un archivo de
datos escrito por Redis 8.

> **¿Solo quiere eliminar la advertencia?** Defina `COS_REDIS_PASSWORD` en
> `docker/.env` y ejecute `docker compose up -d`. El resto de esta página
> explica qué cambia con eso y qué más conviene hacer.

## Índice {#table-of-contents}

<!-- TOC -->
* [Para qué se usa Redis](#what-redis-is-used-for)
* [Qué se guarda y durante cuánto tiempo](#what-is-stored-and-for-how-long)
* [Configurar la conexión](#configuring-the-connection)
* [Ejecutar sin Redis](#running-without-redis)
* [La contraseña](#the-password)
* [Aislamiento de red](#network-isolation)
* [Persistencia, o su ausencia deliberada](#persistence-or-the-deliberate-lack-of-it)
* [Memoria y desalojo](#memory-and-eviction)
* [Un Redis externo o gestionado](#an-external-or-managed-redis)
* [Kubernetes](#kubernetes)
* [Estado y monitorización](#health-and-monitoring)
* [Solución de problemas](#troubleshooting)
* [Marcas e independencia](#trademarks-and-affiliation)
<!-- TOC -->

## Para qué se usa Redis {#what-redis-is-used-for}

Tres tareas, y nada más:

1. **La cola.** Un envío se acepta, recibe un uuid y se añade a una lista. El
   worker de ARQ lo saca de ella. Esto es lo que hace que un servicio
   sobrecargado ponga en cola en lugar de rechazar: el envío que llega después
   del último worker libre espera su turno y se le indica su posición.
2. **El estado propio del análisis.** Su estado, el documento de resultado
   cuando existe y lo que se pidió. La aplicación web los lee para responder a
   `GET /api/scans/{uuid}`; nunca ejecuta ella misma un análisis.
3. **Datos de referencia y contadores compartidos.** El calendario de
   versiones y la base de datos de avisos de seguridad que el worker vuelve a
   leer una vez al día, el latido del worker y los contadores del límite de
   frecuencia.

La mayor parte del estado de Redis se puede recrear, pero vaciarlo descarta el
trabajo en cola, los resultados legibles, el estado del límite de frecuencia y
las exclusiones añadidas desde el área de operación. Guarde en
`COS_WEB_BLOCKED_TARGETS` las exclusiones que deban sobrevivir a un reinicio.
Los datos de análisis caducan automáticamente; no dé por hecho que todas las
claves operativas tienen la misma vida útil.

## Qué se guarda y durante cuánto tiempo {#what-is-stored-and-for-how-long}

| Clave | Qué contiene | Vida útil |
|:----|:--------------|:---------|
| `scan:{uuid}:status` | `queued`, `running`, `completed` o `failed` | `COS_WEB_RESULT_TTL` (predeterminado 3600 s) |
| `scan:{uuid}:result` | El documento de resultado que produjo el escáner | `COS_WEB_RESULT_TTL` |
| `scan:{uuid}:metadata` | La dirección enviada, las exclusiones, el canal de publicación, las marcas de tiempo | `COS_WEB_RESULT_TTL` |
| `cos:web:queue` | La lista FIFO de uuid que esperan a un worker | El TTL de los resultados, como mínimo una hora |
| `cos:web:worker:heartbeat` | Que hay un worker vivo, para `/healthz` | La renueva el worker |
| `cos:web:rl:client:{fingerprint}` | El número de solicitudes por cliente | `COS_WEB_IP_RATE_WINDOW` |
| `cos:web:rl:target:{fingerprint}` | El tiempo de espera por destino | `COS_WEB_TARGET_COOLDOWN` |
| `scan:{uuid}:prober` | La huella del cliente al que se imputa el resultado de un análisis, hasta que un worker lo inicia | Como máximo `COS_WEB_RESULT_TTL` |
| `cos:web:rl:probe:{fingerprint}` | Penalizaciones contra una red cliente | `COS_WEB_PROBE_WINDOW` |
| `cos:web:rl:blocked:{fingerprint}` | Una red cliente bloqueada por sondeo | `COS_WEB_PROBE_BLOCK`, creciendo hasta `COS_WEB_PROBE_BLOCK_MAX` |
| `cos:web:rl:blocks:{fingerprint}` | Cuántos bloqueos ha acumulado recientemente una red, para el escalado | El último bloqueo más `COS_WEB_PROBE_REPEAT_WINDOW` |
| `cos:web:rl:daily:{fingerprint}` | El recuento diario por cliente | Un día |
| `cos:web:stats:{blocks,strikes,daily}:{YYYYMMDD}` | Recuentos para el área de operación: bloqueos iniciados, penalizaciones, límites diarios alcanzados. Un número por día, nada más | Ocho días |
| `cos:web:schedule:document`, `cos:web:schedule:checked` | El ciclo de vida de versiones, releído una vez al día | Hasta la siguiente actualización |
| `cos:web:advisories:document`, `cos:web:advisories:checked` | La base de datos de avisos de seguridad, releída una vez al día | Hasta la siguiente actualización |

De esa tabla se derivan dos cosas, y ambas importan más de lo que parece.

**Un uuid es toda la autorización.** Cada análisis tiene su propio espacio de
nombres `scan:{uuid}:*` y nada los enumera. Los uuid desconocidos, no válidos y
caducados responden todos con el mismo 404, así que un resultado caducado no se
distingue de uno que nunca existió. No hay ningún punto de acceso que enumere
los análisis, y añadir uno convertiría cada resultado en un documento público.

**Las claves del límite de frecuencia contienen huellas en lugar de
direcciones de clientes.** Usan `COS_WEB_RATE_LIMIT_SALT`; los registros de
auditoría usan la sal independiente `COS_WEB_AUDIT_SALT`. Configure una sal de
límite de frecuencia compartida cuando ejecute varios procesos web. Consulte
[registro](../webapp.md#what-gets-logged).

Por tanto, mientras dure un TTL, Redis es una copia de las direcciones que ha
enviado la gente y de los hallazgos de seguridad de cada una. Ese es el motivo
de las dos secciones siguientes.

## Configurar la conexión {#configuring-the-connection}

Un solo ajuste, `COS_WEB_REDIS_URL`, y lo leen ambos procesos: la aplicación
web lo abre directamente y el worker entrega la misma URL a ARQ. Una contraseña
o un esquema TLS en la URL configuran, por tanto, toda la pila.

| Forma | Cuándo |
|:-----|:-----|
| `redis://redis:6379/0` | El contenedor de al lado, sin contraseña |
| `redis://:PASSWORD@redis:6379/0` | Con `requirepass` definido. El nombre de usuario está vacío, de ahí los dos puntos solos |
| `redis://user:PASSWORD@host:6379/0` | Usuario ACL de Redis 6+ |
| `rediss://user:PASSWORD@host:6380/0` | Lo mismo por TLS. Dos `s`, y es el esquema lo que activa el cifrado |
| `memory://` | Sin Redis; consulte más abajo |

Codifique con porcentajes una contraseña que contenga `@`, `:`, `/` o `#`, o se
interpretará como parte del host. Las contraseñas que generan
[`docker/setup-wizard.py`](../../docker/setup-wizard.py) y
[`docker/authentik-env.sh`](../../docker/authentik-env.sh) solo usan caracteres
seguros en una URL, por eso se generan en lugar de pedirse.

## Ejecutar sin Redis {#running-without-redis}

`COS_WEB_REDIS_URL=memory://` selecciona un sustituto dentro del proceso: la
misma interfaz, respaldada por un diccionario en el proceso web. Existe con dos
fines.

- **El conjunto de pruebas.** Ninguna prueba necesita un servidor Redis, por
  eso lo define `tests/webapp_support.py`.
- **Echar un vistazo.** Un proceso, un comando, sin infraestructura.

No es una opción de despliegue. No hay ningún worker al que encolar, el estado
desaparece con el proceso y un segundo proceso no vería los análisis del
primero. Todo lo que dé servicio a alguien más que a usted necesita un Redis
real.

## La contraseña {#the-password}

Redis responde a quien llegue a él. De serie no tiene contraseña, y eso es lo
que notifica un análisis de seguridad del host:

```
WARNING: Redis does not require authentication and is not protected by
network restriction
```

El hallazgo es justo. "En esta red solo están nuestros contenedores" es una
suposición sobre todo lo que se ejecute alguna vez en ese host, no un control,
y lo que hay detrás de esa suposición son todos los análisis en curso y todos
los resultados que siguen dentro de su TTL.

Defina una:

```bash
cd docker
printf 'COS_REDIS_PASSWORD=%s\n' "$(openssl rand -base64 36 | tr -d '/+=')" >> .env
chmod 600 .env
docker compose up -d
```

Los archivos compose leen `${COS_REDIS_PASSWORD:-}` en dos lugares: Redis la
recibe como `--requirepass`, y ambos contenedores de la aplicación la reciben
en `COS_WEB_REDIS_URL`. Si deja la variable sin definir, la pila se comporta
exactamente igual que antes, así que es seguro actualizar sin editar nada; pero
no la deje sin definir en nada que no sea un portátil.

Dos comandos lo hacen por usted:

- [`docker/setup-wizard.py`](../../docker/setup-wizard.py) genera una para cada
  despliegue que escribe, en un `.env` creado con `0600`. El archivo compose que
  escribe hace referencia al nombre y nunca contiene el valor, así que se puede
  seguir confirmando en el repositorio.
- [`docker/authentik-env.sh`](../../docker/authentik-env.sh) escribe una junto a
  los secretos de Authentik, y no toca un valor existente.

Compruebe que se ha aplicado:

```bash
docker compose exec -e VALKEYCLI_AUTH= redis valkey-cli ping
# NOAUTH Authentication required.        <- what you want to see
docker compose exec redis valkey-cli ping
# PONG                                   <- authenticated, via VALKEYCLI_AUTH
```

La comprobación de estado dentro del contenedor lee `VALKEYCLI_AUTH` del entorno
en lugar de recibir `-a` en la línea de comandos, así que la contraseña no
aparece en la lista de procesos del propio contenedor.

Cambiar la contraseña más adelante requiere reiniciar los tres servicios a la
vez, no de forma escalonada: los contenedores de la aplicación leen la URL al
arrancar.

## Aislamiento de red {#network-isolation}

La contraseña es la mitad de la respuesta a esa advertencia. La otra mitad es
que Redis no tiene ningún motivo para ser accesible.

En los archivos compose incluidos, Redis no publica ningún puerto y está solo
en una red marcada como `internal: true`:

```yaml
networks:
  scanner_internal:
    internal: true
```

`internal` significa que Docker no da a esa red ninguna puerta de enlace, así
que nada en ella puede llegar al exterior y nada de fuera puede enrutarse hacia
ella. Los dos contenedores de la aplicación están en ella *y* en la red
predeterminada, porque un análisis es una solicitud saliente y el servicio web
se publica en un puerto. Redis solo está en la interna.

Si ejecuta Redis por su cuenta en lugar de con estos archivos, los
equivalentes son `bind 127.0.0.1`, una regla de cortafuegos o un segmento de red
privado. Nunca publique el 6379 en una interfaz del host, y nunca en internet:
los escáneres encuentran un Redis abierto en una dirección pública en cuestión
de minutos.

## Persistencia, o su ausencia deliberada {#persistence-or-the-deliberate-lack-of-it}

El Redis incluido se ejecuta con `--save ""` y `--appendonly no`. No escribe
nada en disco, a propósito.

La persistencia y las copias de seguridad pueden conservar datos de análisis
más allá de su caducidad en el almacén en ejecución. Por eso la pila
predeterminada desactiva tanto las instantáneas como la persistencia
append-only. Un reinicio pierde los resultados temporales y el resto del estado
gestionado por Redis, incluidas las exclusiones añadidas por el operador;
guarde en el entorno las exclusiones duraderas.

No añada un volumen al servicio `redis`. Si usa un Redis gestionado que
persiste por defecto, acepte que los resultados sobrevivan a su TTL en las
copias de seguridad de otra persona o desactive la persistencia en esa
instancia.

Aun así, `docker/setup-wizard.py` generará una pila con persistencia para el
único despliegue en el que compensa: una instancia privada en la que perder un
análisis en cola por un reinicio importa más que el hecho de que los análisis
estén en un disco del que alguien pueda hacer copia. Nunca es la opción
predeterminada, avisa cuando se elige y remite a `COS_WEB_ENCRYPT_RESULTS`:
con esa opción activada, lo que llega al disco es texto cifrado y la clave vive
en `.env` y no a su lado. En un despliegue al que pueden acceder desconocidos,
la respuesta sigue siendo `none`.

## Memoria y desalojo {#memory-and-eviction}

```
--maxmemory 256mb
--maxmemory-policy allkeys-lru
```

El límite de memoria incluido es un punto de partida para el número
predeterminado de workers. Vigile el uso real a medida que aumentan el volumen
de análisis y la retención. Un límite de memoria impide que una cola sin
vaciar consuma la memoria disponible del host.

`allkeys-lru` puede desalojar cualquier clave bajo presión de memoria, en
función de su uso reciente aproximado. No se limita a los resultados de
análisis antiguos: también pueden verse afectados el estado de la cola, los
contadores y los datos gestionados por el operador. Trate el desalojo como una
señal de capacidad e investíguelo en lugar de confiar solo en el TTL.

Aumente el límite si aumenta mucho `COS_WEB_RESULT_TTL` o analiza un conjunto
de cientos de instancias. Vigile `evicted_keys`:

```bash
docker compose exec redis valkey-cli info stats | grep evicted_keys
```

Un desalojo constante con un TTL corto significa que el límite es demasiado
bajo y que la gente pierde resultados antes de leerlos.

## Un Redis externo o gestionado {#an-external-or-managed-redis}

Apunte `COS_WEB_REDIS_URL` a él y elimine el servicio `redis` del archivo
compose. Antes de hacerlo, conviene comprobar:

- **Use TLS.** `rediss://`. La conexión transporta los documentos de resultado
  y la contraseña.
- **Asígnele su propio número de base de datos o su propia instancia.** Los
  nombres de las claves tienen espacio de nombres (`scan:`, `cos:web:`), pero
  la purga de `DELETE /api/purge` recorre `scan:*:metadata`, y una instancia
  compartida con mucha actividad la hace más lenta de lo necesario.
- **Compruebe la política de desalojo.** Un Redis gestionado con
  `noeviction` por defecto empezará a rechazar escrituras cuando se llene en
  lugar de descartar un resultado antiguo, y una escritura rechazada es un
  envío que falla en lugar de ponerse en cola.
- **Compruebe qué persiste.** Consulte la sección anterior.

## Kubernetes {#kubernetes}

La [guía de Kubernetes](../kubernetes.md) despliega el servicio de análisis;
allí Redis es un `Deployment` y un `Service` propios, o una instancia
gestionada. Se aplican las mismas reglas, expresadas de otra forma:

- La contraseña va en un `Secret`, referenciado desde la URL mediante
  `COS_WEB_REDIS_URL`, no en un `ConfigMap`.
- Una `NetworkPolicy` que limite la entrada a los pods web y worker es el
  equivalente de la red interna.
- `ClusterIP` y ningún `Ingress`. Nunca un `LoadBalancer` ni un `NodePort`.
- Ningún `PersistentVolumeClaim`, por el motivo explicado en
  [Persistencia](#persistence-or-the-deliberate-lack-of-it).

## Estado y monitorización {#health-and-monitoring}

`GET /healthz` responde `503` cuando no se puede leer la cola o ningún worker
ha enviado un latido, así que una sonda sobre él cubre Redis sin una segunda
comprobación. Informa de la longitud de la cola y del estado de las dos
actualizaciones diarias, y no dice nada de ningún análisis concreto.

Merece una alerta:

| Señal | Por qué |
|:-------|:----|
| `/healthz` devuelve 503 | Redis no está accesible o el worker ha desaparecido. No se puede analizar nada |
| La longitud de la cola sube y no baja | Los workers están bloqueados o son muy pocos; hay envíos esperando |
| `evicted_keys` aumenta | Se descartan resultados antes de su TTL |
| `rejected_connections` | El límite de conexiones, normalmente por una fuga en algún sitio |

## Solución de problemas {#troubleshooting}

| Lo que ve | Qué significa |
|:-------------|:--------------|
| `NOAUTH Authentication required` | Redis tiene contraseña y la URL no. Añada `:PASSWORD@` después del esquema |
| `WRONGPASS invalid username-password pair` | La URL y `--requirepass` no coinciden. Normalmente cambió `.env` y solo se reinició un contenedor |
| `Connection refused` | Redis no está en marcha, o no está en la red del llamante. Revise `docker compose ps` y que ambos servicios de la aplicación incluyan `scanner_internal` |
| `Name or service not known: redis` | El contenedor de la aplicación no está en la red interna |
| `MISCONF Redis is configured to save RDB snapshots` | La persistencia está activada donde no debería. Consulte [Persistencia](#persistence-or-the-deliberate-lack-of-it) |
| `OOM command not allowed when used memory > 'maxmemory'` | Se ha alcanzado el límite y la política es `noeviction`. Debería ser `allkeys-lru` |
| `/healthz` indica `unavailable` | Redis responde, pero ningún worker ha enviado un latido. Revise los registros del worker, no los de Redis |
| Un resultado da 404 antes de tiempo | Ha caducado el TTL o se ha desalojado una clave. Ambas cosas son intencionadas; revise `evicted_keys` si ocurre a menudo |

El servicio registra marcadores del ciclo de vida y un uuid, nunca una
dirección de destino ni un resultado, así que un problema de Redis aparece en
los registros como análisis que nunca salen de `queued`. Es el compromiso
buscado: los registros no son un historial de lo que ha analizado cada
persona.
