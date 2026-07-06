import re
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

def extract_clave_rastreo(concepto: str) -> Optional[str]:
    """Extrae la clave de rastreo de un concepto (SPEI/CEP)."""
    if not concepto: return None
    m = re.search(r"(?:CLAVE DE RASTREO|CVE RASTREO|RASTREO)[\s:]*([A-Za-z0-9]+)", concepto, re.IGNORECASE)
    if m: return m.group(1).strip()
    return None

def extract_autorizacion(concepto: str) -> Optional[str]:
    """Extrae el nmero de autorizacin."""
    if not concepto: return None
    m = re.search(r"(?:AUTORIZACION|AUT\.|AUT)[\s:]*([A-Za-z0-9]+)", concepto, re.IGNORECASE)
    if m: return m.group(1).strip()
    return None

def extract_numero_operacion(concepto: str) -> Optional[str]:
    """Extrae nmero de operacin/folio/transaccin."""
    if not concepto: return None
    m = re.search(r"(?:OPERACION|OPER\.|TRANSACCION|FOLIO|DOCTO|RECIBO)[\s:]*([A-Za-z0-9]+)", concepto, re.IGNORECASE)
    if m: return m.group(1).strip()
    return None

def extract_referencia_limpia(concepto: str) -> Optional[str]:
    """Extrae referencia general limpia (solo si est etiquetada explicitamente como REF o REFERENCIA)."""
    if not concepto: return None
    m = re.search(r"(?:REFERENCIA|REF\.|REF)[\s:]*([A-Za-z0-9]+)", concepto, re.IGNORECASE)
    if m: return m.group(1).strip()
    return None

def extract_all_references(concepto: str, ref_original: Optional[str] = None) -> Dict[str, Optional[str]]:
    """Extrae y estructura todas las referencias de un concepto bancario original."""
    refs = {
        "clave_rastreo": extract_clave_rastreo(concepto),
        "numero_operacion": extract_numero_operacion(concepto),
        "autorizacion": extract_autorizacion(concepto),
        "referencia_bancaria_limpia": extract_referencia_limpia(concepto)
    }
    
    # Si hay una referencia original por separado (de una columna especifica),
    # intentamos limpiarla y colocarla si referencia_bancaria_limpia no se llen por concepto.
    if ref_original and not refs["referencia_bancaria_limpia"]:
        # Si la original no est vaca, limpiamos caracteres no deseados
        cleaned = re.sub(r'[^A-Za-z0-9]', '', ref_original)
        if cleaned:
            refs["referencia_bancaria_limpia"] = cleaned
            
    # Regla: Si no existe referencia alguna, registrar warning
    if not any(refs.values()):
        logger.warning(f"No se encontr ninguna referencia en el concepto: {concepto[:50]}...")
        
    return refs
