# PRD — himawari24 (Netflix Email Access + Direct Outlook via Microsoft OAuth)

## Original Problem Statement
Add direct personal Outlook/Hotmail mailbox access to the "Netflix Email Access" app via Microsoft Graph
(OAuth 2.0, no password login, encrypted refresh tokens), while keeping a Gmail/IMAP path. Admin connects each
Outlook mailbox once; app reads Netflix codes in the background.

## Architecture (as built)
- Adapted to the Emergent platform stack: **FastAPI + MongoDB + React** (the original Flask/SQLite app did not exist
  in this environment, so the full app was built natively on this stack).
- Backend: `server.py` (routes), `msgraph.py` (MSAL/Graph), `services/email_fetcher.py` (provider branches + Netflix
  parsers), `crypto_utils.py` (Fernet), `auth_utils.py` (JWT admin), `db.py` (Mongo).
- Collections: `users`, `email_assignments`, `mailbox_accounts`, `oauth_states` (TTL 10min).
- Frontend: React (dark tactical dashboard) — Login + Dashboard with Mailboxes / Assignments / Code Search tabs.

## User Personas
- **Admin**: connects Outlook mailboxes, manages email→provider assignments, searches Netflix codes.

## Core Requirements (static)
- OAuth connect/disconnect per Outlook mailbox (admin-only, state/CSRF protected).
- Encrypted-at-rest refresh tokens (Fernet); auto-refreshing access tokens (MSAL); refresh-token rotation persisted.
- Graph inbox read + category parsing (Login Code, Verification Code, Household, Password Reset, TV Login).
- Hybrid routing per mailbox: `outlook_graph` vs `gmail_imap`.
- Graph 429/Retry-After handling; revoked/expired token → `needs_reconnect`.
- Admin dashboard status: Connected / Needs Reconnect / Not connected.

## Implemented (2026-08-13)
- JWT admin auth (seeded `admin@himawari24.app` / `admin123`).
- Email assignments CRUD + provider switching.
- Microsoft OAuth connect flow (MSAL `consumers` authority), encrypted refresh token store, `/me` mailbox detection,
  callback with state validation + error redirects.
- Graph-based fetcher + Gmail IMAP fetcher sharing one set of Netflix category parsers.
- Search routing with needs_reconnect/throttled/empty/not_configured handling.
- Dark dashboard UI: mailbox cards w/ status badges, connect/reconnect/disconnect, assignments table, code search with
  copy-to-clipboard result card.
- Verified: 20/20 backend pytest + 100% frontend flows.

## Configuration status
- `MS_CLIENT_ID` / `MS_CLIENT_SECRET` — **BLANK** (user fills after Azure app registration). Redirect URI to register:
  `https://outlook-graph-mail.preview.emergentagent.com/api/oauth/microsoft/callback`, authority `consumers`,
  delegated scopes `offline_access` + `User.Read` + `Mail.Read`.
- `TOKEN_ENCRYPTION_KEY`, `JWT_SECRET` — auto-generated in backend/.env.
- Gmail IMAP (`GMAIL_IMAP_USER`/`GMAIL_IMAP_PASSWORD`) — blank (optional secondary path).

## Backlog / Remaining
- P0: User adds real Azure credentials to complete live Outlook connect + code fetch (only step needing external setup).
- P1: Bulk multi-mailbox concurrent search (MAX_WORKERS) endpoint + UI.
- P1: Reconnect email/alert notifications when a token is revoked.
- P2: Rotate admin password off default; publisher verification for Azure app to remove consent cap.
- P2: Pagination for large assignment/mailbox lists.

## Next tasks
- Provide Azure MS_CLIENT_ID/MS_CLIENT_SECRET → test one real Outlook connect end-to-end.
