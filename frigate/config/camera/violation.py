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

__all__ = ["ViolationRuleConfig", "ViolationTypeEnum", "ViolationSeverityEnum"]


class ViolationTypeEnum(str, Enum):
    """Rule types accepted by frigate.extras.dsl.rule_types.create_rule."""

    object_logic = "object_logic"
    zone_object = "zone_object"
    zone_sequence = "zone_sequence"
    sustained_condition = "sustained_condition"
    proximity = "proximity"
    fall_down = "fall_down"


class ViolationSeverityEnum(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


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

    # proximity
    first_object: Optional[str] = Field(default=None)
    second_object: Optional[str] = Field(default=None)
    within: Optional[int] = Field(default=None, gt=0)

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
        if self.condition:
            zones.update(m.strip() for m in re.findall(r"in_zone\(([^)]+)\)", self.condition))
            # detected(label, zone) names a zone in its second argument
            for match in re.findall(r"detected\(([^)]+)\)", self.condition):
                parts = [p.strip() for p in match.split(",")]
                if len(parts) > 1:
                    zones.add(parts[1])

        return {z for z in zones if z}

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
        if self.condition:
            for match in re.findall(r"detected\(([^)]+)\)", self.condition):
                labels.add(match.split(",")[0].strip())

        return {label for label in labels if label}
