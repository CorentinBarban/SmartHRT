"""Tests de non-régression : la consigne modifiée via l'options flow survit au reload.

Bug corrigé: l'options flow déplace tsp/target_hour/recoverycalc_hour de
entry.data vers entry.options. Le coordinateur ne lisait que entry.data au
démarrage, donc tsp retombait sur DEFAULT_TSP après un reload/restart
(tsp n'étant pas persisté dans le Store).
"""

from datetime import time as dt_time

import pytest

from custom_components.SmartHRT.const import DEFAULT_TSP


@pytest.mark.asyncio
async def test_tsp_from_options_used_on_startup(mock_entry, create_coordinator):
    """Après l'options flow, tsp absent de data mais présent dans options."""
    mock_entry.data = {
        "name": "Test SmartHRT",
        "sensor_interior_temperature": "sensor.interior_temp",
        "weather_entity": "weather.home",
    }
    mock_entry.options = {
        "tsp": 21.0,
        "target_hour": "07:30:00",
        "recoverycalc_hour": "22:00:00",
    }
    assert DEFAULT_TSP != 21.0

    coordinator = await create_coordinator()

    assert coordinator.data.tsp == 21.0
    assert coordinator.data.target_hour == dt_time(7, 30)
    assert coordinator.data.recoverycalc_hour == dt_time(22, 0)


@pytest.mark.asyncio
async def test_options_take_precedence_over_data(mock_entry, create_coordinator):
    """Si une clé est dans data et options, options l'emporte."""
    mock_entry.data = {**mock_entry.data, "tsp": 20.0}
    mock_entry.options = {"tsp": 21.0}

    coordinator = await create_coordinator()

    assert coordinator.data.tsp == 21.0


@pytest.mark.asyncio
async def test_data_used_when_no_options(mock_entry, create_coordinator):
    """Entrée jamais passée par l'options flow : data est utilisé."""
    mock_entry.data = {**mock_entry.data, "tsp": 20.0}
    mock_entry.options = {}

    coordinator = await create_coordinator()

    assert coordinator.data.tsp == 20.0


@pytest.mark.asyncio
async def test_tsp_persisted_and_restored(mock_entry, mock_store, create_coordinator):
    """tsp modifié à chaud (entité number) est sauvegardé puis restauré."""
    coordinator = await create_coordinator()
    coordinator.data.tsp = 21.5
    await coordinator._save_learned_data()

    assert mock_store._data["tsp"] == 21.5

    restarted = await create_coordinator()
    await restarted._restore_learned_data()

    assert restarted.data.tsp == 21.5
