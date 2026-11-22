# Mode interactif — lancement et surveillance (étude #888)

État actuel du mécanisme (pas l'historique — voir `CHANGELOG.md` pour le
déroulé des issues #900/#901). Référence courte dans `BRIDGE_AGENT_DOC.md`
§4 ; détail complet ici.

## Déclenchement

Label GitHub `mode_interactif` (constante `watcher.LABEL_INTERACTIF`),
orthogonal aux labels de mode (`mode_write`/`mode_scratch`). Posé via le
champ d'en-tête `INTERACTIF` du dépôt d'issues par fichier (`oui` exact).
`watcher.est_interactif(labels, mode)` décide s'il est **effectivement**
retenu — jamais un rejet, deux replis vers le comportement automatique :
lecture seule (jamais interactive) et issue destinée à Windows (label
`for-windows` — le mode interactif ne concerne que le ThinkPad/CCL).

## Lancement (issue #901, étape 2)

Pour une issue interactive effective, `watcher._traiter_issue_interactive`
remplace la boucle de tentatives habituelle : CCL est lancé une seule fois,
dans une session **tmux détachée**, nommée `bridge-<projet>-issue<numero>`
(`_nom_session_tmux` — nom du projet assaini, seuls lettres/chiffres/
tiret/underscore conservés).

- Même prompt, même répertoire de travail, mêmes options (`--model`,
  `--dangerously-skip-permissions`) que le chemin automatique : construits
  par `watcher.lancer_claude(..., mode_tmux=True)`, qui réutilise
  l'intégralité de la construction de prompt existante et ne bifurque
  qu'au moment de lancer le process (jamais `--print`, voir
  `_construire_cmd_claude_interactif`).
- La commande claude est écrite dans un petit script shell
  (`logs/tmux/<session>.sh`, `_ecrire_script_lancement_tmux`) plutôt que
  passée directement à `tmux new-session` : tmux rejoint les arguments
  restants par de simples espaces sans ré-échapper quoi que ce soit, ce
  qu'un prompt long (CONTEXTE + CONSIGNES + corps d'issue) casserait. Le
  script exporte `BRIDGE_PROJET`/`BRIDGE_ISSUE` (utiles aux hooks des
  étapes suivantes), `cd` dans le répertoire de travail, puis `exec` la
  commande claude.
- Lancement effectif via `tmux new-session -d -s <session> -c <cwd>
  <script>`, précédé par `systemd-run --user --scope --collect
  --unit=bridge-tmux-<session> --` quand `systemd-run` est disponible —
  voir « Survie à un redémarrage » ci-dessous. Repli silencieux
  (log.warning) sur un lancement direct si `systemd-run` est absent ou
  échoue.

## Surveillance (non bloquante)

`watcher._surveiller_session_tmux` remplace, pour ces seules issues,
l'attente bloquante `proc.communicate(timeout=...)` du chemin automatique :
sondage périodique (`tmux has-session`, toutes les
`INTERVALLE_SURVEILLANCE_TMUX_S` = 15s) jusqu'à ce que la session disparaisse
ou que l'échéance (TIMEOUT de l'issue) soit dépassée. Au dépassement, la
session est tuée (`tmux kill-session`) comme le process `claude` l'aurait
été dans le chemin automatique.

## Fin de session (étape 3, issue #903)

Invariant central : quelle qu'en soit la cause, une fin de session laisse
TOUJOURS l'issue dans un état qui empêche la relance au cycle suivant
(`lister_issues()` ne renvoie que les issues OUVERTES) — jamais ouverte sans
label comme à l'étape 2, où le watcher relançait CCL (nouveau worktree
`-bis`) au cycle suivant une fin déjà traitée. Trois issues, détectées à
chaque sondage par `_surveiller_session_tmux` (`watcher._chemin_rapport_
interactif(nom_projet, numero)` = `logs/interactif/<projet>-issue<numero>.md`,
chemin FIXE hors de tout worktree/REP_TRAVAIL, gitignoré — jamais happé par
un commit) :

1. **Rapport de clôture trouvé et STABLE** (taille inchangée entre deux
   sondages — sauf si la session a déjà disparu, où une seule lecture
   suffit, personne ne pouvant plus écrire) : c'est Alain qui décide de la
   fin en demandant/confirmant à CCL d'écrire ce fichier (bloc de prompt
   dédié dans `lancer_claude`, injecté uniquement si `mode_tmux`) — jamais
   un critère automatique. La session tmux est terminée si encore ouverte,
   et le contenu est transmis tel quel à `_finaliser_succes` : chaîne de
   clôture IDENTIQUE au chemin automatique (verdict, commentaire, fermeture,
   label `done`). Le rapport est conservé comme trace, jamais supprimé.
   Pour une issue en lecture active (`mode_scratch`), ce fichier est la
   SEULE écriture autorisée hors du dossier scratch — hors du projet, le
   garde-fou technique (`_restaurer_rep_travail_modifie`) ne le voit jamais.
2. **Session disparue SANS rapport** (Alain a quitté Claude ou fermé la
   fenêtre) : commentaire décrivant l'état du worktree (commits depuis la
   sauvegarde, fichiers non committés — `_resume_worktree_sans_rapport`,
   même relevé que le bouton « Avancement » #887), puis fermeture SANS le
   label `done` (`_fermer_issue_sans_done`) — une issue fermée sans ce label
   signale justement une fin sans rapport.
3. **TIMEOUT dépassé** : comme à l'étape 2 (session tuée, commentaire), plus
   le label `needs-human`, comme le chemin automatique après un abandon —
   garde-fou déjà existant en tête de `_guards_precoces_et_bootstrap`.

Verrou et place de parallélisme libérés dans les trois cas par le mécanisme
déjà existant (`_nettoyer_apres_traitement`). Étape suivante de l'étude
#888 : alerte quand CCL attend Alain.

## Suspension du TIMEOUT pendant l'attente d'Alain (étape 4, issue #909)

Le TIMEOUT était jusqu'ici un délai brut de bout en bout : une pause de
réflexion ou une absence d'Alain pouvait le faire dépasser et tuer la
session alors que CCL ne travaillait plus. Une sentinelle de pause,
`watcher._chemin_pause_interactif(nom_projet, numero)` =
`logs/interactif/<projet>-issue<numero>.pause` (même dossier et convention
que le rapport de clôture, hors worktree), suspend maintenant le TIMEOUT
tant qu'elle existe.

- **Pose/retrait** : quatre hooks Claude Code (étude #888, signal retenu dès
  l'issue #901 via les variables d'environnement `BRIDGE_PROJET`/
  `BRIDGE_ISSUE`, déjà exportées par le script de lancement tmux) — `Stop`
  et `Notification` (CCL a fini son tour ou demande quelque chose = il
  attend Alain) posent la sentinelle (contenu : heure de début, horloge
  murale) ; `UserPromptSubmit` (Alain a répondu) et `SessionEnd` (fin de
  session) la retirent. Un seul petit script autonome,
  `scripts/hook_pause_interactif.py`, appelé pour les quatre (argument
  `debut`/`fin`) — ne lève jamais, code de sortie toujours 0, aucune sortie
  stdout/stderr, écriture atomique (fichier temporaire + `os.replace`).
- **Réglages** : `watcher._ecrire_reglages_hooks_interactif` écrit, pour
  CHAQUE session tmux interactive, un fichier de réglages JSON
  (`logs/tmux/<session>.settings.json`, hors du worktree du projet piloté,
  gitignoré, jamais capté par un commit) passé via `claude --settings
  <chemin>` (`_construire_cmd_claude_interactif`) — le chemin automatique
  (`_construire_cmd_claude`) n'a ni ce paramètre ni cette option, et n'écrit
  jamais ce fichier. Les hooks appellent `scripts/hook_pause_interactif.py`
  par chemin absolu (`sys.executable` + chemin absolu du script), jamais par
  nom nu : indépendant du PATH et d'un shell interactif de la session.
- **Calcul** : `watcher._surveiller_session_tmux` teste à chaque sondage si
  la sentinelle existe ; si oui, le sondage ne compte pas contre l'échéance
  (reculée d'exactement la durée dormie) — une ligne de log est écrite au
  début et à la fin de chaque pause, avec sa durée. L'heure de début est lue
  depuis le contenu de la sentinelle (`watcher._heure_debut_pause`, repli
  sur `st_mtime` si contenu corrompu, jamais `None` tant que le fichier
  existe) : c'est une horloge murale, insensible à un redémarrage du
  watcher.
- **Durée maximale absolue** : `watcher.DUREE_MAX_PAUSE_INTERACTIVE_S` (12h,
  constante nommée) — au-delà, `_surveiller_session_tmux` retourne
  `"pause_trop_longue"`, traité par `_traiter_issue_interactive` EXACTEMENT
  comme un TIMEOUT dépassé (session tuée, verrou et place libérés, label
  `needs-human`, jamais de relance), avec un commentaire GitHub distinct
  précisant qu'il s'agit d'une pause trop longue et non d'un dépassement du
  délai de travail.
- **Redémarrage du watcher pendant une pause** : la sentinelle (hors
  worktree, horloge murale persistée sur disque) survit sans changement à
  un redémarrage. Comme au point 5 ci-dessus (reprise d'une session déjà
  existante), le watcher redémarré donne une échéance fraîche de `timeout`
  secondes à la reprise de la surveillance — solution prudente retenue
  plutôt qu'une reconstitution précise du temps déjà écoulé : elle ne risque
  JAMAIS de tuer une session à tort après un redémarrage, pause ou pas. Si
  une pause était déjà en cours, la sentinelle (contenu non réinitialisé)
  continue d'être prise en compte normalement dès le premier sondage, y
  compris pour la limite absolue des 12h (comptée depuis la VRAIE heure de
  début, pas depuis le redémarrage).
- **Fin de session** : la sentinelle est retirée par watcher.py lui-même à
  CHAQUE fin de session (rapport, sans rapport, TIMEOUT, pause trop longue)
  — jamais de sentinelle orpheline qui fausserait une session ultérieure du
  même numéro.
- **Hors mode interactif** : les hooks ne sont jamais actifs (aucun fichier
  de réglages écrit, aucun `--settings`) — chemin automatique strictement
  inchangé.

## Survie à un redémarrage du watcher (point 5, issue #901, étendu #903)

`systemd/watcher@.service` ne déclare pas `KillMode=` : valeur implicite
`control-group`, qui tue TOUS les descendants du watcher (donc un serveur
tmux lancé comme simple sous-process) à l'arrêt/redémarrage du service.
`systemd-run --user --scope` fait sortir le lancement de ce cgroup, dans un
scope systemd indépendant — un redémarrage de `watcher@<projet>` ne devrait
alors pas tuer la session. **Non vérifié en conditions réelles** (aucun
environnement systemd --user disponible pour le valider end-to-end pendant
cette issue) — voir la liste d'essais manuels du rapport de clôture #901.
Au redémarrage, `watcher._traiter_issue_interactive` teste, AVANT toute
autre décision (issue #903) : un rapport déjà présent (traité comme au point
1 ci-dessus, que la session soit encore ouverte ou pas) ; sinon une session
existante par son nom conventionnel (`_tmux_session_existe`) — reprend alors
seulement la surveillance, sans relancer CCL ni recréer de verrou orphelin ;
sinon le script de lancement tmux (`logs/tmux/<session>.sh`) encore présent
sans session ni rapport — signe qu'un redémarrage ou un crash a eu lieu
PENDANT la surveillance d'une session déjà terminée : traité comme le point
2 ci-dessus (fermeture sans `done`), jamais une relance. Ce script n'est
supprimé qu'une fois la fin de session entièrement traitée (commentaire posté
ET fermeture/label réussis) — tant qu'il subsiste, il sert justement de
marqueur « session déjà lancée, fin pas encore traitée ».

## Verrou d'instance unique du watcher et sessions tmux (issue #908)

Le verrou d'instance unique par projet (`watcher.acquerir_verrou_processus`,
`logs/verrous/watcher-processus-<projet>.lock`, un par projet — à ne pas
confondre avec les verrous par issue ci-dessus) est posé tout au début de
`main()`, avant le fichier PID. Il ne doit JAMAIS être hérité par un enfant,
sous peine d'empêcher tout redémarrage du watcher tant qu'une session tmux
survivante le détiendrait : descripteur ouvert `O_CLOEXEC`/non héritable
(`os.set_inheritable`), et de toute façon jamais transmis au CLIENT tmux
lancé via `subprocess` (fermeture par défaut de tous les descripteurs avant
exec, `close_fds=True`) ni, a fortiori, au SERVEUR tmux qu'il fork lui-même —
vérifié par test (non-régression #908). Un redémarrage du watcher pendant
qu'une session interactive tourne acquiert donc normalement ce verrou et
démarre.

## Repli (issue #901, point 6)

`tmux` absent du PATH, agent différent de `claude`, OS Windows, ou
`tmux new-session` en échec malgré le repli `systemd-run` : avertissement
posté dans l'issue ET dans le journal, puis traitement automatique
habituel (`claude --print`, chemin strictement inchangé) — jamais un échec
silencieux.
