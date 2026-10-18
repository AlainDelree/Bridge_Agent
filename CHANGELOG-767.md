# CHANGELOG-767 — à fusionner dans CHANGELOG.md

## 18 octobre 2026 — issue #767

Nettoyage du gabarit de rapport (consigne séparée du modèle à remplir) et
ajout de l'agent traitant dans le commentaire de clôture, dans `watcher.py`.

- **Défaut corrigé (gabarit).** Deux lignes du gabarit de rapport mélangeaient
  le modèle à remplir et la consigne qui permet de le remplir, au lieu de
  séparer les deux : les agents recopiaient la consigne elle-même dans leur
  rapport final au lieu de l'appliquer — observé sur quatre issues
  consécutives d'un même projet pour la ligne des commits.
  - **Ligne des commits.** `Commits (...) : [hash backup] (backup) +
    [hash fix] (fix) — ou "aucun" si lecture seule` laissait l'agent choisir
    entre deux formulations accolées. Le MODE (écriture ou lecture) est déjà
    connu du watcher au moment de construire le prompt : la ligne est
    désormais entièrement résolue par `lancer_claude` avant insertion dans le
    gabarit — `[hash backup] (backup) + [hash fix] (fix)` en écriture,
    `aucun (lecture seule)` sinon. Plus aucun choix laissé à l'agent sur
    cette ligne.
  - **Ligne de compilation.** `py_compile : OK / N/A` présentait deux
    possibilités côte à côte sans indiquer laquelle choisir ni pourquoi. Le
    gabarit porte maintenant un simple `py_compile : [résultat]` ; la règle de
    choix (résultat réel si du code Python a été modifié, `N/A` sinon) est
    énoncée une fois, en prose, juste avant le bloc à reproduire — jamais
    dans la ligne elle-même.
  - Reste du gabarit passé en revue (contexte, consignes, périmètre, blocs
    worktree/tentative/reprise, garde-fous par mode, ligne de verdict) : aucun
    autre cas de consigne glissée dans un modèle à remplir trouvé. Structure
    du rapport et ligne de verdict inchangées, comme demandé.

- **Agent consigné à la clôture.** `formater_bloc_calibration` (bloc ajouté
  par édition du commentaire de résultat déjà posté, à la fermeture de
  l'issue) ajoute désormais une ligne `🤖 Agent : <libellé>`, au même titre
  que la durée réelle et le `TIMEOUT_suggéré` déjà présents. Le libellé vient
  de `CFG.libelle_agent_effectif` — connu du watcher par la configuration du
  projet (`LIBELLE_AGENT` du `.conf`, ou déduction de plateforme Linux/
  Windows à défaut) — jamais d'une déclaration de l'agent lui-même. Présent
  aussi bien sur le commentaire de succès que sur celui d'échec après
  épuisement des tentatives (un seul point d'ajout, partagé par les deux
  issues de l'issue #767). Le modèle utilisé (`modele_ccl`) reste
  délibérément hors de ce bloc — hors périmètre de cette issue, traité
  séparément par un futur journal des changements de modèle.

- **Tests.** Suite complète (`tests/lancer_tous_les_tests.py`) : 68
  fichiers exécutés, 68 réussis, 0 échec — aucune régression, y compris sur
  les tests simulant une sortie d'agent (`test_ligne_verdict_764.py`,
  `test_verification_commentaire_237.py`, `test_corrections_erreurs_bloquantes_761.py`,
  `test_reprise_worktree_725.py`, `test_orphelin_verrou_perime_322.py`,
  `test_nettoyage_arbre_247.py`).
