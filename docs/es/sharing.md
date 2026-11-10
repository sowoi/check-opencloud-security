# Comprobaciones de enlaces públicos compartidos

Con un enlace público compartido, tener la URL puede bastar para acceder a su
contenido. El escáner lee las capacidades de OpenCloud para comprobar si los
enlaces exigen contraseña y si se notifica una caducidad automática.

<!-- TOC -->
* [Enlaces públicos compartidos: qué comprueba este escáner y por qué](#public-link-sharing-what-this-scanner-checks-and-why)
  * [1. ¿Se puede crear un enlace público sin contraseña?: `publicLinkPasswordEnforced`](#1-can-a-public-link-be-created-without-a-password-publiclinkpasswordenforced)
  * [2. ¿Caducan automáticamente los enlaces públicos?: `publicLinkExpirationEnforced`](#2-do-public-links-expire-automatically-publiclinkexpirationenforced)
  * [Qué más contiene ese documento y por qué no se comprueba nada de ello](#what-else-is-in-that-document-and-why-none-of-it-is-checked)
  * [Gravedad y efecto en la nota](#severity-and-rating-impact)
<!-- TOC -->


## 1. ¿Se puede crear un enlace público sin contraseña?: `publicLinkPasswordEnforced` {#1-can-a-public-link-be-created-without-a-password-publiclinkpasswordenforced}

El documento de capacidades indica, para cada tipo de enlace, si se exige
contraseña: los enlaces de solo lectura, de solo subida y editables tienen cada
uno su propio indicador `enforced_for`. Esta comprobación solo se supera cuando
**todos** exigen contraseña. Si aunque sea un tipo de enlace se puede crear sin
ella, cualquiera que tenga esa URL accede a los datos que hay detrás,
indefinidamente y sin ninguna credencial.

**Suele tratarse de un fallo parcial más que de un todo o nada.** OpenCloud
exige por defecto contraseña en los enlaces de solo lectura, pero no en los que
permiten escritura, así que el motivo habitual de este fallo es que los enlaces
de solo subida o editables se dejaron con su valor predeterminado. Un enlace
con escritura y sin contraseña es la más grave de las dos carencias: permite a
un visitante anónimo añadir o sobrescribir archivos, no solo leerlos.

**Corrección:** defina `OC_SHARING_PUBLIC_SHARE_MUST_HAVE_PASSWORD=true` y
`OC_SHARING_PUBLIC_WRITEABLE_SHARE_MUST_HAVE_PASSWORD=true`. Prefiera estos
nombres globales `OC_SHARING_*` a las formas obsoletas `FRONTEND_OCS_*` que aún
aparecen en algunas guías antiguas. La contraseña que finalmente se defina en
un enlace está a su vez sujeta a `passwordPolicyEnforced`; consulte
[Autenticación: ¿es suficientemente estricta la política de contraseñas de los
enlaces?](../authentication.md#5-is-the-link-password-policy-strong-enough-passwordpolicyenforced).

## 2. ¿Caducan automáticamente los enlaces públicos?: `publicLinkExpirationEnforced` {#2-do-public-links-expire-automatically-publiclinkexpirationenforced}

Se lee directamente el campo `files_sharing.public.expire_date.enabled` del
documento de capacidades. En las versiones actuales de OpenCloud es un `false`
fijo en el servicio frontend (una constante, no un ajuste), así que todas las
instancias notifican el mismo valor sea cual sea su configuración. **Esta
comprobación nunca genera alertas** por ese motivo: se excluye de la
línea "Missing hardening", de la métrica `hardenings_missing` y de la carga
útil del webhook, porque nadie puede resolver la advertencia y solo distraería de los
hallazgos que sí se pueden corregir; consulte
[Medidas que no son ajustes](../hardening.md#measures-that-are-not-settings).
`--debug` la sigue mostrando, con su explicación.

Se mantiene en el catálogo en lugar de eliminarse para que una futura versión
de OpenCloud que permita configurar la caducidad automática se detecte en
cuanto el documento de capacidades empiece a notificar algo distinto de
`false`. Es el mismo razonamiento documentado para
`userEnumerationRestricted` en
[Autenticación](../authentication.md#4-is-account-search-restricted-to-shared-groups-userenumerationrestricted).

**Si la caducidad es realmente importante hoy en un despliegue:** no hay
ningún ajuste que cambiar. La caducidad debe fijarse para cada enlace al
crearlo, o la vida útil efectiva del enlace debe controlarse desde fuera de
OpenCloud, por ejemplo con una regla del proxy inverso o con un proceso externo
que revoque los enlaces periódicamente.

## Qué más contiene ese documento y por qué no se comprueba nada de ello {#what-else-is-in-that-document-and-why-none-of-it-is-checked}

El documento de capacidades enumera mucha más información sobre el uso
compartido de la que leen estas dos comprobaciones, y conviene dejar escrito
por qué el resto no merece un indicador; de lo contrario, alguien vuelve a
deducirlo cada año. Verificado en
`services/frontend/pkg/revaconfig/config.go` de
[opencloud-eu/opencloud](https://github.com/opencloud-eu/opencloud):

| Capacidad | Por qué no hay comprobación |
|:--|:--|
| `auto_accept_share`, `share_with_group_members_only`, `share_with_membership_groups_only`, `group_sharing`, `sharing_roles`, `api_enabled` | Constantes fijas en el mapa de capacidades. Todas las instancias notifican el mismo valor, así que una comprobación no diría nada del despliegue; es el mismo motivo por el que `publicLinkExpirationEnforced` nunca genera alertas. |
| `public.upload`, `public.send_mail`, `public.social_share`, `public.alias`, `public.multiple`, `public.supports_upload_only`, `public.can_edit` | Fijas de la misma manera. |
| `federation.incoming`, `federation.outgoing` | Configurables mediante `OC_ENABLE_OCM`, pero la propia descripción de OpenCloud dice que cambiarlo **no está soportado** y que "the backend behaviour is not changed": determina lo que se comunica a los clientes, no lo que hace el servidor. Un hallazgo sobre el que un operador no puede actuar con efecto real es peor que ninguno. |
| `public.default_permissions` | Realmente configurable (`FRONTEND_DEFAULT_LINK_PERMISSIONS`: `0` interno, `1` lector público, predeterminado `1`). *Todavía* no se comprueba, porque todas las instancias con la configuración predeterminada empezarían a fallar, y decidir si compensa es una cuestión de ruido, no de evidencia. |
| `deny_access`, `search_min_length` | Configurables, pero son respectivamente un experimento obsoleto y un ajuste de la experiencia de búsqueda; ninguno cambia quién puede acceder a los datos. |

La regla que sigue esta tabla es la de `AGENTS.md`: antes de añadir una
comprobación de refuerzo, verifique en el código fuente de OpenCloud que un
operador puede cambiarla realmente.

## Gravedad y efecto en la nota {#severity-and-rating-impact}

Ambas son indicadores de refuerzo, que solo se notifican con
`--check-hardening` (o siempre en el resultado web).
`publicLinkPasswordEnforced` se comporta como cualquier otro indicador de
refuerzo: un fallo no limita la nota por sí solo, pero eleva a `WARNING` un
resultado de Icinga que de otro modo sería `OK` y aparece en la línea "Missing
hardening". `publicLinkExpirationEnforced` queda completamente excluido de esa
línea, por el motivo anterior; consulte
[Medidas de refuerzo, una por una](../hardening.md) para la tabla completa y la
regla general.
