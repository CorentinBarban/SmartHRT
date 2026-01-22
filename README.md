# SmartHRT

**Smart Heating Recovery Time** - Native Home Assistant integration for intelligent heating start time calculation.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/corentinBarban/smartHRT?include_prereleases)](https://github.com/corentinBarban/SmartHRT/releases)

🇫🇷 [Version française](README_fr.md)

---
> [!NOTE]
> **This repository is a fork of the original [SmartHRT](https://github.com/ebozonne/smarthrt) project.**
> It converts the original YAML package into a fully native **Home Assistant Integration (Custom Component)** written in Python.
>


## 📋 Table of Contents

1. [Overview](#-overview)
2. [How It Works](#-how-it-works)
3. [Thermal Model](#-thermal-model)
4. [Installation](#-installation)
5. [Configuration](#-configuration)
6. [Created Entities](#-created-entities)
7. [Available Services](#-available-services)
8. [Automatic Lifecycle](#-automatic-lifecycle)
9. [Auto-calibration](#-auto-calibration)
10. [Automation Examples](#-automation-examples)
11. [Technical Architecture](#-technical-architecture)
12. [FAQ](#-faq)

---

## 🎯 Overview

> **Problem**: The thermal mass of radiators and walls provides good thermal comfort but makes it difficult to predict heating recovery time in the morning. Without correctly predicting when to start heating at night, it's either too late (and too cold) or too early (heating the living room unnecessarily while sleeping).

**SmartHRT** solves this problem by automatically calculating the optimal heating restart time (`recovery_start_hour`) to reach the target temperature (`tsp`) at the desired time (`target_hour`).

<img src="./img/SmartHeatingRecoveryTime_principle.png" alt="SmartHRT Principle" style="width:75%; height:auto;">

### Benefits

- ✅ **Energy savings**: Heating only starts when necessary
- ✅ **Optimal comfort**: Target temperature is reached at wake-up time
- ✅ **Self-learning**: Parameters automatically adjust to your home
- ✅ **Weather forecasts**: Uses temperature and wind forecasts
- ✅ **Alarm sync**: Synchronizes with your smartphone alarm

---

## 🔄 How It Works

The system operates on an automatic daily cycle:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SmartHRT DAILY CYCLE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  23:00 (recoverycalc_hour)     03:00 (calculated)      06:00 (target_hour)  │
│         │                            │                        │             │
│         ▼                            ▼                        ▼             │
│    ┌─────────┐                 ┌─────────┐               ┌─────────┐        │
│    │ PHASE 1 │ ──────────────▶ │ PHASE 2 │ ────────────▶ │ PHASE 3 │       │
│    │ HEATING │   Cooling down  │RECOVERY │   Heating up  │RECOVERY │        │
│    │  STOP   │                 │  START  │               │   END   │        │
│    └─────────┘                 └─────────┘               └─────────┘        │
│         │                            │                        │             │
│    • Snapshot Tint/Text        • Calculate actual RCth   • Calculate RPth   │
│    • Temp lag detection        • Start heating           • Update           │
│    • Calculate recovery_time   • rp_calc mode = ON         coefficients     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📐 Thermal Model

SmartHRT uses a first-order thermal model with two key parameters:

### Thermal Constants

| Parameter | Name                        | Description                                                             |
| --------- | --------------------------- | ----------------------------------------------------------------------- |
| **RCth**  | Thermal Time Constant (h)   | Combines insulation and thermal mass. Determines cooling rate.          |
| **RPth**  | Thermal Power Constant (°C) | Combines insulation and heating power. Max temperature gain vs outdoor. |

### Calculation Formula

The recovery start time is calculated using the inverted Newton's law of cooling:

$$
\text{recoveryDuration} = RC_{th} \cdot \ln \left( \frac{RP_{th} + T_{ext} - T_{int}^{start}}{RP_{th} + T_{ext} - T_{sp}} \right)
$$

### Wind Interpolation

RCth and RPth coefficients vary linearly with wind speed:

- **Low wind** (10 km/h): Uses `rcth_lw` / `rpth_lw`
- **High wind** (60 km/h): Uses `rcth_hw` / `rpth_hw`

This interpolation accounts for increased heat losses in windy conditions.

---

## 📦 Installation

### Prerequisites

- Home Assistant 2024.1 or higher
- HACS (recommended)
- A weather entity (weather.\*) configured for forecasts

### Option 1: HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the 3 dots → "Custom repositories"
4. Add `https://github.com/corentinBarban/SmartHRT` with category "Integration"
5. Search for "SmartHRT" and install
6. Restart Home Assistant
7. Go to Settings → Devices & Services → Add Integration → SmartHRT

### Option 2: Manual Installation

1. Download the `custom_components/SmartHRT` folder
2. Copy it to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant
4. Add the integration via the UI

---

## ⚙️ Configuration

### Required Parameters

| Parameter                       | Description                    | Example                 |
| ------------------------------- | ------------------------------ | ----------------------- |
| **name**                        | Instance name                  | "Living Room"           |
| **target_hour**                 | Recovery end time (wake-up)    | 06:00                   |
| **recoverycalc_hour**           | Heating stop time (evening)    | 23:00                   |
| **sensor_interior_temperature** | Interior temperature sensor    | sensor.living_room_temp |
| **tsp**                         | Target temperature (set point) | 20.0                    |

### Optional Parameters

| Parameter                | Description             | Example                 |
| ------------------------ | ----------------------- | ----------------------- |
| **phone_alarm_selector** | Smartphone alarm sensor | sensor.phone_next_alarm |

---

## 📊 Created Entities

### Sensors

| Entity                         | Description                     |
| ------------------------------ | ------------------------------- |
| `sensor.<name>_interior_temp`  | Interior temperature            |
| `sensor.<name>_exterior_temp`  | Exterior temperature            |
| `sensor.<name>_wind_speed`     | Wind speed (m/s)                |
| `sensor.<name>_windchill`      | Wind chill temperature          |
| `sensor.<name>_recovery_start` | Calculated recovery start time  |
| `sensor.<name>_rcth_sensor`    | RCth coefficient                |
| `sensor.<name>_rpth_sensor`    | RPth coefficient                |
| `sensor.<name>_rcth_fast`      | Dynamic RCth (night tracking)   |
| `sensor.<name>_wind_forecast`  | 3h average wind forecast        |
| `sensor.<name>_temp_forecast`  | 3h average temperature forecast |
| `sensor.<name>_phone_alarm`    | Next phone alarm                |

### Numbers (adjustable)

| Entity                     | Description          |
| -------------------------- | -------------------- |
| `number.<name>_setpoint`   | Temperature setpoint |
| `number.<name>_rcth`       | RCth coefficient     |
| `number.<name>_rpth`       | RPth coefficient     |
| `number.<name>_rcth_lw`    | RCth low wind        |
| `number.<name>_rcth_hw`    | RCth high wind       |
| `number.<name>_rpth_lw`    | RPth low wind        |
| `number.<name>_rpth_hw`    | RPth high wind       |
| `number.<name>_relaxation` | Relaxation factor    |

### Switches

| Entity                            | Description                     |
| --------------------------------- | ------------------------------- |
| `switch.<name>_smartheating_mode` | Enable/disable smart heating    |
| `switch.<name>_adaptive_mode`     | Enable/disable auto-calibration |

### Time

| Entity                           | Description               |
| -------------------------------- | ------------------------- |
| `time.<name>_target_hour`        | Target hour (wake-up)     |
| `time.<name>_recoverycalc_hour`  | Heating stop hour         |
| `time.<name>_recoverystart_hour` | Calculated recovery start |

---

## 🔧 Available Services

| Service                                   | Description                     |
| ----------------------------------------- | ------------------------------- |
| `smarthrt.calculate_recovery_time`        | Calculate recovery start time   |
| `smarthrt.calculate_recovery_update_time` | Calculate next update time      |
| `smarthrt.calculate_rcth_fast`            | Calculate dynamic RCth          |
| `smarthrt.on_heating_stop`                | Trigger heating stop (snapshot) |
| `smarthrt.on_recovery_start`              | Trigger recovery start          |
| `smarthrt.on_recovery_end`                | Trigger recovery end            |

### Optional Parameter

All services accept an optional `entry_id` parameter to target a specific instance.

---

## 🔁 Automatic Lifecycle

SmartHRT automatically manages time-based triggers:

### Phase 1: Heating Stop (`recoverycalc_hour`)

At the configured time (e.g., 23:00):

1. Initializes coefficients to 50 if first run
2. Records a snapshot (Tint, Text, timestamp)
3. Activates temperature lag detection
4. Calculates expected recovery start time

### Phase 2: Recovery Start (`recovery_start_hour`)

At the calculated time (e.g., 03:00):

1. Records current temperatures
2. Calculates actual RCth observed overnight
3. Updates `rcth_lw` and `rcth_hw` coefficients
4. Activates RPth calculation mode

### Phase 3: Recovery End (`target_hour` or setpoint reached)

When setpoint is reached or at target time:

1. Records final temperatures
2. Calculates actual observed RPth
3. Updates `rpth_lw` and `rpth_hw` coefficients

---

## 📈 Auto-calibration

Auto-calibration uses **exponential relaxation** with a cubic polynomial to distribute the error:

1. After each cycle, measured RCth/RPth are compared to interpolated values
2. Error is distributed to low/high wind coefficients based on overnight average wind
3. Coefficients are smoothed with the `relaxation_factor` (default: 2.0)

**Update formula**:

$$
coef_{new} = \frac{coef_{old} + relaxation \times coef_{calculated}}{1 + relaxation}
$$

> 💡 The first few days may not be accurate. Auto-calibration improves progressively.

---

## 🤖 Automation Examples

### Start heating at recovery time

```yaml
automation:
  - alias: "SmartHRT - Start heating"
    trigger:
      - platform: time
        at: sensor.smarthrt_recovery_start
    condition:
      - condition: state
        entity_id: switch.smarthrt_smartheating_mode
        state: "on"
    action:
      - service: climate.set_temperature
        target:
          entity_id: climate.living_room
        data:
          temperature: "{{ states('number.smarthrt_setpoint') | float }}"
```

### Stop heating in the evening

```yaml
automation:
  - alias: "SmartHRT - Stop heating evening"
    trigger:
      - platform: time
        at: time.smarthrt_recoverycalc_hour
    action:
      - service: climate.turn_off
        target:
          entity_id: climate.living_room
```

---

## 🏗️ Technical Architecture

```
custom_components/SmartHRT/
├── __init__.py          # Integration entry point
├── coordinator.py       # Central coordinator with thermal logic
├── config_flow.py       # UI configuration interface
├── const.py             # Constants and default values
├── sensor.py            # Sensor entities (temperatures, coefficients)
├── switch.py            # Switch entities (modes)
├── number.py            # Number entities (setpoint, relaxation)
├── time.py              # Time entities (target hours)
├── services.yaml        # Service definitions
├── strings.json         # UI strings (English)
├── manifest.json        # Integration metadata
└── translations/
    ├── de.json          # German translations
    ├── es.json          # Spanish translations
    ├── fr.json          # French translations
    └── it.json          # Italian translations
```

### Main Classes

- **`SmartHRTCoordinator`**: Central coordinator managing all thermal calculations, listeners, and services
- **`SmartHRTData`**: Dataclass containing all state data (temperatures, coefficients, timestamps, modes)

---

## ❓ FAQ

### How to sync with my phone alarm?

Configure the `phone_alarm_selector` parameter with your phone's sensor (e.g., `sensor.phone_next_alarm`). The target hour will be automatically updated.

### What to do during holidays?

Disable the `Smart Heating Mode` switch to suspend calculations.

### Predictions aren't accurate the first few days?

That's normal! Auto-calibration needs a few cycles to adapt to your home. Coefficients improve progressively.

### How to manually adjust coefficients?

Disable `Adaptive Mode` and modify the `number.*_rcth` and `number.*_rpth` entities directly.

---

## 📝 Changelog

### January 2026 - Native Integration

- **NEW**: Complete rewrite as native Home Assistant integration (HACS compatible)
- **NEW**: UI configuration (no more YAML required)
- **NEW**: Home Assistant services for automation
- **NEW**: Automatic time triggers (recoverycalc_hour, target_hour, recovery_start)
- **NEW**: Integrated weather forecasts (temperature and wind over 3h)
- **NEW**: Temperature lag detection (radiator delay)
- **NEW**: 4h wind speed average for calibration
- **IMPROVED**: Centralized architecture with single coordinator

---

## 📄 License

This project is licensed under the GNU GENERAL PUBLIC LICENSE. See the [LICENCE](LICENCE) file for details.

