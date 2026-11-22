# Rafraîchissement de l'interface web — veille, réveil, copie du rapport (issue #917)

État ACTUEL du mécanisme (pas l'historique — voir `CHANGELOG.md` pour le
déroulé de l'issue #917, et l'étude #916 pour les faits qui l'ont motivée).
Pas de référence courte dans `BRIDGE_AGENT_DOC.md` (document CC-facing, sans
section sur les mécanismes internes de l'interface web) ; voir plutôt
`ARCHITECTURE.md` §6 pour la carte générale du socle web.

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
  Ce minuteur de 30s n'est PAS touché par la veille (issue #917) : il
  continue de tourner même pendant la veille (petite requête locale
  existante, hors périmètre de cette issue).
- **Rafraîchissement périodique du projet sélectionné** (NOUVEAU, issue
  #917, `static/js/veille.js`) : seul mécanisme qui, lui, refait un vrai
  appel GitHub de façon périodique — voir §3 ci-dessous.

Avant l'issue #917, aucun rechargement périodique de la liste n'avait jamais
existé (constat de l'étude #916) : un flux `/stream` resté silencieux (cas
réel observé le 22/11/2026, 22 minutes sans requête ciblée après un
`debut_issue`) laissait la liste périmée jusqu'au prochain rattrapage
ponctuel ou au ↻ manuel.

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
  = 2 min — fenêtre plus large que celle du timing : un rechargement
  périodique peut se répéter plusieurs fois avant que GitHub ne rattrape son
  retard). Une issue fermée, ou absente au-delà de cette fenêtre, est
  retirée normalement (vraie fin d'issue).

## 3. Veille et réveil (`static/js/veille.js`)

- **Détection d'inactivité** : écouteurs `mousemove`/`mousedown`/`wheel`/
  `touchstart`/`scroll`/`keydown` (capture) sur `window`, mise à jour d'un
  horodatage. Vérifié toutes les 5s (local, aucun réseau). Après
  `delaiVeilleMin` minutes sans activité (défaut 30, réglage 0 = veille
  désactivée), le voile gris `#voile-veille`
  (`templates/fragments/voile_veille.html`) s'affiche. **Non vérifié sans
  navigateur réel** : si ces écouteurs se déclenchent bien quand la fenêtre
  n'a pas le focus (dépend du système de fenêtrage/navigateur, pas
  seulement de ce code) — voir `VERIFICATIONS_MANUELLES.md`.
- **Pendant la veille** : le rafraîchissement périodique ci-dessous
  s'arrête (aucun appel GitHub) ; les événements `creation_issue` ne
  déclenchent aucun rechargement réseau (rattrapés au réveil). Les requêtes
  locales existantes (battement `/heartbeat`, `/watchers`, `/issues-inbox/etat`,
  panneau Infrastructure) ne sont PAS arrêtées.
- **Réveil** : le voile absorbe le premier clic (listener posé directement
  sur `#voile-veille`) ou la première touche (listener `keydown` en phase de
  capture sur `window`, `preventDefault`/`stopPropagation` avant que
  l'élément focus ne la reçoive). Déclenche
  `resultats.rafraichirSelection(projets sélectionnés)` + le panneau
  Infrastructure + `resultatsCoches.precharderVisibles()` (file plafonnée
  existante, issue #835). Le voile passe à « Mise à jour… », puis :
  - données arrivées → voile masqué, horodatage d'activité réinitialisé,
    rafraîchissement périodique relancé ;
  - délai maximum dépassé (30s, `DELAI_MAX_REVEIL_MS`) ou échec → état
    d'erreur explicite + bouton « Réessayer », jamais de disparition
    silencieuse.
- **Rafraîchissement périodique hors veille** : `resultats.rafraichirSelection`
  (liste + timing, RESTREINT aux projets actuellement sélectionnés dans le
  filtre pastille de l'onglet Résultats — `appelerAncien('projetsActifsDansFiltreResultats')`
  — jamais `chargerTimingTous()`, réservée au ↻ complet) + le panneau
  Infrastructure, à `intervalleSec` (défaut 60, plancher 15 — protège le
  quota GitHub). Se reprogramme lui-même après CHAQUE tentative : succès →
  délai réglé ; échec → attente croissante plafonnée (`prochainDelaiMs`,
  doublement jusqu'à 10 minutes), jamais d'arrêt définitif.
- **Rattrapage à la création d'une issue** (événement SSE `creation_issue`,
  dépôt de fichier ou formulaire — les deux finissent par le même événement,
  voir `app/fin_issue.py::emettre_creation_issue`) : rechargement ciblé
  IMMÉDIAT du projet concerné par l'événement (pas forcément celui
  sélectionné dans le filtre), puis un second après `rattrapageSec` (défaut
  10s) — en BACKUP du flux `/stream` (décision d'Alain : ne pas dépendre du
  flux seul). Rien pendant la veille.
- **(Dé)sélection d'un projet dans le filtre pastille** : un projet qui vient
  d'être sélectionné est rechargé À CE MOMENT (`veille.surSelectionChangee`,
  appelée depuis `app.js::basculerFiltreProjet`/`basculerTousLesFiltres` via
  le pont, débounce 300ms) — jamais pendant qu'il était désélectionné.

## 4. Réglages (modifiables par Alain, sans rechargement de page)

Panneau Infrastructure, partie GLOBALE, juste après l'interrupteur de son
(`templates/fragments/panneau_lateral.html`, zone `#pl-zone-veille`) :

| Réglage | Clé `localStorage` (via `window.Bridge.persistance`) | Défaut | Borne |
|---|---|---|---|
| Délai avant veille (min) | `bridge_veille_delai_min` | 30 | 0 désactive la veille |
| Intervalle de rafraîchissement (s) | `bridge_veille_intervalle_sec` | 60 | minimum 15 |
| Délai de rattrapage après création (s) | `bridge_veille_rattrapage_sec` | 10 | minimum 1 |

Valeur absente ou invalide → défaut (`normaliserDelaiVeilleMin`/
`normaliserIntervalleRafraichissementSec`/`normaliserDelaiRattrapageSec`,
`static/js/veille.js`). Préférences LOCALES AU NAVIGATEUR, une seule valeur
par réglage pour toute l'interface (jamais par projet) — aucun fichier
`configs/*.conf`, aucun mécanisme serveur. Un ordre de grandeur du coût en
appels GitHub par heure (`#pl-veille-cout`, `calculerCoutGithubParHeure` : 2
appels `gh` par cycle et par projet sélectionné — `/issues-liste` +
`/issues-en-attente`) s'affiche à côté, recalculé à chaque changement
d'intervalle ou de sélection pastille.

## 5. Ancienneté visible de la synchro

L'affichage « sync HH:MM:SS » près du ↻ (`#resultats-derniere-sync`,
`app.js::construireBoutonsFiltre`) se colore (`.resultats-derniere-sync-ancienne`,
rouge) quand `veille.syncEstAncienne()` répond vrai : jamais synchronisé, ou
plus ancien que trois fois l'intervalle réglé (`estSyncAncienne`). Recalculé
à chaque reconstruction de cette barre (chaque rechargement de liste, y
compris le rafraîchissement périodique).

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

## 8. Journal de diagnostic (`/stream`)

`app/fin_issue.py::_diffuser` (point UNIQUE de diffusion de tous les
événements `/stream` : `debut_issue`, `fin_issue`, `creation_issue`,
`fichier_recu`, `fichier_refuse`, `case_decochee`) écrit, en plus de la
diffusion SSE elle-même, une ligne dans `logs/charge_interface.log`
(`mesure_charge_interface.ligne_evenement_stream` : type d'événement, projet
concerné — `None` si l'événement n'en porte pas — et nombre de pages
actuellement abonnées) — JAMAIS le contenu de l'événement (titre, labels,
timing, fichier, motif). Best-effort strict : un échec d'écriture du journal
n'empêche jamais la diffusion SSE.
