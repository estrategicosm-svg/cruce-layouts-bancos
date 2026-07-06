class AccountingValidationError(Exception):
    """Raised when an accounting proposal fails internal rules (e.g. cargos != abonos)."""
    pass

class AccountingRuleError(Exception):
    """Raised when a specific accounting rule fails to execute."""
    pass
