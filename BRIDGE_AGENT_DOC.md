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

> **Rafraîchissement automatique (issue #185).** En début de chaque cycle de
> polling, `watcher.py` met à jour son code (`git pull --ff-only`) avant de
> lister les issues : aucun `git push` manuel préalable n'est requis, et ce
> pull échoue proprement sans rien écraser s'il existe des commits locaux
> pas encore poussés.

---

## 2. Projets actifs

<!-- DEBUT:TABLEAU_PROJETS_ACTIFS (généré automatiquement par regenerer_tableaux_projets.py
     depuis configs/*.conf — issue #571 ; ne pas éditer cette zone à la main,
     lancer `python3 regenerer_tableaux_projets.py` après toute création/suppression
     manuelle de projet) -->
| Nom | Dépôt GitHub | Répertoire de travail CCL | Topic ntfy | Couleur |
|-----|-------------|--------------------------|------------|---------|
| `actualise` | AlainDelree/Actualise | ~/Actualise | (conf local) | `#009DD6` |
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
| `scrabble` | AlainDelree/Scrabble | ~/Scrabble | (conf local) | `#7AFFFF` |
<!-- FIN:TABLEAU_PROJETS_ACTIFS -->

Chaque projet a son propre watcher (`watcher.py --config configs/<nom>.conf`)
et son propre journal de log (`logs/watcher-<nom>.log`).

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
Champs d'en-tête reconnus, tous optionnels sauf `PROJET` :

| Champ       | Rôle                                                                |
|-------------|----------------------------------------------------------------------|
| `PROJET`    | **Obligatoire** — doit correspondre à `configs/<PROJET>.conf`        |
| `REDACTEUR` | Optionnel — nom du projet depuis lequel Claude Chat écrit, validé pour cohérence avec `PROJET` (règle complète au §3.4). |
| `TIMEOUT`   | Nombre (secondes, suffixe `s` toléré) — sinon défaut du projet       |
| `MODELE`    | Doit être une valeur reconnue (§6) si fourni                        |
| `MODE`      | Reconnu de façon tolérante (§5) — absent/non reconnu → `lecture`     |
| `LABELS`    | Labels GitHub additionnels, séparés par des virgules                 |
| `ATTENTE`   | Optionnel — condition en une phrase qui retarde la création de l'issue jusqu'à levée manuelle (§3.16) ; à poser par Claude Chat lui-même dès qu'une tâche est « à lancer après... ». |
| `RELANCE`   | Optionnel — `#N` d'une issue `needs-human` déjà ouverte à corriger/relancer plutôt que d'en créer une nouvelle (voir §3.14). |

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
| PROJET | bridge_agent |
| MODE   | écriture     |

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
issue déjà ouverte plutôt que de la redéposer).

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
validation (rétrocompatibilité), mais pose le label informatif
`sans-redacteur` sur l'issue créée.

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
champ est mis de côté individuellement ; les autres blocs suivent le
circuit normal.

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
| `sans-redacteur` | Posé automatiquement quand `REDACTEUR` est absent de l'en-tête — purement informatif, voir §3.4 |

> Sans label `notif_pc` / `notif_gsm` / `notif_tous`, aucune notification
> sonore ou push n'est déclenchée. Le bip est strictement opt-in.

> `mode_scratch` (lecture active, voir §5) n'est pas dans cette liste : il
> n'est **pas provisionné automatiquement** sur un nouveau projet — il doit
> être créé à la main sur le dépôt GitHub avant de pouvoir l'utiliser.

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
projet (échec marqué `needs-human`).

**Mode écriture (`mode_write`)** — CCL peut modifier des fichiers, exécuter
des commandes, faire des commits git. Garde-fous automatiques :
- Backup pinné **avant** toute modification (via `CMD_BACKUP` du `.conf`)
- **JAMAIS `git push`** — Alain pousse lui-même après vérification
- Aucune commande destructrice sans demande explicite
- Périmètre strict : CCL ne travaille que dans le dossier configuré

> `configs/*.conf` reste interdit à l'écriture **quel que soit le mode**
> (lecture active comme écriture) — garde-fou technique, voir §11.

---

## 6. Champs spéciaux dans le corps de l'issue

Le watcher lit ces champs dans le tableau markdown de l'en-tête :

| Champ | Valeur | Effet |
|-------|--------|-------|
| `MODE` | `lecture`, `lecture active` ou `écriture` | Défaut `lecture` si absent/non reconnu. Voir §5 pour le comportement de chaque mode. |
| `PRIORITE` | `haute` ou `critique` | Retry infini (au lieu de 3 max) |
| `TIMEOUT` | ex. `600s` | Surcharge le timeout par défaut (300s) |
| `MODELE` | une des valeurs reconnues (`app/projets.py`) : `claude-sonnet-5`, `claude-opus-4-8`, `claude-haiku-4-5`, `claude-fable-5` | Force un modèle CCL spécifique pour cette issue |
| `PROJET` | ex. `bridge_agent` | Détection d'incohérence par `new_issue.py`. Claude Chat doit l'inclure dans toutes les issues qu'il génère, avec le nom exact du projet cible. |
| `TYPE` | `chef` ou `ouvrier` | Identifie le rôle de l'issue dans le pattern multi-agent (voir §14). `chef` = orchestre les ouvriers. `ouvrier` = sous-tâche créée par le chef. Absent = issue normale. |
| `SUITE_DE` | ex. `#5` | Indique que cette issue fait suite à l'issue #N — préfixer alors aussi le titre par `Suite #N : `. Absent = issue inédite. |
| `RELANCE` | ex. `#612` | **Spécifique à `issues_inbox/`**, voir §3.14 — détourne le fichier déposé vers la correction/relance de l'issue #N déjà ouverte plutôt que de créer une nouvelle issue. |
| `REDACTEUR` | ex. `bridge_agent` | **Spécifique à `issues_inbox/`**, voir §3.4 pour la règle complète — nom du projet depuis le contexte duquel Claude Chat a rédigé l'issue, validé pour cohérence avec `PROJET`. |
| `COMPLEXITE` | `rapide` / `court` / `normal` / `lourd` | 4e dimension de la calibration automatique du TIMEOUT (voir §19), estimée par Claude Chat au moment de rédiger l'issue. Absent ou non reconnu = `normal`. |
| `RESEAU` | `oui` ou `non` | Tag réseau pour la calibration TIMEOUT (voir §19) : `oui` = issue impliquant de lourdes opérations réseau, `non` = purement locale. Optionnel. |

Format dans le corps :
```markdown
| PRIORITE | haute |
| TIMEOUT  | 600s  |
| MODELE   | claude-opus-4-8 |
| PROJET   | bridge_agent |
```

> ⚠️ **Claude Chat doit toujours inclure** `| PROJET | <nom> |` dans l'en-tête
> des issues qu'il génère, avec le nom exact du projet cible
> (`bridge_agent`, `alchess`, `ff_galerie`).

> ℹ️ Le champ `| LABELS | … |` n'est **pas** lu par le watcher `issues_inbox` :
> il est consommé par `new_issue.py` (formulaire web) pour ajouter des
> labels supplémentaires à ceux posés d'office.

`TYPE` ne documente que les valeurs `chef`/`ouvrier` — les valeurs `spec_*`
rencontrées par ailleurs sont des reliquats d'un ancien pattern, traités à
part.

---

## 7. Périmètre par projet

CCL est contraint à un répertoire précis par projet — il refuse de travailler
hors périmètre même si l'issue le demande explicitement :

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
<!-- FIN:TABLEAU_PERIMETRE_PROJETS -->

---

## 8. Sécurité

Seul un auteur autorisé (`AUTEURS_AUTORISES` dans `watcher.py`, contient au
minimum `AlainDelree`) peut faire traiter une issue — quel que soit le
label posé dessus. Une issue par ailleurs éligible (bons labels) mais
d'auteur non autorisé est ignorée, quel que soit le mode (lecture,
écriture, bootstrap CCW).

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

**Convention `CHANGELOG.md` (issue #252, élargie par #253)** : l'historique
complet du projet, une section par issue, la plus récente en premier
(titres `## <date> — issue #N`), vit dans `CHANGELOG.md` à la racine —
pas dans ce document. **Toute issue qui modifie le dépôt** — code, CSS,
consignes, tests, documentation, quel que soit le fichier touché, pas
seulement celles qui modifient cette doc — doit ajouter sa propre entrée
en tête de `CHANGELOG.md` dans la même opération (contenu repris tel quel
de son propre rapport, pas un résumé). Restriction initiale (« qui
modifie cette doc ») abandonnée par #253 : elle recréait, sous une autre
forme, le trou que #240 avait dû combler à la main (issues #237/#238/#239,
du code sans modification de doc, restées sans trace plusieurs jours) —
premier cas depuis #252 : #250 (correctif de contraste CSS pur), rattrapé
rétroactivement par #253.

Le pied de page de ce fichier (paragraphe « Dernière mise à jour : ... »)
continue, lui, de ne garder que les **trois entrées les plus récentes**
— mais uniquement parmi les issues qui modifient **cette doc elle-même**
(`BRIDGE_AGENT_DOC.md`), pas l'ensemble de `CHANGELOG.md` — suivies d'un
renvoi vers `CHANGELOG.md`. Toute issue qui modifie cette doc doit, dans
la même opération, en plus du point ci-dessus :
1. Faire glisser les trois entrées du pied de page d'un cran : la
   nouvelle entrée prend la première place, l'ancienne 3ᵉ sort du pied de
   page (elle reste disponible dans `CHANGELOG.md`, elle y est déjà) ;
2. Conserver impérativement le format de la toute première ligne du pied
   de page — `*Dernière mise à jour : <date> — ...*`, tiret cadratin
   juste après la date — car `nouveau_projet.py` en dépend par regex pour
   mettre à jour la date automatiquement.
3. Ce format n'apparaît qu'à la **toute dernière ligne du fichier** : une
   recherche sur « Dernière mise à jour » remonte d'abord cet exemple-ci,
   dans ce §10 — pas le vrai pied de page, bien plus bas. Toujours viser la
   fin du fichier, jamais la première occurrence trouvée (piège qui a
   corrompu ce paragraphe et raté la mise à jour du vrai pied de page lors
   de l'issue #263, cf. issue #268).

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
  `EF BB BF`) : Windows PowerShell 5.1 — celui embarqué dans les VM CCW —
  interprète sinon un fichier UTF-8 sans BOM comme de l'ANSI (Windows-1252),
  et le script plante au parsing dès la première exécution. `autounattend.xml`
  n'est **pas** concerné (lu par le parseur XML de l'installateur Windows, pas
  par PowerShell).
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
  distinct que possible des autres issues `mode_write` en cours. Détail du
  mécanisme et du workflow de fusion : voir [`WORKTREES.md`](WORKTREES.md).

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
`TOPIC_NTFY`, `FICHIER_CONTEXTE`, etc.) peuvent se faire directement via
l'onglet Configuration de new_issue.py, ou à la main par Alain — elles
ne touchent pas au code et sont gitignorées. **Cette exception vaut
uniquement pour Alain** : CCL/CCW ne modifie **jamais** `configs/*.conf`
via une issue, même en mode_write (ou en lecture active, mode_scratch,
depuis #327) et même si l'issue le demande explicitement en toutes
lettres (issue #318, suite au diagnostic #298 — ce champ texte simple
n'avait aucun garde-fou contre un élargissement ou un rétrécissement
silencieux du PÉRIMÈTRE). La règle est injectée à CCL/CCW via
`consignes/globales.md`, et doublée d'un garde-fou technique dans
`watcher.py` (`_empreinte_configs` / `_restaurer_configs_modifies`) :
toute modification de `configs/*.conf` survenue malgré tout au cours
d'un traitement en écriture ou en lecture active est détectée
(comparaison du contenu avant/après chaque tentative) et annulée
automatiquement, avec un WARNING journalisé, sans faire échouer le reste
du traitement de l'issue (mécanisme technique détaillé dans
`ARCHITECTURE.md`, y compris les actions légitimes d'Alain sur `configs/`
pendant qu'une issue tourne sur un autre projet, issue #724).

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

## 13. Commandes utiles

**Gestion de projet en ligne de commande** (équivalents aux boutons web
« + Nouveau projet » / « 🗑 Supprimer ce projet… ») :

```bash
python3 nouveau_projet.py
python3 supprimer_projet.py <nom>
python3 supprimer_projet.py <nom> --dry-run   # aperçu sans rien toucher au disque
```

`creer_projet()`/`supprimer_projet()` (orchestrateurs partagés par le script
CLI et les routes web) committent **et poussent automatiquement** la mise à
jour de `BRIDGE_AGENT_DOC.md` (§2 Projets actifs, §7 Périmètre, date en bas —
issue #645) dans le dépôt Bridge_Agent. La suppression de projet ne couvre
que le côté CCL/local (répertoire de travail, `configs/<nom>.conf`, doc) —
dépôt GitHub, labels et côté CCW restent hors scope, à traiter par une issue
dédiée (issue #587). Détail de l'orchestration : voir `ARCHITECTURE.md`.

### Parallélisation mode_write via git worktrees (issue #337)

Les issues `mode_write` tournent chacune dans un `git worktree` isolé ; Alain
fusionne les branches à la main une fois le travail relu. Une `RELANCE`
reprend le worktree déjà existant plutôt que d'en recréer un neuf (issue
#725). Les issues `mode_lecture`/`mode_scratch` restent, elles, toujours
traitées une à la fois dans le répertoire principal (`REP_TRAVAIL`). Détail
complet du mécanisme et des procédures de récupération : voir
[`WORKTREES.md`](WORKTREES.md).

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
- L'exemple validé plus bas dans cette section (dictionnaire déposé côté
  Linux puis rebuild côté Windows) est justement un cas où le chef EST
  justifié — la règle ci-dessus ne le contredit pas.
- **⚠️ Contrepartie opérationnelle** : le rallumage automatique du watcher à
  la création d'une issue `for-linux` ne s'applique PAS aux issues
  `for-windows`. Avant d'envoyer une issue `for-windows` directe, vérifier
  dans l'onglet CCW (§16) que le PC fixe est joignable et que le service
  `CCW-Watcher` est démarré ; sinon l'issue restera ouverte sans aucun
  signal. (Ne pas confondre avec les services `CCW-Watcher-<Projet>` du
  modèle multi-projets — actif, voir §16 : ceux-là surveillent les issues
  du dépôt du projet cible directement, pas les issues `for-windows` de
  Bridge_Agent.)

**Ce n'est pas déclenché automatiquement par `watcher.py`** : le chef agit
sur instruction explicite de l'issue qui le mandate (pas de détection auto
du rôle chef).

**⚠️ Contrainte d'exécution synchrone (rappel)** : le chef doit accomplir la
TOTALITÉ de sa tâche — y compris l'attente de fermeture des ouvriers et la
synthèse finale — en une seule exécution synchrone et bloquante. Il n'existe
aucune reprise possible après qu'une issue a été répondue/fermée : ce qui est
proscrit, c'est de CONCLURE son tour de parole avant la fin réelle et
vérifiée de l'opération — pas l'arrière-plan en tant que technique, qui reste
permis à condition d'interroger sa sortie en boucle DANS la même exécution.
Restent interdits, sans changement : un « monitor », une notification, un
rappel programmé, et toute formulation du type « je répondrai plus tard ».
Si une attente est nécessaire, boucler (`sleep` + `gh issue view`) DANS la
même exécution.

> **Injection automatique (issues #209, #243).** Ce rappel n'est plus à
> recopier manuellement dans le corps d'une issue. Depuis #243, la contrainte
> d'exécution synchrone est **universelle** — injectée automatiquement dans
> TOUTE issue via `consignes/globales.md` (§12.1), pas seulement celles de
> TYPE `chef` : le mode de défaillance qu'elle prévient (sortir sur une
> promesse de suivi, un « monitor » ou un rappel programmé) guette toute
> tâche dont une étape dépasse le timeout d'un appel d'outil — ex. les builds
> #241/#242, clôturés `done` avec un rapport annonçant attendre une
> notification alors que le build avait réellement abouti. `consignes/
> type_chef.md` n'ajoute plus que la spécificité chef : boucler (`sleep` +
> `gh issue view`) DANS la même exécution en attendant la fermeture des
> issues ouvrières, puis poster la synthèse finale. Le texte ci-dessus reste
> dans cette section comme référence documentaire.

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

**Exemple validé (build Scrabble, ouvrier CCW) :** un build `.exe` nécessite
qu'un dictionnaire soit déposé avant le rebuild. Le chef CCL dépose le
dictionnaire côté Linux, puis crée l'ouvrier CCW pour le rebuild :

```bash
gh issue create --repo AlainDelree/Bridge_Agent \
  --label "bridge,for-windows,mode_write" \
  --title "Ouvrier 1 : rebuild Scrabble .exe après dépôt du dictionnaire" \
  --body "…"
```

Le chef attend la fermeture de l'issue ouvrière avant de livrer sa réponse
finale.

---

## 16. Agent Windows CCW

**But.** Agent Claude Code sur un PC fixe Windows dédié, pour les issues
`for-windows` — principalement les builds `.exe` (PyInstaller) qui exigent
Windows natif. **CCW ne pousse jamais** (même règle que CCL) : il committe
localement, Alain vérifie et pousse.

La plupart des projets ont leur propre service CCW dédié (`REDACTEUR` =
`PROJET`, règle normale, §3.4). Pour un besoin CCW exceptionnel sur un
projet sans service dédié, `| LABELS | for-windows |` avec
`| REDACTEUR | bridge_agent |` route l'issue vers le service central de
Bridge_Agent (détail complet : §3.4) — indiquer alors aussi `SOUS_DOSSIER`,
ce service central travaillant dans un dossier partagé entre projets.

**Champs d'en-tête utiles à une issue `for-windows`** : `SOUS_DOSSIER`
(chemin RELATIF sous le dossier partagé, pour cibler un sous-projet précis
sans que `claude` démarre avec un cwd divergent du dossier visé par une
commande git) ; `REPO_CIBLE` (chemin ABSOLU, réservé aux projets à
périmètre dynamique, issue #125) ; `CREATION` (déclenche le bootstrap
automatique d'un nouveau service CCW dédié de bout en bout — généré
uniquement par le formulaire web, case « Projet CCW », jamais à produire à
la main).

**Build : copie locale avant partage.** Un build lancé directement sur le
dossier réseau partagé peut produire des fichiers corrompus — copier
d'abord les sources en local sur le PC Windows, builder entièrement là,
puis ne recopier que l'artefact final vers le partage. Détails et
checklist par projet : `BUILD_WINDOWS_CCW.md`.

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

Toujours fixer un `TIMEOUT` dans l'en-tête d'une issue (défaut silencieux
de 300s si absent, §6). La valeur `TIMEOUT_suggéré` affichée à la fin du
commentaire de clôture d'une issue est calculée depuis l'historique réel
des durées, bornée entre un plancher et un **plafond de 3600s** (issue
#590). C'est une **indication, pas une règle** : elle peut être trop haute
(gonflée après des dépassements répétés) comme trop basse — la confronter
à la durée réelle et à la complexité de l'issue avant de l'appliquer
telle quelle.

`RELANCE` (§3.14) corrige la valeur d'une ligne d'en-tête déjà présente
(`TIMEOUT`, `MODELE`, `SOUS_DOSSIER`, `REPO_CIBLE`) mais n'en ajoute
jamais : si l'issue d'origine n'avait pas de ligne `TIMEOUT`, la relance ne
change rien — fermer l'issue et en déposer une nouvelle avec un `TIMEOUT`.

Voir §6 pour les champs `COMPLEXITE` et `RESEAU`, qui affinent cette
calibration (constantes actuelles du code : `K_VARIABILITE` = 3, issue
#475).

---

*Dernière mise à jour : 9 octobre 2026 — nettoyage de la documentation pour
Claude Chat (issue #736, 3/3).*

Historique complet : voir [`CHANGELOG.md`](CHANGELOG.md).
