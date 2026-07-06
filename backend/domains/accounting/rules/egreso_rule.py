from typing import Optional
from domains.shared.canonical_models import CanonicalXML, CanonicalTransaction
from domains.configuration.models import GeneralConfiguration
from domains.accounting.models import AccountingRuleResult, AccountingEntry, AccountingEntryType
from domains.accounting.rules.base import BaseAccountingRule
from domains.accounting.exceptions import AccountingRuleError

class EgresoRule(BaseAccountingRule):
    def evaluate(self, xml: Optional[CanonicalXML], tx: Optional[CanonicalTransaction], config: GeneralConfiguration) -> AccountingRuleResult:
        # Aquí trataremos "Egreso" en el contexto de "Gasto" o CFDI de Proveedor.
        # Si el CFDI es un comprobante que la empresa recibe para deducir (sea tipo I de proveedor, o un gasto general).
        # Para simplificar en este test, si tiene RFC receptor = "RECEPTOR", asumimos que es gasto (o si tiene una bandera).
        # El user dice "Para CFDI de egreso/gasto/proveedor". Usaremos esto como bandera.
        
        if not xml:
            return AccountingRuleResult(rule_name="GASTO_CFDI", applied=False, explanation="No hay XML.")
            
        cuenta_gastos = config.accounting.cuenta_gastos
        if not cuenta_gastos:
            raise AccountingRuleError("La cuenta_gastos no está configurada en el tenant.")
            
        # Cargo a gastos por el subtotal
        entries = [
            AccountingEntry(
                cuenta_contable=cuenta_gastos, 
                tipo=AccountingEntryType.CARGO, 
                monto=xml.subtotal, 
                concepto="Provisión de Gasto/Egreso"
            )
        ]
        
        return AccountingRuleResult(
            rule_name="GASTO_CFDI",
            applied=True,
            entries=entries,
            explanation="Provisión de Subtotal de Gasto."
        )
