## 22 septembre 2026 — issue #586

Fix `tests/test_init_git_local_258.py`, périmé et non collecté par pytest
(diagnostic #579). Deux causes cumulées, une seule anticipée par le
diagnostic :

1. `scenario_deja_git` comparait le résultat de `initialiser_git()` par
   égalité stricte de dictionnaire à une valeur écrite avant le fix #530
   (filet de sécurité email noreply GitHub), donc sans la clé
   `email_corrige` que la fonction renvoie désormais toujours. Dictionnaire
   attendu mis à jour avec `"email_corrige": None`.
2. Non anticipé par #579 : `scenario_contenu_preexistant_pas_de_push`
   vérifiait `"public" in res["detail"]`, texte retiré du message `detail`
   de `nouveau_projet.py` par le fix #528 (choix public/privé du dépôt à la
   création) — un dépôt n'est plus systématiquement public. Assertion
   corrigée pour ne plus exiger ce mot, seule la mention « non relu »
   restant garantie et pertinente.

Par ailleurs, aucune fonction du fichier n'était préfixée `test_` : un
`pytest tests/` classique ne testait donc rien de ce fichier, l'échec ne se
manifestant qu'en exécution directe
(`python3 tests/test_init_git_local_258.py`). Les 5 fonctions
`scenario_*` renommées en `test_*` (et leurs références dans `main()`)
pour que pytest les collecte réellement.

Vérifié : les 5 scénarios passent en exécution directe (code retour 0) et
via `pytest tests/test_init_git_local_258.py` (5 passed). Seul le fichier
de test a été modifié, aucune logique de production touchée.
