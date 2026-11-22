# Issue #917 — Interface new_issue : voile de veille, réveil au clic, rafraîchissement régulier du projet sélectionné et copie du rapport fiabilisée, avec réglages modifiables

Suite de l'étude en lecture #916 (elle-même suite à l'abandon de #915) :
aucun rechargement périodique de la liste Résultats n'avait jamais existé,
le panneau Infrastructure ne recalculait ses compteurs qu'à partir de la
mémoire locale déjà connue, et la copie du rapport en mode moderne pouvait
rester silencieuse en cas de lenteur ou de session expirée. Décision
d'Alain : ne pas dépendre du flux `/stream` seul, ne pas prolonger
indéfiniment les délais de cache, mais rendre l'état de l'interface visible
et la remettre à jour au premier geste, avec des réglages qu'il ajuste
lui-même.

## 1/2/3 — Veille, réveil et rafraîchissement périodique (nouveau module `static/js/veille.js`)

- **Détection d'inactivité** (mouvement de souris, clic, molette, tactile,
  défilement, clavier — `window`, capture) : après `delaiVeilleMin` minutes
  (défaut 30, 0 désactive), un voile gris semi-opaque
  (`#voile-veille`, `templates/fragments/voile_veille.html`, CSS dans
  `static/css/modales.css`) couvre toute l'interface. Vérifié toutes les 5s,
  purement local (aucun réseau).
- **Pendant la veille** : le rafraîchissement périodique ci-dessous s'arrête
  intégralement (aucun appel GitHub). Les petites requêtes locales
  existantes (battement, `/watchers`, `/issues-inbox/etat`, minuteur 30s du
  panneau Infrastructure) ne sont PAS touchées — elles continuent de tourner
  comme avant cette issue.
- **Réveil** : le premier clic (listener posé directement sur le voile) ou
  la première touche (listener `keydown` en phase de CAPTURE sur `window`,
  `preventDefault`/`stopPropagation` avant que l'élément qui a le focus ne la
  reçoive) est absorbé — aucune action sur ce qui se trouve dessous. Lance
  `resultats.rafraichirSelection(projets sélectionnés)` (nouvelle fonction,
  voir plus bas) + `rafraichirPanneauLateralResultats()` (global existant) +
  `resultatsCoches.precharderVisibles()` (file plafonnée existante, #835).
  Le voile passe à « Mise à jour… », puis : données arrivées → masqué,
  horodatage d'activité réinitialisé, rafraîchissement périodique relancé ;
  délai maximum dépassé (30s) ou échec → état d'erreur explicite + bouton
  « Réessayer » (jamais de disparition silencieuse).
- **Rafraîchissement périodique hors veille** : `resultats.rafraichirSelection`
  (voir plus bas) + panneau Infrastructure, à `intervalleSec` (défaut 60,
  plancher 15 — protège le quota GitHub). Se reprogramme lui-même après
  CHAQUE tentative : succès → délai réglé, échec → attente croissante
  plafonnée à 10 minutes (`prochainDelaiMs`, doublement), jamais d'arrêt
  définitif.
- **Rattrapage à la création d'une issue** (événement SSE `creation_issue`,
  dépôt de fichier ou formulaire — les deux finissent par le même événement
  côté serveur) : rechargement ciblé IMMÉDIAT du projet concerné par
  l'événement, puis un second après `rattrapageSec` (défaut 10s) — en BACKUP
  du flux `/stream`, décision explicite d'Alain de ne plus en dépendre seul.
  Rien pendant la veille (rattrapé au réveil).
- **(Dé)sélection d'un projet dans le filtre pastille Résultats** : un projet
  qui vient d'être sélectionné est rechargé À CE MOMENT
  (`veille.surSelectionChangee`, appelée depuis `app.js::basculerFiltreProjet`/
  `basculerTousLesFiltres` via le pont, débounce 300ms) — jamais pendant
  qu'il était désélectionné.

**Nouvelles fonctions dans `static/js/resultats.js`** (aucune n'a touché aux
chemins existants `rafraichir`/`chargerTimingTous`, qui restent réservés au
↻ complet et au chargement initial, inchangés) :
- `chargerListe` renvoie désormais `{succes}` (en plus de son effet de bord
  habituel) — nécessaire pour que le voile sache si des données ont RÉELLEMENT
  été rattrapées (`chargerListe`/`chargerTimingTous` n'ont jamais levé
  d'exception, les échecs étant déjà signalés par toast).
- `chargerTimingSelection(noms)` : variante de `chargerTimingTous()`
  RESTREINTE à une liste de projets — `chargerTimingTous()` continue, elle,
  de tout recharger (chemins existants inchangés).
- `rafraichirSelection(noms)` : liste + timing d'une sélection de projets,
  SANS les cases cochées (purement local, hors périmètre) ni la purge du
  cache détail (réservée au ↻ explicite) — volontairement plus léger que
  `rafraichir()`. Exposée dans `resultats.dernierSyncMs()` (horodatage brut,
  pour `estSyncAncienne`) et `resultats.rafraichirSelection`.

## 4 — Écrasement d'une issue connue par événement mais pas encore indexée par GitHub (même famille que #634)

Réponse à la question posée par la tâche : **oui**, établi par relecture du
code. `fusionnerChargement` (`resultats.js`, utilisée par `chargerListe`,
donc par le chargement initial, le ↻ ET le nouveau rafraîchissement
périodique) remplaçait INCONDITIONNELLEMENT tout le contenu d'un projet
refetché avec succès par la réponse de `/issues-liste` — contrairement à
`fusionnerTimingProjet` (issue #634), qui protégeait déjà `/issues-en-attente`
de ce même décalage d'indexation `gh issue list` juste après `gh issue
create`. `fusionnerChargement` conserve désormais, pour un projet refetché
AVEC SUCCÈS, une issue absente de la réponse si elle est OUVERTE et RÉCENTE
(nouvelle constante `FENETRE_RECENTE_LISTE_MS` = 2 minutes — plus large que
celle du timing, 30s : un rechargement périodique peut se répéter plusieurs
fois avant que GitHub ne rattrape son retard). Une issue absente et fermée,
ou absente au-delà de cette fenêtre, reste retirée normalement (vraie fin
d'issue).

## 5 — Réglages modifiables, panneau Infrastructure (partie globale)

`templates/fragments/panneau_lateral.html`, nouvelle zone `#pl-zone-veille`
juste après l'interrupteur de son (`#pl-zone-son`) — trois champs numériques
(délai de veille en minutes, intervalle de rafraîchissement en secondes,
délai de rattrapage après création en secondes) + une estimation indicative
du coût GitHub par heure, recalculée à chaque changement d'intervalle ou de
sélection pastille. Stockés via `window.Bridge.persistance`
(`CLES.veilleDelaiMin`/`veilleIntervalleSec`/`veilleRattrapageSec`, nouvelles
clés `bridge_veille_delai_min`/`bridge_veille_intervalle_sec`/
`bridge_veille_rattrapage_sec`) — AUCUN fichier `configs/*.conf`, aucun
mécanisme serveur de réglages globaux. Valeur absente ou invalide → défaut
(`normaliserDelaiVeilleMin`/`normaliserIntervalleRafraichissementSec`/
`normaliserDelaiRattrapageSec`, `static/js/veille.js`). Effet immédiat sans
rechargement de page (le prochain tick périodique est reprogrammé avec la
nouvelle valeur dès le changement).

## 6 — Ancienneté visible de la synchro

`#resultats-derniere-sync` (`app.js::construireBoutonsFiltre`) porte
désormais la classe `.resultats-derniere-sync-ancienne` (rouge, gras —
`static/css/resultats.css`) quand `veille.syncEstAncienne()` répond vrai :
jamais synchronisé, ou plus ancien que trois fois l'intervalle réglé
(`estSyncAncienne`, pure, testée).

## 7 — Copie du rapport fiabilisée

- **Délai maximum par requête** : `static/js/socle/api.js::requete` applique
  désormais un délai par défaut de 30s (`TIMEOUT_DEFAUT_MS`, `AbortController`,
  option `timeoutMs` par appel) à TOUTE requête passée par `api.get/post/
  supprimer` — rafraîchissement comme copie. `ErreurApi.timeout` distingue un
  abandon par délai d'une coupure réseau normale.
- **« Préparation du rapport… »** (`resultats_coches.js::lancerCopie`) :
  affichée dès le clic, AVANT tout réseau, y compris en mode moderne où seule
  l'écriture presse-papier est engagée synchroniquement au clic (#858) — pas
  la préparation du contenu, qui peut rester lente. Nouveau champ optionnel
  `preparation` du contrat `feedback` (`feedbackToast`/`feedbackBadge`).
- **Propagation des vraies erreurs** : `detailIssue` (producteur commun des 3
  variantes de copie) PROPAGE désormais un délai dépassé, une coupure réseau,
  ou une session expirée (page de connexion HTML renvoyée à la place du JSON
  attendu, déjà détectée par `api.js` comme « Réponse non-JSON ») au lieu de
  les avaler en silence vers `''`, qui était alors traité comme « réponse pas
  encore disponible » (message et comportement trompeurs).
- **Bouton « Réessayer »** : `toasts.js` accepte une nouvelle option
  `onReessayer` (`toasts.erreur(texte, comptabilise, {onReessayer})`), rendue
  comme un bouton dans le toast. `signalerEchecCopie`/`envelopperFeedbackEchec`
  (`resultats_coches.js`) la propagent — `copierModerne`/`lancerCopie`
  (repli) fournissent un rappel qui relance exactement la même copie. Pour un
  échec SANS texte de secours (la préparation elle-même a échoué), l'échec
  garde donc toujours un moyen de reprendre l'action.
- Cache des rapports : durée inchangée (1h) — le préchargement déclenché au
  réveil le remplace plutôt que de l'allonger.

## 8 — Panne du serveur de l'interface (bandeau rouge, distinct du voile)

`static/js/app.js::demarrerCycleVie` : l'événement SSE `shutdown` explicite
(Ctrl+C/SIGTERM côté serveur) continue d'afficher l'overlay bloquant
existant `#overlay-arret` (arrêt volontaire, inchangé). `sourceEvents.onerror`
(coupure brutale, serveur tué sans signal) affiche désormais, après le même
délai de 3s qu'avant, un bandeau ROUGE NON bloquant
`#bandeau-connexion-perdue` (`templates/fragments/bandeaux.html`, classe déjà
existante `.bandeau-eval-windows.rouge`) au lieu de l'overlay bloquant —
disparaît automatiquement à `sourceEvents.onopen` (reprise), sans recharger
la page.

## 9 — Journal des événements `/stream`

`app/fin_issue.py::_diffuser` (point UNIQUE de diffusion de tous les
événements `/stream`) écrit, en plus de la diffusion SSE elle-même, une
ligne dans le journal existant `logs/charge_interface.log`
(`mesure_charge_interface.ligne_evenement_stream`, nouvelle fonction : type
d'événement, projet concerné — `None` si absent — et nombre de pages
abonnées) — JAMAIS le contenu de l'événement. Best-effort strict : un échec
d'écriture du journal n'empêche jamais la diffusion SSE (`try/except` dédié).

## Documentation

- `ARCHITECTURE.md` §6.5 (fragments HTML, feuille CSS, liste des modules JS
  par fonctionnalité) et un nouveau paragraphe décrivant `veille.js`.
- Nouveau fichier de domaine `docs/contexte/interface_rafraichissement.md`
  (état actuel du mécanisme complet : flux liste/panneau, écrasement par un
  rechargement, veille/réveil, réglages, copie du rapport, panne serveur,
  journal) — ligne ajoutée à l'index de `CONTEXTE.md` (3969 caractères,
  sous le plafond de 4000).
- `BRIDGE_AGENT_DOC.md` délibérément NON modifié : document CC-facing (workflow
  de création d'issue, labels, modes...), sans section sur les mécanismes
  internes de l'interface web — rien d'existant n'y devient faux, le détail
  pertinent vit dans `docs/contexte/interface_rafraichissement.md` et
  `ARCHITECTURE.md` §6.
- `VERIFICATIONS_MANUELLES.md` : nouvelle section « Veille, réveil,
  rafraîchissement périodique et copie du rapport » (essais (a)-(d) de la
  tâche, plus détection d'activité hors focus explicitement signalée comme
  non vérifiable sans navigateur réel) et mise à jour de la section
  « Bandeaux globaux et cycle de vie » (bandeau rouge vs overlay d'arrêt).

## Tests

- `static/js/tests/veille.test.js` (23 tests) : réglages (défauts/bornes),
  bascule en veille après inactivité, attente croissante plafonnée après
  échec, coût GitHub indicatif, ancienneté de synchro.
- `static/js/tests/resultats.test.js` : 4 nouveaux tests `fusionnerChargement`
  (issue/ouverte-récente conservée, ancienne/fermée retirée, dédoublonnage).
- `static/js/tests/resultats_selection_917.test.js` (5 tests) :
  `rafraichirSelection` restreinte à la sélection, jamais aux autres projets
  (liste ET timing), succès/échec.
- `static/js/socle/tests/api.test.js` (5 tests) : délai maximum, désactivation
  explicite, succès/échec inchangés.
- `static/js/tests/resultats_coches_variantes.test.js` : 2 nouveaux tests
  (« Préparation du rapport… » dès le clic, session expirée → échec réel
  avec bouton Réessayer, jamais confondu avec « réponse pas encore
  disponible »).
- `tests/test_journal_evenements_stream_917.py` (6 scénarios) :
  `ligne_evenement_stream`, `_diffuser` (sans fuite de contenu, nb_abonnes,
  projet absent, best-effort).
- Suite complète rejouée : `node --test static/js/socle/tests/
  static/js/tests/` → 616/616 OK (39 nouveaux tests ajoutés par cette issue,
  répartis entre les fichiers listés ci-dessus) ; `python3 tests/test_*.py`
  → 128/128 OK (dont le nouveau fichier).

## Ce qui n'a pas pu être vérifié sans navigateur

Aucune infrastructure de test de navigateur dans le dépôt. En particulier :
la détection d'activité (souris/clavier/molette) quand la fenêtre n'a PAS le
focus — dépend du système de fenêtrage et du navigateur, pas seulement de ce
code ; le rendu réel du voile/bandeau/bouton Réessayer ; le comportement
RÉEL de `navigator.clipboard.write` face à une session expirée. Essais
manuels ajoutés à `VERIFICATIONS_MANUELLES.md`.

## Hors périmètre, explicitement

- Les cases cochées (`/cases-cochees`) ne sont PAS rechargées par le
  rafraîchissement périodique/réveil (purement local, hors périmètre de
  cette issue — la purge du cache détail reste, elle aussi, réservée au ↻
  explicite).
- Le mode repli (`--lan`, HTTP non-localhost) de la copie du rapport n'a pas
  reçu la même propagation d'erreur que le mode moderne pour sa PRÉCHARGE en
  tâche de fond (`precharger`) — seul le mode moderne, explicitement visé par
  la tâche (« y compris en mode moderne »), en bénéficie pleinement ; le
  délai maximum par requête (point 7) s'applique, lui, aux deux modes
  (générique dans `api.js`).
- `watcher.py` et le comportement des watchers n'ont pas été touchés.
