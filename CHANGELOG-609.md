## 24 septembre 2026 — issue #609

Enregistrer la configuration d'un projet ne redémarre plus son watcher
pendant une tâche en cours — vécu sur `relecture_bridge` (issue #73) :
juste après le lancement d'une issue `mode_write`, une config enregistrée
via l'onglet Configuration (« Enregistrer et relancer ») a redémarré le
watcher en plein traitement ; au redémarrage, l'issue a été reprise, son
worktree dédié était « déjà pris » par la première tentative, repli sur
REP_TRAVAIL (#589), et le travail — non isolé — a été embarqué dans un
commit automatique d'un autre outil puis poussé par erreur.

**Point 1 (vérification du log) non traité** : `logs/watcher-relecture_bridge.log`
vit dans `/home/alain/Bridge_Agent/logs/` (dépôt principal), hors du
périmètre strict de ce worktree (`/home/alain/bridge_agent-issue609`).
Signalé plutôt que contourné.

- **`watcher.py`** : `acquerir_verrou()` prend désormais un paramètre `mode`,
  consigné dans le fichier de verrou (`logs/verrous/*.lock`, champ `mode=`,
  positionné avant `rep=` qui reste en dernier). Nouvelle fonction publique
  `taches_en_cours(nom_projet)` : scanne les verrous actifs (pid propriétaire
  vivant) et retourne les tâches en cours d'un projet — seul canal permettant
  à `new_issue.py` (process séparé du watcher) de savoir si un projet a une
  tâche en cours, `issues_en_cours` restant en mémoire du process watcher.
- **`app/watchers.py`** : `tache_en_cours(cfg)` (liste des tâches actives),
  `repli_rep_travail(cfg)` (une tâche `mode_write` tourne directement dans
  REP_TRAVAIL, hors worktree isolé — premier slot d'une parallélisation
  normale ET repli #589, même risque dans les deux cas, non distingués).
  `demarrer_watcher_ou_differer(cfg, forcer)` remplace `demarrer_watcher`
  comme point d'entrée de la route `/lancer-watcher` : un redémarrage forcé
  d'un watcher occupé n'est plus exécuté immédiatement (il couperait la
  tâche) — mémorisé dans `_redemarrages_differes`, exécuté automatiquement
  par le nouveau thread démon `surveiller_redemarrages_differes` dès la fin
  de la tâche (sondé toutes les `INTERVALLE_SURVEILLANCE_DIFFERE` = 15 s).
  `demarrer_watcher()`/`redemarrer_si_eteint()` (toujours `forcer=False`)
  restent inchangés — jamais concernés, un watcher avec une tâche en cours
  étant par construction déjà actif.
- **`new_issue.py`** : démarre `surveiller_redemarrages_differes` en thread
  démon, aux côtés de `surveiller_heartbeat`/`surveiller_transitions`.
- **Interface** : route `/watchers` expose `tache_en_cours`,
  `repli_rep_travail`, `redemarrage_differe` par projet. Onglet Watchers
  (`templates/index.html`, `static/js/app.js`) : nouvelle colonne « Statut »
  (⏳ tâche en cours / ⏳ redémarrage différé / ⚠️ REP_TRAVAIL en écriture).
  Bandeau global (même principe que le bandeau éval Windows #454), visible
  sur tous les onglets, listant les projets dont une tâche `mode_write`
  tourne actuellement dans REP_TRAVAIL. `sauvegarderConfig(relancer)` affiche
  « redémarrage différé, appliqué automatiquement à la fin de la tâche en
  cours » au lieu de « Watcher relancé » quand `/lancer-watcher` répond
  `differe: true`.
- **`BRIDGE_AGENT_DOC.md`** : nouveau point 4 dans « Cycle de vie des
  watchers » ; note ajoutée dans la section worktrees/repli #589.

Aucune régression sur les 5 appelants existants de `redemarrer_si_eteint`
(toujours `forcer=False`, jamais différés) ni sur `interrompre_linux`
(tue déjà tout l'arbre du watcher puis le laisse éteint — aucun redémarrage
forcé automatique à sa suite).
