from domains.shared.canonical_models import CanonicalXML
from domains.sat.models import SATRuleResult, SATRuleStatus, SATRuleSeverity
from domains.sat.rules.base_rule import BaseSATRule

class RetencionRule(BaseSATRule):
    def evaluate(self, xml: CanonicalXML) -> SATRuleResult:
        retenciones = xml.impuestos_desglosados.get("RETENCIONES", [])
        if retenciones:
            return SATRuleResult(
                rule_name="RETENCIONES",
                status=SATRuleStatus.WARNING,
                severity=SATRuleSeverity.MEDIUM,
                explanation="El CFDI contiene retenciones. Asegure su validación cruzada contable.",
                details={"retenciones": retenciones}
            )
        return SATRuleResult(
            rule_name="RETENCIONES",
            status=SATRuleStatus.PASS,
            severity=SATRuleSeverity.LOW,
            explanation="Sin retenciones aplicables."
        )
