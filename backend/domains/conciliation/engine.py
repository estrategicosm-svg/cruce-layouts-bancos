from typing import List
from domains.shared.canonical_models import CanonicalTransaction, CanonicalXML
from domains.conciliation.models import MatchResult
from domains.conciliation.resolver import PriorityResolver
from domains.conciliation.strategies import (
    BaseStrategy, UUIDMatchStrategy, ReferenceMatchStrategy, 
    SubsetSumMatchStrategy, ManyToOneMatchStrategy, SplitPaymentMatchStrategy
)

class ConciliationEngine:
    def __init__(self, strategies: List[BaseStrategy]):
        self.strategies = strategies

    def conciliate(self, transactions: List[CanonicalTransaction], xmls: List[CanonicalXML]) -> MatchResult:
        all_candidates = []
        
        # 1. Evaluate all strategies
        for strategy in self.strategies:
            candidates = strategy.evaluate(transactions, xmls)
            if candidates:
                all_candidates.extend(candidates)
                
        # 2. Resolve conflicts (Priority & Confidence)
        resolved_matches = PriorityResolver.resolve(all_candidates)
        
        # 3. Identify unmatched
        used_tx_uuids = set()
        used_xml_uuids = set()
        for match in resolved_matches:
            for t in match.transactions:
                used_tx_uuids.add(t.uuid)
            for x in match.xmls:
                used_xml_uuids.add(x.uuid_cfdi)
                
        unmatched_tx = [t for t in transactions if t.uuid not in used_tx_uuids]
        unmatched_xml = [x for x in xmls if x.uuid_cfdi not in used_xml_uuids]
        
        return MatchResult(
            matches=resolved_matches,
            unmatched_transactions=unmatched_tx,
            unmatched_xmls=unmatched_xml
        )
