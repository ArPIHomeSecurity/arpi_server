# Zigbee Implementation Plan

Implement each step for the real Sonoff MG21 adapter and the simulator together. The simulator should use the same registration, sensor, adapter, and handler contracts; only the device transport and mutable state source should differ.

1. **Configure the coordinator**
   - Add the `zigbee` option (`enabled`, serial port, adapter name, and permit-join settings).
   - Add MG21 startup/shutdown and a simulator adapter with the same lifecycle.
   - Verify both adapters can start, stop, and report connection errors without affecting V2/V3.

2. **Register a Zigbee device**
   - Add the `zigbee_device` model and migration, keyed by IEEE address.
   - Implement device registration and discovery of endpoints/capabilities.
   - Let the simulator call the same registration service/API; store only live simulated state in `simulator_zigbee.json`.

3. **Create logical sensors**
   - Extend `sensor` with nullable Zigbee device, endpoint, and capability fields while preserving wired `channel` behavior.
   - Create one logical sensor per configured capability, with its existing area, zone, type, enabled, and alert settings.
   - Verify wired and Zigbee sensors can coexist.

4. **Expose management and simulator controls**
   - Add API/UI flows to configure the coordinator, register devices, and create or edit Zigbee sensors.
   - Add simulator controls for capability values, availability, battery, signal quality, and device registration through the same contracts.

5. **Define lifecycle and recovery**
   - Handle pairing, reconnects, rediscovery, unknown devices or capabilities, and clean shutdown.
   - Define adapter error reporting and stale-value behavior without creating false alarms.

6. **Add normalized adapter readings**
   - Define the shared reading contract: sensor identity, value, timestamp, availability, battery, and signal quality.
   - Implement the MG21 event cache and the simulator state-backed cache with identical lookup and normalization rules.
   - Verify value changes, availability, stale values, and `last_seen` behave identically.
