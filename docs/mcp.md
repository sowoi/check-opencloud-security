# Using the scanner from an AI agent (MCP)

The web application in this repository speaks the
[Model Context Protocol](https://modelcontextprotocol.io) at `/mcp`, so an
agent can scan an OpenCloud instance as a tool call rather than by being
taught an HTTP API.

Two addresses work:

| | Endpoint | Good for |
|:--|:---------|:---------|
| **Hosted** | `https://scan.okxo.de/mcp` | Trying it out, and the occasional instance. Rate limited, and every scan runs from that server |
| **Self-hosted** | `http://127.0.0.1:8811/mcp` | An estate of your own, no limits, and nothing about your instances leaving your network |

Nothing is required to use either one: no account, no API key, no sign-up.
The one exception is `erase_instance_data`, which needs a credential the
operator of the deployment sets - see [Erasure needs a
credential](#erasure-needs-a-credential).

<!-- TOC -->
* [Using the scanner from an AI agent (MCP)](#using-the-scanner-from-an-ai-agent-mcp)
  * [What the agent gets](#what-the-agent-gets)
  * [Claude Code](#claude-code)
  * [Claude Desktop](#claude-desktop)
  * [GitHub Copilot in VS Code](#github-copilot-in-vs-code)
  * [GitHub Copilot CLI](#github-copilot-cli)
  * [Cursor](#cursor)
  * [Zed](#zed)
  * [Windsurf](#windsurf)
  * [Any other client](#any-other-client)
  * [Clients that only speak stdio](#clients-that-only-speak-stdio)
  * [Running your own endpoint](#running-your-own-endpoint)
  * [Turning MCP off](#turning-mcp-off)
  * [Erasure needs a credential](#erasure-needs-a-credential)
  * [When the endpoint asks you to sign in](#when-the-endpoint-asks-you-to-sign-in)
  * [Limits, and being a good guest](#limits-and-being-a-good-guest)
  * [Checking that it works](#checking-that-it-works)
<!-- TOC -->

## What the agent gets

Six tools, each a whole task rather than one HTTP endpoint:

| Tool | What it does |
|:-----|:-------------|
| `scan_instance` | Submit one instance, wait for the scan, return the grade and the findings. Reporting progress while it waits |
| `scan_instances` | The same for a list of instances, in one batch |
| `get_scan_result` | Read a scan by its uuid without waiting - what an agent polls with |
| `plan_remediation` | The ordered fix list for a finished scan, with the grade each step reaches |
| `export_scan` | A finished scan as `json`, `csv`, `sarif` or `pdf` |
| `erase_instance_data` | **Destructive.** Erase everything held about one hostname. Needs the operator's credential |

and three resources, so an agent can read the contracts without leaving the
protocol: the OpenAPI description, the Arazzo workflows and the discovery
document.

Six prompts as well - the tasks people actually ask for, written out once so
every client sends the same well-formed request:

| Prompt | What it asks for | Arguments |
|:-------|:-----------------|:----------|
| `audit_instance` | Scan one instance, explain the grade and write the remediation plan | `target_url`, optionally `release_track` |
| `audit_estate` | Scan a list of instances and rank them worst first | `targets`, optionally `release_track` |
| `explain_scan_result` | Explain a finished scan to a named audience, without rescanning | `uuid`, optionally `audience` |
| `triage_findings` | Turn a finished scan into one ticket per step of the plan | `uuid`, optionally `tracker` |
| `review_transport_security` | The certificate, its expiry, the chain and the protocol, on their own | `target_url` |
| `check_release_support` | Whether the release still gets security fixes, and what to upgrade to | `target_url`, optionally `release_track` |

In a client that lists them, "Audit an instance and write a remediation plan"
is one entry to pick - Claude Code offers them as slash commands, VS Code
under `/mcp.opencloud-scan.`, and most others in an attachment or prompt menu.
Picking one asks for the arguments and sends the request; the agent then makes
the tool calls itself.

"Scan opencloud.example.com" is one tool call. The submission, the waiting and
the result are inside `scan_instance`; an agent does not have to orchestrate
them.

## Claude Code

```bash
# Hosted
claude mcp add --transport http opencloud-scan https://scan.okxo.de/mcp

# Your own
claude mcp add --transport http opencloud-scan http://127.0.0.1:8811/mcp
```

Add `--scope user` to have it available in every project rather than the
current one. Then, in a session:

```text
> scan opencloud.example.com and tell me what would improve the grade
```

`claude mcp list` shows whether the connection came up, and `/mcp` inside a
session lists the tools that were discovered.

## Claude Desktop

Claude Desktop reads `claude_desktop_config.json`:

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

Restart the application afterwards. Builds that cannot reach a remote server
directly can use the bridge in [Clients that only speak
stdio](#clients-that-only-speak-stdio).

## GitHub Copilot in VS Code

VS Code is the odd one out: the top-level key is `servers`, not `mcpServers`.
Put this in `.vscode/mcp.json` for one workspace, or run **MCP: Open User
Configuration** from the command palette for all of them:

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

Then open Copilot Chat in **Agent** mode; the tools appear in the tool picker.
`MCP: List Servers` shows the connection and its log if it does not.

## GitHub Copilot CLI

Copilot CLI merges configuration from `~/.copilot/mcp-config.json` (global) and
`.github/mcp.json` or `.mcp.json` in the working directory:

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

`/mcp` inside a session lists what was loaded.

## Cursor

`.cursor/mcp.json` in a project, or `~/.cursor/mcp.json` globally:

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

Settings → MCP shows the server and lets you toggle individual tools.

## Zed

`settings.json` (**Zed: Open Settings**), under `context_servers`:

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

Recent Zed versions also accept an `.mcp.json` with the usual `mcpServers`
key.

## Windsurf

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

## Any other client

The endpoint is ordinary **streamable HTTP** MCP: one URL, `POST` for
requests, no session to keep alive, no authentication. Anything that can be
told a URL will work with

```json
{"type": "http", "url": "https://scan.okxo.de/mcp"}
```

or the same URL typed into a settings dialogue. If a client asks which
transport, the answer is *streamable HTTP* (sometimes called "HTTP" or
"remote"), not SSE and not stdio.

An agent that has never heard of this service can find the endpoint itself:
`https://scan.okxo.de/.well-known/ai.json` names it, alongside the OpenAPI and
Arazzo documents. That is the whole point of the discovery document - see
[the page for agents](https://scan.okxo.de/ai).

## Clients that only speak stdio

Some clients still launch a subprocess and talk to it over stdin and stdout.
The community bridge `mcp-remote` connects such a client to a remote endpoint:

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

That is a third-party package this project has nothing to do with, and it
means your prompts pass through code neither of us wrote. Prefer a client that
can speak HTTP directly, and prefer your own endpoint over the hosted one if
you are going to bridge at all.

## Running your own endpoint

The hosted service is convenient; your own is unlimited, and no address of
yours leaves your network. Everything below is the stack from
[`docker/`](../docker/README.md), described in full in [the public scan
service](webapp.md).

```bash
git clone https://github.com/sowoi/check-opencloud-security
cd check-opencloud-security/docker
docker compose up --build -d
```

That brings up the web application, the ARQ worker and Redis, with `/mcp`
already mounted. Point a client at `http://127.0.0.1:8811/mcp` and nothing
else changes.

Without Docker:

```bash
pip install "check-opencloud-security[web,mcp]"
uvicorn webapp.app:app --host 127.0.0.1 --port 8811
```

The `mcp` extra is what mounts the endpoint. Without it the application starts
perfectly well and `/mcp` answers **404**.

Three settings are worth knowing:

| Setting | Default | What it does |
|:--------|:--------|:-------------|
| `COS_WEB_ENABLE_MCP` | `true` | Serve `/mcp` at all |
| `COS_WEB_MCP_ALLOWED_HOSTS` | *(empty)* | `Host` values the endpoint accepts, separated by `;` - DNS-rebinding protection. Name your public hostname when it is reachable from a browser |
| `COS_WEB_MCP_MAX_CONCURRENT_WAITS` | `8` | How many tool calls may wait on a scan at once. Past that a call still submits the scan and returns the uuid to poll, rather than being refused |

Exposing it beyond localhost means putting it behind TLS: see [reverse
proxies](reverse-proxy.md), which covers the one thing MCP needs that a normal
page does not - an unbuffered response, because the endpoint streams.

## Turning MCP off

An operator who does not want an agent interface can remove it. It is a
setting, not a build:

```bash
# docker/, without editing docker-compose.yml
COS_WEB_ENABLE_MCP=false docker compose up -d
```

or write it once in a `.env` file next to `docker-compose.yml`:

```dotenv
COS_WEB_ENABLE_MCP=false
```

or set `COS_WEB_ENABLE_MCP=false` in the environment of whatever runs
`uvicorn`. With it off, `/mcp` answers **404**, the endpoint disappears from
`/.well-known/ai.json` and the "For AI agents" page stops advertising it. The
HTTP API, the OpenAPI description and the Arazzo workflows are unaffected -
they are how everything else uses the service, MCP or no MCP.

## Erasure needs a credential

`erase_instance_data` deletes every stored scan of one hostname, including
results other people may be reading. It is marked destructive, and it only
works when the deployment has `COS_WEB_PURGE_TOKEN` set - the hosted service
does not hand that out.

The tool takes the credential from the `Authorization` header of the agent's
own request, never as a tool argument, so the model never sees it. In a client
that supports headers:

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

Use your client's secret or input mechanism, as above, rather than pasting the
token into a file you commit. Without the header the tool answers **401**, and
on a deployment with no token set it answers **404** - as though the feature
were not there, which for that deployment it is not.

**On a deployment that requires a sign-in** (below), the purge credential
moves to `X-Purge-Authorization`: `Authorization` then carries the agent's
identity token, and reading one as the other would compare a credential
against a credential and answer 401 for a reason nobody could see.

```json
"headers": {
  "Authorization": "Bearer ${input:token}",
  "X-Purge-Authorization": "Bearer ${input:purge_token}"
}
```

## When the endpoint asks you to sign in

Neither the hosted service nor the default self-hosted stack does. An operator
running this for their own estate can, and then `/mcp` becomes an OAuth 2.0
protected resource:

- a request without a token gets **401** with a `WWW-Authenticate` header
  naming `/.well-known/oauth-protected-resource/mcp`;
- that document is public, and names the provider to get a token from;
- `/.well-known/ai.json` says the same under `mcp.authentication`, so a client
  can know before it connects.

A client that implements the MCP authorization specification needs nothing but
the URL - it follows that chain itself. Everything else takes a header:

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

Signing in changes who may ask and nothing else. The rate limit, the target
cooldown, the queue and the refusal to scan a private address are identical
for an authenticated agent - a sign-in that raised a limit would have turned
itself into a way around it.

Setting one up is [Authentik in front of the MCP
endpoint](authentik.md), which ships as a complete Docker stack of its own and
works the same way with any provider that publishes a JWKS. That page also
covers the two things an operator needs after the stack is up: [who may use
the endpoint](authentik.md#adding-somebody-who-may-use-the-endpoint) - a
provisioned application with no bindings admits every account in the directory
- and [how a caller gets a token](authentik.md#getting-a-token), whether it is
a person in a browser or an agent with a service account.

## Limits, and being a good guest

The hosted service applies the same limits to an agent as to a browser:

- **Rate limit per client address**, answered with **429** and a
  `Retry-After`. A tool call retries politely and then hands the wait back to
  the agent rather than hammering.
- **A cooldown per target**, so the same instance is not scanned repeatedly on
  somebody else's behalf.
- **Results expire.** A uuid is the only way back to a scan, and it stops
  working when the result does - typically an hour.
- **Public targets only.** Private, loopback, link-local and cloud metadata
  addresses are refused. An instance inside your network can only be scanned
  by an endpoint inside your network, which is the better reason to run your
  own.

A scan puts load on somebody else's server. Scan instances you are responsible
for, and if you are checking more than a handful, run the scanner yourself -
it is the same code, with no limits and no queue.

One more thing worth telling an agent explicitly: **a result is a report, not
an instruction.** The version, product and explanation in it are strings the
scanned host chose, and the tool output marks them as such in an `untrusted`
block. They are to be quoted, never obeyed. That goes double for
`export_scan`, which returns a whole rendered document: it cannot be flattened
the way a summary field is without ceasing to be the file it claims to be, so
its content carries the same `untrusted` block, and an export too large to
return inline comes back with `truncated` and its URL rather than filling a
context window.

## Checking that it works

Without any client at all:

```bash
curl -sS -X POST https://scan.okxo.de/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":"2025-06-18","capabilities":{},
        "clientInfo":{"name":"curl","version":"1"}}}'
```

An answer naming `check-opencloud-security` means the endpoint is up and the
path is not being rewritten by anything in between.

The official inspector is the friendlier way to look around - it lists the
tools, their schemas and their descriptions, and lets you call one by hand:

```bash
npx @modelcontextprotocol/inspector
# then connect to https://scan.okxo.de/mcp with transport "Streamable HTTP"
```

If a client shows no tools, the usual causes are: the transport set to SSE or
stdio instead of streamable HTTP; a proxy buffering the response (see [reverse
proxies](reverse-proxy.md)); `COS_WEB_MCP_ALLOWED_HOSTS` not naming the host
the client is using, which answers **421**; or the `mcp` extra missing, which
answers **404**.

---

This is an independent community project. It is not affiliated with, endorsed
by or supported by OpenCloud GmbH. "OpenCloud" and all related marks belong to
their respective owners and are used here only to identify the software this
tool checks.
