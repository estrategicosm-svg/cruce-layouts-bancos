from domains.shared.canonical_models import CanonicalXML
from domains.sat.models import SATRuleResult, SATRuleStatus, SATRuleSeverity
from domains.sat.rules.base_rule import BaseSATRule

class MetodoPagoRule(BaseSATRule):
    def evaluate(self, xml: CanonicalXML) -> SATRuleResult:
        if xml.tipo_cfdi not in ("I", "E"):
            return SATRuleResult(
                rule_name="METODO_PAGO",
                status=SATRuleStatus.PASS,
                severity=SATRuleSeverity.LOW,
                explanation=f"Regla no aplica para CFDI tipo {xml.tipo_cfdi}"
            )
            
        if xml.metodo_pago not in ("PUE", "PPD"):
            return SATRuleResult(
                rule_name="METODO_PAGO",
                status=SATRuleStatus.FAIL,
                severity=SATRuleSeverity.HIGH,
                explanation=f"Método de pago inválido o ausente: {xml.metodo_pago}"
            )
            
        return SATRuleResult(
            rule_name="METODO_PAGO",
            status=SATRuleStatus.PASS,
            severity=SATRuleSeverity.LOW,
            explanation=f"Método de pago válido: {xml.metodo_pago}"
        )
