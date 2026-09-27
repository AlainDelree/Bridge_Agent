# CHANGELOG-666 — à fusionner dans CHANGELOG.md

## 27 septembre 2026 — issue #666

Onglet CCW, section « Finaliser » : `ccwFinaliserProjet()` (`static/js/ccw.js`) vidait déjà `#ccw-fin-gh` et `#ccw-fin-oauth` après soumission (succès ou échec) mais oubliait `#ccw-fin-topic` — constaté par Alain en finalisant plusieurs projets à la suite (Bridge_Agent, Scrabble, Actualise), le champ TOPIC_NTFY affichait la valeur du projet précédent (aucune donnée réelle affectée, uniquement visuel). Second point, plus sérieux : changer de projet sélectionné (clic sur une ligne du tableau ou sélection directe dans le menu déroulant `#ccw-fin-nom`) ne vidait aucun des trois champs — un token resté affiché pour l'ancien projet aurait pu être posé par erreur sur le nouveau via « Finaliser ».

- **`static/js/ccw.js`** : extraction de `ccwViderChampsFinalisation()` (exportée), qui vide les trois champs (`#ccw-fin-topic`, `#ccw-fin-gh`, `#ccw-fin-oauth`). Appelée : (1) dans `ccwFinaliserProjet()`, aux deux points où les tokens étaient déjà vidés (succès/avertissement et erreur réseau) — remplace les deux paires d'affectations dupliquées ; (2) dans `ccwPreselectionnerProjet()`, dès qu'une sélection valide est appliquée (clic sur une ligne du tableau) ; (3) via un nouveau gestionnaire délégué (`dom.surAction`) sur l'événement `change` de `#ccw-fin-nom`, pour la sélection directe dans le menu déroulant.
- **`static/js/tests/ccw.test.js`** : test DOM minimal (stub `global.document.getElementById`, patron déjà utilisé par `resultats_activation.test.js`) vérifiant que `ccwViderChampsFinalisation()` vide bien les trois champs.
- **`VERIFICATIONS_MANUELLES.md`** : deux nouvelles cases dans la section « Onglet CCW » (remise à zéro au changement de sélection ; remise à zéro du topic après finalisation).

Tests : `node --test static/js/tests/` (164 tests, tous passent, aucune régression). Aucune modification de `configs/*.conf`. Aucun `git push`.
