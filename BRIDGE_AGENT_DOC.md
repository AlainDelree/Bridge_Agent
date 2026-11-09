# Bridge_Agent — Documentation de référence

Document destiné à Claude Chat (CC) pour comprendre et utiliser le bridge
inter-agents d'Alain. À lire en début de conversation impliquant Bridge_Agent.

---

## 1. Vue d'ensemble

Bridge_Agent permet à Claude Chat (toi) de déléguer des tâches via des
GitHub Issues, traitées par l'un de deux agents selon la plateforme requise :

- **CCL (Linux)** — label `for-linux`. S'exécute sur le ThinkPad d'Alain.
  Choix par défaut pour toute tâche sur un projet standard.
- **CCW (Windows)** — label `for-windows`. S'exécute sur un poste Windows.
  Réservé aux tâches qui ont réellement besoin de Windows (builds, tests
  PowerShell, etc. — détail au §16).

**Flux complet :**
```
Claude Chat → crée une issue → GitHub → watcher.py détecte → CCL/CCW exécute
→ poste le résultat en commentaire → ferme l'issue → notification
```

> **Rafraîchissement automatique.** En début de chaque cycle de polling,
> `watcher.py` met à jour son code (`git pull --ff-only`) avant de lister
> les issues, sans rien écraser s'il existe des commits locaux non poussés.

---

## 2. Projets actifs

<!-- DEBUT:TABLEAU_PROJETS_ACTIFS (généré automatiquement par regenerer_tableaux_projets.py
     depuis configs/*.conf — issue #571 ; ne pas éditer cette zone à la main,
     lancer `python3 regenerer_tableaux_projets.py` après toute création/suppression
     manuelle de projet) -->
| Nom | Dépôt GitHub | Répertoire de travail CCL | Topic ntfy | Couleur |
|-----|-------------|--------------------------|------------|---------|
| `actualise` | AlainDelree/Actualise | ~/Actualise | (conf local) | `#009DD6` |
| `actualise_ccw` | AlainDelree/Actualise | C:\CCW\actualise | (lecture CCW) | `#00FFDD` |
| `alchess` | AlainDelree/AlChess | ~/NicLink | (conf local) | `#00D68F` |
| `annuairetoken` | AlainDelree/Annuairetoken | ~/AnnuaireToken | (conf local) | `#FFE4CC` |
| `apiselect` | AlainDelree/ApiSelect | ~/ApiSelect | (conf local) | `#FFD429` |
| `bloc_score` | AlainDelree/Bloc_score | ~/Bloc_score | (conf local) | `#FF8595` |
| `bridge_agent` | AlainDelree/Bridge_Agent | ~/Bridge_Agent | (conf local) | `#EB0000` |
| `chesscoach` | AlainDelree/Chesscoach | ~/ChessCoach | (conf local) | `#BB00FF` |
| `diagnostique_programme` | AlainDelree/Diagnostique_Programme | ~/Diagnostique_Programme | (conf local) | `#FC00A8` |
| `ecole` | AlainDelree/Ecole | ~/Ecole | (conf local) | `#767676` |
| `ff_galerie` | AlainDelree/FF_Galerie | ~/FF_Galerie | (conf local) | `#767676` |
| `gestionmail` | AlainDelree/GestionMail | ~/GestionMail | (conf local) | `#3B45A0` |
| `relecture_bridge` | AlainDelree/Relecture_Bridge | ~/Relecture_Bridge | (conf local) | `#CCFF00` |
| `rummikub` | AlainDelree/Rummikub | ~/Rummikub | (conf local) | `#ADFF8F` |
| `rummikub_ccw` | AlainDelree/Rummikub | C:\CCW\rummikub | (lecture CCW) | `#3DD8FF` |
| `scrabble` | AlainDelree/Scrabble | ~/Scrabble | (conf local) | `#7AFFFF` |
| `scrabble_ccw` | AlainDelree/Scrabble | C:\CCW\scrabble | (lecture CCW) | `#767676` |
| `testvibe` | AlainDelree/Testvibe | ~/Testvibe | (conf local) | `#CCDDFF` |
<!-- FIN:TABLEAU_PROJETS_ACTIFS -->

Chaque projet a son propre watcher (`watcher.py --config configs/<nom>.conf`)
et son propre journal de log (`logs/watcher-<nom>.log`).

> **Lignes `<nom>_ccw`.** Un projet qui a un clone dédié sur le PC Windows
> (`.conf` portant `REP_TRAVAIL_CCW`) reçoit, juste après sa propre ligne,
> une seconde ligne `<nom>_ccw` — même dépôt GitHub, répertoire de travail
> le chemin Windows du clone (ex. `C:\CCW\rummikub`). Elle ne sert QU'à
> l'outil de relecture (`relecture_web`), qui l'identifie comme distante
> grâce à ce chemin : ce n'est PAS un projet — aucun `.conf` dédié, aucun
> watcher — et elle ne doit JAMAIS être utilisée comme valeur du champ
> `PROJET` d'une issue (issue #804).

---

## 3. Créer une issue — la méthode normale : watcher `issues_inbox` (issue #483)

### 3.1 Objectif et workflow

Une issue générée par Claude Chat **ne se colle jamais dans le formulaire
web** : la méthode normale consiste à déposer un fichier `.txt` dans
**`~/Bridge_Agent/issues_inbox/`**. Un watcher dédié
(`scripts/watcher_issues_inbox.py`) le détecte au cycle de polling suivant,
le valide, crée l'issue via `gh issue create` (mêmes labels/en-tête que le
formulaire web) puis supprime le fichier. Un fichier rejeté (en-tête
malformé, projet inconnu, titre déjà porté par une issue ouverte...) est
déplacé dans `issues_inbox/rejected/`, jamais retraité automatiquement.

### 3.2 Structure disque

- **`issues_inbox/`** (gitignoré) : fichiers `.txt` en attente, nommage libre.
- **`issues_inbox/rejected/`** : fichiers rejetés, laissés en place pour
  correction manuelle.
- **`issues_inbox/en_attente/`** : fichiers portant un champ `ATTENTE` non
  vide, mis de côté avant création (voir §3.16).

### 3.3 Format attendu du fichier

Un en-tête `| CHAMP | Valeur |` optionnel et une ligne `#Titre: ...`, dans
**l'un ou l'autre ordre** (issue #512) — en-tête avant `#Titre:` ou
`#Titre:` avant l'en-tête, les deux sont équivalents — puis le corps.
Champs d'en-tête reconnus, tous optionnels sauf `PROJET` et `COMPLEXITE` :

| Champ       | Rôle                                                                |
|-------------|----------------------------------------------------------------------|
| `PROJET`    | **Obligatoire** — doit correspondre à `configs/<PROJET>.conf`        |
| `COMPLEXITE` | **Obligatoire, dans TOUTE issue, quel que soit le MODE** — une des quatre valeurs exactes `rapide`/`court`/`normal`/`lourd`, jamais un autre mot ; détail et critère de choix au §6 (issue #843). |
| `REDACTEUR` | Optionnel pour le code, mais à toujours renseigner par Claude Chat avec le nom du projet depuis lequel il écrit, validé pour cohérence avec `PROJET` (règle complète au §3.4). |
| `TIMEOUT`   | Nombre (secondes, suffixe `s` toléré) — sinon défaut du projet (`TIMEOUT_CLAUDE` du `.conf`), au moins 900 s en écriture (issue #752) ; à toujours fixer explicitement |
| `MODELE`    | Doit être une valeur reconnue (§6) si fourni                        |
| `MODE`      | Reconnu de façon tolérante (§5) — absent/non reconnu → `lecture`     |
| `LABELS`    | Labels GitHub additionnels, séparés par des virgules                 |
| `ATTENTE`   | Optionnel — condition en une phrase qui retarde la création de l'issue jusqu'à levée manuelle (§3.16) ; à poser par Claude Chat lui-même dès qu'une tâche est « à lancer après... ». |
| `RELANCE`   | Optionnel — `#N` d'une issue `needs-human` déjà ouverte à corriger/relancer plutôt que d'en créer une nouvelle (voir §3.14). |
| `REPO_CIBLE` | Chemin ABSOLU — **obligatoire** pour un projet à `PERIMETRE_DYNAMIQUE=true` (issue #125), **refusé** pour tout autre projet (issue #829). Réservé à ces projets : leur `REP_TRAVAIL` devient le `cwd` réel et le périmètre d'écriture de cette exécution, remplaçant celui du `.conf`. Si `REP_TRAVAIL` (où vit le code de l'outil) est DISJOINT de `REPO_CIBLE`, il reste quand même accessible en LECTURE et EXÉCUTION SEULEMENT, jamais en écriture (issue #833, détail §7). Supporté à la création (fichier déposé **et** formulaire web, qui affiche alors un champ obligatoire « Dépôt cible ») — pas seulement corrigeable par `RELANCE` (§3.14). |

> ⚠️ **Choix du MODE quand la tâche exécute un script (issue #722).** Si la
> « Tâche demandée » contient un mot déclencheur (**exécuter, lancer,
> mesurer, simuler, tester**, `python3`, `pytest`, **script**...), le mode
> `lecture` (défaut) ne convient presque jamais : en lecture seule, aucune
> commande en dehors d'une courte allowlist n'est exécutée, `python3` et
> tout script compris (voir §5). Choisir `| MODE | lecture active |` si le
> script ne doit pas toucher au projet, ou `| MODE | écriture |` s'il doit
> le modifier.

Label de notification par défaut : `notif_pc` est posé systématiquement,
sauf si `LABELS` demande déjà explicitement `notif_gsm` ou `notif_tous`.

**Lot multi-issues (issue #508) :** un fichier peut contenir plusieurs blocs
`#Titre:` à la suite — voir §3.13.

**Exemple canonique :**
```markdown
| PROJET     | bridge_agent |
| MODE       | écriture     |
| COMPLEXITE | normal       |

#Titre: Titre court et actionnable

## Contexte
Pourquoi cette tâche existe.

## Tâche demandée
Description précise. Indiquer explicitement si LECTURE SEULE.

## Résultat attendu
Ce que CCL doit produire ou confirmer.
```

### 3.4 Validation avant création et règles de rédaction

Un fichier est rejeté (déplacé vers `rejected/`, jamais créé sur GitHub) si :
`PROJET` absent/vide, `configs/<PROJET>.conf` introuvable ou invalide,
`#Titre:` absent/vide, `MODELE` fourni mais non reconnu, `TIMEOUT` fourni
mais non numérique, ou si le titre est déjà porté par une issue **ouverte**
du même dépôt (anti-doublon — utiliser `RELANCE`, §3.14, pour corriger une
issue déjà ouverte plutôt que de la redéposer). `REPO_CIBLE` (issue #829) :
rejet si le projet est à `PERIMETRE_DYNAMIQUE=true` et que ce champ est
absent (il serait de toute façon abandonné à l'exécution par le watcher,
sans aucun repli) ; rejet aussi si ce champ est fourni pour un projet qui
n'est **pas** à périmètre dynamique (ignoré sinon en silence), ou si le
chemin fourni est refusé par la même validation qu'à l'exécution (absolu,
existant, dossier, appartenant à l'utilisateur du watcher). Un lot (§3.13)
applique cette règle à **chaque bloc** séparément.

**Règle `REDACTEUR` (cas normal).** `REDACTEUR` doit être égal à `PROJET` —
y compris pour les projets qui ont leur propre service CCW dédié (Scrabble,
Rummikub, Actualise), dont les issues `for-windows` passent par ce service.
**Possibilité supplémentaire**, acceptée par le code pour n'importe quel
projet : le label `for-windows` avec `REDACTEUR=bridge_agent` envoie
l'issue au service CCW central de Bridge_Agent plutôt qu'au service dédié
du projet — à réserver à un besoin CCW exceptionnel sur ce projet. Dans ce
cas, indiquer aussi `SOUS_DOSSIER` (chemin du projet sous le dossier
partagé) : ce service central travaille dans un dossier parent commun à
tous les projets, pas dans le dossier d'un seul projet. Tout autre
`REDACTEUR` que ces deux cas → rejet. `REDACTEUR` absent → aucune
validation (rétrocompatibilité), mais pose le label `sans-redacteur` sur
l'issue créée, qui signale une issue rédigée sans déclarer son projet
d'origine et permet de repérer un projet qui rédige à la place d'un autre.

### 3.13 Lots multi-issues par fichier — mode mixte (issue #508)

Un fichier peut contenir **plusieurs** blocs `#Titre:` à la suite : dès
**2 occurrences ou plus**, le fichier bascule en mode lot — chaque bloc va
de son `#Titre:` jusqu'au `#Titre:` suivant (exclu) ou la fin du fichier, et
est traité **séquentiellement** comme une issue indépendante (validation,
anti-doublon, création). Un contenu placé avant le premier `#Titre:` d'un
fichier à plusieurs blocs n'appartient à aucun bloc et est ignoré. Chaque
bloc porte son propre `MODE` : un même lot peut librement mélanger lecture,
lecture active et écriture.

### 3.14 Champ `RELANCE` : corriger/relancer une issue `needs-human` existante (issues #516, #567, #726, #727)

Corriger une issue en échec (`needs-human`, ex. un `TIMEOUT` trop court)
sans sortir du flux `issues_inbox` : redéposer un fichier avec le même
titre échoue toujours (anti-doublon, §3.4, qui vaut aussi pour une issue
`needs-human` puisqu'elle reste ouverte) — `RELANCE` est le chemin
volontaire et distinct pour cibler une issue déjà ouverte.

**Format** : `| RELANCE | #N |` dans l'en-tête — détourne tout le bloc vers
la relance, `#Titre:` n'est alors plus requis et aucune issue n'est créée.

```markdown
| PROJET  | bridge_agent |
| RELANCE | #612 |
| TIMEOUT | 1800s |

Le TIMEOUT de 900s était trop court : la tâche a échoué par dépassement.
Reprendre le travail déjà committé dans le worktree plutôt que repartir
de zéro.
```

L'issue ciblée doit être **ouverte** et appartenir au dépôt du `PROJET`
indiqué, sinon rejet. Champs corrigibles dans son corps : `TIMEOUT`,
`MODELE`, `SOUS_DOSSIER` et `REPO_CIBLE` (une ligne déjà présente est
corrigée, jamais insérée) — `MODE` et `LABELS` ne sont pas corrigibles par
ce chemin. Le texte libre du fichier (au-delà de l'en-tête et de
`#Titre:`) est ajouté en fin de corps de l'issue, dans une section
horodatée `## Relance du <date>` — c'est donc bien lu par CCL à la reprise.

**Modèle recommandé pour ce texte libre (issue #727)** : la cause de
l'échec, puis la correction apportée (ex. le nouveau `TIMEOUT`). Après un
échec par dépassement de délai, ajouter une phrase du type « Un travail
partiel existe peut-être déjà dans le worktree : le vérifier et le
compléter plutôt que de repartir de zéro. »

Hors périmètre de ce chemin : changer `MODE`/labels, insérer un champ
absent du corps cible, renommer le titre GitHub — une correction plus
large reste possible à la main sur GitHub.

### 3.16 Champ `ATTENTE` : mettre une issue de côté avant sa création (issue #713)

Pour une issue à lancer plus tard (après la fusion d'une autre étape, après
une vérification manuelle...) plutôt que tout de suite — à ne pas confondre
avec `needs-human`, qui s'applique à une issue déjà créée et déjà en échec.

**Format** : `| ATTENTE | <condition en une phrase> |` dans l'en-tête, texte
libre écrit par Claude Chat (ex. « après la fusion de l'étape C et l'arrêt
de Rummikub »). Valeur vide ou champ absent → traitée tout de suite, comme
d'habitude.

Une valeur non vide détourne tout le bloc **avant** toute validation ou
création (même famille que `RELANCE`, mais en amont) : le fichier est
déplacé tel quel vers `issues_inbox/en_attente/`, aucune issue n'est créée.
**Aucune vérification automatique de la condition** — c'est Alain seul qui
juge, en relisant le texte, puis déclenche l'envoi depuis l'interface
(onglet dédié « En attente »). Pour un lot (§3.13), chaque bloc portant le
champ est mis de côté individuellement — une ligne par bloc dans l'onglet,
même si plusieurs blocs du même lot partagent exactement le même `#Titre:`
et le même `PROJET` (issue #854) ; les autres blocs suivent le circuit
normal.

Un lot déposé **directement** dans `issues_inbox/en_attente/` (dépôt
manuel, hors circuit ci-dessus — par exemple pour reporter en bloc tout un
ensemble de tâches) est lui aussi découpé automatiquement en un fichier par
bloc, avec le même nommage que ci-dessus, dès que l'onglet « En attente »
le lit (issue #855) : chaque bloc y apparaît ainsi sur sa propre ligne,
avec son propre titre, projet et condition (« aucune condition » pour un
bloc sans `ATTENTE`), au lieu d'une seule ligne pour tout le lot.

**Corriger une issue encore en attente (issue #820).** Pas de nouveau champ
— la règle est implicite : redéposer un fichier avec **exactement le même
`#Titre:` ET le même `PROJET`** qu'un élément déjà présent dans « En
attente » REMPLACE cet élément (il garde sa place dans la liste) au lieu
d'en créer un second. Si le fichier corrigé porte toujours un `ATTENTE` non
vide, sa nouvelle condition devient celle de l'élément (toujours en
attente) ; sinon il suit le circuit normal de création, et l'ancien élément
n'est supprimé qu'une fois l'issue réellement créée (jamais avant — un
fichier rejeté laisse l'ancien élément intact). Dans un lot, cette
correspondance ne vise jamais un bloc FRÈRE du même lot (seulement un
élément déjà présent dans « En attente » avant ce dépôt, issue #854) :
deux blocs du même lot, même de titre et projet identiques, restent deux
lignes distinctes.

> ⚠️ **Le titre doit être recopié à l'identique, au caractère près**, même
> si la correction porte sur le sujet de l'issue : un titre modifié, même
> légèrement, crée un **second** élément en attente à côté de l'ancien,
> **sans aucun avertissement**. Si le titre doit vraiment changer, le Chat
> prévient Alain qu'il devra supprimer l'ancien élément à la main dans
> l'onglet « En attente ». Dans sa réponse, le Chat signale aussi à Alain
> qu'il produit un fichier de remplacement d'une issue en attente.

---

## 4. Labels disponibles

| Label | Effet |
|-------|-------|
| `for-linux` | **Requis** — le watcher CCL ne voit que ces issues |
| `for-windows` | **Requis** — le watcher CCW ne voit que ces issues |
| `bridge` | Marque l'issue comme tâche bridge (traçabilité) |
| `mode_write` | **ARME le mode écriture** — CCL/CCW peut modifier des fichiers |
| `needs-human` | Posé automatiquement après 3 échecs — stoppe le retraitement |
| `done` | Posé automatiquement au succès |
| `notif_pc` | Ajoute une notification bureau (notify-send) |
| `notif_gsm` | Ajoute une notification push (ntfy) |
| `notif_tous` | notify-send + ntfy |
| `mode_scratch` | **ARME le mode lecture active** — écriture confinée au dossier scratch, voir §5 |
| `sans-redacteur` | Posé automatiquement quand `REDACTEUR` est absent de l'en-tête — signale une issue rédigée sans déclarer son projet d'origine, pour repérer un projet qui rédige à la place d'un autre, voir §3.4 |
| `sans-complexite` | Posé automatiquement quand `COMPLEXITE` est absente ou non reconnue dans l'en-tête — signale une erreur de rédaction à corriger, l'issue ayant été traitée avec le repli `normal`, voir §6 |
| `agent-claude` | Posé automatiquement à la clôture — **agent d'exécution** Claude Code (clé `AGENT` du `.conf`, issue #768) |
| `agent-vibe` | Posé automatiquement à la clôture — **agent d'exécution** Mistral Vibe (clé `AGENT` du `.conf`, issue #768) |

> `agent-claude`/`agent-vibe` identifient l'agent qui a RÉELLEMENT traité
> l'issue (`CFG.label_agent`), distinct de `for-linux`/`for-windows` (qui ne
> désignent que la plateforme visée). Comme `sans-redacteur` et `mode_scratch`,
> ils sont provisionnés d'office sur tout nouveau projet
> (`labels_github.LABELS`) — posés best-effort, un échec de pose (label
> absent du dépôt) ne bloque jamais la clôture elle-même.

> Sans label `notif_pc` / `notif_gsm` / `notif_tous`, aucune notification
> sonore ou push n'est déclenchée. Le bip est strictement opt-in.

### 4.1 Notifications — canaux et plateformes (issue #863)

Trois canaux, tous best-effort (un échec ne bloque et ne fait jamais échouer
une issue, seulement journalisé) : le **bip** (`scripts/traitement_fin.py`,
toujours émis si un label `notif_*` est posé), la **bulle de bureau**
(`notifications.py::notifier_bureau`, `notif_pc`/`notif_tous`) et **ntfy**
(push téléphone, `notif_gsm`/`notif_tous`, indépendant de la plateforme —
simple requête HTTP via `curl`).

- **Linux (CCL, ThinkPad)** : bip via `aplay`, bulle via `notify-send`
  (paquet `libnotify-bin`) — comportement historique, inchangé par #863.
- **Windows (CCW)** : depuis #863, un chemin natif existe pour les deux
  canaux locaux, sans aucune dépendance Python supplémentaire :
  - bip → module `winsound` de la bibliothèque standard Python (disponible
    uniquement sous Windows, aucun paquet à installer) ;
  - bulle → une commande PowerShell pilotant l'assembly .NET
    `System.Windows.Forms.NotifyIcon` (balloon tip), déjà présente sur tout
    Windows avec .NET Framework — pas de module PowerShell externe (type
    BurntToast) ni de paquet Python (type `win10toast`) à installer.
  - Si `aplay`/`winsound` ou `notify-send`/PowerShell sont introuvables, ou
    échouent (timeout, erreur), le canal est simplement ignoré et journalisé
    — cela ne peut plus faire échouer la fin de traitement d'une issue
    (correctif #863 : auparavant, une exception dans la lecture du bip
    pouvait interrompre `traitement_fin.py` avant le POST SSE de fin
    d'issue vers `new_issue.py`).
- **Watcher Windows en SERVICE, sans session de bureau ouverte** : la bulle
  et le bip ne peuvent physiquement pas s'afficher/s'entendre (pas de
  bureau interactif en « Session 0 »). Ce cas n'est pas détecté a priori
  (aucune dépendance supplémentaire pour l'interroger) : il se traduit par
  un timeout ou une erreur PowerShell/`winsound`, journalisée comme tout
  autre échec de ces deux canaux. **Le canal ntfy reste disponible dans ce
  cas** (requête HTTP sortante, aucun lien avec une session de bureau) : sur
  une telle installation, préférer `notif_gsm`/`notif_tous` à `notif_pc`
  seul.
- **Notification locale sur une machine Windows SEULE** (pas de ThinkPad
  CCL lançant `new_issue.py` pour centraliser) : le réglage `NOTIFIER_LOCAL`
  du `.conf` (défaut `true`, clé lue par `watcher.py`) doit rester à `true`
  côté CCW pour que ce watcher émette lui-même bip/bulle/ntfy à la fin de
  chaque issue. Sur une installation à deux postes (ThinkPad CCL + PC CCW),
  `NOTIFIER_LOCAL=false` est au contraire recommandé côté CCW, pour laisser
  `new_issue.py` (lancé sur le ThinkPad) centraliser toutes les
  notifications sans doublon ntfy — voir §16 et `app/notifications_poller.py`.
  Rappel : CCL/CCW ne modifie jamais `configs/*.conf` lui-même (ce réglage
  est réservé à Alain, voir §11).

> `mode_scratch` (lecture active, voir §5) a longtemps manqué de cette
> provision automatique (introduit par #327, oublié de `nouveau_projet.LABELS`
> jusqu'à #785) : sur un dépôt où le label n'a jamais été créé à la main,
> `creer_issue_gh` le retirait silencieusement (même repli que #648/#768
> ci-dessus) et l'issue s'exécutait en lecture seule sans que rien ne le
> signale — voir l'écart MODE déclaré/retenu journalisé et commenté sur
> l'issue (§5) depuis #785, qui détecte désormais ce cas (et tout autre
> label de mode manquant) au lancement.

> **Ajouter un label** (issue #816) : il suffit de l'ajouter à
> `labels_github.LABELS`. Chaque watcher (CCL et CCW, même `watcher.py`) le
> crée de lui-même sur son dépôt au démarrage du processus — les quatre
> incidents ci-dessus (`sans-redacteur`, `agent-claude`/`agent-vibe`,
> `mode_scratch`) venaient tous de labels restés absents de dépôts déjà
> provisionnés jusqu'à un `gh label create` manuel. Pour ne pas attendre le
> prochain redémarrage de chaque watcher, `python3 rattraper_labels.py`
> applique la même vérification tout de suite à tous les projets déclarés
> (`configs/*.conf`). Dans les deux cas : idempotent, jamais de modification
> ni de suppression d'un label déjà présent.

---

## 5. Modes lecture seule / lecture active / écriture

Le watcher pilote un MODE à trois valeurs, déduit des labels de l'issue par
ordre de priorité : `mode_write` (écriture) > `mode_scratch` (lecture
active) > aucun des deux (lecture seule, défaut).

**Lecture seule (défaut)** — CCL peut lire, analyser, grep, rapporter. Ne
peut PAS écrire de fichier ni exécuter de commande modifiant le système.
Idéal pour : diagnostics, audits, lectures de fichiers, comptages.

> ⚠️ **Aucun script ne s'exécute en lecture seule (issue #722).** En dehors
> d'une courte allowlist (`git fetch`, `git pull --ff-only`, et l'équivalent
> CCW de chargement d'assembly), tout le reste est bloqué derrière une
> approbation interactive inatteignable en session non-interactive —
> `python3`, `pytest`, un shell script, peu importe le langage : aucune
> exception. Une tâche qui doit **exécuter** un script d'analyse, de
> simulation ou de mesure, sans toucher au projet, doit choisir la
> **lecture active** (`| MODE | lecture active |`, ci-dessous) ; une tâche
> qui doit exécuter un script **modifiant** le projet doit choisir
> l'**écriture** (`| MODE | écriture |`).

**Lecture active (`mode_scratch`)** — CCL peut écrire, mais **UNIQUEMENT**
dans un dossier scratch dédié (`/tmp/bridge_scratch_<projet>/`, détruit
après la tâche), jamais dans le projet. Utile aux outils d'analyse qui
exigent un vrai fichier de config sur disque. Le livrable attendu reste un
**rapport**, comme en lecture seule — ce mode n'autorise pas de modifier le
projet. Défense en profondeur : une consigne de prompt interdit toute
écriture hors du scratch, et une vérification technique après coup détecte
et restaure automatiquement toute écriture malgré tout survenue dans le
projet (échec marqué `needs-human`). **Indisponible pour l'agent `vibe`**
(issue #761) : l'outil n'a aucun moyen d'ouvrir le scratch en écriture sans
ouvrir aussi le projet — une issue en lecture active sur un projet réglé
sur cet agent échoue.

**Mode écriture (`mode_write`)** — CCL peut modifier des fichiers, exécuter
des commandes, faire des commits git. Garde-fous automatiques :
- Backup pinné **avant** toute modification — commit git fait par le
  **watcher lui-même**, juste avant de lancer CCL (issue #846), sauf
  commande de sauvegarde personnalisée dans `CMD_BACKUP` (issue #847 :
  une valeur vide ou la commande standard écrite par `nouveau_projet.py` —
  `git add -A && git commit -m "avant-<description>" --allow-empty`, quel
  que soit le message — ne compte pas comme personnalisée et laisse le
  watcher committer ; seule une commande réellement différente, ex.
  alchess, reste la consigne que CCL exécute lui-même)
- **JAMAIS `git push`** — Alain pousse lui-même après vérification
- Aucune commande destructrice sans demande explicite
- Périmètre strict : CCL ne travaille que dans le dossier configuré
- Avertissement best-effort « Succès sans commit » (issues #764/#856) :
  signalé dans le commentaire de clôture si un succès ne laisse AUCUN commit
  propre à la tâche depuis le HEAD d'avant traitement (en excluant le commit
  de sauvegarde du watcher seulement s'il en a réellement fait un — jamais
  par position, pour ne pas se tromper sur un projet à `CMD_BACKUP`
  personnalisée comme alchess, qui n'en a aucun). Ton neutre, jamais
  bloquant : peut être parfaitement légitime (rien à modifier).

> `configs/*.conf` reste interdit à l'écriture **quel que soit le mode**
> (lecture active comme écriture) — garde-fou technique, voir §11.

---

## 6. Champs spéciaux dans le corps de l'issue

Le watcher lit ces champs dans le tableau markdown de l'en-tête :

| Champ | Valeur | Effet |
|-------|--------|-------|
| `MODE` | `lecture`, `lecture active` ou `écriture` | Défaut `lecture` si absent/non reconnu. Voir §5 pour le comportement de chaque mode. |
| `PRIORITE` | `haute` ou `critique` | Retry infini (au lieu de 3 max) |
| `TIMEOUT` | ex. `600s` | Surcharge le défaut du projet (`TIMEOUT_CLAUDE` du `.conf`), au moins 900 s en écriture si absent (issue #752) ; à toujours fixer explicitement |
| `MODELE` | une des valeurs reconnues (`app/projets.py`) : `claude-sonnet-5`, `claude-opus-4-8`, `claude-haiku-4-5`, `claude-fable-5` | Force un modèle CCL spécifique pour cette issue |
| `PROJET` | ex. `bridge_agent` | Détection d'incohérence par `new_issue.py`. Claude Chat doit l'inclure dans toutes les issues qu'il génère, avec le nom exact du projet cible. |
| `TYPE` | `chef` ou `ouvrier` | Identifie le rôle de l'issue dans le pattern multi-agent (voir §14). `chef` = orchestre les ouvriers. `ouvrier` = sous-tâche créée par le chef. Absent = issue normale. |
| `SUITE_DE` | ex. `#5` | Indique que cette issue fait suite à l'issue #N — préfixer alors aussi le titre par `Suite #N : `. Absent = issue inédite. |
| `RELANCE` | ex. `#612` | **Spécifique à `issues_inbox/`**, voir §3.14 — détourne le fichier déposé vers la correction/relance de l'issue #N déjà ouverte plutôt que de créer une nouvelle issue. |
| `REDACTEUR` | ex. `bridge_agent` | **Spécifique à `issues_inbox/`**, voir §3.4 pour la règle complète — nom du projet depuis le contexte duquel Claude Chat a rédigé l'issue, validé pour cohérence avec `PROJET`. À toujours renseigner par Claude Chat. |
| `COMPLEXITE` | **uniquement** `rapide` / `court` / `normal` / `lourd` — aucun autre mot | **Obligatoire dans toute issue, quel que soit le MODE** (lecture, lecture active, écriture) — estimée par Claude Chat au moment de rédiger l'issue, jamais omise. 4e dimension de la calibration automatique du TIMEOUT (voir §19). `Absent ou non reconnu = normal` est un **repli technique du code**, pas un choix de rédaction légitime (voir encadré ci-dessous, issue #843). |
| `RESEAU` | `oui` ou `non` | Tag réseau pour la calibration TIMEOUT (voir §19) : `oui` = issue impliquant de lourdes opérations réseau, `non` = purement locale. Optionnel. |

> ⚠️ **`COMPLEXITE` obligatoire, quatre valeurs exactes (issue #843).** Une
> mesure sur ~1500 issues fermées des dépôts du système montre ce champ
> absent dans plus de la moitié des issues de plusieurs projets, et des
> valeurs hors liste ailleurs — le code range alors tout cela
> silencieusement dans `normal`, ce qui fausse la calibration du TIMEOUT.
> **Claude Chat doit donc inclure `| COMPLEXITE | <valeur> |` dans TOUTE
> issue qu'il rédige**, quel que soit le MODE, en choisissant **exactement**
> l'un de ces quatre mots — tout autre mot est interdit :
>
> - `rapide` (durée médiane ≈ 1-2 min) — correction ponctuelle dans un seul
>   fichier, sans test ni build : un libellé, une valeur de config, une
>   couleur CSS.
> - `court` (≈ 2-5 min) — modification simple limitée à 2-3 fichiers, sans
>   refonte ni ajout de tests.
> - `normal` (≈ 3-15 min) — plusieurs fichiers, ajout ou adaptation de
>   tests, ou modification touchant à la fois le serveur et une page/l'IHM.
> - `lourd` (≈ 10-30 min) — refonte ou migration, mesure/analyse portant sur
>   un périmètre étendu, ou tâche impliquant un build/une installation
>   longue.
>
> **En cas d'hésitation entre deux valeurs, toujours choisir la plus
> élevée** : une issue sous-estimée (TIMEOUT trop court, échec par
> dépassement) coûte plus cher qu'une issue surestimée.

Format dans le corps :
```markdown
| PRIORITE   | haute |
| TIMEOUT    | 600s  |
| MODELE     | claude-opus-4-8 |
| PROJET     | bridge_agent |
| COMPLEXITE | court |
```

> ⚠️ **Claude Chat doit toujours inclure** `| PROJET | <nom> |` dans l'en-tête
> des issues qu'il génère, avec le nom exact du projet cible
> (`bridge_agent`, `alchess`, `ff_galerie`).

> ℹ️ Le champ `| LABELS | … |` n'est **pas** lu par le watcher `issues_inbox` :
> il est consommé par `new_issue.py` (formulaire web) pour ajouter des
> labels supplémentaires à ceux posés d'office.

---

## 7. Périmètre par projet

CCL est contraint à un répertoire précis par projet — il refuse de travailler
hors périmètre même si l'issue le demande explicitement :

> ℹ️ **Projet à périmètre dynamique (`PERIMETRE_DYNAMIQUE=true`) et dossier
> propre à l'outil (issue #833).** Pour ce type de projet (ex.
> `diagnostique_programme`, un outil d'audit qui analyse d'AUTRES dépôts, son
> code vivant dans son propre `REP_TRAVAIL`), le périmètre d'écriture et le
> `cwd` restent le seul `REPO_CIBLE` de l'issue. Mais quand `REP_TRAVAIL` est
> DISJOINT de `REPO_CIBLE` (ni identique, ni l'un contenu dans l'autre), il
> reste accessible en LECTURE et EXÉCUTION SEULEMENT — notamment pour
> importer ou lancer le code de l'outil lui-même (`PYTHONPATH`) — jamais en
> écriture. Ce confinement reste, comme pour le scratch de la lecture active
> (#327, §5), une CONVENTION DE PROMPT complétée par une détection technique
> après coup (empreinte `git status --porcelain -uall` avant/après la
> tentative) : une écriture détectée dans ce dossier est restaurée, l'échec
> est DÉFINITIF (pas de nouvelle tentative) et le label `needs-human` est
> posé. Comme pour ce même garde-fou #327, **les fichiers ignorés par git ne
> sont PAS détectés** (`git status` ne les voit pas sans `--ignored`).
> Agent `vibe` : jamais ouvert (aucune option de lecture seule par
> répertoire côté `vibe`) — un projet dynamique réglé sur cet agent reste
> incapable de lire/exécuter son propre code quand il est hors `REPO_CIBLE`.

> ℹ️ **Projet à périmètre dynamique : issue visant le dépôt du projet
> lui-même traitée comme un projet normal (issue #837).** Quand `REPO_CIBLE`
> d'une issue désigne EXACTEMENT `REP_TRAVAIL` (chemin résolu identique —
> cas de `diagnostique_programme` développant son propre code), cette issue
> précise suit les règles d'un projet à périmètre FIXE : worktree isolé
> (#337) et parallélisme selon `MAX_WRITE_PARALLELE`, verrou, commit de
> sauvegarde, contrôles habituels — `REPO_CIBLE` est alors seulement vérifié
> (même dossier), sans autre effet. Pour TOUTES LES AUTRES issues de ce même
> projet (`REPO_CIBLE` absent, différent, ou imbriqué dans un sens ou
> l'autre avec `REP_TRAVAIL`), le traitement reste celui décrit ci-dessus :
> direct dans `REP_TRAVAIL`, sans worktree ni parallélisme —
> `MAX_WRITE_PARALLELE` n'a alors AUCUN effet sur elles.

<!-- DEBUT:TABLEAU_PERIMETRE_PROJETS (généré automatiquement par regenerer_tableaux_projets.py
     depuis configs/*.conf — issue #571 ; ne pas éditer cette zone à la main,
     lancer `python3 regenerer_tableaux_projets.py` après toute création/suppression
     manuelle de projet) -->
| Projet | Périmètre autorisé |
|--------|-------------------|
| `actualise` | /home/alain/Actualise |
| `alchess` | /home/alain/NicLink |
| `annuairetoken` | /home/alain/AnnuaireToken |
| `apiselect` | /home/alain/ApiSelect |
| `bloc_score` | /home/alain/Bloc_score |
| `bridge_agent` | /home/alain/Bridge_Agent |
| `chesscoach` | /home/alain/ChessCoach |
| `diagnostique_programme` | /home/alain/Diagnostique_Programme |
| `ecole` | /home/alain/Ecole |
| `ff_galerie` | /home/alain/FF_Galerie |
| `gestionmail` | /home/alain/GestionMail |
| `relecture_bridge` | /home/alain/Relecture_Bridge |
| `rummikub` | /home/alain/Rummikub |
| `scrabble` | /home/alain/Scrabble |
| `testvibe` | /home/alain/Testvibe |
<!-- FIN:TABLEAU_PERIMETRE_PROJETS -->

---

## 8. Sécurité

Seul un auteur autorisé (`auteurs_autorises()` dans `watcher.py`) peut faire
traiter une issue — quel que soit le label posé dessus. Une issue par
ailleurs éligible (bons labels) mais d'auteur non autorisé est ignorée, quel
que soit le mode (lecture, écriture, bootstrap CCW).

**Identifiant GitHub paramétrable (issue #859).** Bridge_Agent est pensé
pour être installé par quelqu'un d'autre qu'Alain (compte GitHub différent) :
`auteurs_autorises()` ne contient plus `AlainDelree` en dur, mais le compte
renvoyé par `identite.compte_github()` — module `identite.py` à la racine du
dépôt, SEULE source de vérité pour cette valeur (également utilisée comme
propriétaire par défaut du dépôt dans `nouveau_projet.py`). Deux sources,
dans cet ordre de priorité :
1. `identite_locale.conf` à la racine du dépôt (gitignoré, jamais committé —
   format `CLÉ = valeur` comme `configs/*.conf`, mais délibérément HORS de ce
   dossier : §12 interdit à CCL/CCW toute écriture dans `configs/*.conf`, et
   ce fichier doit pouvoir y échapper même par accident) :
   `COMPTE_GITHUB = <login GitHub à utiliser>`.
2. à défaut : le compte `gh` connecté localement (`gh api user --jq
   .login`). Sur la machine d'Alain, c'est déjà `AlainDelree` —
   comportement inchangé sans rien configurer de plus.

Si aucune des deux sources ne fournit de valeur (ex. `gh` absent ou non
authentifié, et aucun `identite_locale.conf`), `auteurs_autorises()` renvoie
un ensemble **vide** — jamais `AlainDelree` par défaut ni « tout le monde » :
le watcher refuse alors de démarrer (`verifier_identite_demarrage()` dans
`main()`, `sys.exit` explicite) plutôt que de tourner en rejetant
silencieusement chaque issue. Même principe pour l'utilisateur SSH par
défaut du PC fixe CCW (`app/ccw.py`) : `identite.utilisateur_ssh_defaut()`
lit `UTILISATEUR_SSH` dans `identite_locale.conf`, à défaut retombe sur le
repli historique `AlainW` (seule installation existante à ce jour, sans
équivalent auto-détectable comme `gh`).

---

## 9. Accès externe

**Lire la doc par curl** (le dépôt est public, pas d'authentification requise) :
```bash
curl -sL https://raw.githubusercontent.com/AlainDelree/Bridge_Agent/master/BRIDGE_AGENT_DOC.md
```

⚠️ **Cache CDN après un push très récent.** Dans les toutes premières minutes
suivant un `git push` sur `BRIDGE_AGENT_DOC.md`, `curl` peut encore servir
une version mise en cache par le CDN GitHub. Si le contenu lu ne semble pas
refléter un push très récent, ajouter un paramètre anti-cache avant de
conclure à une absence réelle du contenu :
```bash
curl -sL "https://raw.githubusercontent.com/AlainDelree/Bridge_Agent/master/BRIDGE_AGENT_DOC.md?nocache=$(date +%s)"
```

---

## 10. Structure du dépôt Bridge_Agent

Arborescence et détail de l'architecture technique interne : voir `ARCHITECTURE.md`.

**Agent d'exécution par projet** (clé `AGENT` du `.conf`, issue #759) :
`claude` par défaut. Un second agent, `vibe` (Mistral Vibe), est disponible
depuis l'issue #760 — son profil d'écriture versionné et la procédure de
déploiement (profil TOML + dossiers de confiance) vivent dans
`provisioning/vibe/` (voir `provisioning/vibe/README.md`). Basculer un
projet dessus reste une action manuelle, projet par projet. L'agent qui a
réellement traité une issue est tracé à sa clôture par un label GitHub
dédié (`agent-claude`/`agent-vibe`, issue #768, voir §4).

**Historique du projet** : vit dans `CHANGELOG.md` à la racine, une entrée
par issue (`## <date> — issue #N`), la plus récente en premier — pas dans ce
document. Une issue en écriture n'édite jamais `CHANGELOG.md` directement :
elle écrit sa propre entrée dans un fichier `CHANGELOG-<N>.md` à la racine de
son worktree, fusionné ensuite dans `CHANGELOG.md` par
`scripts/fusionner_changelog.py` — **après** avoir fusionné la branche
worktree dans `master`, jamais avant, et toujours depuis `REP_TRAVAIL`,
jamais depuis le worktree lui-même (détail et raison : `WORKTREES.md` §3).

**Toute issue qui modifie ce document** (`BRIDGE_AGENT_DOC.md`) doit, dans la
même opération, mettre à jour la toute dernière ligne du fichier — format
`*Dernière mise à jour : <date> — ...*` (tiret cadratin juste après la date)
— dont `regenerer_tableaux_projets.py` dépend par regex pour la rafraîchir
automatiquement. Viser la **toute fin du fichier** : une recherche sur
« Dernière mise à jour » remonte d'abord cet exemple-ci, pas le vrai pied de
page, bien plus bas.

---

## 11. Conventions de code

- **Langue** : français pour tout ce qu'Alain et Claude nomment librement
  (identifiants Python, commentaires, clés de config). Anglais conservé pour
  les contrats existants (noms de labels GitHub, drapeaux CLI, mots-clés Python).
- **Issues** : produire titre + corps avec `#Titre:` en première ligne du corps.
  Claude Chat dépose ce contenu dans un fichier `.txt` sous `issues_inbox/`
  (§3) — jamais en le présentant pour copier-coller manuel dans le formulaire
  web `new_issue.py` (repli légitime, mais réservé à Alain). **Si aucun outil
  fichier (`bash`, `create_file`, etc.) n'est disponible dans la conversation
  en cours** — donc impossible de produire ce `.txt` — Claude Chat ne bascule
  **jamais** silencieusement vers le formulaire web comme repli de sa propre
  initiative, même en s'appuyant sur le statut de repli légitime de ce
  formulaire pour se justifier : il le signale explicitement à Alain (« je
  n'ai pas d'outil fichier dans cette conversation ») et lui demande comment
  procéder (issue #685, suite à un cas constaté sur le projet Rummikub où
  cette ambiguïté a conduit à présenter le texte en clair de bonne foi).
- **Mode par défaut** : lecture seule. N'armer `mode_write` que si la tâche
  demande explicitement une modification de fichier.
- **Scripts PowerShell (`.ps1`) : BOM UTF-8 obligatoire dès la création.**
  Tout fichier `.ps1` contenant des caractères accentués (donc quasiment tous,
  vu la langue française) **doit** commencer par un BOM UTF-8 (octets
  `EF BB BF`) : Windows PowerShell 5.1 — celui installé sur le PC fixe CCW —
  interprète sinon un fichier UTF-8 sans BOM comme de l'ANSI (Windows-1252),
  et le script plante au parsing dès la première exécution.
- **Dogfooding** : Bridge_Agent se développe lui-même via ses propres issues.
- **Niveau de détail des issues (issue #281)** : Claude Chat décrit le
  problème, la cause et l'intention du fix. Il ne rédige pas le code complet
  (blocs Avant/Après, implémentations entières) : CCL lit les fichiers
  source et fait l'implémentation lui-même. **Exception tolérée** : un
  snippet de 1-2 lignes si la syntaxe est non-triviale ou si l'intention
  serait ambiguë sans exemple.
  - *Mauvais exemple* : fournir les trois méthodes complètes Avant/Après
    pour un fix pywebview de navigation différée.
  - *Bon exemple* : « Dans `api.py`, pour les trois méthodes de navigation,
    différer l'appel dans un thread daemon avec `time.sleep(0.05)` avant
    de naviguer. »
- **Parallélisation `mode_write` (issue #337, information pour les projets
  utilisant Bridge_Agent)** : plusieurs issues `mode_write` d'un même projet
  peuvent tourner **en parallèle**, chacune dans son propre `git worktree`.
  Deux issues touchant les mêmes fichiers ou les mêmes zones de code peuvent
  donc générer un conflit de merge à résoudre manuellement par Alain.
  **Recommandation** : scoper chaque issue sur un périmètre de fichiers aussi
  distinct que possible des autres issues `mode_write` en cours. Une
  `RELANCE` (§3.14) reprend le worktree déjà existant de l'issue ciblée
  plutôt que d'en recréer un neuf. Détail du mécanisme et du workflow de
  fusion : voir [`WORKTREES.md`](WORKTREES.md).

---

## 12. Règles d'usage

### Règle fondamentale : toujours passer par Claude Chat

Toute modification de Bridge_Agent ou des projets associés doit
être initiée par Claude Chat (CC) sous forme d'issue, même pour
les petits changements (une ligne CSS, un label, une couleur).

**Pourquoi :**
- **Traçabilité** : chaque modif a une issue qui explique le pourquoi,
  un diff connu de CC, un commit git pour le retour arrière.
- **Diagnostic** : si une régression apparaît, CC connaît le contexte
  exact de chaque changement récent.
- **Cohérence** : CC maintient une vision globale de l'architecture
  et évite les effets de bord.

**Workflow :**
1. Alain décrit l'idée à CC dans Claude Chat
2. CC dépose un fichier `.txt` dans `issues_inbox/` (§3) — jamais de texte
   présenté pour un copier-coller manuel dans le formulaire web (repli
   réservé à Alain)
3. CCL exécute, committe, ne pousse pas
4. Alain vérifie (`git show`) et pousse

**Exception :** les modifications de `configs/*.conf` (`PERIMETRE`,
`TOPIC_NTFY`, `FICHIER_CONTEXTE`, etc.) sont réservées à **Alain seul** —
onglet Configuration de `new_issue.py`, ou directement à la main.
**CCL/CCW ne modifient JAMAIS `configs/*.conf`**, quel que soit le mode
(écriture comme lecture active) et même si l'issue le demande
explicitement en toutes lettres : toute modification survenue malgré tout
est détectée et annulée automatiquement par un garde-fou technique de
`watcher.py` (mécanisme détaillé dans `ARCHITECTURE.md`).

### 12.1 Consignes injectées — architecture à trois couches (issues #209, #211)

Le bridge injecte automatiquement des **consignes** à trois couches dans le
**prompt donné à CCL au moment du traitement de l'issue**, quel que soit le
chemin par lequel l'issue a été créée. Trois couches, de la plus générale à la
plus spécifique, lues dans le dossier `consignes/` (à la racine du dépôt,
communes à tous les projets) :

| Couche | Fichier | Portée | Optionnel ? |
|--------|---------|--------|-------------|
| **Globale** | `consignes/globales.md` | TOUTE issue, tout projet, tout TYPE | **Non** — rappels de sécurité transversaux (ne jamais pousser, backup avant modif, respect du périmètre, abandon immédiat au refus de permission / blocage sans progrès — mais PAS aux opérations longues légitimes qui progressent normalement ; contrainte d'exécution synchrone et bloquante, sans attente différée) |
| **Type** | `consignes/type_<type>.md` | Issues d'un TYPE donné (ex. `type_chef.md`) | **Oui** — créé à la demande |
| **Projet** | `consignes/projet_<projet>.md` | Issues ciblant un projet donné | **Oui** — créé à la demande |

⚠️ **Pour un Claude en conversation** (celui qui rédige une issue avant de
l'envoyer) : ce tableau décrit une injection qui n'a lieu qu'à l'exécution
(CCL/CCW) — tu ne vois donc pas ce contenu ici. Avant de proposer une issue,
consulte `consignes/globales.md` (rappels de sécurité, garde-fous) via :
```bash
curl -sL "https://raw.githubusercontent.com/AlainDelree/Bridge_Agent/master/consignes/globales.md"
```

---

## 14. Délégation Chef → Ouvrier (changement d'environnement)

**Principe :** quand une sous-tâche exige un environnement différent de celui
du CCL en cours (typiquement CCL Linux → CCW Windows), le CCL « chef » crée
lui-même une issue « ouvrier » ciblant le bon environnement via `gh issue
create`, puis surveille sa fermeture avant de livrer sa réponse.

**Quand NE PAS passer par un chef (issue #225) :**

- **Critère de décision** : le chef se justifie quand la tâche comporte du
  travail réel côté Linux (avant et/ou après) dans la même unité de travail.
  Si la TOTALITÉ de la tâche s'exécute sous Windows, créer directement
  l'issue avec `| LABELS | for-windows |` (champ `LABELS`, §6) — pas de chef.
- **Contre-exemple explicite** : un chef qui se contente de créer un ouvrier
  puis d'attendre sa fermeture, sans orchestration réelle, est du surcoût
  pur (deux issues, deux invocations `claude`, TIMEOUT long, attente
  synchrone bloquante).
- **⚠️ Contrepartie opérationnelle** : depuis les issues #709/#711, créer
  une issue `for-windows` par le formulaire web ou par un fichier déposé
  dans `issues_inbox/` démarre automatiquement en arrière-plan le service
  dédié du projet — mais un échec (SSH par exemple) ne fait pas échouer la
  création de l'issue et n'affiche aucun message ; de plus, une issue créée
  par `gh issue create` direct ne bénéficie pas de ce démarrage
  automatique. Vérifier dans l'onglet CCW (§16) que le service est bien
  démarré avant d'envoyer une issue `for-windows` directe ou un ouvrier.

**Ce n'est pas déclenché automatiquement par `watcher.py`** : le chef agit
sur instruction explicite de l'issue qui le mandate (pas de détection auto
du rôle chef). La contrainte d'exécution synchrone et bloquante (attendre la
fermeture des ouvriers avant de conclure) est injectée automatiquement dans
le prompt via `consignes/globales.md` (§12.1) — rien à rappeler dans le
corps de l'issue chef.

**Format des titres :**
- **Chef** : titre préfixé par `Chef : ` (ex. `Chef : rebuild Scrabble avec
  nouveau dictionnaire`).
- **Ouvrier** : titre préfixé par `Ouvrier N : ` (ex. `Ouvrier 1 : ...`).
- Claude Chat génère toujours l'issue chef uniquement — l'ouvrier est créé
  par le chef lui-même.

**Timeout du chef :** si le chef attend la fermeture d'un ouvrier (surtout
CCW, dont le watcher peut nécessiter un rallumage), prévoir un `TIMEOUT`
généreux dans l'en-tête de l'issue chef (ex. 1800-3600s) pour couvrir le
cycle complet, plutôt que le timeout par défaut d'une issue simple.

---

## 16. Agent Windows CCW

**But.** Agent Claude Code sur un PC fixe Windows dédié, pour les issues
`for-windows` — principalement les builds `.exe` (PyInstaller) qui exigent
Windows natif. **CCW ne pousse jamais** (même règle que CCL) : il committe
localement, Alain vérifie et pousse.

La plupart des projets ont leur propre service CCW dédié (`REDACTEUR` =
`PROJET`, règle normale, §3.4). Pour un besoin CCW exceptionnel sur un
projet — même s'il a son propre service dédié —, `| LABELS | for-windows |`
avec `| REDACTEUR | bridge_agent |` route l'issue vers le service central de
Bridge_Agent (détail complet : §3.4) — indiquer alors aussi `SOUS_DOSSIER`,
ce service central travaillant dans un dossier partagé entre projets.

**Champs d'en-tête utiles à une issue `for-windows`** : `SOUS_DOSSIER`
(chemin RELATIF sous le dossier partagé, pour cibler un sous-projet précis
sans que `claude` démarre avec un cwd divergent du dossier visé par une
commande git) ; `REPO_CIBLE` (chemin ABSOLU, réservé aux projets à
périmètre dynamique, issue #125 — **obligatoire** pour ces projets,
**refusé** pour les autres, voir §3.3/§3.4 ; leur `REP_TRAVAIL`, s'il est
disjoint de `REPO_CIBLE`, reste accessible en lecture et exécution seules —
issue #833, détail §7 ; s'il désigne `REP_TRAVAIL` lui-même, l'issue est
traitée comme un projet normal — worktree, parallélisme, `MAX_WRITE_
PARALLELE` effectif — sinon directe, sans worktree ni parallélisme, issue
#837, détail §7) ; `CREATION` (déclenche le
bootstrap automatique d'un nouveau service CCW dédié de bout en bout —
généré uniquement par le formulaire web, case « Projet CCW », jamais à
produire à la main).

**Build : copie locale avant partage.** Un build lancé directement sur le
dossier réseau partagé peut produire des fichiers corrompus — copier
d'abord les sources en local sur le PC Windows, builder entièrement là,
puis ne recopier que l'artefact final vers le partage. Détails et
checklist par projet : `BUILD_WINDOWS_CCW.md`.

**Avant de rédiger une issue de build Windows**, lire
`BUILD_WINDOWS_CCW.md` avec
`curl -sL https://raw.githubusercontent.com/AlainDelree/Bridge_Agent/master/BUILD_WINDOWS_CCW.md`
— il contient le modèle d'issue à utiliser.

**Issue coincée.** Le bouton ⛔ « Interrompre cette issue » de l'interface
web arrête le service côté Windows et nettoie son verrou si le process est
bien confirmé mort ; l'issue n'est **pas** fermée (label `needs-human`
posé), le service reste à relancer manuellement.

Provisioning et réinstallation complète du PC fixe :
`provisioning/windows/REINSTALLATION_CCW.md`.

---

## 18. Pièces jointes image dans les issues (issues #191, #248)

Les images sont ajoutées par **Alain**, depuis l'onglet « Nouvelle issue »
du formulaire web (upload PNG/JPEG/GIF, intégré automatiquement au corps
via une URL `raw.githubusercontent.com`) — **Claude Chat n'en produit
jamais** : il n'a pas la main sur cet upload et ne doit jamais prétendre le
contraire dans une issue.

---

## 19. Calibration automatique du TIMEOUT (issues #220, #221, #222, #223, #434, #475, #590)

Toujours fixer un `TIMEOUT` dans l'en-tête d'une issue (sinon défaut du
projet, `TIMEOUT_CLAUDE` du `.conf`, au moins 900 s en écriture — §6, issue
#752). La valeur
`TIMEOUT_suggéré` affichée à la fin du commentaire de clôture d'une issue
est calculée depuis l'historique réel
des durées, bornée entre un plancher et un **plafond de 3600s** (issue
#590). C'est une **indication, pas une règle** : elle peut être trop haute
(gonflée après des dépassements répétés) comme trop basse — la confronter
à la durée réelle et à la complexité de l'issue avant de l'appliquer
telle quelle.

`RELANCE` (§3.14) corrige la valeur d'une ligne d'en-tête déjà présente
(`TIMEOUT`, `MODELE`, `SOUS_DOSSIER`, `REPO_CIBLE`) mais n'en ajoute
jamais : si l'issue d'origine n'avait pas de ligne `TIMEOUT`, la relance ne
change rien — fermer l'issue et en déposer une nouvelle avec un `TIMEOUT`.
`REPO_CIBLE` fait exception depuis l'issue #829 : il est désormais fourni
dès la création (fichier déposé ou formulaire web, §3.3), `RELANCE` ne
servant plus qu'à le CORRIGER après coup, comme avant.

Voir §6 pour les champs `COMPLEXITE` et `RESEAU`, qui affinent cette
calibration (constantes actuelles du code : `K_VARIABILITE` = 3, issue
#475).

### 19.1 Format d'une ligne de `logs/historique_durees.json` (issue #845)

Fichier gitignoré (télémétrie locale), liste JSON append-only — une entrée
par tentative close (succès OU tentative expirée). Champs présents depuis
l'origine (issues #108/#220) : `projet`, `type`, `mode`, `duree` (secondes,
entier, `None` si inconnue), `date`, `longueur_corps_issue`,
`nb_etapes_checklist`, `nb_fichiers_cibles` (toujours `None`),
`nb_projets_actifs_au_lancement`, `expiree`, `k_utilise`, et `tag_reseau`
(absent si non détecté).

Champs ajoutés par l'issue #845, **tous optionnels** (absents sur toute
ligne écrite avant cette issue — voir rétrocompatibilité ci-dessous) :

| Champ                        | Contenu |
|-------------------------------|---------|
| `numero_issue`                | numéro de l'issue GitHub |
| `tentative`                   | rang de la tentative (1 = première) à laquelle cette ligne correspond |
| `timeout_applique`            | TIMEOUT (secondes) réellement utilisé pour lancer l'agent sur cette tentative |
| `complexite`                  | valeur RETENUE pour la calibration (identique à `extraire_complexite()`) : `rapide`/`court`/`normal`/`lourd` |
| `complexite_statut`           | `valide` (ligne COMPLEXITE reconnue), `absente` (aucune ligne), ou `non_reconnue` (ligne présente, valeur hors des 4 niveaux — repli sur `normal`) |
| `complexite_brute`            | valeur d'origine, telle qu'écrite — présent SEULEMENT si `complexite_statut == "non_reconnue"` |
| `timeout_suggere_lancement`   | `TIMEOUT_suggéré` (secondes) en vigueur AU LANCEMENT de l'issue, avant toute mise à jour de la calibration par ce traitement — absent si aucune suggestion n'était encore calculable |
| `estimation_lancement`        | estimation de durée affichée au lancement, même format que `estimer_duree()` : `{"mediane", "n", "fiabilite"}` |

`timeout_suggere_lancement`/`estimation_lancement` sont **figés une seule
fois, avant la première tentative** (`_demarrer_traitement`), puis
retransmis tels quels à chaque ligne écrite pour cette même issue (succès et
chaque tentative expirée) — jamais recalculés après coup : les recalculer
à la clôture, une fois la calibration déjà mise à jour par CETTE issue,
fausserait la mesure de leur propre fiabilité.

**Tentative expirée (`expiree: true`)** : `duree` y est le **plafond
TIMEOUT atteint**, pas une durée réelle de traitement — l'agent a été tué
avant d'avoir fini. Ne jamais l'interpréter comme une mesure de durée de
traitement réussi.

**Rétrocompatibilité** : une ligne écrite avant l'issue #845 n'a aucun de
ces nouveaux champs — tous les lecteurs (`estimer_duree`, l'estimation
affichée côté interface, `scripts/archiver_historique.py`) doivent
continuer à fonctionner sur une telle ligne sans lever d'exception.
`scripts/archiver_historique.py` déplace chaque entrée comme un dict
entier (jamais une reconstruction champ par champ) : une ligne archivée
conserve donc automatiquement tous ses champs, anciens comme nouveaux.

`estimer_duree()` (badge de fiabilité de l'interface, issue #108) vit
désormais dans `watcher.py` — SEULE source, importée par `app/issues.py` —
pour que le watcher puisse, au lancement d'une issue, figer l'EXACTE même
estimation que celle déjà affichée, sans dupliquer ce calcul.

---

*Dernière mise à jour : 9 novembre 2026 — §4.1 (nouveau), notifications :
chemin Windows natif pour la bulle de bureau (PowerShell/NotifyIcon) et le
bip (`winsound`), sans dépendance Python supplémentaire ; une notification
qui échoue (outil absent, watcher en service sans session de bureau) ne
peut plus faire échouer la fin de traitement d'une issue, sous aucun
système (issue #863).*

Historique complet : voir [`CHANGELOG.md`](CHANGELOG.md).
