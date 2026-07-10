# Bridge Manager — Contexte de projet

Document de démarrage pour une conversation dédiée à la conception et au développement d'un outil de gestion multi-projets du bridge inter-agents actuellement en place pour AlChess.

---

## Résumé exécutif

Le bridge inter-agents actuel (`~/bridge-agent/watcher.py` sur le ThinkPad d'Alain) fonctionne bien pour AlChess : il surveille les GitHub Issues d'un dépôt, les délègue à Claude Code Linux (CCL) en non-interactif, rapporte les résultats en commentaire et ferme les issues quand elles réussissent. Deux besoins ont émergé de son usage réel qu'il faut adresser :

1. **Multi-projets** : Alain a plusieurs projets actifs (au moins AlChess et un site peinture). Le watcher actuel est hardcodé sur AlChess. Il faut pouvoir faire tourner plusieurs watchers en parallèle, un par projet, sans interférence.
2. **Interface de création d'issues** : la création d'issues à la main via `gh issue create` en ligne de commande est source de friction (labels à mémoriser, en-tête markdown à recopier, échappement des caractères spéciaux dans le body, oublis de champs). Une petite UI permettrait de choisir les paramètres visuellement.

Ce document trace ce qui existe aujourd'hui, ce que ces deux évolutions doivent adresser, et les options d'implémentation identifiées.

---

## 1. Ce qui existe aujourd'hui

### 1.1 Le watcher (`~/bridge-agent/watcher.py`)

Un script Python en boucle infinie qui :

1. Toutes les 10 secondes, appelle `gh issue list --repo AlainDelree/AlChess --label for-linux --state open`.
2. Pour chaque issue trouvée, extrait les labels et lit certains champs de l'en-tête markdown du body.
3. Lance `claude --print` avec un prompt construit à partir du titre + body de l'issue, avec ou sans `--dangerously-skip-permissions` selon les labels.
4. Attend le résultat (avec timeout).
5. Poste le résultat comme commentaire sur l'issue, ferme l'issue, ajoute le label `done` en cas de succès.
6. En cas d'échec, retry 3 fois puis pose le label `needs-human` pour bloquer le retraitement automatique (voir §1.4 sur la boucle infinie corrigée).

Le processus `claude --print` lancé par le watcher est démarré avec `cwd=~/NicLink` (défini en dur dans `watcher.py`, `subprocess.run(..., cwd=Path.home() / "NicLink")`). Précisions importantes sur ce que ça signifie :

- **Cwd ≠ sandbox** : le cwd fixe seulement le point de départ pour les chemins relatifs et le contexte mental de CCL. Techniquement, CCL peut lire n'importe où sur le système de fichiers dans la limite des droits Unix de l'utilisateur `alain` qui a lancé le watcher.
- **En mode lecture seule** (sans `--dangerously-skip-permissions`) : CCL demande approbation à chaque écriture. En session non-interactive, cette approbation ne peut pas être fournie → il ne peut rien écrire en pratique.
- **En `mode_write`** (avec `--dangerously-skip-permissions`) : CCL peut écrire n'importe où où `alain` a les droits. Le prompt système et le cwd l'orientent vers `~/NicLink`, mais rien ne l'empêche techniquement de toucher ailleurs. Les garde-fous sont dans le **prompt** (backup pinné, jamais de push, pas de destructif), pas dans une sandbox système.
- **Root interdit** : `--dangerously-skip-permissions` refuse d'être lancé en root, donc le watcher ne doit pas non plus l'être.

**Conséquence pour le multi-projets** : le cwd doit devenir un paramètre de la config par projet (`CWD=/home/alain/NicLink` pour AlChess, `CWD=/home/alain/SitePeinture` pour l'autre projet, etc.). Le refactoring devra sortir cette valeur hardcodée du code vers la config.

### 1.2 Les 8 paramètres actionnables aujourd'hui

**Labels GitHub (6)** — posés au moment de la création de l'issue :

| Label | Effet |
|---|---|
| `for-linux` | **Requis** — filtre de `lister_issues()`. Sans lui, l'issue n'est pas vue. |
| `mode_write` | Arme le mode écriture (`--dangerously-skip-permissions`), sinon lecture seule |
| `needs-human` | Bloque le retraitement automatique (posé par le watcher après 3 échecs) |
| `notif_pc` | Ajoute une bulle desktop `notify-send` aux notifs |
| `notif_gsm` | Ajoute une notification ntfy (téléphone) aux notifs |
| `notif_tous` | Les deux à la fois |

Label auto-ajouté au succès : `done`.

**Champs lus dans l'en-tête du body (2)** — sous forme de tableau markdown `| CHAMP | VALEUR |` :

| Champ | Effet |
|---|---|
| `PRIORITE` | Si `haute` ou `critique` → retry infini au lieu de s'arrêter à 3 tentatives |
| `TIMEOUT` | Surcharge le timeout par défaut (300s) — utile pour les tâches lourdes |

**Champs documentaires non lus par le code** (mais présents dans le template `TACHES-ISSUES.md`, à des fins de traçabilité) : `SOURCE`, `DEST`, `RETOUR`, `PARCOURS`, `CONV_ID`, `ACK_REQUIS`, `RETRY`, `DEPENDS_ON`, `CHECKSUM`.

### 1.3 Notifications

Trois canaux, cumulatifs :

- **Beep** — toujours émis, via `~/NicLink/bip.py` (custom 440 Hz via aplay). Non désactivable par label.
- **notify-send** — bulle desktop locale, opt-in via `notif_pc` ou `notif_tous`. Requiert `libnotify-bin`.
- **ntfy** — push téléphone via `curl` sur `https://ntfy.sh/{topic}`. Opt-in via `notif_gsm` ou `notif_tous`. Topic actuel hardcodé dans `watcher.py` : `hippocampe-ff-galerie-xyz123` (mutualisé avec le projet site peinture).

Les notifications sont envoyées sur trois événements : succès, échec définitif (`needs-human` posé), alerte critique (issue `PRIORITE=haute/critique` en échec avant retry).

### 1.4 Historique des corrections déjà appliquées

Le watcher a été itéré sur cette conversation. Corrections notables :

- **Boucle infinie sur échec définitif** — avant la correction, une issue ayant épuisé ses 3 tentatives restait ouverte avec `for-linux` et était retraitée en boucle par le watcher (ACK → 3 tentatives → timeout → ACK → …). Fix : ajout du label `needs-human` par le watcher lui-même à l'abandon, et court-circuit en tête de `traiter_issue()` pour ignorer les issues portant ce label.
- **Timeout par issue** — le champ `TIMEOUT` du template `TACHES-ISSUES.md` était documenté mais jamais lu. Ajout de `extraire_timeout()` qui parse le tableau markdown et transmet à `lancer_claude()`.
- **Notifications** — le TODO `# TODO: ajouter notification desktop` a été concrétisé avec les 3 labels `notif_pc/gsm/tous` + les fonctions `notify_desktop()` / `notify_ntfy()` / `notifier()` (dispatch).

Le fichier `watcher.py` à jour est en cours d'exécution sur le ThinkPad d'Alain.

### 1.5 Templates de création d'issues (`TACHES-ISSUES.md`)

Un fichier de référence à la racine d'AlChess documente trois modèles de commande `gh issue create` : tâche complète lecture seule, tâche légère lecture seule, tâche écriture. Les commandes contiennent l'en-tête markdown à remplir manuellement, avec échappements shell pour les guillemets et pipes.

En pratique, Alain crée les issues en copiant-collant depuis Claude Chat (moi) qui rédige les commandes complètes à chaque fois. C'est fonctionnel mais laborieux.

---

## 2. Besoin 1 — Watcher multi-projets

### 2.1 Le problème

Le watcher actuel est hardcodé sur AlChess : `REPO`, `LABEL`, `LOG_FILE`, working directory de `claude --print` (`~/NicLink`), `BIP_SCRIPT`, `NTFY_TOPIC`. Impossible d'en lancer une seconde instance sur un autre projet sans dupliquer le fichier et éditer les constantes.

### 2.2 Ce qui est important à préserver

- **Sérialité intra-projet** : dans un même projet, les tâches se traitent une par une. C'est un choix architectural voulu (pas de collision sur les fichiers, git index unique, `claude --print` bloquant). Ne PAS chercher à paralléliser deux CCL sur le même projet.
- **Parallélisme inter-projets** : par contre, un watcher AlChess ET un watcher site peinture doivent pouvoir tourner en même temps. Chacun sur son propre working directory, son propre repo, son propre log.
- **Isolation des notifications** : les événements d'un projet doivent être identifiables (probablement titre de notification préfixé par le nom du projet, éventuellement topic ntfy différent par projet).

### 2.3 Architecture cible envisagée

```
~/bridge-agent/
  watcher.py                → générique, prend --config en argument
  configs/
    alchess.conf            → REPO, LABEL, LOG_FILE, NTFY_TOPIC, CWD, BIP_SCRIPT
    peinture.conf           → idem pour l'autre projet
  logs/
    watcher-alchess.log
    watcher-peinture.log
```

Lancement :

```bash
python3 ~/bridge-agent/watcher.py --config configs/alchess.conf &
python3 ~/bridge-agent/watcher.py --config configs/peinture.conf &
```

Refactoring estimé léger (~30 lignes touchées, logique inchangée). Toutes les constantes en tête de `watcher.py` deviennent des champs d'un dict `config` chargé au démarrage.

### 2.4 Point d'attention

Il faudra décider si le topic ntfy est partagé entre projets (comme aujourd'hui) ou séparé. Partagé = simple mais les notifs de tous les projets arrivent sur le même canal ; séparé = chaque projet son topic, filtrage plus fin côté application ntfy sur le GSM.

---

## 3. Besoin 2 — Interface graphique de création d'issues

### 3.1 Le problème

La création d'une issue via `gh issue create` en ligne de commande demande :

- Se souvenir des labels applicables et de leur nom exact (une faute de frappe fait échouer la commande).
- Rédiger l'en-tête markdown en respectant la syntaxe des tableaux.
- Échapper correctement les guillemets, pipes, backticks dans le body.
- Choisir le bon repo si multi-projets.

En pratique, Alain me demande à moi (Claude Chat) de rédiger la commande, il la copie-colle. C'est verbeux et une simple faute de frappe (par exemple un caractère `µ` accidentel) peut passer inaperçue jusqu'à ce que le watcher ou CCL bute dessus.

### 3.2 Objectif de l'interface

Choisir visuellement :
- Le projet cible (parmi les configs déclarées).
- Les labels de mode (lecture seule / écriture).
- Les labels de notification (`notif_pc`, `notif_gsm`, `notif_tous`).
- La priorité (`normale` / `haute` / `critique`).
- Le timeout.
- Le titre et le corps (avec en-tête pré-rempli automatiquement selon les choix ci-dessus).

Puis générer et exécuter la commande `gh issue create` correspondante.

### 3.3 Trois options d'implémentation identifiées

**Option A — Générateur CLI interactif**
Un `~/bridge-agent/new_issue.py` qui pose les questions dans le terminal (`inquirer` ou juste `input()`), construit la commande, la montre pour validation, l'exécute. Zéro dépendance, réalisation en 30 minutes.

- ✅ Simple, fiable, aligné avec la chaîne de travail actuelle.
- ❌ Reste en terminal, pas de vraie interface.

**Option B — Mini web UI Flask indépendante**
Un serveur Flask local à `~/bridge-agent/web/`, avec un formulaire HTML (cases à cocher, sélecteurs, textarea) qui poste vers un endpoint local exécutant `gh issue create`.

- ✅ Ergonomique, visuel.
- ❌ Serveur Flask de plus à lancer, code et maintenance en plus.

**Option C — Extension du watcher**
Le watcher lui-même expose un endpoint HTTP local (`http://localhost:8765/new-issue`) qui sert un formulaire. Un seul processus à lancer par projet.

- ✅ Un seul point d'entrée.
- ❌ Couple deux responsabilités (surveiller + créer) dans le même processus. Débuggage plus délicat si l'un casse l'autre.

### 3.4 Recommandation

Commencer par **Option A**, l'utiliser une semaine, puis décider si le pas vers B ou C vaut le coup en fonction du ressenti réel. Principe "voir avant d'agir" qu'Alain applique déjà partout ailleurs.

### 3.5 Point d'attention important

Ce projet d'interface est **très bien placé pour être multi-projets dès le départ**. Puisqu'on refactore le watcher pour multi-projets de toute façon, autant que l'outil de création d'issues sache aussi cibler AlChess *ou* site peinture selon un choix au moment de la création — plutôt qu'un outil AlChess-only qu'il faudra refactorer plus tard.

Cela suggère que **l'outil de création lit les mêmes fichiers `configs/*.conf`** que le watcher. C'est une bonne raison pour concevoir le format de config avec soin dès le début.

---

## 4. Ce qu'il faut éviter (leçons de la conversation en cours)

- **Ne PAS chercher à paralléliser deux CCL sur le même projet** — même sur plan Max Anthropic, les risques d'incohérence sur le working directory, le git index, les fichiers de config partagés dépassent le gain de temps réel. Le vrai gain de parallélisme se trouve entre projets distincts, pas dans un même projet.
- **Ne PAS fusionner le générateur d'issues et le watcher au niveau logique** — même si un futur wrapper commun peut les servir tous les deux (config partagée), ils doivent rester deux briques indépendantes, testables séparément. L'un est un serveur de background, l'autre un outil interactif à la demande.
- **Ne PAS traiter les champs documentaires (`SOURCE`, `DEST`, etc.) comme du bruit à supprimer** — ils servent à la traçabilité conversationnelle entre agents (Claude Chat ↔ CCL ↔ CCW). Les préserver dans les templates de l'interface même s'ils ne sont pas actionnables par le code.

---

## 5. Références et fichiers à récupérer avant de démarrer

Sur le ThinkPad d'Alain :

- `~/bridge-agent/watcher.py` — le watcher actuel, à jour avec les corrections listées en §1.4.
- `~/NicLink/TACHES-ISSUES.md` — le fichier de référence des templates d'issues actuels (base pour le futur outil de création).
- `~/NicLink/TACHES.md` — historique des sessions et bugs résolus, contient plusieurs mentions du bridge (notamment session 2026-07-03 où `mode_write` a été introduit).
- `~/NicLink/bip.py` — script beep, utilisé par le watcher.

Sur GitHub :

- `github.com/AlainDelree/AlChess` — dépôt actuellement surveillé par le watcher, contient l'historique des issues du bridge (numéros ~4 à ~18 au moment de la rédaction de ce document).

---

## 6. Suggestion de démarrage pour la nouvelle conversation

Dans le nouveau chat, on peut :

1. Copier ce document tel quel (ou en résumé) pour donner le contexte.
2. Décider du nom du projet (par exemple `bridge-manager` ou `bridge-tools`), du dépôt GitHub associé.
3. Décider de la stack (Python simple, Flask, Textual, autre) selon ce qu'Alain veut explorer.
4. Attaquer par le refactoring `watcher.py` → configurable, parce que c'est le prérequis technique de tout le reste (l'outil de création doit lire les mêmes configs).
5. Puis attaquer l'Option A (générateur CLI) comme premier livrable utilisable.
6. Puis évaluer si Option B ou C vaut le coup.

---

*Document rédigé pendant la conversation AlChess du 2026-07-10, en attendant le résultat de l'issue #18 (finalisation du chantier Rodent IV). À utiliser comme entrée en matière pour une conversation dédiée à Bridge Manager.*
