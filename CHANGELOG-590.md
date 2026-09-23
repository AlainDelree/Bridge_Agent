## 23 septembre 2026 — issue #590

Backoff EWMA irrécupérable (§19) — ancrage de la condition « succès rapide »
sur `duree_typique` au lieu du `TIMEOUT` courant, et plafond de sécurité sur
`TIMEOUT_suggéré`. Constaté sur `relecture_bridge|normal|write|normal` :
`multiplicateur_backoff` monté à 7481.83 (→ `TIMEOUT_suggéré` ~2 062 012s,
~23 jours) et `relecture_bridge|normal|write|lourd` à 7.59 — dans les deux
cas le backoff ne pouvait plus jamais redescendre seul.

- `watcher.py` :
  - Cause : `_maj_combinaison_timeout` comparait `duree_s` à
    `SEUIL_SUCCES_RAPIDE × timeout_courant`, où `timeout_courant` est le
    `TIMEOUT` de l'en-tête de CETTE exécution — une valeur décorrélée du
    comportement réel de la combinaison (peut rester basse d'une issue à
    l'autre, ex. constaté « 300s, TIMEOUT plancher, trop court »). Un succès
    pourtant nettement plus rapide que la normale pouvait ainsi ne jamais
    franchir la barre, bloquant `succes_rapides_consecutifs` à 0 et le
    backoff dans son état emballé — sans recours (verrou permanent).
  - Correctif de fond : la comparaison est désormais ancrée sur
    `duree_typique + K_VARIABILITE × variabilite` — le repère historique
    EWMA propre à la combinaison — totalement indépendant du `TIMEOUT` de
    l'exécution en cours et donc du `multiplicateur_backoff` lui-même.
    Suppression du paramètre `timeout_courant`, devenu inutile, de
    `_maj_combinaison_timeout` et `maj_calibration_timeout` (et des deux
    points d'appel dans `_traiter_issue_synchrone`).
  - Filet de sécurité : nouvelle constante `TIMEOUT_SUGGERE_PLAFOND = 3600`
    (1h — largement au-dessus des complexités `lourd` observées à ce jour)
    et nouvelle fonction `_timeout_suggere_borne()` (formule §19.2 + bornage
    plancher/plafond), utilisée par `maj_calibration_timeout` et
    `lire_timeout_suggere` — protège contre tout emballement futur non
    anticipé du backoff, même après le correctif d'ancrage ci-dessus.
  - Correction manuelle des deux valeurs anormales dans
    `logs/etat_timeout.json` demandée par l'issue : **non appliquée** —
    ce fichier (gitignoré, état d'exécution) vit dans le clone de travail
    réel (`/home/alain/Bridge_Agent`), hors du périmètre de ce worktree
    isolé (`/home/alain/bridge_agent-issue590`). Alain doit remettre
    manuellement `multiplicateur_backoff` à `1.0` pour les combinaisons
    `relecture_bridge|normal|write|normal` (7481.83) et
    `relecture_bridge|normal|write|lourd` (7.59) dans
    `/home/alain/Bridge_Agent/logs/etat_timeout.json` après déploiement
    de ce fix.

- `tests/test_backoff_ancrage_duree_typique_590.py` (nouveau) : 4 scénarios
  — succès rapide détecté malgré un backoff emballé (cas réel), 3 succès
  rapides consécutifs réinitialisant le backoff, succès non notablement
  rapide remettant le compteur à zéro sans y toucher, et plafonnement de
  `TIMEOUT_suggéré` (`_timeout_suggere_borne`). Suite de tests existante
  (18 fichiers) toujours verte.
