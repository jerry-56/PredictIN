import hashlib
import hmac
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from starlette.requests import Request
from routes import wallet
from schemas import DepositRequest, DepositVerifyRequest


class FakeQuery:
    def __init__(self, record):
        self.record = record

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def ilike(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def update(self, *_args, **_kwargs):
        return self

    def insert(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=[self.record] if self.record else [])


class FakeSupabase:
    def __init__(self, transaction, rpc_result=True):
        self.transaction = transaction
        self.rpc_result = rpc_result
        self.rpc_name = None
        self.rpc_params = None

    def table(self, _table_name):
        return FakeQuery(self.transaction)

    def rpc(self, name, params):
        self.rpc_name = name
        self.rpc_params = params
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.rpc_result))


class WalletPaymentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user_id = "user-123"
        self.order_id = "order_123"
        self.payment_id = "pay_123"
        self.reference_id = "DEP_1700000000_ABC123"
        self.decentro_txn_id = "DECENTRO_TXN_999"
        self.secret = "gateway-secret"

        self.transaction = {
            "id": "txn-123",
            "user_id": self.user_id,
            "type": "deposit",
            "amount": 500,
            "status": "pending",
            "reference_id": self.reference_id,
            "decentro_txn_id": self.decentro_txn_id,
            "razorpay_order_id": self.order_id,
        }

    def test_deposit_amounts_are_limited_to_supported_values(self):
        self.assertEqual(DepositRequest(amount=500).amount, 500)
        self.assertEqual(DepositRequest(amount=1000).amount, 1000)
        with self.assertRaises(ValueError):
            DepositRequest(amount=750)

    async def test_decentro_deposit_creates_pending_txn_and_returns_link(self):
        database = FakeSupabase(self.transaction)
        mock_decentro_res = {
            "status": "success",
            "reference_id": self.reference_id,
            "decentro_txn_id": self.decentro_txn_id,
            "amount": 500,
            "currency": "INR",
            "payment_link": "https://in.decentro.tech/pay/test1234",
            "upi_uri": "upi://pay?pa=test@yesbank",
            "encoded_dynamic_qr_code": "iVBORw0KGgo...",
            "psp_uri": {"gpay": "upi://pay?pa=test@yesbank"},
        }

        with (
            patch.object(wallet, "supabase", database),
            patch.object(wallet.decentro_client, "is_configured", return_value=True),
            patch.object(wallet.decentro_client, "create_upi_collection_link", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_decentro_res
            result = await wallet.create_deposit(
                DepositRequest(amount=500),
                {"sub": self.user_id, "name": "John Doe", "email": "john@example.com"},
            )

        self.assertEqual(result["gateway"], "decentro")
        self.assertEqual(result["amount"], 500)
        self.assertEqual(result["payment_link"], "https://in.decentro.tech/pay/test1234")
        self.assertEqual(result["upi_uri"], "upi://pay?pa=test@yesbank")

    async def test_decentro_status_check_completes_when_live_status_success(self):
        database = FakeSupabase(self.transaction)
        with (
            patch.object(wallet, "supabase", database),
            patch.object(wallet.decentro_client, "is_configured", return_value=True),
            patch.object(
                wallet.decentro_client,
                "get_transaction_status",
                new_callable=AsyncMock,
                return_value={"status": "completed", "bank_reference_number": "BANK_12345"},
            ),
            patch.object(wallet, "_complete_decentro_deposit", return_value=True) as mock_complete,
        ):
            result = await wallet.check_deposit_status(
                self.reference_id,
                {"sub": self.user_id},
            )

        self.assertEqual(result["status"], "completed")
        mock_complete.assert_called_once()

    async def test_decentro_callback_acknowledges_with_cb_s00000(self):
        database = FakeSupabase(self.transaction)
        payload = {
            "transaction_status": "SUCCESS",
            "reference_id": self.reference_id,
            "decentro_txn_id": self.decentro_txn_id,
            "bank_reference_number": "BANK_REF_9876",
            "transaction_amount": 500,
        }
        body_bytes = json.dumps(payload).encode()

        async def receive():
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        req = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/wallet/decentro/callback",
                "headers": [(b"content-type", b"application/json")],
            },
            receive,
        )

        with (
            patch.object(wallet, "supabase", database),
            patch.object(wallet, "_complete_decentro_deposit", return_value=True) as mock_complete,
        ):
            res = await wallet.payment_webhook(req)

        self.assertEqual(res, {"response_code": "CB_S00000"})
        mock_complete.assert_called_once_with(
            reference_id=self.reference_id,
            decentro_txn_id=self.decentro_txn_id,
            bank_ref="BANK_REF_9876",
            amount=500.0,
        )

    async def test_razorpay_verify_still_works_as_fallback(self):
        database = FakeSupabase(self.transaction)
        payment = {
            "id": self.payment_id,
            "order_id": self.order_id,
            "amount": 50000,
            "currency": "INR",
            "status": "captured",
        }
        signature = hmac.new(
            self.secret.encode(),
            f"{self.order_id}|{self.payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        body = DepositVerifyRequest(
            razorpay_order_id=self.order_id,
            razorpay_payment_id=self.payment_id,
            razorpay_signature=signature,
        )
        client = SimpleNamespace(payment=SimpleNamespace(fetch=Mock(return_value=payment)))

        with (
            patch.object(wallet, "supabase", database),
            patch.object(wallet, "_razorpay_credentials", return_value=("rzp_test", self.secret)),
            patch.object(wallet, "_razorpay_client", return_value=client),
            patch.object(wallet, "_complete_deposit", return_value=True),
        ):
            result = await wallet.verify_deposit(body, {"sub": self.user_id})

        self.assertEqual(result, {"status": "completed"})


if __name__ == "__main__":
    unittest.main()
