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
- **Slots suivants dans des worktrees dédiés.** Toute tâche `mode_write`
  détectée pendant qu'au moins un thread est déjà actif, et tant que
  `MAX_WRITE_PARALLELE` n'est pas atteint, obtient un worktree dédié, nommé
  `<NOM_PROJET>-issue<N>`, branche `worktree-issue-<N>`, créés par
  `git -C <REP_TRAVAIL> worktree add <chemin> -b worktree-issue-<N>`. Si
  la création échoue (chemin ou branche déjà existants, ou toute autre
  erreur git), repli automatique et silencieux sur le traitement
  séquentiel classique — jamais d'exception propagée, l'issue attend
  simplement qu'un slot se libère au cycle suivant.
  - **Emplacement (issues #740 CCL, #749 CCW).** Sous **CCL (Linux)**,
    `<chemin>` est désormais `~/worktrees/<NOM_PROJET>-issue<N>` — un
    dossier **dédié**, séparé des dossiers de projets
    (`DOSSIER_WORKTREES_DEDIE` dans `watcher.py`, variable globale
    modifiable, PAS un champ de `configs/*.conf` ; créé automatiquement au
    besoin). Sous **CCW (Windows)**, même principe mais emplacement
    différent : `<chemin>` est `<parent de REP_TRAVAIL>\worktrees\<NOM_PROJET>-issue<N>`
    — par exemple `C:\CCW\worktrees\scrabble-issue444` pour un projet dont
    `REP_TRAVAIL` est `C:\CCW\Scrabble` (`_dossier_worktrees_dedie_windows()`
    dans `watcher.py`, recalculé à chaque appel à partir de
    `CFG.rep_travail.parent` — **jamais** à partir du profil utilisateur
    /`Path.home()` : les services CCW tournent sous NSSM, éventuellement
    sous un compte distinct de l'utilisateur interactif, dont le profil n'a
    aucun rapport avec l'installation). Dans les deux cas, si le dossier
    dédié ne peut pas être créé ou n'est pas accessible en écriture, repli
    automatique sur l'ancien emplacement — répertoire **frère** de
    `REP_TRAVAIL` (`<REP_TRAVAIL>/../<NOM_PROJET>-issue<N>`) — signalé par
    un `log.warning` explicite dans `logs/watcher-<projet>.log`, pour
    qu'aucune issue ne soit bloquée par ce repli.
  - **Worktrees déjà existants : aucune migration.** Les worktrees créés
    avant l'issue #740 restent à leur ancien emplacement (frère du projet)
    — aucun déplacement automatique. Ils restent trouvés et réutilisables
    par une RELANCE (§2 ci-dessous, issue #725) : la recherche interroge
    `git worktree list` et compare le NOM du dossier, jamais son
    emplacement. Le nettoyage manuel (§3, étape 5) continue de fonctionner
    à l'identique, quel que soit l'emplacement du worktree.
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
- **Réutilisation sur RELANCE, pas de `-bis` vierge (issue #725).** Avant ce
  correctif, une RELANCE (nouveau traitement après un échec/timeout/
  needs-human de la tentative précédente) repartait toujours d'un worktree
  **neuf** : si le chemin standard existait encore (reliquat de la
  tentative précédente, jamais nettoyé automatiquement), le code basculait
  sur `-bis`/`-ter` — un worktree vierge basé sur `master`, qui abandonnait
  tout le travail déjà fait par la tentative précédente (constaté sur
  Rummikub #146 : deux worktrees `rummikub-issue146`/`-bis` pour la même
  issue, travail refait, timeouts répétés). Désormais, `traiter_issue`
  cherche D'ABORD un worktree déjà existant pour cette même issue (nom
  standard ou `-bis`/`-ter` hérité), enregistré comme worktree de ce dépôt,
  dont la branche correspond et qui n'est pas verrouillé par un traitement
  en cours — s'il en existe plusieurs (cas hérité d'avant ce correctif), le
  plus récemment modifié (dernier commit) est choisi. Trouvé, il est REPRIS
  **tel quel** (commits et modifications non commitées compris) : aucun
  `-bis` créé, le travail déjà fait est conservé. CCL reçoit alors un bloc
  de prompt dédié l'invitant à vérifier/compléter ce travail plutôt qu'à le
  refaire, et à le signaler explicitement dans son rapport final. `master`
  n'est **jamais** rebasé automatiquement sur ce worktree repris : si
  `master` a avancé depuis sa création, l'écart (nombre de commits) est
  journalisé et ajouté au compte-rendu de clôture, pour un merge manuel en
  connaissance de cause. Aucun candidat trouvé (première exécution, dossier
  présent mais non enregistré comme worktree, branche absente) : repli
  inchangé sur `_creer_worktree_avec_retries` ci-dessus (nom standard, puis
  `-bis`, puis `-ter`).

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
3. **Merger chaque branche worktree dans `master` manuellement, en premier**,
   une par une, en relisant le diff avant. Rien de spécifique aux worktrees
   ici — un `git merge worktree-issue-<N>` classique depuis `REP_TRAVAIL`
   (ou l'outil habituel).
4. **Consolider les `CHANGELOG-<N>.md` ensuite, depuis `REP_TRAVAIL` —
   jamais depuis un worktree.** C'est l'ordre inverse de celui qu'on
   serait tenté d'appliquer (fusionner le changelog avant de merger, par
   analogie avec « committer avant de merger »), mais c'est le seul qui
   fonctionne en parallélisation :
   ```bash
   cd <rep_master>
   python3 scripts/fusionner_changelog.py
   git diff CHANGELOG.md   # vérifier le résultat avant de committer
   git add CHANGELOG.md && git commit -m "chore(<N>): fusion du changelog"
   ```
   Le script scanne la racine du dépôt indiqué par `--repo` (`.` par
   défaut, donc `REP_TRAVAIL` ici) : une fois le merge de l'étape 3 fait,
   les `CHANGELOG-<N>.md` des branches fusionnées sont désormais présents
   à la racine de `master`, donc trouvés par ce scan par défaut.

   **Pourquoi cet ordre, et pas l'inverse.** Lancer le script *depuis le
   worktree*, avant de merger, modifie `CHANGELOG.md` **sur la branche du
   worktree** elle-même (insertion de l'entrée en tête de fichier). Si
   deux worktrees tournent en parallèle, chacun insère sa propre entrée en
   tête de son propre `CHANGELOG.md`, à partir du même `master` d'origine :
   ce sont deux modifications indépendantes et incompatibles de la même
   zone du même fichier. Le premier merge passe sans histoire, mais le
   second entre en conflit, systématiquement — ce n'est pas un bug du
   script, c'est une conséquence mécanique d'avoir deux branches qui
   modifient le même texte au même endroit. Fusionner d'abord élimine le
   problème à la racine : `master` ne contient alors qu'un seul
   `CHANGELOG.md` de référence, et la consolidation qui s'ensuit n'a
   jamais qu'une seule branche à la fois à combiner avec lui. **Règle
   générale : ne jamais consolider le changelog depuis un worktree,
   toujours depuis `REP_TRAVAIL`, et toujours après le merge des branches
   concernées.**

   Cette règle ne remplace pas la leçon voisine, toujours valable : le
   travail d'un worktree (code) doit être committé *avant* sa fusion.
   L'une concerne le code (committer avant de merger), l'autre le
   changelog (consolider après avoir mergé) — deux étapes différentes,
   dans des sens différents, à ne pas confondre.

   ⚠️ Si un `CHANGELOG-<N>.md` d'une branche déjà mergée est encore
   présent à la racine, non consolidé, au moment d'un `git push` : le
   pousser quand même ne pose pas de problème en soi, mais laisse
   `CHANGELOG.md` incomplet sur le dépôt distant jusqu'à la prochaine
   consolidation — relancer alors `fusionner_changelog.py` depuis
   `REP_TRAVAIL` dès que possible, committer, puis repousser.

   **Méthode alternative, vérifiée mais non recommandée : copier
   `CHANGELOG-<N>.md` sur `master` avant de merger, puis consolider
   depuis `master`.** Elle ne provoque pas le conflit sur `CHANGELOG.md`
   décrit ci-dessus, pour la même raison que l'ordre recommandé : le
   `CHANGELOG.md` de la branche worktree n'est jamais modifié, seul celui
   de `master` l'est. Mais elle a un effet de bord vérifié par un test
   réel : au merge qui suit, `CHANGELOG-<N>.md` — supprimé sur `master`
   par le script, mais toujours présent sans modification sur la branche
   worktree — **réapparaît** à la racine de `master` (git le considère
   comme une addition de la branche, puisque ni l'ancêtre commun ni
   `master` n'y voient de changement net sur ce chemin). Il faut alors le
   supprimer une seconde fois après le merge (`git rm CHANGELOG-<N>.md`).
   Cette méthode fonctionne donc, sans produire la collision visée, mais
   elle n'apporte aucun avantage sur la méthode recommandée (étapes 3-4)
   et lui ajoute ce nettoyage manuel systématique — à réserver aux cas où
   merger en premier n'est, pour une raison quelconque, pas possible.
5. **Nettoyer** une fois la branche mergée :
   ```bash
   git worktree remove <chemin>
   git branch -d worktree-issue-<N>
   ```

**Après la fusion : quoi relancer (issue #727).** Un processus déjà lancé
garde l'ancien code en mémoire jusqu'à son propre redémarrage — l'avoir
lancé avant la fusion, même le même jour, ne suffit pas. Selon les fichiers
touchés par l'issue fusionnée :

| Fichiers modifiés | Quoi relancer |
|---|---|
| `watcher.py` | Relancer les watchers de projet concernés — de préférence quand aucune issue en écriture ne tourne (un redémarrage interromprait une issue en cours). |
| `app/*.py`, templates, ou modules importés par `new_issue.py` | Redémarrer `new_issue.py`. |
| `scripts/watcher_issues_inbox.py` | Relancer le Watcher spool — sans conséquence pour les issues en cours, il est indépendant des watchers de projet. |
| JavaScript ou CSS uniquement | Ctrl+Maj+R dans le navigateur — aucun redémarrage. |
| Documentation ou tests uniquement | Rien à relancer. |

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
- **Alerte accumulation de worktrees (issue #432).** En début de chaque
  cycle de polling, juste après `git pull --ff-only`, `watcher.py` compte
  les worktrees secondaires actifs (`git worktree list`, hors
  `REP_TRAVAIL`) et émet un `log.warning` (chemin + branche de chacun) dès
  que ce nombre dépasse `SEUIL_ALERTE_WORKTREES` (clé `.conf`, entier,
  défaut **3**) — visible dans l'onglet Journal watcher de l'interface.
  Simple signal dans le log, pas de notification ntfy/bureau ; le
  nettoyage (§3, étape 5) reste entièrement manuel.
- **`mode_lecture` / `mode_scratch` non parallélisés.** Le mécanisme ne
  couvre que `mode_write` — les issues en lecture seule ou en lecture
  active (scratch) restent strictement séquentielles dans `REP_TRAVAIL`,
  qu'un ou plusieurs worktrees `mode_write` tournent ou non en parallèle
  à côté.
- **`-bis`/`-ter` hérités ni supprimés ni migrés (issue #725).** La
  réutilisation sur relance ci-dessus (§2) choisit le plus récent si
  plusieurs worktrees existent déjà pour une même issue, mais ne supprime
  ni ne fusionne jamais les autres — un `-bis` laissé par une relance
  d'avant ce correctif reste tel quel tant qu'Alain ne le nettoie pas
  manuellement (§3, étape 5). Le nettoyage des worktrees reste, dans tous
  les cas, entièrement manuel.
