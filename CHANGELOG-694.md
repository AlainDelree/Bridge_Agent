# CHANGELOG-694

## Issue #694 — Issue F (plan hybride Windows) : app/issues_inbox.py portable

- `demarrer_watcher_inbox()` (app/issues_inbox.py) : `subprocess.Popen(...,
  start_new_session=True)` était POSIX-only et levait une exception sous
  Windows. Remplacé par une branche `os.name == "nt"` utilisant
  `CREATE_NEW_PROCESS_GROUP`, même pattern que `watcher.py::lancer_claude`
  (déjà suivi par l'issue D pour `app/watchers.py`). Comportement Linux
  inchangé.
- Ajout d'un commentaire bref aux deux appels `os.kill(pid, signal.SIGTERM)`
  (`demarrer_watcher_inbox`, `arreter_watcher_inbox`) confirmant leur
  compatibilité Windows (CPython route SIGTERM vers `TerminateProcess()`,
  hors du piège `os.kill(pid, 0)`/`CTRL_C_EVENT` découvert issue #682) —
  aucun changement de code sur ce point, juste une note pour éviter une
  future modification par réflexe.
