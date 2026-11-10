# Poner un proveedor de identidad delante de OpenCloud, paso a paso

[Ejecutar OpenCloud en una infraestructura segura](../secure-deployment.md#1-put-a-real-identity-provider-in-front)
explica *por qué* un proveedor de identidad externo debe estar delante de una
instancia de OpenCloud y resume lo que necesita cada uno de los tres más
habituales. Esta página es la versión larga de ese resumen: tres tutoriales
completos, desde cero hasta un inicio de sesión que funciona, para
**Keycloak**, **Authentik** y **Authelia**.

Elija uno. Hacen el mismo trabajo, y ejecutar dos es una forma de no tener
ninguno bien configurado.

> **Esta página cambia quién puede iniciar sesión, no cómo se expone
> OpenCloud.** Un proveedor de identidad es un control entre varios. El
> cortafuegos, el registro de auditoría, el proxy inverso y el ciclo de vida
> de versiones son el resto del trabajo, y
> [Ejecutar OpenCloud en una infraestructura segura](../secure-deployment.md)
> los trata en conjunto.

<!-- TOC -->
* [Poner un proveedor de identidad delante de OpenCloud, paso a paso](#putting-an-identity-provider-in-front-of-opencloud-step-by-step)
  * [Antes de empezar](#before-you-start)
  * [Lo que tiene que producir cualquier proveedor](#what-every-provider-has-to-produce)
    * [Los cuatro clientes](#the-four-clients)
    * [Por qué todos son clientes públicos](#why-they-are-all-public-clients)
  * [Lo que necesita OpenCloud, elija el proveedor que elija](#what-opencloud-needs-whichever-provider-you-pick)
  * [Tutorial A: Keycloak](#tutorial-a-keycloak)
  * [Tutorial B: Authentik](#tutorial-b-authentik)
  * [Tutorial C: Authelia](#tutorial-c-authelia)
  * [Verificar que realmente ha funcionado](#verifying-it-actually-worked)
  * [Migrar una instancia que ya tiene cuentas](#moving-an-instance-that-already-has-accounts)
  * [Solución de problemas](#troubleshooting)
  * [Siguientes pasos](#where-to-go-next)
  * [Marcas e independencia](#trademarks-and-affiliation)
<!-- TOC -->

## Antes de empezar {#before-you-start}

Tres nombres, decididos ahora y sin cambiarlos después. Todas las URL
siguientes se construyen a partir de ellos, y un emisor que cambia después de
que la gente haya iniciado sesión invalida de golpe todas las sesiones y todos
los tokens guardados de los clientes de escritorio:

| Nombre | Ejemplo | Qué es |
|:-----|:--------|:-----------|
| La instancia | `opencloud.example.com` | Donde responde OpenCloud |
| El proveedor | `id.example.com` | Donde está la página de inicio de sesión |
| El realm o slug de la aplicación | `opencloud` | El nombre que da el proveedor a esta aplicación |

También necesita:

- **Una instancia de OpenCloud que funcione por HTTPS.** No una instancia que
  esté construyendo al mismo tiempo. Si el inicio de sesión falla, querrá
  saber que ha sido el proveedor, y una instancia a medio construir le quita
  esa certeza.
- **Un certificado real en ambos nombres.** El descubrimiento de OpenID
  Connect es una solicitud HTTPS de OpenCloud al proveedor; un certificado
  autofirmado ahí falla con un mensaje de error que rara vez menciona el certificado.
- **Que ambos nombres se resuelvan tanto desde dentro de la red de
  contenedores como desde fuera.** Es la causa más frecuente de "funciona en el
  navegador y el cliente de escritorio se queda colgado"; consulte
  [Solución de problemas](#troubleshooting).
- **Una forma de volver a entrar.** Conserve un administrador local de
  OpenCloud hasta que el nuevo inicio de sesión esté probado, y no quite `idp`
  de los servicios en ejecución hasta entonces.

## Lo que tiene que producir cualquier proveedor {#what-every-provider-has-to-produce}

Los clientes, las URI de redirección y los ámbitos son propiedades de **las
aplicaciones propias de OpenCloud**, no del proveedor. Son idénticos para
Keycloak, Authentik y Authelia, y equivocarse en uno produce el mismo fallo sea
cual sea el proveedor elegido. Configure estos cuatro, siempre.

### Los cuatro clientes {#the-four-clients}

| Cliente | ID de cliente predeterminado | URI de redirección | Ámbitos |
|:-------|:------------------|:--------------|:-------|
| Web | `web` | `https://opencloud.example.com/`, `https://opencloud.example.com/oidc-callback.html`, `https://opencloud.example.com/oidc-silent-redirect.html` | `openid profile email groups` |
| Escritorio | `OpenCloudDesktop` | `http://127.0.0.1`, `http://localhost` | `openid profile email groups offline_access` |
| Android | `OpenCloudAndroid` | `oc://android.opencloud.eu` | `openid profile email groups offline_access` |
| iOS | `OpenCloudIOS` | `oc://ios.opencloud.eu`, `oc.ios://ios.opencloud.eu` | `openid profile email groups offline_access` |

Hay tres cosas en esa tabla que son fundamentales:

**El cliente web necesita las tres URI de redirección.**
`oidc-callback.html` termina el inicio de sesión; `oidc-silent-redirect.html`
es la forma en que la pestaña renueva un token sin devolver a nadie a una
pantalla de inicio de sesión en mitad de una subida. Si registra solo la
primera, el inicio de sesión funciona, pero las sesiones terminan después a
intervalos difíciles de reproducir.

**Solo los clientes que no son navegador reciben `offline_access`.** Ese
ámbito es el que emite el token de actualización que un cliente de escritorio
o móvil necesita para sobrevivir a un reinicio. El navegador no lo
recibe, porque una pestaña no puede guardar un token de actualización de
forma segura.

**Los ID de cliente se pueden configurar, y las dos partes deben coincidir.**
El proveedor los conoce porque usted los escribió allí; OpenCloud los publica
a sus propios clientes mediante WebFinger, a partir de
`WEBFINGER_WEB_OIDC_CLIENT_ID` y sus equivalentes `ANDROID`, `IOS` y
`DESKTOP`. Si cambia uno sin el otro, el cliente de escritorio pide al
proveedor un cliente que no existe.

### Por qué todos son clientes públicos {#why-they-are-all-public-clients}

Todos los clientes de OpenCloud (la aplicación web en una pestaña, la
aplicación de escritorio en un portátil, las dos aplicaciones móviles) se
ejecutan por completo en el equipo de otra persona. Ninguno puede guardar un
secreto, porque cualquier cosa que se distribuye a todos ellos es un secreto
del que tienen copia todos sus usuarios.

Por eso los cuatro son **clientes públicos que usan el flujo de código de
autorización con PKCE**, y PKCE es obligatorio: sustituye
al secreto de cliente que esos clientes no pueden guardar. Defina el método de
desafío como `S256`, nunca `plain`. No emita un secreto de cliente para ninguno
de ellos: un proveedor que lo exige para un cliente público está mal
configurado, y pegar un secreto en una aplicación de escritorio para
satisfacerlo publica ese secreto.

## Lo que necesita OpenCloud, elija el proveedor que elija {#what-opencloud-needs-whichever-provider-you-pick}

Defina esto en OpenCloud una vez que el proveedor esté en marcha. La
[guía de IdP externo](https://docs.opencloud.eu/docs/admin/configuration/authentication-and-user-management/external-idp)
es la referencia oficial; las notas de aquí son las partes que merecen una
segunda reflexión.

```shell
# The provider, and turning the built-in one off.
OC_OIDC_ISSUER="https://id.example.com/realms/opencloud"
OC_EXCLUDE_RUN_SERVICES="idp"

# Verify tokens against the provider's published keys rather than asking it
# on every single request.
PROXY_OIDC_ACCESS_TOKEN_VERIFY_METHOD="jwt"
PROXY_OIDC_REWRITE_WELLKNOWN="true"

# Who a token belongs to, and the OpenCloud attribute it is matched against.
PROXY_USER_OIDC_CLAIM="preferred_username"
PROXY_USER_CS3_CLAIM="username"

# Create the account on first sign-in, and where its fields come from.
PROXY_AUTOPROVISION_ACCOUNTS="true"
PROXY_AUTOPROVISION_CLAIM_USERNAME="preferred_username"
PROXY_AUTOPROVISION_CLAIM_EMAIL="email"
PROXY_AUTOPROVISION_CLAIM_DISPLAYNAME="name"
PROXY_AUTOPROVISION_CLAIM_GROUPS="groups"

# Roles from a claim - and the default role switched off, or everybody gets
# that one as well.
PROXY_ROLE_ASSIGNMENT_DRIVER="oidc"
PROXY_ROLE_ASSIGNMENT_OIDC_CLAIM="roles"
GRAPH_ASSIGN_DEFAULT_USER_ROLE="false"

# The client IDs, published to OpenCloud's own clients through WebFinger.
WEBFINGER_WEB_OIDC_CLIENT_ID="web"
WEBFINGER_DESKTOP_OIDC_CLIENT_ID="OpenCloudDesktop"
WEBFINGER_ANDROID_OIDC_CLIENT_ID="OpenCloudAndroid"
WEBFINGER_IOS_OIDC_CLIENT_ID="OpenCloudIOS"
```

Dos de ellos son decisiones de control de acceso disfrazadas de
configuración, y ambas se tratan con más detalle en
[secure-deployment.md](../secure-deployment.md#what-opencloud-needs-whichever-provider-you-pick):

- **`PROXY_AUTOPROVISION_ACCOUNTS=true` significa que cualquiera a quien
  autentique su proveedor obtiene una cuenta de OpenCloud en su primera
  visita.** Es correcto cuando el proveedor limita esta aplicación a un grupo,
  e incorrecto cuando el proveedor autentica a toda su organización. Limítelo
  en el proveedor. Desactivar el aprovisionamiento automático y crear las
  cuentas a mano no es la solución; es la misma decisión, empeorada por ser
  manual.
- **`PROXY_ROLE_ASSIGNMENT_DRIVER=oidc` junto con
  `GRAPH_ASSIGN_DEFAULT_USER_ROLE=true` es la configuración errónea que da a
  todo el mundo un rol que no pretendía.** Definir lo primero implica
  desactivar lo segundo.

Reinicie OpenCloud después de cambiar cualquiera de ellos.
`OC_EXCLUDE_RUN_SERVICES`, en particular, solo se lee una vez, al arrancar.

## Tutorial A: Keycloak {#tutorial-a-keycloak}

La opción más habitual donde una organización ya tiene uno, y la más pesada de
las tres. Elíjala si necesita un realm completo (federación, intermediación de
identidades, asignación de roles detallada) o si Keycloak ya está ahí.

**1. Ejecútelo.** Un servicio compose mínimo con forma de producción, detrás
del proxy inverso que ya le termine TLS:

```yaml
services:
  keycloak:
    image: quay.io/keycloak/keycloak:latest
    command: ["start", "--optimized"]
    environment:
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://keycloak-db:5432/keycloak
      KC_DB_USERNAME: keycloak
      KC_DB_PASSWORD_FILE: /run/secrets/kc_db_password
      KC_HOSTNAME: https://id.example.com
      KC_PROXY_HEADERS: xforwarded
      KC_HTTP_ENABLED: "true"
      # Bootstrap only. Create a real administrator, then remove these two
      # and restart - they are a password in an environment variable.
      KC_BOOTSTRAP_ADMIN_USERNAME: admin
      KC_BOOTSTRAP_ADMIN_PASSWORD_FILE: /run/secrets/kc_bootstrap
    secrets: [kc_db_password, kc_bootstrap]
    depends_on: [keycloak-db]
```

`KC_PROXY_HEADERS: xforwarded` es importante: sin él, Keycloak construye su
emisor y sus URL de redirección a partir de la dirección interna, y todas son
incorrectas de una forma que solo se nota en la redirección.

**2. Cree el realm.** *Realms → Create realm*, con el nombre `opencloud`. No
use el realm `master` para aplicaciones: es el realm que administra el propio
Keycloak, y un cliente de aplicación ahí es un cliente de aplicación en su
plano de administración.

Su emisor es ahora:

```
https://id.example.com/realms/opencloud
```

**3. Cree los cuatro clientes.** *Clients → Create client*, cuatro veces, con
los ID y las URI de redirección de [la tabla anterior](#the-four-clients). Para
cada uno:

- **Client type**: OpenID Connect.
- **Client authentication**: **desactivado**. Esto es lo que lo convierte en
  un cliente público.
- **Authentication flow**: solo *Standard flow*. Desactive *Direct access
  grants*: es la concesión por contraseña, y es una forma de eludir todos los
  segundos factores que va a configurar.
- **Valid redirect URIs**: las de la tabla. El cliente de escritorio necesita
  `http://127.0.0.1/*` y `http://localhost/*`: el puerto se elige en tiempo de
  ejecución, así que aquí el comodín cumple una función real y no es pereza.
- **Web origins**: `https://opencloud.example.com`, solo para el cliente web.
- En *Advanced → Advanced settings*, defina
  **Proof Key for Code Exchange Code Challenge Method** como `S256`.

**4. Cree los claims que lee OpenCloud.** *Client scopes →
`<client>-dedicated` → Add mapper → By configuration*:

- Mapper **Group Membership**, nombre del claim del token `groups`, *Full
  group path* **desactivado**. Sin esto último, sus grupos llegan como
  `/finance` y todas las comparaciones con `finance` fallan.
- Mapper **User Client Role**, nombre del claim del token `roles`, si asigna
  roles de OpenCloud desde Keycloak.

Añada ambos al **token de acceso** y a la respuesta de **userinfo**. OpenCloud
lee el token; un claim que solo existe en el token de ID es un claim que nunca
ve.

**5. Exija un segundo factor.** *Authentication → Required actions* → active
*Configure OTP*, y después *Authentication → Flows* → vincule un flujo de
navegador que lo exija. Un proveedor sin segundo factor ha trasladado su
inicio de sesión, no lo ha mejorado.

**6. Apunte OpenCloud a él** con las variables anteriores y reinicie.

## Tutorial B: Authentik {#tutorial-b-authentik}

El peso medio, y el más cómodo de configurar desde un archivo en lugar de con
clics. Elíjalo si quiere un solo proveedor delante de varias aplicaciones con
políticas por aplicación.

> Este repositorio ya incluye una pila de Authentik, pero con otra finalidad:
> protege [el punto de acceso MCP del propio servicio de análisis](../authentik.md)
> y el [área de operación](../../ADMIN.md), no OpenCloud.
> [`authentik/blueprints/`](../../authentik/blueprints/) es un ejemplo práctico
> de aprovisionar un proveedor desde un archivo, que merece la pena copiar sea
> lo que sea lo que configure.

**1. Ejecútelo.** Authentik publica un archivo compose y un generador para él;
siga
[su guía de instalación](https://docs.goauthentik.io/install-config/install/docker-compose)
en lugar de una copia que aquí quedaría desactualizada. Lo que importa después
es que `https://id.example.com` llegue a él y que el TLS sea real.

**2. Cree la asignación de ámbito para los grupos.** *Customisation → Property
mappings → Create → Scope mapping*:

- **Name**: `OpenCloud groups`
- **Scope name**: `groups`
- **Expression**:
  ```python
  return {"groups": [group.name for group in request.user.ak_groups.all()]}
  ```

Authentik incluye asignaciones para `openid`, `profile` y `email`; `groups` es
la que normalmente hay que añadir, y es la que OpenCloud necesita para los
roles.

**3. Cree cuatro proveedores.** *Applications → Providers → Create →
OAuth2/OpenID Provider*, una vez por cada cliente de
[la tabla anterior](#the-four-clients):

- **Client type**: **Public**.
- **Client ID**: el de la tabla.
- **Redirect URIs**: las de la tabla. Authentik las compara como expresiones
  regulares, así que escape los puntos: `http://127\.0\.0\.1(:[0-9]+)?` para
  el rango de loopback del cliente de escritorio.
- **Scopes**: las tres asignaciones incluidas más `OpenCloud groups`.
- **Signing key**: su certificado, para que los tokens vayan firmados.
- **Authorization flow**: `implicit consent` para una aplicación interna: no
  hay que pedir a la gente que consienta el uso de su propio servidor de
  archivos en cada inicio de sesión.

**4. Cree la aplicación y vincúlela a un grupo.** *Applications →
Applications → Create*, slug `opencloud`, proveedor el web del paso 3. Después
vincúlela: *Policies / Group / User bindings* → vincule el grupo que debe tener
acceso a OpenCloud.

**Esta vinculación es el control de acceso que hace seguro el
aprovisionamiento automático.** Con ella, `PROXY_AUTOPROVISION_ACCOUNTS=true`
solo crea cuentas para las personas que ya ha decidido que deben tener una.

**5. Lea el emisor en el proveedor.** Es:

```
https://id.example.com/application/o/opencloud/
```

**La barra final forma parte de él.** OpenID Connect compara la cadena del
emisor de forma exacta, así que un emisor configurado sin ella no supera la
validación con tokens que sí la llevan, y el error no menciona ni la barra ni
el emisor.

**6. Apunte OpenCloud a él** con las variables anteriores y reinicie.

## Tutorial C: Authelia {#tutorial-c-authelia}

El más ligero de los tres, configurado por completo en un archivo, y una buena
opción cuando el proxy inverso ya hace autenticación delegada para otros
servicios. Elíjalo si quiere un binario pequeño en lugar de un servidor de
realms.

**1. Ejecútelo**, junto con su almacén de sesiones:

```yaml
services:
  authelia:
    image: ghcr.io/authelia/authelia:latest
    volumes:
      - ./authelia:/config
    environment:
      AUTHELIA_IDENTITY_PROVIDERS_OIDC_HMAC_SECRET_FILE: /run/secrets/oidc_hmac
      AUTHELIA_IDENTITY_PROVIDERS_OIDC_ISSUER_PRIVATE_KEY_FILE: /run/secrets/oidc_key
    secrets: [oidc_hmac, oidc_key]
```

Genere los dos secretos antes del primer arranque; Authelia no se los
inventará:

```shell
docker run --rm ghcr.io/authelia/authelia:latest \
    authelia crypto rand --length 64 --charset alphanumeric
docker run --rm -v "$PWD/authelia:/keys" ghcr.io/authelia/authelia:latest \
    authelia crypto pair rsa generate --bits 4096 --directory /keys
```

**2. Registre los cuatro clientes** en `identity_providers.oidc.clients` de
`configuration.yml`. Este es el cliente web completo; los otros tres solo se
diferencian en `client_id`, `redirect_uris` y en que no tienen navegador:

```yaml
identity_providers:
  oidc:
    clients:
      - client_id: 'web'
        client_name: 'OpenCloud'
        public: true
        authorization_policy: 'two_factor'
        require_pkce: true
        pkce_challenge_method: 'S256'
        token_endpoint_auth_method: 'none'
        scopes: ['openid', 'profile', 'email', 'groups']
        redirect_uris:
          - 'https://opencloud.example.com/'
          - 'https://opencloud.example.com/oidc-callback.html'
          - 'https://opencloud.example.com/oidc-silent-redirect.html'
        response_types: ['code']
        grant_types: ['authorization_code']

      - client_id: 'OpenCloudDesktop'
        client_name: 'OpenCloud Desktop'
        public: true
        authorization_policy: 'two_factor'
        require_pkce: true
        pkce_challenge_method: 'S256'
        token_endpoint_auth_method: 'none'
        scopes: ['openid', 'profile', 'email', 'groups', 'offline_access']
        redirect_uris: ['http://127.0.0.1', 'http://localhost']
        response_types: ['code']
        grant_types: ['authorization_code', 'refresh_token']

      - client_id: 'OpenCloudAndroid'
        client_name: 'OpenCloud Android'
        public: true
        authorization_policy: 'two_factor'
        require_pkce: true
        pkce_challenge_method: 'S256'
        token_endpoint_auth_method: 'none'
        scopes: ['openid', 'profile', 'email', 'groups', 'offline_access']
        redirect_uris: ['oc://android.opencloud.eu']
        response_types: ['code']
        grant_types: ['authorization_code', 'refresh_token']

      - client_id: 'OpenCloudIOS'
        client_name: 'OpenCloud iOS'
        public: true
        authorization_policy: 'two_factor'
        require_pkce: true
        pkce_challenge_method: 'S256'
        token_endpoint_auth_method: 'none'
        scopes: ['openid', 'profile', 'email', 'groups', 'offline_access']
        redirect_uris: ['oc://ios.opencloud.eu', 'oc.ios://ios.opencloud.eu']
        response_types: ['code']
        grant_types: ['authorization_code', 'refresh_token']
```

`authorization_policy: 'two_factor'` es donde se exige el segundo factor, por
cliente, y es el motivo para preferirlo a una regla global: el cliente de
escritorio y el navegador pueden someterse al mismo nivel sin depender de que
alguien recuerde una regla de control de acceso.

**3. Añada la regla de control de acceso** para la propia instancia, para que
también quede protegido todo lo que no cubra el flujo de OpenID Connect:

```yaml
access_control:
  default_policy: 'deny'
  rules:
    - domain: 'opencloud.example.com'
      policy: 'two_factor'
```

**4. El emisor es el host sin más**, sin ruta ni barra final:

```
https://id.example.com
```

**5. Apunte OpenCloud a él** con las variables anteriores y reinicie.

## Verificar que realmente ha funcionado {#verifying-it-actually-worked}

Cuatro comprobaciones, en este orden. Cada una falla de forma distinta, así
que ejecutarlas desordenadas hace perder tiempo.

**1. El proveedor publica un documento de descubrimiento.**

```shell
curl -fsS https://id.example.com/.well-known/openid-configuration | \
    python3 -m json.tool | head -20
```

El campo `issuer` de la respuesta debe ser **exactamente, byte a byte**, lo
que puso en `OC_OIDC_ISSUER`. Una barra final cuenta.

**2. OpenCloud apunta a él.** Con `PROXY_OIDC_REWRITE_WELLKNOWN=true`,
preguntar a OpenCloud devuelve el documento del proveedor:

```shell
curl -fsS https://opencloud.example.com/.well-known/openid-configuration | \
    python3 -c 'import json,sys; print(json.load(sys.stdin)["issuer"])'
```

Si devuelve la dirección propia de OpenCloud, el `idp` integrado sigue en
marcha: `OC_EXCLUDE_RUN_SERVICES` no surtió efecto o no se reinició el
contenedor.

**3. Una persona puede iniciar sesión.** En una ventana privada, para no estar
probando una sesión que ya tenía. Después compruebe que se ha creado la
cuenta, si activó el aprovisionamiento automático.

**4. Analícelo.** Para eso está el resto de este repositorio. El escáner
indica qué proveedor ha encontrado y lee cuatro propiedades del documento de
descubrimiento que publica ese proveedor:

```shell
check-opencloud-security --host opencloud.example.com --check-hardening --debug
```

Busque que `identityProviderDetected` se supere, así como
`oidcPkceSupported`, `oidcImplicitFlowDisabled`, `oidcSigningAlgorithmStrong`
y `oidcEndpointsUseHttps`. [Autenticación](../authentication.md) explica qué
significa cada uno y por qué se comprueba. Un proveedor que no supera
`oidcImplicitFlowDisabled` sigue ofreciendo un flujo que pone tokens en una
URL, algo que conviene corregir antes de que nadie lo use.

Tenga en cuenta lo que esto **no** demuestra: el escáner lee lo que publica el
proveedor sin iniciar sesión, así que no puede decirle si la asignación de
grupos es correcta ni si se exige el segundo factor. Esas son las dos cosas que
hay que probar a mano.

## Migrar una instancia que ya tiene cuentas {#moving-an-instance-that-already-has-accounts}

Cambiar una instancia que la gente ya usa es un trabajo distinto de configurar
una nueva, y la diferencia está por completo en la correspondencia de
identidades.

**Las cuentas tienen que coincidir.** `PROXY_USER_OIDC_CLAIM` y
`PROXY_USER_CS3_CLAIM` son lo que conecta a una persona en el proveedor con su
cuenta de OpenCloud existente y todo lo que contiene. Si
`preferred_username` en el proveedor no es igual a `username` en OpenCloud, el
aprovisionamiento automático crea una *segunda* cuenta vacía para alguien que
ya tenía una, y sus archivos siguen en la primera.

Por tanto, en este orden:

1. **Exporte los nombres de usuario existentes** y compárelos con los del
   proveedor antes de cambiar nada. Resuelva las diferencias en el proveedor.
2. **Deje `idp` en marcha** y configure el proveedor externo junto a él.
3. **Pruebe con una cuenta** que exista en ambos y confirme que llega a su
   espacio existente y no a uno nuevo.
4. **Después** añada `idp` a `OC_EXCLUDE_RUN_SERVICES` y reinicie.
5. **Mantenga `PROXY_ENABLE_BASIC_AUTH=false`.** Los montajes WebDAV, los
   clientes CalDAV y los trabajos de copia de seguridad se autentican con HTTP
   Basic y eluden el proveedor y todos sus segundos factores. Cuando algo lo
   necesita de verdad, la respuesta son tokens de aplicación y no contraseñas
   de cuenta; consulte
   [secure-deployment.md](../secure-deployment.md#basic-authentication-is-the-hole-in-all-of-this).

## Solución de problemas {#troubleshooting}

| Lo que ve | Lo que suele ser |
|:-------------|:-------------------|
| `invalid issuer` o fallos de validación de tokens | `OC_OIDC_ISSUER` no coincide exactamente con la cadena `issuer` del proveedor. Authentik necesita la barra final; Authelia no lleva ninguna |
| El inicio de sesión funciona en el navegador y el cliente de escritorio se queda colgado | El nombre del proveedor no se resuelve desde dentro de la red de contenedores, o la URI de redirección de escritorio no tiene comodín de puerto |
| El inicio de sesión funciona y luego las sesiones mueren a intervalos extraños | Al cliente web le falta `oidc-silent-redirect.html` entre sus URI de redirección |
| El cliente de escritorio nunca mantiene la sesión | Falta `offline_access` en los ámbitos de ese cliente, así que no se emite token de actualización |
| Todo el mundo tiene más permisos de los previstos | `GRAPH_ASSIGN_DEFAULT_USER_ROLE` sigue en `true` mientras los roles proceden de un claim |
| Una segunda cuenta vacía para alguien que ya tenía una | El claim de `PROXY_USER_OIDC_CLAIM` no es igual al atributo de `PROXY_USER_CS3_CLAIM` |
| Los grupos llegan pero nunca coinciden | *Full group path* de Keycloak está activado, así que `finance` llega como `/finance` |
| Se autentican usuarios que no deberían tener cuenta | El aprovisionamiento automático está activado y la aplicación no está limitada a un grupo en el proveedor |
| El escáner sigue notificando el proveedor integrado | `OC_EXCLUDE_RUN_SERVICES` no incluye `idp`, o no se reinició OpenCloud |

## Siguientes pasos {#where-to-go-next}

| Página | Para qué |
|:-----|:----|
| [Ejecutar OpenCloud en una infraestructura segura](../secure-deployment.md) | El registro de auditoría, el cortafuegos y el resto del trabajo del que esta página es una parte |
| [Autenticación](../authentication.md) | Todas las comprobaciones de autenticación y OpenID Connect que ejecuta el escáner, en detalle |
| [Proxies inversos](../reverse-proxy.md) | Terminar TLS delante de ambos nombres |
| [TLS y certificados](../tls.md) | Cómo es un buen certificado, y todas las comprobaciones de transporte |
| [Authentik delante del punto de acceso MCP](../authentik.md) | El mismo proveedor, protegiendo este servicio de análisis en lugar de OpenCloud |
| [Medidas de refuerzo](../hardening.md) | Qué significan realmente `basicAuthDisabled` y las demás |
