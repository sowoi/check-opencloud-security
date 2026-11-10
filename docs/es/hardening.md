# Medidas de refuerzo de OpenCloud, una por una

Esta guía explica los identificadores de refuerzo que aparecen en las alertas:
qué significa cada hallazgo, qué ajuste puede resolverlo y cuándo es adecuada
una exclusión. También señala los valores que OpenCloud tiene fijados en el
código y que los operadores no pueden cambiar.

`--debug` imprime la misma explicación junto a cada hallazgo. El
[README principal](../../README.md#hardening-checks) explica cómo llegan las
medidas a la salida y a las métricas.

<!-- TOC -->
* [Medidas de refuerzo, una por una](#hardening-measures-one-by-one)
  * [Qué significa cada medida](#what-each-measure-means)
  * [Medidas que no son ajustes](#measures-that-are-not-settings)
  * [Aceptar un hallazgo que no se va a corregir](#accepting-a-finding-you-are-not-going-to-fix)
<!-- TOC -->


## Qué significa cada medida {#what-each-measure-means}

| Refuerzo | Qué significa un fallo | Ajuste que hay que cambiar |
|:-------------------------------|:------------------------------------------|:------------------------------------------|
| `basicAuthDisabled`            | La instancia ofrece autenticación HTTP Basic, así que las credenciales pueden reutilizarse en cada solicitud y se elude el inicio de sesión único (con cualquier segundo factor). A menudo es deliberado: los clientes CalDAV, CardDAV y WebDAV no admiten OpenID Connect, por eso se califica como `medium`, y como `low` cuando un proveedor de identidad externo gestiona el inicio de sesión interactivo. | [`PROXY_ENABLE_BASIC_AUTH=false`][proxy-env] si nada lo necesita; de lo contrario, manténgalo y dé a esos clientes tokens de aplicación en lugar de contraseñas de cuenta. |
| `cspWithoutUnsafeInline`       | La `Content-Security-Policy` contiene `'unsafe-inline'`, así que el marcado inyectado puede ejecutarse. **Es el valor predeterminado de OpenCloud**; consulte la nota más abajo. | [`PROXY_CSP_CONFIG_FILE_LOCATION`][proxy-env] apuntando a su propio `csp.yaml` (o `PROXY_CSP_CONFIG_FILE_OVERRIDE_LOCATION` para sustituir por completo el predeterminado). |
| `publicLinkPasswordEnforced`   | Se pueden crear enlaces públicos sin contraseña, así que la URL basta para acceder. OpenCloud exige contraseña en los enlaces de solo lectura, pero no en los que permiten escritura. | [`OC_SHARING_PUBLIC_SHARE_MUST_HAVE_PASSWORD=true`][sharing-env] y `OC_SHARING_PUBLIC_WRITEABLE_SHARE_MUST_HAVE_PASSWORD=true`. |
| `passwordPolicyEnforced`       | Las contraseñas de enlaces públicos pueden tener menos de 8 caracteres. (Esta política afecta a las contraseñas de enlaces, no a las de cuentas, que corresponden a su proveedor de identidad). | [`OC_PASSWORD_POLICY_MIN_CHARACTERS`][link-password] (predeterminado `8`), junto con sus complementos `MIN_LOWERCASE`/`MIN_UPPERCASE`/`MIN_DIGITS`/`MIN_SPECIAL_CHARACTERS`. |
| `passwordPolicyComplexity`     | La política de contraseñas de enlaces ya no exige una minúscula, una mayúscula, una cifra y un carácter especial. Cada uno vale `1` por defecto, así que un fallo significa que alguien ha reducido alguno; una política desactivada se notifica como desconocida, no como fallida. | [`OC_PASSWORD_POLICY_MIN_LOWERCASE_CHARACTERS`][link-password] y sus complementos `MIN_UPPERCASE`/`MIN_DIGITS`/`MIN_SPECIAL_CHARACTERS`, de nuevo a `1` o más. |
| `hstsLongMaxAge`               | `Strict-Transport-Security` lleva un `max-age` inferior a un año. | Ninguno en OpenCloud: su proxy envía diez años, así que un valor corto procede de un proxy inverso situado delante. |
| `hstsPreload`                  | La misma cabecera no tiene la directiva `preload`, así que la primera solicitud al host queda sin protección. | Ninguno en OpenCloud: de nuevo, un proxy inverso que reescribe la cabecera. Añada `preload` solo cuando todos los subdominios usen exclusivamente HTTPS. |
| `hstsPreloadEligible`          | La cabecera no se aceptaría para la precarga en navegadores: la lista exige a la vez un `max-age` de al menos un año, `includeSubDomains` *y* `preload`, y el proxy de OpenCloud omite `includeSubDomains`. `hstsPreload` indica que la directiva está presente; esta comprobación indica que la solicitud se rechazaría. Se notifica en `setup.advisoryChecks` y **nunca genera alertas**, porque la carencia está en lo que incluye OpenCloud. No se mide si el dominio figura en la lista; consulte [ADR 0037](../../adr/0037-preload-eligibility-is-measured-list-membership-is-not.md). | Añada `includeSubDomains` en el proxy inverso y después envíe el dominio en [hstspreload.org](https://hstspreload.org/); la aceptación requiere ambas cosas. Confirme antes que todos los subdominios usan exclusivamente HTTPS. |
| `publicLinkExpirationEnforced` | No dice nada de su instancia: OpenCloud fija esta capacidad a `false` en el código. **Nunca genera alertas**; consulte más abajo. | No existe ninguno. |
| `userEnumerationRestricted`    | La búsqueda de cuentas no está limitada a grupos compartidos. OpenCloud fija en el código el estado restringido, así que se supera en todas partes. | No existe ninguno. |
| `oidcPkceSupported`            | El documento de descubrimiento del proveedor de identidad publica `code_challenge_methods_supported` sin `S256`, así que el flujo de código de autorización se ejecuta sin PKCE. Solo se notifica cuando el proveedor publica el campo: el proveedor integrado de OpenCloud lo omite, y una respuesta ausente no es una respuesta fallida. | Exija PKCE con `S256` en el proveedor: *Proof Key for Code Exchange* en Keycloak, cliente público con PKCE obligatorio en Authentik, `require_pkce` en Authelia. |
| `oidcImplicitFlowDisabled`     | `response_types_supported` sigue ofreciendo un tipo que devuelve un token desde el punto de acceso de autorización (`token` o `id_token`), es decir, el flujo implícito. **Solo para proveedores externos**: el proveedor integrado de OpenCloud los ofrece y no se puede reconfigurar. | Limite el cliente al flujo de código de autorización; en Keycloak, Standard flow activado e Implicit flow desactivado. |
| `oidcSigningAlgorithmStrong`   | `id_token_signing_alg_values_supported` ofrece `none` (un token de ID sin firmar que cualquiera puede escribir) o un algoritmo `HS` (firmado con el secreto del cliente, que un cliente público no puede guardar). El proveedor integrado de OpenCloud firma con `PS256` y supera la comprobación. | Ofrezca solo algoritmos asimétricos (`RS256`, `PS256`, `ES256` o `EdDSA`) y elimine `none` y la familia `HS`. |
| `oidcEndpointsUseHttps`        | Un punto de acceso del documento de descubrimiento es una dirección `http://`. Solo se comprueba cuando la propia instancia respondió por HTTPS: una instancia analizada por HTTP sin cifrar publica `http://` porque así se le preguntó, y eso ya lo notifica `httpsEnforced`. | Publique el proveedor por HTTPS y defina su emisor con la dirección `https://`; un emisor `http://` suele ser un proveedor detrás de un proxy que termina TLS y al que nunca se le indicó su URL pública. |

[proxy-env]: https://docs.opencloud.eu/docs/dev/server/services/proxy/environment-variables
[sharing-env]: https://docs.opencloud.eu/docs/dev/server/services/sharing/environment-variables
[frontend-env]: https://docs.opencloud.eu/docs/dev/server/services/frontend/environment-variables
[link-password]: https://docs.opencloud.eu/docs/admin/configuration/link-password-policy

## Medidas que no son ajustes {#measures-that-are-not-settings}

Nadie puede influir en dos de las filas anteriores:

- **`publicLinkExpirationEnforced`** se notifica como `false` en *todas* las
  instancias de OpenCloud. La capacidad es una constante fija en el servicio
  frontend, no un valor de configuración, así que no hay ninguna variable que
  definir ni ninguna versión que la supere.
- **`userEnumerationRestricted`** es el mismo caso con el signo contrario:
  está fijado en el estado restringido, así que siempre se supera.

Se siguen registrando en el documento de resultado, porque la observación es
real, pero **se excluyen de la línea "Missing hardening", de la métrica
`hardenings_missing` y del webhook**. Nadie puede resolver esas advertencias,
así que alertar sobre ellas solo distraería de los hallazgos que sí se pueden
corregir. `--debug` los sigue mostrando, con su explicación.

`cspWithoutUnsafeInline` es una versión más leve del mismo problema: la **CSP
predeterminada de OpenCloud contiene `'unsafe-inline'`**, así que falla en una
instancia estándar. Esta sí se puede cambiar, por lo que se notifica en lugar
de excusarse; pero tenga en cuenta que la interfaz web depende actualmente de
scripts y estilos en línea, así que una política estricta probablemente romperá
la interfaz y cualquier servicio de ofimática o de identidad conectado. Pruébela
antes de implantarla. Consulte [`docs/csp.md`](../csp.md) para la explicación
completa de ambas comprobaciones de CSP.

Las filas derivadas de capacidades solo aparecen cuando la instancia notifica
realmente la capacidad correspondiente, así que una versión antigua no acumula
hallazgos fantasma.

## Aceptar un hallazgo que no se va a corregir {#accepting-a-finding-you-are-not-going-to-fix}

Algunos hallazgos son reales pero no se pueden resolver en su entorno: una CSP
que no puede endurecer sin romper la interfaz web, una cabecera HSTS que
controla su proxy inverso o una autenticación básica que realmente necesita
para una herramienta de migración. Si se dejan así, mantienen baja la nota y
la comprobación siempre en amarillo, y se deja de mirar una comprobación que
nunca cambia.

`--ignore-hardening` acepta un hallazgo por su nombre. La nota se vuelve a
calcular sin él, así que aceptar un hallazgo cambia realmente la calificación:

```bash
check-opencloud-security --host opencloud.example.com --check-hardening \
    --ignore-hardening cspWithoutUnsafeInline \
    --ignore-hardening basicAuthDisabled
```

La opción es repetible, admite también una lista separada por comas y entiende
comodines de estilo shell para los identificadores que llevan una ruta o un
puerto:

```bash
--ignore-hardening 'debugPort:*,exposed:/status.php'
```

Coincide con medidas de refuerzo, nombres de cabeceras de seguridad,
`httpsEnforced` y los identificadores de las comprobaciones adicionales: una
sola opción para todos, porque `basicAuthDisabled` es a la vez una medida de
refuerzo y una comprobación adicional, y aceptarlo en un lugar pero no en el
otro resultaría sorprendente.

Un hallazgo excluido:

- ya no reduce la nota,
- ya no aparece en `Missing hardening:` ni en `Additional checks failed`,
- ya no cuenta en las métricas `hardenings_missing` y `extra_checks_failed`,
- se omite en la carga útil del webhook,
- pero **permanece en el documento de resultado JSON**, marcado con
  `"ignored": true`, y aparece en la salida del complemento como
  `Ignored by configuration (n): ...`.

Una exclusión suprime la alerta y conserva la
evidencia: el análisis sigue registrando lo que vio, `--debug` lo sigue
explicando y cualquiera que lea la salida puede ver qué se omite.

Hay dos cosas que una exclusión no hace:

- **No puede excluir algo que se supera.** Una exclusión solo se aplica a un
  hallazgo que ha fallado realmente, así que un retroceso posterior de la
  medida no pasa desapercibido.
- **No puede excluir una versión sin soporte.** Ejecutar una versión que no
  recibe correcciones de seguridad prevalece sobre cualquier otra señal,
  incluido `--ignore-hardening '*'`.

Las exclusiones encajan bien en un archivo de configuración, donde pueden
llevar un comentario que explique por qué existe cada una:

```yaml
scanner:
  release_track: production
  ignore_hardenings:
    - cspWithoutUnsafeInline   # default csp.yaml, tightening it breaks the web UI
    - hstsPreload              # the reverse proxy sets its own HSTS header
```
