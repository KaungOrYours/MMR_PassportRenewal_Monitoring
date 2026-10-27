# MMR Passport Renewal Monitoring System

Watches the Myanmar Embassy Singapore's passport-renewal approval list
(published weekly, usually Sundays) for specific names/passport numbers and
sends a Telegram alert the moment a match appears.

## How it works

```
GitHub Actions (every 3h, free)
   checker/main.py
     -> conditional GET the embassy PDF (ETag/Last-Modified; cheap when unchanged)
     -> extract text (pdftotext) or OCR (tesseract, for scanned PDFs)
     -> parse rows, anchored on passport/ID number, with an integrity check
        that re-OCRs any page where rows were silently dropped
     -> match against the watchlist (passport number + fuzzy name)
     -> write results to Neon Postgres
     -> send a Telegram alert

Vercel (frontend) <--API key--> Render (FastAPI backend) <--> Neon Postgres
```

Three independently deployed pieces, one repo:

- `checker/` -- the scraping/OCR/matching pipeline. Runs in GitHub Actions
  because OCR needs the `tesseract` + `poppler` system binaries, which Actions
  installs in seconds via `apt-get`; Render's free Python runtime can't
  without switching to Docker.
- `backend/` -- FastAPI REST API over the same Postgres database, deployed to
  Render. All routes except `/api/health` require an `X-API-Key` header.
- `frontend/` -- React + Vite + Tailwind GUI, deployed to Vercel. Four views:
  Watchlist, Alerts, Lists, Status.

## Setup

### 1. Telegram bot

Already created: `@MMR_PassportRenewalMonitoringBot`. **Revoke and regenerate
the bot token via @BotFather** before deploying -- the original token was
shared in plaintext during setup. Message the bot `/start` once to register
your chat; the chat ID is already captured as `REDACTED_OPERATOR_TELEGRAM_CHAT_ID`.

### 2. Database -- Neon Postgres

1. Create a free project at https://neon.tech
2. Copy the connection string (it should start with `postgresql://`)
3. That's the `NEON_DATABASE_URL` used below. Tables are created
   automatically on first run (`checker/db.py` calls `create_all`) -- no
   separate migration step for this schema's scope.

### 3. GitHub Actions secrets

In the repo's Settings -> Secrets and variables -> Actions, add:

- `NEON_DATABASE_URL`
- `TELEGRAM_BOT_TOKEN` (the regenerated token)
- `TELEGRAM_CHAT_ID` = `REDACTED_OPERATOR_TELEGRAM_CHAT_ID`

The workflow (`.github/workflows/check.yml`) runs every 3 hours and on
manual dispatch.

### 4. Backend -- Render

Uses `render.yaml` (Blueprint). In Render: New -> Blueprint -> point at this
repo. Set these env vars when prompted:

- `NEON_DATABASE_URL` -- same as above
- `API_SECRET` -- a long random string you generate (e.g. `openssl rand -hex 32`)
- `GH_DISPATCH_TOKEN` -- a GitHub personal access token (fine-grained,
  `Actions: write` on this repo only) so the GUI's "Check now" button can
  trigger the workflow
- `FRONTEND_ORIGIN` -- your Vercel URL, once you have it (comma-separate if
  more than one)

### 5. Frontend -- Vercel

Import the repo, set the project root to `frontend/`, and set env vars:

- `VITE_API_BASE` -- your Render backend URL
- `VITE_API_KEY` -- same value as `API_SECRET` above

**Note on the security model:** per your choice, there is no login -- the
site is protected only by the API key baked into the frontend bundle and by
the URL being unguessable ("secret URL"). Anyone who finds the Vercel URL can
read the page source and extract the API key. This is fine for a low-stakes
personal tool, but understand it is not a real access control: if you ever
want a password gate, say so and it can be added to the backend.

## Local development

```bash
# checker
cd checker && python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt
brew install poppler tesseract   # macOS, for extract/OCR
pytest tests/ -v

# backend
source .venv/bin/activate && pip install -r backend/requirements.txt
NEON_DATABASE_URL="sqlite:////tmp/dev.db" API_SECRET="dev" \
  uvicorn backend.main:app --reload

# frontend
cd frontend && npm install
cp .env.example .env.local   # fill in VITE_API_BASE / VITE_API_KEY
npm run dev
```

## Known data-format quirks (why the parser is written the way it is)

The embassy's PDF format is not consistent:

- Some weeks it's a text-layer PDF (Excel export), other times a scanned
  image needing OCR -- `checker/extract.py` auto-detects which.
- The "Passport No. / Other" column sometimes holds a seaman-book number
  (`SIRB-10245/24-12-2014`) or a CDC number (`CDC3363`) instead of a
  standard passport number -- `checker/parse.py` has a fallback identifier
  pattern for these so the row isn't silently dropped.
- Long or Burmese-script names sometimes wrap onto their own line above the
  index/ID line -- the parser pulls the name from the previous line in that
  case.
- OCR occasionally misreads a capital `I` as `!` -- folded before matching.
- A per-page integrity check compares the count of index markers (`1.`,
  `2.`, Burmese `၁။` etc.) against the count of successfully parsed rows.
  Any shortfall triggers a re-OCR at higher DPI; if it's still short, the
  gap is recorded and surfaced as a warning in the Telegram alert rather
  than silently treated as "no match."
