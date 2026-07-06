import unittest
from typing import List, Optional
from domains.configuration.models import (
    Tenant, GeneralConfiguration, CompanyConfiguration, ConfigurationVersion,
    ConciliationConfiguration, AccountingConfiguration
)
from domains.configuration.repositories import ConfigurationRepository
from domains.configuration.engine import ConfigurationEngine
from domains.configuration.exceptions import ConfigurationDuplicateError, ConfigurationNotFoundError

class MockConfigurationRepository(ConfigurationRepository):
    def __init__(self):
        self.tenants = []
        self.globals = []
        self.companies = []
        
    def add_tenant(self, tenant: Tenant) -> None:
        self.tenants.append(tenant)
        
    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        return next((t for t in self.tenants if t.id == tenant_id), None)
        
    def add_global_config(self, config: GeneralConfiguration) -> None:
        self.globals.append(config)
        
    def get_global_configs(self) -> List[GeneralConfiguration]:
        return self.globals
        
    def add_company_config(self, config: CompanyConfiguration) -> None:
        self.companies.append(config)
        
    def get_company_configs(self, tenant_id: str) -> List[CompanyConfiguration]:
        return [c for c in self.companies if c.tenant_id == tenant_id]

class TestPhase13(unittest.TestCase):
    def setUp(self):
        self.repo = MockConfigurationRepository()
        self.engine = ConfigurationEngine(self.repo)
        
        # Setup base global config
        self.global_cfg = GeneralConfiguration(
            id="GLOBAL_1",
            version_info=ConfigurationVersion(version="1.0"),
            conciliation=ConciliationConfiguration(bancos_activos=["GLOBAL_BANK"])
        )
        self.engine.register_global_config(self.global_cfg)

    def test_duplicate_global_config(self):
        duplicate = GeneralConfiguration(
            id="GLOBAL_2",
            version_info=ConfigurationVersion(version="1.0")
        )
        with self.assertRaises(ConfigurationDuplicateError):
            self.engine.register_global_config(duplicate)

    def test_fallback_to_global(self):
        # Request config for unknown tenant
        resolved = self.engine.resolve_configuration(tenant_id="UNKNOWN")
        self.assertEqual(resolved.id, "GLOBAL_1")
        self.assertEqual(resolved.conciliation.bancos_activos[0], "GLOBAL_BANK")

    def test_tenant_specific_override(self):
        tenant_cfg = CompanyConfiguration(
            id="TENANT_CFG_1",
            tenant_id="TENANT_1",
            version_info=ConfigurationVersion(version="1.0"),
            conciliation=ConciliationConfiguration(bancos_activos=["LOCAL_BANK"])
        )
        self.engine.register_company_config(tenant_cfg)
        
        resolved = self.engine.resolve_configuration(tenant_id="TENANT_1")
        self.assertEqual(resolved.id, "TENANT_CFG_1")
        self.assertEqual(resolved.conciliation.bancos_activos[0], "LOCAL_BANK")

    def test_tenant_period_specific_override(self):
        # Base tenant config
        tenant_base = CompanyConfiguration(
            id="TENANT_CFG_BASE",
            tenant_id="TENANT_1",
            version_info=ConfigurationVersion(version="1.0"),
            accounting=AccountingConfiguration(catalogo_contable_id="BASE")
        )
        # Year config
        tenant_year = CompanyConfiguration(
            id="TENANT_CFG_YEAR",
            tenant_id="TENANT_1",
            ejercicio=2024,
            version_info=ConfigurationVersion(version="1.0"),
            accounting=AccountingConfiguration(catalogo_contable_id="YEAR")
        )
        # Period config
        tenant_period = CompanyConfiguration(
            id="TENANT_CFG_PERIOD",
            tenant_id="TENANT_1",
            ejercicio=2024,
            periodo=5,
            version_info=ConfigurationVersion(version="1.0"),
            accounting=AccountingConfiguration(catalogo_contable_id="PERIOD")
        )
        
        self.engine.register_company_config(tenant_base)
        self.engine.register_company_config(tenant_year)
        self.engine.register_company_config(tenant_period)
        
        # Test fallback chain
        res_period = self.engine.resolve_configuration(tenant_id="TENANT_1", ejercicio=2024, periodo=5)
        self.assertEqual(res_period.id, "TENANT_CFG_PERIOD")
        
        res_year = self.engine.resolve_configuration(tenant_id="TENANT_1", ejercicio=2024, periodo=6)
        self.assertEqual(res_year.id, "TENANT_CFG_YEAR")
        
        res_base = self.engine.resolve_configuration(tenant_id="TENANT_1", ejercicio=2023, periodo=1)
        self.assertEqual(res_base.id, "TENANT_CFG_BASE")

    def test_deactivate_config(self):
        self.engine.deactivate_config("GLOBAL_1", "1.0")
        
        # Now global config is inactive, should raise not found for unknown tenant
        with self.assertRaises(ConfigurationNotFoundError):
            self.engine.resolve_configuration(tenant_id="UNKNOWN")

if __name__ == "__main__":
    unittest.main()
