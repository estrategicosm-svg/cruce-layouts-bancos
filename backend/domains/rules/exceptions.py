class RuleDuplicateError(Exception):
    """Raised when trying to register a rule that is an active duplicate."""
    pass

class RuleNotFoundError(Exception):
    """Raised when a rule is not found."""
    pass

class RuleValidationError(Exception):
    """Raised when a rule fails integrity validations."""
    pass
