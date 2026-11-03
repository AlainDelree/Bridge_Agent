## 3 novembre 2026 — issue #846

Le commit de sauvegarde en mode écriture n'était jusqu'ici qu'une consigne
de prompt (« tout premier geste, avant toute modification ») — rien ne
l'imposait techniquement, et l'agent l'oubliait régulièrement (dernier cas :
issue #121 de Relecture_Bridge, où le commit de sauvegarde avait englouti le
travail de correction, laissant un commit de correctif vide et un contrôle
« succès sans commit au-delà de la sauvegarde » faussé). Ce commit est
désormais fait par le **watcher lui-même**, juste après avoir relevé le HEAD
d'avant traitement (`tete_avant_traitement`, issue #689) et juste avant de
lancer la première tentative — il est donc toujours le premier commit, créé
une seule fois par traitement (`_demarrer_traitement` → nouvelle fonction
`_commit_sauvegarde_watcher`).

**Décisions sur les cas particuliers (demandées par l'issue) :**
- **Tentatives 2/3 d'un même traitement** : aucun second commit — le commit
  watcher n'est tenté qu'une fois, avant la tentative 1 ; les tentatives
  suivantes réutilisent le même `tete_avant_traitement`/hash, sans rien
  recommitter (testé explicitement, deux tentatives échouées d'affilée ne
  laissent qu'un seul commit).
- **RELANCE sur un worktree repris** (travail déjà commité) : le commit
  watcher reste fait, à la position du PREMIER commit après
  `tete_avant_traitement` — celui-ci étant relevé APRÈS le travail déjà
  présent, le nouveau commit ne fusionne jamais avec lui ; il sépare
  proprement « avant cette relance » de « pendant cette relance ».
- **Projets définissant `CMD_BACKUP`** (recherché dans le dépôt : aucun
  `.conf` présent, `configs/` étant gitignoré et hors périmètre de ce
  worktree — uniquement le défaut documenté dans `nouveau_projet.py` et
  `BRIDGE_AGENT_DOC.md` a pu être vérifié) : comportement intégralement
  conservé — le watcher ne committe rien lui-même, la consigne historique
  (exécuter `CMD_BACKUP`) reste inchangée dans le prompt.
- **Dossier non-git ou essai à blanc** : `tete_avant_traitement` reste
  `None` dans ces deux cas (comportement déjà existant) → le commit watcher
  n'est jamais tenté, repli sur la consigne de prompt historique inchangée.
- **Garde-fou backup/reset** : `_commit_sauvegarde_watcher` compare les
  fichiers non suivis avant/après son propre `git add -A` et journalise
  (plus mention dans le bloc de prompt) les chemins qu'il vient de mettre
  sous suivi, pour que l'agent reste vigilant avant un script se terminant
  par une opération git destructrice — même précaution que celle déjà
  documentée côté agent, reprise côté watcher.

**Repli (point 3)** : toute erreur du commit watcher (`git add`/`git commit`
en échec, SHA introuvable) retombe sur `None`, journalisée en
`log.warning`, jamais bloquante — le prompt repasse alors sur la consigne
historique inchangée caractère pour caractère.

**Consignes mises à jour** (`consignes/globales.md`, bloc mode écriture de
`watcher.py::lancer_claude`) : l'agent est désormais informé que le commit
de sauvegarde est déjà fait, avec son hash, et ne doit pas en refaire un ;
la procédure de rattrapage (stash/commit/pop) n'est conservée que pour le
cas de repli explicitement signalé.

**Rapport de clôture** : le hash du commit de sauvegarde watcher est
communiqué à l'agent dans son prompt (pour la ligne « Commits ») et,
défense en profondeur, `_finaliser_succes` substitue lui-même le
placeholder littéral `[hash backup]` par ce hash si l'agent ne l'a pas fait.
Le contrôle existant « succès sans commit au-delà de la sauvegarde »
(`_avertissement_succes_sans_commit`) continue de fonctionner sans
modification : il repère ce commit par POSITION (premier commit après
`tete_avant_traitement`), inchangée par ce correctif.

**Documentation** : `BRIDGE_AGENT_DOC.md` §5 (mode écriture) mis à jour —
le backup est désormais décrit comme fait par le watcher, sauf projet
`CMD_BACKUP` (comportement conservé). Aucune fiche d'architecture/worktree
(`ARCHITECTURE.md`, `WORKTREES.md`) ne décrivait ce geste — rien à y
changer.

**Fichiers modifiés** : `watcher.py` (nouvelle fonction
`_commit_sauvegarde_watcher` ; `_demarrer_traitement`, `lancer_claude`,
`_executer_une_tentative`, `_finaliser_succes` et leur unique site d'appel
dans `_traiter_issue_synchrone` adaptés pour transmettre
`commit_sauvegarde_watcher`/`backup_watcher_nouveaux_suivis`) ;
`consignes/globales.md` ; `BRIDGE_AGENT_DOC.md` ;
`tests/test_contexte_decision_historique_845.py` (adapté au nouveau tuple
de retour de `_demarrer_traitement`) ; nouveau
`tests/test_commit_sauvegarde_watcher_846.py` (9 scénarios : commit vide
sur worktree neuf, fichiers non suivis capturés + remontés, tentative 2
sans second commit, RELANCE séparant bien le travail antérieur, projet
`CMD_BACKUP` inchangé — comportement ET texte de prompt —, échec du commit
avec repli journalisé, et substitution du hash dans le rapport de
clôture). Aucun fichier `.conf` modifié.

**Tests** : `pytest tests/` → 413 passed (404 avant, +9 nouveaux), mêmes 11
erreurs préexistantes et sans rapport (`tests/test_signature_attente_825.py`,
fixture `tmp_dir_factory` inexistante — non touché par cette issue).
`node --test static/js/tests/ static/js/socle/tests/` → 492 passed, 0 fail,
inchangé (aucun fichier JS modifié). `python3 -m py_compile watcher.py` → OK.
