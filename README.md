# SmartHRT

**Smart Heating Recovery Time** - Intelligent heating startup time calculation.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/corentinBarban/smartHRT?include_prereleases)](https://github.com/corentinBarban/SmartHRT/releases)

## 🙏 Acknowledgments

**[@ebozonne](https://github.com/ebozonne)**: Author of the [original SmartHRT code](https://github.com/ebozonne/SmartHRT) on which this native integration is based

## What is it?

SmartHRT automatically calculates when to start the heating in the morning to reach your desired temperature at wake-up time. The algorithm continuously learns your home's thermal characteristics.

## Installation & Configuration

👉 **[User Guide](docs/GUIDE.md)** - Installation, setup, and everyday use.

After installation, configure the integration via **Settings → Devices & Services → SmartHRT**.

## Documentation

- 📖 **[User Guide](docs/GUIDE.md)** - Installation, configuration, automations, and troubleshooting
- 🏗️ **[Architecture Guide](docs/ARCHITECTURE.md)** - Technical design, thermal model, state machine
- 👨‍💻 **[Contributing Guide](docs/CONTRIBUTING.md)** - Development setup and contribution workflow

---

## 🧮 Thermal Calculation

→ **[Complete technical explanation](docs/ARCHITECTURE.md#thermal-model)**

SmartHRT uses Newton's law of cooling to calculate recovery time:

**Key Parameters**:

> - $RC_{th}$: this combines your home's insulation (including air infiltrations) & its effective thermal mass (emitter, furniture, walls, ...)
> - $RP_{th}$: this combines the same insulation & the effective heating power

Both $RC_{th}$ & $RP_{th}$ are necessary to determine the `recovery time`

```math
recoveryTime = RC_{th} \cdot ln \left( \frac {RP_{th}-\left(T_{int}^{START}-T_{ext}\right)} {RP_{th}-\left( T_{sp}-T_{ext}\right)} \right)
```

## 📦 Installation & Prerequisites

→ **[Full installation guide](docs/GUIDE.md#installation)**

**Requirements**:

- Home Assistant 2024.1 or higher
- HACS (recommended)
- A configured weather entity

---

## ⚙️ Configuration

→ **[Detailed configuration guide](docs/GUIDE.md#configuration)**

Required parameters are configured via the Home Assistant interface:

- **Wake-up time** (target hour)
- **Heating stop time** (evening)
- **Interior temperature sensor**
- **Weather source** (temperature and wind)
- **Target temperature** (°C)

---

## 📊 Created Entities

SmartHRT automatically creates **Sensors**, **Numbers**, **Switches** and **Time** entities. See [User Guide](docs/GUIDE.md#available-sensors--controls) for complete list and descriptions.

---

## 🎨 Custom Lovelace Card

SmartHRT includes `smarthrt-card.js`, a custom card to visualize the heating state.

### Installation

1. Copy `smarthrt-card.js` to your `/config/www/` folder
2. In Home Assistant go to **Settings** ⚙️ → **Dashboards** → **⁝** (top right) → **Resources**
3. Click **Add Resource** and enter:
   - **URL**: `/local/smarthrt-card.js`
   - **Type**: JavaScript Module
4. Click **Create**

### Usage

Add the card to your dashboard with:

```yaml
type: custom:smarthrt-card
prefix: salon # required — your SmartHRT instance name
name: Salon # optional — display name
min_temp: 13 # optional — gauge minimum (default: 13)
max_temp: 26 # optional — gauge maximum (default: 26)
```

The card displays current temperature, setpoint, machine state, and relay time.

---

## 🔧 Services

SmartHRT provides Home Assistant services to control the heating cycle manually if needed.

→ **[Complete services documentation](docs/SERVICES.md)**

**Recommended services**:

- `start_heating_cycle` - Start a new heating cycle
- `stop_heating` - Stop heating and start monitoring
- `start_recovery` - Start heating recovery phase
- `end_recovery` - End recovery phase
- `get_state` - Get current state and details
- `reset_learning` - Reset learned thermal coefficients
- `trigger_calculation` - Force immediate recalculation

**Example**:

```yaml
service: smarthrt.stop_heating
```

## Requirements

- For dashboard interface:
  - [HACS](https://www.home-assistant.io/blog/2024/08/21/hacs-the-best-way-to-share-community-made-projects/#how-to-install)
  - [Bubble-Card](https://github.com/Clooos/Bubble-Card)
  - [Mini-Graph-Card](https://github.com/kalkih/mini-graph-card)
  - [Apexcharts-Card](https://github.com/RomRider/apexcharts-card)
  - [Lovelace-Card-Mod](https://github.com/thomasloven/lovelace-card-mod)

## ❓ FAQ & Support

→ **[Troubleshooting and FAQ](docs/GUIDE.md#faq)**

Common questions covered:

- How long until accurate predictions?
- Can I use it with multiple rooms?
- What if my wake-up time changes?
- How to manually adjust calculations?

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
