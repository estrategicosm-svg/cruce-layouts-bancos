from typing import List, Callable
from domains.rules.models import Rule, RuleContext, RuleResult

class RuleRegistry:
    """
    Deterministically holds in-memory references to the actual execution 
    logic (callables) for rules stored in the database.
    """
    def __init__(self):
        self._handlers = {}

    def register_handler(self, rule_id: str, handler: Callable[[RuleContext, dict], RuleResult]):
        self._handlers[rule_id] = handler

    def get_handler(self, rule_id: str) -> Callable[[RuleContext, dict], RuleResult]:
        if rule_id not in self._handlers:
            raise KeyError(f"No execution handler registered for rule ID: {rule_id}")
        return self._handlers[rule_id]
