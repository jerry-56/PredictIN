# PredictIN frontend

React frontend for the PredictIN prediction market, using the FastAPI backend for authentication, markets, wallet balances, and transaction history.

## Run

```bash
npm install
npm run dev
```

Set `VITE_API_URL` to the backend base URL when it is not running at `http://localhost:7860`. Open the local URL printed by Vite.

## Wallet deposits

Razorpay Checkout is loaded by the frontend and payments are verified by the backend before funds are credited. Configure the Razorpay key ID, key secret, and webhook secret in the backend environment, point the Razorpay `payment.captured` webhook to `/api/wallet/webhook`, and apply [`wallet_payment_migration.sql`](../backend/wallet_payment_migration.sql) to an existing Supabase database before accepting deposits. Withdrawals are currently handled manually by support.

To check the production frontend bundle, run `npm run build`.
