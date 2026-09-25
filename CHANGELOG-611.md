## 25 septembre 2026 — issue #611

Corrige l'incohérence entre l'encart #577 de `BRIDGE_AGENT_DOC.md`
(« REP_TRAVAIL n'est plus jamais touché directement ») et le code réel
depuis #337 : à `MAX_WRITE_PARALLELE > 1`, le premier slot d'un lot
`mode_write` était délibérément dispatché dans `REP_TRAVAIL`
(`worktree=None`), sans isolation — un redémarrage du watcher pendant
ce premier slot tuait le processus CCL et laissait du travail inachevé
mélangé dans `REP_TRAVAIL` (`relecture_bridge` #73).

- **`watcher.py`** : le bloc `if not actifs:` de `traiter_issue` (premier
  slot direct sur `REP_TRAVAIL`) est supprimé — toute tâche `mode_write`,
  quel que soit son rang dans le lot, passe désormais par la création d'un
  worktree dédié. Nouvelle fonction `_creer_worktree_avec_retries(numero)` :
  enveloppe `_creer_worktree` avec jusqu'à 2 tentatives supplémentaires sous
  noms alternatifs (`-bis`, `-ter`, via le nouveau paramètre `suffixe` de
  `_chemin_worktree`/`_branche_worktree`/`_creer_worktree`) quand l'échec est
  attribuable à un chemin/branche déjà pris (reliquat non nettoyé, #589) —
  aucune retentative sur une erreur git générique, qu'un changement de nom
  ne résoudrait pas. Si les 3 tentatives échouent, nouvelle fonction
  `_signaler_repli_worktree_echoue(numero, raison)` : `notify-send` immédiat
  (`notifier_bureau`, urgence `critical`) + `log.warning` explicite avec le
  chemin, avant le repli en tout dernier recours sur `REP_TRAVAIL` (toujours
  en tâche de fond à `MAX_WRITE_PARALLELE > 1`, pour que la boucle
  principale reste libre). `_lancer_thread_ecriture` et
  `_traiter_issue_synchrone` transmettent `echec_worktree_deja_pris` dans ce
  cas aussi, pour que le compte-rendu de clôture (#589) mentionne le repli
  quel que soit le chemin qui y a mené.
- **`tests/test_worktree_parallelisation_337.py`** : nouveaux scénarios pour
  `_creer_worktree_avec_retries` (réussite via `-bis`, épuisement des 3
  tentatives, pas de retry sur erreur générique) et pour le repli signalé
  (`notify-send` capturé par un faux exécutable) à `MAX_WRITE_PARALLELE <= 1`
  et `> 1`. Scénario de parallélisation à 2 tâches mis à jour : les deux
  obtiennent désormais chacune un worktree dédié (plus aucune dans
  `REP_TRAVAIL`).
- **`BRIDGE_AGENT_DOC.md`** : encart et section détaillée réécrits pour
  décrire le comportement sans exception (worktree pour toute tâche
  `mode_write`) et la séquence de repli (tentatives `-bis`/`-ter` puis
  signalement actif en dernier recours).

Suite de tests existante (21 fichiers) toujours verte.
