class CFDIParseError(Exception):
    """Raised when the XML cannot be parsed or is fundamentally malformed."""
    pass

class CFDIValidationError(Exception):
    """Raised when the CFDI data fails strict business rule validations (missing total, emisor, etc)."""
    pass

class UnsupportedCFDITypeError(Exception):
    """Raised when the CFDI type is recognized but not supported by the current process."""
    pass
