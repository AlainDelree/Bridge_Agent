# WORKTREES.md — Parallélisation mode_write via git worktrees

Documentation de référence pour le mécanisme introduit par l'issue #337
(et son complément #336, `scripts/fusionner_changelog.py`). Ce fichier
couvre le workflow utilisateur (Alain) et les procédures de récupération.
Pour l'architecture générale du bridge, voir `BRIDGE_AGENT_DOC.md` — la
sous-section « Parallélisation mode_write via git worktrees (issue #337) »
de son §13 en donne un résumé technique ; ce document-ci est le
complément détaillé, propre à l'infrastructure, volontairement gardé hors
du manuel commun à tous les projets.

## 1. Pourquoi

**Problème résolu.** Avant #337, `watcher.py` traitait les issues
`mode_write` **strictement en séquence** : une seule tâche d'écriture à
la fois par projet, dans `REP_TRAVAIL`. Une deuxième issue `mode_write`
créée pendant qu'une première tournait devait attendre — parfois
plusieurs minutes — que la première se termine, même si les deux tâches
touchaient des fichiers totalement indépendants.

**Bénéfice attendu.** Plusieurs issues `mode_write` d'un même projet
peuvent désormais tourner **en parallèle**, chacune dans un répertoire
isolé sur sa propre branche git (`git worktree`). Le débit global du
bridge augmente sans risque de collision fichier entre tâches, puisque
chaque tâche a son propre arbre de travail. Les modes `lecture` et
`lecture active` (scratch) restent, eux, toujours séquentiels — hors
périmètre de ce mécanisme (voir §5 « Limites connues »).

## 2. Design

- **`MAX_WRITE_PARALLELE`** (clé `.conf`, entier, défaut **2**) — nombre
  maximum de tâches `mode_write` concurrentes pour un projet donné. `1`
  (ou `0`) désactive tout le mécanisme : aucun thread, aucun worktree,
  comportement séquentiel historique intégral.
- **Premier slot sans worktree.** La toute première tâche `mode_write`
  détectée (aucune autre déjà en cours) est dispatchée dans un thread
  Python ciblant `REP_TRAVAIL` **directement**, sans créer de worktree.
  C'est nécessaire : la boucle principale du watcher est mono-thread, et
  si elle restait bloquée en attendant la fin de `_traiter_issue_synchrone`
  pour la première tâche, elle ne pourrait jamais détecter une deuxième
  issue `mode_write` pendant que la première tourne encore.
- **Slots suivants dans des worktrees frères.** Toute tâche `mode_write`
  détectée pendant qu'au moins un thread est déjà actif, et tant que
  `MAX_WRITE_PARALLELE` n'est pas atteint, obtient un worktree dédié :
  `<REP_TRAVAIL>/../<NOM_PROJET>-issue<N>` (répertoire frère de
  `REP_TRAVAIL`), branche `worktree-issue-<N>`, créés par
  `git -C <REP_TRAVAIL> worktree add <chemin> -b worktree-issue-<N>`. Si
  la création échoue (chemin ou branche déjà existants, ou toute autre
  erreur git), repli automatique et silencieux sur le traitement
  séquentiel classique — jamais d'exception propagée, l'issue attend
  simplement qu'un slot se libère au cycle suivant.
- **Verrou par chemin de travail effectif.** Le verrou anti-collision
  inter-process (issues #189/#322, un fichier sous `logs/verrous/`) est
  désormais posé sur le **chemin de travail effectif** de chaque tâche
  (`REP_TRAVAIL` pour le premier slot, ou le chemin du worktree pour les
  suivants) — et non plus systématiquement sur `REP_TRAVAIL` seul. Deux
  worktrees du même projet obtiennent donc deux verrous distincts et
  tournent sans s'attendre l'un l'autre, tandis qu'une issue
  `mode_lecture`/`mode_scratch` visant `REP_TRAVAIL` pendant que le
  premier slot y tourne encore reste bloquée par ce même verrou, comme
  avant #337.
- **CHANGELOG séparé par worktree.** Dans un worktree, CCL reçoit une
  consigne de prompt dédiée lui demandant d'écrire son entrée dans
  `CHANGELOG-<N>.md` à la racine du worktree plutôt que dans
  `CHANGELOG.md` directement — sinon toutes les tâches parallèles
  entreraient systématiquement en conflit sur ce fichier unique.
  `scripts/fusionner_changelog.py` (#336) intègre ensuite ces fichiers
  dans `CHANGELOG.md` (insertion en tête, triés par N décroissant, plus
  récent en premier) et les supprime. Lancement **manuel** uniquement —
  `watcher.py` ne l'appelle jamais automatiquement.
- **Auto-extinction différée.** Le watcher ne s'éteint jamais pour
  inactivité (`DELAI_INACTIVITE_MIN`) tant qu'au moins un thread
  `mode_write` tourne encore, même si le délai est dépassé — réévalué à
  chaque cycle, dès qu'un thread se termine l'extinction redevient
  possible.
- **Fin de tâche = pas de nettoyage automatique.** Un worktree n'est
  **jamais** supprimé automatiquement par `watcher.py`, ni sa branche —
  ni en cas de succès, ni en cas d'échec. C'est Alain qui merge et pousse
  manuellement une fois le travail relu, puis nettoie (§3, §4). Le numéro
  d'issue, le chemin du worktree et la branche sont toujours journalisés
  clairement en fin de traitement dans `logs/watcher-<projet>.log`.

## 3. Workflow normal d'Alain

C'est la section la plus importante de ce document — le déroulé attendu
au quotidien.

1. **Créer les issues normalement**, sans rien faire de spécial pour
   profiter de la parallélisation — le watcher gère seul la décision
   (premier slot direct vs worktree) selon `MAX_WRITE_PARALLELE` et les
   tâches déjà en cours.
2. **Après notification** (bip/notify-send/ntfy, §17 du DOC) qu'une ou
   plusieurs issues sont closes, lancer `git worktree list` dans
   `REP_TRAVAIL` pour voir quels worktrees sont prêts à être relus et
   mergés (chemin + branche de chaque tâche encore en attente de
   traitement manuel).
3. **Avant de merger ou de pousser quoi que ce soit**, lancer
   `python3 scripts/fusionner_changelog.py` depuis la racine du dépôt
   (ou `--repo <chemin>` si besoin) — il intègre tous les
   `CHANGELOG-<N>.md` trouvés dans `CHANGELOG.md` et les supprime. Sans
   cette étape, les entrées changelog des tâches en worktree restent
   invisibles dans l'historique fusionné.
4. **Merger chaque branche worktree dans `master` manuellement**, une
   par une, en relisant le diff avant. Rien de spécifique aux worktrees
   ici — un `git merge worktree-issue-<N>` classique depuis `REP_TRAVAIL`
   (ou l'outil habituel).
5. **Nettoyer** une fois la branche mergée :
   ```bash
   git worktree remove <chemin>
   git branch -d worktree-issue-<N>
   ```

## 4. Procédures de récupération

- **Worktree orphelin** (CCL planté ou TIMEOUT atteint pendant le
  traitement, worktree laissé dans un état incertain) :
  ```bash
  git worktree list                        # identifier le chemin orphelin
  git worktree remove --force <chemin>      # --force : ignore les modifs non commitées
  git branch -d worktree-issue-<N>          # -D si la branche n'a jamais été mergée et qu'on l'abandonne
  ```
- **Verrou non libéré.** Le verrou d'une tâche en worktree suit le même
  mécanisme fichier que celui de `REP_TRAVAIL` (`logs/verrous/*.lock`),
  mais avec sa propre clé (basée sur le chemin résolu du worktree). Le
  bouton ⛔ « Interrompre cette issue » de l'interface web (§13 du DOC,
  « Interrompre une issue bloquée ») tue tout l'arbre de process du
  watcher — donc aussi les tâches en worktree qui tournaient encore en
  parallèle — puis, une fois l'arbre confirmé mort, supprime
  automatiquement le verrou de `REP_TRAVAIL` **et** ceux de tous les
  worktrees actifs détectés à côté (`interrompre_linux()`, issue #340) :
  plus besoin d'intervention manuelle dans ce cas.
  - Procédure manuelle (résiduelle, pour un verrou orphelin en dehors du
    circuit « Interrompre », ou si `interrompre_linux()` échoue) :
    identifier le PID du watcher (`ps aux | grep watcher`), le tuer
    (`kill -9 <pid>` + descendance), puis supprimer le fichier
    `logs/verrous/<...>.lock` correspondant **uniquement une fois l'arbre
    de process confirmé mort**.
- **`CHANGELOG-N.md` oublié avant push.** Si un push a déjà eu lieu sans
  passer par `fusionner_changelog.py` et qu'un `CHANGELOG-<N>.md` traîne
  encore à la racine : relancer `python3 scripts/fusionner_changelog.py`,
  vérifier le résultat (`git diff CHANGELOG.md`), committer, puis
  pousser.
- **Conflit de merge** entre une branche worktree et `master` (deux
  tâches ayant touché la même zone d'un même fichier, ou `master` ayant
  avancé entre-temps) : résolution via l'outil de merge intégré de
  VSCode, comme pour tout conflit git classique — rien de spécifique aux
  worktrees dans la résolution elle-même.

## 5. Limites connues

- **`issues_en_cours` sans verrou explicite.** L'ensemble Python
  `issues_en_cours` (déduplication en mémoire, dans le process du
  watcher) protège contre le retraitement d'une même issue au sein d'un
  même watcher, mais ce n'est **pas** un verrou inter-process — la
  protection inter-process réelle reste le fichier verrou par chemin de
  travail (§2). Deux watchers distincts visant le même `REP_TRAVAIL` par
  erreur de configuration restent exposés au même risque qu'avant #337.
- **Pas d'alerte sur l'accumulation de worktrees.** Rien ne prévient
  Alain si des worktrees s'accumulent faute de merge/nettoyage régulier
  (§3, étape 5) — seul `git worktree list` donne l'état réel. Un projet
  laissé sans repasse pendant longtemps peut accumuler plusieurs
  répertoires frères oubliés.
- **`mode_lecture` / `mode_scratch` non parallélisés.** Le mécanisme ne
  couvre que `mode_write` — les issues en lecture seule ou en lecture
  active (scratch) restent strictement séquentielles dans `REP_TRAVAIL`,
  qu'un ou plusieurs worktrees `mode_write` tournent ou non en parallèle
  à côté.
