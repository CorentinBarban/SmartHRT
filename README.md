# SmartHRT

**Smart Heating Recovery Time** - Intelligent heating startup time calculation.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/corentinBarban/smartHRT?include_prereleases)](https://github.com/corentinBarban/SmartHRT/releases)

## What is it?

SmartHRT automatically calculates when to start the heating in the morning to reach your desired temperature at wake-up time. The algorithm continuously learns your home's thermal characteristics.

## Installation & Configuration

👉 **[Quick Start](docs/GETTING_STARTED.md)** - Step-by-step guide with HACS or manual installation.

After installation, configure the integration via **Settings → Devices & Services → SmartHRT**.

## Documentation

- 🚀 [Getting Started](docs/GETTING_STARTED.md) - Installation and configuration
- 📊 [Architecture Diagrams](docs/ARCHITECTURE_DIAGRAMS.md) - Visual schemas and workflows
- 🏗️ [Technical Reference](docs/TECHNICAL_REFERENCE.md) - Architecture and formulas
- 🔧 [Support](docs/SUPPORT.md) - Troubleshooting and FAQ
- 👨‍💻 [Developer Guide](docs/DEVELOPER.md) - Contribution guide

---

## 🧮 Thermal Calculation

→ **[Complete technical specification](docs/TECHNICAL_REFERENCE.md#thermal-calculations)**

SmartHRT uses an inverted Newton's law of cooling formulation to calculate recovery time:

**Key Parameters**:

- **RCth**: Thermal time constant (dissipation)
- **RPth**: Thermal power constant (heating)

These parameters adapt to **wind speed** via linear interpolation.

## 📦 Installation & Prerequisites

→ **[Full installation guide](docs/GETTING_STARTED.md)**

**Requirements**:

- Home Assistant 2024.1 or higher
- HACS (recommended)
- A configured weather entity

---

## ⚙️ Configuration

→ **[Detailed configuration guide](docs/GETTING_STARTED.md#configuration)**

Required parameters are configured via the Home Assistant interface:

- **Wake-up time** (`target_hour`)
- **Heating stop time** (`recoverycalc_hour`)
- **Interior temperature sensor**
- **Weather source** (temperature and wind)
- **Target temperature** (°C)

---

## 📊 Created Entities

SmartHRT automatically creates **Sensors**, **Numbers**, **Switches** and **Time** entities. See [Technical Reference](docs/TECHNICAL_REFERENCE.md) for complete documentation.

## ❓ FAQ & Support

→ **[Complete FAQ and troubleshooting](docs/SUPPORT.md)**

**Frequently asked questions**:

- What to do during holidays?
- Why aren't predictions accurate in the first few days?
- How to manually adjust coefficients?

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
