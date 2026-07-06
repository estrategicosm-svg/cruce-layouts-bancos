from typing import List
from domains.rules.models import Rule, RuleStatus
from domains.rules.exceptions import RuleDuplicateError, RuleValidationError

def validate_rule_integrity(rule: Rule):
    if not rule.id or not rule.id.strip():
        raise RuleValidationError("Rule must have an ID.")
    if not rule.name or not rule.name.strip():
        raise RuleValidationError("Rule must have a name.")
    if not rule.version_info or not rule.version_info.version:
        raise RuleValidationError("Rule must have a version.")

def ensure_no_active_duplicates(new_rule: Rule, existing_rules: List[Rule]):
    for existing in existing_rules:
        if (existing.id == new_rule.id and 
            existing.version_info.version == new_rule.version_info.version and
            existing.status == RuleStatus.ACTIVE and 
            new_rule.status == RuleStatus.ACTIVE):
            raise RuleDuplicateError(f"Rule {new_rule.id} v{new_rule.version_info.version} is already active.")
