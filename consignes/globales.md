## Rappels systématiques (injectés automatiquement dans toute issue)

- **Ne jamais exécuter `git push`.** Tu committes en local uniquement ;
  Alain vérifie et pousse lui-même après revue.
- **En mode_write, toujours faire un commit de sauvegarde
  (`git commit --allow-empty` ou équivalent) AVANT toute modification**,
  pour garantir un point de retour arrière.
- **Respecter strictement le périmètre du projet** (dossier configuré) —
  ne jamais travailler hors de ce périmètre même si l'issue semble le
  suggérer.
- **Si une commande ou un outil est refusé par le système de permissions
  (session non-interactive, aucune approbation possible), ou reste bloqué
  SANS AUCUN PROGRÈS (silence total, boucle apparente, > 30s sans le moindre
  signe d'avancement) : abandonne IMMÉDIATEMENT cette approche et signale-le
  dans ton rapport, plutôt que de retenter.** Bascule sur un repli plus
  simple (lecture directe, `grep`, analyse manuelle) si la tâche le permet.
  Ne jamais insister sur une commande déjà refusée. **À l'inverse, une
  opération intrinsèquement longue mais qui PROGRESSE normalement (build,
  compilation, installation de dépendances, suite de tests, clonage
  volumineux) n'est PAS une anomalie** : le seuil de 30s vise l'ABSENCE de
  progrès, pas la durée en elle-même — attends sa fin (voir la contrainte
  d'exécution ci-dessous pour la façon d'attendre correctement).
- **Contrainte d'exécution : accomplis la TOTALITÉ de ta tâche en une seule
  exécution synchrone et bloquante.** Ne lance jamais une commande en
  arrière-plan, ne recours jamais à un « monitor », une notification, un
  rappel programmé, ou une formulation du type « je répondrai/poursuivrai
  quand… » / « j'attends la fin de… ». Si une opération dépasse le timeout
  d'un appel d'outil, relance-la avec un timeout explicite plus long, ou
  boucle sur sa sortie DANS cette même exécution jusqu'à complétion réelle —
  ne conclus jamais ton tour de parole sur une attente. Le watcher ferme
  l'issue dès ta réponse postée : il n'existe AUCUNE reprise possible.
