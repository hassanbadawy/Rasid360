# Quick Start Guide - Wrong-Way Vehicle Detection

Get up and running with wrong-way vehicle detection in 5 minutes.

## Prerequisites

✅ Frigate NVR running with MQTT enabled
✅ Python 3.8+ installed
✅ Zones configured in Frigate (zone01, zone02, wrongzone)

## Step 1: Install Dependencies

```bash
cd /Users/hassanbadawy/Documents/CODE/Rasid360
pip3 install -r frigate/extras/requirements.txt
```

Expected output:
```
Successfully installed paho-mqtt-1.6.1 PyYAML-6.0 requests-2.28.0
```

## Step 2: Verify Configuration

The system is pre-configured for your setup:

**Zones in Frigate** (`data/frigate-config/config.yml`):
- ✓ zone01 - Valid zone (fixed from zon02)
- ✓ zone02 - Valid zone
- ✓ wrongzone - Violation zone

**Action Configuration** (`frigate/extras/config.yml`):
```yaml
wrong_way_detection:
  enabled: true
  cameras: [test]
  valid_zones: [zone01, zone02]
  violation_zone: wrongzone
  vehicle_types: [car, bus, truck, motorcycle]
```

## Step 3: Test System

Run the test script to verify everything is working:

```bash
python3 frigate/extras/test_system.py
```

Expected output:
```
============================================================
Testing Configuration
============================================================
✓ Configuration loaded successfully
✓ MQTT Host: mqtt
✓ MQTT Port: 1883
✓ Frigate API: http://localhost:5000/api
✓ Enabled Actions: ['wrong_way_detection']

============================================================
Testing Frigate API Connection
============================================================
✓ Frigate API is accessible at http://localhost:5000/api
✓ Successfully retrieved system stats
✓ Cameras found: ['test']

============================================================
Testing MQTT Connection
============================================================
✓ Connected to MQTT broker at mqtt:1883
✓ MQTT connection is stable

============================================================
Testing Zone Configuration
============================================================
✓ Valid zones: ['zone01', 'zone02']
✓ Violation zone: wrongzone
✓ Zone configuration looks good

============================================================
Test Summary
============================================================
✓ PASS: Configuration
✓ PASS: Frigate API
✓ PASS: MQTT Broker
✓ PASS: Zone Config

============================================================
✓ All tests passed! System is ready to run.

Start the event dispatcher with:
  python3 -m frigate.extras.main
```

### If Tests Fail

**Cannot connect to Frigate API:**
```bash
# Check if Frigate is running
docker ps | grep frigate

# Check Frigate logs
docker logs frigate

# Test API directly
curl http://localhost:5000/api/version
```

**Cannot connect to MQTT:**
```bash
# Check if MQTT broker is running
docker ps | grep mqtt

# Start MQTT if needed
docker compose up -d mqtt
```

## Step 4: Start Event Dispatcher

```bash
python3 -m frigate.extras.main
```

Expected output:
```
============================================================
Frigate Extras - Custom Event Detection System
============================================================
2025-01-13 10:30:00 - ConfigLoader - INFO - Loaded configuration from /path/to/config.yml
2025-01-13 10:30:00 - EventDispatcher - INFO - Loading action handlers...
2025-01-13 10:30:00 - WrongWayDetection - INFO - Initialized: valid_zones=['zone01', 'zone02'], violation_zone=wrongzone, vehicle_types=['car', 'bus', 'truck', 'motorcycle']
2025-01-13 10:30:00 - EventDispatcher - INFO - ✓ Loaded action: wrong_way_detection
2025-01-13 10:30:00 - EventDispatcher - INFO - Loaded 1 action handler(s)
2025-01-13 10:30:00 - EventDispatcher - INFO - Starting Event Dispatcher
2025-01-13 10:30:00 - EventDispatcher - INFO - Active actions: ['WrongWayDetection']
2025-01-13 10:30:00 - MQTTClient - INFO - Connecting to MQTT broker at mqtt:1883
2025-01-13 10:30:00 - MQTTClient - INFO - Connected to MQTT broker successfully
2025-01-13 10:30:00 - MQTTClient - INFO - Subscribed to frigate/events topic
2025-01-13 10:30:00 - EventDispatcher - INFO - Event dispatcher is running. Press Ctrl+C to stop.
```

The system is now monitoring Frigate events!

## Step 5: Test Wrong-Way Detection

The system will automatically detect violations when a vehicle:
1. Enters zone01 or zone02
2. Then enters wrongzone

### Watch for Violations

When a violation is detected, you'll see:

```
2025-01-13 10:35:45 - WrongWayDetection - WARNING - 🚨 WRONG-WAY VIOLATION DETECTED!
   Vehicle ID: 1705148145.123456-abc
   Type: car
   Camera: test
   Path: zone01 → wrongzone
   Valid zones: zone01, zone02
   Violation zone: wrongzone

2025-01-13 10:35:45 - WrongWayDetection - INFO - Created violation event: 1705148145.789012-xyz
```

### View in Frigate UI

1. Open Frigate UI: http://localhost:5000
2. Go to **Events** page
3. Filter by camera: **test**
4. Look for events with sub-label: **wrong_way_violation**
5. Click to view 30-second recording clip

## Step 6: View Logs

Logs are written to `/tmp/frigate_extras.log`:

```bash
# View all logs
tail -f /tmp/frigate_extras.log

# View only violations
tail -f /tmp/frigate_extras.log | grep "VIOLATION"

# View only created events
tail -f /tmp/frigate_extras.log | grep "Created event"
```

## Running in Production

### Option 1: Background Process

```bash
# Start in background
nohup python3 -m frigate.extras.main > /tmp/frigate_extras_console.log 2>&1 &

# Check if running
ps aux | grep "frigate.extras.main"

# Stop
pkill -f "frigate.extras.main"
```

### Option 2: Systemd Service (Recommended)

Create `/etc/systemd/system/frigate-extras.service`:

```ini
[Unit]
Description=Frigate Extras Event Detection
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=hassanbadawy
WorkingDirectory=/Users/hassanbadawy/Documents/CODE/Rasid360
ExecStart=/usr/bin/python3 -m frigate.extras.main
Restart=always
RestartSec=10
StandardOutput=append:/tmp/frigate_extras.log
StandardError=append:/tmp/frigate_extras.log

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable frigate-extras
sudo systemctl start frigate-extras
sudo systemctl status frigate-extras
```

View logs:
```bash
sudo journalctl -u frigate-extras -f
```

### Option 3: Docker Service

Add to `docker-compose.yml`:

```yaml
services:
  frigate-extras:
    image: python:3.11-slim
    container_name: frigate-extras
    restart: unless-stopped
    working_dir: /app
    command: python3 -m frigate.extras.main
    volumes:
      - ./frigate:/app/frigate:ro
      - ./frigate/extras/config.yml:/app/frigate/extras/config.yml:ro
    depends_on:
      - frigate
      - mqtt
    networks:
      - default
    environment:
      - PYTHONUNBUFFERED=1
```

Start:
```bash
docker compose up -d frigate-extras
docker logs -f frigate-extras
```

## Troubleshooting

### No violations detected

Check:
1. Zone names match exactly: `zone01`, `zone02`, `wrongzone`
2. Vehicles are entering zones in correct order
3. Camera name is `test`
4. View Frigate debug stream to see zones: http://localhost:5000/api/test?zones=1

### Duplicate violations

The system has a 30-second cooldown per vehicle to prevent spam. This is normal behavior.

### High memory usage

Adjust cleanup timeout in `config.yml`:

```yaml
wrong_way_detection:
  cleanup_timeout: 30  # Reduce from 60 to clean up faster
```

### Cannot see events in Frigate UI

1. Check Frigate API is accessible: http://localhost:5000/api/events
2. Verify events are being created: `tail -f /tmp/frigate_extras.log | grep "Created event"`
3. Check Frigate logs: `docker logs frigate`

## Next Steps

✅ System is running and detecting violations!

**Customize:**
- Add more cameras to monitor
- Adjust cleanup timeout
- Modify vehicle types tracked
- Create additional actions (fall detection, loitering, etc.)

**Monitor:**
- Set up notifications (email, SMS, push)
- Create dashboards with event data
- Export violation statistics

**Scale:**
- Add more zones for complex road networks
- Implement different violation types
- Create custom actions for other scenarios

See [README.md](README.md) for full documentation.

---

**Need Help?**
- Check logs: `/tmp/frigate_extras.log`
- Run tests: `python3 frigate/extras/test_system.py`
- Review configuration: `cat frigate/extras/config.yml`
