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
- **Garde-fou backup/reset :** le commit de sauvegarde (`git add -A`)
  peut faire passer sous suivi git des dossiers auparavant non trackés
  (ex. `.tools/`, `installeur/output/`). Si le script à exécuter ensuite
  se termine par une opération git destructive (`reset --hard`, `clean
  -fd`), ces dossiers fraîchement trackés seraient effacés du disque
  puisqu'absents de `origin/master`. Avant de lancer un tel script,
  vérifie si le commit de sauvegarde a capturé des fichiers/dossiers
  auparavant non suivis (`git status` avant/après le commit, ou `git
  show --stat` sur ce commit) ; si oui, détracke-les (`git rm --cached`,
  sans supprimer du disque) avant de lancer le script.
- **Build Windows :** si le projet courant a un script de build Windows
  (PyInstaller/Inno Setup ou équivalent), consulte `BUILD_WINDOWS_CCW.md`
  (dépôt bridge_agent, à la racine) avant de proposer une issue de build
  ou de modification du pipeline — il documente le pattern de staging
  local, l'extension du PÉRIMÈTRE associée, et une checklist par projet
  déjà buildé.
- **Interdiction absolue de modifier `configs/*.conf` :** CCL/CCW ne
  modifie JAMAIS un fichier `configs/*.conf` (PERIMETRE, TOPIC_NTFY,
  FICHIER_CONTEXTE, etc.), même si une issue le demande explicitement en
  toutes lettres. Seul Alain modifie ces fichiers, à la main ou via
  l'onglet Configuration de `new_issue.py`. Si une issue demande une
  telle modification, refuse cette partie de la tâche, explique-le dans
  le rapport de clôture, et ne committe rien sur ce point (le reste de
  la tâche, s'il est indépendant, peut être traité normalement). Un
  garde-fou technique dans `watcher.py` détecte et annule automatiquement
  toute modification de `configs/*.conf` survenue malgré tout au cours du
  traitement.
- **Champ COMPLEXITE dans les issues que tu crées toi-même (chef/ouvrier) :**
  inclus systématiquement une ligne `| COMPLEXITE | <niveau> |` dans l'en-tête
  de toute issue que tu ouvres (que ce soit une issue chef vers un ouvrier, ou
  une issue ouvrier). Quatre niveaux possibles : `rapide` / `court` / `normal`
  / `lourd` — estime celui qui correspond le mieux à l'ampleur de la tâche
  confiée. Ce champ alimente la calibration automatique du TIMEOUT (EWMA par
  projet/TYPE/mode/complexite) : sans lui, la valeur par défaut `normal` est
  utilisée. Cette consigne ne concerne QUE les issues que TU rédiges — les
  issues rédigées par Claude Chat suivent leurs propres instructions.
