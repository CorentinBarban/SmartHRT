# Contributing to SmartHRT

**Development guide for contributors**

## Getting Started

### Prerequisites

- Python 3.12+
- Home Assistant 2024.1+
- Git
- Basic knowledge of Home Assistant

### Development Environment

**Using Dev Container (Recommended):**

1. Clone the repository:

```bash
git clone https://github.com/corentinBarban/SmartHRT.git
cd SmartHRT
```

2. Open in VS Code with Dev Container:
   - Install "Dev Containers" extension
   - Click "Reopen in Container"
   - Wait for setup (5-10 minutes first time)

**Manual Setup:**

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install dev tools
pip install pytest pytest-cov pylint black isort
```

### Running Home Assistant

```bash
# Start with debugger (port 5678)
uv run .devcontainer/hass_debug.sh

# OR start normally (port 8123)
uv run .devcontainer/hass.sh
```

Access at `http://localhost:8123`

## Project Structure

```
SmartHRT/
├── custom_components/SmartHRT/
│   ├── __init__.py           # Integration entry point
│   ├── coordinator.py        # Main logic
│   ├── config_flow.py        # Configuration UI
│   ├── const.py              # Constants
│   ├── sensor.py             # Sensor platform
│   ├── switch.py             # Switch platform
│   ├── number.py             # Number platform
│   ├── time.py               # Time platform
│   ├── services.py           # Service handlers
│   ├── manifest.json         # Integration metadata
│   └── strings.json          # UI strings
│
├── tests/                    # Unit tests
├── docs/                     # Documentation
└── requirements.txt          # Dependencies
```

## Code Style

### Python Standards

- **Line length:** 88 characters (Black formatter)
- **Naming:** snake_case for functions, PascalCase for classes
- **Type hints:** Required for all functions
- **Docstrings:** Google-style format

Example:

```python
async def calculate_recovery_time(
    temperature_drop: float,
    rc_thermal: float
) -> int:
    """Calculate heating recovery time based on temperature decay.

    Args:
        temperature_drop: Observed temperature decrease (°C)
        rc_thermal: Thermal time constant (hours)

    Returns:
        Recovery time in minutes
    """
    ...
```

### Formatting

```bash
# Auto-format with Black
black .

# Sort imports
isort .

# Lint code
pylint custom_components/SmartHRT/*.py
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=custom_components/SmartHRT

# Run specific test
pytest tests/test_coordinator.py::test_example
```

### Writing Tests

Tests should cover:

- State transitions
- Thermal calculations
- Configuration validation
- Error handling

Example test structure:

```python
async def test_recovery_calculation():
    """Test recovery time calculation."""
    # Setup
    coordinator = create_test_coordinator()

    # Execute
    recovery_time = coordinator.calculate_recovery()

    # Assert
    assert recovery_time > 0
    assert recovery_time < 720  # Max 12 hours
```

## Making Changes

### Before You Start

1. Check [GitHub Issues](https://github.com/corentinBarban/SmartHRT/issues) for existing work
2. For major features, open a discussion first
3. Read the [Architecture Guide](ARCHITECTURE.md)

### Development Workflow

1. **Create a branch:**

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes:**
   - Keep commits small and focused
   - Write clear commit messages
   - Add tests for new code

3. **Test locally:**

   ```bash
   pytest
   black .
   pylint custom_components/SmartHRT/*.py
   ```

4. **Push and create PR:**
   ```bash
   git push origin feature/your-feature-name
   ```
   Then open a pull request on GitHub

### PR Checklist

- [ ] Code follows style guide (Black, isort, pylint)
- [ ] Tests added/updated for new features
- [ ] Tests pass: `pytest --cov=custom_components/SmartHRT`
- [ ] Docstrings added/updated
- [ ] Commit messages are clear
- [ ] No debug print statements left
- [ ] Compatible with Home Assistant 2024.1+

## Common Tasks

### Adding a New Sensor

1. Define in `const.py`:

```python
SENSOR_INTERIOR_TEMPERATURE = "interior_temperature"
```

2. Create in `sensor.py`:

```python
class SmartHRTTemperatureSensor(CoordinatorEntity):
    def native_value(self):
        return self.coordinator.data.interior_temperature
```

3. Register in entity description

### Modifying Thermal Calculations

- Main logic: `coordinator.py`
- Constants: `const.py`
- Tests: `tests/test_coordinator.py`
- Update [Architecture Guide](ARCHITECTURE.md) if formula changes

### Adding a New Configuration Option

1. Update `config_flow.py` with new field
2. Add to data model in `coordinator.py`
3. Update `const.py` with defaults
4. Add strings to `strings.json` for UI labels
5. Update documentation

## Debugging

### Enable Verbose Logging

In Home Assistant:

1. **Settings** → **Developer Tools** → **Logs**
2. Add custom logger for SmartHRT at DEBUG level
3. Watch real-time logs

### Debugger (VS Code)

```bash
# Start with debugger
uv run .devcontainer/hass_debug.sh

# In VS Code: Debug → Python: Remote Attach (port 5678)
```

### Common Issues

**"Type hints not recognized"**

- Ensure Python 3.12+ in virtual environment
- Try: `pip install --upgrade typing-extensions`

**"Import errors in tests"**

- Run: `pip install -e .`
- Or run: `export PYTHONPATH=/workspaces/SmartHRT`

**"Tests fail locally but work in CI"**

- Check Python version matches
- Ensure Home Assistant version 2024.1+
- Clear pytest cache: `pytest --cache-clear`

## Documentation

- User guide: [GUIDE.md](GUIDE.md)
- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- Inline: Code comments for complex logic

Update documentation when:

- Adding user-facing features
- Changing configuration options
- Modifying thermal model
- Updating dependencies

## Code Review Process

1. Automated checks run (linting, tests)
2. Manual review by maintainers
3. Feedback provided as comments
4. Update code as needed
5. Maintainer approves and merges

## Release Process

Maintainers handle:

1. Version bump in `manifest.json`
2. Update `README.md` changelog
3. Tag release on GitHub
4. HACS picks up automatically

## Questions or Issues?

- Open a [GitHub Issue](https://github.com/corentinBarban/SmartHRT/issues)
- Ask in [Discussions](https://github.com/corentinBarban/SmartHRT/discussions)
- Check [GUIDE.md](GUIDE.md) troubleshooting section

---

**Thank you for contributing to SmartHRT!**
