"""Subscription rule matching and transfer planning."""

from .matcher import (
    SubscriptionMatch,
    SubscriptionMatcher,
    SubscriptionRule,
    validate_subscription_pattern,
    validate_subscription_signals,
)
from .repository import SubscriptionRepository, SubscriptionRuleRecord
from .service import SubscriptionRuleNotFoundError, SubscriptionService, SubscriptionTestResult
from .transfer_plan import TransferPlan, build_transfer_plans

__all__ = [
    "SubscriptionMatch",
    "SubscriptionMatcher",
    "SubscriptionRepository",
    "SubscriptionRule",
    "SubscriptionRuleNotFoundError",
    "SubscriptionRuleRecord",
    "SubscriptionService",
    "SubscriptionTestResult",
    "TransferPlan",
    "build_transfer_plans",
    "validate_subscription_pattern",
    "validate_subscription_signals",
]
