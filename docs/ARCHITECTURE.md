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

SmartHRT uses a **5-state finite state machine** for the daily heating cycle:

```
Evening (23:00)          Night              Morning           Wake-up (06:00)
      │                   │                    │                    │
      ▼                   ▼                    ▼                    ▼
   HEATING_ON ────► DETECTING_LAG ────► MONITORING ────► RECOVERY ────► RECOVERY_END
      │                   │                    │                │
   Stop heating      Temp drops            Calculate      Start heating    Target reached
   Record baseline   Detect pattern        recovery time   Update learning
```

### State Descriptions

| State             | Triggered By                         | Action                         | Transitions To |
| ----------------- | ------------------------------------ | ------------------------------ | -------------- |
| **HEATING_ON**    | Heating active                       | Monitor heating effect         | DETECTING_LAG  |
| **DETECTING_LAG** | Temp drops 0.2°C+                    | Detect thermal response delay  | MONITORING     |
| **MONITORING**    | Recovery time calculated             | Wait for calculated start time | RECOVERY       |
| **RECOVERY**      | Heating starts at calculated time    | Measure heating rate (RPth)    | RECOVERY_END   |
| **RECOVERY_END**  | Target hour reached or temp achieved | Finalize learning, reset       | HEATING_ON     |

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
- zone_name: Name of the heating zone
- target_hour: When to reach target temperature
- heating_stop_hour: When to turn off heating
- interior_temp_sensor: Room thermometer
- weather_entity: Weather source
- target_temperature: Desired temperature (°C)
```

### Learned Coefficients (Persistent)

```
- rc_thermal: Cooling constant (1-200 hours)
- rc_thermal_windy: Cooling at max wind (1-200 hours)
- rp_thermal: Heating constant (0.1-50 hours)
- rp_thermal_windy: Heating at max wind (0.1-50 hours)
- temperature_lag: Heating detection delay (minutes)
```

### Calculated Values (Real-time)

```
- recovery_start_time: When to start heating (HH:MM)
- recovery_duration: How long heating will run (minutes)
- interior_temperature: Current room temperature
- exterior_temperature: Outside temperature
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

### smarthrt.on_heating_stop

Called when heating stops (evening). Records baseline temperature for next calculation.

### smarthrt.on_recovery_start

Called when heating starts (morning). Triggers RPth measurement mode.

### smarthrt.on_recovery_end

Called at target hour. Finalizes learning and resets for next day.

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
