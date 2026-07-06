from typing import Optional
from domains.shared.canonical_models import CanonicalXML, CanonicalTransaction
from domains.configuration.models import GeneralConfiguration
from domains.accounting.models import AccountingRuleResult, AccountingEntry, AccountingEntryType
from domains.accounting.rules.base import BaseAccountingRule

class IngresoRule(BaseAccountingRule):
    def evaluate(self, xml: Optional[CanonicalXML], tx: Optional[CanonicalTransaction], config: GeneralConfiguration) -> AccountingRuleResult:
        if not xml or xml.tipo_cfdi != "I":
            return AccountingRuleResult(rule_name="INGRESO_CFDI", applied=False, explanation="No es CFDI de Ingreso.")
            
        # Póliza de provisión de ventas
        # Cargo a Clientes (Total), Abono a Ventas (Subtotal)
        # El IVA se delega a IVARule.
        
        # En la realidad esto vendría del catálogo de cuentas vía Config.
        cuenta_clientes = "105-01-000" # Dummy
        cuenta_ventas = "401-01-000"   # Dummy
        
        entries = [
            AccountingEntry(cuenta_contable=cuenta_clientes, tipo=AccountingEntryType.CARGO, monto=xml.total, concepto="Provisión Venta"),
            AccountingEntry(cuenta_contable=cuenta_ventas, tipo=AccountingEntryType.ABONO, monto=xml.subtotal, concepto="Ingresos por Ventas")
        ]
        
        return AccountingRuleResult(
            rule_name="INGRESO_CFDI",
            applied=True,
            entries=entries,
            explanation="Provisión de CFDI de Ingreso."
        )
