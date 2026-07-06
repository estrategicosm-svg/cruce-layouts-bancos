from decimal import Decimal, InvalidOperation
from datetime import date, datetime
import re
from typing import Tuple

def validate_currency(currency: str) -> str:
    """Ensures currency is valid, defaulting to MXN if not provided."""
    if not currency:
        return "MXN"
    clean_currency = currency.strip().upper()
    if clean_currency not in ["MXN", "USD", "EUR"]:
        raise ValueError(f"Invalid or unsupported currency: {currency}")
    return clean_currency

def validate_date(date_input: str) -> date:
    """Parses standard date strings into date objects."""
    if not date_input:
        raise ValueError("Date cannot be empty.")
    
    # Try ISO format
    try:
        return date.fromisoformat(date_input)
    except ValueError:
        pass
        
    # Additional deterministic fallback formats can be added here
    # Example: DD/MM/YYYY
    match = re.match(r"^(\d{2})[/.-](\d{2})[/.-](\d{4})$", date_input)
    if match:
        day, month, year = match.groups()
        return date(int(year), int(month), int(day))
        
    raise ValueError(f"Invalid date format: {date_input}. Expected YYYY-MM-DD or DD/MM/YYYY")

def validate_amount(amount_input: str | float | Decimal) -> Decimal:
    """Ensures amount is a valid Decimal >= 0."""
    try:
        # If it's a string with commas, remove them
        if isinstance(amount_input, str):
            amount_input = amount_input.replace(",", "")
        amount = Decimal(amount_input)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Invalid amount format: {amount_input}")
        
    if amount < 0:
        raise ValueError(f"Amount cannot be negative: {amount}")
    return amount

def validate_nature(nature_input: str) -> str:
    """Ensures nature is strictly CARGO or ABONO."""
    clean = str(nature_input).strip().upper()
    if clean not in ["CARGO", "ABONO"]:
        raise ValueError(f"Invalid transaction nature: {nature_input}. Must be CARGO or ABONO.")
    return clean

def validate_rfc(rfc: str) -> str:
    """Validates Mexican RFC format (12 or 13 chars)."""
    clean_rfc = str(rfc).strip().upper()
    # Basic deterministic regex for RFC
    pattern = r"^[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}$"
    if not re.match(pattern, clean_rfc):
        raise ValueError(f"Invalid RFC format: {clean_rfc}")
    return clean_rfc

def validate_uuid(uuid_input: str) -> str:
    """Validates standard SAT UUID format."""
    clean_uuid = str(uuid_input).strip().upper()
    pattern = r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$"
    if not re.match(pattern, clean_uuid):
        raise ValueError(f"Invalid UUID format: {clean_uuid}")
    return clean_uuid
