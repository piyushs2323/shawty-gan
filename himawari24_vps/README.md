# himawari24 — Netflix Email Access (Direct Outlook via Microsoft OAuth)

Self-contained **Flask + SQLite** app. Reads Netflix codes directly from personal
Outlook/Hotmail inboxes via **Microsoft Graph** — no email forwarding, **no passwords stored**.

> Personal Outlook.com/Hotmail basic auth (email:password over IMAP) was **disabled by Microsoft
> on 16 Sep 2024**. That's why this uses OAuth: each mailbox is connected **once** on Microsoft's
> login page, then fetched automatically forever using an encrypted refresh token.

---

## What you get
- Admin login (username/password from `.env`)
- Bulk-add mailboxes (paste many emails at once)
- **Connect Outlook** per mailbox → Microsoft login → consent (one time)
- Fetch Netflix codes by category: Login Code, Verification Code, Household, Password Reset, TV Login
- Connection status: Connected / Needs Reconnect
- Refresh tokens encrypted at rest (Fernet); access tokens auto-refresh (MSAL); Graph 429 handling

---

## 1. Register a free Azure app (5 min) — required for Connect to work
1. Go to https://entra.microsoft.com → **App registrations** → **New registration**.
2. **Supported account types:** *Personal Microsoft accounts only*.
3. **Authentication → Add platform → Web** → Redirect URI:
   - Local test: `http://localhost:8000/oauth/microsoft/callback`
   - Production: `https://YOUR_DOMAIN/oauth/microsoft/callback`
   (Must match `MS_REDIRECT_URI` in `.env` **exactly**.)
4. **API permissions → Add → Microsoft Graph → Delegated** → add `offline_access`, `User.Read`, `Mail.Read`.
5. **Certificates & secrets → New client secret** → copy the **Value** (shown once).
6. **Overview** → copy the **Application (client) ID**.
7. Put both into `.env`: `MS_CLIENT_ID`, `MS_CLIENT_SECRET`.

---

## 2. Run locally
```bash
cd himawari24_vps
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # (a ready-to-run .env with generated keys is already included)
# edit .env: set ADMIN_PASSWORD, MS_CLIENT_ID, MS_CLIENT_SECRET
python app.py
```
Open http://localhost:8000 → log in → add mailboxes → **Connect Outlook** → fetch codes.

---

## 3. Deploy on a VPS (production)
```bash
# with gunicorn (installed via requirements.txt)
gunicorn -w 2 -b 0.0.0.0:8000 app:app
```
Recommended: put **nginx** in front for HTTPS and set:
```
MS_REDIRECT_URI="https://YOUR_DOMAIN/oauth/microsoft/callback"
```
and register that same HTTPS redirect URI in Azure.

Example systemd service:
```ini
[Unit]
Description=himawari24
After=network.target

[Service]
WorkingDirectory=/opt/himawari24
Environment="PATH=/opt/himawari24/.venv/bin"
ExecStart=/opt/himawari24/.venv/bin/gunicorn -w 2 -b 127.0.0.1:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## Security notes (please read)
- **Change `ADMIN_PASSWORD`** in `.env` before exposing it.
- Keep `TOKEN_ENCRYPTION_KEY` secret and **backed up** — losing it means every mailbox must reconnect.
- These tokens grant inbox read across many accounts; protect the server and use HTTPS.
- Programmatically harvesting login codes across many mailboxes can run into Microsoft Graph terms —
  use accounts you own/control.

---

## Files
- `app.py` — the whole app (auth, assignments, OAuth, Graph fetcher, search)
- `templates/login.html`, `templates/dashboard.html` — UI (Tailwind via CDN, no build step)
- `requirements.txt`, `.env` / `.env.example`
