# Architecture Diagrams

**Schémas visuels du fonctionnement de l'intégration SmartHRT**

## Table des matières

1. [Architecture système](#architecture-système)
2. [Cycle de chauffage quotidien](#cycle-de-chauffage-quotidien)
3. [Machine à états](#machine-à-états)
4. [Flux de données](#flux-de-données)
5. [Pipeline de calcul](#pipeline-de-calcul)
6. [Modèle thermique](#modèle-thermique)
7. [Processus de calibration](#processus-de-calibration)

---

## Architecture système

```
Home Assistant
      |
      v
SmartHRTCoordinator
      |
      +----> Sensors (T°, %)
      +----> Numbers (coefficients)
      +----> Switches (modes)
      +----> Times (horaires)
      +----> Services
```

### Intégrations externes

```
Weather Entity --> SmartHRT
Temperature Sensor --> SmartHRT
```

---

## Cycle de chauffage quotidien

```
23:00                     ~23:10-30          03:00              06:00
  |                           |                 |                  |
Étape 1                   Étape 2           Étape 3            Étape 4
heatingstopTIME      temperatureDecrease   boostTIME      recoveryendTIME
Chauffage OFF         Baisse réelle         Relance        Consigne atteinte
  |                           |                 |                  |
HEATING_ON             DETECTING_LAG      MONITORING         RECOVERY
  |                           |                 |                  |
  v                           v                 v                  v
Snapshot T_calc         Lag détecté       Snapshot T_start   HEATING_PROCESS
Active détection        → MONITORING      Calcul RCth           |
                        Calcul recovery   → HEATING_PROCESS     v
                                                            Snapshot T_end
                                                            Calcul RPth
                                                            → HEATING_ON
```

### Captures de données

```
Snapshot 1 (23:00)               Snapshot 2 (03:00)               Snapshot 3 (06:00)
heatingstopTIME                  boostTIME                        recoveryendTIME
  • T_interior_calc                • T_interior_start               • T_interior_end
  • T_exterior_calc                • T_exterior_start               • T_exterior_end
  • time_calc                      • time_start                     • time_end
  • Active lag detection           • Calcul RCth observé            • Calcul RPth observé
  • État: HEATING_ON               • État: RECOVERY                 • État: HEATING_PROCESS
    → DETECTING_LAG                  → HEATING_PROCESS                → HEATING_ON
```

---

## Machine à états

```
État 1: HEATING_ON (journée)
    |
    v [heatingstopTIME - 23:00]
    | Snapshot T_calc
    | Active temp_lag_detection
    |
État 2: DETECTING_LAG
    |
    v [baisse T° ≥ 0.2°C détectée]
    | Snapshot mise à jour
    | Calcul recovery_time
    | recovery_calc_mode ON
    |
État 3: MONITORING (nuit)
    |
    | [Mises à jour périodiques recovery_time]
    |
    v [recoverystart_hour atteinte - 03:00]
    |
État 4: RECOVERY (instant)
    |
    | Snapshot T_start
    | Calcul RCth observé
    | Update rcth_lw/hw
    | rp_calc_mode ON
    | recovery_calc_mode OFF
    |
    v [Auto-transition immédiate]
    |
État 5: HEATING_PROCESS (montée)
    |
    v [target_hour OU T°≥setpoint - 06:00]
    | Snapshot T_end
    | Calcul RPth observé
    | Update rpth_lw/hw
    | rp_calc_mode OFF
    |
    v
État 1: HEATING_ON (cycle suivant)
```

### Correspondance YAML → Code

```
Automation YAML                    État Machine          Trigger/Condition
────────────────────────────────────────────────────────────────────────────
heatingstopTIME                    HEATING_ON            time: recoverycalc_hour
  → Active detect_lag              → DETECTING_LAG       + Active automation

temperatureDecrease                DETECTING_LAG         T ≤ T_calc - 0.2°C
  → recovery_calc_mode ON          → MONITORING          + recovery_calc_mode ON

recoveryupdate (périodique)        MONITORING            time: recoveryupdate_hour
  → Recalcul recovery_time                               + recovery_calc_mode ON

boostTIME                          MONITORING            time: recoverystart_hour
  → Calcul RCth                    → RECOVERY            + Snapshot T_start
  → rp_calc_mode ON                → HEATING_PROCESS     + Auto-transition

recoveryendTIME                    HEATING_PROCESS       time: target_hour
  OU T°≥setpoint                                         OU T ≥ tsp
  → Calcul RPth                    → HEATING_ON          + rp_calc_mode OFF
```

---

## Flux de données

```
Entrées (HA)
    |
    +-> Températures
    +-> Météo
    +-> Vent
    |
    v
Coordinator (update 60s)
    |
    +-> Récupération données
    +-> Calculs thermiques
    +-> Machine à états
    |
    v
Entités
    |
    +-> Sensors
    +-> Numbers
    +-> Switches
    +-> Times
```

---

## Pipeline de calcul

### Calcul du temps de récupération

```
Entrées:
  • T_interior
  • T_exterior
  • T_setpoint
  • RCth, RPth
  • Vitesse vent
    |
    v
1. Interpolation vent
   wind ≤ 10 km/h  -> RCth_lw, RPth_lw
   wind ≥ 60 km/h  -> RCth_hw, RPth_hw
   entre deux      -> interpolation linéaire
    |
    v
2. Validation
   • RCth > 0
   • RPth > 0
   • T_ext définie
    |
    v
3. Calcul durée
   recovery_duration = RCth * ln((RPth + T_ext - T_int) / (RPth + T_ext - T_sp))
    |
    v
4. Conversion horaire
   recovery_start = target_hour - recovery_duration
    |
    v
Sortie:
  • sensor.recovery_start
  • time.recovery_start
```

---

## Modèle thermique

```
Phase refroidissement:
T(t) = T_ext + (T_0 - T_ext) * e^(-t/RCth)

Phase chauffage:
T(t) = T_ext + RPth - (T_ext + RPth - T_0) * e^(-t/RCth)
```

---

## Processus de calibration

### Cycle quotidien

```
Jour N - Soir (23:00) - heatingstopTIME
    |
    +-> HEATING_ON → DETECTING_LAG
    +-> Snapshot: T_calc, T_ext_calc, time_calc
    +-> Active temp_lag_detection
    +-> Utilise RCth/RPth précédents
    +-> Calcule recovery_start_hour
    |
    v
Soir/Nuit (~23:10-30) - temperatureDecrease
    |
    +-> DETECTING_LAG → MONITORING
    +-> Détection: T ≤ T_calc - 0.2°C
    +-> Mise à jour snapshot (lag réel)
    +-> recovery_calc_mode ON
    +-> Calcul recovery_start_hour actualisé
    |
    v
Nuit (refroidissement) - MONITORING
    |
    +-> Mises à jour périodiques (recoveryupdate_hour)
    +-> Recalcul recovery_start_hour
    +-> Surveillance continue
    |
    v
Nuit/Matin (03:00) - boostTIME
    |
    +-> MONITORING → RECOVERY (instant)
    +-> Snapshot: T_start, T_ext_start, time_start
    +-> Calcul RCth observé
    +-> Compare RCth_observé vs RCth_prédit
    |
    v
    +-> RECOVERY → HEATING_PROCESS (auto)
    +-> rp_calc_mode ON
    +-> recovery_calc_mode OFF
    +-> Distribution erreur sur rcth_lw/hw
    |
    v
Matin (06:00) - recoveryendTIME
    |
    +-> HEATING_PROCESS → HEATING_ON
    +-> Trigger: target_hour OU T°≥setpoint
    +-> Snapshot: T_end, T_ext_end, time_end
    +-> Calcul RPth observé
    +-> Distribution erreur sur rpth_lw/hw
    +-> rp_calc_mode OFF
    |
    v
Distribution vent (après chaque calcul)
    |
    +-> wind ≤ 35 km/h  -> met à jour coeff_lw
    +-> wind ≥ 35 km/h  -> met à jour coeff_hw
    +-> entre deux      -> répartition polynomiale
    |
    v
Lissage exponentiel
    |
    coeff_new = (coeff_old * relax + coeff_mesure) / (relax + 1)
    Default: relax = 2.0 → 67% ancien, 33% nouveau
    |
    v
Sauvegarde coefficients persistants
    |
    v
Jour N+1 (23:00)
    |
    +-> Utilise nouveaux coefficients
    +-> Prédiction améliorée
    +-> Cycle recommence
```

### Évolution de la précision

```
Jours 1-3:   Apprentissage   (±30-15 min)
Semaine 1:   Stabilisation   (±10 min)
Mois 1:      Haute précision (±5 min)
```

---

**Voir aussi:**

- [Technical Reference](TECHNICAL_REFERENCE.md) - Spécifications détaillées
- [Getting Started](GETTING_STARTED.md) - Guide d'installation
- [Support](SUPPORT.md) - Dépannage
