## 25 septembre 2026 — issue #630

Refonte de l'interface web, **étape 7a/n : son plat/cloche par issue
(backend seul)**. Décision d'Alain : l'interrupteur GLOBAL plat/cloche
(`scripts/son_actif.txt`, #498/#527) reste la règle par défaut ; en plus,
n'importe quelle issue peut désormais être basculée en plat ou en cloche pour
elle-même. Le réglage PAR PROJET envisagé un temps (tonalité `TONALITE_BIP`,
script `SCRIPT_BIP`) est abandonné au profit de ce choix plus fin, par issue.
Interface prévue aux étapes 7b/8 — cette étape-ci ne touche à rien de visible.

### Stockage et routes

- `etat_son_issue.py` (racine du dépôt, sans dépendance Flask, sur le modèle
  de `notifications.py`/`etat_rate_limit.py`) : `logs/son_issues.json`
  (`{projet: {numéro: "plat"|"cloche"}}`), écriture atomique + verrou
  anti-collision — même mécanisme que `etat_rate_limit.json` (#615).
  `son_choisi`/`definir_son`/`nettoyer_projet`/`nettoyer_entrees_perimees`.
- `app/son_issue.py` : `GET`/`POST /son-issue/<nom_projet>/<numero>`, même
  famille que les routes `/son-actif` existantes (`app/son.py`).

### Nettoyage

Même règle que les cases cochées côté navigateur : au démarrage de
`new_issue.py`, purge PAR PROJET des entrées dont le numéro est ≤ (plus grand
numéro connu de ce projet dans `son_issues.json` − 50) ; purge TOTALE d'un
projet à sa suppression (`supprimer_projet.py`, best-effort, non bloquant).

### Résolution au moment du bip

`scripts/traitement_fin.py::son_a_jouer(projet, numéro)` : le choix de
l'issue s'il existe, sinon l'interrupteur global (`son_actif()`) — valable
pour les issues CCL (`watcher.py::bip()`/`notifier()`) comme pour les issues
CCW (`app/notifications_poller.py::_notifier_transition()`), qui transmettent
toutes deux `--projet`/`--numero` au script.

### TONALITE_BIP / SCRIPT_BIP retirés du chemin réel du bip

`watcher.py` et `app/notifications_poller.py` appellent désormais toujours
`scripts/traitement_fin.py` (script partagé) avec une tonalité neutre (`0`),
quel que soit le `.conf` du projet. `scripts/bip_Cloche.py` (legacy,
pitch-shift via `sox`) est **supprimé**. Le code tolère la présence
résiduelle de `SCRIPT_BIP`/`TONALITE_BIP` dans les `configs/*.conf`
existants (jamais modifiés directement par CCL) : ces deux clés restent
lues/exposées par l'onglet Configuration (`/config`, `/tester-bip/<projet>`,
`app/projets.py`) et écrites par `nouveau_projet.py` pour les nouveaux
projets — **volontairement non touchés** par cette étape, retrait prévu à
l'étape 8 avec l'onglet lui-même.

### Tests

`tests/test_son_issue_630.py` (13 scénarios pytest) : résolution du son
(choix par issue, repli sur l'interrupteur global, absence de projet/numéro),
stockage (écriture/lecture isolées par projet+numéro, valeur invalide
refusée, remise à zéro), nettoyage (purge par projet, conservation des 50
dernières issues connues par projet), routes Flask.

Mise à jour de `BRIDGE_AGENT_DOC.md` §17 (nouveau modèle de son).
