## 24 septembre 2026 — issue #599

Ajout du champ d'en-tête optionnel `REDACTEUR` dans `issues_inbox/`, validé
pour cohérence avec `PROJET` **avant** toute création d'issue GitHub — filet
de sécurité contre une issue rédigée par Claude Chat dans le contexte d'un
projet puis déposée par erreur sous un `PROJET` différent (distraction,
relecture insuffisante d'Alain avant dépôt du fichier).

- `scripts/watcher_issues_inbox.py` : `REDACTEUR` ajouté à `CHAMPS_ENTETE`
  et à `extraire_champs()` ; nouvelle fonction `valider_redacteur()` appelée
  par `valider()` avant toute autre vérification. Trois règles : (1)
  `REDACTEUR == PROJET` → OK ; (2) label `for-windows` **et**
  `REDACTEUR == bridge_agent` → OK (canal central CCW, quel que soit le
  `PROJET` réellement ciblé) ; (3) tout autre cas → rejet vers
  `issues_inbox/rejected/` avec message explicite de discordance, journalisé
  dans `issues_inbox.log`. `REDACTEUR` absent → aucune validation
  (rétrocompatibilité avec les issues existantes).
- `BRIDGE_AGENT_DOC.md` : `REDACTEUR` ajouté au tableau des champs
  d'en-tête de `issues_inbox/` (§3.3), règle de validation détaillée dans
  §3.4, et entrée miroir dans le tableau général des champs spéciaux (§6).
- `tests/test_champ_redacteur_599.py` (12 scénarios) : extraction du champ,
  les 3 règles de `valider_redacteur()`, et le chemin complet
  `traiter_fichier()` pour les 4 cas de vérification demandés par l'issue
  (REDACTEUR == PROJET, REDACTEUR d'un autre projet sans for-windows,
  canal CCW for-windows + REDACTEUR=bridge_agent, REDACTEUR absent).
