# 👨‍💻 DEVELOPER.md

**Guide for Contributing to SmartHRT**

## Table of Contents

1. [Environment Setup](#-environment-setup)
2. [Project Structure](#-project-structure)
3. [Code Style](#-code-style)
4. [Adding Features](#-adding-features)
5. [Testing](#-testing)
6. [Debugging](#-debugging)
7. [Git Workflow](#-git-workflow)
8. [PR Checklist](#-pr-checklist)

---

## 🛠️ Environment Setup

### Prerequisites

- Python 3.12+
- Home Assistant 2024.1+
- Git
- Visual Studio Code (recommended)

### Dev Container (Recommended)

This project includes a `.devcontainer/` configuration:

```bash
# Open in VS Code and select "Reopen in Container"
# OR manually:
docker build -f .devcontainer/Dockerfile -t smarthrt-dev .
docker run -it --name smarthrt-dev smarthrt-dev /bin/bash
```

### Manual Setup

```bash
# Clone repository
git clone https://github.com/corentinBarban/SmartHRT.git
cd SmartHRT

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development tools
pip install pytest pytest-cov pylint black isort
```

### Running Home Assistant Locally

```bash
# Start Home Assistant with debugging
uv run .devcontainer/hass_debug.sh

# OR start normal
uv run .devcontainer/hass.sh
```

Access at `http://localhost:8123`

---

## 📁 Project Structure

```
SmartHRT/
├── .devcontainer/              # Dev environment
│   ├── Dockerfile
│   ├── devcontainer.json
│   ├── hass.sh                 # Start HA normally
│   └── hass_debug.sh           # Start HA with debugger
│
├── custom_components/SmartHRT/
│   ├── __init__.py             # Integration entry point (async_setup_entry)
│   ├── coordinator.py          # Central logic (SmartHRTCoordinator)
│   ├── config_flow.py          # UI configuration
│   ├── const.py                # Constants & defaults
│   ├── const_messages.py       # Error/info messages
│   ├── sensor.py               # Sensor entities
│   ├── switch.py               # Switch entities
│   ├── number.py               # Adjustable number entities
│   ├── time.py                 # Time entities
│   ├── services.py             # Service handlers
│   ├── services.yaml           # Service definitions
│   ├── strings.json            # UI strings (EN)
│   ├── manifest.json           # Integration metadata
│   └── translations/           # Localized strings
│       ├── de.json
│       ├── es.json
│       ├── fr.json
│       └── it.json
│
├── tests/
│   ├── conftest.py             # Pytest fixtures
│   ├── test_*.py               # Test files
│   └── __init__.py
│
├── ADR/                        # Architecture Decision Records
│   ├── 001-*.yaml
│   ├── 002-*.yaml
│   └── ...
│
├── ARCHITECTURE.md             # Technical architecture
├── DEVELOPER.md                # This file
├── README.md                   # User documentation (EN)
├── README_fr.md                # User documentation (FR)
├── specification.md            # Technical specification
├── requirements.txt            # Python dependencies
└── pyproject.toml              # Project metadata
```

---

## 🎨 Code Style

### Standards

- **Language**: Python 3.12+
- **Type hints**: Mandatory on all functions and class attributes
- **Docstrings**: Google Style for all public classes and functions
- **Formatting**: `black` + `isort`
- **Linting**: `pylint` + Pylance

### Formatting

```bash
# Format code
black custom_components/SmartHRT/ tests/
isort custom_components/SmartHRT/ tests/

# Lint
pylint custom_components/SmartHRT/

# Type checking
pylance check custom_components/SmartHRT/
```

### Example: Function Docstring

```python
async def calculate_recovery_time(self) -> None:
    """Calculate the optimal heating recovery start time.

    Uses the inverted Newton's law of cooling model:

        recovery_duration = RCth * ln((RPth + Text - Tint_start) / (RPth + Text - TSP))

    The calculation is triggered at recoverycalc_hour (evening) and considers:
    - Current thermal coefficients (RCth, RPth)
    - Forecasted weather (temperature, wind speed)
    - Average wind speed from the last 4 hours

    Results are stored in:
    - self.data.recovery_start_hour (datetime)
    - self.data.recovery_update_hour (next recalc time)

    Raises:
        UpdateFailed: If weather forecast is unavailable
    """
```

### Example: Class Docstring

```python
class SmartHRTCoordinator(DataUpdateCoordinator[SmartHRTData]):
    """Central coordinator for SmartHRT thermal management system.

    Implements the DataUpdateCoordinator pattern (HA standard) to manage:
    - Fetching outdoor temperature and weather forecasts
    - Maintaining the 5-state heating cycle machine
    - Calculating thermal recovery times (anticipation strategy)
    - Auto-calibrating thermal coefficients (learning)
    - Persisting learned data across restarts
    - Handling service calls

    Data Flow:
        Weather Entity → _async_update_data() → SmartHRTData → Entities

    State Machine:
        HEATING_ON → DETECTING_LAG → MONITORING → RECOVERY → HEATING_PROCESS
        ↑                                                          ↓
        └──────────────── (repeat daily) ─────────────────────────┘

    Attributes:
        hass: Home Assistant instance
        config_entry: Configuration entry with user settings
        data: SmartHRTData instance (current state)
    """
```

---

## ✨ Adding Features

### Feature Development Workflow

#### 1. Propose via ADR

If it's a significant architectural change:

```yaml
# ADR/XXX-feature-name.yaml
title: "Feature: Friendly Title"
date: 2026-01-26
status: "proposed"

context: |
  Why do we need this?
  What's the current limitation?

decision: |
  What we decided to do and why.
  Include trade-offs considered.

consequences: |
  What changes as a result?
  Any breaking changes?

related_adrs: |
  - ADR-001
  - ADR-003
```

#### 2. Create Feature Branch

```bash
git checkout -b feat/descriptive-name
```

#### 3. Implement Feature

- Add code to relevant module
- Add/update docstrings
- Add type hints
- Add unit tests

#### 4. Update Strings

If UI-facing, add to [strings.json](custom_components/SmartHRT/strings.json):

```json
{
  "services": {
    "my_service": {
      "name": "My Service",
      "description": "What it does",
      "fields": {
        "param": {
          "name": "Parameter",
          "description": "What it is"
        }
      }
    }
  }
}
```

#### 5. Test Thoroughly

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=custom_components/SmartHRT --cov-report=html

# Specific test
pytest tests/test_coordinator.py::test_calculate_recovery_time -v
```

---

## 🧪 Testing

### Test Structure

```python
# tests/test_coordinator.py

import pytest
from unittest.mock import AsyncMock, patch
from homeassistant.util import dt as dt_util

from custom_components.SmartHRT.coordinator import SmartHRTCoordinator
from custom_components.SmartHRT.const import DOMAIN

@pytest.fixture
async def coordinator(hass, config_entry):
    """Fixture for SmartHRTCoordinator."""
    coord = SmartHRTCoordinator(hass, config_entry)
    await coord.async_init()
    return coord

@pytest.mark.asyncio
async def test_calculate_recovery_time(coordinator):
    """Test recovery time calculation with known values."""
    # Arrange
    coordinator.data.rcth = 3.0
    coordinator.data.rpth = 2.0
    coordinator.data.interior_temp = 18.0
    coordinator.data.exterior_temp = 5.0
    coordinator.data.tsp = 20.0

    # Act
    await coordinator.calculate_recovery_time()

    # Assert
    assert coordinator.data.recovery_start_hour is not None
    assert coordinator.data.recovery_start_hour.time() > dt_util.now().time()
```

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific module
pytest tests/test_coordinator.py -v

# Specific test
pytest tests/test_coordinator.py::test_calculate_recovery_time -v

# With coverage
pytest tests/ --cov=custom_components/SmartHRT --cov-report=term-missing

# With markers
pytest -m "not integration" tests/
```

### Test Coverage Target

Aim for **>85% coverage**:

```bash
pytest tests/ --cov=custom_components/SmartHRT --cov-report=html
open htmlcov/index.html
```

---

## 🐛 Debugging

### Enable Debug Logging

**Option 1: Home Assistant Settings**

```yaml
# configuration.yaml
logger:
  default: info
  logs:
    custom_components.SmartHRT: debug
    homeassistant.components.generic: debug
```

**Option 2: Services**

```yaml
service: logger.set_level
data:
  custom_components.SmartHRT: debug
```

### VS Code Debugger

1. Install `debugpy`:

   ```bash
   pip install debugpy
   ```

2. Start HA with debugger:

   ```bash
   uv run .devcontainer/hass_debug.sh
   ```

3. In VS Code: **Run → Start Debugging**

4. Set breakpoints and inspect variables

### Common Issues

#### Coordinator not updating

- Check weather entity exists and has current state
- Check `_async_update_data()` for exceptions
- Verify `update_interval` setting

#### Entities not appearing

- Run integration setup in Home Assistant UI
- Check entity registry in `core.entity_registry`
- Verify `_attr_has_entity_name = True`

#### Tests failing

- Clear pytest cache: `pytest --cache-clear`
- Check Home Assistant version compatibility
- Verify mock fixtures are properly async

---

## 📝 Git Workflow

### Branch Naming

- `feat/feature-name` - New feature
- `fix/bug-description` - Bug fix
- `docs/update-docs` - Documentation
- `refactor/improve-logic` - Code refactoring
- `test/add-tests` - Test improvements

### Commit Messages

Follow **Conventional Commits**:

```
feat(coordinator): add wind history averaging

- Maintain 4h rolling window of wind speed samples
- Calculate average for smoother calibration
- Implements ADR-013

Related-to: ADR-013
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `refactor`: Code refactoring
- `perf`: Performance improvement
- `test`: Test additions/fixes
- `chore`: Build, CI, dependencies

### Create Pull Request

1. Push to your fork
2. Create PR with descriptive title
3. Link related issues
4. Include test results
5. Request review

---

## ✅ PR Checklist

Before submitting a pull request:

- [ ] Code passes `black` formatting
- [ ] Code passes `pylint` linting
- [ ] All type hints are present
- [ ] Docstrings added (Google style)
- [ ] Tests added/updated with >85% coverage
- [ ] Tests pass locally: `pytest tests/ -v`
- [ ] No breaking changes OR documented in ADR
- [ ] strings.json updated (if UI changes)
- [ ] README.md updated (if user-facing)
- [ ] ARCHITECTURE.md updated (if architecture changes)
- [ ] Commit messages follow Conventional Commits
- [ ] Branch is up-to-date with `main`
- [ ] No hardcoded values (use `const.py`)

---

## 📚 Additional Resources

- [Home Assistant Integration Documentation](https://developers.home-assistant.io/docs/integration_index)
- [DataUpdateCoordinator Pattern](https://developers.home-assistant.io/docs/integration_fetching_data)
- [Entity Development](https://developers.home-assistant.io/docs/entity)
- [HACS Contributing Guide](https://hacs.xyz/docs/developer/start)

---

## 🤝 Getting Help

- **Discussions**: GitHub Discussions
- **Issues**: GitHub Issues (bugs, feature requests)
- **Docs**: [ARCHITECTURE.md](ARCHITECTURE.md), [specification.md](specification.md)
- **ADRs**: [ADR/](ADR/) folder

Happy coding! 🚀
