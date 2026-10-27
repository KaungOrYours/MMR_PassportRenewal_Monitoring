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
      -> match against the watchlist -- the passport number is the
         authoritative identifier; a name hit alone is never sufficient
         (two people can share a name), but a passport hit alone IS
         reported even if the name didn't match, since OCR mangles names
         often enough that requiring both would turn a real match into a
         missed notification

  [2] telegram_renewal check
      -> Telethon (Telegram client API, full-resolution photos) fetches new
         posts from @mesg15 since the last processed message id
      -> OCR each photo (tesseract), parse the PV/PJ table format, same
         integrity-check-and-retry pattern as [1]
      -> match against the watchlist, same passport-is-authoritative rule --
         matching checks the visible first/last 2 of 6 digits plus the
         letters, since the channel redacts the middle 2 digits for privacy

  Both checks -> write results to Neon Postgres -> send a Telegram alert

Vercel (frontend) <--Passkey session cookie--> Render (FastAPI backend) <--> Neon Postgres
```

Three independently deployed pieces, one repo:

- `checker/` -- the scraping/OCR/matching pipeline. Runs in GitHub Actions
  because OCR needs the `tesseract` + `poppler` system binaries, which Actions
  installs in seconds via `apt-get`; Render's free Python runtime can't
  without switching to Docker.
- `backend/` -- FastAPI REST API over the same Postgres database, deployed to
  Render. `POST /api/watchlist` (self-service signup) and `/api/health` are
  public; everything else requires a Passkey-authenticated session -- see
  "Admin access" below.
- `frontend/` -- React + Vite + Tailwind, deployed to Vercel. `/` is the
  public signup page; `/admin` is the Passkey-gated dashboard (Watchlist,
  Alerts, Lists, Status).

## Setup

### 1. Telegram bot

Already created: `@MMR_PassportRenewalMonitoringBot`. **Revoke and regenerate
the bot token via @BotFather** before deploying -- the original token was
shared in plaintext during setup. Message the bot `/start` once to register
your chat; the chat ID is already captured as `REDACTED_OPERATOR_TELEGRAM_CHAT_ID`.

The backend also needs `TELEGRAM_BOT_TOKEN` set on **Render** (separate from
the GitHub Actions secret above -- this is a different runtime) so the
signup confirmation messages and the webhook below can actually send.

On every boot, the backend self-registers a Telegram webhook
(`backend/telegram_webhook.py`) pointing at its own `RENDER_EXTERNAL_URL`
(set automatically by Render, no action needed), secured with `API_SECRET`
as the verification token. This is what makes the signup form's "Connect
Telegram" button work: tapping it opens a chat with the bot, the user taps
Start, and the bot immediately replies with their chat ID (or, if they're
already registered, a welcome-back message with their status link) --
without this, Telegram's Bot API has no way to message someone who hasn't
started a conversation with the bot first, so this closes that gap.

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
- `API_SECRET` -- a long random string (`openssl rand -hex 32`). This is a
  **one-time bootstrap credential only**, used once to register the first
  admin device -- see step 7. Never baked into the frontend; type it in by
  hand during that one ceremony and never use it again afterward.
- `GH_DISPATCH_TOKEN` -- a GitHub personal access token (fine-grained,
  `Actions: write` on this repo only) so the admin dashboard's "Check now"
  button can trigger the workflow
- `FRONTEND_ORIGIN` -- your exact Vercel URL (e.g.
  `https://mmr-passport-renewal-monitoring.vercel.app`). **Required, not
  optional** -- credentialed cross-origin cookies (used by the Passkey
  session) do not work with a wildcard CORS origin.
- `WEBAUTHN_RP_ID` -- your Vercel domain with no scheme/path, e.g.
  `mmr-passport-renewal-monitoring.vercel.app`
- `WEBAUTHN_ORIGIN` -- the full origin, e.g.
  `https://mmr-passport-renewal-monitoring.vercel.app`

### 6. Frontend -- Vercel

Import the repo, set the project root to `frontend/`, and set env vars:

- `VITE_API_BASE` -- your Render backend URL

That's the only one needed. There is no `VITE_API_KEY` -- nothing secret is
baked into the frontend bundle anymore (see step 7).

### 7. Admin access -- Passkey (Face ID / Touch ID) login

The site has two parts:

- **Public signup** (`/`) -- open to anyone with the link, no login. Lets
  someone add their own name/passport/Telegram ID to get notified.
- **Admin dashboard** (`/admin`) -- everything else (viewing the full
  watchlist, Alerts, Lists, Status, triggering checks). Gated by a Passkey
  login: no username or password, your device's Face ID/Touch ID key pair
  **is** the credential. There is no standing API key for this -- a stolen
  URL or a read of the public bundle gets an attacker nothing.

One-time setup, right after the backend is deployed with the env vars above:

1. Open `https://<your-vercel-domain>/admin` on your **first** device (e.g.
   MacBook). Since no device is registered yet, it asks for the one-time
   setup code -- enter the `API_SECRET` value from step 5, give the device a
   label, and complete the Touch ID prompt. You're now logged in, and that
   `API_SECRET` value is permanently useless afterward (bootstrap closes the
   moment one device exists).
2. On the **Status** tab, click **"Generate code to add another device"** --
   it shows a code valid for 10 minutes.
3. Open `/admin` on your **second** device (e.g. iPhone), expand "Registering
   a new device?", enter that code and a label, complete the Face ID prompt.

From then on, each device just does **"Log in with Passkey"** -- no code
needed. Lost a device? Revoke it from the Status tab on another logged-in
device.

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
  FRONTEND_ORIGIN="http://localhost:5173" \
  WEBAUTHN_RP_ID="localhost" WEBAUTHN_ORIGIN="http://localhost:5173" \
  uvicorn backend.main:app --reload

# frontend
cd frontend && npm install
cp .env.example .env.local   # fill in VITE_API_BASE
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
