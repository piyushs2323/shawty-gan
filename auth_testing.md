# Auth Testing — himawari24

Admin (JWT bearer): `admin@himawari24.app` / `admin123`

## Steps
1. Login: `POST /api/auth/login {email,password}` → returns `access_token`. Send as `Authorization: Bearer <token>`.
2. `GET /api/auth/me` with bearer → returns admin object.
3. Protected routes reject requests without a valid bearer (401).

Note: Microsoft OAuth (`MS_CLIENT_ID`/`MS_CLIENT_SECRET`) and Gmail IMAP creds are intentionally blank —
the flows are built but connecting a live mailbox needs those credentials.
