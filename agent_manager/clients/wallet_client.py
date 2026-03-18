"""HTTP client for the NetworkChain wallet service."""

from __future__ import annotations

import logging
from typing import Any, Dict

import httpx

from ..config import settings

logger = logging.getLogger("agent_manager.clients.wallet_client")

TIMEOUT = 5.0  # seconds


class InsufficientBalanceError(Exception):
    """Raised when the user's wallet balance is too low."""

    def __init__(self, balance_cents: int = 0, message: str = ""):
        self.balance_cents = balance_cents
        super().__init__(message or f"Insufficient balance: {balance_cents} cents")


class DebtLimitReachedError(Exception):
    """Raised when the user's debt has hit the cap and they can't use agents."""

    def __init__(self, debt_cents: int = 0, message: str = ""):
        self.debt_cents = debt_cents
        super().__init__(message or f"Debt limit reached: {debt_cents} cents")


class WalletClient:
    """Async client that talks to NetworkChain's internal wallet endpoints."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        self.base_url = (base_url or settings.WALLET_SERVICE_URL).rstrip("/")
        self.api_key = api_key or settings.WALLET_INTERNAL_API_KEY
        self._headers = {"X-Internal-Api-Key": self.api_key}

    async def check_balance(self, user_id: str) -> Dict[str, Any]:
        """Return wallet balance and debt for a user. Raises on network errors."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{self.base_url}/wallet/internal/balance",
                params={"userId": user_id},
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def deduct_credits(
        self, user_id: str, amount_cents: int, description: str
    ) -> Dict[str, Any]:
        """Deduct credits with partial deduction + debt support.

        - Full balance covers it → deducted normally
        - Partial balance → drained to $0, remainder becomes debt
        - Debt at cap → raises DebtLimitReachedError
        """
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{self.base_url}/wallet/internal/deduct",
                json={
                    "userId": user_id,
                    "amountCents": amount_cents,
                    "description": description,
                },
                headers=self._headers,
            )

            if resp.status_code == 402:
                data = resp.json()
                error_type = data.get("error", "")
                if error_type == "debt_limit_reached":
                    raise DebtLimitReachedError(
                        debt_cents=data.get("debtCents", 0),
                        message=data.get("message", "Debt limit reached"),
                    )
                raise InsufficientBalanceError(
                    balance_cents=data.get("balanceCents", 0),
                    message=f"Insufficient balance: ${data.get('balanceDollars', '0.00')}",
                )

            resp.raise_for_status()
            return resp.json()
