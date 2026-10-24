"""Import upcoming cricket fixtures as markets; never place user orders."""

import os
from datetime import datetime, timedelta, timezone

MATCHES_URL = "https://api.cricapi.com/v1/matches"


def market_from_match(match: dict, now: datetime) -> dict | None:
    teams = match.get("teams")
    match_id = match.get("id")
    start_text = match.get("dateTimeGMT")
    if not match_id or not isinstance(teams, list) or len(teams) != 2 or not start_text:
        return None
    if not all(isinstance(team, str) and team.strip() for team in teams):
        return None
    if match.get("matchStarted") or match.get("matchEnded"):
        return None
    try:
        start = datetime.fromisoformat(start_text.replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        start = start.astimezone(timezone.utc)
    except ValueError:
        return None
    if not now + timedelta(minutes=30) < start <= now + timedelta(days=14):
        return None

    first, second = (team.strip() for team in teams)
    return {
        "title": f"Will {first} win against {second}?",
        "description": (
            f"Scheduled cricket match. YES: {first} wins. NO: {second} wins. "
            "Draw, tie, cancellation, or no result requires a void/refund. "
            "Entries close at the scheduled start."
        ),
        "category": "cricket",
        "end_date": start.isoformat(),
        "cricapi_match_id": match_id,
        "status": "open",
    }


async def import_upcoming_cricket_markets() -> None:
    import httpx
    from database import supabase

    api_key = os.environ.get("CRICAPI_KEY", "")
    if not api_key:
        return
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(MATCHES_URL, params={"apikey": api_key, "offset": 0})
            response.raise_for_status()
            payload = response.json()
        if payload.get("status") != "success":
            print(f"Cricket import skipped: {payload.get('reason', 'provider error')}")
            return

        existing = supabase.table("markets").select("cricapi_match_id").not_.is_("cricapi_match_id", "null").execute()
        seen = {row["cricapi_match_id"] for row in existing.data}
        now = datetime.now(timezone.utc)
        for match in payload.get("data") or []:
            market = market_from_match(match, now)
            if not market or market["cricapi_match_id"] in seen:
                continue
            try:
                supabase.table("markets").insert(market).execute()
                seen.add(market["cricapi_match_id"])
            except Exception as exc:
                print(f"Cricket import failed for match {market['cricapi_match_id']}: {exc}")
    except (httpx.HTTPError, ValueError) as exc:
        print(f"Cricket import unavailable: {exc}")


async def close_expired_markets() -> None:
    from database import supabase

    now = datetime.now(timezone.utc).isoformat()
    supabase.table("markets").update({"status": "closed"}).eq("status", "open").lte("end_date", now).execute()
