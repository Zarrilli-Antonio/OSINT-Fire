# OSINT-Fire

![License: MIT](https://img.shields.io/badge/license-MIT-green)

Automated OSINT collection and correlation on public sources. MIT licensed, no API keys needed. Maigret is installed with the backend dependencies.

## Run (dev)
```bash
# backend
cd backend && uv run uvicorn osint.main:app --port 8765
# app
cd app && flutter run -d macos
```
Design and decisions: [DESIGN.md](DESIGN.md). Tests: `cd backend && uv run pytest`.

## Build the app
```bash
./scripts/build_app.sh   # -> dist/OSINT-Fire.app (Flutter UI + frozen Python backend, ~215 MB)
```
The packaged app starts its own backend and stores data in `~/Library/Application Support/OSINT-Fire/osint.db`.
To bring over searches made while developing: `cp backend/osint.db ~/Library/Application\ Support/OSINT-Fire/osint.db` (app closed).

## Searches are saved as you left them
Each investigation stores its definition (seeds, depth, the entities you expanded by hand) and its layout (node positions, pins, camera, hidden types).
Opening it restores both; **AGGIORNA** re-runs the whole search ignoring the cache and flags what is new.

## Settings
The gear icon opens the settings: collector on/off, passive-only mode, cache lifetime, proxy, optional API keys, AI connector and data
maintenance (cache, backup, wipe). Settings and keys are stored locally in `backend/osint.db`.

## AI
- **In-app analyst**: summary, review, "what to search next" and report, using Anthropic or any OpenAI-compatible endpoint (including a local Ollama).
- **MCP server** for Claude Desktop and other agents (the app must be open):
  `uv run --directory backend --extra mcp python -m osint.mcp_server`. The exact config block is in Settings → AI.

## License
[MIT](LICENSE) © 2026 Antonio Zarrilli. Third-party components and their licenses: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

OSINT-Fire only queries public sources and official APIs. You are responsible for using it lawfully (GDPR for personal data, the terms of each service).
