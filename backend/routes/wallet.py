import os
import hmac
import hashlib
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Request, Depends, status
import razorpay

from database import supabase
from auth import get_current_user
from schemas import DepositRequest, DepositVerifyRequest, DEPOSIT_AMOUNTS
from decentro_client import decentro_client

logger = logging.getLogger("wallet")

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


# ── Razorpay Helpers ──────────────────────────────────────────────────────────

def _razorpay_credentials():
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret or key_id.startswith("placeholder") or key_id.startswith("rzp_test_placeholder"):
        return None, None
    return key_id, key_secret


def _razorpay_client():
    key_id, key_secret = _razorpay_credentials()
    if not key_id or not key_secret:
        raise HTTPException(status_code=503, detail="Razorpay is not configured with valid keys")
    return razorpay.Client(auth=(key_id, key_secret))


def _complete_deposit(order_id: str, payment_id: str, amount_paise: int, currency: str):
    """Complete deposit using legacy Razorpay RPC or table update."""
    try:
        result = supabase.rpc("complete_wallet_deposit", {
            "p_order_id": order_id,
            "p_payment_id": payment_id,
            "p_amount_paise": amount_paise,
            "p_currency": currency,
        }).execute()
        return result.data is True
    except Exception as exc:
        logger.warning("complete_wallet_deposit RPC failed (%s), falling back to direct update", exc)
        txn_res = supabase.table("transactions").select("*").eq("razorpay_order_id", order_id).eq("type", "deposit").execute()
        if not txn_res.data:
            return False
        txn = txn_res.data[0]
        if txn.get("status") == "completed":
            return True
        supabase.table("transactions").update({
            "status": "completed",
            "razorpay_payment_id": payment_id,
        }).eq("id", txn["id"]).execute()
        supabase.table("users").update({
            "wallet_balance": (txn.get("amount") or 0)
        }).eq("id", txn["user_id"]).execute()
        return True


# ── Decentro Helpers ──────────────────────────────────────────────────────────

def _complete_decentro_deposit(
    reference_id: str,
    decentro_txn_id: Optional[str] = None,
    bank_ref: Optional[str] = None,
    amount: Optional[float] = None,
) -> bool:
    """
    Atomically complete deposit and credit user's wallet.
    Tries the atomic RPC complete_decentro_deposit, with safe fallback.
    """
    try:
        result = supabase.rpc("complete_decentro_deposit", {
            "p_reference_id": reference_id,
            "p_decentro_txn_id": decentro_txn_id,
            "p_bank_ref": bank_ref,
            "p_amount": amount,
        }).execute()
        return result.data is True
    except Exception as exc:
        logger.warning("complete_decentro_deposit RPC failed (%s); attempting fallback", exc)
        # Fallback if RPC is not yet executed in Supabase SQL editor
        query = supabase.table("transactions").select("*").eq("reference_id", reference_id).eq("type", "deposit").execute()
        if not query.data and decentro_txn_id:
            query = supabase.table("transactions").select("*").eq("decentro_txn_id", decentro_txn_id).eq("type", "deposit").execute()

        if not query.data:
            logger.error("Deposit transaction not found for reference_id: %s", reference_id)
            return False

        txn = query.data[0]
        if txn.get("status") == "completed":
            return False  # Already processed

        user_id = txn["user_id"]
        txn_amount = float(txn["amount"])

        # Update transaction
        update_data = {"status": "completed"}
        if decentro_txn_id:
            update_data["decentro_txn_id"] = decentro_txn_id
        if bank_ref:
            update_data["bank_reference_number"] = bank_ref
        supabase.table("transactions").update(update_data).eq("id", txn["id"]).execute()

        # Update user wallet balance
        user_res = supabase.table("users").select("wallet_balance").eq("id", user_id).execute()
        current_bal = float(user_res.data[0]["wallet_balance"] or 0) if user_res.data else 0.0
        new_bal = current_bal + txn_amount
        supabase.table("users").update({"wallet_balance": new_bal}).eq("id", user_id).execute()
        return True


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/balance")
async def get_balance(current_user: dict = Depends(get_current_user)):
    user = supabase.table("users").select("wallet_balance").eq("id", current_user["sub"]).execute()
    txns = (
        supabase.table("transactions")
        .select("*")
        .eq("user_id", current_user["sub"])
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    balance = user.data[0]["wallet_balance"] if user.data else 0.0
    return {"balance": balance, "transactions": txns.data or []}


@router.post("/deposit")
async def create_deposit(body: DepositRequest, current_user: dict = Depends(get_current_user)):
    """
    Initiates a deposit.
    Primary gateway: Decentro UPI (Dynamic QR, Payment Link, and UPI intent deep links).
    Fallback gateway: Razorpay (if configured).
    """
    if body.amount not in DEPOSIT_AMOUNTS:
        raise HTTPException(status_code=400, detail=f"Amount must be one of {DEPOSIT_AMOUNTS}")

    user_id = current_user["sub"]
    user_name = current_user.get("name", "PredictIN User")
    user_email = current_user.get("email", "")

    # Decentro Gateway (Primary)
    if decentro_client.is_configured():
        # Generate clean, unique reference ID: DEP_<timestamp>_<short_uuid>
        ts = int(datetime.now(timezone.utc).timestamp())
        short_id = uuid.uuid4().hex[:6].upper()
        reference_id = f"DEP_{ts}_{short_id}"

        # Record pending transaction in Supabase
        try:
            supabase.table("transactions").insert({
                "user_id": user_id,
                "type": "deposit",
                "amount": body.amount,
                "status": "pending",
                "reference_id": reference_id,
                "payment_gateway": "decentro",
                "notes": f"Deposit ₹{body.amount} via UPI",
            }).execute()
        except Exception as exc:
            # If reference_id column doesn't exist yet, insert without it
            logger.warning("Insert with reference_id failed (%s); trying standard insert", exc)
            supabase.table("transactions").insert({
                "user_id": user_id,
                "type": "deposit",
                "amount": body.amount,
                "status": "pending",
                "notes": f"Deposit ₹{body.amount} via UPI (Ref: {reference_id})",
            }).execute()

        # Call Decentro UPI Collections API
        try:
            decentro_res = await decentro_client.create_upi_collection_link(
                reference_id=reference_id,
                amount=float(body.amount),
                purpose_message=f"PredictIN ₹{body.amount} Deposit",
                payer_name=user_name,
                payer_email=user_email,
            )

            decentro_txn_id = decentro_res.get("decentro_txn_id", "")
            active_ref = decentro_res.get("reference_id") or reference_id
            if decentro_txn_id or active_ref != reference_id:
                try:
                    update_data = {}
                    if decentro_txn_id:
                        update_data["decentro_txn_id"] = decentro_txn_id
                    if active_ref != reference_id:
                        update_data["reference_id"] = active_ref
                    supabase.table("transactions").update(update_data).eq("reference_id", reference_id).execute()
                except Exception:
                    pass

            return {
                "gateway": "decentro",
                "reference_id": active_ref,
                "decentro_txn_id": decentro_txn_id,
                "amount": body.amount,
                "currency": "INR",
                "payment_link": decentro_res.get("payment_link") or "",
                "upi_uri": decentro_res.get("upi_uri") or "",
                "encoded_dynamic_qr_code": decentro_res.get("encoded_dynamic_qr_code") or "",
                "psp_uri": decentro_res.get("psp_uri") or {},
                "message": "UPI payment generated successfully. Scan QR or open UPI app.",
            }

        except Exception as exc:
            logger.error("Failed to generate Decentro UPI link: %s", exc)
            # Mark transaction failed so it doesn't linger
            try:
                supabase.table("transactions").update({"status": "failed"}).eq("reference_id", reference_id).execute()
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not initiate Decentro payment: {str(exc)}",
            )

    # Razorpay Gateway (Fallback if Decentro is not configured)
    key_id, _ = _razorpay_credentials()
    if key_id:
        try:
            order = _razorpay_client().order.create({
                "amount": body.amount * 100,
                "currency": "INR",
                "notes": {"user_id": user_id},
            })
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Could not create Razorpay order")

        supabase.table("transactions").insert({
            "user_id": user_id,
            "type": "deposit",
            "amount": body.amount,
            "status": "pending",
            "razorpay_order_id": order["id"],
            "payment_gateway": "razorpay",
        }).execute()

        return {
            "gateway": "razorpay",
            "razorpay_order_id": order["id"],
            "razorpay_key": key_id,
            "amount_paise": order["amount"],
            "currency": order["currency"],
        }

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Payment gateway is not configured. Please check backend credentials in .env.",
    )


@router.get("/deposit/status/{reference_id}")
async def check_deposit_status(reference_id: str, current_user: dict = Depends(get_current_user)):
    """
    Check the status of a pending deposit.
    Queries the database and performs live Decentro status inquiry if still pending.
    """
    user_id = current_user["sub"]

    # 1. Fetch transaction from database
    txn_res = (
        supabase.table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .eq("reference_id", reference_id)
        .execute()
    )

    if not txn_res.data:
        # Fallback query if notes contains reference_id
        txn_res = (
            supabase.table("transactions")
            .select("*")
            .eq("user_id", user_id)
            .ilike("notes", f"%{reference_id}%")
            .execute()
        )

    if not txn_res.data:
        raise HTTPException(status_code=404, detail="Deposit transaction not found")

    txn = txn_res.data[0]
    current_status = txn.get("status")

    if current_status == "completed":
        return {"status": "completed", "reference_id": reference_id, "amount": txn["amount"]}
    if current_status == "failed":
        return {"status": "failed", "reference_id": reference_id}

    # 2. If pending, query Decentro directly for live terminal status
    if decentro_client.is_configured():
        decentro_txn_id = txn.get("decentro_txn_id")
        check_res = await decentro_client.get_transaction_status(
            decentro_txn_id=decentro_txn_id,
            reference_id=reference_id,
        )

        if check_res.get("status") == "completed":
            bank_ref = check_res.get("bank_reference_number")
            _complete_decentro_deposit(
                reference_id=reference_id,
                decentro_txn_id=decentro_txn_id,
                bank_ref=bank_ref,
                amount=float(txn["amount"]),
            )
            return {"status": "completed", "reference_id": reference_id, "amount": txn["amount"]}
        elif check_res.get("status") == "failed":
            supabase.table("transactions").update({"status": "failed"}).eq("id", txn["id"]).execute()
            return {"status": "failed", "reference_id": reference_id}

    return {"status": "pending", "reference_id": reference_id}


@router.post("/deposit/verify")
async def verify_deposit(body: DepositVerifyRequest, current_user: dict = Depends(get_current_user)):
    """
    Verifies deposit manually from frontend.
    Handles Decentro reference verification or Razorpay signature verification.
    """
    # ── Decentro verification ──────────────────────────────────────────────
    if body.reference_id:
        status_res = await check_deposit_status(body.reference_id, current_user)
        return status_res

    # ── Razorpay verification (legacy) ─────────────────────────────────────
    if body.razorpay_order_id and body.razorpay_payment_id and body.razorpay_signature:
        _, key_secret = _razorpay_credentials()
        if not key_secret:
            raise HTTPException(status_code=503, detail="Razorpay is not configured")

        expected_signature = hmac.new(
            key_secret.encode(),
            f"{body.razorpay_order_id}|{body.razorpay_payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_signature, body.razorpay_signature):
            raise HTTPException(status_code=400, detail="Invalid payment signature")

        txn_result = (
            supabase.table("transactions")
            .select("*")
            .eq("razorpay_order_id", body.razorpay_order_id)
            .eq("user_id", current_user["sub"])
            .eq("type", "deposit")
            .execute()
        )
        if not txn_result.data:
            raise HTTPException(status_code=404, detail="Deposit order not found")
        txn = txn_result.data[0]

        try:
            payment = _razorpay_client().payment.fetch(body.razorpay_payment_id)
        except Exception:
            raise HTTPException(status_code=502, detail="Could not verify payment with Razorpay")

        amount_paise = payment.get("amount")
        if payment.get("status") != "captured":
            return {"status": "pending"}

        completed = _complete_deposit(
            body.razorpay_order_id,
            body.razorpay_payment_id,
            amount_paise,
            payment.get("currency", "INR"),
        )
        return {"status": "completed" if completed else "already_processed"}

    raise HTTPException(status_code=400, detail="Missing payment reference or signature")


# ── Webhook / Callback ────────────────────────────────────────────────────────

@router.post("/decentro/callback")
@router.post("/webhook")
async def payment_webhook(request: Request):
    """
    Receives automated payment confirmation callbacks from payment gateways.
    Supports both Decentro Terminal Transaction Status Callbacks and Razorpay webhooks.
    Always acknowledges Decentro with {"response_code": "CB_S00000"}.
    """
    body_bytes = await request.body()
    headers = request.headers

    # ── 1. Check if Decentro Callback ─────────────────────────────────────────
    # Decentro sends X-Signature or standard JSON payload with transaction_status
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    # Check for Decentro callback signature / payload markers
    is_decentro = (
        "transaction_status" in payload
        or "callback_txn_id" in payload
        or "consumer_urn" in payload
        or "decentro_txn_id" in payload
        or request.url.path.endswith("/decentro/callback")
    )

    if is_decentro:
        # Verify signature if secret configured
        signature = headers.get("x-signature") or headers.get("x-decentro-signature") or ""
        if not decentro_client.verify_webhook_signature(body_bytes, signature):
            logger.warning("Invalid Decentro webhook signature")
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

        txn_status = (payload.get("transaction_status") or payload.get("status") or "").upper()
        reference_id = payload.get("reference_id")
        decentro_txn_id = payload.get("decentro_txn_id")
        bank_ref = payload.get("bank_reference_number")
        amount = payload.get("transaction_amount") or payload.get("amount")

        if txn_status in ("SUCCESS", "COMPLETED"):
            logger.info("Decentro deposit successful for ref=%s, txn=%s", reference_id, decentro_txn_id)
            if reference_id or decentro_txn_id:
                _complete_decentro_deposit(
                    reference_id=reference_id,
                    decentro_txn_id=decentro_txn_id,
                    bank_ref=bank_ref,
                    amount=float(amount) if amount else None,
                )

        # Decentro mandatory acknowledgment response code
        return {"response_code": "CB_S00000"}

    # ── 2. Check if Razorpay Webhook ──────────────────────────────────────────
    webhook_secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    signature = headers.get("X-Razorpay-Signature", "")
    if webhook_secret and signature:
        expected = hmac.new(webhook_secret.encode(), body_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

        if payload.get("event") == "payment.captured":
            payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
            order_id = payment.get("order_id")
            payment_id = payment.get("id")
            amount_paise = payment.get("amount")
            currency = payment.get("currency", "INR")
            if order_id and payment_id:
                _complete_deposit(order_id, payment_id, amount_paise, currency)
                return {"status": "completed"}

    return {"status": "ignored"}


@router.post("/withdraw")
async def withdraw(current_user: dict = Depends(get_current_user)):
    """Placeholder: manual withdrawals handled by admin for MVP."""
    raise HTTPException(status_code=503, detail="Withdrawals are processed manually. Contact support@predictin.in")
