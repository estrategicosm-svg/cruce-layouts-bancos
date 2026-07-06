from domains.conciliation.models import MatchExplanation

class MatchExplainer:
    """
    Generates deterministic human-readable explanations.
    """
    @staticmethod
    def explain_uuid_match(details: dict) -> MatchExplanation:
        return MatchExplanation(
            rule_name="UUID Match",
            description=f"El UUID {details.get('uuid')} fue encontrado directamente en el concepto bancario.",
            confidence_score=1.0,
            details=details
        )
        
    @staticmethod
    def explain_reference_match(details: dict) -> MatchExplanation:
        return MatchExplanation(
            rule_name="Reference Match",
            description=f"La referencia bancaria limpia {details.get('ref')} coincide con información del CFDI y el monto es exacto.",
            confidence_score=0.95,
            details=details
        )

    @staticmethod
    def explain_subset_sum(details: dict) -> MatchExplanation:
        return MatchExplanation(
            rule_name="Subset Sum Match",
            description=f"Se conciliaron {details.get('count')} CFDI porque la suma matemática exacta coincide con el depósito de {details.get('target')}.",
            confidence_score=0.75,
            details=details
        )

    @staticmethod
    def explain_many_to_one(details: dict) -> MatchExplanation:
        return MatchExplanation(
            rule_name="Many To One Match",
            description=f"Se conciliaron {details.get('count')} transacciones bancarias que sumadas coinciden exactamente con el total del CFDI de {details.get('target')}.",
            confidence_score=0.75,
            details=details
        )

    @staticmethod
    def explain_partial_match(details: dict) -> MatchExplanation:
        return MatchExplanation(
            rule_name="Split Payment Match",
            description=f"Pago parcial aplicado. Saldo aplicado: {details.get('applied')}. Saldo restante: {details.get('remaining')}.",
            confidence_score=0.85,
            details=details
        )
