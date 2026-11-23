# Issue #943 — Interface new_issue : la sélection d'une issue saute à la première ligne à chaque rechargement de la liste (zone de détail et panneau d'actions qui changent d'issue seuls)

Suite de l'issue #933 (rechargement de la liste du projet concerné à la
création, au début ET à la fin de traitement d'une issue, en plus des ↻, des
retours d'onglet et des rattrapages) : Alain constatait qu'une issue ouverte
par double-clic dans la zone de détail « s'ouvre puis se referme », ou est
remplacée par une autre quelques secondes plus tard — le titre du panneau
Infrastructure (« Actions — <projet> #<numéro> ») changeant d'issue en même
temps. Traitée après la fusion de l'issue #940 (garde du focus d'une case à
cocher, même fonctions mais défaut distinct), comme demandé.

## Cause confirmée à la lecture du code

`static/js/app.js::executerRenduListeIssues` (corps réel de
`rendreListeIssues`, extrait par #940 pour que le rendu forcé au plafond de
la garde #878 ne repasse pas par elle) reconstruit `#liste-issues` à partir
de rien à chaque rendu complet, puis appelait INCONDITIONNELLEMENT
`selectionnerPremiereVisible()` quand `reset=true` — paramètre TOUJOURS vrai,
son seul appelant (`appliquerListeIssues`) ne le passant jamais autrement.
`appliquerListeIssues` est à son tour le seul appelant de `rendreListeIssues`,
lui-même appelé par `static/js/resultats.js::rendreListeComplete` à CHAQUE
rendu complet : rechargement réseau (↻, réveil, flux silencieux) ET,
depuis #933, création/début/fin de traitement d'une issue et retour d'onglet
(5 appelants recensés par relecture complète de `resultats.js`, listés plus
bas). `selectionnerPremiereVisible()` abandonne la sélection courante
(`projetCourant`/`numeroCourant`) pour la première ligne visible — y compris
quand l'issue déjà sélectionnée (ouverte au double-clic) est toujours
présente et visible. Le panneau Infrastructure
(`panneau_lateral.js::rendrePanneauLateralActions`, via
`obtenirIssueSelectionnee`) lit directement `projetCourant`/`numeroCourant` :
il suivait donc, lui aussi, ce saut — avec le risque qu'un de ses boutons
(ex. « Interrompre et relancer ») s'applique à une autre issue que celle crue
sélectionnée. Hypothèse de l'issue CONFIRMÉE telle que décrite.

### Appelants recensés

- `rendreListeIssues` / `executerRenduListeIssues` : UN SEUL appelant,
  `appliquerListeIssues` (`static/js/app.js`), toujours avec `reset=true`.
  `appliquerListeIssues` est à son tour appelée par
  `resultats.js::rendreListeComplete`, elle-même appelée par 5 endroits —
  TOUS des rendus complets où la décision « conserver si toujours présente et
  visible, sinon première ligne » s'applique : `chargerListe` (rechargement
  réseau — ↻, réveil, flux silencieux), `surDebutIssue` (issue apparue sans
  être connue avant), `surFinIssue` (repli si l'issue n'était pas déjà
  connue), `surCreationIssue` (apparition d'une issue créée), et
  `onActiverOnglet` (retour d'onglet, réaffichage immédiat depuis le store).
  Aucun de ces 5 appelants n'a besoin de réinitialiser la sélection : la
  conservation devient donc le comportement de `rendreListeIssues` lui-même,
  sans toucher à ses appelants.
- `selectionnerPremiereVisible` : appelée directement par
  `basculerFiltreOuvriers`, `basculerFiltreProjet` et
  `basculerTousLesFiltres` (`static/js/app.js`) — UNIQUEMENT si la ligne
  sélectionnée devient masquée par le nouveau filtre — et par
  `restaurerSelectionApresRendu` (nouvelle fonction, voir ci-dessous) en
  repli. Les trois premiers DOIVENT réinitialiser la sélection dans ce cas
  précis (changement de contexte voulu par l'utilisateur) : comportement
  déjà correct, non modifié par ce correctif — ils ne reconstruisent pas la
  liste, ils (dé)masquent des lignes existantes.

## Solution retenue

Remplacement, dans `executerRenduListeIssues`, de l'appel inconditionnel à
`selectionnerPremiereVisible()` par un appel à `restaurerSelectionApresRendu()`
(nouvelle fonction, `static/js/app.js`) :

- Si une issue est sélectionnée (`projetCourant`/`numeroCourant` non nuls) ET
  qu'elle est toujours présente dans la liste rafraîchie (`trouverLigneIssue`)
  ET que sa ligne reconstruite n'est pas masquée (`style.display !== 'none'`,
  posé par `appliquerFiltresListe` juste avant) : on se contente de remarquer
  cette ligne (classe `.selectionnee`) et de rafraîchir le panneau
  Infrastructure (`rafraichirPanneauLateralResultats`, purement local) — SANS
  appeler `selectionnerLigne`/`afficherIssue` : la zone de détail n'est donc
  ni réinitialisée ni rechargée, et `projetCourant`/`numeroCourant` ne
  changent pas (panneau d'actions toujours sur le bon numéro).
- Dans tous les autres cas (aucune sélection, issue disparue de la liste, ou
  devenue masquée) : comportement HISTORIQUE inchangé,
  `selectionnerPremiereVisible()` (issue #261).

Un changement de projet actif ou de filtre pastille ne passe PAS par ce
chemin (voir « Appelants recensés » ci-dessus) : la sélection s'y réinitialise
donc toujours comme avant, volontairement hors périmètre de ce correctif.

Aucun autre fichier touché : ni les déclencheurs de rechargement (#933), ni
le voile de veille, ni la garde du focus d'une case à cocher (#878/#940), ni
`watcher.py`.

## Tests

Logique pure automatisée (`static/js/tests/app_selection_943.test.js`, même
patron bac à sable `vm` que `app_redessin_878.test.js`/
`app_rendu_differe_940.test.js` — charge le VRAI `static/js/app.js`) :
décision de `restaurerSelectionApresRendu`/`executerRenduListeIssues` selon
la présence et la visibilité de l'issue sélectionnée dans la nouvelle liste :

- issue sélectionnée toujours présente ET visible → sélection conservée,
  `projetCourant`/`numeroCourant` inchangés, zone de détail NON touchée,
  aucun fetch de détail (`/issue/...`) déclenché ;
- issue sélectionnée disparue de la nouvelle liste → repli sur la première
  ligne visible (issue #261) ;
- issue sélectionnée toujours dans la liste mais masquée (filtre/quota) →
  même repli ;
- aucune sélection au départ → même repli (non-régression explicite,
  contrainte de la tâche).

`node --test static/js/tests/` : 598 tests, tous au vert (aucune régression
sur la suite existante, en particulier `app_redessin_878.test.js` et
`app_rendu_differe_940.test.js`, dont ce correctif réutilise le même patron
de test).

**Reste à vérifier à la main** (aucune infrastructure de test de navigateur
dans le dépôt) — voir `VERIFICATIONS_MANUELLES.md`, section « Veille, réveil,
rechargement sur événements et copie du rapport », essais (a)/(b)/(c)/(d,
#943) : (a) ouvrir une issue par double-clic puis déposer/laisser terminer
une issue — zone de détail et titre du panneau d'actions restent sur l'issue
ouverte ; (b) même chose en cliquant sur ↻ ; (c) changer de projet/filtre —
la sélection se réinitialise comme avant (non concerné par ce correctif) ;
(d) fermer la sélection puis recharger — repli sur la première ligne visible,
comme avant.

## Fichiers touchés

- `static/js/app.js` — `executerRenduListeIssues` appelle désormais
  `restaurerSelectionApresRendu()` (nouvelle fonction) au lieu de
  `selectionnerPremiereVisible()` inconditionnel ; commentaire de
  `brancherEvenementsLigneIssue` mis à jour en conséquence.
- `static/js/tests/app_selection_943.test.js` (nouveau) — 4 tests de la
  logique pure de décision.
- `docs/contexte/interface_rafraichissement.md` — nouveau §9quater (règle de
  conservation de la sélection), titre mis à jour (+ #943).
- `VERIFICATIONS_MANUELLES.md` — 4 essais manuels (a)/(b)/(c)/(d, #943)
  ajoutés à la section veille/réveil/rechargement, titre mis à jour.
- `CHANGELOG-943.md` (ce fichier, convention #336).
