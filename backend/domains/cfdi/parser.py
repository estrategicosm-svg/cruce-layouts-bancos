from lxml import etree
from decimal import Decimal
from domains.cfdi.base import BaseCFDIParser, CFDIParserResult
from domains.cfdi.exceptions import CFDIParseError, CFDIValidationError, UnsupportedCFDITypeError
from domains.shared.canonical_models import CanonicalXML

class LXMLCFDIParser(BaseCFDIParser):
    """
    Deterministic XML parser using lxml to extract CFDI elements.
    """
    
    def parse(self, raw_bytes: bytes) -> CFDIParserResult:
        try:
            root = etree.fromstring(raw_bytes)
        except etree.XMLSyntaxError as e:
            raise CFDIParseError(f"Malformed XML: {str(e)}")
            
        # Namespaces in CFDI
        namespaces = {
            'cfdi': 'http://www.sat.gob.mx/cfd/4',
            'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'
        }
        
        # Fallback to CFDI 3.3 if 4.0 not found in nsmap
        if 'http://www.sat.gob.mx/cfd/3' in root.nsmap.values():
            namespaces['cfdi'] = 'http://www.sat.gob.mx/cfd/3'
            
        # Basic CFDI checks
        if "Comprobante" not in root.tag:
            raise CFDIParseError("Root element is not Comprobante. This is not a CFDI.")
            
        tipo_cfdi = root.attrib.get('TipoDeComprobante')
        if not tipo_cfdi:
            raise CFDIValidationError("Missing TipoDeComprobante attribute.")
            
        if tipo_cfdi not in ['I', 'E', 'P', 'N', 'T']:
            raise UnsupportedCFDITypeError(f"Unsupported CFDI type: {tipo_cfdi}")
            
        # Extract basic nodes
        emisor = root.find('cfdi:Emisor', namespaces)
        receptor = root.find('cfdi:Receptor', namespaces)
        
        if emisor is None or receptor is None:
            raise CFDIValidationError("Missing Emisor or Receptor nodes.")
            
        rfc_emisor = emisor.attrib.get('Rfc', '')
        rfc_receptor = receptor.attrib.get('Rfc', '')
        
        # Extract UUID
        complemento = root.find('cfdi:Complemento', namespaces)
        uuid = "UNKNOWN"
        if complemento is not None:
            tfd = complemento.find('tfd:TimbreFiscalDigital', namespaces)
            if tfd is not None:
                uuid = tfd.attrib.get('UUID', 'UNKNOWN')
                
        # Subtotal, Total
        subtotal = Decimal(root.attrib.get('SubTotal', '0.00'))
        total = Decimal(root.attrib.get('Total', '0.00'))
        
        # Metodo / Forma
        metodo_pago = root.attrib.get('MetodoPago')
        forma_pago = root.attrib.get('FormaPago')
        
        canonical = CanonicalXML(
            uuid_cfdi=uuid,
            rfc_emisor=rfc_emisor,
            rfc_receptor=rfc_receptor,
            tipo_cfdi=tipo_cfdi,
            metodo_pago=metodo_pago,
            forma_pago=forma_pago,
            subtotal=subtotal,
            total=total
        )
        
        return CFDIParserResult(xml=canonical, warnings=[])
