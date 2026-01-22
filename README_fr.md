# SmartHRT

**Smart Heating Recovery Time** - Intégration native Home Assistant pour le calcul intelligent de l'heure de relance du chauffage.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/corentinBarban/smartHRT?include_prereleases)](https://github.com/corentinBarban/SmartHRT/releases)

---
> [!NOTE]
> **Ce repository est un fork du projet original [SmartHRT](https://github.com/ebozonne/smarthrt).**
> Il transforme le package YAML original en une **Intégration Home Assistant (Custom Component)** native en Python.
>
> 
## 📋 Table des matières

1. [Présentation](#-présentation)
2. [Principe de fonctionnement](#-principe-de-fonctionnement)
3. [Modèle thermique](#-modèle-thermique)
4. [Installation](#-installation)
5. [Configuration](#-configuration)
6. [Entités créées](#-entités-créées)
7. [Services disponibles](#-services-disponibles)
8. [Cycle de vie automatique](#-cycle-de-vie-automatique)
9. [Auto-calibration](#-auto-calibration)
10. [Exemples d'automatisation](#-exemples-dautomatisation)
11. [Architecture technique](#-architecture-technique)
12. [FAQ](#-faq)

---

## 🎯 Présentation

> **Problème** : La masse thermique des radiateurs et des murs offre un bon confort thermique, mais rend difficile la prédiction du temps de relance du chauffage le matin. Sans prédire correctement le moment de démarrer le chauffage la nuit, il est soit trop tard (et il fait froid), soit trop tôt (on chauffe inutilement le salon pendant le sommeil).

**SmartHRT** résout ce problème en calculant automatiquement l'heure optimale de redémarrage du chauffage (`recovery_start_hour`) pour atteindre la température de consigne (`tsp`) à l'heure souhaitée (`target_hour`).

<img src="./img/SmartHeatingRecoveryTime_principle.png" alt="Principe SmartHRT" style="width:75%; height:auto;">

### Avantages

- ✅ **Économies d'énergie** : Le chauffage ne démarre qu'au moment nécessaire
- ✅ **Confort optimal** : La température cible est atteinte à l'heure du réveil
- ✅ **Auto-apprentissage** : Les paramètres s'ajustent automatiquement à votre logement
- ✅ **Prévisions météo** : Utilise les prévisions de température et de vent
- ✅ **Synchronisation alarme** : Se synchronise avec l'alarme de votre smartphone

---

## 🔄 Principe de fonctionnement

Le système fonctionne selon un cycle quotidien automatique :

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CYCLE QUOTIDIEN SmartHRT                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  23:00 (recoverycalc_hour)     03:00 (calculé)        06:00 (target_hour)   │
│         │                            │                        │             │
│         ▼                            ▼                        ▼             │
│    ┌─────────┐                 ┌─────────┐               ┌─────────┐        │
│    │ PHASE 1 │ ──────────────▶ │ PHASE 2 │ ────────────▶ │ PHASE 3 │       │
│    │  ARRÊT  │   Refroidiss.   │ RELANCE │   Chauffage   │   FIN   │        │
│    │CHAUFFAGE│                 │         │               │ RELANCE │        │
│    └─────────┘                 └─────────┘               └─────────┘        │
│         │                            │                        │             │
│    • Snapshot Tint/Text        • Calcul RCth réel        • Calcul RPth      │
│    • Détection lag temp        • Début chauffe           • Mise à jour      │
│    • Calcul recovery_time      • Mode rp_calc = ON         coefficients     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📐 Modèle thermique

SmartHRT utilise un modèle thermique du premier ordre avec deux paramètres clés :

### Constantes thermiques

| Paramètre | Nom                                   | Description                                                                           |
| --------- | ------------------------------------- | ------------------------------------------------------------------------------------- |
| **RCth**  | Constante de temps thermique (h)      | Combine l'isolation et la masse thermique. Détermine la vitesse de refroidissement.   |
| **RPth**  | Constante de puissance thermique (°C) | Combine l'isolation et la puissance de chauffe. Gain de température max vs extérieur. |

### Formule de calcul

L'heure de relance est calculée par la formule (inversée de la loi de Newton) :

$$
\text{duréeRelance} = RC_{th} \cdot \ln \left( \frac{RP_{th} + T_{ext} - T_{int}^{départ}}{RP_{th} + T_{ext} - T_{sp}} \right)
$$

### Interpolation selon le vent

Les coefficients RCth et RPth varient linéairement selon la vitesse du vent :

- **Vent faible** (10 km/h) : Utilise `rcth_lw` / `rpth_lw`
- **Vent fort** (60 km/h) : Utilise `rcth_hw` / `rpth_hw`

Cette interpolation permet de tenir compte de l'augmentation des pertes thermiques par vent fort.

---

## 📦 Installation

### Prérequis

- Home Assistant 2024.1 ou supérieur
- HACS (recommandé)
- Une entité météo (weather.\*) configurée pour les prévisions

### Option 1 : HACS (Recommandé)

1. Ouvrir HACS dans Home Assistant
2. Aller dans "Intégrations"
3. Cliquer sur les 3 points → "Dépôts personnalisés"
4. Ajouter `https://github.com/corentinBarban/SmartHRT` avec la catégorie "Integration"
5. Rechercher "SmartHRT" et installer
6. Redémarrer Home Assistant
7. Aller dans Paramètres → Appareils & Services → Ajouter une intégration → SmartHRT

### Option 2 : Installation manuelle

1. Télécharger le dossier `custom_components/SmartHRT`
2. Le copier dans le répertoire `config/custom_components/` de Home Assistant
3. Redémarrer Home Assistant
4. Ajouter l'intégration via l'interface

---

## ⚙️ Configuration

### Paramètres obligatoires

| Paramètre                       | Description                       | Exemple                  |
| ------------------------------- | --------------------------------- | ------------------------ |
| **name**                        | Nom de l'instance                 | "Salon"                  |
| **target_hour**                 | Heure de fin de relance (réveil)  | 06:00                    |
| **recoverycalc_hour**           | Heure de coupure chauffage (soir) | 23:00                    |
| **sensor_interior_temperature** | Capteur de température intérieure | sensor.salon_temperature |
| **tsp**                         | Température de consigne           | 20.0                     |

### Paramètres optionnels

| Paramètre                | Description               | Exemple                 |
| ------------------------ | ------------------------- | ----------------------- |
| **phone_alarm_selector** | Capteur alarme smartphone | sensor.phone_next_alarm |

---

## 📊 Entités créées

### Sensors

| Entité                         | Description                      |
| ------------------------------ | -------------------------------- |
| `sensor.<name>_interior_temp`  | Température intérieure           |
| `sensor.<name>_exterior_temp`  | Température extérieure           |
| `sensor.<name>_wind_speed`     | Vitesse du vent (m/s)            |
| `sensor.<name>_windchill`      | Température ressentie            |
| `sensor.<name>_recovery_start` | Heure de relance calculée        |
| `sensor.<name>_rcth_sensor`    | Coefficient RCth                 |
| `sensor.<name>_rpth_sensor`    | Coefficient RPth                 |
| `sensor.<name>_rcth_fast`      | RCth dynamique (suivi nuit)      |
| `sensor.<name>_wind_forecast`  | Prévision vent moyenne 3h        |
| `sensor.<name>_temp_forecast`  | Prévision température moyenne 3h |
| `sensor.<name>_phone_alarm`    | Prochaine alarme téléphone       |

### Numbers (modifiables)

| Entité                     | Description             |
| -------------------------- | ----------------------- |
| `number.<name>_setpoint`   | Consigne de température |
| `number.<name>_rcth`       | Coefficient RCth        |
| `number.<name>_rpth`       | Coefficient RPth        |
| `number.<name>_rcth_lw`    | RCth vent faible        |
| `number.<name>_rcth_hw`    | RCth vent fort          |
| `number.<name>_rpth_lw`    | RPth vent faible        |
| `number.<name>_rpth_hw`    | RPth vent fort          |
| `number.<name>_relaxation` | Facteur de relaxation   |

### Switches

| Entité                            | Description                               |
| --------------------------------- | ----------------------------------------- |
| `switch.<name>_smartheating_mode` | Active/désactive le chauffage intelligent |
| `switch.<name>_adaptive_mode`     | Active/désactive l'auto-calibration       |

### Time

| Entité                           | Description                |
| -------------------------------- | -------------------------- |
| `time.<name>_target_hour`        | Heure cible (réveil)       |
| `time.<name>_recoverycalc_hour`  | Heure de coupure chauffage |
| `time.<name>_recoverystart_hour` | Heure de relance calculée  |

---

## 🔧 Services disponibles

| Service                                   | Description                            |
| ----------------------------------------- | -------------------------------------- |
| `smarthrt.calculate_recovery_time`        | Calcule l'heure de relance             |
| `smarthrt.calculate_recovery_update_time` | Calcule la prochaine mise à jour       |
| `smarthrt.calculate_rcth_fast`            | Calcule RCth dynamique                 |
| `smarthrt.on_heating_stop`                | Déclenche l'arrêt chauffage (snapshot) |
| `smarthrt.on_recovery_start`              | Déclenche le début de relance          |
| `smarthrt.on_recovery_end`                | Déclenche la fin de relance            |

### Paramètre optionnel

Tous les services acceptent un paramètre `entry_id` optionnel pour cibler une instance spécifique.

---

## 🔁 Cycle de vie automatique

SmartHRT gère automatiquement les déclencheurs horaires :

### Phase 1 : Arrêt du chauffage (`recoverycalc_hour`)

À l'heure configurée (ex: 23:00) :

1. Initialise les coefficients à 50 si première exécution
2. Enregistre un snapshot (Tint, Text, timestamp)
3. Active la détection du lag de température
4. Calcule l'heure de relance prévue

### Phase 2 : Début de relance (`recovery_start_hour`)

À l'heure calculée (ex: 03:00) :

1. Enregistre les températures actuelles
2. Calcule le RCth réel observé sur la nuit
3. Met à jour les coefficients `rcth_lw` et `rcth_hw`
4. Active le mode de calcul RPth

### Phase 3 : Fin de relance (`target_hour` ou consigne atteinte)

Quand la consigne est atteinte ou à l'heure cible :

1. Enregistre les températures finales
2. Calcule le RPth réel observé
3. Met à jour les coefficients `rpth_lw` et `rpth_hw`

---

## 📈 Auto-calibration

L'auto-calibration utilise une **relaxation exponentielle** avec un polynôme cubique pour distribuer l'erreur :

1. Après chaque cycle, les RCth/RPth mesurés sont comparés aux valeurs interpolées
2. L'erreur est répartie sur les coefficients vent faible/fort selon le vent moyen de la nuit
3. Les coefficients sont lissés avec le `relaxation_factor` (défaut: 2.0)

**Formule de mise à jour** :

$$
coef_{new} = \frac{coef_{old} + relaxation \times coef_{calculated}}{1 + relaxation}
$$

> 💡 Les premiers jours peuvent ne pas être précis. L'auto-calibration s'améliore progressivement.

---

## 🤖 Exemples d'automatisation

### Démarrer le chauffage à l'heure de relance

```yaml
automation:
  - alias: "SmartHRT - Démarrer chauffage"
    trigger:
      - platform: time
        at: sensor.smarthrt_recovery_start
    condition:
      - condition: state
        entity_id: switch.smarthrt_smartheating_mode
        state: "on"
    action:
      - service: climate.set_temperature
        target:
          entity_id: climate.salon
        data:
          temperature: "{{ states('number.smarthrt_setpoint') | float }}"
```

### Arrêter le chauffage le soir

```yaml
automation:
  - alias: "SmartHRT - Arrêter chauffage soir"
    trigger:
      - platform: time
        at: time.smarthrt_recoverycalc_hour
    action:
      - service: climate.turn_off
        target:
          entity_id: climate.salon
```

---

## 🏗️ Architecture technique

```
custom_components/SmartHRT/
├── __init__.py          # Point d'entrée de l'intégration
├── coordinator.py       # Coordinateur central avec logique thermique
├── config_flow.py       # Interface de configuration UI
├── const.py             # Constantes et valeurs par défaut
├── sensor.py            # Entités sensor (températures, coefficients)
├── switch.py            # Entités switch (modes)
├── number.py            # Entités number (consigne, relaxation)
├── time.py              # Entités time (heures cibles)
├── services.yaml        # Définitions des services
├── strings.json         # Chaînes UI (anglais)
├── manifest.json        # Métadonnées de l'intégration
└── translations/
    └── fr.json          # Traductions françaises
```

### Classes principales

- **`SmartHRTCoordinator`** : Coordinateur central gérant tous les calculs thermiques, les listeners et les services
- **`SmartHRTData`** : Dataclass contenant toutes les données d'état (températures, coefficients, timestamps, modes)

---

## ❓ FAQ

### Comment synchroniser avec l'alarme de mon téléphone ?

Configurez le paramètre `phone_alarm_selector` avec le capteur de votre téléphone (ex: `sensor.phone_next_alarm`). L'heure cible sera automatiquement mise à jour.

### Que faire pendant les vacances ?

Désactivez le switch `Mode chauffage intelligent` pour suspendre les calculs.

### Les prédictions ne sont pas précises les premiers jours ?

C'est normal ! L'auto-calibration nécessite quelques cycles pour s'adapter à votre logement. Les coefficients s'améliorent progressivement.

### Comment ajuster manuellement les coefficients ?

Désactivez le `Mode adaptatif` et modifiez les entités `number.*_rcth` et `number.*_rpth` directement.

---

## 📝 Changelog

### Janvier 2026 - Intégration Native

- **NOUVEAU** : Réécriture complète en intégration native Home Assistant (compatible HACS)
- **NOUVEAU** : Configuration via interface UI (plus de YAML requis)
- **NOUVEAU** : Services Home Assistant pour l'automatisation
- **NOUVEAU** : Déclencheurs horaires automatiques (recoverycalc_hour, target_hour, recovery_start)
- **NOUVEAU** : Prévisions météo intégrées (température et vent sur 3h)
- **NOUVEAU** : Détection du lag de température (délai radiateur)
- **NOUVEAU** : Calcul de la moyenne de vent sur 4h pour la calibration
- **AMÉLIORÉ** : Architecture centralisée avec coordinateur unique

---

## 📄 Licence

Ce projet est sous licence GNU GENERAL PUBLIC LICENSE. Voir le fichier [LICENCE](LICENCE) pour plus de détails.

