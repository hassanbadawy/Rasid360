"""Violation rule configuration.

Rasid360 violation rules live alongside the camera they apply to, so a rule and
the zones it references are validated together -- see verify_violation_rules in
frigate/config/config.py. Previously rules lived in frigate/extras/config.yml,
read by a separate process, so a rule naming a zone that did not exist loaded
cleanly and then silently never fired.
"""

from enum import Enum
from typing import Optional, Union

from pydantic import Field, model_validator

from ..base import FrigateBaseModel

__all__ = [
    "ViolationRuleConfig",
    "ViolationTypeEnum",
    "ViolationSeverityEnum",
    "ANY_ZONE",
    "COUNT_ALL",
]


class ViolationTypeEnum(str, Enum):
    """Rule types accepted by frigate.extras.dsl.rule_types.create_rule."""

    object_logic = "object_logic"
    zone_object = "zone_object"
    zone_sequence = "zone_sequence"
    sustained_condition = "sustained_condition"
    proximity = "proximity"
    fall_down = "fall_down"
    zone_occupancy = "zone_occupancy"


#: Wildcard accepted wherever a zone name is expected, meaning "any zone on this
#: camera". Kept as a sentinel string rather than an empty value because the
#: engine has to tell "match anything" apart from "not configured" -- an unset
#: from_zones/to_zone is a rule authoring error and still raises.
ANY_ZONE = "any"

#: `count_label` value meaning "every tracked object", matching Frigate's own
#: `frigate/<zone>/all` topic.
COUNT_ALL = "all"


class ViolationSeverityEnum(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


def _split_top_level(expr: str, op: str) -> list[str]:
    """Split on a boolean operator, ignoring occurrences inside parentheses.

    Mirrors ConditionParser._split_on_operator in frigate/extras/dsl/operators.py.
    Duplicated rather than imported because the DSL imports this module, and the
    grammar is three lines of splitting.
    """
    parts: list[str] = []
    depth = 0
    current = ""
    token = f" {op} "
    i = 0

    while i < len(expr):
        char = expr[i]

        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1

        if depth == 0 and expr[i : i + len(token)].upper() == token:
            parts.append(current)
            current = ""
            i += len(token)
            continue

        current += char
        i += 1

    parts.append(current)
    return [p.strip() for p in parts if p.strip()]


def unsatisfiable_condition(condition: str) -> Optional[str]:
    """Explain why a condition can never do what its author meant, or None.

    A rule is evaluated against ONE MQTT event, which describes ONE object. So
    `detected(label)` tests only that event's own label
    (DetectedOperator.evaluate). Two consequences that are invisible in the
    written form:

      detected(a) AND detected(b)      -> always False, an event has one label
      detected(a) AND NOT detected(b)  -> always True, `detected(b)` is always
                                          False so NOT of it is always True --
                                          the rule silently degenerates to
                                          `detected(a)`

    The second is the dangerous one: it reads as "a without b" and fires on
    every a. Co-presence across objects needs a rule type that keeps state
    between events, not a condition. Rejecting these at parse time is the point
    of moving rules into the config -- a condition that cannot work should be a
    hard error, not a rule that never fires or always fires.
    """
    import re

    if not condition:
        return None

    expr = " ".join(condition.split())

    def labels_anded(part: str) -> Optional[str]:
        # OR is satisfiable however its branches disagree, so recurse per branch
        or_parts = _split_top_level(part, "OR")

        if len(or_parts) > 1:
            for branch in or_parts:
                found = labels_anded(branch)
                if found:
                    return found
            return None

        and_parts = _split_top_level(part, "AND")
        labels: set[str] = set()

        for atom in and_parts:
            atom = atom.strip()

            if atom.upper().startswith("NOT "):
                inner = atom[4:].strip()
                if re.match(r"^detected\s*\(", inner, re.I):
                    return (
                        f"`{atom}` can never be false: a rule sees one object per "
                        "event, so detected() of a different label is always "
                        "false and NOT of it is always true. This rule would "
                        "fire every time, regardless of whether that object is "
                        "present."
                    )
                continue

            if atom.startswith("("):
                found = labels_anded(atom[1:-1] if atom.endswith(")") else atom)
                if found:
                    return found
                continue

            # both detected(label) and detected(label, zone) -- the zone
            # narrows where, it does not add a second object
            m = re.match(
                r"^detected\s*\(\s*([^,)]+?)\s*(?:,[^)]*)?\)$", atom, re.I
            )
            if m:
                labels.add(m.group(1).strip())

        if len(labels) > 1:
            names = ", ".join(sorted(labels))
            return (
                f"requires {names} to be detected at the same time, but a rule "
                "sees one object per event, so this can never be true. Use a "
                "rule type that tracks objects across events instead."
            )

        return None

    return labels_anded(expr)


class ViolationRuleConfig(FrigateBaseModel):
    name: str = Field(title="Rule name. Becomes the event sub_label.")
    enabled: bool = Field(default=True, title="Enable this rule.")
    type: ViolationTypeEnum = Field(title="Rule type.")
    description: str = Field(default="", title="Human readable description.")

    # Shared behaviour
    duration: int = Field(default=30, ge=1, title="Length of the created event, seconds.")
    severity: ViolationSeverityEnum = Field(default=ViolationSeverityEnum.medium)
    cooldown: int = Field(
        default=30,
        ge=0,
        title="Seconds before this rule can fire again for the same camera.",
    )
    retention_days: int = Field(default=30, ge=1)

    # zone_object / object_logic / sustained_condition
    condition: Optional[str] = Field(
        default=None,
        title="Boolean condition, e.g. 'in_zone(no_parking) AND detected(car)'.",
    )

    # sustained_condition
    monitor_duration: Optional[int] = Field(
        default=None,
        ge=1,
        title="Seconds the condition must hold continuously.",
    )

    speed_threshold: Optional[float] = Field(
        default=None,
        gt=0,
        title="Only fire above this speed. Requires the zone to set `distances`.",
    )

    # zone_sequence
    vehicle_types: Optional[list[str]] = Field(default=None)
    from_zones: Optional[list[str]] = Field(default=None)
    to_zone: Optional[str] = Field(default=None)
    min_detections: int = Field(
        default=1, ge=1, title="Consecutive detections before firing."
    )

    # fall_down
    object_type: Optional[str] = Field(default=None)
    width_height_ratio: Optional[float] = Field(default=None, gt=0)
    min_duration: Optional[Union[int, float]] = Field(default=None, ge=0)

    # zone_occupancy -- how many objects are in a zone right now.
    #
    # Fed by Frigate's own per-zone counts, which it republishes on every change
    # to `frigate/<zone>/<label>` and `frigate/<zone>/all` (see
    # CameraActivityManager). Nothing here counts objects itself.
    zone: Optional[str] = Field(
        default=None, title="Zone whose occupancy is watched."
    )
    count_label: str = Field(
        default="all",
        title="Object label to count, or 'all' for every tracked object.",
    )
    min_count: Optional[int] = Field(
        default=None,
        ge=0,
        title="Fire when the count drops below this, e.g. a post left unmanned.",
    )
    max_count: Optional[int] = Field(
        default=None,
        ge=0,
        title="Fire when the count rises above this, e.g. overcrowding.",
    )

    # proximity
    first_object: Optional[str] = Field(default=None)
    second_object: Optional[str] = Field(default=None)
    within: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def check_condition_can_work(self):
        """Reject a condition that cannot mean what it looks like it means."""
        problem = unsatisfiable_condition(self.condition)

        if problem:
            raise ValueError(f"Violation rule '{self.name}' {problem}")

        return self

    @model_validator(mode="after")
    def check_required_fields_for_type(self):
        """Mirror the required-field checks in dsl/rule_types.py, but at config
        parse time so a bad rule is reported before the worker starts."""
        missing: list[str] = []

        if self.type in (
            ViolationTypeEnum.object_logic,
            ViolationTypeEnum.zone_object,
            ViolationTypeEnum.sustained_condition,
        ):
            if not self.condition:
                missing.append("condition")

        if self.type == ViolationTypeEnum.sustained_condition:
            if not self.monitor_duration:
                missing.append("monitor_duration")

        if self.type == ViolationTypeEnum.zone_sequence:
            if not self.from_zones:
                missing.append("from_zones")
            if not self.to_zone:
                missing.append("to_zone")

        if self.type == ViolationTypeEnum.fall_down:
            if not self.width_height_ratio:
                missing.append("width_height_ratio")

        if self.type == ViolationTypeEnum.zone_occupancy:
            if not self.zone:
                missing.append("zone")
            if self.min_count is None and self.max_count is None:
                missing.append("min_count or max_count")
            elif (
                self.min_count is not None
                and self.max_count is not None
                and self.min_count > self.max_count
            ):
                raise ValueError(
                    f"Violation rule '{self.name}' has min_count "
                    f"({self.min_count}) greater than max_count "
                    f"({self.max_count}), so it can never be satisfied."
                )

        if self.type == ViolationTypeEnum.proximity:
            if not self.first_object:
                missing.append("first_object")
            if not self.second_object:
                missing.append("second_object")

        if missing:
            raise ValueError(
                f"Violation rule '{self.name}' of type '{self.type.value}' is missing: "
                + ", ".join(missing)
            )

        return self

    def referenced_zones(self) -> set[str]:
        """Zone names this rule depends on, from both structured fields and the
        condition string."""
        import re

        zones: set[str] = set()

        if self.from_zones:
            zones.update(self.from_zones)
        if self.to_zone:
            zones.add(self.to_zone)
        if self.zone:
            zones.add(self.zone)
        if self.condition:
            zones.update(m.strip() for m in re.findall(r"in_zone\(([^)]+)\)", self.condition))
            # detected(label, zone) names a zone in its second argument
            for match in re.findall(r"detected\(([^)]+)\)", self.condition):
                parts = [p.strip() for p in match.split(",")]
                if len(parts) > 1:
                    zones.add(parts[1])

        # ANY_ZONE is a wildcard, not a zone name -- verify_violation_rules would
        # otherwise reject every rule that uses it.
        return {z for z in zones if z and z != ANY_ZONE}

    def referenced_labels(self) -> set[str]:
        """Object labels this rule depends on."""
        import re

        labels: set[str] = set()

        if self.vehicle_types:
            labels.update(self.vehicle_types)
        if self.object_type:
            labels.add(self.object_type)
        if self.first_object:
            labels.add(self.first_object)
        if self.second_object:
            labels.add(self.second_object)
        # "all" is a wildcard over the camera's tracked objects, not a label
        if self.count_label and self.count_label != COUNT_ALL:
            labels.add(self.count_label)
        if self.condition:
            for match in re.findall(r"detected\(([^)]+)\)", self.condition):
                labels.add(match.split(",")[0].strip())

        return {label for label in labels if label}
