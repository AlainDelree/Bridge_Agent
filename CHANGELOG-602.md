## 24 septembre 2026 — issue #602

Retrait des 2 étapes manuelles caduques depuis #597 du corps de l'issue CCL
généré par `app/projet_ccw.py::_corps_issue_ccl()` (case « Projet CCW » du
formulaire de création, issue #559).

- `app/projet_ccw.py::_corps_issue_ccl()` : supprime les 2 anciennes étapes
  numérotées (ajout d'une entrée au tableau `$Projets` de
  `reinstaller_projets_ccw.ps1` + ligne dans le tableau de rappel de
  `REINSTALLATION_CCW.md` §7) — toutes deux automatisées depuis #597
  (dérivation dynamique de `$Projets` depuis `configs\*-ccw.conf`) et #556
  (le fichier `.conf` est déjà créé par le flux CREATION). Le corps devient
  purement informatif (section « Contexte » expliquant qu'aucune action
  manuelle n'est requise), conservant la référence croisée vers l'issue CCW.
- `tests/test_projet_ccw_559.py::scenario_corps_issue_ccl_contenu` : les
  assertions vérifient désormais l'ABSENCE des 2 anciennes instructions
  plutôt que leur présence.
- `BRIDGE_AGENT_DOC.md` §16 (séquence `bootstrap_projet_ccw`, point 3) :
  description mise à jour pour refléter le corps simplifié.
- Évaluation demandée par l'issue : le corps de l'issue CCL, une fois les 2
  étapes retirées, ne contient plus aucune action exécutable (seulement du
  contexte + la cross-référence) — l'issue CCL elle-même pourrait donc être
  supprimée du flux (route `bootstrap_projet_ccw`, frontend, doc, tests).
  Non fait ici : ce retrait toucherait le contrat de l'issue CCW (paramètre
  `numero_ccl`), le template/JS affichant les 2 liens d'issue, et une bonne
  partie de `tests/test_projet_ccw_559.py` — portée plus large que la
  COMPLEXITE `normal` déclarée pour #602, et l'issue demande explicitement
  de ne pas supprimer le flux sans confirmation. Recommandation : ouvrir une
  issue dédiée si ce retrait complet est souhaité (même logique de scission
  que #601/#602).

Tests : suite complète (21 fichiers `tests/test_*.py`) toujours verte.
