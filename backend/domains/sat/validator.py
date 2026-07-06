from typing import List
from domains.shared.canonical_models import CanonicalXML
from domains.sat.models import SATValidationResult, SATRuleStatus
from domains.sat.rules.base_rule import BaseSATRule

class SATValidator:
    """
    Executes a suite of deterministic SAT rules against a CanonicalXML 
    and returns a summarized validation result.
    """
    def __init__(self, rules: List[BaseSATRule]):
        self.rules = rules

    def validate(self, xml: CanonicalXML) -> SATValidationResult:
        result = SATValidationResult(uuid_cfdi=xml.uuid_cfdi, overall_status=SATRuleStatus.PASS)
        
        has_warnings = False
        has_fails = False
        
        for rule in self.rules:
            rule_result = rule.evaluate(xml)
            result.results.append(rule_result)
            
            if rule_result.status == SATRuleStatus.FAIL:
                has_fails = True
            elif rule_result.status == SATRuleStatus.WARNING:
                has_warnings = True

        if has_fails:
            result.overall_status = SATRuleStatus.FAIL
        elif has_warnings:
            result.overall_status = SATRuleStatus.WARNING
            
        return result
