# Biblioteca y CLI JSON del escáner de seguridad de OpenCloud

El motor de análisis que hay detrás de `check-opencloud-security` y del
servicio `check-opencloud-scanner`.

El escáner se conecta directamente a la instancia por HTTP(S), comprueba los
ajustes observables públicamente y devuelve un documento de resultado con una
nota de `0` a `5`. También prueba las credenciales de demostración
documentadas contra el proveedor de identidad propio de la instancia.

La escala de notas sigue la de la API de análisis de Nextcloud, para que los
umbrales, los datos de rendimiento, los webhooks y los paneles
existentes conserven su significado.

| Módulo | Finalidad |
|:-------|:--------|
| `scanner.py` | El motor de análisis; produce el documento de resultado |
| `releases.py` | Comprobación de actualizaciones con el canal de versiones de OpenCloud |
| `vulndb.py`, `data/` | Base de datos de avisos de seguridad y comparación de rangos de versiones |
| `versions.py` | Análisis y comparación de versiones, y periodo de versiones con soporte |
| `config.py`, `secrets.py` | Configuración por YAML, entorno y proveedores de secretos |
| `service.py`, `cli.py` | El servicio de análisis HTTP y el comando `check-opencloud-scanner` |
| `factory.py` | Construye objetos de ajustes a partir de una `Configuration` |
| `tls.py` | Seguridad del transporte: handshake, protocolo, certificado, cadena, stapling |

## Qué lee de la instancia {#what-it-reads-from-the-instance}

En OpenCloud hay dos puntos de acceso públicos, y se necesitan ambos:

- **`/status.php`**: producto, edición, `productversion`. También lleva
  `maintenance`, `installed` y `needsDbUpgrade`, pero el propio manejador de
  OpenCloud fija los tres en el código en lugar de leer un estado real, así que
  este paquete no los comprueba; consulte
  [`docs/status-php.md`](../status-php.md).
- **`/ocs/v1.php/cloud/capabilities`**: los indicadores de funciones de los
  que se deriva la sección de refuerzo descrita más abajo

Todo lo demás se deduce de las cabeceras de respuesta, los códigos de estado y
las conexiones TCP.

Una respuesta de `/status.php` por sí sola no identifica OpenCloud. El escáner
comprueba el producto notificado y lanza `ScanError` si es otro producto, cuyas
versiones, avisos de seguridad y valores predeterminados no corresponderían a
esta base de datos. Consulte [Qué es OpenCloud](../what-is-opencloud.md).

### La trampa de la versión {#the-version-trap}

`/status.php` notifica tres campos de versión:

```json
{"version": "0.1.0.0", "versionstring": "0.1.0", "productversion": "7.4.0"}
```

`version` y `versionstring` son **constantes fijas en el código**
(`pkg/version` en el código fuente de OpenCloud). Existen para que sigan
funcionando los clientes de sincronización antiguos que esperan una cadena de
versión al estilo de ownCloud, y son idénticas en todas las instancias
publicadas. Solo `productversion` es la versión real.

Por eso `versions.select_version()` prefiere `productversion`, recurre al
punto de acceso de capacidades si falta y considera inutilizables los
marcadores conocidos. Cuando una instancia no ofrece más que el marcador, el
documento de resultado lleva `legacyVersion` y las comprobaciones de fin de
vida, actualizaciones y avisos de seguridad se omiten en lugar de ejecutarse
contra `0.1.0`.

Si ya procesa `/status.php` en otro script, este es el campo que debe
comprobar.

## Algoritmo de calificación {#rating-algorithm}

Se evalúa en este orden:

| Nota | Letra | Condición |
|:------:|:-----:|:----------|
| 0 | F | Fin de vida |
| 1 | E | Vulnerabilidad de gravedad crítica o alta |
| 2 | D | Cualquier otra vulnerabilidad conocida |
| 3 | C | Una línea de versiones completa por detrás |
| 4 | A | Actualización disponible dentro de la línea de versiones |
| 5 | A+ | Actualizada |

y después se **limita** según la peor comprobación adicional fallida:
`critical` -> como máximo `2` (D), `high` -> `3` (C), `medium` -> `4` (A),
`low` -> `5` (A+).

Un límite solo puede reducir la nota inicial, así que un hallazgo de
configuración no puede mejorar un resultado de fin de vida. Tenga en cuenta la
consecuencia para la monitorización: un hallazgo crítico limita la puntuación a
`2` (`D`), que el valor predeterminado `--critical 1` notifica como WARNING.
Use `--critical 2` para que sea CRITICAL.

Para notificar los hallazgos sin tocar la nota:

```yaml
scanner:
  extra_checks_rating: false
```

O prescinda por completo de las comprobaciones adicionales con
`--no-extra-checks`.

Cada análisis registra en `ratingExplanation` cómo ha llegado a su nota:

```json
{
  "rating": 4,
  "base": {"rating": 5, "reason": "the installed release is current and no advisory matches this version"},
  "caps": [
    {"check": "basicAuthDisabled", "severity": "medium", "cap": 4,
     "detail": "PROXY_ENABLE_BASIC_AUTH is on", "applied": true}
  ]
}
```

`base` es la nota que produjeron solo la versión y la base de datos de avisos;
`caps` enumera cada comprobación adicional fallida con el techo que impone su
gravedad. Una comprobación que falló sin decidir el resultado se conserva con
`applied: false`, para que un hallazgo nunca desaparezca en silencio del
razonamiento. La lista se ordena por gravedad, lo que hace que la explicación
no dependa del orden en que se ejecutaron las comprobaciones.

## Qué subiría la nota {#what-would-raise-the-rating}

El mismo resultado incluye un `remediationPlan`, construido por
`remediation.py` a partir de los límites anteriores: una lista ordenada de
correcciones con la nota que alcanzaría cada paso.

```json
{
  "currentRating": 3,
  "achievableRating": 5,
  "summary": "Two fixes would raise this instance from 3/5 to 5/5.",
  "steps": [
    {"order": 1, "id": "exposed:/opencloud.yaml", "kind": "finding",
     "severity": "high", "title": "A deployment file is publicly readable",
     "action": "Stop serving the deployment directory ...",
     "ratingBefore": 3, "ratingAfter": 4, "ratingGain": 1}
  ],
  "blocked": [],
  "waived": []
}
```

Es una repetición de `_compute_rating` quitando un hallazgo cada vez, no un
segundo modelo de la nota, así que una nota prevista no puede discrepar de la
real. No se guarda nada nuevo: el plan se deriva del documento en el que está.

Tres propiedades son fundamentales y tienen pruebas:

- El **orden** es por límite, después por gravedad y después por
  identificador, así que no depende del orden en que se ejecutaron las
  comprobaciones. Un paso que por sí solo no gana nada (el primero de varios
  hallazgos que comparten un mismo techo) sigue en la lista con
  `ratingGain: 0` en lugar de ocultarse.
- **Una actualización también es un paso**, insertado en la primera posición
  en la que empieza a aportar algo. Corregir hallazgos no puede elevar una nota
  por encima de lo que permite la versión instalada, así que un plan que
  pusiera primero la actualización prometería una mejora que no podría
  cumplir.
- **Los hallazgos que no se pueden corregir** (`actionable: false`, los
  indicadores que OpenCloud fija en el código) van a `blocked` y permanecen en
  cada resto simulado, que es lo que acota correctamente `achievableRating`.

Una versión sin soporte lleva la nota directamente a `0` sin registrar ningún
límite, así que en ese único caso el plan los reconstruye a partir de
`extraChecks`. De lo contrario, prometería una puntuación perfecta tras una
actualización con un hallazgo crítico todavía abierto.

## El problema de la aplicación de una sola página {#the-single-page-application-problem}

OpenCloud es un único binario Go que sirve una interfaz de una sola página
incrustada. Esa interfaz responde a las **rutas desconocidas con HTTP 200 y el
armazón de la aplicación**, así que la comprobación ingenua de rutas expuestas
("¿devuelve 200 `/opencloud.yaml`?") notifica unas cuantas exposiciones
fantasma en cada instancia sana.

Antes de sondear nada, el escáner solicita una ruta que no puede existir
(`/check-opencloud-security-probe-404`) y registra la respuesta. Una ruta solo
se notifica como expuesta cuando su respuesta difiere realmente de esa línea
base general. La misma protección cubre los proxies inversos configurados con
una regla de respaldo general.

## Detección de fin de vida {#end-of-life-detection}

OpenCloud mantiene a la vez tres tipos de versiones, y cada uno tiene su propio
periodo de soporte:

| Canal | Frecuencia | Con soporte hasta |
|:------|:--------|:----------------|
| `rolling` | aproximadamente cada 3 semanas | que se publica su sucesora |
| `production` | aproximadamente cada 6 meses | la siguiente versión production |
| `lts` | una línea production | 2 años después de abrirse la línea |

Así que un número de versión por sí solo no responde a "¿sigue teniendo
soporte?". `7.2.3` es la versión production actual aunque el canal rolling ya
vaya por `7.4.0`, y `7.3.0`, una versión *superior*, dejó de recibir
correcciones el día en que apareció `7.4.0`.

La unidad de soporte es la **línea de versiones** (`MAJOR.MINOR`), porque es lo
que mantiene OpenCloud: `7.2.3` es un parche de la línea `7.2`. Una línea puede
publicarse en varios canales, y se evalúa según el que le dé soporte durante
más tiempo:

- `7.2` se publicó como versión rolling y después pasó a production. Como
  versión rolling está sin soporte (existe la 7.3); como versión production
  está actualizada. **Actualizada** es la respuesta que importa.
- `4.0` es la línea production anterior *y* la línea LTS actual. Su periodo
  production terminó cuando llegó `7.2`, pero sus correcciones LTS se mantienen
  hasta dos años después de `4.0.0`.

`schedule_source.py` lee las fechas de publicación de la
[documentación de administración de OpenCloud][lifecycle], la única fuente que
indica el *tipo* de versión; la lista de versiones de GitHub no distingue una
versión rolling de una production. `scripts/update_release_schedule.py` lo
ejecuta en CI y escribe el resultado en `data/release_schedule.json`, que es el
archivo que se distribuye:

[lifecycle]: https://docs.opencloud.eu/docs/admin/resources/lifecycle/

```json
{
  "lifetime_days": {"rolling": 21, "production": 183, "lts": 730},
  "latest_release": {"production": "7.2.3", "rolling": "7.4.0"},
  "lines": [
    {"line": "7.4", "tracks": ["rolling"], "released": "2026-08-03", "latest": "7.4.0"},
    {"line": "7.2", "tracks": ["production", "rolling"], "released": "2026-06-25", "latest": "7.2.3"},
    {"line": "4.0", "tracks": ["lts", "production"], "released": "2025-12-01", "latest": "4.0.8"}
  ]
}
```

Las líneas rolling y production terminan cuando se publica su sucesora en el
mismo canal; `lifetime_days` acota la línea más reciente de un canal y da a LTS
el periodo de dos años que promete la documentación. Una línea sin soporte
recibe `EOL: true` y la nota `F`.

Hay dos casos que deliberadamente *no* son fin de vida:

- una versión más reciente que todo lo que contiene el calendario, porque el
  archivo incluido envejece entre actualizaciones y una versión recién
  publicada no debe hacer saltar la alarma;
- la línea más reciente de un canal, que no tiene nada a lo que actualizar.

Cuando la instancia es más reciente que el calendario, el resultado incluye
`scheduleStale`, `scheduleUpdated`, `scheduleSource` y un `scheduleNote` que
enlaza a la [página de ciclo de vida][lifecycle]. Estos campos describen los
datos de referencia sin cambiar la nota ni la recomendación de actualización.
`ReleaseSchedule.is_behind()` ofrece la misma comparación.

El complemento conserva el calendario con el que se distribuyó: un host de
monitorización ejecuta la comprobación cada pocos minutos y no debe convertir
eso en una descarga de documentación, así que el archivo se actualiza
actualizando el paquete. La aplicación web es el otro caso, un proceso que
sigue en marcha durante meses, y vuelve a leer la misma página una vez al día
mediante `schedule_source.fetch_schedule_document()`, entregando el resultado a
`ScannerSettings.release_schedule`. En ambos casos al escáner se le *entrega*
un calendario y no decide nada nuevo sobre su procedencia.

```yaml
scanner:
  use_release_schedule: true       # false skips the EOL check entirely
  # release_schedule: /etc/check-opencloud-security/release_schedule.json
```

El veredicto completo aparece como `lifecycle` en el documento de resultado
(línea, canal, fecha de publicación, fin del soporte, días restantes, versión a
la que actualizar y antigüedad del calendario que lo decidió todo), para que un
calendario obsoleto o sustituido se vea y no pase desapercibido.

## Comprobación de actualizaciones {#update-check}

Una instancia de OpenCloud no notifica actualizaciones pendientes: no hay
comando `occ` ni punto de acceso de actualización. Por eso la versión más
reciente se busca externamente y se compara con `productversion`.

La recomendación **tiene en cuenta el canal**. Un canal de versiones solo
conoce la versión más reciente en general, que siempre es una rolling, así que
ofrecerla a una instancia production o LTS la llevaría a un periodo de soporte
de tres semanas. A esas instancias se les ofrece en su lugar la versión más
reciente de su propio canal, y la más reciente en general se notifica aparte
como `newestRelease`.

| Modo | Comportamiento |
|:-----|:----------|
| `auto` | Prueba el canal; ante cualquier fallo usa `latest_release` de los datos incluidos |
| `feed` | Solo el canal; un fallo se notifica como desconocido |
| `pinned` | Usa el `latest_version` configurado; sin acceso a la red |
| `bundled` | Usa el `latest_release` incluido; sin acceso a la red |
| `off` | Omite la comprobación de actualizaciones |

`auto` es el valor predeterminado y nunca hace fallar una comprobación: si
GitHub limita la frecuencia o no está accesible, se recurre a la versión
incluida, que es tan reciente como el paquete instalado. `feed` es el modo
adecuado cuando se prefiere un estado `UNKNOWN` explícito a recurrir a los
datos incluidos sin avisar.

El canal es por defecto la API de versiones de GitHub. `parse_release_feed()`
entiende también un documento simple `{"tag_name": ...}` y una lista de
versiones, así que una réplica interna no necesita ningún formato especial. Se
omiten los borradores y las versiones preliminares.

## Vulnerabilidades {#vulnerabilities}

### Actualizar los datos de referencia en un host de monitorización {#refreshing-reference-data-on-a-monitoring-host}

El paquete incluye un comando `refresh-data` independiente para las
instalaciones que no pueden esperar a una actualización del paquete:

```console
$ check-opencloud-scanner refresh-data \
    --output-dir /var/lib/check-opencloud-security
/var/lib/check-opencloud-security/release_schedule.json
/var/lib/check-opencloud-security/vulnerabilities.json
```

Lee ambos documentos del propio repositorio de este proyecto (los archivos
revisados que ha integrado una persona encargada del mantenimiento, no una
consulta en directo a un tercero) y **verifica una certificación de Sigstore**
de ambos antes de aceptarlos. Después rechaza un documento de ciclo de
vida que pierda una línea de versiones incluida, rechaza avisos sin límites y
sustituye cada archivo de forma atómica. Nunca escribe en el paquete
instalado. Apunte `scanner.release_schedule` y `scanner.vulnerability_db` a los
dos archivos generados y ejecute a diario el
[`check-opencloud-security-refresh.timer`](../../contrib/systemd/check-opencloud-security-refresh.timer)
incluido. Un fallo de red deja intactos los archivos anteriores.

La verificación de firmas necesita el extra `signing`:

```console
$ pip install 'check-opencloud-security[signing]'
```

Sin él, la actualización se ejecuta igualmente: recurre solo a las
protecciones estructurales y registra una advertencia indicándolo. Tenga en
cuenta lo que significa: un host sin el extra no comprueba en absoluto la
procedencia, así que instálelo en todos los lugares donde la actualización
importe realmente.

Con el extra instalado, hay tres resultados posibles. Un
documento verificado se escribe. Una firma que no se pudo *comprobar* (la
certificación aún no está publicada, GitHub no está accesible, la raíz de
confianza no se cargó) genera una advertencia y recurre a las protecciones
estructurales. Una firma presente e *incorrecta* detiene la actualización y
deja los archivos anteriores exactamente donde estaban.

Indicar `--schedule-url` o `--advisory-url` consulta esa fuente en directo y
sin verificar, para una réplica aislada o una bifurcación, y lo indica en el
registro. Consulte
[ADR 0027](../../adr/0027-refreshed-reference-data-is-attested-not-merely-fetched.md).

`data/vulnerabilities.json` contiene los avisos de seguridad publicados para
OpenCloud y se regenera a diario mediante
`.github/workflows/vulnerability-db.yml`, que ejecuta
`scripts/update_vulnerability_db.py` contra la API de consultas de OSV y abre
una pull request cuando la respuesta ha cambiado. La actualización **solo
añade**: un aviso que el canal ha olvidado se queda en el archivo, y una
entrada escrita a mano se conserva. Una entrada solo se elimina a mano.

Aun así, solo es tan completo como los canales a partir de los que se
construye. `vulnerabilities: []` en un análisis significa *"nada de la base de
datos que ha configurado coincide"*, no *"esta instancia no tiene
vulnerabilidades conocidas"*, y una gran parte de la nota procede en cualquier
caso de las comprobaciones de configuración. Añada su propia fuente si tiene
una:

```yaml
scanner:
  vulnerability_db: /etc/check-opencloud-security/advisories.json
  vulnerability_feed: https://api.osv.dev/v1/query
```

Se aceptan tres formatos de entrada (el nativo,
`{"advisories": [{"id": ..., "introduced": ..., "fixed": ...}]}`, el formato
de la GitHub Advisory API y los documentos OSV), así que una instalación
aislada puede replicar un canal en un archivo sin conversión. Las entradas se
comparan con el rango de versiones semiabierto `[introduced, fixed)` y se
deduplican por identificador entre fuentes. Las fuentes que se cargaron
realmente aparecen como `advisorySources` en el documento de resultado, para
que una ruta mal configurada se vea y no pase desapercibida.

Un aviso puede afectar a varias líneas de versiones que se corrigieron por
separado. `GHSA-vf5j-r2hw-2hrw` se corrigió tanto en `4.0.3` como en `5.0.2`,
y es un único aviso con dos rangos disjuntos, no dos avisos, así que una
entrada puede llevar una lista `ranges`:

```json
{
  "id": "GHSA-vf5j-r2hw-2hrw",
  "severity": "high",
  "ranges": [
    {"introduced": "4.0.0", "fixed": "4.0.3"},
    {"introduced": "5.0.0", "fixed": "5.0.2"}
  ]
}
```

Una coincidencia notifica la corrección correspondiente a la línea de la
instancia analizada, así que a una instancia `5.0.1` se le indica que
actualice a `5.0.2` y no a una versión que no corrige nada para ella.
`introduced` y `fixed` se mantienen a su lado como el primer rango, que es lo
que siempre ha sido un aviso de un solo rango.

**Un aviso sin ningún límite de versión se descarta**, venga de donde venga.
Un rango abierto por ambos extremos coincide con todas las versiones que han
existido, y los canales públicos sí publican esa forma: la base de datos de
vulnerabilidades de Go registra este mismo aviso como `introduced: "0"` sin
corrección. Creérselo notificaría como vulnerables todas las instancias de
OpenCloud del mundo, así que el analizador lo rechaza en lugar de confiar en
que el canal sea sensato.

## Refuerzos {#hardenings}

Este paquete **no tiene matriz de refuerzos**. No deduce "esta versión admite
la función X, así que X está activada": solo notifica lo que la instancia ha
dicho realmente:

| Refuerzo | Evidencia |
|:----------|:---------|
| `hstsLongMaxAge` | `Strict-Transport-Security` con `max-age` >= un año |
| `hstsPreload` | La misma cabecera con `preload` |
| `cspWithoutUnsafeInline` | Una `Content-Security-Policy` sin `'unsafe-inline'` |
| `basicAuthDisabled` | `WWW-Authenticate` en un punto de acceso protegido que no ofrece `Basic` |
| `publicLinkPasswordEnforced` | Capacidades: contraseña obligatoria en los enlaces públicos |
| `publicLinkExpirationEnforced` | Capacidades: caducidad obligatoria en los enlaces públicos |
| `userEnumerationRestricted` | Capacidades: búsqueda de usuarios restringida |
| `passwordPolicyEnforced` | Capacidades: política activada y longitud mínima de contraseña >= 8 |
| `passwordPolicyComplexity` | Capacidades: la política sigue exigiendo una minúscula, una mayúscula, una cifra y un carácter especial |
| `oidcPkceSupported` | Documento de descubrimiento: `code_challenge_methods_supported` contiene `S256` |
| `oidcImplicitFlowDisabled` | Documento de descubrimiento: `response_types_supported` no devuelve ningún token desde el punto de acceso de autorización (solo proveedores externos) |
| `oidcSigningAlgorithmStrong` | Documento de descubrimiento: `id_token_signing_alg_values_supported` no tiene `none` ni ningún algoritmo `HS` |
| `oidcEndpointsUseHttps` | Documento de descubrimiento: todos los puntos de acceso publicados son `https://` (solo se mide cuando la propia instancia respondió por HTTPS) |

Una clave se omite por completo cuando no hay evidencia correspondiente: una
cabecera ausente o una instancia cuyo punto de acceso de capacidades no
notifica esa función. Así, una versión antigua no acumula hallazgos
fantasma, y `capabilitiesAvailable` en el documento de resultado indica si se
pudo evaluar la segunda mitad de la tabla.

Los sondeos adicionales también leen la configuración web pública: los
orígenes de mensajes de inserción con comodín hacen fallar
`webEmbedMessageOriginRestricted`, la autenticación delegada en iframe sin un
origen explícito hace fallar `webEmbedDelegatedAuthenticationRestricted`, y un
servicio de OpenCloud que responde en el puerto directo del backend hace fallar
`backendPortClosed`.

Tenga en cuenta lo siguiente antes de activar `--check-hardening`:

- **`cspWithoutUnsafeInline` falla en un OpenCloud estándar.** El `csp.yaml`
  predeterminado contiene `'unsafe-inline'` en `script-src` y `style-src`. Se
  notifica en lugar de excusarse, pero corregirlo implica distribuir su propia
  CSP, y la interfaz web depende actualmente de scripts y estilos en línea.
- **`basicAuthDisabled` es realmente observable a distancia.** Con
  `PROXY_ENABLE_BASIC_AUTH=true`, el proxy añade `Basic realm="<host>"` a su
  desafío `WWW-Authenticate` junto a `Bearer`. Se califica como `medium`, y como
  `low` cuando `identityProvider.external` es verdadero: los clientes CalDAV,
  CardDAV y WebDAV no admiten OpenID Connect, así que una instancia que los
  quiera tiene que dejar activada la autenticación básica, y calificarlo como
  un fallo grave decía a los operadores algo que con razón no se creían.
- **`publicLinkExpirationEnforced` y `userEnumerationRestricted` no son
  ajustes.** OpenCloud escribe ambas capacidades como constantes fijas, así que
  la primera falla en todas las instancias y la segunda se supera en todas.
  Están marcadas como `actionable=False` en el catálogo descrito más abajo, lo
  que las mantiene fuera de las alertas y los recuentos pero las deja en el
  documento de resultado.

### Observaciones que no son hallazgos {#observations-that-are-not-findings}

`scan()` notifica además dos integraciones visibles sin iniciar sesión. Están
en `integrations`, no producen ninguna entrada en `extraChecks` y no pueden
cambiar la nota:

| Clave | Evidencia |
|:----|:---------|
| `integrations.office.detected` | `/app/list`, que la política del proxy de OpenCloud no protege, indica al menos un proveedor de aplicaciones registrado |
| `integrations.office.apps` | Los nombres de proveedores que devolvió, p. ej. `Collabora` |
| `integrations.office.groupware` | La capacidad `groupware.enabled` |
| `integrations.calendar.detected` | `/.well-known/caldav` responde con una redirección o una solicitud de autenticación en lugar de 404 |
| `integrations.calendar.advertised` | La capacidad `core.support_radicale`, que por defecto es `true` y por tanto solo sirve de confirmación |

La capacidad `files.app_providers` es una constante fija y se ignora.

`setup.advisoryChecks` es el otro bloque que no puede cambiar la nota, por otro
motivo: no porque la observación sea neutral, sino porque OpenCloud no la
cumple en ninguna instancia, así que contarla presentaría el estado de serie
del software como un fallo de este despliegue. Contiene dos entradas:

- `securityTxtPublished`: si `/.well-known/security.txt` contiene el campo
  `Contact` que exige la RFC 9116, para que quien encuentre un fallo sepa
  adónde enviarlo. Lo que se lee es el cuerpo, no el código de estado: una
  instancia cuya interfaz responde a cualquier ruta desconocida con su propio
  armazón también devuelve 200 para esa ruta.
- `hstsPreloadEligible`: si la cabecera `Strict-Transport-Security` se
  aceptaría realmente para la precarga en navegadores, lo que requiere a la vez
  un max-age de al menos un año, `includeSubDomains` y `preload`. `hstsPreload`
  en el bloque `hardenings` responde a la pregunta más limitada de si la
  directiva está presente; el proxy de OpenCloud la envía junto con diez años y
  sin `includeSubDomains`, así que la cabecera de toda instancia estándar pide
  algo que la lista de precarga rechaza. Deliberadamente no se mide si el
  dominio *figura* en la lista; consulte
  [ADR 0037](../../adr/0037-preload-eligibility-is-measured-list-membership-is-not.md).

El bloque es `{}` y no un diccionario de `false` cuando las comprobaciones
adicionales están desactivadas, porque una observación que nadie ha hecho no es
una observación fallida. Consulte
[ADR 0034](../../adr/0034-an-advisory-observation-need-not-be-a-header.md).

La observación `identityProvider` nombra un proveedor externo cuando su emisor
OIDC lo identifica. Para Keycloak, Authelia y Authentik incluye además
`advisoryUrl`, que apunta a la página oficial de GitHub Security Advisories del
proveedor. `version` está presente pero vacío, porque ninguno de estos
proveedores expone su versión de producto en un punto de acceso público y
activado por defecto. El escáner no la adivina a partir de rutas de URL,
recursos ni cabeceras del proxy; si llegara a haber evidencia pública fiable de
la versión, ese campo podría contenerla sin cambiar la forma del resultado.

### Lo que el escáner no puede medir {#what-the-scanner-cannot-measure}

Hay dos preguntas que surgen tan a menudo que conviene declararlas como
objetivos excluidos:

- **El registro de auditoría no se puede comprobar.** El servicio de auditoría
  de OpenCloud consume el bus de eventos interno y no expone ninguna superficie
  HTTP; ninguna capacidad, cabecera ni documento público revela si está en
  marcha. No hay ninguna señal que leer, así que no existe ninguna comprobación
  y no se puede añadir ninguna sin credenciales.
- **"Configurado correctamente" queda fuera del alcance de las integraciones
  anteriores.** Que un proveedor esté registrado no dice nada de los secretos
  WOPI, los permisos de uso compartido ni la configuración propia del segundo
  servicio, todo lo cual está detrás de un inicio de sesión.

El escáner no usa credenciales de usuarios normales. La excepción documentada
es `_demo_user_finding`: con el proveedor integrado, prueba las cuentas de
demostración publicadas a través de `/ocs/v1.php/cloud/user`. Un inicio de
sesión correcto produce el hallazgo crítico `demoUsersDisabled`. No se envía
ninguna credencial a un proveedor externo. Un rechazo solo confirma que esas
credenciales de demostración han fallado, no que la autenticación sea segura en
todos los aspectos.

### Explicar los indicadores {#explaining-the-flags}

`hardening.py` es el catálogo que convierte estos identificadores en algo sobre
lo que un operador puede actuar. Para cada indicador contiene un significado en
lenguaje sencillo, la variable de entorno de OpenCloud que lo regula y un
enlace a la documentación oficial:

```python
from opencloud_local_scan import describe_hardening

print(describe_hardening("basicAuthDisabled").describe())
```

```text
basicAuthDisabled: HTTP Basic authentication is enabled
    The instance answers with a 'WWW-Authenticate: Basic' challenge, so ...
    Setting: PROXY_ENABLE_BASIC_AUTH
    Fix: Set PROXY_ENABLE_BASIC_AUTH=false (the default). ...
    Docs: https://docs.opencloud.eu/docs/dev/server/services/proxy/environment-variables
```

El catálogo cubre también las cabeceras de seguridad de `setup.headers`, las
observaciones de `setup.advisoryHeaders` y `setup.advisoryChecks`, y
`httpsEnforced`, y devuelve un marcador con nombre para un identificador que no
conoce, de modo que una comprobación futura nunca pueda romper un informe. Una
prueba analiza la instancia simulada y verifica que cada indicador que produce
tiene una entrada, así que añadir un refuerzo sin documentarlo hace fallar el
conjunto de pruebas.

El mismo catálogo está disponible como comando, para el caso mucho más
habitual de tener un identificador y ningún intérprete de Python a mano:

```shell
$ check-opencloud-scanner explain basicAuthDisabled
$ check-opencloud-scanner explain exposed:/config/opencloud.yaml
$ check-opencloud-scanner explain --category transport
$ check-opencloud-scanner explain --list
$ check-opencloud-scanner explain --format json cookieSecure
```

El comando funciona sin conexión y solo lee el catálogo instalado. Acepta
nombres de cabeceras e identificadores con ruta, como
`exposed:/config/opencloud.yaml`. Sin identificador, imprime el catálogo
completo. Un identificador desconocido devuelve el código de salida 1 y sugiere
nombres parecidos.

### La misma corrección, como configuración {#the-same-fix-as-configuration}

`snippets.py` convierte las entradas `env_fix` y `header_fix` del catálogo en
fragmentos de configuración:

```python
from opencloud_local_scan import configuration_fragment

print(configuration_fragment(["basicAuthDisabled", "demoUsersDisabled"], "compose").text)
```

```yaml
services:
  opencloud:
    environment:
      PROXY_ENABLE_BASIC_AUTH: "false"
      IDM_CREATE_DEMO_USERS: "false"
```

Cinco variantes: `compose`, `env`, `nginx`, `caddy`, `traefik`. Cada una
expresa un tipo de corrección, porque los dos tipos están en archivos distintos
y normalmente en equipos distintos: las asignaciones de entorno van en la
instancia de OpenCloud, y las cabeceras de respuesta en lo que termine TLS
delante de ella. Convertir una cabecera en un bloque de entorno de Compose
produciría una línea que no hace nada, así que una variante notifica lo que no
puede expresar en `Fragment.elsewhere`, y `flavours_for` indica las variantes
que sí pueden.

Todos los nombres y valores de configuración proceden del catálogo. Los ajustes
que dependen del despliegue, como un origen CORS o la ruta de un archivo CSP,
aparecen en `Fragment.undecided`. Requieren una decisión del operador antes de
poder generar un fragmento utilizable.

## Lo que cubrió el análisis {#what-the-scan-covered}

Una comprobación superada y una que nunca se ejecutó dejan la misma huella en
este documento: ninguna. En `coverage` queda escrita la diferencia. Véase
[ADR 0064](../../adr/0064-a-scan-records-what-it-did-not-measure.md).

```json
{
  "coverage": {
    "schema": 1,
    "counts": {"passed": 49, "failed": 10, "not_checked": 12, "inconclusive": 0, "total": 71},
    "checks": [
      {"id": "Content-Security-Policy", "group": "header", "state": "passed"},
      {"id": "directoryListing", "group": "extraCheck", "state": "failed"},
      {"id": "tlsInspection", "group": "tls", "state": "not_checked",
       "reason": "not_applicable", "detail": "The instance answered over plain HTTP."}
    ]
  }
}
```

Cada comprobación que el análisis tuvo en cuenta aparece exactamente una vez,
en uno de cuatro estados:

| Estado | Significado |
|:--|:--|
| `passed` | La comprobación se ejecutó y la instancia la satisfizo |
| `failed` | La comprobación se ejecutó y la instancia no la satisfizo |
| `not_checked` | El escáner no ejecutó la comprobación |
| `inconclusive` | El escáner la ejecutó y no pudo decidir |

`passed` y `failed` no llevan motivo: una medición que se hizo no necesita
excusa. Las otras dos llevan siempre uno, de un conjunto cerrado:

| Motivo | Significado |
|:--|:--|
| `not_applicable` | La comprobación no puede aplicarse a este despliegue: no hay certificado en una instancia por HTTP simple, ni una segunda dirección que comparar |
| `probe_disabled` | Un ajuste desactivó la comprobación en este análisis |
| `prerequisite_missing` | La instancia no publicó lo que la comprobación lee |
| `timeout` | Nada respondió a tiempo |
| `unreadable` | Algo respondió y no se pudo entender |
| `no_route` | No hay ruta hasta esa familia de direcciones desde donde se ejecutó el análisis |

Hay dos propiedades en las que conviene apoyarse:

- **El total es lo que tuvo en cuenta este análisis**, no una constante. Las
  comprobaciones son dinámicas - qué rutas se sondean, qué puertos de
  depuración se marcan y qué direcciones se comparan dependen de la instancia
  y de los ajustes -, así que no hay un denominador fijo.
- **La cobertura nunca cambia una nota.** Nada de este bloque llega a la
  calificación, las gravedades, la línea de alerta, el código de salida ni la
  carga del webhook. Un fallo eximido sigue siendo `failed` aquí; la
  aceptación está en `extraChecks[].ignored`, porque una exención es una
  decisión sobre las alertas y no sobre las pruebas.

Un documento escrito antes de que existiera este bloque no tiene
la clave `coverage`, que es un informe que no dice lo que cubrió y no un
análisis sin lagunas. Léalo con `coverage.coverage_of(result)`, que devuelve
`None` tanto para un bloque ausente como para uno mal formado.

### El resumen en una línea {#the-one-line-summary}

`coverage.summary(result)` reduce el bloque a las cuatro cifras que necesita
quien lo lee, y `coverage.summary_line(result)` las escribe como una frase en
inglés:

```
84 checks evaluated, 6 skipped, 2 indeterminate, 1 network-limited
```

Cada comprobación está en exactamente una de las cuatro. `evaluated` es una
conclusión, correcta o no; `skipped` es una comprobación que el escáner decidió
no ejecutar; `indeterminate` es una que se ejecutó y no pudo decidir;
`networkLimited` se separa de las dos anteriores porque un tiempo de espera
agotado o una ruta que falta - DNSSEC, un proveedor de identidad externo, un
extremo opcional - es la laguna que otro punto de observación podría cerrar.
La frase omite los ceros, pero siempre nombra cuántas comprobaciones se
evaluaron. Ambas funciones devuelven `None` y `""` para un documento sin bloque
de cobertura, de modo que "no se pasó nada por alto" y "este informe no lo
dice" nunca se leen igual.

El complemento imprime la frase como una línea de detalle `Coverage:`, la
carga útil del webhook lleva las mismas cifras en `coverage` y la aplicación
web las muestra en *Lo que este análisis no midió*.

## En qué condiciones se ejecutó un análisis {#the-conditions-a-scan-ran-under}

Dos análisis de la misma instancia pueden diferir sin que la instancia haya
cambiado: se añadió un CVE a la base de datos de avisos, terminó un periodo de
soporte, se actualizó el escáner o caducó una exención. `provenance` registra lo
que se sabía en ese momento, para que una comparación pueda distinguir eso de
un empeoramiento real. Véase
[ADR 0066](../../adr/0066-a-result-records-the-conditions-it-was-produced-under.md).

```json
{
  "provenance": {
    "schema": 1,
    "scannerVersion": "1.25.0",
    "scannedAt": "2026-09-17T19:56:35.852320+00:00",
    "releaseTrack": "auto",
    "advisoryData": {"digest": "7ffa242f...", "count": 1},
    "scheduleData": {"digest": "6e9468bf...", "updated": "2026-09-15"},
    "waivers": {"active": [], "expired": []},
    "coverage": {"measured": 59, "total": 71}
  }
}
```


`digest` es un SHA-256 sobre los campos identificativos de los datos de
referencia en forma canónica, de modo que los mismos avisos producen el mismo
valor sin importar cómo se serializaron, combinaron u ordenaron. Es un resumen
y no una copia - incrustar la base de datos pondría megabytes de avisos ajenos
en cada informe - y tampoco una ruta de fichero, que revelaría dónde guarda sus
ficheros la máquina. `scheduleData.updated` es cuándo se *generó* el calendario,
que no es cuándo se leyó; `scannedAt` es el análisis.

`waivers` registra patrones y estados, nunca el texto del motivo: un motivo es
prosa escrita para una persona, y una comparación que lo contrastara informaría
de una errata corregida como si fuera un cambio de política.

### Comparar dos resultados {#comparing-two-results}

`check-opencloud-scanner diff` imprime los cambios que contribuyeron bajo el
resumen existente, y `--format json` los entrega como `explanation`:

| Categoría | Qué cambió |
|:--|:--|
| `instance` | La versión, o una comprobación que empezó o dejó de fallar |
| `referenceData` | Los avisos, el calendario, el canal, o una ventana de soporte que simplemente venció |
| `scanner` | La versión del escáner, o cuántas comprobaciones llegaron a una conclusión |
| `policy` | Una exención caducó, se añadió o se retiró |
| `unknown` | Algo se movió y nada de lo registrado lo explica |

La redacción es prudente. Un resumen distinto establece que los
datos de referencia difirieron; no establece que eso hiciera moverse ninguna
nota concreta, y la frase lo refleja. Varios cambios pueden contribuir sin que
se elija uno como la causa.

`limitations` enumera lo que la comparación no pudo establecer, casi siempre que
uno de los dos informes es anterior a estos bloques y por tanto no puede decir
contra qué se juzgó ni cuánto se ejecutó. Eso se informa, no se supone.

## ¿Ha cambiado la instalación? {#has-the-deployment-changed}

Una nota dice si una instancia está en buena forma. No dice si sigue siendo la
misma instancia que la semana pasada. Una política reescrita sin ganar
`unsafe-inline`, un proxy sustituido por otro producto que pone las mismas
cabeceras, enlaces públicos que dejan de pedir contraseña y vuelven a pedirla,
un certificado trasladado a otro emisor: nada de eso tiene que mover la nota, y
quien solo mira la nota no ve nada de ello.

`configuration` contiene **huellas** de la configuración medida, agrupadas
por área, sin los valores de configuración originales. Véase
[ADR 0073](../../adr/0073-a-result-fingerprints-the-configuration-it-measured.md).

```json
{
  "configuration": {
    "schema": 1,
    "digest": "9e3c4428...",
    "groups": {
      "tls": {"digest": "89a97538...", "scope": "1d0f4b77...", "facts": 12},
      "headers": {"digest": "cb25144c...", "scope": "b8e1a930...", "facts": 13},
      "sharing": {"digest": "7b8a1ced...", "scope": "44c0ae51...", "facts": 3},
      "authentication": {"digest": "588d045f...", "scope": "0a7be2cc...", "facts": 6},
      "proxy": {"digest": "b7db6daf...", "scope": "ff31c084...", "facts": 5}
    }
  }
}
```

Dos análisis con el mismo resumen de grupo vieron la misma configuración; dos
que difieren, no. No se afirma nada más, y estas reglas son las que lo
hacen útil:

- **Solo resúmenes, nunca la configuración.** Una política de seguridad de
  contenido nombra los orígenes en los que confía una instalación, un documento
  de descubrimiento puede nombrar un inquilino, un banner de servidor nombra una
  compilación interna. Cada dato se resume dentro de su grupo y se descarta: se
  registra *que* la compartición cambió, nunca *cuál es la nueva configuración*.
- **Los grupos son las preguntas que hace quien opera.** "¿Cambió TLS?" sirve;
  "¿cambió el dato 37?" no.
- **Solo lo que decide la instalación.** El grupo de transporte resume el
  emisor, la clave, el algoritmo de firma y los protocolos negociados; no el
  número de serie, las fechas ni la huella del certificado, porque una renovación
  es rutina. El grupo del proxy resume el producto, no el banner con su número
  de compilación.
- **Lo que deciden los ajustes del análisis nunca es un dato.** `scope` es un
  resumen de *qué* datos pudo mirar un grupo, sin sus valores. Dos grupos solo
  se comparan cuando su alcance coincide, así que una ejecución que dejó de
  inspeccionar TLS informa "no comparable" en lugar de un cambio. Un grupo sin
  ningún dato es `none`.
- **Nunca cambia una nota.** Nada de esto llega a la calificación, las
  severidades, la línea de alerta ni el código de salida.

Léelo con `fingerprint.fingerprint_of(result)`, que devuelve `None` tanto para
un bloque ausente como para uno mal formado: un informe que no puede decirlo no
es una instalación que no cambió. `fingerprint.digests(result)` lo reduce a una
cadena opaca `scope:digest` por grupo y `fingerprint.drift(before, after)`
nombra los grupos que difieren.

El complemento imprime `Configuration fingerprint: 9e3c4428` en cada análisis,
y `--baseline` lo convierte en `No new findings, but the configuration changed
(headers)`.

## Puertos de depuración {#debug-ports}

Cada servicio de OpenCloud ejecuta un servicio de depuración que sirve
`/healthz`, `/readyz`, `/metrics`, `/config` y `/debug/pprof`. `/metrics`
expone la versión exacta mediante `opencloud_proxy_build_info`, `/config`
vuelca la configuración efectiva del servicio y `/debug/pprof` permite a
cualquiera lanzar un perfilado.

Escuchan en loopback salvo que `<SERVICE>_DEBUG_ADDR` indique otra cosa, así
que uno que responda desde un host de monitorización es un hallazgo real,
casi siempre un contenedor que publicó un rango de puertos completo. Por
defecto se sondean cinco:

| Puerto | Servicio |
|:-----|:--------|
| 9205 | proxy |
| 9141 | frontend |
| 9124 | graph |
| 9134 | idp |
| 9239 | idm |

Cada sondeo es una conexión TCP con un tiempo de espera de tres segundos, así
que un host protegido por cortafuegos cuesta hasta quince segundos por
análisis. Están disponibles `check_debug_ports: false`,
`debug_port_timeout`, una lista `debug_ports` más corta y `concurrency`.

Los mismos manejadores se sondean también en la dirección principal, donde
nunca deben aparecer (hallazgos `debugEndpoint:`).

## Todas las direcciones resueltas {#every-resolved-address}

`check_all_addresses=True` (`--all-addresses` en `scan`) repite la parte del
análisis que depende del nodo (`status.php`, las cabeceras calificadas de la
página raíz, las capacidades, la solicitud de autenticación, el proveedor de
identidad y las cuentas de demostración) contra cada dirección a la que se
resolvió el nombre, una tras otra, y emite `addressParity`. Cada solicitud
mantiene el nombre de host en `Host` y en SNI y queda fijada a una dirección
mediante su propia sesión. Las direcciones son la respuesta del resolvedor, o
`pinned_addresses` si se indican, así que un análisis fijado nunca va más allá
de lo que ha validado quien llama; IPv6 se omite cuando `ipv6_enabled` es
falso. Lo que sirvió cada dirección se enumera en `addressObservations`:

```json
{"addressObservations": [
  {"address": "198.51.100.1", "reachable": true, "version": "7.2.3",
   "headers": {"Strict-Transport-Security": true}, "hardenings": {},
   "demoUsersDisabled": true, "error": ""}
]}
```

La primera dirección es la referencia; la gravedad sigue a la peor diferencia
(las cuentas de demostración como `demoUsersDisabled`, otra versión `high`,
cualquier otra cosa `medium`); los nombres excluidos no se comparan. Con una
sola dirección, o con el ajuste desactivado (el valor predeterminado), no hay
hallazgo y la lista está vacía. Consulte
[ADR 0042](../../adr/0042-every-resolved-address-is-compared-only-when-the-operator-asks.md).

## Concurrencia {#concurrency}

Un análisis consiste sobre todo en esperar: unas veinte solicitudes HTTP más
las conexiones a los puertos de depuración, una tras otra. `concurrency`
ejecuta en paralelo las que son independientes:

```python
result = scan("opencloud.example.com", settings=ScannerSettings(concurrency=8))
```

El valor predeterminado es `1`, que no usa ningún hilo, y los valores
superiores a `32` se limitan. Cada trabajador tiene su propia
`requests.Session`, ya que una sesión no se puede compartir con seguridad entre
hilos.

El ajuste solo afecta a los tiempos. Los resultados se recogen en el orden en
que se lanzaron los sondeos, así que un análisis en paralelo notifica
exactamente los mismos hallazgos, en exactamente el mismo orden, que uno
secuencial.

## TLS {#tls}

El proxy de OpenCloud termina él mismo TLS en el puerto 9200, y
`opencloud init` genera un certificado autofirmado. El escáner se degrada en
tres pasos en lugar de fallar en el primero:

1. HTTPS con verificación de certificado.
2. HTTPS sin verificación: el análisis continúa y `tlsTrusted` se notifica como
   fallido.
3. HTTP sin cifrar: se notifica como `httpsAvailable` (critical).

`verify_tls: false` (o `--insecure`) empieza en el paso 2. La cadena no fiable
sigue apareciendo en los hallazgos; simplemente deja de restar en la nota, así
que una instancia autofirmada se puede monitorizar sin una nota
permanentemente rebajada, mientras que un certificado realmente defectuoso en
otro lugar sigue destacando.

Para una CA interna, mantenga la verificación activada y defina
`scanner.tls_ca_file` (o `COS_SCANNER_TLS_CA_FILE`) con su paquete PEM;
`check-opencloud-scanner scan` acepta también `--ca-file`. Así se confía en esa
CA sin desactivar la verificación.

### Qué se mide {#what-is-measured}

`tls.py` hace la inspección y entrega a `scanner.py` una lista de
comprobaciones; no sabe nada de notas. Además del handshake y la confianza,
notifica:

| Hallazgo | Qué pregunta |
|:--------|:-------------|
| `tlsProtocol` | ¿La versión negociada es al menos TLS 1.2? |
| `tlsDeprecatedProtocol` | ¿El servidor *sigue aceptando* TLS 1.0 o 1.1, aunque con nosotros negoció algo más reciente? |
| `tlsHostname` | ¿El certificado cubre el nombre solicitado, incluidos comodines y direcciones IP? |
| `tlsChain` | ¿El servidor envía sus intermedios, o solo un certificado final que se valida por suerte? |
| `tlsCertificate` | ¿Caduca dentro de `tls_min_days`, o ya ha caducado? |
| `tlsCertificateLifetime` | ¿Es válido durante más tiempo que el umbral de 398 días del escáner? |
| `tlsCipherSuite` | ¿El conjunto de cifrado negociado por este análisis es moderno y con secreto perfecto hacia adelante? |
| `tlsCertificatePolicy` | ¿El certificado usa una clave de tamaño adecuado y una firma moderna? |
| `tlsAddressParity` | ¿Los puntos de acceso IPv4 e IPv6 publicados presentan la misma identidad TLS utilizable? |
| `tlsCaaRecord` | ¿El nombre tiene un registro DNS CAA que indique al menos un emisor autorizado? |
| `tlsDnssec` | ¿Está firmada la zona, de modo que se pueda confiar en la dirección en la que se basan todas las comprobaciones anteriores? Ausente, no fallida, cuando el resolvedor usado no admite DNSSEC |
| `cookieSecure`, `cookieHttpOnly`, `cookieSameSite` | ¿Las cookies observadas realmente en la respuesta pública llevan estos atributos? |
| `tlsOcspStapling` | ¿Hay una respuesta de revocación adjunta al handshake? |

Las mediciones en las que se basan están en un bloque `tls` del documento de
resultado: el protocolo y el cifrado, el sujeto del certificado, el emisor, el
periodo de validez, los días restantes y los nombres, la longitud de la cadena
y lo que encontraron los sondeos de protocolos obsoletos y de stapling.

```json
{
  "host": "opencloud.example.com",
  "port": 443,
  "reachable": true,
  "protocol": "TLSv1.3",
  "cipher": "TLS_AES_256_GCM_SHA384",
  "cipherBits": 256,
  "trusted": true,
  "hostnameMatch": true,
  "chainComplete": true,
  "chainLength": 2,
  "deprecatedProtocolsProbed": ["TLSv1", "TLSv1.1"],
  "deprecatedProtocolsAccepted": [],
  "ocspStapled": false,
  "ocspNote": "the certificate names no OCSP responder",
  "certificate": {
    "subject": "opencloud.example.com",
    "issuer": "Example CA R3",
    "serialNumber": "03A1...",
    "notBefore": "2026-06-01T00:00:00+00:00",
    "notAfter": "2026-08-30T00:00:00+00:00",
    "daysRemaining": 9,
    "lifetimeDays": 90,
    "altNames": ["opencloud.example.com"],
    "ocspResponders": [],
    "selfSigned": false,
    "keyType": "RSA",
    "keyBits": 2048,
    "signatureAlgorithm": "sha256WithRSAEncryption"
  }
}
```

**`null` significa "no determinado", nunca "correcto".** Una comprobación que
no se pudo realizar (`get_unverified_chain()` necesita Python 3.13, el sondeo
de protocolos obsoletos necesita una compilación que todavía admita alguno, el
stapling necesita el comando `openssl` y un certificado que indique un
servidor OCSP) se omite por completo de los hallazgos en lugar de registrarse
como superada. Consulte
[ADR 0013](../../adr/0013-transport-security-is-measured-not-assumed.md).

El certificado se decodifica a partir de lo que presentó el servidor, se haya
verificado o no, así que a una instancia con el certificado autofirmado que
genera `opencloud init` se le siguen comprobando la caducidad, los nombres y la
duración. Hay dos sondeos opcionales en la llamada: `probe_deprecated` abre un
handshake adicional por cada protocolo antiguo, y `check_stapling` ejecuta un
`openssl s_client` con una lista de argumentos fija y sin shell.

## Lo que este paquete no hace {#what-this-package-does-not-do}

- **No hay elección de backend.** No hay ningún escáner remoto que
  seleccionar, así que no existen `--scan-backend`, `--scan-url` ni
  `--scan-token`, y no hay nada cuyo reanálisis haya que forzar, porque nunca se
  guarda nada en caché.
- **No hay comprobación del registro de auditoría.** El servicio de auditoría
  no tiene superficie HTTP ni capacidad propia, así que no hay nada que
  observar. Consulte
  [Lo que el escáner no puede medir](#what-the-scanner-cannot-measure).
- **No hay matriz de refuerzos.** Los refuerzos se observan, no se deducen de
  la versión (véase arriba).
- **No hay credenciales en la instancia.** Todas las comprobaciones funcionan
  con lo que puede ver un cliente no autenticado. La comprobación de
  actualizaciones lee un canal público.
- **No hay suposiciones de la era PHP.** OpenCloud es un único binario Go con
  recursos incrustados: no hay `config/config.php`, ni `/data/`, ni
  `/3rdparty/`. Los hallazgos se centran en lo que OpenCloud expone realmente:
  la autenticación de la API Graph y de OCS, los puertos de depuración,
  `opencloud.yaml`, `proxy/server.key` y la boltdb de idm.

## Usarlo directamente {#using-it-directly}

```python
from opencloud_local_scan import ScannerSettings, scan

result = scan("opencloud.example.com", settings=ScannerSettings(timeout=10))
print(result["rating"], result["version"], result["extraChecks"])
```

`scan()` lanza `ScanError` cuando no puede identificar OpenCloud: el punto de
acceso no es accesible, su respuesta no es un JSON adecuado, faltan campos de
versión o el producto es otro. Los casos en los que respondió un servicio
lanzan `NotOpenCloud`. Por defecto, el escáner reintenta una respuesta HTTPS no
adecuada sin verificación de certificado y después por HTTP.
`ScannerSettings(stop_when_not_opencloud=True)` se detiene tras la primera
respuesta de ese tipo; la aplicación web pública lo activa.

El documento incluye además `addresses`, las direcciones IPv4 e IPv6 a las que
se resolvió el nombre de host durante el análisis:

```json
{"addresses": {"ipv4": ["198.51.100.7"], "ipv6": ["2001:db8::7"]}}
```

Es contexto y no un hallazgo, y nunca cambia la nota. Las direcciones fijadas
mediante `ScannerSettings.pinned_addresses` se notifican tal cual: la
aplicación web valida un nombre antes de permitir que empiece un análisis y
marca exactamente esas direcciones, así que volver a resolverlo aquí podría
indicar una dirección a la que el análisis nunca se conectó.

Cualquier ajuste de `ScannerSettings` y `ReleaseSettings` puede proceder
también de un archivo de configuración (YAML, o JSON cuando el nombre termina
en `.json`), de una variable de entorno o de un proveedor de secretos;
consulte
[`config/check-opencloud-security.example.yml`](../../config/check-opencloud-security.example.yml)
y la sección
[Archivo de configuración y secretos](../../README.md#configuration-file-and-secrets)
del README principal. `check-opencloud-scanner configure` escribe un archivo
así de forma interactiva.

Para un análisis que no debe usar la red más allá de la propia instancia:

```python
from opencloud_local_scan import ReleaseSettings, ScannerSettings, scan

result = scan(
    "opencloud.example.com",
    settings=ScannerSettings(verify_tls=False, vulnerability_feed=None),
    release_settings=ReleaseSettings(mode="bundled"),
)
```

## Verificar una corrección sin un análisis completo {#verifying-a-fix-without-a-full-scan}

`opencloud_local_scan.verification.verify` vuelve a medir solo los hallazgos
indicados, ejecutando únicamente las sondas del escáner que los producen. Es
la base de `--verify-remediation` (véase [ADR 0072](../../adr/0072-remediation-verification-re-measures-named-findings-without-a-full-scan.md)).

```python
from opencloud_local_scan.verification import verify

document = verify(
    "opencloud.example.com",
    ["Strict-Transport-Security", "exposed"],
)
for entry in document["results"]:
    print(entry["id"], entry["passed"], entry["reason"])
```

El documento contiene `domain`, `url`, `verifiedAt`, `probeGroups` (los
grupos que se ejecutaron) y `results`, una entrada por identificador: `id`,
`verifiable` (false si solo un análisis completo puede decidirlo, como `eol`
o `vulnerability:...`), `passed` (`None` si no se midió nada), `group`,
`checks` con la forma de las entradas de `extraChecks` y `reason`. Como
`scan()`, mide y nunca juzga: sin calificación ni exenciones.
`probe_group(id)` indica de antemano qué grupo mide un identificador.

## Comparar un análisis con el anterior {#comparing-a-scan-with-the-last-one}

`opencloud_local_scan.baseline` reduce un documento de resultado a los
hallazgos que merece la pena comparar (vulnerabilidades, medidas de refuerzo
ausentes que se pueden corregir y no están excluidas, comprobaciones
adicionales fallidas y una actualización pendiente) y los recuerda por host. Es
la base de `--baseline` / `--warn-on-new`.

```python
from opencloud_local_scan import load_baseline, scan, snapshot_of

result = scan("opencloud.example.com")
store = load_baseline("/var/lib/check_opencloud/baseline.json")
comparison = store.compare("opencloud.example.com", snapshot_of(result))

if comparison.regressed:
    print(comparison.summary())

store.record("opencloud.example.com", snapshot_of(result))
store.save()
```

`Comparison.regressed` es verdadero en la primera ejecución (no hay nada con
qué comparar, así que callar ocultaría un problema real), cuando un hallazgo es
nuevo, cuando la nota ha bajado y siempre que la versión haya superado su fin
de vida, esto último sin importar cuánto tiempo lleve siendo cierto, porque
una versión que no recibe correcciones de seguridad empeora cada día que sigue
en producción.

La marca de tiempo del análisis, la duración y la cadena de versión no forman
parte de una instantánea a propósito: cambian por sí solas y harían que cada
ejecución pareciera nueva. La escritura es atómica y solo para el propietario,
y un archivo dañado o de un formato futuro se lee como "todavía no hay línea
base" en lugar de lanzar una excepción: volver a la comprobación normal nunca
es peor que negarse a ejecutarse.
