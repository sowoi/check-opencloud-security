# Notificar solo lo que ha cambiado entre análisis de OpenCloud

Utilice `--baseline` para guardar los hallazgos de cada análisis y compararlos
con la siguiente ejecución. Añada `--warn-on-new` para alertar solo cuando haya
hallazgos nuevos o que hayan empeorado. Los problemas existentes siguen
apareciendo en el informe.

El [README principal](../../README.md#reporting-only-what-changed) contiene la
versión breve. Esta página describe el comportamiento completo: los formatos de
comparación, qué cuenta como regresión y las reglas que impiden que una línea
base oculte algo.

<!-- TOC -->
* [Notificar solo lo que ha cambiado](#reporting-only-what-changed)
  * [Escribir y comparar una línea base](#writing-and-comparing-a-baseline)
  * [Qué cuenta como regresión](#what-counts-as-a-regression)
  * [Aspectos que conviene conocer](#points-worth-knowing)
<!-- TOC -->


## Escribir y comparar una línea base {#writing-and-comparing-a-baseline}

`--baseline` indica el archivo en el que se escriben los hallazgos de cada
ejecución y con el que se compara la siguiente:

```bash
check-opencloud-security -H opencloud.example.com \
    --check-hardening \
    --baseline /var/lib/check_opencloud/baseline.json
```

Por sí sola, esta opción solo añade una línea a la salida (`Baseline: ...`).
Añada `--warn-on-new` para actuar en consecuencia:

```bash
check-opencloud-security -H opencloud.example.com \
    --check-hardening \
    --baseline /var/lib/check_opencloud/baseline.json \
    --warn-on-new
```

La comprobación informa entonces `OK` mientras la situación no cambie, y su
estado normal en cuanto algo es nuevo o ha empeorado. El estado completo se
imprime en cualquier caso: solo se suprime la alerta, nunca la evidencia:

```
OK: nothing new since the last run (WARNING state unchanged).
OpenCloud 7.2.3 on opencloud.example.com, rating: C, last scanned: 2026-01-14
Missing hardening: cspWithoutUnsafeInline (run with --debug for what each means and how to fix it)
Baseline: No new findings since 2026-01-14T09:00:00+00:00 (1 known issue(s) unchanged)
Suppressed by --warn-on-new: this run would otherwise be WARNING (WARNING: 1 hardening measure(s) missing, but no known vulnerabilities.)
```

Cada comparación enumera además los CVE añadidos y resueltos, los cambios en
medidas de refuerzo y en comprobaciones adicionales, los cambios de nota, de
fin de vida y de horizonte de soporte, y los cambios de la versión instalada o
de destino. `text` es el formato predeterminado para los registros. Para el
resumen de un paso de GitHub Actions o un comentario en una pull request,
seleccione Markdown:

```shell
check-opencloud-security -H opencloud.example.com \
  --baseline /var/lib/check_opencloud/baseline.json \
  --diff-format markdown >> "$GITHUB_STEP_SUMMARY"
```

Utilice `--diff-format slack` (o `json`) para obtener JSON de Slack Block Kit.
Cuando hay un webhook configurado, cada comparación con la línea base se
incluye como `baseline_diff`; el formato de Slack coloca además los bloques y
la franja de color en el nivel superior para los webhooks entrantes:

```shell
check-opencloud-security -H opencloud.example.com \
  --baseline /var/lib/check_opencloud/baseline.json \
  --diff-format slack --webhook-url 'https://hooks.slack.com/services/<token>' \
  --webhook-on always
```


## Qué cuenta como regresión {#what-counts-as-a-regression}


- un hallazgo que no estaba la vez anterior: un nuevo aviso de seguridad, una
  medida de refuerzo que ha retrocedido, una comprobación adicional que ha
  empezado a fallar o una actualización recién disponible;
- una nota inferior a la registrada;
- **una versión que ha superado su fin de vida, siempre.** No recibe
  correcciones de seguridad, así que empeora cada día que sigue en producción
  y una línea base nunca puede darla por aceptada.

## Cambios de configuración {#configuration-drift}


La línea base guarda la **huella de configuración** del análisis: hashes
agrupados por transporte, cabeceras, uso compartido, autenticación y proxy.
Permiten detectar cambios de configuración aunque la nota y los hallazgos
sigan igual:

```text
Baseline: No new findings since 2026-09-14T06:00:00Z, but the configuration changed (headers, proxy)
```

El informe nombra los grupos cuya configuración ha cambiado. El archivo de
referencia, la salida y el webhook contienen hashes, sin los valores de
configuración originales.

El cambio se informa, no se juzga: no crea un hallazgo, no hace que una
ejecución empeore y nunca cambia el código de salida. Una referencia escrita
antes de que existieran las huellas no puede detectar cambios de configuración
porque carece de huellas para compararlas. Por eso no informa de cambios;
esto no demuestra que la configuración siga igual.

## Regresiones de cobertura {#coverage-regressions}


Una línea base también recuerda en qué comprobaciones el análisis **llegó a
una conclusión**. Cuando una comprobación que antes se midió ahora es
`inconclusive` - se ejecutó sin poder decidir, por ejemplo porque una consulta
DNS no respondió a tiempo -, la ejecución lo indica aunque la calificación no
haya cambiado:

```text
WARNING: 1 previously measured check(s) are now inconclusive; the rating is unchanged (Server is up to date. No known vulnerabilities.)
Coverage regressed (1): previously measured, now inconclusive: caaRecord (timeout) - the rating is unaffected.
```

Esto se mantiene separado de la calificación de seguridad. La
calificación, los perfdata y los hallazgos siguen siendo los que dieron las
mediciones; solo cambia el estado de alerta, y solo de `OK` a `WARNING`. Una
ejecución que ya está en `WARNING` o `CRITICAL` conserva su mensaje y añade la
línea. `--warn-on-new` no la suprime: un análisis que de pronto ve menos es
una novedad.

- Solo cuenta `inconclusive`. Una comprobación que pasa a `not_checked` -
  desactivada por usted o que ya no aplica - no es una regresión del análisis.
- Una comprobación perdida sigue contando como «medida antes» hasta que una
  ejecución posterior la vuelva a medir: el aviso dura lo que dura la laguna.
- El webhook incluye la lista en `baseline_diff` como `coverage_regressed`; la
  comparación de dos documentos la indica como `coverageRegressed`.
- Una línea base anterior sin cobertura no puede indicar ninguna pérdida en la
  primera ejecución tras actualizar; registra lo medido para la siguiente.

## Comprobaciones que solo hizo una ejecución {#checks-only-one-run-made}

Un hallazgo solo se considera nuevo si la ejecución anterior podía haberlo
indicado. Cuando el analizador incorpora una comprobación - tras una
actualización, o porque usted activó las comprobaciones adicionales -, un
fallo que ahora encuentra *no se comprobó* la vez anterior, no se superó, y
la ejecución lo dice así:

```text
Baseline: Newly measured (1): hardening:basicAuthDisabled - the last run did not check these
Hardening: + basicAuthDisabled (not checked before)
```

Sigue alertando, y `--warn-on-new` no lo suprime: nadie ha sido informado aún
de ese fallo. A la inversa, un fallo que la ejecución actual ya no comprueba
aparece como `(not checked now)` y no como resuelto.

- Lo que una ejecución podía indicar sale de su bloque de cobertura, nunca de
  una clave ausente. Un informe que no enumera sus comprobaciones se compara
  como antes, así que una regresión real nunca cambia de nombre.
- El webhook incluye las listas en `baseline_diff` como `newly_measured` y
  `no_longer_measured`; la comparación web, como `newlyMeasured` y
  `noLongerMeasured`.
- Una línea base anterior no puede decir qué comprobó, así que la primera
  ejecución tras actualizar compara como antes.

## Aspectos que conviene conocer {#points-worth-knowing}


- La primera ejecución no tiene nada con qué compararse, así que informa con
  normalidad y se convierte en la línea base. Empezar a usar la opción nunca
  oculta nada.
- Un archivo contiene una entrada por host, así que una lista de `--host`
  separada por comas puede compartirlo.
- Los hallazgos excluidos con `--ignore-hardening` y las medidas que OpenCloud
  tiene fijadas en el código se omiten, exactamente igual que en la línea de
  alerta.
- `--warn-on-new` sin `--baseline` se rechaza: sin un lugar donde recordar la
  ejecución anterior, informaría de "nada nuevo" para siempre.
- Una línea base que no se puede escribir se notifica con una línea de salida y
  nada más. La contabilidad nunca decide el veredicto sobre una instancia.
- El archivo se escribe de forma atómica y con permisos solo para el
  propietario. Guárdelo en un lugar que pertenezca al usuario de
  monitorización, p. ej. `/var/lib/check_opencloud/`.
