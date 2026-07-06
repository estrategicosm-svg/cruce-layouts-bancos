from typing import List, Optional
from decimal import Decimal
from domains.shared.canonical_models import CanonicalTransaction, CanonicalXML
from domains.conciliation.tolerance import ToleranceEngine
from domains.conciliation.explainer import MatchExplainer
from domains.conciliation.models import MatchCandidate, MatchStatus

class BaseStrategy:
    def __init__(self, tolerance: ToleranceEngine):
        self.tolerance = tolerance
        
    def evaluate(self, transactions: List[CanonicalTransaction], xmls: List[CanonicalXML]) -> List[MatchCandidate]:
        raise NotImplementedError

class UUIDMatchStrategy(BaseStrategy):
    def evaluate(self, transactions: List[CanonicalTransaction], xmls: List[CanonicalXML]) -> List[MatchCandidate]:
        candidates = []
        for t in transactions:
            for x in xmls:
                if x.uuid_cfdi and x.uuid_cfdi.upper() in (t.concepto_original or "").upper():
                    if self.tolerance.amounts_match(t.monto_absoluto, x.total):
                        candidates.append(MatchCandidate(
                            transactions=[t],
                            xmls=[x],
                            status=MatchStatus.EXACT,
                            strategy_used="UUID",
                            confidence=1.0,
                            explanations=[MatchExplainer.explain_uuid_match({"uuid": x.uuid_cfdi})]
                        ))
        return candidates

class ReferenceMatchStrategy(BaseStrategy):
    def evaluate(self, transactions: List[CanonicalTransaction], xmls: List[CanonicalXML]) -> List[MatchCandidate]:
        candidates = []
        for t in transactions:
            for x in xmls:
                if t.referencia_bancaria_limpia and self.tolerance.amounts_match(t.monto_absoluto, x.total):
                    if t.referencia_bancaria_limpia in x.uuid_cfdi.upper().replace("-", ""):
                        candidates.append(MatchCandidate(
                            transactions=[t],
                            xmls=[x],
                            status=MatchStatus.EXACT,
                            strategy_used="REFERENCE",
                            confidence=0.95,
                            explanations=[MatchExplainer.explain_reference_match({"ref": t.referencia_bancaria_limpia})]
                        ))
        return candidates

class SubsetSumMatchStrategy(BaseStrategy):
    """
    1:N Match. One transaction against many XMLs.
    Uses branch and bound with sorting for O(2^n) worst-case but O(n log n + K) in practice with pruning.
    """
    def evaluate(self, transactions: List[CanonicalTransaction], xmls: List[CanonicalXML]) -> List[MatchCandidate]:
        candidates = []
        # Filter positive total XMLs
        valid_xmls = [x for x in xmls if x.total > 0]
        
        for t in transactions:
            target = t.monto_absoluto
            
            # Fast prune: if single max XML > target and no tolerance? We can prune during search.
            # Convert to cents to avoid float precision issues during sum
            target_cents = int(target * 100)
            
            # Sort descending to reach target faster and prune earlier
            sorted_xmls = sorted(valid_xmls, key=lambda x: x.total, reverse=True)
            
            # Simple DFS with branch and bound
            def search(index: int, current_sum: int, current_subset: List[CanonicalXML]):
                if current_sum == target_cents: # Or within tolerance
                    return current_subset
                if current_sum > target_cents or index >= len(sorted_xmls):
                    return None
                    
                # Include
                res = search(index + 1, current_sum + int(sorted_xmls[index].total * 100), current_subset + [sorted_xmls[index]])
                if res: return res
                
                # Exclude
                return search(index + 1, current_sum, current_subset)

            subset = search(0, 0, [])
            if subset and len(subset) > 1:
                candidates.append(MatchCandidate(
                    transactions=[t],
                    xmls=subset,
                    status=MatchStatus.EXACT,
                    strategy_used="SUBSET_SUM",
                    confidence=0.75,
                    explanations=[MatchExplainer.explain_subset_sum({"count": len(subset), "target": float(target)})]
                ))
        return candidates

class OneToManyMatchStrategy(BaseStrategy):
    """
    Wrapper for 1:N relations, practically handled by Subset Sum if exact,
    or partial payments if sums don't match.
    """
    def evaluate(self, transactions: List[CanonicalTransaction], xmls: List[CanonicalXML]) -> List[MatchCandidate]:
        # Implementation depends on business logic, normally subset sum covers exact 1:N.
        # Here we can use it for partials.
        return []

class ManyToOneMatchStrategy(BaseStrategy):
    """
    N:1 Match. Many transactions against one XML.
    Reverse of Subset Sum.
    """
    def evaluate(self, transactions: List[CanonicalTransaction], xmls: List[CanonicalXML]) -> List[MatchCandidate]:
        candidates = []
        valid_tx = [t for t in transactions if t.monto_absoluto > 0]
        
        for x in xmls:
            target_cents = int(x.total * 100)
            sorted_tx = sorted(valid_tx, key=lambda t: t.monto_absoluto, reverse=True)
            
            def search(index: int, current_sum: int, current_subset: List[CanonicalTransaction]):
                if current_sum == target_cents:
                    return current_subset
                if current_sum > target_cents or index >= len(sorted_tx):
                    return None
                res = search(index + 1, current_sum + int(sorted_tx[index].monto_absoluto * 100), current_subset + [sorted_tx[index]])
                if res: return res
                return search(index + 1, current_sum, current_subset)

            subset = search(0, 0, [])
            if subset and len(subset) > 1:
                candidates.append(MatchCandidate(
                    transactions=subset,
                    xmls=[x],
                    status=MatchStatus.EXACT,
                    strategy_used="MANY_TO_ONE",
                    confidence=0.75,
                    explanations=[MatchExplainer.explain_many_to_one({"count": len(subset), "target": float(x.total)})]
                ))
        return candidates

class SplitPaymentMatchStrategy(BaseStrategy):
    """
    Handles partial payments where amount applied < total invoice.
    Requires RFC or Reference match to justify linking them when amounts differ.
    """
    def evaluate(self, transactions: List[CanonicalTransaction], xmls: List[CanonicalXML]) -> List[MatchCandidate]:
        candidates = []
        for t in transactions:
            for x in xmls:
                if x.uuid_cfdi and x.uuid_cfdi.upper() in (t.concepto_original or "").upper():
                    if t.monto_absoluto < x.total:
                        candidates.append(MatchCandidate(
                            transactions=[t],
                            xmls=[x],
                            status=MatchStatus.PARTIAL,
                            strategy_used="SPLIT_PAYMENT",
                            confidence=0.85,
                            partial_applied_amount=float(t.monto_absoluto),
                            partial_remaining_amount=float(x.total - t.monto_absoluto),
                            explanations=[MatchExplainer.explain_partial_match({"applied": float(t.monto_absoluto), "remaining": float(x.total - t.monto_absoluto)})]
                        ))
        return candidates
