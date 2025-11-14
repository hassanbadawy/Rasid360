# DSL Violation Detection - Testing Guide

## Active Violations for Camera: test

### 1. Wrong-Way Detection ✅

**Violation Name**: `wrongway_zone01_zone02`

**Description**: Detects vehicles moving from zone01 or zone02 into wrongzone (wrong-way traffic)

**Configuration**:
```yaml
- name: wrongway_zone01_zone02
  type: zone_sequence
  description: "Vehicles moving from zone01/zone02 to wrongzone"
  vehicle_types: [car, bus, truck, motorcycle]
  from_zones: [zone01, zone02]
  to_zone: wrongzone
  duration: 30
  severity: high
  cooldown: 30
```

**How It Works**:
1. System tracks vehicles as they move through zones
2. Remembers which zones each vehicle has visited
3. When a vehicle enters `wrongzone`:
   - Checks if it previously came from `zone01` or `zone02`
   - If yes → **VIOLATION DETECTED**
   - Creates Frigate event with sub-label: `wrongway_zone01_zone02`
   - Event duration: 30 seconds
   - Retention: 30 days (alert level)
   - Red bounding box displayed in Frigate UI

**Expected Behavior**:
- ✅ Vehicle in zone01 → wrongzone = VIOLATION
- ✅ Vehicle in zone02 → wrongzone = VIOLATION
- ❌ Vehicle in wrongzone (never in zone01/zone02) = NO VIOLATION
- ❌ Vehicle in zone01 → zone02 = NO VIOLATION (valid movement)

---

### 2. Fall Down Detection ✅

**Violation Name**: `person_fall_down`

**Description**: Detects when a person falls down based on bounding box aspect ratio

**Configuration**:
```yaml
- name: person_fall_down
  type: fall_down
  description: "Person fall detected"
  object_type: person
  width_height_ratio: 1.2
  min_duration: 3
  duration: 30
  severity: critical
  cooldown: 15
```

**How It Works**:
1. System monitors all detected `person` objects
2. Calculates width/height ratio of bounding box:
   - **Standing person**: height > width (ratio < 1.0)
   - **Fallen person**: width > height (ratio > 1.0)
3. When ratio ≥ 1.2 **for 3 seconds**:
   - **VIOLATION DETECTED**
   - Creates Frigate event with sub-label: `person_fall_down`
   - Event duration: 30 seconds
   - Retention: 30 days (alert level)
   - Red bounding box displayed in Frigate UI

**Configurable Parameters**:
- `width_height_ratio`: Threshold for detection (default: 1.2)
  - Lower value = more sensitive (may trigger false positives)
  - Higher value = less sensitive (may miss some falls)
- `min_duration`: How long ratio must be sustained (default: 3 seconds)
  - Prevents false triggers from person bending/crouching briefly
  - Ensures person is actually lying down

**Expected Behavior**:
- ✅ Person standing (W:200, H:400, ratio=0.5) = NO VIOLATION
- ✅ Person crouching briefly (W:300, H:300, ratio=1.0) = NO VIOLATION (< 3 sec)
- ✅ Person lying down (W:400, H:200, ratio=2.0 for 3+ sec) = VIOLATION
- ✅ Person sitting (W:350, H:280, ratio=1.25 for 3+ sec) = VIOLATION

---

## Testing the System

### View Violations in Frigate UI

1. **Open Frigate UI**: http://localhost:5001/events
2. **Filter by sub-label**:
   - `wrongway_zone01_zone02` - Wrong-way violations
   - `person_fall_down` - Fall down violations
3. **Check event details**:
   - Red bounding box on violated object
   - Sub-label shows violation name
   - Timestamp and duration
   - Video clip with 30-day retention

### Monitor Live Violations

```bash
# Watch for violations in real-time
docker compose exec devcontainer tail -f /tmp/frigate_extras.log | grep "VIOLATION DETECTED"
```

**Example Output**:
```
2025-11-14 18:30:15 - RuleEvaluator - INFO - VIOLATION DETECTED: wrongway_zone01_zone02
2025-11-14 18:30:15 - DSLViolationDetector - INFO - Created violation event: evt_abc123
2025-11-14 18:32:48 - RuleEvaluator - INFO - VIOLATION DETECTED: person_fall_down
2025-11-14 18:32:48 - DSLViolationDetector - INFO - Created violation event: evt_def456
```

### Check System Status

```bash
# Verify DSL system is running
docker compose exec devcontainer pgrep -f "frigate.extras.main"

# Check loaded rules
docker compose exec devcontainer tail -50 /tmp/frigate_extras.log | grep -E "(Loaded|Initialized)"
```

**Expected Output**:
```
✓ Loaded 4 violation templates
✓ Loaded 2 rules for camera 'test'
✓ All violation rules validated successfully
✓ DSL Violation Detector initialized
```

---

## Adjusting Detection Parameters

### Fine-tune Fall Detection

Edit [frigate/extras/config.yml](config.yml):

```yaml
# More sensitive (detects earlier)
- name: person_fall_down
  type: fall_down
  object_type: person
  width_height_ratio: 1.0  # Lower threshold
  min_duration: 1          # Shorter duration

# Less sensitive (fewer false positives)
- name: person_fall_down
  type: fall_down
  object_type: person
  width_height_ratio: 1.5  # Higher threshold
  min_duration: 5          # Longer duration
```

### Add More Wrong-Way Rules

```yaml
# Monitor different zone combinations
- name: wrongway_zone02_only
  type: zone_sequence
  vehicle_types: [car, bus, truck, motorcycle]
  from_zones: [zone02]  # Only from zone02
  to_zone: wrongzone
  duration: 30
  severity: high
```

### Restart After Config Changes

```bash
# Restart DSL system
docker compose exec devcontainer pkill -f "frigate.extras.main"
docker compose exec -d devcontainer bash -c "cd /workspace/frigate && python3 -m frigate.extras.main > /tmp/frigate_extras.log 2>&1"

# Wait 3 seconds, then check logs
sleep 3
docker compose exec devcontainer tail -30 /tmp/frigate_extras.log
```

---

## API Access

### Get All Violations

```bash
# Get all events
curl http://localhost:5001/api/events

# Get only violation events (with sub_label)
curl http://localhost:5001/api/events | jq '.[] | select(.sub_label != null)'

# Get specific violation type
curl http://localhost:5001/api/events | jq '.[] | select(.sub_label=="wrongway_zone01_zone02")'
curl http://localhost:5001/api/events | jq '.[] | select(.sub_label=="person_fall_down")'
```

---

## Troubleshooting

### No Violations Detected

1. **Check zones are defined** in Frigate config:
   ```bash
   # Zones should exist: zone01, zone02, wrongzone
   grep -A 5 "zones:" data/frigate-config/config.yml
   ```

2. **Verify objects are tracked**:
   ```bash
   # Should track: person, car, bus, truck, motorcycle
   grep -A 5 "objects:" data/frigate-config/config.yml
   ```

3. **Check MQTT events**:
   ```bash
   # Monitor raw MQTT events
   docker compose exec devcontainer tail -f /tmp/frigate_extras.log | grep "Processing event"
   ```

### False Positives (Too Many Violations)

1. **Increase cooldown period**:
   ```yaml
   cooldown: 60  # Wait 60 seconds before re-alerting same object
   ```

2. **Adjust thresholds**:
   - Fall detection: Increase `width_height_ratio` or `min_duration`
   - Wrong-way: Add more specific zone sequences

### System Not Starting

```bash
# Check for errors
docker compose exec devcontainer tail -100 /tmp/frigate_extras.log | grep ERROR

# Validate config syntax
docker compose exec devcontainer python3 -c "
from frigate.extras.utils.config_loader import ConfigLoader
config = ConfigLoader().load_config()
print('Config loaded successfully')
"
```

---

## Summary

✅ **Wrong-way detection**: Zone sequence tracking for traffic violations
✅ **Fall detection**: Aspect ratio analysis for person safety
✅ **Configurable**: Adjust thresholds without code changes
✅ **Real-time**: MQTT-based immediate detection
✅ **Integrated**: Native Frigate events with bounding boxes
✅ **Retained**: 30-day storage for violation footage

Both use cases are **active and ready for testing**!
