class NormalizationError(Exception):
    """Base exception for normalization failures."""
    pass

class MissingRequiredFieldError(NormalizationError):
    """Raised when a required field is missing from the source data during normalization."""
    pass

class InvalidCanonicalModelError(NormalizationError):
    """Raised when the constructed canonical model fails integrity validations."""
    pass
