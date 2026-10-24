from fastapi import APIRouter, HTTPException, Depends
from database import supabase
from auth import get_current_user, require_admin
from schemas import MarketCreate, MarketResolve
from resolve_market import resolve_market
from websocket_manager import manager
import json

router = APIRouter(prefix="/api/markets", tags=["markets"])


@router.get("")
async def list_markets(category: str = None, status: str = "open"):
    query = supabase.table("markets").select("*")
    if status != "all":
        query = query.eq("status", status)
    if category:
        query = query.eq("category", category)
    result = query.order("created_at", desc=True).execute()
    return result.data


@router.get("/{market_id}")
async def get_market(market_id: str):
    market = supabase.table("markets").select("*").eq("id", market_id).execute()
    if not market.data:
        raise HTTPException(status_code=404, detail="Market not found")

    # Price history
    history = supabase.table("price_history").select("*").eq("market_id", market_id).order("recorded_at").execute()

    return {**market.data[0], "price_history": history.data}


@router.post("")
async def create_market(body: MarketCreate, admin=Depends(require_admin)):
    new_market = {
        "title": body.title,
        "description": body.description,
        "category": body.category,
        "end_date": body.end_date.isoformat(),
        "yes_pool": 0.0,
        "no_pool": 0.0,
        "yes_price": 0.5,   # starts at 50%
        "no_price": 0.5,
        "total_volume": 0.0,
        "status": "open",
        "outcome": None,
        "cricapi_match_id": body.cricapi_match_id,
    }
    result = supabase.table("markets").insert(new_market).execute()
    return result.data[0]


@router.post("/{market_id}/resolve")
async def resolve(market_id: str, body: MarketResolve, admin=Depends(require_admin)):
    market = supabase.table("markets").select("*").eq("id", market_id).execute()
    if not market.data or market.data[0]["status"] not in ("open", "closed"):
        raise HTTPException(status_code=404, detail="Market not found or already resolved")
    if (market.data[0].get("description") or "").startswith("[DEMO]"):
        raise HTTPException(status_code=400, detail="Demo markets cannot be settled")

    # Get all orders
    orders = supabase.table("orders").select("*").eq("market_id", market_id).eq("status", "active").execute()
    order_list = [{"user_id": o["user_id"], "side": o["side"], "stake": o["stake"]} for o in orders.data]

    # Run profit engine
    result = resolve_market(body.outcome, order_list)

    if result["void"]:
        # Refund everyone
        for payout in result["payouts"]:
            supabase.rpc("credit_wallet", {
                "p_user_id": payout["user_id"],
                "p_amount": payout["payout"]
            }).execute()
        supabase.table("markets").update({"status": "voided"}).eq("id", market_id).execute()
        supabase.table("orders").update({"status": "refunded"}).eq("market_id", market_id).execute()
        return {"status": "voided", "message": "Market voided — all stakes refunded"}

    # Credit winners
    for payout in result["payouts"]:
        supabase.rpc("credit_wallet", {
            "p_user_id": payout["user_id"],
            "p_amount": payout["payout"]
        }).execute()
        supabase.table("orders").update({
            "status": "won",
            "payout": payout["payout"]
        }).eq("market_id", market_id).eq("user_id", payout["user_id"]).execute()

    # Credit platform wallet
    supabase.rpc("credit_platform_wallet", {
        "p_amount": result["platform_revenue"]
    }).execute()

    # Mark losers
    losing_side = "no" if body.outcome == "yes" else "yes"
    supabase.table("orders").update({"status": "lost", "payout": 0}).eq("market_id", market_id).eq("side", losing_side).execute()

    # Update market
    supabase.table("markets").update({
        "status": "resolved",
        "outcome": body.outcome,
    }).eq("id", market_id).execute()

    # Broadcast result via WebSocket
    await manager.broadcast(json.dumps({
        "type": "market_resolved",
        "market_id": market_id,
        "outcome": body.outcome,
        "platform_revenue": result["platform_revenue"],
    }))

    return {
        "status": "resolved",
        "outcome": body.outcome,
        "payouts": result["payouts"],
        "platform_revenue": result["platform_revenue"],
    }
