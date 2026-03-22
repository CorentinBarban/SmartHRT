# SmartHRT User Guide

**Installation, configuration, and everyday use**

## What is SmartHRT?

SmartHRT automatically calculates the optimal time to start your heating in the morning to reach your desired temperature exactly at wake-up time. The system continuously learns your home's thermal characteristics to improve accuracy over time.

**Key features:**

- Automatic heating startup calculation
- Learns from your home's thermal behavior
- Adapts to weather and wind conditions
- Simple web-based configuration
- No coding required

## Installation

### Option 1: HACS (Recommended)

1. Open **HACS** in Home Assistant
2. Go to **Integrations** → **⋯** (menu) → **Custom repositories**
3. Add: `https://github.com/corentinBarban/SmartHRT`
4. Select category: **Integration**
5. Search for **SmartHRT** and click **Install**
6. Restart Home Assistant

### Option 2: Manual Installation

1. Download the latest release from [GitHub](https://github.com/corentinBarban/SmartHRT/releases)
2. Extract to: `config/custom_components/SmartHRT/`
3. Restart Home Assistant

### Requirements

- Home Assistant 2026.2.0 or newer
- A weather entity (e.g., `weather.home`)
- A temperature sensor for your room

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **Create automation** (bottom right) or **+ Create Integration**
3. Search for and select **SmartHRT**
4. Fill in the configuration:

| Field                           | Example                        | Description                                 |
| ------------------------------- | ------------------------------ | ------------------------------------------- |
| **Name**                        | Living Room                    | Name for this heating zone                  |
| **Target Hour**                 | 06:00                          | When you want to wake up (desired end time) |
| **Heating Stop Hour**           | 23:00                          | When to turn off heating (evening)          |
| **Interior Temperature Sensor** | sensor.living_room_temperature | Your room's thermometer                     |
| **Weather Entity**              | weather.home                   | For temperature and wind data               |
| **Target Temperature**          | 20                             | Desired room temperature (°C)               |

> **Tip:** Find sensor names in **Developer Tools** → **States**

## How It Works

### Daily Cycle

```
Evening (23:00)              Night              Morning (calculated)         Wake-up (06:00)
    |                          |                        |                         |
    ▼                          ▼                        ▼                         ▼
Stop Heating          Temperature drops          Start Heating            Reach target temp
Record baseline       Track decay pattern        Auto-calculated time     Fine-tune learning
```

### First Week

The system is rough at first but improves quickly:

- **Day 1-2:** Learning baseline (expect ±30 min accuracy)
- **Day 3-5:** Improving accuracy (±15 min)
- **Day 6+:** Optimized (±5-10 min with stable conditions)

Accuracy improves faster with:

- Consistent wake-up times
- Stable weather
- Regular heating cycles

## Available Sensors & Controls

### Sensors (Read-only)

> Entity IDs use the pattern `{platform}.{instance}_{entity_slug}` where `*` represents your instance name. Slugs shown are for English HA — they may differ in other languages.

| Entity                               | Description                                      |
| ------------------------------------ | ------------------------------------------------ |
| `sensor.*_interior_temperature`      | Current room temperature                         |
| `sensor.*_exterior_temperature`      | Outside temperature (from weather)               |
| `sensor.*_wind_speed`                | Current wind speed                               |
| `sensor.*_wind_chill_temperature`    | Perceived temperature (wind chill)               |
| `sensor.*_temperature_forecast`      | Outside temperature forecast                     |
| `sensor.*_wind_forecast`             | Wind speed forecast                              |
| `sensor.*_average_wind_4h`           | 4h average wind speed (used in calculations)     |
| `sensor.*_rcth`                      | Cooling coefficient (interpolated, with details) |
| `sensor.*_rpth`                      | Heating coefficient (interpolated, with details) |
| `sensor.*_dynamic_rcth`              | Fast/dynamic RCth (short-term estimate)          |
| `sensor.*_time_to_recovery`          | Time remaining before heating starts (hours)     |
| `sensor.*_machine_state`             | Current state machine status                     |
| `sensor.*_night_state`               | Night monitoring state                           |
| `sensor.*_recovery_calculation_mode` | Whether recovery calculation is active           |
| `sensor.*_rp_calculation_mode`       | Whether RP calculation is active                 |
| `sensor.*_stop_lag_duration`         | Measured temperature lag after heating stops     |

### Timestamp Sensors (For Automations)

These sensors have `device_class: timestamp` and can be used as automation triggers with `platform: time`:

| Entity                         | Description                          |
| ------------------------------ | ------------------------------------ |
| `sensor.*_recovery_start_time` | When heating should start (datetime) |
| `sensor.*_target_hour`         | Target/wake-up time as datetime      |
| `sensor.*_heating_stop_hour`   | Heating stop time as datetime        |

> **Note:** The automation example below uses French entity IDs (`sensor.smarthrt_heure_de_relance`, etc.) as it was written for a French-language HA installation. In English HA the entity IDs follow the slugs in the table above.

**Example automation trigger:**
description: Gère les cycles SmartHRT avec un horaire spécifique pour le week-end (10h-21h)
triggers:

- at: sensor.smarthrt_heure_de_relance
  id: start_heating
  trigger: time
- at: sensor.smarthrt_heure_coupure_timestamp
  id: fin_cycle
  trigger: time
  actions:
- choose: - conditions: - condition: trigger
  id: start_heating
  sequence: - action: climate.turn_on
  target:
  entity_id: climate.<YOUR_ENTITY>
  data: {} - conditions: - condition: trigger
  id: fin_cycle
  sequence: - delay:
  seconds: 10 - if: - condition: time
  before: "12:00:00"
  then: - target:
  entity_id: time.smarthrt_heure_cible
  data:
  time: "{{ soir_cible }}"
  action: time.set_value - target:
  entity_id: time.smarthrt_heure_coupure_chauffage
  data:
  time: "{{ soir_fin }}"
  action: time.set_value
  else: - if: - condition: template
  value_template: "{{ (now() + timedelta(days=1)).weekday() in [5, 6] }}"
  then: - target:
  entity_id: time.smarthrt_heure_cible
  data:
  time: "{{ matin_cible_we }}"
  action: time.set_value - target:
  entity_id: time.smarthrt_heure_coupure_chauffage
  data:
  time: "{{ soir_fin }}"
  action: time.set_value
  else: - target:
  entity_id: time.smarthrt_heure_cible
  data:
  time: "{{ matin_cible }}"
  action: time.set_value - target:
  entity_id: time.smarthrt_heure_coupure_chauffage
  data:
  time: "{{ matin_fin }}"
  action: time.set_value - action: climate.turn_off
  target:
  entity_id: climate.climate.<YOUR_ENTITY>
  data: {}
  variables:
  matin_cible: "07:00:00"
  matin_cible_we: "10:00:00"
  matin_fin: "08:00:00"
  soir_cible: "17:30:00"
  soir_fin: "21:00:00"

````

### Time Entities (User-configurable)

These entities allow users to modify schedule settings via the UI:

| Entity                          | Description                                   |
| ------------------------------- | --------------------------------------------- |
| `time.*_target_hour`            | Set your wake-up/target time                  |
| `time.*_heating_stop_hour`      | Set evening heating stop time                 |
| `time.*_recovery_start_time`    | Calculated recovery start (read-only display) |

### Number Entities (Adjustable parameters)

| Entity                      | Description                          |
| --------------------------- | ------------------------------------ |
| `number.*_set_point`        | Target temperature setpoint (°C)     |
| `number.*_rcth`             | Cooling constant - manual adjustment |
| `number.*_rpth`             | Heating constant - manual adjustment |
| `number.*_rcth_low_wind`    | Cooling constant for low wind        |
| `number.*_rcth_high_wind`   | Cooling constant for high wind       |
| `number.*_rpth_low_wind`    | Heating constant for low wind        |
| `number.*_rpth_high_wind`   | Heating constant for high wind       |
| `number.*_relaxation_factor`| Learning rate factor                 |

### Switches (Mode controls)

| Entity                       | Description                  |
| ---------------------------- | ---------------------------- |
| `switch.*_smart_heating_mode`| Enable/disable smart heating |
| `switch.*_adaptive_mode`     | Enable/disable auto-learning |

> **Note:** The `*` represents your instance name (e.g., `chambre`, `salon`).

## Troubleshooting

### "Integration not showing in Add Integration"

**Solution:**

1. Restart Home Assistant: **Developer Tools** → **System Controls** → **Restart**
2. Go to **HACS** → **Integrations**, click ⋯ → **Clear cache**
3. Try adding again

### "No temperature change detected"

**Possible causes:**

- Heating element not connected/working
- Sensor not updating properly
- Room has too much ventilation/windows open

**Solution:** Check that your heating is actually running and sensors update in **Developer Tools** → **States**

### "Calculated recovery time seems wrong"

**Possible causes:**

- System still learning (normal first few days)
- Weather has changed dramatically
- Heating setup different than usual

**Solution:** Manual adjustment via `number.*_rcth` or `number.*_rpth` entities

### "Getting repeated errors in logs"

**Solution:**

1. Check **Settings** → **System** → **Logs** for SmartHRT errors
2. Verify all sensor entities exist and are valid
3. Check weather entity is properly configured
4. Restart Home Assistant

## FAQ

**Q: How long until it learns my home?**
A: Typically 3-7 days with consistent daily cycles. Improvement happens faster with stable routines.

**Q: Can I use it with multiple rooms?**
A: Yes, add multiple instances (one per room) in configuration.

**Q: Does it work in summer?**
A: The integration is designed for heating. In summer, disable it or turn off learning mode.

**Q: What if my wake-up time changes?**
A: Update the target hour in the `time.*_target_hour` entity. It will recalculate.

**Q: Can I manually adjust the calculation?**
A: Yes, use `number.*_rcth` and `number.*_rpth` to fine-tune.

**Q: Does it need internet?**
A: Only for weather data (wind/temperature forecasts). Works fine with local-only weather.

## 🎨 Custom Lovelace Card

SmartHRT includes a ready-to-use custom card (`smarthrt-card.js`) to display the heating state on your dashboard.

### Installation

1. Copy `smarthrt-card.js` from the repository root to your `/config/www/` folder
2. In Home Assistant, go to **Settings** ⚙️ → **Dashboards** → **⁝** (top right) → **Resources**
3. Click **Add Resource** and fill in:
   - **URL**: `/local/smarthrt-card.js`
   - **Type**: JavaScript Module
4. Click **Create**, then reload the page

### Usage

Add the card to any dashboard:

```yaml
type: custom:smarthrt-card
prefix: salon # required — your SmartHRT instance name (e.g. chambre, salon)
name: Salon # optional — display name
min_temp: 13 # optional — gauge minimum (default: 13)
max_temp: 26 # optional — gauge maximum (default: 26)
````

The card displays:

- Current interior temperature with color scale
- Target setpoint
- Current machine state (INIT / ON / LAG / MONITORING / BOOST)
- Time remaining before heating starts
- Relay and target times

---

## Getting Help

- **GitHub Issues:** [Report bugs](https://github.com/corentinBarban/SmartHRT/issues)
- **GitHub Discussions:** [Ask questions](https://github.com/corentinBarban/SmartHRT/discussions)
- **Home Assistant Community:** [Forum](https://community.home-assistant.io/)

---

**Version:** Latest  
**Last Updated:** March 2026
