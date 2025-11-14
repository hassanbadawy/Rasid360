"""Core operators for DSL evaluation

Operators handle the atomic operations in violation rules:
- detected(label): Check if object is detected
- detected(label, zone): Check if object is detected in specific zone
- in_zone(zone): Check if object is in zone
- Boolean operators: AND, OR, NOT
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import re


class Operator(ABC):
    """Base class for all operators"""

    @abstractmethod
    def evaluate(self, event_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        Evaluate operator against event data

        Args:
            event_data: Event data from Frigate MQTT
            context: Additional context (camera config, state, etc.)

        Returns:
            True if condition is met, False otherwise
        """
        pass


class DetectedOperator(Operator):
    """
    Operator: detected(label) or detected(label, zone)

    Checks if an object with the given label is detected,
    optionally in a specific zone.
    """

    def __init__(self, label: str, zone: Optional[str] = None):
        self.label = label
        self.zone = zone

    def evaluate(self, event_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
        after = event_data.get("after", {})

        # Check if label matches
        if after.get("label") != self.label:
            return False

        # If zone specified, check if object is in that zone
        if self.zone:
            current_zones = after.get("current_zones", [])
            return self.zone in current_zones

        # No zone specified, just check if detected
        return True

    def __repr__(self):
        if self.zone:
            return f"detected({self.label}, {self.zone})"
        return f"detected({self.label})"


class InZoneOperator(Operator):
    """
    Operator: in_zone(zone)

    Checks if the current object is in the specified zone.
    """

    def __init__(self, zone: str):
        self.zone = zone

    def evaluate(self, event_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
        after = event_data.get("after", {})
        current_zones = after.get("current_zones", [])
        return self.zone in current_zones

    def __repr__(self):
        return f"in_zone({self.zone})"


class BooleanOperator(Operator):
    """
    Boolean operators: AND, OR, NOT

    Combines multiple operators using boolean logic.
    """

    def __init__(self, operator: str, operands: List[Operator]):
        """
        Args:
            operator: "AND", "OR", or "NOT"
            operands: List of operators to combine
        """
        self.operator = operator.upper()
        self.operands = operands

        if self.operator not in ["AND", "OR", "NOT"]:
            raise ValueError(f"Invalid boolean operator: {operator}")

        if self.operator == "NOT" and len(operands) != 1:
            raise ValueError("NOT operator requires exactly one operand")

    def evaluate(self, event_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
        if self.operator == "AND":
            return all(op.evaluate(event_data, context) for op in self.operands)
        elif self.operator == "OR":
            return any(op.evaluate(event_data, context) for op in self.operands)
        elif self.operator == "NOT":
            return not self.operands[0].evaluate(event_data, context)
        return False

    def __repr__(self):
        if self.operator == "NOT":
            return f"NOT {self.operands[0]}"
        op_str = f" {self.operator} ".join(str(op) for op in self.operands)
        return f"({op_str})"


class ConditionParser:
    """
    Parse string conditions into operator trees

    Supports syntax:
    - detected(label)
    - detected(label, zone)
    - in_zone(zone)
    - condition AND condition
    - condition OR condition
    - NOT condition
    - Parentheses for grouping
    """

    def parse(self, condition_str: str) -> Operator:
        """
        Parse condition string into operator tree

        Args:
            condition_str: Condition string (e.g., "detected(car) AND in_zone(zone1)")

        Returns:
            Operator tree

        Raises:
            ValueError: If condition syntax is invalid
        """
        # Remove extra whitespace
        condition_str = " ".join(condition_str.split())

        try:
            return self._parse_expression(condition_str)
        except Exception as e:
            raise ValueError(f"Invalid condition syntax: {condition_str}. Error: {e}")

    def _parse_expression(self, expr: str) -> Operator:
        """Parse boolean expression with AND/OR precedence"""
        # Handle OR (lowest precedence)
        or_parts = self._split_on_operator(expr, "OR")
        if len(or_parts) > 1:
            return BooleanOperator("OR", [self._parse_and_expr(part) for part in or_parts])

        return self._parse_and_expr(expr)

    def _parse_and_expr(self, expr: str) -> Operator:
        """Parse AND expression"""
        and_parts = self._split_on_operator(expr, "AND")
        if len(and_parts) > 1:
            return BooleanOperator("AND", [self._parse_not_expr(part) for part in and_parts])

        return self._parse_not_expr(expr)

    def _parse_not_expr(self, expr: str) -> Operator:
        """Parse NOT expression"""
        expr = expr.strip()

        if expr.upper().startswith("NOT "):
            inner = expr[4:].strip()
            return BooleanOperator("NOT", [self._parse_atom(inner)])

        return self._parse_atom(expr)

    def _parse_atom(self, expr: str) -> Operator:
        """Parse atomic expression (function call or parenthesized expression)"""
        expr = expr.strip()

        # Handle parentheses
        if expr.startswith("(") and expr.endswith(")"):
            return self._parse_expression(expr[1:-1])

        # Handle function calls
        if "(" in expr and expr.endswith(")"):
            func_match = re.match(r"(\w+)\((.*)\)", expr)
            if func_match:
                func_name = func_match.group(1)
                args_str = func_match.group(2)
                args = [arg.strip() for arg in args_str.split(",") if arg.strip()]

                if func_name == "detected":
                    if len(args) == 1:
                        return DetectedOperator(args[0])
                    elif len(args) == 2:
                        return DetectedOperator(args[0], args[1])
                    else:
                        raise ValueError(f"detected() takes 1 or 2 arguments, got {len(args)}")

                elif func_name == "in_zone":
                    if len(args) == 1:
                        return InZoneOperator(args[0])
                    else:
                        raise ValueError(f"in_zone() takes 1 argument, got {len(args)}")

                else:
                    raise ValueError(f"Unknown function: {func_name}")

        raise ValueError(f"Invalid atom expression: {expr}")

    def _split_on_operator(self, expr: str, operator: str) -> List[str]:
        """
        Split expression on operator, respecting parentheses and function calls

        Args:
            expr: Expression to split
            operator: Operator to split on (e.g., "AND", "OR")

        Returns:
            List of parts split by operator
        """
        parts = []
        current = []
        paren_depth = 0
        i = 0

        while i < len(expr):
            char = expr[i]

            if char == "(":
                paren_depth += 1
                current.append(char)
            elif char == ")":
                paren_depth -= 1
                current.append(char)
            elif paren_depth == 0:
                # Check if we're at the operator
                remaining = expr[i:]
                if remaining.upper().startswith(operator + " ") or remaining.upper() == operator:
                    # Found operator at top level
                    if current:
                        parts.append("".join(current).strip())
                        current = []
                    i += len(operator)
                    continue
                else:
                    current.append(char)
            else:
                current.append(char)

            i += 1

        if current:
            parts.append("".join(current).strip())

        return parts if len(parts) > 1 else [expr]
