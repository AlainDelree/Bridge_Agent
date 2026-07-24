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
  (session non-interactive, aucune approbation possible), ou boucle/tarde
  anormalement (> 30s sans progrès net) : abandonne IMMÉDIATEMENT cette
  approche et signale-le dans ton rapport, plutôt que de retenter.** Bascule
  sur un repli plus simple (lecture directe, `grep`, analyse manuelle) si la
  tâche le permet. Ne jamais insister sur une commande déjà refusée.
