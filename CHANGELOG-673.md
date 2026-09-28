## #673 — fix(watcher): _watcher_actif() réutilise _pid_vivant() au lieu de os.kill(pid, 0)

`watcher.py` : `_watcher_actif()` (ligne ~2240) sondait la vivacité d'un
process watcher via `os.kill(pid, 0)`, idiome purement POSIX. Sous Windows,
le signal `0` correspond à `CTRL_C_EVENT` dans l'API Win32 — `os.kill(pid, 0)`
y envoie un vrai Ctrl+C via `GenerateConsoleCtrlEvent` : sur son propre pid
(cas de `_compter_watchers_actifs()`, qui teste tous les projets connus y
compris le projet courant) le process s'auto-interrompt
(`KeyboardInterrupt` → `sys.exit(0)` dans `main()`) — crash silencieux
observé 3 fois le 28/09/2026 sur CCW-Watcher (bridge_agent) ; sur le pid
d'un autre projet, `GenerateConsoleCtrlEvent` échoue avec
`OSError: [WinError 87]` (cause très probable de l'erreur repérée le
27/09/2026 sur CCW-Watcher-Actualise, non diagnostiquée jusqu'ici).

La fonction sœur `_pid_vivant()` (issue #584) gérait déjà correctement les
deux plateformes (`os.kill(pid, 0)` sur POSIX, `OpenProcess` en droits
minimaux sur Windows) mais n'était pas réutilisée ici. `_watcher_actif()`
délègue désormais à `_pid_vivant()` : plus aucun appel direct à
`os.kill(pid, 0)`, comportement inchangé sur Linux, plus de faux Ctrl+C ni
de WinError 87 sur Windows. Repli identique dans les 4 cas testés
manuellement (pas de fichier PID, PID vivant, PID mort, PID invalide) ;
aucun test automatisé dédié à `_watcher_actif()` n'existait au préalable.
