# CHANGELOG-716 — à fusionner dans CHANGELOG.md

## 4 octobre 2026 — issue #716

§3.16 « Issues en attente » : **plus de ligne « 📥 fichier reçu » fantôme dans Résultats pour un fichier (ou lot) ENTIÈREMENT mis en attente** (champ `ATTENTE`, #713) — correctif de l'incident documenté dans le changelog de #714 (« fichier reçu : mono.txt » resté affiché sans jamais être remplacé, puisqu'aucune issue n'est créée pour ces blocs).

- `scripts/watcher_issues_inbox.py::traiter_fichier` : cause confirmée — `_notifier_fichier_recu` était appelé en tout début de fonction, AVANT la détection du champ `ATTENTE` (#713). L'appel est déplacé après cette détection sur les trois branches concernées : fichier mono-issue (sauté entièrement si `ATTENTE` couvre tout le fichier, sinon émis juste avant `_traiter_bloc`), lot multi-blocs (sauté si `blocs_a_traiter` finit vide — tous les blocs avaient `ATTENTE` —, sinon émis une fois avant `_traiter_lot`, inchangé pour un lot mixte), extension invalide / lecture impossible (émis immédiatement, comportement inchangé — ces fichiers n'ont jamais de notion d'`ATTENTE`).
- Tests : `tests/test_pas_de_ligne_fichier_recu_si_attente_716.py` (nouveau, 4 scénarios, dans le style de `tests/test_champ_attente_713.py`) — fichier mono-issue avec `ATTENTE` (aucun événement), lot entièrement `ATTENTE` (aucun événement), lot mixte (événement `fichier_recu` toujours émis, non-régression), fichier sans `ATTENTE` (idem). Interception de `_poster_best_effort` comme `tests/test_evenements_issues_inbox_631.py`. Suite complète `pytest tests/` vérifiée verte (156 tests, dont les 4 nouveaux).

Hors périmètre (rappel de l'issue) : toute vérification automatique de la condition `ATTENTE`, inchangée.
