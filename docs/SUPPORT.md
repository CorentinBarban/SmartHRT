# 🔧 Support & FAQ

**Troubleshooting, frequently asked questions, and help**

## Table of Contents

1. [Setup Issues](#setup-issues)
2. [Sensor Issues](#sensor-issues)
3. [Calculation Issues](#calculation-issues)
4. [Calibration Issues](#calibration-issues)
5. [Automation Issues](#automation-issues)
6. [FAQ](#faq)
7. [Getting Help](#getting-help)

---

## Setup Issues

### "Integration not appearing in Add Integration"

**Problem**: SmartHRT doesn't show up in the integration list.

**Solution**:

1. **Restart Home Assistant**

   ```
   Developer Tools → System Controls → Restart Home Assistant
   ```

2. **Clear HACS cache**
   - Go to HACS → Integrations
   - Click ⋯ → Clear cache & reload repositories

3. **Verify installation**
   - Check: `config/custom_components/SmartHRT/__init__.py` exists
   - Restart HA

4. **Check logs**
   ```
   Settings → System → Logs → Find "SmartHRT" errors
   ```

### "Configuration fails with 'No valid selectors'"

**Problem**: Weather entity selector is empty.

**Solution**:

1. **Add weather integration first**
   - Settings → Devices & Services → Create
   - Search for "Weather" (OpenWeatherMap, Météo-France, etc.)
   - Add integration

2. **Wait 30 seconds** for entity discovery

3. **Try adding SmartHRT again**

### "Cannot find interior temperature sensor"

**Problem**: Sensor selector empty or sensor not selectable.

**Solution**:

1. **Verify sensor exists**
   - Developer Tools → States
   - Search for temperature sensors

2. **Check sensor provides numeric value**
   - Click sensor in States
   - Confirm `state` is a number (e.g., "20.5"), not "unknown"

3. **Add temperature sensor if missing**
   ```yaml
   template:
     - sensor:
         - name: "Room Temperature"
           unique_id: room_temp_template
           unit_of_measurement: "°C"
           state: "{{ state_attr('climate.room', 'current_temperature') }}"
   ```

---

## Sensor Issues

### Sensors not appearing in Home Assistant

**Problem**: After adding integration, no SmartHRT entities appear.

**Solution**:

1. **Check entity registry**
   - Developer Tools → States
   - Search for "living_room" (your instance name)
   - If found: UI is lagging. Refresh page (F5)
   - If not found: Restart Home Assistant

2. **Check for errors**

   ```
   Settings → System → Logs → Search "SmartHRT"
   ```

3. **Force entity discovery**
   ```
   Developer Tools → Services
   Service: homeassistant.reload_config_entry
   Data: entry_id = your_smarthrt_entry_id
   ```

### "sensor.\*\_recovery_start shows 'unknown'"

**Problem**: Sensor value is not calculated.

**Causes**:

- Interior temperature not available
- Weather data not available
- Recovery calculation disabled

**Solution**:

1. **Check prerequisites**
   - Interior temp sensor: Developer Tools → States (must be numeric)
   - Weather entity: Developer Tools → States (must exist)

2. **Manually trigger calculation**

   ```yaml
   service: smarthrt.calculate_recovery_time
   data:
     entry_id: "your_entry_id"
   ```

3. **Enable debug logs**
   ```yaml
   logger:
     logs:
       custom_components.SmartHRT: debug
   ```

---

## Calculation Issues

### "Recovery time seems wrong"

**Problem**: Heating starts too early or too late.

**Answer**: First 2-3 cycles are rough. System needs to learn your home's thermal characteristics. After a week, accuracy improves significantly.

**What you can do**:

1. **Wait for auto-calibration** (7-10 days of normal operation)
2. **Check weather forecasts** are accurate for your location
3. **Verify sensor readings** are correct

### "Recovery time stays constant (not updating)"

**Problem**: `sensor.*_recovery_start` doesn't change despite different conditions.

**Causes**:

- Weather data not updating
- Calculation disabled
- Temperature data stale

**Solution**:

1. **Check weather entity updates**
   - Developer Tools → States
   - Click weather entity and watch `last_updated` timestamp
   - Should update every 30-60 minutes

2. **Enable calculation mode**

   ```yaml
   service: switch.turn_on
   target:
     entity_id: switch.living_room_smartheating_mode
   ```

3. **Force manual recalculation**
   ```yaml
   service: smarthrt.calculate_recovery_time
   data: {}
   ```

### "Predictions wrong on very windy days"

**Problem**: Heating time inaccurate during high winds.

**Answer**: SmartHRT uses wind forecasts to adjust calculations. If forecasts are inaccurate, predictions suffer. Once wind stabilizes, predictions improve.

**Workaround**: Manually adjust `rcth_hw` (high wind RCth) during windy periods

---

## Calibration Issues

### "Coefficients not updating"

**Problem**: RCth and RPth values stay constant despite adaptive mode ON.

**Causes**:

- Adaptive mode disabled
- Temperature differences too small
- Calculation errors

**Solution**:

1. **Check adaptive mode**

   ```
   Developer Tools → States
   Check: switch.living_room_adaptive_mode = "on"
   ```

2. **Check temperature differences**
   - Should be ≥ 1°C between recovery phases
   - If < 1°C: Not enough data for calibration

3. **Enable debug logging**

   ```yaml
   logger:
     logs:
       custom_components.SmartHRT: debug
   ```

   - Look for "RCth calculation" or "RPth update" messages

### "I want to manually correct RCth and RPth"

**Solution**:

1. **Disable adaptive mode**

   ```yaml
   service: switch.turn_off
   target:
     entity_id: switch.living_room_adaptive_mode
   ```

2. **Manually edit values**
   - Developer Tools → States
   - Click `number.living_room_rcth` and `number.living_room_rpth`
   - Set desired values

3. **Test with manual calculation**

   ```yaml
   service: smarthrt.calculate_recovery_time
   data: {}
   ```

4. **Monitor predictions**
   - Check `sensor.living_room_recovery_start`
   - If better: lock values by keeping adaptive mode OFF
   - If worse: adjust again

---

## Automation Issues

### "Automations not triggering"

**Problem**: Evening heating stop or morning recovery start not happening.

**Solution**:

1. **Verify automations exist**

   ```
   Settings → Automations → Search "SmartHRT"
   ```

2. **Check automation is enabled**
   - Click automation
   - Verify toggle is ON

3. **Check trigger entities exist**
   - Use same entity ID as SmartHRT instance name
   - Example: `time.living_room_recoverycalc_hour`

4. **Test manually**

   ```yaml
   service: smarthrt.on_heating_stop
   data: {}
   ```

   - Check for errors in logs

### "Automation runs but nothing happens"

**Problem**: Automation triggers but no heating state change.

**Solution**:

1. **Check action target entities**
   - Verify `climate.living_room` exists and is available
   - Developer Tools → States

2. **Check entity permissions**
   - Climate entity must support `turn_off` and `set_temperature`

3. **Check for automation conditions**
   - May have conditions blocking execution
   - Review automation in YAML mode

4. **Test climate entity directly**
   ```yaml
   service: climate.turn_off
   target:
     entity_id: climate.living_room
   ```

---

## FAQ

### How to set phone alarm as target time?

**Answer**:

1. **Activate next alarm sensor** in Companion App
   - Settings → Companion App → Manage Sensors
   - Activate `sensor.yourphone_next_alarm`

2. **Copy sensor name** (e.g., `sensor.clt_l29_next_alarm`)

3. **Add to SmartHRT** during configuration
   - Set "Phone alarm sensor" to this entity
   - SmartHRT will auto-sync target hour to next alarm

4. **Alternative**: Use automation to sync
   ```yaml
   automation:
     - alias: "SmartHRT - Sync Phone Alarm"
       trigger:
         - platform: state
           entity_id: sensor.phone_next_alarm
       action:
         - service: time.set_value
           target:
             entity_id: time.living_room_target_hour
           data:
             time: "{{ states('sensor.phone_next_alarm')[11:16] }}"
   ```

### What are the stages from heating stop to wake-up?

**Answer**:

| Time               | Stage          | What Happens                                                 |
| ------------------ | -------------- | ------------------------------------------------------------ |
| 23:00              | Heating Stop   | Snapshot taken (Tint, Text). Lag detection enabled.          |
| 23:05-03:00        | Lag Detection  | Monitor Tint. Wait for -0.2°C drop. Calculate recovery time. |
| 03:00 (calculated) | Recovery Start | Actual RCth calculated. RCth_lw/hw updated (if adaptive ON). |
| 03:00-06:00        | Recovery       | Heating active. RPth calculation mode enabled.               |
| 06:00              | Recovery End   | Actual RPth calculated. RPth_lw/hw updated (if adaptive ON). |

### Why is first cycle inaccurate?

**Answer**:

First cycle uses default coefficients (RCth=3.0h, RPth=2.0°C). These are generic estimates.

- **After 1st cycle**: Rough calibration (high error margin)
- **After 3-5 cycles**: Better accuracy
- **After 7-10 cycles**: Good precision

System continues learning and adapting automatically if adaptive mode is enabled.

### Can I run multiple rooms?

**Answer**: Yes! Just add the integration multiple times.

Each instance:

- Gets its own sensors/numbers
- Learns independently
- Requires separate automations

Example:

```
SmartHRT - Living Room (instance 1)
  ├── sensor.living_room_*
  ├── number.living_room_*
  └── switch.living_room_*

SmartHRT - Bedroom (instance 2)
  ├── sensor.bedroom_*
  ├── number.bedroom_*
  └── switch.bedroom_*
```

### How do I disable SmartHRT temporarily?

**Answer**: Turn off smart heating mode

```yaml
service: switch.turn_off
target:
  entity_id: switch.living_room_smartheating_mode
```

All calculations suspend. Automations can still run but won't call SmartHRT services.

To fully disable: **Settings → Devices & Services → SmartHRT → Delete**

---

## Getting Help

### How to check if something went wrong

1. **Check automation history**

   ```
   Settings → Automations → [Automation Name] → Execution History
   ```

2. **Check system logs**

   ```
   Settings → System → Logs
   Search: "SmartHRT"
   ```

3. **Enable debug logging**

   ```yaml
   logger:
     logs:
       custom_components.SmartHRT: debug
   ```

   Then restart. Check logs again for debug messages.

4. **Check entity states**
   ```
   Developer Tools → States
   Search: your instance name (e.g., "living_room")
   ```

### Where to report issues

- **GitHub Issues**: [corentinBarban/SmartHRT](https://github.com/corentinBarban/SmartHRT/issues)
- **Provide**:
  - Home Assistant version
  - SmartHRT version
  - Relevant log excerpts
  - Your configuration (without sensitive data)
  - Steps to reproduce

---

**Related:**

- 🚀 [Getting Started](GETTING_STARTED.md)
- 👨‍💻 [API & Examples](API_AND_EXAMPLES.md)
- 🏗️ [Technical Reference](TECHNICAL_REFERENCE.md)
