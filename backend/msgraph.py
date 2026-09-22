import os
import asyncio

import httpx
import msal

AUTHORITY = os.environ.get("MS_AUTHORITY", "https://login.microsoftonline.com/consumers")
SCOPES = ["User.Read", "Mail.Read"]  # offline_access is implicit in MSAL
GRAPH = "https://graph.microsoft.com/v1.0"

# MSAL error codes that mean the user must interactively re-consent.
REAUTH_ERRORS = {
    "invalid_grant",
    "interaction_required",
    "invalid_request",
    "unauthorized_client",
    "consent_required",
}


def is_configured() -> bool:
    return bool(os.environ.get("MS_CLIENT_ID") and os.environ.get("MS_CLIENT_SECRET"))


def _client() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        os.environ["MS_CLIENT_ID"],
        authority=AUTHORITY,
        client_credential=os.environ["MS_CLIENT_SECRET"],
    )


def build_auth_flow(state: str) -> dict:
    """Returns MSAL flow dict containing 'auth_uri' and PKCE material to persist."""
    return _client().initiate_auth_code_flow(
        scopes=SCOPES,
        redirect_uri=os.environ["MS_REDIRECT_URI"],
        state=state,
        prompt="select_account",
    )


def redeem_auth_code(flow: dict, auth_response: dict) -> dict:
    return _client().acquire_token_by_auth_code_flow(flow, auth_response)


def acquire_from_refresh(refresh_token: str) -> dict:
    return _client().acquire_token_by_refresh_token(refresh_token, SCOPES)


async def graph_get(access_token: str, path: str, params: dict | None = None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {access_token}", "ConsistencyLevel": "eventual"}
    async with httpx.AsyncClient(timeout=25) as c:
        resp = None
        for attempt in range(4):
            resp = await c.get(GRAPH + path, headers=headers, params=params)
            if resp.status_code == 429:
                delay = int(resp.headers.get("Retry-After", min(2 ** attempt, 30)))
                await asyncio.sleep(delay)
                continue
            return resp
        return resp
