from typing import List, Optional
from datetime import date
from domains.shared.canonical_models import CanonicalXML, CanonicalTransaction
from domains.configuration.engine import ConfigurationEngine
from domains.configuration.models import GeneralConfiguration
from domains.accounting.models import AccountingProposal
from domains.accounting.rules.base import BaseAccountingRule
from domains.accounting.validators import validate_proposal
from uuid_utils import uuid7

class AccountingEngine:
    """
    Core orchestrator for generating accounting proposals deterministically.
    """
    def __init__(self, config_engine: ConfigurationEngine, rules: List[BaseAccountingRule]):
        # En la vida real, 'rules' podrían obtenerse de un RuleEngine inyectado.
        # Aquí simplificamos inyectando la lista de BaseAccountingRule activos.
        self.config_engine = config_engine
        self.rules = rules

    def generate_proposal(
        self,
        tenant_id: str,
        fecha: date,
        xml: Optional[CanonicalXML] = None,
        tx: Optional[CanonicalTransaction] = None,
        document_uuid: Optional[str] = None
    ) -> AccountingProposal:
        
        # 1. Obtener la Configuración del Tenant sin "hardcoding"
        config = self.config_engine.resolve_configuration(
            tenant_id=tenant_id,
            ejercicio=fecha.year,
            periodo=fecha.month
        )

        proposal = AccountingProposal(
            id=str(uuid7()),
            tenant_id=tenant_id,
            fecha=fecha,
            document_uuid=document_uuid,
            transaction_uuid=tx.uuid if tx else None,
            xml_uuid=xml.uuid_cfdi if xml else None
        )

        # 2. Ejecutar cada regla contable permitida
        for rule in self.rules:
            # Podríamos filtrar si la regla está en config.accounting.reglas_activas, etc.
            result = rule.evaluate(xml, tx, config)
            proposal.rule_results.append(result)
            
            if result.applied:
                proposal.entries.extend(result.entries)

        # 3. Validar la póliza armada
        validate_proposal(proposal)

        return proposal
