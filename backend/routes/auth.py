import asyncio
import httpx
from fastapi import APIRouter, HTTPException

from auth import create_access_token
from database import SUPABASE_KEY, SUPABASE_URL, supabase
from schemas import LoginRequest, RegisterRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def auth_request(path: str, payload: dict) -> dict:
    """Use Supabase Auth without changing the service client's session."""
    url = f"{SUPABASE_URL.rstrip('/')}/auth/v1/{path}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
        "User-Agent": "PredictIN-Backend/1.0",
    }
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(2):
            try:
                response = await client.post(url, headers=headers, json=payload)
            except httpx.RequestError as exc:
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                print(f"Supabase Auth request failed: {type(exc).__name__}: {exc}")
                raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc
            if response.status_code in (502, 503, 504) and attempt == 0:
                await asyncio.sleep(0.5)
                continue
            break

    try:
        data = response.json()
    except ValueError:
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    if response.status_code >= 500:
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    if response.is_error:
        detail = data.get("msg") or data.get("message") or data.get("error_description")
        raise HTTPException(status_code=400, detail=detail or "Authentication failed")
    return data


def ensure_profile(auth_user: dict, name: str | None = None) -> dict:
    """Keep the app's wallet/profile row tied to the Supabase Auth user id."""
    user_id = auth_user["id"]
    email = auth_user["email"]
    result = supabase.table("users").select("*").eq("id", user_id).execute()
    if result.data:
        return result.data[0]

    # Never attach an existing wallet to a different Auth identity by email.
    existing_email = supabase.table("users").select("id").eq("email", email).execute()
    if existing_email.data:
        raise HTTPException(
            status_code=409,
            detail="This email has a legacy app profile. Contact support to link the account.",
        )

    metadata = auth_user.get("user_metadata") or {}
    display_name = name or metadata.get("name") or email.split("@")[0]
    profile = {
        "id": user_id,
        "name": display_name,
        "email": email,
        # The existing database column is NOT NULL. No password is stored here.
        "password_hash": "supabase-auth-managed",
        "wallet_balance": 0,
        "is_admin": False,
    }
    try:
        return supabase.table("users").insert(profile).execute().data[0]
    except Exception:
        # A concurrent first login may have created the same profile.
        retry = supabase.table("users").select("*").eq("id", user_id).execute()
        if retry.data:
            return retry.data[0]
        raise


def auth_response(profile: dict) -> dict:
    token = create_access_token({"sub": profile["id"]})
    return {
        "token": token,
        "user": {
            "id": profile["id"],
            "name": profile["name"],
            "email": profile["email"],
            "is_admin": profile["is_admin"],
            "wallet_balance": profile["wallet_balance"],
        },
    }


@router.post("/register")
async def register(body: RegisterRequest):
    data = await auth_request(
        "signup",
        {"email": body.email, "password": body.password, "data": {"name": body.name}},
    )
    # Supabase can require email confirmation. The profile is created on first login.
    if not data.get("access_token"):
        return {"confirmation_required": True}
    return auth_response(ensure_profile(data["user"], body.name))


@router.post("/login")
async def login(body: LoginRequest):
    try:
        data = await auth_request(
            "token?grant_type=password", {"email": body.email, "password": body.password}
        )
    except HTTPException as exc:
        if exc.status_code == 400:
            raise HTTPException(status_code=401, detail="Invalid email or password") from exc
        raise
    return auth_response(ensure_profile(data["user"]))
