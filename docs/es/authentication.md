# Comprobaciones de autenticación

El escáner comprueba el acceso a puntos de acceso protegidos, la autenticación
HTTP Basic, las cuentas de demostración documentadas y los ajustes de
autenticación que publican las capacidades de OpenCloud y los documentos de
descubrimiento de OpenID Connect. No adivina credenciales. La comprobación de
cuentas de demostración solo usa las credenciales publicadas que se describen
más abajo; consulte los
[límites del análisis](../scanner-checks.md#what-the-scan-deliberately-does-not-answer)
para conocer el alcance completo.

<!-- TOC -->
* [Autenticación: qué comprueba este escáner y por qué](#authentication-what-this-scanner-checks-and-why)
  * [1. ¿Exigen realmente una sesión los puntos de acceso protegidos?: `authentication:<path>`](#1-do-protected-endpoints-actually-require-a-session-authenticationpath)
  * [2. ¿Sigue ofreciendo el proxy autenticación HTTP Basic?: `basicAuthDisabled`](#2-does-the-proxy-still-offer-http-basic-authentication-basicauthdisabled)
  * [3. ¿Siguen pudiendo iniciar sesión las cuentas de demostración documentadas?: `demoUsersDisabled`](#3-do-the-documented-demo-accounts-still-sign-in-demousersdisabled)
  * [4. ¿Está limitada la búsqueda de cuentas a grupos compartidos?: `userEnumerationRestricted`](#4-is-account-search-restricted-to-shared-groups-userenumerationrestricted)
  * [5. ¿Es suficientemente estricta la política de contraseñas de los enlaces?: `passwordPolicyEnforced`](#5-is-the-link-password-policy-strong-enough-passwordpolicyenforced)
  * [5a. ¿Sigue exigiendo algo más que longitud?: `passwordPolicyComplexity`](#5a-does-it-still-ask-for-more-than-length-passwordpolicycomplexity)
  * [6. ¿Se puede encontrar el proveedor de identidad?: `identityProviderDetected`](#6-can-the-identity-provider-be-found-at-all-identityproviderdetected)
  * [7. Qué dice el documento de descubrimiento sobre la protección del inicio de sesión](#7-what-the-discovery-document-says-about-how-sign-in-is-protected)
  * [Qué más contiene ese documento y por qué no se comprueba nada de ello](#what-else-is-in-that-document-and-why-none-of-it-is-checked)
  * [Gravedad y efecto en la nota](#severity-and-rating-impact)
<!-- TOC -->


## 1. ¿Exigen realmente una sesión los puntos de acceso protegidos?: `authentication:<path>` {#1-do-protected-endpoints-actually-require-a-session-authenticationpath}

Se solicitan sin credenciales tres puntos de acceso que nunca deben responder
con contenido a una solicitud no autenticada:

| Ruta                          | Gravedad |
|:-------------------------------|:---------|
| `/remote.php/dav/files/`       | critical |
| `/graph/v1.0/users`             | critical |
| `/ocs/v1.php/cloud/user`        | high     |

Una respuesta HTTP `401`, `403`, `405` o `501`, una redirección a una página de
inicio de sesión o un `404` cuentan como "exigió autenticación": `405`/`501`
aparecen cuando es un proxy inverso, y no OpenCloud, quien responde a un `GET`
sobre una colección WebDAV, y `404` cubre un proxy que oculta la ruta por
completo en lugar de pedir credenciales. Cualquier otra respuesta (sobre todo
un `200` con los datos que esa ruta debería proteger) hace fallar la
comprobación. Un punto de acceso al que no se pudo llegar se considera
superado: un fallo de red no demuestra que el punto de acceso esté abierto, y
este escáner prefiere callar antes que inventar un hallazgo a partir de un
tiempo de espera agotado.

**Si falla:** solicite a mano la ruta notificada y lea qué responde
realmente. La explicación habitual es una caché, una CDN o una regla de proxy
mal configurada que sirve su propia página de error delante de OpenCloud; un
punto de acceso realmente accesible sin sesión es un incidente activo, no una
carencia de refuerzo: rote todo lo que haya expuesto la respuesta y corrija el
enrutamiento de inmediato.

## 2. ¿Sigue ofreciendo el proxy autenticación HTTP Basic?: `basicAuthDisabled` {#2-does-the-proxy-still-offer-http-basic-authentication-basicauthdisabled}

Se solicita a la instancia el desafío `WWW-Authenticate` de un punto de acceso
protegido. Un desafío `Basic` significa `PROXY_ENABLE_BASIC_AUTH=true`: un
nombre de usuario y una contraseña pueden reutilizarse en cada solicitud sin
pasar por el proveedor de identidad, lo que elude el inicio de sesión único y
cualquier segundo factor que se exija allí.

No se trata como un simple error, porque en la práctica la alternativa suele
ser peor: CalDAV, CardDAV y la mayoría de los clientes WebDAV no hablan OpenID
Connect y no tienen otra forma de autenticarse. Por eso se califica como
`medium` y no como `critical`, y como `low` cuando se confirma que un
proveedor de identidad externo gestiona el inicio de sesión interactivo
(consulte [Quién inicia la sesión de los usuarios](../scanner-checks.md#who-signs-users-in)),
ya que las contraseñas de cuenta que protegen esos inicios de sesión del
proveedor no son las que se reutilizan aquí.

**Corrección:** defina `PROXY_ENABLE_BASIC_AUTH=false` (el valor
predeterminado) si nada lo necesita. Si lo necesita un cliente de calendario,
contactos o WebDAV, manténgalo activado y dé a esos clientes tokens de
aplicación en lugar de contraseñas de cuenta, para que lo que se reutiliza en
cada solicitud se pueda revocar por separado y nunca sea la credencial del
inicio de sesión único.

## 3. ¿Siguen pudiendo iniciar sesión las cuentas de demostración documentadas?: `demoUsersDisabled` {#3-do-the-documented-demo-accounts-still-sign-in-demousersdisabled}

`IDM_CREATE_DEMO_USERS=true` crea en una instancia nueva cinco cuentas (una de
ellas de administrador) cuyos nombres y contraseñas aparecen en la
[propia documentación de OpenCloud][opencloud-demo-users]. Esta comprobación
solo se ejecuta cuando el análisis ha determinado que el proveedor de
identidad *propio* de la instancia gestiona el inicio de sesión (un Keycloak,
Authentik o Authelia externo no tiene esas cuentas que probar), y envía
exactamente esos pares publicados a ese proveedor: nada adivinado y nada
enviado a terceros.

Si se deja activado después de la fase de evaluación, es un hallazgo
`critical`: es una cuenta de administrador cuya contraseña es de dominio
público, y por sí sola limita la nota a `D`, sea cual sea el resto de lo que
haya encontrado el análisis.

**Corrección:** defina `IDM_CREATE_DEMO_USERS=false` **y** elimine las cuentas
que ya se crearon: desactivar el ajuste no las borra. Allí donde esto falle,
trate la instancia como comprometida hasta que la cuenta de administrador haya
desaparecido o tenga una contraseña real: las credenciales no son secretas,
están publicadas.

## 4. ¿Está limitada la búsqueda de cuentas a grupos compartidos?: `userEnumerationRestricted` {#4-is-account-search-restricted-to-shared-groups-userenumerationrestricted}

El documento de capacidades de OpenCloud indica si la búsqueda de usuarios
está limitada a miembros de un grupo compartido. En las versiones actuales el
estado restringido está fijado en el código, así que esta comprobación se
supera prácticamente en todas las instancias; se mantiene para detectar una
futura versión que permita configurar el ajuste en cuanto empiece a notificar
algo distinto de restringido.

**Si falla:** actualmente no hay ningún ajuste que cambiar; el hallazgo
describe la configuración propia de OpenCloud, no algo que la corrección de
`--debug` de este escáner pueda señalarle.

## 5. ¿Es suficientemente estricta la política de contraseñas de los enlaces?: `passwordPolicyEnforced` {#5-is-the-link-password-policy-strong-enough-passwordpolicyenforced}

Se lee `password_policy.min_characters` del documento de capacidades y se
compara con 8. Esto regula las contraseñas que un usuario puede definir en un
**enlace público compartido**, no las contraseñas de cuentas del proveedor de
identidad; consulte [Enlaces públicos compartidos](../sharing.md) para las
comprobaciones que determinan si un enlace necesita contraseña.

**Corrección:** defina `OC_PASSWORD_POLICY_DISABLED=false` y
`OC_PASSWORD_POLICY_MIN_CHARACTERS` con `8` o más (`8` ya es el valor
predeterminado, así que normalmente significa que alguien lo redujo
explícitamente).
`OC_PASSWORD_POLICY_MIN_{LOWERCASE,UPPERCASE,DIGITS,SPECIAL}_CHARACTERS` y una
lista de contraseñas prohibidas la hacen más estricta; consulte
[la documentación de la política de contraseñas de enlaces][link-password].

## 5a. ¿Sigue exigiendo algo más que longitud?: `passwordPolicyComplexity` {#5a-does-it-still-ask-for-more-than-length-passwordpolicycomplexity}

Una longitud mínima no es por sí sola una política de contraseñas. La política
predeterminada de OpenCloud exige además **una minúscula, una mayúscula, una
cifra y un carácter especial**, y cada uno de esos mínimos es un ajuste que
alguien puede reducir a cero. Una política de doce caracteres con los cuatro
reducidos acepta `aaaaaaaaaaaa`, que satisface `passwordPolicyEnforced` y nada
más.

Los cuatro campos `min_*_characters` se leen del mismo documento de
capacidades, y la comprobación se supera cuando todos valen al menos 1.

**Es deliberadamente un segundo indicador y no un
`passwordPolicyEnforced` más estricto.** El indicador anterior responde a "¿hay
una política y es lo bastante larga?"; este responde a "¿sigue siendo la
política que incluye OpenCloud?". Unirlos cambiaría el significado de una
alerta existente sin cambiar su nombre.

**Solo se notifica cuando la instancia publica los cuatro mínimos.** Una
política desactivada no publica ninguno (ese caso es un fallo de
`passwordPolicyEnforced`, no de este), y una medición ausente sigue siendo
desconocida en lugar de convertirse en un fallo, como en el resto del
análisis.

**Corrección:** vuelva a definir `OC_PASSWORD_POLICY_MIN_LOWERCASE_CHARACTERS`,
`OC_PASSWORD_POLICY_MIN_UPPERCASE_CHARACTERS`,
`OC_PASSWORD_POLICY_MIN_DIGITS` y
`OC_PASSWORD_POLICY_MIN_SPECIAL_CHARACTERS` con `1` o más. Cada uno vale `1`
por defecto, así que en una instancia que falla alguien los ha reducido.

## 6. ¿Se puede encontrar el proveedor de identidad?: `identityProviderDetected` {#6-can-the-identity-provider-be-found-at-all-identityproviderdetected}

Todo lo anterior pregunta si se acepta una credencial. Esta comprobación hace
la pregunta previa, *¿quién emite los tokens?*, y la responde leyendo una sola
vez `/.well-known/openid-configuration`, sin seguir redirecciones:

- un `200` con JSON: se toma el campo `issuer`;
- una redirección: se resuelve la cabecera `Location` respecto a la instancia
  y se toma en su lugar; así se reconoce un proxy que entrega la ruta
  well-known a un proveedor externo;
- cualquier otra cosa, o un emisor que no sea una URL `http(s)` absoluta con
  nombre de host: el indicador falla.

Para averiguarlo no se envía nada. No se rellena ningún formulario de inicio
de sesión ni se envía ninguna credencial: averiguar quién inicia la sesión de
los usuarios no debe convertirse en un intento de iniciar sesión.

Un fallo se debe con mucha más frecuencia a **un proxy que no reenvía
`/.well-known/`** que a una instancia sin inicio de sesión, por eso nunca
limita la nota.

El emisor encontrado también se registra como contexto, no como veredicto. Un
emisor en un host distinto al de la instancia se notifica como proveedor
**externo** (Keycloak, Authentik o Authelia delante de OpenCloud), y se indica
el fabricante para que el resultado pueda remitir a los avisos de seguridad de
ese proyecto. Usar el proveedor integrado de OpenCloud no es un hallazgo:
ninguna de las dos opciones es obligatoria y ninguna hace fallar nada.

**Si falla:** confirme que el proxy inverso reenvía `/.well-known/` a quien
emita los tokens; consulte [Proxies inversos](../reverse-proxy.md). Si
realmente no hay inicio de sesión configurado, OpenCloud incluye su propio
proveedor y se puede apuntar a uno externo.

## 7. Qué dice el documento de descubrimiento sobre la protección del inicio de sesión {#7-what-the-discovery-document-says-about-how-sign-in-is-protected}

La solicitud anterior ya está hecha. El documento que devuelve es evidencia
pública en el sentido de
[ADR 0022](../../adr/0022-identity-provider-versions-require-public-evidence.md)
(sin autenticación, de solo lectura y pensado para ser público), y cuatro de sus
campos dicen algo sobre lo que un operador puede actuar. Leerlos **no cuesta
ninguna solicitud HTTP adicional**: la misma respuesta que dio el emisor da los
cuatro.

| Indicador | Campo | Falla cuando |
|:--|:--|:--|
| `oidcPkceSupported` | `code_challenge_methods_supported` [^rfc8414] | `S256` no está entre los métodos |
| `oidcImplicitFlowDisabled` | `response_types_supported` | un tipo devuelve un token desde el punto de acceso de autorización (`token`, `id_token`) |
| `oidcSigningAlgorithmStrong` | `id_token_signing_alg_values_supported` | contiene `none` o un algoritmo `HS` |
| `oidcEndpointsUseHttps` | `issuer` y las URL de los puntos de acceso | alguna es una dirección `http://` |

[^rfc8414]: Los proveedores lo publican en el documento de descubrimiento, pero
    el campo lo define [OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html#section-2)
    y no OpenID Connect Discovery, por eso un proveedor solo OIDC puede omitirlo
    legítimamente.

**Cada uno se omite cuando el documento no publica el campo.** Es la misma
regla que en `passwordPolicyComplexity`: una medición ausente es desconocida,
nunca un fallo. Aquí importa más de lo habitual, porque el proveedor integrado
de OpenCloud omite por completo `code_challenge_methods_supported`; calificar
esa ausencia como "sin PKCE" haría fallar todas las instancias estándar por
algo que su operador no puede cambiar.

**`oidcImplicitFlowDisabled` solo se notifica para un proveedor externo.** El
proveedor integrado de OpenCloud ([libregraph/lico][lico]) publica
`response_types_supported` como `id_token token`, `id_token`, `code id_token`
y `code id_token token` (flujos implícito e híbrido, sin `code` simple), y nada
de eso es configurable. Un hallazgo sobre el que un operador no puede actuar
es peor que ninguno, así que solo se genera donde se puede actuar: delante de
Keycloak, Authentik o Authelia, donde los flujos son realmente interruptores
independientes. [Proteger un despliegue](../secure-deployment.md#keycloak) ya
le indica que exija allí PKCE y el flujo de código; esto es lo que por fin
comprueba que lo ha hecho.

**`oidcEndpointsUseHttps` solo se mide cuando la propia instancia respondió
por HTTPS.** Una instancia analizada por HTTP sin cifrar publica puntos de
acceso `http://` porque así se le preguntó, y notificarlo repetiría lo que
`httpsEnforced` ya dice una vez, en el lugar adecuado. El hallazgo que merece
la pena es la discrepancia: una instancia HTTPS cuyo proveedor sigue
anunciando `http://`, es decir, un proveedor detrás de un proxy que termina TLS
y al que nunca se le indicó su URL pública.

**Por qué estos cuatro y no el quinto evidente.** `none` en
`id_token_signing_alg_values_supported` significa que se acepta un token de ID
sin firmar, así que cualquiera puede escribir uno; un algoritmo `HS` firma con
el secreto del cliente, y los clientes de OpenCloud son clientes públicos que
no pueden guardar un secreto, así que cualquiera que lo tenga puede emitir un
token para cualquier usuario. El proveedor integrado de OpenCloud firma con
`PS256` y supera la comprobación.

## Qué más contiene ese documento y por qué no se comprueba nada de ello {#what-else-is-in-that-document-and-why-none-of-it-is-checked}

El documento de descubrimiento publica bastante más de lo que leen estos
cuatro indicadores. Verificado en `oidc/provider/provider.go`
(`InitializeMetadata`) de [libregraph/lico][lico], que es lo que sirve el
proveedor integrado de OpenCloud:

| Campo | Por qué no hay comprobación |
|:--|:--|
| `token_endpoint_auth_methods_supported` | El candidato evidente, y no es un hallazgo. Ofrecer solo `client_secret_basic` no es una debilidad, y `none` (el valor que parece alarmante) es justo lo que necesitan los clientes públicos de escritorio, móviles y web de OpenCloud. lico publica ambos. Un indicador aquí nunca se activaría o se activaría en todas las instancias. |
| `request_object_signing_alg_values_supported` | lico incluye `none` entre ellos, pero esto regula los *objetos de solicitud* firmados, no los tokens de ID. Un objeto de solicitud sin firmar no es un token sin firmar, y los clientes de OpenCloud no envían objetos de solicitud. |
| `scopes_supported`, `claims_supported` | Indican lo que se le puede pedir al proveedor, no lo que concede. Qué ámbitos se permiten a un *cliente* es configuración por cliente que el documento no muestra. |
| `subject_types_supported` | lico solo publica `public`. `pairwise` es una función de privacidad para proveedores con varios inquilinos; exigirla a un despliegue de OpenCloud con un solo inquilino sería ruido. |
| `registration_endpoint` | Su presencia no significa que el registro dinámico esté abierto: no se publica si el registro necesita un token de acceso inicial. Adivinarlo sería una afirmación rotunda basada en evidencia débil, justo lo que [ADR 0022](../../adr/0022-identity-provider-versions-require-public-evidence.md) prohíbe. |

## Gravedad y efecto en la nota {#severity-and-rating-impact}

`authentication:<path>` y `demoUsersDisabled` son `extraChecks`, que se
notifican y limitan la nota siempre que se ejecutan, con las gravedades
indicadas arriba; consulte la tabla de comprobaciones adicionales en
[la guía de comprobaciones](../scanner-checks.md#what-the-scanner-checks).
`basicAuthDisabled`, `userEnumerationRestricted`, `passwordPolicyEnforced`,
`passwordPolicyComplexity`, `identityProviderDetected` y los cuatro
indicadores `oidc*` son indicadores de refuerzo, que solo se notifican con
`--check-hardening` (o siempre en el resultado web); un indicador de refuerzo
fallido no limita la nota por sí solo, sino que eleva a `WARNING` un resultado
de Icinga que de otro modo sería `OK` y aparece en la línea
`hardenings_missing`; consulte
[Comprobaciones de refuerzo](../../README.md#hardening-checks).

[opencloud-demo-users]: https://docs.opencloud.eu/docs/admin/resources/demo-user/
[link-password]: https://docs.opencloud.eu/docs/admin/configuration/link-password-policy
[lico]: https://github.com/libregraph/lico
