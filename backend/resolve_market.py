"""
Core profit engine for PredictIN.

Formula (published rules):
  winner_profit_pool = min(0.50 × winning_stakes, 0.90 × losing_stakes)
  platform_revenue   = losing_stakes − winner_profit_pool
  each_winner_gets   = stake + (stake / winning_stakes) × winner_profit_pool

Rounding: floor to nearest paisa (0.01). All remainder goes to platform.
"""

from typing import List, Dict
import math


MIN_POOL_EACH_SIDE = 100.0  # ₹100 minimum on each side to proceed


def resolve_market(
    outcome: str,  # "yes" or "no"
    orders: List[Dict],  # list of {"user_id", "side", "stake"}
) -> Dict:
    """
    Returns:
        {
          "payouts": [{"user_id": ..., "payout": ...}],
          "platform_revenue": float,
          "void": bool   # True if market must be refunded
        }
    """
    yes_orders = [o for o in orders if o["side"] == "yes"]
    no_orders  = [o for o in orders if o["side"] == "no"]

    yes_total = sum(o["stake"] for o in yes_orders)
    no_total  = sum(o["stake"] for o in no_orders)

    # Safety: void if either side below minimum
    if yes_total < MIN_POOL_EACH_SIDE or no_total < MIN_POOL_EACH_SIDE:
        return {
            "payouts": [{"user_id": o["user_id"], "payout": o["stake"]} for o in orders],
            "platform_revenue": 0.0,
            "void": True,
        }

    if outcome == "yes":
        winning_orders  = yes_orders
        winning_stakes  = yes_total
        losing_stakes   = no_total
    else:
        winning_orders  = no_orders
        winning_stakes  = no_total
        losing_stakes   = yes_total

    # Core formula
    winner_profit_pool = min(0.50 * winning_stakes, 0.90 * losing_stakes)

    # Calculate each winner's payout (floor to paisa)
    payouts = []
    total_paid = 0.0
    for order in winning_orders:
        profit_share = math.floor(
            (order["stake"] / winning_stakes) * winner_profit_pool * 100
        ) / 100
        payout = order["stake"] + profit_share
        payouts.append({"user_id": order["user_id"], "payout": payout})
        total_paid += payout

    # Platform revenue = losing pool − winner profit pool + rounding remainder
    intended_platform = losing_stakes - winner_profit_pool
    rounding_remainder = (winning_stakes + losing_stakes) - total_paid - intended_platform
    platform_revenue = round(intended_platform + rounding_remainder, 2)

    return {
        "payouts": payouts,
        "platform_revenue": platform_revenue,
        "void": False,
    }
