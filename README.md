# *Read it and Weep*

For full architecture details, see `ARCHITECTURE.md`.

## Local Development

Requirements:
- Node.js 20+
- `uv` (for Python Workers tooling)

Run locally:
```bash
npm install
npm run dev:local
```

## Deploy

Will redeploy on git commit landing to main...

IF CHANGING DB: Apply migrations (remote):
```bash
npx wrangler d1 migrations apply readnweep-db --remote
```

SHOULDNT NEED TO RUN: Deploy the Worker:
```bash
uv run pywrangler deploy
```
