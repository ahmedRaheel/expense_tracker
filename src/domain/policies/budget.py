from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True, slots=True)
class ThresholdCrossing:
    level: int
    total: Decimal


def crossed_thresholds(budget: Decimal | None, before: Decimal, after: Decimal) -> tuple[ThresholdCrossing, ...]:
    if budget is None or budget <= 0:
        return ()
    return tuple(
        ThresholdCrossing(level, after)
        for level in (80, 100)
        if before < budget * Decimal(level) / Decimal(100) <= after
    )
