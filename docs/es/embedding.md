# Comprobaciones de inserción en iframe

Una aplicación puede insertar el cliente web de OpenCloud en un `iframe`, por
ejemplo como selector de archivos o como panel de vista previa. La página
principal y el cliente insertado intercambian mensajes mediante `postMessage`;
la autenticación delegada permite además que la página principal aporte una
sesión. El escáner lee el archivo público `/config.json` para comprobar en qué
orígenes confía el cliente insertado.

Si `/config.json` no se puede leer, o no publica ningún bloque `embed`, ambas
comprobaciones se superan: la inserción no está configurada, así
que ninguna de las dos restricciones de origen puede fallar.

<!-- TOC -->
* [Insertar OpenCloud en un iframe: qué comprueba este escáner y por qué](#embedding-opencloud-in-an-iframe-what-this-scanner-checks-and-why)
  * [1. ¿Acepta el cliente insertado mensajes de cualquier origen?: `webEmbedMessageOriginRestricted`](#1-does-the-embed-accept-messages-from-any-origin-webembedmessageoriginrestricted)
  * [2. ¿Acepta la autenticación delegada un origen sin validar?: `webEmbedDelegatedAuthenticationRestricted`](#2-does-delegated-authentication-accept-an-unvalidated-origin-webembeddelegatedauthenticationrestricted)
  * [Gravedad y efecto en la nota](#severity-and-rating-impact)
<!-- TOC -->


## 1. ¿Acepta el cliente insertado mensajes de cualquier origen?: `webEmbedMessageOriginRestricted` {#1-does-the-embed-accept-messages-from-any-origin-webembedmessageoriginrestricted}

Se lee `options.embed.messagesOrigin` de la configuración web pública.
`WEB_OPTION_EMBED_MESSAGES_ORIGIN=*` significa que el cliente insertado
intercambiará mensajes `postMessage` con **cualquier** página que lo enmarque,
no solo con la integración para la que se configuró. Cualquier sitio de
internet puede entonces cargar el cliente web de OpenCloud en un marco oculto o
camuflado y empezar a enviarle mensajes que el cliente tratará como si
procedieran de una página principal de confianza.

**Corrección:** defina `WEB_OPTION_EMBED_MESSAGES_ORIGIN` con el origen exacto
de la página que puede insertar el cliente (esquema, host y puerto; ni un
comodín ni una ruta), o desactive la inserción por completo si nada la utiliza.

## 2. ¿Acepta la autenticación delegada un origen sin validar?: `webEmbedDelegatedAuthenticationRestricted` {#2-does-delegated-authentication-accept-an-unvalidated-origin-webembeddelegatedauthenticationrestricted}

La autenticación delegada permite que la página principal entregue su propia
sesión al marco insertado, para que el visitante no tenga que iniciar sesión
dos veces. Esta comprobación solo falla cuando se cumplen **las dos**
condiciones: `delegateAuthentication` es `true` *y*
`delegateAuthenticationOrigin` está vacío. Eso significa que el cliente acepta
una sesión delegada de un marco principal sin comprobar quién es realmente.
Quien pueda enmarcar la página puede entregarle una sesión, por lo que esta es
la más grave de las dos comprobaciones: se trata de eludir la autenticación, no
de un exceso en el intercambio de mensajes. Por eso se califica como
`critical`, frente al `high` de la anterior.

**Corrección:** defina `WEB_OPTION_EMBED_DELEGATE_AUTHENTICATION_ORIGIN` con el
origen exacto de la página principal de confianza, o desactive la
autenticación delegada si la integración no la necesita. La autenticación
delegada con un origen definido no es en sí un hallazgo; solo lo es la
combinación de estar activada y sin restricción.

## Gravedad y efecto en la nota {#severity-and-rating-impact}

Ambas son `extraChecks`, se notifican y limitan la nota siempre que
`/config.json` publica un bloque `embed`: `webEmbedMessageOriginRestricted` con
gravedad `high` (limita la nota a `C`) y
`webEmbedDelegatedAuthenticationRestricted` con gravedad `critical` (la limita
a `D`). Consulte la tabla de comprobaciones adicionales en
[la guía de comprobaciones](../scanner-checks.md#what-the-scanner-checks).
Ninguna requiere `--check-hardening`.
