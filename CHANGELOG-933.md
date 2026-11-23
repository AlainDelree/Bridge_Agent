# Issue #933 — Interface new_issue : rechargement de la liste sur début/fin d'issue, suppression du rafraîchissement régulier et du rattrapage réglables, journal des rechargements

Suite de l'issue #917 : le rafraîchissement périodique à intervalle fixe
qu'elle avait ajouté n'empêchait pas le symptôme observé (une issue tout
juste créée pouvait rester absente de la liste Résultats plusieurs secondes
après le DÉBUT de son traitement, alors que le badge du projet et les
compteurs du panneau Infrastructure se mettaient bien à jour), sans lien
avec l'intervalle réglé. Essais du 23/11/2026 (00:25-00:35) : le journal
`/stream` montre que chaque création déclenche déjà deux rechargements
(immédiat + ~10s), mais que les événements de début et de fin de traitement
n'en déclenchaient AUCUN — remplacés ici par un rechargement CIBLÉ sur ces
deux événements, et le polling périodique est retiré.

## 1 — Vérification préalable (watcher.py, non modifié)

Relecture de `watcher.py` : `lister_issues()` interroge `gh issue list
--label <label> --state open` une fois par cycle ; `notifier_debut_sse()`
(donc l'événement SSE `debut_issue`) est appelé par `_traiter_issue_synchrone`
juste après l'ACK, pour une issue qui vient d'être retournée par cet appel —
l'hypothèse de l'issue (le début de traitement signale le moment où GitHub
expose l'issue dans `gh issue list`, pas sa création) TIENT. Les événements
`debut_issue`/`fin_issue` (`app/fin_issue.py::_pousser_evenement`) portaient
déjà `{projet, numero}` avant cette issue — aucune modification nécessaire
ni à `watcher.py` ni à l'émission de ces deux événements.

## 2 — Rechargement sur début/fin de traitement (`static/js/veille.js`)

- `debut_issue`/`fin_issue` déclenchent désormais `resultats.chargerListe`
  (liste SEULE, `/issues-liste/<projet>`) du PROJET CONCERNÉ, avec la raison
  (`debut`/`fin`) transmise en requête pour le journal (point 5). Rien
  pendant la veille.
- `fin_issue` arrive deux fois de suite pour une même issue (constat des
  essais) : regroupé côté client (`doitRechargerSurFin`, fenêtre
  `FENETRE_REGROUPEMENT_FIN_MS` = 3s) — un seul rechargement par fenêtre.
- Rattrapage à la création conservé (immédiat + ~10s), mais `rattrapageSec`
  n'est plus un réglage : `RATTRAPAGE_CREATION_SEC` est une valeur FIXE dans
  le code (10s, inchangée).
- Rafraîchissement périodique à intervalle fixe de #917 (et son attente
  croissante après échec, `prochainDelaiMs`) **retiré intégralement**.

## 3 — Réglages retirés du panneau Infrastructure

Section « Veille et rafraîchissement » (`templates/fragments/panneau_lateral.html`,
`#pl-zone-veille`) : « Rafraîchir toutes les (s) » et « Rattrapage création
(s) » retirés, ainsi que l'estimation « ≈ N appel(s) GitHub/h »
(`calculerCoutGithubParHeure`) qui leur était associée. Seul « Veille après
(min) » reste. Les clés localStorage `bridge_veille_intervalle_sec` et
`bridge_veille_rattrapage_sec` (issue #917) ne sont simplement plus lues par
aucun code (`static/js/socle/persistance.js::CLES`) — une valeur déjà
enregistrée par Alain y reste, ignorée sans erreur.

## 4 — Surveillance du flux `/stream`

Sans rafraîchissement périodique, une coupure silencieuse du flux `/stream`
(EventSource qui ne détecte pas la coupure) ne se serait plus vue.
`static/js/veille.js` vérifie désormais toutes les 15s (local, aucun appel
GitHub) l'ancienneté du dernier message reçu sur `/stream`
(`resultats.derniereActiviteStreamMs`, `sse.js::depuisDerniereActiviteMs`).
Seuil retenu : trois fois l'intervalle RÉEL des battements serveur de ce
canal (`app/fin_issue.py::DELAI_PING` = 30s, vérifié par relecture — distinct
du canal `/events` du cycle de vie serveur), soit 90s
(`SEUIL_STREAM_SILENCIEUX_MS`). Au-delà : `resultats.reconnecterStream()`
(ferme/rouvre le canal, purement local) puis un rechargement de la liste
des SEULS projets sélectionnés (raison `flux_silencieux`) — aucun autre
appel GitHub. Suspendu pendant la veille, vérifié explicitement AVANT le
rechargement normal du réveil. `estSyncAncienne` (affichage « sync
HH:MM:SS ») réutilise ce même seuil (90s), faute d'un intervalle réglable
dont dériver un multiple comme avant #933.

## 5 — Journal des rechargements de liste

Choix : réutiliser `logs/charge_interface.log`
(`mesure_charge_interface.py`), déjà le journal de diagnostic de
l'interface (issues #835/#917), plutôt qu'un nouveau fichier. Deux lignes
nouvelles, écrites par `app/issues.py::issues_liste`/`_journaliser_rechargement_liste` :
- `rechargement_liste` (à CHAQUE appel de `/issues-liste/<projet>`) :
  projet, nombre d'issues renvoyées, numéro de la plus récente, durée de
  l'appel GitHub, et la raison transmise par le client en paramètre de
  requête (`?raison=...` — `creation`, `rattrapage`, `debut`, `fin`, `clic`,
  `reveil`, `flux_silencieux`, ou absente pour un appelant antérieur).
- `avertissement_issue_absente` (en plus, seulement quand `raison` vaut
  `debut`/`fin`, que `?numero=...` est transmis, et que ce numéro n'est PAS
  dans la réponse) : projet, numéro, et une ancienneté `age_s` calculée
  depuis `?cree_le=...` (createdAt ISO de l'issue, SI déjà connu du
  navigateur — `store.lireIssue` — jamais recalculé ici par un appel GitHub
  supplémentaire ; `None` si inconnu). Aucune autre action tentée — décision
  d'Alain : voir d'abord, grâce à ce journal, si le rechargement sur
  début/fin suffit, avant d'envisager une ligne provisoire ou une série de
  rattrapages.

Exception documentée à la règle « aucun numéro d'issue » qui s'appliquait
jusqu'ici à ce journal (`mesure_charge_interface.py`, en-tête) : un numéro
d'issue GitHub n'est pas une donnée sensible, et ces deux lignes existent
justement pour objectiver, à l'usage, si le symptôme de l'étude #933
subsiste et d'où il vient.

## Coût en appels GitHub par heure

#917 (rafraîchissement périodique, défaut 60s, 2 appels/cycle/projet
sélectionné) coûtait ≈ 120 appels/h pour UN SEUL projet sélectionné, en
continu, qu'il y ait ou non une issue en cours. #933 ne fait plus AUCUN
appel GitHub en l'absence de transition réelle (création/début/fin) : son
coût suit désormais le nombre d'issues traitées (3 appels `/issues-liste`
par issue — création, rattrapage ~10s, début — plus 1 par fin, groupé en cas
de doublon), jamais un polling continu. Net : coût réduit, sauf débit
d'issues extrêmement élevé (plusieurs dizaines par heure sur un seul
projet), hors du fonctionnement réel observé du bridge.

## Tests

- JS (`node --test static/js/tests/`, `static/js/tests/veille.test.js`
  réécrit) : `doitRechargerSurFin` (regroupement des doublons de
  `fin_issue`), `fautRouvrirStream` (décision de rouvrir le flux selon
  l'ancienneté du dernier message), `estSyncAncienne` (nouveau seuil fixe).
  Fonctions retirées avec leurs tests : `normaliserIntervalleRafraichissementSec`,
  `normaliserDelaiRattrapageSec`, `prochainDelaiMs`, `calculerCoutGithubParHeure`.
- Python (`tests/test_journal_rechargement_liste_933.py`, nouveau) : format
  des deux nouvelles lignes de journal (`mesure_charge_interface.py`), et
  comportement de `app/issues.py::_journaliser_rechargement_liste` (ligne
  systématique, avertissement seulement sur debut/fin + issue absente, âge
  calculé depuis `cree_le` ou `None`, jamais d'exception remontée).
- Non vérifiable sans navigateur réel (voir `VERIFICATIONS_MANUELLES.md`) :
  l'apparition effective d'une ligne au début de traitement sans clic, la
  mise à jour sans clic à la fin, la réouverture réelle du flux `/stream`
  après une coupure silencieuse, et l'absence d'avertissement en usage
  normal dans `logs/charge_interface.log`.

## Fichiers modifiés

`static/js/veille.js` (réécrit), `static/js/resultats.js` (opts
raison/numero/creeLe sur chargerListe/rafraichir/rafraichirSelection,
`derniereActiviteStreamMs`/`reconnecterStream`), `static/js/app.js` (raison
`'clic'` transmise par le bouton ↻), `static/js/socle/persistance.js`
(clés retirées), `templates/fragments/panneau_lateral.html` (réglages
retirés), `app/issues.py` (`_journaliser_rechargement_liste` + paramètres de
requête de `/issues-liste`), `mesure_charge_interface.py` (deux nouvelles
lignes de journal), `static/js/tests/veille.test.js` (réécrit),
`tests/test_journal_rechargement_liste_933.py` (nouveau),
`docs/contexte/interface_rafraichissement.md`, `ARCHITECTURE.md` §6,
`VERIFICATIONS_MANUELLES.md`.
