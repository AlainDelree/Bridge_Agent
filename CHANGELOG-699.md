## #699 — 4e option S=Silence au contrôle de son par issue (G/P/C existants inchangés)

- Besoin : couper le bip pour UNE issue précise, sans toucher à
  l'interrupteur global ni aux autres issues — 4e option à côté des 3
  déjà là (Global/Plat/Cloche), aucune ne disparaît.
- `etat_son_issue.py` : `SONS_VALIDES` étendu à `("plat", "cloche",
  "silence")`. Le module était déjà générique sur les valeurs de
  `SONS_VALIDES` (`son_choisi`, `sons_projet`, `definir_son`,
  `nettoyer_projet`, `nettoyer_entrees_perimees`) : aucun changement
  supplémentaire nécessaire, confirmé par les tests.
- `app/son_issue.py` (routes `GET`/`POST /son-issue/...`) : déjà générique
  via `SONS_VALIDES`, confirmé sans modification de logique (juste le
  docstring mis à jour).
- `scripts/traitement_fin.py::main()` : quand `son_a_jouer()` renvoie
  `"silence"`, aucun bip n'est joué (ni `bip()` ni `bip_plat()`) — le POST
  `notifier_fin_issue` (rafraîchissement SSE de l'onglet Résultats) reste
  appelé normalement, inchangé. Le canal ntfy (`notifications_poller.py`)
  n'est pas concerné par ce script et reste lui aussi inchangé : silence =
  coupe uniquement le son audible de CETTE issue.
- `static/js/actions_ligne.js` : 4e bouton `S` dans `boutonsSonLigne`/
  `rendreControleSonLigne`, état `silence` dans `etatsOptionsSonIssue`,
  normalisation dans `normaliserChoixSonIssue`/`sonIssueDepuisReponse`/
  `fusionnerSonsProjet`/`sonConnuDansCache` — même traitement que
  `'plat'`/`'cloche'`. Infobulle : « Son de cette issue : Silence — clic
  pour changer ».
- `static/css/resultats.css` : contrôle `.ligne-son-opt` pensé compact
  pour une largeur de ligne contrainte (issue #633) — padding horizontal
  resserré (4px→3px) pour absorber la largeur du 4e bouton sans casser la
  mise en page, plutôt que renoncer à la fonctionnalité.
- Tests : `tests/test_son_issue_630.py` (3 scénarios ajoutés — `definir_son`
  accepte `"silence"`, `son_a_jouer` le priorise par issue seule sur
  l'interrupteur global, `main()` ne joue aucun bip mais notifie quand même)
  et `static/js/tests/actions_ligne.test.js` (4e état couvert dans chaque
  fonction pure concernée) — tous passent (20/20 JS, 20/20 Python).
- Doc : `ARCHITECTURE.md`/`BRIDGE_AGENT_DOC.md` — mentions du contrôle
  « G/P/C » à 3 états mises à jour en « G/P/C/S » à 4 états.
