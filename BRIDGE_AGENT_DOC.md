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
| `annuairetoken` | AlainDelree/Annuairetoken | ~/Annuairetoken | (conf local) | `#FFE4CC` |
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
web** (§20) : la méthode normale consiste à déposer un fichier `.txt` dans
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
| `SUITE_DE` | ex. `#5` | Indique que cette issue fait suite à l'issue #N. Absent = issue inédite. |
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
> il est consommé par `new_issue.py` (formulaire web, §20) pour ajouter des
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
| `annuairetoken` | /home/alain/Annuairetoken |
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

```
~/Bridge_Agent/
  watcher.py          — watcher générique (prend --config)
  new_issue.py        — point d'entrée de l'interface web Flask (~150 lignes)
  app/                — package modulaire de l'interface web
    auth.py           — authentification (login, mot de passe hashé)
    projets.py        — gestion des projets et de leur configuration
    watchers.py       — pilotage des watcher (start/stop/état)
    issues.py         — création et suivi des issues GitHub
    journal.py        — lecture des journaux de log
    cycle_vie.py      — cycle de vie de l'application
    tunnel.py         — tunnel Cloudflare (mode externe)
    vues.py           — routes Flask et rendu des pages
    etat.py           — état partagé de l'application
    issues_inbox.py   — état de l'onglet « Résultats inbox » (§3, issue #483)
  templates/          — gabarits HTML (Jinja2)
  static/             — CSS, JS, assets statiques
  issues_inbox/       — gitignoré : dépôt de fichiers .txt d'issues à créer (§3)
    rejected/         — issues malformées, à corriger manuellement (§3)
  consignes/          — consignes injectées dans le prompt CCL par watcher.py (§12.1)
    globales.md       — NON-optionnel : rappels de sécurité, TOUTE issue
    type_chef.md      — optionnel : consignes du TYPE « chef »
    (type_<type>.md et projet_<projet>.md créés à la demande, facultatifs)
  CHANGELOG.md        — historique complet du projet, une entrée par issue
                        (convention détaillée ci-dessous)
  configs/            — gitignoré : un .conf par projet
    bridge_agent.conf
    alchess.conf
    ff_galerie.conf
  logs/               — journaux par projet (rotation par taille, archives datées)
    watcher-bridge_agent.log
    watcher-alchess.log
    watcher-ff_galerie.log
  ssl/                — gitignoré : certificat auto-signé
  venv/               — gitignoré : environnement Python
```

Pour le détail de l'architecture technique interne, voir `ARCHITECTURE.md`.

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
  web `new_issue.py` (voir §20 pour les usages restants, légitimes mais
  distincts, de ce formulaire). **Si aucun outil fichier (`bash`,
  `create_file`, etc.) n'est disponible dans la conversation en cours** —
  donc impossible de produire ce `.txt` — Claude Chat ne bascule **jamais**
  silencieusement vers le formulaire web comme repli de sa propre
  initiative, même en s'appuyant sur son statut de méthode de backup légitime
  (§20) pour se justifier : il le signale explicitement à Alain (« je n'ai
  pas d'outil fichier dans cette conversation ») et lui demande comment
  procéder (issue #685, suite à un cas constaté sur le projet Rummikub où
  l'ambiguïté entre §11 et §20 a conduit à présenter le texte en clair de
  bonne foi).
- **Mode par défaut** : lecture seule. N'armer `mode_write` que si la tâche
  demande explicitement une modification de fichier.
- **Scripts PowerShell (`.ps1`) : BOM UTF-8 obligatoire dès la création.**
  Tout fichier `.ps1` du projet contenant des caractères accentués (donc
  quasiment tous, vu la langue française) **doit** commencer par un BOM UTF-8
  (octets `EF BB BF`). Windows PowerShell 5.1 — celui embarqué dans les VM CCW —
  interprète sinon un fichier UTF-8 sans BOM comme de l'ANSI (Windows-1252) :
  les accents sont mal décodés et le script plante au parsing avec des erreurs
  `UnexpectedToken` **en cascade** (une par ligne accentuée) dès la première
  exécution. C'est la signature à reconnaître : si un `.ps1` neuf « explose »
  ainsi sur la VM, vérifier d'abord le BOM (`hexdump -C fichier.ps1 | head -1`
  doit montrer `ef bb bf` en tête). Correctif : réécriture binaire ajoutant les
  3 octets en tête, avec garde-fou anti-double-BOM (ne rien faire si le fichier
  commence déjà par `EF BB BF`). Historique : correctif ponctuel sur
  `provisionner.ps1` (#151), récidive sur `ajouter_projet_ccw.ps1` et
  `mettre_a_jour_tokens_ccw.ps1` faute de règle établie (#172) → règle
  généralisée ici. `autounattend.xml` n'est **pas** concerné (lu par le parseur
  XML de l'installateur Windows, pas par PowerShell).
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
  utilisant Bridge_Agent)** : depuis #337, plusieurs issues `mode_write` d'un
  même projet peuvent tourner **en parallèle**, chacune dans son propre
  `git worktree`. Deux issues touchant les mêmes fichiers ou les mêmes zones
  de code peuvent donc générer un conflit de merge à résoudre manuellement.
  **Recommandation** : scoper chaque issue sur un périmètre de fichiers aussi
  distinct que possible des autres issues `mode_write` en cours.
- **Workflow de vérification/push après des issues `mode_write` parallèles**
  (issue #342) : en plus de la relecture habituelle des commits avant push,
  Alain doit désormais :
  1. Vérifier `git worktree list` pour repérer les worktrees prêts à être
     mergés.
  2. Lancer `python3 scripts/fusionner_changelog.py` **avant tout merge ou
     push** — intègre les `CHANGELOG-N.md` de chaque worktree dans
     `CHANGELOG.md` (lancement manuel uniquement, jamais automatique).
  3. Merger chaque branche `worktree-issue-<N>` dans `master` manuellement,
     une par une.
  4. Nettoyer : `git worktree remove <chemin>` puis
     `git branch -d worktree-issue-<N>`.
  Détail complet (procédures de récupération incluses) : voir
  [`WORKTREES.md`](WORKTREES.md).

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
2. CC génère l'issue (titre + corps avec `| PROJET | <nom> |`)
3. Alain colle dans new_issue.py et envoie
4. CCL exécute, committe, ne pousse pas
5. Alain vérifie (`git show`) et pousse

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
du traitement de l'issue.

**Actions légitimes d'Alain pendant une issue en cours — issue #724.**
`configs/` est **commun à tous les projets** (un seul dossier, partagé par
tous les watchers) : avant #724, le garde-fou ci-dessus traitait à tort
comme une violation tout geste volontaire d'Alain qui y écrit PENDANT
qu'une issue mode_write (ou lecture active) tourne dans un **autre**
projet — création de projet (`nouveau_projet.ecrire_conf`), suppression de
projet (`supprimer_projet._supprimer_conf`) et enregistrement de l'onglet
Configuration (`app/projets.sauvegarder_conf`) étaient annulés en fin de
traitement (nouveau `.conf` supprimé, `.conf` modifié remis dans son état
d'avant, `.conf` supprimé recréé) — vécu deux fois le 06/10/2026 sur la
création du projet AnnuaireToken (issues #138 et #140). Ces trois points
appellent désormais `etat_configs_legitimes.enregistrer(nom_fichier)`
juste après leur écriture disque, qui horodate l'action dans
`logs/configs_legitimes.json` (purge automatique des entrées de plus d'une
heure, `DUREE_VALIDITE_S`). `_restaurer_configs_modifies` consulte cette
trace (`_action_legitime_posterieure`, via
`etat_configs_legitimes.instant_legitime`) avant d'agir sur chaque fichier
changé : une entrée horodatée **après** le début du traitement de l'issue
(l'instant où `_empreinte_configs` a été prise) fait passer ce changement
pour légitime — ni suppression, ni restauration, ni recréation — avec un
message **INFO** explicite dans le journal du watcher («&nbsp;reconnu comme
une création de projet légitime depuis new_issue.py&nbsp;», etc., en lieu
et place du WARNING habituel. Point important : `enregistrer()` n'est
appelée QUE par ces trois points de new_issue.py — le code de traitement
d'une issue (`watcher.py`, `lancer_claude`, `traiter_issue`) n'appelle
jamais cette fonction, seulement sa contrepartie en lecture
(`instant_legitime`) : une issue ne peut donc pas s'ajouter elle-même à
cette trace via le fonctionnement normal du bridge. Le comportement pour
un changement fait PAR une issue elle-même reste strictement inchangé :
annulé et journalisé en WARNING, comme avant #724.

### 12.1 Consignes injectées — architecture à trois couches (issues #209, #211)

Le bridge injecte automatiquement des **consignes** à trois couches dans le
**prompt donné à CCL au moment du traitement de l'issue**, exactement sur le
même modèle que le `CONTEXTE.md` par projet (`FICHIER_CONTEXTE`, cf. §7) : le
point de passage unique est `watcher.py` (`lancer_claude` →
`_consignes_injectees`), quel que soit **le chemin par lequel l'issue a été
créée**. Trois couches, de la plus générale à la plus spécifique, lues dans le
dossier `consignes/` (à la racine du dépôt, à côté du watcher, communes à tous
les projets) :

| Couche | Fichier | Portée | Optionnel ? |
|--------|---------|--------|-------------|
| **Globale** | `consignes/globales.md` | TOUTE issue, tout projet, tout TYPE | **Non** — rappels de sécurité transversaux (ne jamais pousser, backup avant modif, respect du périmètre, abandon immédiat au refus de permission / blocage sans progrès — mais PAS aux opérations longues légitimes qui progressent normalement ; contrainte d'exécution synchrone et bloquante, sans attente différée, universelle depuis #243) |
| **Type** | `consignes/type_<type>.md` | Issues d'un TYPE donné (ex. `type_chef.md`) | **Oui** — créé à la demande |
| **Projet** | `consignes/projet_<projet>.md` | Issues ciblant un projet donné | **Oui** — créé à la demande |

⚠️ **Pour un Claude en conversation** (celui qui rédige une issue avant de
l'envoyer) : ce tableau décrit une injection qui n'a lieu qu'à l'exécution
(CCL/CCW) — tu ne vois donc pas ce contenu ici. Avant de proposer une issue,
consulte `consignes/globales.md` (rappels de sécurité, garde-fous) via :
```bash
curl -sL "https://raw.githubusercontent.com/AlainDelree/Bridge_Agent/master/consignes/globales.md"
```

**Couverture universelle (issue #211).** Une issue peut naître de trois chemins :
(1) le formulaire web (`new_issue.py`), (2) un CCL « chef » via `gh issue create`
en ligne de commande (§14, pattern Chef → Ouvrier), (3) une création manuelle
directe sur GitHub (§20). En #209 les consignes étaient écrites dans le **corps**
de l'issue par `app/issues.py`, ce qui ne couvrait QUE le chemin 1 — les issues
ouvrières créées par un chef (chemin 2), justement de vraies tâches `mode_write`,
échappaient à l'injection. Depuis #211, l'injection se fait dans le **prompt CCL**
au moment du traitement : peu importe qui a créé l'issue, `watcher.py` déduit le
TYPE de son titre/corps réels et ajoute le bloc de consignes. `app/issues.py`
n'écrit **plus** les consignes dans le corps GitHub (source unique côté watcher,
plus de double injection). Conséquence assumée : comme pour `CONTEXTE.md`, les
consignes ne sont plus visibles en lisant le corps d'une issue sur GitHub.

**Emplacement dans le prompt.** Le bloc de consignes est placé **après** le bloc
`CONTEXTE DU PROJET` et **avant** la clause de périmètre et le garde-fou (mode
lecture/écriture) : choix assumé de regrouper toutes les « règles » (consignes de
sécurité globales, spécificités de type/projet, périmètre strict, garde-fou
écriture) en fin de prompt, la zone la mieux suivie par le modèle.

**Ordre interne des couches :** globales → type (si présent) → projet (si
présent). Le TYPE est déduit par `watcher.deduire_type_issue` (même logique que
partout ailleurs : champ `| TYPE | … |` du corps, sinon préfixe du titre
`Chef :`/`Ouvrier :`), donc le fichier attendu est `consignes/type_<type>.md`.
Le projet est celui piloté par le watcher courant (`CFG.nom`).

**Facultatif = par défaut absent.** Contrairement à `CONTEXTE.md` (une convention
par projet), les couches **type** et **projet** ne doivent PAS exister par défaut :
un projet sans `consignes/projet_<nom>.md` fonctionne normalement, sans rien à
créer ni à maintenir. On ne crée un fichier `type_*`/`projet_*` que si un besoin
réel apparaît. C'est un choix délibéré pour **éviter le piège de maintenance**
d'un fichier obligatoire par projet.

**Garde-fous (aucun traitement d'issue ne doit échouer à cause des consignes) :**
- fichier `type_*`/`projet_*` **absent** → comportement **normal**, aucune
  injection pour cette couche, **sans** log ni avertissement (ce n'est pas une
  anomalie) ;
- `globales.md` **introuvable** → `log.warning` clair, mais le traitement de
  l'issue se poursuit sans jamais échouer pour cette raison seule.

---

## 13. Commandes utiles

```bash
# Lancer l'interface web (local)
cd ~/Bridge_Agent && source venv/bin/activate && python3 new_issue.py

# Lancer en mode externe (tunnel Cloudflare + HTTPS + login)
python3 new_issue.py --externe

# Configurer le mot de passe
python3 new_issue.py --set-password

# Créer / installer un nouveau projet bridge (interactif, terminal)
# Équivalent web : bouton « + Nouveau projet » à côté du sélecteur de projet
# dans l'interface (mêmes étapes, compte-rendu par étape, sélecteur rafraîchi
# sans redémarrer new_issue.py). Le script CLI reste utilisable en parallèle.
python3 nouveau_projet.py

# Supprimer un projet bridge, côté CCL/local uniquement (interactif, terminal ;
# issue #587). Équivalent web : bouton « 🗑 Supprimer ce projet… » (zone
# dangereuse de l'onglet Configuration). --dry-run liste ce qui serait
# supprimé sans rien toucher. Dépôt GitHub distant et côté CCW jamais touchés.
python3 supprimer_projet.py <nom>
python3 supprimer_projet.py <nom> --dry-run

# Lancer un watcher manuellement
python3 watcher.py --config configs/bridge_agent.conf
python3 watcher.py --config configs/bridge_agent.conf --dry-run

# Voir les watcher en cours
ps aux | grep watcher

# Vérifier les commits locaux non poussés
git log --oneline origin/master..HEAD

# Mesurer la consommation du quota API GitHub (issue #263)
# échantillonne `gh api rate_limit` (REST, gratuit — ne consomme ni core ni
# graphql, vérifié empiriquement) à intervalle régulier et journalise dans
# logs/mesure_api.csv (non versionné). Arrêtable proprement par Ctrl+C.
python3 scripts/mesurer_api.py --intervalle 30 --duree 600
python3 scripts/mesurer_api.py --intervalle 15 --duree 0 --note phase_B   # illimité, Ctrl+C pour arrêter
```

**Mesurer et attribuer la consommation GraphQL (issue #263)** — méthode
reproductible :

1. **Coût unitaire par appel** : encadrer un appel isolé de deux
   `gh api rate_limit` (avant/après) et répéter 3-5 fois ; le bruit de fond
   (watchers/poller/interface tournant en parallèle) ajoute parfois +1, donc
   retenir le **delta minimal observé**, pas la moyenne. Résultats mesurés le
   28/07/2026 : `gh issue list --json ...` (celui du polling) = **1 point**,
   `gh issue view --json comments` = **2**, `gh issue comment` = **2**,
   `gh issue edit --add-label` = **3**, `gh issue close` = **2** (plancher,
   variance 2-4 selon contamination par le bruit de fond), `gh issue create`
   = **3** (plancher, mesure annexe).
2. **Attribution par composant** : lancer `mesurer_api.py --note <phase>` en
   continu (append dans le même CSV) pendant qu'on fait varier ce qui tourne
   (watchers `--dry-run` sur un projet sans issue en attente = polling sans
   risque d'exécution réelle, `kill <pid>` pour arrêter), puis calculer le
   taux horaire par phase à partir des horodatages. **Limite connue** : le
   watcher CCL qui traite l'issue de mesure elle-même, et `new_issue.py` dont
   il dépend, ne peuvent pas être arrêtés depuis CCL sans interrompre
   l'exécution en cours — la phase « tout arrêté » ne peut être qu'estimée
   par calcul (coût unitaire × fréquence de polling), jamais mesurée en
   conditions réelles depuis CCL. Le watcher CCW de la VM a la même
   limite, pour la même raison (inaccessible depuis le ThinkPad).
3. Détail des résultats et le classement des leviers correctifs : rapport de
   l'issue #263 (commentaire de clôture GitHub, non dupliqué ici).

**Étapes réellement effectuées par `nouveau_projet.py`/le bouton web** (issues
#98/#99, complété par #257) — le même orchestrateur `creer_projet()` couvre les
deux, mêmes étapes, mêmes messages, comportement idempotent identique :

1. **Dépôt GitHub** : `gh repo view` ; s'il n'existe pas encore, `gh repo create
   <owner>/<Nom> --public` ou `--private` selon le choix fait à la création
   (issue #528 ; défaut **public**, cohérent avec le comportement historique —
   CLI : question « Dépôt public (non = privé) » juste après la confirmation
   de création ; web : case à cocher « Dépôt public », visible seulement
   quand le dépôt n'existe pas encore). Sans effet si le dépôt existe déjà —
   sa visibilité n'est pas modifiée. Un dépôt privé fonctionne à l'identique
   côté Bridge_Agent : l'interface (affichage des résultats, création
   d'issues, `app/issues.py`) passe systématiquement par `gh` authentifié via
   `GH_TOKEN`, jamais par un accès public anonyme — seule condition, que ce
   token ait les permissions nécessaires sur ce dépôt (sinon `gh repo create
   --private` échoue immédiatement à l'étape 1, ou tout appel `gh`/`git`
   ultérieur échoue avec une erreur d'authentification explicite). Si
   décoché côté web (`creer_depot_si_absent`), la création est sautée
   entièrement — auquel cas le choix public/privé est sans objet. S'il
   existe déjà → installation dessus, rien recréé.
2. **`configs/<nom>.conf`** généré depuis le gabarit interne (dépôt, répertoire
   de travail, périmètre, topic ntfy, couleur d'accent — voir « Couleur
   d'accent des projets » ci-dessous, issues #120/#121/#534/#535 —, etc.).
   Cette écriture est aussi tracée dans `etat_configs_legitimes` (issue
   #724, §12 — même mécanisme pour la suppression de projet et
   l'enregistrement de l'onglet Configuration) : si une issue mode_write
   tourne en ce moment dans un **autre** projet, le garde-fou technique
   `configs/*.conf` (§12/#318) reconnaît ce nouveau `.conf` comme légitime
   et ne le supprime plus à la fin de ce traitement.
3. **Labels GitHub** requis (§4) créés sur le dépôt cible, idempotent (les
   présents sont laissés intacts).
4. **Fichier(s) de contexte** : `CONTEXTE.md` (+ les 3 fichiers Specs MVC si
   demandé) créés **vides** dans le répertoire de travail, qui est créé au
   besoin.
5. **Dépôt git local du répertoire de travail** (issue #257, garde-fous
   complétés #258) : si déjà un dépôt git (cas de tous les projets installés
   jusqu'ici), rien n'est fait. Sinon — répertoire non versionné — `git init`
   sur la branche `master`, `git remote add origin` en **HTTPS**
   (`https://github.com/<owner>/<repo>.git`, jamais SSH), `.gitignore`
   minimal s'il est absent, commit initial. Sans cette étape le projet livré
   était inutilisable : ni `git pull --ff-only` (début de cycle du watcher)
   ni le commit de sauvegarde obligatoire en mode écriture ne peuvent
   s'exécuter sur un répertoire non versionné. Chaque appel git est borné
   par un **timeout** (15s pour les opérations locales, 60s pour le push —
   issue #258) : un dépassement est traité comme un échec normal de l'étape,
   jamais comme une exception qui remonterait et ferait échouer la création.

   **Push automatique — mais seulement si le répertoire était réellement
   vide.** Ce push est une **exception documentée** à la règle « Alain
   pousse lui-même » (voir §18.2, même raisonnement que la route pièces
   jointes) : c'est Alain qui déclenche la création de projet, jamais un
   agent. Un échec du push (réseau, droits, timeout) ne fait pas échouer la
   création : le commit reste local, le compte-rendu indique la commande
   manuelle à relancer (`git push -u origin master`).

   **Garde-fou supplémentaire (issue #258, affiné #260)** : ce raisonnement
   ne couvre que le dépôt **distant**, tout juste créé — il ne dit rien du
   contenu **local** du répertoire. Or ce script gère explicitement le cas
   d'un `REP_TRAVAIL` **préexistant et non versionné** : après `git init`,
   remote et écriture du `.gitignore` minimal, `git add -A` est exécuté,
   puis ce que git a **réellement indexé** (`git diff --cached --name-only`)
   est comparé aux seuls fichiers que le script vient lui-même de créer
   (`CONTEXTE.md`, fichiers Specs, `.gitignore`) — la détection porte sur ce
   que git **suivrait**, pas sur un simple inventaire du disque : un `venv/`
   ou `__pycache__/` préexistant, exclu par ce `.gitignore`, n'atteint
   jamais l'index et ne compte donc pas comme contenu préexistant (issue
   #260 — l'ancienne détection, faite par inventaire brut du répertoire
   avant même l'écriture du `.gitignore`, remontait à tort ce genre de
   contenu jamais destiné à être commité, sur le cas pourtant le plus
   fréquent d'un `REP_TRAVAIL` préexistant : un projet Python déjà entamé).
   S'il ne reste rien d'autre → comportement ci-dessus, push automatique.
   S'il reste d'autres fichiers **suivis** → **le push n'est PAS
   déclenché** : `git init`, le remote, le `.gitignore` et le commit
   initial sont faits normalement, mais le push est laissé à Alain après
   relecture (le dépôt étant **public**, ce contenu ne doit pas être publié
   sans vérification). Le compte-rendu (CLI et web) liste alors les
   fichiers préexistants détectés (tronquée à une dizaine) et la commande
   manuelle à lancer une fois la relecture faite.
6. **`BRIDGE_AGENT_DOC.md`** (§2 Projets actifs, §7 Périmètre, date en bas)
   mis à jour **localement** — jamais poussé automatiquement : reste à
   committer/pousser à la main (dépôt Bridge_Agent, distinct du projet créé).

**Reste à faire manuellement dans tous les cas** : rédiger `CONTEXTE.md`
(créé vide — c'est lui qui est injecté dans chaque prompt CCL, plafonné à
4000 caractères), lancer le watcher (`python3 watcher.py --config
configs/<nom>.conf`), et committer/pousser les changements du dépôt
Bridge_Agent lui-même (`configs/`, doc) — bien distinct du dépôt du projet
créé, dont le push initial est géré par l'étape 5 ci-dessus.

### Suppression de projet, côté CCL/local (issue #587)

Diagnostic #580 (fonctionnel) : la création écrit 12 traces persistantes
réparties CCL/GitHub/CCW (étapes ci-dessus) sans qu'aucun flux ne sache les
démonter — décommissionner un projet exigeait jusqu'ici une chirurgie
manuelle sur au moins 8 cibles, avec un risque réel d'oubli. Sur le modèle
déjà utilisé pour la création (chantier scindé en plusieurs issues
coordonnées CCL/CCW), cette issue couvre volontairement **uniquement le
côté CCL/local** — symétrique de `nouveau_projet.py` ci-dessus, mais dans
l'autre sens. Le côté CCW et la suppression du dépôt GitHub font l'objet
d'issues séparées.

`supprimer_projet.py` (script CLI) / `app/supprimer_projet.py` (routes web,
qui réutilisent le script SANS le dupliquer — même relation que
`nouveau_projet.py`/`app/nouveau_projet.py`) démontent, dans cet ordre :

1. **Répertoire de travail** du projet (contenu, `CONTEXTE.md`/specs) **et**
   dépôt git local en une seule opération de disque (`.git` vit dans ce même
   répertoire — voir l'étape 5 de la création ci-dessus) : `shutil.rmtree()`
   du `REP_TRAVAIL` lu dans le `.conf`. Idempotent : un répertoire déjà
   absent n'est pas une erreur.
2. **`configs/<nom>.conf`**.
3. **`BRIDGE_AGENT_DOC.md`** (§2 Projets actifs, §7 Périmètre, date en bas) —
   régénéré immédiatement via `regenerer_tableaux_projets.regenerer()` (même
   mécanisme que l'étape 6 de la création), **pas** en attendant un lancement
   manuel comme c'était le cas jusqu'ici. Mis à jour **localement** — comme
   pour la création, jamais poussé automatiquement.

**Ordre volontairement inverse de la création** : le répertoire de travail
est retiré **en premier**, tant que `configs/<nom>.conf` existe encore pour
attester du projet. Si cette étape échoue (droits, disque), le `.conf` est
conservé et les étapes suivantes ne sont **pas** tentées — pas de
continuation aveugle après un échec. L'inverse (`.conf` supprimé en premier)
risquerait un répertoire orphelin sur disque sans plus aucune trace de son
existence en cas d'échec sur l'étape suivante. Pour la même raison, la
régénération de la doc — qui relit `configs/*.conf` — vient en dernier,
une fois le `.conf` réellement retiré du disque (sans quoi le projet
réapparaîtrait dans §2/§7).

**Explicitement hors scope** (décision actée dans le diagnostic #580) :
suppression du dépôt GitHub et de ses labels — geste destructeur
volontairement laissé manuel — et tout le côté CCW (clone Windows,
`configs\<nom>-ccw.conf`, service NSSM, tokens `AppEnvironmentExtra`/
`TOPIC_NTFY`, entrée `$Projets`, ligne `REINSTALLATION_CCW.md` §7), qui fera
l'objet d'une issue CCW dédiée.

**Mode à blanc (dry-run)** : `previsualiser_suppression(nom)` /
`supprimer_projet(nom, dry_run=True)` décrivent les 3 cibles (dépôt GitHub —
conservé, chemin du répertoire de travail avec son nombre d'éléments et la
présence ou non d'un dépôt git local, aperçu tronqué du contenu) **sans
toucher au disque ni à `BRIDGE_AGENT_DOC.md`**. Côté web, `GET
/supprimer-projet/verifier/<nom>` alimente automatiquement l'aperçu affiché
dans le modal, avant même que la checklist de confirmation ne soit
proposée.

**Route web `POST /supprimer-projet`** (protégée par `login_requis`, comme
le reste de l'application) : appelée depuis le bouton « 🗑 Supprimer ce
projet… » (zone dangereuse de l'onglet Configuration). Double garde-fou
avant toute action destructive, cohérent avec la sensibilité du geste :

1. **Côté interface** — 3 cases à cocher (une par cible démontée) **et** le
   nom du projet retapé à l'identique dans un champ de confirmation ; le
   bouton « Supprimer définitivement » reste désactivé tant que ces 4
   conditions ne sont pas toutes réunies.
2. **Côté serveur** — le champ `confirmation` du corps JSON doit reproduire
   exactement le nom du projet (`nom`), indépendamment des cases cochées
   côté navigateur : la checklist d'interface peut être contournée par un
   appel direct à la route, cette vérification-là ne peut pas l'être. Sans
   correspondance → 400, aucune suppression tentée.

**Reste à faire manuellement dans tous les cas** : dépôt GitHub + labels
(hors scope, cf. issue #587), et committer/pousser les changements du dépôt
Bridge_Agent lui-même (`configs/`, doc) — le script/la route ne poussent
jamais, comme pour la création.

**Étape 4 ajoutée par l'issue #629** : voir « État serveur des cases
cochées » ci-dessous — la suppression retire aussi toutes les coches du
projet, best-effort (un échec ici ne remet pas en cause les étapes
précédentes déjà réalisées avec succès).

### État serveur des cases cochées « traité/lu », backend (issue #629, étape 5a)

Refonte de l'interface web par étapes (§6 d'`ARCHITECTURE.md`). Jusqu'ici, la
case « traité/lu » de chaque ligne de l'onglet Résultats
(`static/js/app.js::basculerCocheResultat`, clé localStorage
`resultat-coche:<projet>:<numero>`, issue #154) vivait **uniquement** dans le
localStorage du navigateur : état perdu après un plantage du PC, différent
selon l'adresse d'accès (localhost vs LAN), clés accumulées sans fin.
Décision d'Alain : cet état passe côté serveur. **Cette issue ne livre que
le backend** — aucun front ne l'utilise encore, aucun changement visible ;
la reprise du localStorage existant (via la route d'import ci-dessous)
viendra à l'étape 5b.

**Stockage** (`etat_cases_cochees.py`, racine) — même modèle que
`etat_rate_limit.py` (issue #615) : petit fichier JSON
(`logs/etat_cases_cochees.json`), écriture atomique (fichier temporaire +
`os.replace`) protégée par un verrou anti-collision (`.lock`, essais avec
attente courte). Format : `{"<nom_projet>": [<numero>, ...], ...}`.

**Routes web** (`app/cases_cochees.py`), toutes protégées par
`login_requis` comme le reste de l'interface :

| Méthode | Route | Effet |
|---------|-------|-------|
| `GET` | `/cases-cochees/<nom_projet>` | Liste triée des numéros cochés pour ce projet : `{"numeros": [...]}`. |
| `POST` | `/cases-cochees/<nom_projet>/<numero>` | Coche cette issue (idempotent). Réponse : `{"succes": true, "numeros": [...]}`. |
| `DELETE` | `/cases-cochees/<nom_projet>/<numero>` | Décoche cette issue (idempotent). Même forme de réponse. |
| `POST` | `/cases-cochees/importer` | Import en masse, **idempotent** — corps JSON `{"cases": [{"projet": ..., "numero": ...}, ...]}`, potentiellement plusieurs projets à la fois (le localStorage du navigateur n'est pas scindé par projet). Servira à la reprise de l'existant en 5b ; les entrées mal formées sont ignorées silencieusement. Réponse : `{"succes": true, "nb_ajoutees": N}`. |

**Décoche après une relance, deux chemins, un seul cœur partagé (issues
#720, #721).** `app/cases_cochees.py::decocher_et_diffuser(projet, numero)`
porte la logique réelle : décoche via `etat_cases_cochees.decocher_issue`
(même fonction idempotente que la route `DELETE` ci-dessus) puis diffuse
l'événement SSE `case_decochee` (§3.15) à tous les onglets Résultats déjà
ouverts. Deux appelants, tous deux dans le process `new_issue.py` :

- une route distincte, **sans `login_requis`** — `POST
  /notifier-case-decochee` (`app/cases_cochees.py::notifier_case_decochee`)
  — appelée en best-effort par `scripts/watcher_issues_inbox.py` (process
  **séparé**, ne peut pas écrire lui-même dans
  `logs/etat_cases_cochees.json`) après chaque `RELANCE` réussie d'un fichier
  `issues_inbox/` (§3.14) : corps `{"projet", "numero"}` ;
- le bouton « 🔄 Relancer » d'une ligne Résultats (`app/interruption.py::
  route_relancer`, §13), issue #721 : **même process**, appel direct sans
  notification réseau.

**Nettoyage au démarrage de `new_issue.py`** (`nettoyer_anciennes()`,
appelé juste après le chargement du mot de passe) — **sans aucun appel
GitHub** : pour chaque projet, calcule le plus grand numéro connu **parmi
les cases cochées elles-mêmes** (seule source disponible sans requête
réseau), et retire celles dont le numéro est inférieur ou égal à (ce
maximum − 50). 50 est le plafond du réglage « limite d'issues par projet »
(`app/issues.py::LIMITE_ISSUES_MAX`) : une issue plus ancienne que cette
fenêtre ne peut structurellement plus apparaître dans la liste Résultats du
projet, donc sa coche ne sera plus jamais consultée.

**Suppression d'un projet** (flux de l'issue #587, `supprimer_projet.py`) :
une étape supplémentaire (`etat_cases_cochees.supprimer_projet(nom)`)
retire toutes les coches du projet supprimé — voir la section « Suppression
de projet » ci-dessus.

Tests : `tests/test_cases_cochees_629.py` (stockage isolé du vrai
`logs/etat_cases_cochees.json` via monkeypatch de `CHEMIN_ETAT`/
`CHEMIN_VERROU`, comme `tests/test_supprimer_projet_587.py` pour
`configs/`) — lecture/écriture, idempotence cocher/décocher/import, règle
de nettoyage, isolation entre projets, suppression de projet, routes Flask.
`tests/test_decoche_relance_720.py` couvre la route `/notifier-case-decochee`
ci-dessus avec la même isolation ; `tests/test_decoche_bouton_relancer_721.py`
couvre le second appelant (`route_relancer()`) de la même façon.

### Case « traité/lu » côté interface + copie fiable (issue #636, étape 5b)

Branche l'interface sur le backend de #629 et corrige trois défauts connus de
la case à cocher, dans le module dédié **`static/js/resultats_coches.js`**
(sorti d'`app.js` selon `ARCHITECTURE.md` §6.7 ; `app.js` ne garde que de minces
relais appelés par le markup inline des lignes).

- **État serveur.** La case ne vit plus dans le `localStorage` mais dans
  `store.casesCochees` (`{ nomProjet: [numero, …] }`), synchronisé avec le
  serveur : **un seul `GET /cases-cochees/<projet>` par projet** au chargement
  (jamais un par issue). L'état survit à un plantage du PC et est **identique
  quel que soit le navigateur ou l'adresse** (localhost / `--lan`). Relu non
  plus seulement au chargement de la page mais aussi par le ↻, la
  resynchronisation automatique #705 et le rattrapage à l'activation de
  l'onglet (issue #729, détail en §17.4) — sans quoi une décoche serveur
  manquée par l'événement `case_decochee` ci-dessous (ex. deux `RELANCE` coup
  sur coup pendant que l'onglet n'était pas affiché) laissait la case cochée
  à l'écran jusqu'à un rechargement complet de la page.
- **Migration idempotente.** Au premier chargement, les clés héritées
  `resultat-coche:<projet>:<numero>` du `localStorage` sont extraites
  (`extraireCasesLegacy`), envoyées **en une fois** à
  `POST /cases-cochees/importer`, puis retirées du `localStorage`. Rejouable
  sans dégât (import idempotent côté serveur ; clés retirées seulement après
  succès).
- **Copie fiable au cochage.** Cocher une case (ou cliquer un badge
  ✅/Diff/All) **engage la copie pendant le geste**, plus jamais après un fetch
  réseau : en **contexte sécurisé** (localhost/HTTPS) via `ClipboardItem`
  alimenté par une **promesse** (`navigator.clipboard.write` appelé au clic, le
  texte est fetché ensuite) ; en **contexte non sécurisé** (`--lan`, API
  presse-papier moderne absente) via un **préchargement** du détail+diff des
  issues visibles décochées puis `execCommand` **synchrone**. `decisionModeCopie`
  tranche entre les deux. **Feedback honnête** : jamais de ✓ sur échec (toast
  d'erreur, jamais de boîte « OK ») ; le cochage (persistance/grisage/pastilles)
  ne dépend jamais de la copie. Décocher ne copie rien. Les copies des badges
  sont **factorisées** dans le même moteur (`lancerCopie`).
- **Identité de l'issue en tête de la copie (issue #723).** Les variantes
  « réponse » (case à cocher, badge ✅) et « all » (badge All) préfixent le
  texte copié par une ligne `Issue #N — <projet> — <titre>` suivie d'une ligne
  vide — `ligneIdentite`/`texteCopieAvecIdentite`, numéro et titre venant du
  détail d'issue déjà chargé (`detailIssue`), projet venant du contexte de la
  copie. Un titre absent n'ajoute aucun « — » orphelin ; un titre multiligne
  ou très long est aplati sur une seule ligne. Sans comportement sur une issue
  pas encore répondue (texte vide → pas de ligne d'identité orpheline, pour
  que la détection « pas encore disponible » reste correcte). La variante
  « diff » (badge Diff) **reste inchangée** : diff brut, sans ligne
  d'identité. Aucun changement côté watcher ni du commentaire posté sur
  GitHub (JS seul) : le correctif s'applique donc aussi aux anciennes issues.
- **Pastilles ↔ « Cocher tout » alignés.** Choix retenu : **élargir « Cocher
  tout »** au périmètre exact des pastilles (les N premières issues par projet,
  `premieresParProjet`, sans le quota d'affichage ni le filtre ouvriers) plutôt
  que restreindre les pastilles — la pastille garde ainsi son sens (nombre réel
  d'issues à traiter par projet). Après « Cocher tout », aucune pastille des
  projets actifs ne reste.
- **Bouton « ⊘ Tout à zéro »** (à côté de « Cocher tout ») : marque comme
  cochées, côté serveur (`POST /cases-cochees/importer`), **toutes** les issues
  chargées de **tous** les projets, quel que soit le filtre. Confirmation légère
  (`toasts.confirmer`). **Aucune copie.**
- **Décoche instantanée après une RELANCE (issue #720).** `static/js/socle/
  sse.js` route l'événement `case_decochee` (§3.15) vers la tranche dédiée
  `store.derniereNotifCase` (même principe que `derniereNotifFichier`) ;
  `resultats_coches.js` s'y abonne et applique `appliquerCaseDecochee`
  (réutilise `retirerDansEtat`, idempotent) sur `store.casesCochees`, puis
  resynchronise le DOM — sans passer par `resultats.js`, la case « traité/lu »
  restant une préoccupation séparée (voir l'en-tête du module).

Tests de logique pure : `static/js/tests/resultats_coches.test.js` (fusion de
l'état serveur dans le store, décision du mode de copie, migration idempotente
du `localStorage`, périmètre `premieresParProjet`, `appliquerCaseDecochee`
depuis l'issue #720, et `ligneIdentite`/`prefixerIdentite`/
`texteCopieAvecIdentite` depuis l'issue #723).

### Journal des messages éphémères (toasts) — pause au survol, erreurs persistantes (issue #730)

Les messages non bloquants (`toasts.info/succes/erreur/avertissement`,
**static/js/socle/toasts.js**) sont le remplaçant unique de `alert()` dans
l'interface. L'issue #730 corrige trois défauts : trop brefs pour être lus,
jamais consultables une fois disparus, et aucune distinction de durée selon la
gravité. Tout passe par le même point d'entrée (`afficher`) : **aucun appelant
existant n'a eu besoin d'être modifié**.

- **Durée de vie selon le type** (`dureeAffichage`). `info`/`succes`
  disparaissent seuls après 4s (`DUREE_DEFAUT_MS`, inchangé) ; `erreur`/
  `avertissement` ne se ferment plus JAMAIS automatiquement — seul un bouton
  « × », toujours visible sur ces deux types, les retire. Les fenêtres de
  confirmation (`toasts.confirmer`) sont hors périmètre, inchangées.
- **Pause au survol.** Tant que la souris est sur un toast auto-effaçable
  (`mouseenter`), son minuteur est gelé — `calculerDelaiRestant(dureeRestante,
  debutActif, maintenant)` calcule le temps qu'il reste à courir. Au départ de
  la souris (`mouseleave`), un nouveau `setTimeout` reprend avec ce temps
  restant. Un clic ailleurs sur le toast (hors bouton « × ») le ferme
  immédiatement, comme avant #730 — réservé aux types auto-effaçables.
- **Journal consultable.** Chaque appel à `afficher` (donc TOUS les messages,
  quel que soit l'appelant) est consigné par `journaliser` dans un historique
  borné à 50 entrées (`JOURNAL_TAILLE_MAX`, FIFO — `ajouterEntreeJournal`),
  avec horodatage et type. Une icône discrète dans l'en-tête
  (`#toasts-journal-bouton`, `templates/fragments/entete.html`) ouvre un
  panneau listant ces messages du plus récent au plus ancien ; une pastille
  (`#toasts-journal-badge`) affiche le nombre de messages non consultés
  depuis la dernière ouverture (`majNonLusApresAjout` — remis à zéro à
  l'ouverture du panneau). Branchement unique : `initJournalMessages()`,
  appelée une fois par `socle/index.js` (délégation du clic sur l'icône +
  clic en dehors pour refermer).
- **Persistance du journal.** Stocké en **`sessionStorage`** (pas
  `localStorage`, et donc **hors** de `persistance.js` qui lui reste
  restreint aux préférences d'interface) sous une clé dédiée
  (`bridge_toasts_journal`) : survit à un rechargement de la page dans le même
  onglet, sans avoir besoin d'être conservé au-delà — un nouvel onglet/une
  nouvelle session repart d'un journal vide.
- **Aucune donnée sensible au-delà de l'écran.** Le journal ne stocke que ce
  qui est déjà affiché à l'écran (texte, type, horodatage) — rien côté
  serveur, aucun watcher ni notification sonore concernés.

Tests de logique pure (`static/js/tests/toasts.test.js`) : `dureeAffichage`
(durée par type, erreur/avertissement sans fermeture automatique),
`ajouterEntreeJournal` (taille maximale, ordre FIFO, pureté),
`majNonLusApresAjout` (compteur de non-lus selon l'état du panneau),
`calculerDelaiRestant` (pause/reprise du compte à rebours, jamais négatif) et
`formaterHeureJournal` (horodatage affiché). Vérification manuelle en
navigateur réel (Playwright) : pause au survol au-delà de la durée d'origine,
reprise après le survol, non-fermeture automatique d'une erreur, badge
masqué/pastille après ouverture du panneau, fermeture par le bouton « × »,
et persistance du journal après un rechargement de page (`sessionStorage`).

### Couleur d'accent des projets (issues #120, #121, #534, #535, #539, #540)

Trois niveaux de priorité déterminent la couleur affichée d'un projet
(pastilles, badges, fond d'accent — `couleurProjet()` dans `static/js/app.js`,
en miroir de `nouveau_projet.py` côté génération) :

1. **`COULEURS_PROJETS_EXISTANTS`** (Python, `nouveau_projet.py`) /
   **`COULEURS_PROJET`** (JS, `static/js/app.js`) — deux dictionnaires
   figés en dur (mêmes 11 couleurs, mêmes clés, doivent rester synchronisés)
   qui gèlent la couleur des 11 projets déjà existants au moment de #535,
   quel que soit le contenu de leur `.conf`.
2. Sinon le champ `COULEUR` persisté dans `configs/<nom>.conf` (exposé par
   `lister_projets()` et injecté côté web dans `window.COULEURS_PERSISTEES`)
   — fonctionnement historique (issue #121), `.conf` source de vérité quand
   le champ est présent.
3. Sinon un hash HSL de secours dérivé du nom du projet (`couleurHashProjet`),
   pour qu'un projet tout juste créé reste distinguable avant qu'une couleur
   définitive lui soit attribuée.

**Piège à connaître** : 6 des 11 projets gelés par #535 avaient déjà un
champ `COULEUR` persisté dans leur `.conf` au moment de la bascule
(`apiselect`, `actualise`, `bloc_score`, `chesscoach`,
`diagnostique_programme`, `rummikub`) — hérité de l'ancien système (#534),
qui ne garantissait pas la saturation 100% ni le contraste texte noir requis
par le nouveau style « fond coloré + texte noir » de #535. Le niveau 1 étant
prioritaire sur le niveau 2, la couleur affichée de ces 6 projets vient
désormais du code, **pas** de leur `.conf` : modifier `COULEUR` dans un de
ces 6 fichiers n'a **aucun effet visible** — c'est une valeur historique,
plus lue par rien. Pour changer réellement la couleur affichée d'un de ces
11 projets, il faut modifier les deux dictionnaires en dur (Python **et**
JS, en gardant la synchro), pas le `.conf`.

Un projet créé **après** #535 (via `nouveau_projet.py`/le bouton web) n'a
pas d'entrée dans ces deux dictionnaires : sa couleur continue d'être
générée à la création (palette étendue #534, en excluant les couleurs déjà
prises) puis lue/écrite normalement depuis le champ `COULEUR` de son
`.conf`, comme avant #535 — le niveau 2 s'applique à lui sans réserve.

**Recycler la couleur d'un projet mis à l'arrêt (issue #540)** : un projet
qui n'est plus travaillé (`ecole`, `ff_galerie`) n'a pas besoin de garder sa
teinte dédiée — la lui laisser immobilise une couleur pour rien dans une
palette déjà contrainte (#539 : la combinaison distance CIE76 + écart de
teinte Lab ne laisse qu'une poignée de couleurs libres). Procédure pour un
futur projet mis à l'arrêt :

1. Retirer sa clé de `COULEURS_PROJETS_EXISTANTS` (`nouveau_projet.py`) —
   **pas** la remplacer par le gris dans ce dictionnaire précis. Ce
   dictionnaire est passé en `couleurs_a_eviter` à `generer_palette()`, qui
   raisonne en angle de teinte Lab (`_teinte_lab`) ; un gris (saturation 0)
   a un a\*/b\* quasi nul, donc un angle `atan2(0,0)` dégénéré à 0°, qui
   entre en collision avec l'exclusion de teinte prévue pour les rouges et
   fait échouer l'assertion de fin de `generer_palette()` (vérifié
   concrètement en clôture de #540, pas supposé). La retirer suffit : sa
   couleur dédiée n'est alors plus dans `couleurs_utilisees()`, ce qui
   libère un emplacement dans `PALETTE_COULEURS` pour un futur projet
   (vérifié : `couleurs_disponibles()` passe de 5 à 6 entrées en retirant
   `ecole`/`ff_galerie`).
2. Remplacer sa valeur, dans `COULEURS_PROJET` (`static/js/app.js`)
   uniquement, par la constante partagée `COULEUR_PROJET_INACTIF`
   (`#767676`) — cette carte reste, elle, la seule source de vérité pour
   l'affichage, y compris des projets à l'arrêt ; la clé y reste donc
   présente (contrairement au dictionnaire Python), simplement avec cette
   valeur grise au lieu de sa teinte dédiée.
3. `COULEUR_PROJET_INACTIF` (même nom, même valeur `#767676`, définie dans
   les deux fichiers — pas de mécanisme de partage de constantes entre
   Python et JS dans ce projet) est un gris neutre choisi uniquement pour
   son contraste texte noir : 4,62:1, au-dessus du seuil `SEUIL_CONTRASTE_NOIR`
   (4,5:1) commun aux couleurs actives — pas de contrainte de saturation
   100% ni de distance/teinte Lab (le but est justement de signaler
   visuellement l'absence d'identité propre, pas de rivaliser avec les
   couleurs actives).

**Colonne « Couleur » du tableau §2 (issue #608)** : `relecture_web` (projet
`relecture_bridge`) n'a accès qu'au tableau public du §2 — `configs/` est hors
de son périmètre — et voulait pouvoir afficher la couleur d'accent de chaque
projet (fenêtres de confirmation, en-têtes de page) sans confondre des noms
proches (`bridge_agent`/`relecture_bridge`, `alchess`/`chesscoach`).
`regenerer_tableaux_projets.py` ajoute donc une colonne `Couleur`, en
**dernière position** (pour ne décaler aucune des colonnes existantes),
contenant pour chaque projet la couleur **réellement affichée**, au même
format hex que les niveaux 1/2 ci-dessus — pas la valeur brute de son `.conf`
quand celle-ci n'est plus lue par rien (piège des 6 projets ci-dessus).

Réutilise `couleurProjet()` plutôt que de la réécrire : `couleur_affichee()`
(nouvelle fonction de `nouveau_projet.py`) applique la même priorité côté
Python — niveau 1 (`COULEURS_PROJETS_EXISTANTS`), niveau 2 (`COULEUR` du
`.conf`), niveau 3 (hash de secours, `couleur_hash_projet()`, miroir de
`couleurHashProjet()` converti en hex plutôt que `hsl(...)`) — avec un niveau
intercalé pour les projets à couleur recyclée (issue #540, `ecole`,
`ff_galerie`) : un ensemble miroir `PROJETS_COULEUR_RECYCLEE` (à tenir à jour
en même temps que `COULEURS_PROJET` côté `app.js`, étape 2 de la procédure de
recyclage ci-dessus) fait afficher `COULEUR_PROJET_INACTIF` dans cette
colonne pour ces projets, comme le fait déjà l'interface web.
`regenerer_tableaux_projets.py` importe `nouveau_projet` localement, dans
`lire_projets()` — pas en tête de fichier — pour éviter le cycle d'import
avec `nouveau_projet.py`, qui importe déjà `regenerer_tableaux_projets` à son
chargement (issue #571).

### Cycle de vie des watchers (démarrage manuel, démarrage auto, extinction auto)

Les watchers ne tournent **pas** en permanence : ils s'allument à la demande et
s'éteignent d'eux-mêmes après une période d'inactivité. Trois mécanismes se
combinent. Depuis #596 (voir le bloc « Watchers supervisés par systemd --user »
plus bas), ils sont en plus supervisés par `systemd --user` : démarrage
automatique au boot du ThinkPad et relance sur crash, sans jamais relancer un
arrêt volontaire (extinction pour inactivité ci-dessous, ou interruption
manuelle #323).

**1. Démarrage manuel.** Le bouton « Lancer le watcher » du bandeau global
(ou `python3 watcher.py --config configs/<projet>.conf` en terminal, cf. bloc
ci-dessus) démarre le watcher du projet sélectionné — désormais via `systemctl --user
start|restart watcher@<projet>` côté serveur (#596). L'interface suit le
process via un fichier PID (`logs/watcher-<nom>.pid`), publié par `watcher.py`
lui-même dès son démarrage.

**2. Démarrage automatique à la création d'une issue** (issues #198 / #202).
Créer une issue **for-linux** depuis l'interface **rallume automatiquement** le
watcher du projet concerné (`app/issues.py` → `demarrer_watcher(cfg,
forcer=False)`, idempotent : no-op si le watcher tourne déjà). Plus besoin de
cliquer « Lancer watcher » avant d'envoyer une tâche : le watcher qui s'était
éteint pour inactivité est relancé au moment où il redevient utile. La garde ne
démarre **que** pour les issues `for-linux` (une issue `for-windows` est traitée
par CCW, rien à lancer côté Linux) ; un échec de démarrage n'invalide jamais la
création d'issue, qui reste réussie.

**3. Extinction automatique après inactivité** (issues #199 / #200, réglable
#201, correctif horloge #217). En tête de chaque cycle, avant de lister les
issues, le watcher mesure le temps écoulé depuis la dernière issue **traitable**
(ni `done`, ni `needs-human`). Au-delà de `DELAI_INACTIVITE_MIN` minutes (défaut
**20**), il s'arrête proprement (`sys.exit(EXIT_INACTIVITE)`, code 42 depuis
#596 — distinct de 0 pour que `systemd/watcher@.service` puisse le déclarer en
`SuccessExitStatus` et ne jamais le relancer) et nettoie son fichier PID. Le
test se fait uniquement **entre** deux cycles complets : un cycle de retry en
cours (jusqu'à ~20 min, cf. #183) n'est jamais interrompu. L'horloge
d'inactivité (`derniere_activite`) est réarmée **deux fois** par cycle : une fois
**avant** le traitement (dès qu'une issue traitable est détectée) et une fois
**après** (dès qu'au moins une issue traitable a été traitée). Ce second
réarmement (issue #217) date la **fin** réelle du travail : sans lui, le
traitement d'une seule issue s'étirant au-delà du délai (plusieurs timeouts de
300 s + retries en cascade — cas réel `watcher-scrabble.log` du 24/07/2026,
~23 min) laissait l'horloge figée au début du cycle, et le test d'extinction du
cycle suivant se déclenchait **immédiatement après un succès** (~14 s après), sur
une horloge périmée ne reflétant pas le travail réel effectué. `DELAI_INACTIVITE_MIN
= 0` **désactive** le mécanisme → watcher permanent (comportement historique). Le
réglage est exposé par projet dans l'onglet « Configuration » (issue #201) et vit
dans le `.conf` du projet.

**4. Redémarrage forcé différé pendant une tâche en cours** (issue #609).
`systemctl --user restart` tue tout le cgroup du service — donc le process
watcher ET toute tâche `claude` qu'il a en cours, sans distinction (pas un
simple SIGTERM propre sur le seul watcher). Vécu sur `relecture_bridge`
(issue #73, diagnostic confirmé le 24/09/2026) : #73 tournait dans son
worktree dédié avec `MAX_WRITE_PARALLELE=1` ; Alain a changé la valeur à 2
et relancé le watcher via l'onglet « Configuration » (bouton « Enregistrer
et relancer ») pendant que la tâche tournait encore ; `systemctl --user
restart` a tué tout le cgroup, dont le process CCL en cours ; au
redémarrage, le watcher a repris #73 comme **premier slot** et l'a relancée
directement dans `REP_TRAVAIL` — l'ancien comportement du premier slot
(issues #577/#337), supprimé depuis par #611, PAS le repli #589 ci-dessous
(aucune ligne « déjà pris » dans les logs) — et le travail, non isolé, a été
embarqué dans un commit automatique d'un autre outil puis poussé par erreur.
Depuis #609, un redémarrage **forcé** (`demarrer_watcher_ou_differer`,
`app/watchers.py`) d'un watcher qui a une tâche en cours — détectée via les
verrous fichier de `watcher.py` (`logs/verrous/*.lock`, cf. §"Verrous
anti-collision inter-process, issue #189" plus bas — champ `projet=`,
sondé vivant), seul canal visible depuis `new_issue.py` puisque
`issues_en_cours` reste en mémoire du process watcher — n'est **jamais**
exécuté immédiatement. Il est mémorisé, et un thread démon de `new_issue.py`
(`surveiller_redemarrages_differes`) l'exécute automatiquement dès la fin de
la tâche. Ce point d'entrée unique couvre les **deux** déclencheurs de
relance manuelle : bouton « Enregistrer et relancer » de l'onglet
Configuration, et bouton « ↺ Relancer » du panneau latéral Infrastructure
(l'ex-onglet « Watchers », supprimé par l'issue #626, en offrait un troisième,
par lot) — les deux passent par la même route `/lancer-watcher` →
`demarrer_watcher_ou_differer`. L'onglet Configuration l'indique clairement
(« redémarrage différé, appliqué à la fin de la tâche en cours »). Un redémarrage
`forcer=False` (`redemarrer_si_eteint`, watcher éteint relancé à la création
d'une issue — point 2 ci-dessus) n'est par construction jamais concerné : il
ne redémarre qu'un watcher **inactif**, qui ne peut pas avoir de tâche en
cours.

> **Limite connue : `Restart=on-failure` de systemd échappe à ce mécanisme.**
> #609/#611 protègent les redémarrages déclenchés **depuis l'interface**
> (`demarrer_watcher_ou_differer`, ci-dessus). Un crash du watcher lui-même
> (exception non rattrapée, OOM, etc.) déclenche `Restart=on-failure` — et
> comme lors de l'incident #73, `systemctl` tue **tout le cgroup** du
> service avant de le relancer, y compris le process `claude` d'une tâche
> `mode_write` en cours. Ce cas ne peut PAS être intercepté côté Python :
> le process est tué avant d'avoir eu la main pour différer quoi que ce
> soit. Aucun mécanisme de ce dépôt ne couvre ce scénario à ce jour — voir
> aussi l'encart « Watchers supervisés par systemd --user » (§16) pour le
> détail de `Restart=on-failure`.

**Cycle complet.** Watcher éteint pour inactivité → on crée une issue for-linux
→ le watcher est rallumé automatiquement (#202) → il traite la tâche → après
`DELAI_INACTIVITE_MIN` minutes sans nouvelle issue traitable, il se rééteint
(#200). Aucun process ne tourne inutilement, et aucune étape manuelle n'est
requise pour le flux normal.

### Interrompre une issue bloquée (issue #323, suite #320)

**Symptôme visé.** Une issue en cours de traitement reste bloquée — CCL
plante, boucle, ou dépasse largement le TIMEOUT attendu sans jamais poser
`done` ni `needs-human` — et Alain veut la sortir du circuit sans attendre
indéfiniment ni sacrifier les autres issues en file pour le même watcher
(elles restent ouvertes sur GitHub, simplement en attente tant que le
watcher n'est pas relancé manuellement).

**Ce que fait le bouton.** Sur toute ligne OUVERTE actuellement **EN COURS**
(lecture OU écriture — `needs-human` exclu, déjà arrêtée) de l'onglet
Résultats, une icône dédiée (carré **vert ✓** au repos, **rouge ✕** au survol)
est affichée directement sur la ligne (issue #641, refonte web étape 6, puis
détachée du préfixe ✏️ par l'issue #642 — un temps dans le panneau latéral
Infrastructure, issue #628, puis dans le détail avant #628) : cliquer dessus
**interrompt cette issue**, avec la même confirmation détaillée et la même
modale de résultat qu'auparavant (contrairement à « Interrompre et fermer »,
#144, qui ferme l'issue, celui-ci ne fait que la sortir du circuit — bouton
« Interrompre et relancer » toujours dans le panneau latéral). Jusqu'à l'issue
#642, cette action n'apparaissait sur la ligne que si l'issue portait le label
`mode_write` (badge ✏️ alors cliquable) : une issue en **LECTURE** en cours
n'avait donc plus aucun moyen d'être interrompue seule depuis sa ligne — l'icône
dédiée, basée sur le même état que le décompte TIMEOUT actif (`timing.debut`,
pas sur le seul label `mode_write`), corrige cette régression ; ✏️ redevient
purement informatif (infobulle « Mode écriture en cours »). `interrompreIssue()`
(`static/js/app.js`, appelée directement par le clic sur l'icône, voir
`static/js/actions_ligne.js::rendreIconeInterruption`/`afficherIconeInterruption`)
appelle `POST /interrompre` (`app/interruption.py::route_interrompre`), qui pose
**toujours** le label `needs-human` et poste un commentaire `⛔ Interrompu
via new_issue.py` (trace GitHub, quel que soit le résultat des étapes
techniques qui suivent), puis exécute selon le label de l'issue
`interrompre_windows()` (issue `for-windows`, voir §16.4) ou
`interrompre_linux()` (issue `for-linux`, ci-dessous) :

- lit le PID du watcher dans `logs/watcher-<projet>.pid` ;
- remonte tout son arbre de process par lecture directe de `/proc/<pid>
  /status` (`PPid`, jamais par nom d'exécutable) ;
- l'achève par `SIGKILL`, attend jusqu'à 5 s sa disparition confirmée
  (avec `waitpid` non bloquant sur le PID du watcher, pour éviter qu'un
  zombie non réapé ne soit à tort signalé comme encore vivant) ;
- supprime le verrou du projet (`_chemin_verrou`) **uniquement** si l'arbre
  est confirmé mort — sinon la suppression est sautée, pour ne jamais
  risquer un double traitement.

Le watcher n'est **jamais** relancé automatiquement (contrairement à
#202) : relance manuelle requise (panneau latéral Infrastructure ou bandeau
global côté CCL, onglet CCW côté CCW-Watcher).

**Équivalent manuel (CCL) :**

```bash
ps aux | grep watcher            # trouver le PID du watcher bloqué
kill -9 <pid>                    # puis ceux de sa descendance si besoin
rm logs/verrous/<fichier>.lock   # UNIQUEMENT si l'arbre est bien mort
```

**Résultat affiché.** Une modale récapitule chaque étape (badges succès /
rien à faire / échec) et le statut global : `ok`, `succes_partiel` (au
moins une étape non critique en échec) ou `echec_critique` (l'arbre de
process n'a pas pu être confirmé mort — le verrou est alors volontairement
laissé en place, intervention manuelle requise).

### Relancer une issue bloquée en `needs-human` (issue #460, cf. #509)

**Symptôme visé.** Après 3 tentatives infructueuses, le watcher pose le
label `needs-human` sur l'issue et cesse de la reprendre — jusqu'ici, la
seule façon de débloquer le circuit était de retirer ce label à la main sur
GitHub, un aller-retour répété en pratique à chaque échec.

**Ce que fait le bouton.** Sur toute ligne OUVERTE portant le label
`needs-human` de l'onglet Résultats, le badge **⚠️** est cliquable
(directement sur la ligne, depuis l'issue #641, refonte web étape 6 — un
temps « 🔄 Retirer needs-human » dans la zone d'actions contextuelles
`#pl-zone-actions` du panneau latéral Infrastructure, issue #628, retiré de
là par #641) : sans fetch réseau supplémentaire, le label vient des données
déjà en mémoire (`listeIssuesResultats`/`it.labels` de la ligne). Un clic
(après confirmation) appelle `relancerIssue()` (`static/js/app.js`, appelée
directement par le clic sur le badge, voir
`static/js/actions_ligne.js::rendrePrefixeLigneOuverte`) → `POST
/relancer-issue` (`app/interruption.py::route_relancer`), qui :

- retire le label `needs-human` côté GitHub (`gh issue edit --remove-label`,
  même mécanisme que `--add-label`/`--remove-label` utilisé par
  `app/issues.py::modifier_label_notif`) ;
- poste un commentaire de trace `🔄 Relancée via new_issue.py (retrait de
  needs-human).` ;
- **ne ferme pas l'issue** — il n'existe pas de label « pending » dans ce
  projet : une issue ouverte sans `needs-human` ni `done` est déjà éligible
  au prochain cycle de polling du watcher (`watcher.py`), à condition que
  celui-ci tourne (aucune relance automatique du watcher lui-même).

**Rafraîchissement.** Après succès, `relancerIssue()` recharge la liste
(`chargerListeIssues()`) puis, si la ligne de l'issue reste visible sous les
filtres courants, son détail (`afficherIssue()`) — le badge ⚠️ disparaît
donc de la ligne concernée sans rechargement manuel complet de la page.

**Décoche de la case « traité/lu » (issue #721).** Une issue relancée va
produire un **nouveau** résultat : si elle était déjà cochée, `route_relancer()`
décoche aussi sa case — même intention et même mécanisme que la relance par
fichier `RELANCE` d'`issues_inbox/` (§3.14, issue #720), via la fonction
partagée `app/cases_cochees.py::decocher_et_diffuser` (voir « État serveur
des cases cochées » ci-dessus). `route_relancer()` s'exécute dans le même
process (`new_issue.py`) que l'état des cases : appel direct, pas de
notification réseau. L'événement SSE `case_decochee` ainsi diffusé décoche
la case **instantanément** dans un onglet Résultats déjà ouvert, sans
rechargement de page. Rien n'est décoché si la relance échoue, ni si
l'issue n'était pas cochée (idempotent).

### Nettoyage de l'arbre de process après une tâche (issue #247)

**Problème constaté.** Après un build Scrabble réussi côté CCW, un `cmd.exe`
(lancé par `pushd \\VBOXSVR\CCW_Share\CCW\scrabble && build\rebuild_scrabble.bat`)
est resté vivant après la fermeture de l'issue — conséquence non cosmétique :
`Scrabble-Setup.exe` refusait de se lancer (« un autre programme utilise ce
fichier ») jusqu'à un `taskkill` manuel. La cause précise côté script important
peu : le défaut de fond était que **rien ne garantissait qu'un process lancé
pendant une tâche soit mort quand la tâche se termine** — n'importe quelle
commande attendant une entrée, une fenêtre ou un verrou pouvait laisser un
orphelin rendant un livrable inutilisable, sans le moindre signal, avec une
issue déjà marquée `done`.

**Mécanisme.** `lancer_claude` (`watcher.py`) lance désormais `claude` via
`subprocess.Popen` avec `start_new_session=True` (POSIX) / `CREATE_NEW_PROCESS_GROUP`
(Windows), qui donne à ce process un groupe/une session à lui plutôt que de
partager celui du watcher. Un bloc `finally` — donc exécuté dans TOUS les cas
de sortie (succès, échec, `TimeoutExpired`, exception) et **avant**
`commenter_resultat_avec_retry`/`fermer_issue` — appelle
`_nettoyer_arbre_claude(proc, job_windows)` :
- **POSIX (CCL)** : `start_new_session=True` garantit que le pgid du process
  claude vaut son propre PID — un groupe forcément neuf, distinct de celui du
  watcher et de tout watcher frère. `_lister_processus_pgid` énumère (lecture
  directe de `/proc`, sans dépendance externe) les process vivants de ce pgid,
  journalise chacun (`log.warning`, PID + ligne de commande), puis
  `os.killpg(pid, SIGKILL)` sur ce seul groupe.
- **Windows (CCW)** : objet Job noyau (`CreateJobObjectW` +
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` + `AssignProcessToJobObject`, via
  `ctypes`) — voir révision ci-dessous (issue #249).

**Révision Windows — objet Job requis (issue #249).** La première version
(2026-07-26) retenait un `taskkill /PID <pid> /T /F` tenté depuis
`_nettoyer_arbre_claude`, par symétrie avec la branche POSIX. Cette approche
s'est révélée **inopérante dans le cas exact visé par #247** :
`_nettoyer_arbre_claude` s'exécute dans le `finally` de `lancer_claude`,
c'est-à-dire **après** le retour de `proc.communicate()` — à cet instant le
process `claude` est déjà terminé et réapé par l'OS. Or `taskkill /PID <pid>
/T /F` a besoin que ce PID **existe encore** pour parcourir son arbre
généalogique ; sur un PID mort, il échoue immédiatement (« process not
found ») sans toucher un seul descendant. C'est précisément le scénario
d'origine : le `cmd.exe` orphelin survit à `claude`, donc au moment du
nettoyage son PID parent n'est plus traçable. `CREATE_NEW_PROCESS_GROUP` ne
comble pas l'écart : sous Windows les groupes de process ne servent qu'au
routage de Ctrl+C/Ctrl+Break, pas à la terminaison d'une arborescence.

**Solution retenue.** Un objet Job Windows (`CreateJobObjectW` +
`SetInformationJobObject(JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)`), créé et
assigné (`AssignProcessToJobObject`) au process `claude` **juste après son
démarrage** (`_preparer_job_windows`, appelé dans `lancer_claude`
immédiatement après le `Popen`, pendant que le process est encore vivant —
seul moment où l'assignation est possible). Fermer le handle du job
(`CloseHandle`, dans `_nettoyer_arbre_claude`) termine alors immédiatement
toute la descendance encore assignée, **qu'un PID cible existe encore ou
non** : c'est la seule garantie réelle sous Windows, sans la fenêtre de
course que la solution symétrique précédente laissait subsister. Implémenté
via `ctypes` pur (pas de nouvelle dépendance, pas de `pywin32`). La branche
POSIX (`start_new_session` + `os.killpg`) est inchangée : elle était déjà
correcte et testée.

**Journalisation, pas critère d'échec — désormais aussi les échecs (#249
point 3).** Chaque orphelin POSIX tué produit un `log.warning` explicite
(PID + ligne de commande). Côté Windows, la version #247 ne journalisait que
le succès d'un `taskkill` : un échec silencieux (le cas réel, taskkill
échouant toujours sur PID mort) ne laissait donc **aucune trace**. Depuis
#249, `_preparer_job_windows` journalise l'échec de création du job ou
d'assignation, et `_nettoyer_arbre_claude` journalise l'échec de fermeture du
handle (ou l'absence de job disponible) — toute tentative de nettoyage laisse
désormais une trace, succès ou échec. Le nettoyage ne fait jamais échouer la
tâche : c'est une garantie de fin de traitement, pas une condition de succès.

**Point critique vérifié (#247 point 4, renforcé #249).** Le nettoyage ne
cible **jamais** par nom d'exécutable — seulement le groupe/pgid POSIX ou
l'objet Job Windows assigné à CE `claude`, garanti distinct de celui du
watcher et de tout watcher frère par construction. Une erreur ici aurait pu
arrêter tous les watchers d'une même machine. #249 a en outre enveloppé
l'intégralité du corps de `_nettoyer_arbre_claude` dans un garde-fou
(`try/except Exception`) : `_lister_processus_pgid` peut lever une `OSError`
sur `iterdir()`, `os.killpg` une `PermissionError`, et l'appel `ctypes`
Windows n'importe quelle exception — aucune ne doit s'échapper d'une fonction
appelée depuis un `finally`, sous peine de masquer la valeur de retour de
`lancer_claude`.

**Tests de non-régression** :
- `tests/test_nettoyage_arbre_247.py` (POSIX, inchangé) — un faux `claude`
  (script shell en tête de `PATH`) lance un vrai enfant bloqué (lecture sur
  un FIFO jamais écrit, équivalent d'une lecture stdin qui n'aboutit jamais)
  puis termine aussitôt ; le test vérifie que l'enfant est mort après le
  retour de `lancer_claude`, que le nettoyage est journalisé, et que le
  process de test (jouant le rôle du watcher) n'est jamais affecté.
- `tests/test_nettoyage_arbre_windows_249.py` (Windows, ajouté #249) — le
  scénario réel n'étant pas exécutable sur le ThinkPad (Linux), ce test mocke
  `ctypes.windll` (et force `os.name = "nt"`) pour vérifier que
  `_preparer_job_windows` appelle bien `CreateJobObjectW` /
  `SetInformationJobObject` / `AssignProcessToJobObject` dans le bon ordre,
  que `_nettoyer_arbre_claude` ferme bien le handle de job et journalise
  succès/échec, et qu'une exception pendant le nettoyage n'est jamais
  remontée. ⚠️ **Ce mock ne remplace pas une validation réelle sur la VM
  CCW** : il vérifie que le code ctypes fait les bons appels, pas que Windows
  tue effectivement l'arbre de process en pratique — cette validation reste
  à faire par un build réel.

**Révision — restype/argtypes ctypes et droits minimaux (issue #251).** Les
appels kernel32 ci-dessus n'avaient pas de `restype`/`argtypes` déclarés :
ctypes suppose alors par défaut un retour `c_int` (32 bits signés), alors que
`CreateJobObjectW`/`OpenProcess` retournent un `HANDLE` — 64 bits sur Windows
x64. Le handle était donc tronqué silencieusement (fonctionnel tant que sa
valeur reste petite, ce qui est le cas en pratique pour un handle noyau, mais
rien ne le garantit), puis retronqué à chaque appel suivant
(`SetInformationJobObject`, `AssignProcessToJobObject`, `CloseHandle`), eux
aussi non déclarés. `_declarer_prototypes_kernel32_windows` (appelée une
seule fois, à l'import de `watcher.py`, sous la garde `if os.name == "nt"`)
déclare désormais `restype`/`argtypes` pour les cinq fonctions avec les types
de `ctypes.wintypes` (`HANDLE`, `BOOL`, `DWORD`, `LPVOID`, `LPCWSTR`). Cette
garde au niveau du module (et non répétée à chaque appel) est délibérée :
le test `tests/test_nettoyage_arbre_windows_249.py` mocke `kernel32` par un
objet Python (méthodes liées, qui ne supportent pas l'affectation
`.restype`/`.argtypes`) et ne force `os.name = "nt"` qu'après l'import —
répéter la déclaration à chaque appel casserait ce mock. Au passage,
`_PROCESS_ALL_ACCESS = 0x1F0FFF` (valeur pré-Vista, toujours fonctionnelle)
a été remplacée par les deux seuls droits que documente Microsoft pour
`AssignProcessToJobObject` : `PROCESS_SET_QUOTA | PROCESS_TERMINATE`.

> **NSSM et jobs imbriqués.** Sous NSSM (§16), le service `CCW-Watcher` peut
> déjà lui-même être assigné à un objet Job Windows. Les jobs imbriqués
> (« nested jobs ») sont supportés depuis Windows 8 : l'assignation du
> process `claude` au job créé par `_preparer_job_windows` doit donc réussir
> même si le watcher qui le lance est déjà dans un job. Si ce n'était pas le
> cas, le `log.warning` de `_preparer_job_windows` le signalerait
> (`_assigner_job_windows` retournant `False`) — point à surveiller lors de
> la prochaine validation réelle sur la VM CCW.

> **Watchers supervisés par systemd --user (issue #119, corrigé et réactivé
> par #596).** Chaque projet actif tourne comme service `watcher@<projet>`
> (`systemd/watcher@.service`), installé par `installer_services.sh` :
>
> - **Démarrage** : à l'ouverture de session (`WantedBy=default.target`) et
>   dès le boot sans session ouverte, grâce au linger utilisateur
>   (`loginctl enable-linger`, posé une fois par le script d'installation).
> - **Redémarrage automatique sur crash, mais pas sur auto-extinction** :
>   `Restart=on-failure` + `SuccessExitStatus=42`. Le watcher s'éteint
>   proprement avec le code 42 (constante `EXIT_INACTIVITE`, `watcher.py`)
>   après `DELAI_INACTIVITE_MIN` minutes sans issue traitable (#199/#200) ;
>   déclarer ce code en `SuccessExitStatus` fait traiter cette sortie comme
>   un arrêt normal, donc **jamais relancée**. Toute autre sortie non nulle,
>   ou une terminaison par signal (crash réel), **est** relancée après
>   `RestartSec=10`. C'est précisément l'incompatibilité qui avait fait
>   abandonner la première tentative (#119, `Restart=always`) : elle
>   relançait systématiquement tout watcher éteint pour inactivité, en
>   boucle sans fin.
>   **Limite (issue #612)** : ce redémarrage sur crash tue tout le cgroup du
>   service, y compris une tâche `claude` `mode_write` en cours — sans
>   avertissement, et sans que ce soit interceptable côté Python (le process
>   est tué avant d'avoir la main). Le mécanisme de report #609/#611 ne
>   couvre que les redémarrages déclenchés depuis l'interface ; celui-ci en
>   est hors de portée par construction.
> - **Installation dynamique** (`installer_services.sh`) : une unité par
>   `configs/*.conf` valide, listés via `app.projets.lister_projets()` —
>   plus de liste de projets codée en dur.
> - **Boutons Démarrer/Arrêter/Relancer de l'interface** : `app/watchers.py`
>   (`demarrer_watcher`/`arreter_watcher`) appelle `systemctl --user
>   start|restart|stop watcher@<projet>` côté serveur — même source de
>   vérité que les services installés, plus de risque de double process.
>   `watcher_actif()` reste basé sur `logs/watcher-<nom>.pid`, désormais
>   publié par `watcher.py` lui-même dès son démarrage (quel que soit son
>   mode de lancement : terminal, `systemctl`, ou bouton de l'interface).
> - **Bouton « Interrompre cette issue » (#323)** : le SIGKILL de l'arbre de
>   process est, du point de vue de systemd, une terminaison par signal —
>   donc normalement relancée par `Restart=on-failure`. `app/interruption.py`
>   neutralise ce cas via `_neutraliser_relance_systemd()`, qui appelle
>   `systemctl --user stop` juste après le SIGKILL : un arrêt délibéré de ce
>   point de vue, qui n'active jamais la politique `Restart=`. Préserve le
>   contrat de #323 (jamais de relance automatique après une interruption
>   manuelle).
> - **Aucune commande sudo requise** : `systemctl --user` gère des services
>   utilisateur, sans droits root (seul `loginctl enable-linger`, posé une
>   fois à l'installation, en demande).
> - **`PATH` explicite obligatoire (issue #598).** Les services systemd
>   --user démarrent avec un `PATH` minimal, sans les ajouts du shell
>   interactif — notamment `~/.npm-global/bin` (où réside `claude`) et
>   `~/Bridge_Agent/venv/bin`. Sans correctif, une issue échoue
>   immédiatement avec « Claude Code introuvable (claude non trouvé dans
>   PATH) » (constaté juste après #596, sur l'issue #67 relecture_bridge) —
>   **même piège** que celui déjà documenté côté CCW/NSSM (§16, service
>   démarré au boot qui n'hérite pas du `PATH` utilisateur). Corrigé par une
>   directive `Environment="PATH=..."` dans `[Service]` de
>   `systemd/watcher@.service`, en chemins **absolus** (`/home/alain/...` —
>   systemd n'interprète pas `~` dans les fichiers d'unité) : à adapter si le
>   bridge est réinstallé sous un autre compte ou une autre machine.
>   Vérification après installation/redémarrage :
>   `cat /proc/<pid>/environ | tr '\0' '\n' | grep PATH` doit lister
>   `~/.npm-global/bin` et `~/Bridge_Agent/venv/bin`.
> - **Diagnostic** : `systemctl --user status watcher@<projet>`,
>   `journalctl --user -u watcher@<projet> -f`.
>
> Hors périmètre de #596 : `new_issue.py` reste lancé manuellement (pas de
> service systemd dédié), et le watcher spool (`scripts/watcher_issues_inbox.py`)
> garde son propre mécanisme de durée/échéance.

**Diagnostic — CCL ne démarre pas** (issue #279, nuit du 29/07/2026) :

- **Symptôme** : plusieurs issues échouent avec un message générique
  « Erreur inconnue » en environ **1,2 s**, après les 3 tentatives prévues —
  la passe diagnostique elle-même échoue aussi. Un échec aussi rapide et
  systématique (toutes les issues, pas une seule) trahit une **cause
  systémique**, indépendante du contenu de la tâche : il ne sert à rien
  d'analyser l'issue elle-même.
- **Première vérification à faire**, en terminal sur la machine CCL :
  ```bash
  claude -p "test" 2>&1
  ```
  Si la réponse contient **« Not logged in »**, le **token de session CCL a
  expiré** — c'est la cause la plus fréquente de ce symptôme.
- **Résolution** : lancer `claude` (sans `-p`, session interactive), puis
  taper `/login` dans l'interface et suivre le flux de connexion.
- **Autres causes possibles** si `claude -p "test"` ne répond pas
  « Not logged in » : réseau indisponible (résolution DNS en échec),
  installation `claude` corrompue (binaire ou dépendances).
- **Distinguer les causes par le temps d'échec** : un token expiré échoue
  **quasi immédiatement (< 2 s)**, comme observé le 29/07/2026 ; un problème
  réseau échoue en général bien plus tard, **proche du TIMEOUT** configuré
  dans l'en-tête de l'issue (l'appel reste bloqué à attendre une réponse qui
  ne vient jamais, jusqu'à expiration).

### Parallélisation mode_write via git worktrees (issue #337, isolation
systématique depuis #577, sans exception depuis #611)

Par défaut, plusieurs issues `mode_write` peuvent désormais tourner **en
parallèle**, chacune dans son propre `git worktree` (répertoire frère isolé,
sur sa propre branche) — au lieu du traitement strictement séquentiel
historique (un seul `mode_write` à la fois, dans `REP_TRAVAIL`). Les issues
`mode_lecture`/`mode_scratch` restent, elles, toujours traitées
séquentiellement dans `REP_TRAVAIL` (hors périmètre de cette issue).

> **Issues #577/#611 — `REP_TRAVAIL` n'est plus jamais touché directement
> par une tâche `mode_write`, quelle que soit la valeur de
> `MAX_WRITE_PARALLELE`, sauf échec confirmé du worktree.**
> Incident réel ayant motivé #577 : sur `relecture_bridge`
> (`MAX_WRITE_PARALLELE=1`), Alain a fait un `git commit`/`git stash` manuel
> dans `REP_TRAVAIL` pendant qu'une issue `mode_write` y travaillait
> directement (comportement d'avant #577) — collision directe, une
> modification manuelle temporairement effacée, récupérée de justesse depuis
> un commit orphelin. `MAX_WRITE_PARALLELE` et l'isolation de CCL
> vis-à-vis d'Alain sont deux besoins distincts : le premier pilote la
> parallélisation **entre tâches CCL** (thread principal vs threads
> parallèles, utilité réelle uniquement `> 1`) ; le second doit s'appliquer
> **systématiquement**, y compris à `MAX_WRITE_PARALLELE = 1` où une seule
> tâche tourne à la fois. #577 avait laissé une exception non documentée :
> à `MAX_WRITE_PARALLELE > 1`, la PREMIÈRE tâche `mode_write` d'un lot était
> quand même dispatchée directement dans `REP_TRAVAIL` (`worktree=None`),
> sans isolation — incohérence entre l'encart ci-dessus et le code, qui a
> laissé du travail inachevé mélangé dans `REP_TRAVAIL` lors d'un redémarrage
> du watcher pendant ce premier slot (`relecture_bridge` #73). **Issue #611**
> supprime cette exception : toute tâche `mode_write`, quel que soit son
> rang dans le lot, obtient d'abord un worktree dédié — avec plusieurs
> tentatives sous noms alternatifs (`-bis`, `-ter`) si le chemin/la branche
> standard est déjà pris (reliquat non nettoyé). Manipuler `REP_TRAVAIL`
> (commit, stash, navigation) pendant qu'une issue `mode_write` est en cours
> reste donc sans risque de collision dans l'écrasante majorité des cas — la
> seule exception restante est le repli en tout DERNIER recours, quand
> **toutes** les tentatives de création de worktree ont échoué : ce cas est
> volontairement signalé de façon active (notify-send immédiat + log.warning
> + mention dans le compte-rendu de clôture de l'issue), jamais silencieux.

- **`MAX_WRITE_PARALLELE`** (`.conf`, entier, défaut **2**) — nombre maximum
  de tâches `mode_write` concurrentes **entre elles**. `1` = pas de
  parallélisation entre tâches (une seule à la fois, thread principal,
  aucun `threading.Thread` créé) — mais la tâche obtient malgré tout un
  worktree dédié (issue #577) : `REP_TRAVAIL` reste libre pour Alain même
  dans ce cas. `0` = désactivé, identique à `1`.
- **Réglage via l'interface et plafond de 4 (issue #568)** : réglable depuis
  l'onglet Configuration de `new_issue.py` via un slider (`min="1" max="4"`)
  — la valeur invalide est donc physiquement impossible à sélectionner par ce
  chemin, sans validation serveur à contourner. Le plafond de 4 est un choix
  délibéré : au-delà, risque de contention sur CCW (Pentium G2020 dual-core)
  et de diluer la relecture humaine des diffs sur CCL. Rien n'empêche cependant une
  modification manuelle du `.conf` au-delà de ce plafond : `charger_config`
  plafonne alors silencieusement `CFG.max_write_parallele` à `4` pour
  l'exécution en cours (jamais de blocage total du traitement du projet
  pour ce seul motif), **sans jamais modifier le `.conf`** — règle absolue
  du projet, le `.conf` reste le domaine exclusif d'Alain. Tant que l'écart
  persiste, `verifier_plafond_max_write_parallele()` (appelée en début de
  cycle, comme `verifier_accumulation_worktrees()`) émet un `log.warning`
  explicite à **chaque cycle** — jamais une fois puis silence.
- **Décision de parallélisation** (`traiter_issue`, point d'entrée public
  appelé pour chaque issue) :
  - `MAX_WRITE_PARALLELE > 1` : **toute** issue `mode_write` détectée,
    y compris la première d'un lot (issue #611 — plus d'exception
    `REP_TRAVAIL` pour ce cas, cf. encart ci-dessus), est dispatchée dans un
    thread Python après obtention d'un worktree dédié via
    `_creer_worktree_avec_retries` — nécessaire dans tous les cas pour que la
    boucle principale (mono-thread) reste libre de détecter d'autres issues
    `mode_write` pendant que celle-ci tourne encore.
  - `MAX_WRITE_PARALLELE ≤ 1` (issue #577) : aucune raison de garder la
    boucle principale libre puisqu'une seule tâche `mode_write` tourne à la
    fois — `_creer_worktree_avec_retries` est appelée directement, puis
    `_traiter_issue_synchrone` **sans thread**, en appel bloquant, avec ce
    worktree. Le modèle d'exécution (synchrone vs thread) reste donc piloté
    par `MAX_WRITE_PARALLELE` comme avant #577 ; seule la présence d'un
    worktree change — plus jamais `REP_TRAVAIL` directement.
  - Dans tous les cas, échec de **toutes** les tentatives de création du
    worktree (chemin ou branche déjà pris, erreur git — voir
    `_creer_worktree_avec_retries` ci-dessous) → repli propre sur
    `REP_TRAVAIL` (`chemin_worktree = None`), jamais d'exception propagée,
    mais désormais signalé activement (issue #611, voir plus bas) plutôt
    qu'un simple `log.warning`.
- **Worktree** : chemin `<REP_TRAVAIL>/../<NOM_PROJET>-issue<N>` (répertoire
  frère de `REP_TRAVAIL`), branche `worktree-issue-<N>`, créés par
  `git -C <REP_TRAVAIL> worktree add <chemin> -b worktree-issue-<N>`. Si le
  chemin ou la branche existe déjà, `_creer_worktree_avec_retries` (issue
  #611) retente jusqu'à 2 fois de plus sous un nom alternatif —
  `<NOM_PROJET>-issue<N>-bis` puis `-ter`, branches `worktree-issue-<N>-bis`/
  `-ter` — couvrant le cas le plus fréquent (worktree orphelin non nettoyé),
  sans introduire de worktree permanent partagé. Si `git worktree add` échoue
  pour une raison différente (erreur git générique), aucune retentative :
  changer de nom ne résoudrait rien. Si **toutes** les tentatives échouent,
  repli propre sur le traitement séquentiel classique dans `REP_TRAVAIL`
  (l'issue attend qu'un slot se libère au prochain cycle) — jamais
  d'exception propagée, mais signalé activement (voir point suivant).
  **Réutilisation sur RELANCE (issue #725)** : AVANT toute tentative de
  création, `_preparer_worktree_ecriture` (appelée par `traiter_issue` à la
  place de `_creer_worktree_avec_retries`) cherche via
  `_trouver_worktree_reutilisable` un worktree déjà existant pour CETTE MÊME
  issue (nom standard ou `-bis`/`-ter` hérité), enregistré comme worktree de
  ce dépôt, dont la branche correspond et qui n'est pas verrouillé par un
  traitement en cours — s'il en existe plusieurs (cas hérité), le plus
  récemment modifié (dernier commit) est choisi. Trouvé : il est REPRIS tel
  quel (commits et modifications non commitées compris), sans `-bis` ni
  perte du travail déjà fait — c'est le correctif direct du problème constaté
  sur Rummikub #146 (relance qui recréait un worktree vierge basé sur
  master, abandonnant le travail de la tentative précédente). CCL reçoit
  alors dans son prompt un bloc dédié (même esprit que la clause « tentative
  précédente » #689) l'invitant à vérifier/compléter ce travail plutôt qu'à
  le refaire, et à le dire explicitement dans son rapport final. `master`
  n'est JAMAIS rebasé automatiquement sur ce worktree repris : si `master` a
  avancé depuis sa création, l'écart (nombre de commits) est journalisé et
  ajouté au compte-rendu de clôture, pour un merge manuel en connaissance de
  cause. Aucun candidat valide trouvé (première exécution, dossier présent
  mais non enregistré comme worktree, branche absente) : comportement
  historique inchangé, repli sur `_creer_worktree_avec_retries` ci-dessus.
  Le nettoyage des worktrees reste, comme avant, entièrement manuel.
- **Repli en dernier recours : signalement actif (issue #611)** — quand
  `_creer_worktree_avec_retries` épuise ses 3 tentatives, `traiter_issue`
  appelle `_signaler_repli_worktree_echoue` avant de lancer la tâche dans
  `REP_TRAVAIL` : `notify-send` immédiat (bulle bureau Linux, via
  `notifier_bureau` — instantané et visible si Alain est présent, sans le
  délai possible de `ntfy`), `log.warning` explicite avec le chemin
  concerné, et mention dans le compte-rendu de clôture de l'issue (mécanisme
  `echec_worktree_deja_pris` déjà en place depuis #589, désormais transmis
  aussi côté thread parallélisé via `_lancer_thread_ecriture`). Ce repli
  reste, comme avant, en tâche de fond (thread), pas un appel bloquant : la
  boucle principale demeure libre même dans ce cas de dernier recours.
- **Signal d'interface (issue #609, mis à jour #611/#612)** : depuis #611,
  toute tâche `mode_write` obtient d'abord un worktree dédié, quel que soit
  `MAX_WRITE_PARALLELE` — il n'existe donc plus qu'**un seul** cas où une
  tâche `mode_write` tourne directement dans `REP_TRAVAIL` : le repli en
  tout dernier recours, quand `_creer_worktree_avec_retries` a épuisé ses 3
  tentatives (#589). `app.watchers.repli_rep_travail` (via le verrou fichier
  de `watcher.py`, champ `mode=`, cf. §"Redémarrage forcé différé..." plus
  haut) ne signale donc plus qu'un cas d'anomalie, plus un cas normal et
  fréquent comme avant #611 : dès qu'une tâche `mode_write` est en cours
  dans `REP_TRAVAIL`, un bandeau global (visible sur tous les onglets) le
  signale — en plus, désormais, du `notify-send` immédiat émis au moment du
  repli (issue #611, ci-dessus). Le bandeau ne s'allume donc plus à chaque tâche `mode_write`
  normale (toutes isolées dans un worktree désormais), seulement dans ce cas
  d'anomalie rare.
- **CHANGELOG** : dans un worktree, CCL reçoit une consigne de prompt dédiée
  lui demandant d'écrire son entrée dans `CHANGELOG-<N>.md` à la racine du
  worktree plutôt que dans `CHANGELOG.md` directement, pour éviter un
  conflit systématique sur ce fichier unique entre worktrees actifs en
  parallèle — voir `scripts/fusionner_changelog.py` (issue #336), qui
  intègre ces fichiers dans `CHANGELOG.md` avant le push d'Alain (lancement
  manuel, pas encore appelé automatiquement par `watcher.py`).
- **Verrou anti-collision (issue #189/#322)** : posé par `chemin_travail`
  (le `REP_TRAVAIL` ou le worktree effectif de CETTE tâche), et non plus
  systématiquement par `REP_TRAVAIL` seul — deux worktrees du même projet
  obtiennent donc deux verrous distincts et peuvent tourner sans s'attendre,
  tandis qu'une issue `mode_lecture`/`mode_scratch` visant `REP_TRAVAIL`
  pendant qu'une tâche `mode_write` y tourne encore (repli en dernier
  recours, #611, ou `MAX_WRITE_PARALLELE ≤ 1`) reste bloquée par le même
  verrou qu'avant, reprise au cycle suivant.
- **Libération garantie, quel que soit le chemin de sortie (issue #584)** :
  `_traiter_issue_synchrone` pose le verrou puis entre immédiatement dans un
  `try`/`finally` qui enveloppe l'intégralité du traitement — succès, échec
  après une ou plusieurs tentatives, abandon définitif (`needs-human`), **et
  refus précoce** (claude répond ❌ en quelques secondes, avant tout travail
  réel, ex. « hors périmètre ») empruntent tous des `return` internes à ce
  `try` : le `finally` (`liberer_verrou`) s'exécute dans tous les cas, sans
  exception. Une issue qui échoue immédiatement ne peut donc pas, par ce
  mécanisme, laisser le verrou posé pour les issues `mode_write` suivantes
  sur le même `REP_TRAVAIL` — voir `tests/test_verrou_refus_precoce_584.py`.
  Seul un arrêt BRUTAL du process watcher lui-même (crash, `kill -9`,
  redémarrage de service) contourne ce `finally` (aucun `try`/`finally`
  Python n'y survit, sur aucune plateforme) : c'est le scénario réel
  identifié derrière l'incident #583 (verrou orphelin bloquant 48 minutes),
  couvert par le filet de sécurité ci-dessous, pas par un défaut du
  `try`/`finally` lui-même.
- **Filet de sécurité contre un verrou orphelin, deux niveaux (issues
  #322/#584)** : `acquerir_verrou` reprend un verrou existant selon deux
  critères indépendants (le premier qui matche suffit) :
  1. **Péremption par ancienneté** (issue #322, mécanisme d'origine) : âge du
     verrou ≥ `max_essais × (TIMEOUT_projet + pause) + marge`. Pour un projet
     à `TIMEOUT` élevé (ex. 1800 s), ce délai peut légitimement atteindre
     plusieurs dizaines de minutes — c'est l'ordre de grandeur du blocage
     observé sur #583.
  2. **PID du watcher propriétaire confirmé mort** (issue #584, filet
     complémentaire, plus rapide) : le fichier verrou porte toujours un champ
     `pid=<n>` (le PID du watcher qui l'a posé, écrit dès la création — à ne
     pas confondre avec `claude_pgid=<n>`, ajouté seulement après le
     lancement de claude). Si ce PID est sondé et confirmé **mort**
     (`_pid_vivant`, POSIX : `os.kill(pid, 0)` ; Windows : `OpenProcess`), le
     verrou est repris **immédiatement**, sans attendre l'écoulement de la
     péremption par ancienneté — corrige directement le délai de 48 minutes
     de #583. Asymétrie volontaire : PID introuvable ⇒ orphelin certain ; PID
     vivant, sonde en échec, ou plateforme non gérée ⇒ verrou considéré actif
     par prudence (repli sur le critère 1, jamais moins sûr qu'avant #584—
     un PID mort peut en théorie avoir été recyclé par l'OS pour un tout
     autre process, d'où le choix de ne JAMAIS conclure « orphelin » sur la
     seule foi d'un PID trouvé vivant).
  Dans les deux cas, avant de reprendre le verrou, le nettoyage de
  l'éventuel `claude` orphelin (pgid stocké, POSIX uniquement) reste
  appliqué à l'identique (issue #322, inchangé). Ce filet reste un
  complément, pas un remplacement : la libération normale (`finally`
  ci-dessus) demeure le chemin attendu à chaque traitement.
- **Fin de tâche** : le worktree n'est **jamais** supprimé automatiquement
  (ni `git worktree remove`, ni suppression de la branche) — Alain merge et
  pousse manuellement une fois le travail relu. Le numéro d'issue, le
  chemin du worktree et la branche sont journalisés clairement en fin de
  traitement.
- **Auto-extinction (§13 ci-dessus)** : le watcher ne s'éteint jamais tant
  qu'un thread `mode_write` tourne encore, même si `DELAI_INACTIVITE_MIN`
  est dépassé — réévalué à chaque cycle, dès qu'un thread se termine
  l'extinction redevient possible.
- **Alerte accumulation de worktrees (issue #432)** : en début de chaque
  cycle de polling, juste après le `git pull --ff-only` (§13), le watcher
  compte les worktrees secondaires actifs (`git worktree list`, hors
  `REP_TRAVAIL`) et émet un `log.warning` clair (chemin + branche de
  chacun) dès que ce nombre dépasse `SEUIL_ALERTE_WORKTREES` (`.conf`,
  entier, défaut **3**) — visible dans l'onglet Journal watcher de
  l'interface. Aucune notification ntfy/bureau ; le nettoyage reste
  entièrement manuel (Alain).
- **`needs-human` occupe sa place jusqu'à résolution manuelle (issue #576,
  changement de sémantique)** : depuis #576, une issue `mode_write` qui
  échoue définitivement (label `needs-human` posé — épuisement des
  tentatives, `SOUS_DOSSIER`/`REPO_CIBLE`/bootstrap CREATION refusé, etc.)
  **continue d'occuper une place de `MAX_WRITE_PARALLELE`** au lieu d'être
  libérée aussitôt le thread terminé (comportement d'avant #576). Avec
  `MAX_WRITE_PARALLELE = 1`, une seule issue `needs-human` oubliée bloque
  donc tout traitement `mode_write` suivant sur ce projet — comportement
  voulu, pas un bug : Alain dépose parfois plusieurs issues en cascade
  potentiellement dépendantes (sans mécanisme de dépendance explicite,
  volontairement écarté) puis s'absente ; laisser la suivante démarrer sur
  un état de projet intermédiaire laissé par l'échec serait pire que
  d'attendre son intervention. Avec une valeur plus haute, l'issue bloquée
  occupe une place parmi les autres sans empêcher le reste de tourner.
  La place n'est libérée que par une intervention **explicite** d'Alain,
  détectée au cycle suivant :
  - retrait manuel du label `needs-human` sur GitHub (issue toujours
    ouverte) — détecté par `traiter_issue` à la relecture des labels frais ;
  - relance via le bouton web « 🔄 Relancer » (#574) ou un fichier
    `RELANCE` (#516/#572), qui retirent tous deux ce même label ;
  - fermeture manuelle de l'issue sur GitHub SANS retirer le label — cas
    distinct, car `lister_issues()` ne renvoie que les issues **ouvertes**
    et une issue fermée disparaît donc purement et simplement de la liste
    sans jamais repasser par `traiter_issue` ; détecté séparément par
    `_reconcilier_issues_en_cours_fermees`, appelée une fois par cycle juste
    après `lister_issues()`, en tête de boucle principale.
  Le chemin de succès normal (issue traitée et fermée avec le label `done`)
  est inchangé : seul le comportement du chemin `needs-human` est affecté.

> Pour le détail du workflow et les procédures de récupération, voir
> [`WORKTREES.md`](WORKTREES.md).

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
  l'issue avec `| LABELS | for-windows |` (§20) — pas de chef.
- **Contre-exemple explicite** : un chef qui se contente de créer un ouvrier
  puis d'attendre sa fermeture, sans orchestration réelle, est du surcoût
  pur (deux issues, deux invocations `claude`, TIMEOUT long, attente
  synchrone bloquante).
- L'exemple validé plus bas dans cette section (dictionnaire déposé côté
  Linux puis rebuild côté Windows) est justement un cas où le chef EST
  justifié — la règle ci-dessus ne le contredit pas.
- **⚠️ Contrepartie opérationnelle** : le rallumage automatique du watcher à
  la création d'issue (§13, mécanisme 2) ne s'applique PAS aux issues
  `for-windows`. Avant d'envoyer une issue `for-windows` directe, vérifier
  dans l'onglet CCW (§16.2) que le PC fixe est joignable et que le service
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

**But :** disposer d'un agent **Claude Code Windows (CCW)** tournant sur un
**PC fixe physique dédié**, pour traiter les issues `for-windows` —
principalement les builds `.exe` (PyInstaller) qui exigent un environnement
Windows natif.

**Réinstallation du PC fixe :** procédure complète (Windows →
`configurer_ssh_ccw.ps1` → `provisionner.ps1` → tokens → vérification) dans
`provisioning/windows/REINSTALLATION_CCW.md` (issue #451).

> **🚀 Démarrage rapide — ajouter CCW à un projet (issue #559/#560).**
> Dans le modal « + Nouveau projet », coche la case **« Projet CCW »**,
> remplis le topic ntfy, puis clique **« Créer le projet »**. Une fois le
> projet créé, un bloc **« Finaliser le bootstrap CCW »** apparaît avec le
> nom du dépôt réel : crée à ce moment-là un token GitHub fine-grained
> dédié (accès **uniquement** au nouveau dépôt, `Issues: Read and write` /
> `Metadata: Read-only`) et un `CLAUDE_CODE_OAUTH_TOKEN` (`claude
> setup-token`), colle les deux, clique **« Finaliser le bootstrap CCW »**.
> C'est tout — un service Windows dédié se crée automatiquement, même si
> CCW est éteint au moment du clic (l'issue attend simplement en file).
> Si le bouton « Rafraîchir la clé publique » indique une clé absente ou
> périmée, CCW doit être allumé le temps de cliquer dessus une fois — voir
> §16.7 pour le détail. Le reste de ce §16 documente le fonctionnement
> interne, pas la marche à suivre au quotidien.

> **⚠️ Changement de plateforme (depuis août 2026, issue #446).** CCW ne
> tourne plus dans une VM VirtualBox mais **sur un PC fixe physique**
> (Pentium G2020). De nombreux paragraphes ci-dessous décrivent encore
> l'ancienne architecture VM (VirtualBox, `VBoxManage`, chemin UNC, éval 90
> jours) : ils sont conservés à titre **historique** et signalés comme tels
> au fil du texte, mais ne décrivent plus le fonctionnement réel. Les deux
> paramètres qui changent partout dans ce §16 : `REP_TRAVAIL = C:\CCW_Share`
> (chemin **local**, plus de partage VirtualBox) et le service NSSM
> `CCW-Watcher` tourne sous le compte **`AlainW`** (administrateur, mais
> jeton filtré par l'UAC en session normale — voir issue #717 plus bas) et
> non plus sous `LocalSystem`.

**Modèle de build partagé (PC physique) — issues `for-windows` dans
Bridge_Agent.** Le service NSSM `CCW-Watcher` (service de base, sans
suffixe de projet) surveille les issues `for-windows` du dépôt
`AlainDelree/Bridge_Agent` — c'est le canal utilisé pour les builds
PyInstaller ponctuels (procédure détaillée en §16.3). `REP_TRAVAIL =
C:\CCW_Share` — répertoire de travail **local** sur le PC physique, partagé
entre CCL (qui y accède via le réseau local) et CCW (qui y accède en
chemin local direct). Chaque projet buildé est cloné dans un sous-dossier
dédié : `C:\CCW_Share\CCW\<projet>\`. Ce modèle garantit le séquencement
strict des builds par construction (un seul process `watcher.py` sur ce
canal, une issue à la fois) et supprime tout risque de contention CPU/RAM
entre deux builds parallèles.

> **Champ d'en-tête `SOUS_DOSSIER` (issue #550) — cibler un sous-projet du
> canal unifié sans blocage `git`.** Sur ce canal, `claude` démarrait
> jusqu'ici TOUJOURS avec pour cwd `REP_TRAVAIL` tout entier
> (`C:\CCW_Share`), même quand l'issue ne visait qu'un sous-projet précis
> (ex. `C:\CCW_Share\CCW\gestionmail\`). **Confirmé empiriquement** (issue
> #550, reproduction locale Linux avec la même structure cwd-parent +
> sous-dossier-cible) : quand le cwd réel du process diverge du dossier où
> une commande `git` opère effectivement — atteint via `git -C <chemin>` ou
> `cd <chemin> &&` —, Claude Code bloque la commande par une demande
> d'approbation interactive (`This command requires approval`, ou pour la
> forme `cd && git` : `This command changes directory before running git,
> which can execute untrusted hooks from the target directory`), **même si
> son préfixe correspond exactement à une entrée de
> `OUTILS_LECTURE_AUTORISES`** — `--allowedTools` ne pilote pas ce
> garde-fou-là. `git pull --ff-only` **bare** (sans `-C` ni `cd`), lancé
> avec un cwd déjà positionné sur le bon dossier, n'est en revanche PAS
> bloqué. C'était la cause racine réelle du blocage persistant constaté sur
> `gestionmail` dans #546/#548/#549 — les correctifs successifs sur
> l'allowlist (#546) et l'hypothèse de version CLI (#549) portaient sur le
> mauvais mécanisme.
>
> Pour une issue `for-windows` ciblant un sous-projet du canal unifié,
> ajouter dans l'en-tête un champ optionnel `| SOUS_DOSSIER | CCW\<projet> |`
> (chemin **relatif** à `REP_TRAVAIL`, jamais absolu — un chemin absolu
> reste l'usage de `REPO_CIBLE`, §périmètre dynamique). `watcher.py`
> (`extraire_sous_dossier`/`valider_sous_dossier`) construit alors
> `cwd_effectif = REP_TRAVAIL / SOUS_DOSSIER` (rejeté si absolu, si la
> résolution sort de `REP_TRAVAIL` — traversée `..`/lien symbolique —, ou si
> le dossier n'existe pas ; erreur définitive, `needs-human`, aucun retry) et
> l'utilise aussi bien comme cwd réel du process que comme périmètre
> effectif du prompt. Sans objet si le projet est déjà en
> `PERIMETRE_DYNAMIQUE`/`REPO_CIBLE` (#125) ou si la tâche tourne dans un
> worktree isolé (#337) — ces deux mécanismes restent seuls décisifs si
> combinés par erreur. **Absent de l'issue (usage historique, sans
> sous-projet ciblé) : comportement strictement inchangé**, `cwd_effectif`
> reste `REP_TRAVAIL`.
>
> **Protocole de retest** (à rejouer sur CCW, hors du périmètre Linux de la
> tâche #550 qui a implémenté ce champ) : ouvrir une issue `for-windows` en
> mode lecture, en-tête `| SOUS_DOSSIER | CCW\gestionmail |`, corps demandant
> `git pull --ff-only` dans `C:\CCW_Share\CCW\gestionmail\` — succès attendu
> sans demande d'approbation, désormais que le cwd du process coïncide avec
> ce dossier.

> **Ce canal de build coexiste avec le modèle multi-projets (issue #170,
> actif — voir plus bas dans ce §16).** Des services NSSM **additionnels**
> `CCW-Watcher-<Projet>` surveillent chacun les issues **directement dans
> le dépôt du projet concerné** (ex. `AlainDelree/Scrabble`), indépendamment
> du canal `for-windows`/Bridge_Agent décrit ci-dessus. Les deux modèles ne
> s'excluent pas : `CCW-Watcher` (build, Bridge_Agent) et
> `CCW-Watcher-<Projet>` (agent dédié par projet) tournent **simultanément**
> sur le même PC physique.

> **⚠️ Le clone `C:\CCW\Bridge_Agent` n'est JAMAIS mis à jour automatiquement
> (issue #240).** Le `git pull --ff-only` automatique de début de cycle (§1)
> porte sur `REP_TRAVAIL` — ici `C:\CCW_Share`, qui **n'est même pas un
> dépôt git**. Le code réellement exécuté par le service `CCW-Watcher` vit
> dans un clone **distinct**, `C:\CCW\Bridge_Agent` (cloné en lecture seule
> par `provisionner.ps1`, cf. tableau de provisioning ci-dessous) : **personne
> ne le rafraîchit automatiquement**, ni le watcher lui-même (qui ne pull que
> `REP_TRAVAIL`), ni aucun autre mécanisme.
>
> **Cas réel constaté** : le 26/07/2026, ce clone avait accumulé **80 commits
> de retard** sur `origin/master`, sans aucun signal — le service tournait
> avec du code antérieur à l'issue #195. Cause probable de l'incident #236
> (issue fermée `done` sans commentaire de résultat, code de vérification
> post-publication de #237 pas encore présent sur la VM).
>
> **Procédure obligatoire après tout push touchant `watcher.py` (ou tout
> fichier chargé par le process) :**
> 1. Dans la VM, depuis `C:\CCW\Bridge_Agent` : `git pull --ff-only`.
> 2. **Redémarrer le service** `CCW-Watcher` (`nssm restart CCW-Watcher`) —
>    un pull seul **ne suffit pas** : un process Python déjà démarré garde en
>    mémoire le code chargé à son lancement, il ne relit pas les fichiers
>    `.py` modifiés sur disque.
>
> **Contrôle rapide** (à lancer dans `C:\CCW\Bridge_Agent`) :
> ```
> git status -sb
> ```
> Le résultat ne doit **jamais** mentionner `behind` — sa présence signale un
> clone en retard, donc potentiellement un service tournant sur du code
> obsolète.

**Modèle multi-projets — actif en production (#170 ; correction issue
#547).** ⚠️ Contrairement à ce qu'affirmait une version antérieure de ce
document, le modèle multi-projets — un clone `C:\CCW\<Projet>` + un config
`configs\<nom>-ccw.conf` + un service NSSM `CCW-Watcher-<Projet>` par
projet — n'est **pas** abandonné : il est **actif et utilisé en
production**, avec 5 services NSSM confirmés à l'état `running` (constat
empirique via l'onglet CCW de `new_issue.py`, issue #547) : `CCW-Watcher`
(base, Bridge_Agent) + `CCW-Watcher-actualise`, `-alchess`, `-rummikub`,
`-scrabble`. Les scripts `ajouter_projet_ccw.ps1` et
`finaliser_projet_ccw.ps1` (`provisioning\windows\`) restent les scripts
**de référence** pour tout nouveau projet — voir aussi
`creer_projet_ccw_complet.ps1` (§16.5), qui les orchestre (le premier des
deux) en une seule commande.

> **Architecture confirmée : un seul `watcher.py` partagé par tous les
> services (issue #547).** Les 5 services NSSM ci-dessus exécutent tous le
> **même** fichier source `C:\CCW\Bridge_Agent\watcher.py` — chaque service
> se contente de passer un `--config configs\<projet>-ccw.conf` différent
> en paramètre (`AppParameters`, vérifié via `nssm get <Service>
> AppParameters`). Les dossiers `C:\CCW\<projet>\` (créés par
> `ajouter_projet_ccw.ps1`) contiennent **uniquement** le code du projet
> cible lui-même (pour builds/traitement) — **jamais** une copie de
> `watcher.py`. **Conséquence pratique :** un correctif apporté à
> `C:\CCW\Bridge_Agent\watcher.py` s'applique **à tous les projets** dès que
> chaque service concerné est redémarré (`nssm restart
> CCW-Watcher-<Projet>`) — inutile de repousser du code dans chaque
> sous-dossier `C:\CCW\<projet>\`. Cohérent avec la mise en garde plus haut
> sur `C:\CCW\Bridge_Agent` (jamais mis à jour automatiquement, issue
> #240) : un `git pull --ff-only` dans ce clone unique, suivi du
> redémarrage des services concernés, suffit à propager le correctif
> partout.

**Provisioning** (dossier `provisioning/windows/`) :

| Fichier | Rôle |
|---------|------|
| `provisionner.ps1` | Script PowerShell d'installation logicielle : installe Git, GitHub CLI, Python 3.12 et NSSM par **téléchargement direct des installeurs officiels** (plus de dépendance à winget, issue #658 — bootstrap winget systématiquement en échec sur l'édition LTSC/IoT du PC fixe, dépendance `Microsoft.VCLibs.140.00` introuvable en autonome), OpenSSL en installeur autonome (winget en repli optionnel `-TenterWinget`), pyinstaller (pip) + Claude Code (installeur natif, sans Node.js, + ajout du `PATH` utilisateur `.local\bin`), désactive Windows Update, clone le dépôt en lecture seule dans `C:\CCW\Bridge_Agent`, écrit `configs\ccw.conf` (`LABEL=for-windows`, `NOM=ccw`, `REP_TRAVAIL=C:\CCW_Share` — chemin **local** sur le PC physique —, `TOPIC_NTFY` placeholder), et enregistre le service Windows `CCW-Watcher` via NSSM sous le compte **`AlainW`** (administrateur, jeton filtré par l'UAC en session normale — issue #717), avec son `PATH` complet posé dans `AppEnvironmentExtra`. Mot de passe du compte de service demandé via `Read-Host -AsSecureString` (fonctionne en SSH, contrairement à l'ancien `Get-Credential`). Mode `-DryRun`/`-WhatIf` disponible. Reste utilisable comme référence des étapes d'installation logicielle, à rejouer manuellement sur le PC physique le cas échéant. |
| `mettre_a_jour_tokens_ccw.ps1` | Renouvellement des tokens d'un service CCW sans manipuler à la main la chaîne PowerShell (issue #168). Demande `GH_TOKEN` puis `CLAUDE_CODE_OAUTH_TOKEN` en `Read-Host -AsSecureString` (jamais affichés en clair), reconstruit `AppEnvironmentExtra` comme **trois lignes distinctes** — `PATH`, `GH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN` — passées en arguments séparés à `nssm set` (issue #658 : une chaîne unique jointe par `` `n`` ne fonctionne pas avec `nssm set`, et sans reconstruire la ligne `PATH` à chaque appel, `nssm set` — qui REMPLACE toute la valeur — effacerait celle posée par `provisionner.ps1`), fait `nssm restart`, attend puis affiche les 10 dernières lignes du log de service et conclut OK / à vérifier (code 2 si `ERROR`). Paramétrable (`-NomService`, `-RepDepot`, `-NomLog` pour cibler le bon log de service ex. `ccw-scrabble-service.log` issue #173, et `-CompteService` pour reconstruire la ligne `PATH`) : sert aussi bien à `CCW-Watcher` qu'aux services multi-projets `CCW-Watcher-<NomProjet>` (issue #170). Depuis l'issue #174, accepte aussi `-FichierTokens <chemin>` : les deux valeurs sont alors **lues dans un fichier** « clé=valeur » (au lieu de `Read-Host`), ce qui permet à l'onglet CCW de poser les tokens à distance sans saisie dans la VM et sans jamais les passer en argument de commande. |
| `ajouter_projet_ccw.ps1` | **(actif, modèle multi-projets #170 ; voir aussi `creer_projet_ccw_complet.ps1`, §16.5, qui l'appelle)** Instancie un projet CCW **supplémentaire** sur le modèle multi-projets (issue #170), sans rien réinstaller. Paramétrable (`-NomProjet`, `-Depot owner/repo`, ou prompt interactif) : clone le dépôt en lecture seule dans `C:\CCW\<NomProjet>`, écrit `configs\<nom>-ccw.conf` (`NOM=<nom>-ccw`, `LABEL=for-windows`, `REP_TRAVAIL`/`PERIMETRE`=`C:\CCW\<NomProjet>`, `TOPIC_NTFY` placeholder), et enregistre un service NSSM dédié `CCW-Watcher-<NomProjet>` : `SERVICE_AUTO_START`, `AppExit Default Restart` (vrais plantages) **+ `AppExit 42 Exit`** (retrofit CCW, issue #712 — service « à la demande » dès sa création, voir encadré ci-dessous), `AppRestartDelay`, `logs\ccw-<nom>-service.log`. Idempotent (clone mis à jour par pull, service arrêté/supprimé avant recréation — donc le réglage `AppExit 42 Exit` est reposé à chaque recréation, même pour un projet déjà existant). Pose aussi les droits de démarrage/arrêt sans élévation UAC (`sc.exe sdset`, issue #717) en fin de script — même raison : `nssm remove`+`install` les effacerait sinon à chaque recréation. Ne configure **pas** `AppEnvironmentExtra` : chaque projet a son propre token dédié, posé ensuite en **une seule commande** via `finaliser_projet_ccw.ps1` (rappel affiché en fin de script). |
| `autoriser_demarrage_ccw.ps1` | **(issue #717, étape F)** À lancer **une seule fois**, en PowerShell ADMINISTRATEUR, pour les services `CCW-Watcher*` **déjà existants** au moment de l'exécution (base comprise) : accorde à `AlainW` (paramètre `-NomCompte`, SID résolu dynamiquement) le droit de démarrer/arrêter/interroger chacun **sans élévation UAC** ensuite (`sc.exe sdset`, via `ccw-commun.psm1::Autoriser-DemarrageServiceCcw`). Idempotent, affiche le résultat par service. Les services créés/recréés APRÈS cette exécution reçoivent les droits automatiquement via `ajouter_projet_ccw.ps1` (voir ci-dessus) — pas besoin de relancer ce script pour eux. |
| `lister_projets_ccw.ps1` | **(appelé à distance — issue #174)** Inventaire **JSON** des projets CCW : énumère les services `CCW-Watcher*` (NSSM), et pour chacun émet le nom du service, le projet dérivé, l'état (`running`/`stopped`) et le statut du placeholder `TOPIC_NTFY` (lu dans le config, sans jamais renvoyer la valeur réelle du topic). Sortie encadrée par `<<<CCW_JSON>>>…<<<CCW_END>>>` pour extraction fiable côté Linux. Exécuté par l'onglet CCW de l'interface web. |
| `finaliser_projet_ccw_auto.ps1` | **(appelé à distance — issue #174)** Variante **non interactive** de `finaliser_projet_ccw.ps1` : lit `TOPIC_NTFY` + les deux tokens dans un **fichier « clé=valeur »** poussé par l'appelant (jamais en argument de commande), remplace le placeholder `TOPIC_NTFY` dans le config (édition ciblée) puis **appelle** `mettre_a_jour_tokens_ccw.ps1 -FichierTokens` (aucune duplication de la logique des tokens). Supprime le fichier de valeurs dans un `finally` (nettoyage côté VM). Code de sortie = celui du script de tokens (0/2/1). |
| `finaliser_projet_ccw.ps1` | **(actif, modèle multi-projets #170)** Finalise en **une seule commande** un projet déjà créé par `ajouter_projet_ccw.ps1` (issue #173, suite #170), regroupant les 3 étapes manuelles auparavant dispersées. À partir du seul `-NomProjet` (argument ou prompt), **dérive** `CCW-Watcher-<NomProjet>`, `C:\CCW\<NomProjet>` et `configs\<nom>-ccw.conf` (même logique qu'`ajouter_projet_ccw.ps1`) et **vérifie** leur existence (sinon renvoie vers `ajouter_projet_ccw.ps1`). Puis : (1) demande `TOPIC_NTFY` (`Read-Host`, pas un secret) et remplace le placeholder `###TOPIC_NTFY_A_DEFINIR###` **dans** le config par édition ciblée (le reste du fichier préservé, UTF-8 sans BOM) ; (2) rappelle les réglages du token dédié à créer (repo unique, permissions, expiration alignée) avec une **pause** ; (3) **appelle** `mettre_a_jour_tokens_ccw.ps1` (pas de duplication) avec les paramètres déduits — dont `-NomLog ccw-<nom>-service.log` — pour la saisie masquée + pose des tokens + redémarrage + vérif des logs ; (4) résumé final selon le code renvoyé. |
| `surveiller_builds.ps1` | **(lancé manuellement — issue #370)** Surveille en continu, pendant un build en cours (PyInstaller/ISCC), les processus de build et la croissance du dossier de sortie. Paramètre `-Dossier` **obligatoire** (chemin du dossier de sortie à surveiller, ex. `installeur\output`) ; `-Processus` optionnel (liste de noms de process à surveiller, défaut `claude, ISCC, python, pyinstaller`) ; `-IntervalleSecondes` optionnel (défaut `10`). À chaque passage : affiche pour chaque process surveillé son PID/CPU/mémoire/durée de vie s'il est actif, et la taille du dossier avec le delta depuis le dernier passage et depuis le début. Exemple : `powershell -ExecutionPolicy Bypass -File provisioning\windows\surveiller_builds.ps1 -Dossier C:\CCW\actualise\installeur\output -IntervalleSecondes 15`. **Attention** : le nom de process Claude Code (`claude` par défaut dans `-Processus`) est une hypothèse à vérifier via `Get-Process` pendant un build réel — l'installeur natif Windows peut l'enregistrer sous un nom différent, auquel cas le passer explicitement en paramètre. |

**Script d'orchestration complémentaire, hors dossier `provisioning/windows/`.**
`creer_projet_ccw_complet.ps1`, placé à la **racine** du dépôt (pas dans
`provisioning/windows/`), enchaîne les scripts ci-dessus en une seule
commande pour créer un nouveau projet CCW de bout en bout — voir §16.5.

**Phase 2 (issue #147)** prépare le provisioning logiciel qui tourne UNE FOIS
Windows installé (pas encore exécuté contre une VM réelle). À noter :
`watcher.py` n'a nécessité **aucune modification** — il est déjà portable et
son `LABEL` est paramétrable par config, donc `LABEL=for-windows` dans
`ccw.conf` suffit à ce qu'il ne prenne que les issues Windows.

**Libellé d'agent dans l'ACK (issue #239).** Le message d'ACK posté à la
réception d'une issue (`✅ ACK — Issue #N reçue par watcher.py (…, projet
<nom>)`) affiche un libellé d'agent déduit automatiquement de la plateforme
(`platform.system()`) : « agent Linux » côté CCL, « agent Windows » côté CCW.
Aucune action requise sur les `.conf` existants (repli inchangé). Champ
optionnel `LIBELLE_AGENT` disponible dans n'importe quel `.conf` pour forcer
un libellé explicite si la détection automatique ne convient pas (ex.
exécution dans un conteneur ou un environnement où `platform.system()` ne
reflète pas l'agent réel) :

```
LIBELLE_AGENT = agent Windows
```

Le watcher tourne comme **vrai service Windows** enregistré via NSSM (issue #148) —
équivalent direct des services systemd du §13 : démarrage au boot **sans
session ouverte** (`SERVICE_AUTO_START`) et redémarrage automatique sur
échec (`AppExit Default Restart` + `AppRestartDelay 5000`). Cela remplace
l'ancienne tâche planifiée `-AtLogOn`, qui ne redémarrait pas au boot sans
session ; la boucle interne du watcher reste la première ligne de
robustesse.

> **Retrofit « à la demande » — `AppExit 42 Exit` (issue #712, validé en réel
> le 03/10/2026).** Le réglage ci-dessus (`AppExit Default Restart`) décrit le
> comportement sur **plantage** (NSSM relance). Depuis #712, les **services de
> projet** (`CCW-Watcher-<Projet>`, posés par `ajouter_projet_ccw.ps1`)
> reçoivent en plus `AppExit 42 Exit` : le code de sortie **42** signale
> l'**auto-extinction pour inactivité** du watcher après 20 min (issues
> #199/#200), qui n'est PAS un plantage — dans ce cas précis, NSSM laisse le
> service **éteint** au lieu de le relancer aussitôt (sans ce réglage, l'auto-
> extinction n'avait aucun effet : `Default Restart` le relançait en
> permanence, annulant l'économie de ressources visée par #199/#200).
>
> **Rallumage à la demande.** Un service de projet ainsi éteint est rallumé
> par `new_issue.py` au moment où une issue `for-windows` visant ce projet est
> **créée ou relancée**, via SSH vers le PC fixe (`app.ccw.
> demarrer_service_ccw_arriere_plan`, thread démon non bloquant) — trois
> points d'entrée couverts : le **formulaire web** (`app/issues.py::envoyer()`,
> issue #709, étape C), le dépôt dans **`issues_inbox/`** et sa **RELANCE**
> (`scripts/watcher_issues_inbox.py`, issue #711, étape D). Symétrique du
> rallumage auto déjà en place côté `for-linux` (`app.watchers.
> redemarrer_si_eteint`, issue #600/#202).
>
> **Exception volontaire : `CCW-Watcher` (service de base, sans suffixe)
> reste TOUJOURS actif** — `provisionner.ps1` ne pose PAS `AppExit 42 Exit`
> dessus, seulement `Default Restart`. Deux raisons : (1) il traite, par le
> canal central `for-windows`/Bridge_Agent, les issues des projets **sans**
> service CCW dédié (`REDACTEUR=bridge_agent`, §3.4) — le démarrage à la
> demande cherche le service du projet **visé par l'issue** et n'en trouve
> aucun dans ce cas, donc rien ne serait rallumé ; (2) il reçoit les
> délégations de CCL vers Windows créées par `gh issue create` **direct** (ex.
> #692), qui ne passent par aucun des trois points d'entrée ci-dessus et ne
> déclenchent donc aucun démarrage à la demande.
>
> **Une limite restante (démarrage à la demande non applicable) :** une
> issue `for-windows` créée par `gh issue create` **direct** (hors
> `new_issue.py`) ne déclenche rien — cas visé par l'exception ci-dessus,
> mais vaut aussi pour un projet avec service dédié si l'issue est créée hors
> interface. Dans ce cas : démarrer le service à la main, soit `nssm start
> <service>` directement sur le PC fixe, soit le bouton **Démarrer** de
> l'onglet **CCW** de l'interface web (§16.2).
>
> **`new_issue.py` natif Windows — résolu (issue #717, étape F, 04/10/2026).**
> Jusque-là, `new_issue.py` tournant **nativement sous Windows** (pas d'hôte
> SSH configuré dans ce cas — `app.ccw._preparer()` renvoie une erreur de
> config) ne pouvait pas se SSH vers lui-même pour rallumer un service CCW
> éteint : le démarrage à la demande était ignoré silencieusement. Constat
> vérifié le 04/10/2026, depuis un PowerShell **NON élevé** en `AlainW` :
> `nssm status` fonctionne, mais `nssm start` échoue avec
> « OpenService(): Access is denied » — l'hypothèse « UAC désactivé » était
> donc fausse ; le jeton d'une session normale reste bridé par l'UAC même
> pour un compte administrateur (voir « Compte NSSM » ci-dessous), alors
> qu'une session SSH d'administrateur reçoit les droits complets.
>
> Depuis #717, `app.ccw._piloter_service_ccw_action` (donc
> `demarrer_service_ccw_arriere_plan` ET les actions **Démarrer**/
> **Arrêter**/**Redémarrer** de l'onglet CCW) détecte ce cas (`os.name ==
> "nt"` + aucun hôte SSH configuré — `app.ccw._local_natif_sans_ssh()`) et
> appelle `nssm` **directement en local** (toujours en thread démon non
> bloquant pour le démarrage à la demande), sans passer par SSH — le service
> visé est alors forcément local. Comportement **Linux strictement
> inchangé** (`os.name` y vaut toujours `"posix"`, branche SSH historique
> seule utilisée). Ceci suppose les droits `sc.exe sdset` posés au préalable
> (paragraphe suivant) — sans eux, même échec « Access is denied » qu'avant.
> Échec (droits non posés, service introuvable) → journalisé clairement
> (`app.ccw`), jamais silencieux.
>
> **Retour arrière pour un service donné** (désactiver l'auto-extinction
> effective, revenir au comportement « toujours actif ») :
> ```powershell
> nssm set <service> AppExit 42 Restart
> ```
>
> **Droits de démarrage/arrêt sans élévation UAC — `sc.exe sdset` (issue
> #717).** Un service Windows a par défaut un descripteur de sécurité (SDDL)
> où seuls `SYSTEM`/`Administrateurs` peuvent le démarrer/arrêter ; un
> compte administrateur en session **normale** (jeton bridé par l'UAC,
> niveau Medium, groupe Administrators en « deny only ») n'en bénéficie PAS
> effectivement. `sc.exe sdset` ajoute une entrée dédiée à un compte précis,
> sans dépendre de son appartenance au groupe Administrateurs — ce compte
> peut alors démarrer/arrêter/interroger le service **en session normale,
> sans élévation**. Entrée ajoutée (droits START + STOP + QUERY STATUS +
> QUERY CONFIG ; SID résolu **dynamiquement** à partir du nom de compte —
> jamais codé en dur, propre à chaque PC) :
> ```
> (A;;LCSWRPWPLOCRRC;;;<SID d'AlainW>)
> ```
> Appliquée par `provisioning\windows\ccw-commun.psm1::
> Autoriser-DemarrageServiceCcw` : lecture du descripteur actuel (`sc.exe
> sdshow`, jamais l'alias PowerShell `sc`), insertion **idempotente** dans la
> section `D:` SANS retirer les entrées existantes (SYSTEM/Administrateurs/
> utilisateurs interactifs), réécriture par `sc.exe sdset`.
> - **Services déjà existants** : lancer **une seule fois**, en PowerShell
>   ADMINISTRATEUR (l'élévation n'est requise que pour POSER le droit, pas
>   pour s'en servir ensuite) :
>   ```powershell
>   powershell -ExecutionPolicy Bypass -File provisioning\windows\autoriser_demarrage_ccw.ps1
>   ```
>   applique les droits à tous les services `CCW-Watcher*` du PC (service de
>   base compris — il reste toujours actif, volontairement, cf. ci-dessus).
> - **Services créés ou recréés ensuite** : `ajouter_projet_ccw.ps1` pose les
>   droits automatiquement en fin de script (il supprime puis recrée le
>   service à chaque relance, ce qui effacerait sinon ce réglage) — aucune
>   étape manuelle supplémentaire.

> **Compte NSSM — `AlainW`, pas `LocalSystem` (issue #446).** Sur le PC fixe
> physique, le service `CCW-Watcher` tourne sous le compte **`AlainW`**
> (administrateur, mais jeton filtré par l'UAC en session normale — voir
> issue #717 ci-dessus), et non plus sous `LocalSystem`. `REP_TRAVAIL`
> pointe vers `C:\CCW_Share`, un chemin **local** au PC. La justification
> historique de `LocalSystem` — un chemin UNC (`\\VBOXSVR\CCW_Share`)
> inaccessible aux lecteurs réseau montés en session interactive, alors que
> `LocalSystem` y accédait — **ne s'applique plus** : un chemin local est
> accessible normalement à n'importe quel compte, y compris `AlainW`. Le
> paramètre `$LettrePartage` (issue #149) et sa logique de résolution de
> lettre de lecteur réseau n'ont donc plus lieu d'être.

**Renouveler les tokens du service (issue #168).** Les tokens `GH_TOKEN` et
`CLAUDE_CODE_OAUTH_TOKEN` du service `CCW-Watcher` sont passés via
`AppEnvironmentExtra` (NSSM). Piège connu : les deux paires doivent être
séparées par un **saut de ligne** `` `n`` et non par un espace — un espace
corrompt silencieusement `GH_TOKEN` (erreur « Bad credentials » à la
prochaine opération `gh`). Pour éviter de reconstruire cette chaîne à la main
à chaque renouvellement, lancer **sur le PC physique** :

```powershell
# Depuis C:\CCW\Bridge_Agent, dans une console PowerShell admin :
powershell -ExecutionPolicy Bypass -File provisioning\windows\mettre_a_jour_tokens_ccw.ps1
```

Le script demande les deux valeurs une à une (`Read-Host -AsSecureString`,
donc jamais affichées en clair), reconstruit la chaîne avec le bon
séparateur, applique `nssm set … AppEnvironmentExtra` puis
`nssm restart CCW-Watcher`, attend quelques secondes et affiche les 10
dernières lignes de `logs\ccw-service.log` pour confirmer l'absence
d'erreur d'authentification. Résumé final : OK si aucune ligne `ERROR`,
sinon invitation à vérifier manuellement (code de sortie 2).

**Modèle multi-projets — un service par projet (issue #170).** À l'origine CCW
ne surveillait qu'`AlainDelree/Bridge_Agent` (mono-projet). Il suit désormais le
**même modèle que les watchers CCL** : un clone dédié + un config dédié + un
service NSSM dédié **par projet**, pour qu'une issue `for-windows` puisse être
créée directement dans le dépôt du projet concerné (ex. `AlainDelree/Scrabble`)
plutôt que systématiquement dans Bridge_Agent. Le script
`ajouter_projet_ccw.ps1` instancie un projet supplémentaire sans rien
réinstaller :

```powershell
# Dans la VM CCW-Build, console PowerShell admin, depuis C:\CCW\Bridge_Agent.
# Exemple Scrabble (dépôt PUBLIC : aucun token requis pour le clone) :
powershell -ExecutionPolicy Bypass -File provisioning\windows\ajouter_projet_ccw.ps1 `
    -NomProjet Scrabble -Depot AlainDelree/Scrabble
# → clone C:\CCW\Scrabble, config configs\scrabble-ccw.conf,
#   service CCW-Watcher-Scrabble, log logs\ccw-scrabble-service.log.
```

`watcher.py` est **inchangé** : générique par conception, `LABEL` et
`REP_TRAVAIL` sont pilotés par config, donc un deuxième service qui pointe vers
`configs\scrabble-ccw.conf` suffit — aucune modification de code.

**État actuel (issue #547).** 5 services NSSM tournent ainsi en
production, tous confirmés à l'état `running` via l'onglet CCW : `CCW-Watcher`
(base, Bridge_Agent) + `CCW-Watcher-actualise`, `-alchess`, `-rummikub`,
`-scrabble`. Voir §16.5 pour `creer_projet_ccw_complet.ps1`, qui orchestre
en une commande la création (ce paragraphe) et la finalisation (topic +
tokens + `PATH`, ci-dessous) d'un nouveau projet.

**Finaliser en une seule commande (issue #173).** Là où il fallait auparavant
trois étapes manuelles dispersées (éditer `TOPIC_NTFY` à la main dans le config,
créer le token GitHub, puis relancer `mettre_a_jour_tokens_ccw.ps1` avec les bons
`-NomService`/`-RepDepot` reconstitués), `finaliser_projet_ccw.ps1` enchaîne le
tout à partir du **seul** nom du projet :

```powershell
# Dans la VM CCW-Build, console PowerShell admin, depuis C:\CCW\Bridge_Agent :
powershell -ExecutionPolicy Bypass -File provisioning\windows\finaliser_projet_ccw.ps1 `
    -NomProjet Scrabble
```

Il dérive lui-même le service `CCW-Watcher-Scrabble`, le dossier `C:\CCW\Scrabble`
et le config `configs\scrabble-ccw.conf` (même logique qu'`ajouter_projet_ccw.ps1`),
vérifie qu'ils existent (sinon il renvoie vers `ajouter_projet_ccw.ps1`), demande
`TOPIC_NTFY` et l'écrit **directement** dans le config (remplacement ciblé du
placeholder), rappelle la marche à suivre pour **créer le token dédié** (voir
ci-dessous) avec une pause, puis appelle `mettre_a_jour_tokens_ccw.ps1` pour la
saisie masquée + pose des deux tokens, redémarre le service et vérifie les logs.
La seule action GitHub restante — forcément manuelle car dans le navigateur — est
la **création** du token pendant la pause.

**Un token GitHub dédié PAR projet, mais à expiration ALIGNÉE (issue #170).**
Chaque service CCW (`CCW-Watcher`, `CCW-Watcher-Scrabble`, futurs projets) a son
**propre** token fine-grained, limité à son **seul** dépôt — pas un token unique
élargi à plusieurs dépôts. Avantages : rayon de dégâts limité en cas de fuite,
révocation ciblée sans affecter les autres projets, cohérent avec l'isolation
déjà pratiquée côté CCL (topics ntfy et configs distincts par projet). Réglages
du token, à créer manuellement sur GitHub (Settings → Developer settings →
Fine-grained tokens) :

- **Repository access** → *Only select repositories* → le dépôt du projet
  **uniquement** (ex. `AlainDelree/Scrabble`) ;
- **Permissions** → *Issues* = **Read and write**, *Metadata* = **Read-only**
  (Metadata est requis implicitement) ;
- **Expiration** → **la MÊME date que le token Bridge_Agent** (≈ **17 octobre
  2026**) — surtout **ne pas laisser dériver** vers une autre échéance.

> **Règle d'or :** tout nouveau token CCW réutilise la date d'expiration commune
> (≈ mi-octobre 2026) pour ne garder **qu'une seule fenêtre de maintenance** —
> Windows, le token Bridge_Agent et tous les tokens projets expirent ensemble.
> Au renouvellement, on recale simplement tout le monde sur la nouvelle date
> commune. Ne créer aucun token depuis ce dépôt (action manuelle GitHub) : le
> script se contente de rappeler la marche à suivre.

### 16.2 Onglet « CCW » de l'interface web (issue #174, SSH depuis #447)

**Rôle.** Piloter CCW (le PC fixe physique et ses projets) **entièrement
depuis Linux**, via l'onglet **CCW** de `new_issue.py` — même style que les
autres onglets. Il **remplace l'usage manuel de PowerShell sur le PC** pour
les opérations courantes : plus besoin d'ouvrir une console PowerShell sur le
PC fixe ni de copier-coller hôte↔PC (source d'erreurs récurrentes). Les
scripts PowerShell existants restent l'**implémentation sous-jacente** :
l'onglet les pousse et les exécute à distance via **SSH/SCP** (copie par
`scp`, exécution par `ssh ... powershell.exe -File`). Côté serveur, toute la
logique vit dans `app/ccw.py` (routes `/ccw/*`).

**Ce que fait l'onglet :**

1. **Projets CCW existants** — liste les services `CCW-Watcher*` du PC fixe
   (via `lister_projets_ccw.ps1`, poussé puis exécuté à distance par SSH) :
   nom du projet, service, état (`running`/`stopped`) et indicateur si
   `TOPIC_NTFY` est encore un placeholder. **Rafraîchi à la demande** (pas de
   polling : chaque appel déclenche un aller-retour SSH complet).
2. **Ajouter un projet** — champs *nom* + *dépôt owner/repo*, bouton **Créer**
   qui pousse puis exécute `ajouter_projet_ccw.ps1` à distance (clone +
   config + service) et affiche sa sortie.
3. **Finaliser un projet** — champs *projet* (ou sélection dans la liste du
   point 1), `TOPIC_NTFY`, `GH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`. Bouton
   **Finaliser** qui écrit le topic **et** pose les deux tokens en enchaînant,
   puis redémarre le service et affiche les dernières lignes de log
   (via `finaliser_projet_ccw_auto.ps1`).
4. **Démarrer / arrêter / redémarrer un service** — actions indépendantes
   pilotant le service NSSM d'un projet (`nssm start|stop|restart <service>`,
   exécuté à distance), sans toucher au topic ni aux tokens (issues #180,
   #203). Le nom exact du service est résolu via `lister_projets_ccw.ps1`
   (source de vérité unique — gère notamment le cas spécial
   `Bridge_Agent` → service `CCW-Watcher` sans suffixe).
5. **Nettoyer verrous CCW** — bouton « 🔒 Nettoyer verrous CCW + redémarrer »
   (issue #431) : arrête le service, supprime les `.lock` orphelins du
   dossier de verrous du projet, puis relance le service, en un seul
   aller-retour SSH (via `nettoyer_verrous_ccw.ps1`).

**Configuration SSH.** Lue au moment de l'action (jamais codée en dur), par
ordre de priorité pour chaque valeur — variable d'environnement d'abord,
sinon fichier local `configs/ccw_ssh.conf` (gitignoré, comme les
`configs/*.conf`, format « CLÉ = valeur ») :

1. hôte du PC fixe (IP ou nom réseau local) : `CCW_SSH_HOTE` / `HOTE` ;
2. utilisateur SSH : `CCW_SSH_UTILISATEUR` / `UTILISATEUR` (défaut `AlainW`) ;
3. chemin de la clé privée SSH sur CCL : `CCW_SSH_CLE_PRIVEE` / `CLE_PRIVEE`.

Prérequis manuels (hors périmètre de ce code) : OpenSSH Server activé sur le
PC fixe, clé publique installée dans `authorized_keys` de l'utilisateur SSH.
Authentification **par clé uniquement** (`BatchMode=yes` — jamais de prompt
interactif, un serveur web ne peut pas répondre à un mot de passe),
acceptation silencieuse d'une nouvelle clé d'hôte (`StrictHostKeyChecking=
accept-new`, réseau local de confiance), délai de connexion court
(`ConnectTimeout=10`) pour échouer vite si le PC est injoignable.
Configuration absente/incomplète → l'onglet affiche un message clair, aucune
erreur Flask brute. Toute erreur SSH/SCP (PC éteint ou injoignable, timeout,
script distant en échec) remonte de la même façon un message lisible dans
l'interface.

**Sécurité des tokens (impératif).** Les tokens ne transitent **jamais** en
argument de ligne de commande (invisibles dans les process/event logs
Windows) et ne sont **jamais journalisés** côté Linux. Ils sont écrits dans
un **fichier temporaire local à permissions `0600`**, poussé sur le PC fixe
via `scp`, lu côté PC par PowerShell (`-FichierValeurs`), puis supprimé des
**deux côtés** dans un `finally` (Python côté hôte, PowerShell côté PC).

### 16.3 Procédure — builder un projet Windows

**Envoyer un build :** créer une issue `for-windows` dans `bridge_agent` via
`new_issue.py` (champ `| LABELS | for-windows |`). Pas de pattern chef/ouvrier
nécessaire — l'issue est directe.

**Template d'issue build (à adapter par projet) :**

Étape 1 — Si `C:\CCW_Share\CCW\<projet>\` n'existe pas ou n'est pas un dépôt
git : cloner `https://github.com/AlainDelree/<Projet>.git` dans
`C:\CCW_Share\CCW\<projet>\`. Sinon : `git pull --ff-only`.

Étape 2 — `pip install -r requirements.txt` depuis `C:\CCW_Share\CCW\<projet>\`.

Étape 3 — Build PyInstaller depuis `C:\CCW_Share\CCW\<projet>\` :

```bash
python -m PyInstaller --noconfirm --onedir --noconsole --name <Projet> <entrypoint>.py
```

Étape 4 — Confirmer la présence de
`C:\CCW_Share\CCW\<projet>\dist\<Projet>\<Projet>.exe` et l'absence d'erreur
PyInstaller. Ne pas committer ni pousser.

**Récupération des artefacts :** manuelle, depuis Linux via le point de
montage réseau local vers `C:\CCW_Share` (accès réseau local au PC
physique ; chemin exact de montage côté CCL selon la configuration réseau
en place).

**Dépôts sources :** publics sur GitHub — aucun token Contents requis.
Le token `CCW-Watcher` (Issues read/write sur Bridge_Agent) suffit.

**Note staging local (issue #297) :** pattern général de contournement
d'une corruption de fichiers constatée par le passé, et checklist par
projet buildé (dont Scrabble) — voir `BUILD_WINDOWS_CCW.md`.

### 16.4 Interrompre une issue CCW coincée (issue #287)

**Symptôme :** le watcher `CCW-Watcher` détecte bien l'issue à chaque cycle
mais log en boucle, sans jamais progresser :

```
Issue différée : un autre traitement détient déjà le verrou sur C:\CCW_Share\
```

**Cause :** un fichier verrou laissé dans
`C:\CCW\Bridge_Agent\logs\verrous\` n'a pas été nettoyé — process tué
brutalement, ou redémarrage NSSM du service sans libération propre du
verrou en cours. Le watcher refuse alors de retraiter l'issue tant que ce
fichier existe, même après redémarrage.

> **Atténué depuis #584.** Si le redémarrage du service (étape 1 ci-dessous)
> se produit AVANT la reprise automatique du verrou, `acquerir_verrou` sonde
> désormais le PID du watcher propriétaire (champ `pid=` du fichier verrou) :
> confirmé mort, le verrou est repris immédiatement au cycle suivant, sans
> attendre l'écoulement de la péremption par ancienneté (qui pouvait
> auparavant dépasser 45 minutes sur un projet à `TIMEOUT` élevé — incident
> #583, cause de cette procédure). La suppression manuelle ci-dessous reste
> le repli si la sonde ne peut pas conclure (PID recyclé par l'OS pour un
> autre process, ou blocage persistant pour toute autre raison).

**Procédure manuelle :**

1. Redémarrer le service (ne suffit pas seul, mais nécessaire) :

   ```powershell
   nssm restart CCW-Watcher
   ```

2. Lister puis supprimer le(s) fichier(s) verrou restant(s) :

   ```powershell
   Get-ChildItem C:\CCW\Bridge_Agent\logs\verrous\ -Filter "*.lock"
   Remove-Item C:\CCW\Bridge_Agent\logs\verrous\<fichier>.lock
   ```

**Bouton « Interrompre » (issue #323, implémenté).**

> **⚠️ Obsolète sur PC physique (issue #446).** Comme pour l'onglet CCW
> (§16.2), ce bouton s'appuie sur l'ancien mécanisme de pilotage à distance
> de la VM : il est **inopérant** sur un PC physique. En attendant sa
> refonte, utiliser la **procédure manuelle** décrite ci-dessus
> (redémarrage du service + suppression des `.lock`).

Le bouton ⛔ « Interrompre
cette issue », affiché sur toute issue ouverte ni `done` ni `needs-human` dans
l'interface, automatise cette procédure à distance depuis Linux pour les
issues `for-windows` : `POST /interrompre` (`app/interruption.py::
interrompre_windows`) copie et exécute `provisioning/windows/
interrompre_projet_ccw.ps1` à distance — arrêt du service NSSM (`nssm stop
<Service>`), vérification bornée (~5 s, kill
ciblé si besoin) que l'arbre de process du service (watcher + éventuel
`claude` orphelin) est bien mort, puis suppression des `.lock` de
`<RepDepot>\logs\verrous\` **uniquement** si cet arbre est confirmé mort —
sinon le verrou est volontairement laissé en place, pour ne jamais risquer un
double traitement. Le label `needs-human` et un commentaire de traçabilité
sont toujours postés sur GitHub ; l'issue n'est **pas** fermée et le watcher
CCW n'est **jamais** relancé automatiquement (relance manuelle via l'onglet
CCW). Voir § « Interrompre une issue bloquée » (§13) pour le pendant côté CCL
et le détail commun de l'interface (bouton, route Flask, statuts).

### 16.5 Créer un nouveau projet CCW en une commande (`creer_projet_ccw_complet.ps1`, issue #492)

**Rôle.** Script d'orchestration qui enchaîne, en **une seule commande**,
les 3 étapes mécaniques nécessaires pour ajouter un projet au modèle
multi-projets actif (#170, cf. plus haut dans ce §16) :

1. Clone + `.conf` + service NSSM, via le script existant
   `provisioning\windows\ajouter_projet_ccw.ps1` — **appelé**, pas
   dupliqué.
2. Remplacement ciblé du placeholder `TOPIC_NTFY` dans le `.conf`
   fraîchement créé.
3. Saisie masquée des deux tokens (`GH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`),
   **testés à blanc avant application** (`gh repo view <Depot>` /
   `claude --print "réponds juste OK"` — échouer vite et clairement plutôt
   que découvrir un 401 après coup) ; puis écriture de
   `AppEnvironmentExtra` avec un **`PATH` explicite** incluant
   `C:\Users\AlainW\.local\bin` (fix du piège PATH-au-boot constaté avec
   Scrabble : un service NSSM démarré au boot n'hérite pas du `PATH`
   utilisateur, donc pas de `claude.exe`) ; et redémarrage du service avec
   affichage des 10 dernières lignes de son log.

Contrairement à `finaliser_projet_ccw.ps1` (tableau de provisioning
ci-dessus), les étapes 2 et 3 ne délèguent pas à
`mettre_a_jour_tokens_ccw.ps1` : elles sont réimplémentées directement dans
ce script, pour intégrer le test à blanc des tokens et le correctif `PATH`
— deux besoins apparus après coup (issue #492 bis) que le script de tokens
historique ne couvrait pas.

**Emplacement et usage.** Placé à la **racine** du dépôt (pas dans
`provisioning\windows\`), à exécuter depuis `C:\CCW\Bridge_Agent` :

```powershell
cd C:\CCW\Bridge_Agent
powershell -ExecutionPolicy Bypass -File creer_projet_ccw_complet.ps1 `
    -NomProjet actualise -Depot AlainDelree/Actualise -TopicNtfy <topic>
```

- `-NomProjet` (obligatoire) — dérive `CCW-Watcher-<NomProjet>`,
  `C:\CCW\<NomProjet>` et `configs\<nom>-ccw.conf` (même logique
  qu'`ajouter_projet_ccw.ps1`/`finaliser_projet_ccw.ps1`).
- `-Depot` (obligatoire) — dépôt GitHub du projet, au format `owner/repo`.
- `-TopicNtfy` (optionnel — une valeur de secours est câblée dans le
  script) — topic ntfy dédié au projet.

**Prérequis manuel (hors périmètre du script).** Créer **au préalable**, à
la main sur GitHub (Settings → Developer settings → Fine-grained tokens),
le token GitHub **dédié** au projet — repository access limité à `<Depot>`
uniquement, permissions *Issues* = Read and write, *Metadata* = Read-only,
expiration alignée sur les autres tokens CCW (cf. règle d'or plus haut) —
et avoir `claude setup-token` prêt à lancer pour générer le second token.
Le script s'arrête (code de sortie 1) et invite à vérifier/recréer le
token concerné si l'un des deux manque ou échoue au test à blanc.

### 16.6 Bootstrap automatique via le champ `CREATION` (issues #554/#556, 2/3)

**But.** Créer un service CCW dédié **de bout en bout à partir d'une seule
issue GitHub**, sans aucune session `claude` (décision #554 §2.5) : les
scripts PowerShell déjà testés en §16.5/tableau de provisioning
(`ajouter_projet_ccw.ps1` puis `finaliser_projet_ccw_auto.ps1
-FichierValeurs`) sont appelés directement par `watcher.py`, en Python
déterministe. Le problème résolu est la transmission **asynchrone** de
`GH_TOKEN`/`CLAUDE_CODE_OAUTH_TOKEN` : le PC CCW peut être éteint au moment
où l'issue est créée, donc les tokens ne peuvent pas transiter en clair —
d'où le chiffrement asymétrique avec la paire de clés de bootstrap générée
par `provisionner.ps1` (issue #554, 1/3, `C:\CCW\cles_bootstrap\`).

**Détection et traitement (`watcher.py`, issue #556).** `_traiter_issue_
synchrone` détecte le champ `| CREATION | oui |` **tôt dans le dispatch**,
juste après la garde d'idempotence habituelle et AVANT tout ce qui touche au
pipeline `lancer_claude` (mode, périmètre, verrou) — `creation_demandee(body)`
→ délégation complète à `_traiter_creation_projet_ccw`, qui gère seule tout
le cycle de vie de l'issue (aucun retour au dispatch normal). Sans objet sur
n'importe quel autre canal/projet : en pratique n'a de sens que posté sur le
dépôt `AlainDelree/Bridge_Agent` avec le label `for-windows` (canal unifié,
service `CCW-Watcher`, seul habilité à écrire les 4 services concernés —
chicken-and-egg sinon : le nouveau projet n'a par définition pas encore de
token pour recevoir sa propre issue de bootstrap).

**Format attendu du corps de l'issue.** Six champs dans le tableau d'en-tête
(en plus des champs standards SOURCE/DEST/…, §6) :

```markdown
| CREATION              | oui |
| CREATION_NOM_PROJET   | <NomProjet> |
| CREATION_DEPOT        | <owner/repo> |
| CREATION_TOPIC_NTFY   | <topic ntfy dédié> |
| CREATION_GH_TOKEN     | <token GH_TOKEN chiffré, base64> |
| CREATION_OAUTH_TOKEN  | <token CLAUDE_CODE_OAUTH_TOKEN chiffré, base64> |
```

- `CREATION` : déclencheur. Valeurs actives reconnues : `oui`/`true`/`vrai`
  (insensible à la casse) ; absent ou toute autre valeur → dispatch normal
  inchangé (comportement historique, aucun risque de régression).
- `CREATION_NOM_PROJET` / `CREATION_DEPOT` : passés **tels quels** à
  `ajouter_projet_ccw.ps1 -NomProjet -Depot` (même validation qu'un appel
  manuel — nom sans espace, dépôt au format `owner/repo`).
- `CREATION_TOPIC_NTFY` : passé tel quel dans le fichier de valeurs
  (`TOPIC_NTFY=`, voir plus bas).
- `CREATION_GH_TOKEN` / `CREATION_OAUTH_TOKEN` : les deux tokens, **chiffrés
  individuellement** avec la clé PUBLIQUE de bootstrap (`bootstrap_publique.
  pem`, récupérée depuis CCW — cf. §554 1/3), puis encodés en base64 **sur
  une seule ligne** (`base64 -w0` ou équivalent — indispensable pour tenir
  dans une cellule de tableau markdown). Convention de chiffrement, à
  respecter EXACTEMENT côté formulaire (issue à venir, 3/3) :

  ```bash
  # Une seule fois : récupérer bootstrap_publique.pem depuis CCW (§554 1/3).
  echo -n "<token en clair>" | openssl pkeyutl -encrypt \
      -pubin -inkey bootstrap_publique.pem \
      -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 \
      -out token.bin
  base64 -w0 token.bin        # → valeur du champ CREATION_GH_TOKEN/CREATION_OAUTH_TOKEN
  ```

  **Padding OAEP/SHA-256 impératif des deux côtés** (chiffrement côté
  formulaire, déchiffrement côté `watcher.py`/`dechiffrer_token_bootstrap`)
  — propriété volontaire d'OAEP : un mauvais padding fait **échouer**
  `openssl pkeyutl -decrypt` plutôt que de réussir silencieusement avec un
  résultat corrompu, contrairement au padding PKCS#1 v1.5 historique
  (`RSA genpkey`/`rsa_keygen_bits:3072`, issue #554 — la taille de clé
  n'impose aucune contrainte de padding, choisi indépendamment ici).

**Comportement précis de `watcher.py` (issue #556).**

1. Extraction des 6 champs (`extraire_champs_creation`) ; un seul manquant
   → échec **définitif** immédiat (`needs-human`, aucun retry, aucun script
   PowerShell ni déchiffrement tenté) — erreur de configuration/issue, pas
   un échec transitoire, même logique que `REPO_CIBLE`/`SOUS_DOSSIER`.
2. **Retrait immédiat** des deux tokens chiffrés du corps GitHub
   (`gh issue edit --body-file`, remplacés par `<retiré après application>`)
   — AVANT même la tentative de déchiffrement, dès que les valeurs sont en
   mémoire : limite le temps d'exposition résiduel (§2.4 de #554).
   Best-effort (un échec ici ne bloque pas le bootstrap, juste journalisé).
3. Résolution robuste du chemin `openssl` (`_resoudre_openssl`) : PATH →
   installation manuelle Windows documentée en #557
   (`C:\Program Files\OpenSSL-Win64\bin\openssl.exe`, **pas** sur le PATH par
   défaut sur CCW) → repli `usr\bin` de Git pour Windows (même binaire que
   celui utilisé par `provisionner.ps1` pour la GÉNÉRATION des clés,
   `Resoudre-OpenSSL` côté PowerShell — dupliqué en Python plutôt que
   dot-sourcé, cette fonction n'ayant besoin que d'un chemin).
4. Déchiffrement des deux tokens avec `C:\CCW\cles_bootstrap\bootstrap_
   privee.pem` (chemin dérivé de `DOSSIER_SCRIPT.parent` — jamais un
   `C:\CCW` en dur — puisque `watcher.py` vit toujours dans
   `<RepCCW>\Bridge_Agent`, cf. plus haut dans ce §16).
5. Écriture d'un fichier temporaire « clé=valeur » **au format EXACT** déjà
   lu par `finaliser_projet_ccw_auto.ps1 -FichierValeurs` (vérifié en lisant
   le script avant d'écrire ce code — identique à celui déjà produit par
   `app/ccw.py`, `ccw_finaliser_projet`) : trois lignes `TOPIC_NTFY=`/
   `GH_TOKEN=`/`CLAUDE_CODE_OAUTH_TOKEN=`, UTF-8, **aucun espace autour du
   `=`** (`Lire-ValeurFichier` côté PowerShell ne rogne que la clé, pas la
   valeur).
6. Appel séquentiel `ajouter_projet_ccw.ps1 -NomProjet -Depot` puis
   `finaliser_projet_ccw_auto.ps1 -NomProjet -FichierValeurs` (PowerShell
   **local** — `watcher.py` tourne déjà sur la machine CCW cible,
   contrairement à l'onglet CCW de l'interface web qui pilote la même paire
   de scripts à distance via SSH, `app/ccw.py`). Sortie complète des deux
   scripts capturée pour le compte-rendu.
7. Suppression du fichier de valeurs en deux lignes de défense : le
   `finally` PowerShell de `finaliser_projet_ccw_auto.ps1` (déjà en place),
   PUIS un nettoyage Python en repli (couvre le cas où le script n'a jamais
   démarré ou a planté avant son propre `finally`) — même prudence que
   `app/ccw.py`.
8. Selon le résultat : commentaire de compte-rendu (log complet des deux
   scripts en accordéon `<details>`) + fermeture de l'issue si succès (codes
   0 et 2 — 2 = tokens appliqués mais vérification finale non concluante,
   signalé en avertissement, pas un échec), ou `needs-human` + log complet
   en commentaire si échec (code ≠ 0/2, timeout, script introuvable, erreur
   de déchiffrement…).

**Sans objet pour l'agent Linux (CCL).** `_traiter_creation_projet_ccw`
vérifie `platform.system() == "Windows"` avant toute tentative réelle
(scripts PowerShell inexistants sur CCL) — échec propre et explicite
(`needs-human`) plutôt qu'une exception si le champ apparaissait par erreur
sur un canal `for-linux`.

**Test sans vraie issue GitHub ni machine CCW réelle** (sur le modèle du
test unitaire `SOUS_DOSSIER` de #550) :
`tests/test_creation_bootstrap_ccw_556.py` — extraction/détection des
champs, non-collision `CREATION`/`CREATION_NOM_PROJET` (préfixe partagé),
retrait des tokens du corps, résolution `openssl` (3 replis), chiffrement/
déchiffrement RÉEL via un openssl local, chemin complet de
`_traiter_creation_projet_ccw` (succès/champ manquant/dry-run, faux `gh` et
faux `powershell` sur le `PATH`), et un scénario bout en bout via
`traiter_issue` vérifiant qu'un faux `claude` marqueur n'est **jamais**
touché.

**Formulaire web générant ces 6 champs automatiquement : voir §16.7
(issue #559, 3/3 — chantier complet).**

### 16.7 Case « Projet CCW » du formulaire de création de projet (issue #559, 3/3 ; ordre du flux corrigé par #560)

**But.** Dernière brique du chantier « Projet CCW » (#553 conception → #554
clés → #555/#556/#557 traitement `CREATION` validé en conditions réelles) :
une case à cocher dans le modal « Nouveau projet » (`templates/index.html`)
qui automatise ce que §16.6 documentait comme fait « à la main » —
récupérer la clé publique, chiffrer les 2 tokens, construire le corps de
l'issue `CREATION`, créer les 2 issues croisées. Module dédié
`app/projet_ccw.py` (même séparation que `app/ccw.py`), **jamais** de
modification de `app/nouveau_projet.py` : appelé par le front-end
SÉPARÉMENT de la création classique du projet CCL (`POST /nouveau-projet`,
`np_cli.creer_projet`), jamais dans le même clic/submit.

**Correction d'ordre (issue #560).** La version initiale (#559) affichait
les instructions de token **dès que la case était cochée**, donc **avant**
que l'utilisateur clique « Créer le projet » — alors que GitHub exige de
choisir un dépôt **existant** au moment de créer un token fine-grained.
Chicken-and-egg réel : impossible de scoper un token sur un dépôt qui n'est
créé qu'à la soumission. Le flux est maintenant scindé en 2 étapes
séquentielles :
1. Cocher « Projet CCW » + cliquer « Créer le projet » crée le projet CCL
   normalement (dépôt GitHub inclus) — la case cochée n'affiche à ce stade
   qu'un bloc d'information (`#np-ccw-bloc`) SANS champ de token, plus le
   bouton indépendant « Rafraîchir la clé publique » (n'a pas besoin du
   dépôt).
2. Une fois `POST /nouveau-projet` revenu en succès (`res.depot` connu, donc
   le dépôt confirmé créé), le front-end (`static/js/app.js::
   npCcwAfficherPostBloc`) masque le bloc d'information et révèle
   `#np-ccw-post-bloc` : instructions de scoping **avec le nom réel du
   dépôt** injecté, les 2 champs tokens, et le bouton dédié « Finaliser le
   bootstrap CCW » (`npCcwFinaliser`) — c'est ce clic, et lui seul, qui
   appelle `POST /projet-ccw/bootstrap`. Un échec y laisse le bloc de
   saisie affiché (nouvelle tentative possible sans recréer le projet) ;
   un succès le masque au profit de l'encart de confirmation habituel.

Revérifié côté **serveur** (jamais confiance seule au JS) :
`bootstrap_projet_ccw` refuse désormais explicitement si le dépôt cible
n'existe pas encore (`_depot_existe_deja`, `gh repo view`) — garde-fou pour
le cas où la route serait appelée hors du parcours normal du formulaire.

**Décision — cache local de la clé publique de bootstrap (point le plus
ouvert de la conception #553).** La clé publique
(`C:\CCW\cles_bootstrap\bootstrap_publique.pem`, #554) n'est **pas**
récupérée par un aller-retour SSH à chaque création de projet — cela
réintroduirait exactement la dépendance à « CCW allumé » que ce chantier
vise à éviter (la case doit fonctionner même PC éteint). Elle est mise en
cache localement dans `configs/ccw_bootstrap_publique.pem` (gitignoré :
état local de la machine CCL, spécifique à l'instance CCW courante, sans
intérêt dans l'historique git — régénérée à chaque réinstallation de CCW,
cf. `REINSTALLATION_CCW.md` §8). **Rafraîchissement MANUEL** : bouton « 🔄
Rafraîchir la clé publique » dans le bloc d'instructions du formulaire
(`GET /projet-ccw/cle-publique/etat` pour l'état affiché avant soumission,
`POST /projet-ccw/rafraichir-cle` pour le rafraîchir), réutilisant le
mécanisme SSH déjà en place et testé (`app/ccw.py::_charger_config_ssh` /
`OPTIONS_SSH`, scp `C:/CCW/cles_bootstrap/bootstrap_publique.pem` →
cache local) — **seul** point de `app/projet_ccw.py` qui exige CCW allumé.
À relancer après une (première génération ou) rotation de la paire de
clés côté CCW. Si le cache est absent au moment de la soumission :
`/projet-ccw/bootstrap` refuse proprement (message explicite), aucune
issue n'est créée.

**Formulaire (`templates/index.html`, `static/js/app.js`).** Case
« Projet CCW » à côté des options existantes du modal. Cochée → affichage
immédiat (JS pur, aucun aller-retour serveur) d'un bloc d'information
(`#np-ccw-bloc`, **sans champ de token** — voir correction #560 ci-dessus).
Les instructions de scoping (repo dédié, permissions `Issues: Read and
write` / `Metadata: Read-only`, `claude setup-token`) et les 2 champs
`type="password"` (GH_TOKEN, CLAUDE_CODE_OAUTH_TOKEN) n'apparaissent que
dans `#np-ccw-post-bloc`, révélé APRÈS le succès de la création du dépôt.
Validation stricte **côté client ET serveur** : à la création, seul le
topic ntfy est exigé côté client (le topic est **exigé explicitement**
plutôt que de résoudre le défaut serveur silencieusement — évite toute
divergence entre le topic CCL réellement écrit dans le `.conf` du nouveau
projet et celui transmis à l'issue CCW) ; les 2 tokens ne sont exigés
qu'à l'étape 2, juste avant l'appel à `/projet-ccw/bootstrap`.

**Séquence côté serveur (`app/projet_ccw.py::bootstrap_projet_ccw`,
`POST /projet-ccw/bootstrap`, appelée par le JS au clic sur « Finaliser le
bootstrap CCW », séparément de `/nouveau-projet`) :**
1. Validation (nom/dépôt/topic transmis, 2 tokens non vides, cache de clé
   publique présent, **dépôt cible existant** via `_depot_existe_deja`,
   #560) — sinon échec propre, aucune issue créée.
2. Chiffrement des 2 tokens (`_chiffrer_token`, RSA/OAEP-SHA256, base64 sur
   une seule ligne) — miroir exact, côté chiffrement, de
   `dechiffrer_token_bootstrap` (`watcher.py`, §16.6) : même padding, même
   encodage, vérifié par aller-retour réel en test (voir plus bas).
3. Issue **CCL** créée en premier sur `AlainDelree/Bridge_Agent`
   (`bridge,for-linux,mode_write`) : corps purement informatif depuis #602
   (les 2 anciennes étapes manuelles — tableau `$Projets` de
   `reinstaller_projets_ccw.ps1` et tableau de rappel de
   `REINSTALLATION_CCW.md` §7 — sont caduques depuis #597, dérivation
   dynamique), sert surtout de support à la cross-référence avec l'issue CCW.
4. Issue **CCW** créée ensuite, même dépôt (`bridge,for-windows,mode_write`,
   canal unifié) : corps au format EXACT du §16.6 (les 6 champs
   `CREATION*`), référence l'issue CCL. Traitée par `watcher.py` (#556)
   sans aucune session `claude` (décision #554 §2.5) — si CCW est éteint,
   elle attend simplement dans la file.
5. Commentaire de référence croisée posté sur l'issue CCL (numéro de
   l'issue CCW). Best-effort : un échec ici ne remet pas en cause le
   succès des 2 créations.
6. Démarrage best-effort du watcher `for-linux` de `bridge_agent` (même
   logique que `app.issues.envoyer`, issue #202).

**Anti-double-soumission :** `_issue_ouverte_meme_titre` (`app/issues.py`,
#189, déjà en place) réutilisé avec un titre déterministe par projet
(`_titre_issue_ccl`/`_titre_issue_ccw`), plus désactivation du bouton
« Créer » côté JS dès le premier clic (mécanisme déjà existant du modal,
issue #99).

**Échec partiel assumé** (§4 de la conception #553, pas de mécanisme
transactionnel) : si l'issue CCW échoue après que l'issue CCL a réussi, la
réponse renvoie quand même le numéro/l'URL de l'issue CCL déjà créée —
Alain peut réessayer manuellement le volet CCW sans dupliquer le volet CCL.

**Confirmation utilisateur :** encart dédié (`static/js/app.js::
npCcwBootstrap`) affichant les liens directs vers les 2 issues créées, avec
le rappel explicite que l'issue CCW attend simplement dans la file si CCW
est éteint — aucune action supplémentaire nécessaire.

**Test sans vraie machine CCW ni vraie issue GitHub** (même technique que
`tests/test_creation_bootstrap_ccw_556.py`) :
`tests/test_projet_ccw_559.py` — chiffrement réel (aller-retour avec
`watcher.dechiffrer_token_bootstrap`, y compris le cas mauvaise clé),
corps des 2 issues (celui de l'issue CCW vérifié **parsable** par
`watcher.creation_demandee`/`extraire_champs_creation` — le verrou anti-
régression le plus important de ce fichier), titres déterministes,
création d'issue via un faux `gh` (succès + anti-doublon), et la route
`bootstrap_projet_ccw` complète de bout en bout (validations — y compris le
refus propre si le dépôt n'existe pas encore, garde-fou #560 — chemin de
succès avec déchiffrement réel des tokens postés, cross-référence,
démarrage du watcher neutralisé pour ne jamais lancer un vrai sous-
processus pendant le test).

---

## 17. Notifications centralisées — détection serveur des transitions (issue #187)

**Problème résolu.** Historiquement, c'est `watcher.py` qui émet le bip / la
bulle bureau (`notify-send`) / le push `ntfy` à la fin d'une issue **qu'il
traite**. Cela marche bien pour **CCL** (le watcher tourne sur le ThinkPad
d'Alain). Mais pour **CCW**, le watcher tourne **dans la VM Windows** : son bip
et sa bulle bureau y restent, invisibles pour Alain ; seul le `ntfy` (push
téléphone) sortirait — et ferait alors doublon avec toute notification
centralisée. Il manquait donc une notification **locale au ThinkPad** pour les
transitions traitées par CCW.

**Principe : polling GitHub côté `new_issue.py`, zéro appel réseau depuis la VM.**
Plutôt que la VM CCW ouvre un canal réseau vers l'hôte (surface d'attaque,
NAT, secret partagé — **approche écartée**), c'est `new_issue.py` — qui tourne
en permanence sur le ThinkPad — qui **détecte lui-même** les transitions en
interrogeant GitHub via `gh` (exactement comme il le fait déjà pour l'onglet
Résultats et les badges). La VM CCW continue de n'écrire **que** sur GitHub
(labels, commentaires) ; `new_issue.py` lit ces écritures par polling et
déclenche bip/`notify-send`/`ntfy` **localement**, sur le ThinkPad, quel que
soit l'agent (CCL **ou** CCW) à l'origine.

```
watcher CCL/CCW → écrit sur GitHub (ferme + `done`, ou pose `needs-human`)
                        ↓  (aucun appel réseau VM → hôte)
new_issue.py (ThinkPad) → polling gh → détecte la transition → bip/bulle/ntfy
```

**Ce qui a été mis en place :**

- **Module partagé `notifications.py`** (racine du dépôt) : factorise
  `bip()` / `notifier_bureau()` / `notifier_ntfy()` / `notifier()`, sans état ni
  dépendance à l'objet `CFG` de `watcher.py` ni à Flask (tout leur est passé en
  argument). Importé par **les deux** programmes. `watcher.py` conserve des
  enveloppes minces qui délèguent à ce module — ses sites d'appel sont inchangés.
  `TOPIC_NTFY` est **facultatif** dans le `.conf` (issue #667, ne fait plus
  partie de `CHAMPS_REQUIS`) : `Config.url_ntfy` renvoie alors une chaîne
  vide plutôt qu'une URL invalide (`https://ntfy.sh/`), et `notifier_ntfy()`
  détecte cette chaîne vide en tête de fonction pour sauter l'envoi
  **proprement** — aucune requête réseau tentée, au plus un `log.debug`,
  jamais un `log.error`/`log.warning` (ce n'est pas un échec). Se renseigne
  à tout moment via l'onglet Configuration pour activer ce canal sur un
  projet donné, sans qu'aucun redémarrage du watcher au-delà de celui déjà
  requis pour tout changement de `.conf` ne soit nécessaire.
- **Poller `app/notifications_poller.py`** : thread démon lancé par
  `new_issue.py` (à côté du heartbeat). Toutes les `BRIDGE_NOTIF_INTERVALLE`
  secondes (défaut **60 s**), il vérifie une **liste d'issues surveillées**
  (`depot`, `numéro`) — voir « Une liste d'issues, pas de projets (issue
  #624) » ci-dessous — et détecte pour chacune :
  - la **prise en charge** (commentaire ACK), en réutilisant la logique de
    repérage de `/issues-en-attente` (`app.issues._debut_traitement`/
    `_commentaires_issue`) plutôt que de la dupliquer → SSE `debut_issue` (§17.3) ;
  - **succès** : issue **fermée** portant le label `done` (`closedAt` récent) ;
  - **échec définitif** : label `needs-human` posé, issue restée **ouverte**
    (`updatedAt` récent).
  Une transition terminale (succès ou échec définitif) **retire** l'issue de
  la liste surveillée : son cycle de vie pour ce poller est terminé.

  **Une liste d'issues, pas de projets (issue #624, remplace #623, diagnostic
  #621).** Avant #624, chaque cycle balayait, pour **chaque projet dans la
  portée**, deux `gh issue list` (done fermées + needs-human ouvertes) — la
  portée étant décidée par `_projets_dans_la_portee()` (#614) en filtrant
  `lister_projets()` sur le champ `LABEL` du `.conf` de chaque projet
  (`cfg.label`), **avant** tout appel gh. Bug découvert en #621 : `LABEL` est
  un **défaut** de projet, pas la vérité — c'est le label `for-windows`/
  `for-linux` posé sur **chaque issue** (exclusifs, voir §16) qui dit si elle
  concerne CCW, pas le projet qui l'héberge. Aucun `.conf` CCL ne portant
  `LABEL=for-windows`, `_projets_dans_la_portee()` ne retenait plus aucun
  projet : le poller n'interrogeait plus rien et ne détectait plus aucune
  transition CCW, silencieusement, depuis #614.

  Le poller connaît désormais `_ISSUES_SURVEILLEES` : un dict `{(depot,
  numéro): état}` en mémoire process (comme l'ancien `deja_vu`), rempli par :
  1. **`_balayage_initial()`**, appelé **une seule fois** au démarrage de
     `surveiller_transitions()` : liste, pour **tous les projets configurés**
     (plus de filtrage par `.conf`), les issues **ouvertes** dont le label
     entre dans `BRIDGE_NOTIF_SCOPE` ;
  2. **`ajouter_issue_surveillee(depot, numero, labels)`**, appelée en direct
     (même process Flask) à chaque création d'issue depuis le formulaire web
     (`app.issues.envoyer`) et à chaque relance réussie depuis l'onglet
     Résultats (`app.interruption.route_relancer`) ;
  3. la route **`POST /notifier-issue-a-surveiller`** (sans `login_requis`,
     même famille que `/notifier-fin-issue` ci-dessous), appelée par
     `scripts/watcher_issues_inbox.py` — qui tourne dans un **process
     séparé** et ne peut donc pas muter directement `_ISSUES_SURVEILLEES` —
     à chaque création ou relance (champ `RELANCE`) d'une issue for-windows.
  Dans tous les cas, `ajouter_issue_surveillee()` filtre par
  `_dans_la_portee(labels)` (labels de l'ISSUE, inchangé depuis #187) : une
  issue hors de `BRIDGE_NOTIF_SCOPE` n'est jamais ajoutée.

  **Liste vide → AUCUN appel gh** à ce cycle : le cas courant, CCW n'étant
  utilisé qu'une ou deux fois par semaine. Chaque appel gh reste journalisé
  (`_gh_list()`/`_gh_view_issue()`, `[notif HH:MM:SS] gh issue …`, dans les
  logs de `new_issue.py`) pour recompter précisément la charge du poller lors
  d'un futur épisode d'épuisement de quota GraphQL (cf. #613).

  **Limite connue, documentée et non traitée.** Une issue for-windows créée
  **directement sur GitHub** ou par un chef (`gh issue create` hors des trois
  chemins ci-dessus) n'est ajoutée à la liste surveillée qu'au **prochain
  démarrage** de `new_issue.py` (rattrapée par `_balayage_initial()`).
- **Script bip partagé `scripts/traitement_fin.py`** (anciennement
  `scripts/bip.py`, renommé issue #350) : le bip vivait dans `~/NicLink/bip.py`
  (dépôt AlChess) alors que c'est de l'infrastructure commune à tous les projets.
  Il a été déplacé/recréé dans `scripts/`, renommé une première fois `bip.py`
  puis `traitement_fin.py` (#350, une fois devenu aussi le déclencheur du SSE
  de fin d'issue — voir §17.3) ; le **défaut** de `SCRIPT_BIP` pointe désormais
  vers lui. **La clé de config reste `SCRIPT_BIP`** (renommer impliquerait de
  modifier les `configs/*.conf` gitignorés, hors périmètre agent — voir §17.3
  pour la marche à suivre manuelle). **Depuis l'issue #630, c'est le SEUL
  script utilisé pour le bip réel de fin d'issue** (CCL comme CCW) — `SCRIPT_BIP`
  n'est plus lu sur ce chemin, voir plus bas.
- **Choix du son : `scripts/son_actif.txt` (#498), interrupteur GLOBAL.** Le
  script contient deux implémentations de bip — `bip_plat()` (440 Hz,
  sinusoïde plate) et `bip()` (880 Hz, cloche à enveloppe exponentielle
  décroissante ; voir #437 et sa révocation). Historiquement un projet isolé
  (ex. ff_galerie) pouvait obtenir la cloche en pointant `SCRIPT_BIP` vers un
  script dédié (`scripts/bip_Cloche.py`, **supprimé en #630**) — lourd, et il
  aurait fallu éditer `SCRIPT_BIP` dans chaque `.conf` pour changer le son de
  tous les projets à la fois. `son_actif()` lit un fichier unique
  `scripts/son_actif.txt` (une seule ligne : `plat` ou `cloche`) — un seul
  endroit pilote donc le son par défaut pour **toutes** les issues sans choix
  propre (voir « Choix du son PAR ISSUE » ci-dessous). Fichier absent,
  illisible, ou valeur non reconnue → défaut inchangé (`plat`), pour ne rien
  casser silencieusement. Ce fichier n'est **pas** un `configs/*.conf` : le
  garde-fou §11 ne s'y applique pas.
- **Interrupteur plat/cloche accessible depuis l'interface (issue #527).**
  Avant cette issue, changer de son imposait d'éditer `son_actif.txt` à la
  main. `new_issue.py` expose désormais ce choix dans le panneau latéral
  Infrastructure de l'onglet Résultats (`#pl-zone-son`,
  `templates/fragments/panneau_lateral.html` +
  `static/js/panneau_lateral.js::initZoneSon`/`choisirSonActif`/`testerSonActif`,
  issue #628) : un
  sélecteur à deux positions « Plat »/« Cloche », toujours visible, et un
  bouton **« Tester le son »**. Deux routes dédiées (`app/son.py`,
  **GLOBALES, sans `<nom_projet>`**) :
  - `GET`/`POST /son-actif` : lit/écrit `son_actif.txt` — le clic sur une
    position écrit directement le fichier (pas de bouton « Enregistrer »
    séparé), effectif au bip suivant sans redémarrage d'aucun processus
    (`traitement_fin.py::son_actif()` relit le fichier à chaque bip) ;
  - `POST /tester-son` : joue le bip avec le timbre actuellement enregistré
    dans `son_actif.txt` (tonalité neutre, `0` — ce réglage n'est pas
    rattaché à un projet).
- **Choix du son PAR ISSUE (issue #630, backend ; interface issue #637, étape
  7b).** Réglage PAR PROJET envisagé (`TONALITE_BIP`) abandonné au profit
  d'un choix plus fin : n'importe quelle issue peut être basculée en plat ou
  en cloche pour ELLE-MÊME, en plus de l'interrupteur global ci-dessus.
  - **Stockage** : `logs/son_issues.json` (`{projet: {numéro: "plat"|
    "cloche"}}`), écriture atomique + verrou anti-collision — même mécanisme
    que `etat_rate_limit.json` (issue #615). Module `etat_son_issue.py`
    (racine du dépôt, sans dépendance Flask, comme `notifications.py`/
    `etat_rate_limit.py`) : `son_choisi(projet, numéro)`,
    `definir_son(projet, numéro, son)` (`son=None` retire le choix propre —
    l'issue retombe sur l'interrupteur global), `nettoyer_projet(projet)`,
    `nettoyer_entrees_perimees()`.
  - **Routes** `GET`/`POST /son-issue/<nom_projet>/<numero>` (`app/son_issue.py`,
    même famille que `/son-actif` ci-dessus) : lisent/écrivent le choix
    propre à UNE issue.
  - **Interface (issue #637, étape 7b ; déplacée sur la ligne par l'issue
    #641, étape 6 ; 4e option Silence ajoutée #699)** : contrôle compact à 4
    états « G / P / C / S » (Global / Plat / Cloche / Silence — coupe le bip
    pour cette seule issue, sans toucher aux autres canaux de notification)
    directement sur CHAQUE ligne OUVERTE de la liste Résultats
    (`static/js/actions_ligne.js::rendreControleSonLigne`), plus dans le
    panneau latéral. Les fonctions pures posées à #637
    (`sonIssueDepuisReponse`, `normaliserChoixSonIssue`, `etatsOptionsSonIssue`,
    testées sous Node) ont été reprises TELLES QUELLES, comme prévu — seul le
    rendu (compact, lettres au lieu du texte « Global »/« Plat »/« Cloche »,
    contrainte de largeur #633) et le déclenchement réseau ont changé.
    **Chargement en bloc** : `GET /son-issue/<nom_projet>` (nouvelle route,
    même fichier `app/son_issue.py`) renvoie TOUS les choix propres d'un
    projet en une requête (`etat_son_issue.sons_projet`) — une seule requête
    **par projet** au premier rendu d'une ligne de ce projet (jamais une par
    ligne ni par cycle), mise en cache dans `actions_ligne.js`
    (`fusionnerSonsProjet`/`sonConnuDansCache`) ; les lignes déjà rendues
    avant la réponse sont repatchées (`resyncLignesSon`, même principe que
    `resultats_coches.js::resyncDom`). Le clic (P/C/G) reste sur la route
    existante `POST /son-issue/<nom_projet>/<numero>`, mise à jour optimiste
    puis persistée, sans reconstruire toute la ligne. L'interrupteur global
    (`#pl-zone-son`, panneau latéral) reste inchangé dans son fonctionnement.
  - **Résolution au moment du bip** (`scripts/traitement_fin.py::son_a_jouer(
    projet, numéro)`) : le choix de l'issue s'il existe, sinon
    `son_actif()` (interrupteur global) — dans cet ordre, pour **les deux**
    chemins de bip réel : `watcher.py` (issues CCL, `bip()`/`notifier()`
    transmettent toujours `--projet`/`--numero`) et
    `app/notifications_poller.py` (issues CCW, `_notifier_transition()`,
    même transmission).
  - **Nettoyage**, même règle que les cases cochées côté navigateur
    (`resultat-coche:`, `static/js/app.js`/`persistance.js`) : au démarrage
    de `new_issue.py` (`etat_son_issue.nettoyer_entrees_perimees()`), purge
    PAR PROJET des entrées dont le numéro est ≤ (plus grand numéro connu de
    ce projet dans `son_issues.json` − 50) ; et purge TOTALE d'un projet
    (`nettoyer_projet()`) à sa suppression (`supprimer_projet.py`, entre le
    retrait du `.conf` et la régénération de la doc).
  - **Le chemin réel du bip n'utilise plus `TONALITE_BIP` ni `SCRIPT_BIP`**
    (issue #630) : `watcher.py::bip()`/`notifier()` et
    `app/notifications_poller.py::_notifier_transition()` appellent
    toujours `scripts/traitement_fin.py` avec une tonalité neutre (`0`),
    quel que soit le `.conf` du projet. **Le réglage PAR PROJET a été
    intégralement retiré de l'interface à l'issue #643** : `TONALITE_BIP`/
    `SCRIPT_BIP` ne sont plus éditables depuis l'onglet Configuration
    (`CLES_EDITABLES` de `app/projets.py`), la route `/tester-bip/<projet>`
    a été supprimée, et `nouveau_projet.py` n'écrit plus ces clés (ni de
    référence à `scripts/bip_Cloche.py`, supprimé en #630) dans le `.conf`
    d'un nouveau projet. Ces deux clés `.conf` restent **tolérées** dans les
    `configs/*.conf` existants (résiduelles, ex. l'ancien `chesscoach.conf`
    pointant vers `scripts/bip_Cloche.py` — retrait manuel laissé à Alain,
    ces fichiers gitignorés étant hors périmètre agent, §11) :
    `charger_config()` (`watcher.py`) continue de les lire sans erreur si
    présentes, avec les mêmes défauts sensés si absentes. **Le modèle son ne
    comporte donc plus que deux niveaux** : l'interrupteur GLOBAL
    (`#pl-zone-son`, ci-dessus) et le choix PAR ISSUE (ci-dessus) — plus
    aucune tonalité par projet.

**Éviter le spam de vieilles issues au démarrage.** Deux garde-fous combinés :
- **filtre de récence** : seules les transitions horodatées dans les
  `BRIDGE_NOTIF_RECENCE_MIN` dernières minutes (défaut **30 min**) sont
  considérées ;
- **amorçage silencieux au premier cycle** : les transitions déjà présentes au
  démarrage sont mémorisées **sans notifier** (ligne de base) ; seules les
  transitions apparues **ensuite** déclenchent un signal.

L'état (`{depot, numéro, type}` déjà notifiés) vit **en mémoire process** — pas
de fichier, par simplicité (un suivi de transitions n'a pas besoin de survivre à
un redémarrage). Contrepartie assumée : une transition survenue **pendant** un
redémarrage de `new_issue.py` est ré-amorcée silencieusement au redémarrage (donc
non notifiée) — cas rare et sans gravité.

**Bonus — un label `notif_*` ajouté EN COURS de route est pris en compte.**
Contrairement au mécanisme de `watcher.py` (qui capture les labels **une seule
fois**, au tout début de `traiter_issue()` — un label ajouté après n'a alors
aucun effet), le poller lit les labels **COURANTS** de l'issue **au moment où il
détecte sa fermeture**. Conséquence directe et voulue : **Alain peut ajouter
`notif_pc` / `notif_gsm` sur GitHub à tout moment tant que l'issue est encore
ouverte** (en file d'attente **ou** en cours de traitement) et recevra bien la
notification correspondante à sa fermeture.

### 17.1 Anti-doublon : réglages et choix par défaut

`watcher.py` et le poller peuvent **tous deux** notifier. Pour qu'Alain ne
reçoive pas deux fois le même signal, deux réglages se combinent :

| Réglage | Où | Effet |
|---------|-----|-------|
| `NOTIFIER_LOCAL = true/false` | `.conf` de chaque projet (défaut **true**) | Le **watcher** émet-il lui-même ses notifications ? `false` = il se tait, le poller s'en charge. |
| `BRIDGE_NOTIF_SCOPE` | variable d'env de `new_issue.py` (défaut **`for-windows`**) | Portée des transitions notifiées par le **poller** : `for-windows` (CCW seul) \| `for-linux` \| `all` \| `off`. |

**Choix livré par défaut (sans régression, sans doublon) — variante de l'option
(b) faite proprement :**
- **CCL** : le watcher notifie (`NOTIFIER_LOCAL=true`), le poller ignore
  `for-linux` (scope `for-windows`) → **une seule** notification, comme
  aujourd'hui. Aucun changement de comportement pour CCL.
- **CCW** : le watcher de la VM doit poser **`NOTIFIER_LOCAL = false`** dans ses
  `configs\*-ccw.conf` (sinon son `ntfy` ferait doublon avec le poller), et le
  poller notifie les transitions `for-windows` → **une seule** notification,
  désormais **locale au ThinkPad** (bip + bulle inclus, ce qui manquait).

> ⚠️ **Action requise côté VM CCW** (hors périmètre de cette issue, à faire par
> Alain) : ajouter `NOTIFIER_LOCAL = false` dans chaque `configs\*-ccw.conf` de
> la VM, puis redémarrer les services `CCW-Watcher*`. Sans cela, les issues CCW
> avec `notif_gsm`/`notif_tous` déclencheraient **deux** push `ntfy` (un depuis
> la VM, un depuis le poller).

**Pourquoi ce défaut plutôt que l'option (a) « centralisation complète ».**
L'objectif final recommandé reste l'**option (a)** : `new_issue.py` **seule**
source de notification pour **tous** les projets (CCL + CCW), en posant
`NOTIFIER_LOCAL=false` partout et `BRIDGE_NOTIF_SCOPE=all`. Elle est **déjà
implémentée et à un réglage près** (voir plus bas). Mais elle a une **implication
opérationnelle à trancher par Alain** : elle fait de `new_issue.py` une
**dépendance dure** de TOUTE notification — or `new_issue.py` n'a **pas** de
service systemd (seul `watcher@.service` existe) ; il est lancé à la main. Tant
qu'il n'est pas un service permanent, retirer les notifications de `watcher.py`
CCL signifierait **plus aucune notification** si l'interface web n'est pas
lancée. Le défaut livré évite ce risque tout en fixant immédiatement le vrai
manque (les notifications CCW sur le ThinkPad).

**Basculer en option (a) (centralisation complète), une fois `new_issue.py`
rendu permanent** (par ex. un `new_issue.service` systemd `--user`) :

```bash
# 1. Poller : notifier toutes les plateformes.
export BRIDGE_NOTIF_SCOPE=all      # avant de lancer new_issue.py
# 2. Watchers : couper leur notification locale (CCL et CCW).
#    Dans chaque configs/*.conf (CCL) et configs\*-ccw.conf (VM) :
NOTIFIER_LOCAL = false
# puis redémarrer les watchers (systemctl --user restart 'watcher@*' côté CCL).
```

### 17.2 Réglages (variables d'environnement du poller)

| Variable | Défaut | Rôle |
|----------|--------|------|
| `BRIDGE_NOTIF_SCOPE` | `for-windows` | Portée : `for-windows` \| `for-linux` \| `all` \| `off` (désactive). |
| `BRIDGE_NOTIF_INTERVALLE` | `60` | Période de polling (secondes) — 20→60 s en #188 pour alléger la charge gh cumulée. |
| `BRIDGE_NOTIF_RECENCE_MIN` | `30` | Fenêtre de récence des transitions (minutes). |
| `BRIDGE_NOTIF_ESPACEMENT` | `2` | Délai (secondes) entre le traitement de deux issues de la liste surveillée (issue #190, adapté #624) : étale les appels gh du poller au lieu d'une rafale groupée qui rendait le bouton Rafraîchir lent et faisait « sursauter » les badges. Sans effet la plupart du temps (liste vide ou à un seul élément). `0` = rafale immédiate (ancien comportement). |

### 17.3 SSE de fin d'issue — rafraîchissement instantané de l'onglet Résultats (issue #350)

Avant #350, la ligne d'une issue dans l'onglet Résultats restait figée après sa
clôture jusqu'au ↻ manuel ou jusqu'au fetch unique post-TIMEOUT de #334 (15 s
après dépassement du décompte). #350 ajoute un canal de rafraîchissement quasi
instantané (< 1 s), **sans polling supplémentaire**, en réutilisant
`scripts/traitement_fin.py` (le script bip partagé, voir plus haut) comme
déclencheur et un canal SSE dédié comme transport :

- **`scripts/traitement_fin.py --projet <nom> --numero <n>`** : après le bip
  habituel, POST **best-effort** (timeout 1 s, échec silencieux — new_issue.py
  peut ne pas être lancé, notamment sur la VM CCW) vers
  `http://localhost:5100/notifier-fin-issue` avec le corps
  `{"projet": ..., "numero": ...}`. `notifications.bip()` transmet ces deux
  arguments dès que `notifications.notifier()` les reçoit — ce qui remonte
  jusqu'aux enveloppes `bip()`/`notifier()` de `watcher.py` (paramètre
  `numero` ajouté). Comme le bip lui-même, **ce chemin-là** reste **opt-in via
  les labels `notif_*`** (§4) : `notifications.notifier()` n'appelle `bip()`
  que si l'issue en porte un.
- **`watcher.py::notifier_fin_sse`/`notifier_debut_sse`** (CCL) et
  **`app/notifications_poller.py`** (CCW, issue #624) appellent en plus
  `traitement_fin.notifier_fin_issue`/`notifier_debut_issue` **directement**,
  **décorrélé des labels `notif_*`** — le rafraîchissement de l'onglet
  Résultats doit être universel, contrairement au bip/bulle/ntfy (opt-in).
  Pour CCW, c'est `_traiter_transition()`/`_verifier_issue_surveillee()` qui
  appellent ces deux fonctions à chaque transition détectée sur une issue de
  la liste surveillée (§17, garde-fous d'amorçage/récence conservés — pas de
  SSE pour une transition/ACK déjà présente au démarrage). Sans label
  `notif_*`, la ligne reste malgré tout rafraîchie quasi instantanément ; sans
  ce mécanisme (avant #350/#624), elle resterait soumise au ↻ manuel / au
  fetch post-TIMEOUT de #334.
- **`POST /notifier-fin-issue`** (`app/fin_issue.py`, sans `login_requis` —
  appelé par un script local, pas par un navigateur, comme `/heartbeat`) :
  pousse un événement SSE `event: fin_issue\ndata: {"projet": ..., "numero": ...}`
  à tous les onglets Résultats actuellement ouverts. `POST /notifier-debut-issue`
  (même module) est le pendant côté début de traitement, événement `debut_issue`.
- **`POST /notifier-issue-a-surveiller`** (`app/notifications_poller.py`,
  issue #624, sans `login_requis` — même famille que les deux routes
  ci-dessus) : ajoute immédiatement une issue `{"depot", "numero", "labels"}`
  à `_ISSUES_SURVEILLEES`, filtrée par `BRIDGE_NOTIF_SCOPE`. Appelée par
  `scripts/watcher_issues_inbox.py` (process séparé, cf. « Une liste
  d'issues, pas de projets » ci-dessus) — sans effet sur le SSE `/stream`
  lui-même, qui n'est poussé qu'à la détection effective de l'ACK/de la
  transition, au cycle suivant.
- **`POST /notifier-fichier-recu` / `/notifier-creation-issue` /
  `/notifier-fichier-refuse`** (`app/fin_issue.py`, issue #631, sans
  `login_requis`, même famille que les routes ci-dessus) : trois événements
  couvrant le cycle de vie d'un fichier déposé dans `issues_inbox/` —
  `fichier_recu` (prise en charge), `creation_issue` (par
  `scripts/watcher_issues_inbox.py` ET, en appel direct sans HTTP,
  `app.issues.envoyer()`), `fichier_refuse` (par bloc refusé). Détail complet
  du contenu de chaque événement et de l'ordre pour un fichier multi-blocs :
  §3.15. `fichier_recu`/`fichier_refuse` sont désormais consommés côté
  navigateur depuis la fusion de l'onglet « Résultats inbox » dans Résultats
  (étape 9b, #639 — voir §3.8) ; `creation_issue` est consommé côté navigateur
  depuis #627, enrichi depuis #634 (voir « Côté navigateur » ci-dessous).
- **`GET /stream`** (`app/fin_issue.py`, protégé par `login_requis` comme
  `/events`) : générateur Flask SSE dédié, séparé de `/events` (cycle de vie)
  et de `/journal/<projet>` (log watcher). Mécanisme de diffusion : une
  **`queue.Queue` par connexion active**, ajoutée à la liste partagée
  `app.config["FIN_ISSUE_ABONNES"]` à la connexion et retirée (`finally`,
  couvre le `GeneratorExit` d'une déconnexion navigateur) à la fermeture — pas
  de broadcast global, car new_issue.py est mono-utilisateur mais plusieurs
  onglets peuvent être ouverts en même temps. Ping `: ping\n\n` toutes les 30 s
  pour maintenir la connexion (proxys, navigateur).
- **Côté navigateur** (refonte étape 3, issue #627) : le canal `/stream` est
  désormais ouvert et géré par **`static/js/resultats.js`** (via la brique
  `sse` du socle, `sse.stream.connecter()`), **une seule fois** au chargement de
  la page — plus par `app.js` (l'ancien `demarrerStreamFinIssue()` a été retiré,
  garantissant une **UNIQUE** connexion `/stream`). Le traitement est **toujours
  CIBLÉ** sur le projet+issue concernés (jamais un rechargement de tous les
  projets) et alimente le **store** (source de vérité unique — plus de cache de
  liste en `localStorage`) :
    - `debut_issue` : recharge les **données de temps de cette issue** (le
      décompte TIMEOUT démarre) et l'ajoute à la liste si absente. Ne passe
      **JAMAIS** par la vérification post-dépassement de #334 (correctif du bug
      où le badge restait « ⏳ en file » et où l'issue était marquée à tort
      « dépassement déjà vérifié »).
    - `fin_issue` : met à jour la ligne (état final, arrêt du décompte) via un
      unique fetch `/issue/<projet>/<numero>`.
    - `creation_issue` (contrat de l'étape 9a, **enrichi issue #634** :
      `projet`, `numero`, `titre`, `labels`, `timing`, et `fichier` d'origine
      si créée via `issues_inbox` — détail du contenu de `labels`/`timing` :
      §3.15) : fait apparaître la ligne avec ses **vrais labels** et son
      estimation/« en file » **directement depuis l'événement**, SANS AUCUN
      fetch réseau supplémentaire. Avant #634, un fetch ciblé
      (`chargerTimingProjet()`) suivait immédiatement l'apparition de la
      ligne pour enrichir labels/estimation/timeout — mais juste après un
      `gh issue create`, la réponse de `/issues-en-attente` pouvait ne pas
      encore contenir la toute nouvelle issue (décalage d'indexation
      GitHub) : `chargerTimingProjet()` purgeait alors INCONDITIONNELLEMENT
      les entrées de timing du projet avant de les réinjecter, effaçant le
      badge « ⏳ en file » déjà affiché — qui restait absent jusqu'à
      `debut_issue`, seul appelant suivant de `chargerTimingProjet()`.
  **Robustesse générale de `chargerTimingProjet()` (issue #634, fonction pure
  `fusionnerTimingProjet()`)** : une réponse `/issues-en-attente` qui ne
  contient pas encore une issue OUVERTE et RÉCENTE (< 30 s,
  `FENETRE_RECENTE_TIMING_MS`) que le navigateur connaît déjà ne l'efface
  **plus** — que ce fetch soit déclenché par `debut_issue` ou par ↻. Passé
  cette fenêtre, une absence prolongée signale une vraie fin d'issue (clôture,
  `needs-human` — celui-ci n'est jamais renvoyé par `/issues-en-attente`,
  issue #523) et l'entrée est retirée normalement. Le retrait explicite reste
  déclenché par ce qui établit RÉELLEMENT la fin d'une issue : `fin_issue`,
  la vérification post-dépassement de #334, ou ↻ une fois la fenêtre de
  récence écoulée — jamais par une simple absence côté liste. Testé sous
  Node (`fusionnerTimingProjet`, voir plus bas).
  Le **fetch unique post-dépassement de #334** est conservé, réservé au décompte
  tombé à zéro. Un projet dont le chargement échoue **reste affiché** (données
  précédentes conservées) et l'échec est signalé par un **toast**. Au-delà du
  chargement initial unique et des mises à jour SSE ciblées, l'activation de
  l'onglet peut déclencher un **rechargement discret en arrière-plan** quand la
  dernière synchro réseau est périmée (issue #729, détail en §17.4 ci-après) :
  ce n'est donc plus un strict « aucun rechargement réseau hors ↻ ». La
  logique pure (application d'un événement à l'état, calcul des badges de temps,
  fusion du timing) est testée sous Node — `node --test static/js/tests/`. La
  reconnexion après coupure reste native à `EventSource`.

### 17.4 Rattrapage des événements manqués dans l'onglet Résultats (issues #705, #729)

Le canal `/stream` (§17.3) n'alimente la liste et les badges que par des
événements **ciblés** : un événement manqué (onglet masqué, flux coupé/en
pause, `RELANCE` qui ne produit jamais de `creation_issue`, §3.14) laisse la
liste, le décompte ou la case « traité/lu » périmés **sans qu'aucun
rechargement périodique ne vienne les rattraper**. Trois mécanismes
complémentaires, tous côté navigateur (`static/js/resultats.js`), couvrent ce
risque sans jamais toucher au protocole d'événements ni au serveur :

- **Retour au premier plan après masquage prolongé (issue #705).**
  `document.addEventListener('visibilitychange', …)` (`app.js`) horodate le
  passage en arrière-plan (`momentMasquageOnglet`) ; au retour, si la durée
  masquée dépasse `SEUIL_RESYNC_MASQUAGE_MS` (30 s — fonction pure
  `fautResynchroniserApresMasquage(dureeMasqueeMs)`), déclenche
  `resynchroniserResultatsAuRetour()`, qui rejoue le **même rafraîchissement
  que le bouton ↻** (`rafraichirResultats()`). Un renfort du heartbeat
  navigateur→serveur (`envoyerHeartbeat()` immédiat) accompagne ce retour,
  contre le throttling des `setInterval` en arrière-plan (issue #157).
- **Reconnexion SSE après coupure (issue #705).** L'`onOuvert` de
  `sse.stream.connecter()` (`static/js/resultats.js::surOuvertureSse`)
  distingue la **toute première** ouverture du canal (page qui vient de
  charger la liste — aucune resync) d'une **reconnexion** après coupure
  (fonction pure `fautResynchroniserApresReconnexionSse(premiereOuverture)`),
  qui déclenche le même `resynchroniserResultatsAuRetour()` que ci-dessus.
- **Activation de l'onglet, liste déjà chargée (issue #729).** Avant #729,
  `onActiverOnglet()` (hors tout premier chargement) se contentait de
  réafficher le store SANS AUCUN accès réseau — un événement manqué survenu
  pendant que l'onglet était sur Résultats mais inactif (un autre onglet
  sélectionné sans jamais masquer la page, donc sans déclencher #705) restait
  invisible jusqu'au ↻ manuel. Désormais : le contenu courant est affiché
  **immédiatement** (`rendreListeComplete()`, lecture pure du store), **puis**,
  si la dernière synchro réseau de la liste date de plus que
  `SEUIL_RESYNC_MASQUAGE_MS` (ou n'a **jamais** eu lieu — fonction pure
  `fautRechargerAOuverture(dernierSyncMs, maintenant, seuilMs)`, même seuil
  que #705 : un seul réglage simple à ajuster), liste + décompte + cases
  cochées sont rechargés **en arrière-plan** (`rechargerEnArrierePlan()`) —
  sans vider ni bloquer l'affichage déjà posé, le remplacement restant
  atomique (store mis à jour puis rendu complet d'un coup, comme pour le ↻).
  Anti-rafale : aucun intervalle dédié, la décision ne se pose qu'À
  l'activation et se referme d'elle-même dès que la synchro redevient
  récente — le garde-fou anti-rafale existant de #705
  (`DELAI_MIN_ENTRE_RESYNCS_AUTO_MS` côté `resynchroniserResultatsAuRetour`,
  `app.js`) reste par ailleurs inchangé et actif en parallèle. Contrairement
  à #705 (qui rejoue le ↻, restreint au filtre de projets actifs — issue
  #428), ce rattrapage à l'activation **n'est pas filtré** : un rattrapage se
  veut complet, quel que soit le filtre d'affichage courant au moment de
  l'ouverture.
- **Cases « traité/lu » désormais incluses dans le ↻ et #705 (issue #729).**
  Avant #729, `rechargerCases()` (`static/js/resultats_coches.js`) n'était
  relu qu'au chargement de la page : une décoche serveur manquée par le canal
  `case_decochee` (§3.15, issue #720 — ex. deux `RELANCE` déposées coup sur
  coup pendant que l'onglet Résultats n'était pas affiché) laissait la case
  cochée à l'écran malgré la décoche réelle côté serveur, sans que le ↻ la
  corrige. `resultats.rafraichir()` (↻, et donc aussi #705 qui le rejoue)
  appelle désormais `resultatsCoches.rechargerCases(nomsAFetcher)` avec
  **EXACTEMENT** le même sous-ensemble de projets que la liste/le décompte
  (respect du filtre de projets de l'issue #428) ; le rattrapage à
  l'activation ci-dessus l'appelle lui aussi, sans filtre (cohérent avec le
  reste de son rechargement). Import ES direct de `resultats_coches.js` dans
  `resultats.js` (pas de cycle : `resultats_coches.js` n'importe jamais
  `resultats.js`), plutôt qu'un aller-retour par `pont.js` (réservé aux
  échanges nouveau↔ancien code).
- **Heure de dernière synchro, affichée près du ↻ (issue #729).** Repère
  discret (`#resultats-derniere-sync`, juste après le bouton ↻ dans
  `construireBoutonsFiltre()`, `app.js`) formaté par la fonction pure
  `formaterHeureSync(ms)` de `resultats.js` (« sync. HH:MM:SS », ou « jamais
  synchronisé ») — reconstruit à chaque reconstruction de cette barre
  (chargement initial, ↻, les deux resynchros ci-dessus), donc toujours à
  jour sans abonnement ni minuterie dédiés.

Logique pure testée sous Node (`static/js/tests/resultats.test.js` :
`fautResynchroniserApresMasquage`, `fautResynchroniserApresReconnexionSse`,
`fautRechargerAOuverture`, `formaterHeureSync` ; comportemental, DOM/réseau
mockés, dans `static/js/tests/resultats_resync_729.test.js` : périmètre de
projets transmis à `rechargerCases`, déclenchement du rattrapage passé le
seuil). **Après fusion : `Ctrl+Maj+R` suffit (JS et CSS uniquement) — aucun
redémarrage de `new_issue.py` ni des watchers, aucun changement de protocole
d'événements.**

**Badge « modèle forcé » d'une ligne (issue #638)** : une issue peut imposer un
modèle précis via le champ `| MODELE | … |` de son en-tête (§3). Dans l'onglet
Résultats, chaque ligne dont le **modèle effectif** diffère du **modèle par
défaut de son projet** porte un **badge discret** indiquant le nom court du
modèle (ex. « opus »), placé entre le titre et les badges de temps sans les
recouvrir. Une issue **sans** champ `MODELE`, ou dont le modèle forcé est
justement le défaut du projet, n'affiche **rien de plus**. Pour l'alimenter,
**trois routes exposent deux champs supplémentaires** (`app/issues.py`) :
- **`modele`** — modèle effectif de l'issue, lu dans le champ `MODELE` de son
  **corps** ; `null` si le champ est absent, vide ou porte une valeur inconnue
  (aucun badge). Source unique côté serveur : `extraire_modele_entete(body)`,
  primitive dédiée à la lecture depuis un **corps d'issue GitHub** (distincte de
  `watcher.extraire_modele`, qui retombe sur son `CFG` global, et du parseur de
  `scripts/watcher_issues_inbox.py`, qui lit un fichier `issues_inbox/`),
  partagée par `/issues-liste`, `/recherche-issues`, `/issues-en-attente` et
  `/issue`.
- **`modele_defaut`** — modèle par défaut **réel du projet** (`MODELE_CCL` du
  `.conf` s'il en fixe un, sinon `claude-sonnet-5`), via `modele_defaut_projet(cfg)`.
  Une valeur par projet, répétée sur chaque issue de la réponse (les listes
  restent de simples tableaux JSON).
La décision « afficher/masquer » est prise côté navigateur par l'unique fonction
pure `calculerBadgeModele(modele, modele_defaut)` de `static/js/resultats.js`,
testée sous Node (`node --test static/js/tests/`). Le versant serveur
(`extraire_modele_entete` : présent/absent/invalide) est testé par
`tests/test_modele_effectif_638.py`.

`MODELES_VALIDES`/`MODELE_DEFAUT_GLOBAL` vivent dans `app/projets.py` (SOURCE
UNIQUE, issue #656 — auparavant dupliquées à l'identique dans `app/issues.py`
et `scripts/watcher_issues_inbox.py`, qui les importent désormais d'ici ;
définies dans `app/projets.py` plutôt que dans `app/issues.py` pour éviter un
import circulaire, `app/issues.py` important déjà `projet_par_nom` depuis
`app/projets.py`). `GET /config/<projet>` les expose (`modeles_valides` triée,
`modele_defaut_global`) pour que l'onglet Configuration construise
dynamiquement la liste déroulante du champ **Modèle Claude Code**
(`#conf-MODELE_CCL`, `static/js/config.js::construireOptionsModeleCCL`,
`templates/fragments/onglet_config.html`) — remplace l'ancien champ texte
libre, source de fautes de frappe silencieuses (`--model` de `watcher.py`
transmettait la valeur telle quelle au CLI sans validation). Une option vide
en tête correspond à un `MODELE_CCL` vide/absent (défaut global) ; si la
valeur déjà enregistrée dans le `.conf` d'un projet n'est plus reconnue
(ancienne valeur, faute de frappe historique), elle est ajoutée comme option
supplémentaire en fin de liste plutôt que silencieusement écrasée, avec un
avertissement discret sous le champ. Testé sous Node
(`static/js/tests/config.test.js`) et par
`tests/test_modele_ccl_liste_deroulante_656.py` (partage de l'objet
`MODELES_VALIDES`, contenu de la réponse `/config`, tolérance à une ancienne
valeur).

**Badge « sans REDACTEUR » d'une ligne (issue #647)** : signal purement
**visuel**, jamais bloquant, complémentaire de la validation `REDACTEUR` du
§3.4. Une issue créée via `issues_inbox/` (`scripts/watcher_issues_inbox.py`)
**sans** champ optionnel `REDACTEUR` dans son en-tête — cas déjà accepté par
`valider_redacteur()` (rétrocompatibilité, jamais de rejet) — reçoit en plus,
à la création, le label GitHub `sans-redacteur` (`watcher.LABEL_SANS_
REDACTEUR`), posé par `construire_labels()`. `REDACTEUR` **présent** (cohérent
avec `PROJET` ou non — l'incohérence a son propre traitement, rejet vers
`rejected/`, inchangé au §3.4) → jamais posé. Objectif (besoin d'Alain) :
repérer, dans l'onglet Résultats, le cas où Claude Chat a rédigé une issue sans
indiquer son projet d'origine au fil d'une conversation longue (plusieurs
projets abordés sans changer de session) — l'absence de tout signal
empêchait jusqu'ici de le remarquer.

Cette pastille ambrée discrète (infobulle « Créée sans REDACTEUR »), placée
juste après le badge « modèle forcé » ci-dessus, **réutilise l'infrastructure
de #638** plutôt que de la dupliquer : aucun appel GitHub supplémentaire (le
label posé à la création est déjà présent dans la réponse `labels` de chaque
route existante), même patron span-toujours-présent-masqué-si-rien-à-afficher
rafraîchi à chaque tick par `majBadges()`. La décision « afficher/masquer »
est prise côté navigateur par l'unique fonction pure
`calculerBadgeSansRedacteur(labels)` de `static/js/resultats.js` (simple
présence du label `sans-redacteur`, réutilisant `normaliserNomsLabels()`
d'`actions_ligne.js` — objets `{name}` de `gh issue list` ou chaînes),
testée sous Node. Le versant serveur (pose du label par `construire_labels()`)
est testé par `tests/test_label_sans_redacteur_647.py`.

Formulaire web (`new_issue.py`, `app/issues.py::envoyer()`) : **volontairement
non concerné**. Ce chemin (Alain tapant directement dans le navigateur, pas
Claude Chat) ne propose **aucun** champ `REDACTEUR` — `construire_labels(data)`
n'en lit jamais depuis `data`. Y appliquer la même logique poserait donc le
label sur **100 % des créations de ce chemin sans exception**, un signal
toujours vrai qui ne distinguerait jamais rien (contrairement à `issues_inbox/`
où l'absence reste l'exception) : ajouter ce code y aurait été du code mort
en pratique, écarté sciemment plutôt qu'ajouté sans utilité.

**Régression #647 corrigée en #648** : `LABELS` de `nouveau_projet.py` (les
labels provisionnés d'office sur chaque dépôt) n'avait pas été mis à jour par
#647 pour y inclure `sans-redacteur` — le label n'existait donc sur AUCUN
dépôt, faisant échouer `gh issue create` (`could not add label:
'sans-redacteur' not found`) pour TOUTE issue sans REDACTEUR, sur tous les
projets. Corrigé par : (1) ajout de `sans-redacteur` à `LABELS` — tout nouveau
projet le provisionne désormais d'office ; (2) `gh label create` exécuté
manuellement sur les 13 dépôts existants (liste du tableau §1) ; (3)
`app.issues.creer_issue_gh()`, point d'appel commun de `gh issue create`
partagé par `app/issues.py::envoyer()` et
`scripts/watcher_issues_inbox.py::_creer_issue()`, retire désormais de
lui-même un label ABSENT du dépôt cible (détecté au message d'erreur exact de
gh) et journalise l'anomalie (`log.warning`) plutôt que de faire échouer toute
la création — gh échouant de façon atomique avant de créer l'issue dès qu'un
label manque, réessayer sans le label fautif ne crée jamais de doublon. Un
label manquant, quel qu'il soit, ne peut donc plus faire rejeter un fichier
entier. Voir `tests/test_label_manquant_648.py`.

**Configuration héritée** : la clé `.conf` reste `SCRIPT_BIP` (voir §17.1
ci-dessus et §10) — Alain doit mettre à jour manuellement le chemin dans ses
`configs/*.conf` existants (`.../scripts/bip.py` → `.../scripts/traitement_fin.py`).

---

## 18. Pièces jointes image dans les issues (issues #191, #248)

L'onglet **« Nouvelle issue »** permet de **joindre une image (PNG/JPEG/GIF)** —
par exemple une maquette d'interface souhaitée — pour qu'elle soit **automatiquement
intégrée au corps** de l'issue créée, sans le détour manuel (glisser-déposer dans
un commentaire GitHub web, récupérer l'URL, la coller).

### 18.1 Pourquoi committer l'image plutôt que l'attacher

L'API GitHub **ne permet pas** d'uploader une pièce jointe arbitraire sur une
issue de façon simple/stable via un token : le glisser-déposer du web repose sur
un mécanisme interne non documenté pour un usage scripté. La solution fiable et
bien supportée retenue ici :

1. **Committer** l'image dans un dossier dédié : **`issue-attachments/`** — mais
   sur une **branche dédiée et orpheline**, `pieces-jointes` (§18.1bis), **PAS**
   sur la branche de travail du projet ;
2. **Pousser** cette seule référence sur `origin` ;
3. **Référencer** l'image dans le corps Markdown de l'issue via une URL
   **`raw.githubusercontent.com/<owner>/<repo>/pieces-jointes/issue-attachments/<fichier>`**
   — ce format s'affiche correctement dans les issues GitHub une fois postées.

Le nom de fichier est **horodaté** (`AAAAMMJJ-HHMMSS-<nom_original>.png`) pour
éviter toute collision.

### 18.1bis Isolation du push sur une branche dédiée (issue #248)

La version initiale (#191) poussait sur `HEAD:<branche_courante>` (la branche de
**travail** du projet, déduite dynamiquement). Or **git ne peut pas publier un
commit sans ses ancêtres** : ce push emportait donc, en même temps que l'image,
**tous les commits locaux non encore poussés** de cette branche — c'est-à-dire
tout travail que CCL avait committé et qu'Alain n'avait pas encore relu. C'est
une brèche dans le garde-fou central du système (§18.2 ci-dessous précisait déjà
que l'exception ne couvrait QUE le commit de l'image, jamais le code — la brèche
tenait au mécanisme, pas à l'intention).

**Correctif retenu** : la route publie désormais sur une branche **`pieces-jointes`**,
**orpheline** (aucun ancêtre commun avec `master`/`main`, créée sans parent à sa
première utilisation) et ne contenant **que** `issue-attachments/`. Par
construction, aucun commit de code ne peut plus jamais être emporté par ce push,
quel que soit l'état de la branche de travail au moment de l'upload.

Le commit est construit par **plomberie git**, sans jamais toucher à l'arbre de
travail ni à `HEAD` du dépôt du projet cible (un watcher peut être en train d'y
exécuter une tâche `mode_write` au même instant) :

1. `git fetch origin pieces-jointes` (best-effort — échoue silencieusement si la
   branche n'existe pas encore côté origin, auquel cas le commit sera un commit
   **racine**, sans parent) ;
2. `git hash-object -w` sur un **fichier temporaire** (créé hors du dépôt, jamais
   dans `REP_TRAVAIL`) → écrit le blob directement dans `.git/objects` ;
3. `read-tree` (du tip précédent, pour conserver les pièces jointes déjà
   publiées) + `update-index --add --cacheinfo` + `write-tree`, le tout sur un
   **index temporaire isolé** via la variable d'environnement `GIT_INDEX_FILE`
   — l'index réel du dépôt n'est jamais touché ;
4. `git commit-tree` (avec `-p <tip précédent>` si la branche existait déjà) ;
5. `git push origin <sha>:refs/heads/pieces-jointes` — cette seule référence,
   jamais `HEAD`, jamais la branche de travail.

Aucun `checkout`, aucun changement de branche, aucun `git add` dans l'index
courant du dépôt. Si le tip distant a bougé entre l'étape 1 et l'étape 5 (course
avec un autre push), l'étape 5 est rejetée nativement par git comme
**non-fast-forward** — pas d'écrasement silencieux possible.

Conséquence directe : le fichier n'est **plus jamais écrit dans `REP_TRAVAIL`**
(plus de `dossier.mkdir`/`write_bytes` dans le dépôt de travail) — il transite
par un fichier temporaire hors dépôt, le temps de calculer son blob.

### 18.2 ⚠️ Exception « push par Alain via l'outil » — distincte de la règle CCL

> **Rappel de la règle habituelle** : **CCL ne pousse JAMAIS** — le watcher
> committe un `backup + fix` en local et **Alain pousse lui-même** après
> vérification.
>
> **Cette fonctionnalité fait exception, et c'est intentionnel.** Le
> commit+push de l'image est déclenché **directement par ALAIN** via l'interface
> (upload manuel de sa part), **PAS par CCL ni par le watcher**. C'est
> exactement comme si Alain committait et poussait l'image lui-même en ligne de
> commande — l'outil ne fait qu'automatiser ces gestes **à sa demande explicite,
> sur son action**. La règle « CCL ne pousse jamais » **n'est donc pas violée** :
> elle concerne les modifications de code produites par l'agent, pas une image
> qu'Alain choisit lui-même de publier via le formulaire.
>
> **Précision (issue #248), la justification ci-dessus était incomplète** : elle
> couvrait l'intention (qui déclenche le push) mais pas le mécanisme (ce que le
> push publie réellement). Depuis #248, ce push est de plus **confiné par
> construction à la branche orpheline `pieces-jointes`**, qui ne contient jamais
> de code — seulement des images. Même dans l'hypothèse où Alain déclencherait
> ce geste sans avoir mesuré ses conséquences, aucun commit de travail (relu ou
> non) ne peut plus jamais être emporté. L'exception ne repose donc plus
> uniquement sur l'intention d'Alain, mais aussi sur une impossibilité technique
> de dérive vers le code.
>
> **Seconde exception du même type (issue #257)** : le push initial que
> `nouveau_projet.py`/le bouton web effectuent pour initialiser le dépôt git
> **du projet créé** (§13, étape 5) — pas Bridge_Agent lui-même. Même
> raisonnement : c'est Alain qui déclenche la création de projet, jamais un
> agent. Contrairement aux pièces jointes, ce push n'est pas confiné à une
> branche orpheline sans code : c'est le commit initial normal (`master`) du
> nouveau dépôt, ce qui reste sûr **côté dépôt distant**, puisque ce dépôt
> vient d'être créé et ne contient encore aucun travail d'un tiers
> susceptible d'être emporté.
>
> **Précision (issue #258), ce raisonnement était incomplet** : il couvrait
> le dépôt distant (rien à emporter, puisqu'il vient de naître) mais pas le
> contenu **local** de `REP_TRAVAIL` — ce script gère explicitement le cas
> d'un répertoire préexistant non versionné, dont le contenu n'a alors
> jamais été relu par Alain avant la création du projet. Le push distant
> serait sûr en lui-même, mais publierait sans confirmation tout ce que
> contenait déjà ce répertoire. Depuis #258, ce cas est détecté : si le
> répertoire contient autre chose que les fichiers que le script vient
> lui-même de créer (`CONTEXTE.md`, fichiers Specs, `.gitignore`), le push
> n'est **pas** déclenché automatiquement — seuls `git init`/remote/
> `.gitignore`/commit le sont, le push restant à la main après relecture.
> L'exception ne s'applique donc en pratique qu'aux répertoires réellement
> vides (ou ne contenant que les fichiers créés par le script lui-même).

### 18.3 Fonctionnement concret

- **Frontend** (`templates/index.html`, onglet Nouvelle issue) : champ
  `<input type="file" accept="image/png,image/jpeg,image/gif">` + bouton
  **« Joindre une image »** à côté du corps. À la réussite, la ligne Markdown
  `![<nom_fichier>](<url>)` est insérée **automatiquement** dans le champ Corps
  (à la position du curseur), sans copier-coller manuel.
- **Backend** : route **`POST /joindre-image`** (`app/issues.py`,
  `joindre_image()` + `_publier_piece_jointe()`). Reçoit le fichier + le nom du
  projet sélectionné, **valide** le type (PNG/JPEG/GIF, contrôle du Content-Type
  **et** des magic bytes) et la **taille** (**≤ 5 Mo**), écrit un fichier
  temporaire hors dépôt, construit et pousse le commit par plomberie git sur la
  branche `pieces-jointes` (§18.1bis), puis retourne l'URL
  `raw.githubusercontent.com`.

### 18.4 Gestion d'erreurs

- **Push échoué** (réseau, conflit non-fast-forward, pas de remote, droits
  manquants) → message clair et **aucune URL insérée** (elle serait cassée tant
  que le commit n'est pas sur `origin`). Rien n'est laissé en local dans
  `REP_TRAVAIL` (le fichier temporaire est nettoyé dans tous les cas via
  `finally`) : contrairement à la version #191, il n'y a plus de « commit orphelin
  local » à gérer puisque l'arbre de travail n'est jamais impliqué.
- **Projet dont le `REP_TRAVAIL` n'est pas un dépôt git** (ou introuvable) →
  message clair (commit/push impossibles), plutôt qu'un échec silencieux.
- **Type non supporté / fichier trop lourd / fichier vide / contenu non conforme
  à une image** → refus explicite, rien n'est écrit ni committé.
- **Échec d'une étape de plomberie** (`hash-object`, `read-tree`,
  `update-index`, `write-tree`, `commit-tree`) → message clair incluant le
  détail git, aucune URL retournée ; aucune de ces étapes n'a d'effet observable
  sur l'arbre de travail ou l'index réel du dépôt, donc aucun nettoyage de
  working-tree n'est nécessaire en cas d'échec partiel.

> **Note** : `issue-attachments/` n'est **pas** dans `.gitignore` — c'est
> voulu, puisque les images doivent être suivies et poussées pour que les URL
> `raw` fonctionnent. Cela dit, depuis #248 ce dossier n'existe **que sur la
> branche `pieces-jointes`** : il n'apparaît jamais dans l'arbre de travail
> checké out d'un projet.

---

## 19. Calibration automatique du TIMEOUT (issues #220, #221, #222, #223)

### 19.1 Objectif et principe général

Le champ `TIMEOUT` de l'en-tête d'une issue (§6) est aujourd'hui choisi « à
vue de nez » par Claude Chat (souvent le défaut du formulaire, 300s, ou
600s pour une tâche qui semble plus lourde). Ce système calcule, à partir de
l'**historique réel** des durées de traitement, une valeur suggérée —
`TIMEOUT_suggéré` — par combinaison (projet, `TYPE`, mode, `COMPLEXITE` —
issue #434), pour aider Claude Chat à mieux calibrer ce champ au fil du
temps.

> ℹ️ **4e dimension `COMPLEXITE` (issue #434) :** la clé à 3 dimensions
> `projet|TYPE|mode` mélangeait des populations incompatibles dans la même
> case (ex. une issue de doc de 250s et une refonte de 1800s). Le champ
> `COMPLEXITE` de l'en-tête (§6 — `rapide` / `court` / `normal` / `lourd`,
> défaut `normal` si absent) est désormais inclus dans la clé EWMA :
> `projet|TYPE|mode|complexite`. Les issues sans ce champ (historique
> existant) sont traitées comme `normal` — aucune régression, nouvelles
> clés distinctes, recalibration progressive.

Principe d'inspiration explicitement choisi (validé avec Alain) : l'algorithme
de calcul du **RTO (Retransmission TimeOut) de TCP**, Jacobson/Karels — durée
typique observée + marge proportionnelle à la variabilité récente, réaction
**rapide** à un dépassement (backoff multiplicatif immédiat), et décroissance
**progressive** au retour à la normale (pas un reset brutal au premier succès).
Ce n'est **pas** une simple moyenne/médiane glissante : le système réagit plus
vite à la dégradation qu'il ne « oublie » un épisode difficile.

### 19.2 Formule

```
TIMEOUT_suggéré = max( (duree_typique + k × variabilite) × F × backoff , TIMEOUT_SUGGERE_PLANCHER )
```

- **`duree_typique`** — EWMA (moyenne mobile à pondération exponentielle) de
  la durée réelle des issues **réussies** de cette combinaison projet/`TYPE`/
  mode.
- **`variabilite`** — EWMA de l'écart absolu entre chaque durée réussie et la
  `duree_typique` d'AVANT cette observation (mesure la « nervosité » récente
  de la combinaison, pas juste sa moyenne).
- **`k` (`K_VARIABILITE`)** — marge multipliant la variabilité, pour absorber
  les fluctuations normales sans déclencher de faux timeout.
- **`F`** (facteur d'ambiance, `F_reseau` ou `F_local` selon le contexte) —
  multiplicateur reflétant si les conditions actuelles (réseau/machine) sont
  globalement plus lentes que d'habitude, **planché à 1.0** : F ne fait
  jamais redescendre `TIMEOUT_suggéré` en dessous de sa calibration normale,
  seulement l'allonger en cas de dégradation constatée.
- **`backoff`** (`multiplicateur_backoff`) — multiplicateur propre à la
  combinaison, augmenté immédiatement à chaque timeout réel et ramené à 1.0
  seulement après plusieurs succès rapides consécutifs (décroissance
  progressive, jamais un reset au 1er succès).
- **`TIMEOUT_SUGGERE_PLANCHER`** — plancher absolu appliqué en dernier, quel
  que soit le résultat du calcul — garde-fou contre une suggestion
  dérisoirement basse sur une combinaison encore peu observée.

### 19.3 Fichiers d'état

Deux fichiers JSON, tous deux sous `DOSSIER_LOGS` (`logs/`, fixe — dérivé de
l'emplacement du script `watcher.py`, **pas** du `REP_TRAVAIL` du projet
piloté — donc **partagé entre tous les process watcher**, quel que soit le
projet, et déjà **gitignoré** comme le reste de `logs/`) :

- **`logs/etat_timeout.json`** — une entrée par combinaison
  **`projet|TYPE|mode|complexite`** (4e dimension `complexite` ajoutée par
  l'issue #434, cf. §19.1) : EWMA `duree_typique` et `variabilite` (à
  **demi-vie EN NOMBRE D'ISSUES**, `DEMI_VIE_ISSUES`), `multiplicateur_backoff`,
  compteur `succes_rapides_consecutifs`, `n_observations`.
- **`logs/etat_ambiance.json`** — `F_reseau` et `F_local`, chacun une EWMA à
  **demi-vie TEMPORELLE** (`DEMI_VIE_AMBIANCE_HEURES`, pas en nombre
  d'issues), **GLOBALE à tous les projets** (pas de clé par combinaison).

Les deux sont protégés par un **verrou fichier court** (création atomique
`O_CREAT|O_EXCL`, péremption `VERROU_ETAT_PEREMPTION` = 30s si un process a
été tué en section critique) et une **écriture atomique** (fichier temporaire
+ `os.replace`) — nécessaire puisque plusieurs watchers de projets différents
peuvent clore une issue quasi simultanément sur le même fichier partagé.
Toute la mécanique est **best-effort** : verrou non obtenu ou erreur → mise à
jour abandonnée pour ce cycle (journalisée), jamais propagée au traitement de
l'issue en cours.

**Traçabilité des écritures (issue #521)** : `historique_durees.json` et
`etat_timeout.json` étant tous deux gitignorés (comme le reste de `logs/`),
une perte de données sur l'un d'eux ne laisse par défaut aucune trace
exploitable après coup (pas de diff, pas de commit, pas d'horodatage). Chaque
écriture significative (`enregistrer_duree`, et `_maj_etat_json` pour
`etat_timeout.json` uniquement) ajoute désormais une ligne à
`logs/journal_ecritures_historique.jsonl` (JSON Lines, append-only, lui-même
déjà couvert par le `.gitignore` de `logs/`) : nombre d'entrées et taille en
octets AVANT/APRÈS l'écriture, plus `reinitialise_corruption=true` si
l'écriture est repartie d'un fichier illisible (JSON corrompu) — la
signature d'une perte de données silencieuse. Une chute de `nb_avant` par
rapport au `nb_apres` de la ligne précédente pour le même fichier permet de
dater un futur incident similaire, sans avoir besoin de suivre ces fichiers
dans git (ce qui alourdirait chaque commit de sauvegarde CCL, ces fichiers
grossissant à chaque issue close). Cf. `_journaliser_ecriture`.

### 19.4 Constantes actuelles et leur statut

| Constante | Valeur | Rôle |
|-----------|--------|------|
| `K_VARIABILITE` | `4` | Multiplicateur de `variabilite` dans la formule |
| `DEMI_VIE_ISSUES` | `15` | Demi-vie (en nombre d'issues) de l'EWMA `duree_typique`/`variabilite` |
| `DEMI_VIE_AMBIANCE_HEURES` | `4.0` | Demi-vie (en heures) de l'EWMA `F_reseau`/`F_local` |
| `SEUIL_SUCCES_RAPIDE` | `0.7` | Un succès est « rapide » si `duree_reelle < 0.7 × timeout_courant` |
| `SUCCES_RAPIDES_POUR_RESET` | `3` | Nombre de succès rapides consécutifs pour remettre `multiplicateur_backoff` à 1.0 |
| `FACTEUR_BACKOFF` | `1.5` | Multiplicateur appliqué à `multiplicateur_backoff` à chaque timeout de la combinaison |
| `TIMEOUT_SUGGERE_PLANCHER` | `30` (s) | Plancher absolu de `TIMEOUT_suggéré` |

> ⚠️ **Ce sont des valeurs de DÉPART, pas des valeurs backtestées** sur
> l'historique réel de `historique_durees.json` — choisies par analogie avec
> le RTO TCP et le bon sens (cf. commentaire de `TIMEOUT_SUGGERE_PLANCHER`
> dans `watcher.py`, basé sur le 5e percentile observé des durées réussies
> au 2026-07-25). Elles sont **à revisiter** une fois assez de données
> accumulées — notamment de **vrais timeouts**, inexistants dans
> l'historique à ce jour (au 2026-07-25, `historique_durees.json` ne compte
> que des issues réussies).

### 19.5 Où voir la suggestion

Le **commentaire de clôture GitHub** d'une issue — succès (`fermer_issue`
suivi d'une édition du commentaire de résultat) comme **échec définitif**
(label `needs-human` posé) — affiche désormais un bloc :

```
---
⏱️ Durée réelle : 187s (TIMEOUT courant : 300s)
📊 TIMEOUT_suggéré (calibration automatique, issue #221) : 245s
```

(`formater_bloc_calibration`). C'est le **seul canal actuel** par lequel
Claude Chat peut prendre connaissance de la calibration : il n'a **pas
d'accès direct** aux fichiers d'état gitignorés du ThinkPad
(`etat_timeout.json`, `etat_ambiance.json`, `historique_durees.json`).

**Rien n'applique automatiquement cette suggestion.** Le TIMEOUT réellement
utilisé pour lancer `claude` reste exclusivement celui écrit dans l'en-tête
de l'issue, lu par `extraire_timeout()` — `TIMEOUT_suggéré` est calculé et
journalisé (`maj_calibration_timeout`) à chaque clôture, mais n'a **aucun
effet** sur le comportement d'exécution. C'est à **Claude Chat**, à la
lecture du commentaire, d'ajuster manuellement le `TIMEOUT` des futures
issues de la même combinaison s'il le juge utile.

### 19.6 Limitations connues, à traiter plus tard

- **Démarrage à froid trompeur** : la toute première observation réussie
  d'une combinaison (projet, `TYPE`, mode) donne `variabilite = 0` (pas
  d'écart mesurable sans historique préalable), donc un `TIMEOUT_suggéré`
  initial **sans marge de variabilité** (hors plancher absolu) —
  trompeusement optimiste pour une combinaison neuve, avant que quelques
  observations supplémentaires ne stabilisent l'EWMA.
- **Aucune des constantes du §19.4 n'a encore été validée par backtest** sur
  `historique_durees.json`.
- Le badge d'estimation de l'interface web (`estimer_duree` dans
  `app/issues.py`, médiane simple utilisée pour le temps restant estimé côté
  navigateur — système **distinct** de celui décrit ici) **exclut désormais
  les entrées `expiree=true`** depuis l'issue #223, sans effet sur la
  calibration TIMEOUT elle-même, même si les deux lisent le même fichier
  source (`historique_durees.json`).

### 19.7 Historique d'implémentation

- **#220** — extension d'`historique_durees.json` avec les champs bruts
  nécessaires à la calibration (`longueur_corps_issue`, `nb_etapes_checklist`,
  `nb_projets_actifs_au_lancement`, `expiree`, `tag_reseau` si connu) et
  enregistrement systématique des tentatives expirées (pas seulement
  l'abandon définitif).
- **#221** — mécanique EWMA complète : `etat_timeout.json`/`etat_ambiance.json`,
  `maj_calibration_timeout`, calcul et journalisation de `TIMEOUT_suggéré` à
  chaque clôture d'issue (succès ou timeout), sans effet sur le TIMEOUT
  réellement appliqué.
- **#222** — exposition du `TIMEOUT_suggéré` dans le commentaire de clôture
  GitHub (`formater_bloc_calibration`), succès et échec définitif
  (`lire_timeout_suggere` pour l'échec, simple lecture sans double comptage).
- **#223** — exclusion des entrées `expiree=true` du calcul du badge
  d'estimation de durée de l'interface web (`estimer_duree`), pour ne pas
  fausser la médiane affichée à Alain avec des tentatives avortées.
- **#435** — `_detecter_tag_reseau` implémenté : lecture du champ d'en-tête
  `RESEAU` (`oui`/`non`, §6), calquée sur `extraire_complexite`. `F_reseau`/
  `F_local` sont désormais réellement alimentés. `lire_timeout_suggere`
  reçoit en plus un paramètre `body` pour choisir le bon `F` sur le chemin
  échec définitif, au lieu de toujours retomber sur `F_local`.
- **#521** — traçabilité des écritures (`logs/journal_ecritures_historique.jsonl`,
  cf. ci-dessus) suite à une coupure nette de `historique_durees.json`
  restée inexpliquée faute de preuve (fichier gitignoré, aucun historique
  git natif).

---

## 20. Formulaire web `new_issue.py` — méthode de backup (issue #483)

Depuis l'issue #483, la méthode normale de création d'issue est le watcher `issues_inbox` (§3) : déposer un fichier `.txt` dans `issues_inbox/`, sans interaction manuelle. Le formulaire web `new_issue.py` reste pleinement fonctionnel et documenté ci-dessous, comme méthode de **backup**, avec des cas d'usage propres : consulter l'**aperçu de la commande** `gh issue create` avant envoi (bouton « Aperçu de la commande », voir plus bas) ; création manuelle par Alain directement depuis l'interface, sans passer par un fichier ; et repli si le watcher spool `issues_inbox` est indisponible ou arrêté (§3.10).

Via l'interface web `new_issue.py` (Flask, port 5100) :

```bash
# Mode local (devant le ThinkPad)
python3 new_issue.py

# Mode LAN (accès depuis le réseau local, ex. PC fixe Windows) — issue #461
python3 new_issue.py --lan
# → écoute sur 0.0.0.0:5100, HTTP, sans tunnel, sans mot de passe
# → destiné à un LAN de confiance uniquement, rien n'est exposé vers l'extérieur

# Mode externe (accès depuis téléphone via Cloudflare)
python3 new_issue.py --externe
# → tunnel cloudflared automatique sur https://bridge.frederiqueferette.be
# → login mot de passe requis
```

**Lancement supervisé avec log (recommandé, issue #150) :** le wrapper
`lancer_new_issue.sh` fait exactement la même chose que `python3 new_issue.py`
(mêmes arguments) mais horodate le démarrage/arrêt/code de sortie et capture
stdout+stderr dans `logs/new_issue.log` (rotation par taille, comme les
watchers) — utile pour diagnostiquer un plantage silencieux. La sortie reste
affichée dans le terminal (`tee`). `python3 new_issue.py` reste valable et
inchangé.

```bash
./lancer_new_issue.sh                 # mode local, avec log
./lancer_new_issue.sh --lan           # mode LAN, avec log
./lancer_new_issue.sh --externe       # mode externe, avec log
# Après un plantage : voir les dernières lignes de logs/new_issue.log
```

**Bouton « Aperçu de la commande » (issue #285) :** avant d'envoyer, ce
bouton appelle la route `/apercu` (fonction `apercu()` de `app/issues.py`),
qui construit — à partir des champs actuellement remplis dans le
formulaire — la commande `gh issue create` exacte qui serait exécutée
(dépôt, titre, labels, `--body-file`), suivie en commentaire du corps
complet qui serait envoyé. Cette commande est renvoyée en JSON et affichée
telle quelle, en texte brut, dans la zone `zone-apercu` sous le formulaire
(fonction `afficherApercu()` de `static/js/app.js`). C'est un aperçu pur :
aucune issue n'est créée, aucune commande n'est réellement exécutée — rien
n'est modifié tant que le bouton d'envoi n'est pas cliqué séparément.

**Format du corps reconnu par le formulaire :**

La première ligne du corps peut contenir `#Titre:` — new_issue.py détecte
ce tag et remplit automatiquement le champ Titre, quelle que soit la façon
dont le corps a été saisi dans le formulaire (frappe manuelle par Alain,
par exemple). C'est le même format que celui attendu par le watcher
`issues_inbox` (§3.3) pour les fichiers `.txt` que Claude Chat y dépose —
Claude Chat ne doit en revanche jamais produire ce texte pour qu'Alain le
copie-colle ici. **Ce formulaire reste un repli légitime, mais c'est à
Alain de décider de l'utiliser — jamais à Claude Chat d'y basculer de sa
propre initiative** : si l'outil fichier manque dans la conversation en
cours (§11), Claude Chat le signale et demande la marche à suivre plutôt
que de présenter le texte en clair en invoquant ce formulaire comme
justification (issue #685) :

```
#Titre: Titre court et actionnable

## Contexte
Pourquoi cette tâche existe.

## Tâche demandée
Description précise. Indiquer explicitement si LECTURE SEULE.

## Résultat attendu
Ce que CCL doit produire ou confirmer.
```

**Champs d'en-tête optionnels reconnus (`PROJET`, `TIMEOUT`, `MODELE`, `MODE`,
`LABELS`) :**

`| MODE | … |` (issue #326) est détecté par `new_issue.py`
(`detecterModeDansCorps`) exactement comme `TIMEOUT`/`PROJET`/`MODELE` :
la valeur reconnue pré-sélectionne le radio Mode du formulaire, puis la
ligne est retirée du corps saisi dans le champ (le tableau d'en-tête final
est reconstruit depuis le formulaire, pas depuis le texte brut du champ
Corps). Les **trois**
valeurs du mode (voir §5) sont reconnues : `| MODE | lecture |`,
`| MODE | lecture active |` et `| MODE | écriture |`. La reconnaissance
est **tolérante** — insensible à la casse et aux accents, plusieurs libellés
acceptés par valeur (ex. « écriture »/« ecriture »/« write » ;
« lecture active »/« scratch »/« mode_scratch » ;
« lecture »/« lecture seule »/« read ») — et le **défaut est LECTURE** si le
champ `MODE` est absent du corps ou si sa valeur n'est reconnue par aucun
synonyme : une issue doit toujours déclarer explicitement l'écriture (ou la
lecture active) pour l'obtenir, jamais par omission. En mode mono-issue,
cette détection ne pilote que le radio du formulaire (choix unique) ; en
mode lot, chaque bloc peut porter son propre `MODE` — voir « Envoi en lot »
ci-dessous.

Au même titre que `PROJET`/`TIMEOUT`/`MODELE`, `new_issue.py` reconnaît aussi
un champ `| LABELS | … |` dans l'en-tête du corps du formulaire. Sa valeur est une liste de
labels séparés par des virgules (les espaces superflus autour de chacun sont
ignorés) qui **s'ajoutent** aux labels standards posés automatiquement (`bridge`,
`for-linux`, `mode_write` selon le MODE, notifications) — ils ne les remplacent
pas. Cas d'usage concret : `| LABELS | for-windows |` pour créer, depuis le flux
web habituel, une issue destinée à l'agent Windows CCW (label `for-windows`, cf.
§16) sans repasser par `gh issue create` en ligne de commande. Voir §14 pour
le critère de choix entre cette issue `for-windows` directe et le pattern
chef → ouvrier. Plusieurs labels
sont possibles : `| LABELS | for-windows,urgent |`. Aucun contrôle d'existence du
label n'est fait ici : si le label n'existe pas sur le dépôt, `gh issue create`
échoue avec un message clair. En mode lot, chaque bloc `#Titre:` peut porter ses
propres `LABELS`.

> ⚠️ `for-windows` **retire** `for-linux` (issue #164) : `for-linux` et
> `for-windows` sont mutuellement exclusifs — une tâche cible CCL *ou* CCW,
> rarement les deux. Une issue `| LABELS | for-windows |` créée par ce flux ne
> portera donc *pas* `for-linux` et ne sera vue que par le watcher CCW. Les
> autres labels standards (`bridge`, `mode_write`, notifications) restent posés
> normalement, et tout autre label listé dans `LABELS` est ajouté tel quel. Pour
> forcer les deux watchers sur une même issue (cas rare), ajouter `for-linux`
> manuellement sur GitHub après création.

**Envoi en lot (plusieurs issues dans un même corps) — issue #135 :**
placer *plusieurs* blocs `#Titre:` à la suite dans le même corps déclenche
automatiquement le **mode lot** : le bouton d'envoi devient
« Envoyer le lot (N issues) ». Chaque bloc va de son `#Titre:` jusqu'au
`#Titre:` suivant et est traité comme une issue indépendante, avec ses propres
champs d'en-tête optionnels (`PROJET`, `TIMEOUT`, `MODELE`, `MODE`, `LABELS`) —
à défaut, les valeurs du formulaire (projet sélectionné, timeout, modèle, mode
du radio) s'appliquent en repli (le champ `LABELS`, lui, est propre à chaque
bloc : sans fallback). Seules les **notifications** restent communes à tout le
lot.

**Mode mixte, les trois modes (issue #505) :** contrairement à un
fonctionnement antérieur où `MODE` restait commun à tout le lot (seul le radio
du formulaire décidait, un `| MODE | … |` par bloc étant ignoré), chaque bloc
porte désormais son propre `MODE` — `modeEffectifBloc()`, source unique
partagée par `mettreAJourBoutonLot()` (libellé du bouton, qui signale
« — modes mixtes » si plusieurs modes distincts sont détectés dans le lot) et
`envoyerLot()` (envoi réel) : le `MODE` du bloc s'il est présent (reconnu de
façon tolérante, les trois valeurs, §5), sinon le radio du formulaire en
repli. Un même lot peut donc librement mélanger des blocs en lecture, lecture
active et écriture. Ce contournement (envoyer des lots séparés par mode) reste
possible mais n'est plus nécessaire.

Les issues partent **en séquence** (une à la fois, jamais en parallèle),
**sans validation intermédiaire** (aucune modale « issues en attente » ni
d'incohérence projet) : un bloc dont le `PROJET` diffère du projet sélectionné
part quand même sur *son* `PROJET` et c'est simplement signalé ; un bloc en
échec n'interrompt pas le lot. À la fin, un **résumé** liste, pour chaque bloc,
le titre + le lien de l'issue créée ou le message d'erreur, puis le corps est
vidé. Un seul bloc `#Titre:` conserve le comportement mono-issue habituel
(bouton « Envoyer sur <projet> », détection automatique du titre).

**Regroupement des blocs pour le mode lot (issue #153, étendue par #443) :**
pour que le formulaire détecte le mode lot, les blocs `#Titre:` de plusieurs
issues doivent se trouver à la suite dans **un seul et même corps** (pas un
bloc séparé par issue) — même règle de découpage côté fichier `.txt` déposé
dans `issues_inbox/` (§3.13). Cette convention ne concerne plus Claude Chat :
il ne doit plus jamais présenter de texte destiné à être copié-collé dans ce
formulaire, quel que soit le nombre d'issues — voir §3 pour son flux normal
de création d'issue, seul valable pour du contenu qu'il produit.

> ⚠️ **Claude Chat doit toujours inclure** `| PROJET | <nom> |` dans l'en-tête
> des issues qu'il génère (nom exact du projet cible : `bridge_agent`,
> `alchess`, `ff_galerie`). Détaillé au §6 « Champs spéciaux ».

> ⚠️ **Exception pour les issues `for-windows` (modèle CCW unifié, §16.3) :**
> `PROJET` reste toujours `bridge_agent`, même si le build cible un autre projet
> (ex. `actualise`) — c'est la config du watcher CCW unique, pas le projet
> réellement construit. Le nom du projet cible s'exprime en texte dans le corps
> de l'issue (chemins, commandes `git clone`/`git pull`), voir le template du
> §16.3.

> 🔗 **Issue de suivi** : si l'issue fait suite à une discussion sur une issue
> existante #N, préfixer le titre par `Suite #N : ` et inclure
> `| SUITE_DE | #N |` dans l'en-tête. Sans ce préfixe/champ, l'issue est
> considérée comme inédite. (Convention cohérente avec `Chef :`/`Ouvrier N :`
> du §14 ; voir aussi le champ `SUITE_DE` au §6.)

---

*Dernière mise à jour : 8 octobre 2026 — issue #629 (étape 5a de la
refonte web, §6 d'`ARCHITECTURE.md`) : nouveau backend d'état serveur pour
la case « traité/lu » de l'onglet Résultats, jusqu'ici 100% localStorage
(issue #154) — `etat_cases_cochees.py` (fichier JSON sous `logs/`, écriture
atomique + verrou anti-collision, même modèle que `etat_rate_limit.py`,
#615) et ses routes Flask `app/cases_cochees.py` (lire l'état d'un projet,
cocher/décocher une issue, importer en masse — toutes protégées par
`login_requis` comme le reste de l'interface). Nettoyage sans aucun appel
GitHub : au démarrage de `new_issue.py`, les coches dont le numéro est
inférieur ou égal à (plus grand numéro connu du projet − 50, le plafond de
`app/issues.py::LIMITE_ISSUES_MAX`) sont retirées ; à la suppression d'un
projet (flux #587), toutes ses coches le sont aussi. Backend seul :
**aucun changement visible**, aucun front ne l'utilise encore — la reprise
du localStorage existant viendra à l'étape 5b. Tests :
`tests/test_cases_cochees_629.py`.

Précédemment — 24 septembre 2026 — issue #584 : le verrou
anti-collision `REP_TRAVAIL` (section « Parallélisation mode_write via git
worktrees », #189/#322) gagne un filet de sécurité complémentaire. Incident
réel : issue #583 (canal unifié for-windows, mode_write) bloquée 48 minutes,
chaque cycle affichant « un autre traitement détient déjà le verrou sur
C:\CCW_Share ». Hypothèse initiale (un chemin de sortie anticipée de
`_traiter_issue_synchrone`, ex. refus précoce avant tout travail réel, ne
relâcherait pas le verrou faute de `try`/`finally`) vérifiée puis
**INFIRMÉE** par lecture de code : le `try`/`finally` entourant le verrou
existe depuis #189 (2026-07-20) et couvre déjà tous les chemins de sortie, y
compris les refus précoces — confirmé par
`tests/test_verrou_refus_precoce_584.py`. Cause réelle la plus probable :
un watcher tué brutalement (crash, `kill -9`, redémarrage de service)
pendant qu'il détenait le verrou — aucun `try`/`finally` Python n'y survit,
sur aucune plateforme ; le seul filet existant (péremption par ancienneté,
issue #322) se calcule à partir de `max_essais × TIMEOUT_projet`,
potentiellement des dizaines de minutes pour un projet à `TIMEOUT` élevé
(1800 s dans #583), expliquant l'ordre de grandeur observé. Nouveau filet
complémentaire dans `acquerir_verrou` : le PID du watcher propriétaire
(champ `pid=` du fichier verrou, écrit dès la pose) est sondé
(`_pid_vivant`, POSIX `os.kill(pid, 0)` / Windows `OpenProcess`) ; confirmé
mort, le verrou est repris immédiatement, sans attendre la péremption par
ancienneté — corrige directement le délai de #583. Asymétrie volontaire :
PID introuvable ⇒ orphelin certain, PID vivant/sonde en échec/plateforme non
gérée ⇒ verrou considéré actif par prudence (repli sur le critère
d'ancienneté existant, jamais moins sûr qu'avant #584). §16.4 (dépannage
« Interrompre une issue CCW coincée ») mis à jour en conséquence.

Précédemment — 21 septembre 2026 — Section « Parallélisation
mode_write via git worktrees » (#337) : isolation de `REP_TRAVAIL`
désormais **systématique**, y compris à `MAX_WRITE_PARALLELE = 1` (issue
#577). Incident réel ayant motivé ce changement, sur `relecture_bridge`
(`MAX_WRITE_PARALLELE=1`) : Alain a fait un `git commit`/`git stash` manuel
dans `REP_TRAVAIL` pendant qu'une issue `mode_write` y travaillait
directement (comportement d'avant #577) — collision directe, une
modification manuelle temporairement effacée, récupérée de justesse depuis
un commit orphelin. `MAX_WRITE_PARALLELE` (parallélisation **entre**
tâches CCL) et l'isolation de CCL vis-à-vis d'Alain sont deux besoins
distincts que le couplage précédent confondait. Condition
`CFG.max_write_parallele > 1` retirée du côté worktree dans `traiter_issue`
(`watcher.py`) : à `MAX_WRITE_PARALLELE ≤ 1`, `_creer_worktree` est
maintenant appelée avant `_traiter_issue_synchrone`, qui reste appelée
directement (sans thread) — seule la présence d'un worktree change, le
modèle d'exécution (synchrone vs threads) reste piloté par
`MAX_WRITE_PARALLELE` comme avant. Nettoyage/traçabilité déjà en place
(alerte d'accumulation #432, comptage `MAX_WRITE_PARALLELE` via
`needs-human` #576) inchangés, aucun traitement spécial ajouté pour ces
worktrees « solo » — ils sont indiscernables des worktrees créés en
parallélisation. Tests étendus dans
`tests/test_worktree_parallelisation_337.py` : isolation effective à
`MAX_WRITE_PARALLELE=1` (worktree utilisé, `REP_TRAVAIL` inchangé — même
HEAD, aucun fichier ajouté) et repli propre sur `REP_TRAVAIL` si la
création du worktree échoue.*

Historique complet : voir [`CHANGELOG.md`](CHANGELOG.md).
