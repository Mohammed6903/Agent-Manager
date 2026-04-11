"""Shared wallet-gate + cron-auto-disable helpers.

When a user's wallet drops below the minimum balance OR hits the debt
cap, we auto-disable every cron job they own in the openclaw gateway.
When they top up and clear the block, we re-enable ONLY the crons we
auto-disabled (never the ones the user explicitly paused — those are
identified by ``cron_ownership.disabled_reason IS NULL``).

This module is called from:
  - ``cron_service.create_cron`` / ``trigger_cron`` — refuse with 402
    if the user is currently blocked.
  - ``usage_service.deduct_chat_session_cost`` / ``deduct_cron_run_cost``
    — after a successful deduction, re-check the balance and disable
    crons if the user has now crossed into blocked territory.
  - Any wallet top-up / credit webhook — call
    ``restore_crons_for_user_if_unblocked`` to reactivate auto-disabled
    crons once balance is back above the minimum.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from ..clients.gateway_client import GatewayClient
from ..clients.wallet_client import get_wallet_client
from ..config import settings
from ..models.cron import CronOwnership

logger = logging.getLogger("agent_manager.services.cron_gate_service")

# Reason string stamped on cron_ownership.disabled_reason when we
# auto-disable a cron because of negative balance. Used as a needle so
# the restore path only re-enables crons WE disabled, never user-disabled.
BALANCE_NEGATIVE_REASON = "balance_negative"


async def is_user_wallet_blocked(user_id: str, agent_id: str = "") -> bool:
    """Return True if the user's wallet is at or below zero.

    Cron gating uses a stricter rule than the chat gate in
    ``chat_service._check_wallet_balance``. Chat has a grace window
    (small debt allowed up to MAX_DEBT_CENTS, MIN_BALANCE_CENTS floor)
    because a user can recover between turns. Crons fire autonomously
    and burst through any grace window in minutes, so we block
    immediately at the zero line:

    - ``balance_cents <= 0`` → blocked (nothing to spend)
    - ``debt_cents > 0``     → blocked (wallet is already underwater)

    Any non-zero positive balance with zero debt is unblocked. Top-up
    of even 1 cent lifts the block.

    On any wallet-service error we return False (fail-open). Blocking
    the whole cron system when the wallet backend has a hiccup would
    be worse than letting one extra cron run.
    """
    if not settings.WALLET_INTERNAL_API_KEY and not settings.GARAGE_WALLET_INTERNAL_API_KEY:
        return False  # Wallet integration disabled entirely.

    try:
        wallet = get_wallet_client(agent_id)
        result = await wallet.check_balance(user_id)
        data = result.get("data", result) if isinstance(result, dict) else {}
        balance_cents = int(data.get("balanceCents", 0) or 0)
        debt_cents = int(data.get("debtCents", 0) or 0)
    except Exception as exc:
        logger.warning(
            "is_user_wallet_blocked: wallet check failed for user %s (allowing): %s",
            user_id,
            exc,
        )
        return False

    if balance_cents <= 0:
        return True
    if debt_cents > 0:
        return True
    return False


async def disable_crons_for_user(
    db: Session,
    gateway: GatewayClient,
    user_id: str,
    reason: str = BALANCE_NEGATIVE_REASON,
) -> int:
    """Disable every cron owned by ``user_id`` in the openclaw gateway.

    Only touches crons that don't already have a ``disabled_reason`` —
    i.e. ones the user explicitly disabled keep their user-owned
    disabled state and are not re-enabled on restore. Returns the
    number of crons newly disabled.

    Idempotent: calling twice with the same user_id does not re-disable
    already-auto-disabled rows.
    """
    ownerships: List[CronOwnership] = (
        db.query(CronOwnership)
        .filter(
            CronOwnership.user_id == user_id,
            CronOwnership.disabled_reason.is_(None),
        )
        .all()
    )
    if not ownerships:
        return 0

    disabled_count = 0
    for own in ownerships:
        try:
            await gateway.cron_update(own.cron_id, {"enabled": False})
        except Exception as exc:
            logger.warning(
                "disable_crons_for_user: gateway cron_update failed "
                "for cron %s (continuing): %s",
                own.cron_id,
                exc,
            )
            continue
        own.disabled_reason = reason
        disabled_count += 1

    if disabled_count:
        db.commit()
        logger.info(
            "Auto-disabled %d cron(s) for user %s (reason=%s)",
            disabled_count,
            user_id,
            reason,
        )
    return disabled_count


async def restore_crons_for_user_if_unblocked(
    db: Session,
    gateway: GatewayClient,
    user_id: str,
) -> int:
    """Re-enable auto-disabled crons if the user is no longer wallet-blocked.

    Only re-enables crons whose ``disabled_reason`` matches
    ``BALANCE_NEGATIVE_REASON`` — user-disabled crons (with
    ``disabled_reason IS NULL``) are never touched. Returns the number
    of crons re-enabled.

    Safe to call on every deduct / every top-up webhook — it's a no-op
    when the user is still blocked or has nothing to restore.
    """
    blocked = await is_user_wallet_blocked(user_id)
    if blocked:
        return 0  # still below min — leave disabled

    ownerships: List[CronOwnership] = (
        db.query(CronOwnership)
        .filter(
            CronOwnership.user_id == user_id,
            CronOwnership.disabled_reason == BALANCE_NEGATIVE_REASON,
        )
        .all()
    )
    if not ownerships:
        return 0

    restored = 0
    for own in ownerships:
        try:
            await gateway.cron_update(own.cron_id, {"enabled": True})
        except Exception as exc:
            logger.warning(
                "restore_crons_for_user_if_unblocked: gateway cron_update "
                "failed for cron %s (continuing): %s",
                own.cron_id,
                exc,
            )
            continue
        own.disabled_reason = None
        restored += 1

    if restored:
        db.commit()
        logger.info(
            "Auto-restored %d cron(s) for user %s after wallet recovery",
            restored,
            user_id,
        )
    return restored
