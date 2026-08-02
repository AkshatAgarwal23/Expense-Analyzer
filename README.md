# Expense Analyzer

Voice-first expense tracker with split/settle-up.

## Prerequisites

- Python 3.11+
- PostgreSQL 16 (Docker Compose or native)
- For voice extract fallback: [Ollama](https://ollama.com) locally (optional if regex finds the amount)
- For voice transcribe: a [Sarvam](https://sarvam.ai) API key (`SARVAM_API_KEY` in `.env`)

## Setup

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -e ".[dev]"
copy .env.example .env   # or: cp .env.example .env
# Put SARVAM_API_KEY in .env (never commit the real key)
```

```bash
alembic upgrade head
python -m scripts.seed
.\start.ps1
```

## Identity

Send `X-User-Id: <seeded user id>` on every protected request. Seed prints IDs (Akshat=1, Rahul=2, Priya=3 after a fresh seed).

## API surface

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/me` | Current user (`display_name`, email) via `X-User-Id` |
| GET | `/health` | Liveness |
| POST/GET | `/expenses` | Create (equal/exact/percentage) and list |
| POST/GET | `/friendships` | Request friendship; list |
| POST | `/friendships/{id}/accept` | Accept (non-requester only) |
| GET | `/balances` | Derived nets vs accepted friends |
| POST | `/settlements` | Append-only settlement |
| GET | `/categories` | Global + your categories |
| GET | `/analytics/spend-by-category` | Personal spend totals by category |
| POST | `/voice/transcribe` | Multipart audio → transcript (**Sarvam** STT) |
| POST | `/voice/extract` | Transcript → editable draft (regex + optional Ollama; no DB write) |
| POST | `/voice/confirm` | Confirmed `ExpenseCreate` → ledger via `create_expense` (`source=voice`) |

Money is always integer **paise**. Positive `net_paise` means they owe you.

### App UI (Kharcha)

- Dashboard: http://127.0.0.1:8001/  
- Friends / settle: http://127.0.0.1:8001/static/kharcha-friends.html  
- Voice entry (record → draft → confirm): http://127.0.0.1:8001/static/kharcha-voice-record.html  
- Confirm draft: http://127.0.0.1:8001/static/kharcha-confirm.html  
- PWA manifest: `/static/manifest.webmanifest` (installable from the browser)  

### Voice / Sarvam

- Endpoint: `https://api.sarvam.ai/speech-to-text`
- Default model `saaras:v3`, mode **`translit`** (romanized Hinglish) so amount/friend regex works
- Set `SARVAM_MODE=codemix` if you prefer mixed Devanagari + English

Demo UI: http://127.0.0.1:8001/

### Voice curl (skip mic)

```bash
curl -X POST http://127.0.0.1:8001/voice/extract ^
  -H "X-User-Id: 1" -H "Content-Type: application/json" ^
  -d "{\"transcript\":\"400 ka dinner, Rahul ke saath split\"}"
```

## Tests

```bash
pytest
```

Unit/service tests mock Sarvam/Ollama and do not call real APIs.
