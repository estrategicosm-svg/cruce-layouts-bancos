from domains.shared.canonical_models import CanonicalXML
from domains.sat.models import SATRuleResult, SATRuleStatus, SATRuleSeverity
from domains.sat.rules.base_rule import BaseSATRule

class CFDIStatusRule(BaseSATRule):
    def evaluate(self, xml: CanonicalXML) -> SATRuleResult:
        if xml.estado_cancelacion == "CANCELADO":
            return SATRuleResult(
                rule_name="CFDI_STATUS",
                status=SATRuleStatus.FAIL,
                severity=SATRuleSeverity.CRITICAL,
                explanation="El CFDI se encuentra CANCELADO localmente. No es válido para deducir o acreditar."
            )
            
        return SATRuleResult(
            rule_name="CFDI_STATUS",
            status=SATRuleStatus.PASS,
            severity=SATRuleSeverity.LOW,
            explanation="El CFDI está VIGENTE localmente."
        )
