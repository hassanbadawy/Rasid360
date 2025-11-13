#!/usr/bin/env python3
"""
Test script for Frigate Extras system
Verifies connectivity and configuration
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from frigate.extras.config import ConfigLoader
from frigate.extras.utils.mqtt_client import MQTTClient
from frigate.extras.utils.frigate_api import FrigateAPI


def test_config():
    """Test configuration loading"""
    print("=" * 60)
    print("Testing Configuration")
    print("=" * 60)

    config_path = os.path.join(os.path.dirname(__file__), "config.yml")

    try:
        config = ConfigLoader(config_path)
        print("✓ Configuration loaded successfully")

        # Test MQTT config
        mqtt_config = config.get_mqtt_config()
        print(f"✓ MQTT Host: {mqtt_config.get('host')}")
        print(f"✓ MQTT Port: {mqtt_config.get('port')}")

        # Test Frigate config
        frigate_config = config.get_frigate_config()
        print(f"✓ Frigate API: {frigate_config.get('api_url')}")

        # Test actions
        enabled_actions = config.get_all_enabled_actions()
        print(f"✓ Enabled Actions: {list(enabled_actions.keys())}")

        return True

    except Exception as e:
        print(f"✗ Configuration error: {e}")
        return False


def test_frigate_api():
    """Test Frigate API connectivity"""
    print("\n" + "=" * 60)
    print("Testing Frigate API Connection")
    print("=" * 60)

    config_path = os.path.join(os.path.dirname(__file__), "config.yml")
    config = ConfigLoader(config_path)
    frigate_config = config.get_frigate_config()
    api_url = frigate_config.get("api_url", "http://localhost:5000/api")

    api = FrigateAPI(api_url)

    # Health check
    if api.health_check():
        print(f"✓ Frigate API is accessible at {api_url}")

        # Get stats
        stats = api.get_stats()
        if stats:
            print(f"✓ Successfully retrieved system stats")
            cameras = stats.get("cameras", {})
            print(f"✓ Cameras found: {list(cameras.keys())}")
        else:
            print("⚠ Could not retrieve stats")

        return True
    else:
        print(f"✗ Cannot connect to Frigate API at {api_url}")
        print("  Make sure Frigate is running")
        return False


def test_mqtt():
    """Test MQTT broker connectivity"""
    print("\n" + "=" * 60)
    print("Testing MQTT Connection")
    print("=" * 60)

    config_path = os.path.join(os.path.dirname(__file__), "config.yml")
    config = ConfigLoader(config_path)
    mqtt_config = config.get_mqtt_config()

    host = mqtt_config.get("host", "localhost")
    port = mqtt_config.get("port", 1883)

    mqtt_client = MQTTClient(
        host=host,
        port=port,
        client_id="frigate_extras_test"
    )

    if mqtt_client.connect():
        print(f"✓ Connected to MQTT broker at {host}:{port}")

        # Start async loop to process connection callback
        mqtt_client.start_async()
        
        # Wait a moment for connection and callback processing
        import time
        time.sleep(3)

        if mqtt_client.is_connected():
            print("✓ MQTT connection is stable")
            mqtt_client.stop_async()
            mqtt_client.disconnect()
            return True
        else:
            print("⚠ MQTT connection unstable")
            mqtt_client.stop_async()
            mqtt_client.disconnect()
            return False
    else:
        print(f"✗ Cannot connect to MQTT broker at {host}:{port}")
        print("  Make sure MQTT broker (mosquitto) is running")
        return False


def test_zones():
    """Test zone configuration"""
    print("\n" + "=" * 60)
    print("Testing Zone Configuration")
    print("=" * 60)

    config_path = os.path.join(os.path.dirname(__file__), "config.yml")
    config = ConfigLoader(config_path)

    wrong_way_config = config.get_action_config("wrong_way_detection")

    if not wrong_way_config:
        print("✗ Wrong-way detection not configured")
        return False

    valid_zones = wrong_way_config.get("valid_zones", [])
    violation_zone = wrong_way_config.get("violation_zone", "")

    print(f"✓ Valid zones: {valid_zones}")
    print(f"✓ Violation zone: {violation_zone}")

    if not valid_zones or not violation_zone:
        print("⚠ Warning: Zones not properly configured")
        return False

    print("✓ Zone configuration looks good")
    return True


def main():
    """Run all tests"""
    print("\nFrigate Extras System Test\n")

    results = []

    results.append(("Configuration", test_config()))
    results.append(("Frigate API", test_frigate_api()))
    results.append(("MQTT Broker", test_mqtt()))
    results.append(("Zone Config", test_zones()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)

    if all_passed:
        print("✓ All tests passed! System is ready to run.")
        print("\nStart the event dispatcher with:")
        print("  python3 -m frigate.extras.main")
    else:
        print("✗ Some tests failed. Please fix issues before running.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
