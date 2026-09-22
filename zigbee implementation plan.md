# Zigbee Implementation Plan

## Goal

Support Zigbee devices alongside the existing V2/V3 wired sensors without changing
the meaning of the existing `Sensor.channel` field. The real coordinator and the
simulator must use the same adapter, registration, sensor mapping, and monitoring
contracts. Only the transport and mutable state source should differ.

The first alarm-capability slice supports:

- contact/open-close state;
- tamper state;
- availability and communication error reporting.

Battery level and signal quality remain device metadata and maintenance information,
not alarm sensors. Generic numeric capabilities and manufacturer-specific attributes
are later work.

## Architecture Decisions

### One shared adapter instance

There is one Zigbee coordinator, so create one adapter instance per monitor process.
The instance is dependency-injected into the components that need it; it is not a
process-global singleton.

```text
Monitor
  - creates and starts one ZigbeeAdapter
  - dispatches pairing commands
  - owns adapter shutdown
  - passes the adapter to SensorHandler and Zigbee registration handling

ZigbeeAdapter
  - controls the real or mock coordinator
  - enables permit joining
  - discovers devices and capabilities
  - maintains latest normalized readings
  - does not create SQLAlchemy records

SensorHandler
  - uses the same adapter for readings
  - resolves wired and Zigbee sensors independently
  - feeds both sources into the existing alert pipeline

Registration service/handler
  - owns ZigbeeDevice persistence
  - validates duplicate IEEE addresses and discovered capabilities
  - removes a simulator pairing request only after a successful commit
```

Do not call `get_zigbee_adapter()` independently from both `Monitor` and
`SensorHandler`. Pairing and reading must use the same coordinator state, cache, and
event loop.

### Device versus logical sensor

`ZigbeeDevice` represents paired hardware. `Sensor` represents an alarm input with
its own name, type, area, zone, enabled state, contact semantics, and alert timing.
Pairing creates a device, but does not automatically create alarm sensors. The user
must explicitly map discovered capabilities to logical sensors so zones and alert
behavior are never guessed.

A single physical device can therefore produce multiple logical sensors:

```text
Front door device
  - endpoint 1 / contact -> Front door sensor
  - endpoint 1 / tamper  -> Front door tamper sensor
```

## Phase 1: Contracts and Coordinator Configuration

1. Finalize the public Zigbee coordinator configuration contract. Reuse the existing
   option infrastructure in `src/monitor/config/models.py`,
   `src/server/services/option/zigbee.py`, and `src/server/blueprints/option.py`.
2. Resolve the naming mismatch between the current fields (`enable`,
   `serial_port_path`, `baudrate`) and the design fields (`enabled`, `serial_port`,
   `adapter`, `permit_join`). Preserve compatibility for existing installations if
   these options are already deployed.
3. Define normalized adapter contracts for both implementations:

   ```python
   adapter.start() -> None
   adapter.stop() -> None
   adapter.permit_joining(duration_seconds: int) -> bool
   adapter.get_joined_devices() -> list[DiscoveredDevice]
   adapter.get_values() -> list[ZigbeeReading]
   adapter.get_value(ieee_address, endpoint, capability) -> ZigbeeReading | None
   ```

   A `ZigbeeReading` contains IEEE address, endpoint, capability, value, timestamp,
   availability, battery level, signal quality, and an optional error reason.
   A `DiscoveredDevice` contains device identity, network address, metadata, and
   discovered endpoint/capability information.
4. Define startup failure, pairing timeout, reconnect, and shutdown behavior. Real
   adapter initialization must not leave `start()` waiting forever if Bellows fails.
5. Verify that disabling Zigbee leaves existing V2/V3 startup, calibration, and
   monitoring unchanged.

## Phase 2: Database Model and Migrations

1. Add a migration under `migrations/versions/` extending `sensor` with nullable:

   - `zigbee_device_id`;
   - `zigbee_endpoint`;
   - `zigbee_capability`.

2. Add a foreign key from `sensor.zigbee_device_id` to `zigbee_device.id`.
3. Add constraints for exactly one source:

   - wired sensor: `channel` is set and all Zigbee fields are null;
   - Zigbee sensor: `channel` is null and all Zigbee fields are set.

4. Add uniqueness for a logical capability mapping, preferably
   `(zigbee_device_id, zigbee_endpoint, zigbee_capability)`, unless the product
   deliberately supports multiple logical sensors for one capability.
5. Update `src/utils/models.py` so `Sensor` can construct, validate, update, and
   serialize both sources. Preserve existing wired validation and API behavior.
6. Add a `Sensor` relationship to `ZigbeeDevice`. Keep the device model focused on
   identity and metadata; alarm state remains on `Sensor`.
7. Choose and implement device deletion behavior before adding the foreign key.
   Recommended policy: block deletion while logical sensors reference the device and
   require explicit sensor remapping or deletion.
8. Make alert and arm history source-aware. `AlertSensor` and `ArmSensor` currently
   assume a channel; Zigbee history must not fail when `channel` is null. Update
   `src/monitor/alert.py` and all notification formatting that assumes
   `sensor.channel + 1`.
9. Verify migration upgrade/downgrade behavior and confirm existing wired rows are
   unchanged.

## Phase 3: Pairing and Device Registration

1. Complete the existing `MonitorZigbeePairingCommand` path in:

   - `src/monitor/actions.py`;
   - `src/monitor/ipc.py`;
   - `src/server/ipc.py`;
   - `src/monitor/monitor.py`.

2. Add the monitor action handler that calls `permit_joining()` on the shared adapter.
3. Enforce the existing configuration rule: pairing and device configuration are
   allowed only while the system is disarmed/configurable.
4. Implement discovery separately from persistence:

   ```text
   pairing command
     -> adapter permit_joining()
     -> coordinator reports joined device
     -> adapter returns DiscoveredDevice
     -> registration service validates and commits ZigbeeDevice
     -> monitor reloads relevant configuration
   ```

5. Duplicate IEEE addresses must update discovery metadata or return a clear
   duplicate result. They must never create a second device row.
6. Add or complete REST endpoints in `src/server/blueprints/zigbee.py` and service
   operations in `src/server/services/zigbee.py` for listing, registering, updating,
   deleting, pairing, and discovering capabilities.
7. Keep adapter code independent of SQLAlchemy. The adapter reports a joined device;
   the registration service decides how it becomes a database record.
8. Add transaction ordering for the simulator: commit the device first, then remove
   the one-shot pairing request from JSON. If persistence fails, retain the request
   for retry and report the failure.

## Phase 4: Source-Aware Monitoring

1. Refactor `src/monitor/sensor/handler.py` to receive the already-created Zigbee
   adapter. Remove independent adapter creation and startup from the handler.
2. Keep wired-only behavior isolated:

   - channel-count validation;
   - duplicate channel validation;
   - ADC/GPIO calibration;
   - `detector.py` voltage, EOL, open-circuit, and short-circuit rules.

3. Zigbee sensors must not be skipped because `channel` is null and must not count
   toward wired channel limits.
4. Resolve Zigbee readings by `zigbee_device_id`, endpoint, and capability. Handle a
   missing mapping, unknown capability, malformed value, and unavailable device
   without crashing the monitor loop.
5. Add dedicated Zigbee normalization and evaluation instead of passing Zigbee
   values through wired `detect_alert()` and `detect_error()`:

   - `contact`: normalize vendor values to open/closed and apply `NO`/`NC` semantics;
   - `tamper`: normalize tamper-active to an alert and use existing sabotage/tamper
     zone behavior;
   - battery and signal: update device metadata only, with no alarm sensor.

6. Define availability behavior:

   - keep the last value available for diagnostics;
   - set the mapped sensor `error` when unavailable or stale;
   - do not create a new alarm from a stale value;
   - clear the communication error after recovery;
   - document how an already-active alert is cleared.

7. Feed the normalized boolean state and error state through the existing
   `SensorsHistory`, MQTT publication, database commit, and `handle_alerts()` logic.
8. Verify wired and Zigbee sensors coexist in one monitor cycle with existing arm,
   zone, delay, and sensitivity behavior unchanged.

## Phase 5: Simulator Parity

1. Treat `simulator_zigbee.json` as a transport/state file, not a second device
   registry. Database rows are the authoritative list of registered devices.
2. Use a structure with separate one-shot pairing requests and persistent runtime
   state:

   ```json
   {
     "pairing_requests": {
       "00:11:22:33:44:55:66:77": {
         "name": "Front door",
         "manufacturer": "Simulator",
         "model": "Door Sensor",
         "pairing": true,
         "capabilities": {
           "1/contact": false,
           "1/tamper": false
         }
       }
     },
     "devices": {
       "00:11:22:33:44:55:66:77": {
         "available": true,
         "battery_level": 87,
         "signal_quality": 72,
         "last_seen": "2026-09-13T10:15:00+00:00",
         "capabilities": {
           "1/contact": false,
           "1/tamper": false
         }
       }
     }
   }
   ```

3. Extend `src/monitor/adapters/mock/utils.py` with locked operations for reading,
   updating, and consuming pairing requests and runtime state. Preserve unrelated
   JSON fields during updates.
4. Update `src/monitor/adapters/mock/zigbee.py` to implement the same pairing,
   discovery, lookup, availability, and normalization contract as the real adapter.
   It must not create database rows or write alarm state.
5. Update `src/simulator/app.py`:

   - Add Device writes a pairing request;
   - the adapter consumes the request after pairing and database commit;
   - the device list reads registered devices from the database;
   - Update from database refreshes the list and current metadata;
   - contact and tamper controls update only JSON runtime state;
   - battery and signal remain metadata controls;
   - changing a capability updates `last_seen`.

6. Keep the existing wired simulator files and behavior unchanged.
7. Verify that a simulator restart preserves database registration and mutable JSON
   state, while a removed database device no longer appears in the simulator list.

## Phase 6: Web API and Angular UI

1. Add Angular models and remote service methods for Zigbee devices, capabilities,
   coordinator configuration, pairing, and sensor mappings.
2. Add a device management view showing name, IEEE address, model, availability,
   battery, signal, last seen, and discovered capabilities.
3. Add pairing controls with clear states for idle, pairing, joined, failed, timed
   out, duplicate, and unavailable coordinator.
4. Extend the sensor detail form so the user chooses either:

   - wired source and channel configuration; or
   - Zigbee device, endpoint, and capability.

5. Hide wired channel/EOL controls for Zigbee sensors and preserve existing wired
   validation.
6. Make contact and tamper mappings explicit. Do not automatically create battery
   alarms.
7. Apply existing authentication, admin, host, and disarmed-system restrictions.
8. Add frontend tests for service payloads, pairing state, list refresh, source
   switching, and Zigbee sensor updates.

## Phase 7: Tests and Verification

### Unit tests

Add focused server tests for:

- `Sensor` source validation and serialization;
- Zigbee device validation and duplicate IEEE handling;
- capability mapping uniqueness;
- pairing command dispatch and handler registration;
- shared adapter lifecycle and one start/stop call;
- real adapter lifecycle with Bellows mocked;
- mock JSON locking and pairing-request transitions;
- contact normalization and `NO`/`NC` behavior;
- tamper normalization and sabotage semantics;
- unavailable, stale, malformed, and recovered readings;
- alert and arm history with no wired channel;
- wired/Zigbee source routing and calibration isolation.

### Functional tests

Cover:

- pairing while disarmed;
- pairing rejection while armed;
- successful database commit followed by pairing-request removal;
- retained request after database failure;
- duplicate IEEE address;
- database-backed simulator device list;
- contact state causing a normal alarm;
- tamper state causing a sabotage alarm;
- unavailable device causing an error without a stale-value alarm;
- recovery clearing the error;
- wired and Zigbee sensors coexisting;
- restart preserving registered devices and simulator state.

### Manual simulator scenario

1. Start the simulator, monitor, database, and MQTT test infrastructure.
2. Fill the Zigbee device form and press Add Device.
3. Enable pairing through the pairing action.
4. Confirm a `ZigbeeDevice` row is created and the one-shot request is removed.
5. Refresh from the database and confirm the device appears in the list.
6. Map `endpoint=1`, `capability=contact` to a logical sensor.
7. Toggle contact while disarmed and verify sensor state changes.
8. Arm the appropriate area and toggle contact again; verify the normal alarm path.
9. Toggle `endpoint=1`, `capability=tamper`; verify sabotage behavior.
10. Toggle availability off; verify error state without interpreting the stale contact
    value as a new alarm.
11. Restore availability and verify recovery.
12. Restart and confirm both database registration and JSON runtime state remain.

### Commands

Run the repository-standard checks from `server/AGENTS.md`:

```text
uv run pytest -v
task test:all
```

Also run the webapplication package's existing lint, typecheck, and unit-test
commands after the Angular work. Run migration upgrade/downgrade checks against a
disposable database before merging schema changes.

## Scope Boundaries

Included:

- coordinator lifecycle and shared adapter ownership;
- pairing and device discovery;
- database-backed device registration;
- logical sensor-to-capability mapping;
- contact, tamper, and availability monitoring;
- simulator parity;
- API/UI management;
- focused unit and functional tests.

Deferred:

- battery and signal-quality alarm sensors;
- generic numeric thresholds such as temperature;
- automatic logical sensor creation for every discovered capability;
- arbitrary manufacturer-specific attributes;
- replacement of the existing wired detector;
- multiple coordinators.

## Risks and Required Decisions

1. **Configuration names:** choose the stable public coordinator option names before
   API implementation; translate legacy names internally if required.
2. **Device deletion:** choose the foreign-key policy before migration; blocking
   deletion while mapped sensors exist is recommended.
3. **Pairing timeout:** define whether a request remains visible for retry after a
   timeout; it should remain until successful registration or explicit cancellation.
4. **Unavailable values:** ensure stale readings never create new alarms.
5. **Historical identity:** update all alert, arm, MQTT, and notification code that
   assumes every sensor has a channel.
6. **Real-device discovery:** isolate Bellows/ZHA details behind the adapter contract
   so another coordinator or simulator transport does not require model changes.
