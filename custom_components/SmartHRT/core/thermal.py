"""Modèle thermique Pure Python pour SmartHRT.

ADR-026: Extraction du modèle thermique en Pure Python.
ADR-031: Optimisation algorithmique avec convergence adaptative.
ADR-054: TOUTES LES TEMPÉRATURES DOIVENT ÊTRE EN CELSIUS.

Ce module contient la classe ThermalSolver qui implémente tous les calculs
de physique thermique sans aucune dépendance à Home Assistant:
- Calcul du temps de relance (ADR-005, ADR-022, ADR-031)
- Interpolation selon le vent (ADR-007)
- Apprentissage des coefficients (ADR-006)
- Calcul du windchill

IMPORTANT (ADR-054): Ce module utilise exclusivement le système métrique (Celsius).
La conversion depuis/vers Fahrenheit est de la responsabilité de l'appelant
(voir coordinator.py: _normalize_to_celsius).
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, time as dt_time
from typing import TYPE_CHECKING, Tuple

from .types import (
    ThermalState,
    ThermalCoefficients,
    ThermalConfig,
    RecoveryResult,
    CoefficientUpdateResult,
    PhysicsGuardResult,
    PhysicsValidation,
)


# ADR-050: Fonction de validation des contraintes physiques
def validate_recovery_physics(
    interior_temp: float | None,
    exterior_temp: float | None,
    target_temp: float,
    rcth: float,
) -> PhysicsValidation:
    """Valide les contraintes physiques pour le calcul de recovery.

    ADR-050: Gardes physiques explicites avant les calculs.
    ADR-054: TOUTES LES TEMPÉRATURES DOIVENT ÊTRE EN CELSIUS.

    Args:
        interior_temp: Température intérieure actuelle en °C (ou None)
        exterior_temp: Température extérieure en °C (ou None)
        target_temp: Température cible en °C
        rcth: Constante de temps thermique (heures)

    Returns:
        PhysicsValidation avec le résultat et un message explicatif.
    """
    # Garde 0: Données manquantes
    if interior_temp is None:
        return PhysicsValidation(
            PhysicsGuardResult.MISSING_DATA,
            "Température intérieure non disponible",
            suggested_value=None,
        )

    if exterior_temp is None:
        return PhysicsValidation(
            PhysicsGuardResult.MISSING_DATA,
            "Température extérieure non disponible",
            suggested_value=None,
        )

    # Garde 1: Coefficient valide
    if rcth <= 0:
        return PhysicsValidation(
            PhysicsGuardResult.INVALID_COEFFICIENT,
            f"rcth doit être positif, reçu: {rcth}",
        )

    # Garde 2: Déjà à température cible
    if interior_temp >= target_temp:
        return PhysicsValidation(
            PhysicsGuardResult.ALREADY_AT_TARGET,
            f"Température intérieure ({interior_temp:.1f}°C) >= cible ({target_temp:.1f}°C)",
            suggested_value=0.0,  # Pas de temps de récupération nécessaire
        )

    # Garde 3: Pas de perte thermique (extérieur plus chaud que l'intérieur)
    if exterior_temp >= interior_temp:
        return PhysicsValidation(
            PhysicsGuardResult.NO_HEAT_LOSS,
            f"Extérieur ({exterior_temp:.1f}°C) >= intérieur ({interior_temp:.1f}°C)",
            suggested_value=0.0,  # Chauffage passif par l'extérieur
        )

    # Garde 4: Cible inatteignable (extérieur plus chaud que la cible)
    if target_temp <= exterior_temp:
        return PhysicsValidation(
            PhysicsGuardResult.TARGET_UNREACHABLE,
            f"Cible ({target_temp:.1f}°C) <= extérieur ({exterior_temp:.1f}°C)",
        )

    return PhysicsValidation(PhysicsGuardResult.VALID)


class ThermalSolver:
    """Solveur thermique Pure Python (ADR-026, ADR-031, ADR-054).

    Implémente tous les calculs de physique thermique:
    - calculate_recovery_duration: temps nécessaire pour atteindre la consigne
      avec convergence adaptative (ADR-031)
    - calculate_windchill: température ressentie
    - interpolate_for_wind: interpolation des coefficients selon le vent
    - update_coefficients: apprentissage avec relaxation (ADR-006)
    - calculate_rcth_fast: RCth dynamique pendant refroidissement
    - calculate_rcth_at_recovery: RCth au moment de la relance
    - calculate_rpth_at_recovery: RPth à la fin de la relance

    Cette classe ne dépend d'aucun élément Home Assistant et peut être
    testée unitairement avec des données synthétiques.

    ADR-031: Optimisation algorithmique avec critère de convergence adaptatif.

    IMPORTANT (ADR-054): TOUTES les méthodes de ce solveur attendent des
    températures en CELSIUS. La conversion depuis Fahrenheit doit être
    effectuée par l'appelant (SmartHRTCoordinator._normalize_to_celsius).
    Les formules physiques (windchill, coefficients thermiques) sont calibrées
    pour le système métrique et ne doivent pas être modifiées.
    """

    def __init__(
        self,
        config: ThermalConfig | None = None,
        logger: logging.Logger | None = None,
        log_prefix: str = "",
    ) -> None:
        """Initialise le solveur avec une configuration optionnelle.

        Args:
            config: Configuration statique (seuils de vent, etc.)
                    Si None, utilise les valeurs par défaut.
            logger: Logger à utiliser pour les messages de debug/warning.
                    Si None, utilise un NullHandler (pas de logs).
            log_prefix: Préfixe pour les logs (ex: "[SmartHRT Chambre#xxx]").
                        Permet d'identifier l'instance émettrice.
        """
        self.config = config or ThermalConfig()
        self._logger = logger or logging.getLogger(__name__)
        self._log_prefix = log_prefix

    # ─────────────────────────────────────────────────────────────────────────
    # Calcul du windchill (température ressentie)
    # ─────────────────────────────────────────────────────────────────────────

    def calculate_windchill(self, temp_celsius: float, wind_speed_ms: float) -> float:
        """Calcule la température ressentie (windchill).

        Utilise la formule JAG/TI (Joint Action Group for Temperature Indices):
        - Active si temp < 10°C et vent > 1.34 m/s (4.824 km/h)
        - Sinon retourne la température brute

        Args:
            temp_celsius: Température de l'air en °C
            wind_speed_ms: Vitesse du vent en m/s

        Returns:
            Température ressentie en °C, arrondie à 0.1°C
        """
        wind_kmh = wind_speed_ms * 3.6

        # Formule de windchill (JAG/TI)
        # Active si temp < 10°C et vent > 1.34 m/s (4.824 km/h)
        if temp_celsius < 10 and wind_speed_ms > 1.34:
            windchill = (
                13.12
                + 0.6215 * temp_celsius
                - 11.37 * wind_kmh**0.16
                + 0.3965 * temp_celsius * wind_kmh**0.16
            )
            return round(windchill, 1)
        else:
            return temp_celsius

    # ─────────────────────────────────────────────────────────────────────────
    # ADR-007: Interpolation linéaire selon le vent
    # ─────────────────────────────────────────────────────────────────────────

    def interpolate_for_wind(
        self,
        value_low_wind: float,
        value_high_wind: float,
        wind_kmh: float,
    ) -> float:
        """Interpole une valeur en fonction du vent (ADR-007).

        Pour une vitesse de vent donnée, calcule une valeur interpolée
        entre la valeur par vent faible et la valeur par vent fort.

        Args:
            value_low_wind: Valeur à utiliser par vent faible (WIND_LOW)
            value_high_wind: Valeur à utiliser par vent fort (WIND_HIGH)
            wind_kmh: Vitesse du vent actuelle en km/h

        Returns:
            Valeur interpolée, minimum 0.1
        """
        wind_low = self.config.wind_low_kmh
        wind_high = self.config.wind_high_kmh

        # Clamp la vitesse du vent entre les bornes
        wind_clamped = max(wind_low, min(wind_high, wind_kmh))

        # Ratio: 1.0 à wind_low (utilise low), 0.0 à wind_high (utilise high)
        ratio = (wind_high - wind_clamped) / (wind_high - wind_low)

        # Interpolation linéaire
        result = value_high_wind + (value_low_wind - value_high_wind) * ratio

        return max(self.config.coef_min, result)

    def get_interpolated_rcth(
        self, coefficients: ThermalCoefficients, wind_kmh: float
    ) -> float:
        """Retourne RCth interpolé selon le vent."""
        return self.interpolate_for_wind(
            coefficients.rcth_lw, coefficients.rcth_hw, wind_kmh
        )

    def get_interpolated_rpth(
        self, coefficients: ThermalCoefficients, wind_kmh: float
    ) -> float:
        """Retourne RPth interpolé selon le vent."""
        return self.interpolate_for_wind(
            coefficients.rpth_lw, coefficients.rpth_hw, wind_kmh
        )

    # ─────────────────────────────────────────────────────────────────────────
    # ADR-005, ADR-022, ADR-031, ADR-050, ADR-054: Calcul du temps de relance
    # ─────────────────────────────────────────────────────────────────────────

    def calculate_recovery_duration(
        self,
        state: ThermalState,
        coefficients: ThermalCoefficients,
        now: datetime,
    ) -> RecoveryResult:
        """Calcule l'heure de démarrage de la relance (ADR-005, ADR-022, ADR-031).

        ADR-050: Utilise des gardes physiques explicites pour valider les
        contraintes avant le calcul au lieu de try/except génériques.
        ADR-054: TOUTES les températures dans ThermalState DOIVENT être en °C.
        La conversion depuis Fahrenheit est de la responsabilité de l'appelant.

        Utilise les prévisions météo et un algorithme itératif avec convergence
        adaptative pour affiner la prédiction. Le calcul prend en compte:
        - La température intérieure actuelle
        - Les prévisions météo (température, vent)
        - Les coefficients RCth/RPth interpolés selon le vent

        ADR-031: Critère de convergence adaptatif (arrêt précoce si delta < seuil).

        Args:
            state: État thermique actuel
            coefficients: Coefficients thermiques appris
            now: Instant actuel (datetime)

        Returns:
            RecoveryResult avec l'heure de démarrage et la durée estimée
        """
        # Utiliser les prévisions météo (avec fallback)
        text = (
            state.temperature_forecast_avg
            if state.temperature_forecast_avg
            else (state.exterior_temp or 0.0)
        )
        tsp = state.tsp

        # Utiliser les prévisions de vent
        wind_kmh = (
            state.wind_speed_forecast_avg_kmh
            if state.wind_speed_forecast_avg_kmh
            else (state.wind_speed_ms * 3.6)
        )

        rcth = self.get_interpolated_rcth(coefficients, wind_kmh)
        rpth = self.get_interpolated_rpth(coefficients, wind_kmh)

        # Calculer l'heure cible (target_hour)
        target_dt = now.replace(
            hour=state.target_hour.hour,
            minute=state.target_hour.minute,
            second=0,
            microsecond=0,
        )
        if target_dt < now:
            target_dt += timedelta(days=1)

        # ADR-050: Validation physique explicite
        # Note: On utilise la température prévue (text) pour la validation
        tint = state.interior_temp if state.interior_temp is not None else 17.0
        validation = validate_recovery_physics(
            interior_temp=state.interior_temp,
            exterior_temp=text if text else None,
            target_temp=tsp,
            rcth=rcth,
        )

        # Log de diagnostic détaillé pour non-régression (TC-PRED)
        self._logger.info(
            "%s [TC-PRED] Recovery prediction: "
            "tint=%.2f°C, text=%.2f°C, tsp=%.2f°C, "
            "rcth=%.2f, rpth=%.2f, target_time=%s, validation_status=%s",
            self._log_prefix,
            tint,
            text,
            tsp,
            rcth,
            rpth,
            state.target_hour.strftime("%H:%M:%S"),
            validation.result.name,
        )

        time_remaining = (target_dt - now).total_seconds() / 3600
        max_duration = max(time_remaining - 1 / 6, 0)  # 10 min de marge

        # ADR-050: Gestion des cas spéciaux selon la validation
        # NOTE: ALREADY_AT_TARGET n'est PAS un cas d'arrêt en mode MONITORING
        # car la température va baisser (chauffage coupé). On doit anticiper.
        if validation.result == PhysicsGuardResult.ALREADY_AT_TARGET:
            # La température actuelle >= TSP, mais le chauffage est coupé
            # La température va baisser vers text (extérieur plus froid)
            # On doit calculer quand démarrer pour remonter à TSP à target_hour
            if text < tint:
                # Il y aura des pertes thermiques → continuer le calcul avec prédiction
                self._logger.info(
                    "%s ADR-050: %s mais text=%.1f°C < tint → prédiction de refroidissement",
                    self._log_prefix,
                    validation.message,
                    text,
                )
                # Ne pas retourner, laisser le calcul se poursuivre
            else:
                # Extérieur plus chaud que TSP → pas besoin de relance
                self._logger.info(
                    "%s ADR-050: %s et text >= tint → démarrage immédiat (now=%s)",
                    self._log_prefix,
                    validation.message,
                    now.strftime("%H:%M:%S"),
                )
                return RecoveryResult(
                    recovery_start_hour=now,
                    duration_hours=0.0,
                )

        if validation.result == PhysicsGuardResult.NO_HEAT_LOSS:
            # Extérieur plus chaud → chauffage passif
            self._logger.info(
                "%s ADR-050: %s - pas de relance nécessaire (target_dt=%s)",
                self._log_prefix,
                validation.message,
                target_dt.strftime("%H:%M"),
            )
            return RecoveryResult(
                recovery_start_hour=target_dt,
                duration_hours=0.0,
            )

        if validation.result == PhysicsGuardResult.MISSING_DATA:
            # Données manquantes → utiliser valeur par défaut sécuritaire
            self._logger.warning(
                "%s ADR-050: %s - utilisation de tint=17°C par défaut",
                self._log_prefix,
                validation.message,
            )
            tint = 17.0  # Fallback déjà appliqué, mais on log

        if validation.result in (
            PhysicsGuardResult.TARGET_UNREACHABLE,
            PhysicsGuardResult.INVALID_COEFFICIENT,
        ):
            # Cas d'erreur → retourner un résultat safe (démarrage à target)
            self._logger.warning(
                "%s ADR-050: Calcul impossible - %s",
                self._log_prefix,
                validation.message,
            )
            return RecoveryResult(
                recovery_start_hour=target_dt,
                duration_hours=0.0,
            )

        # ADR-050: Calcul sûr - les gardes garantissent la validité mathématique
        # En mode prédiction (MONITORING), on doit d'abord estimer la température
        # au moment de la relance, puis calculer le temps de chauffage nécessaire

        # Si tint >= tsp actuellement, calculer quand tint aura baissé suffisamment
        if tint >= tsp and text < tint:
            # Prédiction de refroidissement: T(t) = text + (tint - text) * e^(-t/rcth)
            # On prédit la température à différents instants jusqu'à target_hour
            # et on calcule quand démarrer la relance
            duree_relance, iterations = self._calculate_with_cooling_prediction(
                tint=tint,
                text=text,
                tsp=tsp,
                rcth=rcth,
                rpth=rpth,
                time_remaining=time_remaining,
                max_duration=max_duration,
            )
        else:
            # Cas normal: tint < tsp, calcul direct de la durée de relance
            ratio = (rpth + text - tint) / (rpth + text - tsp)
            # Clamp ratio pour éviter log(0) même après gardes (double sécurité)
            ratio = max(ratio, 0.001)
            duree_relance = min(max(rcth * math.log(ratio), 0), max_duration)

            # ADR-031: Prédiction itérative avec convergence adaptative
            duree_relance, iterations = self._calculate_with_convergence(
                tint=tint,
                text=text,
                tsp=tsp,
                rcth=rcth,
                rpth=rpth,
                time_remaining=time_remaining,
                max_duration=max_duration,
                initial_estimate=duree_relance,
            )

        recovery_start_hour = target_dt - timedelta(seconds=int(duree_relance * 3600))

        # Log final détaillé pour non-régression (TC-PRED)
        self._logger.info(
            "%s [TC-PRED] Recovery result: "
            "duration_hours=%.2f, start_time=%s, iterations=%d, "
            "tint=%.2f°C, text=%.2f°C, tsp=%.2f°C, rcth=%.2f",
            self._log_prefix,
            duree_relance,
            recovery_start_hour.strftime("%H:%M"),
            iterations,
            tint,
            text,
            tsp,
            rcth,
        )

        return RecoveryResult(
            recovery_start_hour=recovery_start_hour,
            duration_hours=duree_relance,
        )

    def _calculate_with_convergence(
        self,
        tint: float,
        text: float,
        tsp: float,
        rcth: float,
        rpth: float,
        time_remaining: float,
        max_duration: float,
        initial_estimate: float,
    ) -> tuple[float, int]:
        """Calcul itératif avec critère de convergence (ADR-031, ADR-050).

        ADR-050: Les gardes physiques sont validées en amont, ce qui garantit
        que rcth > 0 et que les températures sont cohérentes. Les gardes
        internes protègent contre les cas limites numériques.

        Args:
            tint: Température intérieure actuelle
            text: Température extérieure moyenne prévue
            tsp: Température de consigne
            rcth: Coefficient RCth interpolé
            rpth: Coefficient RPth interpolé
            time_remaining: Temps restant avant target (heures)
            max_duration: Durée maximale autorisée (heures)
            initial_estimate: Estimation initiale de la durée

        Returns:
            Tuple (durée de relance calculée, nombre d'itérations)
        """
        duree_relance = initial_estimate
        prev_estimate = float("inf")
        converged = False
        iterations = 0

        for iteration in range(self.config.max_iterations):
            iterations = iteration + 1

            # ADR-050: Garde contre division par zéro (rcth garanti > 0 par validation amont)
            exponent = (time_remaining - duree_relance) / rcth
            # Garde contre overflow exponentiel
            exponent = max(-100, min(100, exponent))

            # Estimer la température intérieure au moment du démarrage
            exp_factor = math.exp(exponent)
            tint_start = text + (tint - text) / exp_factor

            # ADR-050: Garde contre division par zéro
            denominator = rpth + text - tsp
            if abs(denominator) < 0.001:
                self._logger.debug(
                    "%s ADR-050: Dénominateur proche de zéro (%f), arrêt itération %d",
                    self._log_prefix,
                    denominator,
                    iteration + 1,
                )
                break

            ratio = (rpth + text - tint_start) / denominator

            # ADR-050: Garde contre log de valeur non positive
            if ratio <= 0.001:
                self._logger.debug(
                    "%s ADR-050: Ratio non valide (%.4f), arrêt itération %d",
                    self._log_prefix,
                    ratio,
                    iteration + 1,
                )
                break

            # Moyenne pondérée pour éviter les oscillations
            new_estimate = min(
                (duree_relance + 2 * max(rcth * math.log(ratio), 0)) / 3,
                max_duration,
            )

            # ADR-031: Vérifier la convergence
            if abs(new_estimate - prev_estimate) < self.config.convergence_threshold:
                self._logger.debug(
                    "%s Convergence atteinte en %d itérations (delta=%.4f h)",
                    self._log_prefix,
                    iteration + 1,
                    abs(new_estimate - prev_estimate),
                )
                converged = True
                duree_relance = new_estimate
                break

            prev_estimate = duree_relance
            duree_relance = new_estimate

        if not converged:
            self._logger.warning(
                "%s Max itérations (%d) atteint sans convergence (threshold=%.3f h)",
                self._log_prefix,
                self.config.max_iterations,
                self.config.convergence_threshold,
            )

        return duree_relance, iterations

    def _calculate_with_cooling_prediction(
        self,
        tint: float,
        text: float,
        tsp: float,
        rcth: float,
        rpth: float,
        time_remaining: float,
        max_duration: float,
    ) -> tuple[float, int]:
        """Calcul avec prédiction de refroidissement (tint >= tsp actuellement).

        Quand la température intérieure est >= consigne mais que le chauffage
        est coupé (mode MONITORING), la température va baisser. On doit prédire
        quand démarrer la relance pour atteindre TSP à target_hour.

        Algorithme itératif :
        1. Estimer une durée de relance initiale
        2. Calculer la température prédite au moment du démarrage de relance
           T_start = text + (tint - text) * e^(-(time_remaining - duree)/rcth)
        3. Calculer la durée de relance depuis T_start jusqu'à TSP
        4. Itérer jusqu'à convergence

        Args:
            tint: Température intérieure actuelle (>= tsp)
            text: Température extérieure moyenne prévue
            tsp: Température de consigne
            rcth: Coefficient de refroidissement
            rpth: Coefficient de réchauffement
            time_remaining: Temps restant avant target (heures)
            max_duration: Durée maximale autorisée (heures)

        Returns:
            Tuple (durée de relance calculée, nombre d'itérations)
        """
        # Estimation initiale : temps pour remonter de text à tsp
        # (cas le plus pessimiste où on aurait refroidi jusqu'à text)
        ratio_init = (rpth + text - text) / (rpth + text - tsp) if rpth > 0 else 1.0
        ratio_init = max(ratio_init, 0.001)
        duree_relance = min(max(rcth * math.log(ratio_init), 0.1), max_duration)

        prev_estimate = float("inf")
        iterations = 0

        for iteration in range(self.config.max_iterations):
            iterations = iteration + 1

            # Temps de refroidissement avant le démarrage de la relance
            cooling_time = time_remaining - duree_relance
            if cooling_time <= 0:
                # Pas assez de temps pour refroidir, démarrage immédiat
                duree_relance = time_remaining
                break

            # Température prédite au moment du démarrage de la relance
            # T(t) = text + (tint - text) * e^(-t/rcth)
            exponent = -cooling_time / rcth
            exponent = max(-100, min(100, exponent))  # Garde contre overflow
            tint_at_start = text + (tint - text) * math.exp(exponent)

            self._logger.debug(
                "%s Cooling prediction iter %d: cooling_time=%.2fh, tint_at_start=%.1f°C",
                self._log_prefix,
                iterations,
                cooling_time,
                tint_at_start,
            )

            # Si la température prédite est encore >= TSP, pas besoin de relance
            if tint_at_start >= tsp:
                # La température ne baissera pas assez, on démarre à target_hour
                duree_relance = 0.0
                break

            # Calculer la durée de relance depuis tint_at_start jusqu'à TSP
            denominator = rpth + text - tsp
            if abs(denominator) < 0.001:
                break

            ratio = (rpth + text - tint_at_start) / denominator
            if ratio <= 0.001:
                break

            new_estimate = min(max(rcth * math.log(ratio), 0), max_duration)

            # Moyenne pondérée pour éviter les oscillations
            new_estimate = (duree_relance + 2 * new_estimate) / 3

            # Vérifier la convergence
            if abs(new_estimate - prev_estimate) < self.config.convergence_threshold:
                self._logger.debug(
                    "%s Cooling prediction convergence en %d itérations",
                    self._log_prefix,
                    iterations,
                )
                duree_relance = new_estimate
                break

            prev_estimate = duree_relance
            duree_relance = new_estimate

        self._logger.info(
            "%s Cooling prediction: durée=%.2fh après %d itérations (tint=%.1f → %.1f°C)",
            self._log_prefix,
            duree_relance,
            iterations,
            tint,
            tint_at_start if iterations > 0 else tint,
        )

        return duree_relance, iterations

    def calculate_recovery_update_time(
        self,
        recovery_start_hour: datetime,
        now: datetime,
    ) -> datetime | None:
        """Calcule l'heure de la prochaine mise à jour du calcul de relance.

        La logique:
        - Reconstruit recoverystart_time à partir de l'heure de recovery_start_hour
        - Calcule le temps restant avant la relance
        - Reprogramme dans max(time_remaining/3, 0) secondes, plafonné à 1200s (20min)
        - À moins de 30min avant la relance, arrête en programmant dans 3600s

        Args:
            recovery_start_hour: Heure prévue de démarrage de la relance
            now: Instant actuel

        Returns:
            Datetime de la prochaine mise à jour, ou None si non calculable
        """
        if recovery_start_hour is None:
            return None

        # Reconstruire recoverystart_time depuis l'heure
        recovery_hour = recovery_start_hour.hour
        recovery_minute = recovery_start_hour.minute
        recoverystart_time = now.replace(
            hour=recovery_hour,
            minute=recovery_minute,
            second=0,
            microsecond=0,
        )
        if recoverystart_time < now:
            recoverystart_time += timedelta(days=1)

        time_remaining = (recoverystart_time - now).total_seconds()

        # Recalcule pas plus tard que dans 1200s (20min)
        # À moins de 30min avant la relance on arrête
        if time_remaining < 1800:
            seconds = 3600  # Impose un calcul après la relance
        else:
            seconds = min(max(time_remaining / 3, 0), 1200)

        return now + timedelta(seconds=seconds)

    # ─────────────────────────────────────────────────────────────────────────
    # Calcul dynamique des coefficients
    # ─────────────────────────────────────────────────────────────────────────

    def calculate_rcth_fast(
        self,
        interior_temp: float,
        exterior_temp: float,
        temp_at_start: float,
        text_at_start: float,
        time_since_start_hours: float,
    ) -> float | None:
        """Calcule l'évolution dynamique de RCth pendant le refroidissement.

        Ce calcul permet de suivre l'évolution du coefficient thermique
        en temps réel pendant la phase de refroidissement.

        Args:
            interior_temp: Température intérieure actuelle (°C)
            exterior_temp: Température extérieure actuelle (°C)
            temp_at_start: Température intérieure au début du refroidissement (°C)
            text_at_start: Température extérieure au début du refroidissement (°C)
            time_since_start_hours: Temps écoulé depuis le début (heures)

        Returns:
            RCth calculé dynamiquement, ou None si calcul impossible
        """
        if time_since_start_hours < 0:
            time_since_start_hours += 24

        avg_text = (text_at_start + exterior_temp) / 2

        if interior_temp < temp_at_start and interior_temp > avg_text:
            try:
                rcth_fast = time_since_start_hours / max(
                    0.0001,
                    math.log((avg_text - temp_at_start) / (avg_text - interior_temp)),
                )
                return rcth_fast
            except (ValueError, ZeroDivisionError):
                return None
        return None

    def calculate_rcth_at_recovery(
        self,
        temp_recovery_calc: float,
        temp_recovery_start: float,
        text_recovery_calc: float,
        text_recovery_start: float,
        time_recovery_calc: datetime,
        time_recovery_start: datetime,
    ) -> float | None:
        """Calcule RCth au démarrage de la relance.

        Ce calcul utilise les températures et timestamps de référence
        pour déterminer le coefficient de refroidissement réel.

        Args:
            temp_recovery_calc: Température intérieure au début du refroidissement
            temp_recovery_start: Température intérieure au démarrage de la relance
            text_recovery_calc: Température extérieure au début du refroidissement
            text_recovery_start: Température extérieure au démarrage de la relance
            time_recovery_calc: Timestamp du début du refroidissement
            time_recovery_start: Timestamp du démarrage de la relance

        Returns:
            RCth calculé, ou None si calcul impossible
        """
        dt_hours = (
            time_recovery_start.timestamp() - time_recovery_calc.timestamp()
        ) / 3600
        avg_text = (text_recovery_start + text_recovery_calc) / 2

        try:
            rcth = min(
                self.config.coef_max,
                dt_hours
                / math.log(
                    (avg_text - temp_recovery_calc) / (avg_text - temp_recovery_start)
                ),
            )
            # Log détaillé pour non-régression (TC-CALIB-RCth)
            self._logger.info(
                "%s [TC-CALIB-RCTH] RCth calibration: "
                "tint_start=%.2f°C, tint_end=%.2f°C, "
                "text_start=%.2f°C, text_end=%.2f°C, "
                "duration_minutes=%.1f, rcth_calculated=%.2f",
                self._log_prefix,
                temp_recovery_calc,
                temp_recovery_start,
                text_recovery_calc,
                text_recovery_start,
                dt_hours * 60,
                rcth,
            )
            return rcth
        except (ValueError, ZeroDivisionError) as e:
            self._logger.warning(
                "%s [TC-CALIB-RCTH] RCth calculation failed: %s",
                self._log_prefix,
                str(e),
            )
            return None

    def calculate_rpth_at_recovery(
        self,
        temp_recovery_start: float,
        temp_recovery_end: float,
        text_recovery_start: float,
        text_recovery_end: float,
        time_recovery_start: datetime,
        time_recovery_end: datetime,
        rcth_interpolated: float,
    ) -> float | None:
        """Calcule RPth à la fin de la relance.

        Ce calcul utilise les températures et timestamps de référence
        ainsi que le RCth interpolé pour déterminer le coefficient
        de puissance de chauffage réel.

        Args:
            temp_recovery_start: Température intérieure au démarrage de la relance
            temp_recovery_end: Température intérieure à la fin de la relance
            text_recovery_start: Température extérieure au démarrage de la relance
            text_recovery_end: Température extérieure à la fin de la relance
            time_recovery_start: Timestamp du démarrage de la relance
            time_recovery_end: Timestamp de la fin de la relance
            rcth_interpolated: RCth interpolé selon le vent

        Returns:
            RPth calculé, ou None si calcul impossible
        """
        dt_hours = (
            time_recovery_end.timestamp() - time_recovery_start.timestamp()
        ) / 3600
        avg_text = (text_recovery_start + text_recovery_end) / 2

        try:
            exp_term = math.exp(dt_hours / rcth_interpolated)
            numerator = (avg_text - temp_recovery_end) * exp_term - (
                avg_text - temp_recovery_start
            )
            rpth = min(
                self.config.coef_max,
                max(self.config.coef_min, numerator / (1 - exp_term)),
            )
            # Log détaillé pour non-régression (TC-CALIB-RPth)
            self._logger.info(
                "%s [TC-CALIB-RPTH] RPth calibration: "
                "tint_start=%.2f°C, tint_end=%.2f°C, "
                "text_start=%.2f°C, text_end=%.2f°C, "
                "duration_minutes=%.1f, rcth_interpolated=%.2f, rpth_calculated=%.2f",
                self._log_prefix,
                temp_recovery_start,
                temp_recovery_end,
                text_recovery_start,
                text_recovery_end,
                dt_hours * 60,
                rcth_interpolated,
                rpth,
            )
            return rpth
        except (ValueError, ZeroDivisionError) as e:
            self._logger.warning(
                "%s [TC-CALIB-RPTH] RPth calculation failed: %s",
                self._log_prefix,
                str(e),
            )
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # ADR-006: Apprentissage des coefficients avec relaxation
    # ADR-044: Protection contre les valeurs aberrantes (outliers)
    # ─────────────────────────────────────────────────────────────────────────

    def update_coefficients(
        self,
        coef_type: str,
        current_lw: float,
        current_hw: float,
        current_main: float,
        calculated_value: float,
        wind_kmh: float,
        relaxation_factor: float,
    ) -> CoefficientUpdateResult:
        """Met à jour les coefficients avec relaxation (ADR-006) et protection outliers (ADR-044).

        Ce calcul:
        1. Vérifie si la valeur calculée est un outlier (ADR-044)
        2. Calcule l'erreur entre valeur mesurée et interpolée
        3. Applique une formule de mise à jour pour rcth_lw/hw ou rpth_lw/hw
        4. Utilise la relaxation pour éviter les oscillations

        Args:
            coef_type: Type de coefficient ("rcth" ou "rpth")
            current_lw: Valeur actuelle low wind
            current_hw: Valeur actuelle high wind
            current_main: Valeur principale actuelle
            calculated_value: Valeur mesurée/calculée
            wind_kmh: Vitesse du vent en km/h
            relaxation_factor: Facteur de relaxation

        Returns:
            CoefficientUpdateResult avec les nouvelles valeurs
        """
        wind_low = self.config.wind_low_kmh
        wind_high = self.config.wind_high_kmh
        coef_min = self.config.coef_min
        coef_max = self.config.coef_max

        # ADR-044: Protection contre les valeurs aberrantes
        outlier_detected = False
        outlier_clamped = False
        original_calculated = calculated_value

        if current_main > 0:
            deviation_percent = (
                abs(calculated_value - current_main) / current_main * 100
            )

            if deviation_percent > self.config.outlier_threshold_percent:
                outlier_detected = True
                # Log détaillé pour non-régression (TC-SAFE)
                self._logger.warning(
                    "%s [TC-SAFE] Outlier détecté pour %s: "
                    "calculated_raw=%.2f, current_memory=%.2f, "
                    "outlier_threshold_percent=%.1f, deviation_percent=%.1f%%",
                    self._log_prefix,
                    coef_type,
                    calculated_value,
                    current_main,
                    self.config.outlier_threshold_percent,
                    deviation_percent,
                )

                if self.config.outlier_mode == "reject":
                    # Mode reject: ignorer complètement la mise à jour
                    self._logger.info(
                        "%s Mise à jour rejetée pour %s (mode reject)",
                        self._log_prefix,
                        coef_type,
                    )
                    return CoefficientUpdateResult(
                        coef_lw=current_lw,
                        coef_hw=current_hw,
                        coef_main=current_main,
                        error=0.0,
                        outlier_detected=True,
                        outlier_clamped=False,
                        original_calculated=original_calculated,
                    )
                else:
                    # Mode clamp: plafonner la valeur
                    threshold = self.config.outlier_threshold_percent / 100
                    max_allowed = current_main * (1 + threshold)
                    min_allowed = current_main * (1 - threshold)
                    clamped_value = max(min_allowed, min(max_allowed, calculated_value))
                    outlier_clamped = True
                    # Log détaillé pour non-régression (TC-SAFE)
                    self._logger.info(
                        "%s [TC-SAFE] Valeur plafonnée pour %s: "
                        "action=CLAMP_VALUE, clamped_to=%.2f (min=%.2f, max=%.2f)",
                        self._log_prefix,
                        coef_type,
                        clamped_value,
                        min_allowed,
                        max_allowed,
                    )
                    calculated_value = clamped_value

        # Position relative du vent entre les bornes (centré sur 0)
        x = (wind_kmh - wind_low) / (wind_high - wind_low) - 0.5
        relax = relaxation_factor

        # Valeur interpolée actuelle
        interpol = max(coef_min, current_lw + (current_hw - current_lw) * (x + 0.5))

        # Erreur observée
        err = calculated_value - interpol

        # Formules de mise à jour (polynômes cubiques pour répartition lw/hw)
        lw_new = max(
            coef_min,
            current_lw + err * (1 - 5 / 3 * x - 2 * x * x + 8 / 3 * x * x * x),
        )
        hw_new = max(
            coef_min,
            current_hw + err * (1 + 5 / 3 * x - 2 * x * x - 8 / 3 * x * x * x),
        )

        # Application de la relaxation
        new_lw = min(coef_max, (current_lw + relax * lw_new) / (1 + relax))
        new_hw = (current_hw + relax * hw_new) / (1 + relax)

        # Contrainte: hw <= lw (plus de pertes thermiques par vent fort)
        new_hw = min(new_lw, new_hw)

        # Mise à jour du coefficient principal avec relaxation
        new_main = (current_main + relax * calculated_value) / (1 + relax)

        # Appliquer les limites selon le type
        if coef_type == "rpth":
            new_main = min(coef_max, max(coef_min, new_main))

        final_main = max(coef_min, new_main)

        # Log final pour non-régression (TC-SAFE si outlier)
        if outlier_detected:
            self._logger.info(
                "%s [TC-SAFE] Coefficient final pour %s: "
                "final_%s=%.2f (après relaxation factor=%.1f)",
                self._log_prefix,
                coef_type,
                coef_type,
                final_main,
                relaxation_factor,
            )

        return CoefficientUpdateResult(
            coef_lw=new_lw,
            coef_hw=new_hw,
            coef_main=final_main,
            error=round(err, 3),
            outlier_detected=outlier_detected,
            outlier_clamped=outlier_clamped,
            original_calculated=original_calculated if outlier_detected else None,
        )
