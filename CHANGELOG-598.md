## 23 septembre 2026 — issue #598

Ajout d'un `PATH` explicite dans `systemd/watcher@.service` : les services
systemd --user démarrent avec un `PATH` minimal, sans les chemins ajoutés
par le shell interactif — notamment `~/.npm-global/bin` (où réside `claude`)
et `~/Bridge_Agent/venv/bin`. Après la migration systemd de #596, l'issue #67
(relecture_bridge) a échoué immédiatement avec « Claude Code introuvable
(claude non trouvé dans PATH) ». Même piège que celui déjà documenté côté
CCW/NSSM (§16 du DOC).

Un correctif manuel (`systemctl --user edit --full` + `daemon-reload` +
`restart`) avait déjà été appliqué en prod sur toutes les instances, mais
ne vivait que dans `~/.config/systemd/user/` — perdu à la prochaine
exécution d'`installer_services.sh`, qui écrase ce fichier depuis le
gabarit du dépôt.

- `systemd/watcher@.service` : directive `Environment="PATH=..."` ajoutée
  dans `[Service]`, en chemins absolus (systemd n'interprète pas `~`) —
  `/home/alain/Bridge_Agent/venv/bin`, `/home/alain/.npm-global/bin`,
  `/home/alain/.local/bin`, `/home/alain/bin`, puis le PATH système standard.
  Validé avec `systemd-analyze verify`.
- `BRIDGE_AGENT_DOC.md` (section « Watchers supervisés par systemd --user ») :
  nouveau point documentant l'exigence du `PATH` explicite, la cause, et la
  commande de vérification post-installation (`/proc/<pid>/environ`).
