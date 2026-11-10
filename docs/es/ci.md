# Comprobaciones de seguridad de OpenCloud en canalizaciones de CI

Utilice una canalización de CI programada para análisis periódicos o para
comprobar una instancia desde otra red. Compruebe que la canalización se
ejecuta y entienda lo que notifica: un trabajo que no se ejecuta no produce
ningún resultado de análisis.

Sea cual sea la plataforma, tres cosas deciden si funciona:

- **El runner tiene que llegar a la instancia.** Un runner alojado no puede
  analizar algo que está detrás de su cortafuegos; para eso use un runner
  propio.
- **El análisis se hace desde el punto de vista del runner.** Lo que mide
  sobre TLS, la obligatoriedad de HTTPS y los puertos de depuración accesibles
  es lo que ve alguien de fuera en esa red, que suele ser la respuesta
  interesante.
- **El código de salida es el resultado**: `0` OK, `1` WARNING, `2` CRITICAL,
  `3` UNKNOWN. Una canalización falla con cualquier valor distinto de cero, así
  que `--warning` y `--critical` deciden lo estricta que es.

<!-- TOC -->
* [Ejecutar la comprobación desde CI](#running-the-check-from-ci)
  * [GitHub Actions](#github-actions)
    * [La acción](#the-action)
    * [Alimentar el panel de análisis de código](#feeding-the-code-scanning-dashboard)
    * [Instalarlo usted mismo](#installing-it-yourself-instead)
    * [Evidencia de compatibilidad con OpenCloud](#opencloud-compatibility-evidence)
    * [Informar en lugar de fallar](#reporting-rather-than-failing)
    * [El documento JSON](#the-json-document-instead)
  * [GitLab CI](#gitlab-ci)
  * [Usar la imagen de contenedor en lugar de instalar](#using-the-container-image-instead-of-installing)
  * [No ponga el token en la línea de comandos](#do-not-put-the-token-on-the-command-line)
<!-- TOC -->


## GitHub Actions {#github-actions}

### La acción {#the-action}

```yaml
name: OpenCloud security check

on:
  schedule:
    - cron: "0 6 * * *"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: sowoi/check-opencloud-security@v1.16.0
        with:
          target: opencloud.example.com
          # Raises GitHub's anonymous rate limit for the release feed. The
          # token the job already has is enough; it needs no scopes.
          releases-token: ${{ github.token }}
```

El paso instala la versión fijada, analiza la instancia, escribe
`opencloud-security.json`, añade el resultado al resumen del trabajo y hace
fallar el trabajo con WARNING, CRITICAL o UNKNOWN.

**Fije la etiqueta.** El calendario de versiones y la versión de OpenCloud más
reciente conocida van *dentro* del paquete, así que la versión que se ejecuta
forma parte del veredicto. `@v1.16.0` instala exactamente la 1.16.0; una
referencia a una rama o a un SHA instala la versión más reciente y lo indica
en una anotación de advertencia.

| Entrada | Valor predeterminado | Qué hace |
|:--|:--|:--|
| `target` | *obligatorio* | La instancia, como nombre de host o URL |
| `version` | la etiqueta fijada | Qué versión de la comprobación se instala |
| `format` | `json` | `json`, `sarif`, `junit` o `nagios` |
| `output-file` | `opencloud-security.json` | Dónde se escribe la salida |
| `fail-on` | `warning` | `warning`, `critical` o `never` |
| `warning` / `critical` | valores predeterminados del complemento | Umbrales de nota |
| `check-hardening` | `true` | Tiene en cuenta las medidas de refuerzo en el resultado |
| `ignore-hardening` | *ninguno* | Identificadores que se excluyen, separados por comas |
| `release-track` | `auto` | `auto`, `rolling`, `production` o `lts` |
| `releases-token` | *ninguno* | Un token para el límite de frecuencia del canal de versiones |
| `summary` | `true` | Escribe el resultado en el resumen del trabajo |
| `extra-args` | *ninguno* | Cualquier otra opción, pasada tal cual |

Las salidas son `exit-code`, `status`, `rating`, `rating-label`, `message` y
`result-file`. Todas salvo las dos primeras están vacías si `format` no es
`json`, porque se leen de ese documento:

```yaml
      - uses: sowoi/check-opencloud-security@v1.16.0
        id: scan
        with:
          target: opencloud.example.com
          fail-on: never

      - name: Open an issue when the grade drops below A
        if: steps.scan.outputs.rating < 4
        run: gh issue create --title "OpenCloud is rated ${{ steps.scan.outputs.rating-label }}"
        env:
          GH_TOKEN: ${{ github.token }}
```

`fail-on: never` es lo que lo hace posible: el paso tiene éxito y la decisión
pasa a un paso posterior que puede hacer algo más útil que poner la ejecución
en rojo.

Tenga en cuenta que el runner tiene que poder llegar a la instancia. Un runner
alojado no ve nada que esté detrás de su cortafuegos; para eso use uno propio,
o analice desde la red en la que realmente se publica la instancia.

### Alimentar el panel de análisis de código {#feeding-the-code-scanning-dashboard}

`format: sarif` escribe SARIF 2.1.0, que es lo que importa la pestaña Security
de GitHub. Así los hallazgos quedan donde están el resto de sus hallazgos de
seguridad, con su propio historial, y no en un registro que nadie abre:

```yaml
permissions:
  contents: read
  security-events: write

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: sowoi/check-opencloud-security@v1.16.0
        with:
          target: opencloud.example.com
          format: sarif
          output-file: opencloud-security.sarif
          # Upload the findings even when they are bad enough to fail a build.
          fail-on: never

      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: opencloud-security.sarif
          category: opencloud-security
```

Mantenga aquí `fail-on: never` y condicione el resultado a los hallazgos
subidos. Un paso que falla antes de la subida desecha precisamente los
hallazgos que lo hicieron fallar.

### Instalarlo usted mismo {#installing-it-yourself-instead}

La acción no tiene nada privilegiado: instala el mismo paquete y ejecuta el
mismo comando. Hágalo a mano cuando necesite un paso que la acción no
contempla, o cuando prefiera no depender de ninguna acción.

```yaml
name: OpenCloud security check

on:
  schedule:
    - cron: "0 6 * * *"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - name: Install the check
        run: pipx install check-opencloud-security==1.1.0

      - name: Scan the instance
        env:
          COS_HOST: opencloud.example.com
          COS_CHECK_HARDENING: "true"
          COS_UPDATE_WARNING: "true"
          # Raises GitHub's anonymous rate limit for the release feed. The
          # token GITHUB_TOKEN gives the job is enough; it needs no scopes.
          COS_RELEASES_TOKEN: ${{ github.token }}
        run: check-opencloud-security
```

Fije la versión en lugar de seguir `latest`. El calendario de versiones y la
versión de OpenCloud más reciente conocida van dentro del paquete, así que la
versión que instala forma parte del veredicto, y una instalación sin fijar
convierte una publicación de origen en un fallo inexplicable de la
canalización.

Merece la pena mantener `workflow_dispatch`: es la forma de volver a ejecutar
la comprobación después de corregir algo sin esperar al día siguiente.

### Informar en lugar de fallar {#reporting-rather-than-failing}

Un flujo de trabajo programado que falla solo avisa a la última persona que lo
modificó. Para que el resultado llegue a donde la gente mira, mantenga el
trabajo en verde y publique el resultado:

```yaml
      - name: Scan the instance
        id: scan
        continue-on-error: true
        env:
          COS_HOST: opencloud.example.com
          COS_CHECK_HARDENING: "true"
        run: |
          set +e
          check-opencloud-security > result.txt
          state=$?
          set -e
          cat result.txt
          echo "state=$state" >> "$GITHUB_OUTPUT"

      - name: Summarise
        run: |
          {
            echo "### OpenCloud security check"
            echo '```'
            cat result.txt
            echo '```'
          } >> "$GITHUB_STEP_SUMMARY"
```

Como alternativa, defina `--webhook-url` para entregar el resultado
directamente; consulte [Recetas de webhooks](../webhook-recipes.md). La entrega
sigue dependiendo de que el flujo de trabajo se ejecute. Si las ejecuciones
programadas están desactivadas, no se generan ni resúmenes ni webhooks.

### El documento JSON {#the-json-document-instead}

Para todo lo que tenga que tomar una decisión (un control de políticas, un
panel, una incidencia creada automáticamente), use el escáner en lugar del
complemento. Imprime el documento de resultado completo, y todos sus campos
están documentados en
[el README de la biblioteca](../../opencloud_local_scan/README.md).

```yaml
      - name: Scan and keep the result
        run: |
          check-opencloud-scanner scan --compact opencloud.example.com > scan.json
          jq -e '.EOL == false' scan.json \
            || { echo "::error::The installed release no longer receives security fixes"; exit 1; }

      - uses: actions/upload-artifact@v4
        with:
          name: opencloud-scan
          path: scan.json
```

`jq -e` termina con un valor distinto de cero cuando la expresión es falsa, y
eso es lo que convierte un campo del documento en un control de la
canalización. `.EOL`, `.rating`, `.updates.available` y
`.lifecycle.daysRemaining` son los cuatro campos por los que merece la pena
condicionar.

### Evidencia de compatibilidad con OpenCloud {#opencloud-compatibility-evidence}

El flujo de trabajo del repositorio **real OpenCloud container** mantiene como
referencia un digest inmutable y revisado de la imagen rolling y ejecuta el
escáner contra él cada semana. Verifica que el contenedor sigue
inicializándose, expone el punto de acceso de estado público esperado, se
identifica como OpenCloud, notifica una versión y produce una nota acotada. La
imagen notifica su versión exacta de OpenCloud durante la prueba; el flujo de
trabajo no afirma deliberadamente la compatibilidad con una nueva versión
hasta que se ha revisado esa evidencia.

| Evidencia | Referencia | Compatible cuando | Vía de revisión |
|:--|:--|:--|:--|
| Integración con el contenedor del fabricante | `opencloudeu/opencloud-rolling@sha256:0bb9038f4c01ab187a014e97550435f5d45630731aed9341d87a0b40fe72fe3d` | La prueba de integración completa se supera y se revisan la versión notificada y el comportamiento observable desde fuera | Lance el flujo de trabajo con `candidate_image`; actualice la referencia solo en una pull request revisada |
| Ciclo de vida de versiones | Calendario incluido más la actualización diaria conservadora | Las líneas nuevas o modificadas conservan los datos de soporte existentes y superan las pruebas de regresión del ciclo de vida | Revise la PR de actualización del calendario de versiones |
| Avisos de seguridad | Base de datos incluida más la actualización diaria conservadora | Los avisos nuevos añaden evidencia sin eliminar rangos afectados conocidos | Revise la PR de actualización de la base de datos de avisos |

La automatización nunca reescribe fixtures, notas ni expectativas de seguridad
para poner en verde a una candidata. Una respuesta, cabecera, punto de acceso o
propiedad de seguridad que cambie debe contar con evidencia de la versión y con
un cambio de prueba revisable que cite esa evidencia.

El flujo de trabajo `Supply-chain checks` del repositorio se ejecuta en las
pull requests, en los pushes a `main` y cada semana. Exporta el conjunto de
dependencias completamente resuelto de `uv.lock`, ejecuta `pip-audit` sobre
las dependencias del núcleo, de la web y de MCP, y publica un SBOM CycloneDX
como artefacto del flujo de trabajo. Los pushes y las ejecuciones programadas
reciben además una certificación Sigstore de GitHub, de modo que el SBOM se
puede verificar con `gh attestation verify`. El flujo de trabajo de
publicación repite esto para el entorno de ejecución exacto que se distribuye
con cada paquete y certifica los archivos del paquete y el paquete web.

## GitLab CI {#gitlab-ci}

```yaml
opencloud-security:
  image: python:3.13-slim
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
  variables:
    COS_HOST: opencloud.example.com
    COS_CHECK_HARDENING: "true"
  before_script:
    - pip install --no-cache-dir check-opencloud-security==1.1.0
  script:
    - check-opencloud-security
  # WARNING (1) is worth seeing without failing the pipeline outright.
  allow_failure:
    exit_codes: [1]
```

`allow_failure.exit_codes` asigna directamente los estados del complemento a
los de GitLab: indique `1` para tolerar WARNING y añada `3` para tolerar un
análisis que no se pudo completar, aunque un análisis que no se puede
completar suele ser justo lo que más interesa saber.

Añada la programación en *Build → Pipeline schedules*; el bloque `rules`
anterior mantiene el trabajo fuera de las canalizaciones normales de commits.

## Usar la imagen de contenedor en lugar de instalar {#using-the-container-image-instead-of-installing}

Este ejemplo construye la imagen del complemento a partir de la copia del
repositorio. La imagen publicada `okxo/opencloud-scanner` es otra opción si
selecciona el complemento con `--entrypoint check-opencloud-security`.

```shell
docker build -f docker/Dockerfile \
  -t registry.example.com/check-opencloud-security:1.1.0 .
docker push registry.example.com/check-opencloud-security:1.1.0

docker run --rm \
  -e COS_HOST=opencloud.example.com \
  -e COS_CHECK_HARDENING=true \
  registry.example.com/check-opencloud-security:1.1.0
```

## No ponga el token en la línea de comandos {#do-not-put-the-token-on-the-command-line}

Los registros de CI los puede leer más gente de la que cree, y un
`--release-token` en una línea de comandos acaba en ellos. Pase los secretos
como variables de entorno (`COS_RELEASES_TOKEN`, `COS_WEBHOOK_URL`) o como
[referencia a un secreto](../../README.md#configuration-file-and-secrets). El
complemento oculta los tokens en su propia salida de depuración; no puede
ocultarlos en la traza de su shell.

---

[Volver al índice de la documentación](../README.md) | [Volver al README principal](../../README.md)
