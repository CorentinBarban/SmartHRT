# SmartHRT Services

This document describes the available services to control SmartHRT and their relationship with the state machine.

## State Machine

SmartHRT uses an explicit **6-state** finite state machine to model the daily thermal cycle:

```
(Re)start
    │
    ▼
INITIALIZING ──────────────────────────────────────────► (any state, restore)

HEATING_ON → DETECTING_LAG → MONITORING → RECOVERY → HEATING_PROCESS → HEATING_ON
  (State 1)    (State 2)      (State 3)    (State 4)      (State 5)
```

### State Descriptions

- **INITIALIZING**: Transient entry state after (re)start. Transitions to the persisted state from last session.
- **HEATING_ON**: Normal daytime heating mode
- **DETECTING_LAG**: Temperature lag detection after heating stops
- **HEATING_PROCESS**: Temperature rise phase (RPth calculation)

## Simplified Services (Recommended)

These services are user-oriented and correspond to the natural transitions of the state machine.

### `start_heating_cycle`

**Usage**: Starts a new daily heating cycle

**Transition**: `*` → `HEATING_ON`

**Parameters**:

- `entry_id` (optional): Instance ID for multi-instance setups

**Return**:

```yaml
success: true
state: "heating_on"
message: "Heating cycle started"
```

**Example call**:

```yaml
service: smarthrt.start_heating_cycle
```

---

### `stop_heating`

**Usage**: Stops heating and starts nighttime monitoring

**Transition**: `HEATING_ON` → `DETECTING_LAG` → `MONITORING`

**Description**:

- Records current temperatures
- Activates temperature lag detection
- Launches recovery time calculations once lag is detected

**Parameters**:

- `entry_id` (optional): Instance ID for multi-instance setups

**Return**:

```yaml
success: true
state: "monitoring"
recovery_start_hour: "2026-02-04T04:30:00+01:00"
message: "Heating stopped, monitoring started"
```

**Example call**:

```yaml
service: smarthrt.stop_heating
```

**⚠️ Note**: This service is normally called automatically at `recoverycalc_hour` (default 11:00 PM).

---

### `start_recovery`

**Usage**: Starts the heating recovery phase

**Transition**: `MONITORING` → `RECOVERY` → `HEATING_PROCESS`

**Description**:

- Calculates RCth (thermal time constant)
- Enables RPth calculation mode
- Automatic transition to HEATING_PROCESS

**Parameters**:

- `entry_id` (optional): Instance ID for multi-instance setups

**Return**:

```yaml
success: true
state: "heating_process"
time_recovery_start: "2026-02-04T04:30:15+01:00"
rcth_calculated: 52.3
message: "Recovery started"
```

**Example call**:

```yaml
service: smarthrt.start_recovery
```

**⚠️ Note**: This service is normally called automatically at `recovery_start_hour`.

---

### `end_recovery`

**Usage**: Ends the recovery phase

**Transition**: `HEATING_PROCESS` → `HEATING_ON`

**Description**:

- Calculates RPth (thermal power constant)
- Returns to normal heating mode
- Updates learned coefficients

**Parameters**:

- `entry_id` (optional): Instance ID for multi-instance setups

**Return**:

```yaml
success: true
state: "heating_on"
time_recovery_end: "2026-02-04T06:00:00+01:00"
rpth_calculated: 48.7
message: "Recovery ended"
```

**Example call**:

```yaml
service: smarthrt.end_recovery
```

**⚠️ Note**: This service is normally called automatically at `target_hour` (wake-up time) or when the setpoint is reached.

---

### `get_state`

**Usage**: Returns the complete system state

**Parameters**:

- `entry_id` (optional): Instance ID for multi-instance setups

**Return**:

```yaml
success: true
state: "monitoring"
smartheating_mode: true
recovery_calc_mode: true
rp_calc_mode: false
temp_lag_detection_active: false
interior_temp: 18.5
exterior_temp: 2.3
target_hour: "06:00:00"
recoverycalc_hour: "23:00:00"
recovery_start_hour: "2026-02-04T04:30:00+01:00"
time_to_recovery_hours: 5.2
rcth: 52.3
rpth: 48.7
```

**Example call**:

```yaml
service: smarthrt.get_state
response_variable: state_info
```

---

### `force_monitoring`

**Usage**: Forces immediate transition to MONITORING state

**Transition**: `*` → `MONITORING`

**Description**:

- Skips the DETECTING_LAG phase
- Immediately starts recovery time calculations
- Useful when lag detection is stuck or not needed

**Parameters**:

- `entry_id` (optional): Instance ID for multi-instance setups

**Example call**:

```yaml
service: smarthrt.force_monitoring
```

---

## Utility Services

### `reset_learning`

Resets all learned thermal coefficients to default values (50).

**Usage**: After home modifications or if learned values are inaccurate

**Parameters**:

- `entry_id` (optional): Instance ID for multi-instance setups

**Example**:

```yaml
service: smarthrt.reset_learning
```

---

### `trigger_calculation`

Immediately triggers a new recovery time calculation.

**Usage**: After parameter changes to see the effect immediately

**Parameters**:

- `entry_id` (optional): Instance ID for multi-instance setups

**Example**:

```yaml
service: smarthrt.trigger_calculation
```

---

## Automation Examples

### Complete manual cycle

```yaml
# Automation 1: Stop heating in the evening
automation:
  - alias: "SmartHRT - Stop heating at 11 PM"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      - service: smarthrt.stop_heating

# Automation 2: Start recovery (automatic via recovery_start_hour)
# No automation needed, SmartHRT triggers automatically

# Automation 3: End recovery at wake-up
automation:
  - alias: "SmartHRT - End recovery at wake-up"
    trigger:
      - platform: time
        at: "06:00:00"
    action:
      - service: smarthrt.end_recovery
```

### Force a new cycle

```yaml
automation:
  - alias: "SmartHRT - Reset cycle after absence"
    trigger:
      - platform: state
        entity_id: person.home
        to: "home"
    action:
      - service: smarthrt.start_heating_cycle
```

### Debug and monitoring

```yaml
automation:
  - alias: "SmartHRT - Log state every hour"
    trigger:
      - platform: time_pattern
        hours: "/1"
    action:
      - service: smarthrt.get_state
        response_variable: state
      - service: system_log.write
        data:
          message: "SmartHRT state: {{ state.state }}, Recovery in: {{ state.time_to_recovery_hours }}h"
          level: info
```

---

## Multi-Instance

If you have multiple SmartHRT instances configured, you must specify the `entry_id` parameter to target a specific instance:

```yaml
service: smarthrt.stop_heating
data:
  entry_id: "abc123def456"
```

To find your `entry_id`, check the logs at startup or use Home Assistant's Developer Tools.

---

## Important Notes

1. **Automatic mode**: In most cases, you don't need to call these services manually. SmartHRT automatically manages state transitions.

2. **Recommended services**: Always prefer simplified services (`start_heating_cycle`, `stop_heating`, etc.) over legacy services.

3. **Service responses**: All services return a dictionary with at minimum `success` (bool) and contextual information. Use `response_variable` to capture this data in your automations.

4. **Transient states**: Some states are transient (DETECTING_LAG, RECOVERY) and may be very short in duration.
