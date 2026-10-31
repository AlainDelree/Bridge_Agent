## Issue #833 — Périmètre dynamique : ajout du dossier du projet (REP_TRAVAIL) en lecture et exécution seules, avec contrôle d'écriture

Pour un projet à périmètre dynamique (`PERIMETRE_DYNAMIQUE = true`, issue
#125), le périmètre d'une issue était jusqu'ici le seul `REPO_CIBLE` —
`REP_TRAVAIL` (le dossier du projet lui-même, où vit le code de l'outil)
n'apparaissait nulle part. Pour un outil d'audit multi-dépôts comme
`diagnostique_programme`, dont le code vit dans son propre `REP_TRAVAIL` et
doit analyser d'AUTRES dépôts, cela rendait l'agent incapable de lire ou
d'exécuter son propre outil dès que l'issue visait un autre dépôt que le
sien (clause de périmètre appliquée strictement).

- **`watcher.py::_resoudre_contexte_execution`** : pour un projet à
  périmètre dynamique, si `REP_TRAVAIL` (résolu) est DISJOINT de
  `REPO_CIBLE` (résolu) — ni identique, ni l'un contenu dans l'autre — il
  est ajouté au nouveau champ `ContexteExecution.chemin_outil_lecture_exec`,
  SANS modifier `perimetre_effectif` ni `cwd_effectif` (qui restent
  `REPO_CIBLE` seul, comportement inchangé). Identique ou imbriqué (dans un
  sens ou dans l'autre) : rien n'est ajouté, un message d'information est
  journalisé. **Agent `vibe`** : jamais ajouté, même disjoint — `vibe` n'a
  aucune option de ligne de commande ouvrant un répertoire en lecture seule
  (`--workdir` seul) ; un projet dynamique réglé sur cet agent reste donc
  incapable de lire/exécuter son propre code hors de `REPO_CIBLE` après
  cette issue (limitation documentée, pas corrigée — hors périmètre de
  cette issue). Nouvelle fonction `_chemins_disjoints`.
- **`watcher.py::lancer_claude`/`diagnostiquer_echec`** (les deux gabarits
  de prompt qui contiennent `{clause_perimetre}`) : nouveau paramètre
  `chemin_outil_lecture_exec`. Quand il est fourni, une phrase est ajoutée à
  la clause de périmètre : le dossier du projet est lisible et exécutable
  (import/lancement de son code, par exemple via `PYTHONPATH`), mais toute
  écriture y est interdite (réservée à `REPO_CIBLE`, et au scratch en
  lecture active) ; la phrase rappelle `PYTHONDONTWRITEBYTECODE=1` pour ne
  pas y laisser Python écrire de bytecode. **Sans ce paramètre (défaut
  `None`), la clause reste identique, caractère pour caractère, au texte
  actuel** — projets à périmètre fixe, ou `REP_TRAVAIL` identique/imbriqué.
- **Contrôle technique d'écriture** (nouvelles fonctions
  `_preparer_controle_outil`/`_verifier_violation_outil`, appelées dans les
  TROIS modes, contrairement au garde-fou scratch #327 réservé à la lecture
  active) : réutilisent tel quel `_statut_git_rep_travail`/
  `_restaurer_rep_travail_modifie` (#327) sur ce dossier supplémentaire.
  Écriture détectée pendant une tentative ⇒ restaurée, échec DÉFINITIF (pas
  de nouvelle tentative), label `needs-human`, commentaire et notification
  dédiés (« écriture détectée dans le code de l'outil — dossier en lecture
  seule »). Dossier non-git : aucun contrôle, un seul message journalisé
  (best-effort, comme le garde-fou existant). Limite héritée du #327,
  documentée : les fichiers ignorés par git ne sont pas détectés.
- **`BRIDGE_AGENT_DOC.md`** (§3.3, §7, §16) : documente cette règle,
  rappelle que le confinement reste une convention de prompt complétée par
  une détection après coup, et les deux limites ci-dessus (fichiers ignorés,
  agent `vibe`).
- **Tests** (`tests/test_perimetre_outil_lecture_exec_833.py`, 14
  scénarios) : relations REP_TRAVAIL/REPO_CIBLE (disjoint, identique,
  imbriqué dans les deux sens, agent `vibe`) ; clause de prompt avec/sans ce
  chemin pour les deux gabarits (identité caractère pour caractère vérifiée
  dans le cas sans) ; écriture détectée dans les trois modes (restaurée,
  échec définitif, une seule tentative malgré `MAX_ESSAIS` > 1,
  `needs-human`) ; fichier ignoré par git non détecté ; dossier non-git (un
  seul message) ; `cwd` toujours `REPO_CIBLE`.

Aucun fichier `configs/*.conf` modifié. Aucune régression sur les 87
fichiers de tests Python existants (`tests/lancer_tous_les_tests.py`,
88/88 avec le nouveau fichier) ni sur la suite JavaScript (431 tests, 23
fichiers, inchangée — aucun fichier JS touché par cette issue).
