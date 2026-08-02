## 2 août 2026 — issue #337

Parallélisation des issues `mode_write` via `git worktree` : `watcher.py`
peut désormais traiter plusieurs tâches d'écriture **en parallèle**, chacune
dans un répertoire isolé sur sa propre branche, au lieu du traitement
strictement séquentiel historique. Les issues `mode_lecture`/`mode_scratch`
restent traitées séquentiellement dans `REP_TRAVAIL`, inchangées.

- Nouvelle clé `.conf` `MAX_WRITE_PARALLELE` (entier, défaut `2`) : nombre
  maximum de tâches `mode_write` concurrentes. `1` (ou `0`) = comportement
  séquentiel historique intégral, aucun thread ni worktree créé.
- `traiter_issue` (nouveau point d'entrée public) décide, pour chaque issue
  `mode_write` prête, entre traitement séquentiel classique et
  parallélisation : la première tâche détectée sans autre `mode_write` déjà
  en cours est dispatchée dans un thread ciblant `REP_TRAVAIL` directement
  (sans worktree, nécessaire pour que la boucle principale reste libre de
  détecter une deuxième tâche pendant que la première tourne) ; les
  suivantes, sous `MAX_WRITE_PARALLELE`, obtiennent chacune un worktree
  dédié (`<REP_TRAVAIL>/../<PROJET>-issue<N>`, branche
  `worktree-issue-<N>`, créés via `git worktree add`). Le corps de
  traitement existant (`_traiter_issue_synchrone`) est inchangé, à
  l'exception du chemin de travail effectif qu'il reçoit désormais en
  paramètre.
- Liste thread-safe (`threading.Lock` + liste) des tâches `mode_write`
  actuellement en thread (numéro, chemin du worktree ou `None`, thread
  Python), purgée des threads terminés à chaque décision de dispatch et en
  tête de boucle principale.
- Garde-fous à la création du worktree : chemin ou branche déjà existants,
  ou tout autre échec de `git worktree add` → repli propre sur le
  traitement séquentiel (l'issue attend qu'un slot se libère), jamais
  d'exception propagée.
- `lancer_claude` reçoit `chemin_worktree` : injecte dans le prompt, en
  worktree uniquement, un bloc d'avertissement (chemin, branche, consigne
  d'écrire l'entrée changelog dans `CHANGELOG-<N>.md` plutôt que
  `CHANGELOG.md` — voir `scripts/fusionner_changelog.py`, issue #336).
  Toutes les opérations déjà paramétrées par `cwd`/`perimetre` (backup,
  clause de périmètre du prompt, opérations git de garde-fou) reçoivent
  déjà le chemin de travail effectif (worktree ou `REP_TRAVAIL`) — aucun
  changement de signature nécessaire sur ces fonctions.
- Verrou anti-collision (#189/#322) posé par le chemin de travail effectif
  de la tâche (`REP_TRAVAIL` ou le worktree), et non plus systématiquement
  par `REP_TRAVAIL` seul : deux worktrees du même projet obtiennent deux
  verrous distincts et tournent sans s'attendre l'un l'autre.
- Fin de tâche en worktree : **aucune suppression automatique** (ni
  `git worktree remove`, ni suppression de branche) — Alain merge et pousse
  manuellement une fois le travail relu. Numéro d'issue, chemin du worktree
  et branche journalisés clairement.
- Auto-extinction (#199/#200) : ne se déclenche plus tant qu'un thread
  `mode_write` tourne encore, même au-delà de `DELAI_INACTIVITE_MIN` —
  réévaluée à chaque cycle.
- `BRIDGE_AGENT_DOC.md` §13 documente le mécanisme et `MAX_WRITE_PARALLELE`.
- Test de non-régression `tests/test_worktree_parallelisation_337.py` :
  nommage chemin/branche, création + replis (chemin/branche déjà pris),
  purge des threads terminés, scénario de bout en bout à deux issues
  `mode_write` concurrentes (première dans `REP_TRAVAIL`, seconde dans un
  worktree dédié, worktree conservé après coup), et non-régression avec
  `MAX_WRITE_PARALLELE = 1`.
