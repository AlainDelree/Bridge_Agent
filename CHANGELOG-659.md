# CHANGELOG-659 — à fusionner dans CHANGELOG.md

## 27 septembre 2026 — issue #659

Réconciliation de la contradiction PATH/`AppEnvironmentExtra` entre l'ancien fix #558 (`ajouter_projet_ccw.ps1`) et #658 (`mettre_a_jour_tokens_ccw.ps1`), signalée dans les deux fichiers depuis #658 sans être résolue.

**Archéologie (lecture des commits/issues, pas supposition)** : le fix #558 (743f068) avait diagnostiqué qu'un tableau splatté (`@envExtra`) passé à `nssm set … AppEnvironmentExtra` était fautif, et l'avait remplacé par une chaîne unique jointe par `` `n``. Mais la clôture #558 confirme que cette cause n'a JAMAIS été reproduite sur un nssm réel (lecture du code seule — l'étape « reproduire le bug » demandée par l'issue n'a pas été faite), et n'a jamais été testée avec une ligne PATH (contenant des espaces, ex. « Program Files ») — PATH n'existait pas encore dans `AppEnvironmentExtra` à l'époque (ajouté par #658). #658 a lui constaté empiriquement, sur ce PC fixe et nssm 2.24, l'inverse pour une valeur à espaces : la chaîne unique jointe par `` `n`` ne pose PAS de ligne PATH effective, alors que des arguments SÉPARÉS fonctionnent — y compris pour cette valeur à espaces, donc a fortiori pour des tokens qui n'en ont pas.

**Décision** : arguments séparés retenu comme SEULE méthode dans tout le dépôt (le fix #558 n'ayant jamais eu de confirmation empirique propre, contrairement à #658).

- **`provisioning/windows/ajouter_projet_ccw.ps1`** : la réapplication des tokens préservés (relance sur projet déjà finalisé, issue #181) ne joint plus les entrées en une chaîne unique — elle les retrouve par clé (PATH/GH_TOKEN/CLAUDE_CODE_OAUTH_TOKEN, l'ordre/le nombre variant selon que le service a ou non déjà une ligne PATH) puis les repasse à `nssm set` comme autant d'arguments scalaires distincts (0 à 3, jamais de tableau splatté). Commentaire « BUG #558 » retiré et remplacé par l'explication de la réconciliation.
- **`creer_projet_ccw_complet.ps1`** (racine, script courant hors `provisioning/windows/`) : même alignement — PATH/GH_TOKEN/CLAUDE_CODE_OAUTH_TOKEN passés à `nssm set` comme 3 arguments séparés au lieu d'une chaîne jointe par `` `n``.
- **`provisioning/windows/mettre_a_jour_tokens_ccw.ps1`** : déjà aligné depuis #658, commentaire mis à jour pour référencer la réconciliation (#659) plutôt que renvoyer à une contradiction non résolue.
- **`provisioning/windows/finaliser_projet_ccw.ps1`/`finaliser_projet_ccw_auto.ps1`** : aucun changement nécessaire — ils délèguent déjà entièrement la pose d'`AppEnvironmentExtra` à `mettre_a_jour_tokens_ccw.ps1`, déjà correct.
- **`tests/test_ajouter_projet_ccw_env_558.py`** : réécrit pour vérifier la nouvelle méthode (arguments séparés) sur les 3 scripts qui posent `AppEnvironmentExtra`, avec contrôles négatifs sur l'ancien pattern (splat ET chaîne jointe).

**Non résolu ici (nécessite un accès Windows/nssm réel, hors de portée de CCL/Linux)** : la certitude absolue sur l'origine exacte du bug #558 (splat vs qualité des données relues via `nssm get`) et la vérification directe de l'état réel du service `CCW-Watcher-Scrabble` (créé aujourd'hui via l'onglet CCW). Délégué à CCW via l'issue for-windows #660 (test jetable sur nssm 2.24 + vérification/correction immédiate de `CCW-Watcher-Scrabble` si affecté).

Tests : `python3 tests/test_ajouter_projet_ccw_env_558.py` (6 scénarios, tous passent) + suite complète relancée (`tests/test_*.py`), aucune régression. BOM UTF-8 préservé sur les 3 scripts `.ps1` modifiés. Aucune modification de `configs/*.conf`. Aucun `git push`.
