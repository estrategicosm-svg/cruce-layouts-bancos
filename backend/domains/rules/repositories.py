from abc import ABC, abstractmethod
from typing import List, Optional
from domains.rules.models import Rule, RuleType

class RuleRepository(ABC):
    @abstractmethod
    def add(self, rule: Rule) -> None: pass
    
    @abstractmethod
    def get_by_id(self, rule_id: str) -> List[Rule]: pass
    
    @abstractmethod
    def get_all(self) -> List[Rule]: pass
    
    @abstractmethod
    def get_active_by_type(self, rule_type: RuleType) -> List[Rule]: pass
