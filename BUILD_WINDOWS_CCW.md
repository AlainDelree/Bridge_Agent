# BUILD_WINDOWS_CCW — guide pour rédiger une issue de build Windows

Guide destiné aux **Claude Chat** (CC) des projets qui rédigent eux-mêmes
une issue de build Windows (`for-windows`). Il décrit le fonctionnement
actuel (worktree dédié, numéro de build, ordre de publication) et fournit
un modèle d'issue prêt à l'emploi. Le pattern général d'une issue
`for-windows` (champs d'en-tête, routage vers le service CCW) reste
documenté au §16 de `BRIDGE_AGENT_DOC.md` ; ce fichier se concentre sur les
builds et sur ce qui est spécifique à chaque projet.

Convention d'ajout : une nouvelle fiche par projet buildé, ajoutée en tête
de liste (la plus récente en premier). Ne pas renuméroter les entrées
existantes.

---

## Quand utiliser ce guide

Avant de rédiger une issue de build Windows (`for-windows`, mode écriture)
pour un projet qui produit un exécutable/installeur (PyInstaller, Inno
Setup ou équivalent). Lire ce fichier en entier avant de rédiger l'issue —
il contient le modèle à utiliser en bas de page.

---

## Avant de déposer l'issue

- **Le service se démarre normalement tout seul.** Chaque projet a son
  propre service Windows dédié (nom du type `CCW-Watcher-<Projet>`),
  éteint par défaut : depuis les issues #709/#711, créer une issue
  `for-windows` par le formulaire web ou par un fichier déposé dans
  `issues_inbox/` le démarre automatiquement en arrière-plan. Un échec
  (SSH par exemple) ne fait pas échouer la création de l'issue et
  n'affiche aucun message — si l'issue ne démarre pas, regarder l'onglet
  CCW. Deux cas ne bénéficient pas de ce démarrage automatique et exigent
  de démarrer le service à la main (`nssm start <service>` ou bouton
  **Démarrer** de l'onglet CCW) avant de déposer l'issue : une issue créée
  par `gh issue create` direct, et `new_issue.py` lancé nativement sous
  Windows.
- **Calculer le numéro de build.** Regarder sur GitHub où en est le
  projet : prendre le plus haut entre le `build` de `version.json` sur la
  branche `master` et la plus haute étiquette `v<N>` du dépôt, puis
  ajouter 1. Cela vise à garantir que l'étiquette de Release sera libre et
  que le numéro dépasse tout ce qui est déjà installé. Exemple (Rummikub) :
  `version.json` indique 4, les étiquettes montent à `v12` → numéro 13.
  Commandes utilisables par un Chat pour obtenir ces deux informations :
  ```
  curl -sL https://raw.githubusercontent.com/AlainDelree/<Projet>/master/version.json
  git ls-remote --tags https://github.com/AlainDelree/<Projet>
  ```
  **Ne pas utiliser l'API GitHub non authentifiée** (`api.github.com`) pour
  cette vérification : elle refuse rapidement les requêtes au-delà d'un
  faible quota (limite de débit sans jeton). Pour un dépôt privé, ces deux
  commandes échouent également sans authentification : c'est alors Alain
  qui doit faire ces vérifications lui-même avant de transmettre le numéro.
- **Vérifier les prérequis du script de build** propres au projet (voir la
  fiche du projet plus bas) — notamment l'emplacement d'Inno Setup pour un
  projet avec installeur.

---

## Comment se passe un build

- L'agent CCW travaille dans un **worktree dédié** (par exemple
  `C:\CCW\worktrees\<projet>-ccw-issue<N>`), sur une branche
  `worktree-issue-<numéro>`. Le script de build, suivi par git, s'y trouve
  et construit à partir des seuls fichiers suivis par git.
- Le watcher rafraîchit le clone de travail du projet par un
  `git pull --ff-only` au début de chaque cycle (issue #185), avant de
  créer le worktree — c'est pourquoi l'agent n'a jamais à le faire
  lui-même. Ce `pull` est « au mieux » : il ne bloque jamais, et il est
  ignoré, avec un message dans le journal du watcher, si le clone a des
  commits locaux non poussés ou en l'absence de réseau. C'est la raison
  d'être de la vérification « le commit à construire est un ancêtre de
  `HEAD` », et pourquoi il faut pousser juste après une fusion.
- Le script se lance avec **l'outil PowerShell**, depuis la racine du
  worktree — jamais avec Git Bash : un appel `cmd /c` du script y échoue
  silencieusement.
- Le script copie les sources vers un dossier de build local
  (`C:\Temp\<Projet>Build`), construit entièrement là (environnement
  Python, PyInstaller, Inno Setup), puis recopie les résultats dans
  `installeur\output` du worktree. Ce contournement existe parce qu'un
  build lancé directement dans un dossier partagé a produit des fichiers
  tronqués. Ce dossier de build local et l'installation d'Inno Setup sont
  utilisés par le **script**, pas par l'agent : l'agent n'a aucune raison
  de lire ni d'écrire ailleurs que dans le worktree.
- En mode publication (`--publier`), le script calcule le numéro de build,
  écrit `version.json` (numéro et somme SHA-256 de l'archive produite) et
  fait un commit local. **Il ne pousse jamais et ne crée jamais de Release**
  — il le rappelle lui-même à la fin de son exécution.
- Les fichiers produits restent dans le worktree, sous `installeur\output` :
  l'archive `<projet>-v<N>.zip` et l'installeur `<Projet>-Setup-v<N>.exe`.
  Pour les projets dont la fiche indique que le script les copie aussi dans
  le dossier fixe `C:\CCW_Share\_derniers_builds\<projet>\` (Actualise,
  Scrabble et Rummikub à ce jour), il suffit de vérifier leur présence dans
  ce dossier avant de supprimer le worktree ; pour un futur projet dont la
  fiche indiquerait l'absence de cette copie, Alain devrait récupérer les
  fichiers dans `installeur\output` du worktree avant de le supprimer.
- Commits attendus dans le worktree à l'issue d'un build réussi : une
  sauvegarde vide, le commit de `version.json` fait par le script, et
  l'entrée de changelog `CHANGELOG-<numéro-de-l'issue>.md` ajoutée par
  l'agent (le numéro est celui de l'issue du **projet buildé**, dans son
  propre dépôt GitHub — pas une issue de Bridge_Agent, ni le numéro du
  build — même règle que pour le nom du worktree ci-dessus ; exemple réel :
  build 13 de Scrabble, fichier `CHANGELOG-470.md`, issue 470 du dépôt
  Scrabble).

---

## Ce que l'agent vérifie et rapporte

- Branche et dossier de travail propres, et qu'une sauvegarde a été faite
  avant toute action.
- `version.json` présent, avec la somme SHA-256 de l'archive recalculée et
  identique à celle qu'il contient.
- `manifest.json` présent à la racine de l'archive, avec les trois
  premiers octets lus pour confirmer l'absence de BOM UTF-8
  (`7B 22 62`, soit `{"b`).
- Tailles exactes des fichiers produits, comparées aux valeurs de référence
  de la fiche du projet.
- Dossiers de premier niveau de l'archive, avec leur nombre de fichiers.
- Les avertissements éventuels du build (PyInstaller, Inno Setup).

---

## Ce que l'agent ne fait jamais

- Il ne lance **jamais** `git pull` (le worktree est fixé sur sa branche ;
  un `pull` n'y a aucune raison d'être et peut interagir avec l'état laissé
  par un build précédent).
- Il ne lance **jamais** `git push`.
- Il ne crée **jamais** de Release GitHub (aucune commande `gh release`).
- Il ne recompresse ni ne modifie l'archive produite par le script de
  build : sa somme SHA-256 ne correspondrait plus à celle de
  `version.json`.
- Il ne lit ni n'écrit **jamais** hors du worktree : le dossier de build
  local et Inno Setup sont utilisés par le script, pas par l'agent.
- Pour inspecter une archive, il la liste sans l'extraire, ou l'extrait
  seulement dans un sous-dossier temporaire du worktree, non suivi par git
  et supprimé ensuite — jamais dans un dossier système ou temporaire situé
  hors du worktree (ni `C:\WINDOWS\TEMP`, ni `/tmp`).
- Il n'écrit **jamais** de jeton ni de secret dans son rapport : celui-ci
  est publié en commentaire public sur l'issue GitHub.
- La branche courante est celle de cette issue ; si `git status --short` ne
  montre rien, un commit de sauvegarde vide est fait avant toute action.
  S'il montre des modifications, il s'agit probablement d'une reprise
  d'une tentative précédente de cette même issue : vérifier ce travail
  avant de le conserver, ne pas le refaire, et l'indiquer en tête du
  rapport. Il **s'arrête seulement** si la branche courante n'est pas
  celle de l'issue ou si le commit de départ n'est pas un ancêtre de
  `HEAD`.
- Pour une issue de build, **le numéro de build est toujours imposé
  explicitement** (jamais laissé au script) : une reprise qui laisserait
  le script choisir le numéro après qu'une tentative précédente a déjà
  écrit `version.json` sauterait un numéro. Si le script refuse ce numéro
  parce qu'il n'est pas strictement supérieur à celui de `version.json`,
  c'est que le build a déjà été écrit par une tentative précédente :
  vérifier ce travail existant plutôt que de le refaire. Les fichiers
  produits par une tentative interrompue ne sont jamais réutilisés tels
  quels — le script est toujours relancé entièrement.

---

## Ce que fait Alain ensuite

1. Selon la fiche du projet (ci-dessous) : si le script copie aussi les
   fichiers produits dans le dossier fixe
   `C:\CCW_Share\_derniers_builds\<projet>\` (Actualise, Scrabble et
   Rummikub à ce jour), vérifie leur présence dans ce dossier ; sinon
   (pour un futur projet dont la fiche indiquerait l'absence de cette
   copie), récupère les fichiers produits dans `installeur\output` du
   worktree. Dans les deux cas, avant de supprimer le worktree.
2. Fusionne la branche du worktree dans `master`, en passant par l'outil de
   relecture (`relecture_web`) et en y choisissant l'entrée `<projet>_ccw`
   — pas l'entrée du projet lui-même : c'est elle qui montre le clone
   Windows et ses worktrees, et qui permet de fusionner la branche du
   build (depuis les issues #804/#805). Si le tableau a été modifié
   récemment (ex. création d'un nouveau projet CCW), compter environ cinq
   minutes après le push avant que l'entrée `_ccw` apparaisse dans l'outil
   (cache de `raw.githubusercontent.com`). **Sans pousser** à ce stade.
3. Crée la Release GitHub (étiquette `v<N>`), avec **DEUX fichiers** :
   l'installeur `<Projet>-Setup-v<N>.exe` et l'archive `<projet>-v<N>.zip`.
   **Ordre de publication recommandé** (point à prendre comme une
   recommandation, pas comme un fait établi) : créer la Release **avant**
   de pousser — le script lui-même rappelle plutôt « git push, puis
   Release », mais pousser `version.json` sur `master` déclenche la
   recherche de l'archive par les clients (voir « Actualise » ci-dessous),
   et créer la Release d'abord évite un intervalle où l'archive n'existe
   pas encore. Comment Actualise réagit concrètement à une archive
   introuvable n'a pas été vérifié.
4. Pousse `master`.
5. Vérifie qu'Actualise propose bien la mise à jour sur un PC de test.
6. Supprime le worktree une fois les fichiers vérifiés ou récupérés (selon
   le cas de l'étape 1) et la Release publiée.

---

## En cas d'échec

Le script ne pousse rien et ne crée aucune Release en cas d'échec comme en
cas de succès : un échec en cours de build laisse le worktree et la branche
en l'état, sans conséquence sur `master`. L'agent rapporte l'erreur
rencontrée (sortie du script, étape atteinte) ; Alain décide de relancer
l'issue ou d'investiguer le script en premier.

---

## Le numéro de build et Actualise

L'application Actualise met à jour les jeux sur le PC : elle lit
`version.json` du dépôt de chaque application, sur la branche `master`
(via `raw.githubusercontent.com`), et compare des entiers — mise à jour si
`distant.build > local.build`. La Release suit ce même numéro : étiquette
`v<N>`, archive `<projet>-v<N>.zip`, et le champ `sha256` de `version.json`
est la somme de cette archive. L'URL de téléchargement est
`releases/download/v<N>/<projet>-v<N>.zip`. Chaque projet a sa propre
liste de numéros, indépendante des autres.

---

## Fiche par projet

### Rummikub

- **Script de build** (ligne de commande exacte) :
  `build\rebuild_rummikub.bat --publier [--build N]` — ligne de commande
  inchangée par le durcissement du script (issue #178 de Rummikub). Sans
  `--build`, le numéro est le build de `version.json` plus 1, désormais
  dans tous les modes (auparavant `--build` ne s'appliquait qu'avec
  `--publier`).
- **Dix étapes** numérotées de 0 à 9, plus trois sous-étapes non comptées
  dans la numérotation (`0bis` — garde-fou, `3bis`, `8bis`), depuis le
  durcissement (issue #178 de Rummikub) ; le script n'en annonçait que
  neuf (0 à 8) avant cette issue.
- **Inno Setup** : trouvé d'abord dans `C:\CCW\tools\InnoSetup6\ISCC.exe`
  (issue #176), confirmé par l'essai du 25 octobre 2026.
- **`.spec`** : `rummikub.spec` — liste explicite des `datas`
  (`src/rummikub/ui/web/`), aucun `collect_tree` en bloc.
- **Deux garde-fous de taille distincts** (issue #57 — dist non compressé
  et installeur compressé sont deux grandeurs différentes) :
  - dossier non compressé : fourchette 20-45 Mo
  - installeur compressé : fourchette 5-25 Mo
- **Artefacts et dossier fixe** : `Rummikub-Setup-v<N>.exe` et
  `rummikub-v<N>.zip` produits dans `installeur\output` du worktree ; le
  nom de l'archive porte toujours le numéro, y compris sans `--publier`
  (l'ancien nom fixe `rummikub.zip` n'existe plus). Copiés en plus dans
  `C:\CCW_Share\_derniers_builds\rummikub\` **dans tous les modes**, à
  l'étape `[8/9]`. Le script affiche lui-même, à la fin, l'emplacement
  d'Inno Setup utilisé et les noms et tailles en octets des fichiers
  copiés : l'agent ne lit pas ce dossier, il reprend cet affichage dans
  son rapport.
- **Garde-fou** (sous-étape `0bis`, issue #178 de Rummikub) : exécuté juste
  après la recherche d'Inno Setup et avant la copie vers le dossier de
  build local, il refuse, avec le code de sortie 1 et avant toute copie,
  construction ou écriture, un numéro qui n'est pas un entier strictement
  supérieur au build de `version.json` ; il refuse aussi `--build` sans
  valeur ou suivi d'un autre argument, et tout argument inconnu, en
  listant les arguments acceptés.
- **Nettoyage obsolète supprimé** (issue #178 de Rummikub) : la commande
  `git -C C:\CCW_Share\CCW\rummikub reset --hard origin/master` de l'étape
  de nettoyage (sans `--publier`) et les commentaires sur un « clone
  partagé » ont été retirés — le script construit dans un dossier local et
  écrit dans le worktree. Non établi : si une infrastructure extérieure à
  Rummikub référence encore ce chemin `C:\CCW_Share\CCW\rummikub`.
- **Vérification du code de sortie d'un `.bat`** : se fait avec `call` et
  `%errorlevel%` dans un petit fichier temporaire — `$LASTEXITCODE` de
  PowerShell est peu fiable pour ce genre de script.
- **`build/` est ignoré par git** : le script lui-même reste suivi grâce à
  un ajout forcé ; `git ls-files build` doit continuer à le lister.
- **Release à deux fichiers** : comme pour Scrabble et Actualise, le
  rappel final du script avec `--publier` mentionne DEUX fichiers à
  attacher à la Release — l'installeur ET l'archive.
- **Build de référence du script durci** (build 14, issue #179 du dépôt
  Rummikub, 25 octobre 2026) : commande
  `build\rebuild_rummikub.bat --publier --build 14`, code de sortie 0. Le
  mode `--publier` est validé : le script a écrit `version.json` (numéro et
  somme SHA-256 de l'archive) et fait lui-même le commit local ; la somme
  recalculée à part par l'agent est identique. Manifeste
  `{"build": 14, "supprimer": []}`, trois premiers octets `7B 22 62`, sans
  BOM. Installeur 12 801 538 octets ; archive 12 895 604 octets ;
  `dist\Rummikub` non compressé 26 251 767 octets (identique au build 13) ;
  dossier `_internal` de 73 fichiers (89 entrées en tout dans l'archive).
  Durée réelle de l'issue : 229 secondes. Seuls avertissements : les deux
  avertissements habituels de PyInstaller sur `pycparser.lextab` et
  `pycparser.yacctab`. Copie vers `C:\CCW_Share\_derniers_builds\rummikub\`
  confirmée par l'affichage du script (noms et tailles identiques). La
  Release `v14` porte l'installeur et l'archive (sommes vérifiées),
  `version.json` de `master` annonce le build 14, et la mise à jour par
  Actualise de la v13 à la v14 a été vérifiée par Alain sur un PC.
- **Essai antérieur avec le numéro fictif 99, sans `--publier`** (25 octobre
  2026) : mêmes tailles à peu de chose près (installeur 12 796 415 octets,
  archive 12 896 340 octets, durée 99,69 secondes) et six refus vérifiés,
  tous avec le code de sortie 1 et sans rien écrire (numéro égal au build
  courant, numéro inférieur, numéro non numérique, `--build` seul,
  `--publier --build` avec un numéro non supérieur, argument inconnu).
- **Build de référence de l'ancien script (avant le durcissement)** : build
  13, issue #177 du
  dépôt Rummikub, réussi — worktree
  `C:\CCW\worktrees\rummikub-ccw-issue177`. Neuf étapes (numérotées 0 à 8)
  sans erreur ; seuls avertissements : deux avertissements habituels de
  PyInstaller sur `pycparser.lextab` et `pycparser.yacctab`, sans effet.
  Tailles de référence : dossier non compressé `dist\Rummikub` 26 251 767
  octets, installeur `Rummikub-Setup-v13.exe` 12 800 339 octets, archive
  `rummikub-v13.zip` 12 896 659 octets (2 fichiers à la racine —
  `Rummikub.exe` et `manifest.json` — et un dossier `_internal` de 87
  entrées). Durée réelle de l'agent : 219 secondes (`TIMEOUT` de 1800s).
  Durée observée : 333 secondes (build antérieur).

### Scrabble

- **Script de build** (ligne de commande exacte) :
  `build\rebuild_scrabble.bat --publier [--build N]` — l'ancienne forme
  `--publier <N>` (numéro accolé) n'est plus acceptée. Sans `--build`, le
  numéro est le build de `version.json` plus 1, dans tous les modes, y
  compris sans `--publier`.
- **Dix étapes** numérotées de 0 à 9, depuis la nouvelle syntaxe du script
  (issue #472 de Scrabble, fusionnée dans master et publiée) — l'ancienne
  syntaxe n'en annonçait que neuf, de 0 à 8.
- **Garde-fou** (issue #472 de Scrabble) : le script refuse, avant toute
  écriture, un numéro qui n'est pas un entier strictement supérieur au
  build de `version.json`, avec un message clair et un code de sortie non
  nul ; un argument inconnu, l'ancienne forme `--publier <N>` et `--build`
  sans valeur sont aussi refusés.
- **Artefacts et dossier fixe** : `Scrabble-Setup-v<N>.exe` et
  `scrabble-v<N>.zip` produits dans `installeur\output` du worktree, et
  copiés en plus dans `C:\CCW_Share\_derniers_builds\scrabble\` **dans
  tous les modes**, même sans `--publier`. Le script affiche lui-même les
  noms et les tailles en octets de ces deux fichiers copiés : l'agent ne
  lit pas ce dossier, il reprend ces valeurs dans son rapport.
- **`.spec`** : `scrabble.spec`, liste explicite des `datas` (pas de
  `collect_tree` en bloc, suite à l'incident du dump wiktionnaire embarqué
  en bloc).
- **Vérification propre à ce projet** : s'assurer qu'aucun fichier de
  dictionnaire n'est présent dans l'archive produite.
- **Build de référence de la nouvelle syntaxe** (build 14, issue #474 du
  dépôt Scrabble, 25 octobre 2026) : commande
  `build\rebuild_scrabble.bat --publier --build 14`, code de sortie 0 ;
  `version.json` écrit et commité par le script, somme recalculée
  identique. Installeur 12 901 348 octets ; archive 13 356 766 octets ; 77
  fichiers dans l'archive, comme au build 13 ; aucun fichier de
  dictionnaire dans l'archive. Par rapport au build 13 : archive
  +81 544 octets (+0,6 %), installeur +57 447 octets (+0,4 %), écart
  attribué à des paquets Python mis à jour lors de la recréation de
  l'environnement de build. Durée réelle de l'issue : 220 secondes. Mêmes
  deux avertissements PyInstaller. Les deux fichiers copiés dans
  `C:\CCW_Share\_derniers_builds\scrabble\` portent les mêmes tailles. La
  Release `v14` porte l'installeur et l'archive (sommes vérifiées), et la
  mise à jour par Actualise de la v13 à la v14 a été vérifiée par Alain.
- **Écart connu du manifeste, sans conséquence fonctionnelle** : le
  manifeste de l'archive contient `{"build": 1, "supprimer": []}`, avec un
  numéro de build fixe égal à 1, dans la v13 comme dans la v14, parce que
  le script de Scrabble l'écrit en dur. Le client Actualise ne lit que le
  champ `supprimer`. Cet écart n'est pas corrigé.
- **Build de référence de l'ancienne syntaxe** : build 13, issue réussie,
  283 secondes de durée réelle — worktree
  `C:\CCW\worktrees\scrabble-ccw-issue470`. Taille de référence du build 13
  (les dictionnaires ne sont pas embarqués dans l'archive) : archive
  13 275 222 octets, installeur 12 843 901 octets, 77 fichiers dans
  l'archive.
- **Release à deux fichiers** : comme pour Rummikub et Actualise, la
  Release porte l'installeur ET l'archive, créée par Alain avant de
  pousser `master`.
- **Essais avec un numéro fictif** : comme pour Actualise, la copie vers le
  dossier fixe (`C:\CCW_Share\_derniers_builds\scrabble\`) a lieu dans tous
  les modes, y compris un essai sans `--publier` : Alain supprime à la main
  les fichiers de l'essai après coup.

### Actualise

- **Script de build** (ligne de commande exacte) :
  `build\rebuild_actualise.bat --publier [--build N]` — sans `--build`, le
  numéro est le build de `version.json` plus 1.
- **Dix étapes** numérotées de 0 à 9 (Rummikub et Scrabble en annoncent
  dix, de 0 à 9, comme Actualise), parce qu'Actualise produit deux builds
  PyInstaller distincts (`Actualise.exe` en dossier, `ActualiseUI.exe` en
  fichier unique) et a une étape d'archive séparée.
- **Inno Setup** : trouvé dans `C:\CCW\tools\InnoSetup6\ISCC.exe`.
- **Artefacts et dossier fixe** : `Actualise-Setup-v<N>.exe` et
  `actualise-v<N>.zip` produits dans `installeur\output` du worktree, et
  copiés en plus dans `C:\CCW_Share\_derniers_builds\actualise\` **dans
  tous les modes**, même sans `--publier`.
- **Garde-fou** (issue #71 d'Actualise) : le script refuse, avant toute
  copie, construction ou écriture et dans tous les modes, un numéro qui
  n'est pas un entier strictement supérieur au build de `version.json`,
  ainsi que `--build` sans valeur et tout argument inconnu, avec un
  message et le code de sortie 1.
- **Archive** : 31 entrées — à la racine `Actualise.exe`, `ActualiseUI.exe`,
  `manifest.json` (`{"build": N, "supprimer": []}`, sans BOM UTF-8) et le
  dossier `_internal` (28 entrées).
- **Tailles de référence (build 11, publié)** : installeur 20 641 285
  octets ; archive 20 575 302 octets ; `Actualise.exe` 4 159 103 octets ;
  `dist\Actualise` non compressé 21 635 190 octets ; `ActualiseUI.exe`
  entre 10 314 263 et 10 315 521 octets selon la reconstruction.
- **Durée observée** : environ 2 minutes pour le script ; les issues #70
  et #71 d'Actualise ont pris respectivement 668 et 675 secondes en tout.
- **Release à deux fichiers** : comme pour Rummikub et Scrabble, la
  Release porte l'installeur ET l'archive, créée par Alain avant de
  pousser `master`.
- **Essais toujours en `--build 99`**, jamais avec le numéro automatique ni
  avec un numéro proche d'un build réel : la copie vers le dossier fixe
  (`C:\CCW_Share\_derniers_builds\actualise\`) a lieu dans tous les modes.
  Alain supprime à la main les fichiers de l'essai après coup.
- **Particularité : Actualise se met à jour lui-même.** Ne jamais publier
  un build d'essai ; tester la mise à jour automatique sur un PC avant de
  généraliser, car une archive défectueuse pourrait empêcher les mises à
  jour suivantes. Le nouvel `updater.bat` (issue #68 d'Actualise) ne
  s'exécutera chez un client qu'à la mise à jour de la v12 à la v13.
- **Remarque PowerShell** : avec `2>&1`, une ligne d'information de
  PyInstaller apparaît comme `NativeCommandError` — ce n'est pas une
  erreur (code de sortie 0 malgré cette apparence).

---

## Modèle d'issue de build

Paramètres à remplacer : `<Projet>`, `<numéro-de-build>`,
`<commit-a-construire>` (commit à builder, pour la vérification qu'il est
bien un ancêtre de `HEAD`), `<numéro-de-l'issue>` (numéro attribué par
GitHub dans le dépôt du projet buildé, connu seulement une fois l'issue
créée, à reporter dans le nom du fichier de changelog),
`<ligne-de-commande-exacte-du-script>` (donnée par la fiche du projet
ci-dessus). La fiche de chaque projet (ci-dessus) peut lister des
vérifications qui lui sont propres (voir par exemple Scrabble) : les
recopier dans la section « Vérifications préalables » de l'issue.

```
#Titre: Build Windows <Projet> — version v<numéro-de-build>

| PROJET    | <Projet> |
| REDACTEUR | <Projet> |
| LABELS    | for-windows |
| MODE      | écriture |
| TIMEOUT   | 1800s |

## Contexte
Build de publication de <Projet>, numéro de build <numéro-de-build>
(calculé à partir de `version.json` sur master et de la plus haute
étiquette `v<N>` existante, +1). Commit à construire : <commit-a-construire>.
Durées observées sur les builds déjà réalisés : entre 90 et 333 secondes
selon le projet — 1800s de TIMEOUT laisse une marge confortable.

## Vérifications préalables
- La branche courante est celle de cette issue ; si `git status --short` ne
  montre rien, un commit de sauvegarde vide est fait avant toute action.
  S'il montre des modifications, il s'agit probablement d'une reprise
  d'une tentative précédente de cette même issue : vérifier ce travail
  avant de le conserver, ne pas le refaire, et l'indiquer en tête du
  rapport.
- Le commit à construire (<commit-a-construire>) est un ancêtre de `HEAD` :
  `git merge-base --is-ancestor <commit-a-construire> HEAD`.
- Le numéro de build (<numéro-de-build>) est toujours imposé explicitement
  à la ligne de commande, jamais laissé au script : en cas de reprise, le
  laisser choisir sauterait un numéro si une tentative précédente a déjà
  écrit `version.json`.
- [si installeur] Inno Setup disponible à l'emplacement attendu par le
  script.
- [vérifications propres au projet, recopiées depuis sa fiche ci-dessus]
- S'arrêter seulement si la branche courante n'est pas celle de l'issue ou
  si le commit de départ n'est pas un ancêtre de `HEAD`. Si le script
  refuse le numéro imposé parce qu'il n'est pas strictement supérieur à
  celui de `version.json`, c'est que le build a déjà été écrit par une
  tentative précédente : vérifier ce travail existant plutôt que de le
  refaire — ne jamais réutiliser tels quels les fichiers produits par une
  tentative interrompue, le script est toujours relancé entièrement.

## Construire
Lancer <ligne-de-commande-exacte-du-script> avec l'outil PowerShell, depuis
la racine du worktree (jamais Git Bash).

## Vérifier le résultat
- `version.json` : numéro de build et SHA-256 de l'archive, recalculé et
  identique.
- `manifest.json` à la racine de l'archive : trois premiers octets
  `7B 22 62` (pas de BOM UTF-8).
- Tailles des fichiers produits comparées aux valeurs de référence du
  projet.
- Dossiers de premier niveau de l'archive avec leur nombre de fichiers.
- Avertissements éventuels du build.

## Ne pas publier
Ne jamais lancer `git push` ni `git pull`, ne jamais créer de Release
GitHub (aucune commande `gh release`), ne jamais recompresser ni modifier
l'archive produite. Ne rien lire ni écrire hors du worktree (le dossier de
build local et Inno Setup sont utilisés par le script, pas par l'agent).
Pour inspecter une archive : la lister sans l'extraire, ou l'extraire
seulement dans un sous-dossier temporaire du worktree, non suivi par git et
supprimé ensuite — jamais dans un dossier système ou temporaire hors du
worktree. N'écrire aucun jeton ni secret dans le rapport : il est publié en
commentaire public sur GitHub.

## Conduite en cas d'échec
Rapporter l'erreur rencontrée (sortie du script, étape atteinte) sans
tenter de contournement ; ne rien pousser.

## Contraintes
Fichiers modifiés limités à `version.json` et à l'entrée de changelog
`CHANGELOG-<numéro-de-l'issue>.md` (numéro de l'issue, pas du build).

## Rapport attendu
Résultat des vérifications ci-dessus, chemin des fichiers produits dans
`installeur\output`. Si la fiche du projet indique que le script les copie
aussi dans le dossier fixe `C:\CCW_Share\_derniers_builds\<Projet>\`,
reprendre les noms et tailles affichés par le script ; sinon, rappeler
qu'Alain doit récupérer les fichiers dans `installeur\output` avant la
suppression du worktree.
```
