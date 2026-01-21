Ceci est une analyse technique et fonctionnelle détaillée du code YAML fourni (principalement issu du fichier `thermal_recovery_time.yaml`), destinée à servir de spécification pour un redéveloppement en Python (Intégration Custom Component Home Assistant).

L'intégration vise à **optimiser le moment de relance du chauffage** le matin (Smart Recovery) en apprenant les caractéristiques thermiques de la pièce ( pour l'isolation/inertie, pour la puissance de chauffe) et en les adaptant en fonction des conditions extérieures (température et vent).

---

### 1. Architecture des Données et États (Data Model)

Pour une réécriture en Python, il faut persister certaines variables qui évoluent dans le temps (Self-Learning).

#### A. Les Constantes Physiques (Persistantes)

Le système repose sur deux coefficients physiques majeurs, chacun divisé en deux valeurs selon la vitesse du vent (Vent Faible "lw" / Vent Fort "hw") :

1. ** (Room Constant - Cooling)** : Représente l'inertie et l'isolation. Temps (en heures) pour perdre 63% de la différence de température.

- Variables : `rcth_lw` (low wind), `rcth_hw` (high wind).
- Stockage : `input_number` persistants.

2. ** (Room Power - Heating)** : Représente la capacité de montée en température (delta T max atteignable à l'équilibre).

- Variables : `rpth_lw`, `rpth_hw`.
- Stockage : `input_number` persistants.

3. **Facteur de Relaxation** : Un coefficient (ex: 2.0) qui amortit l'apprentissage pour éviter des changements brutaux des constantes après un seul cycle aberrant.

#### B. Les Entrées Utilisateur (Configuration)

- `sensor_interior_temperature` : Capteur T° intérieure.
- `tsp` (Target Set Point) : T° cible (ex: 20°C).
- `target_hour` : Heure cible (réveil) ou synchronisation avec l'alarme du téléphone.
- `recoverycalc_hour` : Heure d'arrêt du chauffage le soir (début de la surveillance de la chute).

---

### 2. Le Cœur Mathématique (Algorithmes)

#### A. Interpolation du Vent

Avant tout calcul, le code YAML interpole les coefficients et en fonction de la prévision de vent moyen.

- **Limites définies :** , .
- **Formule linéaire :**

_Note : Le code applique un `max(0.1, ...)` pour éviter la division par zéro._

#### B. Prédiction du Temps de Relance (`calculate_recovery_time`)

C'est la fonction critique. Elle doit déterminer combien de temps () il faut pour passer de la température "au moment du démarrage" () à la consigne ().

**Problème :** On ne connait pas car elle dépend de l'heure de démarrage, qui dépend elle-même de (la température continue de chuter tant qu'on n'a pas démarré).

**Algorithme (Script YAML) :**

1. **Calcul initial :** Estimation de la durée de chauffe nécessaire avec la T° actuelle.
   Formula logarithmique dérivée de la loi de refroidissement de Newton :

2. **Boucle Itérative (Convergence) :**
   Le script exécute une boucle (20 itérations) pour affiner la prédiction :

- Estimer la future à l'heure supposée de démarrage (basée sur la chute exponentielle depuis la T° actuelle pendant le temps d'attente).
- Recalculer la `Duration` nécessaire à partir de cette nouvelle .
- Mettre à jour la durée avec une moyenne pondérée pour converger.

_Implémentation Python recommandée :_ Remplacer la boucle `for 20` par une boucle `while` avec un seuil de convergence (epsilon) sur le delta temps.

#### C. L'Apprentissage (Self-Calibration)

Cette logique ajuste les coefficients et après chaque cycle (Automatisme `recovery_constants_calc2`).

1. **Calcul de l'erreur () :** Différence entre le coefficient théorique qui aurait donné le résultat parfait et le coefficient actuellement utilisé (interpolé).

- Pour le refroidissement () : Calculé au moment de l'allumage (entre l'arrêt chauffage et le démarrage relance).
- Pour la chauffe () : Calculé quand la consigne est atteinte.

2. **Répartition de la correction (Wind Weighting) :**
   L'erreur est distribuée sur les composantes "Low Wind" et "High Wind" selon la vitesse du vent observée durant le cycle, via un polynôme de degré 3.

- Variable normalisée : position du vent entre low et high (-0.5 à 0.5).
- Le code utilise des formules complexes pour pondérer la mise à jour :

_(Et inversement pour hw)_

3. **Application avec Relaxation :**

---

### 3. Machine à État (Cycle de Vie)

Pour l'intégration Python, il faut gérer une machine à état explicite plutôt que des triggers disparates.

#### État 1 : HEATING_ON (Journée)

- **Transition vers État 2 :** À l'heure `recoverycalc_hour` (ex: 23h00, heure de coupure programmée).
- **Action :** Initialiser les variables de suivi (T° init, Time init). Activer la détection de lag.

#### État 2 : DETECTING_LAG (Inertie post-coupure)

- Le code YAML attend que la température baisse réellement de **0.2°C** par rapport à la température de coupure.
- **Pourquoi ?** Les radiateurs en fonte continuent de chauffer après l'arrêt. Calculer le refroidissement immédiatement fausserait .
- **Transition vers État 3 :** Dès que .
- **Action :** Enregistrer `temperature_recovery_calc`, `time_recovery_calc`. Activer le mode calcul.

#### État 3 : MONITORING (La nuit)

- **Action récurrente :**
- Exécuter l'algorithme de prédiction (Point 2.B) régulièrement (défini par `calculate_recoveryupdate_time`).
- Mettre à jour l'entité `sensor.recovery_start_time`.
- _(Optionnel)_ `calculate_rcth_fast` : Estime le en temps réel pour voir si la maison refroidit plus vite que prévu.

- **Transition vers État 4 :** Quand `now() >= calculated_start_time`.

#### État 4 : RECOVERY (La relance)

- **Événement :** Le chauffage s'allume (géré par l'utilisateur via une automatisation externe qui lit le `sensor.recovery_start_time`).
- **Calcul "Post-Cooling" :** À cet instant précis, on connait la vraie chute de température. On lance le calcul de calibration pour .
- **Action :** Enregistrer `temperature_recovery_start`, `time_recovery_start`.

#### État 5 : HEATING_PROCESS (Montée en température)

- On surveille la montée en température.
- **Transition vers État 1 :** Quand (Consigne atteinte) OU .
- **Calcul "Post-Heating" :** À cet instant, on connait la vitesse de chauffe réelle. On lance le calcul de calibration pour .

---

### 4. Spécifications pour le développeur Python

Voici les points clés pour l'implémentation de la classe principale :

1. **Classe `SmartHRT` :** Doit hériter de `RestoreEntity` pour sauvegarder les coefficients entre les redémarrages de HA (crucial pour ne pas perdre l'apprentissage).
2. **Gestion du Vent :** Récupérer l'historique du vent (moyenne) sur la période écoulée (4h pour le refroidissement, durée du cycle pour la chauffe). Le YAML utilise un `statistics sensor`. En Python, il faudra peut-être interroger l'historique (`recorder`).
3. **Inputs dynamiques :** L'intégration ne doit pas hardcoder les entités. Elle doit accepter via `config_flow` :

- L'entité thermostat/température.
- L'entité météo (pour T° ext et Vent).
- L'entité switch/input_boolean qui définit "Mode Nuit/Absent".

4. **Exposition :**

- **Sensors :** `recovery_start_time` (timestamp), `time_to_recovery` (durée).
- **Attributes :** actuel, actuel, Erreur dernier cycle.
- **Services :** `reset_learning`, `trigger_calculation`.

5. **Robustesse :**

- Gérer le cas où (Pas de refroidissement).
- Gérer le cas où (Pas besoin de chauffage).
- Implémenter les `min/max` présents dans le YAML pour éviter les valeurs aberrantes (ex: division par zéro dans le log).

### Résumé visuel du flux (basé sur l'analyse)

1. **Soir :** Coupure -> Attente chute T° (-0.2°C) -> **Start Cooling Timer**.
2. **Nuit :** Boucle { Estimation -> Calcul Durée Chauffage -> Update Heure Allumage }.
3. **Matin (Allumage) :** **Stop Cooling Timer** -> Update Coeff -> **Start Heating Timer**.
4. **Matin (Confort) :** T° atteinte -> **Stop Heating Timer** -> Update Coeff .
