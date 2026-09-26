# CHANGELOG-650 — à fusionner dans CHANGELOG.md

## 26 septembre 2026 — issue #650

Refonte web, étape 11 — sortie de l'onglet Journal watcher d'`app.js` vers `static/js/journal.js`.

Dernier chantier de la refonte de l'interface web (ARCHITECTURE.md §6, procédure §6.7), le plus petit morceau restant : l'onglet Journal watcher.

- **`static/js/journal.js`** (nouveau) : `demarrerJournal()` (ouvre une connexion SSE `/journal/<projet>`, ferme la précédente si déjà ouverte, code couleur des lignes selon leur contenu — `classeLigneJournal()`, extraite en fonction pure) et `viderTerminal()`, déplacées d'`app.js`. La variable `sourceSSE`, propriété exclusive de ces deux fonctions (vérifié : aucune autre partie d'`app.js` ne la lisait), devient une variable de module (`sourceJournal`), non exposée globalement. `initJournal()` branche la délégation du bouton « Vider l'affichage ».
- **`static/js/onglets.js`** : `demarrerJournal` importé DIRECTEMENT (plus via le pont `appelerAncien`) et appelé dans `activerOnglet('journal')` ; `initialisationsPour('journal')` ne pousse plus `'demarrerJournal'`.
- **`static/js/socle/index.js`** : import de `initJournal`, appelé une fois au chargement (comme les autres modules par fonctionnalité).
- **`templates/fragments/onglet_journal.html`** : retrait de l'`onclick="viderTerminal()"` inline, remplacé par `data-action="journal-vider"` (délégation du socle).
- **`static/js/app.js`** : `demarrerJournal`/`viderTerminal`/`sourceSSE` retirés — plus aucune trace de l'onglet Journal watcher dans l'ancien code.
- **Tests** : `static/js/tests/journal.test.js` (nouveau, logique pure de `classeLigneJournal`) ; `static/js/tests/onglets.test.js` ajusté (`initialisationsPour('journal')` → `[]`) ; `static/js/tests/pont_globales.test.js` inchangé, toujours au vert (plus aucun appel `appelerAncien('demarrerJournal')` à couvrir).
- **`ARCHITECTURE.md`** §6.5/§6.7 : `journal.js` déplacé de la liste des « futurs modules » vers les modules déjà sortis, nouveau paragraphe « Étape 11 réalisée ».
- **`VERIFICATIONS_MANUELLES.md`** : section « Onglet Journal watcher » complétée (note sur le branchement par import direct + vérification de la fermeture propre de la connexion SSE au changement de projet/onglet).

Fichiers modifiés : `static/js/journal.js` (nouveau), `static/js/onglets.js`, `static/js/socle/index.js`, `static/js/app.js`, `templates/fragments/onglet_journal.html`, `static/js/tests/journal.test.js` (nouveau), `static/js/tests/onglets.test.js`, `ARCHITECTURE.md`, `VERIFICATIONS_MANUELLES.md`.

Tests : `node --test static/js/tests/` (110 tests) et `node --test static/js/socle/tests/` (29 tests) → tous au vert. Vérification manuelle du comportement visible (journal en direct, réinitialisation au changement de projet) laissée à Alain (VERIFICATIONS_MANUELLES.md), non rejouable en session non interactive (nécessite un navigateur).
