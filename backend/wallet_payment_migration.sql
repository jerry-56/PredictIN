-- Apply once to an existing Supabase database before enabling wallet deposits.
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
