from typing import Optional
from decimal import Decimal
from domains.shared.canonical_models import CanonicalXML, CanonicalTransaction
from domains.configuration.models import GeneralConfiguration
from domains.accounting.models import AccountingRuleResult, AccountingEntry, AccountingEntryType
from domains.accounting.rules.base import BaseAccountingRule

class IVARule(BaseAccountingRule):
    def evaluate(self, xml: Optional[CanonicalXML], tx: Optional[CanonicalTransaction], config: GeneralConfiguration) -> AccountingRuleResult:
        if not xml or not xml.impuestos_desglosados:
            return AccountingRuleResult(rule_name="IVA", applied=False, explanation="No hay impuestos desglosados en el CFDI.")
            
        iva_list = xml.impuestos_desglosados.get("IVA", [])
        monto_iva = sum((Decimal(str(t.get("Importe", 0))) for t in iva_list), Decimal("0.0"))
        
        if monto_iva == Decimal("0.0"):
             return AccountingRuleResult(rule_name="IVA", applied=False, explanation="Monto de IVA es cero.")
             
        entries = []
        if xml.tipo_cfdi == "I":
            # IVA Trasladado (Abono)
            cuenta_iva = "208-01-000"
            entries.append(AccountingEntry(cuenta_contable=cuenta_iva, tipo=AccountingEntryType.ABONO, monto=monto_iva, concepto="IVA Trasladado"))
        elif xml.tipo_cfdi == "E" or (xml.tipo_cfdi == "I" and tx and tx.naturaleza == "CARGO"):
             # Simplificación: Si es un CFDI de gasto (aún modelado como ingreso en ciertos casos o si hubiera CFDI Traslado/Gasto)
             # Asumimos que si estamos pagando, hay IVA acreditable
             pass
             
        if entries:
            return AccountingRuleResult(rule_name="IVA", applied=True, entries=entries, explanation=f"Provisión de IVA por {monto_iva}")
            
        return AccountingRuleResult(rule_name="IVA", applied=False, explanation="No aplicó regla de IVA específica.")
