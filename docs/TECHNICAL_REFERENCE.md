# 🏗️ Technical Reference

**Architecture, design and mathematical specifications**

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [State Machine](#state-machine)
3. [Data Model](#data-model)
4. [Thermal Calculations](#thermal-calculations)
5. [Mathematical Formulas](#mathematical-formulas)
6. [Persistence Strategy](#persistence-strategy)
7. [Visual Diagrams](#visual-diagrams)

---

## Architecture Overview

SmartHRT is built on Home Assistant's **DataUpdateCoordinator** pattern:

```
┌─────────────────────────────────────────────────────┐
│         Home Assistant Core                         │
├─────────────────────────────────────────────────────┤
│  ConfigEntry ──► SmartHRTCoordinator ◄── Services  │
│                       │                             │
│         ┌─────────────┼──────────────┐              │
│         ▼             ▼              ▼              │
│    SmartHRTData  Weather Entity  Temperature Lag   │
│    (Dataclass)                                      │
│         │                                           │
│    ┌────┴──────────────────────────┐               │
│    │   Entities (Sensors/Switches)  │               │
│    │ - Interior/Exterior Temps      │               │
│    │ - RCth/RPth coefficients       │               │
│    │ - Recovery time prediction     │               │
│    │ - Mode switches                │               │
│    └────────────────────────────────┘               │
```

### Coordinator Pattern

The **SmartHRTCoordinator** manages:

- **Thermal calculations** (RCth, RPth interpolation based on wind)
- **State machine** (5-state heating cycle)
- **Time-based triggers** (recoverycalc_hour, recovery_start_hour, target_hour)
- **Automatic calibration** (exponential relaxation with polynomial distribution)
- **Weather integration** (temperature and wind forecasts)
- **Persistence** (coefficients stored in Home Assistant Store)

---

## State Machine

SmartHRT operates on a **5-state heating cycle**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DAILY CYCLE                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  23:00                    03:00 (calc)            06:00 (target_hour)  │
│    │                         │                         │               │
│    ▼                         ▼                         ▼               │
│ ┌─────────┐            ┌──────────┐             ┌─────────┐            │
│ │ PHASE 1 │            │ PHASE 2  │             │ PHASE 3 │            │
│ │ HEATING │            │ RECOVERY │             │ RECOVERY│            │
│ │  STOP   │─(cool)────►│  START   │─(heat)────►│  END    │            │
│ └─────────┘            └──────────┘             └─────────┘            │
│    │                         │                         │               │
│    • Record snapshot     • Calculate actual     • Calculate            │
│    • Detect lag           RCth                   RPth                 │
│    • Calc recovery      • Start heating         • Update coefs       │
│      time               • Enable rp_calc        • Disable rp_calc    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### State Definitions

| State             | Trigger                              | Action                           | Next State    |
| ----------------- | ------------------------------------ | -------------------------------- | ------------- |
| **HEATING_ON**    | Heating active                       | Monitor, calculate recovery time | DETECTING_LAG |
| **DETECTING_LAG** | Temperature drop detected (-0.2°C)   | Enable recovery calculation mode | MONITORING    |
| **MONITORING**    | Recovery time calculated             | Wait for recovery_start_hour     | RECOVERY      |
| **RECOVERY**      | Heating starts at recovery time      | Update RCth, enable RPth calc    | RECOVERY_END  |
| **RECOVERY_END**  | Target hour reached or temp achieved | Update RPth, disable calc modes  | HEATING_ON    |

---

## Data Model

### Core Data Class (SmartHRTData)

```
SmartHRTData
├── Configuration
│   ├── name: str
│   ├── tsp: float (target set point, °C)
│   ├── target_hour: time
│   └── recoverycalc_hour: time
├── State Machine
│   ├── current_state: str
│   ├── smartheating_mode: bool
│   ├── recovery_adaptive_mode: bool
│   ├── recovery_calc_mode: bool
│   └── rp_calc_mode: bool
├── Thermal Coefficients (Persistent)
│   ├── rcth: float (combined, interpolated)
│   ├── rpth: float (combined, interpolated)
│   ├── rcth_lw: float (low wind, ≤10 km/h)
│   ├── rcth_hw: float (high wind, ≥60 km/h)
│   ├── rpth_lw: float (low wind)
│   ├── rpth_hw: float (high wind)
│   ├── rcth_fast: float (dynamic, no persistence)
│   └── relaxation_factor: float (smoothing)
├── Current Conditions
│   ├── interior_temp: float (°C)
│   ├── exterior_temp: float (°C)
│   ├── wind_speed: float (m/s)
│   ├── wind_speed_forecast_avg: float (km/h)
│   ├── temperature_forecast_avg: float (°C)
│   └── wind_speed_avg: float (m/s, 4h rolling)
├── Reference Temperatures
│   ├── temp_recovery_calc: float (Tint @ recoverycalc_hour)
│   ├── temp_recovery_start: float (Tint @ recovery_start)
│   ├── temp_recovery_end: float (Tint @ target_hour)
│   ├── text_recovery_calc: float (Text @ recoverycalc_hour)
│   ├── text_recovery_start: float (Text @ recovery_start)
│   └── text_recovery_end: float (Text @ target_hour)
└── Timestamps
    ├── time_recovery_calc: datetime
    ├── time_recovery_start: datetime
    ├── time_recovery_end: datetime
    ├── recovery_start_hour: datetime (calculated)
    └── recovery_update_hour: datetime (next recalc)
```

### Wind-Based Interpolation

Coefficients are interpolated based on wind speed:

$$
\text{coeff}_{interpolated} = \text{coeff}_{lw} + \frac{\text{wind}_{avg} - 10}{60 - 10} \times (\text{coeff}_{hw} - \text{coeff}_{lw})
$$

**Thresholds:**

- Low wind: ≤ 10 km/h → use `*_lw` coefficients
- High wind: ≥ 60 km/h → use `*_hw` coefficients
- Between: Linear interpolation

---

## Thermal Calculations

### RCth (Room Constant - Cooling)

**Definition**: Thermal time constant (hours). Time to lose 63% of temperature difference.

**How it's calculated (on_recovery_start)**:

$$
RCth_{actual} = \frac{\Delta t}{\ln\left(\frac{T_{ext,start} - T_{int,start}}{T_{ext,calc} - T_{int,calc}}\right)}
$$

Where:

- $\Delta t$ = time since heating stop (hours)
- $T_{int,start}$, $T_{int,calc}$ = interior temp at start and stop
- $T_{ext,start}$, $T_{ext,calc}$ = exterior temp at start and stop

**Error detection**: Aborted if $|\ln(...) | < 0.1$ (insufficient temperature difference)

### RPth (Room Power - Heating)

**Definition**: Thermal power constant (°C). Maximum temperature gain at equilibrium.

**How it's calculated (on_recovery_end)**:

$$
RPth_{actual} = T_{ext,end} - T_{int,end}
$$

If system is close to target temperature, RPth represents the max heating power in the current conditions.

### Relaxation Formula (Adaptive Learning)

When updating coefficients, use exponential smoothing:

$$
coeff_{new} = \frac{coeff_{old} \times relaxation_{factor} + coeff_{observed}}{relaxation_{factor} + 1}
$$

**Default relaxation factor**: 2.0 (smooths out aberrant measurements)

---

## Mathematical Formulas

### Main Recovery Time Prediction

This is the **critical formula** used to calculate when heating should start:

$$
recovery\_duration = RCth \times \ln\left(\frac{RPth + T_{ext} - T_{int}^{start}}{RPth + T_{ext} - T_{sp}}\right)
$$

Where:

- $RCth$ = thermal time constant (hours)
- $RPth$ = thermal power constant (°C)
- $T_{ext}$ = exterior temperature (°C) - uses 3h forecast
- $T_{int}^{start}$ = interior temperature at calculation time (°C)
- $T_{sp}$ = target set point (°C)

**Requirements**:

- $RPth + T_{ext} - T_{int}^{start} > 0$ (interior is colder than equilibrium)
- $RPth + T_{ext} - T_{sp} > 0$ (target is achievable)
- $RCth > 0$, $RPth > 0$

### Wind Speed History

Maintains a **4-hour rolling window** (240 samples at 60s intervals):

```python
wind_speed_history = deque(maxlen=240)  # 4 hours
wind_speed_avg = mean(wind_speed_history)  # Current average
```

**Updated every 60 seconds** during coordinator `_async_update_data()`

---

## Persistence Strategy

### What's Persisted

SmartHRT stores **learned coefficients** in Home Assistant's persistent storage:

| Item                | Where            | Trigger                                       |
| ------------------- | ---------------- | --------------------------------------------- |
| `rcth_lw`           | Persistent store | Updated on_recovery_start if adaptive mode ON |
| `rcth_hw`           | Persistent store | Updated on_recovery_start if adaptive mode ON |
| `rpth_lw`           | Persistent store | Updated on_recovery_end if adaptive mode ON   |
| `rpth_hw`           | Persistent store | Updated on_recovery_end if adaptive mode ON   |
| `relaxation_factor` | Persistent store | Manual change via `number.*_relaxation`       |

### What's NOT Persisted

- `rcth_fast` (dynamic, recalculated during cooling phase)
- `rcth`, `rpth` (interpolated from `*_lw` and `*_hw`)
- `wind_speed_history` (recalculates on restart)
- All sensor readings (snapshots taken during each phase)

### Restore on Startup

1. ConfigEntry validated
2. Persistent store loaded
3. All `*_lw`, `*_hw` coefficients restored
4. Initial recovery time calculated

---

## Lifecycle Events

### Event: Heating Stop (Evening)

**Triggered**: `automation.on_heating_stop()` at `recoverycalc_hour` (e.g., 23:00)

**Actions**:

1. Record snapshot: $T_{int,calc}$, $T_{ext,calc}$
2. Initialize coefficients if first run
3. Activate lag detection
4. Transition → DETECTING_LAG

### Event: Lag Detected (Nighttime)

**Triggered**: Temperature drop ≥ 0.2°C detected

**Actions**:

1. Disable lag detection
2. Enable `recovery_calc_mode`
3. Calculate recovery start time
4. Transition → MONITORING

### Event: Recovery Start (Morning)

**Triggered**: `automation.on_recovery_start()` at calculated time

**Actions**:

1. Record snapshot: $T_{int,start}$, $T_{ext,start}$
2. Calculate actual $RCth$ observed
3. Update `rcth_lw` and `rcth_hw` via relaxation
4. Enable `rp_calc_mode`
5. Transition → RECOVERY

### Event: Recovery End (Wake-up)

**Triggered**: `automation.on_recovery_end()` at `target_hour` (e.g., 06:00)

**Actions**:

1. Record snapshot: $T_{int,end}$, $T_{ext,end}$
2. Calculate actual $RPth$ observed
3. Update `rpth_lw` and `rpth_hw` via relaxation
4. Disable `rp_calc_mode`
5. Transition → HEATING_ON

---

## Visual Diagrams

For comprehensive visual schemas and workflows, see [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md):

- System Architecture
- Daily Heating Cycle Timeline
- State Machine Flow
- Data Flow Diagrams
- Calculation Pipeline
- Thermal Model
- Calibration Process

---

**Related:**

- 📊 [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md)
- 🚀 [Getting Started](GETTING_STARTED.md)
- 🔧 [Support](SUPPORT.md)
