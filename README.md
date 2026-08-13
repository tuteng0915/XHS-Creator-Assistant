# Creator Content Workspace

This repository contains the original single-file creator-content prototype and the migrated creator workspace application.

## Open the original prototype

The original product prototype remains at [`index.html`](./index.html). It does not require a build step.

From the repository root, start a local static server:

```bash
python3 -m http.server 8000
```

Then open:

```text
http://localhost:8000/index.html
```

The prototype's demo mode works without external services. Its live mode is legacy reference behavior and requests an Anthropic API key in the browser; do not use a production or shared key there.

## Frontend workspace UI

Requirements: Node.js and npm.

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The frontend health page remains available at
`http://localhost:5173/health`.

Run the FastAPI backend at the same time. The frontend application calls the
backend through relative `/api/...` paths. In local development only, Vite
proxies those `/api` requests to `http://127.0.0.1:8000`.

For VPS sharing, serve the frontend and backend under the same public origin:

```text
https://your-domain/
https://your-domain/api/...
```

Do not expose a frontend build that still depends on a viewer's local
`localhost:8000`.

Checks:

```bash
npm run lint
npm run test
npm run build
```

## Backend health endpoint

Requirements: Python 3.11 or newer.

Local uploaded video preview extraction additionally requires `ffmpeg` on the
backend machine:

```bash
ffmpeg -version
```

If it is installed under a non-default path, set:

```bash
export FFMPEG_PATH=/absolute/path/to/ffmpeg
```

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[dev]'
uvicorn app.main:app --reload
```

Open `http://localhost:8000/api/health` or `http://localhost:8000/docs`.

Live generation uses the backend model proxy. Anthropic remains the default:

```bash
export MODEL_PROVIDER=anthropic
export ANTHROPIC_API_KEY=...
export ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

If you use Codex from an editor plugin and cannot inject shell environment
variables into this process, create a local env file at the repository root
or under `backend/`:

```text
.env.local
backend/.env.local
```

This file is ignored by git. Put local model credentials there using the same
`export KEY=value` format:

```bash
export MODEL_PROVIDER=anthropic
export ANTHROPIC_API_KEY=...
export ANTHROPIC_BASE_URL=https://your-qwen-host/apps/anthropic
export ANTHROPIC_MODEL=qwen-plus
```

The smoke script reads `.env.local` and then `backend/.env.local`
automatically:

```bash
backend/.venv/bin/python scripts/smoke_model_api.py
```

To use Qwen through DashScope's OpenAI-compatible API:

```bash
export MODEL_PROVIDER=qwen
export QWEN_API_KEY=...
export QWEN_MODEL=qwen-plus
# Optional; this is the default:
export QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

`DASHSCOPE_API_KEY` and `DASHSCOPE_BASE_URL` are also accepted aliases.

Some Qwen deployments also expose an Anthropic-compatible endpoint. Use it
through the same backend proxy by overriding the Anthropic endpoint:

```bash
export MODEL_PROVIDER=anthropic
export ANTHROPIC_API_KEY=...
export ANTHROPIC_MODEL=...
export ANTHROPIC_BASE_URL=https://your-qwen-host/apps/anthropic
# If the deployment requires an exact messages endpoint, use this instead:
export ANTHROPIC_MESSAGES_URL=https://your-qwen-host/apps/anthropic/v1/messages
```

For Qwen's Anthropic-compatible `/apps/anthropic` endpoint, the backend derives
`/apps/anthropic/v1/messages` automatically when `ANTHROPIC_MESSAGES_URL` is
not set.

Checks:

```bash
ruff check .
python -m pytest
```

## Current scope

The migrated app now includes creator content assets, capability assets,
workspace persistence, workflow execution, LangGraph-backed workflows, topic
and simulation history, batch account-profile import, batch workflow runs, and Qwen /
Anthropic backend model providers.

The app still intentionally does not include Docker, authentication,
multi-tenancy, Redis, Postgres, or deployment infrastructure.

See [`docs/status-and-todo.md`](./docs/status-and-todo.md) for the current
implementation summary and TODO list.
