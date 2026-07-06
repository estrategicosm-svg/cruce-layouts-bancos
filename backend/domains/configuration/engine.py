from typing import Optional, Union
from domains.configuration.models import GeneralConfiguration, CompanyConfiguration, Tenant
from domains.configuration.repositories import ConfigurationRepository
from domains.configuration.validators import validate_configuration, ensure_no_active_duplicates
from domains.configuration.exceptions import ConfigurationNotFoundError

class ConfigurationEngine:
    """
    Central hub for registering and resolving tenant and global configurations.
    Implements a fallback mechanism: Period -> Year -> Company -> Global.
    """
    def __init__(self, repository: ConfigurationRepository):
        self.repository = repository

    def register_tenant(self, tenant: Tenant) -> None:
        self.repository.add_tenant(tenant)

    def register_global_config(self, config: GeneralConfiguration) -> None:
        validate_configuration(config)
        existing = self.repository.get_global_configs()
        ensure_no_active_duplicates(config, existing)
        self.repository.add_global_config(config)

    def register_company_config(self, config: CompanyConfiguration) -> None:
        validate_configuration(config)
        existing = self.repository.get_company_configs(config.tenant_id)
        ensure_no_active_duplicates(config, existing)
        self.repository.add_company_config(config)

    def deactivate_config(self, config_id: str, version: str, tenant_id: Optional[str] = None) -> None:
        if tenant_id:
            configs = self.repository.get_company_configs(tenant_id)
        else:
            configs = self.repository.get_global_configs()
            
        target = next((c for c in configs if c.id == config_id and c.version_info.version == version), None)
        if not target:
            scope = f"tenant {tenant_id}" if tenant_id else "global scope"
            raise ConfigurationNotFoundError(f"Config {config_id} v{version} not found in {scope}.")
            
        target.version_info.activo = False

    def resolve_configuration(
        self, tenant_id: Optional[str] = None, ejercicio: Optional[int] = None, periodo: Optional[int] = None
    ) -> GeneralConfiguration:
        """
        Resolves configuration by attempting to find the most specific one active,
        falling back to the global default.
        """
        # 1. Fetch Global
        globals_active = [c for c in self.repository.get_global_configs() if c.version_info.activo]
        global_config = globals_active[-1] if globals_active else None

        if not tenant_id:
            if not global_config:
                raise ConfigurationNotFoundError("No active global configuration available.")
            return global_config
            
        # 2. Fetch Tenant configs
        tenant_configs = [c for c in self.repository.get_company_configs(tenant_id) if c.version_info.activo]
        
        if not tenant_configs:
            if not global_config:
                raise ConfigurationNotFoundError(f"No configuration available for tenant {tenant_id} or globally.")
            return global_config

        # 3. Try to find the most specific matching config
        # Order of precedence: matches Period+Year -> matches Year -> matches Tenant only
        
        match_period = None
        match_year = None
        match_base = None
        
        for c in tenant_configs:
            if c.ejercicio == ejercicio and c.periodo == periodo:
                match_period = c
            elif c.ejercicio == ejercicio and c.periodo is None:
                match_year = c
            elif c.ejercicio is None and c.periodo is None:
                match_base = c
                
        # Return most specific found
        if match_period:
            return match_period
        if match_year:
            return match_year
        if match_base:
            return match_base
            
        # Fallback to global if tenant configs exist but none match the requested scope
        if global_config:
            return global_config
            
        raise ConfigurationNotFoundError(f"No suitable configuration found for {tenant_id} - {ejercicio}/{periodo}")
