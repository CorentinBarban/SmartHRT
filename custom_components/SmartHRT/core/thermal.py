"""Calculs thermiques SmartHRT (ThermalSolver), sans dépendance à Home Assistant.

Toutes les températures sont en °C ; la conversion Fahrenheit incombe à l'appelant.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from .types import (
    CoefficientUpdateResult,
    PhysicsGuardResult,
    PhysicsValidation,
    RecoveryResult,
    ThermalCoefficients,
    ThermalConfig,
    ThermalState,
)


def validate_recovery_physics(
    interior_temp: float | None,
    exterior_temp: float | None,
    target_temp: float,
    rcth: float,
) -> PhysicsValidation:
    """Valide les contraintes physiques avant le calcul de recovery (températures en °C).

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
    """Solveur thermique : temps de relance, windchill, interpolation vent, apprentissage RCth/RPth.

    Toutes les méthodes attendent des températures en °C (conversion Fahrenheit
    par l'appelant, cf. SmartHRTCoordinator._normalize_to_celsius) : les formules
    sont calibrées pour le système métrique.
    """

    def __init__(
        self,
        config: ThermalConfig | None = None,
        logger: logging.Logger | None = None,
        log_prefix: str = "",
    ) -> None:
        """Initialise le solveur (config par défaut si None, log_prefix identifie l'instance)."""
        self.config = config or ThermalConfig()
        self._logger = logger or logging.getLogger(__name__)
        self._log_prefix = log_prefix

    # ─────────────────────────────────────────────────────────────────────────
    # Calcul du windchill (température ressentie)
    # ─────────────────────────────────────────────────────────────────────────

    def calculate_windchill(self, temp_celsius: float, wind_speed_ms: float) -> float:
        """Calcule la température ressentie (formule JAG/TI).

        Active si temp < 10°C et vent > 1.34 m/s (4.824 km/h), sinon retourne
        la température brute. Retour en °C arrondi à 0.1.
        """
        wind_kmh = wind_speed_ms * 3.6

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
    # Interpolation linéaire selon le vent
    # ─────────────────────────────────────────────────────────────────────────

    def interpolate_for_wind(
        self,
        value_low_wind: float,
        value_high_wind: float,
        wind_kmh: float,
    ) -> float:
        """Interpole linéairement entre la valeur vent faible et vent fort (vent en km/h, résultat >= coef_min)."""
        wind_low = self.config.wind_low_kmh
        wind_high = self.config.wind_high_kmh

        # Vent borné entre les seuils faible/fort
        wind_clamped = max(wind_low, min(wind_high, wind_kmh))

        # Ratio: 1.0 à wind_low (utilise low), 0.0 à wind_high (utilise high)
        ratio = (wind_high - wind_clamped) / (wind_high - wind_low)

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
    # Calcul du temps de relance
    # ─────────────────────────────────────────────────────────────────────────

    def calculate_recovery_duration(
        self,
        state: ThermalState,
        coefficients: ThermalCoefficients,
        now: datetime,
    ) -> RecoveryResult:
        """Calcule l'heure de démarrage de la relance.

        Utilise les prévisions météo (température, vent), la température
        intérieure et les coefficients RCth/RPth interpolés selon le vent, avec
        un algorithme itératif à arrêt précoce. Des gardes physiques valident
        les entrées (températures de ThermalState en °C).
        """
        # Prévisions météo, avec repli sur la température extérieure mesurée
        text = (
            state.temperature_forecast_avg
            if state.temperature_forecast_avg
            else (state.exterior_temp or 0.0)
        )
        tsp = state.tsp

        # Prévisions de vent (km/h), avec repli sur le vent mesuré
        wind_kmh = (
            state.wind_speed_forecast_avg_kmh
            if state.wind_speed_forecast_avg_kmh
            else (state.wind_speed_ms * 3.6)
        )

        rcth = self.get_interpolated_rcth(coefficients, wind_kmh)
        rpth = self.get_interpolated_rpth(coefficients, wind_kmh)

        target_dt = now.replace(
            hour=state.target_hour.hour,
            minute=state.target_hour.minute,
            second=0,
            microsecond=0,
        )
        if target_dt < now:
            target_dt += timedelta(days=1)

        # Validation sur la température extérieure prévue (text).
        # Sans interior_temp, tint retombe sur temp_recovery_calc (dernière température connue).
        tint = (
            state.interior_temp
            if state.interior_temp is not None
            else state.temp_recovery_calc
        )
        validation = validate_recovery_physics(
            interior_temp=state.interior_temp,
            exterior_temp=text if text else None,
            target_temp=tsp,
            rcth=rcth,
        )

        # Niveau debug : ce log tourne à chaque cycle et pour chaque instance (TC-PRED).
        self._logger.debug(
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

        # ALREADY_AT_TARGET n'est pas un cas d'arrêt en mode MONITORING :
        # le chauffage est coupé, la température va baisser et il faut anticiper.
        if validation.result == PhysicsGuardResult.ALREADY_AT_TARGET:
            # tint >= TSP mais la température va baisser vers text : on calcule
            # quand démarrer pour remonter à TSP à target_hour
            if text < tint:
                self._logger.info(
                    "%s %s mais text=%.1f°C < tint → prédiction de refroidissement",
                    self._log_prefix,
                    validation.message,
                    text,
                )
            else:
                # Extérieur plus chaud que TSP → pas besoin de relance
                self._logger.info(
                    "%s %s et text >= tint → démarrage immédiat (now=%s)",
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
                "%s %s - pas de relance nécessaire (target_dt=%s)",
                self._log_prefix,
                validation.message,
                target_dt.strftime("%H:%M"),
            )
            return RecoveryResult(
                recovery_start_hour=target_dt,
                duration_hours=0.0,
            )

        if validation.result == PhysicsGuardResult.MISSING_DATA:
            # Données manquantes : valeur par défaut sécuritaire
            self._logger.warning(
                "%s %s - utilisation de tint=17°C par défaut",
                self._log_prefix,
                validation.message,
            )
            tint = 17.0

        if validation.result in (
            PhysicsGuardResult.TARGET_UNREACHABLE,
            PhysicsGuardResult.INVALID_COEFFICIENT,
        ):
            # Cas d'erreur → retourner un résultat safe (démarrage à target)
            self._logger.warning(
                "%s Calcul impossible - %s",
                self._log_prefix,
                validation.message,
            )
            return RecoveryResult(
                recovery_start_hour=target_dt,
                duration_hours=0.0,
            )

        # Les gardes garantissent la validité mathématique. Si tint >= tsp, il faut
        # d'abord prédire la température au moment de la relance, puis le temps de chauffe.
        if tint >= tsp and text < tint:
            # Refroidissement : T(t) = text + (tint - text) * e^(-t/rcth)
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
            # tint < tsp : durée de chauffe directe (loi de Newton avec RPth)
            ratio = (rpth + text - tint) / (rpth + text - tsp)
            # Borne basse pour éviter log(0) (double sécurité)
            ratio = max(ratio, 0.001)
            duree_relance = min(max(rcth * math.log(ratio), 0), max_duration)

            # Affinage itératif avec arrêt précoce sur convergence
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

        self._logger.debug(
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
        """Affine la durée de relance jusqu'à convergence.

        rcth > 0 est garanti par la validation amont ; les gardes internes
        couvrent les cas limites numériques. time_remaining et max_duration en
        heures. Retourne (durée en heures, nombre d'itérations).
        """
        duree_relance = initial_estimate
        prev_estimate = float("inf")
        converged = False
        iterations = 0

        for iteration in range(self.config.max_iterations):
            iterations = iteration + 1

            exponent = (time_remaining - duree_relance) / rcth
            # Borne contre l'overflow de exp
            exponent = max(-100, min(100, exponent))

            # Température intérieure estimée au démarrage de la relance
            exp_factor = math.exp(exponent)
            tint_start = text + (tint - text) / exp_factor

            # Garde contre la division par zéro
            denominator = rpth + text - tsp
            if abs(denominator) < 0.001:
                self._logger.debug(
                    "%s Dénominateur proche de zéro (%f), arrêt itération %d",
                    self._log_prefix,
                    denominator,
                    iteration + 1,
                )
                break

            ratio = (rpth + text - tint_start) / denominator

            # Garde contre le log d'une valeur non positive
            if ratio <= 0.001:
                self._logger.debug(
                    "%s Ratio non valide (%.4f), arrêt itération %d",
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
        """Calcule la durée de relance quand tint >= tsp et que le chauffage est coupé.

        La température va baisser ; on itère jusqu'à convergence :
        1. durée de relance initiale
        2. T_start = text + (tint - text) * e^(-(time_remaining - duree)/rcth)
        3. durée de chauffe de T_start à TSP

        Retourne (durée en heures, nombre d'itérations).
        """
        # Estimation initiale : temps pour remonter de text à tsp
        # (cas le plus pessimiste où on aurait refroidi jusqu'à text)
        ratio_init = (rpth + text - text) / (rpth + text - tsp) if rpth > 0 else 1.0
        ratio_init = max(ratio_init, 0.001)
        duree_relance = min(max(rcth * math.log(ratio_init), 0.1), max_duration)

        prev_estimate = float("inf")
        iterations = 0
        # Défini avant la boucle : un break dès la 1ère itération (cooling_time <= 0)
        # laisserait sinon tint_at_start indéfini pour le log final. Valeur par
        # défaut tint : aucun refroidissement si pas le temps de refroidir.
        tint_at_start = tint

        for iteration in range(self.config.max_iterations):
            iterations = iteration + 1

            cooling_time = time_remaining - duree_relance
            if cooling_time <= 0:
                # Pas assez de temps pour refroidir, démarrage immédiat
                duree_relance = time_remaining
                break

            # T(t) = text + (tint - text) * e^(-t/rcth)
            exponent = -cooling_time / rcth
            exponent = max(-100, min(100, exponent))  # Borne contre l'overflow
            tint_at_start = text + (tint - text) * math.exp(exponent)

            self._logger.debug(
                "%s Cooling prediction iter %d: cooling_time=%.2fh, tint_at_start=%.1f°C",
                self._log_prefix,
                iterations,
                cooling_time,
                tint_at_start,
            )

            if tint_at_start >= tsp:
                # La température ne baissera pas assez : pas de relance avant target_hour
                duree_relance = 0.0
                break

            denominator = rpth + text - tsp
            if abs(denominator) < 0.001:
                break

            ratio = (rpth + text - tint_at_start) / denominator
            if ratio <= 0.001:
                break

            new_estimate = min(max(rcth * math.log(ratio), 0), max_duration)

            # Moyenne pondérée pour éviter les oscillations
            new_estimate = (duree_relance + 2 * new_estimate) / 3

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

        self._logger.debug(
            "%s Cooling prediction: durée=%.2fh après %d itérations (tint=%.1f → %.1f°C)",
            self._log_prefix,
            duree_relance,
            iterations,
            tint,
            tint_at_start,
        )

        return duree_relance, iterations

    def calculate_recovery_update_time(
        self,
        recovery_start_hour: datetime,
        now: datetime,
    ) -> datetime | None:
        """Calcule l'heure de la prochaine mise à jour du calcul de relance.

        Reprogramme dans time_remaining/3 secondes, plafonné à 1200s (20 min) ;
        à moins de 30 min de la relance, reprogramme dans 3600s (après la relance).
        Retourne None si recovery_start_hour est None.
        """
        if recovery_start_hour is None:
            return None

        # Prochaine occurrence de l'heure de relance
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

        if time_remaining < 1800:
            seconds = 3600
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
        """Calcule RCth en temps réel pendant le refroidissement (températures en °C, durée en heures).

        Retourne None si le calcul est impossible.
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
        """Calcule le RCth réel du refroidissement entre le début du calcul et le démarrage de la relance.

        Retourne None si le calcul est impossible.
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
        """Calcule le RPth réel de la relance, à partir du RCth interpolé selon le vent.

        Retourne None si le calcul est impossible.
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
    # Apprentissage des coefficients avec relaxation et protection contre les outliers
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
        """Met à jour les coefficients lw/hw/main avec relaxation et protection outliers.

        Args:
            coef_type: "rcth" ou "rpth"
            wind_kmh: Vitesse du vent en km/h
        """
        wind_low = self.config.wind_low_kmh
        wind_high = self.config.wind_high_kmh
        coef_min = self.config.coef_min
        coef_max = self.config.coef_max

        # Valeur aberrante : écart relatif trop grand par rapport à la valeur courante
        outlier_detected = False
        outlier_clamped = False
        original_calculated = calculated_value

        if current_main > 0:
            deviation_percent = (
                abs(calculated_value - current_main) / current_main * 100
            )

            if deviation_percent > self.config.outlier_threshold_percent:
                outlier_detected = True
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
                    # reject : mise à jour ignorée
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
                    # clamp : valeur plafonnée à +/- threshold autour de la valeur courante
                    threshold = self.config.outlier_threshold_percent / 100
                    max_allowed = current_main * (1 + threshold)
                    min_allowed = current_main * (1 - threshold)
                    clamped_value = max(min_allowed, min(max_allowed, calculated_value))
                    outlier_clamped = True
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

        interpol = max(coef_min, current_lw + (current_hw - current_lw) * (x + 0.5))

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

        # Relaxation : moyenne pondérée ancienne/nouvelle valeur
        new_lw = min(coef_max, (current_lw + relax * lw_new) / (1 + relax))
        new_hw = (current_hw + relax * hw_new) / (1 + relax)

        # Contrainte: hw <= lw (plus de pertes thermiques par vent fort)
        new_hw = min(new_lw, new_hw)

        new_main = (current_main + relax * calculated_value) / (1 + relax)

        if coef_type == "rpth":
            new_main = min(coef_max, max(coef_min, new_main))

        final_main = max(coef_min, new_main)

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
