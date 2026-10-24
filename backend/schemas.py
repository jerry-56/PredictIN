from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, Literal
from datetime import datetime


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ── Market ────────────────────────────────────────────────────────────────────

class MarketCreate(BaseModel):
    title: str
    description: str
    category: Literal["cricket", "politics", "finance", "entertainment", "other"]
    end_date: datetime
    cricapi_match_id: Optional[str] = None   # for auto-resolution

class MarketResolve(BaseModel):
    outcome: Literal["yes", "no"]


# ── Orders ────────────────────────────────────────────────────────────────────

ALLOWED_STAKES = {500, 1000, 2000, 5000}

class OrderCreate(BaseModel):
    market_id: str
    side: Literal["yes", "no"]
    stake: float   # validated against market rules in route


# ── Wallet ────────────────────────────────────────────────────────────────────

DEPOSIT_AMOUNTS = [500, 1000, 2000, 5000]

class DepositRequest(BaseModel):
    amount: int = Field(gt=0)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, amount: int):
        if amount not in DEPOSIT_AMOUNTS:
            raise ValueError(f"Amount must be one of {DEPOSIT_AMOUNTS}")
        return amount

class DepositVerifyRequest(BaseModel):
    # Decentro fields
    reference_id: Optional[str] = None
    decentro_txn_id: Optional[str] = None

    # Razorpay fields (for backward compatibility)
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    razorpay_signature: Optional[str] = None
