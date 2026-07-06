import unittest
from decimal import Decimal
from domains.cfdi.parser import LXMLCFDIParser
from domains.cfdi.exceptions import CFDIParseError, CFDIValidationError, UnsupportedCFDITypeError

class TestPhase4(unittest.TestCase):
    
    def setUp(self):
        self.parser = LXMLCFDIParser()

    def test_valid_cfdi(self):
        xml_content = b"""<?xml version="1.0" encoding="utf-8"?>
        <cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" 
            xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
            TipoDeComprobante="I" SubTotal="100.00" Total="116.00" MetodoPago="PUE" FormaPago="03">
            <cfdi:Emisor Rfc="EKU9003173C9" />
            <cfdi:Receptor Rfc="XAXX010101000" />
            <cfdi:Complemento>
                <tfd:TimbreFiscalDigital UUID="F35B6D51-7896-4F7F-B28E-6C0C9FA9F200" />
            </cfdi:Complemento>
        </cfdi:Comprobante>
        """
        
        result = self.parser.parse(xml_content)
        xml = result.xml
        
        self.assertEqual(xml.uuid_cfdi, "F35B6D51-7896-4F7F-B28E-6C0C9FA9F200")
        self.assertEqual(xml.rfc_emisor, "EKU9003173C9")
        self.assertEqual(xml.rfc_receptor, "XAXX010101000")
        self.assertEqual(xml.tipo_cfdi, "I")
        self.assertEqual(xml.subtotal, Decimal("100.00"))
        self.assertEqual(xml.total, Decimal("116.00"))
        self.assertEqual(xml.metodo_pago, "PUE")

    def test_invalid_root(self):
        xml_content = b"<OtherRoot></OtherRoot>"
        with self.assertRaisesRegex(CFDIParseError, "Root element is not Comprobante"):
            self.parser.parse(xml_content)

    def test_malformed_xml(self):
        xml_content = b"<cfdi:Comprobante unclosed='true'"
        with self.assertRaises(CFDIParseError):
            self.parser.parse(xml_content)

    def test_missing_mandatory_nodes(self):
        xml_content = b"""<?xml version="1.0" encoding="utf-8"?>
        <cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" TipoDeComprobante="I">
            <cfdi:Emisor Rfc="EKU9003173C9" />
            <!-- Missing Receptor -->
        </cfdi:Comprobante>
        """
        with self.assertRaisesRegex(CFDIValidationError, "Missing Emisor or Receptor"):
            self.parser.parse(xml_content)

    def test_unsupported_type(self):
        xml_content = b"""<?xml version="1.0" encoding="utf-8"?>
        <cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" TipoDeComprobante="Z">
            <cfdi:Emisor Rfc="EKU9003173C9" />
            <cfdi:Receptor Rfc="XAXX010101000" />
        </cfdi:Comprobante>
        """
        with self.assertRaises(UnsupportedCFDITypeError):
            self.parser.parse(xml_content)

if __name__ == "__main__":
    unittest.main()
