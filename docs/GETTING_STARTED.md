# 🚀 Getting Started

**Installation, configuration and first steps with SmartHRT**

## Installation

### Step 1: Add via HACS

1. Open **HACS** in Home Assistant
2. Go to **Integrations** → **⋯** (menu) → **Custom repositories**
3. Add: `https://github.com/corentinBarban/SmartHRT`
4. Category: **Integration**
5. Search for **SmartHRT** and click **Install**

### Step 2: Add Integration

1. Go to **Settings** → **Devices & Services**
2. Click **Create automation** (bottom right)
3. Search for **SmartHRT**
4. Click **Create**

## Configuration

You'll be guided through two steps:

### Step 1: Name Your Instance

Enter a descriptive name (e.g., "Living Room", "Bedroom"):

```
Name: Living Room
```

### Step 2: Configure Sensors

| Field                    | Example                          | Notes                              |
| ------------------------ | -------------------------------- | ---------------------------------- |
| **Target hour**          | 06:00                            | When you wake up (recovery end)    |
| **Heating stop hour**    | 23:00                            | When you stop heating (evening)    |
| **Interior temp sensor** | `sensor.living_room_temperature` | Your room's thermometer            |
| **Weather source**       | `weather.home`                   | For temperature and wind forecasts |
| **Target temperature**   | 20.0                             | Desired room temperature (°C)      |

> 💡 **Tip**: Find sensor names by going to **Developer Tools** → **States**

## First Run

After adding the integration, SmartHRT will:

1. **Evening (at heating stop hour)**: Record room snapshot
2. **Night**: Track temperature decay
3. **Morning (calculated time)**: Auto-calibrate thermal constants
4. **Wake-up time**: Record final temperatures

**First cycle calibration is rough.** The system learns and improves over several days.

## Enable Automations

SmartHRT provides **services** and **sensors** for automations. Create these to make it work:

### Automation 1: Stop Heating

```yaml
automation:
  - alias: "SmartHRT - Stop Heating Evening"
    trigger:
      platform: time
      at: time.living_room_recoverycalc_hour
    action:
      - service: climate.turn_off
        target:
          entity_id: climate.living_room
      - service: smarthrt.on_heating_stop
        data: {}
```

### Automation 2: Start Heating

```yaml
automation:
  - alias: "SmartHRT - Start Heating Recovery"
    trigger:
      platform: template
      value_template: "{{ states('sensor.living_room_recovery_start_timestamp') }}"
    action:
      - service: climate.set_temperature
        target:
          entity_id: climate.living_room
        data:
          temperature: "{{ states('number.living_room_setpoint') | float(20) }}"
      - service: smarthrt.on_recovery_start
        data: {}
```

### Automation 3: Recovery End

```yaml
automation:
  - alias: "SmartHRT - Recovery End (morning)"
    trigger:
      platform: time
      at: time.living_room_target_hour
    action:
      - service: smarthrt.on_recovery_end
        data: {}
```

## Dashboard Card

Add a visual card to your dashboard:

### Using Lovelace YAML

```yaml
type: entities
title: SmartHRT - Living Room
entities:
  - entity: sensor.living_room_interior_temp
    name: "Indoor Temp"
  - entity: sensor.living_room_exterior_temp
    name: "Outdoor Temp"
  - entity: sensor.living_room_recovery_start
    name: "Next Start Time"
  - entity: sensor.living_room_rcth
    name: "Thermal Constant (RCth)"
  - entity: sensor.living_room_rpth
    name: "Power Constant (RPth)"
  - entity: number.living_room_setpoint
    name: "Target Temp"
  - entity: switch.living_room_smartheating_mode
    name: "Smart Heating"
  - entity: switch.living_room_adaptive_mode
    name: "Auto-Calibration"
```

### Using Entity Card

```yaml
type: custom:stack-in-card
cards:
  - type: custom:auto-entities
    card:
      type: glance
      title: "SmartHRT Status"
    filter:
      include:
        - domain: sensor
          entity_id: "sensor.living_room_*"
```

## Advanced Configuration

SmartHRT supports full configuration via the Home Assistant UI:

**Settings → Devices & Services → SmartHRT → Options**

All parameters can be modified after installation.

### Available Options

#### Time-Based Settings

- **Target hour**: Wake-up time or desired end of recovery (e.g., 06:00)
- **Heating stop hour**: When heating stops in evening (e.g., 23:00)

#### Sensor Selection

- **Interior temperature sensor**: Your room's thermometer
- **Weather source**: For outdoor temp & wind forecasts

#### Thermal Settings

- **Set Point (TSP)**: Target temperature (13-26°C)

## Number Entities (Tuning)

After installation, you can adjust these `number.*` entities:

| Entity                | Default | Range    | Purpose                |
| --------------------- | ------- | -------- | ---------------------- |
| `number.*_setpoint`   | 20.0    | 13-26°C  | Target temperature     |
| `number.*_rcth`       | 3.0     | 0.1-10.0 | Thermal time constant  |
| `number.*_rpth`       | 2.0     | 0.1-10.0 | Thermal power constant |
| `number.*_rcth_lw`    | 3.0     | 0.1-10.0 | RCth (low wind)        |
| `number.*_rcth_hw`    | 3.0     | 0.1-10.0 | RCth (high wind)       |
| `number.*_rpth_lw`    | 2.0     | 0.1-10.0 | RPth (low wind)        |
| `number.*_rpth_hw`    | 2.0     | 0.1-10.0 | RPth (high wind)       |
| `number.*_relaxation` | 2.0     | 0.1-10.0 | Calibration smoothing  |

## Modes & Switches

### Smart Heating Mode

`switch.*_smartheating_mode` - Enable/disable all calculations

- **ON** (default): SmartHRT actively manages heating
- **OFF**: All calculations suspended (useful for holidays)

### Adaptive Mode

`switch.*_adaptive_mode` - Enable/disable auto-calibration

- **ON** (default): System learns & adjusts coefficients
- **OFF**: Freeze current coefficients (manual tuning mode)

## Multiple Rooms

You can run SmartHRT for multiple rooms simultaneously:

1. Add the integration multiple times
2. Each instance gets its own sensors/numbers
3. Each learns independently

## Manual Coefficient Tuning

If automatic calibration doesn't work well:

1. Disable `switch.*_adaptive_mode`
2. Manually adjust `number.*_rcth` and `number.*_rpth`
3. Monitor `sensor.*_recovery_start` predictions
4. Fine-tune until predictions are accurate

## Common Questions

### The recovery time seems wrong

**Answer**: First 2-3 cycles are rough. System needs to learn your home's thermal characteristics. After a week, accuracy improves significantly.

### Heating starts too early/late

**Answer**: Adjust these `number.*` entities:

- **Increase `rcth`** if room cools slower than predicted
- **Decrease `rcth`** if room cools faster
- Disable `switch.*_adaptive_mode` to freeze calibration

### Predictions wrong on very windy days

**Answer**: SmartHRT uses wind forecasts to adjust calculations. If forecasts are inaccurate, predictions suffer. Once wind stabilizes, predictions improve.

### I want multiple rooms

**Answer**: Just add the integration multiple times! Each instance:

- Has its own sensors/numbers
- Learns independently
- Requires separate automations

---

**Next Steps:**

- 🔧 [Dépannage](TROUBLESHOOTING.md)
- 👨‍💻 [API & Exemples](API_AND_EXAMPLES.md)
- 🏗️ [Architecture technique](TECHNICAL_REFERENCE.md)
