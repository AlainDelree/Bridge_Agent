# CHANGELOG — bridge_agent (issue #901, à fusionner)

## 17 novembre 2026 — issue #901

Mode interactif, étape 2 (étude #888, suite de #900) : pour une issue
`mode_interactif` effective, CCL est désormais réellement lancé dans une
session tmux détachée et surveillé de façon non bloquante, au lieu du
`claude --print` + `proc.communicate(timeout=...)` bloquant du chemin
automatique — strictement inchangé par ailleurs.

**Lancement.** `watcher._traiter_issue_interactive` (nouvelle fonction,
appelée par `_traiter_issue_synchrone` juste avant sa boucle de tentatives
habituelle, à laquelle elle ne touche pas) lance CCL dans une session tmux
nommée `bridge-<projet>-issue<numero>` (`_nom_session_tmux`, nom du projet
assaini). `watcher.lancer_claude` reçoit un nouveau paramètre `mode_tmux`
(False partout ailleurs, comportement automatique inchangé) : quand True,
la construction du PROMPT (CONTEXTE/CONSIGNES/corps/garde-fou) reste
EXACTEMENT la même que le chemin automatique — seule la suite change,
remplacée par `_lancer_session_tmux` plutôt que Popen/communicate.
`_construire_cmd_claude_interactif` reprend `_construire_cmd_claude` sans
`--print`. La commande est écrite dans un petit script shell
(`_ecrire_script_lancement_tmux`, sous `logs/tmux/`) qui exporte
`BRIDGE_PROJET`/`BRIDGE_ISSUE` (utiles aux hooks des étapes suivantes), `cd`
dans le répertoire de travail puis `exec` la commande — évite de confier un
prompt long, avec guillemets et retours à la ligne, à l'assemblage
"shell-command" de `tmux new-session` (simple concatenation par espaces,
sans ré-échappement).

**Surveillance non bloquante.** `_surveiller_session_tmux` sonde
périodiquement (`tmux has-session`, 15s) jusqu'à ce que la session
disparaisse ou que l'échéance (le TIMEOUT de l'issue, qu'Alain fixe
simplement long pour une issue interactive) soit dépassée. Au dépassement,
la session est tuée (`_tuer_session_tmux`) — nettoyage équivalent à celui
du chemin automatique.

**Fin de session.** Dans tous les cas (fin normale ou TIMEOUT), un
commentaire explicite est posté sur l'issue — jamais de fermeture
automatique, jamais le label `done`. Le verrou et la place de
parallélisme sont libérés par le mécanisme existant
(`_nettoyer_apres_traitement`, déjà appelé par le `finally` de
`_traiter_issue_synchrone`) — mécanisme choisi car déjà en place, agnostique
du mode et le moins intrusif possible. Clôture manuelle par Alain pour
l'instant, comme décidé.

**Commande d'attache.** Postée dans l'issue ET journalisée dès le
lancement (`tmux attach -t bridge-<projet>-issue<numero>`).

**Reprise au redémarrage du watcher (point 5).** Avant de lancer quoi que
ce soit, `_traiter_issue_interactive` vérifie si une session de ce nom
existe déjà (`_tmux_session_existe`) — si oui, reprend seulement la
surveillance, sans relancer CCL ni recréer de verrou orphelin (le verrou
périmé du watcher précédent est repris normalement par
`acquerir_verrou` ; aucun `claude_pgid` n'est jamais associé au verrou pour
une session tmux, donc le nettoyage d'orphelin existant ne risque pas de
tuer la session en cours).

**Survie à un redémarrage du service systemd (point 5, investigation).**
`systemd/watcher@.service` ne déclare pas `KillMode=` — valeur implicite
`control-group`, qui tue tous les descendants (dont un serveur tmux lancé
en sous-process) à l'arrêt/redémarrage du service. `_lancer_session_tmux`
lance donc via `systemd-run --user --scope --collect` quand ce binaire est
disponible, pour placer la session dans un scope systemd INDÉPENDANT du
service — un redémarrage de `watcher@<projet>` ne devrait alors pas la
tuer. Repli silencieux (log.warning) sur un lancement direct si
`systemd-run` est absent ou échoue (survie alors non garantie). **Non
vérifié en conditions réelles** — aucun environnement systemd --user
disponible pour ce test pendant cette issue, voir la liste d'essais
manuels du rapport de clôture.

**Repli automatique (point 6).** tmux absent du PATH, agent différent de
`claude`, OS Windows (défensif — `est_interactif` écarte déjà Windows via
le label `for-windows`), ou `tmux new-session` en échec malgré le repli
`systemd-run` : avertissement posté dans l'issue ET dans le journal, puis
`_traiter_issue_interactive` retourne False — `_traiter_issue_synchrone`
poursuit alors EXACTEMENT comme pour une issue non interactive (boucle de
tentatives standard, inchangée).

**Chemin automatique.** Strictement inchangé : `_construire_cmd_claude`,
le Popen/communicate existant et `_executer_une_tentative` ne sont pas
modifiés ; le nouveau paramètre `mode_tmux` de `lancer_claude` vaut False
partout ailleurs et n'a aucun effet observable dans ce cas.

Documentation : nouveau fichier de domaine `docs/contexte/mode_interactif.md`
(mécanique complète), `CONTEXTE.md` (index des fichiers de domaine) et
courte mention dans `BRIDGE_AGENT_DOC.md` §4 (label) + ligne « Dernière mise
à jour ».

Tests ajoutés : `tests/test_mode_interactif_tmux_901.py` (23 scénarios) —
nom de session (format, assainissement), construction de la commande claude
interactive (sans `--print`), script de lancement (export/cd/exec, prompt
échappé), construction de la commande tmux (`_lancer_session_tmux` : avec
`systemd-run`, sans, repli si `systemd-run` échoue, tmux absent, échec de
`tmux new-session`), surveillance avec session simulée (fin normale et
expiration), garde-fous de `lancer_claude(mode_tmux=True)` (Windows, agent
non `claude`, dry-run, délégation avec le même prompt que le chemin
automatique), et orchestration complète de `_traiter_issue_interactive`
(lancement + surveillance jusqu'à fin normale, TIMEOUT avec nettoyage,
reprise d'une session déjà existante sans relancer CCL, repli si le
lancement tmux échoue, silence en dry-run). Suite complète (`pytest tests/`)
inchangée par ailleurs : 677 passés (654 déjà existants + 23 nouveaux), les
11 erreurs restantes (`tmp_dir_factory` manquant, `test_signature_attente_825.py`)
sont préexistantes, sans rapport avec cette issue.

**Limites restantes (étapes suivantes de l'étude #888, décidées avec
Alain) :** suspension du délai pendant que CCL attend Alain, alerte, et
détection de fin par fichier de rapport — le TIMEOUT s'applique ici tel
quel comme échéance de temps réel brute. Les hooks Claude Code (fin de
tour, message envoyé, fin de session) ne sont pas câblés par cette étape,
seule la variable d'environnement qu'ils liront plus tard
(`BRIDGE_PROJET`/`BRIDGE_ISSUE`) est déjà exportée dans la session.

**Non vérifiable de bout en bout depuis cet environnement d'agent** (il
faut un vrai terminal interactif et un service systemd --user réel) — voir
la liste d'essais manuels fournie dans le rapport de clôture de l'issue.
