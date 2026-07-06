from typing import Optional
from decimal import Decimal
from domains.shared.canonical_models import CanonicalXML, CanonicalTransaction
from domains.configuration.models import GeneralConfiguration
from domains.accounting.models import AccountingRuleResult, AccountingEntry, AccountingEntryType
from domains.accounting.rules.base import BaseAccountingRule

class PagoRule(BaseAccountingRule):
    def evaluate(self, xml: Optional[CanonicalXML], tx: Optional[CanonicalTransaction], config: GeneralConfiguration) -> AccountingRuleResult:
        if not tx:
            return AccountingRuleResult(rule_name="PAGO_BANCOS", applied=False, explanation="No hay transacción bancaria asociada.")
            
        # Determinar naturaleza
        if tx.naturaleza == "ABONO":
            # Es un cobro (Abono en banco para la empresa = Cargo a Bancos Contablemente)
            # Cargo a Bancos, Abono a Clientes
            cuenta_bancos = "101-01-000"
            cuenta_clientes = "105-01-000"
            
            entries = [
                AccountingEntry(cuenta_contable=cuenta_bancos, tipo=AccountingEntryType.CARGO, monto=tx.monto_absoluto, concepto="Cobro en Banco"),
                AccountingEntry(cuenta_contable=cuenta_clientes, tipo=AccountingEntryType.ABONO, monto=tx.monto_absoluto, concepto="Abono de Cliente")
            ]
            return AccountingRuleResult(rule_name="PAGO_BANCOS_COBRO", applied=True, entries=entries, explanation="Registro de Cobro.")
            
        elif tx.naturaleza == "CARGO":
            # Es un pago (Cargo en banco = Abono a Bancos Contablemente)
            # Cargo a Proveedores, Abono a Bancos
            cuenta_prov = "201-01-000"
            cuenta_bancos = "101-01-000"
            
            entries = [
                AccountingEntry(cuenta_contable=cuenta_prov, tipo=AccountingEntryType.CARGO, monto=tx.monto_absoluto, concepto="Pago a Proveedor"),
                AccountingEntry(cuenta_contable=cuenta_bancos, tipo=AccountingEntryType.ABONO, monto=tx.monto_absoluto, concepto="Salida de Banco")
            ]
            return AccountingRuleResult(rule_name="PAGO_BANCOS_PAGO", applied=True, entries=entries, explanation="Registro de Pago.")
            
        return AccountingRuleResult(rule_name="PAGO_BANCOS", applied=False, explanation="Naturaleza de transacción desconocida.")
