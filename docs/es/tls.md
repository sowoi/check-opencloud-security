# Comprobaciones de TLS y certificados

El escáner examina la conexión TLS, el certificado que presenta el servidor y
los registros DNS relacionados. Estas comprobaciones describen la conexión
desde la posición de red del escáner; no enumeran todas las configuraciones
que podría encontrar otro cliente.

<!-- TOC -->
* [TLS y certificados: qué comprueba este escáner y por qué](#tls-and-certificates-what-this-scanner-checks-and-why)
  * [1. ¿Se puede establecer una conexión TLS?: `tlsHandshake`, `httpsAvailable`](#1-can-a-tls-connection-be-made-at-all-tlshandshake-httpsavailable)
  * [2. ¿Es de confianza el certificado?: `tlsTrusted`](#2-is-the-certificate-trusted-tlstrusted)
  * [3. ¿Es actual el protocolo?: `tlsProtocol`, `tlsDeprecatedProtocol`](#3-is-the-protocol-current-tlsprotocol-tlsdeprecatedprotocol)
  * [4. ¿Cubre el certificado este nombre?: `tlsHostname`](#4-does-the-certificate-cover-this-name-tlshostname)
  * [5. ¿Está completa la cadena?: `tlsChain`](#5-is-the-chain-complete-tlschain)
  * [6. ¿Está a punto de caducar el certificado, o se emitió por demasiado tiempo?](#6-is-the-certificate-about-to-expire-or-issued-for-too-long)
  * [7. ¿Son sólidos el conjunto de cifrado negociado y la política del certificado?](#7-is-the-negotiated-cipher-suite-and-certificate-policy-sound)
  * [8. ¿Presentan IPv4 e IPv6 el mismo servicio?: `tlsAddressParity`](#8-do-ipv4-and-ipv6-present-the-same-service-tlsaddressparity)
  * [9. ¿Está restringida la emisión de certificados?: `tlsCaaRecord`](#9-is-certificate-issuance-restricted-tlscaarecord)
  * [9a. ¿Se puede confiar en la propia dirección?: `tlsDnssec`](#9a-can-the-address-itself-be-trusted-tlsdnssec)
  * [10. ¿Se puede comprobar realmente la revocación?: `tlsOcspStapling`](#10-is-revocation-actually-checkable-tlsocspstapling)
  * [11. ¿Se publicó el certificado en un registro?: `tlsCertificateTransparency`](#11-was-the-certificate-published-to-a-log-tlscertificatetransparency)
  * [12. ¿Se invita a un envío 0-RTT reproducible?: `tlsEarlyData`](#12-is-a-replayable-0-rtt-flight-invited-tlsearlydata)
  * [Qué se deja sin medir deliberadamente](#what-is-deliberately-left-unmeasured)
  * [Instancias con certificado autofirmado](#self-signed-instances)
  * [Gravedad y efecto en la nota](#severity-and-rating-impact)
  * [Referencia](#reference)
<!-- TOC -->


## 1. ¿Se puede establecer una conexión TLS?: `tlsHandshake`, `httpsAvailable` {#1-can-a-tls-connection-be-made-at-all-tlshandshake-httpsavailable}

Antes que nada, el análisis intenta conectarse. Hay dos formas de fallar:

- **`httpsAvailable`** (critical): no se pudo usar HTTPS en absoluto y el
  análisis recurrió a `http://` sin cifrar. Las credenciales, las cookies de
  sesión y todos los archivos viajan sin cifrar y cualquiera en el camino
  puede leerlos o alterarlos. Nada más de esta página importa tanto.
- **`tlsHandshake`**: un puerto TLS respondió, pero no se pudo establecer
  ninguna conexión, ni siquiera con la verificación de certificados
  desactivada. Todos los demás hallazgos TLS descritos más abajo se basan en
  una conexión establecida, así que este limita el análisis: o la instancia no
  sirve TLS en este puerto, o sirve algo que el cliente no pudo negociar.

Si el HTTP sin cifrar se *redirige* a HTTPS es otro indicador,
`httpsEnforced`, que se decide en el proxy y no en la capa TLS; consulte
[Dos hallazgos que se deciden aquí y no son cabeceras](../reverse-proxy.md#two-findings-decided-here-that-are-not-headers).

## 2. ¿Es de confianza el certificado?: `tlsTrusted` {#2-is-the-certificate-trusted-tlstrusted}

`opencloud init` genera un **certificado autofirmado** salvo que se configuren
certificados reales, así que una cadena no fiable es el hallazgo TLS más
frecuente en una instancia recién instalada, y por sí solo no demuestra un
despliegue defectuoso. Consulte
[Instancias con certificado autofirmado](#self-signed-instances) para saber
cómo lo gestiona el escáner sin necesidad de que se le indique ante qué caso
está.

## 3. ¿Es actual el protocolo?: `tlsProtocol`, `tlsDeprecatedProtocol` {#3-is-the-protocol-current-tlsprotocol-tlsdeprecatedprotocol}

La RFC 8996 declaró obsoletos TLS 1.0 y 1.1 en 2021; los navegadores actuales
los rechazan directamente.

- **`tlsProtocol`** falla cuando la conexión que estableció este análisis usó
  algo anterior a TLS 1.2.
- **`tlsDeprecatedProtocol`** es una segunda pregunta, independiente: tras el
  handshake normal, el análisis abre una conexión breve *fijada* a cada
  versión obsoleta y comprueba si el servidor todavía la acepta. Un servidor
  que negocia TLS 1.3 con un cliente moderno puede seguir ofreciendo 1.0 y 1.1
  a un cliente que los pida, y lo que determina lo que un atacante puede
  forzar es la versión **más antigua** aceptada, no la que este análisis
  obtuvo. Corregirlo implica eliminar las versiones antiguas del conjunto
  ofrecido, no solo preferir la nueva.

## 4. ¿Cubre el certificado este nombre?: `tlsHostname` {#4-does-the-certificate-cover-this-name-tlshostname}

Ningún nombre alternativo del sujeto del certificado coincide con el host
analizado: dominio equivocado, `localhost` o ningún nombre alternativo (algo
que todos los clientes rechazan desde hace años; el nombre común por sí solo
no basta). Los clientes no pueden distinguir esto de una interceptación, así
que hacen bien en rechazar la conexión.

## 5. ¿Está completa la cadena?: `tlsChain` {#5-is-the-chain-complete-tlschain}

Los certificados que envió el servidor no llegan por sí solos a una raíz del
almacén de confianza público; normalmente falta un certificado intermedio. Es
el hallazgo clásico que parece correcto en un navegador de escritorio (que
guarda en caché y descarga intermedios que ya ha visto) y falla en clientes
móviles, herramientas de línea de comandos y cualquier llamada entre máquinas
que no tenga esa caché. La corrección es servir la cadena completa (el
certificado final seguido de todos los intermedios, sin la raíz), que es lo
que la mayoría de los emisores publican como archivo `fullchain`.

## 6. ¿Está a punto de caducar el certificado, o se emitió por demasiado tiempo? {#6-is-the-certificate-about-to-expire-or-issued-for-too-long}

Dos comprobaciones independientes, ambas sobre el tiempo, en sentidos
opuestos:

- **`tlsCertificate`**: la validez restante es inferior a
  `scanner.tls_min_days` (14 por defecto). A diferencia de la mayoría de los
  hallazgos, este tiene fecha: fallará tanto si alguien actúa como si no, así
  que conviene comprobar directamente la causa habitual: un emisor automático
  que dejó de renovar, o una recarga que nunca llega al proceso que realmente
  sirve TLS.
- **`tlsCertificateLifetime`** (low): el periodo de validez del certificado es
  *mayor* que el umbral de 398 días del escáner. Eso apunta a una autoridad
  privada o a un certificado emitido a mano, y el riesgo es la clave: un
  certificado válido durante años sigue siéndolo años después de que se filtre
  la clave, sin nada que obligue a la rotación que un certificado de corta
  duración impone por sí mismo.

## 7. ¿Son sólidos el conjunto de cifrado negociado y la política del certificado? {#7-is-the-negotiated-cipher-suite-and-certificate-policy-sound}

- **`tlsCipherSuite`** evalúa el conjunto de cifrado que negoció este análisis
  concreto; no pretende enumerar todos los conjuntos que el servidor podría
  ofrecer a otro cliente. Falla con una primitiva heredada (`NULL`, `RC4`,
  `3DES`/`DES-`, `MD5`, `CCM_8`) o con un conjunto sin secreto perfecto hacia
  adelante.
- **`tlsCertificatePolicy`** falla cuando el propio certificado lleva una clave
  débil (RSA de menos de 2048 bits, EC de menos de 256 bits) o una firma
  MD5/SHA-1, parámetros insuficientes incluso en un certificado que no ha
  caducado.

## 8. ¿Presentan IPv4 e IPv6 el mismo servicio?: `tlsAddressParity` {#8-do-ipv4-and-ipv6-present-the-same-service-tlsaddressparity}

Cuando un nombre de host publica ambas familias de direcciones, el análisis
comprueba que sus puntos de acceso TLS coinciden. Los visitantes pueden llegar
a cualquiera de las dos direcciones, así que un servicio IPv6 obsoleto (un
certificado antiguo, una configuración de proxy inverso olvidada o nada que
responda) puede eludir la configuración TLS que realmente se mantiene en IPv4.

Compara una dirección por familia, y solo la identidad TLS. Varios nodos
detrás de un mismo certificado presentan la misma identidad sirvan lo que
sirvan, así que un nodo al que no llegó una actualización de configuración lo
detecta `addressParity` con `--all-addresses`; consulte
[Todas las direcciones resueltas](../scanner-checks.md#every-resolved-address).

## 9. ¿Está restringida la emisión de certificados?: `tlsCaaRecord` {#9-is-certificate-issuance-restricted-tlscaarecord}

Un registro DNS **CAA** (Certification Authority Authorization) indica qué
autoridades de certificación pueden emitir certificados para un dominio. Sin
él, se puede pedir a cualquier CA de confianza pública que emita un
certificado para el nombre, no solo a la que realmente se usa. Es un hallazgo
de gravedad baja, solo comprueba el nombre exacto analizado (no la cadena de
respaldo hacia dominios superiores de la RFC 8659) y se corrige con un cambio
DNS en la zona, nunca con un ajuste de OpenCloud:

```
example.com. CAA 0 issue "letsencrypt.org"
```

## 9a. ¿Se puede confiar en la propia dirección?: `tlsDnssec` {#9a-can-the-address-itself-be-trusted-tlsdnssec}

Todo lo anterior parte de una dirección entregada por un resolvedor. Sin
**DNSSEC** esa respuesta no lleva firma, así que una respuesta falsificada por
el camino hacia el resolvedor no se distingue de la real, y el registro CAA
anterior, que restringe quién puede emitir un certificado para el nombre, llega
por el mismo canal sin autenticar y puede falsificarse con ella.

La comprobación pregunta al resolvedor que ya usa este equipo (el de
`/etc/resolv.conf`, nunca uno público) por el nombre analizado con el bit
DNSSEC activado, y lee si el resolvedor validó la respuesta, si la respuesta
llevaba firmas y si el resolvedor entendió la pregunta.

Esta última parte explica por qué a veces el hallazgo no aparece.
Un resolvedor que no admite DNSSEC responde igual que una
zona sin firmar, y notificarlo haría fallar todos los análisis ejecutados
detrás de un resolvedor así por un motivo que no tiene nada que ver con la
instancia. Por tanto:

| Lo que respondió el resolvedor | `tlsDnssec` |
|:---------------------------|:------------|
| Validó la respuesta él mismo | se supera |
| Reenvió las firmas sin validarlas | se supera: la zona está firmada, que es la parte que controla el operador |
| Ninguna de las dos cosas, pero entendió la pregunta | **falla**: la zona no está firmada |
| No admite DNSSEC o no respondió | no aparece en el resultado |

Es un hallazgo de gravedad baja, y la corrección está en la zona del propio
dominio y no en OpenCloud: firme la zona en el proveedor DNS y publique
después el registro DS resultante en la zona *superior*; una delegación sin
firmar deja desprotegida una zona firmada. Consulte
[ADR 0038](../../adr/0038-a-dnssec-answer-nobody-could-have-given-is-not-a-finding.md).

## 10. ¿Se puede comprobar realmente la revocación?: `tlsOcspStapling` {#10-is-revocation-actually-checkable-tlsocspstapling}

El certificado indica un servidor OCSP, pero el servidor no adjunta la
respuesta de revocación al handshake, así que cada cliente tiene que
preguntar él mismo a la autoridad. Eso le revela a la autoridad quién está de
visita, y cuando el servidor OCSP es lento suele omitirse en lugar de tratarse
como un fallo. Es solo un hallazgo de gravedad baja: la mayoría de las
autoridades actuales, entre ellas Let's Encrypt, ya no publican ningún
servidor OCSP, y la comprobación no se aplica a esos certificados.

## 11. ¿Se publicó el certificado en un registro?: `tlsCertificateTransparency` {#11-was-the-certificate-published-to-a-log-tlscertificatetransparency}

Certificate Transparency es el registro público, de solo adición, de todos los
certificados que emite una autoridad pública. Existe para que el propietario
de un dominio pueda descubrir que se emitió a otra persona un certificado para
su nombre, una emisión indebida que de otro modo sería invisible hasta que se
usara.

Un certificado participa llevando **marcas de tiempo de certificado firmadas**
(SCT) incrustadas por la autoridad emisora. El análisis las cuenta en el
certificado que ya ha descargado, con la misma llamada
`openssl x509 -text` que lee la clave y el algoritmo de firma: ni conexiones ni
procesos adicionales.

La comprobación busca específicamente SCT incrustadas en el certificado. La
falta de SCT incrustadas produce un hallazgo `medium`, pero por sí sola no
demuestra que un navegador vaya a rechazar la conexión: la evidencia de
Certificate Transparency también puede entregarse por otros mecanismos.

`tlsCertificateTransparency` solo se evalúa cuando la cadena llega a una raíz
pública. Los certificados privados o autofirmados quedan fuera del alcance de
esta comprobación. Si el OpenSSL local no puede decodificar la extensión, el
hallazgo se omite en lugar de registrarse como superado.

**Corrección:** vuelva a emitir el certificado con una autoridad de
certificación que incruste SCT. Todas las públicas lo hacen desde hace años,
incluida Let's Encrypt; un certificado de confianza sin ellas casi seguro que
lo emitió una CA privada que aun así figura en el almacén de confianza del
cliente.

## 12. ¿Se invita a un envío 0-RTT reproducible?: `tlsEarlyData` {#12-is-a-replayable-0-rtt-flight-invited-tlsearlydata}

TLS 1.3 permite que un cliente que reanuda una sesión envíe su primera
solicitud en el mismo envío que el handshake: "0-RTT", o datos tempranos.
Ahorra un viaje de ida y vuelta y, por diseño, no tiene protección contra la
reproducción en la capa TLS: quien pueda grabar ese envío puede volver a
enviarlo, y el servidor no distingue la copia del original.

En un servicio de archivos, eso significa una solicitud de mover, copiar o
borrar reproducida en el momento que elija otra persona. Un servidor correcto
limita 0-RTT a solicitudes idempotentes, pero nada en la comunicación demuestra
que lo haga; por eso es un hallazgo `low` y no uno más grave.

El análisis lee el límite `Max Early Data` que anuncian los tickets de sesión
del propio servidor, en el mismo handshake de `openssl s_client` que responde
a la pregunta sobre el stapling. Un servidor que nunca menciona un límite (un
servidor TLS 1.2, o uno cuyos tickets prohíben los datos tempranos en algunas
compilaciones) se notifica como desconocido, no como si los aceptara.

**Corrección:** desactive los datos tempranos en lo que termine TLS.
`ssl_early_data` de nginx está `off` por defecto; Caddy y Traefik no los
activan. Déjelos activados solo cuando un problema de latencia medido lo
justifique *y* se sepa que la aplicación rechaza las solicitudes no
idempotentes reproducidas.

## Qué se deja sin medir deliberadamente {#what-is-deliberately-left-unmeasured}

El escáner no marca como superada una comprobación que no pudo realizar.
Si la compilación de OpenSSL no admite TLS 1.0, el escáner no puede determinar
si el servidor acepta ese protocolo. Sin el ejecutable `openssl`, tampoco
puede comprobar el stapling OCSP. En ambos casos, la comprobación se omite
del resultado.

**Un certificado que no supera la verificación se lee igualmente.**
`getpeercert()` no devuelve nada para un par no verificado, así que en las
instancias autofirmadas, donde más importa, el escáner descarga el
certificado en formato DER y lo decodifica por su cuenta: la misma fecha de
caducidad, cobertura de nombres y emisor que notificaría un certificado de
confianza, se valide o no la cadena.

## Instancias con certificado autofirmado {#self-signed-instances}

El escáner gestiona un certificado autofirmado o no fiable sin necesidad de
que se le indique ante qué caso está:

1. HTTPS con verificación de certificado. Si funciona, todo lo anterior se
   evalúa con normalidad.
2. HTTPS sin verificación. El análisis continúa y notifica `tlsTrusted` como
   comprobación fallida: se sigue obteniendo el resultado completo, junto con
   el hecho de que la cadena no es de confianza.
3. HTTP sin cifrar: `httpsAvailable` (critical).

`--insecure` (`COS_INSECURE`) omite el requisito de verificación del paso 1.
La cadena no fiable se sigue mostrando en la salida, pero deja de restar
en la nota. Úselo para una instancia que sabe que es autofirmada, para que un
certificado *realmente* defectuoso en otro lugar siga destacando en lugar de
perderse entre hallazgos esperados.

## Gravedad y efecto en la nota {#severity-and-rating-impact}

Todas las comprobaciones de esta página son entradas de `extraChecks`, así que
un fallo limita la nota como cualquier otra comprobación adicional fallida
(critical -> `D`, high -> `C`, medium -> `A`, low -> `A+`); consulte
[Comprobaciones de refuerzo](../../README.md#hardening-checks) para ver en qué
se diferencia de un simple indicador de refuerzo, y la tabla de comprobaciones
adicionales en [la guía de comprobaciones](../scanner-checks.md#what-the-scanner-checks)
para la lista completa de gravedades.

## Referencia {#reference}

[Proxies inversos](../reverse-proxy.md) trata las cabeceras que debe definir
un proxy situado delante de OpenCloud; esta página solo se ocupa de la capa TLS
que hay por debajo.
