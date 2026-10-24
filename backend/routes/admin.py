from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import APIRouter, Depends

from auth import require_admin
from cricket_import import close_expired_markets, import_upcoming_cricket_markets
from database import supabase

router = APIRouter(prefix="/api/admin", tags=["admin"])
scheduler = AsyncIOScheduler()


@router.get("/stats")
async def platform_stats(admin=Depends(require_admin)):
    users = supabase.table("users").select("id", count="exact").execute()
    markets = supabase.table("markets").select("id", count="exact").execute()
    volume = supabase.table("orders").select("stake").eq("status", "active").execute()
    platform = supabase.table("platform_wallet").select("total_revenue").execute()

    total_volume = sum(o["stake"] for o in volume.data) if volume.data else 0
    revenue = platform.data[0]["total_revenue"] if platform.data else 0

    return {
        "total_users": users.count,
        "total_markets": markets.count,
        "total_volume": total_volume,
        "platform_revenue": revenue,
    }


def start_scheduler():
    scheduler.add_job(
        import_upcoming_cricket_markets,
        "interval",
        hours=6,
        next_run_time=datetime.now(timezone.utc),
        id="import_cricket_markets",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        close_expired_markets,
        "interval",
        minutes=1,
        next_run_time=datetime.now(timezone.utc),
        id="close_expired_markets",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
