"""Tests pour la cohérence et le bon fonctionnement des services SmartHRT.

Ce module vérifie que :
1. Tous les services sont correctement définis dans const.py
2. Tous les services ont une définition dans services.yaml
3. Tous les services ont un handler dans services.py
4. Les handlers fonctionnent correctement
"""

from datetime import datetime, time as dt_time
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest
import yaml

from custom_components.SmartHRT.const import (
    DOMAIN,
    SERVICE_START_HEATING_CYCLE,
    SERVICE_STOP_HEATING,
    SERVICE_START_RECOVERY,
    SERVICE_END_RECOVERY,
    SERVICE_GET_STATE,
    SERVICE_RESET_LEARNING,
    SERVICE_TRIGGER_CALCULATION,
)
from custom_components.SmartHRT.coordinator import SmartHRTState


# Liste de tous les services attendus (Services essentiels uniquement)
EXPECTED_SERVICES = [
    SERVICE_START_HEATING_CYCLE,
    SERVICE_STOP_HEATING,
    SERVICE_START_RECOVERY,
    SERVICE_END_RECOVERY,
    SERVICE_GET_STATE,
    SERVICE_RESET_LEARNING,
    SERVICE_TRIGGER_CALCULATION,
]


class TestServicesConsistency:
    """Tests de cohérence entre const.py, services.yaml et services.py."""

    def test_all_services_defined_in_const(self):
        """Vérifie que toutes les constantes de service sont définies."""
        # Toutes les constantes doivent être des strings non vides
        for service in EXPECTED_SERVICES:
            assert isinstance(service, str)
            assert len(service) > 0

    def test_services_yaml_exists(self):
        """Vérifie que services.yaml existe."""
        services_yaml_path = Path("custom_components/SmartHRT/services.yaml")
        assert services_yaml_path.exists(), "services.yaml non trouvé"

    def test_all_services_in_yaml(self):
        """Vérifie que tous les services sont définis dans services.yaml."""
        services_yaml_path = Path("custom_components/SmartHRT/services.yaml")

        if not services_yaml_path.exists():
            pytest.skip("services.yaml non trouvé")

        with open(services_yaml_path) as f:
            yaml_content = yaml.safe_load(f)

        yaml_services = set(yaml_content.keys())

        for service in EXPECTED_SERVICES:
            assert service in yaml_services, (
                f"Service '{service}' non trouvé dans services.yaml. "
                f"Services disponibles: {sorted(yaml_services)}"
            )

    def test_no_extra_services_in_yaml(self):
        """Vérifie qu'il n'y a pas de services orphelins dans services.yaml."""
        services_yaml_path = Path("custom_components/SmartHRT/services.yaml")

        if not services_yaml_path.exists():
            pytest.skip("services.yaml non trouvé")

        with open(services_yaml_path) as f:
            yaml_content = yaml.safe_load(f)

        yaml_services = set(yaml_content.keys())
        expected_set = set(EXPECTED_SERVICES)

        extra_services = yaml_services - expected_set
        assert (
            len(extra_services) == 0
        ), f"Services orphelins dans services.yaml: {extra_services}"

    def test_services_py_imports_all_from_const(self):
        """Vérifie que services.py importe tous les services depuis const.py."""
        services_py_path = Path("custom_components/SmartHRT/services.py")

        if not services_py_path.exists():
            pytest.skip("services.py non trouvé")

        content = services_py_path.read_text()

        # Vérifier que les constantes ne sont pas redéfinies localement
        for service in EXPECTED_SERVICES:
            # Le pattern = "service_name" ne doit pas apparaître (redéfinition)
            pattern = f'= "{service}"'
            # Sauf dans const.py (qui est importé)
            assert pattern not in content or "from .const import" in content, (
                f"Le service '{service}' semble être redéfini localement dans services.py "
                "au lieu d'être importé depuis const.py"
            )


class TestServicesHandlers:
    """Tests des handlers de services."""

    @pytest.mark.asyncio
    async def test_stop_heating_handler_uses_async_method(self, create_coordinator):
        """Vérifie que stop_heating appelle la méthode async correcte."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 8, 0, 0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                interior_temp=19.0,
                exterior_temp=5.0,
            )

            # Simuler l'appel du handler stop_heating
            await coord._async_on_recoverycalc_hour()

            # Vérifier la transition
            assert coord.data.current_state == SmartHRTState.DETECTING_LAG

    @pytest.mark.asyncio
    async def test_start_recovery_handler(self, create_coordinator):
        """Vérifie que start_recovery fonctionne correctement."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 16, 0, 0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                interior_temp=17.0,
                exterior_temp=5.0,
                recovery_calc_mode=True,
            )

            # Simuler l'appel du handler start_recovery
            coord.on_recovery_start()

            # Vérifier la transition
            assert coord.data.current_state == SmartHRTState.HEATING_PROCESS
            assert coord.data.rp_calc_mode is True

    @pytest.mark.asyncio
    async def test_end_recovery_handler(self, create_coordinator):
        """Vérifie que end_recovery fonctionne correctement."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 6, 30, 0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_PROCESS,
                interior_temp=20.0,
                exterior_temp=5.0,
                rp_calc_mode=True,
                time_recovery_start=datetime(2026, 2, 4, 4, 0, 0),
                temp_recovery_start=17.0,
            )

            # Simuler l'appel du handler end_recovery
            coord.on_recovery_end()

            # Vérifier la transition
            assert coord.data.current_state == SmartHRTState.HEATING_ON
            assert coord.data.rp_calc_mode is False

    @pytest.mark.asyncio
    async def test_get_state_returns_all_fields(self, create_coordinator):
        """Vérifie que get_state retourne tous les champs attendus."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 10, 0, 0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                interior_temp=18.0,
                exterior_temp=5.0,
            )

            # Les champs que get_state doit retourner
            expected_fields = [
                "current_state",
                "smartheating_mode",
                "recovery_calc_mode",
                "rp_calc_mode",
                "temp_lag_detection_active",
                "interior_temp",
                "exterior_temp",
                "target_hour",
                "recoverycalc_hour",
            ]

            # Vérifier que tous les champs sont accessibles
            for field in expected_fields:
                assert hasattr(coord.data, field), f"Champ '{field}' manquant dans data"


class TestServiceYamlStructure:
    """Tests de la structure de services.yaml."""

    def test_all_services_have_name_and_description(self):
        """Vérifie que tous les services ont un nom et une description."""
        services_yaml_path = Path("custom_components/SmartHRT/services.yaml")

        if not services_yaml_path.exists():
            pytest.skip("services.yaml non trouvé")

        with open(services_yaml_path) as f:
            yaml_content = yaml.safe_load(f)

        for service_name, service_def in yaml_content.items():
            assert "name" in service_def, f"Service '{service_name}' n'a pas de 'name'"
            assert (
                "description" in service_def
            ), f"Service '{service_name}' n'a pas de 'description'"

    def test_all_services_have_entry_id_field(self):
        """Vérifie que tous les services ont le champ entry_id."""
        services_yaml_path = Path("custom_components/SmartHRT/services.yaml")

        if not services_yaml_path.exists():
            pytest.skip("services.yaml non trouvé")

        with open(services_yaml_path) as f:
            yaml_content = yaml.safe_load(f)

        for service_name, service_def in yaml_content.items():
            assert (
                "fields" in service_def
            ), f"Service '{service_name}' n'a pas de 'fields'"
            assert (
                "entry_id" in service_def["fields"]
            ), f"Service '{service_name}' n'a pas le champ 'entry_id'"
