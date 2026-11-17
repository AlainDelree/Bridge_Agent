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

## Fin de session

Dans tous les cas (fin normale ou TIMEOUT), **aucune fermeture automatique
de l'issue** : un commentaire explicite est posté (différent selon fin
normale / TIMEOUT), le verrou et la place de parallélisme sont libérés par
le mécanisme déjà existant (`_nettoyer_apres_traitement`, appelé par le
`finally` de `_traiter_issue_synchrone` — mécanisme choisi car déjà en
place et agnostique du mode, le moins intrusif possible), mais l'issue
reste ouverte sans le label `done` : clôture manuelle par Alain. Prochaines
étapes de l'étude #888 : suspension du délai pendant l'attente d'Alain,
alerte, détection de fin par fichier de rapport.

## Survie à un redémarrage du watcher (point 5, issue #901)

`systemd/watcher@.service` ne déclare pas `KillMode=` : valeur implicite
`control-group`, qui tue TOUS les descendants du watcher (donc un serveur
tmux lancé comme simple sous-process) à l'arrêt/redémarrage du service.
`systemd-run --user --scope` fait sortir le lancement de ce cgroup, dans un
scope systemd indépendant — un redémarrage de `watcher@<projet>` ne devrait
alors pas tuer la session. **Non vérifié en conditions réelles** (aucun
environnement systemd --user disponible pour le valider end-to-end pendant
cette issue) — voir la liste d'essais manuels du rapport de clôture #901.
Au redémarrage, `watcher._traiter_issue_interactive` retrouve une session
existante par son nom conventionnel (`_tmux_session_existe`) et reprend
seulement la surveillance, sans relancer CCL ni recréer de verrou orphelin.

## Repli (issue #901, point 6)

`tmux` absent du PATH, agent différent de `claude`, OS Windows, ou
`tmux new-session` en échec malgré le repli `systemd-run` : avertissement
posté dans l'issue ET dans le journal, puis traitement automatique
habituel (`claude --print`, chemin strictement inchangé) — jamais un échec
silencieux.
