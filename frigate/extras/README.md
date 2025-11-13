# Frigate Extras - Custom Event Detection System

A modular, plugin-based system for implementing custom event detection logic on top of Frigate NVR.

## Overview

Frigate Extras extends Frigate's native object detection with custom business logic for complex scenarios that aren't natively supported, such as:

- **Wrong-way vehicle detection** - Detect vehicles traveling in prohibited directions
- **Fall detection** - Identify when a person has fallen
- **Loitering detection** - Alert when people remain in an area too long
- **Object co-presence** - Detect missing safety equipment or required objects
- **Custom zone sequencing** - Track complex movement patterns

## Architecture

```
frigate/extras/
├── main.py                    # Event dispatcher (entry point)
├── config.yml                 # Action configuration
├── config.py                  # Configuration loader
├── actions/                   # Pluggable action handlers
│   ├── base_action.py        # Abstract base class
│   ├── wrong_way_detection.py
│   └── [your_custom_action.py]
└── utils/
    ├── mqtt_client.py        # MQTT connection handler
    └── frigate_api.py        # Frigate API wrapper
```

### How It Works

1. **MQTT Listener**: Connects to Frigate's MQTT broker and subscribes to `frigate/events`
2. **Event Dispatcher**: Receives real-time object detection events from Frigate
3. **Action Handlers**: Each enabled action processes events independently
4. **Manual Events**: Actions can create custom events via Frigate API when conditions are met

## Installation

### Prerequisites

- Frigate NVR running with MQTT enabled
- Python 3.8+
- Access to Frigate's MQTT broker and API

### Install Dependencies

```bash
pip install paho-mqtt pyyaml requests
```

### Configuration

Edit `frigate/extras/config.yml`:

```yaml
mqtt:
  host: mqtt              # MQTT broker hostname
  port: 1883
  client_id: frigate_extras

frigate:
  api_url: http://localhost:5000/api

actions:
  wrong_way_detection:
    enabled: true
    cameras:
      - front_camera
    valid_zones:
      - zone01
      - zone02
    violation_zone: wrongzone
    vehicle_types:
      - car
      - bus
      - truck
      - motorcycle
```

## Usage

### Running the Event Dispatcher

#### Option 1: Direct Execution

```bash
cd /path/to/Rasid360
python3 -m frigate.extras.main
```

#### Option 2: Docker (Recommended)

Add to `docker-compose.yml`:

```yaml
services:
  frigate-extras:
    build:
      context: .
      dockerfile: Dockerfile.extras
    container_name: frigate-extras
    restart: unless-stopped
    environment:
      - FRIGATE_EXTRAS_CONFIG=/config/config.yml
    volumes:
      - ./frigate/extras/config.yml:/config/config.yml:ro
    depends_on:
      - frigate
      - mqtt
    networks:
      - frigate
```

#### Option 3: Systemd Service

Create `/etc/systemd/system/frigate-extras.service`:

```ini
[Unit]
Description=Frigate Extras Event Detection
After=network.target frigate.service

[Service]
Type=simple
User=frigate
WorkingDirectory=/opt/frigate
ExecStart=/usr/bin/python3 -m frigate.extras.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable frigate-extras
sudo systemctl start frigate-extras
sudo systemctl status frigate-extras
```

## Built-in Actions

### Wrong-Way Vehicle Detection

Detects vehicles moving from valid zones into prohibited zones.

**Configuration:**

```yaml
actions:
  wrong_way_detection:
    enabled: true
    cameras:
      - street_camera
    valid_zones:
      - zone01      # Allowed zones
      - zone02
    violation_zone: wrongzone  # Prohibited zone
    vehicle_types:
      - car
      - bus
      - truck
      - motorcycle
    cleanup_timeout: 60  # seconds
```

**How it works:**

1. Tracks each vehicle's zone sequence
2. Detects pattern: `zone01/zone02 → wrongzone`
3. Creates Frigate event with `sub_label: wrong_way_violation`
4. Includes 30-second recording clip
5. Prevents duplicate alerts (30s cooldown)

**Viewing Violations:**

- Frigate UI → Events → Filter by camera
- Look for events with sub-label "wrong_way_violation"
- Review recording clip

## Creating Custom Actions

### Step 1: Create Action Class

Create `frigate/extras/actions/your_action.py`:

```python
from typing import Dict, Any
from .base_action import BaseAction

class YourCustomAction(BaseAction):
    """Your custom action description"""

    def __init__(self, config: Dict[str, Any], frigate_api: Any):
        super().__init__(config, frigate_api)

        # Load your custom config
        self.min_duration = config.get("min_duration", 10)

        # Initialize state
        self.tracked_objects = {}

    def process_event(self, event_data: Dict[str, Any]) -> None:
        """Process event from Frigate"""

        if not self.should_process_event(event_data):
            return

        after = event_data.get("after", {})

        # Your custom logic here
        object_id = after.get("id")
        label = after.get("label")
        camera = after.get("camera")

        # Example: Detect something
        if self._detect_condition(after):
            self.create_event(
                camera=camera,
                label=label,
                sub_label="custom_detection",
                duration=30,
                score=0.9,
                source_type="your_action"
            )

    def _detect_condition(self, data: Dict[str, Any]) -> bool:
        """Your detection logic"""
        # Implement your condition
        return True
```

### Step 2: Register Action

Edit `frigate/extras/main.py`:

```python
from frigate.extras.actions.your_action import YourCustomAction

# In _load_actions method, add to action_registry:
action_registry = {
    "wrong_way_detection": WrongWayDetection,
    "your_custom_action": YourCustomAction,  # Add your action
}
```

### Step 3: Configure Action

Edit `frigate/extras/config.yml`:

```yaml
actions:
  your_custom_action:
    enabled: true
    cameras:
      - camera1
    min_duration: 10
    # Your custom parameters
```

### Step 4: Test

```bash
python3 -m frigate.extras.main
```

## API Reference

### BaseAction Class

All actions inherit from `BaseAction`:

```python
class YourAction(BaseAction):
    def process_event(self, event_data: Dict[str, Any]) -> None:
        """Required: Process Frigate event"""
        pass
```

**Available Methods:**

| Method | Description |
|--------|-------------|
| `should_process_event(event_data)` | Check if event matches camera filter |
| `create_event(camera, label, sub_label, ...)` | Create manual Frigate event |
| `log_info(message)` | Log info message |
| `log_warning(message)` | Log warning message |
| `log_error(message)` | Log error message |
| `log_debug(message)` | Log debug message |

### Event Data Structure

Events from MQTT have this structure:

```python
{
    "before": { ... },  # Previous state
    "after": {
        "id": "1234567890.123456-abc",
        "camera": "front_door",
        "label": "car",
        "sub_label": None,
        "start_time": 1234567890.123,
        "end_time": None,
        "top_score": 0.92,
        "current_zones": ["zone01", "zone02"],
        "entered_zones": ["zone01"],
        "stationary": False,
        "box": [100, 200, 300, 400],
        "area": 20000,
        ...
    },
    "type": "new" | "update" | "end"
}
```

### FrigateAPI Methods

```python
# Create event
event_id = self.frigate_api.create_event(
    camera="front_door",
    label="car",
    sub_label="violation",
    duration=30,  # seconds (None for manual end)
    score=1.0,
    source_type="my_detector",
    include_recording=True
)

# End event
self.frigate_api.end_event(event_id)

# Get event details
event = self.frigate_api.get_event(event_id)

# Health check
is_alive = self.frigate_api.health_check()
```

## Troubleshooting

### Check if running

```bash
# If using systemd
sudo systemctl status frigate-extras

# Check logs
tail -f /tmp/frigate_extras.log
```

### Common Issues

**Cannot connect to MQTT**

- Check MQTT broker is running: `docker ps | grep mqtt`
- Verify MQTT host in config matches broker hostname
- Check MQTT authentication if enabled

**Cannot connect to Frigate API**

- Verify Frigate is running: `curl http://localhost:5000/api/version`
- Check API URL in config
- Ensure network connectivity between containers

**Events not triggering**

- Check action is enabled in config
- Verify camera name matches Frigate config
- Check zone names are correct
- Review logs for errors: `tail -f /tmp/frigate_extras.log`
- Enable debug logging: Set `logging.level: DEBUG` in config

**Duplicate events**

- Wrong-way detection has 30s cooldown per vehicle
- Check `cleanup_timeout` in config
- Adjust cooldown in action code if needed

### Debug Mode

Enable debug logging in `config.yml`:

```yaml
logging:
  level: DEBUG
```

View detailed event processing:

```bash
tail -f /tmp/frigate_extras.log | grep "Vehicle"
```

## Examples

### Example 1: Fall Detection

```python
# frigate/extras/actions/fall_detection.py
class FallDetection(BaseAction):
    def process_event(self, event_data: Dict[str, Any]) -> None:
        after = event_data.get("after", {})

        if after.get("label") != "person":
            return

        # Check if person is stationary in floor zone
        is_stationary = after.get("stationary", False)
        zones = after.get("current_zones", [])

        if is_stationary and "floor_area" in zones:
            # Check aspect ratio (fallen person = wide box)
            box = after.get("box", [])
            if len(box) == 4:
                width = box[2] - box[0]
                height = box[3] - box[1]
                ratio = width / height if height > 0 else 0

                if ratio > 1.5:  # Wider than tall
                    self.create_event(
                        camera=after["camera"],
                        label="person",
                        sub_label="possible_fall",
                        duration=60,
                        score=0.8
                    )
```

### Example 2: Loitering Detection

```python
# frigate/extras/actions/loitering_detection.py
class LoiteringDetection(BaseAction):
    def __init__(self, config, frigate_api):
        super().__init__(config, frigate_api)
        self.min_time = config.get("min_loitering_time", 30)
        self.entry_times = {}

    def process_event(self, event_data):
        after = event_data.get("after", {})

        if after.get("label") != "person":
            return

        person_id = after.get("id")
        zones = after.get("current_zones", [])
        start_time = after.get("start_time")

        if "entrance" in zones:
            if person_id not in self.entry_times:
                self.entry_times[person_id] = start_time
            else:
                duration = time.time() - self.entry_times[person_id]
                if duration > self.min_time:
                    self.create_event(
                        camera=after["camera"],
                        label="person",
                        sub_label="loitering",
                        duration=30
                    )
```

## Performance

- **Memory**: ~20-50MB depending on active vehicles
- **CPU**: <1% on modern hardware
- **Network**: Minimal (MQTT + occasional API calls)

### Optimization Tips

1. **Limit cameras**: Only enable actions on specific cameras
2. **Cleanup timeout**: Lower timeout for high-traffic areas
3. **Filter objects**: Only track relevant object types
4. **Action-specific**: Use `should_process_event()` to filter early

## Contributing

To add new actions:

1. Create action class in `actions/`
2. Inherit from `BaseAction`
3. Implement `process_event()` method
4. Register in `main.py`
5. Document in this README
6. Submit pull request

## License

Same as Frigate NVR parent project.

## Support

- **Issues**: Open GitHub issue
- **Discussions**: Frigate Discussions
- **Documentation**: See `/debug/docs/` for full Frigate guides

---

**Version**: 1.0.0
**Last Updated**: 2025-01-13
