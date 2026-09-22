"""Telegram bot for himawari24.

Lets a member/sub_admin/admin log in with their himawari24 email + password
(their app account — never their Netflix password) inside a Telegram chat,
then pick one of their assigned Netflix mailboxes and a category to fetch a
code/link, right from the bot. Enforces the exact same "is this email actually
assigned to you" rule as the website (via server.perform_search), so trying an
email that isn't theirs gets the same "This email is not assigned to you"
response the web app gives.

This module only talks HTTP to the Telegram Bot API directly (no extra SDK
dependency) and is driven by a webhook: Telegram POSTs updates to
/api/telegram/webhook, which calls handle_update() below.
"""
import os
import re
import uuid
import logging
import httpx

from db import db
from auth_utils import verify_password, hash_password  # noqa: F401  (hash_password kept for symmetry/future use)
from services.email_fetcher import categories_list, CATEGORIES

logger = logging.getLogger("himawari24.telegram")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# chat_id -> {"stage": "email" | "password", "email": str}
# Short-lived login flow state. Losing this on a restart just means the user
# re-sends /start — no security-sensitive data lives here longer than a
# couple of messages, and the password itself is never persisted anywhere.
_pending_login: dict[int, dict] = {}


async def _tg(method: str, **params):
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set — ignoring bot request")
        return None
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{TELEGRAM_API}/{method}", json=params)
        if r.status_code >= 400:
            logger.warning("Telegram API %s failed: %s", method, r.text[:300])
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else None


async def send_message(chat_id: int, text: str, keyboard: list = None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    return await _tg("sendMessage", **payload)


async def edit_message(chat_id: int, message_id: int, text: str, keyboard: list = None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    return await _tg("editMessageText", **payload)


async def delete_message(chat_id: int, message_id: int):
    return await _tg("deleteMessage", chat_id=chat_id, message_id=message_id)


async def answer_callback(callback_query_id: str, text: str = None, alert: bool = False):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = alert
    return await _tg("answerCallbackQuery", **payload)


async def _get_linked_user(chat_id: int):
    link = await db.telegram_links.find_one({"chat_id": chat_id})
    if not link:
        return None
    return await db.users.find_one({"id": link["user_id"]}, {"_id": 0, "password_hash": 0})


async def _assigned_emails_for(user: dict):
    query = {} if user.get("role") == "admin" else {"assigned_user_id": user["id"]}
    return await db.email_assignments.find(query, {"_id": 0}).sort("email_norm", 1).to_list(200)


# Icons shown only in the Telegram UI — kept separate from the shared
# category labels (email_fetcher.CATEGORIES) so the website isn't affected.
CATEGORY_ICONS = {
    "login_code": "🔑",
    "verification_code": "✅",
    "household": "🏠",
    "password_reset": "🔒",
    "tv_login": "📺",
}


def _category_keyboard(assignment_id: str):
    rows, row = [], []
    for c in categories_list():
        icon = CATEGORY_ICONS.get(c["key"], "")
        text = f"{icon} {c['label']}" if icon else c["label"]
        row.append({"text": text, "callback_data": f"cat:{assignment_id}:{c['key']}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{"text": "« Back to my emails", "callback_data": "menu"}])
    return rows


async def _email_keyboard(user: dict):
    assignments = await _assigned_emails_for(user)
    if not assignments:
        return None, assignments
    rows = [[{"text": f"📧 {a['email_norm']}", "callback_data": f"email:{a['id']}"}] for a in assignments]
    return rows, assignments


async def _send_email_menu(chat_id: int, user: dict, edit: tuple = None):
    keyboard, assignments = await _email_keyboard(user)
    if not assignments:
        text = "You don't have any Netflix emails assigned to you yet. Ask an admin to assign one."
        keyboard = None
    else:
        text = "Pick a Netflix email to fetch a code from:"
    if edit:
        await edit_message(edit[0], edit[1], text, keyboard)
    else:
        await send_message(chat_id, text, keyboard)


async def _handle_fetch(chat_id: int, message_id: int, user: dict, email_norm: str, category_key: str):
    from server import perform_search  # local import avoids a circular import at module load time

    label = next((c["label"] for c in categories_list() if c["key"] == category_key), category_key)
    try:
        result = await perform_search(user, email_norm, category_key)
    except Exception as exc:  # HTTPException from perform_search (not-assigned, not-found, bad category)
        detail = getattr(exc, "detail", "Something went wrong while fetching that code.")
        await edit_message(chat_id, message_id, f"❌ {detail}")
        return

    if not result.get("found"):
        reason = result.get("reason")
        friendly = {
            "not_connected": "That mailbox isn't connected yet. Ask an admin to connect it in the Mailboxes tab.",
            "needs_reconnect": "That mailbox's connection expired. Ask an admin to reconnect it.",
            "empty": "No matching Netflix email found in that inbox yet. Try again in a bit.",
            "not_configured": "Gmail isn't configured on the server for this mailbox.",
            "throttled": "Microsoft is rate-limiting requests right now — try again shortly.",
        }.get(reason, "Couldn't fetch a result for that category.")
        await edit_message(chat_id, message_id, f"<b>{email_norm}</b> — {label}\n\n{friendly}")
        return

    lines = [f"<b>{email_norm}</b> — {label}"]
    country = result.get("country")
    if country and country.get("flag"):
        lines[0] += f"  {country['flag']}"
        if country.get("country"):
            lines[0] += f" {country['country']}"
    lines.append("")
    if result.get("code"):
        lines.append(f"Code: <code>{result['code']}</code>")
    if result.get("link"):
        lines.append(f"Link: {result['link']}")
    if result.get("snippet"):
        lines.append(f"\n<i>{result['snippet'][:200]}</i>")
    await edit_message(chat_id, message_id, "\n".join(lines))


async def handle_update(update: dict):
    if "callback_query" in update:
        cq = update["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        message_id = cq["message"]["message_id"]
        data = cq.get("data", "")
        await answer_callback(cq["id"])

        user = await _get_linked_user(chat_id)
        if not user:
            await edit_message(chat_id, message_id, "You're not logged in. Send /start to log in first.")
            return

        if data == "menu":
            await _send_email_menu(chat_id, user, edit=(chat_id, message_id))
            return

        if data.startswith("email:"):
            assignment_id = data.split(":", 1)[1]
            assignment = await db.email_assignments.find_one({"id": assignment_id})
            if not assignment:
                await edit_message(chat_id, message_id, "That assignment no longer exists.")
                return
            if user.get("role") != "admin" and assignment.get("assigned_user_id") != user["id"]:
                await edit_message(chat_id, message_id, "This email is not assigned to you.")
                return
            await edit_message(
                chat_id, message_id,
                f"<b>{assignment['email_norm']}</b>\nWhich category?",
                _category_keyboard(assignment_id),
            )
            return

        if data.startswith("cat:"):
            _, assignment_id, category_key = data.split(":", 2)
            assignment = await db.email_assignments.find_one({"id": assignment_id})
            if not assignment:
                await edit_message(chat_id, message_id, "That assignment no longer exists.")
                return
            await edit_message(chat_id, message_id, f"<b>{assignment['email_norm']}</b>\nFetching…")
            await _handle_fetch(chat_id, message_id, user, assignment["email_norm"], category_key)
            return

        return

    message = update.get("message")
    if not message:
        return
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()

    if text == "/start":
        _pending_login.pop(chat_id, None)
        user = await _get_linked_user(chat_id)
        if user:
            await send_message(chat_id, f"You're logged in as {user['email']}.")
            await _send_email_menu(chat_id, user)
            return
        _pending_login[chat_id] = {"stage": "email"}
        await send_message(chat_id, "Welcome to himawari24. Send your account email to log in.")
        return

    if text == "/logout":
        _pending_login.pop(chat_id, None)
        await db.telegram_links.delete_one({"chat_id": chat_id})
        await send_message(chat_id, "You've been logged out. Send /start to log in again.")
        return

    pending = _pending_login.get(chat_id)

    if pending and pending["stage"] == "email":
        if not EMAIL_RE.match(text):
            await send_message(chat_id, "That doesn't look like a valid email. Send your account email again.")
            return
        pending["email"] = text.lower()
        pending["stage"] = "password"
        await send_message(chat_id, "Got it. Now send your password.")
        return

    if pending and pending["stage"] == "password":
        # Delete the password message immediately — it's never stored anywhere,
        # this is just chat hygiene so it doesn't sit visible in the thread.
        await delete_message(chat_id, message["message_id"])
        email = pending["email"]
        user = await db.users.find_one({"email": email})
        _pending_login.pop(chat_id, None)
        if not user or not verify_password(text, user["password_hash"]):
            await send_message(chat_id, "Incorrect email or password. Send /start to try again.")
            return
        await db.telegram_links.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id, "user_id": user["id"], "id": str(uuid.uuid4())}},
            upsert=True,
        )
        await send_message(chat_id, f"Logged in as {user['email']}.")
        await _send_email_menu(chat_id, user)
        return

    # Logged-in user typing an email directly instead of tapping a button —
    # covers "fetch some other email" and must give the same ownership check.
    if EMAIL_RE.match(text):
        user = await _get_linked_user(chat_id)
        if not user:
            await send_message(chat_id, "You're not logged in. Send /start to log in first.")
            return
        email_norm = text.lower()
        assignment = await db.email_assignments.find_one({"email_norm": email_norm})
        if not assignment:
            await send_message(chat_id, "No assignment exists for that email.")
            return
        if user.get("role") != "admin" and assignment.get("assigned_user_id") != user["id"]:
            await send_message(chat_id, "This email is not assigned to you.")
            return
        await send_message(
            chat_id,
            f"<b>{email_norm}</b>\nWhich category?",
            _category_keyboard(assignment["id"]),
        )
        return

    user = await _get_linked_user(chat_id)
    if user:
        await send_message(chat_id, "Send /start to see your assigned emails, or type one directly.")
    else:
        await send_message(chat_id, "Send /start to log in.")
