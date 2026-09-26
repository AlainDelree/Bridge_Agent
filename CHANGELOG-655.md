# CHANGELOG-655 — à fusionner dans CHANGELOG.md

## 26 septembre 2026 — issue #655

Panneau latéral : bouton « ⏹ Arrêter » par projet pour les watchers CCL.

Depuis la suppression de l'onglet Watchers (issue #626, étape 2), la ligne d'un watcher CCL du panneau latéral (`rendrePanneauLateralMonitoring`, `static/js/panneau_lateral.js`) n'offrait que « ▶ Lancer »/« ↺ Relancer » — aucun moyen de l'arrêter immédiatement depuis l'interface, alors que la route serveur `POST /arreter-watcher` (`app/watchers.py::arreter_watcher_route`/`arreter_watcher`, `systemctl --user stop`) existait déjà et n'était utilisée que par le bouton Configuration. Un watcher actif finissait par s'éteindre seul (auto-extinction, 20 min par défaut), mais rien ne permettait de l'arrêter tout de suite (ex. avant de modifier son `.conf`, ou pour libérer des ressources).

- **`static/js/panneau_lateral.js`** : nouvelle fonction pure `afficherBoutonArreterWatcherCcl(actif)` (même patron que `afficherBoutonDemarrer`/`afficherBoutonArreter` de `ccw.js`, issue #203) — le bouton n'apparaît que si le watcher est actif. Nouveau bouton `⏹ Arrêter` (`data-action="pl-arreter-ccl"`) affiché à côté de `↺ Relancer` dans ce cas, dans un nouveau wrapper `<span class="pl-ligne-btns">` (nécessaire pour garder deux boutons dans une ligne `.pl-ligne` en `justify-content:space-between`, qui n'attendait jusqu'ici que deux enfants). Nouvelle fonction réseau `sidebarArreterWatcherCCL(nom, btn)` : confirmation (`toasts.confirmer`, même style que `sidebarArreterWatcherInbox`), `POST /arreter-watcher`, bouton désactivé pendant l'appel, puis rafraîchissement — même mécanique que `sidebarRelancerWatcherCCL`. Reste interne au module (pas exposée en `window.*`, contrairement à `sidebarRelancerWatcherCCL` que `app.js` appelle encore directement).
- **`static/css/resultats.css`** : règle `.pl-ligne-btns{display:flex;gap:6px;flex-shrink:0}` pour le nouveau wrapper.
- **`static/js/tests/panneau_lateral.test.js`** : 3 nouveaux tests sur `afficherBoutonArreterWatcherCcl` (actif → affiché, inactif → masqué, `undefined` → masqué), sur le modèle de `ccw.test.js`.
- **`VERIFICATIONS_MANUELLES.md`** : nouvelle case dans la zone monitoring du panneau latéral décrivant le bouton, sa visibilité conditionnelle et le comportement de confirmation.
- **`BRIDGE_AGENT_DOC.md`** (§3.11, watcher spool) : la phrase « contrairement aux watchers CCL de projet, pas de bouton Arrêter » était devenue fausse — reformulée pour renvoyer vers le nouveau bouton CCL (même mécanique de confirmation).

Tests : `node --test static/js/tests/*.test.js` → 157/157 OK (154 précédents + 3 nouveaux). `py_compile` sans changement côté Python (aucun fichier `.py` touché, la route serveur existait déjà).
