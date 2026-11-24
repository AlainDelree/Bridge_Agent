# Interruption propre d'UNE issue (étude #939, issue #949)

État actuel du mécanisme (pas l'historique — voir `CHANGELOG.md` pour le
déroulé des issues #938/#939/#946/#948/#949). Distinct du bouton
« Interrompre » historique (`app/interruption.py::route_interrompre`,
issue #323) : celui-ci tue l'arbre entier du WATCHER d'un projet (toutes
ses issues en cours, y compris les autres) — le mécanisme ci-dessous
n'arrête QUE l'issue visée.

## Fichier de demande

Un fichier-sentinelle par (projet, numéro d'issue) : seule son EXISTENCE
compte, son contenu (`heure=... origine=...`) n'est qu'informatif et n'est
jamais relu par le watcher.

- Emplacement : `logs/demandes_interruption/` (sous `DOSSIER_LOGS`,
  gitignoré — jamais dans `REP_TRAVAIL`, qui serait happé par le
  `git add -A` de sauvegarde en mode écriture).
- Nom : `<nom_projet>-issue<numero>.demande` — même convention que le
  préfixe des worktrees dédiés (`<cfg.nom>-issue<N>`). Un projet et un
  numéro différents donnent toujours un chemin différent : la portée est
  garantie par construction, sans filtrage applicatif supplémentaire.
- Chemin calculé par `watcher._chemin_demande_interruption(nom_projet,
  numero)` — fonction unique, importée aussi par `app/interruption.py`
  (autre process), pour que les deux cotés s'entendent toujours sur le
  même nom.
- Création atomique côté interface : `app.interruption.deposer_
  demande_interruption` (fichier temporaire dans le même dossier +
  `os.replace`).

## Qui écrit, qui lit

- Écrit par `app.interruption.route_demander_interruption` (POST
  `/demander-interruption-issue`) — ne dépose la demande que si l'issue
  figure parmi les issues réellement en cours pour ce projet
  (`app.watchers.tache_en_cours`, issue #947). Peut aussi être créé à la
  main (fichier texte quelconque) pour un essai manuel.
- Lu uniquement par le watcher qui traite CETTE issue, via le point
  d'extension de la boucle d'attente de `claude` (issue #948) :
  `watcher._verifier_demande_interruption(numero)`, appelé à chaque tour
  (~`INTERVALLE_SONDAGE_CLAUDE_S`, 3s) de `_attendre_fin_claude`.

## Effet d'une demande détectée

Sur cette issue SEULEMENT, dans les ~3s qui suivent la détection
(`watcher._gerer_interruption_demandee`) :

- `_attendre_fin_claude` lève `InterruptionIssueDemandee` ; le `finally`
  de `lancer_claude` nettoie l'arbre de process via `_nettoyer_arbre_claude`
  (inchangé, appelé une seule fois comme pour tout autre mode de sortie —
  pas de double nettoyage).
- PAS de nouvelle tentative, PAS de passe diagnostique
  (`diagnostiquer_echec`), PAS de commentaire « Échec après N tentatives » :
  ce n'est pas un échec.
- `needs-human` posé sur cette issue uniquement, avec un commentaire dédié
  précisant qu'elle a été interrompue sur demande et peut être relancée
  normalement (bouton existant) — l'issue n'est JAMAIS fermée, rien n'est
  relancé automatiquement.
- Le verrou de cette issue est libéré par le chemin de nettoyage habituel
  de fin de traitement ; en mode écriture, le worktree est laissé tel
  quel, sans commit supplémentaire.
- Le fichier de demande est supprimé une fois traitée.
- Les autres issues en cours ou en file du même projet ne sont ni
  arrêtées ni retardées (chaque numéro a son propre fichier, sa propre
  boucle d'attente).

## Priorité sur l'arrêt dit « critique »

Une issue de priorité `haute`/`critique` qui épuise ses tentatives suit
normalement `_gerer_abandon_max_essais` → retry infini, jamais de
needs-human (`alerte_critique`). Une interruption explicite est vérifiée
EN PREMIER, avant ce chemin : elle l'emporte toujours, y compris pour une
issue critique — needs-human est posé, aucun retry.

## Purge des demandes périmées

Une demande non traitée à temps (issue déjà terminée, watcher éteint
quand elle a été déposée) ne doit jamais interrompre un traitement
ultérieur distinct de la même issue. Purgée (`watcher.
_purger_demande_interruption`) à deux moments :

- au tout début de `watcher._traiter_issue_synchrone`, avant toute
  tentative ;
- à la relance d'une issue bloquée (`app.interruption.relancer_issue`,
  appelée par le bouton de relance et par le champ `RELANCE`
  d'`issues_inbox/`).

Une demande arrivant après la fin de `claude` mais avant la clôture de
l'issue peut rester sans effet (la boucle d'attente ne la voit plus) —
sans risque, puisqu'elle est purgée au prochain traitement ou à la
relance.

## Limites connues

- **Processus détachés par l'outil Bash interne de `claude`** (ex. un
  `sleep` en arrière-plan, rattaché à `systemd --user`) : le nettoyage
  (`_nettoyer_arbre_claude`) cible le groupe de process (pgid) de `claude`
  — un process qui a changé de groupe/session (`setsid` ou équivalent) y
  échappe et peut survivre. Non traité ici : l'enrichir demanderait de
  suivre les descendants de `claude` en continu PENDANT l'attente (avant
  qu'ils ne se détachent), jamais par nom de process. Voir le rapport de
  clôture de l'issue #949 pour le détail de cette décision.
- **Mode interactif** (session tmux, `docs/contexte/mode_interactif.md`) :
  ne passe pas par `_attendre_fin_claude` ni par cette boucle — ce
  mécanisme ne le couvre pas. Le couvrir demanderait un point d'extension
  équivalent dans `_surveiller_session_tmux`.
- **Issue encore en file** (jamais démarrée) : l'annulation d'une issue en
  attente n'est pas traitée par ce mécanisme (hors périmètre de l'étude
  #939 reprise ici).
