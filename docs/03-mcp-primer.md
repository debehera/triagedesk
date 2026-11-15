# 03 - MCP Primer for Beginners

You are new to MCP, so this is a short, practical guide. Do the hands-on part (section 5) on Day 1-2 before writing the real servers.

## 1. What MCP is

The **Model Context Protocol (MCP)** is an open standard for connecting AI applications to tools and data. Instead of every app inventing its own way to give a model a "search" or "database" tool, an MCP **server** exposes capabilities in a standard format, and any MCP **client** can discover and use them.

Analogy: MCP is to AI tools what USB is to peripherals. Write the tool once as a server, and Claude Code, VS Code, or your own Python app can all plug into it.

## 2. The three roles

| Role | What it is | In this project |
|------|-----------|-----------------|
| **Host** | The application the user interacts with, which contains the model | Your TriageDesk CLI; also Claude Code and VS Code when you test servers |
| **Client** | The connector inside the host that talks to one server | `src/mcp_client.py` using the Python SDK |
| **Server** | A program that exposes tools/resources/prompts | `itsm_server.py`, `directory_server.py` |

## 3. What a server can expose

| Primitive | Meaning | Controlled by | Example here |
|-----------|---------|---------------|--------------|
| **Tools** | Functions the model can call (may have side effects) | The model decides | `search_kb`, `update_ticket` |
| **Resources** | Read-only data the app can load as context | The application | KB article text |
| **Prompts** | Reusable prompt templates | The user | "Triage this ticket" |

For this capstone, **tools** are the main focus. Resources are an optional extra.

## 4. How it works (the mental model)

1. The client starts the server (for local servers, as a subprocess) and talks to it over **stdio** (standard input/output). Messages are JSON-RPC.
2. Handshake: client calls `initialize`, server replies with its capabilities.
3. Client calls `tools/list`. The server returns each tool's **name, description and input schema**.
4. Your app passes these tool definitions to Claude in the API request.
5. Claude replies with a `tool_use` block ("call `search_kb` with `{...}`").
6. Your app forwards that to the server with `tools/call`, gets the result, and sends it back to Claude as a `tool_result`.
7. Repeat until Claude stops with `end_turn`.

Important: **the model never talks to the MCP server directly.** Your application sits in the middle, which is exactly where guardrails, logging and argument validation go.

```text
Claude API  <---tool_use / tool_result--->  Your app (host + MCP client)  <---stdio / JSON-RPC--->  MCP server
```

Key stdio rule: a stdio server must **never print to stdout** except protocol messages. Use `stderr` or logging for debug output, or you will corrupt the protocol stream.

## 5. Hands-on exercise (30-45 minutes)

Setup (from the repo root):

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# macOS / Linux:       source .venv/bin/activate
pip install -r requirements.txt
```

### Step A - Read the hello server

Open `mcp_servers/hello_server.py`. It defines three tools (`add`, `get_greeting`, `lookup_ticket_status`) using the SDK's `FastMCP` helper. The function's type hints become the input schema, and its docstring becomes the tool description. That is the whole trick.

### Step B - Inspect it with the MCP Inspector

```bash
mcp dev mcp_servers/hello_server.py
```

This opens a browser-based inspector (it needs Node.js installed). Click **Tools**, then **List tools**, and call `add` with `a=2, b=3`. Watch the request and response JSON. If you cannot install Node.js, skip to Step C.

### Step C - Call it from Python

```bash
python mcp_servers/hello_client.py
```

The client starts the server, lists the tools, and calls two of them. This is the same pattern `src/mcp_client.py` will use.

### Step D - Plug it into Claude Code

From the repo root:

```bash
claude mcp add hello -- python mcp_servers/hello_server.py
claude mcp list
```

Then in Claude Code ask: "Use the hello server to add 40 and 2." Remove it afterwards with `claude mcp remove hello`. For a project-shared setup, a `.mcp.json` file at the repo root is the usual mechanism (we will add it on Day 5 for the real servers).

### Step E - VS Code (optional)

Recent VS Code versions can use MCP servers with GitHub Copilot chat through a `.vscode/mcp.json` file. Since this varies by version, check the current VS Code MCP documentation if you want to try it; it is not required for the capstone. Your servers and tests do not depend on VS Code.

## 6. Designing good tools (exam-relevant)

1. **One clear job per tool.** `get_user` and `check_access` are separate.
2. **Descriptions are prompts.** State what it does, when to use it, when *not* to, the input format and what comes back. Vague descriptions cause wrong tool choices.
3. **Strict input schemas.** Use enums for fixed values (e.g. ticket status), validate everything server-side.
4. **Structured errors.** Return `{"ok": false, "error": {"code", "message", "retryable"}}` instead of raising, so the agent can decide whether to retry.
5. **Least privilege.** Tools expose the minimum needed; read tools and write tools are separate; no "run any query" tool.
6. **Idempotent where possible.** `update_ticket` with the same arguments twice should be safe.
7. **Compact results.** Return only fields the agent needs; large payloads burn tokens.

## 7. Common beginner mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| `print()` in a stdio server | Client hangs or parse errors | Log to stderr |
| Wrong Python on the client side | Server fails to start | Use `sys.executable` as the command |
| Vague tool description | Model picks the wrong tool | Rewrite it as if briefing a new colleague |
| Returning huge JSON | Slow and expensive | Trim fields, limit results |
| Raising raw exceptions | Agent sees a confusing failure | Catch and return the error contract |
| Forgetting to run `await session.initialize()` | Calls fail | Initialize first |

## 8. Glossary

- **JSON-RPC:** simple request/response message format MCP uses.
- **stdio transport:** server runs as a child process, messages go over stdin/stdout.
- **Tool schema:** JSON Schema describing a tool's inputs.
- **Capability:** what a server says it supports (tools, resources, prompts).
- **Inspector:** developer tool for testing servers interactively.

## 9. Further reading

Check the official MCP documentation (modelcontextprotocol.io) and the Anthropic documentation on tool use for the current API details, because SDK interfaces evolve.
