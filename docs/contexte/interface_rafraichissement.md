# Rafraîchissement de l'interface web — veille, réveil, copie du rapport (issues #917, #933)

État ACTUEL du mécanisme (pas l'historique — voir `CHANGELOG.md` pour le
déroulé des issues #917/#933, et l'étude #916 pour les faits qui ont motivé
#917). Pas de référence courte dans `BRIDGE_AGENT_DOC.md` (document
CC-facing, sans section sur les mécanismes internes de l'interface web) ;
voir plutôt `ARCHITECTURE.md` §6 pour la carte générale du socle web.

## 1. Flux de la liste Résultats et du panneau Infrastructure

- **Chargement initial** (`resultats.js::chargerInitial`) : un seul
  `chargerListe()` (tous les projets, `/issues-liste/<nom>`) + un seul
  `chargerTimingTous()` (tous les projets, `/issues-en-attente/<nom>`), au
  premier affichage de l'onglet Résultats.
- **Canal `/stream`** (SSE, `socle/sse.js`, connecté en permanence par
  `resultats.js::initialiser`) : événements `debut_issue`/`fin_issue`/
  `creation_issue` (ciblés projet+numéro, jamais un rechargement complet) et
  `fichier_recu`/`fichier_refuse`/`case_decochee`. C'est la SEULE source de
  mise à jour qui existait avant l'issue #917.
- **Rattrapages ponctuels existants, inchangés** : retour de masquage de
  l'onglet (`fautResynchroniserApresMasquage`, seuil 30s), reconnexion SSE
  après coupure (`fautResynchroniserApresReconnexionSse`), activation de
  l'onglet Résultats si la dernière synchro est périmée
  (`fautRechargerAOuverture`), bouton ↻ explicite (`rafraichirResultats`,
  `app.js` — recharge TOUS les projets ou le sous-ensemble du filtre pastille
  selon l'état de « Tous », purge aussi le cache détail).
- **Panneau Infrastructure** (`panneau_lateral.js::rafraichirPanneauLateralResultats`,
  minuteur de 30s, `intervalPanneauLateral`) : calcule ses compteurs « en
  cours / en file » UNIQUEMENT à partir de la mémoire locale déjà alimentée
  par ce qui précède (`resumeProjetMonitoring`, `app.js`) — il ne refait
  JAMAIS lui-même un appel GitHub pour ces compteurs ; son fetch réseau
  propre (`/watchers`, `/issues-inbox/etat`) est purement LOCAL (pas GitHub).
  Ce minuteur de 30s n'est PAS touché par la veille : il continue de tourner
  même pendant la veille (petite requête locale existante).
- **Rechargement de la liste du PROJET CONCERNÉ sur événement** (issue #933,
  `static/js/veille.js`) : à la création d'une issue (`creation_issue`,
  inchangé depuis #917 hors durée fixe du rattrapage), et DÉSORMAIS aussi au
  DÉBUT et à la FIN de son traitement (`debut_issue`/`fin_issue`) — voir §3.
  Plus aucun rechargement PÉRIODIQUE (retiré par #933, voir §3 et §4) : seuls
  ces événements déclenchent un vrai appel GitHub.

Avant l'issue #917, aucun rechargement périodique ni déclenché par
début/fin de traitement n'avait jamais existé (constat de l'étude #916) : un
flux `/stream` resté silencieux (cas réel observé le 22/11/2026, 22 minutes
sans requête ciblée après un `debut_issue`) laissait la liste périmée
jusqu'au prochain rattrapage ponctuel ou au ↻ manuel. #917 avait comblé ce
manque par un POLLING à intervalle fixe ; l'étude #933 (essais du
23/11/2026) a montré que ce polling n'empêchait pas le symptôme (une ligne
tout juste créée pouvait rester absente plusieurs secondes après le début de
son traitement, sans lien avec l'intervalle réglé) : il a donc été remplacé
par un rechargement déclenché par les événements eux-mêmes, moins coûteux en
appels GitHub (voir §3) et mieux corrélé à la cause réelle.

## 2. Écrasement d'une issue connue par événement mais pas encore indexée par GitHub

Deux endroits distincts, même famille de problème (décalage d'indexation de
`gh issue list`/`gh issue view` juste après `gh issue create`) :

- **Timing** (`/issues-en-attente`, issue #634) : `fusionnerTimingProjet`
  (`resultats.js`) conserve l'entrée de timing d'une issue OUVERTE et
  RÉCENTE (< `FENETRE_RECENTE_TIMING_MS` = 30s) absente de la réponse.
- **Liste complète** (`/issues-liste`, issue #917 point 4, établi par
  relecture du code à la demande de l'étude #916 : OUI, un rechargement
  complet pouvait effacer une telle issue avant ce correctif —
  `fusionnerChargement` remplaçait INCONDITIONNELLEMENT le contenu d'un
  projet refetché avec succès) : `fusionnerChargement` (`resultats.js`)
  conserve désormais, pour un projet refetché AVEC SUCCÈS, une issue absente
  de la réponse si elle est OUVERTE et RÉCENTE (< `FENETRE_RECENTE_LISTE_MS`
  = 2 min). Une issue fermée, ou absente au-delà de cette fenêtre, est
  retirée normalement (vraie fin d'issue).

Ce mécanisme reste la DERNIÈRE ligne de défense : §3 et §9 ci-dessous
décrivent ce que l'issue #933 ajoute en AMONT (rechargement sur
début/fin + journal) pour réduire le nombre de cas où il doit intervenir, et
pour objectiver, à l'usage, s'il en reste.

## 3. Veille et réveil (`static/js/veille.js`)

- **Détection d'inactivité** : écouteurs `mousemove`/`mousedown`/`wheel`/
  `touchstart`/`scroll`/`keydown` (capture) sur `window`, mise à jour d'un
  horodatage. Vérifié toutes les 5s (local, aucun réseau). Après
  `delaiVeilleMin` minutes sans activité (défaut 30, réglage 0 = veille
  désactivée — SEUL réglage de ce module depuis #933, voir §4), le voile
  gris `#voile-veille` (`templates/fragments/voile_veille.html`) s'affiche.
  **Non vérifié sans navigateur réel** : si ces écouteurs se déclenchent bien
  quand la fenêtre n'a pas le focus (dépend du système de fenêtrage/
  navigateur, pas seulement de ce code) — voir `VERIFICATIONS_MANUELLES.md`.
- **Pendant la veille** : AUCUN rechargement réseau déclenché par événement
  (création/début/fin ci-dessous) ne part — rattrapés au réveil. La
  surveillance du flux `/stream` (§3bis) est elle aussi suspendue. Les
  requêtes locales existantes (battement `/heartbeat`, `/watchers`,
  `/issues-inbox/etat`, panneau Infrastructure) ne sont PAS arrêtées.
- **Réveil** : le voile absorbe le premier clic (listener posé directement
  sur `#voile-veille`) ou la première touche (listener `keydown` en phase de
  capture sur `window`, `preventDefault`/`stopPropagation` avant que
  l'élément focus ne la reçoive). Déclenche D'ABORD la vérification du flux
  `/stream` (§3bis, réouverture locale si besoin — aucun appel GitHub), PUIS
  `resultats.rafraichirSelection(projets sélectionnés, {raison: 'reveil'})` +
  le panneau Infrastructure + `resultatsCoches.precharderVisibles()` (file
  plafonnée existante, issue #835). Le voile passe à « Mise à jour… », puis :
  - données arrivées → voile masqué, horodatage d'activité réinitialisé,
    surveillance du flux relancée ;
  - délai maximum dépassé (30s, `DELAI_MAX_REVEIL_MS`) ou échec → état
    d'erreur explicite + bouton « Réessayer », jamais de disparition
    silencieuse.
- **Rechargement sur DÉBUT et FIN de traitement** (événements SSE
  `debut_issue`/`fin_issue`, issue #933 point 2 — REMPLACE le
  rafraîchissement périodique de #917, retiré) : `resultats.chargerListe`
  (liste SEULE, pas le timing — déjà géré en ciblé par
  `resultats.js::surDebutIssue`/`surFinIssue`) du PROJET CONCERNÉ par
  l'événement, raison `'debut'`/`'fin'` transmise au journal (§9). Pour
  `fin_issue`, watcher.py poste l'événement DEUX FOIS de suite pour une même
  issue (constat de l'étude #933) : regroupé côté client
  (`doitRechargerSurFin`, fenêtre `FENETRE_REGROUPEMENT_FIN_MS` = 3s) — un
  seul rechargement. Les deux événements portaient déjà `{projet, numero}`
  (vérifié par relecture de `app/fin_issue.py`, aucune modification
  nécessaire — voir le rapport de l'issue #933). Rien pendant la veille.
- **Rattrapage à la création d'une issue** (événement SSE `creation_issue`,
  dépôt de fichier ou formulaire — les deux finissent par le même événement,
  voir `app/fin_issue.py::emettre_creation_issue`) : rechargement ciblé
  IMMÉDIAT du projet concerné par l'événement (pas forcément celui
  sélectionné dans le filtre), puis un second après
  `RATTRAPAGE_CREATION_SEC` (10s, valeur FIXE dans le code depuis #933 — ce
  n'est plus un réglage, voir §4) — en BACKUP du flux `/stream`. Rien pendant
  la veille.
- **(Dé)sélection d'un projet dans le filtre pastille** : un projet qui vient
  d'être sélectionné est rechargé À CE MOMENT (`veille.surSelectionChangee`,
  appelée depuis `app.js::basculerFiltreProjet`/`basculerTousLesFiltres` via
  le pont, débounce 300ms) — jamais pendant qu'il était désélectionné.

### 3bis. Surveillance du flux `/stream` (issue #933 point 4, corrigée par #937)

Sans rafraîchissement périodique, une coupure SILENCIEUSE du flux `/stream`
(EventSource qui ne détecte pas la coupure, ex. proxy/tunnel qui l'absorbe
sans déclencher `onerror`) ne se verrait plus. `static/js/veille.js` vérifie
donc, toutes les 15s (local, aucun appel GitHub tant que rien n'est anormal),
l'ancienneté du dernier message reçu sur CE canal (événement OU battement
serveur — `sse.js::depuisDerniereActiviteMs`, exposé par
`resultats.derniereActiviteStreamMs()`). Seuil retenu : **trois fois
l'intervalle réel des battements serveur**, soit `SEUIL_STREAM_SILENCIEUX_MS`
= 3 × 30s = 90s — l'intervalle de 30s est celui de `app/fin_issue.py::DELAI_PING`
(canal `/stream` lui-même, PAS le canal `/events` du cycle de vie serveur,
dont le heartbeat JS suit sa propre logique inchangée dans `static/js/app.js`
— vérifié par relecture avant de fixer ce seuil).

**Nature du battement (issue #937)** : AVANT ce correctif, le battement de
`app/fin_issue.py` (`yield ": ping\n\n"`) était un simple COMMENTAIRE du
protocole SSE (ligne commençant par `:`) — EventSource ne transmet JAMAIS une
telle ligne à un gestionnaire JavaScript, qui ne comptait donc jamais comme
une activité réelle, même un flux parfaitement sain. Il est désormais un
ÉVÉNEMENT SSE NOMMÉ (`yield "event: battement\ndata: {}\n\n"`), écouté côté
client par `sse.js` (gestionnaire `battement`, sans AUCUN effet visible —
seule la mise à jour de l'horodatage d'activité, commune à tout événement,
compte) : un flux sain sans ÉVÉNEMENT métier pendant 90s n'est donc plus
jugé silencieux à tort.

**Grâce/réouverture, pas de déclenchement en boucle (issue #937)** :
`fautRouvrirStream` seul (ancienneté du dernier message ≥ seuil, ou valeur
absente) répond « oui » dans deux cas qui ne sont PAS un vrai silence : juste
après le chargement de la page (aucune ouverture encore confirmée) et juste
après une fermeture/réouverture EXPLICITE décidée par cette même
surveillance (l'ouverture n'a pas encore eu le temps d'être confirmée) — ce
second cas est même auto-entretenu sans garde-fou : rouvrir détruit la
tentative de connexion en cours avant qu'elle n'ait pu réussir, qui reparaît
alors « jamais ouverte » à la vérification suivante (15s plus tard), d'où une
boucle fermeture/réouverture/rechargement toutes les 15s observée le
23/11/2026 juste après un redémarrage de l'interface — et un retard de plus
d'une minute avant la première ouverture confirmée, le temps que la boucle
elle-même cesse de l'empêcher. `veille.js::fautDeclarerStreamSilencieux`
ne déclare donc le silence que si, EN PLUS, un délai de grâce — le même seuil
de 90s, réarmé à la connexion initiale ET à chaque réouverture explicite
(`referenceSilenceStreamMs`) — est lui aussi écoulé.

Au-delà de ces deux conditions : `resultats.reconnecterStream()` (ferme puis
rouvre le canal `/stream`, purement local), `resultats.journaliserReouvertureStream()`
(POST `/journal-reouverture-stream`, best-effort, voir §9bis) puis, UNE SEULE
FOIS par épisode de silence (`doitRechargerListePourSilence`,
`episodeSilenceStreamSignale` remis à faux dès que le flux redonne signe de
vie — issue #937 point 3, pour limiter le coût si le flux reste réellement
muet) : `resultats.chargerListe(projets sélectionnés, {raison: 'flux_silencieux'})`.
AUCUN autre appel GitHub. Suspendu pendant la veille ; vérifié explicitement
au réveil, AVANT le rechargement normal (voir ci-dessus) — le réveil, comme
le chargement de la page, réarme aussi le délai de grâce.

## 4. Réglage (modifiable par Alain, sans rechargement de page)

Panneau Infrastructure, partie GLOBALE, juste après l'interrupteur de son
(`templates/fragments/panneau_lateral.html`, zone `#pl-zone-veille`) :

| Réglage | Clé `localStorage` (via `window.Bridge.persistance`) | Défaut | Borne |
|---|---|---|---|
| Délai avant veille (min) | `bridge_veille_delai_min` | 30 | 0 désactive la veille |

Valeur absente ou invalide → défaut (`normaliserDelaiVeilleMin`,
`static/js/veille.js`). Préférence LOCALE AU NAVIGATEUR, une seule valeur
pour toute l'interface (jamais par projet) — aucun fichier `configs/*.conf`,
aucun mécanisme serveur.

**Retirés par l'issue #933** : « Rafraîchir toutes les (s) »
(`bridge_veille_intervalle_sec`) et « Rattrapage création (s) »
(`bridge_veille_rattrapage_sec`), ainsi que le rafraîchissement périodique
qu'ils pilotaient et l'estimation « ≈ N appel(s) GitHub/h » qui leur était
associée (`calculerCoutGithubParHeure`, `#pl-veille-cout`) — remplacés par le
rechargement sur événements décrit au §3. Une valeur déjà enregistrée par
Alain sous ces deux clés localStorage n'est simplement plus lue par aucun
code (aucune purge nécessaire, aucune erreur).

## 5. Ancienneté visible de la synchro

L'affichage « sync HH:MM:SS » près du ↻ (`#resultats-derniere-sync`,
`app.js::construireBoutonsFiltre`) se colore (`.resultats-derniere-sync-ancienne`,
rouge) quand `veille.syncEstAncienne()` répond vrai : jamais synchronisé, ou
plus ancien que `SEUIL_STREAM_SILENCIEUX_MS` (`estSyncAncienne`, 90s — depuis
#933, même seuil que la surveillance du flux §3bis ; plus aucun réglage
d'intervalle dont il aurait pu rester un multiple). Recalculé à chaque
reconstruction de cette barre (chaque rechargement de liste).

## 6. Copie du rapport (case à cocher / badges ✅/Diff/All)

- **Délai maximum par requête** (`static/js/socle/api.js::requete`,
  `TIMEOUT_DEFAUT_MS` = 30s, `AbortController`) : s'applique à TOUTE requête
  passée par `api.get/post/supprimer` — rafraîchissement comme copie.
  `err.timeout` distingue un abandon par délai d'une coupure réseau normale.
- **« Préparation du rapport… »** (`resultats_coches.js::lancerCopie`) :
  affichée dès le clic, AVANT tout réseau — y compris en mode moderne, où
  seule l'ÉCRITURE presse-papier est engagée synchroniquement au clic
  (`copierModerne`, issue #858), pas la préparation du contenu (fetch
  `/issue`, `/diff`, `/inventaire-commit`), qui peut rester lente.
- **Toute erreur, de n'importe quelle nature** (délai dépassé, coupure
  réseau, OU une session expirée qui renvoie la page de connexion HTML au
  lieu du JSON attendu — `detailIssue` PROPAGE désormais ces erreurs au lieu
  de les avaler en silence vers `''`, qui était traité comme « réponse pas
  encore disponible ») ouvre la fenêtre de repli existante (`toasts.erreur`,
  zone `texteSecours` si un texte a pu être produit) ou, à défaut de texte,
  un message d'erreur explicite avec un bouton « Réessayer »
  (`toasts.js::definirContenuToast`, option `onReessayer`) — jamais de
  silence, jamais une simple lenteur confondue avec un échec.
- **Cache des rapports** : durée inchangée (`AGE_MAX_TEXTE_PREPARE_MS` = 1h,
  `resultats_coches.js`) — le préchargement déclenché au réveil
  (`resultatsCoches.precharderVisibles`) le remplace plutôt que de
  l'allonger.

## 7. Panne du serveur de l'interface (bandeau rouge, distinct du voile)

`static/js/app.js::demarrerCycleVie` (canal `/events`, cycle de vie serveur,
inchangé pour le reste) :

- Événement SSE `shutdown` explicite (Ctrl+C/SIGTERM côté serveur,
  `app/cycle_vie.py`) → overlay bloquant existant `#overlay-arret`
  (inchangé, nécessite un rechargement manuel) — arrêt VOLONTAIRE.
- `sourceEvents.onerror` (coupure brutale, serveur tué sans signal) → après
  3s (anti micro-freeze), bandeau ROUGE non bloquant
  `#bandeau-connexion-perdue` (`templates/fragments/bandeaux.html`, classe
  `.bandeau-eval-windows.rouge` déjà existante) — disparaît automatiquement
  à `sourceEvents.onopen` (reprise), sans recharger la page. Distinct du
  voile gris de veille (lequel ne signale jamais une panne serveur).

## 8. Journal des événements `/stream`

`app/fin_issue.py::_diffuser` (point UNIQUE de diffusion de tous les
événements `/stream` : `debut_issue`, `fin_issue`, `creation_issue`,
`fichier_recu`, `fichier_refuse`, `case_decochee`) écrit, en plus de la
diffusion SSE elle-même, une ligne dans `logs/charge_interface.log`
(`mesure_charge_interface.ligne_evenement_stream` : type d'événement, projet
concerné — `None` si l'événement n'en porte pas — et nombre de pages
actuellement abonnées) — JAMAIS le contenu de l'événement (titre, labels,
timing, fichier, motif). Best-effort strict : un échec d'écriture du journal
n'empêche jamais la diffusion SSE. `debut_issue`/`fin_issue` portent déjà
`{projet, numero}` dans le message SSE lui-même (vérifié par l'issue #933,
aucune modification nécessaire) — seule cette ligne de journal-ci n'inclut
pas le numéro, par choix antérieur (#917) : voir §9 pour le journal qui, lui,
en a besoin.

## 9. Journal des rechargements de liste (issue #933 point 5)

Réutilise le MÊME journal que le §8 ci-dessus (`logs/charge_interface.log`,
`mesure_charge_interface.py`) plutôt qu'un nouveau fichier : c'est déjà le
journal de diagnostic de l'interface, avec sa rotation et son usage établis
pour corréler exactement ce genre de décalage (voir l'étude #916/#933).

À CHAQUE appel de `app/issues.py::issues_liste` (route `/issues-liste/<nom>`,
quel que soit le déclencheur), une ligne `rechargement_liste`
(`mci.ligne_rechargement_liste`) : projet, nombre d'issues renvoyées, numéro
de la plus récente (`None` si la liste est vide), durée de l'appel GitHub
(`_lister_issues_labels`, en secondes), et la `raison` transmise par le
client en paramètre de requête (`?raison=...` — `creation`, `rattrapage`,
`debut`, `fin`, `clic`, `reveil`, ou `flux_silencieux` pour une réouverture
du flux §3bis ; `None` si l'appelant ne la transmet pas, ex. un appel
antérieur à #933).

Quand `raison` vaut `debut` ou `fin` ET que le client transmet aussi
`?numero=...` (l'issue qu'il attendait), si ce numéro n'est PAS dans la
réponse : une seconde ligne `avertissement_issue_absente`
(`mci.ligne_avertissement_issue_absente`) — projet, numéro, et une
ancienneté `age_s` calculée à partir de `?cree_le=...` (createdAt ISO de
cette issue, SI le navigateur le connaît déjà localement — `store.lireIssue`,
jamais recalculé ici par un appel GitHub supplémentaire ; `None` si inconnu).
Exception documentée à la règle « aucun numéro d'issue » du reste de ce
journal (§8 inclus) — un numéro n'est pas une donnée sensible, et ces deux
lignes existent justement pour objectiver, à l'usage, si le symptôme de
l'étude #933 (ligne absente au début/à la fin de traitement) subsiste et
d'où il vient : aucune autre action n'est tentée automatiquement en réponse
à cet avertissement (pas de ligne provisoire, pas de série de rattrapages —
décision d'Alain, voir le rapport de l'issue #933).

## 9bis. Journal des réouvertures du flux `/stream` (issue #937 point 4)

Réutilise le MÊME journal que les §8/§9 ci-dessus. Une ligne `reouverture_stream`
(`mci.ligne_reouverture_stream`, POST `/journal-reouverture-stream`,
`app/charge_interface.py::route_reouverture_stream`) est écrite par le
serveur CHAQUE fois que la surveillance du flux (§3bis) décide de le rouvrir
— y compris quand ce n'est PAS la première réouverture de l'épisode de
silence en cours et qu'aucun rechargement de liste n'en découle (issue #937
point 3) : seule la décision de rouvrir compte ici, pas celle de recharger.
Champ unique au-delà du type/horodatage : `age_dernier_message_ms`,
l'ancienneté EN MILLISECONDES du dernier message reçu sur `/stream` au
moment de la décision côté navigateur (`None` si aucune activité n'avait
encore été enregistrée, ex. juste après le chargement de la page). Route
purement LOCALE (aucun appel GitHub), best-effort strict comme le reste de
ce journal — sert à juger, à l'usage, si cette surveillance se déclenche à
tort (voir le rapport de l'issue #937).
