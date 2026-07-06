from domains.shared.canonical_models import CanonicalXML
from domains.sat.models import SATRuleResult, SATRuleStatus, SATRuleSeverity
from domains.sat.rules.base_rule import BaseSATRule

class FormaPagoRule(BaseSATRule):
    def evaluate(self, xml: CanonicalXML) -> SATRuleResult:
        if xml.tipo_cfdi not in ("I", "E"):
            return SATRuleResult(
                rule_name="FORMA_PAGO",
                status=SATRuleStatus.PASS,
                severity=SATRuleSeverity.LOW,
                explanation=f"Regla no aplica para CFDI tipo {xml.tipo_cfdi}"
            )
            
        if xml.metodo_pago == "PPD" and xml.forma_pago != "99":
            return SATRuleResult(
                rule_name="FORMA_PAGO",
                status=SATRuleStatus.FAIL,
                severity=SATRuleSeverity.HIGH,
                explanation="CFDI PPD debe tener forma de pago 99 (Por definir)."
            )
            
        if xml.metodo_pago == "PUE" and xml.forma_pago == "99":
            return SATRuleResult(
                rule_name="FORMA_PAGO",
                status=SATRuleStatus.FAIL,
                severity=SATRuleSeverity.HIGH,
                explanation="CFDI PUE no puede tener forma de pago 99."
            )
            
        return SATRuleResult(
            rule_name="FORMA_PAGO",
            status=SATRuleStatus.PASS,
            severity=SATRuleSeverity.LOW,
            explanation=f"Combinación válida: {xml.metodo_pago} / {xml.forma_pago}"
        )
