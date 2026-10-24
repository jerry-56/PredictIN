import os
import hmac
import hashlib
import logging
from typing import Optional, Dict, Any, List
import httpx

logger = logging.getLogger("decentro")


class DecentroClient:
    """
    Client for Decentro Banking & Payments APIs (UPI Collections / Dynamic QR / Links).
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        consumer_urn: Optional[str] = None,
        payments_module_secret: Optional[str] = None,
        core_banking_module_secret: Optional[str] = None,
        provider_secret: Optional[str] = None,
        payee_account: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.client_id = (client_id or os.environ.get("DECENTRO_CLIENT_ID", "")).strip()
        self.client_secret = (client_secret or os.environ.get("DECENTRO_CLIENT_SECRET", "")).strip()
        self.consumer_urn = (consumer_urn or os.environ.get("DECENTRO_CONSUMER_URN", "")).strip()
        self.payments_module_secret = (payments_module_secret or os.environ.get("DECENTRO_PAYMENTS_MODULE_SECRET", "")).strip()
        self.core_banking_module_secret = (core_banking_module_secret or os.environ.get("DECENTRO_CORE_BANKING_MODULE_SECRET", "")).strip()
        self.provider_secret = (provider_secret or os.environ.get("DECENTRO_YBL_PROVIDER_SECRET", "")).strip()
        self.payee_account = (payee_account or os.environ.get("DECENTRO_PAYEE_ACCOUNT", "")).strip()
        
        env_base = os.environ.get("DECENTRO_BASE_URL", "").strip()
        if env_base:
            self.base_url = env_base.rstrip("/")
        else:
            self.base_url = "https://staging.api.decentro.tech"

    def is_configured(self) -> bool:
        """Check if Decentro credentials are present."""
        return bool(
            self.client_id
            and self.client_secret
            and not self.client_id.startswith("placeholder")
        )

    def get_headers(
        self,
        module_secret: Optional[str] = None,
        include_provider: bool = False,
    ) -> Dict[str, str]:
        """Standard Decentro API headers."""
        headers = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if module_secret:
            headers["module_secret"] = module_secret
        if include_provider and self.provider_secret:
            headers["provider_secret"] = self.provider_secret

        return headers

    def _get_candidate_endpoints(self) -> List[str]:
        """Returns candidate collection endpoints prioritizing the V3 API."""
        return [
            "https://staging.api.decentro.tech/v3/payments/upi/link",
            "https://staging.api.decentro.tech/v3/payments/upi/qr",
            "https://in.staging.decentro.tech/v2/payments/upi/link",
            "https://in.staging.decentro.tech/v2/payments/collection",
            "https://api.decentro.tech/v3/payments/upi/link",
            "https://api.decentro.tech/v3/payments/upi/qr",
            "https://in.decentro.tech/v2/payments/upi/link",
        ]

    async def create_upi_collection_link(
        self,
        reference_id: str,
        amount: float,
        purpose_message: str = "PredictIN Deposit",
        payer_name: str = "",
        payer_email: str = "",
        payer_mobile: str = "",
        payer_upi: str = "",
        expiry_minutes: int = 15,
    ) -> Dict[str, Any]:
        """
        Generates a dynamic UPI payment link, intent deep links (GPay, PhonePe, Paytm),
        and QR code payload from Decentro.
        """
        if not self.is_configured():
            raise RuntimeError("Decentro payment gateway is not configured with credentials in backend/.env")

        base_payload: Dict[str, Any] = {
            "reference_id": reference_id,
            "amount": float(amount),
            "currency": "INR",
            "purpose_message": (purpose_message or "PredictIN Deposit")[:40],
            "generate_uri": 1,
            "generate_psp_uri": True,
            "expiry_time": expiry_minutes,
        }

        # Consumer URN
        if self.consumer_urn:
            base_payload["consumer_urn"] = self.consumer_urn

        # Payee Account
        if self.payee_account:
            base_payload["payee_account"] = self.payee_account

        # Payer UPI
        if payer_upi:
            base_payload["payer_upi"] = payer_upi

        # Note: In Decentro V3 collections, `payer_details` is exclusively a list
        # of allowed bank accounts used for TPV (Third Party Validation).
        # We do not pass it for standard ad-hoc customer collections.

        candidate_endpoints = self._get_candidate_endpoints()
        attempt_details: List[str] = []

        # Try without module_secret first (standard V3 stack), then with module_secret
        header_variants = [
            (None, False),                          # Standard V3: client_id + client_secret
            (self.payments_module_secret, False),   # V3/V2 with payments module secret
            (self.payments_module_secret, True),    # With provider secret
            (self.core_banking_module_secret, True),# Core banking with provider secret
        ]

        attempt_idx = 0
        async with httpx.AsyncClient(timeout=15.0) as client:
            for mod_secret, include_prov in header_variants:
                headers = self.get_headers(module_secret=mod_secret, include_provider=include_prov)

                for url in candidate_endpoints:
                    attempt_idx += 1
                    active_ref_id = reference_id if attempt_idx == 1 else f"{reference_id}_{attempt_idx}"
                    req_payload = dict(base_payload)
                    req_payload["reference_id"] = active_ref_id

                    try:
                        resp = await client.post(url, headers=headers, json=req_payload)
                        resp_text = resp.text.strip()
                        
                        if resp.status_code in (200, 201):
                            data = resp.json()
                            api_status = str(data.get("api_status") or data.get("status") or "").upper()
                            if api_status == "FAILURE":
                                err_msg = data.get("message") or data.get("response_message") or "API reported failure"
                                attempt_details.append(f"{url} -> HTTP {resp.status_code} FAILURE: {err_msg}")
                                continue

                            res_data = data.get("data") if isinstance(data.get("data"), dict) else {}

                            decentro_txn_id = (
                                data.get("decentro_txn_id")
                                or data.get("decentroTxnId")
                                or res_data.get("decentro_txn_id")
                                or res_data.get("decentroTxnId")
                                or res_data.get("transaction_id")
                                or ""
                            )

                            # Decentro V3 returns app links and common URL under `upi_uris`
                            upi_uris = {}
                            if isinstance(data.get("upi_uris"), dict):
                                upi_uris.update(data["upi_uris"])
                            if isinstance(res_data.get("upi_uris"), dict):
                                upi_uris.update(res_data["upi_uris"])
                            if isinstance(res_data.get("psp_uri"), dict):
                                upi_uris.update(res_data["psp_uri"])
                            if isinstance(data.get("psp_uri"), dict):
                                upi_uris.update(data["psp_uri"])
                            if isinstance(res_data.get("upi_uri"), dict):
                                upi_uris.update(res_data["upi_uri"])

                            # Primary payment link / hosted checkout link
                            payment_link = (
                                upi_uris.get("common_uri")
                                or res_data.get("payment_link")
                                or res_data.get("shortened_url")
                                or res_data.get("short_url")
                                or res_data.get("link")
                                or res_data.get("payment_url")
                                or data.get("payment_link")
                                or data.get("link")
                                or ""
                            )

                            # Universal UPI URI or Intent deep link
                            raw_upi_uri = res_data.get("upi_uri") or data.get("upi_uri")
                            intent_url = res_data.get("intent_url") or data.get("intent_url") or ""

                            upi_uri = (
                                intent_url
                                or upi_uris.get("common_uri")
                                or (raw_upi_uri if isinstance(raw_upi_uri, str) else "")
                                or upi_uris.get("generic")
                                or upi_uris.get("gpay")
                                or (next(iter(upi_uris.values())) if upi_uris else "")
                                or payment_link
                            )

                            if not payment_link and upi_uri:
                                payment_link = upi_uri

                            # Base64 Dynamic QR Code
                            encoded_qr = (
                                res_data.get("encoded_dynamic_qr_code")
                                or res_data.get("encoded_qr_code")
                                or res_data.get("qr_code")
                                or res_data.get("dynamic_qr")
                                or data.get("encoded_dynamic_qr_code")
                                or data.get("encoded_qr_code")
                                or data.get("qr_code")
                                or ""
                            )

                            logger.info(
                                "Decentro success: txn=%s link=%s uri=%s qr_len=%d",
                                decentro_txn_id,
                                payment_link,
                                upi_uri,
                                len(encoded_qr) if encoded_qr else 0,
                            )

                            return {
                                "status": "success",
                                "reference_id": active_ref_id,
                                "decentro_txn_id": str(decentro_txn_id),
                                "amount": amount,
                                "currency": "INR",
                                "payment_link": payment_link,
                                "upi_uri": str(upi_uri) if upi_uri else "",
                                "encoded_dynamic_qr_code": encoded_qr,
                                "psp_uri": upi_uris,
                                "raw": data,
                            }

                        # Route not found check
                        is_route_not_found = (
                            resp.status_code == 404
                            or "no handler found for uri" in resp_text.lower()
                            or "<title>404 not found</title>" in resp_text.lower()
                        )
                        if is_route_not_found:
                            continue

                        err_entry = f"{url} [mod={'yes' if mod_secret else 'no'}, prov={include_prov}] -> HTTP {resp.status_code}: {resp_text}"
                        attempt_details.append(err_entry)

                    except httpx.RequestError as exc:
                        attempt_details.append(f"{url} -> Connection error: {str(exc)}")

        full_log = "\n".join(attempt_details[:4]) if attempt_details else "No response from Decentro servers."
        raise RuntimeError(f"Decentro payment initiation failed:\n{full_log}")

    async def get_transaction_status(
        self,
        decentro_txn_id: Optional[str] = None,
        reference_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Queries Decentro to verify whether a transaction has succeeded, failed, or is pending.
        """
        if not self.is_configured():
            raise RuntimeError("Decentro payment gateway is not configured")

        status_hosts = [
            "https://staging.api.decentro.tech",
            "https://in.staging.decentro.tech",
            "https://api.decentro.tech",
            "https://in.decentro.tech",
        ]
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            for host in status_hosts:
                headers = self.get_headers(module_secret=self.payments_module_secret, include_provider=False)
                endpoints = []
                if decentro_txn_id:
                    endpoints.append(f"{host}/v3/payments/transaction/status?decentro_txn_id={decentro_txn_id}")
                    endpoints.append(f"{host}/v2/payments/transaction/{decentro_txn_id}/status")
                if reference_id:
                    endpoints.append(f"{host}/v3/payments/transaction/status?reference_id={reference_id}")
                    endpoints.append(f"{host}/v2/payments/transaction/status?reference_id={reference_id}")

                for url in endpoints:
                    try:
                        resp = await client.get(url, headers=headers)
                        if resp.status_code in (200, 201):
                            data = resp.json()
                            res_data = data.get("data") if isinstance(data.get("data"), dict) else {}
                            
                            # CRITICAL: In Decentro, `data["status"]` or `data["api_status"]` denotes
                            # the HTTP API request status (which is "SUCCESS" for any valid 200 HTTP call),
                            # NOT the financial payment status. The actual financial status is strictly
                            # located in `transaction_status` (e.g. "PENDING", "SUCCESS", "FAILURE").
                            raw_status = (
                                res_data.get("transaction_status")
                                or res_data.get("transactionStatus")
                                or data.get("transaction_status")
                                or data.get("transactionStatus")
                                or "PENDING"
                            ).upper()

                            normalized_status = "pending"
                            if raw_status in ("SUCCESS", "COMPLETED", "CAPTURED"):
                                normalized_status = "completed"
                            elif raw_status in ("FAILURE", "FAILED", "EXPIRED", "REJECTED"):
                                normalized_status = "failed"
                            else:
                                normalized_status = "pending"

                            bank_ref = (
                                res_data.get("bank_reference_number")
                                or data.get("bank_reference_number")
                                or ""
                            )
                            amount = res_data.get("amount") or data.get("amount")

                            return {
                                "status": normalized_status,
                                "raw_status": raw_status,
                                "bank_reference_number": bank_ref,
                                "amount": amount,
                                "raw": data,
                            }
                    except httpx.RequestError as exc:
                        logger.warning("Decentro status check failed on %s: %s", url, str(exc))

        return {"status": "pending", "message": "Unable to verify transaction with Decentro directly"}

    def verify_webhook_signature(self, raw_body: bytes, received_signature: str) -> bool:
        """
        Verifies Decentro HMAC-SHA256 signature if a webhook secret is configured.
        """
        webhook_secret = (
            os.environ.get("DECENTRO_WEBHOOK_SECRET")
            or os.environ.get("DECENTRO_CLIENT_SECRET")
            or ""
        )
        if not webhook_secret:
            return True

        expected_signature = hmac.new(
            webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_signature, received_signature or "")


# Singleton client
decentro_client = DecentroClient()
