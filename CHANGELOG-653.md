# CHANGELOG-653 — à fusionner dans CHANGELOG.md

## 26 septembre 2026 — issue #653

URGENT — régression #646 : `dom.$` supprimé à tort, casse tout le panneau latéral.

Le « balayage exhaustif » de #646 a retiré `dom.$`/`dom.$$`/`creerElement` de `static/js/socle/dom.js` en affirmant zéro appelant restant. Faux pour `dom.$` : `static/js/panneau_lateral.js` l'utilise à 17 endroits (`grep -rn "dom\.\$(" static/js/*.js`). Effet observé en usage réel : `TypeError: dom.$ is not a function` en rafale (sélection de ligne, chaque événement SSE `debut_issue`/`fin_issue`, ouverture de page) — le bouton « Tester le son » restait grisé en permanence (`testerSonActif()` le désactive puis appelle `majBoutonTesterSonActif()`, qui plantait avant de le réactiver), et plus largement tout le panneau latéral (monitoring, son, actions, notifications) était affecté.

- **`static/js/socle/dom.js`** : restauration de `export function $(selecteur, racine)` (querySelector), reprise à l'identique du commit précédant #646 (`git show 39ed79d:static/js/socle/dom.js`). `dom.$$` et `creerElement` **non restaurés** : confirmés sans appelant (recherche généralisée sur `\.\$\b` / `\.\w+\b` par module, pas seulement le style d'appel `dom.$(` qui avait fait manquer la régression à #646).
- **Autres retraits de #646 vérifiés sans effet** (méthode élargie, ne présumant plus d'un style d'appel précis) : le canal `/events` de `static/js/socle/sse.js` (jamais connecté, `app.js` garde son propre `EventSource('/events')` indépendant), la classe CSS orpheline `.barre-issue` (zéro occurrence, JS ou template).
- **Nouveau test `static/js/socle/tests/exports_socle.test.js`** (modèle `pont_globales.test.js`, issue #632) : scanne tous les `static/js/*.js` à la recherche de `dom.<nom>` / `persistance.<nom>` (exports top-level, import en espace de noms) et de `api.<nom>` / `store.<nom>` (clés de l'objet exporté) ; échoue si un nom utilisé ne correspond à rien d'exposé par le module concerné. Inclut un cas explicite : `panneau_lateral.js` appelle bien `dom.$`, `dom.js` l'exporte bien. Vérifié que ce test échoue effectivement si `dom.$` est retiré (reproduction de la régression avant correctif).

Fichiers modifiés : `static/js/socle/dom.js`, `static/js/socle/tests/exports_socle.test.js` (nouveau).

Tests : `node --test static/js/` → 138/138 OK (133 précédents + 5 nouveaux). `py_compile` sans changement côté Python (aucun fichier `.py` touché).
