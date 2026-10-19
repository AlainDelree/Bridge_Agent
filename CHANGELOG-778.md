## 19 octobre 2026 — issue #778

Correction de deux défauts cumulés dans les tests ajoutés par l'issue #777 :
des worktrees créés dans le VRAI répertoire `~/worktrees` du système (jamais
nettoyés) et une VRAIE notification de bureau (`notify-send`) déclenchée pour
une issue de test fictive.

- **Isolation du worktree de test.** `tests/test_arret_verdict_illisible_
  commits_777.py` (`_lancer_scenario`) redirigeait déjà `REP_TRAVAIL` vers un
  dossier jetable, mais oubliait `watcher.DOSSIER_WORKTREES_DEDIE` (constante
  globale, `~/worktrees` par défaut) — utilisée par `_chemin_worktree` pour
  TOUTE issue `mode_write` traitée via `traiter_issue`, y compris avec
  `max_write_parallele=1` (comportement #577). Désormais isolée sous le
  `tempfile.TemporaryDirectory()` du scénario, comme le font déjà
  `test_worktree_parallelisation_337.py`/`test_reprise_worktree_725.py`
  (issue #740).
- **Neutralisation de `notify-send`.** La même fonction de test ne plaçait
  un faux exécutable sur le PATH que pour `claude`/`gh` — pas pour
  `notify-send`, pourtant appelé directement par `_signaler_repli_worktree_
  echoue` (hors du dispatch `watcher.notifier` mocké par le test) quand
  toutes les tentatives de création de worktree échouent. Un faux
  `notify-send` (même technique que #611/`test_worktree_parallelisation_
  337.py`) est désormais préparé et vérifié par `verifier_faux_executables_
  actifs`.
- **Revue des autres tests du dépôt** créant des worktrees réels ou
  pouvant notifier (`traiter_issue`/`_traiter_issue_synchrone`/
  `_creer_worktree*` en mode_write non dry-run) : seul le fichier ci-dessus
  présentait le défaut — `test_worktree_parallelisation_337.py` et
  `test_reprise_worktree_725.py` isolaient déjà correctement `DOSSIER_
  WORKTREES_DEDIE` (#740) ; les autres fichiers appelant `traiter_issue`
  soit n'atteignent jamais la branche `mode_write` (label `mode_scratch`,
  issue déjà finalisée, `perimetre_dynamique` par défaut), soit appellent
  `_traiter_issue_synchrone` directement (en-dehors de la branche de
  création de worktree de `traiter_issue`).
- **Garde-fou ajouté** (`tests/garde_fou_faux_executables.py`) :
  `verifier_dossier_sous_tmp`, même esprit que `verifier_faux_executables_
  actifs` (#710) — échec FERMÉ si un chemin de test censé être jetable
  (`DOSSIER_WORKTREES_DEDIE` réaffecté) n'est pas sous le répertoire
  temporaire système. Appelé dans les trois fichiers de test qui
  redirigent cette constante (#777, #337, #725).
- Suppression des deux dossiers résiduels déjà présents dans `~/worktrees`
  (`test777a-issue97771`, `test777b-issue97772`) — orphelins, non
  enregistrés dans le vrai dépôt (`git worktree list`).

Aucune modification de `watcher.py` : le défaut était uniquement dans les
tests (isolation manquante), pas dans le code de production.
