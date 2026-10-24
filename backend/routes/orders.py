from fastapi import APIRouter, HTTPException, Depends
from database import supabase
from auth import get_current_user
from schemas import OrderCreate
from websocket_manager import manager
import json
from datetime import datetime, timezone

router = APIRouter(prefix="/api/orders", tags=["orders"])

MIN_STAKE = 10.0    # ₹10 minimum stake per order
MAX_STAKE = 50000.0 # ₹50,000 maximum stake per order


@router.post("/buy")
async def buy(body: OrderCreate, current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]

    # Validate stake amount
    if body.stake < MIN_STAKE or body.stake > MAX_STAKE:
        raise HTTPException(status_code=400, detail=f"Stake must be between ₹{MIN_STAKE} and ₹{MAX_STAKE}")

    # Check market is open
    market_res = supabase.table("markets").select("*").eq("id", body.market_id).eq("status", "open").execute()
    if not market_res.data:
        raise HTTPException(status_code=404, detail="Market not found or closed")

    market = market_res.data[0]
    if (market.get("description") or "").startswith("[PRACTICE]") and user_id not in {
        "21eb7702-f65f-4c1b-9c2f-3e994410e32c",
        "f4c80b09-1275-44f5-8681-4c07c5383ddd",
    }:
        raise HTTPException(status_code=403, detail="Practice markets are reserved for the two test accounts")
    if (market.get("description") or "").startswith("[DEMO]"):
        raise HTTPException(status_code=400, detail="Demo markets do not accept stakes")
    end_date = datetime.fromisoformat(market["end_date"].replace("Z", "+00:00"))
    if end_date <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Entries are closed for this market")

    # One-side-per-market rule: check if user already staked on the OTHER side
    existing = supabase.table("orders").select("side").eq("market_id", body.market_id).eq("user_id", user_id).eq("status", "active").execute()
    for order in existing.data:
        if order["side"] != body.side:
            raise HTTPException(
                status_code=400,
                detail=f"You already have a {order['side'].upper()} position on this market. You cannot stake on both sides."
            )

    # Check wallet balance
    user_res = supabase.table("users").select("wallet_balance").eq("id", user_id).execute()
    balance = user_res.data[0]["wallet_balance"]
    if balance < body.stake:
        raise HTTPException(status_code=400, detail=f"Insufficient balance. You have ₹{balance:.2f}")

    # Deduct wallet
    supabase.rpc("debit_wallet", {"p_user_id": user_id, "p_amount": body.stake}).execute()

    # Record order
    order_result = supabase.table("orders").insert({
        "user_id": user_id,
        "market_id": body.market_id,
        "side": body.side,
        "stake": body.stake,
        "status": "active",
    }).execute()

    # Update market pools and recalculate price
    new_yes = market["yes_pool"] + (body.stake if body.side == "yes" else 0)
    new_no  = market["no_pool"]  + (body.stake if body.side == "no"  else 0)
    total   = new_yes + new_no
    yes_price = round(new_yes / total, 4) if total > 0 else 0.5
    no_price  = round(new_no  / total, 4) if total > 0 else 0.5

    supabase.table("markets").update({
        "yes_pool": new_yes,
        "no_pool": new_no,
        "yes_price": yes_price,
        "no_price":  no_price,
        "total_volume": market["total_volume"] + body.stake,
    }).eq("id", body.market_id).execute()

    # Record price history snapshot
    supabase.table("price_history").insert({
        "market_id": body.market_id,
        "yes_price": yes_price,
        "no_price": no_price,
    }).execute()

    # Log transaction
    supabase.table("transactions").insert({
        "user_id": user_id,
        "type": "trade",
        "amount": -body.stake,
        "status": "completed",
        "notes": f"Staked ₹{body.stake} on {body.side.upper()} — {market['title']}",
    }).execute()

    # Broadcast real-time odds update
    await manager.broadcast_to_market(body.market_id, json.dumps({
        "type": "odds_update",
        "market_id": body.market_id,
        "yes_price": yes_price,
        "no_price": no_price,
        "yes_pool": new_yes,
        "no_pool": new_no,
        "total_volume": market["total_volume"] + body.stake,
    }))

    return {
        "message": f"Successfully staked ₹{body.stake} on {body.side.upper()}",
        "order": order_result.data[0],
        "new_balance": balance - body.stake,
        "yes_price": yes_price,
        "no_price": no_price,
        "yes_pool": new_yes,
        "no_pool": new_no,
        "total_volume": market["total_volume"] + body.stake,
    }


@router.get("/my")
async def my_orders(current_user: dict = Depends(get_current_user)):
    orders = supabase.table("orders").select("*, markets(title, status, outcome, category)").eq("user_id", current_user["sub"]).order("created_at", desc=True).execute()
    return orders.data
