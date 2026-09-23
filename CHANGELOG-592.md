## 23 septembre 2026 — issue #592

Exclusion des RELANCES de la mise à jour de `duree_typique` (biais de mesure
EWMA, §19/§21). Quand une issue est relancée via le champ RELANCE (#516)
après un échec `needs-human` ou un timeout, `watcher.py` peut retrouver dans
le worktree du travail déjà effectué par la tentative précédente : la durée
mesurée (nouvelle ACK → clôture) est alors artificiellement courte et tirait
`duree_typique` vers le bas. Quantifié sur GitHub : 7 RELANCES sur 192 issues
`done` depuis le 2026-09-02 (3.6%).

- `watcher.py` :
  - Nouveau marqueur `MARQUEUR_ECHEC_TENTATIVES = "❌ Échec après"` (préfixe
    du message d'échec définitif déjà posté par le watcher avant
    `needs-human`, ~L4453).
  - Nouvelles fonctions `_lister_commentaires(numero)` (lecture best-effort
    des commentaires actuels de l'issue via `gh issue view --json comments`)
    et `_issue_est_relance(commentaires)` (True si `MARQUEUR_ECHEC_TENTATIVES`
    est déjà présent dans cet historique).
  - `_traiter_issue_synchrone` : détection `est_relance` juste AVANT le
    commentaire d'ACK (donc sur l'historique strictement antérieur à cette
    exécution) — un seul appel réseau, réutilisé côté succès plus bas.
  - `_maj_combinaison_timeout` / `maj_calibration_timeout` : nouveau
    paramètre `relance` (défaut `False`). Sur succès avec `relance=True`,
    la durée est traitée comme CENSURÉE, même principe que le timeout :
    aucune mise à jour de `duree_typique`/`variabilite`/succès rapides/
    backoff, ni de F_reseau/F_local (même biais de durée artificiellement
    courte) — seul un compteur `n_relances_exclues` (par combinaison) est
    incrémenté à titre de traçabilité.

- `tests/test_relance_exclusion_calibration_592.py` (nouveau) : 4 scénarios
  — détection RELANCE sur l'historique des commentaires (positif/négatif/
  historique vide), exclusion de `duree_typique`/`variabilite` avec
  incrément de `n_relances_exclues`, non-régression d'un succès normal
  (mise à jour comme avant #592), et `maj_calibration_timeout` bout en bout
  (amorce → RELANCE inchangée → issue normale de nouveau mise à jour).
  Suite de tests existante (20 fichiers) toujours verte.
