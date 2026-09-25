## 25 septembre 2026 — issue #620

Diagnostic #579 (bas niveau, point 2) : `nouveau_projet.py` (~1450 lignes)
mélangeait plusieurs responsabilités ; la plus clairement séparable — la
science des couleurs (~410 lignes, algorithmes WCAG/Lab, génération de
palette, `couleur_affichee`, `couleur_hash_projet`) — était en outre
autonome, sans dépendance vers le reste du fichier.

Extraite telle quelle vers un nouveau module `palette.py` à la racine du
dépôt : constantes (`SATURATION_PALETTE`, `COULEURS_PROJETS_EXISTANTS`,
`PALETTE_COULEURS`, `PROJETS_COULEUR_RECYCLEE`, etc.), fonctions privées
(`_hsl_vers_hex`, `_linearise_srgb`, `_luminance_relative`,
`_contraste_avec_noir`, `_plancher_contraste_teinte`, `_plancher_effectif`,
`_lab_depuis_hsl`, `_distance_lab`, `_teinte_lab`, `_ecart_teinte`,
`_lab_depuis_hex`) et fonctions publiques (`generer_palette`,
`couleur_hash_projet`, `couleur_affichee`). `nouveau_projet.py` importe
désormais `COULEURS_PROJETS_EXISTANTS`/`PALETTE_COULEURS` depuis `palette` ;
`couleurs_utilisees()`/`couleurs_disponibles()`, qui combinent ces couleurs
avec la lecture de `configs/*.conf`, restent inchangées sur place.

Bénéfice concret : `regenerer_tableaux_projets.py` faisait un import local
différé de `nouveau_projet` pour accéder à `couleur_affichee` — un
`from nouveau_projet import couleur_affichee` en tête de fichier créait un
cycle (ce module importe déjà `regenerer_tableaux_projets` à son chargement,
issue #571/#608). Avec `palette.py`, sans dépendance vers `nouveau_projet`,
l'import se fait désormais proprement en tête de fichier
(`from palette import couleur_affichee`).

`app/nouveau_projet.py` (accès à `couleurs_disponibles`) continue de
fonctionner sans modification, ces fonctions restant dans `nouveau_projet.py`.
Vérifié : `py_compile` sur les trois fichiers, suite de tests existante
(pytest + scripts autonomes) toujours verte, `create_app()` toujours
fonctionnel, et test manuel de `lire_projets()` sur un dossier `.conf`
temporaire (couleur gelée, couleur recyclée grisée, couleur `.conf`
persistée — les trois niveaux de priorité de `couleur_affichee`).
