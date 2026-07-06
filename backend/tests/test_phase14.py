import unittest
from datetime import date
from decimal import Decimal
from typing import List, Optional

from domains.shared.canonical_models import CanonicalXML, CanonicalTransaction
from domains.configuration.models import GeneralConfiguration, ConfigurationVersion, Tenant, AccountingConfiguration
from domains.configuration.engine import ConfigurationEngine
from domains.configuration.repositories import ConfigurationRepository
from domains.accounting.engine import AccountingEngine
from domains.accounting.rules.egreso_rule import EgresoRule
from domains.accounting.rules.iva_acreditable_rule import IVAAcreditableRule
from domains.accounting.rules.proveedor_rule import ProveedorRule
from domains.accounting.rules.pago_rule import PagoRule
from domains.accounting.exceptions import AccountingValidationError, AccountingRuleError
from uuid_utils import uuid7

class MockConfigRepo(ConfigurationRepository):
    def __init__(self):
        self.globals = []
    def add_tenant(self, tenant: Tenant) -> None: pass
    def get_tenant(self, tenant_id: str) -> Optional[Tenant]: return None
    def add_global_config(self, config: GeneralConfiguration) -> None: self.globals.append(config)
    def get_global_configs(self) -> List[GeneralConfiguration]: return self.globals
    def add_company_config(self, config) -> None: pass
    def get_company_configs(self, tenant_id: str) -> List: return []

class TestPhase14Egreso(unittest.TestCase):
    def setUp(self):
        self.repo = MockConfigRepo()
        self.config_engine = ConfigurationEngine(self.repo)
        self.config_engine.register_global_config(GeneralConfiguration(
            id="GLOBAL_1",
            version_info=ConfigurationVersion(version="1.0"),
            accounting=AccountingConfiguration(
                cuenta_gastos="501-01-000",
                cuenta_iva_acreditable="118-01-000",
                cuenta_proveedores="201-01-000",
                cuenta_bancos="102-01-000"
            )
        ))
        
        self.engine = AccountingEngine(
            config_engine=self.config_engine,
            rules=[EgresoRule(), IVAAcreditableRule(), ProveedorRule(), PagoRule()]
        )

    def test_egreso_con_iva_cuadrado(self):
        xml = CanonicalXML(
            uuid_cfdi="UUID-EGR",
            rfc_emisor="PROVEEDOR",
            rfc_receptor="TENANT",
            tipo_cfdi="I", # A receipt from supplier is 'I' for them, but it's an expense for us
            subtotal=Decimal("1000.00"),
            total=Decimal("1160.00"),
            impuestos_desglosados={"IVA": [{"TasaOCuota": "0.160000", "Importe": "160.00"}]}
        )
        
        proposal = self.engine.generate_proposal(
            tenant_id="TENANT1",
            fecha=date(2024, 1, 1),
            xml=xml
        )
        
        self.assertEqual(proposal.total_cargos, Decimal("1160.00")) # Gasto (1000) + IVA Acred (160)
        self.assertEqual(proposal.total_abonos, Decimal("1160.00")) # Proveedor (1160)
        self.assertEqual(len(proposal.entries), 3)

    def test_egreso_sin_iva(self):
        xml = CanonicalXML(
            uuid_cfdi="UUID-EGR2",
            rfc_emisor="PROVEEDOR",
            rfc_receptor="TENANT",
            tipo_cfdi="I",
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
            impuestos_desglosados={}
        )
        
        proposal = self.engine.generate_proposal(
            tenant_id="TENANT1",
            fecha=date(2024, 1, 1),
            xml=xml
        )
        
        self.assertEqual(proposal.total_cargos, Decimal("1000.00")) # Gasto (1000)
        self.assertEqual(proposal.total_abonos, Decimal("1000.00")) # Proveedor (1000)
        self.assertEqual(len(proposal.entries), 2)

    def test_error_falta_cuenta(self):
        # Create a repo with a config missing the IVA account
        repo2 = MockConfigRepo()
        config_engine2 = ConfigurationEngine(repo2)
        config_engine2.register_global_config(GeneralConfiguration(
            id="GLOBAL_2",
            version_info=ConfigurationVersion(version="1.0"),
            accounting=AccountingConfiguration(
                cuenta_gastos="501-01-000",
                cuenta_proveedores="201-01-000"
                # missing cuenta_iva_acreditable
            )
        ))
        
        engine2 = AccountingEngine(
            config_engine=config_engine2,
            rules=[EgresoRule(), IVAAcreditableRule(), ProveedorRule()]
        )
        
        xml = CanonicalXML(
            uuid_cfdi="UUID-EGR",
            rfc_emisor="PROVEEDOR",
            rfc_receptor="TENANT",
            tipo_cfdi="I",
            subtotal=Decimal("1000.00"),
            total=Decimal("1160.00"),
            impuestos_desglosados={"IVA": [{"TasaOCuota": "0.160000", "Importe": "160.00"}]}
        )
        
        with self.assertRaises(AccountingRuleError):
            engine2.generate_proposal(
                tenant_id="TENANT1",
                fecha=date(2024, 1, 1),
                xml=xml
            )

    def test_error_cargos_distintos_abonos(self):
        # We simulate a rule that intentionally creates an imbalance
        class BadRule(EgresoRule):
            def evaluate(self, xml, tx, config):
                res = super().evaluate(xml, tx, config)
                res.entries[0].monto = Decimal("9999.00") # Ruin the balance
                return res

        engine3 = AccountingEngine(
            config_engine=self.config_engine,
            rules=[BadRule(), IVAAcreditableRule(), ProveedorRule()]
        )
        
        xml = CanonicalXML(
            uuid_cfdi="UUID-EGR",
            rfc_emisor="PROVEEDOR",
            rfc_receptor="TENANT",
            tipo_cfdi="I",
            subtotal=Decimal("1000.00"),
            total=Decimal("1160.00"),
            impuestos_desglosados={"IVA": [{"TasaOCuota": "0.160000", "Importe": "160.00"}]}
        )
        
        with self.assertRaises(AccountingValidationError):
            engine3.generate_proposal(
                tenant_id="TENANT1",
                fecha=date(2024, 1, 1),
                xml=xml
            )

if __name__ == "__main__":
    unittest.main()
