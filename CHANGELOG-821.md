## Issue #821 — pytest : supprimer les 238 avertissements « test returned dict » de la sortie

26 fichiers de `tests/` se terminent par un `return` (petit dict ou texte)
utilisé par leur lanceur maison (`main()`, exécutable en direct avec
`python3 tests/test_xxx.py`) pour afficher le détail de chaque scénario.
Pytest le signale par `PytestReturnNotNoneWarning`, ce qui noyait la sortie
de `python3 -m pytest tests/ -q` sous 238 avertissements répétés.

Ajout de `pytest.ini` à la racine (aucune config pytest n'existait) qui
ignore spécifiquement `pytest.PytestReturnNotNoneWarning` via
`filterwarnings`, sans toucher aux fichiers de tests ni masquer d'autres
avertissements. Résultat : `367 passed` en quelques lignes, sans bloc
d'avertissements. Les lanceurs maison continuent de fonctionner à
l'identique (vérifié sur `tests/test_tableau_ccw_804.py`).

Documenté dans `ARCHITECTURE.md` (§1, note sous l'arborescence) :
pourquoi ces `return` existent et pourquoi l'avertissement est
volontairement ignoré.
