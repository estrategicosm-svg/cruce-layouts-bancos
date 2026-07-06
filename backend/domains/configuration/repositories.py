from abc import ABC, abstractmethod
from typing import List, Optional, Union
from domains.configuration.models import GeneralConfiguration, CompanyConfiguration, Tenant

class ConfigurationRepository(ABC):
    @abstractmethod
    def add_tenant(self, tenant: Tenant) -> None: pass
    
    @abstractmethod
    def get_tenant(self, tenant_id: str) -> Optional[Tenant]: pass

    @abstractmethod
    def add_global_config(self, config: GeneralConfiguration) -> None: pass
    
    @abstractmethod
    def get_global_configs(self) -> List[GeneralConfiguration]: pass
    
    @abstractmethod
    def add_company_config(self, config: CompanyConfiguration) -> None: pass
    
    @abstractmethod
    def get_company_configs(self, tenant_id: str) -> List[CompanyConfiguration]: pass
