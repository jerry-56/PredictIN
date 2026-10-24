-- ============================================================
-- PredictIN — Supabase SQL Schema
-- Run this in Supabase SQL Editor (Dashboard > SQL Editor)
-- ============================================================

-- ── Users ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            TEXT NOT NULL,
  email           TEXT UNIQUE NOT NULL,
  password_hash   TEXT NOT NULL, -- legacy column; new accounts use a fixed non-secret marker
  wallet_balance  NUMERIC(12,2) DEFAULT 0.00,
  is_admin        BOOLEAN DEFAULT FALSE,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Markets ──────────────────────────────────────────────────
CREATE TYPE market_status AS ENUM ('open', 'closed', 'resolved', 'voided');
CREATE TYPE market_category AS ENUM ('cricket', 'politics', 'finance', 'entertainment', 'other');

CREATE TABLE IF NOT EXISTS markets (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title             TEXT NOT NULL,
  description       TEXT,
  category          market_category NOT NULL,
  end_date          TIMESTAMPTZ NOT NULL,
  yes_pool          NUMERIC(12,2) DEFAULT 0.00,
  no_pool           NUMERIC(12,2) DEFAULT 0.00,
  yes_price         NUMERIC(6,4) DEFAULT 0.5000,
  no_price          NUMERIC(6,4) DEFAULT 0.5000,
  total_volume      NUMERIC(12,2) DEFAULT 0.00,
  status            market_status DEFAULT 'open',
  outcome           TEXT,           -- 'yes' or 'no' after resolve
  cricapi_match_id  TEXT,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- ── Orders ───────────────────────────────────────────────────
CREATE TYPE order_status AS ENUM ('active', 'won', 'lost', 'refunded');

CREATE TABLE IF NOT EXISTS orders (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
  market_id   UUID REFERENCES markets(id) ON DELETE CASCADE,
  side        TEXT CHECK (side IN ('yes','no')) NOT NULL,
  stake       NUMERIC(12,2) NOT NULL,
  payout      NUMERIC(12,2),
  status      order_status DEFAULT 'active',
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Transactions ─────────────────────────────────────────────
CREATE TYPE txn_type AS ENUM ('deposit', 'trade', 'payout', 'refund', 'withdrawal');

CREATE TABLE IF NOT EXISTS transactions (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               UUID REFERENCES users(id) ON DELETE CASCADE,
  type                  txn_type NOT NULL,
  amount                NUMERIC(12,2) NOT NULL,
  status                TEXT DEFAULT 'completed',
  notes                 TEXT,
  razorpay_order_id     TEXT,
  razorpay_payment_id   TEXT,
  created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ── Price History ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS price_history (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  market_id    UUID REFERENCES markets(id) ON DELETE CASCADE,
  yes_price    NUMERIC(6,4),
  no_price     NUMERIC(6,4),
  recorded_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Platform Wallet ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS platform_wallet (
  id              INT PRIMARY KEY DEFAULT 1,        -- singleton row
  total_revenue   NUMERIC(14,2) DEFAULT 0.00,
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO platform_wallet (id, total_revenue) VALUES (1, 0) ON CONFLICT DO NOTHING;

-- ============================================================
-- RPCs (atomic wallet operations to prevent race conditions)
-- ============================================================

CREATE OR REPLACE FUNCTION credit_wallet(p_user_id UUID, p_amount NUMERIC)
RETURNS VOID AS $$
BEGIN
  UPDATE users SET wallet_balance = wallet_balance + p_amount WHERE id = p_user_id;
END;
$$ LANGUAGE plpgsql;

CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_razorpay_order_id
  ON transactions(razorpay_order_id)
  WHERE razorpay_order_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_razorpay_payment_id
  ON transactions(razorpay_payment_id)
  WHERE razorpay_payment_id IS NOT NULL;

CREATE OR REPLACE FUNCTION complete_wallet_deposit(
  p_order_id TEXT,
  p_payment_id TEXT,
  p_amount_paise BIGINT,
  p_currency TEXT
)
RETURNS BOOLEAN AS $$
DECLARE
  v_txn transactions%ROWTYPE;
BEGIN
  SELECT * INTO v_txn
    FROM transactions
    WHERE razorpay_order_id = p_order_id AND type = 'deposit'
    FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Deposit order not found';
  END IF;

  IF p_payment_id IS NULL OR p_payment_id = ''
    OR p_amount_paise IS NULL OR p_amount_paise <= 0
    OR p_currency IS DISTINCT FROM 'INR'
    OR v_txn.amount * 100 <> p_amount_paise THEN
    RAISE EXCEPTION 'Payment does not match the deposit';
  END IF;

  IF v_txn.status = 'completed' THEN
    IF v_txn.razorpay_payment_id = p_payment_id THEN
      RETURN FALSE;
    END IF;
    RAISE EXCEPTION 'Deposit was completed with a different payment';
  END IF;

  IF v_txn.status <> 'pending' THEN
    RAISE EXCEPTION 'Deposit is not pending';
  END IF;

  UPDATE transactions
    SET status = 'completed', razorpay_payment_id = p_payment_id
    WHERE id = v_txn.id;

  UPDATE users
    SET wallet_balance = COALESCE(wallet_balance, 0) + v_txn.amount
    WHERE id = v_txn.user_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Wallet owner not found';
  END IF;

  RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION debit_wallet(p_user_id UUID, p_amount NUMERIC)
RETURNS VOID AS $$
BEGIN
  UPDATE users
    SET wallet_balance = wallet_balance - p_amount
    WHERE id = p_user_id AND wallet_balance >= p_amount;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Insufficient balance';
  END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION credit_platform_wallet(p_amount NUMERIC)
RETURNS VOID AS $$
BEGIN
  UPDATE platform_wallet SET total_revenue = total_revenue + p_amount, updated_at = NOW() WHERE id = 1;
END;
$$ LANGUAGE plpgsql;

-- ── Indexes ───────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_orders_market    ON orders(market_id);
CREATE INDEX IF NOT EXISTS idx_orders_user      ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_txns_user        ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_price_market     ON price_history(market_id);
CREATE INDEX IF NOT EXISTS idx_markets_status   ON markets(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_markets_cricapi_match_id ON markets(cricapi_match_id) WHERE cricapi_match_id IS NOT NULL;


-- ── Decentro Payment Gateway ─────────────────────────────────
ALTER TABLE transactions 
  ADD COLUMN IF NOT EXISTS reference_id TEXT,
  ADD COLUMN IF NOT EXISTS decentro_txn_id TEXT,
  ADD COLUMN IF NOT EXISTS bank_reference_number TEXT,
  ADD COLUMN IF NOT EXISTS payment_gateway TEXT DEFAULT 'decentro';

CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_reference_id
  ON transactions(reference_id)
  WHERE reference_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_decentro_txn_id
  ON transactions(decentro_txn_id)
  WHERE decentro_txn_id IS NOT NULL;

CREATE OR REPLACE FUNCTION complete_decentro_deposit(
  p_reference_id TEXT,
  p_decentro_txn_id TEXT,
  p_bank_ref TEXT,
  p_amount NUMERIC
)
RETURNS BOOLEAN AS $$
DECLARE
  v_txn transactions%ROWTYPE;
BEGIN
  SELECT * INTO v_txn
    FROM transactions
    WHERE (
      (p_reference_id IS NOT NULL AND reference_id = p_reference_id)
      OR (p_decentro_txn_id IS NOT NULL AND decentro_txn_id = p_decentro_txn_id)
    )
    AND type = 'deposit'
    FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Deposit transaction not found';
  END IF;

  IF p_amount IS NOT NULL AND v_txn.amount <> p_amount THEN
    RAISE EXCEPTION 'Payment amount does not match deposit';
  END IF;

  IF v_txn.status = 'completed' THEN
    RETURN FALSE;
  END IF;

  IF v_txn.status <> 'pending' THEN
    RAISE EXCEPTION 'Deposit is not pending';
  END IF;

  UPDATE transactions
    SET status = 'completed',
        decentro_txn_id = COALESCE(p_decentro_txn_id, decentro_txn_id),
        bank_reference_number = COALESCE(p_bank_ref, bank_reference_number)
    WHERE id = v_txn.id;

  UPDATE users
    SET wallet_balance = COALESCE(wallet_balance, 0) + v_txn.amount
    WHERE id = v_txn.user_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Wallet owner not found';
  END IF;

  RETURN TRUE;
END;
$$ LANGUAGE plpgsql;
