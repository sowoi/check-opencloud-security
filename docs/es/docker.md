# Ejecutar el escáner de seguridad de OpenCloud con Docker

Ejecute el escáner en su propio equipo con la imagen de Docker publicada. Usa el
mismo escáner que el [servicio web](../webapp.md), se conecta directamente a su
instancia y no está sujeto al límite de frecuencia del sitio web. Necesita
Docker, pero ninguna cuenta en el servicio de análisis.

```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com
```

Imprime la misma línea que recibiría un sistema de
monitorización:

```text
OK: Server is up to date. No known vulnerabilities.
OpenCloud 7.2.3 on opencloud.example.com, rating: A+, last scanned: 2026-08-25 09:41:12
Release lifecycle: 7.2 (production, track detected), current release
```

El código de salida es el de Nagios (`0` OK, `1` WARNING, `2` CRITICAL, `3`
UNKNOWN), así que la misma línea sirve en un script, una canalización o una
tarea de cron sin nada más alrededor.

> **Aviso sobre marcas.** Este proyecto es independiente. No está afiliado a
> OpenCloud GmbH, ni respaldado ni apoyado por ella. "OpenCloud" y todas las
> marcas relacionadas pertenecen a sus respectivos titulares y aquí solo se
> utilizan para identificar el software que se comprueba.

<!-- TOC -->
* [Analizar desde la línea de comandos, en una línea](#scanning-from-the-command-line-in-one-line)
  * [Qué es la imagen](#what-the-image-is)
  * [El mismo análisis, en JSON](#the-same-scan-as-json)
  * [Variantes útiles](#useful-variations)
  * [Acortar el comando](#make-it-shorter)
  * [Sin Docker](#without-docker)
  * [Siguientes pasos](#where-to-go-next)
<!-- TOC -->


## Qué es la imagen {#what-the-image-is}

[`okxo/opencloud-scanner`](https://hub.docker.com/r/okxo/opencloud-scanner) se
construye a partir de este repositorio e incluye ambos puntos de entrada:

| Punto de entrada | Qué hace |
|:------------|:-------------|
| `check-opencloud-security` | El complemento de Nagios/Icinga: una línea de estado, datos de rendimiento y un código de salida |
| `check-opencloud-scanner` | El escáner por sí solo: el documento de resultado completo en JSON, o un servicio HTTP |

El comando predeterminado de la imagen inicia la aplicación web, por eso todas
las líneas de esta página indican `--entrypoint`. Fije una versión en lugar de
`latest` (`okxo/opencloud-scanner:1.9`) si quiere que el comando se comporte
igual el mes que viene.

## El mismo análisis, en JSON {#the-same-scan-as-json}

Todo lo que muestra la interfaz web procede de este documento: la nota, el
ciclo de vida de la versión, los avisos de seguridad, cada comprobación y el
plan de corrección:

```shell
docker run --rm --entrypoint check-opencloud-scanner \
  okxo/opencloud-scanner:latest scan opencloud.example.com
```

Páselo por `jq` para quedarse con las partes que le interesen:

```shell
docker run --rm --entrypoint check-opencloud-scanner \
  okxo/opencloud-scanner:latest scan opencloud.example.com \
  | jq '{rating, version, addresses, failed: [.extraChecks[] | select(.passed | not) | .id]}'
```

`addresses` contiene las direcciones IPv4 e IPv6 a las que se resolvió el
nombre durante el análisis, las mismas que la página de resultados muestra en
**Resuelto a**. Merece la pena revisarlas cuando un análisis notifica algo
inesperado: un nombre que apunta a una dirección antigua explica una cantidad
sorprendente de resultados sorprendentes.

## Variantes útiles {#useful-variations}

Explicar cada hallazgo en lugar de solo nombrarlo:

```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com --debug
```

Aceptar un hallazgo con el que ha decidido convivir, exactamente como las
casillas del sitio web:

```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com \
  --ignore-hardening basicAuthDisabled
```

Evaluar la versión frente a un canal de publicación concreto en lugar del que
deduce el análisis:

```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com \
  --release-track lts
```

Analizar una instancia que no está en internet, como un servidor de pruebas de
su propia red o uno detrás de un nombre que solo conoce su resolvedor:

```shell
docker run --rm --network host --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.internal.example.com
```

El servicio alojado rechaza las direcciones privadas. Un análisis desde su
propio equipo no lo hace.

Configurarlo con variables de entorno en lugar de opciones, lo que resulta más
fácil de convertir en plantilla para una lista de hosts. Cada opción tiene una
variable `COS_`, enumerada en el
[README principal](../../README.md#environment-variables):

```shell
docker run --rm -e COS_HOST=opencloud.example.com \
  --entrypoint check-opencloud-security okxo/opencloud-scanner:latest
```

Omitir la comprobación de actualizaciones cuando el equipo no tiene acceso a
internet o cuando no desea que se consulte el canal de versiones:

```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com --no-update-check
```

## Acortar el comando {#make-it-shorter}

Si lo ejecuta a menudo, una función de shell lo reduce a una sola palabra:

```shell
# ~/.bashrc or ~/.zshrc
opencloud-scan() {
  docker run --rm --entrypoint check-opencloud-security \
    okxo/opencloud-scanner:latest --host "$1" "${@:2}"
}
```

```shell
opencloud-scan opencloud.example.com --debug
```

## Sin Docker {#without-docker}

La comprobación está en PyPI y es un programa Python normal, así que
[`uv`](https://docs.astral.sh/uv/) o `pipx` la ejecutan sin ningún contenedor:

```shell
uvx --from check-opencloud-security check-opencloud-security \
  --host opencloud.example.com
```

```shell
pipx run --spec check-opencloud-security check-opencloud-security \
  --host opencloud.example.com
```

## Siguientes pasos {#where-to-go-next}

- [El README principal](../../README.md): todas las opciones y el significado
  de cada comprobación.
- [Programación](../scheduling.md): el mismo comando con un temporizador,
  mediante una unidad de systemd o una entrada de cron.
- [Ejecutar la comprobación desde CI](../ci.md): condicionar una canalización a
  un campo del documento de resultado.
- [Comprobar un conjunto de instancias](../many-instances.md): un archivo por
  instancia y alertas solo sobre lo que ha cambiado.
- [El servicio público de análisis](../webapp.md): ejecutar usted mismo la
  interfaz web, si además del comando quiere las páginas.
