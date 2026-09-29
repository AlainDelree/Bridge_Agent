## #689 — Informer chaque tentative de son rang et lui faire reconnaître le travail d'une tentative précédente dans le même worktree

Constaté à plusieurs reprises (dernier cas net : #687, « Durée réelle :
356s (TIMEOUT courant : 300s) ») : la tentative 1 termine réellement le
travail (commits inclus) mais dépasse le TIMEOUT de peu et se fait tuer
avant de pouvoir le rapporter. Le watcher relance alors la tentative 2 dans
le même worktree (les commits de la tentative 1 y sont déjà présents), mais
`lancer_claude()` ne recevait pas le numéro de tentative en paramètre :
chaque essai recevait exactement le même prompt, sans savoir qu'un essai
précédent avait pu réussir juste avant d'être interrompu — la tentative 2
décrivait alors le travail déjà fait comme une « exécution antérieure »
ambiguë, sans jamais faire le lien avec sa propre tentative précédente.

- `lancer_claude()` reçoit désormais `tentative` (1 = première), `max_tentatives`
  (`None` si issue critique = essais illimités) et `tete_avant_traitement` (SHA de
  `HEAD` capturé avant la toute première tentative de ce traitement).
- `_demarrer_traitement()` capture ce SHA via `_tete_git(cwd_effectif)`, en
  mode écriture uniquement (seul mode qui produit des commits) et hors
  dry-run — retourné en 5e élément du tuple, propagé par
  `_traiter_issue_synchrone` à chaque `_executer_une_tentative`.
- À partir de la tentative 2, `lancer_claude()` injecte dans le prompt un
  bloc dédié (après la clause worktree, avant le garde-fou de mode) : il
  indique le rang de la tentative en cours, et explique que des commits déjà
  présents et absents du SHA `tete_avant_traitement` proviennent très
  probablement de sa propre tentative précédente pour cette même issue,
  tuée par le TIMEOUT juste après avoir fini son travail — à vérifier plutôt
  qu'à refaire, et à signaler explicitement comme telle (pas comme une
  « exécution antérieure » non identifiée) dans le rapport final.
- Tentative 1 (comportement par défaut, valeurs par défaut des nouveaux
  paramètres) : aucun bloc injecté, prompt inchangé.

Fichiers touchés : `watcher.py` (`lancer_claude`, `_executer_une_tentative`,
`_demarrer_traitement`, `_traiter_issue_synchrone`).
