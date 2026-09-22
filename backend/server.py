import os
import uuid
import logging
import secrets
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from db import db
from auth_utils import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_admin,
    get_current_staff,
    get_current_user,
)
import msgraph
from services.email_fetcher import (
    CATEGORIES,
    categories_list,
    fetch_netflix_code,
)
from services import telegram_bot
from crypto_utils import encrypt_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("himawari24")

app = FastAPI(title="himawari24 - Netflix Email Access")
api = APIRouter(prefix="/api")

PROVIDERS = {"gmail_imap", "outlook_graph"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize_email(e: str) -> str:
    return (e or "").strip().lower()


# ---------- Models ----------
class LoginReq(BaseModel):
    email: EmailStr
    password: str


class RegisterReq(BaseModel):
    name: str
    email: EmailStr
    password: str


class AssignmentCreate(BaseModel):
    email: EmailStr
    provider: str = "outlook_graph"
    label: str = ""
    assigned_user_id: str | None = None


class AssignmentUpdate(BaseModel):
    provider: str


class AssignReq(BaseModel):
    user_id: str | None = None


class SearchReq(BaseModel):
    email_norm: str
    category: str


# ---------- Auth ----------
@api.post("/auth/login")
async def login(body: LoginReq):
    email = normalize_email(body.email)
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], email)
    return {
        "access_token": token,
        "user": {"id": user["id"], "email": email, "name": user.get("name", "Admin"), "role": user["role"]},
    }


@api.post("/auth/register")
async def register(body: RegisterReq):
    email = normalize_email(body.email)
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user_id = str(uuid.uuid4())
    await db.users.insert_one({
        "id": user_id,
        "email": email,
        "name": body.name.strip() or email,
        "password_hash": hash_password(body.password),
        "role": "member",
        "created_at": now_iso(),
    })
    token = create_access_token(user_id, email)
    return {
        "access_token": token,
        "user": {"id": user_id, "email": email, "name": body.name.strip() or email, "role": "member"},
    }


@api.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return user


# ---------- Users (staff, for assigning emails) ----------
@api.get("/users")
async def list_users(staff=Depends(get_current_staff)):
    # Include sub_admins here too, not just plain members — an admin needs to
    # be able to assign a mailbox directly to a sub_admin (that's how it lands
    # in the sub_admin's own view so they can fetch it and, in turn, hand it
    # off to one of their members).
    docs = await db.users.find({"role": {"$in": ["member", "sub_admin"]}}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    return docs


@api.get("/users/all")
async def list_all_staff_users(admin=Depends(get_current_admin)):
    """Admin-only: members + sub_admins, for the Team/role management panel."""
    docs = await db.users.find({"role": {"$in": ["member", "sub_admin"]}}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    return docs


class RoleUpdate(BaseModel):
    role: str


@api.patch("/users/{user_id}/role")
async def set_user_role(user_id: str, body: RoleUpdate, admin=Depends(get_current_admin)):
    if body.role not in ("member", "sub_admin"):
        raise HTTPException(status_code=400, detail="Role must be member or sub_admin")
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("role") == "admin":
        raise HTTPException(status_code=400, detail="Cannot change an admin's role here")
    await db.users.update_one({"id": user_id}, {"$set": {"role": body.role}})
    return {"ok": True}


# ---------- Config status ----------
@api.get("/config/status")
async def config_status(user=Depends(get_current_user)):
    return {
        "microsoft_configured": msgraph.is_configured(),
        "gmail_configured": bool(os.environ.get("GMAIL_IMAP_USER") and os.environ.get("GMAIL_IMAP_PASSWORD")),
        "redirect_uri": os.environ.get("MS_REDIRECT_URI", ""),
        "authority": os.environ.get("MS_AUTHORITY", ""),
    }


@api.get("/categories")
async def get_categories(user=Depends(get_current_user)):
    return categories_list()


# ---------- Assignments ----------
@api.get("/assignments")
async def list_assignments(user=Depends(get_current_user)):
    # Full admin sees every mailbox. Everyone else — including sub_admin —
    # only sees mailboxes currently assigned to THEM specifically. A sub_admin
    # gets mailboxes into this list the same way a member would: the admin
    # assigns one to them via the "Assigned to" dropdown. From there the
    # sub_admin can hand it off to one of their own members using the same
    # dropdown (their staff permission on the assign endpoint), at which point
    # it moves into that member's own filtered view instead of the sub_admin's.
    query = {} if user.get("role") == "admin" else {"assigned_user_id": user["id"]}
    docs = await db.email_assignments.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    mailboxes = await db.mailbox_accounts.find({}, {"_id": 0, "ms_refresh_token_enc": 0}).to_list(500)
    mb_by_email = {m["email_norm"]: m for m in mailboxes}
    for d in docs:
        mb = mb_by_email.get(d["email_norm"])
        d["mailbox_status"] = mb["status"] if mb else None
        d["mailbox_email"] = mb.get("mailbox_email") if mb else None
    return docs


@api.post("/assignments")
async def create_assignment(body: AssignmentCreate, admin=Depends(get_current_admin)):
    if body.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Invalid provider")
    email_norm = normalize_email(body.email)
    existing = await db.email_assignments.find_one({"email_norm": email_norm})
    if existing:
        raise HTTPException(status_code=409, detail="Email already assigned")
    if body.assigned_user_id:
        target = await db.users.find_one({"id": body.assigned_user_id})
        if not target:
            raise HTTPException(status_code=404, detail="Assigned user not found")
    doc = {
        "id": str(uuid.uuid4()),
        "email_norm": email_norm,
        "provider": body.provider,
        "label": body.label or "",
        "assigned_user_id": body.assigned_user_id,
        "created_at": now_iso(),
    }
    await db.email_assignments.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.patch("/assignments/{assignment_id}")
async def update_assignment(assignment_id: str, body: AssignmentUpdate, admin=Depends(get_current_admin)):
    if body.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Invalid provider")
    res = await db.email_assignments.update_one(
        {"id": assignment_id}, {"$set": {"provider": body.provider}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return {"ok": True}


@api.patch("/assignments/{assignment_id}/assign")
async def assign_to_user(assignment_id: str, body: AssignReq, staff=Depends(get_current_staff)):
    if body.user_id:
        target = await db.users.find_one({"id": body.user_id})
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
    res = await db.email_assignments.update_one(
        {"id": assignment_id}, {"$set": {"assigned_user_id": body.user_id}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return {"ok": True}


@api.delete("/assignments/{assignment_id}")
async def delete_assignment(assignment_id: str, admin=Depends(get_current_admin)):
    doc = await db.email_assignments.find_one({"id": assignment_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Assignment not found")
    await db.email_assignments.delete_one({"id": assignment_id})
    await db.mailbox_accounts.delete_one({"email_norm": doc["email_norm"]})
    return {"ok": True}


# ---------- Mailboxes ----------
@api.get("/mailboxes")
async def list_mailboxes(admin=Depends(get_current_admin)):
    docs = await db.mailbox_accounts.find({}, {"_id": 0, "ms_refresh_token_enc": 0, "access_token_cache": 0}).to_list(500)
    return docs


@api.get("/mailboxes/connect")
async def mailboxes_connect(email_norm: str, admin=Depends(get_current_admin)):
    if not msgraph.is_configured():
        raise HTTPException(status_code=400, detail="Microsoft OAuth is not configured. Set MS_CLIENT_ID and MS_CLIENT_SECRET.")
    email_norm = normalize_email(email_norm)
    assignment = await db.email_assignments.find_one({"email_norm": email_norm})
    if not assignment:
        raise HTTPException(status_code=404, detail="No assignment for this email")

    state = secrets.token_urlsafe(24)
    flow = msgraph.build_auth_flow(state)
    if "auth_uri" not in flow:
        raise HTTPException(status_code=500, detail=flow.get("error_description", "MSAL error"))
    await db.oauth_states.insert_one({
        "state": state,
        "email_norm": email_norm,
        "flow": flow,
        "created_at": now_iso(),
        "created_dt": datetime.now(timezone.utc),
    })
    return {"auth_url": flow["auth_uri"]}


@api.get("/oauth/microsoft/callback")
async def oauth_callback(request: Request):
    frontend = os.environ.get("FRONTEND_URL", "")
    params = dict(request.query_params)
    state = params.get("state")
    if not state:
        return RedirectResponse(f"{frontend}/?error=missing_state")
    stored = await db.oauth_states.find_one_and_delete({"state": state})
    if not stored:
        return RedirectResponse(f"{frontend}/?error=invalid_state")

    try:
        result = msgraph.redeem_auth_code(stored["flow"], params)
    except Exception as e:
        logger.error("Token redemption failed: %s", e)
        return RedirectResponse(f"{frontend}/?error=token_exchange_failed")

    if "access_token" not in result:
        logger.error(
            "Token exchange returned no access_token. error=%s error_description=%s",
            result.get("error"),
            result.get("error_description"),
        )
        return RedirectResponse(f"{frontend}/?error=token_exchange_failed")
    refresh = result.get("refresh_token")
    if not refresh:
        return RedirectResponse(f"{frontend}/?error=no_refresh_token")

    # Detect the connected mailbox address
    resp = await msgraph.graph_get(result["access_token"], "/me", {"$select": "id,displayName,mail,userPrincipalName"})
    mailbox_email = ""
    if resp is not None and resp.status_code < 400:
        me_data = resp.json()
        mailbox_email = me_data.get("mail") or me_data.get("userPrincipalName") or ""

    email_norm = stored["email_norm"]
    await db.mailbox_accounts.update_one(
        {"email_norm": email_norm},
        {"$set": {
            "email_norm": email_norm,
            "provider": "outlook_graph",
            "mailbox_email": mailbox_email,
            "ms_refresh_token_enc": encrypt_token(refresh),
            "status": "connected",
            "connected_at": now_iso(),
            "updated_at": now_iso(),
        }},
        upsert=True,
    )
    return RedirectResponse(f"{frontend}/?connected={email_norm}")


@api.post("/mailboxes/{email_norm}/disconnect")
async def disconnect_mailbox(email_norm: str, admin=Depends(get_current_admin)):
    email_norm = normalize_email(email_norm)
    res = await db.mailbox_accounts.delete_one({"email_norm": email_norm})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Mailbox not connected")
    return {"ok": True}


# ---------- Search ----------
async def perform_search(user: dict, email_norm: str, category: str) -> dict:
    """Core fetch-and-authorize logic, shared by the HTTP /search route and the
    Telegram bot — so both enforce the exact same assignment ownership rule and
    never drift apart. Returns the same shape the /search route sends back."""
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Unknown category")
    assignment = await db.email_assignments.find_one({"email_norm": email_norm})
    if not assignment:
        raise HTTPException(status_code=404, detail="No assignment for this email")
    # Only full admin can fetch any mailbox. A sub_admin is otherwise scoped
    # exactly like a member: they can only fetch from mailboxes assigned to
    # THEM — matching the /assignments view above, so what a sub_admin can see
    # in Code Search always matches what's in their own Assignments list.
    if user.get("role") != "admin" and assignment.get("assigned_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="This email is not assigned to you")

    provider = assignment["provider"]
    mailbox = await db.mailbox_accounts.find_one({"email_norm": email_norm})

    if provider == "outlook_graph":
        if not mailbox or mailbox.get("status") != "connected":
            return {"found": False, "reason": "not_connected", "provider": provider}
        result = await fetch_netflix_code(mailbox, email_norm, category, provider)
    else:
        result = await fetch_netflix_code(mailbox or {}, email_norm, category, provider)

    status = result.get("status")

    # Persist rotated refresh token if Microsoft returned a new one
    if result.get("new_refresh") and mailbox:
        await db.mailbox_accounts.update_one(
            {"email_norm": email_norm},
            {"$set": {"ms_refresh_token_enc": encrypt_token(result["new_refresh"]), "updated_at": now_iso()}},
        )

    if status == "needs_reconnect":
        if mailbox:
            await db.mailbox_accounts.update_one(
                {"email_norm": email_norm},
                {"$set": {"status": "needs_reconnect", "updated_at": now_iso()}},
            )
        return {"found": False, "reason": "needs_reconnect", "provider": provider}

    if status == "found":
        return {"found": True, "provider": provider, **result["message"]}

    return {"found": False, "reason": status, "provider": provider}


@api.post("/search")
async def search(body: SearchReq, user=Depends(get_current_user)):
    email_norm = normalize_email(body.email_norm)
    return await perform_search(user, email_norm, body.category)


app.include_router(api)


# ---------- Telegram bot webhook ----------
@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request):
    # Telegram lets us set a secret_token on setWebhook; it sends it back on
    # every request in this header. If we've configured one, reject anything
    # that doesn't match instead of trusting an unauthenticated POST body.
    expected_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if expected_secret:
        got = request.headers.get("x-telegram-bot-api-secret-token")
        if got != expected_secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")
    body = await request.json()
    try:
        await telegram_bot.handle_update(body)
    except Exception:
        logger.exception("Error handling Telegram update")
    # Telegram only cares about the 200 — it retries on anything else.
    return {"ok": True}

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    # Idempotent admin seeding
    admin_email = normalize_email(os.environ.get("ADMIN_EMAIL", "admin@himawari24.local"))
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Admin",
            "role": "admin",
            "created_at": now_iso(),
        })
        logger.info("Seeded admin %s", admin_email)
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})

    await db.email_assignments.create_index("email_norm", unique=True)
    await db.mailbox_accounts.create_index("email_norm", unique=True)
    await db.oauth_states.create_index("state", unique=True)
    await db.oauth_states.create_index("created_dt", expireAfterSeconds=600)


@app.on_event("shutdown")
async def shutdown():
    pass
