"""Tests for ADR-053: Inter-season optimization (Snooze) and learning protection.

This module tests:
1. Intelligent Snooze: No recovery is scheduled when estimated duration < 15 minutes
2. Learning Guard: RPth calculation is skipped when actual heating duration < 15 minutes

ADR-053 implementation ensures:
- No micro-cycles during mild weather (energy savings)
- Thermal model (RPth) is protected from corrupted data from short cycles
"""

import logging
from datetime import datetime, time as dt_time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.SmartHRT.const import (
    DEFAULT_RCTH,
    DEFAULT_RPTH,
    DEFAULT_TSP,
    MIN_DURATION_THRESHOLD_HOURS,
    MIN_LEARNING_DURATION_HOURS,
    TimerKey,
)
from custom_components.SmartHRT.coordinator import (
    SmartHRTCoordinator,
    SmartHRTState,
)
from custom_components.SmartHRT.data_model import SmartHRTData


def _now_aware() -> datetime:
    """Return timezone-aware current datetime."""
    return datetime.now(timezone.utc)


class TestSnoozeIntelligent:
    """Tests for the intelligent Snooze feature (ADR-053).

    When estimated recovery duration is below MIN_DURATION_THRESHOLD_HOURS (15 min),
    no recovery should be scheduled and existing timers should be cancelled.
    """

    @pytest.fixture
    def coordinator_monitoring(self, create_coordinator):
        """Fixture for a coordinator in MONITORING state."""

        async def _setup():
            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                smartheating_mode=True,
                interior_temp=18.5,  # Close to TSP
                exterior_temp=10.0,
            )
            return coord

        return _setup

    @pytest.mark.asyncio
    async def test_snooze_when_duration_below_threshold(
        self, coordinator_monitoring, caplog
    ):
        """Test that recovery is NOT scheduled when duration < 15 minutes."""
        caplog.set_level(logging.INFO)
        coord = await coordinator_monitoring()

        # Set a very short estimated duration (10 minutes = 0.167 hours)
        short_duration = 0.167  # < MIN_DURATION_THRESHOLD_HOURS (0.25)

        # Mock the timer manager
        coord._timer_manager = MagicMock()
        coord._timer_manager.is_active.return_value = True

        with patch.object(coord, "calculate_rcth_fast"):
            with patch.object(coord, "calculate_recovery_time") as mock_calc:

                def set_short_duration():
                    coord.data.recovery_duration_hours = short_duration
                    coord.data.recovery_start_hour = _now_aware() + timedelta(
                        hours=short_duration
                    )

                mock_calc.side_effect = set_short_duration

                with patch.object(
                    coord, "calculate_recovery_update_time"
                ) as mock_update:
                    mock_update.return_value = _now_aware() + timedelta(hours=1)

                    await coord._async_on_recovery_update_hour()

                    # Verify timer was cancelled (Snooze active)
                    coord._timer_manager.cancel.assert_called_once_with(
                        TimerKey.RECOVERY_START
                    )

                    # Verify snooze was logged
                    assert "ADR-053 Snooze" in caplog.text

    @pytest.mark.asyncio
    async def test_no_snooze_when_duration_above_threshold(
        self, coordinator_monitoring
    ):
        """Test that recovery IS scheduled when duration >= 15 minutes."""
        coord = await coordinator_monitoring()

        # Set a sufficient duration (30 minutes = 0.5 hours)
        sufficient_duration = 0.5  # > MIN_DURATION_THRESHOLD_HOURS (0.25)
        recovery_time = _now_aware() + timedelta(hours=sufficient_duration)

        coord._timer_manager = MagicMock()
        coord._timer_manager.is_active.return_value = False

        with patch.object(coord, "calculate_rcth_fast"):
            with patch.object(coord, "calculate_recovery_time") as mock_calc:

                def set_duration():
                    coord.data.recovery_duration_hours = sufficient_duration
                    coord.data.recovery_start_hour = recovery_time

                mock_calc.side_effect = set_duration

                with patch.object(coord, "_schedule_recovery_start") as mock_schedule:
                    with patch.object(
                        coord, "calculate_recovery_update_time"
                    ) as mock_update:
                        mock_update.return_value = _now_aware() + timedelta(hours=1)

                        await coord._async_on_recovery_update_hour()

                        # Verify timer was scheduled (no Snooze)
                        mock_schedule.assert_called_once_with(recovery_time)

    @pytest.mark.asyncio
    async def test_snooze_logs_when_no_existing_timer(
        self, coordinator_monitoring, caplog
    ):
        """Test that snooze logs appropriately when no timer exists to cancel."""
        caplog.set_level(logging.DEBUG)
        coord = await coordinator_monitoring()

        # Duration below threshold
        coord._timer_manager = MagicMock()
        coord._timer_manager.is_active.return_value = False  # No existing timer

        with patch.object(coord, "calculate_rcth_fast"):
            with patch.object(coord, "calculate_recovery_time") as mock_calc:

                def set_short_duration():
                    coord.data.recovery_duration_hours = 0.1  # 6 minutes
                    coord.data.recovery_start_hour = _now_aware() + timedelta(minutes=6)

                mock_calc.side_effect = set_short_duration

                with patch.object(
                    coord, "calculate_recovery_update_time"
                ) as mock_update:
                    mock_update.return_value = _now_aware() + timedelta(hours=1)

                    await coord._async_on_recovery_update_hour()

                    # Cancel should not be called since no timer is active
                    coord._timer_manager.cancel.assert_not_called()

                    # But snooze should be logged (at DEBUG level)
                    assert "ADR-053 Snooze" in caplog.text


class TestLearningGuard:
    """Tests for the learning protection feature (ADR-053).

    RPth calculation should be skipped when actual heating duration
    is below MIN_LEARNING_DURATION_HOURS (15 min).
    """

    @pytest.fixture
    def coordinator_with_heating_data(self, create_coordinator):
        """Fixture for a coordinator with heating cycle data."""

        async def _setup(heating_duration_minutes: float):
            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_PROCESS,
                smartheating_mode=True,
            )

            # Set recovery start and end times (timezone-aware)
            end_time = datetime(2026, 2, 28, 6, 0, 0, tzinfo=timezone.utc)
            start_time = end_time - timedelta(minutes=heating_duration_minutes)

            coord.data.time_recovery_start = start_time
            coord.data.time_recovery_end = end_time
            coord.data.temp_recovery_start = 17.0
            coord.data.temp_recovery_end = 19.0
            coord.data.text_recovery_start = 5.0
            coord.data.text_recovery_end = 5.0

            return coord

        return _setup

    @pytest.mark.asyncio
    async def test_rpth_not_calculated_when_duration_too_short(
        self, coordinator_with_heating_data, caplog
    ):
        """Test that RPth is NOT calculated when heating duration < 15 minutes."""
        caplog.set_level(logging.INFO)
        # Create coordinator with 10-minute heating cycle
        coord = await coordinator_with_heating_data(heating_duration_minutes=10)

        # Mock the thermal solver
        mock_solver = MagicMock()
        coord._thermal_solver = mock_solver

        # Call calculate_rpth_at_recovery_end
        coord.calculate_rpth_at_recovery_end()

        # Verify thermal solver was NOT called
        mock_solver.calculate_rpth_at_recovery.assert_not_called()

        # Verify guard was logged
        assert "ADR-053 Learning Guard" in caplog.text
        assert "calcul RPth annulé" in caplog.text

    @pytest.mark.asyncio
    async def test_rpth_calculated_when_duration_sufficient(
        self, coordinator_with_heating_data
    ):
        """Test that RPth IS calculated when heating duration >= 15 minutes."""
        # Create coordinator with 30-minute heating cycle
        coord = await coordinator_with_heating_data(heating_duration_minutes=30)

        # Mock the thermal solver
        mock_solver = MagicMock()
        mock_solver.calculate_rpth_at_recovery.return_value = 45.0
        coord._thermal_solver = mock_solver

        # Call calculate_rpth_at_recovery_end
        coord.calculate_rpth_at_recovery_end()

        # Verify thermal solver WAS called
        mock_solver.calculate_rpth_at_recovery.assert_called_once()

    @pytest.mark.asyncio
    async def test_rpth_not_calculated_at_exact_threshold(
        self, coordinator_with_heating_data, caplog
    ):
        """Test edge case: RPth NOT calculated when duration equals threshold."""
        caplog.set_level(logging.INFO)
        # Create coordinator with exactly 14.9-minute heating cycle (just below threshold)
        coord = await coordinator_with_heating_data(heating_duration_minutes=14.9)

        mock_solver = MagicMock()
        coord._thermal_solver = mock_solver

        coord.calculate_rpth_at_recovery_end()

        # Should NOT be calculated (14.9 min < 15 min threshold)
        mock_solver.calculate_rpth_at_recovery.assert_not_called()
        assert "ADR-053 Learning Guard" in caplog.text

    @pytest.mark.asyncio
    async def test_rpth_calculated_at_exact_threshold(
        self, coordinator_with_heating_data
    ):
        """Test edge case: RPth calculated when duration equals exactly 15 minutes."""
        # Create coordinator with exactly 15-minute heating cycle
        coord = await coordinator_with_heating_data(heating_duration_minutes=15)

        mock_solver = MagicMock()
        mock_solver.calculate_rpth_at_recovery.return_value = 45.0
        coord._thermal_solver = mock_solver

        coord.calculate_rpth_at_recovery_end()

        # Should be calculated (15 min >= 15 min threshold)
        mock_solver.calculate_rpth_at_recovery.assert_called_once()


class TestConstantsConsistency:
    """Tests to verify ADR-053 constants are properly defined."""

    def test_min_duration_threshold_is_15_minutes(self):
        """Verify MIN_DURATION_THRESHOLD_HOURS represents 15 minutes."""
        assert MIN_DURATION_THRESHOLD_HOURS == 0.25  # 15 min / 60 = 0.25 hours

    def test_min_learning_duration_is_15_minutes(self):
        """Verify MIN_LEARNING_DURATION_HOURS represents 15 minutes."""
        assert MIN_LEARNING_DURATION_HOURS == 0.25  # 15 min / 60 = 0.25 hours

    def test_thresholds_are_equal(self):
        """Verify both thresholds are the same (as per ADR-053)."""
        assert MIN_DURATION_THRESHOLD_HOURS == MIN_LEARNING_DURATION_HOURS


class TestSnoozeExitRescheduling:
    """Tests for snooze exit trigger rescheduling (Bug fix: Salon 2026-03-06).

    When temperature drops after a snooze (temperature was at target, then dropped),
    the trigger must be rescheduled even if recovery_start_hour hasn't changed.
    """

    @pytest.fixture
    def coordinator_monitoring(self, create_coordinator):
        """Fixture for a coordinator in MONITORING state."""

        async def _setup():
            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                smartheating_mode=True,
                interior_temp=18.5,
                exterior_temp=10.0,
            )
            return coord

        return _setup

    @pytest.mark.asyncio
    async def test_trigger_rescheduled_after_snooze_exit(
        self, coordinator_monitoring, caplog
    ):
        """Test that trigger IS rescheduled when exiting snooze.

        Scenario:
        1. First call: duration < threshold → timer cancelled (snooze)
        2. Second call: duration >= threshold → timer must be rescheduled
              even if recovery_start_hour is the same
        """
        caplog.set_level(logging.INFO)
        coord = await coordinator_monitoring()

        recovery_time = _now_aware() + timedelta(hours=1)

        # Setup timer manager mock
        coord._timer_manager = MagicMock()

        # STEP 1: Enter snooze (duration below threshold)
        coord._timer_manager.is_active.return_value = True  # Timer exists

        with patch.object(coord, "calculate_rcth_fast"):
            with patch.object(coord, "calculate_recovery_time") as mock_calc:

                def set_short_duration():
                    coord.data.recovery_duration_hours = 0.1  # 6 minutes < 15 min
                    coord.data.recovery_start_hour = recovery_time

                mock_calc.side_effect = set_short_duration

                with patch.object(
                    coord, "calculate_recovery_update_time"
                ) as mock_update:
                    mock_update.return_value = _now_aware() + timedelta(hours=1)

                    await coord._async_on_recovery_update_hour()

                    # Timer was cancelled (snooze active)
                    coord._timer_manager.cancel.assert_called_once_with(
                        TimerKey.RECOVERY_START
                    )
                    assert "ADR-053 Snooze" in caplog.text

        # Reset mock for step 2
        coord._timer_manager.reset_mock()
        caplog.clear()

        # STEP 2: Exit snooze (duration above threshold)
        coord._timer_manager.is_active.return_value = False  # Timer was cancelled

        with patch.object(coord, "calculate_rcth_fast"):
            with patch.object(coord, "calculate_recovery_time") as mock_calc:

                def set_sufficient_duration():
                    # Same recovery_start_hour but duration now sufficient
                    coord.data.recovery_duration_hours = 0.5  # 30 min > 15 min
                    coord.data.recovery_start_hour = recovery_time

                mock_calc.side_effect = set_sufficient_duration

                with patch.object(coord, "_schedule_recovery_start") as mock_schedule:
                    with patch.object(
                        coord, "calculate_recovery_update_time"
                    ) as mock_update:
                        mock_update.return_value = _now_aware() + timedelta(hours=1)

                        await coord._async_on_recovery_update_hour()

                        # Timer MUST be rescheduled (exit from snooze)
                        mock_schedule.assert_called_once_with(recovery_time)
                        assert "Sortie de snooze" in caplog.text

    @pytest.mark.asyncio
    async def test_no_rescheduling_when_already_active(self, coordinator_monitoring):
        """Test that trigger is NOT rescheduled if already active and time unchanged."""
        coord = await coordinator_monitoring()

        recovery_time = _now_aware() + timedelta(hours=1)

        # Set prev_recovery_start to same value to simulate unchanged time
        coord.data.recovery_start_hour = recovery_time

        coord._timer_manager = MagicMock()
        coord._timer_manager.is_active.return_value = True  # Timer already exists

        with patch.object(coord, "calculate_rcth_fast"):
            with patch.object(coord, "calculate_recovery_time") as mock_calc:

                def set_duration():
                    coord.data.recovery_duration_hours = 0.5  # Above threshold
                    # Keep same recovery_start_hour (no change)

                mock_calc.side_effect = set_duration

                with patch.object(coord, "_schedule_recovery_start") as mock_schedule:
                    with patch.object(
                        coord, "calculate_recovery_update_time"
                    ) as mock_update:
                        mock_update.return_value = _now_aware() + timedelta(hours=1)

                        await coord._async_on_recovery_update_hour()

                        # Timer should NOT be rescheduled (already active, time unchanged)
                        mock_schedule.assert_not_called()
