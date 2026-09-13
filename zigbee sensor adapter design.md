# Sensor Adapter Source Design

## Goal

Support both existing wired sensor boards and a Sonoff MG21 Zigbee dongle in the same monitor process.

- V2: GPIO digital inputs
- V3: MCP3008 ADC inputs over SPI
- Zigbee: event-driven device updates exposed as latest cached values

Existing V2/V3 adapters remain unchanged.

## Current Implementation

- [sensor_base.py](src/monitor/adapters/sensor_base.py) defines the legacy channel interface.
- [sensor.py](src/monitor/adapters/sensor.py) selects V2 or V3 using `BOARD_VERSION`.
- [sensor_v2.py](src/monitor/adapters/sensor_v2.py) reads GPIO inputs.
- [sensor_v3.py](src/monitor/adapters/sensor_v3.py) reads MCP3008 channels.
- [handler.py](src/monitor/sensor/handler.py) loads sensors, polls values, and applies alert logic.

## Proposed Design

`SensorHandler` owns multiple sensor adapters. The existing adapter is selected by board version; Zigbee is selected independently by configuration.

```mermaid
classDiagram
    class SensorHandler {
        -adapters
        +initialize()
        +load_sensors()
        +scan_sensors()
        +handle_alerts()
        +close()
    }

    class SensorAdapter {
        <<interface>>
        +get_values()
        +close()
    }

    class LegacySensorAdapter {
        +get_value(channel)
        +get_values()
        +channel_count
        +calibrate()
    }

    class SensorAdapterV2
    class SensorAdapterV3

    class ZigbeeAdapter {
        +start()
        +get_values()
        +close()
    }

    SensorHandler o-- SensorAdapter
    SensorAdapter <|.. LegacySensorAdapter
    LegacySensorAdapter <|.. SensorAdapterV2
    LegacySensorAdapter <|.. SensorAdapterV3
    SensorAdapter <|.. ZigbeeAdapter
```

## Runtime Flow

```mermaid
flowchart LR
    V2V3[Legacy V2/V3 adapter] -->|poll| Handler[SensorHandler]
    Zigbee[Zigbee adapter] -->|device events| Cache[Thread-safe latest-value cache]
    Cache -->|poll latest values| Handler
    Handler --> State[Sensor state]
    State --> Alerts[Existing alert and notification flow]
```

The Zigbee adapter receives device events internally, updates a thread-safe cache, and returns the latest normalized readings when `SensorHandler` polls it. A reading should include:

```python
SensorReading(
    sensor_id=123,
    value=True,
    timestamp=...,
    available=True,
    battery_level=87,
)
```

## Handler Rules

- Poll all configured adapters at the existing monitor rate, approximately 20 Hz.
- Apply the same state, sensitivity, arm/zone, and alert logic to every reading.
- Use `channel` only for V2/V3 sensors.
- Identify Zigbee readings by configured device identity, endpoint, and capability.
- Keep Zigbee `available` and `last_seen` separate from the alarm value.
- Keep ADC calibration and legacy channel validation only on the V2/V3 adapter.

## Adapter Selection

```text
get_sensor_adapter() -> V2 or V3 legacy adapter
get_zigbee_adapter() -> Zigbee adapter when enabled
SensorHandler.adapters = [legacy_adapter, zigbee_adapter]
```

The Zigbee adapter must not replace the current factory.
Zigbee adapter can operate simultaneously with legacy adapters on a V2 or V3 installation.

## Simulator Integration

Simulator mode keeps the existing wired channel protocol and adds a separate
Zigbee protocol. The Textual simulator continues to write wired values to
`simulator_input.json`; simulated Zigbee device state is written to
`simulator_zigbee.json`. Namespacing Zigbee state separately prevents device
identity and capability data from being confused with legacy `CH01`-style input.

The simulator must use the normal device-registration service or API contract when
creating a simulated device. The resulting device and logical sensor records are
real database records, so registration, sensor configuration, and monitor lookup
are exercised exactly as they are for a physical device. The simulator JSON file
contains only mutable runtime state such as capability values, availability,
battery level, signal quality, and last-seen timestamps.

The mock adapter reads `simulator_zigbee.json`, resolves entries by IEEE address,
endpoint, and capability, and exposes normalized readings through the same
adapter boundary as the hardware Zigbee adapter. The mock must not bypass
`SensorHandler` or write `Sensor.alert` directly.

Both mock adapters run together when `USE_SIMULATOR` is enabled:

```text
get_sensor_adapter()       -> mock legacy V2/V3 channel adapter
get_zigbee_adapter()       -> mock Zigbee adapter when Zigbee is enabled
SensorHandler.adapters     -> [legacy_adapter, zigbee_adapter]
```

The simulator UI should expose these Zigbee controls:

- create/register a simulated device;
- set boolean or numeric capability values;
- toggle availability;
- set battery level and signal quality; and
- display the device's last-seen timestamp.

Changing a capability value updates `last_seen`. Availability changes do not
change the alarm value. If a device is unavailable, the adapter returns the
unavailable status and the last cached value; the handler reports sensor error
state and does not create a new alarm from stale data.

Simulator-specific automated tests are intentionally out of scope for the first
implementation. The adapter and handler contracts should remain testable without
the Textual UI, so coverage can be added later without changing the simulator
state format.
