from typing import Optional
from decimal import Decimal
from domains.shared.canonical_models import CanonicalXML, CanonicalTransaction
from domains.configuration.models import GeneralConfiguration
from domains.accounting.models import AccountingRuleResult, AccountingEntry, AccountingEntryType
from domains.accounting.rules.base import BaseAccountingRule
from domains.accounting.exceptions import AccountingRuleError

class IVAAcreditableRule(BaseAccountingRule):
    def evaluate(self, xml: Optional[CanonicalXML], tx: Optional[CanonicalTransaction], config: GeneralConfiguration) -> AccountingRuleResult:
        if not xml or not xml.impuestos_desglosados:
            return AccountingRuleResult(rule_name="IVA_ACREDITABLE", applied=False, explanation="No hay XML o impuestos desglosados.")
            
        cuenta_iva = config.accounting.cuenta_iva_acreditable
        if not cuenta_iva:
            raise AccountingRuleError("La cuenta_iva_acreditable no está configurada en el tenant.")

        iva_list = xml.impuestos_desglosados.get("IVA", [])
        monto_iva = sum((Decimal(str(t.get("Importe", 0))) for t in iva_list), Decimal("0.0"))
        
        if monto_iva == Decimal("0.0"):
             return AccountingRuleResult(rule_name="IVA_ACREDITABLE", applied=False, explanation="Monto de IVA es cero.")
             
        # Cargo a IVA acreditable
        entries = [
            AccountingEntry(
                cuenta_contable=cuenta_iva, 
                tipo=AccountingEntryType.CARGO, 
                monto=monto_iva, 
                concepto="IVA Acreditable"
            )
        ]
            
        return AccountingRuleResult(
            rule_name="IVA_ACREDITABLE", 
            applied=True, 
            entries=entries, 
            explanation=f"Provisión de IVA Acreditable por {monto_iva}"
        )
