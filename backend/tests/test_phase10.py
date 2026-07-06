import unittest
from decimal import Decimal
from domains.shared.canonical_models import CanonicalXML
from domains.sat.models import SATRuleStatus
from domains.sat.validator import SATValidator
from domains.sat.rules.iva_rule import IVARule
from domains.sat.rules.retencion_rule import RetencionRule
from domains.sat.rules.metodo_pago_rule import MetodoPagoRule
from domains.sat.rules.forma_pago_rule import FormaPagoRule
from domains.sat.rules.cfdi_status_rule import CFDIStatusRule

class TestPhase10(unittest.TestCase):
    def setUp(self):
        self.validator = SATValidator(rules=[
            IVARule(),
            RetencionRule(),
            MetodoPagoRule(),
            FormaPagoRule(),
            CFDIStatusRule()
        ])
        
        self.xml_valid = CanonicalXML(
            uuid_cfdi="A1B2C3D4",
            rfc_emisor="EMISOR1",
            rfc_receptor="RECEP1",
            tipo_cfdi="I",
            metodo_pago="PUE",
            forma_pago="03",
            subtotal=Decimal("1000.00"),
            total=Decimal("1160.00"),
            estado_cancelacion="VIGENTE",
            impuestos_desglosados={"IVA": [{"TasaOCuota": "0.160000", "Importe": "160.00"}]}
        )

    def test_all_pass(self):
        result = self.validator.validate(self.xml_valid)
        self.assertEqual(result.overall_status, SATRuleStatus.PASS)
        for r in result.results:
            self.assertEqual(r.status, SATRuleStatus.PASS)

    def test_iva_invalid(self):
        self.xml_valid.impuestos_desglosados = {"IVA": [{"TasaOCuota": "0.150000"}]} # Invalid rate
        result = self.validator.validate(self.xml_valid)
        self.assertEqual(result.overall_status, SATRuleStatus.FAIL)
        iva_res = next(r for r in result.results if r.rule_name == "IVA_VALIDATION")
        self.assertEqual(iva_res.status, SATRuleStatus.FAIL)

    def test_retenciones_warning(self):
        self.xml_valid.impuestos_desglosados["RETENCIONES"] = [{"Impuesto": "ISR", "Importe": "100.00"}]
        result = self.validator.validate(self.xml_valid)
        self.assertEqual(result.overall_status, SATRuleStatus.WARNING)
        ret_res = next(r for r in result.results if r.rule_name == "RETENCIONES")
        self.assertEqual(ret_res.status, SATRuleStatus.WARNING)

    def test_metodo_forma_pago_conflict(self):
        self.xml_valid.metodo_pago = "PPD"
        self.xml_valid.forma_pago = "03" # PPD must be 99
        result = self.validator.validate(self.xml_valid)
        self.assertEqual(result.overall_status, SATRuleStatus.FAIL)
        fp_res = next(r for r in result.results if r.rule_name == "FORMA_PAGO")
        self.assertEqual(fp_res.status, SATRuleStatus.FAIL)

    def test_cfdi_cancelado(self):
        self.xml_valid.estado_cancelacion = "CANCELADO"
        result = self.validator.validate(self.xml_valid)
        self.assertEqual(result.overall_status, SATRuleStatus.FAIL)
        stat_res = next(r for r in result.results if r.rule_name == "CFDI_STATUS")
        self.assertEqual(stat_res.status, SATRuleStatus.FAIL)

if __name__ == "__main__":
    unittest.main()
