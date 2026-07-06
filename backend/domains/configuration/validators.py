from typing import List, Union
from domains.configuration.models import GeneralConfiguration, CompanyConfiguration
from domains.configuration.exceptions import ConfigurationValidationError, ConfigurationDuplicateError

def validate_configuration(config: Union[GeneralConfiguration, CompanyConfiguration]):
    if not config.id or not config.id.strip():
        raise ConfigurationValidationError("Configuration must have an ID.")
    if not config.version_info or not config.version_info.version:
        raise ConfigurationValidationError("Configuration must have a version.")
        
def ensure_no_active_duplicates(
    new_config: Union[GeneralConfiguration, CompanyConfiguration], 
    existing_configs: List[Union[GeneralConfiguration, CompanyConfiguration]]
):
    for existing in existing_configs:
        if existing.version_info.activo and new_config.version_info.activo:
            if existing.version_info.version == new_config.version_info.version:
                # If they are both General, it's a duplicate.
                # If they are both Company, check if tenant_id matches
                if isinstance(existing, CompanyConfiguration) and isinstance(new_config, CompanyConfiguration):
                    if (existing.tenant_id == new_config.tenant_id and 
                        existing.ejercicio == new_config.ejercicio and 
                        existing.periodo == new_config.periodo):
                        raise ConfigurationDuplicateError(
                            f"Active configuration v{new_config.version_info.version} already exists for this tenant/scope."
                        )
                elif type(existing) == GeneralConfiguration and type(new_config) == GeneralConfiguration:
                     raise ConfigurationDuplicateError(
                        f"Active global configuration v{new_config.version_info.version} already exists."
                    )
