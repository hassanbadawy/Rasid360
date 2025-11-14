# Frigate DSL Violation Detection System

## Overview

The DSL (Domain-Specific Language) Violation Detection System allows you to define custom violation rules in YAML configuration without writing Python code. This system supports complex violation patterns including object detection logic, zone sequences, temporal conditions, and custom actions.

## Quick Start

### 1. Basic Configuration Structure

```yaml
actions:
  dsl_violations:
    enabled: true

    # Global reusable templates
    violation_templates:
      template_name:
        type: rule_type
        # Template-specific configuration
        param: "{placeholder}"  # Parametrizable values

    # Camera-specific violations
    cameras:
      camera_name:
        violations:
          - name: violation_name
            template: template_name
            params:
              placeholder: actual_value
```

### 2. Simple Example

```yaml
actions:
  dsl_violations:
    enabled: true

    violation_templates:
      restricted_zone:
        type: zone_object
        condition: "in_zone({zone}) AND detected({object})"
        duration: 20
        severity: medium

    cameras:
      front_camera:
        violations:
          - name: person_in_danger_zone
            template: restricted_zone
            params:
              zone: danger_zone
              object: person
```

## Rule Types

### 1. Object Logic Rules

**Type**: `object_logic`

Boolean logic on object detection states.

**Configuration**:
```yaml
violation_name:
  type: object_logic
  condition: "detected(object1) AND NOT detected(object2)"
  duration: 30          # Event duration in seconds
  severity: critical    # critical/high/medium/low
  cooldown: 30         # Seconds before re-alerting same object
```

**Supported Operators**:
- `detected(label)` - Object is detected
- `detected(label, zone)` - Object detected in specific zone
- `AND` - Both conditions must be true
- `OR` - Either condition must be true
- `NOT` - Condition must be false
- Parentheses for grouping: `(cond1 OR cond2) AND cond3`

**Examples**:
```yaml
# Electrical hazard without safety equipment
electrical_hazard:
  type: object_logic
  condition: "detected(transformer) AND NOT detected(fire_extinguisher)"
  severity: critical

# Person or vehicle in restricted area
unauthorized_access:
  type: object_logic
  condition: "detected(person, restricted_zone) OR detected(vehicle, restricted_zone)"
  severity: high
```

### 2. Zone + Object Rules

**Type**: `zone_object`

Combines zone presence with object detection.

**Configuration**:
```yaml
violation_name:
  type: zone_object
  condition: "in_zone(zone_name) AND detected(object_label)"
  duration: 20
  severity: medium
```

**Operators**:
- `in_zone(zone)` - Object currently in zone
- `detected(label)` - Object type detected
- Boolean operators: AND, OR, NOT

**Examples**:
```yaml
# Red zone violation
red_zone_alert:
  type: zone_object
  condition: "in_zone(red_zone) AND (detected(person) OR detected(vehicle))"
  severity: high

# Equipment in safe zone
safe_operation:
  type: zone_object
  condition: "in_zone(safe_zone) AND detected(heavy_equipment)"
  severity: low
```

### 3. Zone Sequence Rules

**Type**: `zone_sequence`

Tracks objects moving through a sequence of zones.

**Configuration**:
```yaml
violation_name:
  type: zone_sequence
  vehicle_types: [car, bus, truck, motorcycle]
  from_zones: [zone1, zone2]  # Valid starting zones
  to_zone: violation_zone      # Violation zone
  duration: 30
  severity: high
```

**Use Cases**:
- Wrong-way traffic detection
- Unauthorized path tracking
- Access control violations

**Examples**:
```yaml
# Wrong-way vehicle detection
wrong_way:
  type: zone_sequence
  vehicle_types: [car, bus, truck, motorcycle]
  from_zones: [lane1, lane2]
  to_zone: wrong_way_zone
  severity: high

# Unauthorized vehicle path
restricted_path:
  type: zone_sequence
  vehicle_types: [car, truck]
  from_zones: [public_area]
  to_zone: restricted_area
  severity: critical
```

### 4. Sustained Condition Rules

**Type**: `sustained_condition`

Triggers when a condition remains true for a specified duration.

**Configuration**:
```yaml
violation_name:
  type: sustained_condition
  condition: "detected(object1) AND NOT detected(object2)"
  monitor_duration: 30  # Must be true for 30 seconds
  duration: 30          # Event duration
  severity: critical
```

**Use Cases**:
- Missing safety equipment over time
- Loitering detection
- Equipment without operator

**Examples**:
```yaml
# Equipment without flagman for 30 seconds
missing_flagman:
  type: sustained_condition
  condition: "detected(heavy_equipment) AND NOT detected(flagman)"
  monitor_duration: 30
  severity: critical

# Person in hazard zone too long
loitering_hazard:
  type: sustained_condition
  condition: "detected(person, hazard_zone)"
  monitor_duration: 60
  severity: high
```

### 5. Proximity Rules

**Type**: `proximity`

Detects when two objects appear within a time window.

**Configuration**:
```yaml
violation_name:
  type: proximity
  first_object: equipment
  second_object: person
  within: 5  # Seconds
  duration: 30
  severity: medium
```

**Use Cases**:
- Unsafe proximity to equipment
- Coordination violations
- Temporal safety checks

**Examples**:
```yaml
# Person near operating equipment
unsafe_proximity:
  type: proximity
  first_object: heavy_equipment
  second_object: person
  within: 10
  severity: high
```

## Template System

### Global Templates

Define reusable violation patterns with parameters:

```yaml
violation_templates:
  # Template with parameters
  missing_ppe:
    type: object_logic
    condition: "detected({worker}) AND NOT detected({ppe})"
    monitor_duration: 0
    severity: critical
    cooldown: 30

  wrong_way:
    type: zone_sequence
    vehicle_types: [car, bus, truck, motorcycle]
    from_zones: "{from}"
    to_zone: "{to}"
    duration: 30
    severity: high
```

### Using Templates

Apply templates with specific parameters:

```yaml
cameras:
  construction_site:
    violations:
      # Hard hat requirement
      - name: missing_hardhat
        template: missing_ppe
        params:
          worker: worker
          ppe: hardhat

      # Safety vest requirement
      - name: missing_vest
        template: missing_ppe
        params:
          worker: worker
          ppe: safety_vest

      # Wrong-way detection
      - name: wrong_way_lane1
        template: wrong_way
        params:
          from: [lane1, lane2]
          to: oncoming_lane
```

## Configuration Options

### Rule-Level Options

```yaml
violation_name:
  type: rule_type

  # Core options
  duration: 30            # Event duration in Frigate (seconds)
  severity: high          # critical/high/medium/low
  cooldown: 30            # Seconds before re-alerting same object
  retention_days: 30      # Override default retention (optional)

  # Description
  description: "Human-readable description of violation"
```

### Severity Levels

- `critical` - Immediate safety hazards
- `high` - Significant violations
- `medium` - Moderate concerns
- `low` - Minor infractions

## Complete Examples

### Construction Site Safety

```yaml
actions:
  dsl_violations:
    enabled: true

    violation_templates:
      missing_ppe:
        type: object_logic
        condition: "detected({worker}) AND NOT detected({ppe})"
        severity: critical
        cooldown: 60

      restricted_zone:
        type: zone_object
        condition: "in_zone({zone}) AND detected({object})"
        severity: high
        cooldown: 30

    cameras:
      construction_main:
        violations:
          - name: missing_hardhat
            template: missing_ppe
            params:
              worker: worker
              ppe: hardhat

          - name: missing_gloves
            template: missing_ppe
            params:
              worker: worker
              ppe: gloves

          - name: red_zone_violation
            template: restricted_zone
            params:
              zone: red_zone
              object: person

          - name: equipment_without_spotter
            type: sustained_condition
            condition: "detected(heavy_equipment) AND NOT detected(spotter)"
            monitor_duration: 30
            severity: critical
```

### Traffic Monitoring

```yaml
actions:
  dsl_violations:
    enabled: true

    violation_templates:
      wrong_way:
        type: zone_sequence
        vehicle_types: [car, bus, truck, motorcycle]
        from_zones: "{from}"
        to_zone: "{to}"
        severity: high

    cameras:
      street_camera:
        violations:
          - name: wrong_way_northbound
            template: wrong_way
            params:
              from: [southbound_lane]
              to: northbound_lane

          - name: wrong_way_southbound
            template: wrong_way
            params:
              from: [northbound_lane]
              to: southbound_lane
```

### Industrial Safety

```yaml
actions:
  dsl_violations:
    enabled: true

    violation_templates:
      hazard_proximity:
        type: proximity
        first_object: "{hazard}"
        second_object: person
        within: 10
        severity: high

    cameras:
      factory_floor:
        violations:
          - name: person_near_machinery
            template: hazard_proximity
            params:
              hazard: industrial_robot

          - name: transformer_without_safety
            type: object_logic
            condition: "detected(transformer) AND NOT detected(fire_extinguisher)"
            severity: critical

          - name: green_hardhat_supervision
            type: object_logic
            condition: "detected(worker) AND NOT detected(green_hardhat)"
            severity: medium
            description: "Requires green hardhat supervisor present"
```

## Validation

The system validates rules at startup:

- **Zone names** checked against Frigate configuration
- **Object labels** verified against tracked objects
- **Condition syntax** parsed and validated
- **Template parameters** checked for completeness

**View validation results** in logs:
```bash
docker compose exec devcontainer tail -f /tmp/frigate_extras.log | grep -E "(Loaded|Validation|Error)"
```

## Monitoring

### View Violations

1. **Frigate UI**: http://localhost:5001/events
2. **Filter by sub-label**: violation_name
3. **Check severity**: Displayed in event details

### Logs

```bash
# Live violations
docker compose exec devcontainer tail -f /tmp/frigate_extras.log | grep "VIOLATION DETECTED"

# System stats
docker compose exec devcontainer tail -f /tmp/frigate_extras.log | grep "statistics"
```

### Event API

```bash
# Get recent violations
curl http://localhost:5001/api/events

# Filter by sub-label
curl http://localhost:5001/api/events | jq '.[] | select(.sub_label=="wrong_way_violation")'
```

## Troubleshooting

### No Violations Detected

1. **Check zone names**: Ensure zones match Frigate config exactly
2. **Verify object labels**: Check objects being tracked by Frigate
3. **Review condition syntax**: Look for validation errors in logs
4. **Test with simple rule**: Start with basic object_logic rule

### Duplicate Violations

- **Cooldown setting**: Increase cooldown duration
- **Object tracking**: Frigate may split single object into multiple IDs

### System Not Starting

1. **Check logs**: `docker compose logs devcontainer`
2. **Validate YAML**: Ensure proper YAML syntax
3. **Check Frigate API**: `curl http://localhost:5001/api/version`

## Advanced Topics

### Custom Rule Development

To add new rule types, extend the DSL engine:

1. Create new rule class in `frigate/extras/dsl/rule_types.py` or `temporal.py`
2. Add to factory in `rule_types.py` `create_rule()` function
3. Implement `evaluate()` and `get_violation_label()` methods

### State Management

The DSL uses `StateTracker` for temporal violations:
- Zone sequence tracking
- Condition duration monitoring
- Object proximity detection
- Automatic cleanup after 60 seconds

### Performance

- **Memory usage**: Automatic state cleanup prevents buildup
- **CPU usage**: Rules evaluated sequentially per event
- **Scalability**: Supports dozens of rules per camera

## Migration from Legacy Actions

### Old Wrong-Way Detection

```yaml
# OLD (wrong_way_detection action)
actions:
  wrong_way_detection:
    enabled: true
    cameras: [test]
    valid_zones: [zone01, zone02]
    violation_zone: wrongzone
    vehicle_types: [car, bus, truck, motorcycle]
```

### New DSL Equivalent

```yaml
# NEW (DSL system)
actions:
  dsl_violations:
    enabled: true

    violation_templates:
      wrong_way:
        type: zone_sequence
        vehicle_types: [car, bus, truck, motorcycle]
        from_zones: "{from}"
        to_zone: "{to}"
        duration: 30
        severity: high

    cameras:
      test:
        violations:
          - name: wrongway_detection
            template: wrong_way
            params:
              from: [zone01, zone02]
              to: wrongzone
```

## Best Practices

1. **Start Simple**: Begin with basic object_logic rules, add complexity gradually
2. **Use Templates**: Create reusable templates for common patterns
3. **Descriptive Names**: Use clear, descriptive violation names
4. **Test Incrementally**: Add one rule at a time, verify before adding more
5. **Monitor Logs**: Watch for validation errors and detection patterns
6. **Adjust Cooldowns**: Tune cooldown periods to reduce noise
7. **Document Rules**: Add descriptions to explain violation logic

## Support

- **Configuration**: [frigate/extras/config.yml](config.yml)
- **Documentation**: This file
- **Logs**: `/tmp/frigate_extras.log`
- **Frigate Docs**: https://docs.frigate.video/

---

**System Version**: DSL v1.0
**Frigate Version**: 0.17.0
**Last Updated**: 2025-11-14
