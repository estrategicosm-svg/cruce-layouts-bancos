from typing import List, Dict
from domains.conciliation.models import MatchCandidate

class PriorityResolver:
    """
    Resolves conflicts when multiple strategies find matches for the same items.
    """
    PRIORITY_MAP = {
        "UUID": 100,
        "REFERENCE": 95,
        "SPLIT_PAYMENT": 85,
        "SUBSET_SUM": 75,
        "MANY_TO_ONE": 75,
        "UNKNOWN": 0
    }
    
    @classmethod
    def get_priority(cls, strategy: str) -> int:
        return cls.PRIORITY_MAP.get(strategy, 0)

    @classmethod
    def resolve(cls, candidates: List[MatchCandidate]) -> List[MatchCandidate]:
        # Sort candidates by confidence and priority
        sorted_candidates = sorted(
            candidates, 
            key=lambda c: (c.confidence, cls.get_priority(c.strategy_used)), 
            reverse=True
        )
        
        resolved = []
        used_tx_uuids = set()
        used_xml_uuids = set()
        
        for candidate in sorted_candidates:
            # Check if any part of the candidate is already used
            # For strict 1:1, 1:N, N:1 without overlapping groups
            tx_ids = {t.uuid for t in candidate.transactions}
            xml_ids = {x.uuid_cfdi for x in candidate.xmls}
            
            # If there's an overlap, we skip this candidate in favor of the higher priority one
            if tx_ids.intersection(used_tx_uuids) or xml_ids.intersection(used_xml_uuids):
                # Unless it's a partial payment logic, which we can handle later if needed.
                # For this baseline determinism, we skip.
                continue
                
            resolved.append(candidate)
            used_tx_uuids.update(tx_ids)
            used_xml_uuids.update(xml_ids)
            
        return resolved
