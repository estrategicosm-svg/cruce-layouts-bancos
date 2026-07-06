class ParserConfidenceError(Exception):
    """Raised when a parser cannot confidently extract data from a document."""
    pass

class UnsupportedBankError(Exception):
    """Raised when the bank is not recognized or supported by the registry."""
    pass

class ParserValidationError(Exception):
    """Raised when extracted data fails business rule validations."""
    pass
