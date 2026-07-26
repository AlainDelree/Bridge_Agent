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
  exécution synchrone et bloquante.** Ce qui est interdit, c'est de CONCLURE
  ton tour de parole avant que l'opération soit réellement terminée et son
  résultat vérifié — pas l'arrière-plan en tant que technique : l'outil Bash
  a lui-même un timeout maximum par appel (de l'ordre de dix minutes) qu'aucun
  paramètre ne permet de dépasser. Si une opération dépasse le timeout d'un
  appel d'outil, deux voies sont permises : relance-la avec un timeout
  explicite plus long tant que le plafond de l'outil le permet, OU lance-la
  en arrière-plan À CONDITION IMPÉRATIVE d'interroger sa sortie en boucle DANS
  cette même exécution jusqu'à complétion réelle. Restent formellement
  interdits, sans changement : un « monitor », une notification, un rappel
  programmé, et toute formulation du type « je répondrai/poursuivrai quand… »
  / « j'attends la fin de… » en guise de conclusion. Le watcher ferme
  l'issue dès ta réponse postée : il n'existe AUCUNE reprise possible.
