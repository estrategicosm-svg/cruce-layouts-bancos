from decimal import Decimal
from datetime import date

class ToleranceEngine:
    """
    Deterministically evaluates if two values are equal within configured tolerances.
    """
    def __init__(self, allowed_cents_diff: Decimal = Decimal("0.02"), allowed_days_diff: int = 3):
        self.allowed_cents_diff = allowed_cents_diff
        self.allowed_days_diff = allowed_days_diff

    def amounts_match(self, amount1: Decimal, amount2: Decimal) -> bool:
        """Checks if two amounts match within the cent tolerance."""
        diff = abs(amount1 - amount2)
        return diff <= self.allowed_cents_diff

    def dates_match(self, date1: date, date2: date) -> bool:
        """Checks if two dates match within the day tolerance."""
        diff = abs((date1 - date2).days)
        return diff <= self.allowed_days_diff
