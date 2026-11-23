# Issue #937 — Interface new_issue : la surveillance du flux /stream ne doit plus recharger la liste en boucle quand le flux est sain

Suite de l'issue #933 : sa surveillance du flux `/stream` (minuteur local
toutes les 15s, seuil de 90s = 3× l'intervalle des battements serveur)
déclenchait en réalité des rechargements `flux_silencieux` toutes les ~15s
juste après un redémarrage de l'interface (essais du 23/11/2026, 16:43:46 à
16:44:35), alors que le serveur répondait normalement — exactement le
rafraîchissement régulier que #933 devait supprimer, et coûteux en appels
GitHub. Deux causes confirmées à la lecture du code, plus une troisième
découverte en creusant la seconde.

## 1 — Cause confirmée : le battement serveur était un commentaire SSE invisible du navigateur

`app/fin_issue.py::stream_fin_issue` émettait, en l'absence d'événement
pendant `DELAI_PING` (30s), `yield ": ping\n\n"` — une ligne de COMMENTAIRE
du protocole SSE (commence par `:`). EventSource ne transmet JAMAIS une
telle ligne à un gestionnaire JavaScript : elle ne comptait donc jamais comme
une activité du flux côté `static/js/socle/sse.js`
(`derniereActiviteMs`/`depuisDerniereActiviteMs`), même pour un flux
parfaitement sain. Un flux sans événement métier pendant plus de 90s — cas
normal en période calme — était donc TOUJOURS jugé silencieux.

Corrigé : le battement est désormais un ÉVÉNEMENT SSE NOMMÉ
(`yield "event: battement\ndata: {}\n\n"`), écouté côté client par un
gestionnaire dédié (`sse.js`, clé `battement` de `sse.stream`) qui ne fait
RIEN d'autre que laisser `creerCanalSse` réarmer l'horodatage d'activité —
aucun effet visible, comme demandé. Testé sous Node (aucun navigateur requis)
via un faux `EventSource` : `static/js/tests/sse.test.js` (6 scénarios) et
`tests/test_journal_reouverture_stream_937.py::scenario_generateur_stream_emet_battement_nomme`
(le générateur Flask produit bien la ligne attendue, jamais plus un
commentaire).

## 2 — Cause confirmée (et approfondie) : l'horodatage de référence n'était jamais réarmé à la grâce/réouverture

`veille.js::fautRouvrirStream` répondait « oui » dès que l'ancienneté du
dernier message était `null` (aucune activité ENCORE confirmée) OU au-delà
du seuil — sans distinguer ce cas de celui d'un VRAI silence. Deux
conséquences :
- juste après le chargement de la page, avant la toute première ouverture
  confirmée du flux, la vérification (toutes les 15s) concluait
  immédiatement au silence ;
- PIRE, en creusant pourquoi l'ouverture avait mis « plus d'une minute » à
  se confirmer après le redémarrage du 23/11/2026 (demandé par l'issue) :
  chaque réouverture forcée (`resultats.reconnecterStream()`) détruit la
  tentative de connexion EventSource en cours avant qu'elle ait pu réussir
  (le serveur venait de redémarrer, l'ouverture réelle prenait plus de 15s).
  La vérification suivante, 15s plus tard, retrouvait donc encore une
  ouverture non confirmée, rouvrait de nouveau, etc. — une boucle
  AUTO-ENTRETENUE qui empêchait elle-même la connexion de jamais réussir,
  jusqu'au rechargement manuel de la page par Alain (qui repart d'un
  `EventSource` neuf, sans l'historique de la boucle).

Corrigé : `veille.js` introduit `fautDeclarerStreamSilencieux(depuisActivite,
depuisReference, seuil)` — ne déclare le silence que si l'ancienneté du
dernier message ET l'ancienneté depuis le dernier point de grâce
(`referenceSilenceStreamMs`, réarmé à CHAQUE (re)démarrage de la
surveillance — connexion initiale, réveil — ET à chaque réouverture
explicite) ont TOUS LES DEUX dépassé le seuil (même valeur, 90s, réutilisée
comme délai de grâce « raisonnable »). Une réouverture explicite ne peut
donc plus se redéclencher avant qu'un seuil complet se soit écoulé, qu'elle
ait réussi ou non — rompt la boucle auto-entretenue.

## 3 — Limitation du coût en cas de vrai problème (point 3 de la tâche)

Si le flux reste réellement muet au-delà du délai de grâce, la surveillance
continue de le rouvrir à chaque vérification (pour donner sa chance à chaque
nouvelle tentative), mais `doitRechargerListePourSilence` + un drapeau
`episodeSilenceStreamSignale` limitent le rechargement de la liste à UNE
SEULE FOIS par épisode de silence — remis à zéro dès que le flux redonne
signe de vie (événement métier ou battement reçu sous le seuil).

## 4 — Nouvelle ligne de journal `reouverture_stream` (point 4 de la tâche)

`mesure_charge_interface.ligne_reouverture_stream` + route locale (aucun
appel GitHub) `POST /journal-reouverture-stream`
(`app/charge_interface.py::route_reouverture_stream`, mêmes règles de
connexion que le reste de l'interface) : une ligne à CHAQUE réouverture
décidée par la surveillance (y compris les réouvertures sans rechargement de
liste, point 3 ci-dessus), portant uniquement `age_dernier_message_ms`
(ancienneté en ms du dernier message au moment de la décision, `None` si
aucune activité n'avait encore été enregistrée) — pour juger à l'usage si
cette surveillance se déclenche à tort. Voir
`docs/contexte/interface_rafraichissement.md` §9bis.

## 5 — Fichiers touchés

- `app/fin_issue.py` : battement nommé (point 1).
- `static/js/socle/sse.js` : gestionnaire `battement` (point 1).
- `static/js/veille.js` : grâce/réouverture + un rechargement par épisode
  (points 2/3), journalisation de la réouverture (point 4).
- `static/js/resultats.js` : `journaliserReouvertureStream` (point 4).
- `mesure_charge_interface.py` + `app/charge_interface.py` + `app/__init__.py` :
  nouvelle ligne de journal et route associée (point 4).
- Tests : `static/js/tests/sse.test.js` (nouveau),
  `static/js/tests/veille.test.js` (7 scénarios ajoutés),
  `tests/test_journal_reouverture_stream_937.py` (nouveau).
- Documentation : `docs/contexte/interface_rafraichissement.md` §3bis/§9bis,
  `ARCHITECTURE.md` §6 (mention courte), `VERIFICATIONS_MANUELLES.md`.

Aucune régression voulue sur création/début/fin, veille/réveil, bandeau de
panne ni `watcher.py` — non touchés ; voir le rapport de clôture pour le
détail des essais manuels restants (délai de grâce et seuil de 90s
difficiles à vérifier intégralement sans navigateur réel ni redémarrage
contrôlé du serveur pendant l'exécution de cette tâche).
