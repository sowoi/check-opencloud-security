# Ejecutar OpenCloud en una infraestructura segura

Un análisis externo solo cubre una parte de la operación segura de OpenCloud.
Esta guía trata el resto del trabajo: políticas del proveedor de identidad,
registro de auditoría, reglas de cortafuegos, mantenimiento del host, copias
de seguridad y orientación a los usuarios.

Use estos controles junto con análisis programados. La última sección explica
qué pueden detectar los análisis periódicos una vez que el despliegue está en
marcha.

> Todos los ajustes siguientes se citan de la propia documentación de
> OpenCloud y enlazan a ella. OpenCloud evoluciona deprisa; cuando una variable
> de aquí no coincida con la página enlazada, la página enlazada tiene razón, y
> [una incidencia](https://github.com/sowoi/check-opencloud-security/issues)
> será bienvenida.

<!-- TOC -->
* [Ejecutar OpenCloud en una infraestructura segura](#running-opencloud-in-a-secure-infrastructure)
  * [La forma de un despliegue defendible](#the-shape-of-a-defensible-deployment)
  * [1. Ponga delante un proveedor de identidad real](#1-put-a-real-identity-provider-in-front)
    * [El porqué, antes que el cómo](#why-before-how)
    * [Lo que necesita OpenCloud, elija el proveedor que elija](#what-opencloud-needs-whichever-provider-you-pick)
    * [Keycloak](#keycloak)
    * [Authentik](#authentik)
    * [Authelia](#authelia)
    * [La autenticación básica es el agujero de todo esto](#basic-authentication-is-the-hole-in-all-of-this)
  * [2. Active el registro de auditoría y después léalo](#2-turn-the-audit-log-on-then-read-it)
    * [El servicio de auditoría no se ejecuta por defecto](#the-audit-service-does-not-run-by-default)
    * [Sacar el registro del equipo](#getting-the-log-off-the-box)
    * [Sobre qué alertar realmente](#what-to-actually-alert-on)
    * [Retención y legislación](#retention-and-the-law)
  * [3. Proteja bien el cortafuegos](#3-firewall-it-properly)
    * [Los puertos, y cuáles deben estar en internet](#the-ports-and-which-of-them-belong-on-the-internet)
    * [Un cortafuegos de host que funcione con Docker](#a-host-firewall-that-works-with-docker)
    * [El tráfico saliente también importa](#egress-matters-too)
  * [4. Por debajo de todo: el host y los datos](#4-underneath-it-all-the-host-and-the-data)
  * [5. Lo que deben saber las personas que lo usan](#5-what-the-people-using-it-should-know)
    * [Para todas las personas con cuenta](#for-everybody-with-an-account)
    * [Para administradores](#for-administrators)
  * [6. Dónde encaja este escáner: monitorización continua](#6-where-this-scanner-fits-continuous-monitoring)
    * [Lo que detecta un análisis programado y una auditoría puntual no](#what-a-scheduled-scan-catches-that-a-one-off-audit-does-not)
    * [Una configuración de monitorización que merece la pena](#a-monitoring-setup-that-is-worth-having)
    * [Lo que deliberadamente no le dirá](#what-it-deliberately-will-not-tell-you)
  * [Lista de comprobación](#checklist)
  * [Siguientes pasos](#where-to-go-next)
  * [Marcas e independencia](#trademarks-and-affiliation)
<!-- TOC -->


## La forma de un despliegue defendible {#the-shape-of-a-defensible-deployment}

```
                    internet
                        │
                   443/tcp only
                        │
              ┌─────────▼─────────┐
              │   reverse proxy   │  TLS, HSTS, security headers,
              │  (nginx/Caddy/…)  │  rate limits, TRACE refused
              └─────────┬─────────┘
                        │  private network, no published ports
         ┌──────────────┼──────────────┐
         │              │              │
  ┌──────▼─────┐ ┌──────▼─────┐ ┌──────▼──────┐
  │ OpenCloud  │ │  identity  │ │    audit    │
  │   :9200    │ │  provider  │ │   service   │
  └──────┬─────┘ └────────────┘ └──────┬──────┘
         │                             │
   ┌─────▼──────┐               ┌──────▼──────┐
   │  storage   │               │  log sink   │  off-host, append-only
   └────────────┘               └─────────────┘
```

Exponga solo los puntos de entrada públicos previstos, aplique su política de
inicio de sesión en el proveedor de identidad y envíe los registros de
auditoría a un sistema independiente. Las secciones siguientes describen cada
parte.

## 1. Ponga delante un proveedor de identidad real {#1-put-a-real-identity-provider-in-front}

### El porqué, antes que el cómo {#why-before-how}

OpenCloud incluye un proveedor de identidad (`idp`) y una gestión de
identidades (`idm`) para que la instalación inicial funcione. Un proveedor
externo es útil cuando una organización necesita un ciclo de vida de cuentas
compartido, autenticación multifactor y políticas coherentes entre servicios:

- **Segundos factores.** Un proveedor externo le da TOTP, WebAuthn o passkeys
  en todas las aplicaciones que ejecuta, configurados una sola vez.
- **Ciclo de vida.** Alguien se va y usted desactiva una cuenta, no una cuenta
  por servicio.
- **Política de sesiones.** Bloqueo tras intentos fallidos, duración de la
  sesión, confianza en dispositivos, acceso condicional: todo ello corresponde
  al proveedor.
- **Auditoría.** Los intentos de inicio de sesión se registran en el lugar que
  gestiona los inicios de sesión, que es donde los buscará quien investigue.

Este escáner indica qué proveedor ha encontrado en `identityProvider`, y
rebaja el hallazgo de autenticación HTTP Basic de medium a low cuando detecta
uno externo; consulte
[Autenticación](../authentication.md#6-can-the-identity-provider-be-found-at-all-identityproviderdetected).

> **Paso a paso, para cada uno de los tres:** esta sección es el resumen y el
> razonamiento.
> [Poner un proveedor de identidad delante de OpenCloud, paso a paso](../identity-providers.md)
> es el tutorial: la instalación de cada proveedor, los cuatro clientes de
> OpenCloud que necesita cada uno, la verificación de que funciona y la
> migración de una instancia que ya tiene cuentas.

### Lo que necesita OpenCloud, elija el proveedor que elija {#what-opencloud-needs-whichever-provider-you-pick}

Las variables son las mismas para los tres; solo cambian la URL del emisor y
la forma de crear el cliente. Tomado de la
[guía de IdP externo de OpenCloud](https://docs.opencloud.eu/docs/admin/configuration/authentication-and-user-management/external-idp):

| Variable | Qué hace |
|:---------|:-------------|
| `OC_OIDC_ISSUER` | La URL del emisor del proveedor, p. ej. `https://id.example.com/realms/opencloud` |
| `OC_EXCLUDE_RUN_SERVICES` | Añada `idp` para que no arranque el proveedor integrado |
| `PROXY_OIDC_ACCESS_TOKEN_VERIFY_METHOD` | `jwt`, para que los tokens se verifiquen con las claves publicadas por el proveedor en lugar de preguntarle en cada solicitud |
| `PROXY_OIDC_REWRITE_WELLKNOWN` | `true`, para que los clientes que descubren `/.well-known/openid-configuration` en el host de OpenCloud se dirijan al proveedor real |
| `PROXY_USER_OIDC_CLAIM` | El claim que identifica a un usuario, normalmente `preferred_username` |
| `PROXY_USER_CS3_CLAIM` | El atributo de OpenCloud con el que se compara, normalmente `username` |
| `PROXY_AUTOPROVISION_ACCOUNTS` | `true` crea una cuenta en el primer inicio de sesión |
| `PROXY_ROLE_ASSIGNMENT_DRIVER` | `oidc` para tomar los roles de un claim, `default` para dar a todos el mismo rol |
| `PROXY_ROLE_ASSIGNMENT_OIDC_CLAIM` | Qué claim los transporta; `roles` por defecto |
| `GRAPH_ASSIGN_DEFAULT_USER_ROLE` | `false` cuando los roles proceden del proveedor, o cada usuario recibirá además, sin avisar, el predeterminado |

Revise juntos el aprovisionamiento de cuentas y la asignación de roles:

**El aprovisionamiento automático es una decisión de control de acceso.** Con
`PROXY_AUTOPROVISION_ACCOUNTS=true`, cualquiera a quien autentique su
proveedor obtiene una cuenta de OpenCloud la primera vez que entra. Es
correcto cuando la aplicación OpenCloud del proveedor está limitada a un
grupo, e incorrecto cuando el proveedor autentica a toda su organización:
limítelo en el proveedor, no desactivando el aprovisionamiento automático y
creando las cuentas a mano.

**Asignar roles desde un claim requiere desactivar el rol predeterminado.**
Definir `PROXY_ROLE_ASSIGNMENT_DRIVER=oidc` dejando
`GRAPH_ASSIGN_DEFAULT_USER_ROLE=true` es la configuración errónea que da a
todo el mundo un rol que no pretendía.

### Keycloak {#keycloak}

> [El tutorial paso a paso de Keycloak](../identity-providers.md#tutorial-a-keycloak)
> es el trabajo completo; lo que sigue es su esquema.

La opción más habitual donde una organización ya tiene uno. Cree un realm (o
reutilice el suyo) y después un cliente:

- **Client type** OpenID Connect. Registre por separado los clientes web,
  de escritorio, Android e iOS, con los ID de cliente del tutorial enlazado.
- **Cliente público** con PKCE: los clientes de OpenCloud son públicos y no
  pueden guardar un secreto. Defina *Proof Key for Code Exchange* como `S256`.
- **Valid redirect URIs** debe incluir el loopback del cliente de escritorio
  (`http://127.0.0.1:*` y `http://localhost:*`) y su dirección web.
- **Emisor**: `https://id.example.com/realms/opencloud`.

Para los roles, añada un mapper *User Client Role* que ponga los roles del
cliente en un claim `roles` y defina después
`PROXY_ROLE_ASSIGNMENT_OIDC_CLAIM=roles`. Dé al realm una política de
contraseñas y exija OTP como mínimo para el rol de administrador.

### Authentik {#authentik}

> [El tutorial paso a paso de Authentik](../identity-providers.md#tutorial-b-authentik)
> es el trabajo completo; lo que sigue es su esquema.

Este repositorio ya incluye una pila de Authentik, aunque con otra finalidad:
protege [el punto de acceso MCP del propio servicio de análisis](../authentik.md),
no OpenCloud. La configuración del proveedor tiene la misma forma:

- Cree un **OAuth2/OpenID Provider**, con flujo de autorización
  `implicit consent` para una aplicación interna de confianza.
- **Client type** público, con PKCE obligatorio.
- Defina las URI de redirección como arriba, con una expresión regular para el
  rango de loopback.
- El emisor es `https://id.example.com/application/o/<application-slug>/`. La
  barra final importa.
- Vincule la aplicación a un grupo para que no todos los usuarios de Authentik
  obtengan una cuenta de OpenCloud, y después active
  `PROXY_AUTOPROVISION_ACCOUNTS`.

[`authentik/blueprints/`](../../authentik/blueprints/) en este repositorio es un
ejemplo práctico de aprovisionar un proveedor desde un archivo en lugar de con
clics, que merece la pena copiar sea lo que sea lo que configure.

### Authelia {#authelia}

> [El tutorial paso a paso de Authelia](../identity-providers.md#tutorial-c-authelia)
> es el trabajo completo; lo que sigue es su esquema.

El más ligero de los tres, y una buena opción cuando el proxy inverso ya hace
autenticación delegada. El proveedor OpenID Connect de Authelia se configura en
`configuration.yml` en lugar de en una interfaz:

- Registre un cliente en `identity_providers.oidc.clients` con
  `public: true`, `require_pkce: true` y `pkce_challenge_method: S256`.
- Ámbitos `openid`, `profile`, `email`, `groups`.
- El emisor es `https://auth.example.com`.
- Asigne grupos a roles de OpenCloud con
  `PROXY_ROLE_ASSIGNMENT_OIDC_CLAIM=groups`.

Las reglas de control de acceso de Authelia son el lugar natural para exigir
dos factores específicamente para OpenCloud:

```yaml
access_control:
  rules:
    - domain: opencloud.example.com
      policy: two_factor
```

### La autenticación básica es el agujero de todo esto {#basic-authentication-is-the-hole-in-all-of-this}

Nada de lo anterior se aplica a un cliente que no admite OpenID Connect:
calendarios CalDAV y CardDAV, montajes WebDAV, trabajos de copia de seguridad.
Esos se autentican con HTTP Basic, y `PROXY_ENABLE_BASIC_AUTH=true` vuelve a
abrir una vía que elude su proveedor y todos sus segundos factores.

Déjelo en `false` si nada lo necesita. Si algo lo necesita, use
**tokens de aplicación en lugar de contraseñas de cuenta**: lo que se puede reutilizar
es entonces revocable y nunca es la credencial que protege su proveedor de
identidad. Este escáner notifica `basicAuthDisabled` como medium, o como low
cuando ve un proveedor externo, porque a veces ese compromiso es
intencionado; consulte [Autenticación](../authentication.md).

## 2. Active el registro de auditoría y después léalo {#2-turn-the-audit-log-on-then-read-it}

### El servicio de auditoría no se ejecuta por defecto {#the-audit-service-does-not-run-by-default}

OpenCloud tiene un
[servicio de auditoría](https://docs.opencloud.eu/docs/dev/server/services/audit/),
y no está en el conjunto de servicios predeterminado. Nada registra quién ha
compartido qué hasta que lo inicie:

```bash
# Add it to the services that run, alongside the default set.
OC_ADD_RUN_SERVICES=audit
```

Registra tres cosas que merece la pena tener:

- **Operaciones del sistema de archivos**: crear, borrar, mover, incluidas la
  papelera y el control de versiones.
- **Gestión de usuarios**: cuentas creadas y borradas.
- **Uso compartido**: comparticiones con usuarios y grupos, enlaces públicos,
  cambios de permisos y llamadas de los clientes a la API de uso compartido.

La tercera categoría es la que más importa aquí. Este escáner puede decirle
que se pueden crear enlaces públicos sin contraseña
([`publicLinkPasswordEnforced`](../sharing.md)); solo el registro de auditoría
puede decirle que alguien creó 4000 de ellos el martes pasado.

Configúrelo con las variables de
[la referencia del servicio de auditoría](https://docs.opencloud.eu/docs/dev/server/services/audit/environment-variables):

| Variable | Valor predeterminado | Qué valor darle |
|:---------|:--------|:------------------|
| `AUDIT_LOG_TO_CONSOLE` | `true` | Déjelo activado cuando un controlador de registros del contenedor envíe stdout a algún sitio |
| `AUDIT_LOG_TO_FILE` | `false` | `true` si prefiere escribir un archivo |
| `AUDIT_FILEPATH` | *(vacío)* | Obligatorio cuando se registra en un archivo |
| `AUDIT_FORMAT` | `json` | Mantenga `json`; el formato mínimo es para leerlo a simple vista, no para un recolector |
| `AUDIT_LOG_LEVEL` | `error` | Súbalo, o no registrará casi nada |
| `OC_EVENTS_ENDPOINT` | `127.0.0.1:9233` | El intermediario de eventos del que lee el servicio |
| `AUDIT_EVENTS_AUTH_USERNAME` / `_PASSWORD` | *(vacío)* | Defina ambos en cuanto el intermediario no esté en loopback |
| `AUDIT_EVENTS_ENABLE_TLS` | `false` | `true` cuando se llegue al intermediario a través de una red |

Que `AUDIT_LOG_LEVEL` tenga por defecto `error` es el detalle que pilla a la
gente desprevenida: iniciar el servicio sin cambiar el nivel produce un
registro que técnicamente funciona y en la práctica está vacío.

### Sacar el registro del equipo {#getting-the-log-off-the-box}

Un registro de auditoría guardado solo en el equipo auditado es una evidencia
que un atacante puede editar. Envíelo fuera:

```yaml
# docker-compose fragment: hand stdout to the host's journal, which a
# collector then forwards off the machine.
services:
  opencloud:
    logging:
      driver: journald
      options:
        tag: opencloud
```

Sea cual sea el recolector que use (Loki, Elasticsearch, un servidor syslog,
un servicio gestionado), las propiedades que debe exigir son las mismas:
**solo adición desde el punto de vista del emisor, en un dominio de confianza
distinto del de la instancia y con su propia retención.** Un recolector del que
pueden borrar las propias credenciales de OpenCloud no es mucho mejor que un
archivo local.

### Sobre qué alertar realmente {#what-to-actually-alert-on}

Un exceso de alertas dificulta detectar los problemas importantes. Dé
prioridad a los siguientes:

- Un **enlace público creado sin contraseña o sin caducidad**, sobre todo en un
  espacio que no suele compartirse.
- **Permisos de compartición ampliados** en cualquier cosa, en particular a un
  grupo.
- **Una cuenta creada o que recibe un rol de administración** fuera de su
  proceso normal de aprovisionamiento.
- **Descargas o borrados masivos**: un volumen de operaciones de archivo de una
  cuenta muy por encima de su propia línea base.
- **Anomalías de inicio de sesión**, que proceden de su proveedor de identidad
  y no de OpenCloud: desplazamientos imposibles, un pico de fallos, un primer
  inicio de sesión desde un país nuevo.

### Retención y legislación {#retention-and-the-law}

El registro de auditoría de un servicio de archivos es un registro de quién ha
accedido a qué documentos, lo que en la mayoría de las jurisdicciones son datos
personales con un límite de retención, no algo que se guarda para siempre.
Decida el periodo de forma deliberada, déjelo por escrito y haga que el
recolector lo aplique. Si está sujeto al RGPD, este registro entra en su
registro de actividades de tratamiento.

## 3. Proteja bien el cortafuegos {#3-firewall-it-properly}

### Los puertos, y cuáles deben estar en internet {#the-ports-and-which-of-them-belong-on-the-internet}

| Puerto | Qué es | ¿Expuesto a internet? |
|:-----|:-----------|:-------------------------|
| 443 | El proxy inverso | **Sí**: este, y solo este |
| 80 | HTTP sin cifrar | Solo para redirigir al 443, o nada |
| 9200 | El servicio proxy propio de OpenCloud | **No.** Publicarlo permite a los clientes eludir por completo su política de TLS y cabeceras |
| 9233 | El intermediario de eventos (NATS) | **No** |
| 9205, 9141, 9124, 9134, 9239 | Servicios de depuración de cada servicio: métricas, un volcado de configuración y, opcionalmente, pprof | **No.** Escuchan por defecto en `127.0.0.1`; llegar a uno desde fuera significa que lo publicó un mapeo de puertos del contenedor |
| 22 | SSH | Solo desde la red de gestión o una VPN, nunca desde internet |

Este escáner comprueba desde fuera las tres últimas filas:
`backendPortClosed`, `debugPort:*` y `debugEndpoint:*`, descritas en
[Rutas expuestas y puntos de acceso de depuración](../exposure.md). Comprueba
su cortafuegos por usted, desde el único punto de vista que cuenta.

### Un cortafuegos de host que funcione con Docker {#a-host-firewall-that-works-with-docker}

Conviene decir claramente cuál es el error habitual: **Docker escribe sus
propias reglas de iptables y se evalúan antes que las de UFW.** Un contenedor
iniciado con `-p 9200:9200` es accesible desde internet diga lo que diga
`ufw status`. Hay dos salidas, y necesita una de ellas:

**Publicar solo en loopback.** La solución más sencilla, y no necesita ningún
cortafuegos:

```yaml
services:
  opencloud:
    ports:
      # Not "9200:9200" - that binds 0.0.0.0.
      - "127.0.0.1:9200:9200"
```

Mejor aún: no publique nada y deje que el proxy inverso llegue a OpenCloud a
través de una red de Docker por el nombre del servicio. Un puerto que no se
publica no se puede configurar mal.

**O hacer que Docker respete el cortafuegos del host.** En
`/etc/docker/daemon.json`:

```json
{
  "iptables": true,
  "ip-forward": true
}
```

y después filtre en `DOCKER-USER`, que es la única cadena que Docker le deja:

```bash
# Everything reaching a container from outside must come via the proxy.
iptables -I DOCKER-USER -i eth0 -p tcp --dport 9200 -j DROP
```

El equivalente en [nftables](https://nftables.org/), si es lo que usa:

```
table inet filter {
  chain input {
    type filter hook input priority 0; policy drop;
    ct state established,related accept
    iif lo accept
    tcp dport { 80, 443 } accept
    tcp dport 22 ip saddr 10.0.0.0/8 accept
  }
}
```

Use lo que use, verifíquelo desde otro lugar en lugar de fiarse de la
configuración. `nmap -Pn -p 9200,9205,9233 opencloud.example.com` desde fuera
del host, o simplemente ejecute este escáner, que sondea exactamente esos
puertos:

```bash
check-opencloud-security --host opencloud.example.com --check-hardening --debug
```

### El tráfico saliente también importa {#egress-matters-too}

Las reglas de entrada son las que escribe la gente. Las reglas de salida son
las que limitan lo que puede hacer un compromiso: exfiltración, una shell
inversa, unirse a una botnet. Un host de OpenCloud necesita muy poco: DNS, NTP,
el directorio ACME si emite sus propios certificados, su réplica de paquetes y
el backend de almacenamiento o de correo que haya configurado deliberadamente.
Deniegue todo lo demás por defecto.

## 4. Por debajo de todo: el host y los datos {#4-underneath-it-all-the-host-and-the-data}

En pocas palabras, porque nada de esto es específico de OpenCloud y todo es
fundamental:

- **Actualizaciones de seguridad automáticas** en el host, y un proceso real de
  actualización para la propia versión de OpenCloud. Este escáner califica la
  versión en la que está ([ciclo de vida](../lifecycle.md)); no puede instalar
  nada.
- **Cifrado de disco completo** en lo que contenga el almacenamiento, para que
  un disco retirado o robado no sea una fuga de datos.
- **Copias de seguridad que ya ha restaurado.** Una copia sin probar puede
  no restaurarse. Guarde una copia fuera de línea o en almacenamiento de
  escritura única: el ransomware busca primero la copia de seguridad.
- **Privilegios mínimos para la cuenta de servicio.** Las unidades de systemd
  de [`contrib/systemd/`](../../contrib/systemd/) muestran el patrón:
  `DynamicUser=yes`, `ProtectSystem=strict`, `NoNewPrivileges=yes`, un
  `CapabilityBoundingSet=` vacío. Ejecute `systemd-analyze security <unit>` en
  las suyas.
- **Separe el proxy inverso de OpenCloud**, en hosts distintos o al menos en
  contenedores distintos, para que comprometer el proxy no suponga de inmediato
  comprometer el almacenamiento.

## 5. Lo que deben saber las personas que lo usan {#5-what-the-people-using-it-should-know}

La mayoría de los incidentes reales en un servicio de archivos no son
exploits. Alguien comparte la carpeta equivocada con un enlace público, o
reutiliza una contraseña que estaba en una filtración. Los parches no evitan ninguna de
las dos cosas; ambas dependen de la documentación y de los valores
predeterminados.

### Para todas las personas con cuenta {#for-everybody-with-an-account}

- **Un enlace público es una contraseña.** Quien tiene la URL tiene los datos:
  reenviada, pegada en una incidencia o guardada en un archivo de correo.
  Póngale contraseña y fecha de caducidad.
- **Compruebe qué comparte antes de compartirlo.** Compartir una carpeta
  superior comparte todo lo que hay debajo, incluido lo que se añada después.
- **Registre un segundo factor**, y prefiera una passkey o una llave de
  hardware a TOTP.
- **Las contraseñas de aplicación son para las aplicaciones.** Su cliente de
  calendario recibe su propio token revocable; nunca recibe la contraseña de su
  cuenta.
- **Quitar una compartición no es lo mismo que anular el envío de un
  archivo.** Suponga que todo lo compartido se ha descargado.
- **Notifique de inmediato una compartición errónea.** El margen en el que un
  administrador puede revocar un enlace y leer el registro de auditoría es
  corto, y nadie se mete en problemas por avisar rápido.

### Para administradores {#for-administrators}

- **Revise las comparticiones periódicamente.** Los enlaces públicos se
  acumulan; casi ninguno se borra nunca de forma deliberada.
- **Tenga un procedimiento de baja** que cubra el proveedor de identidad, los
  tokens de aplicación y las comparticiones que creó esa persona.
- **Conozca lo normal en su instancia.** La lista de alertas anterior solo
  funciona respecto a una línea base.
- **Deje por escrito a quién llamar.** Un incidente a las 03:00 no es el
  momento de descubrir que nadie sabe quién es responsable del almacenamiento.

## 6. Dónde encaja este escáner: monitorización continua {#6-where-this-scanner-fits-continuous-monitoring}

### Lo que detecta un análisis programado y una auditoría puntual no {#what-a-scheduled-scan-catches-that-a-one-off-audit-does-not}

Una revisión de seguridad es una fotografía. La infraestructura es una
película. Todo lo de esta página puede ser cierto el lunes y falso el jueves, y
las formas en que ocurre son cotidianas, no dramáticas:

- Un **certificado caduca**, o se renueva con uno que no cubre todos los
  nombres.
- Un **proxy inverso se reconfigura** para otro servicio y deja de enviar
  `Strict-Transport-Security`, o empieza a responder a `TRACE`.
- Alguien **publica un puerto de depuración** mientras persigue un problema de
  rendimiento y no lo retira.
- Una **versión pierde el soporte**, lo que es un cambio en el mundo y no en su
  despliegue: la instancia que tenía soporte completo el mes pasado ya no
  recibe correcciones de seguridad, y nada ha cambiado en su host que se lo
  indique.
- Se **publica un aviso de seguridad** para la versión que ejecuta.
- Se pone en marcha un **despliegue nuevo** a partir de un archivo compose
  copiado que sigue publicando el 9200.

Ejecutar este complemento de forma programada convierte cada una de esas
situaciones en una alerta el mismo día en que ocurre, desde fuera de la
instancia, que es el mismo punto de vista que tiene un atacante. La
monitorización continua **reduce el tiempo entre la aparición de un problema
y su detección al comprobar la instancia cada pocos minutos.**

### Una configuración de monitorización que merece la pena {#a-monitoring-setup-that-is-worth-having}

Empiece por aquí y después lea [Programación](../scheduling.md) o
[Icinga2 / Nagios](../installation.md#icinga2--nagios) para su plataforma:

```bash
check-opencloud-security \
  --host opencloud.example.com \
  --check-hardening \
  --baseline /var/lib/check-opencloud-security/baseline.json \
  --warn-on-new \
  --webhook-url https://hooks.example.com/opencloud \
  --webhook-on warning
```

Ahí hay cuatro decisiones, y cada una se gana su sitio:

- **`--check-hardening`** incluye las cabeceras y las medidas de refuerzo, no
  solo la nota.
- **`--baseline` con `--warn-on-new`** alerta sobre lo que *ha cambiado* y no
  sobre el estado aceptado de las cosas. Una instancia con un hallazgo con el
  que ha decidido convivir conscientemente permanece en silencio hasta que
  aparece un segundo; consulte
  [Notificar solo lo que ha cambiado](../../README.md#reporting-only-what-changed).
- **Un webhook**, para que la alerta llegue a una persona y no a un panel que
  nadie abre.
- **Los hallazgos que acepta se excluyen explícitamente**, con
  `--ignore-hardening`, lo que los mantiene en el documento de resultado y en
  el informe pero los saca de la alerta. Una exclusión es una decisión con
  nombre y apellidos, no una comprobación silenciada; consulte
  [Aceptar un hallazgo que no se va a corregir](../hardening.md#accepting-a-finding-you-are-not-going-to-fix).

Para un conjunto de instancias,
[Comprobar un conjunto de instancias](../many-instances.md) trata el uso de un
archivo de configuración por instancia y cómo revisar periódicamente las
exclusiones en todas ellas. Para gráficos y tendencias a largo plazo,
[Prometheus y Grafana](../prometheus.md): la nota como serie temporal es un
resumen sorprendentemente bueno para mostrar a quien no lee alertas.

### Lo que deliberadamente no le dirá {#what-it-deliberately-will-not-tell-you}

Dejarlo claro es lo que hace fiable el resto del informe:

- **Nada que esté detrás de un inicio de sesión.** El análisis nunca se
  autentica, así que ve lo que ve un visitante anónimo y nada más. Su modelo de
  permisos, la organización de sus espacios y el contenido de sus
  comparticiones le resultan invisibles.
- **Nada sobre la configuración de su proveedor de identidad.** Detecta que hay
  uno y nombra al fabricante; si exige un segundo factor es cosa suya y del
  proveedor.
- **Nada sobre su registro de auditoría.** Si el servicio está en marcha, si
  alguien lo lee y si sale del host son cosas que un análisis HTTP no puede
  observar.
- **Nada sobre las reglas de su cortafuegos**, solo sobre su efecto en el
  puñado de puertos que sondea.
- **Ninguna explotación.** Nunca prueba una carga maliciosa, nunca adivina una
  contraseña, y el único sondeo con credenciales que hace solo usa las
  contraseñas de demostración que OpenCloud publica en su propia
  documentación.

[Lo que el análisis no responde deliberadamente](../scanner-checks.md#what-the-scan-deliberately-does-not-answer)
es la versión completa de esta lista.

## Lista de comprobación {#checklist}

Imprímala, discútala y tache lo que no se aplique:

- [ ] Solo el 443 (y el 80, redirigiendo) accesible desde internet
- [ ] El 9200 y todos los puertos de depuración `92xx` inaccesibles desde
      fuera, verificado desde otro host y no desde la configuración
- [ ] Tráfico saliente limitado a lo que la instancia necesita realmente
- [ ] Un proveedor de identidad externo gestiona el inicio de sesión
- [ ] Segundo factor obligatorio, como mínimo para administradores
- [ ] `PROXY_ENABLE_BASIC_AUTH=false`, o tokens de aplicación emitidos para los
      clientes que lo necesitan
- [ ] `GRAPH_ASSIGN_DEFAULT_USER_ROLE=false` si los roles proceden de un claim
- [ ] Aprovisionamiento automático limitado por un grupo en el proveedor
- [ ] `OC_ADD_RUN_SERVICES=audit` y `AUDIT_LOG_LEVEL` por encima de `error`
- [ ] Registro de auditoría enviado fuera del host, con un periodo de retención
      decidido
- [ ] Alertas definidas para enlaces públicos, ampliación de comparticiones y
      cambios de rol
- [ ] TLS de una CA pública, con renovación automática y un registro CAA
- [ ] Cabeceras de seguridad definidas en el proxy; consulte
      [proxies inversos](../reverse-proxy.md)
- [ ] `OC_CORS_ALLOW_ORIGINS` restringido respecto a su valor predeterminado `*`
- [ ] Los enlaces públicos exigen contraseña y caducidad
- [ ] Las copias de seguridad existen, salen del host y se han restaurado alguna
      vez
- [ ] Host actualizado automáticamente; versión de OpenCloud dentro de su
      periodo de soporte
- [ ] Esta comprobación se ejecuta de forma programada, con una línea base y
      avisando a una persona

## Siguientes pasos {#where-to-go-next}

| Página | Para qué |
|:-----|:----|
| [Proxies inversos](../reverse-proxy.md) | La configuración de nginx, Apache, Caddy, Traefik y HAProxy que hay detrás de gran parte de la sección 3 |
| [TLS y certificados](../tls.md) | Todas las comprobaciones de transporte, y cómo es un buen certificado |
| [Rutas expuestas y puntos de acceso de depuración](../exposure.md) | Con qué se contrasta la sección del cortafuegos |
| [Autenticación](../authentication.md) | Los hallazgos del proveedor de identidad y de la autenticación básica, en detalle |
| [Enlaces públicos compartidos](../sharing.md) | La política de uso compartido dentro de la que trabajan sus usuarios |
| [Programación](../scheduling.md) | Temporizadores de systemd y cron para la monitorización de la sección 6 |
| [Comprobar un conjunto de instancias](../many-instances.md) | Cuando hay más de una |
| [Prometheus y Grafana](../prometheus.md) | La nota como serie temporal |
| [Qué es OpenCloud](../what-is-opencloud.md) | Contexto, si llega desde ownCloud o Nextcloud |
