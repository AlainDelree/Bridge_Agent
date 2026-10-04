# CHANGELOG-718 — à fusionner dans CHANGELOG.md

## 4 octobre 2026 — issue #718

§3.16 « Issues en attente » : l'onglet **« En attente » passe AVANT l'onglet « Résultats »** dans la barre d'onglets, pour plus de visibilité (demande d'usage d'Alain, suite #713/#714). **Résultats reste l'onglet actif au lancement du programme**, comme avant — le changement d'ordre ne déplace pas l'activation par défaut.

- `templates/fragments/onglets.html` : le bloc `data-onglet="attente"` est déplacé avant le bloc `data-onglet="resultats"` (qui garde seul la classe `actif`). Les autres onglets (Journal watcher, Configuration, CCW, Nouvelle issue) gardent leur position relative.
- Aucun changement de code JS nécessaire : l'association onglet ↔ panneau se fait déjà par **identifiant** (`data-onglet` / `panneau-<nom>`), pas par position dans le DOM (voir l'en-tête de `static/js/onglets.js`, issue #626) ; l'onglet actif au lancement est déjà désigné par une constante explicite (`ONGLET_PAR_DEFAUT = 'resultats'` dans `static/js/onglets.js`, reprise par `store.js` : `ongletActif: 'resultats'`), jamais par position dans la liste. Aucune mémorisation (`localStorage`) ni raccourci clavier de l'onglet actif n'existe par ailleurs. Vérifié : aucune règle CSS `nth-child`/`first-child`/`order` sur `.onglet` dans `static/css/base.css`.
- `BRIDGE_AGENT_DOC.md` §3 : correction de la mention « juste après Résultats » (issue #714) → « avant Résultats dans la barre d'onglets », avec rappel explicite que Résultats reste l'onglet actif au lancement.
- Tests : `tests/test_ordre_onglets_718.py` (nouveau, 3 scénarios, dans le style de `tests/test_champ_attente_713.py` — lecture directe des fichiers, aucune dépendance au DOM) — ordre des blocs `data-onglet` dans le gabarit (En attente avant Résultats), un seul onglet `actif` au chargement et c'est Résultats, `ONGLET_PAR_DEFAUT` désignant `'resultats'` par son nom dans `static/js/onglets.js`. Suite Python complète vérifiée verte (`pytest tests/` → 178 tests, dont les 3 nouveaux, aucune régression) ainsi que la suite JS (`node --test tests/` dans `static/js/` → 182 tests, inchangée).

Hors périmètre (rappel de l'issue) : `configs/*.conf` non touché, contenu/badge/boutons Lancer-Supprimer de l'onglet « En attente » inchangés.
