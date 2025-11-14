"""DSL (Domain-Specific Language) Engine for Violation Detection

This module provides a flexible DSL for defining violation rules in YAML configuration
without requiring Python code changes.

Key Components:
- parser: Parse YAML rules into Rule objects
- operators: Core operators (detected, in_zone, boolean logic)
- evaluator: Evaluate rules against Frigate events
- validator: Validate rules at startup
- rule_types: Different rule type implementations
"""

from .parser import RuleParser
from .evaluator import RuleEvaluator
from .validator import RuleValidator
from .operators import Operator, DetectedOperator, InZoneOperator, BooleanOperator
from .rule_types import Rule, ObjectLogicRule, ZoneObjectRule, ZoneSequenceRule

__all__ = [
    "RuleParser",
    "RuleEvaluator",
    "RuleValidator",
    "Operator",
    "DetectedOperator",
    "InZoneOperator",
    "BooleanOperator",
    "Rule",
    "ObjectLogicRule",
    "ZoneObjectRule",
    "ZoneSequenceRule",
]
