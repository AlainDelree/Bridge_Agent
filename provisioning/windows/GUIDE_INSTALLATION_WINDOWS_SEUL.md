# GUIDE_INSTALLATION_WINDOWS_SEUL — Bridge_Agent sur un PC Windows seul, avec Mistral Vibe

Dernière mise à jour : 10 novembre 2026. Corrigé d'après un premier essai réel complet (compte de test sur le PC d'Alain, voir le journal au §13) ; §0 et §8 : réglages `COPIE_NON_PROPRIETAIRE` (issue #869) et `MACHINE_SEULE` (issue #870), détection automatique de Relecture_Bridge, faux encadré « Action requise » corrigé.

Ce guide ne répète pas ce que disent déjà les autres documents du dépôt : il donne l'ordre des étapes, renvoie vers le bon document pour le détail, et signale les pièges déjà rencontrés.

**État de chaque point.** Chaque étape porte une marque :
- **établi** : lu dans le code ou dans la documentation du dépôt ;
- **constaté** : vu en vrai sur une machine (PC d'Alain) ;
- **à vérifier** : jamais essayé sur un Windows seul, à valider lors de l'installation.

Aucune étape de ce guide ne demande de coller un secret dans une conversation.

## 0. De quoi s'agit-il

Une seule machine Windows fait tout : l'interface web (`new_issue.py`), le dépôt d'issues par fichiers, les watchers des projets, et l'agent d'exécution, qui est Mistral Vibe (abonnement Mistral, connexion par compte). Il n'y a ni ThinkPad Linux, ni second PC (rôle « CCW »). Le rôle CCW délégué par SSH n'est **pas** utilisé ici (établi).

Ce qui n'existe pas dans cette installation : l'outil de relecture Relecture_Bridge (la fusion se fait à la main, voir §10), le mode « lecture active » avec Vibe (établi, limite de Vibe). Son absence est détectée automatiquement (établi, issue #870) : l'encadré de rappel « relancer le hook de relecture », propre à la machine d'Alain, ne s'affiche donc jamais ici après la création d'un projet.

## 1. Avant de venir (préparation côté Alain)

- Compte GitHub de l'ami créé ; dépôts de ses projets créés ou à créer depuis l'interface (§8).
- Abonnement Mistral actif et identifiants connus de l'ami (la connexion de Vibe se fait dans le navigateur, §6).
- Ce guide imprimé ou ouvert sur un second écran.
- **Rien à préparer côté jetons** : le rôle CCW n'étant pas utilisé, les jetons GitHub dédiés des notes précédentes ne servent pas ici (à vérifier : `gh auth login` suffit à tout).

## 2. Prérequis Windows (PowerShell, utilisateur normal)

Git, GitHub CLI et Python. Avec `winget` (inclus dans Windows 11 récent) :

```powershell
winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements; winget install --id GitHub.cli -e --source winget --accept-package-agreements --accept-source-agreements; winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
```

L'option `--source winget` évite que `winget` demande d'accepter les conditions de la source « msstore » (le catalogue du Microsoft Store), inutile ici (constaté). Les caractères illisibles comme `Ã©` dans la console ne sont qu'un défaut d'affichage, sans conséquence.

Fermer puis rouvrir PowerShell, puis vérifier : `git --version; gh --version; python --version`.

**Piège constaté : le raccourci « python » du Microsoft Store.** Si `python` répond « Python est introuvable ; exécutez sans arguments à installer à partir du Microsoft Store », ce n'est pas que Python manque : Windows place un faux `python` qui masque le vrai. Désactiver les deux lignes `python.exe` et `python3.exe` dans Paramètres, Applications, Paramètres avancés des applications, **Alias d'exécution d'application**, puis rouvrir PowerShell. À défaut, ajouter pour la fenêtre en cours le dossier du vrai Python (`$env:LOCALAPPDATA\Programs\Python\Python312`) au début de `$env:Path` (la commande `py` n'est pas installée avec cette version). Faire cette correction **avant** l'étape 9 : les tâches planifiées rencontreraient le même défaut. **À vérifier** : les trois identifiants `winget` sur la machine de l'ami ; sinon installer à la main depuis les sites officiels.

**Deux règles pour toutes les commandes de ce guide (constaté).** Les écrire dans une vraie console : **Windows PowerShell** ou **Terminal**, ni « PowerShell ISE » (qui ne gère pas les programmes interactifs : `vibe --setup` y répond « Interactive mode needs a terminal », cause supposée, non confirmée), ni la fenêtre « (x86) ». Et lancer les scripts `.ps1` du dépôt par `powershell -NoProfile -ExecutionPolicy Bypass -File <script>` : Windows bloque par défaut les scripts d'un compte neuf, et cette forme ne change aucun réglage de la machine.

## 3. Récupérer Bridge_Agent

```powershell
git clone https://github.com/AlainDelree/Bridge_Agent.git "$env:USERPROFILE\Bridge_Agent"; Set-Location "$env:USERPROFILE\Bridge_Agent"
```

Le dossier conseillé est `Bridge_Agent` dans le dossier personnel de l'utilisateur (`$env:USERPROFILE`, par exemple `C:\Users\<nom>\Bridge_Agent`) : il n'exige aucun droit d'administrateur. **Ne pas utiliser `C:\Program Files`** (protégé : le clonage échoue avec `Permission denied`, constaté) ni `C:\CCW`, dossier du rôle CCW délégué, absent ici. Le bloc rouge « NativeCommandError » qui s'affiche pendant le clonage n'est que la façon dont PowerShell présente les messages de progression de git : ce n'est pas une erreur (constaté).

Créer tout de suite le fichier de réglages local `identite_locale.conf` de la copie (ignoré par git, voir §4), avec les deux réglages utiles à une copie de l'outil qui n'appartient pas à son utilisateur :

```powershell
Set-Content -Path identite_locale.conf -Value "COPIE_NON_PROPRIETAIRE = oui`nMAJ_AUTO_DEPOT = oui" -Encoding ascii; git status --short
```

`git status --short` ne doit rien afficher (preuve que le fichier est bien ignoré). Le codage `ascii` évite le marqueur invisible que l'option `utf8` de PowerShell 5 ajoute en début de fichier. **`COPIE_NON_PROPRIETAIRE` doit être posé avant de créer le premier projet** (§8). Vérification de la lecture du fichier : `python -c "import identite; print(identite.copie_non_proprietaire(), repr(identite.valeur_locale('MAJ_AUTO_DEPOT')))"` doit afficher `True 'oui'`.

Ce dossier est une copie de l'outil ; **tout autre dossier sans espace et accessible en écriture convient** (lu dans le code : `installer_demarrage_session.ps1` et `provisionner_new_issue_local.ps1` calculent le chemin du dépôt depuis leur propre emplacement). Le seul endroit à adapter à la main est l'alias `bridge` du profil PowerShell (`NEW_ISSUE_LOCAL_WINDOWS.md` §2). Les scripts du rôle CCW (`provisionner.ps1`, `ajouter_projet_ccw.ps1`…) supposent `C:\CCW\Bridge_Agent`, mais ne servent pas ici. À vérifier : le dossier où les projets sont créés.

**Recevoir les mises à jour de l'outil (établi, issue #868).** Ce dossier est une copie de l'outil Bridge_Agent, publié par Alain ; les projets de l'utilisateur ont leurs propres dépôts, ailleurs. Quand Alain corrige ou améliore l'outil, ces changements arrivent sur GitHub mais pas dans cette copie. Sur le PC fixe d'Alain, un service CCW fait cette mise à jour seul avant chaque cycle ; cette installation n'a pas ce service, mais `new_issue.py` peut désormais faire l'équivalent tout seul à son lancement — réglage **facultatif, désactivé par défaut**, à ajouter dans `identite_locale.conf` (racine du dépôt, gitignoré, voir §4 ci-dessous) :

```
MAJ_AUTO_DEPOT = oui
```

Avec ce réglage, chaque lancement de `new_issue.py` tente un `git pull --ff-only` rapide (quelques secondes maximum, jamais bloquant) avant d'ouvrir l'interface : rien n'est écrasé si la copie a été personnalisée (modification non enregistrée) ou si son historique a divergé de celui d'Alain (ex. un correctif local pas encore poussé) — la tentative est alors simplement ignorée, sans toucher au dépôt. Le résultat (à jour, mis à jour avec la liste des fichiers changés, ignoré ou en échec, avec sa raison) s'affiche à la fois dans la console de `new_issue.py` (capturée dans `logs\new_issue-session.log` sous l'installeur de démarrage de session, §9) et dans un bandeau de l'interface elle-même. **Un rappel important accompagne toute mise à jour réussie** : les watchers déjà démarrés continuent de tourner sur l'ancien code tant qu'ils ne sont pas relancés — penser à les relancer (§9 ou boutons de l'onglet Infrastructure) après une mise à jour signalée.

Deux clés facultatives supplémentaires, `MAJ_AUTO_DEPOT_REMOTE` et `MAJ_AUTO_DEPOT_BRANCHE`, permettent de suivre un dépôt distant/une branche différents de ceux déjà configurés dans le dépôt — utile si cette copie est elle-même personnalisée sur sa propre branche mais doit malgré tout continuer à suivre celle d'Alain (voir §8.1 de `BRIDGE_AGENT_DOC.md`).

Sans ce réglage (valeur par défaut), ou en complément quand Alain annonce une mise à jour entre deux lancements de l'interface, la méthode manuelle reste :

```powershell
git -C "$env:USERPROFILE\Bridge_Agent" pull --ff-only
```

Puis relancer les watchers pour que le nouveau code soit pris en compte.

## 4. Connexion à GitHub

```powershell
gh auth login
```

Choisir GitHub.com, HTTPS, la connexion par navigateur. Le code à 8 caractères (`XXXX-XXXX`) s'affiche **dans la fenêtre PowerShell** (ligne « First copy your one-time code »), à saisir sur la page web qui s'ouvre. Vérifier avec `gh auth status` (constaté). **Affichage et PowerShell 5 (constaté)** : les accents des commandes `gh` et des fichiers journaux s'affichent mal ; passer d'abord la console en UTF-8 (`[Console]::OutputEncoding = [Text.Encoding]::UTF8`) et lire les fichiers avec `-Encoding UTF8`. L'option `--jq` de `gh` perd ses guillemets sous PowerShell 5 : filtrer plutôt en enchaînant `| ConvertFrom-Json`.

Le compte connecté devient le **seul auteur autorisé** à faire traiter des issues (établi, issue #859 : lecture de l'identité par `gh`). Il peut aussi être imposé par un fichier `identite_locale.conf` à la racine du dépôt (ignoré par git), si `gh` ne répond pas dans le contexte d'un service. En cas d'identité introuvable, le watcher refuse volontairement de démarrer : ce n'est pas un bogue.

## 5. Dépendances de l'interface et alias

Pour une machine seule, **ne pas utiliser** `provisionner_new_issue_local.ps1` : il exige une fenêtre administrateur et ouvre un port du pare-feu pour le mode réseau `--lan`, inutile ici. Installer les dépendances de l'interface depuis le dossier du dépôt (constaté) :

```powershell
python -m pip install -r requirements.txt
```

Puis lancer l'interface (`python new_issue.py`, ou la tâche de démarrage du §9, qui la lance avec `--no-browser`) et ouvrir **`http://127.0.0.1:5100`** dans le navigateur. Constaté : en mode local (sans `--lan`), l'interface s'ouvre **sans mot de passe**. Pour un alias `bridge`, voir `NEW_ISSUE_LOCAL_WINDOWS.md` §2 en retirant `--lan` et en adaptant le dossier (`"$env:USERPROFILE\Bridge_Agent"`) ; non essayé ici (**à vérifier**).

**Mot de passe de l'interface — uniquement si le mode réseau `--lan` est utilisé** (constaté chez Alain) :
- `python new_issue.py --set-password` (saisie invisible, deux fois) affiche une ligne à mettre dans `configs\bridge_agent.conf`.
- La ligne doit être de la forme `MOT_DE_PASSE = <hash>` : le hash seul sur sa ligne est ignoré.
- Ce fichier doit aussi contenir `NOM`, `DEPOT` et `REP_TRAVAIL`, sinon l'interface répète « MOT_DE_PASSE non configuré » sans autre message.
- Le dossier `configs\` n'existe pas dans le dépôt (non versionné) : le créer.
- Sans `--lan` (adresse `127.0.0.1` seule), aucun mot de passe n'est demandé (constaté) ; c'est le mode conseillé pour une machine seule.

## 6. Mistral Vibe

Détail complet : `provisioning/vibe/README.md`. Étapes constatées sur le PC fixe d'Alain (Vibe 3.1.0) puis dans un compte de test :

1. Installer `uv` : `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`, puis, pour la fenêtre en cours, `$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"`.
2. **Installer une version précise, jamais « la dernière »** : `uv tool install "mistral-vibe==3.1.0"`, puis `vibe --version`. C'est la version qui a fonctionné sur le PC fixe et dans le compte de test ; avec la 3.1.1, une première issue est restée bloquée plus de huit minutes (la cause n'a pas été isolée : plusieurs choses ont changé entre le blocage et le succès). Ne la changer que volontairement, jamais par `uv tool upgrade`.
3. **Connexion par compte, pas par clé API** : `vibe --setup` dans une vraie console, puis « Launch browser ». Une clé API en mode gratuit est restée bloquée sur « Retrying » sans jamais répondre (constaté). Si une ligne `MISTRAL_API_KEY=…` traîne dans `~\.vibe\.env`, la retirer avant.
4. Copier le profil d'écriture : `New-Item -ItemType Directory -Force "$env:USERPROFILE\.vibe\agents"` puis `Copy-Item provisioning\vibe\agents\bridge_ecriture.toml "$env:USERPROFILE\.vibe\agents\"`. Constaté.
5. Vérifier depuis un dossier de projet : `vibe --prompt "réponds ok"`. Le résultat attendu est `ok`, précédé de la ligne « Reading API keys from the system keyring » : c'est le signe que la connexion par compte est bien lue (constaté).
6. Dossiers de confiance (`~\.vibe\trusted_folders.toml`) : **probablement inutile**. La documentation de Mistral indique que le mode non interactif ne demande jamais de confiance de dossier. Pendant l'essai, ce fichier a été renseigné (dossier du projet et dossier des worktrees) avant le premier succès : son effet n'a pas été isolé. À essayer seulement en cas de blocage inexpliqué.

**Refus de commandes `bash` (constaté, à surveiller).** En mode non interactif, Vibe refuse automatiquement les commandes `bash` qui contiennent une substitution de commande (`$(…)`) ou une redirection (`>`), et prend une option Windows comme `date /T` pour un chemin hors du dossier de travail ; le profil `bridge_ecriture` ne les autorise pas (la permission « always » ne couvre pas ces cas). Une tâche peut ainsi échouer ou rester sans réponse selon la manière dont le modèle écrit ses commandes. Une consigne dédiée à l'agent Vibe est prévue. En attendant, un message de clôture parlant de commande refusée n'indique pas une panne de l'installation.

**Compte sous lequel tout tourne.** La connexion de Vibe est dans le trousseau Windows de l'utilisateur. Un programme qui tourne sous un autre compte ne la voit pas : c'est pourquoi les watchers démarrent dans la session de l'utilisateur (§9). Constaté sur un service CCW, qui a échoué sous `LocalSystem` puis réussi sous le compte de l'utilisateur.

## 7. Régler l'emplacement du dépôt d'issues (facultatif)

Par défaut, les fichiers d'issues se déposent dans `issues_inbox\` du dépôt. Une clé `INBOX_DIR` dans `configs\watcher_issues_inbox.conf` permet d'utiliser un autre dossier (établi). Régler le navigateur pour télécharger directement dans ce dossier évite la fenêtre « choisir l'emplacement ».

## 8. Créer le premier projet

**Avant de créer le premier projet, activer le réglage `COPIE_NON_PROPRIETAIRE` (établi, issue #869).** Cette copie de l'outil appartient à Alain, pas à l'ami qui l'utilise ici : sans ce réglage, la création (et la suppression) d'un projet réécrirait les tableaux §2/§7 de `BRIDGE_AGENT_DOC.md` avec les seuls projets de l'ami, créerait un commit local qui ferait diverger la copie de celle d'Alain (le `git pull --ff-only` du §3 serait alors systématiquement refusé), puis tenterait un push qui échouerait — ou écraserait la doc d'Alain si les droits d'écriture étaient accordés par erreur. Ajouter dans `identite_locale.conf` (même fichier que `MAJ_AUTO_DEPOT`, §3) :

```
COPIE_NON_PROPRIETAIRE = oui
```

Avec ce réglage, créer ou supprimer un projet n'écrit, ne committe ni ne pousse plus jamais `BRIDGE_AGENT_DOC.md` : les mêmes informations (tableaux §2/§7) sont écrites dans `PROJETS_LOCAUX.md`, fichier local gitignoré, régénéré automatiquement à chaque création/suppression — à donner tel quel à Mistral Vibe pour qu'il connaisse les noms valides des projets de l'ami. Le résultat de la création l'annonce clairement (ex. « liste des projets écrite dans PROJETS_LOCAUX.md, doc de l'outil inchangée »), sans jamais afficher « push échoué » dans ce cas — ni, depuis #870, le faux encadré orange « Action requise » qui s'affichait encore à tort juste après (établi, corrigé). **Ne pas pousser `BRIDGE_AGENT_DOC.md` à la main** après une création/suppression avec ce réglage actif : il n'a pas été modifié, il n'y a rien à pousser.

**Également avant de créer le premier projet, poser le réglage `MACHINE_SEULE` (établi, issue #870)** : cette installation n'a pas de second poste Windows délégué (rôle CCW, §8) ; sans ce réglage, l'onglet « CCW » de la barre d'onglets et la case « Projet CCW » du formulaire de nouveau projet restent visibles, sans aucune utilité et avec un risque de piège (label `for-windows` posé par erreur, voir `provisioning/windows/ROUTAGE_LABELS_POSTE_SEUL.md`). Ajouter, dans le même `identite_locale.conf` :

```
MACHINE_SEULE = oui
```

Avec ce réglage, l'onglet « CCW » et la case « Projet CCW » sont masqués dans l'interface (établi). **Ne règle pas** le piège du label `for-windows` lui-même (routage, issue #867, toujours non implémenté) : laisser quand même le champ `LABELS` vide à la création d'une issue, comme indiqué dans `ROUTAGE_LABELS_POSTE_SEUL.md`.

Dans l'interface, bouton « Nouveau projet ». Constaté dans un compte de test : la création fonctionne ; le dossier du projet est créé **directement dans le dossier personnel, sous le nom du dépôt GitHub** (ex. `C:\Users\bridgetest\WindowsBA` pour le projet `windowsba`), le dépôt GitHub est créé sous le compte connecté et le premier push est fait. Les dossiers de travail des issues en écriture sont créés dans `%USERPROFILE%\worktrees\`. Avant la correction de l'issue #870, deux encadrés « Action requise » s'affichaient à tort après la création (le commit de la doc « a échoué », puis « relancer le hook de relecture ») : ils ne doivent plus apparaître ; s'ils apparaissent, les ignorer.

Ensuite, dans `configs\<projet>.conf` :
- ajouter une ligne `AGENT = vibe` ;
- laisser `CMD_BACKUP` à la commande standard (une commande personnalisée fait afficher de faux avertissements) ;
- **modifier ce fichier uniquement quand aucune issue en écriture ne tourne** (sur n'importe quel projet), sinon la modification est annulée à la fin de cette issue (garde-fou #318, constaté) ; puis relancer le watcher du projet, qui ne lit son `.conf` qu'au démarrage ;
- versionner `consignes\projet_<nom>.md` s'il existe, sinon la fusion d'une branche est refusée.

Piège connu de la création **sans le réglage `COPIE_NON_PROPRIETAIRE`** (constaté chez Alain, dépend d'un crochet de tests au `pre-push`) : le push du commit de documentation a un délai de 60 s ; si un crochet lent est installé, la création affiche « push échoué ». Vérifier avec `git fetch` puis `git log origin/master..master`, et pousser à la main. Un correctif est prévu. **Ne concerne pas** une copie avec `COPIE_NON_PROPRIETAIRE` actif : aucun push n'est jamais tenté sur `BRIDGE_AGENT_DOC.md` dans ce cas.

## 9. Démarrage automatique

Détail : `provisioning/windows/DEMARRAGE_SESSION_WINDOWS.md`. D'abord une simulation, qui n'installe rien :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\provisioning\windows\installer_demarrage_session.ps1 -Projets <projet> -DryRun
```

Avant l'installation réelle : arrêter l'interface si elle tourne dans une autre fenêtre (elle serait lancée deux fois sur le même port), et vérifier que `(Get-Command python).Source` ne contient pas `WindowsApps` (le script enregistre le chemin de Python tel qu'il le trouve). Puis la même commande **sans** `-DryRun` : trois tâches planifiées démarrent à l'ouverture de session, sans mot de passe (watcher du projet, dépôt d'issues, interface web). Constaté sur un compte de test : les trois tâches sont `Running` juste après l'installation, et elles repartent seules après une déconnexion suivie d'une reconnexion. Les neuf contrôles listés dans `DEMARRAGE_SESSION_WINDOWS.md` §8 n'ont pas tous été faits : seuls ces deux points sont vérifiés.

**Pièges constatés au démarrage de session.** (1) Les journaux `logs\*-session.log` ne reçoivent la sortie des programmes qu'à leur arrêt (le superviseur les recopie à ce moment), donc rien de ce que `new_issue.py` affiche n'y est visible pendant son fonctionnement, ni après une déconnexion ; le message de mise à jour automatique se lit dans le bandeau de l'interface. (2) La mise à jour automatique du §3 peut annoncer « échec : délai dépassé (8 s) » à l'ouverture de session alors que le dépôt a bien été mis à jour : vérifier avec `git log -1 --oneline`. (3) Les watchers démarrent en même temps que l'interface et peuvent donc charger l'ancien code avant la fin de la mise à jour : après une mise à jour signalée, relancer les watchers (ou fermer puis rouvrir la session).

À savoir : la bulle de bureau et le son ne fonctionnent que dans la session de l'utilisateur (établi) ; le mode service en option ne les affiche pas.

## 10. Travailler au quotidien

- **Ne jamais écrire `for-windows` dans une issue.** Sur une machine seule, cette étiquette désigne un service CCW qui n'existe pas : l'issue reste ouverte sans que personne la traite et sans signal visible. L'étiquette normale est `for-linux` (nom trompeur, comportement correct), posée par défaut. Détail : `provisioning/windows/ROUTAGE_LABELS_POSTE_SEUL.md` (établi). Un réglage de fond est décrit mais pas implémenté.
- **Lecture seule avec Vibe** : pas de mode « lecture active » (établi).
- **Fusion d'une issue terminée, sans Relecture_Bridge** (voir `WORKTREES.md`) : `git merge worktree-issue-<N>`, puis `python scripts\fusionner_changelog.py`, puis commit et `git push`. Le crochet de tests s'exécute au push.
- **Notifications** : constaté, une bulle « <projet> #<n> — traitée » s'affiche à la fin d'une issue, dans la session de l'utilisateur (issue #863). Le bip n'a pas été vérifié.
- **Deux sortes d'issues, à ne pas confondre.** Une issue **pour un de ses projets** se dépose chez lui et se traite sur son PC, sans passer par Alain. Une issue **pour l'outil lui-même** (un défaut de Bridge_Agent, une amélioration) ne se traite pas chez lui : il demande à Mistral de la rédiger en fichier `.txt` et l'envoie à Alain, qui la relit, la lance de son côté et lui dit quand la correction est disponible (puis `git pull`, voir §3). Pour qu'Alain puisse corriger sans voir le PC : message d'erreur exact (copié, pas résumé), ce qui a été fait juste avant, ce qui était attendu, et le journal concerné dans `logs\`.

## 11. Premier essai

Une issue minuscule, en mode écriture, sans étiquette `for-windows`, par exemple : créer à la racine du dépôt du projet un fichier d'une ligne et le committer. Une fois terminée, vérifier sur GitHub que l'issue porte les labels `done` et `agent-vibe` : c'est la preuve que c'est bien Vibe qui l'a traitée (constaté chez Alain et dans le compte de test). Constaté : une telle issue prend de 1 à 2 minutes (74 s la fois où elle a réussi dans le compte de test), laisse deux commits dans un dossier de travail `%USERPROFILE%\worktrees\<projet>-issue<N>` (la sauvegarde du watcher, puis celui de l'agent), et ne pousse rien. Pour la déposer : un fichier `.txt` dans `issues_inbox\` (UTF-8 sans marqueur d'ordre des octets, voir `INSTRUCTIONS_MISTRAL_BRIDGE_AGENT.md`). Si l'issue reste sans réponse plus de quelques minutes, ne pas lancer d'essais en parallèle : les processus `vibe` en cours se voient avec `Get-Process vibe*`, et le journal de session de Vibe est dans `%USERPROFILE%\.vibe\logs\session\unified\`. Noter ci-dessous tout ce qui plante.

## 12. Déroulé de la visite

1. Prérequis, clonage, `gh auth login`, dépendances, alias (§2 à §5), à la main sur son PC.
2. Vibe, connexion par compte (§6).
3. Premier projet et `AGENT = vibe` (§8) ; simulation puis installation du démarrage (§9) ; issue de test (§11).
4. Si Alain pilote le PC depuis son portable en SSH : serveur OpenSSH et `configurer_ssh_ccw.ps1`, **clé SSH dédiée** à la visite, retirée de `administrators_authorized_keys` à la fin, et configuration d'origine remise côté portable (sauvegarder `configs/ccw_ssh.conf` avant). Non indispensable pour ce guide : tout se fait localement sur le PC.

## 13. Journal d'installation

### Premier essai : compte de test sur le PC d'Alain (10 novembre 2026)

| Étape | Résultat | Ce qui a posé problème | Correction |
|---|---|---|---|
| Création du compte Windows | OK | `New-LocalUser` introuvable dans une fenêtre 32 bits | `net user … /add` puis `net localgroup Administrators … /add` |
| `winget install` (§2) | OK | Question d'acceptation de la source « msstore » | `--source winget --accept-package-agreements --accept-source-agreements` |
| Clonage (§3) | OK au deuxième essai | Dans `C:\Program Files` : « Permission denied » | Cloner dans `$env:USERPROFILE\Bridge_Agent` |
| Python (§2, §3) | OK | `python` introuvable : le raccourci du Microsoft Store masque le vrai Python | Mettre le dossier de Python en tête du chemin ; désactiver les alias d'exécution |
| `gh auth login` (§4) | OK | Le code à 8 caractères s'affiche dans la console, pas sur la page web | Voir §4 |
| Interface (§5) | OK | Le script `provisionner_new_issue_local.ps1` exige l'administrateur et le pare-feu (`--lan`) | Inutile en local : `pip install -r requirements.txt` puis `python new_issue.py` ; aucun mot de passe sans `--lan` |
| Vibe (§6) | OK au bout de plusieurs essais | `vibe --setup` : « Interactive mode needs a terminal » ; première issue bloquée plus de huit minutes avec la 3.1.1 | Version figée à 3.1.0 : issue suivante traitée en 74 s (cause du blocage non isolée) |
| Refus de commandes (§6) | Constaté dans le journal de session de Vibe | `bash` avec `$(…)` et `>` refusé en mode non interactif | Consigne dédiée prévue |
| Projet (§8) | OK | Deux encadrés « Action requise » faux ; onglet CCW et case « Projet CCW » inutiles | À ignorer ; correction prévue |
| Démarrage de session (§9) | OK, y compris après déconnexion et reconnexion | Journaux de session vides tant que les programmes tournent ; faux « échec » de 8 s pour la mise à jour | Voir les pièges du §9 ; corrections prévues |
| Notification (§10) | OK | — | — |

### Visite chez l'ami (à compléter)

| Étape | Résultat | Ce qui a posé problème | Correction |
|---|---|---|---|
| | | | |
