# Desplegar el servicio web del escáner de seguridad de OpenCloud

La aplicación web ejecuta el escáner incorporado y presenta sus hallazgos con
una nota de **A+** a **F**. Por defecto, los resultados permanecen disponibles
en Redis durante una hora. La capa web se limita a presentar el resultado del
escáner; no calcula una calificación propia.

Pruebe el servicio público en [scan.okxo.de](https://scan.okxo.de) para un
análisis puntual. Las instrucciones siguientes explican cómo alojar su propio
servicio, incluidos el acceso de red, la retención y los límites de uso.

**No** está en PyPI. `pip install check-opencloud-security` instala el
complemento y la biblioteca del escáner, deliberadamente sin FastAPI, sin
Redis y sin una sola plantilla. La aplicación web se distribuye como recurso de
las versiones de GitHub, `check_opencloud_security_web.tar.gz`, o se construye
a partir de una copia del repositorio.

| | |
|:--|:--|
| **Ejecuta** | FastAPI + un worker de ARQ + Redis |
| **Guarda** | Nada en disco. Solo Redis, y cada clave con un TTL |
| **Necesita** | Ninguna base de datos, ninguna cuenta, ninguna clave de API |
| **Concurrencia** | La fija el operador, nunca una solicitud |

La interfaz está disponible en inglés, alemán, francés y español. Al principio
sigue la preferencia de idioma del navegador; una elección hecha con el
selector de idioma se recuerda en una cookie `HttpOnly` y `SameSite=Lax`. Las
guías están disponibles en los cuatro idiomas. Los contratos de la API, las
exportaciones y la evidencia medida conservan sus valores técnicos originales.

## Contenido {#contents}

- [Ponerlo en marcha](#starting-it)
- [Qué puede pedir un visitante](#what-a-visitor-can-ask-for)
- [Configuración](#configuration)
- [Cómo fluye un análisis](#how-a-scan-flows-through-it)
- [Poner en cola en lugar de rechazar](#queueing-rather-than-refusing)
- [Aislamiento entre análisis](#isolation-between-scans)
- [Comparar dos análisis](#comparing-two-scans)
- [La protección contra SSRF](#the-ssrf-guard)
- [Limitación de frecuencia](#rate-limiting)
- [Qué se registra](#what-gets-logged)
- [Ponerlo detrás de un proxy inverso](#putting-it-behind-a-reverse-proxy)
- [La API HTTP](#the-http-api)
- [Estructura](#layout)
- [Marcas e independencia](#trademarks-and-affiliation)

## Ponerlo en marcha {#starting-it}

El asistente de configuración crea los tres servicios necesarios: la
aplicación web, el worker de análisis y Redis. Es un script de Python
independiente que usa la biblioteca estándar y no necesita una copia del
repositorio:

```bash
mkdir opencloud-scanner && cd opencloud-scanner

base=https://github.com/sowoi/check-opencloud-security/releases/latest/download
curl -fsSLO "$base/setup-wizard.py" -O "$base/setup-wizard.py.sha256"
sha256sum --check setup-wizard.py.sha256    # macOS: shasum -a 256 --check
chmod +x setup-wizard.py
./setup-wizard.py --version
./setup-wizard.py

docker compose up -d
# http://127.0.0.1:8811
```

Hace una pregunta cada vez y escribe un archivo compose comentado con las
respuestas no secretas en línea, además de un `.env` legible solo por el
propietario con todas las credenciales a las que ese archivo hace referencia
como `${NAME}`: la contraseña de Redis, el token de borrado, la clave de firma,
la sal de auditoría y la clave de cifrado.
[Un despliegue propio](#a-deployment-of-your-own) describe las opciones.

### O los archivos compose que incluye este proyecto {#or-the-compose-files-this-project-ships}

Dos formas, ambas listas para `up`. La imagen publicada:

```bash
git clone https://github.com/sowoi/check-opencloud-security.git
cd check-opencloud-security/docker

printf 'COS_REDIS_PASSWORD=%s\n' "$(openssl rand -base64 36 | tr -d '/+=')" > .env
chmod 600 .env

docker compose -f docker-compose.dockerhub.yml up -d
# http://127.0.0.1:8811
```

O la misma pila construida a partir de la copia del repositorio, con
`docker compose up --build -d` y sin `-f`.

Tres ajustes deciden si esa pila está preparada para que otras personas
accedan a ella, y los tres están en `.env`, junto al archivo compose:

| Ajuste | Por qué importa |
|:--------|:---------------|
| `COS_WEB_PUBLIC_BASE_URL` | Las URL canónicas, el mapa del sitio y el documento de descubrimiento se construyen a partir de él y no de una cabecera `Host` entrante. Su valor predeterminado es `http://localhost:8811`, para que un primer `up` funcione; todo lo que sea accesible para desconocidos debe definirlo |
| `COS_REDIS_PASSWORD` | Redis contiene todos los análisis en curso y todos los resultados que siguen dentro de su TTL. Sin definir, no pide nada. Consulte [Redis](../redis.md) |
| `COS_WEB_TRUST_FORWARDED_FOR` | `true` solo detrás de un proxy propio; de lo contrario, cualquier cliente puede falsificar su propia identidad de límite de frecuencia. Defina `COS_WEB_TRUSTED_PROXY_HOPS` con el número de proxies que hay |

La imagen publicada está en Docker Hub como **`okxo/opencloud-scanner`**, así
que un despliegue no tiene que construir ninguna. `latest` y
`MAJOR.MINOR.PATCH` siguen la versión publicada, `MAJOR.MINOR` sigue la línea
y `edge` es el `main` actual. Incluye `linux/amd64` y `linux/arm64`, y la misma
imagen ejecuta tanto el servicio web como el worker (solo se diferencian en el
comando), por eso el código que describe un resultado y el que lo produce no
pueden divergir entre despliegues.

Ejecutar un contenedor a mano requiere un Redis compartido con el worker y la
dirección pública, porque ninguno de los dos tiene un valor predeterminado útil
fuera de un archivo compose:

```bash
docker run --rm -p 8811:8811 \
    -e COS_WEB_REDIS_URL="redis://:PASSWORD@redis:6379/0" \
    -e COS_WEB_PUBLIC_BASE_URL=http://127.0.0.1:8811 \
    okxo/opencloud-scanner:latest
```

[`docker/README.md`](../../docker/README.md) describe las pilas por completo,
incluida la de Authentik, y la descripción de Docker Hub incluye una receta
simple con `docker run` para los tres contenedores.

### Sin contenedores {#without-containers}

Desde una copia del repositorio, con tres terminales o tres `&`:

```bash
pip install ".[web,mcp]"    # the mcp extra is optional; it serves /mcp
valkey-server &
COS_WEB_REDIS_URL=redis://127.0.0.1:6379/0 python -m webapp.tasks &
COS_WEB_REDIS_URL=redis://127.0.0.1:6379/0 \
    uvicorn webapp.app:app --host 127.0.0.1 --port 8811
```

Para construir usted mismo el archivo de la versión:

```bash
python scripts/build_web_bundle.py
# dist/check_opencloud_security_web.tar.gz  (+ .sha256)
```

### Un despliegue propio {#a-deployment-of-your-own}

Use el asistente para configurar otro puerto, destinos internos, cifrado de
resultados o autenticación de MCP. Se puede ejecutar desde una copia del
repositorio o como descarga independiente:

```bash
cd docker
./setup-wizard.py --output-dir ~/opencloud-scanner
```

Explica cada ajuste, muestra una respuesta de ejemplo y escribe un archivo
compose comentado con las respuestas no secretas en línea, además de un
`.env`, legible solo por el propietario, con las credenciales a las que ese
archivo hace referencia como `${NAME}`. Si responde `generate`, crea por usted
el token de borrado, la clave de firma, la sal de auditoría y la clave de
cifrado. `--preset private` parte de lo que necesita un parque que analiza sus
propias instancias, y `--non-interactive` acepta todos los valores
predeterminados para una instalación desatendida.

`--sign-in` exige un token en `/mcp` y pregunta por el emisor, la audiencia y
las claves del proveedor que ya tenga en marcha. `--with-authentik` aprovisiona
uno: Authentik y su base de datos se añaden a la pila generada, esos tres
valores se derivan de las respuestas y el blueprint se escribe junto al archivo
compose que lo monta. Ambas opciones son independientes: aprovisionar un
proveedor no cierra el punto de acceso, así que la forma habitual de empezar es
levantar Authentik con `/mcp` todavía abierto, obtener un token y activar la
protección cuando funcione. Ninguna opción implica la otra, y no se escribe
nada de Authentik en un despliegue que no lo haya pedido. Eso sí, en modo
interactivo, activar `/admin` o el inicio de sesión en `/mcp` hace que *sí* sea
la respuesta predeterminada a la pregunta sobre el proveedor que viene a
continuación, ya que la mayoría de los despliegues que piden cualquiera de las
dos cosas todavía no tienen proveedor. Cuando se pide, se piden también sus
ajustes de correo (`--smtp-host`, `--smtp-from`, `--smtp-security` y los
demás), ya que un proveedor de identidad que no puede enviar una recuperación
de contraseña deja fuera a la única cuenta con la que empieza; la contraseña
procede de `AUTHENTIK_EMAIL_PASSWORD` en el entorno y no de una opción.
[`docker/README.md`](../../docker/README.md#the-setup-wizard) describe las
opciones. No tiene relación con `check-opencloud-security --configure`, que
configura una comprobación de monitorización y no un despliegue de
contenedores.

## Qué puede pedir un visitante {#what-a-visitor-can-ask-for}

Cuatro cosas, y la lista está cerrada:

| Campo | Significado |
|:------|:--------|
| `target_url` | La dirección principal de la instancia: nombre de host, `http://` o `https://` opcional y puerto opcional. Sin ruta, consulta, fragmento ni credenciales. Obligatorio |
| `ignore_hardenings` | Comprobaciones que se excluyen, de una lista permitida fija. Opcional, repetible |
| `release_track` | `rolling`, `production`, `lts` o `auto`. Opcional, `auto` por defecto |
| `output_format` | `dashboard`, `json`, `csv`, `sarif` o `pdf`. Opcional, solo afecta a la presentación |

`release_track` es la misma idea que `--release-track` del complemento: decide
cuánto tiempo tiene soporte la versión de la instancia y a qué versión se le
indica actualizar. Por defecto es `auto`, que pregunta al calendario de
versiones a qué canal pertenece la versión instalada, la respuesta adecuada
para el servidor de un desconocido, donde cualquier suposición fija es errónea
para alguien: suponer `production` declara desactualizada una instancia
rolling al día, y suponer `rolling` notifica un fin de vida que una instancia
production no ha alcanzado. Un valor desconocido recurre al predeterminado en
lugar de hacer fallar el análisis.

Cualquier otra cosa se rechaza con **422**, por su nombre, en lugar de
ignorarse: a quien envía `concurrency=50` hay que decirle que no ha servido de
nada, no dejarle creer que ha funcionado. La concurrencia, el número de hilos,
los tiempos de espera y la verificación TLS son ajustes del operador y no
tienen ningún equivalente en la solicitud.

El destino es una dirección, nunca una plantilla de solicitud. Una ruta como
`/apps/files`, una cadena de consulta, un fragmento, credenciales incrustadas,
espacios en blanco o caracteres de control de solicitud se rechazan en lugar de
descartarse sin avisar. El escáner elige por sí mismo las rutas de OpenCloud
que conoce; nada de lo que añada un visitante puede convertirse en una ruta, un
parámetro o una carga útil de una solicitud saliente.

Las exclusiones se comprueban con una lista permitida construida a partir del
catálogo de refuerzos, así que `*` y `debugPort:*` se descartan en lugar de
aplicarse. Una exclusión con comodín en un servicio público ocultaría todos
los hallazgos a la vez. Tampoco se ofrecen los indicadores que OpenCloud
fija en el código: nadie puede corregir esos hallazgos, y una exclusión
daría a entender lo contrario.

## Configuración {#configuration}

Cada ajuste es una variable de entorno que se lee una vez al arrancar.

| Variable | Valor predeterminado | Qué hace |
|:---------|:--------|:-------------|
| `COS_WEB_REDIS_URL` | `redis://127.0.0.1:6379/0` | Dónde se guarda el estado temporal. `memory://` funciona sin Redis, para una evaluación en un solo proceso. Incluya la contraseña cuando Redis la exija: `redis://:PASSWORD@redis:6379/0` |
| `COS_WEB_RESULT_TTL` | `3600` | Segundos durante los que se puede leer un análisis. También es el TTL de todas las claves |
| `COS_WEB_COMPARISON_TTL` | `300` | Segundos durante los que se puede leer una comparación con un informe subido. Limitado a 300; se respeta un valor menor |
| `COS_WEB_MAX_WORKERS` | `5` | Análisis que se ejecutan a la vez |
| `COS_WEB_SCAN_CONCURRENCY` | `4` | Sondeos en curso dentro de un análisis |
| `COS_WEB_SCAN_TIMEOUT` | `15` | Segundos que puede tardar un sondeo HTTP |
| `COS_WEB_JOB_TIMEOUT` | `180` | Segundos que puede tardar un análisis completo |
| `COS_WEB_VERIFY_TLS` | `true` | Verifica el certificado del destino. Una cadena no fiable se convierte en hallazgo en cualquier caso |
| `COS_WEB_ALLOW_PRIVATE_TARGETS` | `false` | Permite destinos privados, de loopback y de enlace local. Solo para despliegues locales |
| `COS_WEB_ALLOWED_HOSTS` | *(vacío)* | Nombres de host exentos de la protección contra SSRF, separados por `;` |
| `COS_WEB_BLOCKED_TARGETS` | *(vacío)* | Direcciones que este despliegue no analizará, separadas por `;`. Nombres de host, dominios `.suffix` y rangos CIDR. Prevalece sobre los dos ajustes anteriores; una entrada que no se puede interpretar impide el arranque |
| `COS_WEB_CHECK_DEBUG_PORTS` | `false` | Sondea puertos adicionales. Desactivado en público: es un escaneo de puertos del host de otra persona |
| `COS_WEB_IPV6_ENABLED` | `false` | Si este servicio tiene IPv6 saliente propio. Desactivado, nunca se marcan direcciones IPv6 y se omite la comparación TLS IPv4/IPv6, para que la falta de ruta en el host que analiza no se notifique como fallo de la instancia |
| `COS_WEB_IP_RATE_LIMIT` | `10` | Análisis por dirección de cliente y ventana. `0` lo desactiva |
| `COS_WEB_IP_RATE_WINDOW` | `60` | La ventana, en segundos |
| `COS_WEB_TARGET_COOLDOWN` | `300` | Segundos antes de que la misma instancia pueda volver a analizarse. `0` lo desactiva |
| `COS_WEB_PROBE_LIMIT` | `5` | Análisis de una misma dirección de cliente que pueden no encontrar ningún OpenCloud dentro de `COS_WEB_PROBE_WINDOW` antes de que esa dirección se bloquee. El mismo host analizado de nuevo vuelve a contar. Defínalo en el servicio web **y** en el worker. `0` lo desactiva |
| `COS_WEB_PROBE_WINDOW` | `300` | La ventana en la que se cuentan esos análisis, en segundos |
| `COS_WEB_PROBE_BLOCK` | `3600` | Cuánto dura el primer bloqueo, en segundos |
| `COS_WEB_PROBE_BLOCK_MAX` | `86400` | La duración máxima que alcanza un bloqueo repetido; cada bloqueo dentro de la ventana de repetición dura seis veces el anterior |
| `COS_WEB_PROBE_REPEAT_WINDOW` | `86400` | Cuánto tiempo después de terminar un bloqueo escala el siguiente, en segundos. `0` no escala nunca |
| `COS_WEB_PROBE_IPV4_PREFIX` | `24` | La red IPv4 que el bloqueo por sondeo cuenta como un solo cliente. `32` cuenta direcciones individuales |
| `COS_WEB_CLIENT_IPV6_PREFIX` | `64` | La red IPv6 que todos los límites de cliente cuentan como un solo cliente |
| `COS_WEB_DAILY_SCAN_LIMIT` | `50` | Análisis por cliente y día, además del límite por minuto. `0` lo desactiva |
| `COS_WEB_DNS_CONSISTENCY_CHECK` | `true` | Resuelve dos veces un nombre enviado y lo rechaza cuando las respuestas no comparten ninguna dirección |
| `COS_WEB_REQUIRE_APPROVAL` | `false` | Analiza solo instancias aprobadas; consulte [Modo de aprobación](#approval-mode) |
| `COS_WEB_APPROVED_TARGETS` | *(vacío)* | Nombres de host, dominios `.suffix`, direcciones y rangos CIDR aprobados, separados por `;`. Una entrada que no se puede interpretar impide el arranque |
| `COS_WEB_APPROVAL_DNS` | `true` | En modo de aprobación, acepta un registro TXT `_check-opencloud-security` que indique el nombre de host de este servicio |
| `COS_WEB_MAX_BATCH_TARGETS` | `10` | Destinos que puede llevar un `POST /api/scans/batch`. Cada uno sigue contando para todos los límites |
| `COS_WEB_TRUST_FORWARDED_FOR` | `false` | Lee la dirección del cliente de `X-Forwarded-For` |
| `COS_WEB_TRUSTED_PROXY_HOPS` | `1` | Cuántos proxies propios hay delante. La cabecera se lee desde la **derecha**, tantas entradas como se indique, porque ese extremo es la única parte que escribe un proxy |
| `COS_WEB_RATE_LIMIT_SALT` | *(aleatoria por proceso)* | Sal para las claves del límite de frecuencia y del tiempo de espera. Debe tener el **mismo valor en todos los procesos web** de un despliegue que ejecute más de uno: sin ella, cada uno deriva sus propias claves y un cliente obtiene un cupo por proceso |
| `COS_WEB_PUBLIC_BASE_URL` | *(obligatorio)* | El origen estable en el que se accede a este servicio, usado para los enlaces canónicos, `sitemap.xml` y el descubrimiento automático. Un valor sin definir impide el arranque, para que una cabecera `Host` entrante no pueda publicar URL controladas por un atacante |
| `COS_WEB_INDEX_META_TAG` | *(vacío)* | Hasta 10 pares de metadatos `name=content` opcionales en la página de inicio, separados por `;`. Los nombres y el contenido se escapan por separado; se rechazan el HTML sin procesar, los nombres duplicados o reservados y los metadatos de plataformas prohibidas |
| `COS_WEB_ALLOW_INDEXING` | `true` | Permite que los buscadores indexen la página de inicio y sus páginas explicativas. Las páginas de resultados nunca son indexables, diga lo que diga este ajuste |
| `COS_WEB_RELEASES_MODE` | `off` | Comprobación de actualizaciones con el canal de versiones de OpenCloud: `off`, `auto`, `feed`, `bundled` |
| `COS_WEB_RELEASES_TOKEN` | *(ninguno)* | Token de GitHub que eleva el límite de frecuencia del canal |
| `COS_WEB_SCHEDULE_REFRESH` | `true` | Vuelve a leer una vez al día la página de ciclo de vida de versiones de OpenCloud y evalúa los análisis según lo que diga. Una solicitud al día para todo el despliegue, no una por visitante |
| `COS_WEB_SCHEDULE_REFRESH_URL` | *(la página de ciclo de vida de OpenCloud)* | De dónde se lee ese calendario. Es configuración del operador, así que puede apuntar a una réplica; nunca es un campo de la solicitud |
| `COS_WEB_SCHEDULE_REFRESH_HOUR` | `4` | La hora (UTC) de la lectura diaria. Conviene variarla entre despliegues para que no lleguen todos a la vez |
| `COS_WEB_ADVISORY_REFRESH` | `true` | Pregunta una vez al día al canal de avisos qué vulnerabilidades afectan a OpenCloud y evalúa los análisis según la respuesta. Una actualización solo añade avisos, y nunca se cree uno sin límites de versión |
| `COS_WEB_ADVISORY_REFRESH_URL` | `https://api.osv.dev/v1/query` | De dónde se leen los avisos. Es configuración del operador, así que puede apuntar a una réplica; nunca es un campo de la solicitud |
| `COS_WEB_ADVISORY_REPOSITORY_URL` | `https://api.github.com/repos/opencloud-eu/opencloud/security-advisories` | Los avisos publicados solo en el repositorio de OpenCloud, que OSV nunca recibió; `off` los omite |
| `COS_WEB_FRONTEND_DIR` | *junto a `webapp/`* | Dónde están las plantillas y los recursos estáticos |
| `COS_WEB_ENABLE_DOCS` | `false` | Sirve las páginas navegables `/docs` y `/redoc`. Los documentos legibles por máquina son públicos diga lo que diga este ajuste |
| `COS_WEB_ENABLE_MCP` | `true` | Sirve el punto de acceso MCP en `/mcp` y registra las herramientas WebMCP del navegador. Se ignora si no está instalado el extra opcional `mcp` |
| `COS_WEB_MCP_ALLOWED_HOSTS` | *(vacío)* | Valores de `Host` que acepta el punto de acceso MCP, separados por `;`. Vacío desactiva la comprobación de DNS rebinding, lo que es correcto cuando un proxy ya fija el host |
| `COS_WEB_MCP_MAX_CONCURRENT_WAITS` | `8` | Cuántas llamadas a herramientas MCP pueden esperar a la vez a un análisis. Alcanzar el límite no rechaza nada: el análisis se envía y se devuelve el uuid para consultarlo |
| `COS_WEB_MCP_AUTH_ENABLED` | `false` | Exige un token bearer en `/mcp`. Desactivado, porque el servicio está pensado para responder a cualquiera; un despliegue que quiera lo contrario lo activa e indica un emisor. Consulte [un inicio de sesión en el punto de acceso MCP](../authentik.md) |
| `COS_WEB_MCP_AUTH_ISSUER` | *(vacío)* | El emisor OIDC cuyos tokens se aceptan, exactamente como lo escribe su documento de descubrimiento. Se acepta con o sin barra final |
| `COS_WEB_MCP_AUTH_AUDIENCE` | *(vacío)* | Lo que debe contener el claim `aud` de un token, normalmente el ID de cliente con el que se autentican los agentes. **Obligatorio** cuando el inicio de sesión está activado: vacío impide el arranque, porque de lo contrario un token emitido para otra aplicación detrás del mismo proveedor abriría esta |
| `COS_WEB_MCP_AUTH_JWKS_URL` | *(derivado)* | Dónde se publican las claves de firma. Por defecto `<issuer>/jwks/`, que es lo que responde un proveedor que sigue la especificación de descubrimiento |
| `COS_WEB_MCP_AUTH_RESOURCE_URL` | *(derivado)* | La URL que este punto de acceso reclama como recurso protegido. Por defecto `<COS_WEB_PUBLIC_BASE_URL>/mcp`; la audiencia de un token se comprueba con ella |
| `COS_WEB_MCP_AUTH_SCOPES` | *(vacío)* | Ámbitos que debe llevar un token, separados por `;`. Vacío significa que basta con cualquier token válido del emisor |
| `COS_WEB_ADMIN_ENABLED` | `false` | Sirve el área de operación en `/admin`. Desactivado significa que las rutas no se registran, así que la ruta da 404 como cualquier otra desconocida |
| `COS_WEB_ADMIN_PROXY_SECRET` | *(sin definir)* | El secreto que el outpost de authentik añade como `X-COS-Admin-Proxy`, y la única razón por la que se confía en las cabeceras de identidad. Obligatorio cuando el área está activada, de al menos 32 caracteres, o el arranque se rechaza |
| `COS_WEB_ADMIN_USERS` | *(vacío)* | Quién puede usar el área, por nombre de usuario de authentik, separados por `;`. Vacío con el área activada impide el arranque en lugar de significar "todo el mundo" |
| `COS_WEB_ADMIN_SIGN_OUT_URL` | *(sin definir)* | Adónde lleva el enlace de cierre de sesión del área. Este servicio no tiene ninguna sesión que terminar, así que la salida corresponde al proveedor situado delante; para la pila incluida, `/outpost.goauthentik.io/sign_out`. Sin definir, la franja muestra el nombre del operador y no ofrece salida. Solo se acepta una ruta local o una URL `http(s)`; cualquier otra cosa impide el arranque, porque el valor se muestra como `href` en una página cuya política de contenido prohíbe los scripts |
| `COS_WEB_ADMIN_AUDIT_BUFFER` | `200` | Registros de auditoría recientes que se guardan en memoria para la vista en directo, para un despliegue que registra en stdout. `0` no guarda ninguno |
| `COS_WEB_ADMIN_REFRESH_COOLDOWN` | `60` | Intervalo mínimo entre dos actualizaciones de los mismos datos de referencia lanzadas por el operador. La prueba en seco del área, que lee ambas fuentes y no aplica nada, se retiene durante el mismo intervalo con una clave propia, para que siga disponible justo después de que una actualización haya notificado un fallo |
| `COS_WEB_UPDATE_CHECK` | `true` | Consulta en GitHub si existe una versión más reciente de este servicio, solo para el área de operación y como máximo cada seis horas. Use `false` si no hay acceso de red saliente |
| `COS_WEB_ADMIN_UPDATE_DIR` | *(sin definir)* | Directorio tmpfs con permisos de escritura; los archivos de Compose lo montan en `/var/lib/opencloud-scan/update`. Si se define, el área de operación permite instalar una versión más reciente: descarga el paquete web de GitHub, verifica su atestación de compilación, lo extrae aquí y reinicia los procesos web y los workers para usarlo. El servicio se interrumpe brevemente. La actualización permanece activa hasta que se reinician los contenedores. Sin definir, el área solo informa de las actualizaciones disponibles |
| `COS_WEB_AUDIT_LOG` | `false` | Escribe un registro de auditoría por cada solicitud de análisis, rechazo y límite alcanzado |
| `COS_WEB_AUDIT_LOG_TARGETS` | `false` | Registra el nombre de host del destino en claro en lugar de como huella. Solo para despliegues locales |
| `COS_WEB_AUDIT_SALT` | *(aleatoria por proceso)* | Sal para las huellas de auditoría. Definir una permite relacionar registros tras un reinicio; rotarla lo impide |
| `COS_WEB_AUDIT_LOG_FILE` | *(la salida del proceso)* | Escribe los registros de auditoría en este archivo, en un montaje que sobreviva al contenedor. Legible solo por el propietario, y el registro normal ya no lleva copia. Una ruta en la que no se puede escribir impide el arranque |
| `COS_WEB_AUDIT_LOG_MAX_BYTES` | `10000000` | Tamaño al que se rota ese archivo. `0` no rota nunca |
| `COS_WEB_AUDIT_LOG_BACKUPS` | `5` | Generaciones rotadas que se conservan junto a él. Con el tamaño anterior, es lo máximo que puede ocupar el registro |
| `COS_WEB_AUDIT_LOG_ROTATION` | `service` | Quién rota ese archivo: `service` (este proceso, por tamaño) o `external` (logrotate en el host; este proceso solo vuelve a abrir el archivo que sustituye). Un valor no reconocido impide el arranque |
| `COS_WEB_PURGE_TOKEN` | *(ninguno)* | Activa `DELETE /api/purge` y es el secreto que exige. Sin definir, el punto de acceso responde 404 como cualquier otra ruta que no existe. Al menos 32 caracteres, o el arranque se rechaza: es toda la autorización de la única llamada que borra resultados de otras personas. Cinco respuestas erróneas desde una misma dirección en cinco minutos van seguidas de `429` |
| `COS_WEB_PURGE_SIGNING_KEY` | *(ninguno)* | Firma el justificante de borrado. Sin definir, el borrado se realiza igualmente, pero el justificante no se puede verificar después |
| `COS_WEB_EXPORT_SIGNING_KEY` | *(ninguno)* | Añade una cabecera HMAC-SHA256 `X-COS-Signature` a cada exportación JSON, CSV, SARIF y PDF |
| `COS_WEB_ENCRYPT_RESULTS` | `false` | Cifra el documento de resultado guardado con AES-256-GCM. Requiere una clave; un proceso al que se le pide cifrar sin clave se niega a arrancar |
| `COS_WEB_WEBHOOK_SECRET` | *(ninguno)* | Se lee al arrancar, pero el servicio web no lo usa, porque no envía webhooks; los webhooks firmados son el `--webhook-secret` del complemento. Se enumera para que definirlo no se confunda con una errata |
| `COS_WEB_ENCRYPTION_KEY_<n>` | *(ninguno)* | Una clave de 32 bytes como 64 caracteres hexadecimales. El `<n>` más alto cifra y los inferiores siguen descifrando, que es la forma de rotar una clave |

`COS_WEB_RELEASES_MODE` está en `off` por defecto: un despliegue
público que consulta el canal de versiones una vez por visitante acaba
limitado por frecuencia, y entonces la comprobación de actualizaciones falla a
la vez para todos los visitantes. El calendario de versiones sigue decidiendo
el fin de vida sin él.

`COS_WEB_SCHEDULE_REFRESH` es el caso contrario, y está activado por defecto.
El calendario que incluye la imagen lo escribe la CI, así que un servicio que
lleva seis semanas en marcha evalúa las instancias con una imagen del mundo de
hace seis semanas: dice que la versión de la semana pasada está "por delante
del calendario" y que una línea que ha perdido el soporte desde la
construcción "sigue teniendo soporte". Por eso el worker vuelve a leer una vez
al día la página de ciclo de vida publicada (también al arrancar, para que un
despliegue nuevo no espere a la madrugada) y guarda el resultado en Redis,
donde lo recogen los trabajos de análisis.

Una actualización solo puede añadir conocimiento. Se rechaza un documento que
ha perdido una línea que conoce el calendario incluido, porque una línea que
falta convierte una instancia sin soporte en una desconocida; una página
inaccesible, rediseñada o con una tabla truncada deja el calendario anterior
exactamente como estaba; y un archivo incluido más reciente tras un nuevo
despliegue prevalece sobre lo que quede en Redis. No se escribe nada en el
repositorio: `README.md` y el JSON incluido siguen siendo asunto de la CI.
Desactive la actualización en un despliegue sin acceso saliente, que entonces
se comporta exactamente igual que antes. `/healthz` indica la fecha del
calendario y la hora de la última lectura correcta, y
[ADR 0016](../../adr/0016-the-release-schedule-refreshes-itself.md) recoge el
razonamiento.

`COS_WEB_ADVISORY_REFRESH` actualiza la base de datos de avisos. Estos datos
determinan si una instancia *se notifica como vulnerable*. Si falta un aviso
reciente, el servicio puede presentar una instancia vulnerable como segura
sin que el visitante sepa que el resultado es incorrecto. Por eso el worker
consulta la fuente una vez al día y al arrancar. Los trabajos de análisis
usan los últimos datos aceptados.

Las reglas impiden tanto la pérdida de avisos como la incorporación de avisos
incorrectos. Una actualización **solo añade**: la respuesta se
combina con la base de datos que ya tiene el despliegue, así que un canal que
devuelve una lista vacía no cambia nada y una entrada escrita a mano se
conserva. Nunca se cree nada **sin límites** (un aviso que no indica versiones
coincidiría con todas las versiones que han existido, y los canales públicos
publican esa forma), y una respuesta con una cantidad absurda de avisos se
rechaza entera. Cualquier fallo deja la base de datos exactamente como estaba.
No se escribe nada en disco; el JSON incluido sigue siendo asunto de la CI, que
lo actualiza con `.github/workflows/vulnerability-db.yml`. Desactívela en un
despliegue sin acceso saliente, que entonces evalúa con el archivo incluido
exactamente igual que el complemento en un host de monitorización. `/healthz`
indica con cuántos avisos evaluaría y cuándo preguntó por última vez (recuentos
y fechas, nunca un hallazgo), y
[ADR 0017](../../adr/0017-the-advisory-database-refreshes-itself.md) recoge el
razonamiento.

## Cómo fluye un análisis {#how-a-scan-flows-through-it}

```text
POST /api/scans ──► client rate limit ──► SSRF guard ──► waiver allow-list
                                                              │
                          target cooldown ◄────────────────────┘
                                 │
                                 ▼
                    uuid4 ──► Redis (queued) ──► ARQ ──► 303 /scan/{uuid}
                                                          │
   worker: re-resolve ──► scan() ──► Redis (completed) ◄───┘
```

El límite por cliente se aplica primero porque es un solo `INCR` e impide que
el resolvedor que hay detrás de la protección contra SSRF se use como
amplificador. El tiempo de espera por destino se aplica al final, para que una
solicitud que iba a rechazarse de todos modos no consuma el turno de un destino
que nunca analizó.

## Poner en cola en lugar de rechazar {#queueing-rather-than-refusing}

Cuando hay más visitantes que workers, las solicitudes esperan en cola. Cada solicitud que supera
la validación recibe un uuid y un **202** (o un **303** desde el formulario), y
espera en una cola FIFO. La página del análisis muestra la posición
(*"Scan queued. Position in line: #2 of 7"*), y el script de consulta la
actualiza cada dos segundos hasta que un worker toma el trabajo.

Nada en la solicitud puede saltarse la cola ni ampliarla.
`COS_WEB_MAX_WORKERS` es lo único que decide cuántos análisis se ejecutan a la
vez, y se lee del entorno al arrancar el worker.

## Aislamiento entre análisis {#isolation-between-scans}

Cada análisis recibe un `uuid4` y tres claves propias:

```text
scan:{uuid}:status      queued | running | completed | failed
scan:{uuid}:result      the result document
scan:{uuid}:metadata    target, waivers, timestamps
```

El uuid es una capacidad: conocerlo es la única forma de llegar al análisis.

- **no** hay ningún punto de acceso que los enumere, y nunca lo habrá; una sola
  solicitud desharía todo el diseño. `GET /api/scans` solo devuelve al
  navegador al formulario, y no lleva nada consigo;
- un uuid desconocido, no válido o caducado es un **404** con un cuerpo
  idéntico en los tres casos, para que un desconocido no pueda saber que un
  uuid existió;
- todas las claves llevan el TTL, incluida la que se escribe mientras el
  análisis sigue en cola. Los datos caducan al terminar el plazo de conservación indicado en la página de inicio.

## Comparar dos análisis {#comparing-two-scans}

`GET /compare` responde a la pregunta que sigue a un plan de corrección: *¿ha
servido de algo?* Recibe dos uuid que el lector ya tiene (`?baseline=` para el
análisis anterior y `?current=` para el posterior) y muestra qué se ha
resuelto, qué es nuevo, qué sigue abierto y cómo ha cambiado la nota. Una
página de resultados terminada enlaza con ella con su propio uuid ya
rellenado, así que solo hay que pegar el anterior.

Las comparaciones usan `opencloud_local_scan.baseline` mediante
`workflows.compare_documents`, el mismo cálculo que usan la CLI y la
herramienta MCP `compare_scans`. Consulte
[ADR 0029](../../adr/0029-a-comparison-is-two-live-results-and-one-arithmetic.md).

**No se guarda nada.** La comparación se calcula a partir de dos resultados que
siguen existiendo y no se escribe en ningún sitio: este servicio no guarda
historial de análisis
([ADR 0002](../../adr/0002-no-scan-result-caching.md)) y un uuid es una
capacidad con TTL ([ADR 0007](../../adr/0007-erasure-on-request.md)). Una
comparación guardada sería un resultado de análisis con otro nombre, que
sobreviviría a los resultados que describe y quedaría exenta de su borrado. El
único caso en el que una comparación *sí* se conserva (porque el archivo del
que se obtuvo ya no está y nada podría volver a calcularla) se describe
[más abajo](#comparing-against-a-report-you-uploaded), y se conserva cinco
minutos, bajo una capacidad y dentro del borrado del que de otro modo quedaría
exenta.

Las respuestas que puede dar:

| Situación | Respuesta |
|:----------|:-------|
| Ambos uuid corresponden a análisis terminados | **200**, la comparación |
| Alguno de los uuid es desconocido o ha caducado | **404**, indicando *cuál* de los dos ha desaparecido; "uno de ellos ha caducado" obliga a buscar en los dos |
| Alguno de los análisis no ha terminado | **409**: todavía no hay nada que comparar, y un 404 haría que el lector volviera a analizar mientras su análisis sigue en curso |
| El mismo uuid dos veces | **422**. Una comparación vacía de un análisis consigo mismo se lee como "no hay nada mal" |
| Los dos análisis describen instancias distintas | **422**, no se comparan. "¿Ha funcionado la corrección?" es una pregunta sobre una sola instancia, y dos hosts comparados por error dan una respuesta equivocada que nadie nota; `check-opencloud-scanner diff` también los rechaza. Consulte [ADR 0059](../../adr/0059-a-comparison-refuses-two-different-instances.md) |

Igual que `/scan/{uuid}` y por el mismo motivo, la página muestra resultados y
por tanto nunca se indexa ni aparece en el esquema OpenAPI, y cada uuid sigue
siendo toda la autorización para el resultado que hay detrás.

## Comparar con un informe subido {#comparing-against-a-report-you-uploaded}

La comparación anterior necesita que ambos análisis sigan existiendo, y la
línea base interesante suele ser más antigua que la hora que dura un
resultado. `POST /compare` recibe el lado anterior como **archivo**: el JSON o
el CSV de las descargas de una página de resultados, subido desde el propio
disco del lector y comparado con un análisis de este servicio que no ha
caducado. La misma página, el mismo cálculo y los mismos veredictos; solo
cambia de dónde procede el documento anterior. Consulte
[ADR 0057](../../adr/0057-an-uploaded-report-is-evidence-not-a-scan.md). Un
informe de una instancia distinta de la del análisis con el que se compara, o
uno que no indica ninguna instancia, se rechaza igualmente con 422.

Es una función del navegador y sigue siéndolo: solo HTML, nunca en el esquema
OpenAPI, y no hay ninguna herramienta MCP para ella. Un agente ya tiene
`compare_scans`, que recibe dos uuid, la forma que un agente está en
condiciones de aportar.

**El archivo es la única estructura no fiable que procesa este servicio.**
Todo lo demás que compara salió de su propio escáner minutos antes, donde la
parte no fiable es una *cadena dentro* de un documento que construyó este
servicio. Así que una subida cruza una única frontera, `webapp/imports.py`, y
lo que sale de ella no es lo que entró: un documento de resultado reconstruido
clave a clave a partir de una lista permitida (los campos que lee
`baseline.snapshot_of`, cada uno con su tipo, longitud y forma comprobados).
Una clave que nadie ha nombrado ahí no llega a nada posterior.

| Protección | Valor |
|:------|:------|
| Archivo más grande que se lee | 256 KB, muy por debajo del límite de 1 MB del cuerpo, que ya ha rechazado todo lo que sea mayor |
| Codificación | UTF-8 estricto; un byte NUL o una secuencia no válida se rechaza en lugar de repararse |
| Formato | se decide examinando los bytes, nunca el nombre del archivo, que nada lee y nunca se refleja en una página |
| Filas CSV | 2000 |
| Anidamiento JSON | 20 niveles |
| Entradas por bloque, caracteres por cadena | 500 y 300; un bloque con más entradas que esas se rechaza en lugar de leerse en parte |
| Identificadores de hallazgos | se descartan salvo que se escriban como los escribe este escáner, y se muestra el número de todo lo que no se ha podido leer |
| Límite de frecuencia | un cupo propio, con los mismos números que el límite por cliente: procesar cuesta trabajo a este servicio y no le cuesta nada a la instancia de nadie |
| POST entre sitios | se rechaza antes del limitador y antes del procesamiento |
| Una red con un bloqueo por sondeo | se rechaza antes de ambos y antes de leer el archivo: el bloqueo juzga al cliente, no a un único endpoint |

**Un dato que el formato nunca registró se elimina de ambos lados en lugar de
adivinarse.** El CSV es una tabla plana de hallazgos; si había una
actualización pendiente y si se exigía HTTPS son datos que quedan fuera de esa
tabla. Ahora se escriben ambos como filas, pero un archivo descargado antes de
eso no dice nada de ellos, y el silencio no equivale a "no". Esas mediciones se
neutralizan en *ambos* documentos antes de la comparación, y la página indica
qué ha dejado fuera. JSON es el formato que se recupera sin pérdidas; CSV es
una tabla de hallazgos que también se puede importar, con esas limitaciones.

**El archivo nunca se guarda. La comparación sí, durante cinco minutos.** La
subida se lee una vez en memoria y no se escribe en ningún sitio. Lo que
sobrevive es la comparación obtenida de ella, guardada con un uuid4 nuevo en su
propio espacio de nombres `compare:{token}:*` para que una recarga y un enlace
compartido sigan funcionando: es lo único aquí que no se puede volver a
calcular, porque el archivo del que procede ya no está. El token se comporta
como el uuid de un análisis: desconocido, mal formado y caducado son un mismo
404, nada los enumera y el cifrado de resultados se aplica donde esté
configurado. `COS_WEB_COMPARISON_TTL` puede acortar ese periodo, pero no
ampliarlo.

**Una solicitud de borrado lo alcanza.** `DELETE /api/purge` recorre el
espacio de nombres de las comparaciones además del de los análisis y borra
todas las comparaciones en caché que mencionen esa instancia en cualquiera de
los dos lados, contando las claves en el mismo justificante para que
`remaining: 0` siga significando lo que dice. Un TTL de cinco minutos no es
motivo para dejar algo fuera de un borrado: ese es el argumento que
[ADR 0007](../../adr/0007-erasure-on-request.md) rechaza para el propio
resultado.

| Situación | Respuesta |
|:----------|:-------|
| Un informe legible y un análisis terminado | **303** a `/compare/{token}` |
| Ningún archivo o ningún uuid | **422**, indicando qué mitad falta |
| El uuid posterior es desconocido o ha caducado | **404** |
| El análisis posterior no ha terminado | **409** |
| El archivo está vacío, es demasiado grande, no es UTF-8 o no es JSON ni CSV | **422**, o **413** por tamaño, con las palabras de este servicio: una subida rechazada nunca se cita de vuelta |
| El archivo se puede procesar, pero no es un informe de análisis | **422** |
| Demasiadas subidas desde una misma red | **429** con `Retry-After` |
| La red tiene un bloqueo por sondeo | **429** con `Retry-After`, mientras dure el bloqueo |
| `GET /compare/{token}` pasados cinco minutos | **404**, exactamente igual que para un token que nunca existió |

## La protección contra SSRF {#the-ssrf-guard}

Un servicio público de análisis reenvía solicitudes por definición, así que el
destino se comprueba antes de conectarse a nada:

- el esquema debe ser `http` o `https`;
- el envío puede incluir una ruta base simple para una instancia instalada en
  una subcarpeta, pero no una cadena de consulta, un fragmento, credenciales,
  parámetros de ruta, secuencias de escape ni segmentos de recorrido. Las
  redirecciones que envía la instancia pueden contener rutas normales, pero se
  vuelven a validar por separado antes de seguirlas;
- el nombre de host debe resolverse, y **todas** las direcciones a las que se
  resuelve deben ser unicast públicas. Una sola respuesta privada entre varias
  rechaza el destino, lo que hace inútil el truco de los registros múltiples;
- `localhost`, `*.internal`, `*.local` y los nombres de metadatos de la nube se
  rechazan también por su nombre, porque un resolvedor que responde a esos
  nombres con una dirección pública ofrece una respuesta no fiable;
- `169.254.169.254`, `100.100.100.200` y `fd00:ec2::254` se rechazan
  explícitamente. La exclusión de enlace local ya cubre la primera, pero
  nombrarlas hace que el rechazo sea legible y sobreviva a una futura
  excepción;
- los nombres de servicios DNS comodín y de rebinding (`nip.io`, `sslip.io`,
  `xip.io`, `traefik.me`, `localtest.me`, `lvh.me`, `vcap.me`,
  `lacolhost.com`, `localhost.direct`, `local.gd`, `rbndr.us`, `1u.ms`) se
  rechazan por su nombre. Existen para que un nombre apunte a donde su lector
  no espera; la dirección pública que hay detrás se puede seguir analizando
  escribiéndola directamente;
- un nombre enviado se resuelve dos veces a la vez, y se rechaza cuando las dos
  respuestas no comparten ninguna dirección (`COS_WEB_DNS_CONSISTENCY_CHECK`).
  Todas las direcciones de ambas respuestas se someten a las reglas
  anteriores.

El **DNS rebinding** se contrarresta resolviendo dos veces: una al aceptar la
solicitud y otra en el worker justo antes del análisis. Así, el margen que
puede aprovechar un atacante es de una sola consulta, y nada en la solicitud
puede ampliarlo, porque nada en la solicitud influye en cuándo queda libre un
worker.

`COS_WEB_ALLOW_PRIVATE_TARGETS=true` desactiva todo esto. Existe para un
despliegue local que analiza su propio parque. No lo active en nada a lo que
pueda acceder un desconocido.

### Direcciones que este despliegue no analizará {#addresses-this-deployment-will-not-scan}

Todo lo anterior es una propiedad de la dirección. `COS_WEB_BLOCKED_TARGETS`
es una decisión que ha tomado alguien: el propietario de una instancia que ha
pedido que lo dejen en paz, un host que alguien sigue enviando hasta que el
servicio lo satura, un rango que aquí no es un destino de análisis por muy
público que parezca:

```bash
COS_WEB_BLOCKED_TARGETS="opencloud.example.com;.example.org;203.0.113.0/24"
```

- una entrada es un **nombre de host**, un **sufijo de dominio** escrito con un
  punto inicial (`.example.org`, o `*.example.org`; ambos significan el
  dominio *y* todo lo que hay debajo, y ninguno coincide con
  `notexample.org`), una **dirección** o un **rango CIDR**;
- los nombres de host se comparan por el nombre y los rangos con **todas las
  direcciones a las que se resuelve el nombre**. Por tanto, una entrada de
  nombre de host rechaza ese nombre y no un segundo nombre que apunte a la
  misma máquina: excluya el rango cuando el compromiso deba cumplirse se llame
  como se llame la instancia;
- se comprueba al enviar, de nuevo en el worker antes del análisis y en cada
  salto de redirección, así que un destino excluido mientras su trabajo
  esperaba en la cola se rechaza en lugar de analizarse;
- **prevalece sobre `COS_WEB_ALLOWED_HOSTS` y
  `COS_WEB_ALLOW_PRIVATE_TARGETS`**. Esos existen para relajar la protección;
  este responde a si el servicio analiza esa dirección en absoluto, y relajar
  no debe volver a abrirla. Consulte
  [ADR 0043](../../adr/0043-an-operators-exclusion-outranks-every-allowance.md);
- una entrada que no tiene ninguna de esas cuatro formas **impide el
  arranque**, tanto en el proceso web como en el worker. De lo contrario, una
  errata aquí sería invisible: el servicio arranca, responde con normalidad y
  analiza las direcciones que se le dijo que no analizara.

El rechazo que ve un visitante solo dice que se ha pedido al servicio que no
analice esa dirección. Qué entrada ha coincidido es configuración del
operador, y repetirla haría de cada rechazo una lectura de la lista.

**La lista tiene una segunda mitad que se puede cambiar con el servicio en
marcha.** La solicitud que origina la mayoría de las exclusiones (alguien que
escribe pidiendo que no se le analice) rara vez llega en un momento oportuno,
y "después de la próxima ventana de despliegue" no es una respuesta. Por eso el
área de operación de `/admin` tiene una tarjeta *Exclusions* que añade y
retira entradas, y:

- una entrada surte efecto **a partir de la siguiente solicitud, en todos los
  procesos**, sin reiniciar nada: la API lee la lista en cada envío y el worker
  al empezar cada trabajo, así que un análisis que ya esperaba en la cola se
  rechaza en lugar de ejecutarse;
- lo que declara `COS_WEB_BLOCKED_TARGETS` **no se puede retirar desde ahí**.
  Esas entradas se muestran sin ningún control al lado, y un intento de
  eliminar una se rechaza con una indicación hacia el entorno: su archivo
  compose conserva el control de esas exclusiones;
- las entradas añadidas en el área se guardan en **Redis**, así que son tan
  duraderas como su Redis. Todo lo que deba sobrevivir a un vaciado pertenece
  a la variable de entorno;
- una entrada tiene como máximo **253 caracteres**, la longitud máxima de un
  nombre de host, aquí y en `COS_WEB_BLOCKED_TARGETS` por igual. Nada más
  largo podría coincidir con un destino que acepte el servicio, así que se
  rechaza como la errata que es;
- las dos mitades se comparan **interpretadas, no como texto**, así que
  `Example.COM` en el entorno y `example.com` en el área son una misma
  exclusión y no dos: el área no guarda lo que el entorno ya contiene, y se
  niega a retirarlo se escriba como se escriba;
- si no se puede leer el almacén, un envío **se rechaza en lugar de analizarse**
  sin la lista: `503`, con el motivo en el idioma del visitante y la indicación
  de alojarlo por cuenta propia, y una línea `exclusions_unreadable` en el
  registro de auditoría en lugar de un destino rechazado.

La tarjeta es lo único de esa área que escribe; consulte
[ADR 0044](../../adr/0044-the-operator-area-may-write-the-exclusions.md) para
las cuatro propiedades que lo hicieron aceptable allí, y
[ADMIN.md](../../ADMIN.md#the-operators-area-at-admin) para el área en sí.

## Limitación de frecuencia {#rate-limiting}

Los contadores de todos los límites se guardan en Redis y caducan automáticamente:

- **por cliente**: `COS_WEB_IP_RATE_LIMIT` análisis por
  `COS_WEB_IP_RATE_WINDOW`, y como máximo `COS_WEB_DAILY_SCAN_LIMIT` al día.
  Protege al servicio de un visitante, y el límite diario protege de la versión
  paciente de una ráfaga que se mantiene justo por debajo del límite por minuto
  toda la noche;
- **por destino**: un análisis por `COS_WEB_TARGET_COOLDOWN`. Protege a una
  instancia de OpenCloud del servicio. Se reclama con `SET NX`, así que dos
  solicitudes simultáneas para la misma instancia no pueden ganar ambas;
- **el bloqueo por sondeo**: `COS_WEB_PROBE_LIMIT` penalizaciones dentro de
  `COS_WEB_PROBE_WINDOW` bloquean la red del cliente durante
  `COS_WEB_PROBE_BLOCK`. Protege los hosts de todos los demás de que este
  servicio se use para averiguar qué responde dónde.

Todos responden **429** con un `Retry-After`. La dirección del cliente nunca se
guarda: una clave contiene un HMAC truncado con una sal secreta, que basta para
contar y no sirve de nada después.

**Qué cuenta como un cliente.** Una sola dirección IPv4 para los límites por
minuto y diario, porque personas desconocidas detrás de un mismo /24 no deben
compartir cupo; un /64 IPv6 (`COS_WEB_CLIENT_IPV6_PREFIX`) para todos los
límites, porque a un abonado se le asigna un /64 entero y de lo contrario
podría recorrerlo gratis. El bloqueo por sondeo cuenta también la red IPv4
`COS_WEB_PROBE_IPV4_PREFIX` (`/24` por defecto), para que un bloqueo no se
pueda esquivar pasando a la dirección siguiente.

**Qué es una penalización.** Un análisis que termina con el veredicto propio
del escáner de *aquí no hay OpenCloud* (`status.php` inaccesible, que no es
JSON u otro producto) o que se queda sin tiempo; y un envío que la protección
rechaza por aquello a lo que apunta: una dirección privada o interna, una
exclusión del operador, un nombre DNS comodín o de rebinding, un nombre cuyas
consultas no coinciden o, en modo de aprobación, una instancia que nadie ha
aprobado. El mismo host de nuevo es otra penalización, porque preguntar una y
otra vez a una dirección si ya responde también es sondear. Un análisis
terminado nunca cuenta, sea cual sea su nota, y tampoco una errata, un nombre
que no se resuelve o un esquema no admitido.

**Los bloqueos crecen cuando se vuelven a ganar.** Una red que vuelve a
bloquearse dentro de `COS_WEB_PROBE_REPEAT_WINDOW` tras terminar su último
bloqueo espera seis veces más (una hora, seis horas, un día), hasta
`COS_WEB_PROBE_BLOCK_MAX`. Las penalizaciones de análisis que terminan durante
un bloqueo no cambian nada, y una red que se mantiene alejada durante la
ventana de repetición vuelve a empezar con una hora.

**El bloqueo se decide a posteriori.** Solo el worker sabe si un host era
OpenCloud, así que el envío le entrega la huella de la red (nunca la
dirección) en `scan:{uuid}:prober`, que el worker lee y borra en cuanto
empieza el análisis. El worker cuenta esas penalizaciones, la API cuenta los
destinos rechazados, y ambos imponen el bloqueo mediante las mismas claves; la
API lo lee antes del límite por cliente, para que los rechazos durante un
bloqueo no gasten además el cupo al que vuelve el visitante. MCP y los flujos
de trabajo esperan por sí mismos un `Retry-After` de hasta cinco minutos y
devuelven a quien llama cualquier espera mayor (un bloqueo o un límite diario
agotado).

**A un host que no es OpenCloud se le pregunta una vez.** El escáner lee
`status.php` antes que nada, y el servicio web define
`ScannerSettings.stop_when_not_opencloud`: una respuesta HTTPS que no es
OpenCloud termina ahí el análisis, en lugar de volver a preguntarse sin
verificación de certificado y después en el puerto 80, como hace el
complemento para un operador que busca el punto de acceso que funciona. El
silencio sí se reintenta, ya que puede deberse solo a un certificado no
fiable.

Un operador legítimo cuya propia instancia está caída también puede
encontrarse con el bloqueo, tras cinco intentos. Es el compromiso: el mensaje
explica el motivo y remite a ejecutar el escáner localmente, que no tiene ese
límite.

**El área de operación muestra la protección en funcionamiento** (redes
bloqueadas en este momento, y bloqueos, penalizaciones y límites diarios
agotados hoy y en siete días) como recuentos. Las claves de bloqueo se
cuentan, nunca se leen ni se enumeran.

### Modo de aprobación {#approval-mode}

`COS_WEB_REQUIRE_APPROVAL=true` convierte el escáner público en uno que solo
analiza instancias aprobadas, y rechaza el resto con **403**. Una instancia
está aprobada cuando coincide con `COS_WEB_APPROVED_TARGETS` (nombres de host,
dominios `.suffix`, direcciones y rangos CIDR, las mismas formas que las
exclusiones) o, con `COS_WEB_APPROVAL_DNS` (activado por defecto), cuando su
propia zona publica

```text
_check-opencloud-security.opencloud.example.com. TXT "check-opencloud-security=scan.example.net"
```

indicando el nombre de host de este servicio tomado de
`COS_WEB_PUBLIC_BASE_URL`. El registro aprueba un despliegue, no todas las
copias del proyecto, y no necesita ningún secreto: quien puede publicar un
registro TXT bajo un nombre controla ese nombre, que es lo que pide la
aprobación. La consulta va solo al resolvedor del sistema, como la
comprobación CAA del escáner (ADR 0024), y una consulta fallida es un rechazo.
La aprobación se comprueba al enviar. Un despliegue que exige aprobación con
una lista vacía y la prueba DNS desactivada, o con una entrada que no se puede
interpretar, se niega a arrancar.

**Una página de informe muestra la cuenta atrás.** Un informe terminado lleva
un botón **Scan again** y, a su lado, el tiempo que falta para que se permita.
Se leen todos los límites que lo impiden (`RateLimiter.peek_client`,
`peek_daily`, `peek_target` y el bloqueo por sondeo, que son las comprobaciones
normales sin la parte que cuenta) y se muestra el más largo, porque una cuenta
atrás que terminara en un rechazo por *otro* límite sería peor que no tener
ninguna. Leer un límite nunca debe gastarlo, o mostrarle a alguien su espera
sería la solicitud que la provoca.

El nombre de host procede del registro que el uuid ya desbloqueó, así que esto
no pregunta nada que quien llama no haya traído consigo: no hay forma de
preguntar por un destino del que no se tenga un uuid, y el uuid sigue siendo
toda la autorización. El botón en sí es un formulario normal que envía a `/`
el destino, las exclusiones, el canal de publicación y el formato de salida del
primer análisis, así que la comprobación entre sitios, ambos límites, la
protección contra SSRF y el registro de auditoría se le aplican exactamente
igual que a cualquier otro envío, y el segundo resultado se evalúa en las
mismas condiciones que el primero.

**Qué le dice un rechazo a un desconocido.** El tiempo de espera por destino
es compartido, así que su 429 dice que una instancia se ha analizado
recientemente, por quien sea. Es algo inherente a un tiempo de espera por
destino y no un fallo de la implementación, y está acotado por lo que cuesta:
cada sondeo, incluido uno dentro de un lote, gasta un análisis de la propia
ventana de cliente de quien sondea, y un destino que responde "no
recientemente" acaba de quedar reclamado por esa persona. Un despliegue que no
quiera que la pregunta tenga respuesta define `COS_WEB_TARGET_COOLDOWN=0` y
confía solo en el límite por cliente. En ningún lugar se dice *quién* lo
analizó.

## Qué se registra {#what-gets-logged}

Marcadores del ciclo de vida y un uuid:

```text
scan_created 0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa
scan_started 0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa
scan_completed 0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa
```

Ninguna URL de destino, ninguna dirección de cliente, ningún resultado. Un
registro que guarda lo que ha analizado todo el mundo *es* una base de datos de
lo que ha analizado todo el mundo, por corta que sea su retención.

### El registro de auditoría opcional {#the-optional-audit-trail}

Un operador que ejecuta esto para otras personas acaba teniendo que responder
preguntas que las líneas anteriores no pueden responder: ¿estuvo una red
enviando análisis toda la noche?, ¿aguantaron los límites?, ¿está alguien
sondeando el punto de acceso con campos que no acepta? `COS_WEB_AUDIT_LOG=true`
activa un segundo registro, independiente, justo para eso: el logger
`check_opencloud.web.audit`, un objeto JSON por línea, para que pueda
enrutarse y conservarse por separado:

```json
{"client": "9f2c1b7d4e6a0c58", "event": "scan_requested", "outputFormat": "dashboard", "releaseTrack": "production", "target": "1a4b9e0f7c23d865", "timestamp": "2026-08-19T10:14:02+00:00", "uuid": "0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa", "waivers": 0}
{"client": "9f2c1b7d4e6a0c58", "event": "rate_limited", "retryAfter": 42, "scope": "rate_limit_client", "timestamp": "2026-08-19T10:14:44+00:00"}
{"client": "3c80d5f21ab94e77", "event": "submission_rejected", "fields": ["workers"], "reason": "unsupported_fields", "status": 422, "timestamp": "2026-08-19T10:15:09+00:00"}
```

Tres eventos: `scan_requested` para un envío aceptado, `rate_limited` para un
límite por cliente, un tiempo de espera por destino, un límite diario
(`rate_limit_daily`), un bloqueo por sondeo (`rate_limit_probe`) o una subida
de informes (`rate_limit_upload`) que realmente se ha activado, y
`submission_rejected` para uno que nunca llegó a ser un análisis:
`unsupported_fields`, `target_rejected`, `target_not_approved`, o para un
informe subido que el analizador no ha podido leer (`report_rejected`, que
lleva la clave del rechazo de este servicio en `fields` y ninguna parte del
archivo).

Lo importante del diseño es lo que sigue sin anotar:

- **Una dirección de cliente es siempre una huella**, un HMAC truncado con la
  sal de auditoría, y ningún ajuste lo cambia. Dos solicitudes desde la misma
  red comparten huella, que es lo que necesita una auditoría; nada permite
  volver atrás.
- **El destino también es una huella**, salvo que
  `COS_WEB_AUDIT_LOG_TARGETS=true` indique que el despliegue analiza su propio
  parque y quiere el nombre de host.
- **La sal es aleatoria por proceso** salvo que se defina
  `COS_WEB_AUDIT_SALT`. Relacionar registros tras un reinicio es una decisión
  deliberada, y rotar la sal la deshace. **Trate como un secreto una sal que
  defina**, con el mismo cuidado que `COS_WEB_PURGE_TOKEN`: una huella solo es
  un seudónimo mientras la sal sea desconocida, y quien la averigüe puede
  volver a obtener las direcciones de cliente de un registro calculando el
  hash de todo el espacio de direcciones. Una sal aleatoria por proceso no
  tiene esa propiedad, por eso es el valor predeterminado.
- **El nombre de un campo enviado se registra, no se obedece**: se acorta, se
  eliminan los caracteres de control y se escapa en JSON, para que un salto de
  línea en el cuerpo de una solicitud no pueda falsificar un segundo registro.

Dejarlo desactivado no cambia nada: el registro normal del ciclo de vida es
exactamente el de arriba.

#### Conservar el registro más allá del contenedor {#keeping-the-trail-past-the-container}

Por defecto, esos registros van a la salida del proceso, que para un
contenedor significa `docker logs`, y un `docker compose down` se los lleva.
Una pregunta de auditoría llega meses después de los hechos, así que un
despliegue que quiera responderla entonces tiene que guardar el registro en un
lugar que sobreviva a la pila:

```yaml
services:
  web_app:
    environment:
      COS_WEB_AUDIT_LOG: "true"
      COS_WEB_AUDIT_LOG_FILE: "/var/log/opencloud-scan/audit.log"
      # Rotated at this size, keeping this many generations. Together they are
      # the most the trail can ever occupy: an audit log nobody rotates fills
      # the volume it sits on and takes the service down with it.
      COS_WEB_AUDIT_LOG_MAX_BYTES: "10000000"
      COS_WEB_AUDIT_LOG_BACKUPS: "5"
    volumes:
      - audit_log:/var/log/opencloud-scan

volumes:
  audit_log:
```

De eso se derivan tres cosas:

- **Los registros van al archivo en lugar de a la salida, no además de a
  ella.** El registro normal es el único lugar que este servicio mantiene libre
  de destinos y huellas de clientes, y un despliegue que lo envía a un sistema
  central no debería encontrarse con el registro de auditoría incluido.
- **El archivo solo es legible por el propietario**, incluidas las
  generaciones rotadas. Un volumen montado es legible por quien llegue al host
  en el que está.
- **Un archivo en el que no se puede escribir detiene el proceso**, con la ruta
  en el mensaje. De lo contrario, el servicio anunciaría un registro de auditoría que no se
  está escribiendo. El mismo razonamiento figura en
  [ADR 0008](../../adr/0008-refuse-to-start-without-the-encryption-key.md).

Un volumen con nombre es la respuesta más sencilla y la primera que ofrece
[`docker/setup-wizard.py`](../../docker/setup-wizard.py). Un montaje de un
directorio del host funciona igual (para un envío de registros o unas copias de
seguridad existentes), pero el directorio tiene que existir y pertenecer al uid
`10001`, el usuario sin privilegios con el que se ejecuta la imagen, antes de
que arranque la pila:

```bash
mkdir -p /srv/opencloud-scan/audit
sudo chown 10001 /srv/opencloud-scan/audit
```

Con Docker **sin root**, el uid 10001 del contenedor es un uid subordinado en el
host, así que ejecute el `chown` dentro de un contenedor, como el root del
espacio de nombres de usuario, que es usted, y sin sudo:

```bash
docker run --rm --user 0 --entrypoint chown \
  -v /srv/opencloud-scan/audit:/target valkey/valkey:9.1-alpine 10001 /target
```

Manténgalo separado de un directorio de datos de Redis: Redis escribe como uid
999, y un directorio solo puede pertenecer a uno de los dos.

#### Dejar que lo gestione el logrotate del host {#letting-the-hosts-logrotate-keep-it}

Un archivo en el sistema de archivos del host es algo que el host ya sabe
cuidar, y un parque con una política de retención prefiere expresarla donde
está la de todos los demás registros. `COS_WEB_AUDIT_LOG_ROTATION=external`
cede esa tarea: el servicio deja de rotar por tamaño y, en su lugar, detecta que
el archivo que tiene abierto se ha apartado y abre el nuevo.

Esa es la mitad que vive en este proceso. La otra mitad es una política que
instala el host: `docker/setup-wizard.py` escribe una junto al archivo compose
cuando la elige, y tiene este aspecto:

```
/srv/opencloud-scan/audit/audit.log {
    daily
    rotate 30
    dateext
    missingok
    notifempty
    compress
    delaycompress
    create 0600 10001 10001
}
```

```bash
sudo install -m 0644 -o root -g root opencloud-scan-audit.logrotate \
    /etc/logrotate.d/opencloud-scan-audit
sudo logrotate --debug /etc/logrotate.d/opencloud-scan-audit   # changes nothing
```

Dos líneas de esa política son fundamentales:

- **`create 0600 10001 10001`.** logrotate renombra el archivo y crea él mismo
  el nuevo, así que el nuevo tiene que poder escribirlo el usuario sin
  privilegios del contenedor y no poder leerlo nadie más.
- **Sin `copytruncate`.** Truncar el archivo por debajo de un proceso que
  escribe pierde lo que se haya escrito entre la copia y el truncado. Volver a
  abrir al cambiar el inodo no pierde nada, y este es un archivo cuya única
  finalidad es estar completo.

**Solo una cosa puede rotar el archivo.** Dejar
`COS_WEB_AUDIT_LOG_ROTATION` en `service` e instalar además una política da
dos, que es como un registro pierde entradas; definirlo como `external` y no
instalar nada da ninguna, y el archivo crece hasta llenar el disco. Un valor no
reconocido impide el arranque en lugar de adivinar a qué se refería.

Los cuerpos de las solicitudes se limitan a **1 MiB** y **30 segundos** antes
de procesar formularios, JSON o MCP. Los cuerpos demasiado grandes devuelven
413; los incompletos agotan el tiempo con 408. Estos límites fijos del
servicio no cambian la cola de análisis ni su comportamiento ante la
sobrecarga. Aplique también límites de conexiones y de ancho de banda en el
proxy inverso.

Cada análisis en curso usa un proceso hijo. Un tiempo de espera agotado o una
cancelación detiene y recoge ese proceso y sus hilos de sondeo antes de que el
worker tome otro trabajo. Por eso el worker necesita permiso para crear
procesos; al dimensionar la memoria y los límites de PID, cuente con un proceso
Python adicional por cada análisis activo. Consulte
[ADR 0053](../../adr/0053-a-scan-timeout-ends-its-process.md).

## Ponerlo detrás de un proxy inverso {#putting-it-behind-a-reverse-proxy}

La configuración completa para nginx, Apache httpd, Caddy, Traefik y HAProxy
(incluido el flujo que necesita el punto de acceso MCP y las rutas que un proxy
no debe reescribir) está en [Proxies inversos](../reverse-proxy.md).

[`docker/setup-wizard.py`](../../docker/setup-wizard.py) le escribirá ese
archivo para los cuatro primeros: responda a su pregunta sobre el proxy inverso
y la configuración aparecerá junto al archivo compose generado, con TLS, el
flujo `/mcp` sin búfer, un `X-Forwarded-For` que un cliente no puede elegir y,
cuando esta pila aporta el outpost, la autenticación delegada delante de
`/admin`. Consulte
[las notas del propio asistente](../../docker/README.md#the-reverse-proxy).

La versión breve:

Termine TLS delante, reenvíe `X-Forwarded-For` y solo entonces defina
`COS_WEB_TRUST_FORWARDED_FOR=true`.

La cabecera se lee desde la **derecha**, `COS_WEB_TRUSTED_PROXY_HOPS`
entradas (`1` por defecto, es decir, un proxy inverso). Ese extremo es la única
parte que escribe un proxy: `proxy_add_x_forwarded_for` de nginx, Traefik y la
mayoría de las redes de distribución de contenidos *añaden*, así que todo lo
que hay a la izquierda de la última entrada es lo que envió el cliente. Una CDN
delante de un ingress son dos saltos y necesita
`COS_WEB_TRUSTED_PROXY_HOPS=2`.

Contar de menos es seguro: la dirección registrada es la de un proxy y no la
del visitante. Lo que hay que evitar es contar más saltos de los que hay
realmente: eso lleva la lectura a la parte de la cabecera que controla el
cliente, y permite así la falsificación que el ajuste pretende impedir. En caso
de duda, cuente los proxies que gestiona usted y ninguno más.

Una entrada que no es una dirección IP se ignora en lugar de contarse, para que
un identificador ofuscado no pueda convertirse en el cupo de límite de
frecuencia de nadie.

La aplicación envía sus propias cabeceras de seguridad, incluida
`Content-Security-Policy: default-src 'self'` sin `unsafe-inline` en ningún
sitio. Todo lo que cargan las páginas (CSS, JavaScript, iconos, tipografías) se
sirve desde `/static`, así que no hay nada que relajar. Si su proxy añade una
política propia, asegúrese de que no relaja esta.

## La API HTTP {#the-http-api}

### `POST /api/scans` {#post-apiscans}

```bash
curl -sS -X POST http://127.0.0.1:8811/api/scans \
  -H 'Content-Type: application/json' \
  -d '{"target_url": "https://opencloud.example.com",
       "ignore_hardenings": ["cspWithoutUnsafeInline"]}'
```

```json
{"uuid": "0f4a1f22-...", "state": "queued", "url": "/scan/0f4a1f22-..."}
```

`target_url` puede ser un nombre de host sin más; si no se indica esquema, se
supone `https://`.

**202** si tiene éxito, **400** para un destino que no se puede analizar,
**403** para una instancia que un despliegue en modo de aprobación no ha
aprobado, **422** para un campo que el servicio no acepta y **429** cuando se
aplica un límite de frecuencia o el bloqueo por sondeo.

El formulario del navegador envía a `/` y no aquí, y recibe un **303** a
`/scan/{uuid}`. Ambas rutas usan el mismo manejador: un envío rechazado se
vuelve a mostrar donde se envió, y `/` es una URL que sobrevive a una recarga.
`Accept: text/html` selecciona el comportamiento HTML en cualquiera de las dos
rutas.

### `GET /api/scans/{uuid}` {#get-apiscansuuid}

```json
{
  "uuid": "0f4a1f22-...",
  "state": "queued",
  "target": "https://opencloud.example.com",
  "expiresIn": 3574,
  "queue": {"position": 2, "length": 7}
}
```

Una vez terminado, el mismo punto de acceso incluye `result` (el documento del
escáner, sin cambios) y `summary` (los mismos datos reagrupados para el panel).
**404** cuando el uuid es desconocido o ha caducado.

### `POST /api/scans/batch` {#post-apiscansbatch}

Para quien tiene que comprobar un parque y no una sola instancia:

```bash
curl -sS -X POST http://127.0.0.1:8811/api/scans/batch \
  -H 'Content-Type: application/json' \
  -d '{"targets": ["https://one.example.com", "https://two.example.com"]}'
```

```json
{
  "accepted": [
    {"uuid": "0f4a1f22-...", "target": "https://one.example.com",
     "state": "queued", "url": "/scan/0f4a1f22-..."}
  ],
  "rejected": [
    {"target": "https://two.example.com", "status": 429,
     "detail": "That instance was scanned very recently...", "retryAfter": 284}
  ],
  "counts": {"submitted": 2, "accepted": 1, "rejected": 1}
}
```

Cada destino de un lote pasa por la misma validación, el mismo límite por
cliente y el mismo tiempo de espera por destino que un envío individual, en el
orden de entrada. Diez destinos consumen diez análisis del cupo. La respuesta
separa los destinos aceptados de los rechazados, porque algunos pueden quedar
en cola mientras otros se rechazan.

Se aceptan los mismos cuatro campos, con `targets` en lugar de `target_url`, y
cualquier otra cosa es un **422** que la nombra. `COS_WEB_MAX_BATCH_TARGETS`
limita la lista; una más larga se rechaza entera, antes de poner nada en cola,
para que ningún destino pague un tiempo de espera por un lote que nunca se
ejecutó.

**202** cuando se ha iniciado al menos un destino. Cuando no se ha iniciado
ninguno, el estado es el motivo por el que se rechazó el primer destino:
**429** con `Retry-After` y la sugerencia de alojarlo por cuenta propia si fue
un límite, y **400** o **422** en los demás casos.

### `GET /api/scans/{uuid}/export/{format}` {#get-apiscansuuidexportformat}

Un análisis terminado se puede descargar como `json`, `csv`, `sarif`, `pdf`
o `html`. Los paquetes `remediation-md` y `remediation-html` solo contienen
hallazgos pendientes que se pueden corregir y fragmentos de configuración
propuestos para nginx, Caddy, Traefik, Compose y `.env`. Utilice un informe
completo para consultar la nota, las comprobaciones superadas y los avisos
de seguridad.

```bash
curl -sS -OJ http://127.0.0.1:8811/api/scans/0f4a1f22-.../export/pdf
```

El informe `html` es **un único archivo independiente** con sus estilos
incluidos. Al abrirlo no hace solicitudes de red: no contiene scripts,
imágenes, fuentes externas ni hojas de estilo externas. Los enlaces a la
documentación solo se abren si los sigue. Incluye los hallazgos, los hallazgos
eximidos con sus motivos, el plan de corrección, las lagunas de cobertura y
los datos de referencia utilizados para evaluar el análisis. No contiene
formularios, controles para repetir el análisis, consultas periódicas ni
tokens de borrado.

Los informes completos incluyen el plan de corrección: filas de resumen y
pasos en CSV, `runs[0].properties.remediation` en SARIF, una sección del plan
en PDF y HTML, y `remediationPlan` en JSON. Los detalles de transporte aparecen
en el bloque de cabecera de CSV, `runs[0].properties.tls` en SARIF, las secciones
de transporte de PDF y HTML, y `tls` en JSON. Incluyen el protocolo, el cifrado,
la validez del certificado y los días restantes, la integridad de la cadena
y el stapling OCSP. Un valor `null` significa que no se ha podido determinar
la medición, no que se haya superado la comprobación.

Las descargas se generan a petición a partir del resultado almacenado. Sus
enlaces dejan de funcionar cuando caduca el análisis. Los archivos ya guardados
siguen disponibles, no se actualizan y no se eliminan al borrar el análisis.
La respuesta de `GET /api/scans/{uuid}` para un análisis terminado enumera
las URL de descarga en `exports`; la página de resultados ofrece los mismos
formatos mediante botones de descarga.

#### Exportaciones firmadas {#signed-exports}

Con `COS_WEB_EXPORT_SIGNING_KEY` definido, cada respuesta de exportación lleva
una firma de sus bytes exactos:

```text
X-COS-Signature: HMAC-SHA256=d68d9da7f04a4dcf38de5c64545141dc02c50c7476e76687e74c015383f34258
```

Es un HMAC-SHA256 sobre el cuerpo tal como se envía, calculado con el texto de
la clave en UTF-8. PDF y CSV se cubren igual que JSON y SARIF. Permite que una
tarea de CI o un archivo demuestren más tarde que un fichero es el que produjo
este servicio y que nadie lo ha editado desde entonces.

**Es un secreto compartido, no una firma pública.** Para verificarlo se
necesita la misma clave, así que solo puede comprobar un archivo quien la
tenga: el operador, o una canalización que la reciba a través de su almacén de
secretos. Un visitante no puede verificar una descarga por su cuenta, y nunca
se le debe enviar la clave para hacerlo. Trátela como una contraseña y genere
una larga y aleatoria:

```bash
openssl rand -hex 32
```

Guarde la cabecera junto con el archivo, porque la firma no va incrustada en el
propio archivo:

```bash
curl -sS -D headers.txt -o result.pdf \
  http://127.0.0.1:8811/api/scans/0f4a1f22-.../export/pdf
grep -i '^x-cos-signature' headers.txt
```

Verifique los **bytes descargados**, nunca una copia procesada o vuelta a
serializar. Reformatear el JSON cambia los bytes y rompe la firma. Desde una
copia de este repositorio:

```bash
COS_WEB_EXPORT_SIGNING_KEY='<key-from-secret-store>' \
  uv run python scripts/verify_export.py result.pdf 'HMAC-SHA256=<hex-from-header>'
```

Imprime `signature verified` y termina con `0`, o imprime
`signature verification failed` y termina con `1`. `--key-env NAME` lee la
clave de otra variable de entorno. Sin una copia del repositorio, `openssl`
calcula el mismo resumen, para compararlo con el hexadecimal que sigue a
`HMAC-SHA256=`:

```bash
openssl dgst -sha256 -hmac "$COS_WEB_EXPORT_SIGNING_KEY" -r result.pdf
```

Rotar la clave invalida todas las firmas hechas con la anterior, ya que no hay
versiones de clave como las de `COS_WEB_ENCRYPTION_KEY_<n>`. Conserve la clave
anterior allí donde todavía haya que comprobar archivos antiguos. Sin la
variable, las exportaciones se envían sin firmar y sin cabecera.

**200** con un `Content-Disposition` que indica el uuid, **409** mientras el
análisis no ha terminado (existe, así que un 404 haría que quien llama entrara
en un bucle de reintentos contra el punto de acceso equivocado) y **404** para
un uuid o un formato desconocidos.

### `GET /api/scans/{uuid}/badge.svg` {#get-apiscansuuidbadgesvg}

La nota como un pequeño SVG, para pegarla donde una imagen lo dice más rápido
que un enlace.

```bash
curl -sS http://127.0.0.1:8811/api/scans/0f4a1f22-.../badge.svg
```

```markdown
![OpenCloud security](https://scan.example.com/api/scans/0f4a1f22-.../badge.svg)
```

Lo escribe `webapp/badge.py`, igual que `reports.py` escribe el PDF: sin
servicio de insignias, sin tipografía externa y sin scripts. Un `<img>` que
apunte al servidor de otra persona le entregaría la URL del resultado en un
referrer en cada visualización, y el uuid de esa URL es toda la autorización
para el resultado completo.

La insignia lleva la letra y nada que haya elegido la instancia analizada: ni
nombre de host, ni cadena de producto, ni versión. El color es el propio tono
del panel para esa nota, así que una insignia y la página a la que enlaza no
pueden discrepar.

**Dura exactamente lo mismo que el análisis.** Con el
`COS_WEB_RESULT_TTL` predeterminado de una hora, una imagen incrustada en un
lugar permanente deja de resolverse en menos de una hora y responde **404**
como cualquier otro uuid caducado. Eso la hace adecuada para una incidencia, un
mensaje de chat o un panel de estado mientras un resultado está vigente, e
inadecuada para un README, salvo que el despliegue que la sirve conserve los
resultados mucho más tiempo, lo que es una decisión con sus propias
consecuencias para todas las personas cuyos análisis guarda. No
hay ningún punto de acceso que genere una insignia para un *nombre de host*:
sería un identificador permanente y adivinable de la instancia de alguien,
algo que este servicio no ofrece.

**200** con `image/svg+xml` y `Cache-Control: no-store`, **409** mientras el
análisis no ha terminado y **404** para un uuid desconocido o caducado. El
`no-store` es el valor predeterminado de todo el servicio y aquí no se
desactiva: todas las rutas que admiten caché pública publican metadatos sobre
*este servicio*
([ADR 0031](../../adr/0031-a-response-is-uncacheable-until-a-route-opts-in.md)),
y una insignia es una afirmación sobre la instancia de alguien.

### `DELETE /api/purge` {#delete-apipurge}

Borrado a petición (la parte del operador de una solicitud del artículo 17 del
RGPD), más un justificante para archivarlo después.

```bash
curl -sS -X DELETE \
  -H "Authorization: Bearer $COS_WEB_PURGE_TOKEN" \
  "http://127.0.0.1:8811/api/purge?target=opencloud.example.com"
```

```json
{
  "receiptId": "8f14e45f-...",
  "issuedAt": "2025-01-30T11:04:07+00:00",
  "target": "opencloud.example.com",
  "targetFingerprint": "6c1f...",
  "deleted": {"scans": 2, "keys": 5, "queueEntries": 1, "rateLimitKeys": 1},
  "remaining": 0,
  "complete": true,
  "statement": "All scan records held for this target were deleted ...",
  "notes": ["..."],
  "signature": {"algorithm": "HMAC-SHA256", "value": "b91c..."}
}
```

Borra todos los espacios de nombres `scan:{uuid}:*` cuyos propios metadatos
indican ese nombre de host, las entradas del destino en la cola y la clave de
tiempo de espera derivada de él. `target` acepta un nombre de host sin más o
una URL completa, en mayúsculas o minúsculas, con o sin puerto.

`targetFingerprint` solo está presente cuando se define
`COS_WEB_PURGE_SIGNING_KEY`, y en otro caso es `null`: un hash sin clave de un
nombre de host no es un seudónimo, porque el espacio de nombres de host es lo
bastante pequeño para recorrerlo.

El justificante registra lo que encontró y eliminó el borrado. `deleted`
cuenta las claves eliminadas; `remaining` procede de una segunda inspección
posterior, y `complete` significa `remaining == 0`. `notes` indica los datos
que quedan fuera del alcance de la operación, incluidos los informes
descargados y cualquier registro de auditoría conservado. Verifique un
justificante firmado con:

```python
from webapp.purge import verify
verify(receipt, key)      # the value of COS_WEB_PURGE_SIGNING_KEY
```

**Está autorizado y desactivado hasta que se configura.** Es la única llamada
que recorre el espacio de claves y la única que destruye resultados que
pertenecen a quien los esté leyendo, así que una versión sin autenticación
sería una herramienta de denegación de servicio con un nombre amable. El
interesado escribe al operador; el operador, que es el responsable del
tratamiento, ejecuta la purga y le devuelve el justificante. **200** con el
justificante, **401** para un secreto erróneo, **422** para un destino que no
es un nombre de host y **404** siempre que `COS_WEB_PURGE_TOKEN` no esté
definido.

Si no se encuentran datos coincidentes, el punto de acceso devuelve 200 con
recuentos a cero. El justificante describe el almacén en el momento de esa
inspección.

### `GET /llms.txt`, `GET /openapi.json`, `GET /arazzo.json`, `GET /.well-known/ai.json` {#get-llmstxt-get-openapijson-get-arazzojson-get-well-knownaijson}

Estos documentos de descubrimiento y de contrato son siempre públicos.
`COS_WEB_ENABLE_DOCS` solo controla las vistas interactivas `/docs` y
`/redoc`.

El documento [OpenAPI](https://spec.openapis.org/oas/latest.html) indica qué
acepta y qué devuelve cada punto de acceso, hasta la forma de cada respuesta;
el documento [Arazzo](https://spec.openapis.org/arazzo/latest.html) que lo
acompaña indica cómo se usan esas operaciones en conjunto: enviar y consultar
hasta `done`, recorrer los uuid aceptados de un lote, esperar a que pase un 409
antes de descargar un archivo y borrar una instancia a cambio de un
justificante. Ambos se construyen a partir de la misma aplicación, y una prueba
falla si un flujo de trabajo describe una operación que ya no existe.

`/.well-known/ai.json` es el punto de entrada: nombre, descripción, las dos
URL de especificaciones, el punto de acceso MCP, los límites de uso que debe
respetar un agente y el enlace para alojarlo por cuenta propia. Es una
**convención a nivel de aplicación**, no un estándar registrado: existe para
que un agente que solo conoce el origen pueda encontrar el resto con una sola
solicitud.

`/llms.txt` es el mapa más breve en Markdown. Enumera los contratos públicos,
las operaciones principales, las herramientas WebMCP y las reglas sobre los
análisis asíncronos y los UUID. No contiene datos de análisis ni ningún
mecanismo de enumeración.

### `POST /mcp` {#post-mcp}

El punto de acceso del [Model Context Protocol](https://modelcontextprotocol.io),
por streamable HTTP, sin estado y con respuestas JSON. Es la capa de ejecución
para agentes y no reimplementa el servicio: cada herramienta llama dentro del
proceso a la propia API HTTP de esta aplicación, así que un agente se encuentra
exactamente con los mismos límites de frecuencia, protección contra SSRF y
autorización de purga que un navegador.

Siete herramientas, una por tarea de usuario y no una por punto de acceso:
`scan_instance`, `scan_instances`, `get_scan_result`, `plan_remediation`,
`compare_scans`, `export_scan` y `erase_instance_data`. Siete prompts nombran
las tareas que pide la gente (`audit_instance`, `audit_estate`,
`explain_scan_result`, `triage_findings`, `review_transport_security`,
`check_release_support` y `verify_remediation`), para que un cliente pueda
ofrecer "auditar esta instancia y redactar un plan de corrección" como una sola
opción. Se publican cinco recursos con URI `spec://`: los documentos OpenAPI,
Arazzo y de descubrimiento, y dos que son una base de conocimiento más que un
contrato: `catalogue`, cada indicador de refuerzo y comprobación adicional que
ejecuta el escáner, explicado, con el ajuste de OpenCloud que hay detrás, la
corrección y la documentación oficial; y `advisories`, toda la base de datos de
avisos con la que se evalúa un análisis. Ambos se construyen con las mismas
funciones que usa la página `/catalogue`, así que un agente puede explicar un
hallazgo, o ver qué detectaría el escáner, sin enviar nunca un destino, y sin
que un recurso discrepe nunca de la página sobre lo que significa una
comprobación. La semántica de consulta, reintentos y errores procede de
`webapp/workflows.py`, que es también la base del documento Arazzo, así que
ambos no pueden divergir.

`erase_instance_data` está marcada como destructiva y necesita la misma
credencial `Authorization: Bearer` que el punto de acceso HTTP. La credencial
se lee de las cabeceras de la solicitud del agente y nunca de un argumento de
la herramienta, así que nunca es un valor que haya visto el modelo. Cuando el
propio punto de acceso exige iniciar sesión, pasa a `X-Purge-Authorization`,
porque `Authorization` lleva entonces el token de identidad del agente y leer
uno como si fuera el otro es una confusión que conviene rechazar.

**El punto de acceso está abierto salvo que un operador diga lo contrario.**
Defina `COS_WEB_MCP_AUTH_ENABLED` y un emisor, y se convierte en un servidor de
recursos OAuth 2.0: un token se verifica localmente con las claves publicadas
por el proveedor (firma, emisor, audiencia, caducidad, ámbitos), y una
solicitud sin token recibe un 401 cuya cabecera `WWW-Authenticate` indica
`/.well-known/oauth-protected-resource/mcp`, el documento público de la
RFC 9728 que dice a qué proveedor preguntar. `/.well-known/ai.json` dice lo
mismo antes de la primera solicitud, en `mcp.authentication`.

Este servicio no emite nada, no guarda nada y no tiene cuentas: comprueba un
token que ha firmado otro. Y a un agente no le aporta nada más: el límite por
cliente, el tiempo de espera por destino, la protección contra SSRF y la cola
son idénticos con sesión iniciada. Una configuración errónea que dejaría el
punto de acceso abierto mientras el operador cree que está protegido impide el
arranque.
[Authentik delante del punto de acceso MCP](../authentik.md) es la
configuración de ejemplo.

La configuración de un cliente (Claude Code, Claude Desktop, GitHub Copilot en
VS Code y en la CLI, Cursor, Zed, Windsurf) está en
[Usar el escáner desde un agente de IA](../mcp.md), que también explica cómo
desactivar el punto de acceso.

### `GET /scan/{uuid}`, `GET /`, `GET /healthz` {#get-scanuuid-get-get-healthz}

La página de resultados, la página de inicio y una sonda de estado basada en
Redis que no dice nada de ningún análisis.

Una página de resultados terminada ofrece también **volver a analizar** (el
mismo destino en las mismas condiciones, con la espera en cuenta atrás al lado;
consulte [Limitación de frecuencia](#rate-limiting)) y muestra los hallazgos
que acaba de enumerar **como configuración**: un fragmento de Compose, `.env`,
nginx, Caddy o Traefik construido por `opencloud_local_scan.snippets` a partir
de los pares `env_fix` y `header_fix` del propio catálogo, con la variante
elegida recordada en el navegador. Las cinco se generan en el servidor y un
script las reduce a un selector, así que un lector sin scripts obtiene todos
los fragmentos en lugar de un bloque visible y cuatro botones que no hacen
nada. No se genera nada en el navegador: los fragmentos proceden del módulo que
cubren las pruebas de la biblioteca, y una segunda implementación en
JavaScript es lo único de la página que no debe existir. Las explicaciones que
antes contenía la página de inicio están en sus propias páginas
(`GET /how-it-works`, `GET /grades`, `GET /documentation`, `GET /search`,
`GET /api`, `GET /privacy` y `GET /about`), que son solo HTML y quedan fuera del
esquema OpenAPI. También `GET /compare`, por un segundo motivo: muestra dos
resultados y por tanto nunca es indexable, igual que `/scan/{uuid}`. `/grades`
explica el mapa real 0-5 del complemento y sus techos de corrección;
`/documentation` es la referencia rápida local de la CLI y el índice de guías,
y es también la página que remite fuera de este servicio: los comandos Docker
de una línea que ejecutan el mismo análisis en el equipo del visitante están
justo debajo de su inicio rápido, documentados en detalle en
[Analizar desde la línea de comandos, en una línea](../docker-oneliner.md).
Antes eran una pestaña `/cli` propia; esa ruta es ahora una redirección
permanente a `/documentation#oneliner`. `GET /healthz` devuelve 200 solo
cuando el backend configurado responde a `PING`, se puede leer la longitud de
su cola y existe el latido de corta duración de un worker. Su cuerpo de éxito
solo contiene el `queueDepth` agregado y `worker: "ok"`; devuelve un 503 sin
detalles mientras alguna dependencia no esté disponible.

Cada `/documentation/{slug}` por debajo del índice se genera al construir a
partir de las guías Markdown para operadores. El HTML confirmado en el
repositorio se verifica en CI y se distribuye dentro de `frontend/`; el
servicio en ejecución no procesa Markdown ni necesita los archivos de origen.
La ADR 0018 recoge esa frontera.

`/search` filtra en el navegador un índice JSON confirmado en el repositorio y
servido desde el mismo origen. Su manifiesto nombra explícitamente las
plantillas públicas y no puede ver Redis, la API, las páginas de resultados,
las exportaciones, los UUID ni las direcciones enviadas. Cada pull request a
`main` reconstruye ese archivo y lo confirma en la rama, y el flujo de trabajo
de publicación lo vuelve a construir antes de generar los artefactos, así que
una versión desplegada tiene un único índice de búsqueda inmutable. La ADR 0019
recoge la frontera y la ADR 0050 cuándo se reconstruye.

Cuando `COS_WEB_ENABLE_MCP` está activado, las páginas de inicio y de
resultados exponen además sus acciones existentes a los navegadores
compatibles mediante el
[borrador de WebMCP](https://webmachinelearning.github.io/webmcp/). La página
de inicio registra `scan_opencloud_security`; una página de resultados registra
`get_scan_result` y `export_scan_report` para el UUID mostrado. Sus esquemas se
generan a partir de los mismos catálogos que los controles de la página. La
ejecución usa la API pública con `Accept: application/json`, así que WebMCP no
elude la protección contra SSRF, los límites de frecuencia, el tiempo de
espera, la cola ni las comprobaciones de capacidad.

Una herramienta del navegador responde a un fallo en lugar de lanzar una
excepción: `ok: false` con `status`, `error` y `retryable`, más `retryAfter` en
segundos cuando el servicio lo envió. Es el contrato que ya usaban las
herramientas de `/mcp`, y los estados que hay detrás se insertan en la página
desde `webapp/workflows.py` en lugar de escribirse en el script. Consulte
[ADR 0041](../../adr/0041-a-browser-tool-answers-a-failure-rather-than-throwing.md).

`POST /` y `GET /scan/{uuid}` negocian JSON para las herramientas del
navegador y otros clientes. `Accept: application/json` solicita una respuesta
estructurada, y `output_format=json` hace lo mismo. HTML sigue siendo el valor
predeterminado para la navegación normal.

El ajuste opcional `COS_WEB_INDEX_META_TAG=name=content;name=content` añade
hasta diez elementos `<meta name="..." content="...">` a la página de inicio.
Docker Compose lo toma del entorno del despliegue. La aplicación interpreta y
escapa cada par en lugar de aceptar HTML sin procesar, y rechaza los nombres
duplicados, los que ya usa la página y los metadatos de plataformas
prohibidas. No se admite un punto y coma literal en un valor.

### `GET /advisories.atom`, `GET /release-schedule.atom` {#get-advisoriesatom-get-release-scheduleatom}

Los dos documentos que se actualizan solos cada día, como canales Atom 1.0.

```bash
curl -sS http://127.0.0.1:8811/advisories.atom
```

`/advisories.atom` es la base de datos de avisos con la que se evalúa un
análisis: una entrada por aviso, con su gravedad, los rangos de versiones
afectados en la forma semiabierta con la que compara el escáner y un enlace al
aviso publicado. `/release-schedule.atom` tiene una entrada por línea de
versiones de OpenCloud, fechada con su fecha de publicación, que indica en qué
canales se publicó y cuándo deja de recibir correcciones.

Ambos se construyen con las mismas funciones que usan las páginas, así que un
canal no puede describir un aviso de forma distinta a `/catalogue`. Son el
motivo por el que un análisis ejecutado hoy puede calificar una instancia con
más dureza que el mismo análisis el mes pasado: un
suscriptor se entera de que la base de datos ha cambiado sin tener que volver a
analizar para descubrirlo.

Los títulos y descripciones de los avisos proceden de un canal público que este
proyecto no controla. Se transmiten escapados como `type="text"`, nunca como
marcado, para que no se pueda obligar a un lector a mostrar el HTML de otra
persona.

Son las únicas rutas de datos de referencia que admiten una caché pública
(`max-age=3600`). No nombran ninguna instancia, no llevan uuid y no aceptan
parámetros (la condición que fija la
[ADR 0031](../../adr/0031-a-response-is-uncacheable-until-a-route-opts-in.md)
para admitir caché), y no se debe añadir esa posibilidad: un canal filtrado por
nombre de host sería una pregunta sobre la instancia de alguien. Los
identificadores de las entradas son URN del aviso o de la línea de versiones y
no URL de este despliegue, así que el historial de un lector sobrevive a que el
servicio cambie de host.

### `GET /robots.txt`, `GET /agents.txt`, `GET /sitemap.xml` {#get-robotstxt-get-agentstxt-get-sitemapxml}

Los tres se generan; nunca son archivos en disco. El mapa del sitio enumera la
página de inicio, las nueve páginas explicativas y de índice y todos los
documentos de la CLI generados, y toma cada `lastmod` de la plantilla que lo
genera, así que no puede divergir de las páginas que existen realmente. Ninguno
menciona nunca un resultado: el uuid es la única autorización, y este
servicio no tiene ninguna enumeración de resultados. `robots.txt`
prohíbe `/scan/`, `/api/`, el esquema y la sonda de estado, y apunta al mapa
del sitio.

`agents.txt` sigue en cambio la convención de
[agents-txt.com](https://agents-txt.com): bloques de capacidades con
directivas `Key: value` en lugar de la lista de permisos de `robots.txt`, para
que un analizador construido según esa convención lea directamente las
herramientas de este despliegue. Declara `MCP: <url>` y `WebMCP: <url>` cuando
este despliegue los sirve, `Authorization: oauth2` e `Identity: required` solo
cuando el propio punto de acceso MCP pide un token bearer, y nada para
`Protocols`/`Payments`/`A2A`/`Skills`/`UCP`, ya que ninguno se aplica aquí. Al
igual que `/.well-known/ai.json`, es una convención informal y no un estándar
registrado, y los contratos OpenAPI, Arazzo y MCP prevalecen sobre cualquier
cosa que diga.

`GET /agents.json` es el complemento estructurado que la convención recomienda
junto al archivo de texto: el mismo documento que sirve
`/.well-known/ai.json`, publicado de nuevo con el nombre al que apunta
`agents.txt`.

`COS_WEB_PUBLIC_BASE_URL` decide el origen en los tres, junto con el enlace
canónico de cada página. Detrás de un proxy, el servicio solo ve su propia
dirección interna, y sin ese ajuste publicaría URL a las que nadie de fuera
puede llegar.

`COS_WEB_ALLOW_INDEXING=false` lo desactiva todo: `robots.txt` pasa a ser un
rechazo total, `agents.txt` pasa a ser el archivo mínimo de la propia
convención sin ninguna capacidad declarada, `sitemap.xml` responde 404 y cada
página lleva `noindex`. Una página de resultados lleva `noindex` y un
`X-Robots-Tag` en cualquier caso.

## Estructura {#layout}

```text
webapp/                 the service
├── app.py              routes, security headers, request validation
├── settings.py         every COS_WEB_* variable
├── ssrf.py             the target guard
├── ratelimit.py        the two limits
├── audit.py            the optional audit trail, pseudonymised
├── store.py            the per-scan Redis namespace
├── queue.py            handing a scan to the worker pool
├── tasks.py            the ARQ worker
├── runner.py           the seam where a request becomes ScannerSettings
├── redis_backend.py    Redis, and the in-process stand-in for tests
├── reports.py          the CSV, SARIF and PDF exports
├── arazzo.py           the API described as executable workflows
├── documentation.py    the manifest for the generated browser documentation
├── purge.py            erasure on request, and the signed receipt for it
├── seo.py              the public page list, robots.txt, agents.txt and sitemap.xml
└── catalog.py          the waiver allow-list and the dashboard grouping

frontend/
├── static/{css,js,img} vanilla CSS, small scripts, hand-drawn SVG
└── templates/          base, index, scan, 404, and the content pages

docker/
├── Dockerfile.web      the image both web_app and arq_worker run
├── docker-compose.yml            locally built frontend, worker and Redis
├── docker-compose.dockerhub.yml  published-image frontend, worker and Redis
├── Dockerfile                    the plugin image, unrelated to the web application
└── docker-compose.monitoring.yml the plugin's own stack, also unrelated
```

[`webapp/README.md`](../../webapp/README.md) trata lo mismo desde el otro lado:
la superficie de la API, cómo acceder a Swagger, qué no puede pedir una
solicitud y cómo ejecutar una interfaz propia.

La frontera que mantiene el resto del proyecto también se aplica aquí:
`opencloud_local_scan` mide, el complemento juzga y `webapp` sirve. Si un
cambio hace que la capa web decida si un hallazgo es aceptable, pertenece al
escáner o al complemento.
