# CHANGELOG — bridge_agent (issue #909, à fusionner)

## 22 novembre 2026 — issue #909

Mode interactif, étape 4 (étude #888, suite de #900/#901/#903) : le
TIMEOUT était jusqu'ici un délai brut de bout en bout — dans une session
interactive, la plupart du temps écoulé est du temps où CCL attend la
réponse d'Alain, une pause de réflexion ou une absence faisait donc
dépasser le délai et tuait la session. Le TIMEOUT est désormais suspendu
pendant que CCL attend Alain.

**Reprise de worktree.** Ce traitement reprend un worktree d'une tentative
précédente de cette même issue #909 : le cœur du mécanisme (script de hook,
branchement dans `watcher.py`) avait déjà été écrit par cette tentative
précédente — vérifié, testé manuellement (script de hook en sous-processus)
et conservé tel quel. Ce traitement a complété ce qui manquait : tests
automatisés dédiés, documentation (`docs/contexte/mode_interactif.md`,
`BRIDGE_AGENT_DOC.md`), ce fichier de changelog.

**Signal de pause : hooks Claude Code.** Signal retenu depuis l'étude #888
et déjà anticipé à l'étape 2 (#901, export de `BRIDGE_PROJET`/`BRIDGE_ISSUE`
dans le script de lancement tmux) : `Stop` et `Notification` (CCL a fini
son tour ou demande quelque chose = il attend Alain) posent une sentinelle
de pause ; `UserPromptSubmit` (Alain a répondu) et `SessionEnd` (fin de
session) la retirent. Les quatre appellent le même petit script autonome,
`scripts/hook_pause_interactif.py` — contrat impératif d'un hook : jamais
de sortie stdout/stderr, code de sortie TOUJOURS 0 (dossier absent, non
inscriptible, variables d'environnement manquantes, argument invalide),
écriture atomique (fichier temporaire + `os.replace`), ne dépend ni du PATH
ni d'un shell interactif (projet/numéro d'issue lus depuis `BRIDGE_PROJET`/
`BRIDGE_ISSUE`, déjà exportés par le script de lancement). La sentinelle,
`watcher._chemin_pause_interactif(nom_projet, numero)` =
`logs/interactif/<projet>-issue<numero>.pause` (même dossier et convention
que le rapport de clôture de l'étape 3, hors de tout worktree, gitignoré),
contient l'heure de début de pause (horloge murale).

**Réglages de hooks hors worktree.** `watcher._ecrire_reglages_hooks_
interactif` écrit, pour CHAQUE session tmux interactive, un fichier de
réglages JSON (`logs/tmux/<session>.settings.json`, à côté du script de
lancement existant — hors du worktree du projet piloté, jamais ajouté au
dépôt du projet ni capté par un commit), passé à Claude via `claude
--settings <chemin>` (`_construire_cmd_claude_interactif`, nouveau
paramètre `chemin_reglages`). Commande de hook construite avec
`sys.executable` + le chemin absolu de `scripts/hook_pause_interactif.py`
(jamais un nom nu qu'un `PATH` différent résoudrait autrement). Ces
réglages ne sont écrits, et cette option n'est ajoutée, QUE pour le
lancement d'une session interactive (`_traiter_issue_interactive`) — le
chemin automatique (`_construire_cmd_claude`, `claude --print`) n'a ni ce
paramètre ni cette option. Repli SANS hooks (log.warning, lancement de la
session poursuivi normalement) si l'écriture du fichier de réglages échoue
— jamais un blocage du lancement pour autant.

**Suspension du TIMEOUT.** `watcher._surveiller_session_tmux` reçoit un
nouveau paramètre `chemin_pause` : à chaque sondage, si la sentinelle
existe, ce sondage ne compte pas contre l'échéance (reculée d'exactement la
durée dormie) — une ligne de log est écrite au début et à la fin de chaque
pause, avec sa durée. L'heure de début de pause est lue depuis le contenu
de la sentinelle (`watcher._heure_debut_pause` — repli sur `st_mtime` du
fichier si le contenu est corrompu, jamais faute de mieux). Un rapport de
clôture stable reste prioritaire sur tout, y compris pendant une pause
active (Alain peut avoir quitté juste après avoir fait écrire le rapport,
avant que la sentinelle ne soit retirée).

**Durée maximale absolue.** `watcher.DUREE_MAX_PAUSE_INTERACTIVE_S` (12h,
constante nommée, facile à changer) : au-delà, `_surveiller_session_tmux`
retourne `"pause_trop_longue"`, traité par `_traiter_issue_interactive`
EXACTEMENT comme un TIMEOUT dépassé (session tuée, verrou et place de
parallélisme libérés, label `needs-human`, jamais de relance), avec un
commentaire GitHub distinct précisant clairement qu'il s'agit d'une pause
trop longue et NON d'un dépassement du délai de travail (celui-ci, suspendu
pendant la pause, n'a compté que du temps de travail réel).

**Redémarrage du watcher pendant une pause.** La sentinelle (hors worktree,
contenu horloge murale) survit sans changement à un redémarrage du
watcher — comme le rapport de clôture et le script de lancement tmux déjà
gérés depuis #901/#903. Solution retenue, **volontairement prudente** :
comme pour toute session déjà existante retrouvée au redémarrage (point 5,
#901), la surveillance reprend avec une échéance FRAÎCHE de `timeout`
secondes plutôt qu'une reconstitution précise du temps de travail déjà
écoulé avant le redémarrage — ce calcul n'étant pas trivial sans persister
davantage d'état, le choix retenu ne risque JAMAIS de tuer une session à
tort après un redémarrage (il ne peut qu'être trop généreux, jamais trop
sévère). Si une pause était déjà en cours au moment du redémarrage, la
sentinelle (contenu jamais réinitialisé) est prise en compte dès le premier
sondage suivant la reprise, y compris pour la limite absolue des 12h —
comptée depuis la VRAIE heure de début de la pause, pas depuis le
redémarrage : une pause déjà trop longue avant le redémarrage est donc
immédiatement détectée comme telle, jamais relancée artificiellement.

**Fin de session.** La sentinelle est désormais retirée par `watcher.py`
lui-même à CHAQUE fin de session (rapport de clôture, session disparue sans
rapport, TIMEOUT, pause trop longue) — en plus du retrait par le hook
`UserPromptSubmit`/`SessionEnd` — pour ne jamais en laisser une orpheline
qui fausserait une session ultérieure du même numéro.

**Chemin automatique** (issues sans le label `mode_interactif`, immense
majorité) : strictement inchangé — aucun fichier de réglages écrit, aucune
option `--settings`, `_construire_cmd_claude` ne reçoit aucun nouveau
paramètre.

Tests ajoutés : `tests/test_mode_interactif_pause_909.py` (25 scénarios) —
script de hook en sous-processus réel (pose/idempotence/retrait de la
sentinelle, variables d'environnement manquantes, argument invalide,
dossier non inscriptible : code de sortie toujours 0, jamais de sortie
stdout/stderr) ; `_chemin_pause_interactif`/`_heure_debut_pause` (lecture,
repli `st_mtime`, fichier absent) ; `_ecrire_reglages_hooks_interactif`
(structure des quatre hooks, chemins absolus, jamais pour le chemin
automatique) ; `_construire_cmd_claude_interactif` avec/sans réglages ;
`_surveiller_session_tmux` (TIMEOUT suspendu pendant une pause puis repris,
pause trop longue, rapport prioritaire même en pause, non-régression sans
sentinelle) ; orchestration complète de `_traiter_issue_interactive`
(pause trop longue ⇒ `needs-human` avec message distinct, sentinelle
retirée à chaque type de fin de session, reprise après un redémarrage
pendant une pause sans relancer ni tuer à tort) ; chemin automatique jamais
concerné par les réglages de hooks. `tests/test_mode_interactif_tmux_901.py`
mis à jour (nouveau paramètre `chemin_pause` de `_surveiller_session_tmux`
dans les mocks de 3 tests existants). Suite complète (`pytest tests/`) :
721 passés (696 déjà existants + 25 nouveaux), les 11 erreurs restantes
(`tmp_dir_factory` manquant, `test_signature_attente_825.py`) sont
préexistantes, sans rapport avec cette issue.

Documentation : `docs/contexte/mode_interactif.md` (nouvelle section
« Suspension du TIMEOUT pendant l'attente d'Alain ») et `BRIDGE_AGENT_DOC.md`
§4 + pied de page mis à jour. `CONTEXTE.md` non modifié (son index pointe
déjà vers `docs/contexte/mode_interactif.md`, rien d'indispensable à y
ajouter).

**Essais manuels pour Alain (TIMEOUT court, 240s) — non exécutables depuis
cet environnement d'agent (il faut un vrai terminal interactif Claude Code
avec hooks actifs) :** (a) laisser CCL finir un petit travail puis ne rien
faire pendant plus de 6 minutes — la session n'est pas tuée, le log du
watcher montre la pause ; (b) répondre à CCL — la pause se termine dans le
log, le délai reprend ; (c) redémarrer le watcher pendant une pause — la
session reste en vie, pas de relance ; (d) quitter Claude pendant une
pause — fin de session sans rapport comme à l'étape 3, et le fichier de
pause a disparu.
