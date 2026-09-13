"""Test de non-régression pour le bug #3.1.

_calculate_with_cooling_prediction() ne doit jamais lever UnboundLocalError
quand cooling_time <= 0 dès la première itération (break avant que
tint_at_start soit calculé dans la boucle).
"""

from custom_components.SmartHRT.core.thermal import ThermalSolver


class TestCoolingPredictionUnboundLocal:
    """Régression #3.1: tint_at_start doit être défini avant la boucle."""

    def test_no_unbound_local_error_when_cooling_time_non_positive_first_iteration(
        self,
    ):
        """cooling_time <= 0 dès la 1ère itération ne doit pas lever d'exception.

        time_remaining=0.0 garantit que cooling_time = time_remaining - duree_relance
        est négatif ou nul dès la première itération (duree_relance initial >= 0.1),
        ce qui déclenche le break avant tout calcul de tint_at_start.
        """
        solver = ThermalSolver()

        duree, iterations = solver._calculate_with_cooling_prediction(
            tint=20.0,
            text=5.0,
            tsp=21.0,
            rcth=10.0,
            rpth=5.0,
            time_remaining=0.0,
            max_duration=0.0,
        )

        assert duree == 0.0
        assert iterations >= 1
