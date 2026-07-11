# Creator Content Workspace

This repository contains the original single-file creator-content prototype and the initial frontend/backend migration shell.

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

Run the FastAPI backend at the same time to use workspace creation, account
positioning, text source materials, and trend CSV uploads. Vite proxies `/api`
requests to `http://127.0.0.1:8000`.

Checks:

```bash
npm run lint
npm run test
npm run build
```

## Backend health endpoint

Requirements: Python 3.11 or newer.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[dev]'
uvicorn app.main:app --reload
```

Open `http://localhost:8000/api/health` or `http://localhost:8000/docs`.

Checks:

```bash
ruff check .
python -m pytest
```

## Current scope

The React and FastAPI applications currently implement the first workspace
persistence slice: workspace selection, account positioning, historical-post
and comment text, and trend CSV upload/preview. Diagnosis, topic generation,
content generation, audience simulation execution, LangGraph, deployment
infrastructure, and authentication are intentionally not implemented yet.
