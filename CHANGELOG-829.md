## Issue #829 — `REPO_CIBLE` transmis à la création (fichier déposé et formulaire web), refusé pour un projet à périmètre dynamique sans ce champ

Un projet à périmètre dynamique (`PERIMETRE_DYNAMIQUE = true`, issue #125)
reçoit son dépôt de travail par le champ `REPO_CIBLE` de l'issue — mais
aucun des deux chemins de création (fichier déposé dans `issues_inbox/`,
formulaire web) ne savait l'écrire : une issue sans ce champ était créée
puis échouait forcément à l'exécution (« projet en périmètre dynamique
mais l'issue ne fournit pas de champ REPO_CIBLE »). Jusqu'ici, seul le
chemin `RELANCE` (issue #567) savait valider/réinsérer ce champ, et
uniquement pour corriger une issue déjà ouverte.

- **`app/issues.py::formater_entete`** : nouveau paramètre facultatif
  `repo_cible` (même mécanisme que `modele`) — ajoute une ligne
  `| REPO_CIBLE | <chemin> |` dans le tableau d'en-tête seulement s'il est
  fourni ; sortie strictement inchangée sans lui.
- **`app/issues.py::construire_body`** (formulaire web) et
  **`app/issues.py::envoyer`** : le champ `repo_cible` du formulaire est
  réinséré dans le corps, et validé AVANT création avec les mêmes
  fonctions que le chemin `RELANCE` (`perimetre_dynamique` du projet,
  `watcher.valider_repo_cible`) — rejet (rien n'est créé, aucun appel
  `gh`) si le projet est à périmètre dynamique sans ce champ, si le champ
  est fourni pour un projet qui ne l'est pas, ou si le chemin est invalide.
- **`app/projets.py::get_config`** : expose désormais `perimetre_dynamique`
  (lu tel quel depuis le `.conf`), pour que le formulaire web sache afficher
  ou masquer le nouveau champ.
- **`templates/fragments/onglet_creation.html` + `static/js/app.js` +
  `static/js/creation.js`** : nouveau champ obligatoire « Dépôt cible »,
  affiché uniquement pour un projet à `PERIMETRE_DYNAMIQUE=true` (vidé à la
  bascule vers un autre projet), collecté par `collecterFormulaire()`,
  vérifié côté client en miroir de la validation serveur (seule réellement
  autoritaire).
- **`scripts/watcher_issues_inbox.py::valider`** : mêmes trois cas de rejet
  que côté web, appliqués à chaque bloc d'un fichier en lot (§3.13)
  individuellement ; `construire_body` réinsère `REPO_CIBLE` dans le corps
  créé. Commentaire corrigé (le champ n'est plus « inutilisé côté
  création »). Chemins `RELANCE`, lot et projets à périmètre fixe
  inchangés — `SOUS_DOSSIER` reste non traité par cette issue (même défaut
  qu'avant, signalé mais pas corrigé).
- **`BRIDGE_AGENT_DOC.md`** : §3.3 (tableau des champs), §3.4 (règles de
  rejet), §16 et §19 mis à jour pour refléter le nouveau comportement.
- **Tests** : nouveau fichier `tests/test_repo_cible_creation_829.py` (16
  scénarios, aucun accès réseau) — `formater_entete` avec/sans le nouveau
  paramètre, aller-retour avec `watcher.extraire_repo_cible`, les quatre cas
  de validation côté inbox (dont le lot) et côté formulaire web (via
  `flask.test_request_context`), non-régression du chemin `RELANCE`.

Mesures : suite Python `tests/lancer_tous_les_tests.py` 86/86 avant → 87/87
après (nouveau fichier ajouté, aucune régression) ; suites JS
`static/js/tests/` 391/391 et `static/js/socle/tests/` 34/34, inchangées
avant/après (aucune fonction pure nouvelle côté JS — l'affichage/masquage du
champ est vérifié manuellement, comme le reste de `creation.js`/`app.js`,
cf. `VERIFICATIONS_MANUELLES.md`, mis à jour en conséquence).
