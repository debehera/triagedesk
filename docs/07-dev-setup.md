# 07 - Developer Setup (VS Code, Python, Git)

## 1. Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.11 or newer | `python --version` |
| Git | any recent | `git --version` |
| VS Code | recent | already installed |
| Node.js | 18+ (only for the MCP Inspector) | `node --version` |
| Claude Code CLI | recent (optional but recommended for the capstone) | `claude --version` |
| Anthropic API key | from the Anthropic Console | see section 4 |

## 2. VS Code

Recommended extensions:
- **Python** (Microsoft) and **Pylance**
- **Ruff** (lint and format)
- **GitLens** (optional)
- **Mermaid Preview** or a Markdown extension that renders Mermaid (to view the architecture diagram)

Select the interpreter: `Ctrl+Shift+P` -> *Python: Select Interpreter* -> choose `.venv`.

The repo includes `.vscode/settings.json` with sensible defaults (pytest enabled, Ruff as formatter).

## 3. Virtual environment

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# Windows cmd:         .venv\Scripts\activate.bat
# macOS / Linux:       source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## 4. API key and environment

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

Edit `.env` and set `ANTHROPIC_API_KEY`. `.env` is git-ignored. **Never commit a key.** If you ever do, revoke it immediately in the Console and create a new one.

Set a spending limit in the Anthropic Console for development.

## 5. Git workflow

You already have a repo. Add the scaffold on a branch:

```bash
git checkout -b day-01-scaffold
git add .
git commit -m "docs: add scope, requirements, architecture, ADRs, eval plan (Day 1)"
git push -u origin day-01-scaffold
```

Conventions:
- Branches: `day-NN-topic` or `feat/<topic>`; merge to `main` through short-lived branches.
- Commits: Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`), referencing requirement IDs where relevant, e.g. `feat(guardrails): enforce G2 restricted access (FR-41)`.
- Commit small and often; a visible history of steady progress is part of the portfolio.
- Tag milestones: `v0.1-scope`, `v0.5-core-loop`, `v1.0`.

## 6. Verify the setup

```bash
python -c "import anthropic, mcp, pydantic; print('imports ok')"
pytest -q            # should report no tests collected or pass
ruff check .         # should pass
python mcp_servers/hello_client.py
```

## 7. Running things (will grow as the project does)

| Task | Command |
|------|---------|
| Hello MCP server in the Inspector | `mcp dev mcp_servers/hello_server.py` |
| Hello client | `python mcp_servers/hello_client.py` |
| Unit tests | `pytest -q` |
| Lint | `ruff check .` and `ruff format .` |
| Triage one ticket (Day 6+) | `python -m src.cli path/to/ticket.json` |
| Run evals (Day 10+) | `python evals/run_evals.py` |

## 8. Troubleshooting

| Problem | Likely cause | Fix |
|---------|--------------|-----|
| `ModuleNotFoundError: mcp` | venv not active or deps not installed | Activate `.venv`, `pip install -r requirements.txt` |
| `mcp dev` fails | Node.js missing | Install Node.js, or use `hello_client.py` instead |
| Client hangs when starting a server | Server printed to stdout | Remove prints; use stderr |
| `AuthenticationError` | Missing/invalid key | Check `.env`, reload the terminal |
| 429 / overloaded errors | Rate limits | Backoff and retry; reduce parallelism |
| VS Code uses the wrong Python | Interpreter not selected | Select `.venv` interpreter |
| `No module named 'mcp.server.fastmcp'` | mcp 2.x installed (FastMCP was renamed) | `pip install "mcp[cli]<2"`; requirements.txt already pins this |

## 9. Windows notes (added Day 2)

- Activate the venv with `.venv\Scripts\Activate.ps1`; if PowerShell blocks it, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.
- Copy the env file with `Copy-Item .env.example .env`; never commit `.env`.
- Line endings are LF (`.gitattributes`); if Git warns about CRLF, run `git add --renormalize .`.
- More PowerShell equivalents and the Docker Desktop caveat: Blueprint Appendix I.
