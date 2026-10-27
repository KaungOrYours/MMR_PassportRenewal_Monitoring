# MMR Passport Renewal Monitoring System

Watches two things the Myanmar Embassy Singapore publishes, and sends a
Telegram alert the moment a watched name/passport appears:

1. **The website's Lost & Seaman/Offshore approved-list PDF** -- for people
   whose passport was lost abroad, or who are seamen/offshore workers,
   approved to get a replacement passport issued.
2. **The `@mesg15` Telegram channel's PV/PJ renewal appointment posts** --
   the actual *standard passport renewal* list: people approved to upgrade
   their passport book type (e.g. PV -> PJ) with a specific appointment date
   to show up at the embassy. This is the one most people actually need.

These are genuinely different lists from different sources (confirmed by
checking the embassy site directly -- there is no general-renewal list
published there; it only has the Lost/Seaman one). Both are monitored
independently against the same watchlist.

## How it works

```
GitHub Actions (every 3h, free) -- checker/main.py runs BOTH checks:

  [1] embassy_pdf check
      -> conditional GET the embassy PDF (ETag/Last-Modified; cheap when unchanged)
      -> extract text (pdftotext) or OCR (tesseract, for scanned PDFs)
      -> parse rows, anchored on passport/ID number, with an integrity check
         that re-OCRs any page where rows were silently dropped
      -> match against the watchlist -- BOTH passport number and fuzzy name
         must match; a hit on only one is not reported at all (too ambiguous
         to alert on: a shared common name, or a passport-only coincidence)

  [2] telegram_renewal check
      -> Telethon (Telegram client API, full-resolution photos) fetches new
         posts from @mesg15 since the last processed message id
      -> OCR each photo (tesseract), parse the PV/PJ table format, same
         integrity-check-and-retry pattern as [1]
      -> match against the watchlist, same both-must-match rule -- passport
         matching checks the visible first/last 2 of 6 digits plus the
         letters, since the channel redacts the middle 2 digits for privacy

  Both checks -> write results to Neon Postgres -> send a Telegram alert

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

### 3. Telegram client API (to read @mesg15)

This is separate from the bot above -- the bot can only *send* messages to
you; reading another channel's full-resolution photos requires Telegram's
client API, logged in as your own account (read-only access to a public
channel, same as just viewing it in the app).

1. Get a free `api_id`/`api_hash` from https://my.telegram.org (log in,
   "API development tools", create an app -- any name/platform is fine)
2. Run the one-time interactive login **yourself, locally** (not here in
   chat -- it asks for your phone number and the login code):
   ```bash
   cd checker && source ../.venv/bin/activate   # or pip install telethon first
   python3 generate_session.py
   ```
3. It prints a session string. Treat it like a password -- save it **only**
   as the GitHub secret below, never anywhere else.

### 4. GitHub Actions secrets

In the repo's Settings -> Secrets and variables -> Actions, add:

- `NEON_DATABASE_URL`
- `TELEGRAM_BOT_TOKEN` (the regenerated token)
- `TELEGRAM_CHAT_ID` = `REDACTED_OPERATOR_TELEGRAM_CHAT_ID`
- `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` (from step 3.1)
- `TELEGRAM_SESSION_STRING` (from step 3.2 -- never commit this)

The workflow (`.github/workflows/check.yml`) runs every 3 hours and on
manual dispatch. On the very first run, the Telegram check only bootstraps
its watermark (no backfill of the channel's history) -- it will start
alerting on posts from that point forward.

### 5. Backend -- Render

Uses `render.yaml` (Blueprint). In Render: New -> Blueprint -> point at this
repo. Set these env vars when prompted:

- `NEON_DATABASE_URL` -- same as above
- `API_SECRET` -- a long random string you generate (e.g. `openssl rand -hex 32`)
- `GH_DISPATCH_TOKEN` -- a GitHub personal access token (fine-grained,
  `Actions: write` on this repo only) so the GUI's "Check now" button can
  trigger the workflow
- `FRONTEND_ORIGIN` -- your Vercel URL, once you have it (comma-separate if
  more than one)

### 6. Frontend -- Vercel

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

## Known data-format quirks (why the parsers are written the way they are)

### Embassy website PDF (`checker/parse.py`)

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

### Telegram renewal posts (`checker/parse_renewal.py`)

- Passport numbers are **partially masked** by the embassy for privacy
  (`MF 40**22` -- the middle 2 of 6 digits are redacted). Matching checks
  the letters plus the visible first/last 2 digits; the 2 redacted digits
  are inherently unrecoverable from this source, so a coincidental
  collision there (different person, same visible digits) is possible in
  theory but requires the name to also match, which is effectively never
  true for a different person.
- The table uses a bare numeric index (no `.`/`။` punctuation) and one
  appointment date per image, applied to every row on that image.
- `t.me/s/<channel>` (the public no-login preview) serves **downscaled,
  recompressed** photos -- OCR accuracy on those is visibly worse. The
  checker instead uses Telegram's client API (Telethon) to fetch the
  original full-resolution photos, which requires the one-time login in
  the setup section above.

### Both sources

A per-page/per-image integrity check compares the count of index markers
against the count of successfully parsed rows. Any shortfall triggers a
re-OCR at a different setting; if it's still short, the gap is recorded and
surfaced as a warning in the Telegram alert rather than silently treated as
"no match."
