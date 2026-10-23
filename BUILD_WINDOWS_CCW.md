# BUILD_WINDOWS_CCW — guide pour rédiger une issue de build Windows

Guide destiné aux **Claude Chat** (CC) des projets qui rédigent eux-mêmes
une issue de build Windows (`for-windows`). Il décrit le fonctionnement
actuel (worktree dédié, numéro de build, ordre de publication) et fournit
un modèle d'issue prêt à l'emploi. Le pattern général d'une issue
`for-windows` (champs d'en-tête, routage vers le service CCW) reste
documenté au §16 de `BRIDGE_AGENT_DOC.md` ; ce fichier se concentre sur les
builds et sur ce qui est spécifique à chaque projet.

Convention d'ajout : une nouvelle fiche par projet buildé, à la suite,
la plus récente en premier. Ne pas renuméroter les entrées existantes.

---

## Quand utiliser ce guide

Avant de rédiger une issue de build Windows (`for-windows`, mode écriture)
pour un projet qui produit un exécutable/installeur (PyInstaller, Inno
Setup ou équivalent). Lire ce fichier en entier avant de rédiger l'issue —
il contient le modèle à utiliser en bas de page.

---

## Avant de déposer l'issue

- **Le service doit déjà tourner.** Chaque projet a son propre service
  Windows dédié (nom du type `CCW-Watcher-<Projet>`). Démarrer ce service
  depuis l'onglet CCW de l'interface web **avant** de déposer l'issue :
  créer l'issue ne le rallume pas.
- **Calculer le numéro de build.** Regarder sur GitHub où en est le
  projet : prendre le plus haut entre le `build` de `version.json` sur la
  branche `master` et la plus haute étiquette `v<N>` du dépôt, puis
  ajouter 1. Cela garantit que l'étiquette de Release sera libre et que le
  numéro dépasse tout ce qui est déjà installé. Exemple (Rummikub) :
  `version.json` indique 4, les étiquettes montent à `v12` → numéro 13.
- **Vérifier les prérequis du script de build** propres au projet (voir la
  fiche du projet plus bas) — notamment l'emplacement d'Inno Setup pour un
  projet avec installeur.

---

## Comment se passe un build

- L'agent CCW travaille dans un **worktree dédié** (par exemple
  `C:\CCW\worktrees\<projet>-ccw-issue<N>`), sur une branche
  `worktree-issue-<numéro>`. Le script de build, suivi par git, s'y trouve
  et construit à partir des seuls fichiers suivis par git.
- Le script se lance avec **l'outil PowerShell**, depuis la racine du
  worktree — jamais avec Git Bash : un appel `cmd /c` du script y échoue
  silencieusement.
- Le script copie les sources vers un dossier de build local
  (`C:\Temp\<Projet>Build`), construit entièrement là (environnement
  Python, PyInstaller, Inno Setup), puis recopie les résultats dans
  `installeur\output` du worktree. Ce contournement existe parce qu'un
  build lancé directement dans un dossier partagé a produit des fichiers
  tronqués.
- En mode publication (`--publier`), le script calcule le numéro de build,
  écrit `version.json` (numéro et somme SHA-256 de l'archive produite) et
  fait un commit local. **Il ne pousse jamais et ne crée jamais de Release**
  — il le rappelle lui-même à la fin de son exécution.
- Les fichiers produits restent dans le worktree, sous `installeur\output` :
  l'archive `<projet>-v<N>.zip` et l'installeur `<Projet>-Setup-v<N>.exe`.
  Alain doit les récupérer avant de supprimer le worktree.
- Commits attendus dans le worktree à l'issue d'un build réussi : une
  sauvegarde vide, le commit de `version.json` fait par le script, et
  l'entrée de changelog `CHANGELOG-<numéro>.md` ajoutée par l'agent.

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

- Il ne lance **jamais** `git push`.
- Il ne crée **jamais** de Release GitHub (aucune commande `gh release`).
- Il ne recompresse ni ne modifie l'archive produite par le script de
  build : sa somme SHA-256 ne correspondrait plus à celle de
  `version.json`.

---

## Ce que fait Alain ensuite

1. Récupère les fichiers produits (`installeur\output` du worktree) avant
   de supprimer le worktree.
2. Fusionne la branche du worktree dans `master` (en passant par
   Relecture_Bridge), puis pousse.
3. **Ordre de publication recommandé** (point à prendre comme une
   recommandation, pas comme un fait établi) : le script lui-même rappelle
   « git push, puis Release ». Or pousser `version.json` sur `master`
   déclenche la recherche de l'archive par les clients (voir
   « Actualise » ci-dessous). Créer la Release GitHub **d'abord**, puis
   pousser, évite un intervalle où l'archive n'existe pas encore. Comment
   Actualise réagit concrètement à une archive introuvable n'a pas été
   vérifié.
4. Vérifie qu'Actualise propose bien la mise à jour sur un PC de test.
5. Supprime le worktree une fois les fichiers récupérés et la Release
   publiée.

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

- **Script de build** : `build\rebuild_rummikub.bat --publier`, option
  `--build <N>` pour imposer le numéro de build (à confirmer en lisant
  l'en-tête du script avant de s'y fier).
- **Inno Setup** : le script doit chercher Inno Setup d'abord dans
  `C:\CCW\tools\InnoSetup6` (installé hors des dépôts), puis dans le
  dossier `.tools\InnoSetup6` du dépôt — ce second chemin n'existe pas
  dans un worktree, le dossier `.tools/` étant ignoré par git. **À
  vérifier avant le premier build** : le script de Rummikub ne cherchait
  jusqu'ici que dans `.tools\InnoSetup6` ; une correction est en cours
  côté projet Rummikub pour ajouter la recherche dans
  `C:\CCW\tools\InnoSetup6` en priorité.
- **Deux garde-fous de taille distincts** (issue #57 — dist non compressé
  et installeur compressé sont deux grandeurs différentes) :
  - dossier non compressé : fourchette 20-45 Mo
  - installeur compressé : fourchette 5-25 Mo
- **Durée observée** : 333 secondes.

### Scrabble

- **Script de build** : `build\rebuild_scrabble.bat --publier <N>`.
- **Build de référence** : build 13, issue réussie, 283 secondes de durée
  réelle — worktree `C:\CCW\worktrees\scrabble-ccw-issue470`.
- **`.spec`** : `scrabble.spec`, liste explicite des `datas` (pas de
  `collect_tree` en bloc, suite à l'incident du dump wiktionnaire embarqué
  en bloc).

### Actualise

- Pas d'étape Inno Setup — Actualise se distribue en `dist\Actualise\` nu
  via Release GitHub, pas d'installeur.
- **`.spec`** : `actualise.spec` — `--onedir --noconsole` (invisible
  pendant que l'application cible tourne, logging fichier compense) ;
  `datas=[]` explicite (`config.json` est externe, jamais embarqué).
- **Mode `--publier`** : après un build réussi, construit `actualise.zip`
  (manifeste `{"build": N, "supprimer": []}`), calcule le SHA-256, écrit
  `version.json`, fait un commit local — jamais de `git push` ni de
  Release GitHub.

---

## Modèle d'issue de build

Paramètres à remplacer : `<Projet>`, `<numéro-de-build>`, `<nom-du-script>`.

```
#Titre: Build Windows <Projet> — version v<numéro-de-build>

| Champ    | Valeur |
|----------|--------|
| PROJET   | <Projet> |
| LABELS   | for-windows |
| MODE     | écriture |

## Contexte
Build de publication de <Projet>, numéro de build <numéro-de-build>
(calculé à partir de `version.json` sur master et de la plus haute
étiquette `v<N>` existante, +1).

## Vérifications préalables
- Branche et dossier de travail propres avant toute action.
- Commit de sauvegarde avant toute modification.
- [si installeur] Inno Setup disponible à l'emplacement attendu par le
  script.

## Construire
Lancer <nom-du-script> --publier <numéro-de-build> avec l'outil
PowerShell, depuis la racine du worktree (jamais Git Bash).

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
Ne jamais lancer `git push`, ne jamais créer de Release GitHub (aucune
commande `gh release`), ne jamais recompresser ni modifier l'archive
produite.

## Conduite en cas d'échec
Rapporter l'erreur rencontrée (sortie du script, étape atteinte) sans
tenter de contournement ; ne rien pousser.

## Contraintes
Fichiers modifiés limités à `version.json` et à l'entrée de changelog
`CHANGELOG-<numéro-de-build>.md`.

## Rapport attendu
Résultat des vérifications ci-dessus, chemin des fichiers produits dans
`installeur\output`, et rappel qu'Alain doit les récupérer avant la
suppression du worktree.
```
