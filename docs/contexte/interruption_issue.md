# Interruption propre d'UNE issue (étude #939, issues #949/#950)

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

## Limites connues (du mécanisme #949 lui-même)

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
  équivalent dans `_surveiller_session_tmux`. Côté interface (#950, voir
  ci-dessous), le bouton « Interrompre » d'une telle issue bascule donc sur
  le mécanisme HISTORIQUE (watcher entier, `/interrompre`) plutôt que sur
  celui-ci.
- **Issue encore en file** (jamais démarrée) : n'est pas traitée par CE
  mécanisme (hors périmètre de l'étude #939 reprise ici) — côté interface,
  elle est couverte par un mécanisme DISTINCT (bouton « Annuler l'issue »,
  simple fermeture GitHub, voir ci-dessous).

## Boutons par état, sur la ligne de résultat (issue #950)

Décision d'Alain : TOUTES les actions par issue (annuler/interrompre/
relancer/fermer) vivent sur la LIGNE de résultat de l'issue concernée
(`static/js/actions_ligne.js`), jamais depuis le panneau de détail ni le
panneau Infrastructure — un bouton de panneau peut viser une autre issue que
celle crue affichée (sélection qui « saute » lors d'un rafraîchissement, cf.
`docs/contexte/interface_rafraichissement.md` §9quater) ; un bouton de LIGNE
ne peut viser que SA PROPRE issue (nom/numéro clos dans son propre markup au
moment du rendu, jamais relus depuis une sélection courante).

Décision pure (`boutonsActionLigne(labels, timing)`, testée sous Node) à
partir des labels GitHub déjà connus et du même `timing.debut` qui pilote le
décompte TIMEOUT actif :

| État de l'issue | Bouton(s) affiché(s) | Route appelée |
|---|---|---|
| En file (jamais démarrée) | « Annuler l'issue » | `POST /annuler-issue/<projet>/<numero>` (`app.issues.annuler_issue`, inchangée sauf la revérification ci-dessous) |
| En cours (`timing.debut` connu) | « Interrompre » + « Fermer » (issue #951) | « Interrompre » : `POST /demander-interruption-issue` (mécanisme CIBLÉ ci-dessus) — SAUF issue interactive, voir plus bas. « Fermer » : séquence de fermeture propre, voir §« Fermeture d'une issue EN COURS » ci-dessous — PAS un simple `gh issue close` immédiat |
| Interrompue / `needs-human` | « Relancer » + « Fermer » | `POST /relancer-issue` (inchangée) et `POST /fermer-issue/<projet>/<numero>` (commentaire corrigé, voir ci-dessous — l'issue est déjà arrêtée, fermeture immédiate) |
| Terminée (`done`) ou fermée | aucun | — |

**Issue interactive** (session tmux, label `mode_interactif`, détectée par
`mecanismeInterruptionLigne(labels)`) : le bouton « Interrompre » de la LIGNE
garde le comportement HISTORIQUE (`POST /interrompre`, watcher entier du
projet) — jamais couverte par la sentinelle ci-dessus. Sa confirmation liste
désormais les autres issues en cours du projet (`GET /issues-en-cours/<projet>`,
issue #947) et annonce clairement qu'elles seront interrompues en même
temps. Les boutons de niveau PROJET (panneau Infrastructure) ont leur propre
traitement de ce cas depuis l'issue #954 — voir la section dédiée ci-dessous,
qui remplace l'ancien comportement (« Interrompre et relancer » conservé tel
quel, « Arrêter » laissant `claude` orphelin).

**« Annuler l'issue »** (`app.issues.annuler_issue`) : revérifie, juste
avant le `gh issue close`, que l'issue n'a pas démarré entre-temps (même
source que `/issues-en-cours`, `app.watchers.tache_en_cours`) — la liste
affichée côté client est indicative seulement. Si elle tourne déjà : refusé,
message invitant à utiliser « Interrompre ». Petite course résiduelle (la
fenêtre entre cette vérification et l'appel `gh` lui-même, quelques
millisecondes sans appel réseau entre les deux) assumée comme négligeable,
même principe que la garde anti-concurrence #748.

**« Fermer » sur une issue `needs-human`** (`app.issues.fermer_issue`) :
simple `gh issue close`, comme avant cette issue — ne touchait déjà pas le
watcher. Le commentaire GitHub posté : *« Issue fermée manuellement depuis
l'interface (new_issue.py). »* remplace *« … intervention humaine
effectuée »*, trompeur (#938 point 2.1 — aucune vérification humaine n'a
forcément eu lieu, juste un clic). Depuis l'issue #951 (point 4), retire
aussi le label `needs-human` APRÈS la fermeture (best-effort strict — voir
§« Affichage d'une issue fermée manuellement » ci-dessous) : la MÊME route
est réutilisée, sans confirmation ni attente supplémentaires, comme dernier
geste de la séquence de fermeture d'une issue EN COURS décrite ci-dessous
(elle y pose elle-même `needs-human` comme étape intermédiaire, avant de
fermer).

**Anciens boutons retirés** (étude #938, boutons A et B) : l'icône carrée
verte/rouge de la ligne (A) est remplacée par le groupe ci-dessus ; le
bouton « Interrompre et fermer cette issue » du détail d'une issue (B) est
retiré sans remplacement direct dans le détail (ses deux effets vivent
désormais séparément sur la ligne : « Interrompre » et/ou « Fermer »,
disponibles ensemble pour une issue EN COURS depuis l'issue #951 — voir
ci-dessous). Le bouton `pl-fermer-issue` du panneau Infrastructure (zone
« Actions — projet #numéro ») est retiré de même.

## Fermeture d'une issue EN COURS depuis sa ligne (issue #951)

Règle d'Alain, qui remplace l'ancien bouton « Interrompre et fermer »
(retiré par #950, qui arrêtait tout le watcher du projet puis fermait avec
le commentaire trompeur #938 point 2.1) : fermer une issue proprement SANS
toucher aux autres issues du projet si c'est possible ; sinon, ne le faire
que si les autres issues du projet sont interrompues ou s'il n'y en a pas,
avec un choix explicite. Toute la séquence (confirmation, dépôt de la
demande, attente non bloquante, fenêtre du cas interactif) est orchestrée
CÔTÉ CLIENT par `static/js/app.js::fermerIssueEnCoursDepuisLigne` et son
arborescence — aucune nouvelle route : les trois routes existantes
`/demander-interruption-issue` (#949), `/issues-en-cours` (#947) et
`/fermer-issue` (#950, ci-dessus) suffisent. Déclenchée par le bouton
« Fermer » UNIQUEMENT quand l'issue ne porte PAS encore `needs-human`
(sinon, chemin historique ci-dessus — déjà arrêtée) ; le mécanisme choisi
(normal/interactif) est la MÊME détection que le bouton « Interrompre »
(`mecanismeInterruptionLigne`), pour ne jamais diverger.

**Invariant central, dans les deux cas : ne JAMAIS fermer l'issue sur GitHub
tant que son traitement tourne encore** — la fermeture GitHub elle-même
(`_executerFermetureGh`, qui appelle `/fermer-issue`) n'est appelée
qu'APRÈS confirmation de l'arrêt.

**Cas normal (issue NON interactive)** —
`fermerIssueNormaleEnCoursDepuisLigne` :
1. Confirmation (numéro, titre, effet : cette issue seule est arrêtée puis
   fermée, les autres issues du projet continuent, le travail déjà fait —
   worktree, commits éventuels — est conservé).
2. Dépose la demande d'interruption CIBLÉE (#949, `POST
   /demander-interruption-issue`).
   - Réponse `deposee:false` (l'issue a déjà fini entre le clic et cet
     appel — plus dans les issues en cours) : fermeture IMMÉDIATE, rien à
     attendre (« si l'issue a déjà fini entre-temps, fermer simplement »).
   - Réponse `succes:false` (vraie erreur de dépôt) : message, PAS de
     fermeture.
   - Sinon (déposée) : sonde `GET /issues-en-cours/<projet>` toutes les
     3s (`INTERVALLE_SONDAGE_FERMETURE_MS`, purement local — aucun appel
     GitHub) jusqu'à ce que le numéro n'y figure plus, ou jusqu'à
     **`DELAI_MAX_ATTENTE_ARRET_FERMETURE_MS` = 30 000 ms** (30s, du même
     ordre que le délai « raisonnable » demandé) — `await` sur un
     `setTimeout`, jamais de boucle bloquante.
     - Arrêt confirmé à temps → fermeture.
     - Délai dépassé → message clair (toast ou `alert`), PAS de fermeture ;
       l'issue reste dans son état (en cours, ou déjà passée à
       `needs-human` par le watcher) ; invite à réessayer « Fermer ».

**Cas interactif** (session tmux, `mode_interactif`, #949 ne la couvre
jamais) — `fermerIssueInteractiveDepuisLigne` : interroge D'ABORD `GET
/issues-en-cours/<projet>?exclure=<numero>` (#947) pour les AUTRES issues en
cours de ce projet, enrichies de leur propre statut interactif (relu
localement via `mecanismeInterruptionLigne` sur les labels déjà connus du
store du socle, `window.Bridge.store.lireIssue` — AUCUN appel GitHub
supplémentaire, voir contrainte ci-dessous) :
- **Aucune autre issue en cours** : confirmation simple, puis arrête le
  watcher ENTIER du projet (mécanisme historique #323, `POST /interrompre`)
  et ferme — rien d'autre n'est affecté.
- **D'autres issues en cours, toutes NON interactives** : fenêtre à deux
  actions (réutilise l'overlay générique `#modal-confirmation`, déjà
  partagé par `static/js/creation.js` — mêmes `id`, pas de nouveau
  gabarit) — « Interrompre les autres puis fermer » (interrompt chacune via
  #949, attend qu'AUCUNE ne figure plus en cours avec le MÊME délai/sondage
  que le cas normal, puis SEULEMENT ALORS arrête le watcher et ferme ; délai
  dépassé → message, rien n'est arrêté, rien n'est fermé) et « Annuler »
  (rien n'est touché).
- **Au moins une autre issue EN COURS ELLE-MÊME interactive** : cette
  action n'est PAS proposée (elle ne peut pas être interrompue proprement,
  même limite que le bouton « Interrompre » pour une telle issue) — la
  fenêtre l'indique et ne laisse que « Annuler ».

Aucune issue n'est arrêtée dans le cas interactif sans ce choix explicite.

**Garde anti-double-fermeture** (même patron que la garde anti-double-
interruption #748) : un ensemble dédié `_fermeturesEnCours` (DISTINCT de
`_interruptionsEnCours`, qu'utilise elle-même l'étape d'interruption
intermédiaire) empêche un second clic sur « Fermer » pendant qu'une
fermeture est déjà en cours pour cette issue — le bouton est désactivé et
affiche « ⏳ Fermeture… » pendant l'attente (limite déjà acceptée pour
`_marquerInterruptionEnCours` : un rendu complet de la ligne survenant
PENDANT l'attente, ex. `fin_issue` d'une AUTRE issue du même projet,
reconstruit la ligne sans cet état visuel — pas une régression propre à
cette issue, l'action elle-même reste correcte).

**Aucun appel GitHub supplémentaire** : la séquence ci-dessus ne consomme
QUE les trois routes existantes mentionnées en tête de section — la
confirmation, l'attente et la fenêtre reposent sur `/issues-en-cours`
(local, verrous fichier) et le store déjà en mémoire côté client ; seule la
fermeture finale (`/fermer-issue`) et son éventuel retrait de label
(ci-dessous) touchent réellement GitHub, en plus de la fermeture
elle-même et de son commentaire.

## Affichage d'une issue fermée manuellement (issue #951, point 4)

Constat : une issue CLOSED portant encore le label `needs-human` continue
de s'afficher comme un « échec » (badge ⚠️ *échec*, `badgeLabel()` dans
`static/js/app.js`, utilisé par le panneau de détail et la recherche —
ce badge ne tient compte QUE des labels, jamais de l'état ouvert/fermé).
Avant l'issue #951, c'était déjà le cas pour toute fermeture manuelle d'une
issue `needs-human` (`app.issues.fermer_issue`, bouton « Fermer » existant
depuis #950) ; depuis #951, c'est aussi le cas courant de la séquence de
fermeture normale ci-dessus, qui POSE `needs-human` comme étape
intermédiaire (via l'interruption ciblée #949) avant de fermer.

Correction retenue, la plus simple : `app.issues.fermer_issue` retire
désormais le label `needs-human` lui-même, systématiquement, **APRÈS**
avoir fermé l'issue (`gh issue edit --remove-label needs-human`, idempotent
— ne pas en avoir besoin, label déjà absent, n'échoue pas) — jamais AVANT,
pour ne jamais rendre l'issue éligible à une relance automatique entre les
deux appels (`watcher.lister_issues()` ne liste que les issues OUVERTES, le
risque n'existe qu'entre un retrait AVANT close et le close lui-même).
Best-effort STRICT, isolé dans son propre `try/except` : un échec ou une
exception de ce second appel ne fait jamais échouer la réponse de la route
— la fermeture elle-même a déjà réussi. Résultat : une issue fermée depuis
l'interface (manuellement, ou via la séquence #951) n'affiche plus le badge
« échec » une fois fermée, qu'elle ait ou non réellement échoué avant sa
fermeture — cohérent avec le fait qu'un `needs-human` conservé sur une
issue OUVERTE reste, lui, un vrai échec en attente de décision (relance ou
fermeture), inchangé.

## Boutons de niveau PROJET, panneau Infrastructure (issue #954)

Principe d'Alain : aucune action de ce panneau n'arrête une ou plusieurs
issues sans qu'elles soient NOMMÉES et que le choix soit explicite — l'arrêt
de plusieurs issues d'un coup est une action À PART ENTIÈRE, jamais l'effet
de bord d'un bouton qui parle du watcher. Logique pure (quelles issues,
interactives ou non, quels messages) dans `static/js/interruption_projet.js`
(testée sous Node, `static/js/tests/interruption_projet.test.js`) ; rendu
des boutons dans `static/js/panneau_lateral.js`, qui l'importe. Orchestration
CÔTÉ CLIENT avec les routes existantes (`/issues-en-cours` #947,
`/demander-interruption-issue` #949, `/lancer-watcher`, `/relancer-issue`,
`/arreter-watcher`) — aucune nouvelle route pour la confirmation/l'attente,
seule la mémorisation ci-dessous (point « Redémarrer le watcher ») ajoute
deux petits points d'extension côté serveur (`app/watchers.py`).

Ces boutons portent tous sur CCL (watcher local, Linux) — le watcher CCW
(délégué par SSH au PC fixe Windows) n'a aucune visibilité locale sur ses
issues en cours (`/issues-en-cours` ne lit que les verrous LOCAUX) : ils
restent donc hors de portée de cette refonte, voir plus bas.

### « Tout interrompre pour ce projet »

Nouveau bouton (`pl-tout-interrompre-projet`), affiché sur la ligne de
chaque watcher CCL UNIQUEMENT s'il a au moins une issue en cours
(`afficherBoutonToutInterrompre`). Au clic : relit `/issues-en-cours/<projet>`
(fraîche, pas le résumé déjà affiché), classe chaque issue normale/interactive
(`classifierIssuesEnCoursProjet`, même détection que le bouton « Interrompre »
de la ligne), puis :
- aucune issue normale (seules des interactives, ou rien) → message
  informatif, aucune action ;
- sinon → confirmation nommant numéro + titre de chaque issue normale ciblée
  (worktrees/commits conservés, passage en `needs-human`, relance possible
  depuis la ligne, watcher qui reste actif) et, si présentes, les issues
  interactives (non touchées, à arrêter uniquement depuis leur propre ligne) ;
  confirmée, dépose une demande d'interruption CIBLÉE (#949) pour chacune,
  attend leur arrêt (sondage local `/issues-en-cours`, 30s max, même ordre de
  grandeur que #951), puis affiche un résumé lisible (quelles issues
  arrêtées, lesquelles non — `resumeArretCibles`). Le watcher n'est JAMAIS
  touché par ce bouton. Aucune issue d'un AUTRE projet n'est concernée
  (`/issues-en-cours` est scopé par projet).

### « Lancer » / « Redémarrer le watcher »

Bouton unique (`pl-relancer-ccl`, texte décidé par `libelleBoutonWatcherCcl` :
« ▶ Lancer » si éteint, « ↺ Redémarrer le watcher » si actif — l'ancien texte
« Relancer » prêtait à confusion avec la relance d'une issue). Géré par
`redemarrerWatcherAvecRelance`, qui dégénère automatiquement en simple appel
`/lancer-watcher` (comportement de « Lancer » strictement inchangé) dès qu'il
n'y a aucune issue en cours pour ce projet — un watcher éteint n'en a jamais.

S'il y a des issues en cours, la confirmation les nomme (même distinction
normales/interactives que ci-dessus) puis, si confirmée :
1. interruption CIBLÉE (#949) de chaque issue NORMALE + attente (30s max,
   même sondage que ci-dessus) — délai dépassé → séquence ABANDONNÉE, watcher
   NON redémarré, rien relancé, message clair ;
2. `POST /lancer-watcher` avec `issues_a_relancer` = la liste de ces mêmes
   numéros — la route (`app.watchers.lancer_watcher`) mémorise AVANT de
   redémarrer, dans un fichier sous `DOSSIER_LOGS/redemarrages_watcher/
   <projet>.json` (gitignoré, JAMAIS dans REP_TRAVAIL — même précaution que
   `app.interruption.deposer_demande_interruption`, #949), la liste que CETTE
   séquence va relancer ;
   - redémarrage DIFFÉRÉ (#609, une tâche tournait encore — course possible
     entre la vérification ci-dessus et l'appel) → le client purge
     immédiatement (`POST /purger-issues-a-relancer`) et prévient qu'aucune
     relance automatique n'aura lieu (à faire depuis la ligne, une fois le
     watcher reparti) ;
   - échec → purge immédiate, message d'erreur, rien relancé ;
3. redémarrage effectif → le client boucle `POST /relancer-issue` (MÊME
   mécanisme que le bouton « Relancer » de la ligne) sur CHAQUE numéro de
   cette liste SEULEMENT (jamais une issue déjà interrompue/`needs-human`
   avant le clic : elle n'apparaissait alors déjà plus dans
   `/issues-en-cours`, donc jamais dans cette liste), puis purge le fichier
   (`POST /purger-issues-a-relancer`) — relance faite, trace inutile.

Les issues INTERACTIVES en cours ne sont jamais incluses dans cette séquence
(#949 ne les couvre pas) — mais n'ont pas besoin de l'être : leur session
tmux survit à un redémarrage du watcher (lancée dans son propre scope
`systemd-run --user --scope`, voir `docs/contexte/mode_interactif.md` §« Survie
à un redémarrage ») et la surveillance reprend automatiquement au cycle
suivant. La confirmation le signale simplement, pour qu'aucun redémarrage ne
paraisse silencieux à leur sujet.

Le bouton « ⛔ Interrompre et relancer (…) » de la zone Actions (issue
sélectionnée, panneau Infrastructure) suit exactement la MÊME séquence pour
une issue for-linux (CCL) — il agit sur le PROJET de l'issue sélectionnée,
pas sur elle seule. Pour une issue for-windows (CCW, délégué), ce mécanisme
n'a aucune visibilité locale : ce bouton garde le comportement HISTORIQUE
inchangé (`interrompreEtRelancer`, `static/js/app.js` — `POST /interrompre`
puis redémarrage du service CCW), hors périmètre de l'issue #954.

### « Arrêter »

Rôle et confirmation existante conservés (`pl-arreter-ccl` →
`app.watchers.arreter_watcher`, simple SIGTERM du process watcher), enrichis :
la confirmation nomme désormais les issues en cours. Confirmée :
1. chaque issue NORMALE en cours est interrompue CIBLÉE (#949) + attente
   (30s max) — délai dépassé → watcher NON arrêté, message clair, état
   inchangé ;
2. `POST /arreter-watcher` (inchangé) — SANS aucune relance automatique : le
   watcher reste éteint, les issues restent `needs-human`, à relancer depuis
   leur ligne après un « Lancer ».

Les issues INTERACTIVES en cours ne PEUVENT PAS être arrêtées proprement par
ce bouton (même limite que partout ailleurs) : la confirmation le dit
explicitement et pointe vers le bouton « Interrompre » de leur propre ligne
(chemin historique, qui arrête alors tout le watcher) comme SEUL moyen de
les arrêter aussi — jamais un arrêt silencieux. Sans aucune issue en cours :
comportement strictement identique à avant #954 (confirmation simple, arrêt
immédiat).

### Garde anti-double-clic et indicateur d'attente

Un ensemble dédié `_actionsProjetEnCours` (noms de PROJET, DISTINCT de
`_interruptionsEnCours` et `_fermeturesEnCours` — ces actions portent sur le
watcher entier, pas sur une issue précise) empêche un second clic sur
N'IMPORTE LEQUEL des 4 boutons de ce projet pendant qu'un autre tourne déjà ;
chaque bouton affiche « ⏳ … » pendant l'attente, restauré (texte d'origine,
réactivé) à la fin — `marquerActionProjetEnCours`.

### Limites connues (reprises de #949, toujours valables ici)

- **Processus détachés par l'outil Bash interne de `claude`** (`setsid`) :
  survivent au nettoyage de l'arbre, quel que soit le chemin (CIBLÉ ou
  historique) — non traité, même décision que #949.
- **Issue encore en file** (jamais démarrée) : hors périmètre de ces 4
  boutons, couverte par le bouton « Annuler » de sa propre ligne.
- **CCW** (délégué, SSH) : ces 4 boutons ne le concernent pas — aucune
  visibilité locale sur ses issues en cours.
