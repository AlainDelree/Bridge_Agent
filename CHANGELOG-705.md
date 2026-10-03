## #705 — Résultats : resynchroniser la liste au retour de l'onglet au premier plan et après une reconnexion SSE

- Front-end uniquement, comme demandé. Constat : la liste Résultats n'est
  alimentée que par les événements `/stream` ciblés (`creation_issue`,
  `debut_issue`, `fin_issue`, traités par `traiterNotif` dans
  `static/js/resultats.js`) — un événement manqué (onglet masqué, coupure
  réseau, redémarrage de `new_issue.py`) la laisse périmée indéfiniment,
  sans aucun rejeu côté serveur.
- Deux fonctions pures ajoutées à `static/js/resultats.js` (testées sous
  Node, `static/js/tests/resultats.test.js`), isolant la décision
  « faut-il resynchroniser (↻) ? » :
  - `fautResynchroniserApresMasquage(dureeMasqueeMs, seuilMs = SEUIL_RESYNC_MASQUAGE_MS)`
    — `SEUIL_RESYNC_MASQUAGE_MS = 30000` (30 s).
  - `fautResynchroniserApresReconnexionSse(premiereOuverture)` — ne resync
    que sur une RECONNEXION, jamais à la toute première ouverture (pas de
    double chargement au démarrage de la page).
- `static/js/socle/sse.js::creerCanalSse().connecter()` accepte désormais un
  paramètre optionnel `{ onOuvert }` (surcharge celui, le cas échéant, passé
  à la construction du canal) — nécessaire pour que `resultats.js` y
  branche sa propre logique de reconnexion sans coupler ce module générique
  à une logique métier.
- `static/js/resultats.js::initialiser()` : `sse.stream.connecter({ onOuvert:
  surOuvertureSse })` — `surOuvertureSse` distingue première ouverture et
  reconnexion (drapeau module `sseDejaOuverte`) et déclenche le ↻ via le pont
  (`appelerAncien('resynchroniserResultatsAuRetour')`) uniquement sur
  reconnexion.
- `static/js/app.js` :
  - Nouvelle fonction `resynchroniserResultatsAuRetour()` : garde anti-rafale
    simple (ne relance pas si un rafraîchissement est en cours ou vient
    d'avoir lieu, `DELAI_MIN_ENTRE_RESYNCS_AUTO_MS = 5000`), puis appelle
    `rafraichirResultats()` — le même rafraîchissement que le bouton ↻.
    Utilisée par les deux déclencheurs (retour d'onglet, reconnexion SSE),
    donc partagée entre les deux.
  - Gestionnaire `visibilitychange` (`demarrerCycleVie`) : mémorise
    l'horodatage de masquage (`momentMasquageOnglet`) ; au retour au premier
    plan, conserve l'appel existant à `envoyerHeartbeat()` puis, si la durée
    masquée dépasse le seuil (`window.Bridge.resultats.fautResynchroniserApresMasquage`),
    déclenche `resynchroniserResultatsAuRetour()`. Comportement inchangé tant
    que l'utilisateur reste sur la page (durée masquée nulle → pas de resync).
- `fautResynchroniserApresMasquage` publiée sous
  `window.Bridge.resultats` (pont, issue #625/#632) pour être consommée par
  l'ancien `app.js`, classique et non importable en module ES — même
  convention que `calculerBadgeModele`/`calculerBadgeSansRedacteur`.
