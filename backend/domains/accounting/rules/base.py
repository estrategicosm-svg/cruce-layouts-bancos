from abc import ABC, abstractmethod
from typing import Optional
from domains.shared.canonical_models import CanonicalXML, CanonicalTransaction
from domains.configuration.models import GeneralConfiguration
from domains.accounting.models import AccountingRuleResult

class BaseAccountingRule(ABC):
    """
    Base class for accounting rules.
    Takes CanonicalXML, Transaction and the Configuration block.
    """
    @abstractmethod
    def evaluate(
        self, 
        xml: Optional[CanonicalXML], 
        tx: Optional[CanonicalTransaction], 
        config: GeneralConfiguration
    ) -> AccountingRuleResult:
        pass
