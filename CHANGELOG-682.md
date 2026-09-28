## #682 — cycle de vie des watchers locaux à la demande (Popen), sans systemd, portable Linux/Windows

Suite au diagnostic du chantier hybride (28/09/2026) : le cycle de vie des
watchers CCL reposait entièrement sur `systemctl --user`
(`app/watchers.py`, `app/interruption.py`), inexistant sous Windows.
Remplacé par un mécanisme portable réutilisant l'existant : auto-extinction
après inactivité déjà interne à `watcher.py`, isolation de groupe de
process déjà par-OS dans `watcher.py`, `start_new_session=True` déjà
utilisé côté POSIX par `app/issues_inbox.py`, sonde `_pid_vivant`
cross-plateforme (#584, dédupliquée par #680).

Terminologie retenue : watcher **local** = `new_issue.py` et le watcher
tournent sur la même machine, lancé à la demande (Linux ou Windows) ;
watcher **délégué** = mécanisme CCW (autre machine, SSH, inchangé par
cette issue).

- `app/watchers.py::demarrer_watcher` : lance désormais `watcher.py`
  directement via `subprocess.Popen([sys.executable, "watcher.py",
  "--config", ...])`, détaché (`start_new_session=True` POSIX,
  `CREATE_NEW_PROCESS_GROUP` Windows — flag déjà utilisé par
  `watcher.py::lancer_claude`), logs redirigés en ajout vers
  `cfg.fichier_log`. Le PID retourné est `proc.pid` (connu immédiatement,
  contrairement à l'ancien sondage du fichier PID nécessaire quand systemd
  gérait le process) ; `watcher.py` republie de toute façon ce même PID
  dans `logs/watcher-<nom>.pid` à son propre démarrage (issue #596,
  inchangé), sans effet puisque la valeur est identique.
- `app/watchers.py::arreter_watcher` : `SIGTERM` direct (`os.kill`,
  cross-plateforme — `TerminateProcess` sous Windows via la même API
  Python) au lieu de `systemctl --user stop`. Ne tue plus tout un cgroup
  (limite de l'ancien service, cause de l'incident relecture_bridge #73) :
  un arrêt manuel pendant une tâche en cours laisse désormais le process
  `claude` en cours orphelin plutôt que de le tuer aussi.
- Démarrage auto après création d'issue (§3.11) : déjà entièrement
  factorisé dans `redemarrer_si_eteint()` (issue #600), qui appelle
  `demarrer_watcher(cfg, forcer=False)` — celui-ci vérifie déjà
  `watcher_actif()` (basé sur `_pid_vivant`) avant tout lancement. Aucun
  changement nécessaire aux points d'appel (`app/issues.py`,
  `app/projet_ccw.py`, `scripts/watcher_issues_inbox.py`).
- `app/interruption.py::_neutraliser_relance_systemd` : supprimée.
  Protégeait contre une relance automatique par systemd
  (`Restart=on-failure`) qui aurait vu le SIGKILL de l'arbre de process
  comme un crash à relancer, contredisant le contrat #323 (« jamais de
  relance automatique après interruption »). Sans supervision systemd,
  aucun mécanisme ne peut plus relancer le watcher de son propre chef
  après un SIGKILL — aucun équivalent Popen nécessaire, le contrat est
  respecté sans action supplémentaire. L'étape correspondante disparaît de
  la liste `etapes` retournée par `POST /interrompre` (aucun consommateur
  frontend ne s'y référait par son nom).
- Comportement des boutons Lancer/Relancer/Arrêter (panneau latéral)
  inchangé du point de vue utilisateur — seule l'implémentation change.
  Non-régression Linux vérifiée : tests existants
  (`test_relancer_watcher_574`, `test_champ_relance_516`,
  `test_champ_redacteur_599`, `test_label_sans_redacteur_647`,
  `test_creation_issue_enrichie_634`, `test_projet_ccw_559`) passent tous
  sans modification ; cycle Popen/SIGTERM/`_pid_vivant` vérifié
  manuellement (process lancé, détecté vivant, SIGTERM appliqué).

Hors périmètre (inchangé, tel que demandé) : `app/ccw.py`, services NSSM,
`provisioning/windows/*.ps1` — un éventuel retrofit de CCW sur ce même
principe fera l'objet d'une issue séparée. Non traité non plus dans cette
issue (au-delà du strict périmètre demandé) : `systemd/watcher@.service`
et `installer_services.sh` restent présents dans le dépôt bien que devenus
obsolètes pour le déploiement CCL (dead code d'infrastructure, pas de code
applicatif) — nettoyage éventuel à discuter séparément.

Point d'attention (non bloquant, non demandé par cette issue) : sans
supervision OS, un process tué par `SIGTERM`/`SIGKILL` reste zombie tant
que le process `new_issue.py` (Flask) ne le réap pas — déjà documenté et
traité côté `app/interruption.py::_reaper_best_effort` pour le chemin
d'interruption ciblée (issue #323), mais pas côté
`app/watchers.py::arreter_watcher`/redémarrage forcé. Sans impact
fonctionnel observé (`watcher_actif()` se base sur la présence du fichier
PID, pas sur l'état du process, pour ce chemin) — seulement une
accumulation lente d'entrées zombies dans la table des process au fil des
redémarrages, à surveiller si ce comportement devient gênant en usage
prolongé.
