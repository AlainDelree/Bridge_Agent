## #698 — Suppression du doublon de logs des watchers locaux (suite #696)

- Diagnostic #696 confirmé : `app/watchers.py::demarrer_watcher()` redirige
  déjà stdout/stderr du process `watcher.py` lancé vers `cfg.fichier_log`,
  mais `watcher.py::configurer_logs()` ajoutait en plus un
  `StreamHandler(sys.stdout)` à côté du `FileHandler` — une fois stdout
  redirigé par le parent vers ce même fichier, chaque ligne de log s'y
  écrivait deux fois. Régression #682 (avant, `systemctl --user` envoyait
  stdout/stderr vers le journal systemd, jamais vers ce fichier).
- Correction : retrait de `logging.StreamHandler(sys.stdout)` de la liste
  `handlers` dans `configurer_logs()` (`watcher.py`), ne conserve que
  `handler_fichier`. Le filet de sécurité de la redirection stdout/stderr
  côté `app/watchers.py::demarrer_watcher()` reste intact pour la fenêtre
  avant `configurer_logs()` (crash très précoce) — pas de duplication
  possible à ce stade puisque rien d'autre n'écrit dans le fichier.
- `_forcer_utf8(sys.stdout/stderr)` conservé (toujours utile pour ce filet
  de sécurité et pour NSSM côté CCW) ; commentaire de `configurer_logs()`
  mis à jour en conséquence.
- Vérifié : aucun test ni autre code ne dépend d'une capture de logs sur
  stdout pour `watcher.py` (seul `scripts/watcher_issues_inbox.py`, hors
  périmètre de cette issue, a son propre `configurer_logs()` distinct avec
  un `StreamHandler` mais sans `FileHandler` — pas concerné par le doublon).
