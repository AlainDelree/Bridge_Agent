## 24 septembre 2026 — issue #601

Factorisation du tableau markdown `## En-tête` dans une fonction commune
`formater_entete()` (diagnostic #579 §3.2) : ce tableau était construit à
la main dans trois sites (`app/issues.py`, `app/projet_ccw.py` ×2,
`scripts/watcher_issues_inbox.py`), avec des divergences déjà présentes
(TIMEOUT/PRIORITE en dur à certains endroits, ligne COMPLEXITE hors
tableau) — or ce tableau est re-parsé tel quel par `watcher.py`, une
dérive future aurait pu casser le parsing silencieusement.

- `app/issues.py` : nouvelle fonction `formater_entete(mode, priorite,
  timeout, projet, *, source="CC", dest="CCL", retour="CC", modele=None,
  complexite=None)` — reproduit EXACTEMENT le format existant (`timeout`
  sans le suffixe `s`, ajouté par la fonction ; `MODELE` et `COMPLEXITE`
  optionnels, absents par défaut). `construire_body()` l'utilise
  désormais au lieu de construire ses lignes à la main.
- `app/projet_ccw.py` : `_corps_issue_ccl()` et `_corps_issue_ccw()`
  appellent `formater_entete()` (import local, comme le reste des imports
  `app.issues` de ce module, pour éviter tout souci d'import circulaire).
  Le bloc `CREATION_*` de `_corps_issue_ccw()` reste construit à part et
  concaténé après l'en-tête (format spécifique à ce seul site, non inclus
  dans la fonction commune).
- `scripts/watcher_issues_inbox.py` : `construire_body()` appelle
  `formater_entete()` au lieu de dupliquer les lignes du tableau.

Format de sortie vérifié identique bit-à-bit à l'ancien code (comparaison
manuelle des chaînes produites, avant/après, pour les trois sites) — pas
de modification du format attendu par `watcher.py`. Suite de tests
existante (21 fichiers, dont `tests/test_projet_ccw_559.py`) toujours
verte sans aucune modification des tests.
