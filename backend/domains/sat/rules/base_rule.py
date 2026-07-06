from abc import ABC, abstractmethod
from domains.shared.canonical_models import CanonicalXML
from domains.sat.models import SATRuleResult

class BaseSATRule(ABC):
    @abstractmethod
    def evaluate(self, xml: CanonicalXML) -> SATRuleResult:
        pass
