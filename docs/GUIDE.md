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

- Home Assistant 2024.1 or newer
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

| Entity                          | Description                                      |
| ------------------------------- | ------------------------------------------------ |
| `sensor.*_interior_temperature` | Current room temperature                         |
| `sensor.*_exterior_temperature` | Outside temperature (from weather)               |
| `sensor.*_wind_speed`           | Current wind speed                               |
| `sensor.*_windchill`            | Perceived temperature (wind chill)               |
| `sensor.*_rcth`                 | Cooling coefficient (interpolated, with details) |
| `sensor.*_rpth`                 | Heating coefficient (interpolated, with details) |
| `sensor.*_time_to_recovery`     | Time remaining before heating starts (hours)     |
| `sensor.*_state`                | Current state machine status                     |

### Timestamp Sensors (For Automations)

These sensors have `device_class: timestamp` and can be used as automation triggers with `platform: time`:

| Entity                             | Description                          |
| ---------------------------------- | ------------------------------------ |
| `sensor.*_heure_de_relance`        | When heating should start (datetime) |
| `sensor.*_heure_cible_timestamp`   | Target/wake-up time as datetime      |
| `sensor.*_heure_coupure_timestamp` | Heating stop time as datetime        |

**Example automation trigger:**

```yaml
automation:
  trigger:
    - platform: time
      at: sensor.smarthrt_chambre_heure_de_relance
  action:
    - service: switch.turn_on
      target:
        entity_id: switch.heating
```

### Time Entities (User-configurable)

These entities allow users to modify schedule settings via the UI:

| Entity                           | Description                                   |
| -------------------------------- | --------------------------------------------- |
| `time.*_heure_cible`             | Set your wake-up/target time                  |
| `time.*_heure_coupure_chauffage` | Set evening heating stop time                 |
| `time.*_heure_de_relance`        | Calculated recovery start (read-only display) |

### Number Entities (Adjustable parameters)

| Entity                           | Description                          |
| -------------------------------- | ------------------------------------ |
| `number.*_consigne`              | Target temperature setpoint (°C)     |
| `number.*_rcth`                  | Cooling constant - manual adjustment |
| `number.*_rpth`                  | Heating constant - manual adjustment |
| `number.*_rcth_vent_faible`      | Cooling constant for low wind        |
| `number.*_rcth_vent_fort`        | Cooling constant for high wind       |
| `number.*_rpth_vent_faible`      | Heating constant for low wind        |
| `number.*_rpth_vent_fort`        | Heating constant for high wind       |
| `number.*_facteur_de_relaxation` | Learning rate factor                 |

### Switches (Mode controls)

| Entity                    | Description                  |
| ------------------------- | ---------------------------- |
| `switch.*_smart_heating`  | Enable/disable smart heating |
| `switch.*_mode_adaptatif` | Enable/disable auto-learning |

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

**Solution:** Manual adjustment via `number.*_rc_thermal` or `number.*_rp_thermal` sensors

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
A: Yes, use `number.*_rc_thermal` and `number.*_rp_thermal` to fine-tune.

**Q: Does it need internet?**  
A: Only for weather data (wind/temperature forecasts). Works fine with local-only weather.

## Getting Help

- **GitHub Issues:** [Report bugs](https://github.com/corentinBarban/SmartHRT/issues)
- **GitHub Discussions:** [Ask questions](https://github.com/corentinBarban/SmartHRT/discussions)
- **Home Assistant Community:** [Forum](https://community.home-assistant.io/)

---

**Version:** Latest  
**Last Updated:** January 2026
