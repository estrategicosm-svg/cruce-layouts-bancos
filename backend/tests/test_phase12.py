import unittest
from datetime import date
from typing import List, Optional

from domains.rules.models import (
    Rule, RuleVersion, RuleType, RuleStatus, RulePriority, RuleScope, RuleContext, RuleResult
)
from domains.rules.engine import RuleEngine
from domains.rules.registry import RuleRegistry
from domains.rules.repositories import RuleRepository
from domains.rules.exceptions import RuleDuplicateError, RuleNotFoundError, RuleValidationError
from domains.shared.canonical_models import CanonicalDocument

class MockRuleRepository(RuleRepository):
    def __init__(self):
        self._rules = []
        
    def add(self, rule: Rule) -> None:
        self._rules.append(rule)
        
    def get_by_id(self, rule_id: str) -> List[Rule]:
        return [r for r in self._rules if r.id == rule_id]
        
    def get_all(self) -> List[Rule]:
        return self._rules
        
    def get_active_by_type(self, rule_type: RuleType) -> List[Rule]:
        return [r for r in self._rules if r.rule_type == rule_type and r.status == RuleStatus.ACTIVE]

def mock_handler_pass(context: RuleContext, config: dict) -> RuleResult:
    return RuleResult(rule_id="RULE_001", passed=True, message="Passed")

def mock_handler_fail(context: RuleContext, config: dict) -> RuleResult:
    return RuleResult(rule_id="RULE_002", passed=False, message="Failed")

class TestPhase12(unittest.TestCase):
    def setUp(self):
        self.repo = MockRuleRepository()
        self.registry = RuleRegistry()
        self.engine = RuleEngine(repository=self.repo, registry=self.registry)
        
        self.registry.register_handler("RULE_001", mock_handler_pass)
        self.registry.register_handler("RULE_002", mock_handler_fail)

    def test_register_rule_success(self):
        rule = Rule(
            id="RULE_001",
            name="Test Rule 1",
            description="A test rule",
            rule_type=RuleType.VALIDATION,
            version_info=RuleVersion(version="1.0", fecha_inicio=date(2024, 1, 1))
        )
        self.engine.register_rule(rule)
        self.assertEqual(len(self.repo.get_all()), 1)

    def test_register_duplicate_active_rule(self):
        rule1 = Rule(
            id="RULE_001", name="Test Rule 1", description="desc",
            rule_type=RuleType.VALIDATION, version_info=RuleVersion(version="1.0", fecha_inicio=date(2024, 1, 1))
        )
        rule2 = Rule(
            id="RULE_001", name="Test Rule 1 updated", description="desc",
            rule_type=RuleType.VALIDATION, version_info=RuleVersion(version="1.0", fecha_inicio=date(2024, 1, 1))
        )
        
        self.engine.register_rule(rule1)
        with self.assertRaises(RuleDuplicateError):
            self.engine.register_rule(rule2)

    def test_deactivate_rule(self):
        rule = Rule(
            id="RULE_001", name="Test Rule 1", description="desc",
            rule_type=RuleType.VALIDATION, version_info=RuleVersion(version="1.0", fecha_inicio=date(2024, 1, 1))
        )
        self.engine.register_rule(rule)
        
        self.engine.deactivate_rule("RULE_001", "1.0")
        rules = self.repo.get_by_id("RULE_001")
        self.assertEqual(rules[0].status, RuleStatus.INACTIVE)
        
        with self.assertRaises(RuleNotFoundError):
            self.engine.deactivate_rule("NONEXISTENT", "1.0")

    def test_execute_rules_priority_and_filtering(self):
        r1 = Rule(
            id="RULE_001", name="R1", description="d", rule_type=RuleType.VALIDATION,
            priority=RulePriority.LOW, version_info=RuleVersion(version="1.0", fecha_inicio=date(2024, 1, 1))
        )
        r2 = Rule(
            id="RULE_002", name="R2", description="d", rule_type=RuleType.VALIDATION,
            priority=RulePriority.HIGH, version_info=RuleVersion(version="1.0", fecha_inicio=date(2024, 1, 1))
        )
        
        self.engine.register_rule(r1)
        self.engine.register_rule(r2)
        
        ctx = RuleContext()
        results = self.engine.execute_rules(RuleType.VALIDATION, ctx)
        
        # High priority should execute first
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].rule_id, "RULE_002")
        self.assertEqual(results[1].rule_id, "RULE_001")
        self.assertFalse(results[0].passed)
        self.assertTrue(results[1].passed)

    def test_scope_filtering(self):
        r1 = Rule(
            id="RULE_001", name="R1", description="d", rule_type=RuleType.VALIDATION,
            scope=RuleScope(empresa_rfc="TEST1"), version_info=RuleVersion(version="1.0", fecha_inicio=date(2024, 1, 1))
        )
        self.engine.register_rule(r1)
        
        # Context without matching RFC should yield no rules
        ctx_no_rfc = RuleContext()
        res_empty = self.engine.execute_rules(RuleType.VALIDATION, ctx_no_rfc)
        self.assertEqual(len(res_empty), 0)
        
        # Context with matching RFC should yield the rule
        doc = CanonicalDocument(uuid="doc1", tipo="PDF", tamanio_bytes=100, hash_sha256="h", empresa_rfc="TEST1")
        
        ctx_with_rfc = RuleContext(document=doc)
        res_match = self.engine.execute_rules(RuleType.VALIDATION, ctx_with_rfc)
        self.assertEqual(len(res_match), 1)

if __name__ == "__main__":
    unittest.main()
