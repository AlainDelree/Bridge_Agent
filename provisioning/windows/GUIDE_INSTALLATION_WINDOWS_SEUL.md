# GUIDE_INSTALLATION_WINDOWS_SEUL — Bridge_Agent sur un PC Windows seul, avec Mistral Vibe

Dernière mise à jour : 9 novembre 2026. Version de travail : à corriger après la première installation réelle.

Ce guide ne répète pas ce que disent déjà les autres documents du dépôt : il donne l'ordre des étapes, renvoie vers le bon document pour le détail, et signale les pièges déjà rencontrés.

**État de chaque point.** Chaque étape porte une marque :
- **établi** : lu dans le code ou dans la documentation du dépôt ;
- **constaté** : vu en vrai sur une machine (PC d'Alain) ;
- **à vérifier** : jamais essayé sur un Windows seul, à valider lors de l'installation.

Aucune étape de ce guide ne demande de coller un secret dans une conversation.

## 0. De quoi s'agit-il

Une seule machine Windows fait tout : l'interface web (`new_issue.py`), le dépôt d'issues par fichiers, les watchers des projets, et l'agent d'exécution, qui est Mistral Vibe (abonnement Mistral, connexion par compte). Il n'y a ni ThinkPad Linux, ni second PC (rôle « CCW »). Le rôle CCW délégué par SSH n'est **pas** utilisé ici (établi).

Ce qui n'existe pas dans cette installation : l'outil de relecture Relecture_Bridge (la fusion se fait à la main, voir §10), le mode « lecture active » avec Vibe (établi, limite de Vibe).

## 1. Avant de venir (préparation côté Alain)

- Compte GitHub de l'ami créé ; dépôts de ses projets créés ou à créer depuis l'interface (§8).
- Abonnement Mistral actif et identifiants connus de l'ami (la connexion de Vibe se fait dans le navigateur, §6).
- Ce guide imprimé ou ouvert sur un second écran.
- **Rien à préparer côté jetons** : le rôle CCW n'étant pas utilisé, les jetons GitHub dédiés des notes précédentes ne servent pas ici (à vérifier : `gh auth login` suffit à tout).

## 2. Prérequis Windows (PowerShell, utilisateur normal)

Git, GitHub CLI et Python. Avec `winget` (inclus dans Windows 11 récent) :

```powershell
winget install --id Git.Git -e; winget install --id GitHub.cli -e; winget install --id Python.Python.3.12 -e
```

Fermer puis rouvrir PowerShell, puis vérifier : `git --version; gh --version; python --version`. **À vérifier** : les trois identifiants `winget` sur la machine de l'ami ; sinon installer à la main depuis les sites officiels.

## 3. Récupérer Bridge_Agent

```powershell
git clone https://github.com/AlainDelree/Bridge_Agent.git C:\CCW\Bridge_Agent
```

`C:\CCW\Bridge_Agent` est le chemin d'exemple utilisé dans ce guide ; **tout autre dossier sans espace convient** (lu dans le code : `installer_demarrage_session.ps1` et `provisionner_new_issue_local.ps1` calculent le chemin du dépôt depuis leur propre emplacement). Le seul endroit à adapter à la main est l'alias `bridge` du profil PowerShell (`NEW_ISSUE_LOCAL_WINDOWS.md` §2). Les scripts du rôle CCW (`provisionner.ps1`, `ajouter_projet_ccw.ps1`…) supposent l'ancien chemin, mais ne servent pas ici. À vérifier : le dossier où les projets sont créés.

**Recevoir les mises à jour de l'outil (à vérifier).** Ce dossier est une copie de l'outil Bridge_Agent, publié par Alain ; les projets de l'utilisateur ont leurs propres dépôts, ailleurs. Quand Alain corrige ou améliore l'outil, ces changements arrivent sur GitHub mais pas dans cette copie. Sur le PC fixe d'Alain, un service CCW fait cette mise à jour seul avant chaque cycle ; cette installation n'a pas ce service, et aucun équivalent n'est confirmé. Il n'y a donc rien à faire au quotidien : **seulement quand Alain annonce une mise à jour**, lancer :

```powershell
git -C C:\CCW\Bridge_Agent pull --ff-only
```

Puis relancer les watchers pour que le nouveau code soit pris en compte.

## 4. Connexion à GitHub

```powershell
gh auth login
```

Le compte connecté devient le **seul auteur autorisé** à faire traiter des issues (établi, issue #859 : lecture de l'identité par `gh`). Il peut aussi être imposé par un fichier `identite_locale.conf` à la racine du dépôt (ignoré par git), si `gh` ne répond pas dans le contexte d'un service. En cas d'identité introuvable, le watcher refuse volontairement de démarrer : ce n'est pas un bogue.

## 5. Dépendances de l'interface et alias

Suivre `provisioning/windows/NEW_ISSUE_LOCAL_WINDOWS.md` : script `provisionner_new_issue_local.ps1` (dépendances Python, pare-feu), puis l'alias PowerShell `bridge` (établi ; constaté chez Alain).

**Mot de passe de l'interface (constaté)** :
- `python new_issue.py --set-password` (saisie invisible, deux fois) affiche une ligne à mettre dans `configs\bridge_agent.conf`.
- La ligne doit être de la forme `MOT_DE_PASSE = <hash>` : le hash seul sur sa ligne est ignoré.
- Ce fichier doit aussi contenir `NOM`, `DEPOT` et `REP_TRAVAIL`, sinon l'interface répète « MOT_DE_PASSE non configuré » sans autre message.
- Le dossier `configs\` n'existe pas dans le dépôt (non versionné) : le créer.
- **À vérifier** : si l'interface lancée sans `--lan` (adresse `localhost` seule) exige ce mot de passe ; c'est le mode conseillé pour une machine seule, et il est plus fiable pour la copie dans le presse-papier.

## 6. Mistral Vibe

Détail complet : `provisioning/vibe/README.md`. Étapes constatées sur le PC d'Alain (Vibe 3.1.0) :

1. Installer `uv` : `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`, rouvrir PowerShell.
2. `uv tool install mistral-vibe`, puis `vibe --version`.
3. **Connexion par compte, pas par clé API** : `vibe --setup`, puis « Launch browser ». Une clé API en mode gratuit est restée bloquée sur « Retrying » sans jamais répondre (constaté). Si une ligne `MISTRAL_API_KEY=…` traîne dans `~\.vibe\.env`, la retirer avant.
4. Copier le profil d'écriture : `copy provisioning\vibe\agents\bridge_ecriture.toml $env:USERPROFILE\.vibe\agents\` (créer le dossier `agents` si besoin). Constaté.
5. Vérifier depuis le dossier d'un projet : `vibe --prompt "réponds ok"`.
6. Déclarer le dossier du projet dans `~\.vibe\trusted_folders.toml` (README Vibe §2). Établi ; Vibe ne pose la question que si le dossier contient un répertoire `.vibe/`.

**Compte sous lequel tout tourne.** La connexion de Vibe est dans le trousseau Windows de l'utilisateur. Un programme qui tourne sous un autre compte ne la voit pas : c'est pourquoi les watchers démarrent dans la session de l'utilisateur (§9). Constaté sur un service CCW, qui a échoué sous `LocalSystem` puis réussi sous le compte de l'utilisateur.

## 7. Régler l'emplacement du dépôt d'issues (facultatif)

Par défaut, les fichiers d'issues se déposent dans `issues_inbox\` du dépôt. Une clé `INBOX_DIR` dans `configs\watcher_issues_inbox.conf` permet d'utiliser un autre dossier (établi). Régler le navigateur pour télécharger directement dans ce dossier évite la fenêtre « choisir l'emplacement ».

## 8. Créer le premier projet

Dans l'interface, bouton « Nouveau projet », **sans** cocher « Projet CCW » (cette case suppose une seconde machine ; elle échoue proprement avec un message explicite, établi). Le code de création n'a rien de spécifique à Linux (établi), mais n'a jamais été exécuté sur un Windows seul : **à vérifier**.

Ensuite, dans `configs\<projet>.conf` :
- ajouter une ligne `AGENT = vibe` ;
- laisser `CMD_BACKUP` à la commande standard (une commande personnalisée fait afficher de faux avertissements) ;
- **modifier ce fichier uniquement quand aucune issue en écriture ne tourne** (sur n'importe quel projet), sinon la modification est annulée à la fin de cette issue (garde-fou #318, constaté) ; puis relancer le watcher du projet, qui ne lit son `.conf` qu'au démarrage ;
- versionner `consignes\projet_<nom>.md` s'il existe, sinon la fusion d'une branche est refusée.

Piège connu de la création (constaté chez Alain, dépend d'un crochet de tests au `pre-push`) : le push du commit de documentation a un délai de 60 s ; si un crochet lent est installé, la création affiche « push échoué ». Vérifier avec `git fetch` puis `git log origin/master..master`, et pousser à la main. Un correctif est prévu.

## 9. Démarrage automatique

Détail : `provisioning/windows/DEMARRAGE_SESSION_WINDOWS.md`. D'abord une simulation, qui n'installe rien :

```powershell
.\provisioning\windows\installer_demarrage_session.ps1 -Projets <projet> -DryRun
```

Puis, sans `-DryRun`, l'installation réelle : tâches planifiées à l'ouverture de session (watchers des projets, dépôt d'issues, interface web), sans mot de passe. Constaté : la simulation s'exécute sans erreur depuis SSH sur le PC d'Alain ; l'installation réelle n'a **jamais** été essayée (à vérifier, avec les neuf contrôles du §8 de ce document).

À savoir : la bulle de bureau et le son ne fonctionnent que dans la session de l'utilisateur (établi) ; le mode service en option ne les affiche pas.

## 10. Travailler au quotidien

- **Ne jamais écrire `for-windows` dans une issue.** Sur une machine seule, cette étiquette désigne un service CCW qui n'existe pas : l'issue reste ouverte sans que personne la traite et sans signal visible. L'étiquette normale est `for-linux` (nom trompeur, comportement correct), posée par défaut. Détail : `provisioning/windows/ROUTAGE_LABELS_POSTE_SEUL.md` (établi). Un réglage de fond est décrit mais pas implémenté.
- **Lecture seule avec Vibe** : pas de mode « lecture active » (établi).
- **Fusion d'une issue terminée, sans Relecture_Bridge** (voir `WORKTREES.md`) : `git merge worktree-issue-<N>`, puis `python scripts\fusionner_changelog.py`, puis commit et `git push`. Le crochet de tests s'exécute au push.
- **Notifications** : bulle et bip sous Windows, issue #863 (établi par les tests ; à vérifier en réel).
- **Deux sortes d'issues, à ne pas confondre.** Une issue **pour un de ses projets** se dépose chez lui et se traite sur son PC, sans passer par Alain. Une issue **pour l'outil lui-même** (un défaut de Bridge_Agent, une amélioration) ne se traite pas chez lui : il demande à Mistral de la rédiger en fichier `.txt` et l'envoie à Alain, qui la relit, la lance de son côté et lui dit quand la correction est disponible (puis `git pull`, voir §3). Pour qu'Alain puisse corriger sans voir le PC : message d'erreur exact (copié, pas résumé), ce qui a été fait juste avant, ce qui était attendu, et le journal concerné dans `logs\`.

## 11. Premier essai

Une issue minuscule, en mode écriture, sans étiquette `for-windows`, par exemple : créer à la racine du dépôt du projet un fichier d'une ligne et le committer. Une fois terminée, vérifier sur GitHub que l'issue porte le label `agent-vibe` : c'est la preuve que c'est bien Vibe qui l'a traitée (constaté chez Alain). Noter ci-dessous tout ce qui plante.

## 12. Déroulé de la visite

1. Prérequis, clonage, `gh auth login`, dépendances, alias (§2 à §5), à la main sur son PC.
2. Vibe, connexion par compte (§6).
3. Premier projet et `AGENT = vibe` (§8) ; simulation puis installation du démarrage (§9) ; issue de test (§11).
4. Si Alain pilote le PC depuis son portable en SSH : serveur OpenSSH et `configurer_ssh_ccw.ps1`, **clé SSH dédiée** à la visite, retirée de `administrators_authorized_keys` à la fin, et configuration d'origine remise côté portable (sauvegarder `configs/ccw_ssh.conf` avant). Non indispensable pour ce guide : tout se fait localement sur le PC.

## 13. Journal d'installation (à compléter pendant la visite)

| Étape | Résultat | Ce qui a posé problème | Correction |
|---|---|---|---|
| | | | |
