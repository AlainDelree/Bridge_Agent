## #680 — refactor: déduplique _pid_vivant vers la version cross-platform de watcher.py

Diagnostic du chantier « Bridge_Agent hybride » : `app/interruption.py`
(fonction locale `_pid_vivant`) et `app/issues_inbox.py`
(`watcher_inbox_actif`) réimplémentaient chacune la sonde « ce PID est-il
vivant ? » via un `os.kill(pid, 0)` POSIX-only, dupliquant et masquant
`watcher._pid_vivant` (cross-plateforme POSIX/Windows, issue #584) — même
risque que celui corrigé dans `watcher.py` lui-même pour `_watcher_actif`
(issue #673). `app/watchers.py::watcher_actif` utilisait déjà la version
partagée depuis l'issue #617, servant de modèle pour cette dédup.

Fix : les deux modules importent désormais `_pid_vivant` depuis `watcher`
(comme `app/watchers.py`) et l'utilisent à la place de leur `os.kill(pid, 0)`
local :
- `app/interruption.py` : suppression de la fonction locale `_pid_vivant`
  (lignes ~166-171) ; le `os.kill(candidat, 0)` inline de
  `interrompre_linux()` (détection du PID du watcher à interrompre) est
  également remplacé par un appel à `_pid_vivant`, même test dupliqué au
  même endroit.
- `app/issues_inbox.py::watcher_inbox_actif` : même substitution, plus
  `sys.path.insert(0, str(DOSSIER_SCRIPT))` ajouté (la racine du dépôt,
  contenant `watcher.py`, n'était pas garantie sur `sys.path` avant cet
  import — seul `scripts/` l'était).

Recherche exhaustive (`grep -rn "os.kill(pid" --include="*.py"`) : aucune
autre réimplémentation trouvée hors `watcher.py` lui-même et les fichiers de
test (qui simulent des process pour leurs scénarios, pas une sonde
générique). Comportement Linux inchangé (mêmes tests passés :
test_relancer_watcher_574, test_champ_relance_516,
test_evenements_issues_inbox_631, test_verrou_refus_precoce_584,
test_nettoyage_arbre_247, test_orphelin_verrou_perime_322) ; ces deux points
deviennent automatiquement sûrs côté Windows sans logique supplémentaire.
