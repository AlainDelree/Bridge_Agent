## 1 novembre 2026 — issue #837

Périmètre dynamique (`PERIMETRE_DYNAMIQUE = true`, issue #125) : une issue
dont `REPO_CIBLE` désigne le dépôt du projet lui-même (`REP_TRAVAIL`, chemin
résolu identique) est désormais traitée comme un projet NORMAL — worktree
isolé (#337), parallélisme selon `MAX_WRITE_PARALLELE`, verrou, commit de
sauvegarde, contrôles habituels. Jusqu'ici, `diagnostique_programme` (dont
les audits visent des dépôts tiers mais dont les issues de développement
visent son propre dépôt) écrivait directement sur la branche principale,
sans isolation ni place de parallélisme, quel que soit `REPO_CIBLE`.

Nouvelle fonction pure `_traiter_comme_perimetre_dynamique(body)` dans
`watcher.py` : faux pour un projet à périmètre fixe ou pour un projet
dynamique dont `REPO_CIBLE` égale `REP_TRAVAIL` (traitement normal) ; vrai
dans tous les autres cas — `REPO_CIBLE` absent, différent, imbriqué dans un
sens ou l'autre, ou invalide (traitement dynamique historique, direct dans
`REP_TRAVAIL`, sans worktree ni parallélisme). Remplace les quatre tests de
`CFG.perimetre_dynamique` propres à une issue : le dispatch mode_write
(`traiter_issue`) et les trois endroits de `_resoudre_contexte_execution`
(bascule worktree, lecture/validation de `REPO_CIBLE`, prise en compte de
`SOUS_DOSSIER`). Les réglages lus une fois au démarrage
(`CFG.perimetre_dynamique` lui-même) ne changent pas.

Une ligne de journal par issue d'un projet dynamique indique le traitement
retenu (« REPO_CIBLE = dépôt du projet : traitement normal » ou « REPO_CIBLE
= dépôt tiers : traitement dynamique »).

Documentation (`BRIDGE_AGENT_DOC.md` §7 et §16) : nouvelle précision sur ce
cas, et sur le fait que les autres issues d'un même projet dynamique restent
sur le chemin direct, sans worktree ni parallélisme (`MAX_WRITE_PARALLELE`
sans effet sur elles).

Nouveau fichier de tests `tests/test_perimetre_dynamique_normal_837.py` (10
scénarios) : fonction de décision pure, dispatch avec worktree/fil simulés
(MAX_WRITE_PARALLELE à 4, à 1, places pleines), issue « différente »,
lecture « identique », non-régression d'un projet à périmètre fixe, et
vérification que `git worktree add` ne modifie pas `git status --porcelain
-uall` du dossier principal.

Hors périmètre (pistes, non traitées) : aucun avertissement à la création
d'une issue en écriture visant un dépôt tiers (elle reste directe, sans
isolation, comme aujourd'hui) ; aucun changement de l'agent `vibe`, des
verrous, de l'inbox ni du formulaire.
