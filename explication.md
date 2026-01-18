Voici l'analyse complète et consolidée du code. Elle intègre désormais la spécification précise des variables de configuration pour le formulaire `config_flow`, ainsi que l'explication détaillée de la logique interne pour le portage en Python.

---

# Spécification Technique : Intégration SmartHRT (YAML vers Python)

Ce document décrit le fonctionnement du package "Smart Heating Recovery Time" afin de le réécrire sous forme d'une intégration Home Assistant native (composant personnalisé).

### 1. Configuration Utilisateur (Config Flow)

Ces variables sont celles que l'utilisateur doit définir lors de l'ajout de l'intégration. Elles correspondent aux entrées identifiées dans le fichier YAML et la documentation.

#### A. Paramètres Obligatoires (Core)

Ces champs sont essentiels au fonctionnement de l'algorithme.

| Variable (YAML) | Type Python (Suggestion) | Description Technique & Rôle |
| --- | --- | --- |
| **`sensor_interior_temperature`** | `str` (Entity ID) | **Capteur de température intérieure.** <br>

<br>L'utilisateur sélectionne l'entité source (ex: `sensor.salon`). L'intégration doit s'abonner aux changements d'état de ce capteur. |
| **`recoverycalc_hour`** | `datetime.time` | **Heure de coupure chauffage (soir).** <br>

<br>Déclencheur du cycle de "refroidissement". À cette heure, l'intégration initialise les constantes pour la nuit. |
| **`tsp`** | `float` | **Température de Consigne (Target Set Point).** <br>

<br>La température cible à atteindre le matin (ex: 20°C). |
| **`target_hour`** | `datetime.time` | **Heure de fin de relance (Réveil).** <br>

<br>L'heure à laquelle la température `tsp` doit être atteinte. <br>

<br>*Note :* Si l'utilisateur n'utilise pas l'option alarme smartphone, c'est cette valeur qui sert de référence. |

#### B. Paramètres Optionnels (Advanced)

| Variable (YAML) | Type Python | Description |
| --- | --- | --- |
| **`phone_alarm_selector`** | `str` (Entity ID) | **Synchro Alarme Android.** <br>

<br>Si défini, l'intégration doit écouter ce capteur. Si une alarme est détectée pour le lendemain matin, elle écrase temporairement le `target_hour` manuel. |
| **`smartheating_mode`** | `bool` | **Interrupteur Global.** <br>

<br>Permet de désactiver totalement la logique de calcul (ex: vacances, été). |

---

### 2. Modèle de Données (État Interne Persistant)

Ces variables constituent la "mémoire" du système. En Python, elles doivent être stockées (ex: via `Store` ou `RestoreEntity`) pour ne pas perdre l'apprentissage au redémarrage.

#### Constantes Physiques (Le Cœur du Modèle)

Le système modélise la pièce selon deux constantes qui varient linéairement selon la vitesse du vent.

* **`RCth` (Inertie/Isolation - heures) :** Temps caractéristique de refroidissement.
* Stocké sous deux formes : `rcth_lw` (vent faible ~10km/h) et `rcth_hw` (vent fort ~60km/h).


* **`RPth` (Puissance - °C) :** Gain de température max par rapport à l'extérieur.
* Stocké sous deux formes : `rpth_lw` et `rpth_hw`.


* **`relaxation_factor` (Facteur d'apprentissage) :** Coefficient (défaut 2.0) qui lisse la mise à jour des constantes `_lw` et `_hw` après chaque nuit.

#### Variables d'État Dynamiques

* **`recoverystart_hour`** : Le résultat du calcul. L'heure planifiée d'allumage du chauffage.
* **Snapshots** : L'intégration doit mémoriser les températures et l'heure à des moments clés :
* `_calc` (au moment de l'extinction le soir).
* `_start` (au moment de l'allumage le matin).



---

### 3. Logique Algorithmique (Les Scripts)

#### A. Prédiction (`calculate_recovery_time`)

C'est la fonction principale appelée régulièrement la nuit pour mettre à jour l'heure d'allumage.

1. **Entrées :** Températures actuelles, prévisions météo (Temp + Vent), Consigne (`tsp`).
2. **Interpolation :** Calculer le `RCth` et `RPth` courants en fonction du vent actuel (interpolation linéaire entre les valeurs `_lw` et `_hw`).
3. **Résolution :** L'équation thermique étant non-linéaire (la température de départ de la chauffe dépend de l'heure à laquelle on commence, qui dépend elle-même de la température...), le script YAML utilise une boucle itérative (20 itérations).
* *Formule de base (inversée) :*




4. **Sortie :** Met à jour la date/heure de `recoverystart_hour`.

#### B. Détection de Fuite Rapide (`calculate_rcth_fast`)

Estime une valeur instantanée de l'inertie (`RCth`) en observant la vitesse de chute de température juste après l'arrêt du chauffage. Utilise la loi de refroidissement de Newton basique.

---

### 4. Cycle de Vie et Auto-Calibration (Les Automatisations)

L'intégration doit implémenter une machine à états (State Machine) qui réagit aux événements horaires et thermiques.

#### Phase 1 : Arrêt Chauffage (Soir)

* **Déclencheur :** Il est `recoverycalc_hour` (ex: 23h00).
* **Action :**
* Si c'est la première exécution, initialise les constantes `RCth`/`RPth` à 50 par défaut.
* Enregistre les valeurs courantes (T_int, T_ext, heure) dans les variables "snapshot" (`_calc`).
* Active un "listener" pour détecter quand la température baisse réellement de 0.2°C (gestion du lag radiateur).



#### Phase 2 : Démarrage Relance (Matin)

* **Déclencheur :** Il est l'heure calculée `recoverystart_hour`.
* **Action (Calibration RC) :**
* Compare la température actuelle avec celle enregistrée le soir (`_calc`).
* Calcule le vrai `RCth` observé sur la nuit.
* Met à jour `rcth_lw` et `rcth_hw` en répartissant l'erreur selon le vent moyen de la nuit (polynôme d'ordre 3 présent dans le YAML).
* Lisse avec le `relaxation_factor`.



#### Phase 3 : Fin de Relance (Réveil)

* **Déclencheur :** Il est `target_hour` OU la consigne `tsp` est atteinte.
* **Action (Calibration RP) :**
* Compare la montée en température réelle vs théorique.
* Calcule le vrai `RPth` (puissance efficace).
* Met à jour `rpth_lw` et `rpth_hw` (même logique polynômiale).


