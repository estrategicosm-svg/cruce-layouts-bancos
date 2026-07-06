from typing import List, Optional
from domains.rules.models import Rule, RuleType, RuleContext, RuleResult, RuleStatus
from domains.rules.repositories import RuleRepository
from domains.rules.registry import RuleRegistry
from domains.rules.validators import validate_rule_integrity, ensure_no_active_duplicates
from domains.rules.exceptions import RuleNotFoundError

class RuleEngine:
    """
    Core orchestrator for rule configuration and execution.
    """
    def __init__(self, repository: RuleRepository, registry: RuleRegistry):
        self.repository = repository
        self.registry = registry

    def register_rule(self, rule: Rule) -> None:
        validate_rule_integrity(rule)
        
        # Ensure no active duplicates of the exact same ID + Version
        existing = self.repository.get_by_id(rule.id)
        if existing:
            ensure_no_active_duplicates(rule, existing)
            
        self.repository.add(rule)

    def deactivate_rule(self, rule_id: str, version: str) -> None:
        rules = self.repository.get_by_id(rule_id)
        target = next((r for r in rules if r.version_info.version == version), None)
        if not target:
            raise RuleNotFoundError(f"Rule {rule_id} v{version} not found.")
        target.status = RuleStatus.INACTIVE

    def execute_rules(self, rule_type: RuleType, context: RuleContext) -> List[RuleResult]:
        active_rules = self.repository.get_active_by_type(rule_type)
        
        # Filter by Scope (Empresa, Ejercicio, Periodo) if context allows it
        # For simplicity, if a rule has a scope defined, it MUST match the context.
        # If it doesn't have a scope, it applies globally.
        filtered_rules = self._filter_by_scope(active_rules, context)
        
        # Order by priority descending
        ordered_rules = sorted(filtered_rules, key=lambda r: r.priority, reverse=True)
        
        results = []
        for rule in ordered_rules:
            handler = self.registry.get_handler(rule.id)
            result = handler(context, rule.config)
            results.append(result)
            
        return results

    def _filter_by_scope(self, rules: List[Rule], context: RuleContext) -> List[Rule]:
        # Helper to extract document metadata from context to match against rule scope
        ctx_rfc = None
        ctx_ejercicio = None
        ctx_periodo = None
        
        if context.document:
            ctx_rfc = getattr(context.document, "empresa_rfc", None)
            ctx_ejercicio = getattr(context.document, "ejercicio", None)
            ctx_periodo = getattr(context.document, "periodo", None)
            
        filtered = []
        for r in rules:
            if r.scope.empresa_rfc and r.scope.empresa_rfc != ctx_rfc:
                continue
            if r.scope.ejercicio and r.scope.ejercicio != ctx_ejercicio:
                continue
            if r.scope.periodo and r.scope.periodo != ctx_periodo:
                continue
            filtered.append(r)
            
        return filtered
