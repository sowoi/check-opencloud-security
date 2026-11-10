# Proteger el MCP del escáner de seguridad de OpenCloud con Authentik

Esta guía ejecuta el servicio de análisis y Authentik en una misma pila
Compose, con autenticación por token activada en `/mcp` desde el arranque.
Úsela cuando MCP solo deba estar disponible para los agentes autorizados por su
proveedor de identidad.

El sitio web y la API HTTP siguen siendo públicos. La autenticación controla el
acceso a MCP; no aumenta los análisis permitidos ni elude el tiempo de espera
por destino, las comprobaciones contra SSRF ni la cola.

<!-- TOC -->
* [Authentik delante del punto de acceso MCP](#authentik-in-front-of-the-mcp-endpoint)
  * [Cómo funciona](#how-it-works)
  * [Ejecutar la pila](#running-the-stack)
  * [Enviar correo](#sending-mail)
  * [Qué ha creado el blueprint](#what-the-blueprint-created)
  * [Un segundo factor para todos](#a-second-factor-for-everybody)
    * [Lo que ve la persona](#what-the-person-sees)
    * [Cómo se aplica](#how-it-is-enforced)
  * [Cuentas sin la interfaz de administración](#accounts-without-the-admin-interface)
  * [Un operador para /admin](#an-operator-for-admin)
    * [Con el asistente](#with-the-wizard)
    * [A mano, en la interfaz de Authentik](#by-hand-in-the-authentik-interface)
    * [Comprobarlo](#checking-it)
  * [Apuntar el escáner a él](#pointing-the-scanner-at-it)
  * [Añadir a alguien que pueda usar el punto de acceso](#adding-somebody-who-may-use-the-endpoint)
    * [Un grupo, y la vinculación que le da sentido](#a-group-and-the-binding-that-makes-it-mean-something)
    * [La persona](#the-person)
    * [El agente que no es nadie](#the-agent-that-is-nobody)
  * [Obtener un token](#getting-a-token)
    * [Como cuenta de servicio](#as-a-service-account)
    * [Sin nombrar ninguna cuenta](#without-naming-an-account-at-all)
    * [Como persona](#as-a-person)
    * [Leer el token obtenido](#reading-the-token-you-got)
  * [Configurar un agente](#configuring-an-agent)
  * [El borrado, que es otra credencial](#erasure-which-is-a-different-credential)
  * [Detrás de un proxy inverso](#behind-a-reverse-proxy)
  * [Copia de seguridad](#backing-it-up)
  * [Restauración](#restoring-it)
  * [Cuando no funciona](#when-it-does-not-work)
  * [Usar un proveedor que no sea Authentik](#using-a-provider-that-is-not-authentik)
<!-- TOC -->

## Cómo funciona {#how-it-works}

El servicio de análisis actúa como servidor de recursos OAuth 2.0. Verifica los
tokens emitidos por el proveedor y no tiene página de inicio de sesión,
sesiones, base de datos de usuarios ni secreto de cliente:

1. Un agente presenta `Authorization: Bearer <token>` en sus solicitudes MCP.
2. El servicio descarga las claves de firma publicadas por el proveedor (el
   JWKS) y verifica con ellas la firma del token.
3. Comprueba el emisor, la audiencia, la caducidad y los ámbitos que exija el
   despliegue.
4. Todo lo que falle en cualquiera de esos puntos no es un token, y la
   solicitud recibe un **401** que indica dónde obtener uno de verdad.

No se guarda nada, no se registra nada y no se hace ninguna solicitud al
proveedor por cada token: las claves se guardan en caché y la verificación es
local. Una clave de firma rotada se incorpora sin reiniciar.

Un agente que llega sin token recibe el tratamiento de la RFC 9728: un `401`
cuya cabecera `WWW-Authenticate` indica
`/.well-known/oauth-protected-resource/mcp`, un documento público que nombra el
servidor de autorización. `/.well-known/ai.json` dice lo mismo antes de la
primera solicitud, así que un agente bien hecho sabe que necesita un token sin
gastar un viaje de ida y vuelta en averiguarlo.

## Ejecutar la pila {#running-the-stack}

`docker/docker-compose.authentik.yml` no es una capa sobre la pila normal; es
el despliegue completo en un solo archivo. Seis servicios (la aplicación web,
el worker, Redis, Authentik, su propio PostgreSQL y el worker de Authentik) y
un solo comando:

```bash
cd docker
./authentik-env.sh                                  # writes .env, once
docker compose -f docker-compose.authentik.yml up -d
```

Después abra **<http://127.0.0.1:9000/if/flow/initial-setup/>** (la barra final
es obligatoria; sin ella obtendrá un 404) y defina la contraseña de la cuenta
`akadmin`. Ese flujo solo se ofrece una vez.

El primer inicio de sesión posterior pide a `akadmin` que registre un segundo
factor (una aplicación de autenticación o una llave de seguridad) antes de
completarse; consulte
[un segundo factor para todos](#a-second-factor-for-everybody).

El blueprint crea el proveedor y la aplicación. En este archivo Compose,
`COS_WEB_MCP_AUTH_ENABLED` sigue a `${COS_WEB_ENABLE_MCP:-true}`, así que
activar MCP exige también autenticación. Desactivar MCP desactiva ambas cosas a
la vez.

`authentik-env.sh` escribe seis secretos en `docker/.env` y nunca sobrescribe
uno que ya exista, así que ejecutarlo dos veces es seguro:

| Variable | Qué es |
|:---------|:-----------|
| `COS_REDIS_PASSWORD` | La contraseña que exige Redis. Contiene todos los análisis en curso y todos los resultados que siguen dentro de su TTL; consulte [Redis](../redis.md) |
| `AUTHENTIK_SECRET_KEY` | Firma todo lo que hay en la base de datos de Authentik |
| `AUTHENTIK_PG_PASS` | La contraseña del PostgreSQL de Authentik |
| `AUTHENTIK_CLIENT_ID` | El ID de cliente OAuth y, por tanto, la audiencia |
| `AUTHENTIK_CLIENT_SECRET` | El secreto de cliente OAuth |
| `COS_WEB_PURGE_TOKEN` | La credencial del operador para el borrado, que es algo completamente distinto |

Haga copia de seguridad de `.env` junto con los datos de Authentik. Conserve
`AUTHENTIK_SECRET_KEY` al restaurar, para que la instalación restaurada pueda
usar su estado criptográfico existente.

¿Accesible desde algún lugar que no sea su portátil? Dos variables, y no
cambia nada más:

```bash
AUTHENTIK_URL=https://sso.example.com \
COS_WEB_PUBLIC_BASE_URL=https://scanner.example.com \
  docker compose -f docker-compose.authentik.yml up -d
```

Es un archivo aparte y no un perfil de Compose porque esos secretos se declaran
*obligatorios*, y Compose valida una variable obligatoria en **cada archivo que
lee**, se haya seleccionado o no el servicio que la usa. Como perfil, rompería
`docker compose up` para todas las personas que nunca quisieron Authentik.

Notas sobre la pila, y en qué se diferencia de la oficial:

- **Authentik no necesita Redis.** Desde 2025.10 guarda las sesiones, la caché
  y su cola de tareas en PostgreSQL. El Redis propio del escáner es una caché
  sin persistencia y con política de desalojo, y sería lo último a lo que
  apuntarlo aunque lo necesitara.
- **PostgreSQL es `postgres:18.6-alpine`**, fijado y no flotante, e
  independiente de cualquier otra cosa que ejecute. Authentik en sí **no tiene
  imagen Alpine**: `ghcr.io/goauthentik/server` solo se publica basado en
  Debian, y no hay ninguna variante a la que cambiar.
- **El worker no recibe el socket de Docker.** La versión oficial lo monta para
  que el worker pueda gestionar contenedores outpost; esta pila no ejecuta
  ningún outpost, y dar a un contenedor el socket del daemon es darle el host.
- **El estado se guarda en volúmenes con nombre** (`authentik_database`,
  `authentik_media`, `authentik_templates`, `authentik_certs`) y no en montajes
  de directorios bajo `docker/`.
- **No monte `/etc/localtime` ni `/etc/timezone`** en estos contenedores.
  Authentik necesita UTC internamente, y montar una zona horaria rompe OAuth.

## Enviar correo {#sending-mail}

Configure SMTP antes de confiar en la recuperación de cuentas. Sin un servidor
de correo externo, los mensajes de recuperación se entregan localmente dentro
del contenedor y no llegan a los buzones de los usuarios.

Cada ajuste es una variable de `docker/.env`, y ambos servicios de Authentik
las leen: el servidor envía el mensaje de prueba y el worker envía todo lo
demás, así que, con solo uno configurado, unos mensajes se envían y otros no:

| Variable | Valor predeterminado | Qué es |
|:---------|:--------|:-----------|
| `AUTHENTIK_EMAIL_HOST` | *(vacío)* | El servidor de correo. Si está vacío, se mantiene la entrega local |
| `AUTHENTIK_EMAIL_PORT` | `587` | `587` para STARTTLS, `465` para TLS implícito, `25` para ninguno |
| `AUTHENTIK_EMAIL_USERNAME` | *(vacío)* | La cuenta con la que se autentica, si se autentica |
| `AUTHENTIK_EMAIL_PASSWORD` | *(vacío)* | La contraseña de esa cuenta |
| `AUTHENTIK_EMAIL_USE_TLS` | `true` | STARTTLS sobre una conexión sin cifrar |
| `AUTHENTIK_EMAIL_USE_SSL` | `false` | TLS desde el primer byte |
| `AUTHENTIK_EMAIL_TIMEOUT` | `10` | Segundos antes de rendirse |
| `AUTHENTIK_EMAIL_FROM` | `authentik@localhost` | La dirección `From:` que ven los destinatarios |

**`USE_TLS` y `USE_SSL` no son dos nombres para lo mismo, y nunca deben ser
ambos `true`.** STARTTLS empieza sin cifrar en el 587 y después se actualiza;
el TLS implícito está cifrado desde el primer byte en el 465. Activar ambos
deja una sesión que no negocia ninguno.

```bash
cat >> docker/.env <<'EOF'
AUTHENTIK_EMAIL_HOST=smtp.example.com
AUTHENTIK_EMAIL_PORT=587
AUTHENTIK_EMAIL_USERNAME=authentik@example.com
AUTHENTIK_EMAIL_PASSWORD=the-password
AUTHENTIK_EMAIL_USE_TLS=true
AUTHENTIK_EMAIL_USE_SSL=false
AUTHENTIK_EMAIL_FROM=authentik@example.com
EOF
docker compose -f docker-compose.authentik.yml up -d
```

`authentik-env.sh` escribe estos nombres comentados en `docker/.env`, para que
tenga la lista delante cuando la busque, y nunca descomenta ni sobrescribe lo
que haya puesto usted. Compruebe que funciona desde **System → Settings →
Email** en la interfaz de Authentik, que envía un mensaje de prueba a través
del contenedor del servidor, y lea el registro del worker para el resto:

```bash
docker compose -f docker-compose.authentik.yml logs -f authentik_worker
```

`docker/setup-wizard.py` pregunta todo esto cuando genera su propia pila, y
toma la contraseña de `AUTHENTIK_EMAIL_PASSWORD` en el entorno en lugar de una
opción: una contraseña en una línea de comandos es una contraseña en `ps` y en
el historial del shell.

## Qué ha creado el blueprint {#what-the-blueprint-created}

`authentik/blueprints/opencloud-scanner.yaml` se monta en ambos contenedores de
Authentik en `/blueprints/custom`, y el worker lo aplica al arrancar. Eso es lo
que convierte la configuración anterior en un solo comando en lugar de una
página de clics: el proveedor OAuth2, su clave de firma, sus ámbitos y la
aplicación cuyo slug se convierte en el emisor existen antes de que inicie
sesión por primera vez.

Aprovisiona **una sola vez**. Cada entrada es `state: created`, lo que
significa que Authentik crea lo que falta y después no lo toca: cambie después
una URI de redirección, un flujo o un ámbito en la interfaz de administración y
el cambio se mantiene. El blueprint no lo restablecerá en el siguiente
arranque.

Lo que crea, en **Applications → Applications**:

| | Valor |
|:--|:-----|
| **Aplicación** | `OpenCloud security scanner`, slug `opencloud-scanner` |
| **Proveedor** | `check-opencloud-security`, OAuth2/OpenID Connect, confidencial |
| **ID / secreto de cliente** | `AUTHENTIK_CLIENT_ID` y `AUTHENTIK_CLIENT_SECRET` de `.env` |
| **Tipos de concesión** | `authorization_code`, `refresh_token`, `client_credentials` |
| **Clave de firma** | `authentik Self-signed Certificate` |
| **Ámbitos** | `openid`, `profile`, `email`, `offline_access` |
| **Modo de emisor** | por proveedor |

Dos de esas filas merecen detenerse.

**La clave de firma es el ajuste más importante de esta página.** Con ella, los
tokens se firman de forma asimétrica y se verifican con el JWKS publicado.
*Sin* ella, Authentik firma con el secreto del cliente (HS256), y ningún
servidor de recursos puede verificar un token así sin recibir ese secreto, algo
que este servicio no acepta. El blueprint la define; si alguna vez vuelve a
crear el proveedor a mano, defínala también.

**El ID de cliente es la audiencia.** Está en `.env`, que es de donde la
aplicación web lo lee como `COS_WEB_MCP_AUTH_AUDIENCE`: ambas partes coinciden
porque leen la misma línea, así que no hay nada que copiar.

El modo de emisor por proveedor da:

| | Valor |
|:--|:-----|
| **Emisor** | `https://sso.example.com/application/o/opencloud-scanner/` |
| **Documento de descubrimiento** | `https://sso.example.com/application/o/opencloud-scanner/.well-known/openid-configuration` |
| **JWKS** | `https://sso.example.com/application/o/opencloud-scanner/jwks/` |
| **Punto de acceso de tokens** | `https://sso.example.com/application/o/token/` |

El punto de acceso de tokens no es por aplicación a propósito: Authentik lo
enruta por `client_id`. Los puntos de acceso de descubrimiento y JWKS son por
slug, y no hay ningún documento de descubrimiento en la raíz.

Lea el emisor del documento de descubrimiento en lugar de escribirlo a mano. Es
lo que llevarán realmente los tokens, y es el valor con el que compara el
escáner.

Un blueprint que falla **no** impide que Authentik arranque: registra el error
en la instancia del blueprint. Si `/mcp` rechaza todos los tokens en una pila
nueva, mire en **Customisation → Blueprints** antes que en ningún otro sitio.

Para hacerlo a mano (por ejemplo, en un Authentik que ya tenga en marcha), el
asistente de **Applications → Applications → Create with wizard** pide lo mismo
en el mismo orden, y la tabla anterior es la hoja de respuestas.

## Un segundo factor para todos {#a-second-factor-for-everybody}

`authentik/blueprints/opencloud-mfa.yaml` se monta con los demás y convierte un
segundo factor en parte de cada inicio de sesión. El flujo de autenticación
predeterminado de Authentik ya contiene una etapa que lo comprueba
(`default-authentication-mfa-validation`), pero viene configurada para
*omitir* las cuentas que no tienen ninguno, que en un directorio nuevo son
todas. El blueprint cambia esa misma etapa a *configurar*:

| | Valor |
|:--|:-----|
| **Cuenta sin factor** | Se la guía para registrar uno antes de completar el inicio de sesión |
| **Se ofrece** | TOTP (una aplicación de autenticación) y WebAuthn (una llave de seguridad o passkey) |
| **Se acepta después** | TOTP, WebAuthn y códigos de recuperación estáticos creados desde los ajustes del propio usuario |
| **Se vuelve a aplicar** | Cada hora (`state: present`), para que no se pueda desactivar en la interfaz y olvidarse |

### Lo que ve la persona {#what-the-person-sees}

1. **El primer inicio de sesión tras la contraseña** se detiene en
   *Configure an authenticator* y ofrece los dos tipos.
2. **Una aplicación de autenticación** (TOTP): escanee el código QR con
   cualquier aplicación de autenticación y escriba el código de seis cifras que
   muestra para confirmar.
3. **Una llave de seguridad o passkey** (WebAuthn): el navegador pide tocar la
   llave o usar la passkey del propio dispositivo, y le pone un nombre.
4. **Cada inicio de sesión posterior** pide un código o un toque después de la
   contraseña.
5. **Conviene crear los códigos de recuperación** enseguida: en los ajustes del
   propio usuario (el avatar y después **Settings → MFA Devices → Enroll →
   Static tokens**), Authentik muestra un conjunto de códigos de un solo uso.
   Guárdelos donde no esté el teléfono.

Desde la misma página se puede registrar más de un factor, y un segundo
dispositivo (una llave además de una aplicación) es la recuperación más barata
que hay.

### Cómo se aplica {#how-it-is-enforced}

Cambia la propia etapa del flujo predeterminado en lugar de vincular una
segunda, así que a una persona con autenticador se le pregunta una vez, no dos.
Para quitar el requisito, elimine el archivo del directorio de blueprints; la
etapa conserva su último ajuste hasta que lo cambie.

Hay dos cosas que no toca. Los **agentes** que usan `client_credentials` se
autentican con una contraseña de aplicación y nunca ejecutan un flujo, así que
un token para `/mcp` no necesita ningún código del teléfono de nadie. Y un
**autenticador perdido** lo recupera un administrador: inicie sesión como
`akadmin`, abra **Directory → Users** y borre el dispositivo de la persona en
*MFA Authenticators*; su siguiente inicio de sesión registra uno nuevo.

## Cuentas sin la interfaz de administración {#accounts-without-the-admin-interface}

Una pila escrita por `docker/setup-wizard.py` va un paso más allá, y nadie crea
ninguna cuenta a mano. El asistente pregunta **quién inicia sesión**, por
nombre de usuario (todas las personas de la lista de operadores,
`COS_WEB_ADMIN_USERS`, están incluidas aunque no se repitan) y escribe tres
cosas:

| Dónde | Qué |
|:------|:-----|
| `.env` | `AUTHENTIK_ENROLLMENT_TOKEN`, un UUID aleatorio, y `AUTHENTIK_BOOTSTRAP_PASSWORD` para `akadmin` |
| El archivo compose | `COS_AUTHENTIK_ACCOUNTS`, los nombres de usuario, y `COS_WEB_ADMIN_USERS`, para ambos contenedores de Authentik |
| `authentik/blueprints/` | `opencloud-enrollment.yaml` y `opencloud-mfa.yaml`, junto a los otros dos |

y termina imprimiendo un enlace:

```
https://sso.example.com/if/flow/opencloud-scanner-enrollment/?itoken=<AUTHENTIK_ENROLLMENT_TOKEN>
```

El token es una credencial, así que el asistente imprime el marcador en lugar
del valor y, a su lado, el comando que compone el enlace real a partir de
`.env`:

```
echo "https://sso.example.com/if/flow/opencloud-scanner-enrollment/?itoken=$(sed -n 's/^AUTHENTIK_ENROLLMENT_TOKEN=//p' .env)"
```

Cada persona indicada lo abre, escribe su nombre de usuario, una dirección de
correo y una contraseña, registra una aplicación de autenticación o una llave
de seguridad, y queda con la sesión iniciada. Quien está en la lista de
operadores acaba, de paso, en `opencloud-scanner-operators`, el grupo al que
está vinculado `/admin`. No se hace ningún clic en Authentik, ni por su parte
ni por la de usted.

El enlace es una puerta de entrada, así que lo limitan tres cosas:

- **Solo los nombres de la lista.** Un nombre de usuario que no esté en
  `COS_AUTHENTIK_ACCOUNTS` se rechaza en el formulario, y una lista vacía no
  admite a nadie.
- **Cada nombre una vez.** El campo de nombre de usuario rechaza un nombre que
  ya existe, así que un nombre ya registrado no se puede volver a reclamar, y
  el enlace deja de servir cuando todas las personas de la lista lo han usado.
- **Solo con el token.** Sin él, o con cualquier otro, el flujo responde
  *access denied* antes de mostrar ningún campo.

Trátelo como una contraseña hasta que todo el mundo lo haya usado. Para añadir
a alguien más adelante, vuelva a ejecutar el asistente, añada el nombre y envíe
el mismo enlace; para retirar el enlace, sustituya
`AUTHENTIK_ENROLLMENT_TOKEN` en `.env` por un UUID nuevo y reinicie los
contenedores de Authentik, y la invitación se vuelve a aplicar con el nuevo
token. Una persona que se detiene tras la contraseña y antes del segundo factor
ya tiene cuenta: al iniciar sesión normalmente se la guía para registrar el
factor.

**`akadmin` se reserva para la recuperación.** `AUTHENTIK_BOOTSTRAP_PASSWORD`
le da una contraseña aleatoria en el primer arranque, lo que además cierra el
flujo `/if/flow/initial-setup/`; de lo contrario, la primera persona que
llegara a él se convertiría en administradora. También a `akadmin` se le pide
registrar un segundo factor en su primer inicio de sesión. La variable no tiene
efecto en una base de datos que ya tiene `akadmin`.

`docker-compose.authentik.yml`, ejecutado a mano, monta también el blueprint de
registro pero no tiene token, así que no se crea ninguna invitación y el flujo
no se puede usar; ahí las cuentas se crean como se describe en
[añadir a alguien](#adding-somebody-who-may-use-the-endpoint).

`--non-interactive` no imprime el enlace, porque no imprime nada; constrúyalo a
partir de la dirección pública de Authentik y de `AUTHENTIK_ENROLLMENT_TOKEN`
en `.env`, como muestra el comentario del principio del archivo compose
generado.

## Un operador para /admin {#an-operator-for-admin}

El área de operación necesita que dos cosas coincidan respecto a una persona, y
están a lados distintos de la autenticación delegada:

| Dónde | Qué decide |
|:------|:----------------|
| Authentik: pertenencia a `opencloud-scanner-operators` | Si el inicio de sesión puede llegar a `scan.example.com`. La aplicación `/admin` está vinculada a ese grupo, así que Authentik detiene a quien no pertenezca a él |
| El servicio de análisis: `COS_WEB_ADMIN_USERS` | Si el nombre de usuario que reenvía el outpost es operador de *este* despliegue |

Una persona necesita ambas: el mismo nombre de usuario en el grupo y en la
lista. Lo que sigue es el mismo resultado alcanzado de dos formas, y la
comprobación del final se aplica a cualquiera de ellas.

### Con el asistente {#with-the-wizard}

Ejecute `docker/setup-wizard.py`, active el área de operación y responda:

- **la lista de operadores** (`admin_users`) con el nombre de usuario, por
  ejemplo `scanokko`;
- **quién inicia sesión** (`authentik_accounts`): la lista de operadores se
  añade de todos modos, así que no hay que repetir nada.

Levante la pila, construya el enlace de registro a partir de `.env` con el
comando que imprimió el asistente (consulte
[cuentas sin la interfaz de administración](#accounts-without-the-admin-interface))
y envíeselo a esa persona. La persona lo abre y:

1. escribe el nombre de usuario exactamente como figura en la lista de
   operadores, una dirección de correo y una contraseña;
2. registra un segundo factor: escanea el código QR con una aplicación de
   autenticación o registra una llave de seguridad o passkey (consulte
   [lo que ve la persona](#what-the-person-sees));
3. queda con la sesión iniciada y ya pertenece a
   `opencloud-scanner-operators`.

Después puede abrir `https://scan.example.com/admin`. Para añadir un operador
más adelante, vuelva a ejecutar el asistente contra el mismo directorio, añada
el nombre a la lista de operadores, reinicie los contenedores de Authentik para
que lean la nueva lista y envíe el mismo enlace.

### A mano, en la interfaz de Authentik {#by-hand-in-the-authentik-interface}

Para una cuenta que ya existía antes de añadirla a la lista de operadores, una
base de datos en la que nunca se ejecutó el flujo de registro, o un Authentik
que gestione usted mismo.

**1. Entre como `akadmin`.** En una pila escrita por el asistente, la
contraseña es `AUTHENTIK_BOOTSTRAP_PASSWORD` de `.env`, pero solo si la base de
datos la creó esa pila. La variable se aplica en el primer arranque y se ignora
en una base de datos que ya tiene `akadmin`, así que un `.env` regenerado junto
a un volumen más antiguo tiene una contraseña que nada acepta. Genere en su
lugar un acceso de un solo uso:

```bash
docker compose exec authentik_worker ak create_recovery_key 10 akadmin
```

Imprime una ruta, válida durante diez minutos. Ábrala en la dirección pública
de Authentik (`https://sso.example.com` seguido de esa ruta) y habrá iniciado
sesión como `akadmin` sin contraseña; defina una en los ajustes de usuario. El
primer inicio de sesión pide a `akadmin` que registre un segundo factor, como a
todo el mundo.

**2. Cree la persona.** **Directory → Users → New User → Internal User**. El
nombre de usuario debe escribirse exactamente como está en
`COS_WEB_ADMIN_USERS`: el servicio compara el nombre reenviado, no el correo ni
el nombre visible. Asígnele una dirección de correo, para que una recuperación
de contraseña tenga adónde ir.

**3. Dele una contraseña.** En la página del usuario, **Set password**, o mejor
**Email recovery link** si el [correo](#sending-mail) está configurado, o
**Create recovery link** para entregar el enlace por otra vía. Un enlace
significa que la contraseña nunca pasa por su portapapeles.

**4. Añádala al grupo.** En la página del usuario, **Groups → Add to existing
group → `opencloud-scanner-operators`**. O desde el grupo:
**Directory → Groups → opencloud-scanner-operators → Users → Add existing
user**. No marque *Superuser* en ningún sitio: un superusuario de Authentik
administra Authentik, que no es lo que significa ser operador del escáner.

**5. La persona inicia sesión.** Abre `https://scan.example.com/admin`, se la
envía a Authentik, inicia sesión, registra un segundo factor y se la devuelve.

Los pasos 2 y 4 también se pueden hacer desde un shell, cada comando en una
sola línea tal como está escrito, porque `ak shell -c` ejecuta la cadena como
un script y una sangría pegada es un error de sintaxis:

```bash
# Create the account with no usable password; hand them a recovery link after.
docker compose exec authentik_worker ak shell -c "from authentik.core.models import User; u = User(username='scanokko', email='scanokko@example.com', name='scanokko'); u.set_unusable_password(); u.save(); print('CREATED')" 2>&1 | grep -E 'CREATED|Error'
docker compose exec authentik_worker ak create_recovery_key 60 scanokko

# Put it in the operator group.
docker compose exec authentik_worker ak shell -c "from authentik.core.models import Group, User; Group.objects.get(name='opencloud-scanner-operators').users.add(User.objects.get(username='scanokko')); print('ADDED')" 2>&1 | grep -E 'ADDED|Error|DoesNotExist'
```

El enlace de recuperación de `create_recovery_key` es la forma en que esa
persona define su propia contraseña; caduca tras los minutos indicados.

### Comprobarlo {#checking-it}

La pertenencia al grupo es la parte que falla en silencio: la persona inicia
sesión y Authentik muestra un error en lugar de devolverla:

```bash
docker compose exec authentik_worker ak shell -c "from authentik.core.models import Group; g = Group.objects.get(name='opencloud-scanner-operators'); print('IN_GROUP', g.users.filter(username='scanokko').exists())" 2>&1 | grep -E 'IN_GROUP|Error|DoesNotExist'
```

Pruebe también el caso negativo: una cuenta que *no* está
en el grupo debe recibir el error de Authentik, no el área. **Events → Logs**
registra cada rechazo con la cuenta y la aplicación que se le denegó.

## Apuntar el escáner a él {#pointing-the-scanner-at-it}

La pila anterior lo hace por usted: los valores siguientes ya están en
`docker-compose.authentik.yml`, leídos de `.env`. Esta sección sirve para
apuntar el servicio a un Authentik, o a cualquier otro proveedor, que ya tenga
en marcha. En `web_app`, en `docker/docker-compose.yml` o en `docker/.env`:

```yaml
COS_WEB_PUBLIC_BASE_URL: "https://scanner.example.com"
COS_WEB_MCP_AUTH_ENABLED: "true"
COS_WEB_MCP_AUTH_ISSUER: "https://sso.example.com/application/o/opencloud-scanner/"
COS_WEB_MCP_AUTH_AUDIENCE: "<the provider's client ID>"
```

| Ajuste | Significado |
|:--------|:--------|
| `COS_WEB_MCP_AUTH_ENABLED` | Si `/mcp` exige un token. Desactivado por defecto |
| `COS_WEB_MCP_AUTH_ISSUER` | El emisor, exactamente como lo escribe el documento de descubrimiento. Se acepta con o sin barra final |
| `COS_WEB_MCP_AUTH_AUDIENCE` | Lo que debe contener el `aud` de un token. En Authentik es el ID de cliente. **Obligatorio** siempre que el inicio de sesión esté activado |
| `COS_WEB_MCP_AUTH_JWKS_URL` | Solo cuando las claves no están en `<issuer>/jwks/` |
| `COS_WEB_MCP_AUTH_RESOURCE_URL` | Solo cuando `/mcp` no está en `<public base URL>/mcp` |
| `COS_WEB_MCP_AUTH_SCOPES` | Ámbitos que debe llevar un token, separados por `;`. Vacío significa que basta con cualquier token válido de ese emisor |

Cuatro configuraciones erróneas **impiden el arranque** en lugar de servir
`/mcp` abierto, porque un operador que cree que el punto de acceso está
protegido cuando no lo está es el peor resultado posible aquí:

- autenticación activada sin emisor: no habría nada con qué comparar;
- autenticación activada sin URL base pública ni URL de recurso: el 401 indica
  esa URL y los metadatos de la RFC 9728 se publican debajo de ella, así que
  adivinarla enviaría a todos los clientes a otro lugar;
- una URL de recurso que no es ni HTTPS ni loopback: un token bearer en un
  tramo sin cifrar es una credencial en claro;
- autenticación activada sin audiencia; véase más abajo.

Pedir autenticación mientras `COS_WEB_ENABLE_MCP` es `false` *no* es un error.
Desactivar el punto de acceso es una forma perfectamente válida de protegerlo,
y hacer que la configuración más segura sea la que no arranca solo enseñaría a
la gente a desactivar la protección.

**La audiencia es obligatoria.** Un Authentik que sirve a más aplicaciones que
esta emite tokens para todas ellas, con el mismo emisor y la misma clave de
firma, así que un `aud` que nunca se compara convierte cada uno de esos tokens
en una llave de `/mcp`, incluido uno emitido para una aplicación que puede usar
cualquiera del directorio. Dejar `COS_WEB_MCP_AUTH_AUDIENCE` vacío detiene por
tanto el servicio en lugar de ampliar el acceso, y un token sin ningún `aud`
se rechaza por el mismo motivo. La pila de
`docker/docker-compose.authentik.yml` lo define a partir de
`AUTHENTIK_CLIENT_ID` y no arranca sin él.

## Añadir a alguien que pueda usar el punto de acceso {#adding-somebody-who-may-use-the-endpoint}

**Lea esto antes de que otras personas puedan acceder a la pila.** El blueprint
aprovisiona un proveedor y una aplicación, y una aplicación sin vinculaciones
la puede usar **cualquier** cuenta de este Authentik. En una pila que existe
para proteger `/mcp`, eso suele estar bien el primer día, cuando la única
cuenta es el `akadmin` creado en el primer arranque, y rara vez el segundo.

Al servicio de análisis no le llega nada sobre *quién* es quien llama.
Comprueba una firma, un emisor, una audiencia, una caducidad y los ámbitos que
se le haya indicado exigir; nunca mira el sujeto, el nombre de usuario ni un
claim de grupo, y no tiene ninguna tabla de usuarios en la que buscarlos. Quién
puede tener un token es, por tanto, una decisión exclusiva de Authentik, que se
toma en los dos pasos siguientes, y es el único lugar donde existe esa
decisión.

### Un grupo, y la vinculación que le da sentido {#a-group-and-the-binding-that-makes-it-mean-something}

Hágalo una vez, antes del primer usuario. Una vinculación a un grupo es una
cosa que revisar más adelante; las vinculaciones por persona se acumulan y
rara vez se depuran.

1. **Directory → Groups → Create**. Llámelo `opencloud-scanner`. Deje
   desactivado *Superuser privileges*: este grupo trata de una aplicación, y un
   superusuario de Authentik es un administrador de Authentik.
2. **Applications → Applications → OpenCloud security scanner**, pestaña
   **Policy / Group / User Bindings**, **Bind existing Group/User**.
3. Elija el grupo, deje el modo del motor de políticas en **any** y créela.

A partir de ese momento la aplicación queda cerrada para quien no esté en el
grupo, y una solicitud de token de cualquier otra persona falla en Authentik y
no en `/mcp`. El fallo se registra en **Events → Logs** como una autorización
denegada, que es la página que hay que consultar cuando alguien jura que su
contraseña es correcta.

Pruebe el caso negativo en lugar de darlo por hecho: una cuenta fuera del grupo
*no* debe poder obtener un token. Una aplicación que parece vinculada pero no
lo está es el único fallo que merece dos minutos de atención.

### La persona {#the-person}

**Directory → Users → New User → Internal User.** El nombre de usuario y el
correo son los dos campos que importan; el correo es adonde va una
recuperación de contraseña, así que una cuenta sin él solo puede recuperarla un
administrador.

Después, en la página del usuario:

- **Set password**, o **Email recovery link** si ha configurado el
  [correo](#sending-mail); lo segundo es mejor costumbre, porque significa que
  la contraseña nunca estuvo en su portapapeles, en su terminal ni en el
  mensaje de chat con el que la envió. **Create recovery link** genera el mismo
  enlace para entregarlo por otra vía cuando no hay servidor de correo.
- **Groups → Add to existing group** → `opencloud-scanner`.

Quien inicia sesión desde un navegador no necesita nada más: su cliente MCP
lo lleva por Authentik, inicia sesión y el cliente obtiene un token. No hay que
copiar nada, y no hay ninguna configuración por usuario en el lado del
escáner.

**Ya se exige un segundo factor.** A la persona se la guía para registrarlo en
su primer inicio de sesión (consulte
[un segundo factor para todos](#a-second-factor-for-everybody)), así que no hay
nada que activar para ella.

### El agente que no es nadie {#the-agent-that-is-nobody}

Una tarea de cron, una canalización de CI o un asistente que se ejecuta en un
servidor no tiene navegador por el que pasar, y no debería tener la contraseña
de una persona. Recibe una **cuenta de servicio**: una cuenta con credenciales
y sin inicio de sesión.

**Directory → Users → New User → Service Account.** La pantalla de
confirmación muestra el nombre de usuario y una **contraseña de aplicación**,
una sola vez: esa cadena es la credencial, y no hay una segunda oportunidad de
leerla. Añada la cuenta a `opencloud-scanner` igual que a una persona, porque a
una vinculación no le importa qué tipo de cuenta es; *Create group* en el
formulario hace lo equivalente en sentido contrario si prefiere vincular una
cuenta por separado.

Hay dos detalles que conviene anotar en el momento en lugar de descubrirlos
después. La contraseña de aplicación **caduca a los 360 días** salvo que
desmarque *Expiring*, así que un agente que ha funcionado todo el año es un
agente que se detiene sin motivo visible: emita una nueva desde **Directory →
Tokens and App passwords** antes de esa fecha. Y una cuenta de servicio no
puede usar la interfaz de administración ni la de usuario, que es justamente la
idea: tiene credenciales y no tiene inicio de sesión.

Dé una a cada llamante en lugar de compartir una. No cuestan nada, y así
puede revocar una sola sin afectar a las demás.

## Obtener un token {#getting-a-token}

La credencial que usa quien llama depende de qué es, y las tres terminan en el
mismo punto de acceso de tokens:

| Quien llama | Qué presenta | De dónde procede la credencial |
|:-----------|:-----------------|:--------------------------------|
| Una persona ante un teclado | El flujo de código de autorización, en un navegador | Su propia contraseña y su segundo factor |
| Un agente que actúa en nombre de una persona | El nombre de usuario de esa persona y una contraseña de aplicación | **Directory → Tokens and App passwords** |
| Un agente que no actúa en nombre de nadie | El nombre de usuario y la contraseña de aplicación de una cuenta de servicio | Se muestra una vez al crear la cuenta de servicio |

Para una cuenta de servicio indicada explícitamente, use su nombre de usuario y
su contraseña de aplicación junto con el ID y el secreto de cliente del
proveedor. Authentik admite también la solicitud solo con el cliente que se
describe más abajo, que crea una cuenta de servicio compartida. Elija una
cuenta distinta por llamante cuando necesite revocaciones individuales.

### Como cuenta de servicio {#as-a-service-account}

El caso habitual para un agente, y el que conviene usar:

```bash
curl -s https://sso.example.com/application/o/token/ \
  -d grant_type=client_credentials \
  -d client_id="$AUTHENTIK_CLIENT_ID" \
  -d client_secret="$AUTHENTIK_CLIENT_SECRET" \
  -d username="scanner-agent" \
  -d password="$APP_PASSWORD" \
  -d scope="openid" | jq -r .access_token
```

`username` es la cuenta de servicio, `password` es su contraseña de aplicación,
y `client_id` y `client_secret` son los del proveedor, tal cual de
`docker/.env`. Pida los ámbitos que exija el despliegue; `openid` basta
mientras `COS_WEB_MCP_AUTH_SCOPES` esté vacío, que es el valor predeterminado.

Para un cliente al que solo se le puede dar un secreto, lo mismo con el nombre
de usuario incorporado:

```bash
curl -s https://sso.example.com/application/o/token/ \
  -d grant_type=client_credentials \
  -d client_id="$AUTHENTIK_CLIENT_ID" \
  -d client_secret="$(printf '%s:%s' scanner-agent "$APP_PASSWORD" | base64 -w0)" \
  -d scope="openid" | jq -r .access_token
```

### Sin nombrar ninguna cuenta {#without-naming-an-account-at-all}

Si omite el nombre de usuario y envía solo el ID y el secreto de cliente del
proveedor, Authentik emite el token para una cuenta de servicio que crea con
ese fin, llamada `ak-check-opencloud-security-client_credentials`:

```bash
curl -s https://sso.example.com/application/o/token/ \
  -d grant_type=client_credentials \
  -d client_id="$AUTHENTIK_CLIENT_ID" \
  -d client_secret="$AUTHENTIK_CLIENT_SECRET" \
  -d scope="openid" | jq -r .access_token
```

Es el camino más corto hacia un token que funcione y el adecuado para probar el
punto de acceso. No conviene dejarlo así: todos los llamantes que lo usan son
la misma cuenta, así que revocar uno los revoca a todos, y la credencial en la
que se basa es el secreto del proveedor que también lee el servicio de
análisis. En cuanto exista la vinculación anterior, recuerde añadir también esa
cuenta generada al grupo, o esto dejará de funcionar, que es el resultado
correcto y el momento de pasar a una cuenta de servicio propia.

### Como persona {#as-a-person}

Un cliente MCP que implementa el flujo OAuth solo necesita la URL: recibe el
`401`, lee `/.well-known/oauth-protected-resource/mcp`, encuentra Authentik,
abre un navegador y vuelve con un token. El blueprint ya permite la
redirección a loopback que usa un cliente así
(`http://127.0.0.1:<port>/...`, solo en 127.0.0.1), y el flujo de autorización
es el de consentimiento implícito, así que no hay pantalla de consentimiento
entre iniciar sesión y quedar conectado.

Si un cliente pide registrarse, regístrelo a mano en **Applications →
Providers**: Authentik admite el registro dinámico de clientes, pero está
desactivado por defecto y protegido por un token de registro.

### Leer el token obtenido {#reading-the-token-you-got}

Antes de preguntarse por qué `/mcp` rechaza uno, mire qué contiene:

```bash
python -c 'import base64,json,sys;p=sys.argv[1].split(".")[1];print(json.dumps(json.loads(base64.urlsafe_b64decode(p+"="*(-len(p)%4))),indent=2))' "$TOKEN"
```

| Claim | Qué debe ser |
|:------|:----------------|
| `iss` | `COS_WEB_MCP_AUTH_ISSUER`, con o sin la barra final |
| `aud` | Contiene `COS_WEB_MCP_AUTH_AUDIENCE`, que es el ID de cliente |
| `exp` | En el futuro; la duración predeterminada del token de acceso en Authentik es de minutos, no de días |
| `scope` | Contiene todo lo de `COS_WEB_MCP_AUTH_SCOPES`, si hay algo definido |
| `sub` | Lo que haya decidido Authentik. **El servicio de análisis no lo lee** |

Después úselo, que es el único paso en el que interviene este servicio:

```bash
curl -s https://scanner.example.com/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Una lista de herramientas significa que toda la cadena funciona. Un `401`
significa que el token no se aceptó, y la cabecera de esa respuesta indica el
documento que explica por qué. Un token, una vez emitido, vale hasta que
caduca: emita uno por ejecución, no uno por solicitud.

Authentik siempre emite tokens de acceso JWT, se pidan como se pidan, así que
nunca hay una cadena opaca que inspeccionar y el servicio de análisis nunca
tiene que preguntarle nada a Authentik.

## Configurar un agente {#configuring-an-agent}

La mayoría de los clientes MCP aceptan una cabecera estática, que es lo más
sencillo que funciona:

```json
{
  "servers": {
    "opencloud-scan": {
      "type": "http",
      "url": "https://scanner.example.com/mcp",
      "headers": { "Authorization": "Bearer ${input:token}" }
    }
  }
}
```

Un cliente que implementa la especificación de autorización de MCP no necesita
más configuración que la URL: recibirá el 401, leerá
`/.well-known/oauth-protected-resource/mcp`, encontrará Authentik y guiará al
usuario por el flujo. Authentik admite el registro dinámico de clientes, pero
está desactivado por defecto y protegido por un token de registro, así que
registrar el cliente a mano en la interfaz de administración es el camino que
siempre funciona.

Consulte [la guía de MCP](../mcp.md) para los archivos de configuración de cada
cliente; lo único que se añade aquí es la cabecera.

## El borrado, que es otra credencial {#erasure-which-is-a-different-credential}

`erase_instance_data` necesita la credencial de purga del operador,
`COS_WEB_PURGE_TOKEN`, y eso nunca ha sido lo mismo que una identidad. Con el
punto de acceso abierto, viaja en `Authorization`, porque nada más usa esa
cabecera.

**Con un inicio de sesión configurado, `Authorization` pertenece al proveedor
de identidad, y la credencial de purga pasa a `X-Purge-Authorization`.** No se
mantiene el comportamiento anterior, para que el token de identidad de
un agente nunca se lea como una credencial de operador.

```json
"headers": {
  "Authorization": "Bearer ${input:token}",
  "X-Purge-Authorization": "Bearer ${input:purge_token}"
}
```

Ninguna de las dos llega nunca al modelo: la herramienta las toma de las
cabeceras de la solicitud, nunca como argumento.

## Detrás de un proxy inverso {#behind-a-reverse-proxy}

Dos hosts, dos requisitos.

**Authentik construye el emisor a partir de la cabecera `Host` que recibe.** Un
proxy que la reescribe da a cada token un `iss` que se rechaza, y el
síntoma confunde porque todo lo demás funciona. Reenvíe `Host` y
`X-Forwarded-Proto` sin cambios, y añada la dirección de salida del proxy a
`AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS` si está fuera de los rangos privados.
Authentik no puede ejecutarse bajo una subruta; dele un nombre de host.

Defina `COS_WEB_PUBLIC_BASE_URL` con la dirección pública del escáner para los
metadatos del recurso. La audiencia del token se configura por separado con
`COS_WEB_MCP_AUTH_AUDIENCE`. La
[guía de proxies inversos](../reverse-proxy.md) incluye configuraciones que
funcionan.

## Copia de seguridad {#backing-it-up}

**Authentik no tiene copia de seguridad integrada.** La que tenía se eliminó
hace años, así que es tarea suya. Importan cuatro cosas, y las dos primeras son
las que hacen posible una restauración:

| Qué | Dónde | Por qué |
|:-----|:------|:----|
| `AUTHENTIK_SECRET_KEY` | `docker/.env` | Firma todo lo que hay en la base de datos. Con otra clave, una base de datos restaurada es inutilizable |
| PostgreSQL | el volumen `authentik_database` | Usuarios, grupos, flujos, políticas, proveedores, tokens, certificados. Perderlo es perderlo todo |
| Medios | el volumen `authentik_media` | Iconos y fondos subidos |
| Certificados y plantillas | `authentik_certs`, `authentik_templates` | Solo si ha puesto ahí algo que no esté en la base de datos |

```bash
cd docker
stack="-f docker-compose.authentik.yml"
stamp=$(date +%F)

# The database, as SQL, with the drop-and-create statements a clean restore
# needs.
docker compose $stack exec -T authentik_postgresql \
  pg_dump -U authentik -d authentik --clean --create \
  > "authentik-db-$stamp.sql"

# The volumes that are not the database.
for volume in media templates certs; do
  docker run --rm \
    -v "$(basename "$PWD")_authentik_$volume:/from:ro" \
    -v "$PWD:/to" alpine \
    tar czf "/to/authentik-$volume-$stamp.tar.gz" -C /from .
done

# And the secrets, without which none of the above is worth anything.
cp .env "authentik-env-$stamp.backup"
```

Los nombres de los volúmenes llevan como prefijo el nombre del proyecto
Compose, que es el nombre del directorio salvo que defina
`COMPOSE_PROJECT_NAME`. `docker volume ls` le indicará cómo se llaman
realmente.

La copia de seguridad contiene credenciales y claves de firma. Cífrela,
guarde una copia fuera del host y pruebe una restauración con la versión de base
de datos y el `.env` correspondientes.

## Restauración {#restoring-it}

```bash
cd docker
stack="-f docker-compose.authentik.yml"

# The secret key first, and it must be the one that was in use when the dump
# was taken.
cp authentik-env-2026-08-21.backup .env

docker compose $stack down
docker compose $stack up -d authentik_postgresql

docker compose $stack exec -T authentik_postgresql \
  psql -U authentik -d postgres < authentik-db-2026-08-21.sql

for volume in media templates certs; do
  docker run --rm \
    -v "$(basename "$PWD")_authentik_$volume:/to" \
    -v "$PWD:/from:ro" alpine \
    tar xzf "/from/authentik-$volume-2026-08-21.tar.gz" -C /to
done

docker compose $stack up -d
```

No se admite restaurar en otra versión mayor; restaure en la versión que creó
el volcado y actualice después.

En el lado del escáner no hay nada que restaurar. No guarda ningún estado sobre
el proveedor más allá de los ajustes del archivo compose, y las claves de firma
se vuelven a descargar en la primera solicitud.

## Cuando no funciona {#when-it-does-not-work}

| Síntoma | Causa |
|:--------|:------|
| El servicio se niega a arrancar mencionando `ISSUER`, `RESOURCE_URL` o `HTTPS` | Exactamente lo que dice; consulte [apuntar el escáner a él](#pointing-the-scanner-at-it) |
| Todas las solicitudes reciben 401 y el token parece correcto | El `iss` del token no coincide con `COS_WEB_MCP_AUTH_ISSUER`. Normalmente es el proxy que reescribe `Host`, o un slug de aplicación distinto del que creía |
| Todas las solicitudes reciben 401 y `iss` es correcto | `aud` no contiene la audiencia. En Authentik es el ID de cliente, no el nombre de la aplicación |
| 401 al cabo de un rato, después de haber funcionado | El token ha caducado. Los tokens de acceso son de corta duración por diseño; el cliente debe renovarlo |
| 401 y el token tiene `"alg": "HS256"` | El proveedor no tiene clave de firma. Defina una y emita un token nuevo: un token firmado de forma simétrica no se puede verificar sin el secreto del cliente, y este servicio no lo acepta |
| 401 y todo parece correcto | Falta en el claim `scope` del token un ámbito exigido por `COS_WEB_MCP_AUTH_SCOPES` |
| Cualquiera con una cuenta de Authentik puede obtener un token | La aplicación no tiene vinculaciones, y eso significa todo el mundo. Consulte [añadir a alguien que pueda usar el punto de acceso](#adding-somebody-who-may-use-the-endpoint) |
| La propia solicitud de token se rechaza, antes de llegar a `/mcp` | La cuenta no está vinculada a la aplicación. **Events → Logs** lo registra como autorización denegada, indicando la cuenta |
| Funcionaba hasta que se añadió una vinculación de grupo, usando solo el secreto del cliente | Esa vía se ejecuta como la cuenta de servicio que generó Authentik, `ak-check-opencloud-security-client_credentials`, que tampoco está en el grupo. Añádala, o pase a una cuenta de servicio propia |
| `invalid_grant` en una solicitud `client_credentials` | El `password` es una **contraseña de aplicación**, no la contraseña de inicio de sesión del usuario ni un token de API. Cree una en **Directory → Tokens and App passwords** |
| El enlace de registro responde *access denied* | El token no es el de `.env`, o la pila se inició sin `AUTHENTIK_ENROLLMENT_TOKEN`. Busque `check-opencloud-security - enrollment` en **Customisation → Blueprints** |
| "This username is not one this invitation was issued for." | El nombre no está en `COS_AUTHENTIK_ACCOUNTS`. Vuelva a ejecutar el asistente y añádalo; la lista se lee al enviar el formulario, tras reiniciar los contenedores de Authentik |
| "Username is already taken." en el enlace de registro | Ese nombre ya se ha registrado. Inicie sesión normalmente |
| Alguien ha perdido su autenticador | Inicie sesión como `akadmin` (contraseña `AUTHENTIK_BOOTSTRAP_PASSWORD` de `.env`) y borre su dispositivo en **Directory → Users** |
| `AUTHENTIK_BOOTSTRAP_PASSWORD` se rechaza para `akadmin` | La base de datos es anterior a ese `.env`: la variable solo se aplica en el primer arranque. `docker compose exec authentik_worker ak create_recovery_key 10 akadmin` imprime un acceso de un solo uso; consulte [un operador para /admin](#by-hand-in-the-authentik-interface) |
| El inicio de sesión en `/admin` funciona en Authentik, que muestra un error en lugar de devolverle | La cuenta no está en `opencloud-scanner-operators`. Consulte [comprobarlo](#checking-it) |
| La cuenta está en el grupo de Authentik y `/admin` sigue rechazándola | El nombre de usuario no está en `COS_WEB_ADMIN_USERS`, o está escrito de otra forma |
| `password authentication failed for user "authentik"` en el registro de Authentik | `AUTHENTIK_PG_PASS` en `.env` no es la contraseña con la que se creó el volumen de la base de datos: PostgreSQL solo lee `POSTGRES_PASSWORD` al inicializar un volumen vacío. Restablezca el valor anterior, o cambie la contraseña del usuario de la base de datos a la nueva con `ALTER USER authentik WITH PASSWORD '...'` mediante `docker compose exec authentik_postgresql psql -U authentik` |
| El correo de recuperación de contraseña nunca llega | No hay servidor de correo, así que Authentik lo entregó localmente. Consulte [enviar correo](#sending-mail) |
| No hay `WWW-Authenticate` en el 401 | Algo situado delante la elimina. La cabecera es la forma en que un cliente encuentra el proveedor |
| El punto de acceso está abierto cuando no debería | `COS_WEB_MCP_AUTH_ENABLED` no llegó al contenedor. `/.well-known/ai.json` indica lo que cree realmente el servicio: `mcp.authentication.type` |
| 401, y el registro dice que no se pudo descargar el JWKS | La URL se resuelve, pero Authentik responde **404**. Un nombre de servicio de Compose con guion bajo no es un nombre de host válido, y Authentik lo rechaza; use el alias `authentik-server`, que es lo que hace la pila incluida |
| El blueprint nunca aparece en **Customisation → Blueprints** | Authentik lo lee con el uid 1000. Un directorio `authentik/blueprints` que no es legible por todos (un `umask` restrictivo al clonar el repositorio) se omite en silencio. `chmod 755 authentik/blueprints && chmod 644 authentik/blueprints/*.yaml` |
| El contenedor de la base de datos no está sano y se queja de `/var/lib/postgresql/data` | PostgreSQL 18 se monta un nivel más arriba, en `/var/lib/postgresql`, y rechaza la ruta antigua en lugar de ignorarla. Un volumen de una pila 16 o 17 tiene que pasar por `pg_upgrade`, no volver a montarse |
| Alguno de los contenedores de Authentik termina con `Address family not supported by protocol` | El host no tiene IPv6, y Authentik escucha en `[::]` por defecto. Las tres variables `AUTHENTIK_LISTEN__*` de la pila incluida lo fijan a IPv4, incluida `__METRICS`, que es la que se olvida con facilidad y basta por sí sola para que falle el worker |

Conviene comprobar esto último después de cada cambio:

```bash
curl -s https://scanner.example.com/.well-known/ai.json | jq .mcp.authentication
curl -s https://scanner.example.com/.well-known/oauth-protected-resource/mcp | jq
curl -si https://scanner.example.com/mcp -X POST -d '{}' | grep -i www-authenticate
```

## Usar un proveedor que no sea Authentik {#using-a-provider-that-is-not-authentik}

Nada de esto es específico de Authentik. Funciona cualquier proveedor que emita
tokens de acceso JWT firmados y publique un JWKS: Keycloak, Zitadel, Authelia,
Auth0, Okta. Defina el emisor como indique su documento de descubrimiento, la
audiencia como lo que ponga en `aud` y, si publica sus claves en otro lugar
distinto de `<issuer>/jwks/`, defina `COS_WEB_MCP_AUTH_JWKS_URL` con esa
dirección. Solo se aceptan algoritmos asimétricos (RS256, RS384, RS512, ES256,
ES384, ES512), lo que excluye `HS256` y, sobre todo, `none`.

Aquí se incluye Authentik porque es de código abierto, se aloja por cuenta
propia, se ejecuta en dos contenedores junto a la pila y no exige una cuenta con
nadie para probarlo.

---

Este es un proyecto comunitario independiente. No está afiliado a OpenCloud
GmbH ni a Authentik Security, Inc., ni respaldado ni apoyado por ellas.
"OpenCloud" y todas las marcas relacionadas pertenecen a sus respectivos
titulares y aquí solo se utilizan para identificar el software que comprueba
esta herramienta.
