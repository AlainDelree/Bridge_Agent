## 26 septembre 2026 — issue #637

Refonte interface web — étape 7b : contrôle à 3 états « Son de cette issue » (Global/Plat/Cloche) dans le panneau latéral.

Contexte : l'étape 7a (#630) avait posé le backend du son par issue (`etat_son_issue.py`, routes `GET`/`POST /son-issue/<projet>/<numero>`) sans aucun bouton dans l'interface. L'étape 6 (badges ✅/Diff/All de la ligne Résultats → actions sur la ligne) n'étant pas encore faite, le contrôle est ajouté dans la zone Actions du panneau latéral (issue sélectionnée), à côté des toggles 🔔 Notifications déjà présents.

- **`static/js/panneau_lateral.js`** : fonctions pures `sonIssueDepuisReponse` (réponse serveur → `'plat'|'cloche'|null`), `normaliserChoixSonIssue` (valeur du bouton cliqué → valeur à poster), `etatsOptionsSonIssue` (état actif des 3 boutons, mutuellement exclusifs) ; rendu `rendreSonIssue()` dans `rendrePanneauLateralActions()` (devenue `async`), visible tant que l'issue sélectionnée n'est pas fermée. Une seule requête `GET /son-issue` par sélection d'issue (mise en cache — `sonIssueSelectionCle`/`sonIssueSelectionValeur` — tant que la sélection ne change pas, pas de refetch au cycle de rafraîchissement de 30s). Clic sur une option : mise à jour optimiste + `POST /son-issue`, retour à l'état précédent et toast d'erreur (via `api.post`, non silencieux) en cas d'échec réseau.
- **`templates/fragments/panneau_lateral.html`** : infobulle sur la ligne « Timbre » de l'interrupteur global (`#pl-zone-son`) rappelant qu'un choix par issue prime sur lui pour cette issue précise ; commentaire d'en-tête mis à jour pour `#pl-zone-actions`.
- **`app/son_issue.py`** : docstring mis à jour (l'étape backend seule #630 a désormais son bouton, étape 7b #637).
- Tests : `static/js/tests/panneau_lateral.test.js` — 13 nouveaux cas (`sonIssueDepuisReponse`, `normaliserChoixSonIssue`, `etatsOptionsSonIssue`, dont la bascule des 3 états). `node --test static/js/tests/ static/js/socle/tests/` → 69/69.
- `VERIFICATIONS_MANUELLES.md` (nouvelle entrée détaillée sous « Zone actions contextuelles ») et `BRIDGE_AGENT_DOC.md` (§ son PAR ISSUE) mis à jour pour documenter l'emplacement choisi et sa reprise prévue à l'étape 6.
