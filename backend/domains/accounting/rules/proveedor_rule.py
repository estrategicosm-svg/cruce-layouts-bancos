from typing import Optional
from domains.shared.canonical_models import CanonicalXML, CanonicalTransaction
from domains.configuration.models import GeneralConfiguration
from domains.accounting.models import AccountingRuleResult, AccountingEntry, AccountingEntryType
from domains.accounting.rules.base import BaseAccountingRule
from domains.accounting.exceptions import AccountingRuleError

class ProveedorRule(BaseAccountingRule):
    def evaluate(self, xml: Optional[CanonicalXML], tx: Optional[CanonicalTransaction], config: GeneralConfiguration) -> AccountingRuleResult:
        if not xml:
            return AccountingRuleResult(rule_name="PROVEEDOR_CFDI", applied=False, explanation="No hay XML.")
            
        cuenta_proveedor = config.accounting.cuenta_proveedores
        if not cuenta_proveedor:
            raise AccountingRuleError("La cuenta_proveedores no está configurada en el tenant.")
            
        # Abono a proveedores por el total
        entries = [
            AccountingEntry(
                cuenta_contable=cuenta_proveedor, 
                tipo=AccountingEntryType.ABONO, 
                monto=xml.total, 
                concepto="Provisión de Proveedor"
            )
        ]
        
        return AccountingRuleResult(
            rule_name="PROVEEDOR_CFDI",
            applied=True,
            entries=entries,
            explanation="Provisión de Total a Proveedor."
        )
