"""
himawari24 — Netflix Email Access with Direct Outlook (Microsoft Graph) OAuth.
Self-contained Flask + SQLite app. Run: `python app.py` (dev) or gunicorn (prod).

Personal Outlook basic-auth (email:password) is disabled by Microsoft since 16 Sep 2024.
This app therefore uses OAuth 2.0: each mailbox is connected ONCE via Microsoft's login
page; we store an encrypted refresh token and fetch codes in the background afterward.
"""
import os
import re
import json
import sqlite3
import secrets
import functools
from datetime import datetime, timezone

import requests
import msal
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from flask import (
    Flask, request, redirect, url_for, render_template,
    session, jsonify, flash,
)

load_dotenv()

# ----------------------------------------------------------------------------- config
SECRET_KEY = os.environ["SECRET_KEY"]
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
MS_CLIENT_ID = os.environ.get("MS_CLIENT_ID", "")
MS_CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET", "")
MS_REDIRECT_URI = os.environ.get("MS_REDIRECT_URI", "http://localhost:8000/oauth/microsoft/callback")
MS_AUTHORITY = os.environ.get("MS_AUTHORITY", "https://login.microsoftonline.com/consumers")
TOKEN_ENCRYPTION_KEY = os.environ["TOKEN_ENCRYPTION_KEY"]
DATABASE_PATH = os.environ.get("DATABASE_PATH", "himawari24.db")

SCOPES = ["User.Read", "Mail.Read"]  # offline_access is implicit in MSAL
GRAPH = "https://graph.microsoft.com/v1.0"
REAUTH_ERRORS = {"invalid_grant", "interaction_required", "invalid_request",
                 "unauthorized_client", "consent_required"}

fernet = Fernet(TOKEN_ENCRYPTION_KEY.encode())
app = Flask(__name__)
app.secret_key = SECRET_KEY

# ----------------------------------------------------------------------------- Netflix parsing
CATEGORIES = {
    "login_code": {"label": "Login Code",
                   "keywords": ["temporary access code", "household travel", "travel", "get code", "access code"]},
    "verification_code": {"label": "Verification Code",
                          "keywords": ["verification code", "verify your", "confirm your", "your code", "verify email"]},
    "household": {"label": "Household",
                  "keywords": ["household", "update your household", "confirm update", "this was me"]},
    "password_reset": {"label": "Password Reset",
                       "keywords": ["reset your password", "password", "forgot"]},
    "tv_login": {"label": "TV Login",
                 "keywords": ["sign-in code", "sign in code", "new device", "signing in", "tv", "device"]},
}


def html_to_text(html):
    if not html:
        return ""
    t = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", t).strip()


def parse_netflix_email(subject, body_html):
    text = html_to_text(body_html)
    code = None
    m = re.search(r"(?<![\d-])(\d{4,8})(?![\d-])", text)
    if m:
        code = m.group(1)
    links = re.findall(r"https?://[^\s\"'<>]*netflix\.com[^\s\"'<>]*", (body_html or "") + " " + text)
    link = None
    for l in links:
        if any(p in l.lower() for p in ["travel", "update", "verify", "password", "confirm", "getcode", "get-code", "account/"]):
            link = l
            break
    if not link and links:
        link = links[0]
    return {"code": code, "link": link, "snippet": text[:400]}


# ----------------------------------------------------------------------------- database
def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS email_assignments (
            email_norm TEXT PRIMARY KEY,
            provider   TEXT NOT NULL DEFAULT 'outlook_graph',
            label      TEXT DEFAULT '',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS mailbox_accounts (
            email_norm           TEXT PRIMARY KEY,
            provider             TEXT NOT NULL DEFAULT 'outlook_graph',
            mailbox_email        TEXT DEFAULT '',
            ms_refresh_token_enc TEXT,
            status               TEXT DEFAULT 'needs_reconnect',
            connected_at         TEXT,
            updated_at           TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def norm(e):
    return (e or "").strip().lower()


# ----------------------------------------------------------------------------- auth
def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == ADMIN_USERNAME and request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("dashboard"))
        flash("Invalid credentials", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ----------------------------------------------------------------------------- Microsoft OAuth
def ms_configured():
    return bool(MS_CLIENT_ID and MS_CLIENT_SECRET)


def msal_app():
    return msal.ConfidentialClientApplication(
        MS_CLIENT_ID, authority=MS_AUTHORITY, client_credential=MS_CLIENT_SECRET)


def acquire_from_refresh(refresh_token):
    return msal_app().acquire_token_by_refresh_token(refresh_token, SCOPES)


def graph_get(access_token, path, params=None):
    headers = {"Authorization": f"Bearer {access_token}", "ConsistencyLevel": "eventual"}
    for attempt in range(4):
        r = requests.get(GRAPH + path, headers=headers, params=params, timeout=25)
        if r.status_code == 429:
            import time
            time.sleep(int(r.headers.get("Retry-After", min(2 ** attempt, 30))))
            continue
        return r
    return r


@app.route("/mailboxes/connect")
@login_required
def mailboxes_connect():
    if not ms_configured():
        flash("Microsoft OAuth is not configured. Set MS_CLIENT_ID and MS_CLIENT_SECRET in .env.", "error")
        return redirect(url_for("dashboard"))
    email = norm(request.args.get("email"))
    conn = get_db()
    row = conn.execute("SELECT 1 FROM email_assignments WHERE email_norm=?", (email,)).fetchone()
    conn.close()
    if not row:
        flash("No assignment for that email.", "error")
        return redirect(url_for("dashboard"))

    flow = msal_app().initiate_auth_code_flow(scopes=SCOPES, redirect_uri=MS_REDIRECT_URI)
    session["flow"] = flow
    session["connect_email"] = email
    return redirect(flow["auth_uri"])


@app.route("/oauth/microsoft/callback")
def oauth_callback():
    flow = session.pop("flow", None)
    email = session.pop("connect_email", None)
    if not flow or not email:
        flash("OAuth session expired. Try again.", "error")
        return redirect(url_for("dashboard"))
    try:
        result = msal_app().acquire_token_by_auth_code_flow(flow, request.args)
    except Exception:
        flash("Microsoft sign-in failed.", "error")
        return redirect(url_for("dashboard"))
    if "access_token" not in result or not result.get("refresh_token"):
        flash(result.get("error_description", "Token exchange failed (check offline_access scope)."), "error")
        return redirect(url_for("dashboard"))

    r = graph_get(result["access_token"], "/me", {"$select": "id,displayName,mail,userPrincipalName"})
    mailbox_email = ""
    if r.status_code < 400:
        d = r.json()
        mailbox_email = d.get("mail") or d.get("userPrincipalName") or ""

    enc = fernet.encrypt(result["refresh_token"].encode()).decode()
    conn = get_db()
    conn.execute(
        """INSERT INTO mailbox_accounts (email_norm, provider, mailbox_email, ms_refresh_token_enc, status, connected_at, updated_at)
           VALUES (?, 'outlook_graph', ?, ?, 'connected', ?, ?)
           ON CONFLICT(email_norm) DO UPDATE SET
             mailbox_email=excluded.mailbox_email, ms_refresh_token_enc=excluded.ms_refresh_token_enc,
             status='connected', connected_at=excluded.connected_at, updated_at=excluded.updated_at""",
        (email, mailbox_email, enc, now_iso(), now_iso()),
    )
    conn.commit()
    conn.close()
    flash(f"Outlook connected: {mailbox_email or email}", "success")
    return redirect(url_for("dashboard"))


@app.route("/mailboxes/disconnect", methods=["POST"])
@login_required
def mailboxes_disconnect():
    email = norm(request.form.get("email"))
    conn = get_db()
    conn.execute("DELETE FROM mailbox_accounts WHERE email_norm=?", (email,))
    conn.commit()
    conn.close()
    flash("Mailbox disconnected.", "success")
    return redirect(url_for("dashboard"))


# ----------------------------------------------------------------------------- assignments
@app.route("/assignments/add", methods=["POST"])
@login_required
def assignments_add():
    provider = request.form.get("provider", "outlook_graph")
    label = request.form.get("label", "")
    raw = request.form.get("emails", "")
    conn = get_db()
    added, skipped = 0, 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Accept "email" or "email:password" (password is ignored — not usable for personal Outlook)
        email = norm(line.split(":")[0].split(",")[0])
        if "@" not in email:
            continue
        try:
            conn.execute(
                "INSERT INTO email_assignments (email_norm, provider, label, created_at) VALUES (?,?,?,?)",
                (email, provider, label, now_iso()))
            added += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit()
    conn.close()
    flash(f"Added {added} assignment(s)" + (f", skipped {skipped} duplicate(s)." if skipped else "."), "success")
    return redirect(url_for("dashboard"))


@app.route("/assignments/delete", methods=["POST"])
@login_required
def assignments_delete():
    email = norm(request.form.get("email"))
    conn = get_db()
    conn.execute("DELETE FROM email_assignments WHERE email_norm=?", (email,))
    conn.execute("DELETE FROM mailbox_accounts WHERE email_norm=?", (email,))
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))


# ----------------------------------------------------------------------------- search / fetch
def fetch_outlook(mailbox, cfg):
    try:
        refresh = fernet.decrypt(mailbox["ms_refresh_token_enc"].encode()).decode()
    except Exception:
        return {"status": "needs_reconnect"}
    result = acquire_from_refresh(refresh)
    if "access_token" not in result:
        if result.get("error") in REAUTH_ERRORS:
            return {"status": "needs_reconnect"}
        return {"status": "error", "reason": result.get("error_description", "token_error")}
    new_refresh = result.get("refresh_token")
    params = {"$search": '"netflix"', "$top": 25,
              "$select": "id,subject,from,receivedDateTime,bodyPreview,webLink,body"}
    r = graph_get(result["access_token"], "/me/messages", params)
    if r.status_code == 401:
        return {"status": "needs_reconnect", "new_refresh": new_refresh}
    if r.status_code == 429:
        return {"status": "throttled", "new_refresh": new_refresh}
    if r.status_code >= 400:
        return {"status": "error", "reason": f"graph_{r.status_code}", "new_refresh": new_refresh}

    kws = [k.lower() for k in cfg["keywords"]]
    msgs = []
    for m in r.json().get("value", []):
        frm = ((m.get("from") or {}).get("emailAddress") or {}).get("address", "") or ""
        hay = (m.get("subject", "") + " " + m.get("bodyPreview", "")).lower()
        if "netflix" in frm.lower() and any(k in hay for k in kws):
            msgs.append(m)
    msgs.sort(key=lambda x: x.get("receivedDateTime", ""), reverse=True)
    if not msgs:
        return {"status": "empty", "new_refresh": new_refresh}
    m = msgs[0]
    parsed = parse_netflix_email(m.get("subject", ""), (m.get("body") or {}).get("content", ""))
    frm = ((m.get("from") or {}).get("emailAddress") or {}).get("address", "")
    return {"status": "found", "new_refresh": new_refresh, "message": {
        "code": parsed["code"], "link": parsed["link"], "snippet": parsed["snippet"],
        "subject": m.get("subject", ""), "from": frm, "received": m.get("receivedDateTime", ""),
        "web_link": m.get("webLink", "")}}


@app.route("/search", methods=["POST"])
@login_required
def search():
    email = norm(request.form.get("email"))
    category = request.form.get("category")
    if category not in CATEGORIES:
        return jsonify({"found": False, "reason": "bad_category"})
    conn = get_db()
    assignment = conn.execute("SELECT * FROM email_assignments WHERE email_norm=?", (email,)).fetchone()
    mailbox = conn.execute("SELECT * FROM mailbox_accounts WHERE email_norm=?", (email,)).fetchone()
    if not assignment:
        conn.close()
        return jsonify({"found": False, "reason": "no_assignment"})
    if assignment["provider"] != "outlook_graph":
        conn.close()
        return jsonify({"found": False, "reason": "not_configured"})  # gmail_imap not in VPS build
    if not mailbox or mailbox["status"] != "connected":
        conn.close()
        return jsonify({"found": False, "reason": "not_connected"})

    result = fetch_outlook(mailbox, CATEGORIES[category])

    if result.get("new_refresh"):
        conn.execute("UPDATE mailbox_accounts SET ms_refresh_token_enc=?, updated_at=? WHERE email_norm=?",
                     (fernet.encrypt(result["new_refresh"].encode()).decode(), now_iso(), email))
        conn.commit()
    if result["status"] == "needs_reconnect":
        conn.execute("UPDATE mailbox_accounts SET status='needs_reconnect', updated_at=? WHERE email_norm=?",
                     (now_iso(), email))
        conn.commit()
        conn.close()
        return jsonify({"found": False, "reason": "needs_reconnect"})
    conn.close()
    if result["status"] == "found":
        return jsonify({"found": True, "provider": "outlook_graph", **result["message"]})
    return jsonify({"found": False, "reason": result["status"]})


# ----------------------------------------------------------------------------- dashboard
@app.route("/")
@login_required
def dashboard():
    conn = get_db()
    assignments = conn.execute("SELECT * FROM email_assignments ORDER BY created_at DESC").fetchall()
    mailboxes = {m["email_norm"]: m for m in conn.execute("SELECT * FROM mailbox_accounts").fetchall()}
    conn.close()
    rows = []
    for a in assignments:
        mb = mailboxes.get(a["email_norm"])
        rows.append({"email_norm": a["email_norm"], "provider": a["provider"], "label": a["label"],
                     "mailbox_email": mb["mailbox_email"] if mb else "",
                     "status": mb["status"] if mb else "none"})
    return render_template("dashboard.html", rows=rows, categories=CATEGORIES,
                           ms_configured=ms_configured(), redirect_uri=MS_REDIRECT_URI)


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
