## 24 septembre 2026 — issue #608

Colonne « Couleur » ajoutée au tableau des projets actifs (§2 de
`BRIDGE_AGENT_DOC.md`) : `relecture_web` (projet `relecture_bridge`) n'a
accès qu'à ce tableau public — `configs/` est hors de son périmètre — et
voulait pouvoir afficher la couleur d'accent de chaque projet sans confondre
des noms proches (`bridge_agent`/`relecture_bridge`, `alchess`/`chesscoach`).

- **`nouveau_projet.py`** : nouvelle fonction `couleur_affichee(nom,
  couleur_conf)`, miroir Python de `couleurProjet()` (`static/js/app.js`) —
  réutilise `COULEURS_PROJETS_EXISTANTS`/`COULEUR_PROJET_INACTIF` existants
  plutôt que de dupliquer la règle de priorité. Ajout de
  `PROJETS_COULEUR_RECYCLEE` (ensemble miroir de `COULEURS_PROJET` côté JS
  pour `ecole`/`ff_galerie`, issue #540) et de `couleur_hash_projet()`
  (miroir de `couleurHashProjet()`, converti en hex via `_hsl_vers_hex`
  plutôt qu'en `hsl(...)`).
- **`regenerer_tableaux_projets.py`** : la colonne `Couleur` est ajoutée en
  **dernière position** du tableau `TABLEAU_PROJETS_ACTIFS` (pour ne décaler
  aucune colonne existante — vérifié qu'aucun autre lecteur du dépôt ne parse
  ce tableau par position). `lire_projets()` importe `nouveau_projet`
  localement (pas en tête de fichier) pour éviter un cycle d'import avec
  `nouveau_projet.py`, qui importe déjà `regenerer_tableaux_projets` à son
  chargement (issue #571) — testé dans les deux ordres d'import.
- **`BRIDGE_AGENT_DOC.md`** : §2 et « Couleur d'accent des projets » mis à
  jour pour documenter la nouvelle colonne et le cas des projets à couleur
  recyclée. Le tableau généré lui-même n'a **pas** été régénéré dans ce
  worktree isolé : `configs/*.conf` (gitignoré) n'y est pas présent — à
  lancer par Alain (`python3 regenerer_tableaux_projets.py`) après fusion,
  sur un checkout ayant accès aux vrais `.conf`.
