from typing import Any
from datetime import date
from domains.documents.identity import DocumentIdentity

class MetadataBuilder:
    """
    Builds the DocumentIdentity extracting fields deterministically from 
    raw or parsed metadata objects without any guesswork.
    """
    @staticmethod
    def build(
        document_uuid: str,
        sha256: str,
        empresa_id: str,
        empresa_rfc: str,
        fecha_documento: date,
        tipo_documento: str,
        origen: str,
        banco: str = None,
        cuenta: str = None
    ) -> DocumentIdentity:
        # Determine Period and Ejercicio from date
        ejercicio = fecha_documento.year
        periodo = fecha_documento.month
        
        return DocumentIdentity(
            document_uuid=document_uuid,
            sha256=sha256,
            empresa_id=empresa_id,
            empresa_rfc=empresa_rfc,
            ejercicio=ejercicio,
            periodo=periodo,
            tipo_documento=tipo_documento,
            banco=banco,
            cuenta=cuenta,
            fecha_documento=fecha_documento,
            origen=origen
        )
