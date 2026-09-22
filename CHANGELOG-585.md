## 22 septembre 2026 — issue #585

Retrait du diagnostic temporaire #157 (`app/diag_heartbeat.py`), balisé
« à retirer » depuis son ajout le 19 juillet mais resté câblé plus de
deux mois après validation du correctif heartbeat/SSE. Procédure de
retrait suivie telle qu'écrite dans le module lui-même : suppression du
fichier (88 lignes), de l'import et des quatre appels `diag_heartbeat.log_*()`
dans `app/cycle_vie.py` (heartbeat, connexion/déconnexion SSE, arrêt par
`surveiller_heartbeat`), de l'import et de l'enregistrement de route dans
`app/__init__.py`, et du bloc `console.log`/`fetch('/diag-visibilite')`
dans `demarrerCycleVie()` (`static/js/app.js`) — en conservant
`envoyerHeartbeat()` sur `visibilitychange`, qui fait partie du correctif
et non du diagnostic. Point de sécurité traité au passage : la route
`/diag-visibilite` disparaît avec le reste, ce qui élimine une route POST
qui n'était pas protégée par `login_requis`, contrairement au reste de
l'application. `logs/heartbeat_diag.log` n'existait pas dans ce
worktree, rien à supprimer sur ce point. Vérifié : `py_compile` OK,
`create_app()` démarre sans erreur, `/diag-visibilite` répond 404, aucune
référence résiduelle (`grep` sur `diag_heartbeat`/`diag-visibilite`/`DIAG
#157`), suite de tests existante verte (un seul échec,
`test_init_git_local_258.py`, pré-existant et sans rapport — dépendant du
réseau, échoue identiquement avant ce commit).
