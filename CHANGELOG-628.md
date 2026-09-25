## Issue #628 — Refonte interface web, étape 4 : panneau latéral (mise en page non recouvrante, monitoring VM mort)

Sortie du panneau latéral « Infrastructure » de `app.js` vers son propre
module `static/js/panneau_lateral.js` (§6.7 ARCHITECTURE.md), premier module
de la refonte à piloter réellement une zone de l'écran (au lieu du socle inerte
posé par #625).

- **Mise en page** : le panneau était en `position:fixed`, collé au bord droit
  au-dessus du contenu — il recouvrait la fin des lignes de la liste Résultats
  (badges de temps). Remplacé par une vraie colonne flex à côté de la liste
  (`.resultats-layout` / `.resultats-corps` / `.panneau-lateral-col`,
  `templates/fragments/onglet_resultats.html` + `static/css/resultats.css`) :
  ne recouvre plus jamais la liste ; sur écran étroit, passe sous la liste au
  lieu de la recouvrir (`flex-direction:column`).
- **État ouvert/fermé** : mémorisé (`localStorage`, socle `persistance.js`) et
  conservé d'un onglet à l'autre — auparavant réinitialisé à chaque entrée dans
  l'onglet Résultats. Ouvert par défaut.
- **Monitoring VM supprimé** : appel mort à `/ccw/vm-statut` (résidu
  VirtualBox, route disparue côté serveur depuis #447, 404 avalé en silence),
  bloc d'affichage « VM », appel à `sidebarDemarrerVm` (jamais défini), styles
  associés.
- **Actions dupliquées retirées du détail d'issue** (`construireHtmlIssue`,
  `static/js/app.js`) : « Interrompre cette issue » et « Fermer définitivement »
  faisaient double emploi avec le panneau (`#pl-zone-actions`) — ne restent
  plus que dans le panneau. Le détail lui-même (hors bloc d'actions) n'a pas
  été touché.
- **Mutualisation `/watchers`** : une seule lecture périodique
  (`rafraichirWatchersPartages`, `static/js/panneau_lateral.js`), écrite dans
  `store.watchers` (socle) — le bandeau de repli REP_TRAVAIL (`app.js`,
  `rafraichirReplisRepTravail`) s'y abonne désormais au lieu de fetcher lui-même ;
  affichage du bandeau inchangé.
- **Zone son** déplacée telle quelle (comportement inchangé), seule la brique
  réseau change (`api.*`/`toasts.*` du socle au lieu de `fetch()`/`alert()` en
  dur).
- Événements migrés vers la délégation du socle (`dom.surAction`,
  attributs `data-action="pl-*"`) au lieu des `onclick=` inline.
- Glue de transition minimale conservée dans `app.js` (pont socle→ancien,
  `appelerAncien`) pour ce qui dépend d'un état encore propriété d'autres
  fonctionnalités non migrées (liste des issues, onglet CCW) : getters
  `obtenirCcwProjetsConnus`/`obtenirIssueSelectionnee`, mutateur
  `actualiserLabelIssueLocal`, `resumeProjetMonitoring` conservé.
- `VERIFICATIONS_MANUELLES.md` et `BRIDGE_AGENT_DOC.md` mis à jour
  (terminologie « panneau flottant » → « panneau latéral », chemins de
  fonctions, nouvelles vérifications non-régression).

Vérifié : `node --test static/js/socle/tests/` (20/20 OK), `node --check` sur
les 3 fichiers JS touchés/ajoutés, rendu de `/` via le client de test Flask
(200, aucune référence fonctionnelle résiduelle à `/ccw/vm-statut` ni
`sidebarDemarrerVm`), fichiers statiques servis (200, `text/javascript`).
Pas de test navigateur réel (pas d'environnement graphique) — à rejouer par
Alain via `VERIFICATIONS_MANUELLES.md`.
