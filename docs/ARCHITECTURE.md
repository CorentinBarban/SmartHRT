# SmartHRT Architecture Guide

**Technical architecture, design patterns, and thermal calculations**

## System Overview

SmartHRT is a Home Assistant custom integration built on the **DataUpdateCoordinator** pattern. It automates heating startup calculations using adaptive thermal modeling.

```
┌───────────────────────────────────────────────────┐
│         Home Assistant Core                       │
├───────────────────────────────────────────────────┤
│  ConfigEntry ──► SmartHRTCoordinator ◄── Services │
│                       │                           │
│     ┌─────────────────┼──────────────┐            │
│     ▼                 ▼              ▼            │
│  Weather Entity   Config Data    Temperature Data │
│                       │                           │
│  ┌────────────────────┴──────────────────┐        │
│  │  Entities (Sensors/Switches/Numbers)  │        │
│  │  - Predictions                        │        │
│  │  - Thermal coefficients               │        │
│  │  - Mode controls                      │        │
│  └───────────────────────────────────────┘        │
└───────────────────────────────────────────────────┘
```

## State Machine

SmartHRT uses a **6-state finite state machine** for the daily heating cycle:

```
(Re)start
    │
    ▼
INITIALIZING ─► (restores persisted state)

Evening (23:00)          Night              Morning           Wake-up (06:00)
      │                   │                    │                    │
      ▼                   ▼                    ▼                    ▼
   HEATING_ON ──► DETECTING_LAG ──► MONITORING ──► RECOVERY ──► HEATING_PROCESS
      ◄────────────────────────────────────────────────────────────────┘
```

### State Descriptions

| State               | Triggered By                      | Action                         | Transitions To         |
| ------------------- | --------------------------------- | ------------------------------ | ---------------------- |
| **INITIALIZING**    | Integration (re)start             | Restore persisted state        | Any (restoration)      |
| **HEATING_ON**      | Heating active                    | Monitor heating effect         | DETECTING_LAG          |
| **DETECTING_LAG**   | Heating stops                     | Detect thermal response delay  | MONITORING             |
| **MONITORING**      | Lag detected                      | Wait for calculated start time | RECOVERY or HEATING_ON |
| **RECOVERY**        | Heating starts at calculated time | Measure heating rate (RPth)    | HEATING_PROCESS        |
| **HEATING_PROCESS** | Recovery confirmed                | Finalize learning, reset       | HEATING_ON             |

## Thermal Model

SmartHRT models your home using **two key constants:**

### RCth - Cooling Constant

Measures how fast your room loses heat when heating is off.

**Newton's Law of Cooling:**
$$T(t) = T_{outside} + (T_{initial} - T_{outside}) \cdot e^{-t/RC_{th}}$$

**Interpretation:**

- High RCth = good insulation (heat loss is slow)
- Low RCth = poor insulation (heat loss is fast)

### RPth - Heating Constant

Measures how fast heating warms your room.

**Heating formula:**
$$T(t) = T_{target} - (T_{target} - T_{initial}) \cdot e^{-t/RP_{th}}$$

**Interpretation:**

- High RPth = fast heating (powerful system)
- Low RPth = slow heating (weak system)

## Wind Adaptation

Both RCth and RPth vary with wind speed using **linear interpolation:**

$$C(wind) = C_0 + (C_w - C_0) \cdot \frac{wind}{wind_{max}}$$

Where:

- $C_0$ = coefficient at zero wind
- $C_w$ = coefficient at maximum wind
- The system automatically learns both values

**Effect:**

- More wind → faster cooling → lower RCth → earlier heating start
- Calm conditions → slower cooling → higher RCth → later heating start

## Learning Process

### Phase 1: Detect Lag (Evening to Night)

After heating stops, monitor temperature drop to identify the thermal time constant.

### Phase 2: Calculate Recovery Time (Night)

Use RCth and RPth to predict when to start heating.

### Phase 3: Measure Heating Rate (Morning)

During heating, measure actual heating speed to update RPth.

### Calibration Strategy

Uses **exponential relaxation** for smooth learning:

$$C_{new} = C_{old} + \alpha \cdot (C_{measured} - C_{old})$$

Where $\alpha$ (learning rate) decays over time for stability.

## Data Model

### Core Configuration

```
- name: Name of the heating zone
- tsp: Target setpoint temperature (°C, 13–26)
- target_hour: When to reach target temperature
- recoverycalc_hour: When to turn off heating (default 23:00)
- sensor_interior_temperature: Room thermometer entity
- weather_entity: Weather source
```

### Learned Coefficients (Persistent)

```
- rcth: Cooling constant (1–200 hours)
- rcth_lw: Cooling constant at low wind
- rcth_hw: Cooling constant at high wind
- rpth: Heating constant (1–200 hours)
- rpth_lw: Heating constant at low wind
- rpth_hw: Heating constant at high wind
- relaxation_factor: Learning rate factor (0.1–10)
- stop_lag_duration: Measured temperature lag after heating stops (hours)
```

### Calculated Values (Real-time)

```
- recovery_start_hour: When to start heating (datetime)
- recovery_duration_hours: How long heating will run (hours)
- interior_temp: Current room temperature (°C)
- exterior_temp: Outside temperature (°C)
- wind_speed: Current wind speed (m/s)
- wind_speed_avg: 4h average wind speed (m/s)
```

## Entity Platform Distribution

### Sensors (Read-only data)

- Interior/exterior temperatures
- Recovery predictions
- Status information

### Numbers (Adjustable coefficients)

- RCth and RPth for manual tuning
- Temperature lag threshold
- Learning rate

### Switches (Mode controls)

- Enable/disable learning
- Manual mode overrides

### Times (User preferences)

- Target hour (wake-up time)
- Heating stop hour

## Services

See [SERVICES.md](SERVICES.md) for the full services reference.

Registered services: `start_heating_cycle`, `stop_heating`, `start_recovery`, `end_recovery`, `get_state`, `force_monitoring`, `reset_learning`, `trigger_calculation`.

## Persistence

**Storage:** Home Assistant's built-in data store (not YAML)

**Persisted Data:**

- RCth and RPth coefficients
- Wind adjustment factors
- Temperature lag measurements
- Learning rate and decay

**Update Frequency:**

- Every morning after recovery phase
- Smooth exponential updates (not instant)

## Wind Speed Integration

Wind data comes from the weather entity (3-hour forecast window). SmartHRT automatically:

1. Reads current/forecasted wind speed
2. Interpolates thermal coefficients
3. Recalculates recovery time if wind changes significantly

## Validation & Safety

The system includes bounds checking:

- RCth: 1-200 hours (invalid values reset to defaults)
- RPth: 0.1-50 hours
- Temperature lag: 0-120 minutes
- Recovery time: Never less than 5 minutes, max 12 hours

Out-of-bounds values trigger warnings but don't crash the system.

---
