# Architecture Diagrams

**Visual schemas of SmartHRT integration functioning**

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Daily Heating Cycle](#daily-heating-cycle)
3. [State Machine Flow](#state-machine-flow)
4. [Data Flow](#data-flow)
5. [Calculation Pipeline](#calculation-pipeline)
6. [Thermal Model](#thermal-model)
7. [Calibration Process](#calibration-process)

---

## System Architecture

### High-Level Integration Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                  Home Assistant Core                             │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────┐         │
│  │         Configuration & UI Layer                    │         │
│  │  ┌──────────────┐      ┌──────────────────────┐    │         │
│  │  │ config_flow  │      │ User Interface       │    │         │
│  │  │ (UI setup)   │◄────►│ (Settings menu)      │    │         │
│  │  └──────┬───────┘      └──────────────────────┘    │         │
│  └─────────┼──────────────────────────────────────────┘         │
│            │                                                    │
│            ▼                                                    │
│  ┌─────────────────────────────────────────────────────┐        │
│  │      SmartHRTCoordinator (Main Engine)              │        │
│  │  ┌─────────────────────────────────────────────┐   │        │
│  │  │  Data Updates (every 60s)                   │   │        │
│  │  │  • Fetch current temperatures                │   │        │
│  │  │  • Get weather forecast                      │   │        │
│  │  │  • Update wind history                       │   │        │
│  │  │  • Calculate recovery time                   │   │        │
│  │  └─────────────────────────────────────────────┘   │        │
│  │  ┌─────────────────────────────────────────────┐   │        │
│  │  │  State Machine Engine                       │   │        │
│  │  │  • Track current phase                       │   │        │
│  │  │  • Handle phase transitions                  │   │        │
│  │  │  • Trigger callbacks                         │   │        │
│  │  └─────────────────────────────────────────────┘   │        │
│  │  ┌─────────────────────────────────────────────┐   │        │
│  │  │  Thermal Calculation Engine                 │   │        │
│  │  │  • RCth computation                          │   │        │
│  │  │  • RPth computation                          │   │        │
│  │  │  • Wind interpolation                        │   │        │
│  │  │  • Auto-calibration                          │   │        │
│  │  └─────────────────────────────────────────────┘   │        │
│  │  ┌─────────────────────────────────────────────┐   │        │
│  │  │  Persistence Layer                          │   │        │
│  │  │  • Load/save coefficients                    │   │        │
│  │  │  • Store learned values                      │   │        │
│  │  └─────────────────────────────────────────────┘   │        │
│  └─────────────────────────────────────────────────────┘        │
│            │                  │                 │                │
│    ┌───────┴──────┐   ┌──────┴────────┐   ┌───┴──────────┐     │
│    ▼              ▼   ▼               ▼   ▼              ▼     │
│  ┌────────┐  ┌──────────┐  ┌──────────┐ ┌────────┐  ┌────────┐│
│  │Sensors │  │ Numbers  │  │ Switches │ │ Times  │  │Services││
│  │(T°,%%%)│  │(coefs)   │  │(modes)   │ │(timing)│  │(events)││
│  └────────┘  └──────────┘  └──────────┘ └────────┘  └────────┘│
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### External Integrations

```
┌──────────────────┐
│  Weather Entity  │◄──── Weather.Home (OpenWeatherMap, etc.)
│  (Forecast API)  │
└────────┬─────────┘
         │
         ▼
  SmartHRTCoordinator
         │
         ▼
┌──────────────────┐
│  Temperature     │◄──── Climate.Living_room (Sensor value)
│  Sensor Input    │
└────────┬─────────┘
         │
         ▼
  SmartHRTCoordinator
```

---

## Daily Heating Cycle

### Complete 24-Hour Timeline

```
TIME:       23:00        03:00 (approx)      06:00        23:00 (next)
            │            │                    │             │
EVENTS:     │            │                    │             │
            │            │                    │             │
PHASE 1     ▼            │                    │             │
HEATING  ┌─────┐         │                    │             │
STOP     │     │         │                    │             │
(Evening)│     │◄────────┤                    │             │
         │     │         │                    │             │
         └─────┘         │                    │             │
           ▲             │                    │             │
           │ Record      │                    │             │
           │ snapshot    │                    │             │
           │             │                    │             │
         ACTIONS:        │                    │             │
         • T_calc        │                    │             │
         • T_ext_calc    │                    │             │
         • Init coefs    │                    │             │
         • Detect lag    │                    │             │
                         │                    │             │
                    PHASE 2                   │             │
                    RECOVERY          PHASE 3 ▼             │
                    START          RECOVERY  ┌─────┐        │
                    (Night)        END       │     │        │
                 ┌─────┐         (Morning)   │     │        │
                 │     │         ┌─────┐    │     │        │
                 │     │◄────────►│     │    │     │        │
                 │     │         │     │    │     │        │
                 └─────┘         └─────┘    └─────┘        │
                   ▲               ▲          ▲             │
                   │ Calculate     │ Update   │ Update      │
                   │ RCth          │ RPth     │ Coefs       │
                   │               │          │             │
                 ACTIONS:        ACTIONS:   ACTIONS:        │
                 • T_start       • T_end    • Store coefs   │
                 • T_ext_start   • T_ext_end│ Disable modes │
                 • Update RCth   • Update   │ Reset phase   │
                 • Enable RP_calc│ RPth     │               │
                                 │ Disable  │               │
                                 │ RP_calc  │               │
                                            │               │
                                         ┌──┴───────────────┘
                                         │ Loop continues
                                         ▼
```

### Sensor Snapshots During Each Phase

```
Phase 1: HEATING STOP (Evening ~23:00)
┌─────────────────────────┐
│ Snapshot 1              │
│ • T_interior_calc       │ ◄─── Current room temp
│ • T_exterior_calc       │ ◄─── Current outdoor temp
│ • time_calc             │ ◄─── Reference time
│ • wind_speed_avg        │ ◄─── Average wind
└─────────────────────────┘
          │
          ▼ (4-12 hours pass)

Phase 2: RECOVERY START (Morning ~03:00)
┌─────────────────────────┐
│ Snapshot 2              │
│ • T_interior_start      │ ◄─── Room cooled down
│ • T_exterior_start      │ ◄─── Outdoor temp changed
│ • time_start            │ ◄─── When heating started
│ • wind_speed_avg_night  │ ◄─── Night wind avg
└─────────────────────────┘
          │
          ▼ (3-6 hours pass)

Phase 3: RECOVERY END (Wake-up ~06:00)
┌─────────────────────────┐
│ Snapshot 3              │
│ • T_interior_end        │ ◄─── Room heated up
│ • T_exterior_end        │ ◄─── Outdoor temp changed
│ • time_end              │ ◄─── When target reached
│ • wind_speed_avg_recovery│ ◄─── Recovery wind avg
└─────────────────────────┘
          │
          ▼ (Loop back to Phase 1)
```

---

## State Machine Flow

### 5-State State Machine with Transitions

```
┌─────────────────────────────────────────────────────────────────────┐
│                    STATE MACHINE DIAGRAM                            │
└─────────────────────────────────────────────────────────────────────┘

                           ┌────────────────┐
                           │   HEATING_ON   │
                           │  (Normal mode) │
                           └────────┬────────┘
                                    │
                    Heating active ◄─┘
                    Temperature drop
                    detected (-0.2°C)
                                    │
                                    ▼
                           ┌────────────────┐
                           │ DETECTING_LAG  │
                           │ (Lag tracking) │
                           └────────┬────────┘
                                    │
                    Lag detected    │
                    or manual        │
                    activation       │
                    of recovery_calc │
                                    │
                                    ▼
                           ┌────────────────┐
                           │  MONITORING    │
                           │ (Wait for start)
                           └────────┬────────┘
                                    │
                    Recovery time   │
                    calculated &    │
                    reached or      │
                    manual trigger  │
                                    │
                                    ▼
                           ┌────────────────┐
                           │  RECOVERY      │
                           │ (Heating phase)│
                           └────────┬────────┘
                                    │
                    Target hour     │
                    reached or      │
                    setpoint        │
                    achieved or     │
                    manual trigger  │
                                    │
                                    ▼
                           ┌────────────────┐
                           │ RECOVERY_END   │
                           │ (Calibration)  │
                           └────────┬────────┘
                                    │
                    Auto-transition │
                    after 2 minutes │
                    or next evening │
                                    │
                                    ▼
                           ┌────────────────┐
                           │   HEATING_ON   │
                           │  (Normal mode) │
                           └────────────────┘
```

### State Details with Callbacks

```
HEATING_ON
├─ Entry callback: None
├─ Active in: Normal operation
├─ Exit callback: Record snapshot
└─ Triggers:
   └─ Temperature drop ≥ 0.2°C → DETECTING_LAG

DETECTING_LAG
├─ Entry callback: Enable lag detection
├─ Active in: Evening to night
├─ Exit callback: Calculate recovery time
└─ Triggers:
   └─ Lag detected → MONITORING

MONITORING
├─ Entry callback: Set waiting state
├─ Active in: Night (waiting)
├─ Exit callback: None
└─ Triggers:
   └─ recovery_start_hour reached → RECOVERY

RECOVERY
├─ Entry callback: Calculate RCth, enable RP calculation
├─ Active in: Morning heating
├─ Exit callback: Record recovery end snapshot
└─ Triggers:
   └─ Target hour reached → RECOVERY_END

RECOVERY_END
├─ Entry callback: Calculate RPth, update coefficients
├─ Active in: Brief (~2 min) or until next HEATING_ON
├─ Exit callback: Reset all calc modes
└─ Triggers:
   └─ Auto-transition or next day → HEATING_ON
```

---

## Data Flow

### Information Flow Through the System

```
┌─────────────────────────┐
│  INPUT SOURCES          │
├─────────────────────────┤
│                         │
│  Home Assistant         │
│  • Sensors (T°)         │◄────────────┐
│  • Climate entities     │             │
│  • Weather entity       │             │
│  • User config          │             │
│                         │             │
└────────┬────────────────┘             │
         │                              │
         │ Coordinator._async_          │
         │ update_data()                │
         │ (Every 60 seconds)           │
         │                              │
         ▼                              │
┌─────────────────────────┐             │
│  DATA FETCHING          │             │
├─────────────────────────┤             │
│                         │             │
│ 1. Get current T°       │─────────────┤
│ 2. Get weather forecast │             │
│ 3. Get wind history     │             │
│ 4. Check state changes  │             │
│                         │             │
└────────┬────────────────┘             │
         │                              │
         │ Update SmartHRTData          │
         │                              │
         ▼                              │
┌─────────────────────────┐             │
│  THERMAL CALCULATIONS   │             │
├─────────────────────────┤             │
│                         │             │
│ • Interpolate RCth/RPth │             │
│   based on wind         │             │
│ • Calculate recovery    │             │
│   start time            │             │
│ • Update forecasts      │             │
│                         │             │
└────────┬────────────────┘             │
         │                              │
         │ Update all entity values     │
         │                              │
         ▼                              │
┌─────────────────────────┐             │
│  STATE MACHINE CHECK    │             │
├─────────────────────────┤             │
│                         │             │
│ • Check phase triggers  │             │
│ • Execute callbacks     │             │
│ • Update state if needed│             │
│                         │             │
└────────┬────────────────┘             │
         │                              │
         │ Emit service calls           │
         │                              │
         ▼                              │
┌─────────────────────────┐             │
│  ENTITY UPDATES         │             │
├─────────────────────────┤             │
│                         │             │
│ • Sensor values         │             │
│ • Number values         │             │
│ • Switch states         │             │
│ • Time values           │             │
│                         │             │
└────────┬────────────────┘             │
         │                              │
         └──────────────────────────────┘
              (Loop every 60s)
```

---

## Calculation Pipeline

### Recovery Start Time Calculation

```
INPUT:
  • T_interior (current room temp)
  • T_exterior (outdoor temp)
  • T_setpoint (desired temp)
  • RCth (thermal time constant)
  • RPth (thermal power constant)
  • Wind speed (for interpolation)

    ▼

┌──────────────────────────┐
│ STEP 1: Wind Interpolation
├──────────────────────────┤
│                          │
│ If wind_avg ≤ 10 km/h:  │
│   use RCth_lw, RPth_lw   │
│                          │
│ If wind_avg ≥ 60 km/h:  │
│   use RCth_hw, RPth_hw   │
│                          │
│ Else:                    │
│   interpolate linearly   │
│                          │
│ Formula:                 │
│ coeff = coeff_lw +       │
│   (wind-10)/(60-10) *    │
│   (coeff_hw - coeff_lw)  │
│                          │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ STEP 2: Validation       │
├──────────────────────────┤
│                          │
│ Check:                   │
│ • RCth > 0               │
│ • RPth > 0               │
│ • T_exterior defined     │
│ • Heating achievable     │
│   (RPth + T_ext - T_sp > 0)
│                          │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ STEP 3: Main Calculation │
├──────────────────────────┤
│                          │
│ recovery_duration =      │
│   RCth * ln(             │
│     (RPth + T_ext -      │
│      T_interior_current) │
│     ───────────────      │
│     (RPth + T_ext -      │
│      T_setpoint)         │
│   )                      │
│                          │
│ Result: Hours needed     │
│                          │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ STEP 4: Convert to Time  │
├──────────────────────────┤
│                          │
│ recovery_start_time =    │
│   target_hour -          │
│   recovery_duration      │
│                          │
│ Example:                 │
│ • Target: 06:00          │
│ • Duration: 2.5 hours    │
│ • Start: 03:30           │
│                          │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ OUTPUT:                  │
│ sensor.*.recovery_start  │
│ time.*.recovery_start    │
│                          │
│ Used by automations to   │
│ trigger heating          │
└──────────────────────────┘
```

---

## Thermal Model

### Simplified Thermal Physics

```
COOLING PHASE (Evening to Night):
┌─────────────────────────────────────────┐
│  Temperature Drop Over Time             │
│                                         │
│  T°C │                                  │
│      │      ┌─ T_interior (snapshot)    │
│  22  │    ┌─┘                           │
│      │   /  Decay rate determined      │
│  21  │  /   by RCth                    │
│      │ /                               │
│  20  │/_______ Asymptote: T_exterior   │
│      │        (10°C)                   │
│  19  │                                  │
│   23:00    01:00    03:00    05:00      │
│                                         │
│  Formula: T(t) = T_ext +               │
│    (T_0 - T_ext) * e^(-t/RCth)        │
└─────────────────────────────────────────┘

RCth = thermal time constant (hours)
       = time to lose 63% of temp difference

Example: RCth = 3 hours
         After 3 hours: 63% cooled
         After 6 hours: 86% cooled
         After 9 hours: 95% cooled


HEATING PHASE (Recovery - Night to Morning):
┌─────────────────────────────────────────┐
│  Temperature Rise During Recovery       │
│                                         │
│  T°C │    ┌─ Asymptote: T_ext + RPth  │
│  22  │   / (Max achievable)            │
│      │  /  Rate determined by RPth     │
│  21  │ /                               │
│      │/_____ T_interior @ start        │
│  20  │      (after cooling)            │
│      │                                  │
│  19  │                                  │
│   03:00   04:00   05:00   06:00         │
│                                         │
│  Formula: T(t) = T_ext + RPth -        │
│    (T_ext + RPth - T_0) * e^(-t/RCth)  │
└─────────────────────────────────────────┘

RPth = thermal power constant (°C)
       = max temperature gain vs outdoor
```

---

## Calibration Process

### Auto-Calibration Feedback Loop

```
┌─────────────────────────────────────────────────────────────┐
│            DAILY CALIBRATION CYCLE                          │
└─────────────────────────────────────────────────────────────┘

DAY N:
  Evening (23:00)
    │
    ├─ Use predicted RCth from previous days
    │  (or defaults if first run)
    │
    ├─ Calculate expected recovery start time
    │
    └─ Store: T_calc, T_ext_calc

    ▼

  Night (Cooling observed)
    │
    ├─ Track temperature drop
    │
    ├─ When recovery start reached (03:00)
    │
    └─ Store: T_start, T_ext_start

    ▼

  Morning (06:00)
    │
    ├─ Store: T_end, T_ext_end
    │
    ├─ CALCULATE ACTUAL RCth:
    │  RCth_observed = ΔT / ln(ratio)
    │
    ├─ COMPARE with predicted:
    │  Error = RCth_observed - RCth_predicted
    │
    └─ DISTRIBUTE to low/high wind coefficients

    ▼

  ┌──────────────────────────────┐
  │ WIND-BASED DISTRIBUTION      │
  ├──────────────────────────────┤
  │                              │
  │ wind_avg_night = ?           │
  │                              │
  │ If wind_avg ≤ 35 km/h:      │
  │   Update RCth_lw ← error     │
  │   Weight: 100%               │
  │   Weight RCth_hw: 0%         │
  │                              │
  │ If wind_avg ≥ 35 km/h:      │
  │   Update RCth_hw ← error     │
  │   Weight: 100%               │
  │   Weight RCth_lw: 0%         │
  │                              │
  │ Else (between):              │
  │   Distribute proportionally   │
  │   between lw and hw           │
  │                              │
  └──────────────────────────────┘
    │
    ▼

  ┌──────────────────────────────┐
  │ EXPONENTIAL SMOOTHING        │
  ├──────────────────────────────┤
  │                              │
  │ coeff_new = (                │
  │   coeff_old * relaxation +   │
  │   coeff_measured             │
  │ ) / (relaxation + 1)         │
  │                              │
  │ Default relaxation = 2.0     │
  │                              │
  │ Effect:                      │
  │ • New measurement: 33%       │
  │ • Old knowledge: 67%         │
  │ • Prevents overfitting       │
  │                              │
  └──────────────────────────────┘
    │
    ▼

  ┌──────────────────────────────┐
  │ STORE UPDATED COEFFICIENTS   │
  ├──────────────────────────────┤
  │                              │
  │ Save to persistent store:    │
  │ • RCth_lw (updated)          │
  │ • RCth_hw (updated)          │
  │ • RPth_lw (if applicable)    │
  │ • RPth_hw (if applicable)    │
  │                              │
  │ Survives HA restart          │
  │                              │
  └──────────────────────────────┘
    │
    ▼

DAY N+1:
  │
  ├─ Use NEW coefficients
  │  (more accurate)
  │
  ├─ Prediction improves
  │
  └─ Loop repeats...
```

### Calibration Quality Timeline

```
First 3 Days (Learning Phase):
  Day 1: Predictions rough (±30 min error)
  Day 2: Improving (±20 min error)
  Day 3: Better (±15 min error)

After 1 Week:
  Stable predictions (±10 min error)
  Coefficients converging

After 1 Month:
  Highly accurate (±5 min error)
  System adapted to your home
  Seasonal variations captured

Seasonal Changes (Summer/Winter):
  RCth increases (less insulation impact)
  RPth decreases (outdoor closer to indoor)
  System auto-adapts over weeks
```

---

**See Also:**

- [Technical Reference](TECHNICAL_REFERENCE.md) - Detailed specifications
- [Getting Started](GETTING_STARTED.md) - Setup guide
- [Support](SUPPORT.md) - Troubleshooting
