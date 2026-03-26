"""Subscription billing service — manages agent monthly subscriptions."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..clients.wallet_client import WalletClient, InsufficientBalanceError, DebtLimitReachedError, get_wallet_client
from ..config import settings
from ..models.agent_subscription import AgentSubscription
from ..models.cron import CronOwnership
from ..repositories.subscription_repository import SubscriptionRepository
from ..repositories.wallet_transaction_repository import WalletTransactionRepository

logger = logging.getLogger("agent_manager.services.subscription_service")


class SubscriptionService:
    def __init__(self, db: Session):
        self.db = db
        self.sub_repo = SubscriptionRepository(db)
        self.txn_repo = WalletTransactionRepository(db)

    def _resolve_agent_name(self, agent_id: str) -> str:
        """Look up agent display name from the registry, falling back to agent_id."""
        try:
            from ..repositories.agent_registry_repository import AgentRegistryRepository
            agent = AgentRegistryRepository(self.db).get(agent_id)
            if agent and agent.name:
                return agent.name
        except Exception:
            pass
        return agent_id

    async def create_subscription(self, agent_id: str, org_id: str, user_id: str) -> AgentSubscription:
        """Charge the initial $24 and create a subscription record."""
        cost = settings.AGENT_MONTHLY_COST_CENTS
        wallet = get_wallet_client(agent_id)
        agent_name = self._resolve_agent_name(agent_id)

        # Check wallet balance
        try:
            balance_resp = await wallet.check_balance(user_id)
            balance_data = balance_resp.get("data", balance_resp)
            balance_cents = balance_data.get("balanceCents", 0)
        except Exception as exc:
            logger.error("Failed to check wallet balance for user %s: %s", user_id, exc)
            raise HTTPException(
                status_code=502,
                detail="Could not verify wallet balance. Please try again.",
            )

        if balance_cents < cost:
            raise HTTPException(
                status_code=402,
                detail="Insufficient balance. $24.00 required to create an agent.",
            )

        # Create subscription record FIRST (validates DB before taking money)
        now = datetime.now(timezone.utc)
        next_billing = now + timedelta(days=30)
        description = f"Agent: {agent_name} — subscription (initial)"
        try:
            subscription = self.sub_repo.create(
                agent_id=agent_id,
                org_id=org_id,
                user_id=user_id,
                amount_cents=cost,
                next_billing_date=next_billing,
            )
        except Exception as exc:
            logger.error("Failed to create subscription record for '%s': %s", agent_id, exc)
            raise HTTPException(
                status_code=500,
                detail="Failed to create subscription. Please try again.",
            )

        # Deduct credits (DB record exists, safe to charge)
        try:
            deduct_result = await wallet.deduct_credits(
                user_id=user_id,
                amount_cents=cost,
                description=description,
            )
        except (InsufficientBalanceError, DebtLimitReachedError):
            # Rollback: remove the subscription record since payment failed
            self.sub_repo.soft_delete(agent_id)
            raise HTTPException(
                status_code=402,
                detail="Insufficient balance. $24.00 required to create an agent.",
            )
        except Exception as exc:
            # Rollback: remove the subscription record since payment failed
            self.sub_repo.soft_delete(agent_id)
            logger.error("Wallet deduct failed for user %s: %s", user_id, exc)
            raise HTTPException(
                status_code=502,
                detail="Payment processing failed. Please try again.",
            )

        # Log transaction
        deduct_data = deduct_result.get("data", deduct_result)
        balance_after = deduct_data.get("balanceCents")
        self.txn_repo.create(
            user_id=user_id,
            agent_id=agent_id,
            type="subscription_initial",
            amount_cents=cost,
            description=description,
            status="success",
            balance_after_cents=balance_after,
        )

        logger.info(
            "Subscription created for agent '%s' (org=%s, user=%s, cost=%d cents)",
            agent_id, org_id, user_id, cost,
        )
        return subscription

    async def check_agent_active(self, agent_id: str) -> bool:
        """Return True if the agent's subscription is active (or no subscription exists)."""
        sub = self.sub_repo.get_by_agent_id(agent_id)
        if sub is None:
            return True  # Legacy agents without subscription
        return sub.status == "active"

    async def process_renewals(self) -> Dict[str, Any]:
        """Process all due renewals and soft-delete locked subscriptions past grace period."""
        now = datetime.now(timezone.utc)
        renewed = []
        locked = []
        deleted = []
        errors = []

        # ── Renewals ──
        due_subs = self.sub_repo.list_due_for_renewal(now)
        for sub in due_subs:
            agent_name = self._resolve_agent_name(sub.agent_id)
            try:
                wallet = get_wallet_client(sub.agent_id)
                description = f"Agent: {agent_name} — subscription (renewal)"
                await wallet.deduct_credits(
                    user_id=sub.user_id,
                    amount_cents=sub.amount_cents,
                    description=description,
                )
                new_next = sub.next_billing_date + timedelta(days=30)
                self.sub_repo.mark_renewed(sub.agent_id, new_next)

                self.txn_repo.create(
                    user_id=sub.user_id,
                    agent_id=sub.agent_id,
                    type="subscription_renewal",
                    amount_cents=sub.amount_cents,
                    description=description,
                    status="success",
                )
                renewed.append(sub.agent_id)
                logger.info("Renewed subscription for agent '%s'", sub.agent_id)

            except (InsufficientBalanceError, DebtLimitReachedError):
                await self.lock_agent(sub.agent_id)
                self.txn_repo.create(
                    user_id=sub.user_id,
                    agent_id=sub.agent_id,
                    type="subscription_renewal",
                    amount_cents=sub.amount_cents,
                    description=f"Agent: {agent_name} — subscription renewal failed",
                    status="failed",
                )
                locked.append(sub.agent_id)
                logger.warning("Locked agent '%s' — renewal payment failed", sub.agent_id)

            except Exception as exc:
                errors.append({"agent_id": sub.agent_id, "error": str(exc)})
                logger.error("Renewal error for agent '%s': %s", sub.agent_id, exc)

        # ── Soft-delete locked subs past grace period ──
        stale_subs = self.sub_repo.list_locked_for_deletion(now)
        for sub in stale_subs:
            await self.soft_delete_agent(sub.agent_id)
            deleted.append(sub.agent_id)
            logger.info("Soft-deleted subscription for agent '%s'", sub.agent_id)

        result = {
            "renewed": renewed,
            "locked": locked,
            "deleted": deleted,
            "errors": errors,
        }
        logger.info("Renewal run complete: %s", result)
        return result

    async def lock_agent(self, agent_id: str) -> None:
        """Lock a subscription and disable all cron jobs for this agent."""
        self.sub_repo.lock(agent_id)

        # Disable crons by removing them from the gateway
        from ..clients.cli_gateway_client import CLIGatewayClient

        cron_entries = (
            self.db.query(CronOwnership)
            .filter(CronOwnership.agent_id == agent_id)
            .all()
        )

        if cron_entries:
            gateway = CLIGatewayClient()
            for entry in cron_entries:
                try:
                    await gateway.cron_remove(entry.cron_id)
                except Exception as exc:
                    logger.warning(
                        "Failed to remove cron '%s' for locked agent '%s': %s",
                        entry.cron_id, agent_id, exc,
                    )

        logger.info("Agent '%s' locked — crons disabled", agent_id)

    async def soft_delete_agent(self, agent_id: str) -> None:
        """Soft-delete a subscription (marks status=deleted)."""
        self.sub_repo.soft_delete(agent_id)
        logger.info("Subscription soft-deleted for agent '%s'", agent_id)

    async def cancel_subscription(self, agent_id: str) -> None:
        """Cancel a subscription (used when user deletes agent)."""
        sub = self.sub_repo.get_by_agent_id(agent_id)
        if sub:
            self.sub_repo.cancel(agent_id)
            logger.info("Subscription cancelled for agent '%s'", agent_id)

    async def unlock_agent(self, agent_id: str, user_id: str) -> AgentSubscription:
        """Pay $24 to unlock a locked agent and reactivate its subscription."""
        sub = self.sub_repo.get_by_agent_id(agent_id)
        if not sub:
            raise HTTPException(status_code=404, detail="No subscription found for this agent.")
        if sub.status != "locked":
            raise HTTPException(
                status_code=400,
                detail=f"Agent is not locked (current status: {sub.status}).",
            )

        # # Uncomment to restrict unlock to the original creator only:
        # if sub.user_id != user_id:
        #     raise HTTPException(
        #         status_code=403,
        #         detail="Only the agent creator can unlock this agent.",
        #     )

        cost = settings.AGENT_MONTHLY_COST_CENTS
        wallet = get_wallet_client(agent_id)
        agent_name = self._resolve_agent_name(agent_id)
        description = f"Agent: {agent_name} — subscription unlock"

        try:
            deduct_result = await wallet.deduct_credits(
                user_id=user_id,
                amount_cents=cost,
                description=description,
            )
        except (InsufficientBalanceError, DebtLimitReachedError):
            raise HTTPException(
                status_code=402,
                detail="Insufficient balance. $24.00 required to unlock this agent.",
            )
        except Exception as exc:
            logger.error("Wallet deduct failed for unlock (user %s, agent %s): %s", user_id, agent_id, exc)
            raise HTTPException(
                status_code=502,
                detail="Payment processing failed. Please try again.",
            )

        # Reactivate
        now = datetime.now(timezone.utc)
        next_billing = now + timedelta(days=30)
        self.sub_repo.unlock(agent_id, next_billing)

        # Log transaction
        deduct_data = deduct_result.get("data", deduct_result)
        balance_after = deduct_data.get("balanceCents")
        self.txn_repo.create(
            user_id=user_id,
            agent_id=agent_id,
            type="subscription_unlock",
            amount_cents=cost,
            description=description,
            status="success",
            balance_after_cents=balance_after,
        )

        logger.info("Agent '%s' unlocked by user '%s'", agent_id, user_id)
        return self.sub_repo.get_by_agent_id(agent_id)

    def get_subscription(self, agent_id: str) -> Optional[AgentSubscription]:
        """Return the subscription for an agent, or None."""
        return self.sub_repo.get_by_agent_id(agent_id)

    def list_org_subscriptions(self, org_id: str, include_deleted: bool = False) -> List[AgentSubscription]:
        """Return subscriptions for an org/workspace."""
        return self.sub_repo.list_by_org(org_id, include_deleted=include_deleted)
