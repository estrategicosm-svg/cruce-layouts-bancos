class ConfigurationDuplicateError(Exception):
    """Raised when an active configuration version already exists for the given scope."""
    pass

class ConfigurationNotFoundError(Exception):
    """Raised when no suitable configuration is found."""
    pass

class ConfigurationValidationError(Exception):
    """Raised when a configuration object fails integrity rules."""
    pass
