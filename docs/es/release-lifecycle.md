# Canales de publicación de OpenCloud, fin de vida y recomendaciones de actualización

OpenCloud mantiene en paralelo los canales Rolling, Production y LTS. Por eso,
el estado de soporte de una versión depende tanto de su canal como de su
número. Esta guía explica cómo usa el escáner las líneas de versiones y el
calendario incluido, cómo elige una actualización y cómo aplica
`--release-track`.

El [README principal](../../README.md#end-of-life-detection) recoge el estado
actual de cada canal y los ajustes que desactivan la comprobación.

<!-- TOC -->
* [Canales de publicación, fin de vida y recomendación de actualización](#release-tracks-end-of-life-and-the-update-recommendation)
  * [Por qué un número de versión no es una respuesta](#why-a-version-number-is-not-an-answer)
  * [Qué puede y qué no puede decir el calendario incluido](#what-the-bundled-schedule-can-and-cannot-tell-you)
  * [La versión recomendada sigue su canal](#the-recommended-release-follows-your-track)
  * [Declarar su canal de publicación](#declaring-your-release-track)
<!-- TOC -->


## Por qué un número de versión no es una respuesta {#why-a-version-number-is-not-an-answer}

OpenCloud publica versiones rolling, production y LTS a partir de la misma
secuencia de versiones. La consecuencia para la monitorización es que la
*misma* versión puede estar perfectamente actualizada o llevar mucho tiempo sin
soporte según el canal en el que se publicó. `7.2.3` es la versión production
actual aunque el canal rolling ya vaya por `7.4.0`, mientras que `7.3.0`, una
versión *superior*, dejó de recibir correcciones el día en que apareció
`7.4.0`.

Por eso el complemento trabaja con **líneas de versiones** (`MAJOR.MINOR`), que
son la unidad que mantiene OpenCloud: `7.2.3` es un parche de la línea `7.2`.
Una línea puede pertenecer a más de un canal (`7.2` se publicó como versión
rolling antes de pasar a production, y `4.0` es a la vez la línea production
anterior y la línea LTS actual) y se evalúa según el canal que le dé soporte
durante más tiempo.

El calendario se incluye en `opencloud_local_scan/data/release_schedule.json`
y se extrae de las fechas de publicación de la documentación de administración
de OpenCloud, la única fuente que indica el *tipo* de versión; la lista de
versiones de GitHub no distingue una versión rolling de una production. Se
actualiza con cada versión y cada semana mediante un
[flujo de trabajo programado](../../.github/workflows/release-schedule.yml), y
la misma ejecución reescribe la tabla anterior, así que las versiones citadas
ahí son las que el complemento usa realmente para evaluar, no las que estaban
vigentes cuando se escribió esta página. Todo lo demás de esta sección,
incluidos los ejemplos siguientes, está escrito a mano y puede mencionar
versiones antiguas para ilustrar una idea.

## Qué puede y qué no puede decir el calendario incluido {#what-the-bundled-schedule-can-and-cannot-tell-you}

El calendario incluido tiene estos límites:

- **Las versiones LTS solo están disponibles con suscripción**, así que una
  línea LTS se reconoce a partir de la documentación, pero sus versiones puede
  que nunca aparezcan públicamente. Si su proveedor se ha comprometido con otro
  periodo, apunte `release_schedule` a su propio archivo en lugar de dejar que
  decida el incluido.
- **Una versión más reciente que el calendario nunca recibe la nota `F` ni se
  cuenta en contra de la instancia.** El archivo envejece entre
  actualizaciones de este paquete, así que una instancia actualizada con
  rapidez suele ser más reciente que los datos con los que se compara. Conserva
  su nota, no recibe ninguna recomendación de actualización y nunca se
  considera sin soporte por ello.
- **La salida lo notifica cuando ocurre.** Una versión posterior a la más reciente
  registrada para su línea, o de una línea más reciente que todas las
  registradas, activa `lifecycle.scheduleStale` en el documento de resultado,
  rellena `scheduleNote`, `scheduleUpdated` y `scheduleSource`, y añade una
  línea a la salida del complemento:

  ```
  Release schedule: 7.4.1 is newer than anything in the bundled release schedule (generated 2026-08-12), so that schedule is probably out of date. This is not counted against the instance. Check the current support window at https://docs.opencloud.eu/docs/admin/resources/lifecycle/, and regenerate the schedule with scripts/update_release_schedule.py.
  ```

  Es una afirmación sobre el archivo incluido, no sobre la instancia: el
  periodo de soporte calculado procede de datos más antiguos que la versión
  evaluada, así que merece la pena volver a consultarlo en la
  [fuente][lifecycle]. Actualizar el paquete, o ejecutar
  `python scripts/update_release_schedule.py`, hace que desaparezca. Una línea
  que realmente ha perdido el soporte sigue sin él: aplicar parches dentro de
  una línea sin soporte no la reabre, y la nota explica los datos en lugar de
  anular el veredicto.

## La versión recomendada sigue su canal {#the-recommended-release-follows-your-track}

Un canal de versiones solo conoce la versión más reciente *en general*, y en
OpenCloud siempre es una rolling. Recomendarla a una instancia production o
LTS la llevaría a un canal con un periodo de soporte de tres
semanas, algo que un operador del canal production no eligió.

Por eso la comprobación de actualizaciones usa el
[calendario de versiones](../../README.md#end-of-life-detection) para elegir un
destino dentro del propio canal de la instancia:

| Instalada | Canal      | Recomendada | Motivo                                                        |
|:----------|:-----------|:------------|:--------------------------------------------------------------|
| `7.2.3`   | production | *nada*      | Versión production actual, aunque rolling vaya por `7.4.0`    |
| `7.2.0`   | production | `7.2.3`     | El parche más reciente de la misma línea                      |
| `7.3.0`   | rolling    | `7.4.0`     | En rolling, la versión más reciente es la adecuada            |
| `4.0.0`   | LTS        | `4.0.8`     | Donde están las correcciones retroportadas                    |

La versión más reciente en general se sigue notificando, como `newestRelease`
en el resultado JSON y en la carga útil del webhook, así que no se oculta nada;
simplemente no se presenta como lo que hay que instalar. Si el canal de
versiones notifica un parche más reciente de la línea en la que ya está,
prevalece el canal, porque es más actual que el calendario incluido.

## Declarar su canal de publicación {#declaring-your-release-track}

De forma predeterminada, el calendario de versiones determina a qué canal
pertenece una versión y la evalúa con la mayor generosidad que permiten los
hechos: `7.2.3` aparece tanto en el canal rolling como en el production, así
que se trata como versión production y se considera actual.

Es el valor predeterminado adecuado mientras no se declare un canal, pero no
sirve para todas las instancias. Si sigue deliberadamente el canal rolling, `7.2.3` perdió el
soporte el día en que se publicó `7.4.0`, y querrá saberlo.
`--release-track` indica en qué canal está, y la versión se evalúa entonces
solo en ese canal:

```bash
check-opencloud-security --host opencloud.example.com --release-track rolling
```

`--release-track auto` es el valor predeterminado: se pregunta al calendario de
versiones a qué canal pertenece la versión instalada. Es la misma respuesta
que omitir la opción, pero dicha explícitamente, y permite usar una misma
configuración en instancias de canales distintos:

```bash
check-opencloud-security --host opencloud.example.com --release-track auto
```

| Instalada | Declarado           | Veredicto                                                                   |
|:----------|:--------------------|:----------------------------------------------------------------------------|
| `7.2.3`   | *nada* o `auto`     | Con soporte: versión production actual                                      |
| `7.2.3`   | `production`        | Con soporte: versión production actual                                      |
| `7.2.3`   | `rolling`           | **Sin soporte**: sustituida por `7.4.0`, actualice a `7.4.0`                |
| `7.4.0`   | `production`        | Con soporte: por delante del canal production, cuya versión actual es `7.2.3` |
| `2.3.0`   | `production`        | **Sin soporte**: por detrás del canal production, actualice a `7.2.3`       |
| `4.0.8`   | `lts`               | Con soporte hasta que termine el periodo de dos años                        |

Esto tiene dos consecuencias:

- **Ir por delante de su canal no es un hallazgo.** Una instancia production
  que ha pasado a la versión rolling actual tiene todo lo que incluye el canal
  production y más, así que se notifica como por delante de su canal en lugar
  de recibir la nota `F`. Solo una versión *por detrás* de la actual de su
  canal está sin soporte.
- **La comprobación nunca recomienda volver a una versión anterior.** Si el
  canal declarado no tiene ninguna versión a la que pueda *subir*, la
  recomendación de actualización queda vacía y el motivo explica la situación.
  Pasar de `7.4.0` a `7.2.3` es una decisión que el complemento le deja a
  usted.

El canal declarado también orienta la recomendación de actualización descrita
en [la sección anterior](#the-recommended-release-follows-your-track), y la
salida lo marca como declarado para distinguirlo de uno deducido:

```
Release lifecycle: 7.2 (rolling track declared), out of support since 2026-07-14, upgrade to 7.4.0
```

Un valor desconocido se ignora en lugar de tratarse como error, así que una
errata en un archivo de configuración vuelve al comportamiento predeterminado
en lugar de detener la comprobación.

## Aviso antes del fin de vida {#warning-before-the-end-of-life}

El fin de vida es `CRITICAL` el día que llega, demasiado tarde para planificar
una actualización. `--eol-warning DÍAS` (`COS_EOL_WARNING`, YAML
`eol_warning`) convierte un resultado que sería `OK` en `WARNING` cuando a la
línea en uso le quedan `DÍAS` o menos días de soporte:

```text
WARNING: The 7.2 release line reaches end of life on 2026-10-14 (20 days left). Upgrade to 7.4.0.
```

Solo eleva `OK`; un resultado que ya es `WARNING` o `CRITICAL` conserva su
propia línea. Una línea sin fecha de fin de vida publicada nunca avisa. `0`,
el valor predeterminado, lo desactiva.

## ¿La actualización corrige los avisos? {#does-the-upgrade-clear-the-advisories}

Cuando la versión instalada tiene avisos de seguridad conocidos, el escaneo
registra `upgradePath`: lo que la versión recomendada hace con cada uno.

```json
{"upgradePath": {"target": "7.2.4", "fixes": ["GHSA-aaaa"],
  "stillAffected": ["GHSA-bbbb"], "safeVersion": "7.3.0"}}
```

Cada rango de un aviso se compara con el destino, así que cuenta una
corrección portada a otra línea. `safeVersion` es la versión más baja que
incluye todas las correcciones que le faltan al destino, o `null` si alguna
aún no existe. El plugin lo muestra como línea de detalle.

## Ensayar cada actualización {#rehearse-every-upgrade}

`upgradePath` cubre la única versión que recomienda el análisis.
`upgradeRehearsal` cubre cada versión a la que merece la pena pasar: el último
parche de la línea instalada y la versión más reciente de cada línea posterior
(solo líneas del canal declarado, si la instancia declara uno). Para cada una
indica los avisos que `fixes`, aquellos por los que sigue `stillAffected`, los
que `introduces`, si está `endOfLife` y el `rating` que le daría el análisis.

```json
{"upgradeRehearsal": [
  {"version": "7.2.4", "line": "7.2", "recommended": false,
   "fixes": ["GHSA-aaaa"], "stillAffected": ["GHSA-bbbb"], "introduces": [],
   "endOfLife": false, "versionRating": 2, "rating": 2}
]}
```

La valoración usa las mismas reglas de versión que el análisis. Las
comprobaciones fallidas de la instancia siguen limitándola (`versionRating`
indica lo que permitiría la versión por sí sola), porque una actualización
cambia la versión, no el proxy que tiene delante. El plugin muestra una línea
de detalle con sus propias letras de valoración:

```text
Upgrade rehearsal: 7.2.4 fixes 1 finding, leaves 1, reaches rating D; 7.3.0 fixes 2 findings, leaves 0, reaches rating A+.
```

El ensayo solo conoce el calendario y la base de datos de avisos incluidos o
actualizados. Una versión o un aviso publicado más adelante puede cambiar el
resultado.

La aplicación web muestra las mismas entradas como **Qué le aportaría
actualizar**: una fila por versión candidata, con los avisos que resuelve, los
que deja y la calificación que alcanzaría. Cuando la versión por sí sola
obtendría más, la diferencia son los hallazgos de esta instancia, que una
actualización no toca.
