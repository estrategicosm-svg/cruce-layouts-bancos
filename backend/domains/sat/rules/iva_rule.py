from domains.shared.canonical_models import CanonicalXML
from domains.sat.models import SATRuleResult, SATRuleStatus, SATRuleSeverity
from domains.sat.rules.base_rule import BaseSATRule

class IVARule(BaseSATRule):
    """
    Validates IVA rates (16%, 8%, 0%, Exento).
    """
    def evaluate(self, xml: CanonicalXML) -> SATRuleResult:
        # En CanonicalXML de fase 4 guardamos `impuestos_desglosados`
        iva = xml.impuestos_desglosados.get("IVA", [])
        
        if not iva:
            return SATRuleResult(
                rule_name="IVA_VALIDATION",
                status=SATRuleStatus.WARNING,
                severity=SATRuleSeverity.MEDIUM,
                explanation="No se detectó IVA desglosado. Puede ser Exento o error de extracción."
            )
            
        tasas = [t.get("TasaOCuota") for t in iva if "TasaOCuota" in t]
        
        # Valid tasas: 0.160000, 0.080000, 0.000000
        invalid_tasas = [t for t in tasas if t not in ("0.160000", "0.080000", "0.000000")]
        
        if invalid_tasas:
             return SATRuleResult(
                rule_name="IVA_VALIDATION",
                status=SATRuleStatus.FAIL,
                severity=SATRuleSeverity.HIGH,
                explanation=f"Se detectaron tasas de IVA no estándar o inválidas: {invalid_tasas}"
            )
            
        return SATRuleResult(
            rule_name="IVA_VALIDATION",
            status=SATRuleStatus.PASS,
            severity=SATRuleSeverity.LOW,
            explanation=f"Tasas de IVA válidas: {tasas}"
        )
