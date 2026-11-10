# El escáner de seguridad de OpenCloud para agentes de IA y MCP

La aplicación web de este repositorio habla el
[Model Context Protocol](https://modelcontextprotocol.io) en `/mcp`, así que un
agente puede analizar una instancia de OpenCloud con una llamada a una
herramienta, sin que haya que enseñarle una API HTTP.

Funcionan dos direcciones:

| | Punto de acceso | Adecuado para |
|:--|:---------|:---------|
| **Alojado** | `https://scan.okxo.de/mcp` | Probarlo y analizar alguna instancia ocasional. Con límite de frecuencia, y cada análisis se ejecuta desde ese servidor |
| **Propio** | `http://127.0.0.1:8811/mcp` | Un parque propio, sin límites y sin que nada de sus instancias salga de su red |

Para usar cualquiera de los dos no hace falta nada: ni cuenta, ni clave de API,
ni registro. La única excepción es `erase_instance_data`, que necesita una
credencial que define el operador del despliegue; consulte
[El borrado necesita una credencial](#erasure-needs-a-credential).

<!-- TOC -->
* [Usar el escáner desde un agente de IA (MCP)](#using-the-scanner-from-an-ai-agent-mcp)
  * [Qué obtiene el agente](#what-the-agent-gets)
  * [Claude Code](#claude-code)
  * [Claude Desktop](#claude-desktop)
  * [GitHub Copilot en VS Code](#github-copilot-in-vs-code)
  * [GitHub Copilot CLI](#github-copilot-cli)
  * [Cursor](#cursor)
  * [Zed](#zed)
  * [Windsurf](#windsurf)
  * [Cualquier otro cliente](#any-other-client)
  * [Clientes que solo hablan stdio](#clients-that-only-speak-stdio)
  * [Ejecutar su propio punto de acceso](#running-your-own-endpoint)
  * [Desactivar MCP](#turning-mcp-off)
  * [El borrado necesita una credencial](#erasure-needs-a-credential)
  * [Cuando el punto de acceso pide iniciar sesión](#when-the-endpoint-asks-you-to-sign-in)
  * [Límites, y ser un buen invitado](#limits-and-being-a-good-guest)
  * [Comprobar que funciona](#checking-that-it-works)
<!-- TOC -->

## Qué obtiene el agente {#what-the-agent-gets}

Siete herramientas, cada una una tarea completa y no un único punto de acceso
HTTP:

| Herramienta | Qué hace |
|:-----|:-------------|
| `scan_instance` | Envía una instancia, espera al análisis y devuelve la nota y los hallazgos. Informa del progreso mientras espera |
| `scan_instances` | Lo mismo para una lista de instancias, en un solo lote |
| `get_scan_result` | Lee un análisis por su uuid sin esperar; es lo que usa un agente para consultar periódicamente |
| `plan_remediation` | La lista ordenada de correcciones de un análisis terminado, con la nota que alcanza cada paso |
| `compare_scans` | Compara dos análisis terminados de una misma instancia: qué se corrigió, qué sigue abierto, qué es nuevo. Ambos deben seguir disponibles |
| `export_scan` | Un análisis terminado como `json`, `csv`, `sarif` o `pdf` |
| `erase_instance_data` | **Destructiva.** Borra todo lo guardado sobre un nombre de host. Necesita la credencial del operador |

y cinco recursos, para que un agente pueda leer los contratos (y el
conocimiento que hay detrás de un hallazgo) sin salir del protocolo:

| Recurso | Qué es |
|:---------|:-----------|
| `openapi` | La descripción OpenAPI 3.1 de la API REST |
| `arazzo` | Los flujos de trabajo Arazzo que combinan esas operaciones |
| `discovery` | El documento `/.well-known/ai.json` |
| `catalogue` | Cada indicador de refuerzo y comprobación adicional que ejecuta el escáner, explicado: qué significa, el ajuste de OpenCloud que hay detrás, cómo corregirlo y un enlace a la documentación oficial. El mismo conocimiento que muestra la página [`/catalogue`](https://scan.okxo.de/catalogue) |
| `advisories` | Toda la base de datos de avisos de seguridad con la que se evalúa un análisis, no solo el subconjunto que coincidió con una instancia |

Los dos últimos son una base de conocimiento más que un contrato: lea
`catalogue` para explicar qué significa el identificador de un hallazgo antes
o después de un análisis, y `advisories` para ver qué detectaría el escáner,
sin enviar ningún destino.

También hay siete prompts: las tareas que la gente pide de verdad, redactadas
una vez para que todos los clientes envíen la misma solicitud bien formada:

| Prompt | Qué pide | Argumentos |
|:-------|:-----------------|:----------|
| `audit_instance` | Analizar una instancia, explicar la nota y redactar el plan de corrección | `target_url`, opcionalmente `release_track` |
| `audit_estate` | Analizar una lista de instancias y ordenarlas de peor a mejor | `targets`, opcionalmente `release_track` |
| `explain_scan_result` | Explicar un análisis terminado a un público concreto, sin volver a analizar | `uuid`, opcionalmente `audience` |
| `triage_findings` | Convertir un análisis terminado en una incidencia por cada paso del plan | `uuid`, opcionalmente `tracker` |
| `review_transport_security` | El certificado, su caducidad, la cadena y el protocolo, por separado | `target_url` |
| `check_release_support` | Si la versión sigue recibiendo correcciones de seguridad y a qué actualizar | `target_url`, opcionalmente `release_track` |
| `verify_remediation` | Volver a analizar una instancia corregida e informar de lo que han conseguido realmente los cambios | `baseline_uuid`, `target_url` |

En un cliente que los enumera, "Audit an instance and write a remediation
plan" es una entrada que se puede elegir: Claude Code los ofrece como comandos
de barra, VS Code bajo `/mcp.opencloud-scan.` y la mayoría de los demás en un
menú de adjuntos o de prompts. Al elegir uno se piden los argumentos y se envía
la solicitud; después el agente hace las llamadas a las herramientas por sí
mismo.

"Scan opencloud.example.com" es una sola llamada a una herramienta. El envío,
la espera y el resultado están dentro de `scan_instance`; el agente no tiene
que orquestarlos.

## Claude Code {#claude-code}

```bash
# Hosted
claude mcp add --transport http opencloud-scan https://scan.okxo.de/mcp

# Your own
claude mcp add --transport http opencloud-scan http://127.0.0.1:8811/mcp
```

Añada `--scope user` para tenerlo disponible en todos los proyectos y no solo
en el actual. Después, en una sesión:

```text
> scan opencloud.example.com and tell me what would improve the grade
```

`claude mcp list` muestra si se estableció la conexión, y `/mcp` dentro de una
sesión enumera las herramientas descubiertas.

## Claude Desktop {#claude-desktop}

Claude Desktop lee `claude_desktop_config.json`:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "opencloud-scan": {
      "type": "http",
      "url": "https://scan.okxo.de/mcp"
    }
  }
}
```

Reinicie la aplicación después. Las compilaciones que no pueden conectarse
directamente a un servidor remoto pueden usar el puente descrito en
[Clientes que solo hablan stdio](#clients-that-only-speak-stdio).

## GitHub Copilot en VS Code {#github-copilot-in-vs-code}

VS Code es la excepción: la clave de nivel superior es `servers`, no
`mcpServers`. Póngalo en `.vscode/mcp.json` para un espacio de trabajo, o
ejecute **MCP: Open User Configuration** desde la paleta de comandos para
todos:

```json
{
  "servers": {
    "opencloud-scan": {
      "type": "http",
      "url": "https://scan.okxo.de/mcp"
    }
  }
}
```

Después abra Copilot Chat en modo **Agent**; las herramientas aparecen en el
selector de herramientas. Si no aparecen, `MCP: List Servers` muestra la
conexión y su registro.

## GitHub Copilot CLI {#github-copilot-cli}

Copilot CLI combina la configuración de `~/.copilot/mcp-config.json` (global) y
de `.github/mcp.json` o `.mcp.json` en el directorio de trabajo:

```json
{
  "mcpServers": {
    "opencloud-scan": {
      "type": "http",
      "url": "https://scan.okxo.de/mcp"
    }
  }
}
```

`/mcp` dentro de una sesión enumera lo que se ha cargado.

## Cursor {#cursor}

`.cursor/mcp.json` en un proyecto, o `~/.cursor/mcp.json` de forma global:

```json
{
  "mcpServers": {
    "opencloud-scan": {
      "type": "http",
      "url": "https://scan.okxo.de/mcp"
    }
  }
}
```

Settings → MCP muestra el servidor y permite activar o desactivar herramientas
concretas.

## Zed {#zed}

`settings.json` (**Zed: Open Settings**), bajo `context_servers`:

```json
{
  "context_servers": {
    "opencloud-scan": {
      "source": "custom",
      "url": "https://scan.okxo.de/mcp"
    }
  }
}
```

Las versiones recientes de Zed también aceptan un `.mcp.json` con la clave
habitual `mcpServers`.

## Windsurf {#windsurf}

`~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "opencloud-scan": {
      "serverUrl": "https://scan.okxo.de/mcp"
    }
  }
}
```

## Cualquier otro cliente {#any-other-client}

El punto de acceso es MCP normal por **streamable HTTP**: una URL, `POST` para
las solicitudes, ninguna sesión que mantener y ninguna autenticación. Todo lo
que admita una URL funcionará con

```json
{"type": "http", "url": "https://scan.okxo.de/mcp"}
```

o con la misma URL escrita en un cuadro de diálogo de ajustes. Si un cliente
pregunta por el transporte, elija *streamable HTTP* (a veces llamado
"HTTP" o "remote") en lugar de SSE o stdio.

Un agente que nunca ha oído hablar de este servicio puede encontrar el punto de
acceso por sí mismo: `https://scan.okxo.de/.well-known/ai.json` lo indica,
junto con los documentos OpenAPI y Arazzo. El documento de descubrimiento
existe para eso; consulte
[la página de la API](https://scan.okxo.de/api#api-agents).
`https://scan.okxo.de/agents.txt` y `https://scan.okxo.de/llms.txt` apuntan al
mismo documento para los programas que buscan primero uno de esos dos nombres
de archivo, según las convenciones informales que ya usan algunos frameworks
de agentes y rastreadores; consulte
[Trabajar en las superficies para agentes](../../AGENTS.md#working-on-the-agent-facing-surfaces).

## Clientes que solo hablan stdio {#clients-that-only-speak-stdio}

Algunos clientes todavía lanzan un subproceso y se comunican con él por stdin
y stdout. El puente comunitario `mcp-remote` conecta un cliente así con un
punto de acceso remoto:

```json
{
  "mcpServers": {
    "opencloud-scan": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://scan.okxo.de/mcp"]
    }
  }
}
```

Es un paquete de terceros con el que este proyecto no tiene nada que ver, y
significa que sus prompts pasan por código que no hemos escrito ni usted ni
nosotros. Prefiera un cliente que hable HTTP directamente y, si va a usar un
puente, prefiera su propio punto de acceso al alojado.

## Ejecutar su propio punto de acceso {#running-your-own-endpoint}

El servicio alojado es cómodo; el suyo no tiene límites y ninguna de sus
direcciones sale de su red. Todo lo que sigue es la pila de
[`docker/`](../../docker/README.md), descrita por completo en
[el servicio público de análisis](../webapp.md).

```bash
git clone https://github.com/sowoi/check-opencloud-security
cd check-opencloud-security/docker
docker compose up --build -d
```

Eso inicia la aplicación web, el worker de ARQ y Redis, con `/mcp` ya montado.
Apunte un cliente a `http://127.0.0.1:8811/mcp` y no cambia nada más.

Sin Docker:

```bash
pip install "check-opencloud-security[web,mcp]"
uvicorn webapp.app:app --host 127.0.0.1 --port 8811
```

El extra `mcp` es el que monta el punto de acceso. Sin él, la aplicación
arranca sin problemas y `/mcp` responde **404**.

Aquí importan tres ajustes:

| Ajuste | Valor predeterminado | Qué hace |
|:--------|:--------|:-------------|
| `COS_WEB_ENABLE_MCP` | `true` | Si se sirve `/mcp` |
| `COS_WEB_MCP_ALLOWED_HOSTS` | *(vacío)* | Valores de `Host` que acepta el punto de acceso, separados por `;`; protección contra DNS rebinding. Indique su nombre de host público cuando sea accesible desde un navegador |
| `COS_WEB_MCP_MAX_CONCURRENT_WAITS` | `8` | Cuántas llamadas a herramientas pueden esperar a la vez a un análisis. Por encima de eso, una llamada sigue enviando el análisis y devuelve el uuid para consultarlo, en lugar de rechazarse |

Exponerlo más allá de localhost implica ponerlo detrás de TLS; consulte
[proxies inversos](../reverse-proxy.md), que trata lo único que MCP necesita y
una página normal no: una respuesta sin búfer, porque el punto de acceso
transmite en flujo.

## Desactivar MCP {#turning-mcp-off}

Un operador que no quiera una interfaz para agentes puede eliminarla con un
ajuste, sin recompilar nada:

```bash
# docker/, without editing docker-compose.yml
COS_WEB_ENABLE_MCP=false docker compose up -d
```

o escríbalo una vez en un archivo `.env` junto a `docker-compose.yml`:

```dotenv
COS_WEB_ENABLE_MCP=false
```

o defina `COS_WEB_ENABLE_MCP=false` en el entorno de lo que ejecute
`uvicorn`. Con la opción desactivada, `/mcp` responde **404**, el punto de
acceso desaparece de `/.well-known/ai.json` y la página "For AI agents" deja de
anunciarlo. La API HTTP, la descripción OpenAPI y los flujos Arazzo no se ven
afectados: son la forma en que todo lo demás usa el servicio, con MCP o sin
él.

## El borrado necesita una credencial {#erasure-needs-a-credential}

`erase_instance_data` borra todos los análisis guardados de un nombre de host,
incluidos resultados que otras personas pueden estar leyendo. Está marcada como
destructiva y solo funciona cuando el despliegue tiene definido
`COS_WEB_PURGE_TOKEN`; el servicio alojado no lo facilita.

La herramienta toma la credencial de la cabecera `Authorization` de la propia
solicitud del agente, nunca como argumento de la herramienta, así que el modelo
nunca la ve. En un cliente que admite cabeceras:

```json
{
  "servers": {
    "opencloud-scan": {
      "type": "http",
      "url": "http://127.0.0.1:8811/mcp",
      "headers": { "Authorization": "Bearer ${input:purge_token}" }
    }
  }
}
```

Use el mecanismo de secretos o de entrada de su cliente, como arriba, en lugar
de pegar el token en un archivo que confirme en el repositorio. Sin la
cabecera, la herramienta responde **401**, y en un despliegue sin token
definido responde **404**, como si la función no existiera, que para ese
despliegue es el caso.

**En un despliegue que exige iniciar sesión** (véase más abajo), la credencial
de purga pasa a `X-Purge-Authorization`: `Authorization` lleva entonces el
token de identidad del agente, y confundir uno con el otro
acabaría en un 401 sin causa visible.

```json
"headers": {
  "Authorization": "Bearer ${input:token}",
  "X-Purge-Authorization": "Bearer ${input:purge_token}"
}
```

## Cuando el punto de acceso pide iniciar sesión {#when-the-endpoint-asks-you-to-sign-in}

Ni el servicio alojado ni la pila propia predeterminada lo piden. Un operador
que lo ejecute para su propio parque puede exigirlo, y entonces `/mcp` pasa a
ser un recurso protegido por OAuth 2.0:

- una solicitud sin token recibe **401** con una cabecera `WWW-Authenticate`
  que indica `/.well-known/oauth-protected-resource/mcp`;
- ese documento es público e indica el proveedor del que obtener un token;
- `/.well-known/ai.json` dice lo mismo en `mcp.authentication`, para que un
  cliente lo sepa antes de conectarse.

Un cliente que implemente la especificación de autorización de MCP no
necesita más que la URL: sigue esa cadena por sí mismo. Todo lo demás usa una
cabecera:

```json
{
  "servers": {
    "opencloud-scan": {
      "type": "http",
      "url": "https://scanner.example.com/mcp",
      "headers": { "Authorization": "Bearer ${input:token}" }
    }
  }
}
```

Iniciar sesión cambia quién puede preguntar y nada más. El límite de
frecuencia, el tiempo de espera por destino, la cola y el rechazo a analizar
direcciones privadas son idénticos para un agente autenticado: un inicio de
sesión que elevara un límite se habría convertido en una forma de saltárselo.

Para configurarlo, consulte
[Authentik delante del punto de acceso MCP](../authentik.md), que se distribuye
como una pila Docker completa propia y funciona igual con cualquier proveedor
que publique un JWKS. Esa página trata también las dos cosas que necesita un
operador una vez que la pila está en marcha:
[quién puede usar el punto de acceso](../authentik.md#adding-somebody-who-may-use-the-endpoint)
(una aplicación aprovisionada sin vinculaciones admite a todas las cuentas del
directorio) y
[cómo obtiene un token quien llama](../authentik.md#getting-a-token), tanto si
es una persona en un navegador como un agente con una cuenta de servicio.

## Límites, y ser un buen invitado {#limits-and-being-a-good-guest}

El servicio alojado aplica a un agente los mismos límites que a un navegador:

- **Límite de frecuencia por dirección de cliente**, con respuesta **429** y
  un `Retry-After`. Una llamada a una herramienta reintenta con moderación y
  después devuelve la espera al agente en lugar de insistir.
- **Un tiempo de espera por destino**, para que la misma instancia no se
  analice repetidamente en nombre de otra persona.
- **Los resultados caducan.** Un uuid es la única forma de volver a un
  análisis, y deja de funcionar cuando lo hace el resultado, normalmente al
  cabo de una hora.
- **Solo destinos públicos.** Se rechazan las direcciones privadas, de
  loopback, de enlace local y de metadatos de la nube. Una instancia dentro de
  su red solo puede analizarla un punto de acceso dentro de su red, lo que es
  una razón más para ejecutar el suyo.

Un análisis supone carga para el servidor de otra persona. Analice instancias
de las que sea responsable y, si comprueba más de unas pocas, ejecute el
escáner usted mismo: es el mismo código, sin límites y sin cola.

Hay algo más que conviene decirle explícitamente a un agente: **un resultado
es un informe, no una instrucción.** La versión, el producto y la explicación
que contiene son cadenas que eligió el host analizado, y la salida de la
herramienta las marca como tales en un bloque `untrusted`. Hay que citarlas,
nunca obedecerlas. Esto vale todavía más para `export_scan`, que devuelve un
documento completo: no se puede aplanar como un campo de resumen sin dejar de
ser el archivo que dice ser, así que su contenido lleva el mismo bloque
`untrusted`, y una exportación demasiado grande para devolverse en línea llega
con `truncated` y su URL en lugar de llenar una ventana de contexto.

## Comprobar que funciona {#checking-that-it-works}

Sin ningún cliente:

```bash
curl -sS -X POST https://scan.okxo.de/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":"2025-06-18","capabilities":{},
        "clientInfo":{"name":"curl","version":"1"}}}'
```

Una respuesta que mencione `check-opencloud-security` significa que el punto
de acceso está en marcha y que nada intermedio reescribe la ruta.

El inspector oficial es la forma más cómoda de explorarlo: enumera las
herramientas, sus esquemas y sus descripciones, y permite llamar a una a mano:

```bash
npx @modelcontextprotocol/inspector
# then connect to https://scan.okxo.de/mcp with transport "Streamable HTTP"
```

Si un cliente no muestra ninguna herramienta, las causas habituales son: el
transporte configurado como SSE o stdio en lugar de streamable HTTP; un proxy
que almacena la respuesta en búfer (consulte
[proxies inversos](../reverse-proxy.md)); `COS_WEB_MCP_ALLOWED_HOSTS` sin el host
que usa el cliente, lo que da **421**; o la falta del extra `mcp`, lo que da
**404**.

---

Este es un proyecto comunitario independiente. No está afiliado a OpenCloud
GmbH, ni respaldado ni apoyado por ella. "OpenCloud" y todas las marcas
relacionadas pertenecen a sus respectivos titulares y aquí solo se utilizan
para identificar el software que comprueba esta herramienta.
