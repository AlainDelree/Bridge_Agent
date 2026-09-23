## 23 septembre 2026 — issue #596

Réactivation des watchers de projet en services `systemd --user`
(`watcher@<projet>.service`), abandonnée une première fois par l'issue #119 :
`Restart=always` + `RestartSec=10` relançait systématiquement tout watcher
qui venait de s'éteindre proprement pour inactivité (`DELAI_INACTIVITE_MIN`,
#199/#200), en boucle sans fin. Constaté concrètement le 22/09/2026 lors d'un
redémarrage du ThinkPad ayant interrompu plusieurs watchers en cours, sans
aucune supervision pour les relancer.

Correction de l'incompatibilité : `Restart=on-failure` + `SuccessExitStatus`
sur un code de sortie dédié à l'auto-extinction (distinct de 0), pour que
systemd relance un crash réel mais jamais un arrêt volontaire — qu'il
s'agisse de l'auto-extinction pour inactivité ou d'une interruption manuelle
(#323).

- `watcher.py` :
  - Nouvelle constante `EXIT_INACTIVITE = 42` — code de sortie de
    l'auto-extinction pour inactivité, désormais `sys.exit(EXIT_INACTIVITE)`
    au lieu de `sys.exit(0)`.
  - `main()` publie désormais son propre fichier PID
    (`logs/watcher-<nom>.pid`) dès son démarrage, quel que soit son mode de
    lancement (terminal, `systemctl`, ou bouton de l'interface) — jusqu'ici
    c'était uniquement `app/watchers.py::demarrer_watcher` (via
    `subprocess.Popen`) qui l'écrivait après coup, ce qui n'aurait plus
    fonctionné pour un watcher lancé directement par systemd. Toute la
    détection existante basée sur ce fichier (`watcher_actif`,
    `_watcher_actif`/`detecter_conflit_watcher`, `interrompre_linux`) reste
    inchangée. Nettoyage du fichier PID ajouté aussi sur `KeyboardInterrupt`
    (Ctrl+C manuel), par symétrie avec l'auto-extinction.
- `systemd/watcher@.service` : `Restart=always` → `Restart=on-failure`,
  ajout de `SuccessExitStatus=42`.
- `installer_services.sh` : la liste de projets codée en dur est remplacée
  par une lecture dynamique de `configs/*.conf` valides via
  `app.projets.lister_projets()` (même définition de « projet actif » que le
  reste de l'interface) ; mise à jour des commentaires d'en-tête (l'ancien
  avertissement de conflit avec le bouton « Lancer/Arrêter watcher » de
  l'interface ne s'applique plus, les deux mécanismes étant désormais
  unifiés).
- `app/watchers.py` :
  - `demarrer_watcher()` appelle `systemctl --user start|restart
    watcher@<projet>` au lieu de `subprocess.Popen` (avec un court sondage
    du fichier PID pour renvoyer le nouveau pid).
  - `arreter_watcher()` appelle `systemctl --user stop watcher@<projet>` au
    lieu d'un `os.kill(pid, SIGTERM)` direct.
  - `watcher_actif()`/`chemin_pid()` inchangés (toujours basés sur le
    fichier PID).
  - Imports `signal`/`sys` retirés (devenus inutiles) ainsi que la constante
    `DOSSIER_SCRIPT` (plus utilisée).
- `app/interruption.py` : nouvelle fonction
  `_neutraliser_relance_systemd()`, appelée par `interrompre_linux()` juste
  après confirmation de la mort de l'arbre de process. Sans elle, le SIGKILL
  existant du bouton « Interrompre cette issue » (#323) serait vu par
  systemd comme un crash et le watcher serait relancé après 10 s par
  `Restart=on-failure` — contredisant le contrat de #323 (« jamais de
  relance automatique après une interruption manuelle »). Appelle
  `systemctl --user stop watcher@<projet>`, un arrêt délibéré du point de
  vue de systemd qui n'active jamais la politique `Restart=`. Best-effort :
  ne fait jamais échouer l'interruption elle-même (watcher lancé hors
  systemd, ou service non installé pour ce projet).
- `BRIDGE_AGENT_DOC.md` : remplacement du bloc « Historique : services
  systemd (abandonnés) » par la documentation du mécanisme actif
  (démarrage/relance, installation dynamique, unification avec les boutons
  de l'interface, interaction avec le bouton Interrompre, absence de sudo
  nécessaire) ; mise à jour de la section « Cycle de vie des watchers » pour
  mentionner systemd et le nouveau code de sortie `EXIT_INACTIVITE`.

Hors périmètre (conforme à l'intention de l'issue) : `new_issue.py` reste
lancé manuellement (pas de service systemd dédié) ; le watcher spool
(`scripts/watcher_issues_inbox.py`) garde son propre mécanisme de
durée/échéance.

Vérification : suite de tests existante (20 fichiers `tests/test_*.py`,
dont `test_auto_extinction_217.py` qui pilote le vrai `watcher.main()`)
toujours verte après ces changements ; `py_compile` OK sur tous les fichiers
Python modifiés. L'installation réelle des services (`installer_services.sh`,
`systemctl --user enable --now`) et la vérification post-redémarrage du
ThinkPad restent à faire par Alain — hors de portée d'une session CCL en
worktree isolé (nécessite d'agir sur `~/.config/systemd/user/` et
`loginctl enable-linger` de la session réelle, hors du périmètre de ce
worktree).
