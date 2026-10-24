---
title: PredictIN Backend
emoji: 🏏
colorFrom: green
colorTo: blue
sdk: docker
pinned: false
---

# PredictIN Backend

FastAPI prediction market backend. Set the following **Secrets** in your HF Space settings:

| Secret | Value |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Your Supabase service role key |
| `JWT_SECRET` | Random 32+ char string |
| `RAZORPAY_KEY_ID` | Razorpay Key ID |
| `RAZORPAY_KEY_SECRET` | Razorpay Key Secret |
| `RAZORPAY_WEBHOOK_SECRET` | Razorpay Webhook Secret |
| `CRICAPI_KEY` | CricAPI key (optional) |

Configure Razorpay Checkout to send the `payment.captured` event to
`/api/wallet/webhook`. For an existing Supabase database, run
`wallet_payment_migration.sql` in the Supabase SQL Editor before accepting
deposits. The migration makes the webhook and checkout callback share an
atomic, idempotent wallet-credit operation.

Sign-in and registration use Supabase Authentication. On first sign-in, the API creates a matching row in `public.users` using the Auth user ID. The existing `password_hash` column is retained only for compatibility with the current database schema; new passwords are stored only by Supabase Auth. Admin access comes from the `is_admin` field on the app profile, never from an email address.

## Automatic cricket markets

With a valid `CRICAPI_KEY`, the backend checks the provider's matches feed every six hours and creates markets for matches starting between 30 minutes and 14 days from now. It uses the match ID to avoid repeats. The provider key currently configured in this workspace is rejected as invalid, so replace it before relying on the import. For an existing database, run `cricapi_unique_index.sql` in the Supabase SQL Editor first to enforce duplicate protection across server instances.

Markets close at the scheduled start, and the order endpoint also rejects late entries. Results and payouts require manual admin review. The importer never creates user orders. Draws, ties, cancellations, or missing results should be voided and refunded after review.
