# CHANGELOG — bridge_agent

Historique complet des évolutions du projet, une section par issue, la
plus récente en premier. Auparavant maintenu comme un unique paragraphe
en pied de page de `BRIDGE_AGENT_DOC.md` ; extrait ici tel quel (issue
#252) car ce paragraphe avait fini par peser plusieurs dizaines de
milliers de caractères sur une seule ligne logique, coûteux à relire et
à réécrire, et sans garde-fou contre une perte silencieuse de contenu.

Convention d'ajout : voir §10 de `BRIDGE_AGENT_DOC.md`.

## 3 août 2026 — issue #370

Script PowerShell `surveiller_builds.ps1` (issu d'une session Claude Chat
précédente) committé dans `provisioning/windows/` : surveille en temps réel,
pendant un build CCW (PyInstaller/ISCC), les processus de build et la
croissance du dossier de sortie (taille + delta par passage et depuis le
début). Paramètre `-Dossier` obligatoire, `-Processus` et
`-IntervalleSecondes` optionnels. Documenté au §16 de `BRIDGE_AGENT_DOC.md`
(tableau de provisioning), avec la note que le nom de process Claude Code
(`claude` par défaut) reste à confirmer via `Get-Process` pendant un build
réel.

## 3 août 2026 — issue #352

Le POST `/notifier-fin-issue` (#350) était déclenché via `notifications.bip()`,
donc uniquement pour les issues portant un label `notif_pc`/`notif_gsm`/
`notif_tous` — le rafraîchissement SSE de l'onglet Résultats restait soumis
au ↻ manuel pour toutes les autres. Il doit être universel, indépendamment
des labels notif.

- `watcher.py` : import direct de `scripts/traitement_fin.py` (ajout de
  `scripts/` au `sys.path`, ce dossier n'étant pas un package) et nouvelle
  enveloppe `notifier_fin_sse(numero)` qui appelle
  `traitement_fin.notifier_fin_issue(CFG.nom, numero)` sans passer par
  `notifier()`/`bip()` — donc sans dépendre des labels `notif_*`. Appelée
  dans `_traiter_issue_synchrone` aux trois points de fin définitive d'une
  issue : succès, échec définitif (garde-fou lecture active niveau 2, issue
  #327), échec définitif après épuisement des tentatives (`max_essais`, non
  critique). Non appelée sur les fins non définitives (retry différé d'une
  issue critique, commentaire de résultat non posté) — l'issue reste ouverte
  et sera retraitée.
- Le bip et les labels `notif_*` restent inchangés — seul le POST est
  découplé, comme demandé par l'issue.

## 3 août 2026 — issue #350

Renommage de `scripts/bip.py` en `scripts/traitement_fin.py` et ajout d'un
canal SSE de rafraîchissement instantané (< 1 s) de l'onglet Résultats, sans
polling supplémentaire.

- `scripts/traitement_fin.py` : après le bip habituel, POST **best-effort**
  (timeout 1 s, échec silencieux si `new_issue.py` n'est pas lancé) vers
  `http://localhost:5100/notifier-fin-issue` avec `{"projet": ..., "numero": ...}`,
  lus depuis deux nouveaux arguments CLI `--projet`/`--numero`. La clé de
  config reste `SCRIPT_BIP` (renommer la clé impliquerait de modifier les
  `configs/*.conf` gitignorés, hors périmètre agent) — **Alain doit mettre à
  jour manuellement le chemin dans ses `configs/*.conf` existants**
  (`.../scripts/bip.py` → `.../scripts/traitement_fin.py`).
- `notifications.py` (`bip()`/`notifier()`) et les enveloppes correspondantes
  de `watcher.py` et `app/notifications_poller.py` : ajout d'un paramètre
  `numero` transmis en CLI au script, pour que le POST identifie précisément
  l'issue concernée. Comme le bip lui-même, ce déclenchement reste opt-in via
  les labels `notif_*` — sans label, la ligne reste soumise au ↻ manuel ou au
  fetch post-TIMEOUT de #334.
- `app/fin_issue.py` (nouveau module) : route `POST /notifier-fin-issue`
  (sans authentification, appelée par le script local) qui pousse un
  événement SSE `event: fin_issue\ndata: {"projet": ..., "numero": ...}` à
  tous les onglets Résultats ouverts, et route `GET /stream` (protégée par
  `login_requis`) qui les diffuse — une `queue.Queue` par connexion active
  (ajoutée/retirée de `app.config["FIN_ISSUE_ABONNES"]`), pas de broadcast
  global, car plusieurs onglets peuvent être ouverts simultanément. Ping
  `: ping\n\n` toutes les 30 s pour maintenir la connexion ; nettoyage propre
  de l'abonné à la déconnexion (`GeneratorExit`).
- `static/js/app.js` : `demarrerStreamFinIssue()`/`arreterStreamFinIssue()`
  ouvrent/ferment un `EventSource('/stream')` à l'entrée/sortie de l'onglet
  Résultats (`basculerOnglet`). Sur réception d'un événement `fin_issue` dont
  le numéro figure dans `listeIssuesResultats`, réutilise directement
  `verifierIssueApresDepassement()` (issue #334) — même fetch de vérification,
  même `remplacerLigneIssue()`, sans dupliquer la logique. Reconnexion
  automatique gérée nativement par `EventSource`.
- `BRIDGE_AGENT_DOC.md` : §17 mis à jour (mentions de `bip.py` →
  `traitement_fin.py`), nouvelle sous-section 17.3 documentant le mécanisme
  SSE complet.
- Testé sans `new_issue.py` lancé (bip normal, POST en échec silencieux,
  aucune exception) et avec un client de test Flask (`app.test_client()`) :
  `POST /notifier-fin-issue` livre bien l'événement à une connexion
  `GET /stream` active, et la liste des abonnés est correctement nettoyée à
  la déconnexion.

## 2 août 2026 — issue #343

`WORKTREES.md` §3 « Workflow normal d'Alain » (étape 3) et §4
« Procédures de récupération » : précisions suite à un cas vécu lors du
premier workflow complet avec worktrees (issues #340/#341, session du
02/08/2026) — `fusionner_changelog.py` lancé depuis `master` avant le
merge n'a rien trouvé, car le script scanne la racine du dépôt qu'on lui
indique et `CHANGELOG-341.md` n'existait alors qu'à la racine du
worktree ; le fichier s'est donc retrouvé dans `master` via le merge
sans être intégré, nécessitant un commit de rattrapage. L'étape 3
documente désormais l'ordre impératif (script avant merge) et deux
méthodes : lancer `--repo .` depuis le worktree lui-même (recommandé),
ou copier `CHANGELOG-<N>.md` dans master avant de fusionner depuis
`REP_TRAVAIL`. Le §4 précise la procédure de rattrapage si le merge a
eu lieu avant le script (relancer le script depuis `REP_TRAVAIL`,
vérifier `git diff CHANGELOG.md`, committer).

## 2 août 2026 — issue #341

Ajout dans `TACHES.md`, juste après le bloc d'en-tête, d'une section
« Worktrees en production — points de surveillance » listant les deux
limites connues restantes après correction de #340 : pas d'alerte sur
l'accumulation de worktrees (nettoyage manuel requis) et
`issues_en_cours` sans verrou explicite inter-process.

## 2 août 2026 — issue #342

§11 « Conventions de code » de `BRIDGE_AGENT_DOC.md` : deux notes ajoutées
pour informer les projets utilisant Bridge_Agent des conséquences
pratiques de la parallélisation `mode_write` par worktrees (issue #337),
jusqu'ici documentée uniquement pour l'infrastructure elle-même (§13 du
DOC, `WORKTREES.md`). Première note : deux issues `mode_write` touchant
les mêmes fichiers ou zones de code peuvent désormais générer un conflit
de merge à résoudre manuellement — recommandation de scoper chaque issue
sur un périmètre de fichiers aussi distinct que possible. Deuxième note :
le workflow de vérification/push d'Alain inclut désormais deux étapes
supplémentaires après une ou plusieurs issues `mode_write` en parallèle —
`git worktree list` pour repérer les worktrees à traiter,
`python3 scripts/fusionner_changelog.py` avant tout merge ou push (intègre
les `CHANGELOG-N.md` des worktrees dans `CHANGELOG.md`), puis merge manuel
de chaque branche `worktree-issue-<N>` et nettoyage
(`git worktree remove` + `git branch -d`) ; renvoi vers `WORKTREES.md` pour
le détail complet plutôt qu'une duplication intégrale. Pied de page du DOC
mis à jour en conséquence (glissement des trois entrées, #327 sort du pied
de page).

## 2 août 2026 — issue #340

Suite #338 : le bouton ⛔ « Interrompre » (`app/interruption.py::interrompre_linux()`)
nettoie désormais aussi les verrous des worktrees actifs, pas seulement
celui de `REP_TRAVAIL`. Nouvelle fonction `_lister_worktrees_actifs()` :
scanne le répertoire parent de `REP_TRAVAIL` à la recherche de
répertoires frères `<NOM_PROJET>-issue<N>` (même convention que
`_chemin_worktree` dans `watcher.py`) ; pour chacun, le chemin de verrou
est recalculé via `_chemin_verrou()` (déjà importé de `watcher.py`) et le
fichier `.lock` supprimé s'il existe — uniquement une fois l'arbre de
process confirmé mort, même garde-fou que pour le verrou de
`REP_TRAVAIL`. Ces suppressions apparaissent dans le rapport de statut
renvoyé à l'interface (une étape `suppression_verrou_worktree_<nom>` par
worktree détecté, ou `suppression_verrous_worktrees` en `rien_a_faire`
si aucun). `WORKTREES.md` §4 mis à jour : la limite « verrou non libéré »
documentée depuis #338 est corrigée, plus besoin d'intervention manuelle
après un « Interrompre » pendant qu'un worktree tournait.

## 2 août 2026 — issue #339

Nettoyage de `TACHES.md` : suppression de trois items devenus obsolètes.
« Parallélisation en mode_write via git worktrees » est implémenté depuis
l'issue #337. « Rafraîchir une seule fois la ligne d'une issue quand son
décompte atteint zéro » est implémenté depuis l'issue #334. « Concurrence
limitée aux issues mode_lecture » est abandonné : le cas d'usage est trop
rare pour justifier une implémentation séparée, et le sujet sera
naturellement couvert par le système de worktrees si le besoin se
confirme. Restent inchangés : « Projet dédié à la communication CCL ↔
CCW » et « Calibration automatique du TIMEOUT — trois défauts à
corriger ».

## 2 août 2026 — issue #338

Documentation dédiée à la parallélisation mode_write via git worktrees
(#337) : nouveau fichier `WORKTREES.md` à la racine du dépôt, distinct de
`BRIDGE_AGENT_DOC.md` (manuel commun à tous les projets) pour ne pas
l'alourdir d'internals d'infrastructure. Couvre le pourquoi du mécanisme,
son design (`MAX_WRITE_PARALLELE`, premier slot sans worktree, verrou par
chemin de travail effectif, auto-extinction différée), le workflow normal
d'Alain (création d'issues, `git worktree list`, `fusionner_changelog.py`
avant merge, merge manuel branche par branche, nettoyage
`git worktree remove` + `git branch -d`), les procédures de récupération
(worktree orphelin, verrou non libéré — y compris la limite du bouton
« Interrompre », qui ne nettoie que le verrou de `REP_TRAVAIL` et pas ceux
des worktrees actifs —, `CHANGELOG-N.md` oublié, conflit de merge) et les
limites connues (`issues_en_cours` sans verrou explicite, pas d'alerte sur
l'accumulation de worktrees, `mode_lecture`/`mode_scratch` non
parallélisés). `BRIDGE_AGENT_DOC.md` §13 pointe désormais vers ce nouveau
fichier juste sous sa sous-section worktrees existante.

## 2 août 2026 — issue #337

Parallélisation des issues `mode_write` via `git worktree` : `watcher.py`
peut désormais traiter plusieurs tâches d'écriture **en parallèle**, chacune
dans un répertoire isolé sur sa propre branche, au lieu du traitement
strictement séquentiel historique. Les issues `mode_lecture`/`mode_scratch`
restent traitées séquentiellement dans `REP_TRAVAIL`, inchangées.

- Nouvelle clé `.conf` `MAX_WRITE_PARALLELE` (entier, défaut `2`) : nombre
  maximum de tâches `mode_write` concurrentes. `1` (ou `0`) = comportement
  séquentiel historique intégral, aucun thread ni worktree créé.
- `traiter_issue` (nouveau point d'entrée public) décide, pour chaque issue
  `mode_write` prête, entre traitement séquentiel classique et
  parallélisation : la première tâche détectée sans autre `mode_write` déjà
  en cours est dispatchée dans un thread ciblant `REP_TRAVAIL` directement
  (sans worktree, nécessaire pour que la boucle principale reste libre de
  détecter une deuxième tâche pendant que la première tourne) ; les
  suivantes, sous `MAX_WRITE_PARALLELE`, obtiennent chacune un worktree
  dédié (`<REP_TRAVAIL>/../<PROJET>-issue<N>`, branche
  `worktree-issue-<N>`, créés via `git worktree add`). Le corps de
  traitement existant (`_traiter_issue_synchrone`) est inchangé, à
  l'exception du chemin de travail effectif qu'il reçoit désormais en
  paramètre.
- Liste thread-safe (`threading.Lock` + liste) des tâches `mode_write`
  actuellement en thread (numéro, chemin du worktree ou `None`, thread
  Python), purgée des threads terminés à chaque décision de dispatch et en
  tête de boucle principale.
- Garde-fous à la création du worktree : chemin ou branche déjà existants,
  ou tout autre échec de `git worktree add` → repli propre sur le
  traitement séquentiel (l'issue attend qu'un slot se libère), jamais
  d'exception propagée.
- `lancer_claude` reçoit `chemin_worktree` : injecte dans le prompt, en
  worktree uniquement, un bloc d'avertissement (chemin, branche, consigne
  d'écrire l'entrée changelog dans `CHANGELOG-<N>.md` plutôt que
  `CHANGELOG.md` — voir `scripts/fusionner_changelog.py`, issue #336).
  Toutes les opérations déjà paramétrées par `cwd`/`perimetre` (backup,
  clause de périmètre du prompt, opérations git de garde-fou) reçoivent
  déjà le chemin de travail effectif (worktree ou `REP_TRAVAIL`) — aucun
  changement de signature nécessaire sur ces fonctions.
- Verrou anti-collision (#189/#322) posé par le chemin de travail effectif
  de la tâche (`REP_TRAVAIL` ou le worktree), et non plus systématiquement
  par `REP_TRAVAIL` seul : deux worktrees du même projet obtiennent deux
  verrous distincts et tournent sans s'attendre l'un l'autre.
- Fin de tâche en worktree : **aucune suppression automatique** (ni
  `git worktree remove`, ni suppression de branche) — Alain merge et pousse
  manuellement une fois le travail relu. Numéro d'issue, chemin du worktree
  et branche journalisés clairement.
- Auto-extinction (#199/#200) : ne se déclenche plus tant qu'un thread
  `mode_write` tourne encore, même au-delà de `DELAI_INACTIVITE_MIN` —
  réévaluée à chaque cycle.
- `BRIDGE_AGENT_DOC.md` §13 documente le mécanisme et `MAX_WRITE_PARALLELE`.
- Test de non-régression `tests/test_worktree_parallelisation_337.py` :
  nommage chemin/branche, création + replis (chemin/branche déjà pris),
  purge des threads terminés, scénario de bout en bout à deux issues
  `mode_write` concurrentes (première dans `REP_TRAVAIL`, seconde dans un
  worktree dédié, worktree conservé après coup), et non-régression avec
  `MAX_WRITE_PARALLELE = 1`.

## 2 août 2026 — issue #336

Création de `scripts/fusionner_changelog.py`, en préparation du futur
système de worktrees : quand CCL travaillera dans un répertoire isolé, il
écrira son entrée CHANGELOG dans `CHANGELOG-<N>.md` (N = numéro de l'issue)
plutôt que dans `CHANGELOG.md` directement, pour éviter les conflits
systématiques sur ce fichier unique quand plusieurs issues mode_write
tournent en parallèle. Ce script fusionne ces fichiers dans `CHANGELOG.md`
avant le push d'Alain.

- Scanne la racine du dépôt (`--repo`, défaut `.`) à la recherche de
  fichiers `CHANGELOG-<N>.md`, les trie par N décroissant (plus récent en
  tête, cohérent avec la convention de `CHANGELOG.md`, issue #252), et
  insère leur contenu tel quel en tête de `CHANGELOG.md`, juste après
  l'en-tête fixe (jusqu'à la ligne vide qui suit « Convention d'ajout :
  ... »). Les fichiers traités sont ensuite supprimés.
- Aucun `CHANGELOG-<N>.md` trouvé : message et sortie propre (code 0),
  `CHANGELOG.md` laissé inchangé — propriété qui rend une seconde exécution
  sans nouveaux fichiers idempotente de fait, puisque les sources du
  premier passage ont déjà été supprimées. Vérifié par test manuel (fichiers
  factices `CHANGELOG-338.md`/`CHANGELOG-340.md` dans un dépôt temporaire,
  hors du dépôt réel) : fusion correcte dans l'ordre #340 puis #338,
  suppression des fichiers sources, relance sans effet.
- Pas encore appelé automatiquement par `watcher.py` — le système de
  worktrees qui produira des `CHANGELOG-<N>.md` n'existe pas encore ;
  lancement manuel uniquement pour l'instant.

## 2 août 2026 — issue #335

Correction du radio Mode qui restait parfois figé sur « Lecture seule » après
un collage, alors que le corps collé portait bien `| MODE | écriture |` —
symptôme intermittent, corrigé par un simple F5 puis re-collage (observé à la
suite des issues #157 et suivantes).

- Cause racine : `viderFormulaire()` (appelée après chaque envoi réussi) remet
  le radio Mode sur *lecture* mais ne réinitialisait pas `dernierModeAutoDetecte`,
  la variable de garde de `detecterModeDansCorps()` (#326) qui évite de réécraser
  un choix manuel quand « rien de neuf » n'est détecté dans le corps. Si le
  corps collé ensuite portait le MÊME MODE que la détection précédente,
  `detecterModeDansCorps` voyait `valeurDetectee === dernierModeAutoDetecte` et
  ne touchait plus au radio — qui restait donc sur *lecture*, alors que ce
  n'était pas un choix manuel d'Alain mais le défaut posé de force par
  `viderFormulaire()` (qui vide aussi le corps par affectation directe de
  `.value`, sans déclencher d'événement `input`, donc sans repasser par la
  détection). Un rafraîchissement de page réinitialise cette variable JS à
  `null`, ce qui « corrigeait » silencieusement le symptôme au collage suivant.
- `static/js/app.js` (`viderFormulaire`) : ajout de `dernierModeAutoDetecte =
  null;` juste après la remise à *lecture* du radio, pour que le prochain
  collage soit toujours traité comme une détection neuve, quelle que soit la
  valeur MODE précédemment vue dans la session.
- Non modifié : `detecterProjetDansCorps`/`detecterTimeoutDansCorps`
  partagent le même schéma de garde-fou (`dernierProjetAutoDetecte`,
  `dernierTimeoutAutoDetecte`) et pourraient présenter la même faille — hors
  périmètre de cette issue, à traiter séparément si observé en pratique.

## 2 août 2026 — issue #334

Onglet Résultats : fetch unique de vérification 15s après le dépassement du
décompte TIMEOUT d'une issue — le watcher a besoin de quelques secondes après
son TIMEOUT pour poster le diagnostic et fermer l'issue ; jusqu'ici, la ligne
restait figée sur « ⌛ 0s — budget épuisé » même une fois l'issue close côté
serveur, jusqu'au prochain ↻ manuel. L'idée du `TACHES.md` (fetch au décompte
UI/médiane) est abandonnée au profit du décompte TIMEOUT réel, déjà présent
côté client, comme déclencheur — plus simple et plus fiable. Zéro polling
ajouté : un seul appel réseau par issue, une seule fois.

- `static/js/app.js` : dès que `formaterBadgeTempsRestant()` atteint la
  branche « budget épuisé », `programmerFetchDepassement()` pose un unique
  `setTimeout` de 15s (`DELAI_FETCH_DEPASSEMENT_MS`) qui appelle
  `verifierIssueApresDepassement()` — fetch de `/issue/<projet>/<numero>`
  (route existante). Un `Set` (`issuesFetchDepassementProgrammees`) garde-fou
  garantit une seule programmation par issue, même si le composant est
  rendu plusieurs fois (rendu de liste, tick/s de `majBadgesTempsRestant`).
- Issue fermée (`done`/`needs-human`) au moment du fetch : la ligne est mise
  à jour normalement (badge terminal, retrait du décompte), comme un ↻
  manuel restreint à cette seule ligne — nouvelle fonction
  `remplacerLigneIssue()`, qui reconstruit la ligne DOM via
  `construireLigneIssueDOM()` et rebranche ses gestes (clic/ctrl+clic/
  double-clic) via `brancherEvenementsLigneIssue()`, extraite de
  `rendreListeIssues()` pour être partagée sans dupliquer le câblage.
- Issue encore ouverte au moment du fetch (cas marginal de timing) : le
  badge devient « ⌛ dépassement — rafraîchir ↻ » (mémorisé dans le Set
  `issuesDepassementVerifie`, relu par `formaterBadgeTempsRestant`) et
  aucun autre fetch automatique n'est reprogrammé pour cette issue.

## 2 août 2026 — issue #333

Documentation : les deux boutons ⛔ « Interrompre » (CCL et CCW, issue
#323) sont désormais implémentés et fonctionnels — mise à jour de
`BRIDGE_AGENT_DOC.md` en conséquence, plus de renvoi mort vers
`TACHES.md`.

- `BRIDGE_AGENT_DOC.md`, §16.4 « Interrompre une issue CCW coincée » : la
  Note « un bouton [...] est prévu [...] (voir `TACHES.md`) » est
  remplacée par une description au présent de `interrompre_windows()`
  (`app/interruption.py`) : copie et exécution à distance (`VBoxManage
  guestcontrol`) de `provisioning/windows/interrompre_projet_ccw.ps1` —
  arrêt du service NSSM, vérification bornée (~5 s) que l'arbre de
  process est mort, suppression conditionnelle des `.lock` de
  `<RepDepot>\logs\verrous\`, label `needs-human` + commentaire de
  traçabilité systématiques, watcher jamais relancé automatiquement.
- `BRIDGE_AGENT_DOC.md`, §13 « Commandes utiles » : nouvelle sous-section
  « Interrompre une issue bloquée (issue #323, suite #320) », même niveau
  de détail que §16.4, pour le pendant côté CCL (`interrompre_linux()`) :
  arbre de process retrouvé par remontée `/proc/<pid>/status` (PPID),
  `SIGKILL`, attente de confirmation avant suppression du verrou —
  équivalent manuel (`kill -9` + suppression du `.lock`) inclus.
- `BRIDGE_AGENT_DOC.md`, pied de page : ligne « Dernière mise à jour »
  mise à jour (nouvelle entrée en tête, l'entrée #318 sort).
- Aucun changement de code — documentation uniquement.

## 2 août 2026 — issue #332

Le bouton « ⛔ Interrompre cette issue » (#323) tue par SIGKILL sans
prévenir que, si l'issue écrivait, le working tree du projet peut rester
PARTIEL (fichier à moitié écrit, backup présent sans le fix) — rien n'est
perdu ni poussé, mais l'état n'est pas nettoyé automatiquement et il faut
l'inspecter avant de relancer quoi que ce soit dessus.

- `static/js/app.js` — `interrompreIssue` : nouvelle `modeEcritureDepuisLabels`
  (mêmes labels que le pastillage `prefixeIssue`, ligne ~606, étendue à
  `mode_scratch`) détecte si l'issue écrivait (`mode_write` → 'ecriture',
  `mode_scratch` → 'lecture_active', aucun des deux → lecture seule, pas
  d'avertissement). Nouvelle `avertissementWorkingTree` formule le message
  (texte différent pour écriture pleine et pour lecture active — nuance :
  le garde-fou de restauration #327 tourne APRÈS claude, donc peut ne pas
  s'être exécuté avant un kill en pleine lecture active).
- Confirmation AVANT le kill (`confirm()`) : enrichie avec l'avertissement
  quand l'issue écrit — dernier moment pour renoncer. Comportement
  inchangé pour une issue en lecture seule.
- Modal de résultat APRÈS (`ouvrirModalInterrompre`, `modal-interrompre-rappel`) :
  reçoit désormais l'avertissement en paramètre et l'ajoute au rappel
  existant (relance manuelle du watcher) — `git status` dans le projet,
  annuler/repartir du commit `avant-XXX`, ne pas relancer d'issue sur ce
  projet avant working tree propre.

## 2 août 2026 — issue #330

Documentation du champ d'en-tête `MODE`, jusqu'ici absent de
`BRIDGE_AGENT_DOC.md` alors qu'il est auto-détecté depuis #326.

- **§3** — ajout de `MODE` à la liste des champs d'en-tête optionnels
  reconnus, avec un paragraphe dédié : `| MODE | … |` est détecté par
  `new_issue.py` (`detecterModeDansCorps`) exactement comme
  `TIMEOUT`/`PROJET`/`MODELE` — pré-sélectionne le radio Mode du
  formulaire puis la ligne est retirée du corps collé. Reconnaissance
  tolérante (insensible casse/accents, plusieurs libellés par valeur) et
  défaut LECTURE si le champ est absent ou non reconnu.
- **§6** — ajout d'une ligne `MODE` au tableau des champs spéciaux :
  valeurs `lecture`/`écriture`, effet (arme ou non le label `mode_write`
  via le radio du formulaire), renvoi au §5 pour le comportement des
  modes.
- **Ligne ~172 (§3, envoi en lot)** — précision : en mono-issue `MODE`
  est auto-détecté depuis l'en-tête du bloc, alors qu'en mode lot il
  reste commun à tout le lot (choisi une fois au radio du formulaire,
  jamais lu bloc par bloc).
- Volontairement **hors périmètre** : la troisième valeur (« lecture
  active » / `mode_scratch`) n'est PAS ajoutée à ces deux endroits — elle
  reste documentée uniquement au §5 (issue #327), car cette issue ne
  documente que les deux valeurs fonctionnelles au sens de la détection
  `new_issue.py`/formulaire.
- Pied de page de `BRIDGE_AGENT_DOC.md` mis à jour selon la convention
  §10 (nouvelle entrée en tête, glissement des deux précédentes ; l'entrée
  #299 sort du pied de page — déjà disponible dans `CHANGELOG.md`).

## 2 août 2026 — issue #327

Implémentation du mode « lecture active » (`mode_scratch`) côté
`watcher.py` — préparé formulaire/en-tête par #326, resté volontairement
inactif (une issue `mode_scratch` sans `mode_write` était traitée comme
lecture seule). Écriture confinée pour les outils d'analyse qui exigent un
vrai fichier de config sur disque (linters, eslint flat config ≥ 9, ...),
impossible à satisfaire en lecture seule.

**Mode à trois valeurs, plus un booléen empilé.** `autoriser_ecriture: bool`
pilotait CINQ points de décision (flag `--dangerously-skip-permissions`,
bloc de garde-fou du prompt, backup, garde-fou `configs/*.conf` #318,
étiquette de calibration TIMEOUT) — insuffisant pour un 3e mode. Remplacé
par `MODE_LECTURE`/`MODE_LECTURE_ACTIVE`/`MODE_ECRITURE` (nouvelle constante
`LABEL_SCRATCH = "mode_scratch"`), déduits des labels par la nouvelle
`_deduire_mode` (priorité `mode_write` > `mode_scratch` > lecture seule par
défaut) et lus par les cinq points ci-dessus — un futur 4e mode n'ajoutera
qu'une valeur, pas cinq retouches éparses. `lancer_claude` prend désormais
`mode` (plus `autoriser_ecriture`) et `chemin_scratch` ; les deux tests
existants qui l'appelaient directement (`test_nettoyage_arbre_247.py`,
`test_orphelin_verrou_perime_322.py`) sont mis à jour en conséquence.

**Chemin scratch** : `/tmp/bridge_scratch_<projet>/` (`<projet>` = `CFG.nom`,
validé strictement — aucun `../`, aucun séparateur de chemin — jamais dérivé
d'une valeur fournie par l'issue). Créé par le watcher juste avant le
premier lancement de claude en lecture active, supprimé dans un `finally`
(succès/échec/timeout confondus, même esprit que `_nettoyer_arbre_claude`).

**Défense en profondeur, niveau 1 + niveau 2** (même schéma que le
garde-fou `configs/*.conf`, #318) :
- **Niveau 1 (prompt)** : nouveau bloc de garde-fou dédié dans
  `lancer_claude`, distinct des deux blocs existants — chemin scratch exact,
  interdiction d'écrire ailleurs (notamment REP_TRAVAIL), interdiction de
  `git commit`/`git push`/commande destructrice, rappel que le scratch est
  éphémère et que le livrable reste un rapport de lecture.
  `--dangerously-skip-permissions` est ajouté (la lecture active doit
  pouvoir écrire dans le scratch), désarmant les mêmes protections claude
  que l'écriture libre — d'où le niveau 2.
- **Niveau 2 (détection technique a posteriori)** : nouvelles
  `_statut_git_rep_travail`/`_restaurer_rep_travail_modifie`, sur le modèle
  de `_empreinte_configs`/`_restaurer_configs_modifies` (#318) — empreinte de
  `git status --porcelain -uall` sur REP_TRAVAIL avant la première tentative,
  comparée après chaque tentative. Toute écriture détectée (fichier modifié,
  neuf ou supprimé) est restaurée (`git checkout`/`git clean` ciblés) et
  l'issue est marquée en échec définitif (`needs-human`, pas de nouvelle
  tentative) avec un message explicite. Le scratch (`/tmp`, hors REP_TRAVAIL)
  n'apparaît jamais dans cette empreinte par construction, donc n'est jamais
  emporté par la restauration.

**Backup et garde-fou configs** : aucun backup projet en lecture active
(comme la lecture seule — le filet est le niveau 2, pas un commit de
sauvegarde). Le garde-fou technique `configs/*.conf` (#318) est étendu : il
s'armait uniquement en mode écriture, il couvre désormais aussi la lecture
active (`mode != MODE_LECTURE`), cohérent avec le fait que ce mode arme
aussi `--dangerously-skip-permissions`.

**Calibration (§19)** : nouvelle étiquette `"scratch"` (fonction
`_etiquette_calibration`), distincte de `"read"`/`"write"`, appliquée aux
trois points de calibration (succès, timeout, échec définitif) —
`etat_timeout.json` et `historique_durees.json` gagnent une population
`projet|TYPE|scratch` propre, pour ne pas refaire le mélange de populations
que #326 avait corrigé côté UI. `app/issues.py` (estimation de durée d'une
issue ouverte, badge de progression) mis à jour en cohérence : `mode_scratch`
y était jusqu'ici classé à tort dans la population `"read"`.

`templates/index.html` : le radio « Lecture active » n'est plus marqué
« réservé » (le mode est désormais fonctionnel) ; `app/issues.py` (table
`MODES`) et le commentaire près de `LABEL_ECRITURE`/`LABEL_SCRATCH` dans
`watcher.py` mis à jour en conséquence.

Tests (`tests/test_lecture_active_327.py`, faux `claude` **et** faux `gh`,
aucun appel réseau) : déduction du mode depuis les labels (les quatre cas,
priorité `mode_write` > `mode_scratch`) ; validation stricte de
`_chemin_scratch` ; traitement complet (`traiter_issue`) d'une lecture
active qui n'écrit que dans le scratch → succès, REP_TRAVAIL inchangé,
scratch nettoyé ; traitement complet d'une lecture active qui écrit dans le
projet hors scratch → détecté, restauré (fichier modifié restauré à son
contenu d'origine, fichier neuf supprimé), `needs-human` posé, jamais
`done`.

`TACHES.md` : entrée « mode_scratch » retirée (implémentée).

## 2 août 2026 — issue #326

Détection automatique du MODE dans l'en-tête + mode à valeurs extensibles,
préparation lecture active/mode_scratch (issue #326). Deux problèmes réglés
ensemble : (1) contrairement à TIMEOUT/PROJET/titre, le champ `| MODE | … |`
était GÉNÉRÉ à l'envoi mais jamais LU depuis le corps collé — Alain cochait
« écriture » à la main par habitude même pour des tâches en réalité en
lecture seule, ce qui rangeait des lectures dans la population « write » et
faussait la calibration TIMEOUT (§19, clé projet|TYPE|mode) ; (2) le mode
était un booléen en dur (`autoriser_ecriture` déduit du seul label
`mode_write`), incapable de porter un futur 3e mode.

Frontend (`static/js/app.js`) : nouveau `detecterModeDansCorps`, calqué sur
`detecterTimeoutDansCorps`, branché sur l'input du corps — lit `| MODE | … |`
via `lireChampEntete` (aucune regex dupliquée), reconnaît la valeur de façon
tolérante (casse/accents, plusieurs libellés par mode : « écriture »/
« write »/`mode_write` ; « lecture active »/« scratch »/`mode_scratch` ;
« lecture »/« lecture seule »/« read »/`mode_read`), coche le bon radio,
retire la ligne MODE du corps (comme TIMEOUT/PROJET) et met à jour la
couleur du bouton d'envoi. **MODE absent ou non reconnu → LECTURE forcée**
(défaut sûr, cohérent avec le reset après envoi). Neutralisé en mode lot
(le MODE reste commun à tout le lot, DOC §3, inchangé).

`templates/index.html` : 3e radio `lecture_active` entre lecture et
écriture (ordre du moins au plus permissif), badge « scratch (mode_scratch,
réservé) » + tooltip précisant que ce mode n'est pas encore fonctionnel côté
watcher. Bouton d'envoi à 3 couleurs (`COULEURS_MODE`) : lecture → noir,
lecture active → bleu, écriture → rouge (inchangé, réservé à l'écriture
pleine, la plus risquée).

`app/issues.py` : nouvelle table `MODES` ({valeur radio → (libellé
français, label GitHub)}) lue à la fois par `construire_body` (champ
`| MODE | … |`) et `construire_labels` (pose du label technique) — remplace
les deux tests booléens en dur (`"ÉCRITURE" if mode == "ecriture" …` /
`if mode == "ecriture": labels.append("mode_write")`). Un futur 4e mode ne
demande qu'une ligne dans cette table.

**`mode_scratch` reste RÉSERVÉ, watcher.py non touché** : cette issue ne
porte pas l'implémentation de la lecture active côté watcher (issue séparée
à venir) — juste documenté (commentaire près de `LABEL_ECRITURE`) qu'une
issue portant `mode_scratch` sans `mode_write` est traitée comme lecture
seule par le watcher actuel (`autoriser_ecriture` ne teste que
`LABEL_ECRITURE`), comportement sûr. Backlog `TACHES.md` renommé en
cohérence (`mode_tmp_write` → `mode_scratch`, vocabulaire retenu par #326).

## 2 août 2026 — issue #325

Retrait de `TACHES.md` de l'entrée backlog « Bouton Interrompre dans
l'onglet CCW » (procédure manuelle nssm restart + suppression des
`.lock`), désormais implémentée — et dépassée — par #323 (suite #320) :
le bouton « ⛔ Interrompre cette issue » a été ajouté dans l'onglet
Résultats, pas l'onglet CCW, et couvre CCL comme CCW. Même convention de
retrait que #317 (retiré par #321) et les entrées PERIMETRE (#319) :
suppression pure de la section obsolète, rien d'autre touché.

## 2 août 2026 — issue #324

Ajout au backlog `TACHES.md` d'une entrée (pas d'implémentation) :
« Rafraîchir une seule fois la ligne d'une issue quand son décompte atteint
zéro ». Née d'une session où le décompte figé côté navigateur
(`majBadgesTempsRestant`, jamais re-fetché depuis #270) a fait douter à
répétition de l'état réel d'issues déjà closes (#320/#322/#323). Idée :
au passage à « ⌛ 0s — budget épuisé », déclencher UN SEUL fetch ciblé de
l'issue via la route existante `/issue/<projet>/<numero>` (`issue_detail`)
plutôt qu'un re-fetch périodique de toutes les issues comme avant #270 —
distinction explicitée dans l'entrée pour qu'une future implémentation ne
réintroduise pas le polling banni par #270 (~3840 pts/h de quota GraphQL,
cf. #263). Point de conception laissé ouvert : comportement au dépassement
légitime (re-fetch à intervalle long vs. badge « rafraîchir » manuel), avec
anti-abus à prévoir si l'option de re-fetch est retenue.

## 2 août 2026 — issue #323 (suite #320)

Bouton **« ⛔ Interrompre cette issue »** dans l'onglet Résultats, sur toute
issue ouverte ni `done` ni `needs-human` — remplace l'intervention manuelle
hors interface (kill + nettoyage de verrou à la main) qu'exigeait jusqu'ici
un watcher bloqué (verrou orphelin, process pendu). Reprise de #320,
abandonnée 3 fois faute de `TIMEOUT` suffisant (600s ne couvrait pas
`watcher.py` + route Flask + logique CCW + modal front) ; `TIMEOUT` porté à
1800s pour cette reprise. **Contrainte centrale** : interrompre UNE issue ne
sacrifie jamais les autres issues en file pour le même watcher — elles
restent ouvertes sur GitHub, simplement en attente d'une relance MANUELLE
(bouton « Lancer watcher » côté CCL, onglet CCW côté CCW-Watcher ; aucun
rallumage automatique ici, à la différence de #202).

- Nouvelle route **`POST /interrompre`** (`app/interruption.py`) : reçoit
  `{depot, numero, labels}`, résout le projet via `projet_par_depot` (nouveau
  dans `app/projets.py`) — **toujours par le champ DEPOT du `.conf`**, jamais
  déduit du nom projet ni du basename de `REP_TRAVAIL` (trois clés distinctes
  qui peuvent diverger, ex. projet « echecs » / dépôt `AlChess` / répertoire
  `~/NicLink`). Chaque étape renvoie un statut à **trois valeurs**
  (`succes`/`rien_a_faire`/`echec`) + message ; une étape en échec n'arrête
  pas les suivantes, sauf la suppression du verrou, volontairement **sautée**
  si l'arbre de process n'est pas confirmé mort. Statut global dérivé : `ok`
  / `succes_partiel` / `echec_critique` (arbre non tué → lock **non**
  nettoyé, pour ne jamais risquer un double traitement). Label `needs-human`
  + commentaire `⛔ Interrompu via new_issue.py` posés dans TOUS les cas
  (sortie du circuit + trace), avant même le résultat des étapes techniques.
  - **for-linux** : arbre de process du watcher (`logs/watcher-<nom>.pid` +
    toute sa descendance, dont l'éventuel claude en session séparée,
    §13/#247) énuméré par **remontée `/proc` via PPID** — jamais par nom
    d'exécutable — puis `SIGKILL`, attente bornée (~5s) de disparition
    effective avant de supprimer le verrou par **nom exact**
    (`watcher._chemin_verrou` réutilisée telle quelle, jamais redupliquée),
    puis re-vérification (verrou frais réapparu → signalé comme course #202
    probable, jamais resupprimé en boucle). Piège découvert en testant :
    le process watcher est un enfant DIRECT du process Flask
    (`app/watchers.py:demarrer_watcher`) jamais attendu (`wait()`) — après
    `SIGKILL` il reste **zombie** et `os.kill(pid, 0)` le signale encore
    vivant indéfiniment ; `_reaper_best_effort` (`os.waitpid(..., WNOHANG)`)
    corrige ce faux positif. `FileNotFoundError` sur le verrou = `rien_a_faire`
    (libéré normalement), pas un échec.
  - **for-windows** : nouveau script `provisioning/windows/
    interrompre_projet_ccw.ps1` (poussé + exécuté via guestcontrol, pattern
    `app/ccw.py` — service et répertoire du projet résolus dynamiquement via
    `_lister_projets_vm`, jamais codés en dur malgré l'exemple `CCW-Watcher`
    / `C:\CCW\Bridge_Agent` de l'issue) : arrêt du service NSSM, vérification
    + kill ciblé de l'arbre resté vivant (remontée par `ParentProcessId`,
    même logique PPID que côté Linux), suppression des `.lock` du dossier
    `logs\verrous` du projet **seulement** si l'arbre est confirmé mort.
    Non exécuté contre une VM réelle (pas d'environnement CCW disponible ici
    — comme `finaliser_projet_ccw.ps1` en son temps).
- `templates/index.html` / `static/js/app.js` : bouton `interrompreIssue()`
  dans `construireHtmlIssue` (dépôt lu depuis le `<select id="projet">`
  peuplé côté serveur « nom — depot », jamais déduit du nom ; labels lus
  depuis le cache localStorage du détail déjà affiché). Modal dédiée
  (`#modal-interrompre`) détaillant **chaque étape** (statut + message), pas
  seulement le résultat global, avec rappel de la relance manuelle adapté à
  l'agent (CCL vs CCW) et alerte explicite en cas de `succes_partiel` /
  `echec_critique` (« vérifier avec ps/Gestionnaire des tâches avant de
  relancer »). Avertissement discret si la VM CCW n'est pas démarrée
  (`vm_running` dans la réponse).
- Testé (hors modal/CCW, sans VM disponible) : arbre de process réel
  (`sh` + enfant `sleep`) tué + confirmé mort + verrou nommé supprimé +
  re-vérifié ; cas `rien_a_faire` (aucun watcher, aucun verrou) ;
  `projet_par_depot` contre les `.conf` réels du dépôt.

## 2 août 2026 — issue #322

Dernier trou résiduel du cycle de vie verrou/claude comblé : si le watcher
meurt BRUTALEMENT (kill -9, coupure de courant, plantage Python non
capturé) pendant qu'un claude tourne, aucun `finally` ne s'exécute — le
claude devient orphelin ET le verrou reste posé. Au démarrage suivant, le
watcher voyait ce verrou, le déclarait périmé et le REPRENAIT sans
vérifier qu'un claude orphelin de l'ancien contexte tournait encore,
risquant de lancer un second claude dans le même `REP_TRAVAIL` pendant que
l'orphelin y écrivait toujours (le périmètre empêche de sortir du dossier,
pas deux process d'y entrer en collision). Fermé PAR CONSTRUCTION, au seul
moment qui compte (la reprise d'un verrou périmé) — pas par une
surveillance externe (cron), aveugle quand le watcher est éteint.

- `watcher.py` :
  - `lancer_claude` accepte un paramètre `verrou` optionnel ; une fois le
    `Popen` du claude réussi, `_maj_verrou_pgid` consigne son pgid
    (== pid, `start_new_session=True`) dans le fichier verrou via un
    nouveau champ `claude_pgid=<n>`, en préservant les champs existants
    (`pid=`/`projet=`/`rep=`). Le verrou est posé par `acquerir_verrou`
    AVANT le lancement de claude : le pgid n'est donc connu qu'après le
    `Popen`, d'où cette mise à jour a posteriori plutôt qu'à la pose.
  - `_lire_pgid_verrou` : lit ce champ, `None` si absent (ancien format,
    ou watcher mort avant même le lancement de claude) — traité sans
    erreur, aucun kill tenté dans ce cas.
  - `_nettoyer_orphelin_verrou_perime` (appelée depuis `acquerir_verrou`,
    juste avant `verrou.unlink()`, uniquement sur la branche verrou
    PÉRIMÉ) : garde-fou anti-reboot à trois conditions cumulées avant
    tout kill — verrou périmé (déjà garanti par l'appelant), un process
    de ce pgid existe encore (`_lister_processus_pgid`, réutilisée telle
    quelle), et sa ligne de commande contient bien « claude » (identifier
    par ce que le process EST, jamais tuer aveuglément, même esprit que
    #247 point 4). Si les trois sont réunies : `os.killpg(pgid,
    SIGKILL)` sur ce seul groupe, un `log.warning` par process tué
    (PID + ligne de commande), attente bornée (5s) de la disparition
    effective. Un pgid mort ou recyclé après un reboot (PID/pgid
    réattribués) ne provoque aucun kill. POSIX uniquement, gardé par
    `os.name != "nt"` côté appelant (sous Windows, objet Job — pas de
    pgid, la question ne se pose pas dans les mêmes termes).
    Best-effort strict, comme `_nettoyer_arbre_claude` (#249) : toute la
    logique est enveloppée dans un garde-fou total (`_lister_processus_
    pgid` peut lever `OSError`, `os.killpg` une `PermissionError`) — une
    erreur du nettoyage journalise et laisse la reprise du verrou suivre
    son cours normal, jamais de remontée qui ferait échouer l'acquisition
    du verrou ni le traitement de l'issue.
  - `traiter_issue` : passe désormais le verrou courant à `lancer_claude`.
- `tests/test_orphelin_verrou_perime_322.py` (nouveau, sur le modèle de
  `tests/test_nettoyage_arbre_247.py`) : orphelin réellement tué à la
  reprise d'un verrou périmé (et journalisé) ; garde-fou anti-reboot sur
  pgid vivant mais pas un claude, et sur pgid mort/recyclé — aucun kill
  dans ces deux cas ; verrou d'ancien format (sans `claude_pgid`) repris
  sans erreur ; `lancer_claude` consigne bien le pgid dans le verrou
  fourni.

## 2 août 2026 — issue #321

Champ de recherche par TITRE dans l'onglet Résultats de `new_issue.py`,
répondant au backlog ouvert par #317 suite au doublon #315/#316 — sous
une forme différente de l'idée initiale (titre ET corps) : décision de
#321 de rester sur le titre seul, plus rapide et suffisant pour
retrouver un sujet déjà traité. Entrée backlog correspondante retirée
de `TACHES.md`.

- `app/issues.py` : nouvelle route `recherche_issues` (une par projet,
  comme `issues_liste`) — `gh issue list --state all --limit <portée>`
  (state `all` : on cherche justement une issue déjà fermée/done),
  `--limit` réutilisant `_limite_issues_requete`/`LIMITE_ISSUES_MIN`/
  `LIMITE_ISSUES_MAX` sans dupliquer de borne. Filtrage sur le titre
  uniquement, insensible casse+accents via `_normaliser_recherche`
  (NFKD + suppression des diacritiques + casefold). Même gestion
  d'erreur (timeout/gh introuvable/returncode) qu'`issues_liste`.
- `app/__init__.py` : route `/recherche-issues/<nom_projet>`.
- `static/js/app.js` : champ texte + champ « portée » (défaut 15/projet,
  borné à `LIMITE_ISSUES_MAX`, réglage DISTINCT de la limite d'affichage
  de l'onglet) dans la barre de contrôles, déclenchement au clic (ou
  Entrée) uniquement — jamais à la frappe, cohérent avec #270. La
  recherche porte sur les projets actuellement sélectionnés dans les
  filtres (un appel `gh` par projet, portée non cumulative), ratisse
  toute la portée sans s'arrêter au premier match, respecte le filtre
  « 👷 Ouvriers », et agrège les échecs par projet sans annuler les
  autres. `construireLigneIssueDOM` extrait de `rendreListeIssues` pour
  être partagée avec la nouvelle fenêtre de résultats, qui réutilise
  telles quelles `copierReponseDepuisBadge`/`copierDiffDepuisBadge`/
  `copierToutEtDiffDepuisBadge` (badges ✅/Diff/All) et une nouvelle
  `afficherIssueRecherche` (double-clic) chargeant dans sa PROPRE zone
  de détail (`#zone-issue-recherche`), autonome de celle de l'onglet —
  plusieurs corps peuvent s'enchaîner sans se fermer mutuellement.
  `demarrerRedimTitre`/`finRedimTitre` adaptés pour redimensionner la
  colonne titre de la fenêtre indépendamment de celle de l'onglet, sans
  persister ce redimensionnement en localStorage.
- `templates/index.html` : barre de recherche statique dans l'onglet
  Résultats + modal `#modal-recherche-titre` (liste + zone de détail
  propres, bouton Fermer).
- `static/css/style.css` : styles de la barre et du modal.
- `TACHES.md` : retrait de l'entrée de backlog « Champ de recherche
  texte dans l'onglet Résultats » (#317), désormais implémentée.

La limite d'affichage par défaut de l'onglet (`LIMITE_ISSUES_DEFAUT`,
30) reste inchangée — le 15 par défaut ne concerne que la portée de
recherche, un réglage distinct.

## 2 août 2026 — issue #319

`TACHES.md` : retrait de l'entrée de backlog « Garde-fou technique sur
la modification de PERIMETRE » (diagnostic du 31/07/2026, issue #298),
désormais implémentée — sous une forme différente de l'idée initiale
(détection/confirmation) : décision finale du 02/08/2026 d'interdire
purement et simplement toute modification de `configs/*.conf` par
CCL/CCW (issue #318, commit 65e81c5). Suppression simple, même
convention que les issues #310/#312. Reste du fichier inchangé,
notamment « Champ de recherche texte dans l'onglet Résultats de
new_issue.py » (#317), toujours en attente sans implémentation.

## 2 août 2026 — issue #318

Interdiction totale de modification de `configs/*.conf` par CCL/CCW, y
compris en mode_write (diagnostic #298, décision du 02/08/2026 : pas de
mécanisme de détection/confirmation, interdiction pure et simple —
seul Alain modifie ces fichiers à la main ou via l'onglet Configuration
de `new_issue.py`).

- `consignes/globales.md` : nouvelle règle explicite — CCL/CCW ne
  modifie JAMAIS `configs/*.conf`, même si une issue le demande en
  toutes lettres ; en cas de demande de ce type, refuser cette partie
  de la tâche, l'expliquer dans le rapport de clôture, ne rien
  committer sur ce point.
- `watcher.py` : garde-fou technique en deux temps.
  - `_detecter_demande_modif_configs` : repérage best-effort (regex sur
    un chemin `configs/*.conf` dans le corps) juste avant le lancement
    de claude en mode_write — purement informatif (WARNING journalisé),
    ne bloque rien.
  - `_empreinte_configs` / `_restaurer_configs_modifies` : instantané
    intégral (contenu brut) de `configs/*.conf` pris une seule fois
    avant la première tentative de `traiter_issue`, comparé après
    CHAQUE tentative (succès ou échec). Toute modification, création ou
    suppression détectée est annulée automatiquement (restauration du
    contenu d'origine, ou suppression d'un fichier apparu), avec un
    WARNING explicite par fichier concerné — sans jamais faire échouer
    le reste du traitement de l'issue (best-effort, aucune exception
    propagée). `configs/` est commun à tous les projets (partagé par ce
    `watcher.py`), donc l'ensemble du dossier est protégé, pas
    seulement le `.conf` du projet en cours de traitement.
- `BRIDGE_AGENT_DOC.md` (§12) : le paragraphe « Exception » sur
  `configs/*.conf` précise désormais que cette exception vaut
  uniquement pour Alain (à la main ou via l'onglet Configuration),
  jamais pour CCL/CCW, même en mode_write, et renvoie vers le
  garde-fou technique de `watcher.py`.

## 2 août 2026 — issue #315

`BUILD_WINDOWS_CCW.md` : ajout de la checklist Rummikub (build validé),
insérée avant l'entrée Scrabble (plus récente en premier) — clone
`Z:\CCW\rummikub`, script `build\rebuild_rummikub.bat` (6 étapes),
`rummikub.spec` en liste explicite des `datas` (`src/rummikub/ui/web/`,
aucun `collect_tree` en bloc), TIMEOUT de référence 1200s (build réel
~333s), et les deux garde-fous de taille distincts introduits par
l'issue #57 (dist non compressé vs installeur compressé étant deux
grandeurs différentes) : `dist\Rummikub\` non compressé 28 712 051
octets (~28,7 Mo, fourchette 20-45 Mo) et `Rummikub-Setup.exe`
compressé 12 778 092 octets (~12,18 Mo, fourchette 5-25 Mo).

## 2 août 2026 — issue #314

`BRIDGE_AGENT_DOC.md` (§12.1, juste après le tableau des trois couches
de consignes) : ajout d'un renvoi explicite pour un Claude en
conversation (celui qui rédige une issue avant envoi, ex.
ClaudeRummikub) vers `consignes/globales.md` via `curl`, sur le même
modèle que le renvoi déjà existant vers `BRIDGE_AGENT_DOC.md` lui-même
(§9). Jusqu'ici le tableau décrivait l'injection automatique par
`watcher.py` à l'exécution (CCL/CCW) sans jamais pointer un Claude en
conversation vers le contenu réel de `globales.md` — notamment le
garde-fou backup/reset ajouté par l'issue #313, invisible avant que
l'issue parte à l'exécution.

## 2 août 2026 — issue #313

`consignes/globales.md` : ajout de deux garde-fous mutualisés à tous les
projets (injection automatique, aucune modification de `CONTEXTE.md` par
projet nécessaire). (1) Garde-fou backup/reset : le commit de sauvegarde
(`git add -A`) peut faire passer sous suivi git des dossiers auparavant
non trackés (ex. `.tools/`, `installeur/output/`) ; si le script exécuté
ensuite se termine par une opération git destructive (`reset --hard`,
`clean -fd`), ces dossiers seraient effacés du disque — vérifier via
`git status`/`git show --stat` et détracker (`git rm --cached`) avant de
lancer un tel script. Problème constaté et corrigé au cas par cas sur
Scrabble et Rummikub (issues #306, #311). (2) Renvoi vers
`BUILD_WINDOWS_CCW.md` (dépôt bridge_agent, racine) avant de proposer une
issue de build ou de modification de pipeline sur un projet ayant un
script de build Windows (PyInstaller/Inno Setup) — documente le pattern
de staging local et l'extension du PÉRIMÈTRE associée (issue #297/#299).

## 2 août 2026 — issue #312

`TACHES.md` : retrait des trois entrées de backlog désormais
implémentées — « Capture stderr CCL dans watcher.py » et « Vérification
pre-flight de la validité du token CCL » (issue #309, commit bcd3a11)
et « Archivage de logs/historique_durees.json » (issue #310, commit
6df2f44). Suppression simple, sans section « Terminé » : c'est déjà la
convention établie pour ce fichier (cf. commit dcecb85). Reste du
fichier inchangé, notamment « Garde-fou technique sur la modification
de PERIMETRE » (#298) et « Concurrence limitée aux issues mode_lecture »,
toujours en attente sans implémentation.

## 2 août 2026 — issue #310

Nouveau script `scripts/archiver_historique.py`, lancement manuel
uniquement — jamais appelé par `watcher.py` (issue #310) — pour purger
`logs/historique_durees.json`, qui accumule toutes les entrées depuis
mai 2026 sans purge et grossit à chaque clôture d'issue. Diagnostic
préalable (lecture du code, pas de conséquence sur ce script) :
`maj_calibration_timeout` (EWMA, calibration TIMEOUT réelle, issue
#221, `watcher.py`) est purement incrémentale et ne lit/écrit jamais
`historique_durees.json` (seulement `etat_timeout.json` et
`etat_ambiance.json`) — l'archivage n'a donc aucun impact sur elle ;
`estimer_duree` (badge de fiabilité à la création d'une issue, issue
#108, `app/issues.py`) recalcule en revanche une médiane à partir de
tout l'historique transmis, filtré par projet/type/mode, donc un
archivage réduit potentiellement le nombre d'échantillons par
catégorie.

Fonctionnement : pour chaque combinaison (projet, type, mode), les
`--n-min` entrées les plus récentes (défaut 20) sont TOUJOURS
conservées quelle que soit leur ancienneté ; au-delà de ce plancher,
les entrées antérieures à `--seuil-mois` (défaut 6) sont déplacées
vers `logs/historique_durees_archive_<année>.json` (une entrée va
dans le fichier de SON année ; fusion avec l'archive existante si déjà
présente). Les entrées à date illisible/absente sont conservées par
prudence, jamais archivées. N_MIN_DEFAUT = 20 choisi en cohérence avec
`SEUIL_ESTIM_SUR = 15` (`app/issues.py`) : une catégorie déjà au badge
"sûr" (vert, n > 15) avant archivage y reste après, avec une marge de
confort de 5. Le rapport console liste, par catégorie, le nombre total
avant, archivé et conservé, avec une alerte si une catégorie repasse
sous le seuil "sûr". `--dry-run` simule sans rien écrire. Écriture
atomique (`tempfile` + `os.replace`, même motif que `watcher.py`) ;
`etat_timeout.json` et `etat_ambiance.json` ne sont ni lus ni écrits
par ce script.

Testé sur une copie temporaire (`/tmp`, hors dépôt) avec des seuils
réduits pour valider le mécanisme (archivage, fusion sur double
exécution, conservation du total d'entrées) avant exécution réelle sur
`logs/historique_durees.json` : avec les valeurs par défaut (6 mois),
aucune entrée n'est encore assez ancienne (données depuis le
24/05/2026 seulement) — 774 entrées conservées, 0 archivée, fichier
inchangé après exécution. `etat_timeout.json` vérifié inchangé (même
empreinte MD5) ; `etat_ambiance.json` n'existe pas encore sur cette
machine et n'a pas été créé par ce script.

## 2 août 2026 — issue #309

Diagnostic CCL amélioré dans `watcher.py`, zone `lancer_claude()` (issue
#309) — suite à l'incident #279 où plusieurs issues avaient échoué en
~1,2s avec le message générique "Erreur inconnue" (cause réelle : token
CCL expiré), sans aucune indication exploitable dans le log. Deux ajouts
dans la même zone de code : **A)** capture stderr — au retour de
`communicate()`, si le process claude échoue (code de retour non nul),
les 2000 premiers caractères de son stderr sont journalisés en WARNING
(`_extrait_stderr`, tronque avec mention du nombre total de caractères
au-delà de cette limite, pour éviter un dump de plusieurs Mo tout en
gardant de quoi diagnostiquer une panne d'auth/réseau) ; **B)**
vérification pre-flight du token — nouvelle fonction
`verifier_preflight_token()`, appelée une seule fois par issue dans
`traiter_issue()` juste avant la boucle de tentatives (pas à chaque
tentative), qui lance un `claude --print` court (stdin vide, timeout 5s)
et recherche dans stdout+stderr des signatures d'authentification
manquante/expirée (`SIGNATURES_TOKEN_EXPIRE` : "not logged in", "/login",
"invalid api key", etc.) ; si détecté, WARNING explicite invitant à
relancer `claude` interactivement et taper `/login`. Choix délibéré de
passer une entrée vide via **stdin** plutôt que l'exemple littéral de
l'issue (`claude -p ""`) : un argument positionnel vide est rejeté
immédiatement par la validation d'arguments du CLI ("Input must be
provided...") AVANT toute vérification d'authentification, quel que
soit l'état du token — inutilisable comme sonde ; passé en stdin, l'appel
atteint bien le contrôle d'authentification. Le pre-flight ne bloque
jamais le traitement (toute exception — timeout, `claude` introuvable —
est avalée silencieusement, aucune tentative n'est empêchée) et est
sauté en dry-run. Comportement nominal (issues qui réussissent) inchangé
: vérifié par exécution manuelle de `verifier_preflight_token()` sur
l'environnement courant (aucune exception, aucun faux positif avec un
token valide) et simulation d'un échec de process (stderr correctement
tronqué et journalisé). Commit local, pas de push.

## 1er août 2026 — issue #299

Crée `BUILD_WINDOWS_CCW.md` à la racine du dépôt (issue #299), dédié au
contenu spécifique-projet des builds Windows délégués à CCW — jusqu'ici en
voie d'accumulation dans `BRIDGE_AGENT_DOC.md` (§16.3) à chaque nouveau
projet buildé (Scrabble déjà, Rummikub en préparation). Le fichier reprend
le pattern général de staging local documenté par l'issue #297 (corruption
de fichiers sur `\\VBOXSVR\CCW_Share`, contournement via
`C:\Temp\<Projet>Build`, extension obligatoire du `PERIMETRE` dans
`configs\ccw.conf`), ajoute une checklist type à remplir par projet
buildé (clone CCW, script de build, `.spec` — datas explicites ou
`collect_tree` en bloc avec mise en garde suite à l'incident dump
wiktionnaire 8,2 Go sur Scrabble du 31/07/2026 —, TIMEOUT de référence,
taille/hash de l'artefact final), et une première entrée déjà remplie
pour Scrabble (`Z:\CCW\scrabble`, `build\rebuild_scrabble.bat` en 7
étapes fix #338, `scrabble.spec` corrigé en liste explicite, TIMEOUT
1200s, installeur de référence 26 546 846 octets, SHA256
`d52e101f8758a1b107011adf0bc1a04102bce48d3283248650019ba101ef3254`).
En contrepartie, la note « staging local » ajoutée au §16.3 de
`BRIDGE_AGENT_DOC.md` par l'issue #297 est remplacée par un renvoi de
deux lignes vers ce nouveau fichier ; pied de page de `BRIDGE_AGENT_DOC.md`
glissé (#299 en tête, #287 conservée, #297 conservée en dernière position
avec note du remplacement, #285 sorti).

## 31 juillet 2026 — issue #297

Documente au §16.3 « Procédure — builder un projet Windows » de `BRIDGE_AGENT_DOC.md` le pattern de staging local pour les builds Windows CCW (issue #297), jusqu'ici décrit uniquement dans le `CONTEXTE.md` propre au projet Scrabble et donc invisible pour toute autre instance CCL/CCW ayant le même besoin (ex. Rummikub, même stack PyInstaller + Inno Setup, prévoit ce pattern dès son premier script de build). Contexte : diagnostic du 31/07/2026 sur Scrabble — les builds PyInstaller + Inno Setup produisaient des fichiers tronqués/corrompus lorsqu'ils tournaient directement sur le partage VirtualBox `\\VBOXSVR\CCW_Share` (fix #338). Nouvelle note ajoutée juste après le paragraphe « Note safe.directory », avant la sous-section 16.4 : **contournement standard** — le script de build copie les sources vers un répertoire local à la VM (`C:\Temp\<Projet>Build` ou équivalent), construit entièrement là, puis ne recopie vers le partage que l'artefact final ; **conséquence obligatoire** — ajouter ce chemin local au `PERIMETRE` de `configs\ccw.conf` (liste séparée par virgules), sans quoi CCW refuse à juste titre d'en sortir et bloque légitimement le build ; **rappel** — avant d'ajouter un nouveau projet à builder sous Windows, vérifier si son script de build suit déjà ce schéma et, si oui, étendre le `PERIMETRE` en conséquence. Pied de page de `BRIDGE_AGENT_DOC.md` glissé (issue #297 en tête, #287 et #285 conservées comme les deux entrées les plus récentes parmi les issues modifiant cette doc, #281 sorti). Aucun fichier `.py`/`.js` modifié (documentation seule), aucune section renumérotée.

## 30 juillet 2026 — issue #287

Documente au §16 « Agent Windows CCW » de `BRIDGE_AGENT_DOC.md` la procédure d'interruption d'une issue CCW coincée (issue #287), jusqu'ici purement manuelle et non écrite nulle part. Nouvelle sous-section **16.4 « Interrompre une issue CCW coincée »** insérée après la note sur `safe.directory` (fin du §16), avant le §17 : **symptôme** — le watcher `CCW-Watcher` détecte bien l'issue à chaque cycle mais log en boucle, sans jamais progresser, « Issue différée : un autre traitement détient déjà le verrou sur `\\VBOXSVR\CCW_Share\` » ; **cause** — un fichier verrou laissé dans `C:\CCW\Bridge_Agent\logs\verrous\` n'a pas été nettoyé (process tué brutalement, ou redémarrage NSSM du service sans libération propre du verrou en cours), le watcher refusant alors de retraiter l'issue tant que ce fichier existe, même après redémarrage ; **procédure manuelle** en deux étapes — `nssm restart CCW-Watcher` (nécessaire mais pas suffisant seul), puis lister et supprimer le(s) fichier(s) `.lock` restant(s) dans `C:\CCW\Bridge_Agent\logs\verrous\` via `Get-ChildItem ... -Filter "*.lock"` et `Remove-Item` ; **note** — un bouton « Interrompre » dans l'onglet CCW de `new_issue.py` est prévu pour automatiser cette procédure à distance depuis Linux (voir `TACHES.md`, backlog ajouté par l'issue précédente be4cae0). Pied de page de `BRIDGE_AGENT_DOC.md` glissé (issue #287 en tête, #285 et #281 conservées comme les deux entrées les plus récentes parmi les issues modifiant cette doc, #279 sorti). Aucun fichier `.py`/`.js` modifié (documentation seule), aucune section renumérotée.

## 30 juillet 2026 — issue #285

Documente au §3 « Créer une issue — la méthode normale » de `BRIDGE_AGENT_DOC.md` le comportement exact du bouton **« Aperçu de la commande »** de l'onglet Nouvelle issue (issue #285), jusqu'ici non décrit malgré sa présence de longue date dans le formulaire. Nouveau paragraphe inséré juste après la description du lancement (`new_issue.py`/`lancer_new_issue.sh`) et avant le « Format du corps pour copier-coller » : le bouton appelle la route `/apercu` (fonction `apercu()` de `app/issues.py`), qui construit à partir des champs actuellement remplis dans le formulaire la commande `gh issue create` exacte qui serait exécutée (dépôt, titre, labels, `--body-file`), suivie en commentaire du corps complet qui serait envoyé, renvoyée en JSON. `afficherApercu()` (`static/js/app.js`) affiche ce texte tel quel dans la zone `zone-apercu` sous le formulaire. Point clé : c'est un aperçu pur — aucune issue n'est créée, aucune commande n'est réellement exécutée, rien n'est modifié tant que le bouton d'envoi n'est pas cliqué séparément. Pied de page de `BRIDGE_AGENT_DOC.md` glissé (issue #285 en tête, #281 et #279 conservées comme les deux entrées les plus récentes parmi les issues modifiant cette doc, #268 sorti). Aucun fichier `.py`/`.js` modifié (documentation seule), aucune section renumérotée.

## 30 juillet 2026 — issue #281

Ajoute au §11 « Conventions de code » de `BRIDGE_AGENT_DOC.md` le paragraphe **« Niveau de détail des issues »** (issue #281), en réponse à une tendance observée chez Claude Chat à rédiger du code complet dans le corps des issues (blocs Avant/Après, implémentations entières) alors que CCL est capable de lire les fichiers source et d'implémenter lui-même à partir d'une description claire. La règle posée : Claude Chat décrit le problème, la cause et l'intention du fix, sans rédiger le code complet — CCL fait l'implémentation. **Exception tolérée** : un snippet de 1-2 lignes si la syntaxe est non-triviale ou si l'intention serait ambiguë sans exemple. **Mauvais exemple** donné : fournir les trois méthodes complètes Avant/Après pour un fix pywebview de navigation différée. **Bon exemple** : « Dans `api.py`, pour les trois méthodes de navigation, différer l'appel dans un thread daemon avec `time.sleep(0.05)` avant de naviguer. » Pied de page de `BRIDGE_AGENT_DOC.md` glissé (issue #281 en tête, #279 et #268 conservées comme les deux entrées les plus récentes parmi les issues modifiant cette doc, #263 sorti). Aucun fichier `.py` modifié, aucune section renumérotée.

## 30 juillet 2026 — issue #279

Documente dans §13 de `BRIDGE_AGENT_DOC.md` le diagnostic du symptôme « Erreur inconnue » observé la nuit du 29/07/2026 (issue #279) : plusieurs issues avaient échoué en ~1,2 s, 3 tentatives et passe diagnostique comprises, le message générique masquant totalement la cause réelle — une session CCL expirée. Nouveau bloc **« Diagnostic — CCL ne démarre pas »** ajouté en fin de §13 (après le paragraphe sur les services systemd abandonnés) : **symptôme** (échec quasi immédiat sur toutes les issues → cause systémique, pas liée au contenu d'une tâche précise) ; **première vérification** (`claude -p "test" 2>&1` — une réponse « Not logged in » signe un token de session CCL expiré) ; **résolution** (lancer `claude` en session interactive, puis taper `/login`) ; **autres causes possibles** (réseau indisponible/DNS, installation `claude` corrompue) ; et le **critère de distinction** entre ces causes par le temps d'échec — un token expiré échoue en moins de 2 secondes (observé le 29/07/2026), un problème réseau échoue en général bien plus tard, proche du `TIMEOUT` configuré dans l'en-tête de l'issue (l'appel reste bloqué à attendre une réponse qui ne vient jamais). Pied de page de `BRIDGE_AGENT_DOC.md` glissé (issue #279 en tête, #268 et #263 conservées comme les deux entrées les plus récentes parmi les issues modifiant cette doc, #257 sorti). Aucun fichier `.py` modifié, aucune section renumérotée.

## 29 juillet 2026 — issue #272

Consignation dans `TACHES.md` de deux sujets diagnostiqués en conversation le 29/07/2026 (issue #272), qui auraient été perdus à la fermeture du fil sans cette entrée : tous deux relèvent du backlog (pistes à mûrir, aucun développement lancé). Ajoutées en tête du fichier, avant « Concurrence limitée aux issues mode_lecture », les entrées existantes n'ont pas été modifiées. **Entrée 1 — calibration automatique du TIMEOUT (§19), trois défauts** : (1) `_detecter_tag_reseau()` retourne toujours `None`, donc le facteur d'ambiance `F` (F_reseau/F_local) n'influence jamais la suggestion malgré la formule qui le prévoit ; (2) même corrigé, `maj_calibration_timeout` retomberait toujours sur `F_local` par défaut sans lire le tag — bug distinct du premier ; (3) la clé `projet|TYPE|mode` mélange des populations de durée incompatibles (une doc de 250s et une refonte avec tests de 1800s dans la même case), produisant des suggestions sans sens (observé : 2794s suggérés pour une issue ayant pris 351s). Piste retenue : séparer le coût de la TÂCHE (proxy : le TIMEOUT déclaré en en-tête, que Claude Chat estime déjà à la rédaction) de l'état de la MACHINE (latence réseau mesurée au démarrage, pour enfin alimenter `tag_reseau`), en conservant une composition en PRODUIT et non en somme. **Entrée 2 — archivage de `logs/historique_durees.json`** : 682 entrées, 112 Ko au 29/07/2026, jamais purgé depuis mai ; les 13 entrées `ff_galerie` (projet piloté par EmailJS, pas d'usage bridge réel) ne polluent aucun calcul mais brouillent la lecture manuelle. Point de vigilance impératif pour toute implémentation future : ne pas archiver naïvement par mois — l'EWMA de calibration a une demi-vie de 15 issues, une bascule mensuelle repartirait de zéro à chaque mois pour les projets les plus actifs. Aucune urgence à 112 Ko ; à traiter avant plusieurs Mo. `BRIDGE_AGENT_DOC.md` non modifié par cette issue (aucune section ne couvre `TACHES.md`), donc pied de page non glissé (condition de #10 non remplie).

## 29 juillet 2026 — issue #271

Résultats : nombre d'issues chargées par projet rendu configurable (issue #271), pour accélérer le bouton rafraîchir et réduire le volume rapatrié — jusqu'ici `issues_liste()` (`app/issues.py`) appelait `gh issue list --limit 30` en dur, **par projet** (jusqu'à 240 issues téléchargées avec 8 projets), alors que l'affichage était déjà plafonné par le quota adaptatif d'`appliquerFiltresListe()` (issue #136). **Backend** : `issues_liste()` accepte désormais un paramètre de requête optionnel `limite` (`_limite_issues_requete()`), entier borné entre 1 et 50 — toute valeur absente, non entière ou hors bornes retombe sur 30 (`LIMITE_ISSUES_DEFAUT`), comportement strictement inchangé pour tout appelant qui ne passe pas le paramètre (vérifié : `?limite=5`→5, `?limite=999`→50, `?limite=0`→1, `?limite=abc`→30, absent→30, via `test_client()` bout-en-bout contre `gh` réel). **Frontend** (`static/js/app.js`, `static/css/style.css`) : champ numérique `#limite-issues-projet` ajouté dans la ligne de filtres, juste avant le bouton rafraîchir, `title` explicite (« Nombre d'issues chargées par projet (pas un total). Ex. 5 → 5 issues par projet affiché. ») pour éviter la confusion nombre-par-projet / total — un total obligerait à diviser par le nombre de projets actifs, qui change à chaque clic sur un filtre. Persisté dans `localStorage` (`bridge_limite_issues_projet`), défaut **5** (besoin réel dans 70% des cas d'après l'issue, et non 30 : l'ancienne valeur reste atteignable en remontant le champ). `chargerListeIssues()` transmet la valeur courante (`limiteIssuesProjet()`) à chaque appel `/issues-liste/<projet>`. Changer la valeur du champ ne déclenche **aucun** rechargement automatique (cohérent avec la décision de #270) : seul le bouton rafraîchir applique la nouvelle limite ; en revanche `changerLimiteIssuesProjet()` invalide immédiatement `CLE_CACHE_ISSUES`, sans quoi un cache constitué à l'ancienne limite continuerait d'afficher une profondeur d'historique incohérente avec le réglage visible. Quota adaptatif de #136 (`appliquerFiltresListe()`) **non touché** : les deux mécanismes sont complémentaires (celui-ci plafonne ce qui est TÉLÉCHARGÉ, celui-là ce qui est MONTRÉ) ; commentaire ajouté pour expliciter que si la limite de téléchargement est plus basse que le quota d'affichage, ce dernier n'a simplement rien de plus à masquer — sans conséquence. **Mesure du coût GraphQL** (méthode #263 : deux `gh api rate_limit` encadrant un appel isolé de `gh issue list --json ...`, 3 répétitions, delta minimal retenu) sur `--limit 30/10/5` : les trois deltas minimaux mesurés valent **1 point** (identique au coût unitaire déjà mesuré par #263 pour cet appel) — résultat inattendu : le coût GraphQL par appel ne varie PAS avec `--limit` dans la plage testée, contrairement à l'intuition de l'issue ; le gain réel n'est donc pas une réduction du quota GraphQL (le nombre d'appels — un par projet — reste le facteur dominant, inchangé par cette issue) mais une réduction du volume de données transférées/parsées (23 113 → 3 445 octets entre `--limit 30` et `--limit 5` sur ce dépôt, soit -85%), donc du temps de traitement `gh`/JS et du risque de timeout sur un historique profond. Détail complet et tableau des mesures dans le rapport de clôture de l'issue #271 (non dupliqué ici). Route `/issues-liste/<projet>` non documentée dans `BRIDGE_AGENT_DOC.md` (aucune section ne la décrit) : aucune mise à jour de ce fichier, pied de page non glissé (condition de #10 non remplie — cette issue ne modifie pas `BRIDGE_AGENT_DOC.md`).

## 29 juillet 2026 — issue #270

Badges de temps restant : suppression du rafraîchissement périodique (issue #270, remplace #269 fermée sans correctif — mesure infaisable dans le TIMEOUT, décisions non tranchées). `intervalFetchTiming` (re-fetch de `/issues-en-attente/<projet>` toutes les 15s pour tous les projets configurés, ~3840 pts/h mesurés par #263, premier poste de consommation du quota GraphQL) supprimé ; `intervalTempsRestant` conservé (décompte purement client, recalcul chaque seconde, sans coût réseau). `chargerTimingIssues()` n'est plus appelée qu'au chargement initial de l'onglet Résultats et depuis `rafraichirResultats()` (bouton rafraîchir), pour qu'un seul geste mette à jour liste ET badges. Décision sur le décompte (point 3 de #269, laissé en suspens) : une fois le budget total épuisé, le badge se fige à « ⌛ 0s — budget épuisé » au lieu d'un compteur de dépassement qui grossissait indéfiniment (`⌛ dépassement +Xs`) — jamais de valeur négative, jamais de message spéculatif du type « terminé ? » (l'état réel n'est pas connu sans re-fetch), badge visible jusqu'au prochain rafraîchissement manuel. Retrait de deux résidus d'une tentative précédente non commitée proprement : un `console.error('[DEBUG-269-TRACE]', …)` dans `chargerTimingIssues()` et un bloc `<script>` de harnais temporaire dans `templates/index.html` (auto-bascule vers l'onglet Résultats après 800ms) qui portait lui-même la mention « à retirer avant commit ». Second appelant de `/issues-en-attente` (~ligne 2735, garde-fou avant l'envoi d'une nouvelle issue) : hors périmètre de cette issue, laissé strictement tel quel. Aucune mesure de gain (hors périmètre, cf. #269 : nécessite un navigateur ouvert 5+ minutes, invérifiable depuis l'agent) — à faire par Alain avec `scripts/mesurer_api.py`.

## 29 juillet 2026 — issue #268

Corrige la corruption du § 10 provoquée par #263 (issue #268) : l'entrée de #263, destinée au vrai pied de page (dernière ligne du fichier), avait été insérée à la place du `<date> — ...` du modèle explicatif du §10 — remplacement effectué sur la première occurrence de « Dernière mise à jour » dans le fichier, qui est cet exemple, pas le pied de page situé bien plus bas. Deux dégâts cumulés : le §10 affichait un modèle cassé (phrase du point 2 disloquée par le texte de #263 inséré en son milieu) et le vrai pied de page n'avait PAS reçu l'entrée de #263 — il avait seulement perdu #252, passant de trois entrées (#257, #253, #252) à deux (#257, #253), contredisant le rapport de clôture de #263 qui affirmait à tort « Footer glissé (#263 en tête, #257 et #253 conservées, #252 sorti) ». **Correctifs** : (1) §10 restauré au mot près dans son état d'origine (`*Dernière mise à jour : <date> — ...*`) ; (2) pied de page reconstruit avec l'entrée #263 en tête suivie de #257 et #253 (les trois entrées les plus récentes parmi les issues modifiant cette doc), puis complété dans la même opération par cette propre entrée #268, faisant sortir #253 ; (3) garde-fou ajouté au §10 (nouveau point 3) : le format n'apparaît qu'à la toute dernière ligne du fichier, une recherche sur « Dernière mise à jour » remontant d'abord l'exemple du §10 — toujours viser la fin du fichier, jamais la première occurrence. **Test (point 4)** : regex de `nouveau_projet.py` (`(\*Dernière mise à jour : )[^—]*( —)`) rejouée réellement (`re.sub`) contre la première ligne du pied de page corrigé — match confirmé, substitution de la date vérifiée avec succès. Aucun fichier `.py` modifié, aucune section renumérotée.

## 28 juillet 2026 — issue #263

Mesure et attribution de la consommation du quota GraphQL GitHub (issue #263, suite à l'épuisement complet du 28/07 vers 3h — 5000/5000, `remaining: 0`) — aucun correctif, mesure seule. Ajout de `scripts/mesurer_api.py` : échantillonne `gh api rate_limit` (REST, **gratuit** — vérifié empiriquement par une rafale de 40 appels sans effet sur `graphql.used`) à intervalle réglable et journalise dans `logs/mesure_api.csv` (déjà gitignoré via la règle `logs/`), arrêtable par Ctrl+C sans perte. **Coûts unitaires mesurés** (delta minimal sur 2-5 répétitions, pour s'affranchir du bruit de fond) : `gh issue list --json ...` (l'appel du polling) = 1 point, `gh issue view --json comments` = 2, `gh issue comment` = 2, `gh issue edit --add-label` = 3, `gh issue close` = 2 (plancher, variance 2-4). **Résultat principal, inattendu** : sur la fenêtre mesurée (baseline ≈ 4045 points/heure, 1 seul watcher CCL actif), la première cause identifiée n'est ni la boucle CCW, ni le délai d'inactivité de 20 min, ni le polling à 10s des watchers (chacun ≈ 360 points/heure, confirmé par calcul coût-unitaire × fréquence) — c'est **l'interface web laissée ouverte dans un navigateur** : `/issues-en-attente/<projet>` interroge deux fois (labels for-linux ET for-windows) CHAQUE projet configuré toutes les ~15s pour rafraîchir les badges du sélecteur, soit environ 3840 points/heure à elle seule avec les 8 projets actuels — avant même qu'un watcher ou le poller de notifications (`app/notifications_poller.py`, ≈ 960 points/heure pour 8 projets) n'entre en jeu. Protocole en phases A-D adapté : la phase « tout arrêté » n'a pas pu être mesurée en conditions réelles (le watcher CCL traitant cette issue de mesure, et `new_issue.py` dont il dépend, ne peuvent pas être arrêtés depuis CCL sans interrompre l'exécution en cours — même limite que le watcher CCW, inaccessible depuis le ThinkPad) ; contournement par deux watchers de test supplémentaires (`rummikub`, `scrabble`, `--dry-run`, 0 issue en attente donc aucun risque d'exécution réelle) pour isoler la contribution marginale d'un watcher au repos. §13 de `BRIDGE_AGENT_DOC.md` complété avec la méthode reproductible ; pied de page glissé (issue #257 et #253 conservées, #252 sorti — déjà dans ce fichier). Classement des leviers correctifs et chiffres complets : rapport détaillé posté en commentaire de clôture de l'issue #263 (non dupliqué ici) — aucun changement de comportement du bridge n'a été apporté, les correctifs éventuels feront l'objet d'issues séparées.

## 28 juillet 2026 — issue #262

Transforme le bouton « Tous » de l'onglet Résultats en véritable interrupteur à deux états, après que #259 a établi que le comportement inconditionnel qu'il évoluait n'était pas un bug : le besoin réel est un basculement rapide entre « tout afficher » et « tout masquer », le bouton « Tous » et la case de marquage étant les deux gestes les plus fréquents de cet onglet (le détail d'une issue y est presque jamais consulté, cf. #261).

**Nouvelle fonction** : `reactiverTousLesFiltres()` renommée `basculerTousLesFiltres()` (`static/js/app.js`), commentaire d'en-tête réécrit pour décrire le toggle plutôt que la remise à zéro inconditionnelle. Règle : `noms.every(nom => projetsFiltresActifs.has(nom))` vrai (tout affiché) → passe à l'ensemble vide (tout masqué) ; faux (état partiel OU tout masqué) → passe à l'ensemble complet (tout affiché). Un seul état bascule vers « tout masqué », tout le reste revient à « tout affiché », conformément à l'énoncé.

**Garde-fou de #259** : supprimé purement et simplement (`if (!noms.length) return;`), sans réécriture ni remplacement — l'ensemble vide qu'il interdisait est désormais l'état « tout masqué », volontaire et légitime, exactement ce que la fonction doit pouvoir produire. Le garder aurait bloqué le nouveau comportement dans le cas `noms` vide (aucun projet configuré), un cas de toute façon sans conséquence réelle (aucun bouton projet à masquer).

**Persistance `localStorage`** (`CLE_FILTRES_RESULTATS`) : asymétrique, à dessein. Vers « tout affiché » → `localStorage.removeItem(...)`, comme avant #262 (retour au défaut — tout actif — au prochain chargement). Vers « tout masqué » → `sauvegarderFiltresProjets(noms)`, la même fonction qu'utilise déjà `basculerFiltreProjet()`, qui écrit `{nom: false, ...}` pour chaque projet : sans cette persistance explicite, un rechargement de page aurait silencieusement annulé le masquage volontaire (retour à tout affiché par défaut, cf. `restaurerFiltresProjets()`).

**État visible sur le bouton** : `majClassesBoutonsFiltre()` (qui ne traitait jusqu'ici que les boutons `[data-projet]`) traite désormais aussi `.filtre-projet.tous` — classe `inactif` (grisée, CSS déjà existante) et `title` reflétant l'action du **prochain** clic (« Tout masquer » quand tout est affiché, « Tout afficher » sinon), pas l'état courant. Effet de bord nécessaire : dans `construireBoutonsFiltre()`, l'appel à `majClassesBoutonsFiltre()` se faisait juste après la boucle des boutons projet, donc **avant** la création du bouton « Tous » — déplacé après sa création (juste avant le bouton rafraîchir), sinon la mise à jour de son état visuel n'aurait rien trouvé dans le DOM à la construction initiale ni après reconstruction de la ligne de filtres.

**Point 5 (cas limite tout masqué)** : `appliquerFiltresListe()` masque bien toutes les lignes (`projetVisible` faux pour tout projet quand l'ensemble est vide), `selectionnerPremiereVisible()` ne trouve aucune ligne visible et affiche proprement « Aucune issue à afficher », sans erreur. Défaut trouvé en vérifiant ce chemin : la ligne précédemment sélectionnée gardait sa classe `.selectionnee` (invisible mais toujours marquée) même masquée — au retour à « tout afficher », cette ligne redevenait visible et le code de resynchronisation (`if (!sel || sel.style.display === 'none')`), la trouvant déjà « sélectionnée » et visible, sautait la resélection : la zone de détail restait bloquée sur le message « Aucune issue à afficher » malgré une ligne visiblement en surbrillance. Ce chemin était déjà latent via `basculerFiltreProjet()` (désactiver le dernier projet actif un par un y menait aussi) mais quasi inatteignable en pratique ; le nouveau toggle le rend trivial (un clic). Corrigé dans `selectionnerPremiereVisible()` : la branche « aucune ligne visible » retire désormais aussi la classe `.selectionnee` de toute ligne qui la porterait encore et réinitialise `projetCourant`/`numeroCourant` (miroir du comportement déjà présent dans `selectionnerLigne()` pour son propre cas « aucune issue »). Effet : au retour à « tout afficher », plus aucune ligne ne porte `.selectionnee`, la resynchronisation se déclenche normalement et sélectionne proprement la première ligne visible.

**Point 6 (rechargement / reconstruction)** : vérifié par lecture du chemin d'appel — `appliquerListeIssues()` recalcule toujours `projetsFiltresActifs = restaurerFiltresProjets(noms)` avant `construireBoutonsFiltre(noms)`, aussi bien au chargement initial qu'à toute reconstruction (ajout de projet). Après un masquage total persisté, un rechargement restaure bien un ensemble vide (chaque projet marqué `false` dans l'état sauvegardé) : le bouton affiche correctement l'état « inactif »/« Tout afficher » dès la construction, premier clic correct. Ajout d'un nouveau projet pendant un masquage total : ce projet, absent de l'état `localStorage` sauvegardé, est actif par défaut (`etat[nom] !== false` vrai pour une clé absente) — l'ensemble devient donc partiel plutôt que resté totalement vide ; le bouton reflète alors correctement « Tout afficher » (état partiel), et un premier clic affiche bien tout, conformément à la règle générale (tout état partiel bascule vers tout affiché).

**Vérification** : `node --check static/js/app.js` → OK. Vérifications des points 5 et 6 faites par relecture attentive du chemin d'exécution réel du fichier (accès à un bac à sable DOM complet non disponible dans cette session — le fichier charge de nombreux `document.getElementById(...).addEventListener` en haut niveau, un stub minimal aurait été trompeur) ; le raisonnement s'appuie sur le code effectivement livré, ligne par ligne, pas sur une hypothèse.

## 28 juillet 2026 — issue #261

Dans l'onglet Résultats, `afficherIssue()` (`static/js/app.js`) lançait un `fetch('/issue/<projet>/<numero>')` systématique — y compris pour un clic simple réflexe (sélectionner une ligne sans vouloir lire son détail) et pour la sélection automatique (`selectionnerPremiereVisible()`, déclenchée à l'ouverture de l'onglet, à chaque changement de filtre projet, après « Tous » et après chaque rafraîchissement de liste). Le TTL du cache `localStorage` (issue #52) ne dispensait que l'affichage immédiat : le fetch d'arrière-plan partait quand même. Dans l'usage réel, ce détail n'est presque jamais consulté ; chaque clic réflexe et chaque changement de filtre coûtaient donc un aller-retour GitHub inutile — autant d'occasions d'erreur/lenteur sur un réseau instable (issue #261).

**Solution retenue** : séparation stricte sélection / chargement. Nouvelle `selectionnerLigne(nom, numero)` — met en évidence la ligne (classe `.selectionnee`), mémorise `projetCourant`/`numeroCourant`, affiche un état neutre (« Double-cliquez une issue pour afficher son détail. ») dans `#zone-issue`, **sans fetch**. `afficherIssue()` (comportement de fetch/cache inchangé) délègue désormais la partie sélection à `selectionnerLigne()` et ne s'en distingue plus que par le chargement effectif. `selectionnerPremiereVisible()` appelle `selectionnerLigne()` au lieu de `afficherIssue()` : la sélection automatique ne charge donc plus rien. Sur chaque ligne, `onclick` (clic simple) appelle `selectionnerLigne()` ; un nouveau `ondblclick` appelle `afficherIssue()` — seul geste, avec le Ctrl+clic (identique à avant, demande explicite de détail + défilement vers le résultat CCL), qui charge encore. `title="Double-cliquez pour afficher le détail de cette issue"` posé sur chaque ligne pour rendre le geste découvrable (point 6).

**Bouton rafraîchir (issue #56, point 4)** : `rafraichirResultats()` mémorisait `projetCourant`/`numeroCourant` avant rechargement pour rouvrir l'issue affichée — mais ces variables sont désormais renseignées même par une simple sélection, jamais chargée. Nouveau drapeau `detailCourantCharge` (true uniquement après un chargement réel via `afficherIssue()`, remis à `false` par `selectionnerLigne()`) : `rafraichirResultats()` ne recharge le détail après rafraîchissement que si `detailCourantCharge` valait `true` juste avant — sinon, aucune issue n'ayant été explicitement ouverte, rien n'est chargé de force.

**Non modifié** : la checkbox de marquage, les badges « ✅ »/« Diff »/« All » (fetch à la demande explicite, inchangés), le filtrage par projet, `annulerIssue()`/`fermerIssue()` (leurs boutons ne sont rendus que dans une issue déjà explicitement chargée — rappeler le détail après leur action reste la continuation directe d'un geste explicite, pas un chargement réflexe). Aucune sélection au clavier n'existe dans ce fichier pour la liste des issues (point 7 : rien à adapter).

**Vérification** : `node --check static/js/app.js` → OK. Comportement rejoué dans un bac à sable Node (`vm`, mêmes stubs DOM/localStorage/fetch que pour #259) chargeant le fichier réel tel quel : sélection automatique et clic simple → zéro appel `fetch('/issue/...')` ; double-clic → exactement un appel ; `rafraichirResultats()` après une simple sélection → zéro appel ; après un double-clic préalable → un appel. Script de vérification non persisté (ad hoc, comme pour #259).

## 28 juillet 2026 — issue #260

Corrige la façon dont `initialiser_git()` (`nouveau_projet.py`) détecte le contenu préexistant d'un `REP_TRAVAIL` non versionné, en la faisant porter sur ce que git suivrait réellement plutôt que sur le contenu brut du disque (issue #260, suite #258). **Défaut** : `_fichiers_preexistants()` (livrée par #258) listait le répertoire via `rglob("*")` **avant** toute écriture — choix délibéré pour que le futur `.gitignore` ne fausse pas le constat — mais comptait de ce fait aussi tout ce que ce même `.gitignore` exclurait. Le cas typique d'un `REP_TRAVAIL` préexistant est un projet Python déjà commencé, contenant donc un `venv/` et des `__pycache__/` : le scan remontait alors potentiellement des milliers d'entrées, le compte-rendu annonçait un nombre de « fichiers préexistants » sans rapport avec la réalité, et le push était retenu pour des fichiers qui n'auraient de toute façon jamais été committés — un garde-fou qui se déclenche presque systématiquement pour de mauvaises raisons finit par être ignoré, ce qui annule le bénéfice recherché par #258. Point mineur de même famille : `rglob("*")` parcourait l'arborescence entière sans borne, au sein d'une requête Flask, alors que #258 venait précisément de poser des timeouts sur les appels git pour cette raison — un `venv/` volumineux aurait pu rendre la création anormalement lente.

**Solution retenue** : réordonnancement de `initialiser_git()` — `git init`, `remote add`, écriture du `.gitignore` minimal (comportement inchangé), PUIS `git add -A`, PUIS détection sur l'index réel (`git diff --cached --name-only`), PUIS commit. Nouvelle `_fichiers_suivis_preexistants(rep_path, git_runner)` remplace `_fichiers_preexistants()` (supprimée, aucune coexistence des deux mécanismes) : liste les fichiers indexés par `git add -A`, exclut ceux que le script crée lui-même (`CONTEXTE.md`, fichiers Specs, `.gitignore` — `FICHIERS_CREES_PAR_SCRIPT`, inchangée), triés, chemins relatifs. Un `venv/`/`__pycache__/` exclu par le `.gitignore` minimal n'atteint jamais l'index et ne compte donc plus comme contenu préexistant. Sémantique de sortie strictement conservée : `contenu_preexistant` (liste triée), `push_ok=None` en cas de retenue volontaire (distinct de `False` = échec réel), `commande_manuelle`, `detail` expliquant le pourquoi — seule la manière de constituer la liste change. `_fichiers_suivis_preexistants()` réutilise le `_git()` local de l'appelant (déjà borné par `TIMEOUT_GIT_LOCAL` et tolérant au dépassement) pour le `git diff --cached` : pas de second mécanisme de timeout à maintenir.

**Test** (`tests/test_init_git_local_258.py`) : scénario « contenu préexistant » (#258) inchangé, continue de passer. Nouveau scénario `scenario_venv_ignore_par_gitignore_pas_de_retenue` : répertoire non versionné contenant un `venv/lib/module.py` et un `__pycache__/module.cpython-311.pyc`, aucun fichier réellement suivi → `contenu_preexistant` vide et push tenté normalement (`push_ok:false`, dépôt distant inexistant — pas `None`). Vérifié comme échouant sur le code d'avant correction (`git stash` du seul `nouveau_projet.py`, test relancé : `venv/lib/module.py` et `__pycache__/module.cpython-311.pyc` remontaient tous les deux) puis passant sur le code corrigé. Les 4 autres scénarios de ce fichier ainsi que `test_nettoyage_arbre_247.py`, `test_auto_extinction_217.py`, `test_verification_commentaire_237.py` repassés sans régression.

**Doc** : §13 étape 5 reformulé — le garde-fou porte désormais explicitement sur les fichiers que git suivrait après `git add -A`, pas sur un inventaire brut du répertoire.

## 28 juillet 2026 — issue #259

Ajoute un garde-fou d'idempotence à `reactiverTousLesFiltres()` (bouton « Tous » de l'onglet Résultats, `static/js/app.js`), suite à un signalement de second clic masquant tous les projets (issue #259). **Diagnostic** : la piste envisagée (`nomsProjetsDisponibles()` retournant vide au second appel, faisant écrire un `Set` vide) ne s'est pas confirmée. `nomsProjetsDisponibles()` lit `[...document.getElementById('projet').options]` — le `<select>` global, peuplé une seule fois côté serveur par `lister_projets()` et jamais vidé/reconstruit côté client (seul `ajouterProjetAuSelecteur()` y ajoute une option, sans jamais en retirer) ; il est donc déjà indépendant de l'état d'affichage/filtre de l'onglet Résultats — `appliquerFiltresListe()` ne fait que masquer des LIGNES d'issues (`ligne.style.display`), jamais les options du select, et `localStorage.removeItem` ne touche pas non plus le DOM. Vérifié par exécution directe du fichier réel (`static/js/app.js` chargé tel quel dans un bac à sable `vm` Node, sans modification) : deux appels consécutifs à `reactiverTousLesFiltres()`, partant d'un état partiellement ou totalement désactivé, produisent chacun l'ensemble complet des projets — aucune régression vers un `Set` vide observée sur ce chemin. Seuls trois points du fichier réaffectent `projetsFiltresActifs` (déclaration initiale, `appliquerListeIssues()` via `restaurerFiltresProjets()`, et `reactiverTousLesFiltres()`) ; les deux derniers ont été rejoués sous test sans reproduire le symptôme. Le symptôme décrit (plus aucune issue affichée, récupérable seulement en recliquant chaque projet un par un) correspond en revanche exactement au comportement déjà connu et documenté de `basculerFiltreProjet()` lorsqu'on désactive le dernier projet actif restant (vérifié : le `Set` devient bien vide dans ce cas précis) — plausiblement la manipulation réellement en cause, plutôt qu'un second clic sur « Tous ».

**Solution retenue** : aucune correction de source nécessaire pour `nomsProjetsDisponibles()`, déjà appuyée sur une source stable. Garde-fou ajouté en second rideau dans `reactiverTousLesFiltres()` : si `nomsProjetsDisponibles()` retourne une liste vide (cas normalement inatteignable dans l'onglet Résultats, `chargerListeIssues()` court-circuitant déjà l'absence de projet), la fonction retourne immédiatement sans toucher à `projetsFiltresActifs` — état laissé inchangé plutôt que vidé. Vérifié par test direct (select vidé artificiellement) : l'état actif reste intact après le clic.

**Non modifié, signalé seulement (point 4)** : `basculerFiltreProjet()` désactivant le dernier projet actif produit bien un `Set` vide et un affichage sans aucune issue — confirmé par test. Comportement volontairement laissé tel quel : désactiver explicitement tous les projets un par un est une action délibérée de l'utilisateur, à la différence d'un second clic sur « Tous ».

**Vérifications (point 5)**, par exécution directe du fichier réel dans un bac à sable Node (`vm`) : **rechargement de page** — filtres partiellement désactivés puis persistés en `localStorage`, `appliquerListeIssues()` (chemin de chargement) restaure correctement l'état partiel, puis deux clics consécutifs sur « Tous » réactivent et maintiennent l'ensemble complet ; **reconstruction de la ligne de filtres** — ajout d'un projet au `<select>` puis `appliquerListeIssues()`/`construireBoutonsFiltre()` reconstruits, `nomsProjetsDisponibles()` inclut bien le nouveau projet, deux clics consécutifs sur « Tous » restent corrects et incluent le projet ajouté. `node --check static/js/app.js` → OK.

## 28 juillet 2026 — issue #258

Corrige deux défauts de `initialiser_git()` livrée par #257 : publication involontaire d'un répertoire préexistant, et absence de timeout sur les appels git (issue #258). **Défaut 1** : `creer_depot()` crée le dépôt GitHub en `--public`, et `initialiser_git()` fait `git add -A` puis pousse automatiquement — sans risque sur un répertoire neuf (cas nominal), mais si `REP_TRAVAIL` désigne un dossier **existant et non versionné** (cas explicitement couvert par le script, qui gère « création ET installation »), l'intégralité de son contenu était publiée sans confirmation ni aperçu ; le `.gitignore` minimal (`venv/`, `__pycache__/`, `*.pyc`, `*.log`, `.env`) ne protège que quelques cas. **Défaut 2** : `_git()` appelait `subprocess.run` sans `timeout=`, alors que le reste du code en pose un partout ailleurs (30s pour `commenter_issue`, 120s pour le push des pièces jointes) — un `git push` qui pend sur un réseau instable bloquait la requête Flask indéfiniment.

**Solution retenue — timeouts (point 1)** : `_git()` accepte désormais un `timeout` par appel, `TIMEOUT_GIT_LOCAL = 15` (secondes) pour `init`/`remote`/`add`/`commit`, `TIMEOUT_GIT_PUSH = 60` pour le push — seul appel réseau du lot, cohérent avec les timeouts déjà en place ailleurs. `subprocess.TimeoutExpired` est capturé et transformé en un `CompletedProcess` factice (`returncode=124`, `stderr` explicite) : le reste de la logique (qui ne fait déjà que tester `returncode != 0`) traite un timeout exactement comme un échec réseau ordinaire, sans exception qui remonterait et sans faire échouer la création — `commande_manuelle` renvoyée comme pour tout échec de push.

**Solution retenue — contenu préexistant (points 2/3)** : nouvelle `_fichiers_preexistants(rep_path)`, appelée AVANT toute écriture (avant que le futur `.gitignore` ne fausse le constat) : liste les fichiers du répertoire autres que ceux que le script crée lui-même (`CONTEXTE.md`, les 3 fichiers Specs MVC, `.gitignore` — constante `FICHIERS_CREES_PAR_SCRIPT`). Répertoire vide ou ne contenant que ces fichiers → comportement inchangé (init + commit + push automatiques). Contenu préexistant détecté → `git init`/remote/`.gitignore`/commit exécutés normalement, mais **le push n'est PAS déclenché** : `push_ok` reste `None` (distinct de `False`, qui signale un échec réel), nouveau champ `contenu_preexistant` (liste triée des chemins relatifs) renvoyé par `initialiser_git()` et propagé par `creer_projet()` (`git_contenu_preexistant`), `commande_manuelle` fournissant le `git push -u origin master` à lancer après relecture, et le `detail` explicitant pourquoi (dépôt public, contenu non relu) — pas un échec, une retenue volontaire.

**CLI** (`etape_git()`, résumé final de `main()`) : affiche la liste des fichiers préexistants détectés, tronquée à une dizaine (« … et N autre(s). »), et le message « push NON déclenché » distinct du message d'échec de push.

**Web** (`static/js/app.js`) : `afficherRappelProjet()` distingue désormais trois branches (déjà-git / poussé / **retenu volontairement** — contenu préexistant, avec la liste tronquée et l'explication « ce n'est pas un échec » — / échec de push), au lieu de fusionner la retenue volontaire avec l'échec de push comme le ferait un simple `else`.

**Doc** : §13 étape 5 réécrite en deux temps (push automatique si répertoire réellement vide ; garde-fou supplémentaire sinon) et complétée des deux timeouts. §18.2 : le paragraphe sur la seconde exception (#257) précisé — le raisonnement d'origine (« le dépôt distant vient d'être créé, rien à emporter ») est exact mais ne couvrait que le dépôt distant, pas le contenu local préexistant ; l'exception ne s'applique donc en pratique qu'aux répertoires réellement vides.

**Test** : nouveau `tests/test_init_git_local_258.py` (persisté — le test de #257 avait été fait sur des répertoires `/tmp` jetables puis supprimés, rien n'était resté sous `tests/`), quatre scénarios : répertoire neuf vide (comportement #257 inchangé, push tenté et échoue proprement sur un dépôt distant inexistant) ; déjà-git (strictement inchangé) ; contenu préexistant (issue #258 — `CONTEXTE.md` déjà présent n'est PAS compté, un fichier tiers l'est, aucun appel `git push` n'est tenté — vérifié en espionnant `subprocess.run` — et la commande manuelle est renvoyée) ; timeout de push (faux `git` en tête de `PATH` qui dort 2s sur `push` avec `TIMEOUT_GIT_PUSH` temporairement réduit à 0.3s — la création aboutit quand même, `push_ok:false`, pas d'exception). `python3 tests/test_init_git_local_258.py` → ✅ (4/4). Suites existantes repassées sans régression : `test_nettoyage_arbre_247.py`, `test_auto_extinction_217.py`, `test_verification_commentaire_237.py` → ✅. Aucune section renumérotée.

## 28 juillet 2026 — issue #257

Ajoute l'initialisation git du répertoire de travail à la création de projet, sans quoi le projet créé était inutilisable (issue #257). Contexte : `creer_projet()` (CLI et route Flask) créait le dépôt GitHub distant, le `.conf`, les labels, le répertoire de travail, `CONTEXTE.md` et mettait à jour la doc — mais ne faisait jamais `git init`/`git remote add` : aucun appel à `git` dans les 784 lignes du script, seule commande externe `gh`. Sur un projet réellement neuf (REP_TRAVAIL non versionné), `git pull --ff-only` en début de cycle du watcher échoue, et le commit de sauvegarde obligatoire avant toute modification en mode écriture ne peut pas s'exécuter — toute issue `mode_write` part en erreur. Cause probable : le script avait été écrit pour installer des dépôts déjà clonés de longue date, pas pour en créer de zéro ; le cas « projet neuf » n'avait jamais été parcouru jusqu'au bout avant `rummikub` (27 juillet 2026), initialisé à la main. **Aggravation** : après une création réussie, l'encart web `afficherRappelGit()` (`static/js/app.js`) affichait « ⚠ Action requise — pousser la doc sur GitHub » avec 3 commandes portant sur le dépôt **Bridge_Agent** (pousser `BRIDGE_AGENT_DOC.md`) — un encart « action requise » plein de commandes git juste après la création laissait croire à tort que rien d'autre n'était à faire, alors que deux étapes manquaient (init git + rédaction de `CONTEXTE.md`), non mentionnées nulle part.

**Solution retenue** : nouvelle étape « Dépôt git local » dans `creer_projet()` (`nouveau_projet.py`), entre « Fichiers contexte » et « Documentation », couvrant les deux cas : **déjà un dépôt git** (installation sur un projet existant, le cas de tous les projets actuels) → rien n'est fait, signalé « déjà un dépôt git — inchangé » ; **répertoire non versionné** (projet réellement neuf) → `git init -b master`, `git remote add origin` en **HTTPS** (`https://github.com/<owner>/<repo>.git`, jamais SSH — toute l'installation `gh` est en HTTPS), `.gitignore` minimal s'il est absent, commit initial, puis **push**. Nouvelle fonction `initialiser_git(rep, depot)`, réutilisée telle quelle par le CLI (`etape_git()`, avec confirmation comme les autres étapes, titre renuméroté « 8. » — Specs MVC en 7, doc en 9, résumé en 10) et par la route Flask (`creer_projet()`, sans confirmation individuelle, cohérent avec les autres étapes du flux web).

**Exception documentée à la règle « CCL/le script ne pousse jamais »** (issue #257, point 2) : ce push initial est déclenché par la création de projet elle-même, toujours à l'initiative d'Alain (terminal ou bouton web), jamais par un agent — même raisonnement que la route pièces jointes (§18.2, où une seconde exception du même type est désormais documentée explicitement). Un échec du push (réseau, droits) **ne fait pas échouer la création** : le commit reste local, `ok:true` mais `push_ok:false`, et une commande manuelle (`git push -u origin master`, ou la séquence complète si `git init` lui-même a échoué) est renvoyée dans `git_commande_manuelle` — affichée dans le récapitulatif CLI et dans un nouvel encart web dédié.

**Web** (`static/js/app.js`, `templates/index.html`, `static/css/style.css`) : nouvel encart `afficherRappelProjet()` (`#np-rappel-projet`, bordure bleue), **visuellement distinct** de l'encart existant `afficherRappelGit()` (bordure orange, dépôt Bridge_Agent uniquement, dont le titre est reformulé pour préciser « dépôt Bridge_Agent ») — c'est précisément la confusion entre les deux dépôts qui avait fait passer le problème inaperçu. Le nouvel encart rappelle systématiquement que `CONTEXTE.md` est créé **VIDE** (injecté dans chaque prompt CCL, plafonné à 4000 caractères) et affiche, le cas échéant, la commande git manuelle restante.

**Doc** : §13 « Commandes utiles » réécrit — décrivait auparavant seulement la commande de lancement sans aucune étape suivante ; détaille maintenant les 6 étapes réelles de bout en bout (dépôt GitHub, `.conf`, labels, contexte, **dépôt git local**, doc Bridge_Agent) et ce qui reste manuel dans tous les cas. §18.2 complété d'un paragraphe documentant cette seconde exception à la règle de push. Docstring d'en-tête de `nouveau_projet.py` mise à jour (« Zéro dépendance externe (stdlib + `gh`) » ne tenait plus, `git` est désormais requis pour le cas dépôt neuf).

**Test (point 6)** : sur des répertoires jetables sous `/tmp` (jamais de vrai dépôt GitHub créé, `depot_existe`/`creer_labels` court-circuités) : cas répertoire neuf → dépôt bien initialisé (`.git` présent, branche `master`, remote `origin` HTTPS correct, un commit), push échoue proprement (dépôt distant inexistant) sans faire échouer `creer_projet()` (`succes:true`), `git_commande_manuelle` renvoyée ; cas déjà-git → fichier préexistant intact, aucun remote ajouté, comportement strictement inchangé. Répertoires de test supprimés après vérification. Aucune section renumérotée.

## 27 juillet 2026 — issue #253

Étend la convention `CHANGELOG.md` à toute issue qui modifie le dépôt, pas seulement celles qui touchent la doc, et rattrape l'entrée manquante de #250 (issue #253, suite #252). Contexte : le texte introduit par #252 limitait l'obligation d'ajouter une entrée aux « issue[s] qui modifi[ent] cette doc » — restriction reconduisant, sous une autre forme, le trou que #240 avait dû combler à la main (issues #237/#238/#239, du code sans modification de doc, restées sans trace plusieurs jours) ; premier cas depuis #252 : #250 (correctif de contraste CSS pur, `static/css/style.css`) n'avait d'entrée ni dans `CHANGELOG.md` ni dans le pied de page, seulement dans l'historique git. **§10** reformulé : l'obligation d'ajouter une entrée en tête de `CHANGELOG.md` porte désormais sur **toute issue qui modifie le dépôt** (code, CSS, consignes, tests, documentation, quel que soit le fichier touché) ; le pied de page de cette doc reste, lui, réservé aux **trois entrées les plus récentes parmi les seules issues qui modifient cette doc elle-même** — comportement inchangé, une issue purement CSS comme #250 n'y figure donc pas. **Entrée rétroactive de #250** ajoutée dans `CHANGELOG.md`, à sa place chronologique (entre #252 et #251) : trois atténuations cumulées sur `.filtre-projet.inactif` (`opacity:.4` + fond `#f2f2f0` + texte `#999`) rendaient le nom des projets désélectionnés illisible (contraste `#999` sur `#f2f2f0` : 2,54:1, sous le seuil WCAG AA de 4,5:1, avant même l'effet de l'opacity) ; `opacity` globale supprimée — elle délavait aussi la pastille de couleur et l'emoji du bouton Ouvriers, pas seulement le texte — ne restent que fond et texte, `#5a5a5a` sur `#f2f2f0`, ratio 6,15:1. **Vérification des écarts (point 3)** : comparaison des numéros d'issue présents dans `CHANGELOG.md` à la liste des issues `done` fermées depuis #240 (13 issues, #240 à #252) — seules #241, #242 et #246 sont également absentes du changelog, mais légitimement : trois relances de build Windows Scrabble, `PROJET=bridge_agent` uniquement par la convention d'exception #233 pour les issues `for-windows`, ne modifiant aucun fichier du dépôt Bridge_Agent lui-même (build exécuté dans un partage CCW distinct) — hors du périmètre de la nouvelle règle, pas un oubli. Aucun autre écart trouvé. Aucune section renumérotée, aucun fichier `.py` modifié.

## 27 juillet 2026 — issue #252

Extrait l'historique du pied de page de `BRIDGE_AGENT_DOC.md` vers un `CHANGELOG.md` dédié (issue #252). Contexte : le pied de page (paragraphe « Dernière mise à jour : ... ») avait fini par contenir l'intégralité de l'historique du projet depuis l'issue #96, chaîné par 34 occurrences du connecteur « Précédemment » (suivi d'un tiret cadratin), soit 55523 caractères sur une seule ligne logique — coût de lecture (la doc est lue intégralement par Claude Chat à chaque conversation impliquant Bridge_Agent), coût d'écriture (chaque issue de doc réécrivait le bloc entier pour y insérer une entrée en tête), et risque de perte silencieuse (rien ne signalerait une troncature, un `git diff` sur une ligne de cette taille étant illisible). **Solution retenue** : nouveau fichier `CHANGELOG.md` à la racine du dépôt, contenant les 35 entrées historiques (de cette issue #252 jusqu'aux issues #135/#101/#97, suite #96) reformatées en sections `## <date> — issue #N`, contenu de chaque entrée repris **tel quel** — déplacement et reformatage, pas de résumé ni de réécriture. Extraction faite par script Python : séparation du pied de page d'origine sur la chaîne de connexion (« Précédemment » + tiret cadratin), avec vérification programmatique que la concaténation des segments reconstitue exactement le texte de départ (aucune perte possible) ; dates des 34 entrées antérieures (absentes du texte lui-même, seule la plus récente portait une date explicite) retrouvées sans ambiguïté via `git log` (recherche de `issue #N` dans les messages de commit, un seul jour de commit trouvé par numéro d'issue). Pied de page de `BRIDGE_AGENT_DOC.md` réduit aux **trois entrées les plus récentes** (celle-ci, #251, #249), suivies d'un renvoi vers `CHANGELOG.md` pour l'historique complet. **Vérification de non-perte (point 4)** : 34 occurrences du connecteur « Précédemment » avant modification, 35 entrées dans `CHANGELOG.md` après (34 + l'entrée « Dernière mise à jour » elle-même comptée à part) — décompte exact, aucun écart, confirmé avant livraison. **Vérification des dépendances (point 5)** : recherche de tout fichier s'appuyant sur le format du pied de page — une dépendance réelle trouvée dans `nouveau_projet.py` (deux occurrences, mise à jour de la date des projets §2/§7) : le script repère la ligne par `ligne.startswith("*Dernière mise à jour :")` puis remplace la date via le regex `(\*Dernière mise à jour : )[^—]*( —)`, insensible à tout ce qui suit le tiret cadratin — compatible tel quel avec le nouveau pied de page réduit, à condition que sa toute première ligne conserve exactement ce préfixe suivi d'un tiret cadratin juste après la date (vérifié, conservé sans changement). Aucun test (`tests/*.py`) ni aucun autre script ne référence ce pied de page ou la chaîne « Précédemment ». **§10** complété avec la nouvelle convention : toute issue modifiant la doc ajoute désormais son entrée en tête de `CHANGELOG.md` et fait glisser les trois entrées du pied de page (la plus ancienne des trois sortant du pied de page, elle reste disponible dans `CHANGELOG.md`). Aucune section renumérotée, aucun fichier `.py` modifié.

## 27 juillet 2026 — issue #250

Corrige le contraste illisible des pastilles de filtre projet désélectionnées (issue #250). Contexte : la règle `.filtre-projet.inactif` cumulait trois atténuations — `opacity:.4` global, fond `#f2f2f0`, texte `#999` — rendant le nom des projets désélectionnés difficile à lire, de façon inégale selon rendu/zoom du fait de l'`opacity` mêlée au fond de page sous-jacent ; contraste `#999999` sur `#f2f2f0` : 2,54:1, déjà sous le seuil WCAG AA (4,5:1) avant même l'effet de l'opacity. **Solution retenue** : suppression de l'`opacity` globale héritée de `.filtre-projet` — elle délavait aussi la pastille de couleur et l'emoji du bouton Ouvriers (`#filtre-ouvriers`, qui porte la même classe `.inactif` par défaut), pas seulement le texte du bouton ; ne restent atténués que le fond et le texte, ciblant uniquement ce qui doit l'être : `.filtre-projet.inactif{background:#f2f2f0;color:#5a5a5a}`. Contraste `#5a5a5a` sur `#f2f2f0` : 6,15:1, marge confortable au-dessus du seuil AA. La distinction sélectionné/désélectionné reste portée par trois signaux non corrélés — fond, texte, bordure (celle-ci retombant sur la valeur par défaut `1px solid #ccc`). Seul `static/css/style.css` modifié, aucun changement JS/HTML. Entrée ajoutée rétroactivement par l'issue #253 : cette issue, purement CSS, ne modifiait pas la doc et était donc restée hors du champ de la convention #252 alors en vigueur.

## 27 juillet 2026 — issue #251

Déclare restype/argtypes des appels ctypes kernel32 de l'objet Job Windows (issue #251, suite #249). Contexte : `_creer_job_windows_kill_on_close`/`_assigner_job_windows` appelaient `CreateJobObjectW`, `SetInformationJobObject`, `OpenProcess`, `AssignProcessToJobObject`, `CloseHandle` sans déclarer `restype`/`argtypes` — ctypes suppose alors par défaut un retour `c_int` (32 bits signés), alors que `CreateJobObjectW`/`OpenProcess` retournent un `HANDLE` (64 bits sur Windows x64) : le handle était donc tronqué silencieusement (fonctionnel en pratique tant que sa valeur reste petite, ce qui est le cas courant pour un handle noyau, mais rien ne le garantit), puis retronqué à chaque réutilisation en argument des appels suivants, eux aussi non déclarés — défaut structurellement invisible au test #249, qui mocke `ctypes.windll`. **Solution retenue** : nouvelle `_declarer_prototypes_kernel32_windows`, déclarant les cinq prototypes avec les types de `ctypes.wintypes` (`HANDLE`, `BOOL`, `DWORD`, `LPVOID`, `LPCWSTR`), appelée **une seule fois** à l'import du module sous la garde `if os.name == "nt":` — et non répétée à chaque appel, car le test `tests/test_nettoyage_arbre_windows_249.py` mocke `kernel32` par des méthodes liées Python (qui n'admettent pas l'affectation `.restype`/`.argtypes`) et ne force `os.name` qu'après l'import : une déclaration répétée aurait cassé ce mock. `python3 -c "import watcher"` vérifié toujours fonctionnel sous Linux (la garde empêche tout accès à `ctypes.windll`, absent hors Windows). **Point 2** : `_PROCESS_ALL_ACCESS = 0x1F0FFF` (valeur pré-Vista, toujours fonctionnelle) remplacé par les deux seuls droits documentés par Microsoft pour `AssignProcessToJobObject` — `PROCESS_SET_QUOTA | PROCESS_TERMINATE` (`_PROCESS_ACCES_JOB`). **Tests** : `tests/test_nettoyage_arbre_windows_249.py` et `tests/test_nettoyage_arbre_247.py` repassés sans modification (le mock ne traverse jamais la déclaration des prototypes, appelée seulement à l'import réel) — les deux passent. **§13** complété (sous-section « Nettoyage de l'arbre de process ») : nouveau paragraphe sur cette révision, et note sur les jobs imbriqués Windows 8+ sous NSSM (le service `CCW-Watcher` peut déjà être dans un job — l'assignation du process `claude` au job créé par `_preparer_job_windows` doit donc réussir même imbriquée ; si ce n'était pas le cas, le `log.warning` de `_preparer_job_windows` le signalerait — à vérifier lors de la prochaine validation réelle sur la VM CCW). Aucune section renumérotée..

## 27 juillet 2026 — issue #249

Remplace, sous Windows, le `taskkill /PID <pid> /T /F` de `_nettoyer_arbre_claude` par un objet Job noyau (issue #249, suite #247). Contexte : le nettoyage livré par #247 était correct sous POSIX mais très probablement inopérant sous Windows — la seule plateforme où le problème d'origine (`cmd.exe` orphelin verrouillant `Scrabble-Setup.exe` après un build CCW) avait été observé. `_nettoyer_arbre_claude` s'exécute dans le `finally` de `lancer_claude`, donc APRÈS le retour de `proc.communicate()` : à cet instant le process `claude` est déjà terminé et réapé, or `taskkill /PID <pid> /T /F` exige que le PID cible existe ENCORE pour parcourir son arbre généalogique — sur un PID mort il échoue immédiatement (« process not found ») sans toucher un seul descendant, exactement le scénario d'origine. `CREATE_NEW_PROCESS_GROUP` ne comble pas l'écart (sous Windows les groupes de process ne servent qu'au routage Ctrl+C/Ctrl+Break, pas à la terminaison d'une arborescence). Aggravation : seul le succès du `taskkill` produisait un `log.warning`, rendant l'échec totalement silencieux sous Windows ; le test de non-régression #247, exécuté sous Linux, ne couvrait que la branche POSIX. **Solution retenue** : objet Job noyau Windows (`CreateJobObjectW` + `SetInformationJobObject(JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)` + `AssignProcessToJobObject`), implémenté en `ctypes` pur (pas de nouvelle dépendance, pas de `pywin32`) — nouvelles fonctions `_creer_job_windows_kill_on_close`/`_assigner_job_windows`/`_preparer_job_windows`. Le job est créé et le process `claude` y est assigné **immédiatement après son démarrage** (`lancer_claude`, juste après le `Popen`, pendant que le process est encore vivant — seul moment où l'assignation est possible) ; fermer le handle du job dans `_nettoyer_arbre_claude(proc, job_windows)` termine alors toute la descendance encore assignée, PID vivant ou non. La branche POSIX (`start_new_session` + `os.killpg`) n'a **pas été touchée** : déjà correcte et testée. **Journalisation des échecs (point 3)** : `_preparer_job_windows` journalise tout échec de création/assignation du job, et `_nettoyer_arbre_claude` journalise tout échec de fermeture du handle (ou l'absence de job disponible) — la plateforme Windows ne peut plus rester silencieuse, succès ou échec. **Garde-fou (point 4)** : l'intégralité du corps de `_nettoyer_arbre_claude` est désormais enveloppée dans un `try/except Exception` — `_lister_processus_pgid` (OSError sur `iterdir()`), `os.killpg` (PermissionError) et les appels `ctypes` Windows ne peuvent plus s'échapper d'une fonction appelée depuis un `finally`, ce qui aurait masqué la valeur de retour de `lancer_claude`. **Test** : nouveau `tests/test_nettoyage_arbre_windows_249.py` — le scénario Windows réel n'étant pas exécutable sur le ThinkPad (Linux), mock de `ctypes.windll` (+ `os.name` forcé à `"nt"`) vérifiant l'ordre des appels ctypes (`CreateJobObjectW` → `SetInformationJobObject` → `OpenProcess` → `AssignProcessToJobObject` → `CloseHandle`), la journalisation succès/échec à chaque étape, et qu'une exception pendant le nettoyage n'est jamais remontée ; `tests/test_nettoyage_arbre_247.py` (POSIX) repassé sans modification — les deux passent (`python3 tests/test_nettoyage_arbre_247.py` et `python3 tests/test_nettoyage_arbre_windows_249.py` → ✅). ⚠️ **Ce mock ne remplace pas une validation réelle sur la VM CCW** : il vérifie que le code ctypes fait les bons appels, pas que Windows tue effectivement l'arbre de process en pratique — validation par build réel sur CCW encore nécessaire avant de considérer le correctif éprouvé en conditions réelles. **§13** réécrit (sous-section « Nettoyage de l'arbre de process ») : la justification de #247 (« symétrie CCL/CCW préférée à l'objet Job, script unique partagé ») est explicitement invalidée — cette symétrie coûtait la correction sous Windows, un objet Job en `ctypes` pur restant parfaitement compatible avec un script unique CCL/CCW (branche POSIX inchangée, aucune divergence de dépendance). Aucune section renumérotée.

## 27 juillet 2026 — issue #248

Isole le push de la route pièces jointes sur une branche orpheline dédiée, `pieces-jointes` (issue #248). Contexte : la route `POST /joindre-image` (§18, issue #191) terminait par `git push origin HEAD:<branche_courante>` — or git ne peut pas publier un commit sans ses ancêtres, ce push emportait donc AVEC l'image tous les commits locaux non encore poussés de la branche de travail, c'est-à-dire tout travail que CCL avait committé et qu'Alain n'avait pas encore relu : brèche dans le garde-fou central « CCL ne pousse jamais, Alain vérifie puis pousse » puisque rien d'autre n'était censé pousser à sa place ; aggravé par la propagation automatique aux autres clones (watchers en `git pull --ff-only` de début de cycle, dont la VM CCW, en quelques secondes) et par le fait que le fichier était écrit et committé DANS `REP_TRAVAIL` — l'arbre de travail qu'un watcher peut être en train d'utiliser pour une tâche `mode_write` au même instant. **Solution retenue** : commit construit par PLOMBERIE git (`hash-object -w` sur un fichier temporaire hors dépôt, puis `read-tree`/`update-index --cacheinfo`/`write-tree` sur un index TEMPORAIRE isolé via `GIT_INDEX_FILE`, puis `commit-tree`), sans jamais toucher à l'arbre de travail, à l'index réel ni à `HEAD` du dépôt ; racine sans parent à la première publication, sinon enfant du tip précédent (`git fetch origin pieces-jointes` best-effort) ; poussé isolément (`git push origin <sha>:refs/heads/pieces-jointes`) sur une branche **orpheline** ne contenant que `issue-attachments/` — par construction, aucun commit de code ne peut plus jamais être emporté, quel que soit l'état de la branche de travail. URL adaptée en conséquence (`.../pieces-jointes/issue-attachments/<fichier>`) ; le fichier n'est plus jamais écrit dans `REP_TRAVAIL` (transite par un fichier temporaire, nettoyé dans un `finally`). Le repli « garde-fou minimal » (refus si `rev-list --count` > 0) n'a pas été nécessaire, la plomberie s'étant révélée simple à implémenter proprement. **§18 réécrit** (nouvelle sous-section **§18.1bis** détaillant le mécanisme, **§18.2** complété : la justification de l'exception `push` ne repose plus seulement sur l'intention d'Alain mais aussi sur l'impossibilité technique désormais garantie de publier du code par cette voie). **Testé de bout en bout** sur un dépôt jetable (bare + clone) : un commit local « FIX CCL non relu » jamais poussé reste totalement absent d'origin après upload d'image (objet introuvable sur le bare, branche de travail inchangée, `HEAD`/index/arbre de travail du clone intacts — `git status --porcelain` vide) ; branche `pieces-jointes` créée avec un unique fichier sous `issue-attachments/`, sans ancêtre commun avec la branche de travail (`git merge-base` échoue, confirmant l'historique orphelin) ; deuxième upload vérifié en accumulation (2 commits, 2 fichiers, parenté correcte). Aucune section renumérotée hors les ajouts internes au §18.

## 26 juillet 2026 — issue #247

Garantit qu'aucun descendant du process `claude` ne survit au retour de `lancer_claude` (issue #247). Contexte : un `cmd.exe` de build Windows (CCW, `rebuild_scrabble.bat`) était resté vivant après la fermeture de l'issue, verrouillant `Scrabble-Setup.exe` jusqu'à un `taskkill` manuel — sans le moindre signal dans le journal ; défaut de fond, générique : rien ne garantissait qu'un process lancé pendant une tâche soit mort à la fin de celle-ci. **`lancer_claude`** (`watcher.py`) lance désormais `claude` via `subprocess.Popen` (plutôt que `subprocess.run`, pour garder la main sur le PID) avec `start_new_session=True` (POSIX) / `CREATE_NEW_PROCESS_GROUP` (Windows), isolant ce process dans un groupe/une session à lui ; un bloc **`finally`** — donc exécuté quel que soit le mode de sortie (succès, échec, `TimeoutExpired`, exception), et **avant** `commenter_resultat_avec_retry`/`fermer_issue` — appelle la nouvelle `_nettoyer_arbre_claude(proc)` : sous POSIX, `_lister_processus_pgid` énumère (lecture directe de `/proc`, sans dépendance externe) les process vivants du pgid de ce `claude`, journalise chacun en `log.warning` (PID + ligne de commande) puis `os.killpg(pid, SIGKILL)` sur ce seul groupe ; sous Windows, `taskkill /PID <pid> /T /F`. **Solution retenue** (justifiée en détail dans la nouvelle sous-section **§13** « Nettoyage de l'arbre de process après une tâche ») : terminaison de l'arbre après coup plutôt qu'un objet Job Windows (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) — ce dernier est natif et sans fenêtre de course, mais une API Windows pure (`ctypes`/`pywin32`) sans équivalent POSIX, alors que `watcher.py` est le script UNIQUE partagé par CCL et CCW ; fenêtre de course résiduelle de quelques millisecondes entre la fin de `communicate()`/le timeout et l'appel de nettoyage, jugée négligeable et strictement meilleure que l'absence totale de garantie d'avant #247. **Point 4 (critique), vérifié explicitement** : le nettoyage ne cible **jamais** par nom d'exécutable, seulement le pgid/l'arbre du PID de CE `claude`, garanti distinct de celui du watcher et de tout watcher frère par construction (`start_new_session`/nouvelle session) — une erreur ici aurait pu arrêter tous les watchers d'une même machine. **Journalisation, pas critère d'échec** : chaque orphelin tué produit un `log.warning` explicite ; le nettoyage ne fait jamais échouer la tâche, c'est une garantie de fin de traitement. **Test de non-régression** : nouveau `tests/test_nettoyage_arbre_247.py` — un faux `claude` (script en tête de PATH) lance un vrai enfant bloqué sur lecture (FIFO jamais écrite, équivalent stdin qui n'aboutit jamais) puis termine ; le test vérifie que l'enfant est mort après le retour de `lancer_claude`, que le nettoyage est journalisé (PID présent dans un `log.warning`), et que le process de test (rôle du watcher) n'est jamais affecté — passe (`python3 tests/test_nettoyage_arbre_247.py` → ✅). Aucune section renumérotée.

## 26 juillet 2026 — issue #245

Aligne le texte historique du §14 sur l'amendement #244 (issue #245). Contexte : le paragraphe « ⚠️ Contrainte d'exécution synchrone (rappel) », hérité de #208 et volontairement laissé intact par #244 comme référence documentaire, interdisait encore catégoriquement « un mécanisme d'attente différée, de tâche en arrière-plan ou de "je répondrai plus tard" » — formulation contredite par le texte en vigueur de `consignes/globales.md` depuis #244 (l'arrière-plan encadré, avec interrogation de la sortie en boucle DANS la même exécution, y est permis ; seul conclure son tour de parole avant la fin réelle et vérifiée de l'opération reste proscrit). Un Claude Chat consultant le §14 en premier — cas fréquent, section de référence sur la délégation — pouvait lire l'interdiction absolue sans descendre jusqu'à l'encart d'injection qui la nuançait déjà, et reconduire dans une issue de build une consigne que le système n'applique plus. **§14** : le paragraphe est reformulé pour dire une seule chose, alignée sur `globales.md` — proscrit : conclure son tour de parole avant la fin réelle et vérifiée de l'opération ; permis : l'arrière-plan encadré (interrogation de la sortie en boucle DANS la même exécution) ; restent interdits sans changement : « monitor », notification, rappel programmé, formulations « je répondrai plus tard ». Reste du paragraphe conservé tel quel (aucune reprise possible après réponse, boucle `sleep` + `gh issue view` pour l'attente d'un ouvrier) ; l'encart d'injection qui suit (issues #209/#243) n'a pas été touché, sa nuance restant exacte. Recherche `arrière-plan`/`monitor`/`attente différée` sur tout le fichier : une autre occurrence trouvée hors §14 et hors pied de page — **§12.1** (ligne « Globale » du tableau des trois couches : « contrainte d'exécution synchrone et bloquante, sans attente différée, universelle depuis #243 ») — laissée telle quelle, ce résumé reste exact (l'interdit qu'elle nomme est bien l'attente différée pour conclure, pas l'arrière-plan comme technique) ; le pied de page (historique de #244 et antérieurs) laissé tel quel par consigne explicite. Aucune section renumérotée, aucun fichier `.py` ni `consignes/*.md` modifié.

## 26 juillet 2026 — issue #244

Amende la contrainte d'exécution universelle de #243 pour lever une contradiction qu'elle introduisait avec le plafond de timeout de l'outil Bash (issue #244). Contexte : le texte issu de #243 interdisait catégoriquement l'arrière-plan (« Ne lance jamais une commande en arrière-plan ») et proposait comme repli de relancer avec un timeout explicite plus long — or l'outil Bash a un timeout MAXIMUM par appel (de l'ordre de dix minutes) qu'aucun paramètre ne permet de dépasser ; si un build excède ce plafond (hypothèse plausible pour #241/#242, probablement à l'origine du basculement en arrière-plan qui avait motivé #243), l'agent se retrouvait pris entre deux interdits — attendre en un seul appel ou lancer en arrière-plan — et improviserait. Second défaut, dans la même phrase : le repli « boucle sur sa sortie DANS cette même exécution » SUPPOSE une exécution en arrière-plan (on lance, puis on interroge la sortie en boucle) ; la consigne décrivait donc le bon comportement tout en interdisant le mécanisme qui le rend possible. Le fautif n'est pas l'arrière-plan en soi, c'est de conclure son tour de parole sans avoir attendu la fin réelle de l'opération. **`consignes/globales.md`** : la fin du bullet « Contrainte d'exécution » (à partir de « Si une opération dépasse le timeout d'un appel d'outil… ») est réécrite — ce qui est interdit, c'est de CONCLURE le tour de parole avant que l'opération soit terminée et son résultat vérifié, pas l'arrière-plan comme technique ; en cas de dépassement du timeout d'un appel d'outil, deux voies restent permises : relancer avec un timeout explicite plus long tant que le plafond de l'outil le permet, OU lancer en arrière-plan À CONDITION IMPÉRATIVE d'interroger sa sortie en boucle DANS cette même exécution jusqu'à complétion réelle ; restent interdits sans changement le « monitor », la notification, le rappel programmé et toute formulation « je répondrai/j'attends… » en guise de conclusion ; rappel inchangé qu'aucune reprise n'existe (le watcher ferme l'issue dès la réponse postée). **`consignes/type_chef.md`** vérifié : sa formulation (« aucune attente différée, aucun monitor ») reste cohérente avec le nouveau texte — non touché. **§12.1** (ligne « Globale ») et **§14** (encart d'injection automatique) vérifiés : leurs résumés restent exacts sans qu'il soit besoin d'y ajouter la précision arrière-plan/plafond — non touchés. Aucune section renumérotée, aucun fichier `.py` modifié.

## 26 juillet 2026 — issue #243

Généralise l'interdiction d'attente différée à toute issue et distingue opération longue légitime du blocage sans progrès (issue #243). Contexte : les issues #241/#242 (builds Scrabble, CCW) se sont fermées `done` avec un rapport annonçant attendre une notification de fin de build ou un rappel programmé, alors que le build avait réellement abouti (`Scrabble.exe` et `Scrabble-Setup.exe` présents, datés du jour) — pas un échec de build, un rapport ne reflétant pas la réalité, produit par un agent sorti avant la fin. Deux consignes en cause, inversées par rapport à ce qu'exige une tâche longue : `consignes/globales.md` (injecté dans TOUTE issue) demandait d'abandonner toute commande « boucle/tarde anormalement (> 30s sans progrès net) » — écrit pour #214 (commande refusée par le système de permissions, bouclage réel), mais assez général pour couvrir aujourd'hui un build PyInstaller + Inno Setup (plusieurs minutes, peu de sortie visible), appliqué à la lettre ; l'interdiction qui aurait dû s'appliquer (ne jamais recourir à une attente différée, un « monitor », etc.) vivait dans `consignes/type_chef.md`, injecté SEULEMENT pour le TYPE `chef` — une issue de build n'en est pas une. Le mode de défaillance n'ayant rien de spécifique au rôle de chef (il guette toute tâche dont une étape dépasse le timeout d'un appel d'outil), la contrainte est rendue universelle. **`consignes/globales.md`** : le rappel issu de #214 est reformulé pour distinguer une commande refusée par les permissions ou bloquée SANS AUCUN PROGRÈS (→ abandon immédiat, comportement inchangé) d'une opération longue mais qui PROGRESSE normalement (build, compilation, installation de dépendances, suite de tests, clonage volumineux — → ce n'est PAS une anomalie, il faut attendre sa fin) ; le seuil de 30s ne s'applique plus qu'à l'absence de progrès, plus à la durée en soi. Nouveau rappel généralisé depuis `type_chef.md` : accomplir la tâche en une seule exécution synchrone et bloquante, jamais de commande en arrière-plan / « monitor » / notification / rappel programmé / « je répondrai quand… », relancer avec un timeout explicite plus long ou boucler DANS la même exécution en cas de dépassement du timeout d'un appel d'outil, jamais conclure sur une attente — rappel qu'aucune reprise n'existe, le watcher fermant l'issue dès la réponse postée. **`consignes/type_chef.md`** : allégé pour éviter la redondance — ne garde que la spécificité chef (boucler `sleep` + `gh issue view` en attendant la fermeture des issues ouvrières, puis synthèse finale), la contrainte générale étant désormais dans `globales.md`. **TYPE `build`** : vérification de `watcher.deduire_type_issue`/`TYPES_ISSUE` — `build` n'est PAS une valeur reconnue (`TYPES_ISSUE` = chef/ouvrier/spec_vue/spec_metier/spec_persistance/normal, et `_classer_valeur_type` n'a aucune branche pour « build » : même un en-tête explicite `| TYPE | build |` retomberait sur `normal`) ; `consignes/type_build.md` n'a donc PAS été créé — le mécanisme ne s'y prête pas sans modifier `watcher.py` (hors périmètre de cette issue), et de toute façon le vrai correctif (la contrainte universelle dans `globales.md`) couvre déjà le cas des builds sans dépendre d'un TYPE dédié. **§12.1** : la parenthèse résumant les rappels globaux (ligne « Globale ») mise à jour pour refléter la distinction blocage/progrès et la contrainte d'exécution synchrone désormais universelle. **§14** : le bloc « Contrainte d'exécution impérative » renommé « rappel » et son encart d'injection automatique mis à jour pour pointer vers `globales.md` (universel depuis #243) plutôt que `type_chef.md`, qui n'ajoute plus que la spécificité chef. **§1** : rattrapage d'une omission de #240 — la réécriture du paragraphe sur le pull automatique avait fait disparaître la parenthèse sur les projets à **périmètre dynamique** (dépôt-cible défini par issue, dépôts d'audit non rafraîchis par le pull automatique, distincts du clone de travail du watcher) ; réintroduite, adaptée au nouveau texte. Aucune section renumérotée.

## 26 juillet 2026 — issue #240

Correctif documentaire §1/§14/§16 et rattrapage de trois issues committées sans mise à jour du DOC (issue #240). Incident du 26/07 : le clone `C:\CCW\Bridge_Agent` de la VM (celui d'où s'exécute réellement `watcher.py`) avait **80 commits de retard** sur `origin/master`, sans aucun signal — le service tournait avec du code antérieur à l'issue #195, cause probable de l'incident #236 (issue fermée `done` sans commentaire de résultat). **§1** réécrit : le `git pull --ff-only` automatique de début de cycle porte bien sur `REP_TRAVAIL` avec la même logique CCL/CCW, mais ne met à jour le CODE du watcher que lorsque `REP_TRAVAIL` coïncide avec le clone du dépôt Bridge_Agent — vrai côté CCL, **faux** côté CCW en modèle unifié (#231), où `REP_TRAVAIL = \\VBOXSVR\CCW_Share` n'est même pas un dépôt git et où le clone contenant `watcher.py` (`C:\CCW\Bridge_Agent`) vit ailleurs, mis à jour par personne. L'ancienne affirmation « comportement identique CCL et CCW » est supprimée car trompeuse sur ce point précis. **§16** gagne un bloc d'avertissement opérationnel : ce clone n'est **jamais** mis à jour automatiquement ; procédure obligatoire après tout push touchant `watcher.py` — `git pull --ff-only` dans `C:\CCW\Bridge_Agent` **puis redémarrage du service** `CCW-Watcher` (`nssm restart`, un pull seul ne suffit pas : un process Python déjà démarré garde en mémoire le code chargé à son lancement) — avec la commande de contrôle rapide `git status -sb` (ne doit jamais afficher `behind`), et le cas réel des 80 commits de retard comme justification. **§14** corrigé : dans le bloc « Quand NE PAS passer par un chef » (#225), la référence au service `CCW-Watcher-<Projet>` — nom venant du modèle multi-projets abandonné par #231 — est remplacée par `CCW-Watcher`. Rattrapage de trois issues committées sans entrée de pied de page : **#237** — `commenter_issue`/`editer_dernier_commentaire` passent par `--body-file` (fichier temporaire UTF-8) au lieu de `--body`, supprimant la limite argv Windows de 32767 caractères ; `commenter_resultat_avec_retry` vérifie désormais la publication par relecture de l'issue (un exit code 0 de `gh` ne suffit plus, la présence effective du commentaire est exigée) ; nouveau marqueur `MARQUEUR_RESULTAT` (`<!-- bridge:resultat -->`) en tête du commentaire de résultat, utilisé aussi par `resultat_deja_poste` à la place de l'ancienne sous-chaîne `"## Résultat"` qui matchait à tort `"## Résultat attendu"` ; test `tests/test_verification_commentaire_237.py` ; deux effets de bord assumés — deux appels `gh` par tentative, et possibilité d'un commentaire en double si la publication réussit mais que la relecture échoue transitoirement (perte silencieuse échangée contre doublon visible). **#238** — `fermer_issue` inspecte désormais les codes de retour de `close` et `add-label`, retourne un booléen, et journalise explicitement les états incohérents (fermée sans label / label sans fermeture) sans compensation automatique. **#239** — libellé d'agent de l'ACK déduit automatiquement de `platform.system()` (« agent Linux » / « agent Windows »), avec champ optionnel `LIBELLE_AGENT` pour forcer un libellé explicite si la détection automatique ne convient pas ; le §16 avait déjà été modifié par cette issue mais aucune entrée de pied de page n'avait été ajoutée — rattrapée ici. Aucune section renumérotée.

## 26 juillet 2026 — issue #233

§3 « Créer une issue » : ajout d'une **exception `PROJET`** pour les issues `for-windows` (issue #233, suite #231). Rapport remonté par le Claude du projet `actualise` : lors de la génération d'une issue de build Windows, le champ `PROJET` avait été renseigné avec `actualise` au lieu de `bridge_agent`, en appliquant par erreur la règle générale du §3 (« nom exact du projet cible »). Or le §16.3 (modèle CCW unifié, #231) applique correctement `PROJET=bridge_agent` dans son template — c'est la config du watcher CCW unique qui compte, pas le projet réellement construit — mais le §3, consulté en premier par Claude Chat, ne mentionnait pas cette exception. Ajout d'un second bloc d'avertissement juste après celui existant (« Claude Chat doit toujours inclure `| PROJET | <nom> |` ») précisant que pour les issues `for-windows`, `PROJET` reste toujours `bridge_agent`, le nom du projet cible s'exprimant en texte dans le corps (chemins, `git clone`/`git pull`), avec renvoi au template du §16.3. Aucune section renumérotée.

## 26 juillet 2026 — issue #231

§16 « Agent Windows CCW » : documentation du **modèle CCW unifié** (issue #231), qui remplace le modèle multi-projets (#170, un service NSSM par projet). Un seul service NSSM `CCW-Watcher` surveille désormais les issues `for-windows` de `AlainDelree/Bridge_Agent`, `REP_TRAVAIL = \\VBOXSVR\CCW_Share` (accessible depuis Linux à `/home/alain/Bridge_Agent_CCW_Share/`), chaque projet buildé étant cloné dans un sous-dossier dédié `\\VBOXSVR\CCW_Share\CCW\<projet>\` — séquencement strict des builds par construction (un seul process `watcher.py`), zéro contention CPU/RAM entre builds parallèles. Validé en production avec le build PyInstaller d'`actualise`. Introduction du §16 réécrite (titre « (en préparation) » retiré, devenu opérationnel) ; nouvelle sous-section **§16.3 « Procédure — builder un projet Windows »** détaillant le template d'issue en 4 étapes (exception `git config --global --add safe.directory` sur le chemin UNC — obligatoire une seule fois par sous-dossier —, clone ou `git pull --ff-only`, `pip install -r requirements.txt`, build `python -m PyInstaller --noconfirm --onedir --noconsole`), la récupération manuelle des artefacts côté Linux et le rappel qu'aucun token GitHub Contents n'est requis (dépôts publics, seul le token Issues du service `CCW-Watcher` sert). Les scripts `ajouter_projet_ccw.ps1` et `finaliser_projet_ccw.ps1` (tableau de provisioning) marqués **« obsolète — modèle multi-projets abandonné, conservé à titre historique »** — ne plus les utiliser, mais conservés dans le dépôt sans suppression. Reste du §16 (§16.1 maintenance 90 jours, §16.2 onglet CCW, description historique du modèle multi-projets #170) laissé inchangé, hors du périmètre de cette issue.

## 26 juillet 2026 — issue #225

§14 « Délégation Chef → Ouvrier » : ajout d'un bloc **« Quand NE PAS passer par un chef »** (issue #225), inséré juste après le paragraphe « Principe » et avant « Ce n'est pas déclenché automatiquement… ». Contexte : sur le projet `actualise`, une tâche entièrement Windows avait donné lieu à une issue chef CCL dont le seul travail était de créer immédiatement un ouvrier CCW et d'attendre sa fermeture — sans étape réelle côté Linux, correct mais coûteux (deux issues, deux invocations `claude`, TIMEOUT long, attente synchrone bloquante payée pour rien). Le nouveau bloc pose le **critère de décision** : le chef se justifie quand la tâche comporte du travail réel côté Linux (avant et/ou après) dans la même unité de travail ; si la TOTALITÉ de la tâche s'exécute sous Windows, créer directement l'issue avec `| LABELS | for-windows |` (§3) plutôt qu'un chef. **Contre-exemple explicite** : un chef qui se contente de créer un ouvrier puis d'attendre sa fermeture, sans orchestration réelle, est du surcoût pur. Rappel que l'**exemple validé** plus bas dans la section (dictionnaire déposé côté Linux puis rebuild côté Windows) reste un cas où le chef EST justifié — la nouvelle règle ne le contredit pas. **⚠️ Contrepartie opérationnelle** ajoutée dans le même bloc : le rallumage automatique du watcher à la création d'une issue (§13, mécanisme 2) ne vaut QUE pour les issues `for-linux` — une issue `for-windows` directe ne démarre rien, donc vérifier dans l'onglet CCW (§16.2) que la VM `CCW-Build` tourne et que le service `CCW-Watcher-<Projet>` est démarré avant d'en envoyer une, sinon elle reste ouverte sans aucun signal. En miroir, **§3** (paragraphe décrivant le champ `LABELS`, juste après la phrase sur le cas d'usage `| LABELS | for-windows |`) gagne une phrase de renvoi croisé vers ce bloc du §14. Aucune section renumérotée ; reste du §14 (contrainte d'exécution impérative, format des titres, timeout du chef, exemple validé) et reste du §3 inchangés.

## 25 juillet 2026 — issue #224

Nouvelle section **§19 « Calibration automatique du TIMEOUT »** (issue #224), documentant de bout en bout le système mis en place par les issues #220 (extension d'`historique_durees.json`), #221 (mécanique EWMA `etat_timeout.json`/`etat_ambiance.json`), #222 (exposition du `TIMEOUT_suggéré` dans le commentaire de clôture GitHub) et #223 (exclusion des `expiree=true` du badge d'estimation de l'interface). Jusqu'ici ce système n'était documenté nulle part dans `BRIDGE_AGENT_DOC.md` — seul `CONTEXTE.md` en gardait une trace partielle, ajoutée par #221 et jamais mise à jour depuis, de toute façon plafonnée par sa limite de taille pour l'injection prompt (§12.1). La nouvelle section couvre, à partir d'une lecture du code réel de `watcher.py`/`app/issues.py` (pas une paraphrase des rapports d'issue) : l'objectif et le principe d'inspiration (RTO TCP, Jacobson/Karels), la formule complète et chacun de ses termes, les deux fichiers d'état (`logs/etat_timeout.json`, `logs/etat_ambiance.json` — partagés entre watchers, verrouillés, écriture atomique), le tableau des constantes actuelles en soulignant explicitement qu'elles sont des valeurs de DÉPART non backtestées, le canal d'exposition (bloc `⏱️/📊` dans le commentaire de clôture, sans aucune application automatique — le TIMEOUT réellement utilisé reste celui de l'en-tête, `extraire_timeout`), et une liste explicite des limitations connues (`tag_reseau` jamais peuplé donc `F_reseau`/`F_local` neutres, incohérence inerte de `lire_timeout_suggere` sur échec définitif, démarrage à froid trompeusement optimiste, aucun backtest des constantes, distinction avec le badge `estimer_duree` de #223). Aucune autre section renumérotée ni modifiée.

## 24 juillet 2026 — issue #217

Correctif horloge d'auto-extinction (issue #217) : le watcher pouvait s'éteindre **immédiatement après un traitement réel** lorsque celui-ci s'étirait au-delà du délai d'inactivité (`DELAI_INACTIVITE_MIN`, défaut 20 min). Cause : `derniere_activite` (horloge monotone d'inactivité, #200) n'était réarmée qu'**en tête de cycle**, juste après `lister_issues()` et **avant** de lancer `traiter_issue()` — donc jamais pendant le traitement (potentiellement long : plusieurs timeouts de 300 s + retries en cascade). Si le traitement d'une seule issue dépassait le délai (cas réel `watcher-scrabble.log` du 24/07/2026 : #237/#238 traités sans interruption de 08:59 à 09:22, puis extinction à 09:23:08 — 14 s après le succès de #238), l'horloge restait figée à l'instant du **début** du cycle ; le test d'extinction du cycle suivant se déclenchait alors sur une horloge périmée, ne reflétant pas le travail réellement effectué. **Correctif** (`watcher.py`, boucle principale) : réarmement de `derniere_activite` **aussi APRÈS** la boucle de traitement, dès qu'au moins une issue traitable a été traitée ce cycle (option a du diagnostic — réarmer sur le travail réel, préférée à l'option b « revérifier `lister_issues()` avant `sys.exit` » car elle satisfait plus directement l'objectif « ne jamais éteindre si du travail vient d'avoir lieu », sans appel réseau supplémentaire ni cas où une issue devenue fermée entre-temps laisserait l'extinction filer). Le flag `travail_a_faire` (calculé une fois) conditionne les deux réarmements ; l'extinction reste possible quand plus rien n'est traitable. **Test de non-régression** : `tests/test_auto_extinction_217.py` pilote le vrai `watcher.main()` avec horloge mockée (`time.monotonic`/`time.sleep` patchés) sur 3 scénarios — (1) traitement long ~23 min + issue restante → **pas** d'extinction prématurée (échoue sur le code d'avant #217, passe sur le code corrigé), (2) inactivité réelle → extinction bien déclenchée, (3) issue non-traitable (`done`) → n'empêche pas l'extinction. §13 (mécanisme 3 « Extinction automatique ») mis à jour pour décrire le double réarmement avant/après.

## 24 juillet 2026 — issue #214

Nouveau rappel global « abandon immédiat au refus de permission » (issue #214) : ajout, à la fin de `consignes/globales.md`, d'un rappel systématique — si une commande/un outil est **refusé par le système de permissions** (session non-interactive, aucune approbation possible) ou **boucle/tarde anormalement** (> 30s sans progrès net), CCL doit **abandonner immédiatement** l'approche et le signaler dans son rapport plutôt que de retenter, en basculant si possible sur un repli plus simple (lecture directe, `grep`, analyse manuelle) et sans jamais insister sur une commande déjà refusée. Motivation : comparaison des issues Scrabble #235 (timeout à 300s, bouclage sur une commande refusée) et #238 (succès) — la seule différence significative était la présence, dans #238, d'une consigne explicite d'abandon-au-lieu-de-retenter ; en session non-interactive, un refus de permission Claude Code est systématique et définitif (aucun utilisateur pour approuver), donc retenter est vain. Consigne volontairement **générale** (pas spécifique à Scrabble ni à JS/eslint) car le problème touche toute commande nécessitant une approbation (installation de paquet, exécution d'un binaire, etc.), quel que soit le projet ou le langage. §12.1 : la parenthèse résumant les rappels globaux dans le tableau des trois couches est complétée (ajout d'« abandon immédiat au refus de permission / boucle anormale ») ; la liste complète des rappels n'étant pas reproduite ailleurs dans la doc, aucune autre duplication à mettre à jour.

## 23 juillet 2026 — issue #211

Déplacement de l'injection des consignes trois couches dans `watcher.py` — couverture universelle (issue #211). Les consignes (globales/type/projet, #209) ne sont plus écrites dans le **corps** de l'issue par `app/issues.py` (chemin qui ne couvrait QUE les issues créées via le formulaire web), mais injectées dans le **prompt donné à CCL au moment du traitement** par `watcher.py` (`lancer_claude` → nouvelles `_consignes_injectees`/`_lire_consigne`, reprises de `app/issues.py`), exactement sur le modèle de `CONTEXTE.md`/`FICHIER_CONTEXTE`. Le point de passage devient **unique** : peu importe le chemin de création — formulaire web, `gh issue create` d'un chef (§14), création manuelle GitHub (§3) — `watcher.py` déduit le TYPE (`deduire_type_issue` sur le titre/corps réels) et le projet (`CFG.nom`), puis ajoute le bloc **après** le bloc `CONTEXTE` et **avant** la clause de périmètre / le garde-fou (regroupement des « règles » en fin de prompt, zone la mieux suivie). Cas particulièrement corrigé : les issues **ouvrières créées par un chef** (chemin 2, vraies tâches `mode_write`) recevaient auparavant zéro consigne — c'est justement là que les rappels de sécurité comptent le plus. `app/issues.py::construire_body` revient à un corps **en-tête + corps rédigé** seulement (suppression de `_consignes_injectees`/`_lire_consigne`/`DOSSIER_CONSIGNES` et de l'import `logging` devenu inutile) — source unique de vérité désormais côté watcher, plus de double injection. Garde-fous inchangés (#209) : `globales.md` absent → `log.warning` sans bloquer le traitement ; `type_*`/`projet_*` absents → silencieux. Conséquence assumée (comme pour `CONTEXTE.md`) : les consignes ne sont plus visibles dans le corps d'une issue sur GitHub. **§12.1 réécrite** (modèle prompt + couverture universelle des 3 chemins + emplacement dans le prompt) et **§10** mis à jour (`consignes/` = injecté dans le prompt CCL, plus « en tête de chaque issue »). Testé de bout en bout par une issue `TYPE=chef` `mode_write` créée **directement en CLI** (`gh issue create`, hors formulaire) : le prompt CCL assemblé par le watcher contient bien les consignes globales + `type_chef.md`.

## 23 juillet 2026 — issue #209

Architecture à trois couches d'injection de consignes (issue #209) : nouveau dossier `consignes/` à la racine, injecté **dans le corps de chaque issue** par `app/issues.py` (`construire_body` → `_consignes_injectees`), entre le tableau d'en-tête et le corps rédigé par Claude Chat. Trois couches, de la plus générale à la plus spécifique : **globales** (`consignes/globales.md`, **NON-optionnel** — rappels de sécurité transversaux : ne jamais pousser, backup avant modif, respect du périmètre — injecté dans TOUTE issue), **type** (`consignes/type_<type>.md`, **facultatif** — ex. `type_chef.md` reprenant la contrainte d'exécution synchrone du #208, injecté selon le TYPE déduit par `watcher.deduire_type_issue`), **projet** (`consignes/projet_<projet>.md`, **facultatif** — aucun créé par défaut). Ordre final : en-tête → globales → type (si présent) → projet (si présent) → corps. Vaut en **mono-issue comme en mode lot** (chaque bloc `#Titre:` passe par `construire_body` avec son propre TYPE). **Choix délibéré anti-piège de maintenance** : contrairement à `CONTEXTE.md`, les couches type/projet sont sans obligation de présence (un projet sans `projet_<nom>.md` fonctionne normalement, rien à créer/maintenir) et créées uniquement à la demande. Garde-fous : fichier `type_*`/`projet_*` absent → aucune injection **sans** log (normal, pas une anomalie) ; `globales.md` introuvable → `logging.warning` clair **sans jamais faire échouer** la création d'issue. Nouvelle sous-section **§12.1** décrivant l'architecture, mise à jour du **§10** (dossier `consignes/`) et du **§14** (la contrainte d'exécution synchrone du chef n'est plus à recopier manuellement — elle est injectée automatiquement via `consignes/type_chef.md`). Testé de bout en bout (issue `TYPE=chef` réelle : corps GitHub contenant, dans l'ordre, globales puis chef puis corps original).

## 23 juillet 2026 — issue #208

Finalisation du nettoyage doc MVC (issue #208, suite #207) : le §14 « Délégation Chef → Ouvrier » gagne un bloc **« ⚠️ Contrainte d'exécution impérative »** rappelant que le chef doit accomplir la TOTALITÉ de sa tâche (attente de fermeture des ouvriers + synthèse finale comprises) en **une seule exécution synchrone et bloquante** — aucune reprise n'étant possible après qu'une issue a été répondue/fermée, ne jamais recourir à une attente différée, une tâche en arrière-plan ou un « je répondrai plus tard » ; si une attente est nécessaire, boucler (`sleep` + `gh issue view`) DANS la même exécution. Cette finalisation confirme aussi l'absence des fichiers `CONTEXTE_VUE.md`/`CONTEXTE_METIER.md`/`CONTEXTE_PERSISTANCE.md` à la racine de bridge_agent (jamais créés ici ; seul `CONTEXTE.md` existe et est conservé).

## 23 juillet 2026 — issue #207

Nettoyage doc MVC (issue #207) : **suppression de l'ancien §15 « Pattern Chef + Specs MVC (évolution future) »**, purement prospectif et jamais implémenté (le watcher ne lit pas le champ `SPECS`, aucun routage par couche Vue/Métier/Persistance n'existe) ; les sections suivantes **ne sont pas renumérotées** (16, 17, 18 restent 16, 17, 18) pour préserver les références croisées existantes. Le **§14 est entièrement réécrit** et recadré « Délégation Chef → Ouvrier (changement d'environnement) » : on ne garde que l'usage réel validé — un CCL « chef » crée lui-même une issue « ouvrier » ciblant un autre environnement (typiquement CCL Linux → CCW Windows) via `gh issue create` et surveille sa fermeture avant de livrer, sur instruction explicite (pas de détection auto du rôle chef, pas de décomposition automatique générique) — avec conseil de `TIMEOUT` généreux côté chef et l'exemple validé du build Scrabble/ouvrier CCW. En complément, l'issue chef #207 délègue à 6 issues « ouvrier » (une par projet actif hors bridge_agent et ff_galerie) la suppression des fichiers `CONTEXTE_VUE.md`/`CONTEXTE_METIER.md`/`CONTEXTE_PERSISTANCE.md` — vestiges du §15 abandonné — `CONTEXTE.md` (mécanisme standard hors MVC) étant conservé partout.

## 20 juillet 2026 — issue #191

§18 (nouveau) « Pièces jointes image dans les issues » (issue #191) : l'onglet « Nouvelle issue » accepte désormais un **upload optionnel PNG/JPEG** (champ fichier + bouton « Joindre une image » à côté du corps). Nouvelle route **`POST /joindre-image`** (`app/issues.py`, `joindre_image()`) : valide le type (Content-Type **et** magic bytes) et la taille (**≤ 5 Mo**), sauvegarde dans **`issue-attachments/`** (racine du `REP_TRAVAIL`) sous un nom **horodaté** anti-collision (`AAAAMMJJ-HHMMSS-<nom>.ext`), puis `git add` + `commit` + **`git push origin HEAD:<branche>`** (branche déduite **dynamiquement**, jamais supposée master/main), et retourne l'URL **`raw.githubusercontent.com/<owner>/<repo>/<branche>/issue-attachments/<fichier>`** — format qui s'affiche correctement dans les issues GitHub. Le frontend (`static/js/app.js`, `joindreImage()`/`insererDansCorps()`) insère alors **automatiquement** `![<nom>](<url>)` dans le corps à la position du curseur. **Exception `push` assumée et documentée (§18.2)** : ce commit+push est déclenché par **ALAIN** via l'outil (son action manuelle), **pas par CCL/le watcher** — la règle « CCL ne pousse jamais » n'est donc pas violée (elle vise les modifications de code de l'agent, pas une image qu'Alain publie lui-même). Gestion d'erreurs (§18.4) : **push échoué → aucune URL insérée** (commit conservé en local, poussable plus tard), **projet sans dépôt git → message clair**, type/taille/contenu invalides refusés proprement. `issue-attachments/` volontairement **hors `.gitignore`** (les images doivent être suivies/poussées). Testé de bout en bout (dépôt jetable + remote bare : succès + URL correcte, et chemins d'échec type/taille/magic/push).

## 20 juillet 2026 — issue #187

§17 (nouveau) « Notifications centralisées — détection serveur des transitions » (issue #187) : `new_issue.py`, qui tourne en permanence sur le ThinkPad, détecte désormais LUI-MÊME par polling `gh` les transitions d'issues (fermeture `done` = succès ; label `needs-human` = échec définitif) de **tous** les projets (for-linux ET for-windows), et déclenche bip/`notify-send`/`ntfy` **localement**, y compris pour les issues traitées par la VM **CCW** — **sans aucun appel réseau initié par la VM** (la VM n'écrit que sur GitHub). Nouveau module partagé `notifications.py` (racine) factorisant `bip`/`notifier_bureau`/`notifier_ntfy`/`notifier`, importé par `watcher.py` (enveloppes minces déléguant, sites d'appel inchangés) ET par le nouveau poller `app/notifications_poller.py` (thread démon lancé par `new_issue.py`). Script bip **déplacé/recréé** de `~/NicLink/bip.py` vers `scripts/bip.py` (infrastructure partagée) ; défaut `SCRIPT_BIP` et `configs/*.conf` mis à jour. Anti-doublon (point 4) : réglage `NOTIFIER_LOCAL` (`.conf`, défaut `true`) coupant la notif du watcher + portée `BRIDGE_NOTIF_SCOPE` (env, défaut `for-windows`) du poller. **Défaut livré sans régression ni doublon** (CCL notifie via son watcher, CCW via le poller — variante propre de l'option b) ; **option (a) « centralisation complète » recommandée mais laissée au choix d'Alain** car elle fait de `new_issue.py` une dépendance dure de toute notification (or il n'a pas encore de service systemd) — implémentée et à un réglage près (`BRIDGE_NOTIF_SCOPE=all` + `NOTIFIER_LOCAL=false` partout). **Action requise côté VM CCW** : poser `NOTIFIER_LOCAL=false` dans `configs\*-ccw.conf` pour éviter un double `ntfy`. Bonus (point 5) : le poller lit les labels COURANTS à la fermeture, donc `notif_pc`/`notif_gsm` ajouté EN COURS de traitement est bien pris en compte. Filtre de récence (`BRIDGE_NOTIF_RECENCE_MIN`, défaut 30 min) + amorçage silencieux au 1er cycle évitent le spam de vieilles issues au démarrage ; état en mémoire process.

## 20 juillet 2026 — issue #186

§1 « Vue d'ensemble » : documentation du **`git pull --ff-only` automatique en début de cycle** de `watcher.py` (issue #186, suite du #185 qui l'a implémenté). Le watcher rafraîchit son clone (`REP_TRAVAIL`) au début de chaque cycle de polling, juste avant `lister_issues()` : fast-forward transparent en cas de succès ; en cas de commits locaux non poussés (divergence) le `--ff-only` échoue proprement sans RIEN écraser et le watcher poursuit sur le code local — donc aucun risque à oublier un `git push`. Comportement **identique CCL (Linux) et CCW (Windows)** puisque `watcher.py` est le script unique partagé ; les projets à périmètre dynamique (dépôt-cible par issue) ne sont pas concernés. Un `git pull`/relance manuel reste possible pour une mise à jour immédiate (confort, plus une nécessité). Aucune instruction obsolète de « git pull manuel obligatoire » à corriger dans le §16 (aucune ne subsistait).

## 19 juillet 2026 — issue #174

§16 « Agent Windows CCW » : **onglet « CCW » dans l'interface web** (issue #174, sous-section §16.2) — pilotage complet de la VM et des projets CCW depuis Linux, sans PowerShell manuel dans la VM. Backend `app/ccw.py` (routes `/ccw/*`) exécutant les scripts existants à distance via `VBoxManage guestcontrol` : état/démarrage de la VM (`demarrer_ccw.sh`), liste des projets (nouveau `lister_projets_ccw.ps1`, sortie JSON encadrée), ajout (`ajouter_projet_ccw.ps1`) et finalisation non interactive (nouveau `finaliser_projet_ccw_auto.ps1` + `mettre_a_jour_tokens_ccw.ps1` doté d'un mode `-FichierTokens`). Sécurité : tokens jamais passés en argument ni journalisés (fichier temporaire `0600` poussé puis supprimé des deux côtés dans un `finally`) ; mot de passe `ccw-admin` lu depuis `CCW_ADMIN_PASSWORD` ou `configs/ccw_admin.secret` (gitignoré). Nouvel onglet + panneau dans `templates/index.html`, fonctions `ccw*` dans `static/js/app.js`, classe `.message.avertissement` dans `style.css`.

## 19 juillet 2026 — issue #173

§16 « Agent Windows CCW » : **finalisation d'un projet CCW en une seule commande** (issue #173, suite #170) — ajout de `provisioning/windows/finaliser_projet_ccw.ps1` qui, à partir du seul `-NomProjet`, dérive le service/dossier/config (même logique qu'`ajouter_projet_ccw.ps1`), vérifie leur existence, demande `TOPIC_NTFY` et l'écrit directement dans le config (remplacement ciblé du placeholder `###TOPIC_NTFY_A_DEFINIR###`, reste du fichier préservé en UTF-8 sans BOM), rappelle avec une pause la marche à suivre pour créer le token GitHub dédié, puis **appelle** `mettre_a_jour_tokens_ccw.ps1` (pas de duplication) pour la saisie masquée + pose des tokens + redémarrage + vérif des logs, et conclut par un résumé ; `mettre_a_jour_tokens_ccw.ps1` gagne un paramètre `-NomLog` pour vérifier le bon log de service (`ccw-<nom>-service.log`) ; les rappels d'`ajouter_projet_ccw.ps1` (en-tête + fin de script) et le §16 pointent désormais vers cette commande unique au lieu des 3 étapes dispersées. Non exécuté contre une VM réelle (test manuel par Alain).

## 19 juillet 2026 — issue #172

§11 « Conventions de code » : **règle BOM UTF-8 obligatoire pour tout script `.ps1`** (issue #172) — ajout du BOM (`EF BB BF`) manquant sur `ajouter_projet_ccw.ps1` (#170) et `mettre_a_jour_tokens_ccw.ps1` (#168), qui plantaient sinon sous Windows PowerShell 5.1 avec des `UnexpectedToken` en cascade sur les accents (même signature que #151) ; règle généralisée en §11 + rappel en tête du §16 pour prévenir la récidive (`provisionner.ps1` déjà OK depuis #151).

## 19 juillet 2026 — issue #170

§16 « Agent Windows CCW » : **généralisation multi-projets de CCW** (issue #170) — ajout de `provisioning/windows/ajouter_projet_ccw.ps1` (un clone + un config `configs\<nom>-ccw.conf` + un service NSSM `CCW-Watcher-<NomProjet>` dédiés par projet, sur le modèle des watchers CCL ; paramétrable `-NomProjet`/`-Depot`, idempotent, `watcher.py` inchangé) ; documentation du modèle « un service par projet » et de la **règle d'expiration alignée** des tokens (un token fine-grained dédié par dépôt, mais tous à la même échéance ≈ 17 octobre 2026) ; commande exacte d'instanciation de Scrabble et marche à suivre pour créer son token dédié (Repository access → Scrabble uniquement, Issues read/write + Metadata read-only).

## 19 juillet 2026 — issue #169

§16 « Agent Windows CCW » : ajout de la sous-section **§16.1 Maintenance périodique (renouvellement à 90 jours)** (issue #169) — runbook séquentiel consolidé pour la fenêtre de maintenance d'octobre 2026 : tableau de repères de dates (install **2026-07-19**, expiration Windows **2026-10-17**, token GitHub aligné ~90 j mais non stocké), puis procédure en 3 étapes renvoyant aux scripts existants — vérifier (`verifier_expiration_ccw.py`), recréer la VM (`creer_vm_ccw.py --recreate` + ré-attacher un ISO frais + `lancer_provisioning.py`), renouveler les tokens (`mettre_a_jour_tokens_ccw.ps1`) — sans dupliquer le détail technique déjà présent dans le §16.

## 19 juillet 2026 — issue #168

§16 « Agent Windows CCW » : ajout du script `provisioning/windows/mettre_a_jour_tokens_ccw.ps1` (issue #168) — renouvellement des tokens `GH_TOKEN`/`CLAUDE_CODE_OAUTH_TOKEN` du service `CCW-Watcher` sans reconstruire à la main la chaîne `AppEnvironmentExtra` : saisie masquée (`Read-Host -AsSecureString`), séparateur `` `n`` impératif entre les deux paires (un espace corrompt `GH_TOKEN` → « Bad credentials »), `nssm set`/`nssm restart`, puis affichage automatique des 10 dernières lignes de `logs\ccw-service.log` pour confirmer l'absence d'erreur d'auth.

## 19 juillet 2026 — issue #167

§16 « Agent Windows CCW » : alerte d'expiration de l'éval 90 jours (issue #167) — ajout de `provisioning/windows/eval-expiration.json` (date d'installation **2026-07-19**, expiration **2026-10-17**) et du script `provisioning/windows/verifier_expiration_ccw.py` (côté Linux : calcule les jours restants, alerte + code de sortie 2 à ≤ 10 j, sinon confirmation calme ; `python3 provisioning/windows/verifier_expiration_ccw.py`) ; rappel `cron` + `ntfy` hebdomadaire proposé mais laissé à l'activation d'Alain.

## 19 juillet 2026 — issue #166

§16 « Agent Windows CCW » : ajout du script `provisioning/windows/demarrer_ccw.sh` (issue #166), wrapper de démarrage de la VM `CCW-Build` depuis CCL (headless par défaut, `--gui`/`--fenetre` pour une fenêtre, `--status` pour l'état sans rien démarrer).

## 19 juillet 2026 — issue #153

§3 « Créer une issue » : ajout d'une note sur la **convention de présentation côté Claude Chat** pour l'envoi en lot (issue #153) — quand Claude Chat prépare plusieurs issues, il les présente toutes à la suite dans un seul bloc de code (pas un bloc par issue) pour un copier-coller en un clic.

## 18 juillet 2026 — issue #149

§16 « Agent Windows CCW » : `REP_TRAVAIL` généré par `provisionner.ps1` pointe désormais vers le **chemin UNC** `\\VBOXSVR\CCW_Share` (et non la lettre automontée `$LettrePartage`), seul accessible au service `CCW-Watcher` tournant sous LocalSystem (issue #149, suite #148) ; `$LettrePartage` conservé pour référence mais plus utilisé pour construire `REP_TRAVAIL`.

## 18 juillet 2026 — issue #148

le watcher CCW tourne comme **vrai service Windows** enregistré via NSSM (issue #148, suite #147) — `provisionner.ps1` installe `NSSM.NSSM` (winget) et enregistre le service `CCW-Watcher` (`SERVICE_AUTO_START` + `AppExit Default Restart` + `AppRestartDelay 5000`, stdout/stderr → `logs\ccw-service.log`, idempotent via `nssm stop`/`remove`), en remplacement de l'ancienne tâche planifiée `-AtLogOn` qui ne redémarrait pas au boot sans session ; équivalent direct des services systemd du §13.

## 18 juillet 2026 — issue #147

provisioning **phase 2** (issue #147, suite #146) — ajout de `provisioning/windows/provisionner.ps1` (installe l'outillage dans la VM via winget + Claude Code natif, clone le dépôt, écrit `ccw.conf`, enregistre la tâche planifiée `CCW-Watcher`) et `lancer_provisioning.py` (pousse/exécute ce script depuis CCL via `VBoxManage guestcontrol`) ; `watcher.py` inchangé (portable, `LABEL` paramétrable) ; limite Task Scheduler vs `Restart=always` documentée.

## 18 juillet 2026 — issue #146

ajout du §16 et du label `for-windows` (issue #146) : provisioning phase 1 de la VM Windows CCW (`provisioning/windows/creer_vm_ccw.py` + `autounattend.xml`) destinée aux builds .exe délégués par CCL.

## 17 juillet 2026 — issues #135, #101, #97 (suite #96)

Bridge_Agent v1, 4 projets actifs. §3 « Créer une issue » : ajout de l'**envoi en lot** (issue #135) — coller plusieurs blocs `#Titre:` à la suite dans le même corps déclenche le mode lot (bouton « Envoyer le lot (N issues) »), chaque bloc étant envoyé en séquence comme une issue indépendante (avec ses `PROJET`/`TIMEOUT`/`MODELE` optionnels), sans validation intermédiaire, suivi d'un résumé listant le résultat de chacune. Ajout du projet `ecole` (AlainDelree/Ecole, ~/Ecole) aux tableaux §2 et §7 (issue #101). Section 15 « Chef + Specs MVC » : champ `SPECS` (pluriel, minuscules, combinable en une ligne) — correction du champ `SPEC` introduit par erreur (issue #97, suite #96).
