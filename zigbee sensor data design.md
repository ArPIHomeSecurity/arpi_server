# Sensor Data Design

## Goal

Store existing wired sensors and Zigbee sensors in the same alarm system without changing the meaning of the existing wired `channel` field.

## Coordinator Configuration

There is one Zigbee coordinator, so store its configuration in the existing `option` table using a dedicated option such as `zigbee`.

```json
{
  "enabled": true,
  "serial_port": "/dev/serial/by-id/sonoff-dongle",
  "adapter": "sonoff_mg21",
  "permit_join": false
}
```

This follows the current `Option` and `BaseConfig` configuration pattern. Paired device data does not belong in options.

## Database Tables

```mermaid
erDiagram
    ZIGBEE_DEVICE ||--o{ SENSOR : provides
    AREA ||--o{ SENSOR : contains
    ZONE ||--o{ SENSOR : assigns
    SENSOR_TYPE ||--o{ SENSOR : classifies
    SENSOR ||--o{ ALERT_SENSOR : triggers
    ALERT ||--o{ ALERT_SENSOR : contains

    ZIGBEE_DEVICE {
        int id PK
        string ieee_address UK
        int network_address
        string manufacturer
        string model
        string name
        string availability
        datetime last_seen
        int battery_level
        int signal_quality
        json metadata
    }

    SENSOR {
        int id PK
        int zigbee_device_id FK "nullable"
        int channel "nullable, existing wired field"
        string endpoint "nullable"
        string capability "nullable"
        string name
        boolean enabled
        boolean alert
        boolean error
        int area_id FK
        int zone_id FK
        int type_id FK
    }

    SENSOR_TYPE {
        int id PK
        string name
        string description
    }

    AREA {
        int id PK
        string name
        string arm_state
    }

    ZONE {
        int id PK
        string name
    }

    ALERT {
        int id PK
        datetime start_time
        datetime end_time
        boolean silent
    }

    ALERT_SENSOR {
        int alert_id FK
        int sensor_id FK
        datetime start_time
        datetime end_time
    }
```

## Sensor Mapping

`SENSOR` is the logical sensor used by the monitor and alert system.

| Source | `channel` | `zigbee_device_id` | `endpoint` / `capability` |
|---|---:|---:|---|
| Wired V2/V3 | required | null | null |
| Zigbee | null | required | required |

Examples:

```text
Wired sensor:
  channel = 3
  zigbee_device_id = NULL

Zigbee contact sensor:
  channel = NULL
  zigbee_device_id = 12
  endpoint = "1"
  capability = "contact"
```

A single Zigbee device may provide multiple logical sensors, for example `contact`, `tamper`, and `temperature`. Each capability gets its own `SENSOR` row and can have its own name, zone, area, and alert settings.

## Runtime Mapping

```mermaid
sequenceDiagram
    participant Z as ZigbeeAdapter
    participant D as zigbee_device
    participant S as sensor
    participant H as SensorHandler
    participant A as Alert logic

    Z->>D: identify by IEEE address
    Z->>S: resolve device + endpoint + capability
    Z->>S: update latest state and availability
    H->>S: poll latest normalized values
    H->>A: apply existing arm, zone, delay, and alert rules
```

The Zigbee adapter owns device identity and latest-value updates. `SensorHandler` consumes normalized sensor values just like wired readings. Existing `channel` validation and ADC calibration apply only to wired sensors.

## Recommended Constraints

- `zigbee_device.ieee_address` is unique.
- A Zigbee sensor requires `zigbee_device_id`, `endpoint`, and `capability`.
- A wired sensor requires `channel` and has no Zigbee device link.
- `channel` remains nullable because Zigbee sensors do not use hardware channels.
- `last_seen` and `availability` are separate from the alarm `alert` state.

## Simulator Design

The simulator must exercise the same device registration and sensor configuration
flow as a real Zigbee installation. It must not maintain a second device registry
that can diverge from the database.

The simulator UI can create a simulated Zigbee device by calling the existing
device-registration service or API contract. Registration persists the device and
its logical sensors in the database, including:

- IEEE address, network address, manufacturer, model, and device name;
- discovered endpoints and capabilities; and
- the normal sensor records used by the server and monitor.

The simulator's live state is separate from registration data and is stored in
`simulator_zigbee.json`. Only state represented in that file is persisted by the
simulator. A restart therefore preserves simulated readings and availability, but
the registered device remains a normal database record rather than simulator-only
data.

Example simulator state:

```json
{
    "devices": {
        "00:11:22:33:44:55:66:77": {
            "available": true,
            "battery_level": 87,
            "signal_quality": 72,
            "last_seen": "2026-09-13T10:15:00+00:00",
            "capabilities": {
                "1/contact": true,
                "1/tamper": false,
                "1/temperature": 21.5
            }
        }
    }
}
```

The UI should provide controls for:

- creating and registering a simulated device;
- changing boolean and numeric capability values;
- toggling availability independently from alarm state; and
- changing battery level and signal quality.

Changing a capability value represents device activity and updates `last_seen`.
The simulator does not write alarm `alert` state directly. The monitor resolves
the registered device, endpoint, and capability, then evaluates the value through
the normal alert path.

When a device is unavailable, availability remains separate from the last value.
The monitor must expose the unavailable condition as sensor error state and must
not treat the stale value as a new alarm event. This keeps communication failure
distinct from a valid contact, tamper, or numeric sensor reading.
