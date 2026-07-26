# Bridge_Agent — Documentation de référence

Document destiné à Claude Chat (CC) pour comprendre et utiliser le bridge
inter-agents d'Alain. À lire en début de conversation impliquant Bridge_Agent.

---

## 1. Vue d'ensemble

Bridge_Agent est un système qui permet à Claude Chat (toi) de déléguer des
tâches à Claude Code Linux (CCL) via des GitHub Issues. CCL s'exécute sur le
ThinkPad d'Alain et surveille les issues en continu.

**Flux complet :**
```
Claude Chat → crée une issue → GitHub → watcher.py détecte → CCL exécute
→ poste le résultat en commentaire → ferme l'issue → notification GSM/bureau
```

> **Rafraîchissement automatique du clone local en début de cycle (issue #185).**
> Au début de **chaque cycle de polling** — juste avant de lister les issues
> ouvertes — `watcher.py` lance un `git pull --ff-only` dans son répertoire de
> travail (`REP_TRAVAIL`). Le watcher travaille donc toujours sur le code le plus
> récent poussé sur `origin`, **sans git pull manuel préalable**.
>
> - **Succès (cas normal)** : le clone est avancé en fast-forward (ou est déjà à
>   jour) — transparent, une simple ligne `[pull] … mis à jour` / `déjà à jour`
>   dans le log.
> - **Divergence** (des commits locaux non poussés existent — typiquement le
>   `backup + fix` que le watcher committe à chaque tâche en attendant qu'Alain
>   vérifie puis pousse) : le `--ff-only` échoue **proprement**, **RIEN n'est
>   écrasé ni perdu**, et le watcher **poursuit sur le code local existant**.
>   Oublier un `git push` avant qu'un watcher ne tourne ne présente donc
>   **aucun risque** — au pire le watcher tourne sur du code un cran moins récent,
>   jamais sur du code corrompu.
> - **Réseau indisponible ou dossier hors dépôt git** : simplement journalisé,
>   jamais bloquant — le pull est un confort de fraîcheur, pas une précondition.
>
> **Même LOGIQUE pour CCL et CCW, mais PAS le même effet (issue #240).** Le
> pull porte sur `REP_TRAVAIL` — c'est bien le même script, la même logique,
> aucune configuration supplémentaire par projet. Mais `REP_TRAVAIL` ne
> désigne PAS forcément le clone qui contient le **code de `watcher.py`
> lui-même** :
> - **Côté CCL** : `REP_TRAVAIL` **EST** le clone du dépôt Bridge_Agent, donc
>   ce pull met bien à jour le code du watcher en plus des fichiers projet.
> - **Côté CCW en modèle unifié** (#231) : `REP_TRAVAIL = \\VBOXSVR\CCW_Share`
>   n'est **même pas un dépôt git** (§16), et le clone qui contient
>   `watcher.py` (`C:\CCW\Bridge_Agent`) vit **ailleurs** — ce pull ne le
>   touche donc **jamais**. Voir le bloc d'avertissement du §16 pour la
>   procédure de mise à jour de ce clone, distincte et non automatique.
>
> **Projets à périmètre dynamique.** Certains projets ont un dépôt-cible
> défini **par l'issue elle-même** plutôt que par `REP_TRAVAIL` (dépôts
> d'audit, pas le clone de travail du watcher) : ce pull automatique ne les
> concerne pas et ne les rafraîchit jamais — volontairement, ce n'est pas un
> oubli.
>
> Rien n'empêche de continuer à faire un `git pull` (ou à relancer le watcher)
> **manuellement** si l'on veut la mise à jour immédiate, sans attendre le
> prochain cycle de polling — c'est désormais un confort, plus une nécessité.

---

## 2. Projets actifs

| Nom | Dépôt GitHub | Répertoire de travail CCL | Topic ntfy |
|-----|-------------|--------------------------|------------|
| `bridge_agent` | AlainDelree/Bridge_Agent | ~/Bridge_Agent | (conf local) |
| `alchess` | AlainDelree/AlChess | ~/NicLink | (conf local) |
| `ff_galerie` | AlainDelree/FF_Galerie | ~/FF_Galerie | (conf local) |
| `ecole` | AlainDelree/Ecole | ~/Ecole | (conf local) |
| `scrabble` | AlainDelree/Scrabble | ~/Scrabble | (conf local) |
| `diagnostique_programme` | AlainDelree/Diagnostique_Programme | ~/Diagnostique_Programme | (conf local) |
| `actualise` | AlainDelree/Actualise | ~/Actualise | (conf local) |
| `bloc_score` | AlainDelree/Bloc_score | ~/Bloc_score | (conf local) |

Chaque projet a son propre watcher (`watcher.py --config configs/<nom>.conf`)
et son propre journal de log (`logs/watcher-<nom>.log`).

---

## 3. Créer une issue — la méthode normale

Via l'interface web `new_issue.py` (Flask, port 5100) :

```bash
# Mode local (devant le ThinkPad)
python3 new_issue.py

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
./lancer_new_issue.sh --externe       # mode externe, avec log
# Après un plantage : voir les dernières lignes de logs/new_issue.log
```

**Format du corps pour copier-coller depuis Claude Chat :**

La première ligne du corps peut contenir `#Titre:` — new_issue.py détecte
ce tag et remplit automatiquement le champ Titre. Un seul copier-coller suffit :

```
#Titre: Titre court et actionnable

## Contexte
Pourquoi cette tâche existe.

## Tâche demandée
Description précise. Indiquer explicitement si LECTURE SEULE.

## Résultat attendu
Ce que CCL doit produire ou confirmer.
```

**Champs d'en-tête optionnels reconnus (`PROJET`, `TIMEOUT`, `MODELE`, `LABELS`) :**
au même titre que `PROJET`/`TIMEOUT`/`MODELE`, `new_issue.py` reconnaît un champ
`| LABELS | … |` dans l'en-tête du corps collé. Sa valeur est une liste de
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

**Envoi en lot (plusieurs issues d'un seul copier-coller) — issue #135 :**
coller *plusieurs* blocs `#Titre:` à la suite dans le même corps déclenche
automatiquement le **mode lot** : le bouton d'envoi devient
« Envoyer le lot (N issues) ». Chaque bloc va de son `#Titre:` jusqu'au
`#Titre:` suivant et est traité comme une issue indépendante, avec ses propres
champs d'en-tête optionnels (`PROJET`, `TIMEOUT`, `MODELE`, `LABELS`) — à défaut,
les valeurs du formulaire (projet sélectionné, timeout, modèle) s'appliquent en
repli (le champ `LABELS`, lui, est propre à chaque bloc : sans fallback). Le `MODE` (lecture/écriture) et les notifications sont communs à tout le
lot. Les issues partent **en séquence** (une à la fois, jamais en parallèle),
**sans validation intermédiaire** (aucune modale « issues en attente » ni
d'incohérence projet) : un bloc dont le `PROJET` diffère du projet sélectionné
part quand même sur *son* `PROJET` et c'est simplement signalé ; un bloc en
échec n'interrompt pas le lot. À la fin, un **résumé** liste, pour chaque bloc,
le titre + le lien de l'issue créée ou le message d'erreur, puis le corps est
vidé. Un seul bloc `#Titre:` conserve le comportement mono-issue habituel
(bouton « Envoyer sur <projet> », détection automatique du titre).

**Convention de présentation côté Claude Chat (issue #153) :** quand Claude
Chat prépare plusieurs issues à la fois pour ce mode lot, il les présente
toutes à la suite dans **un seul bloc de code** (pas un bloc séparé par
issue), afin qu'Alain puisse copier l'ensemble en un clic et le coller
directement dans le champ Corps.

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

## 4. Labels disponibles

| Label | Effet |
|-------|-------|
| `for-linux` | **Requis** — le watcher ne voit que ces issues |
| `bridge` | Marque l'issue comme tâche bridge (traçabilité) |
| `mode_write` | **ARME le mode écriture** — CCL peut modifier des fichiers |
| `needs-human` | Posé automatiquement après 3 échecs — stoppe le retraitement |
| `done` | Posé automatiquement au succès |
| `notif_pc` | Ajoute une notification bureau (notify-send) |
| `notif_gsm` | Ajoute une notification push (ntfy) |
| `notif_tous` | notify-send + ntfy |

> Sans label `notif_pc` / `notif_gsm` / `notif_tous`, aucune notification
> sonore ou push n'est déclenchée. Le bip est strictement opt-in.

---

## 5. Modes lecture seule vs écriture

**Lecture seule (défaut)** — CCL peut lire, analyser, grep, rapporter.
Ne peut PAS écrire de fichier ni exécuter de commande modifiant le système.
Idéal pour : diagnostics, audits, lectures de fichiers, comptages.

**Mode écriture (`mode_write`)** — CCL peut modifier des fichiers, exécuter
des commandes, faire des commits git.
Garde-fous automatiques :
- Backup pinné **avant** toute modification (via `CMD_BACKUP` du `.conf`)
- **JAMAIS `git push`** — Alain pousse lui-même après vérification
- Aucune commande destructrice sans demande explicite
- Périmètre strict : CCL ne travaille que dans le dossier configuré

---

## 6. Champs spéciaux dans le corps de l'issue

Le watcher lit ces champs dans le tableau markdown de l'en-tête :

| Champ | Valeur | Effet |
|-------|--------|-------|
| `PRIORITE` | `haute` ou `critique` | Retry infini (au lieu de 3 max) |
| `TIMEOUT` | ex. `600s` | Surcharge le timeout par défaut (300s) |
| `MODELE` | ex. `claude-opus-4-5` | Force un modèle CCL spécifique pour cette issue |
| `PROJET` | ex. `bridge_agent` | Détection d'incohérence dans `new_issue.py` (issue #44). Inséré automatiquement par l'interface. Claude Chat doit l'inclure dans toutes les issues qu'il génère. |
| `TYPE` | `chef` ou `ouvrier` | Identifie le rôle de l'issue dans le pattern multi-agent. `chef` = orchestre les ouvriers. `ouvrier` = sous-tâche créée par le chef, masquée par défaut dans l'onglet Résultats. Absent = issue normale. |
| `FICHIER_CONTEXTE` | ex. chemin relatif | Fichier additionnel fourni en contexte à CCL pour cette issue (modifiable via l'onglet Configuration, voir §12) |
| `SUITE_DE` | ex. `#5` | Indique que cette issue fait suite à l'issue #N (discussion ou tâche complémentaire). Absent = issue inédite. |

Format dans le corps :
```markdown
| PRIORITE | haute |
| TIMEOUT  | 600s  |
| MODELE   | claude-opus-4-5 |
| PROJET   | bridge_agent |
```

> ⚠️ **Claude Chat doit toujours inclure** `| PROJET | <nom> |` dans l'en-tête
> des issues qu'il génère, avec le nom exact du projet cible
> (`bridge_agent`, `alchess`, `ff_galerie`).

> ℹ️ Le champ `| LABELS | … |` (issue #161) n'est **pas** lu par le watcher :
> il est consommé par `new_issue.py` au moment de la création pour ajouter des
> labels supplémentaires (ex. `for-windows`) à ceux posés d'office. Voir §3.

---

## 7. Périmètre par projet

CCL est contraint à un répertoire précis par projet — il refuse de travailler
hors périmètre même si l'issue le demande explicitement :

| Projet | Périmètre autorisé |
|--------|-------------------|
| `bridge_agent` | /home/alain/Bridge_Agent |
| `alchess` | /home/alain/NicLink |
| `ff_galerie` | /home/alain/FF_Galerie |
| `ecole` | /home/alain/Ecole |
| `scrabble` | /home/alain/Scrabble |
| `diagnostique_programme` | /home/alain/Diagnostique_Programme |
| `actualise` | /home/alain/Actualise |
| `bloc_score` | /home/alain/Bloc_score |

---

## 8. Sécurité

- **Défense en profondeur** : SSL + mot de passe (mode externe) + watcher
  éteint par défaut + périmètre CCL + git comme filet de retour arrière.
- **Mot de passe** : stocké hashé sha256 dans `configs/bridge_agent.conf`.
  Générer/changer : `python3 new_issue.py --set-password`
- **configs/*.conf** : gitignoré — jamais versionné (contient topic ntfy et
  mot de passe hashé).
- **ssl/** : gitignoré — certificat auto-signé, clé privée jamais versionnée.
- **Repo public** : le dépôt GitHub est public — le code source est lisible
  par tous. C'est sans risque car tout ce qui est sensible est gitignoré :
  `configs/*.conf` (topic ntfy, mot de passe hashé), `ssl/` (clé privée),
  `logs/`, `venv/`. Le repo ne contient que du code et de la documentation.

---

## 9. Accès externe

URL publique via tunnel Cloudflare :
```
https://bridge.frederiqueferette.be
```

Lancé automatiquement par `python3 new_issue.py --externe`.
Nécessite : cloudflared installé + `~/.cloudflared/config.yml` configuré
+ `MOT_DE_PASSE` dans le `.conf`.

**Accès à la doc sans token** : le repo étant public, `BRIDGE_AGENT_DOC.md`
est accessible directement (sans authentification) — utile pour les
instructions personnalisées Claude :
```
https://raw.githubusercontent.com/AlainDelree/Bridge_Agent/master/BRIDGE_AGENT_DOC.md
```

⚠️ Pour une lecture fiable et à jour par Claude Chat, privilégier une
récupération via curl/bash plutôt que web_fetch, qui peut servir une
version mise en cache de cette page :
```bash
curl -sL https://raw.githubusercontent.com/AlainDelree/Bridge_Agent/master/BRIDGE_AGENT_DOC.md
```
Si l'outil terminal n'est pas disponible dans la conversation, se rabattre
sur web_fetch en étant conscient du risque de contenu obsolète.

⚠️ **Cache CDN après un push très récent.** Même `curl` peut, dans les
toutes premières minutes suivant un `git push`, servir une version encore
mise en cache par le CDN GitHub (raw.githubusercontent.com), avant que
l'invalidation ne se propage. Si un `git push` sur `BRIDGE_AGENT_DOC.md`
vient d'avoir lieu (il y a quelques minutes) et que le contenu lu ne semble
pas refléter ce changement, ajouter un paramètre anti-cache à l'URL **avant
de conclure à une absence réelle du contenu** :
```bash
curl -sL "https://raw.githubusercontent.com/AlainDelree/Bridge_Agent/master/BRIDGE_AGENT_DOC.md?nocache=$(date +%s)"
```
Ce contournement n'est utile qu'en cas de push très récent (quelques
minutes) ; dans le cas général, un `curl` simple sans paramètre reste la
méthode par défaut recommandée.

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
  templates/          — gabarits HTML (Jinja2)
  static/             — CSS, JS, assets statiques
  consignes/          — consignes injectées dans le prompt CCL par watcher.py (§12.1)
    globales.md       — NON-optionnel : rappels de sécurité, TOUTE issue
    type_chef.md      — optionnel : consignes du TYPE « chef »
    (type_<type>.md et projet_<projet>.md créés à la demande, facultatifs)
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

---

## 11. Conventions de code

- **Langue** : français pour tout ce qu'Alain et Claude nomment librement
  (identifiants Python, commentaires, clés de config). Anglais conservé pour
  les contrats existants (noms de labels GitHub, drapeaux CLI, mots-clés Python).
- **Issues** : produire titre + corps avec `#Titre:` en première ligne du corps.
  Alain colle le tout dans le champ Corps de new_issue.py — un seul copier-coller.
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

**Exception :** les modifications de `configs/*.conf` (`TOPIC_NTFY`,
`FICHIER_CONTEXTE`, etc.) peuvent se faire directement via
l'onglet Configuration de new_issue.py — elles ne touchent
pas au code et sont gitignorées.

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

**Couverture universelle (issue #211).** Une issue peut naître de trois chemins :
(1) le formulaire web (`new_issue.py`), (2) un CCL « chef » via `gh issue create`
en ligne de commande (§14, pattern Chef → Ouvrier), (3) une création manuelle
directe sur GitHub (§3). En #209 les consignes étaient écrites dans le **corps**
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
# Crée le .conf, les 8 labels, CONTEXTE.md et met à jour cette doc (§2/§7).
# Équivalent web : bouton « + Nouveau projet » à côté du sélecteur de projet
# dans l'interface (mêmes étapes, compte-rendu par étape, sélecteur rafraîchi
# sans redémarrer new_issue.py). Le script CLI reste utilisable en parallèle.
python3 nouveau_projet.py

# Lancer un watcher manuellement
python3 watcher.py --config configs/bridge_agent.conf
python3 watcher.py --config configs/bridge_agent.conf --dry-run

# Voir les watcher en cours
ps aux | grep watcher

# Vérifier les commits locaux non poussés
git log --oneline origin/master..HEAD
```

### Cycle de vie des watchers (démarrage manuel, démarrage auto, extinction auto)

Les watchers ne tournent **pas** en permanence : ils s'allument à la demande et
s'éteignent d'eux-mêmes après une période d'inactivité. Trois mécanismes se
combinent.

**1. Démarrage manuel.** Le bouton « Lancer watcher » de l'onglet « Watchers »
(ou `python3 watcher.py --config configs/<projet>.conf` en terminal, cf. bloc
ci-dessus) démarre le watcher d'un projet. L'interface suit le process via un
fichier PID (`logs/watcher-<nom>.pid`).

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
**20**), il s'arrête proprement (`sys.exit(0)`) et nettoie son fichier PID. Le
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

**Cycle complet.** Watcher éteint pour inactivité → on crée une issue for-linux
→ le watcher est rallumé automatiquement (#202) → il traite la tâche → après
`DELAI_INACTIVITE_MIN` minutes sans nouvelle issue traitable, il se rééteint
(#200). Aucun process ne tourne inutilement, et aucune étape manuelle n'est
requise pour le flux normal.

> **Historique : services systemd (abandonnés).** L'issue #119 avait déployé les
> watchers en services `systemd --user` (`systemd/watcher@.service`,
> `installer_services.sh`) pour un démarrage au boot et un auto-restart
> (`Restart=always`, `RestartSec=10`). **Ce mécanisme n'est plus déployé** :
> aucune unité `watcher@*.service` n'existe dans `~/.config/systemd/user/`
> (`systemctl --user list-unit-files 'watcher@*'` → 0 unité). Le gabarit et le
> script sont conservés dans le dépôt à titre de référence historique
> uniquement.
>
> ⚠️ **Ne pas réactiver `installer_services.sh` sans le retravailler d'abord.**
> `Restart=always` + `RestartSec=10` est **incompatible** avec l'auto-extinction
> après inactivité (#199/#200) : systemd relancerait au bout de 10 s tout
> watcher qui vient de s'éteindre pour inactivité, produisant une boucle sans
> fin (allumage/extinction toutes les ~20 min + 10 s) et annulant tout l'intérêt
> du mécanisme. Une éventuelle réintroduction de systemd devrait retirer
> `Restart=always` (ou passer en `Restart=on-failure` avec un code de sortie
> d'inactivité distinct traité en `SuccessExitStatus`).

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
  l'issue avec `| LABELS | for-windows |` (§3) — pas de chef.
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
  dans l'onglet CCW (§16.2) que la VM `CCW-Build` tourne et que le service
  `CCW-Watcher` est démarré ; sinon l'issue restera ouverte sans aucun
  signal. (Le nom `CCW-Watcher-<Projet>` venait du modèle multi-projets,
  abandonné par #231 — voir §16.)

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

**But :** disposer d'un agent **Claude Code Windows (CCW)** tournant dans une VM
Windows, pour traiter les issues `for-windows` — principalement les builds `.exe`
(PyInstaller) qui exigent un environnement Windows natif.

**Modèle unifié (depuis juillet 2026).** Un seul service NSSM `CCW-Watcher`
surveille les issues `for-windows` du dépôt `AlainDelree/Bridge_Agent`.
`REP_TRAVAIL = \\VBOXSVR\CCW_Share` (chemin UNC du partage VirtualBox, accessible
depuis Linux à `/home/alain/Bridge_Agent_CCW_Share/`). Chaque projet buildé
est cloné dans un sous-dossier dédié : `\\VBOXSVR\CCW_Share\CCW\<projet>\`
(ex. `Z:\CCW\actualise\` depuis la VM). Ce modèle garantit le séquencement
strict des builds par construction (un seul process `watcher.py`, une issue
à la fois) et supprime tout risque de contention CPU/RAM entre deux builds
parallèles.

> **⚠️ Le clone `C:\CCW\Bridge_Agent` n'est JAMAIS mis à jour automatiquement
> (issue #240).** Le `git pull --ff-only` automatique de début de cycle (§1)
> porte sur `REP_TRAVAIL` — ici `\\VBOXSVR\CCW_Share`, qui **n'est même pas un
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

**Modèle précédent abandonné.** Le modèle multi-projets (#170) — un clone
`C:\CCW\<Projet>` + un config `configs\<nom>-ccw.conf` + un service NSSM
`CCW-Watcher-<Projet>` par projet — est abandonné. Les scripts
`ajouter_projet_ccw.ps1` et `finaliser_projet_ccw.ps1` sont conservés dans
le dépôt à titre historique uniquement ; ne pas les utiliser.

**Provisioning** (dossier `provisioning/windows/`) :

| Fichier | Rôle |
|---------|------|
| `creer_vm_ccw.py` | **(phase 1)** Crée la VM VirtualBox `CCW-Build` (VBoxManage : 6 Go RAM, 4 CPU, disque fixe 40 Go, dossier partagé). Flag `--recreate` pour reconstruire à l'expiration de l'éval 90 jours. |
| `autounattend.xml` | **(phase 1)** Réponse d'installation Windows automatisée (OOBE, compte admin **local** `ccw-admin`, activation de PowerShell Remoting pour le pilotage à distance). |
| `provisionner.ps1` | **(phase 2)** Script PowerShell exécuté **dans** la VM : installe Git, GitHub CLI, Python 3, pyinstaller (winget) + Claude Code (installeur natif, sans Node.js), clone le dépôt en lecture seule dans `C:\CCW\Bridge_Agent`, écrit `configs\ccw.conf` (`LABEL=for-windows`, `NOM=ccw`, `REP_TRAVAIL` sur le partage `CCW_Share` via son chemin UNC `\\VBOXSVR\CCW_Share` — accessible depuis LocalSystem, contrairement au lecteur automonté en session, issue #149 — `TOPIC_NTFY` placeholder), et enregistre le service Windows `CCW-Watcher` via NSSM (lance le watcher au démarrage sans session, redémarrage automatique sur échec). |
| `lancer_provisioning.py` | **(phase 2)** Orchestration côté **Linux (CCL)** : pousse et exécute `provisionner.ps1` dans la VM via `VBoxManage guestcontrol` (copyto + run) sous le compte `ccw-admin`. Mot de passe lu via `CCW_ADMIN_PASSWORD` (jamais en clair ni committé). Préféré à WinRM : pas de dépendance réseau/pare-feu, juste les Guest Additions. |
| `demarrer_ccw.sh` | Wrapper de démarrage de la VM `CCW-Build` depuis CCL (issue #166) : `--type headless` par défaut (silencieux si déjà démarrée), `--gui`/`--fenetre` pour une fenêtre (`--type separate`), `--status` pour l'état (`VMState`) sans rien démarrer. |
| `eval-expiration.json` | Métadonnées de l'évaluation 90 jours (issue #167) : `date_installation` (**2026-07-19**), `eval_jours` (90), `date_expiration` (informative, **2026-10-17**). |
| `verifier_expiration_ccw.py` | **(côté Linux)** Lit `eval-expiration.json`, recalcule l'expiration (`date_installation` + `eval_jours`) et le nombre de jours restants. À ≤ 10 j restants (ou déjà expiré) : avertissement + **code de sortie 2** (intégrable à une vérif automatisée) ; sinon confirmation calme + code 0. Sans dépendance externe. |
| `mettre_a_jour_tokens_ccw.ps1` | **(dans la VM)** Renouvellement des tokens d'un service CCW sans manipuler à la main la chaîne PowerShell (issue #168). Demande `GH_TOKEN` puis `CLAUDE_CODE_OAUTH_TOKEN` en `Read-Host -AsSecureString` (jamais affichés en clair), reconstruit `AppEnvironmentExtra` avec le saut de ligne `` `n`` **impératif** entre les deux (un simple espace corrompt silencieusement `GH_TOKEN` → « Bad credentials »), applique via `nssm set … AppEnvironmentExtra`, fait `nssm restart`, attend puis affiche les 10 dernières lignes du log de service et conclut OK / à vérifier (code 2 si `ERROR`). Paramétrable (`-NomService`, `-RepDepot`, et `-NomLog` pour cibler le bon log de service, ex. `ccw-scrabble-service.log`, issue #173) : sert aussi bien à `CCW-Watcher` qu'aux services multi-projets `CCW-Watcher-<NomProjet>` (issue #170). Depuis l'issue #174, accepte aussi `-FichierTokens <chemin>` : les deux valeurs sont alors **lues dans un fichier** « clé=valeur » (au lieu de `Read-Host`), ce qui permet à l'onglet CCW de poser les tokens à distance sans saisie dans la VM et sans jamais les passer en argument de commande. |
| `ajouter_projet_ccw.ps1` | **(obsolète — modèle multi-projets abandonné, conservé à titre historique)** **(dans la VM)** Instancie un projet CCW **supplémentaire** sur le modèle multi-projets (issue #170), sans rien réinstaller. Paramétrable (`-NomProjet`, `-Depot owner/repo`, ou prompt interactif) : clone le dépôt en lecture seule dans `C:\CCW\<NomProjet>`, écrit `configs\<nom>-ccw.conf` (`NOM=<nom>-ccw`, `LABEL=for-windows`, `REP_TRAVAIL`/`PERIMETRE`=`C:\CCW\<NomProjet>`, `TOPIC_NTFY` placeholder), et enregistre un service NSSM dédié `CCW-Watcher-<NomProjet>` (mêmes réglages que `CCW-Watcher` : `SERVICE_AUTO_START`, `AppExit Default Restart`, `AppRestartDelay`, `logs\ccw-<nom>-service.log`). Idempotent (clone mis à jour par pull, service arrêté/supprimé avant recréation). Ne configure **pas** `AppEnvironmentExtra` : chaque projet a son propre token dédié, posé ensuite en **une seule commande** via `finaliser_projet_ccw.ps1` (rappel affiché en fin de script). |
| `lister_projets_ccw.ps1` | **(dans la VM, appelé à distance — issue #174)** Inventaire **JSON** des projets CCW : énumère les services `CCW-Watcher*` (NSSM), et pour chacun émet le nom du service, le projet dérivé, l'état (`running`/`stopped`) et le statut du placeholder `TOPIC_NTFY` (lu dans le config, sans jamais renvoyer la valeur réelle du topic). Sortie encadrée par `<<<CCW_JSON>>>…<<<CCW_END>>>` pour extraction fiable côté Linux. Exécuté par l'onglet CCW de l'interface web. |
| `finaliser_projet_ccw_auto.ps1` | **(dans la VM, appelé à distance — issue #174)** Variante **non interactive** de `finaliser_projet_ccw.ps1` : lit `TOPIC_NTFY` + les deux tokens dans un **fichier « clé=valeur »** poussé par l'appelant (jamais en argument de commande), remplace le placeholder `TOPIC_NTFY` dans le config (édition ciblée) puis **appelle** `mettre_a_jour_tokens_ccw.ps1 -FichierTokens` (aucune duplication de la logique des tokens). Supprime le fichier de valeurs dans un `finally` (nettoyage côté VM). Code de sortie = celui du script de tokens (0/2/1). |
| `finaliser_projet_ccw.ps1` | **(obsolète — modèle multi-projets abandonné, conservé à titre historique)** **(dans la VM)** Finalise en **une seule commande** un projet déjà créé par `ajouter_projet_ccw.ps1` (issue #173, suite #170), regroupant les 3 étapes manuelles auparavant dispersées. À partir du seul `-NomProjet` (argument ou prompt), **dérive** `CCW-Watcher-<NomProjet>`, `C:\CCW\<NomProjet>` et `configs\<nom>-ccw.conf` (même logique qu'`ajouter_projet_ccw.ps1`) et **vérifie** leur existence (sinon renvoie vers `ajouter_projet_ccw.ps1`). Puis : (1) demande `TOPIC_NTFY` (`Read-Host`, pas un secret) et remplace le placeholder `###TOPIC_NTFY_A_DEFINIR###` **dans** le config par édition ciblée (le reste du fichier préservé, UTF-8 sans BOM) ; (2) rappelle les réglages du token dédié à créer (repo unique, permissions, expiration alignée) avec une **pause** ; (3) **appelle** `mettre_a_jour_tokens_ccw.ps1` (pas de duplication) avec les paramètres déduits — dont `-NomLog ccw-<nom>-service.log` — pour la saisie masquée + pose des tokens + redémarrage + vérif des logs ; (4) résumé final selon le code renvoyé. |

La VM cible **Windows 11 IoT Enterprise LTSC 2024** en évaluation 90 jours,
d'où la recréation facile prévue.

**Expiration de l'évaluation (issue #167).** L'évaluation 90 jours de
`CCW-Build` a été installée le **19 juillet 2026** et expire le
**17 octobre 2026**. Après expiration, Windows redémarre automatiquement toutes
les heures, ce qui casse en continu le service `CCW-Watcher` : il faut recréer
la VM **avant** cette date (sans urgence, via `creer_vm_ccw.py --recreate`).
Pour connaître les jours restants à tout moment :

```bash
python3 provisioning/windows/verifier_expiration_ccw.py
```

À ≤ 10 jours de l'expiration, le script alerte et renvoie un code de sortie
non nul (2) ; sinon il confirme calmement les jours restants (code 0). Si la
date d'install réelle diffère, ajuster `date_installation` dans
`provisioning/windows/eval-expiration.json` (les jours restants sont recalculés
à partir de cette date). *Rappel automatique possible mais non activé par
défaut* : une tâche `cron` locale hebdomadaire lançant ce script et notifiant
via `ntfy` (mécanisme `notifier_ntfy` du projet, topic `bridge_agent`) si proche
de l'expiration — à activer par Alain s'il le souhaite (cf. proposition issue #167).

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
échec (`AppExit Default Restart` + `AppRestartDelay 5000`), sous LocalSystem
donc sans stocker les identifiants `ccw-admin`. Cela remplace l'ancienne
tâche planifiée `-AtLogOn`, qui ne redémarrait pas au boot sans session ; la
boucle interne du watcher reste la première ligne de robustesse. Comme le
service tourne sous LocalSystem, `REP_TRAVAIL` pointe vers le **chemin UNC**
`\\VBOXSVR\CCW_Share` (nom du partage VirtualBox défini en phase 1) et non
vers la lettre de lecteur automontée `$LettrePartage` (issue #149) : les
lecteurs réseau montés en session interactive ne sont pas visibles pour
LocalSystem, alors que le chemin UNC l'est. Le paramètre `$LettrePartage`
est conservé pour référence mais ne sert plus à construire `REP_TRAVAIL`.

**Lancer le provisioning (une fois Windows installé et la session ouverte) :**

```bash
# Côté CCL (Linux), VM démarrée avec Guest Additions :
export CCW_ADMIN_PASSWORD='…'                       # jamais committé
python3 provisioning/windows/lancer_provisioning.py --dry-run   # vérif
python3 provisioning/windows/lancer_provisioning.py             # copie + exécute
```

Puis, dans la VM : renseigner `TOPIC_NTFY` dans `configs\ccw.conf` et
authentifier Claude (`ANTHROPIC_API_KEY` en variable d'environnement, ou
`claude auth login` une fois).

**Renouveler les tokens du service (issue #168).** Les tokens `GH_TOKEN` et
`CLAUDE_CODE_OAUTH_TOKEN` du service `CCW-Watcher` sont passés via
`AppEnvironmentExtra` (NSSM). Piège connu : les deux paires doivent être
séparées par un **saut de ligne** `` `n`` et non par un espace — un espace
corrompt silencieusement `GH_TOKEN` (erreur « Bad credentials » à la
prochaine opération `gh`). Pour éviter de reconstruire cette chaîne à la main
à chaque renouvellement (~90 j, cf. issue #167), lancer **dans la VM** :

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
  2026**, aligné sur l'éval Windows, cf. §16.1) — surtout **ne pas laisser
  dériver** vers une autre échéance.

> **Règle d'or :** tout nouveau token CCW réutilise la date d'expiration commune
> (≈ mi-octobre 2026) pour ne garder **qu'une seule fenêtre de maintenance** —
> Windows, le token Bridge_Agent et tous les tokens projets expirent ensemble.
> Au renouvellement, on recale simplement tout le monde sur la nouvelle date
> commune. Ne créer aucun token depuis ce dépôt (action manuelle GitHub) : le
> script se contente de rappeler la marche à suivre.

### 16.1 Maintenance périodique (renouvellement à 90 jours)

> **Procédure unique à suivre le jour de l'échéance.** Cette sous-section est
> un mode d'emploi séquentiel autonome : elle renvoie aux scripts existants
> (détaillés plus haut dans le §16) plutôt que de réexpliquer le provisioning.
> Rien d'autre du §16 n'est nécessaire pour l'exécuter.

**Repères de dates**

| Repère | Valeur | Source |
|--------|--------|--------|
| Date d'installation Windows | **2026-07-19** | `provisioning/windows/eval-expiration.json` (`date_installation`) |
| Expiration éval Windows (90 j) | **2026-10-17** | idem (`date_expiration`, recalculée : install + 90 j) |
| Expiration token GitHub | **≈ 2026-10-17** (aligné volontairement, non stocké) | *pas de métadonnée dédiée — voir note ci-dessous* |

> Le token GitHub fine-grained a été créé avec une durée alignée sur l'éval
> Windows (~90 j) pour n'avoir **qu'une seule fenêtre de maintenance** à
> retenir : Windows et le token expirent ensemble, vers le **17 octobre 2026**.
> Sa date exacte n'est pas conservée dans un fichier du dépôt (elle vit dans
> les réglages GitHub du token) ; se fier à l'alignement et à l'échéance
> Windows comme rappel commun. Si à l'avenir cette date est stockée, l'ajouter
> à `eval-expiration.json` et à ce tableau.

**Étape 0 — Vérifier où on en est (sans rien casser)**

```bash
python3 provisioning/windows/verifier_expiration_ccw.py
```

Affiche les jours restants avant l'expiration Windows. À ≤ 10 jours (ou déjà
expiré) : avertissement + code de sortie 2. Sinon : confirmation calme (code 0).
C'est le déclencheur de toute la procédure ci-dessous. *(Si la date d'install
réelle a changé, ajuster `date_installation` dans `eval-expiration.json` : les
jours restants sont recalculés à partir de cette date.)*

**Étape 1 — Recréer la VM à l'expiration**

À faire **avant** la date d'expiration (sans urgence) : après expiration,
Windows redémarre toutes les heures et casse en continu le service `CCW-Watcher`.

```bash
# 1a. Détruire et recréer la coquille VM (VBoxManage) — n'attache PAS l'ISO :
python3 provisioning/windows/creer_vm_ccw.py --recreate

# 1b. Ré-attacher un ISO Windows 11 IoT Enterprise LTSC 2024 :
#     ⚠️ si l'éval a expiré, RE-TÉLÉCHARGER un ISO frais (une nouvelle éval
#     90 j) — l'ancien ISO redonnerait une install déjà entamée.
VBoxManage storageattach CCW-Build --storagectl SATA \
  --port 1 --device 0 --type dvddrive --medium /chemin/vers/windows.iso
#     (+ placer autounattend.xml à la racine d'une clé/ISO secondaire, cf. §16)

# 1c. Démarrer la VM, laisser l'installation automatisée se dérouler, puis
#     rejouer le provisioning logiciel (phase 2, dans la VM via CCL) :
export CCW_ADMIN_PASSWORD='…'                                   # jamais committé
python3 provisioning/windows/lancer_provisioning.py --dry-run   # vérif
python3 provisioning/windows/lancer_provisioning.py             # copie + exécute
```

Après recréation, mettre à jour `date_installation` (et `date_expiration`)
dans `provisioning/windows/eval-expiration.json` avec la nouvelle date d'install
réelle, pour que l'étape 0 reparte sur la bonne échéance.

**Étape 2 — Renouveler les tokens (GitHub + Claude)**

Régénérer les deux tokens côté fournisseurs :
- **GitHub** : nouveau *fine-grained token* (réglages GitHub), durée ~90 j
  pour rester aligné sur l'éval Windows.
- **Claude** : nouveau `CLAUDE_CODE_OAUTH_TOKEN` via `claude setup-token`.

Puis les injecter dans le service `CCW-Watcher`, **dans la VM**, sans
reconstruire à la main la chaîne `AppEnvironmentExtra` (piège du séparateur —
un espace au lieu du saut de ligne `` `n`` corrompt silencieusement `GH_TOKEN`
→ « Bad credentials ») :

```powershell
# Depuis C:\CCW\Bridge_Agent, console PowerShell admin :
powershell -ExecutionPolicy Bypass -File provisioning\windows\mettre_a_jour_tokens_ccw.ps1
```

Le script demande les deux valeurs masquées (`Read-Host -AsSecureString`),
applique `nssm set … AppEnvironmentExtra` + `nssm restart CCW-Watcher`, puis
affiche les 10 dernières lignes de `logs\ccw-service.log` (OK si aucune ligne
`ERROR`, sinon code de sortie 2).

**Récapitulatif express :** vérifier (`verifier_expiration_ccw.py`) → recréer
la VM (`creer_vm_ccw.py --recreate` + ré-attacher un ISO frais +
`lancer_provisioning.py`) → renouveler les tokens
(`mettre_a_jour_tokens_ccw.ps1`) → mettre à jour `eval-expiration.json`.

### 16.2 Onglet « CCW » de l'interface web (issue #174)

**Rôle.** Piloter CCW (la VM et ses projets) **entièrement depuis Linux**, via
l'onglet **CCW** de `new_issue.py` — même style que les autres onglets. Il
**remplace l'usage manuel de PowerShell dans la VM** pour les opérations
courantes : plus besoin d'ouvrir une console PowerShell dans la fenêtre de la VM
ni de copier-coller hôte↔VM (source d'erreurs récurrentes). Les scripts
PowerShell existants restent l'**implémentation sous-jacente** : l'onglet les
pousse et les exécute à distance via `VBoxManage guestcontrol` (pattern
`copyto` + `run` de `lancer_provisioning.py`). Côté serveur, toute la logique
vit dans `app/ccw.py` (routes `/ccw/*`).

**Ce que fait l'onglet :**

1. **VM CCW-Build** — affiche son état (`running`/`poweroff`/`saved`, même
   `VMState` que `demarrer_ccw.sh`) et, si arrêtée, un bouton **Démarrer
   (headless)** (qui appelle `demarrer_ccw.sh`).
2. **Projets CCW existants** — liste les services `CCW-Watcher*` de la VM
   (via `lister_projets_ccw.ps1`, exécuté à distance) : nom du projet, service,
   état (`running`/`stopped`) et indicateur si `TOPIC_NTFY` est encore un
   placeholder. **Rafraîchi à la demande** (pas de polling : chaque appel
   déclenche un `guestcontrol`).
3. **Ajouter un projet** — champs *nom* + *dépôt owner/repo*, bouton **Créer**
   qui exécute `ajouter_projet_ccw.ps1` à distance (clone + config + service) et
   affiche sa sortie.
4. **Finaliser un projet** — champs *projet* (ou sélection dans la liste du
   point 2), `TOPIC_NTFY`, `GH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`. Bouton
   **Finaliser** qui écrit le topic **et** pose les deux tokens en enchaînant,
   puis redémarre le service et affiche les dernières lignes de log
   (via `finaliser_projet_ccw_auto.ps1`).

**Sécurité des tokens (impératif).** Les tokens ne transitent **jamais** en
argument de ligne de commande vers `guestcontrol` (invisibles dans les
process/event logs Windows) et ne sont **jamais journalisés** côté Linux. Ils
sont écrits dans un **fichier temporaire local à permissions `0600`**, poussé
dans la VM via `copyto`, lu côté VM par PowerShell (`-FichierTokens`), puis
supprimé des **deux côtés** dans un `finally` (Python côté hôte, PowerShell côté
VM) — exactement le pattern du mot de passe `ccw-admin`.

**Mot de passe `ccw-admin` (côté serveur).** Jamais demandé à chaque action ni
codé en dur. `app/ccw.py` le lit, à l'action, par ordre de priorité :

1. variable d'environnement **`CCW_ADMIN_PASSWORD`** (cohérent avec
   `lancer_provisioning.py`) — l'exporter avant de lancer `new_issue.py` ;
2. sinon fichier local **`configs/ccw_admin.secret`** (gitignoré, comme les
   `configs/*.conf`), dont la première ligne est le mot de passe.

Absent des deux → l'onglet affiche un message clair, aucune erreur Flask brute.
Toute erreur `guestcontrol` (VM éteinte, timeout, script distant en échec)
remonte de la même façon un message lisible dans l'interface.

### 16.3 Procédure — builder un projet Windows

**Envoyer un build :** créer une issue `for-windows` dans `bridge_agent` via
`new_issue.py` (champ `| LABELS | for-windows |`). Pas de pattern chef/ouvrier
nécessaire — l'issue est directe.

**Template d'issue build (à adapter par projet) :**

Étape 0 — Ajouter l'exception `safe.directory` (nécessaire sur chemin UNC,
une seule fois par sous-dossier) :

```bash
git config --global --add safe.directory '%(prefix)///VBoxSvr/CCW_Share/CCW/<projet>'
```

Étape 1 — Si `Z:\CCW\<projet>\` n'existe pas ou n'est pas un dépôt git :
cloner `https://github.com/AlainDelree/<Projet>.git` dans `Z:\CCW\<projet>\`.
Sinon : `git pull --ff-only`.

Étape 2 — `pip install -r requirements.txt` depuis `Z:\CCW\<projet>\`.

Étape 3 — Build PyInstaller depuis `Z:\CCW\<projet>\` :

```bash
python -m PyInstaller --noconfirm --onedir --noconsole --name <Projet> <entrypoint>.py
```

Étape 4 — Confirmer la présence de `Z:\CCW\<projet>\dist\<Projet>\<Projet>.exe`
et l'absence d'erreur PyInstaller. Ne pas committer ni pousser.

**Récupération des artefacts :** manuelle, depuis Linux via
`/home/alain/Bridge_Agent_CCW_Share/CCW/<projet>/dist/<Projet>/`.

**Dépôts sources :** publics sur GitHub — aucun token Contents requis.
Le token `CCW-Watcher` (Issues read/write sur Bridge_Agent) suffit.

**Note safe.directory :** git refuse de travailler sur un chemin UNC dont
le propriétaire diffère de l'utilisateur courant. L'exception est à ajouter
en étape 0 de chaque première issue sur un nouveau sous-dossier. Les issues
suivantes la trouvent déjà en place.

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
- **Poller `app/notifications_poller.py`** : thread démon lancé par
  `new_issue.py` (à côté du heartbeat). Toutes les `BRIDGE_NOTIF_INTERVALLE`
  secondes (défaut **20 s**), pour **chaque projet actif** (tous, `for-linux` ET
  `for-windows` confondus, via `lister_projets()`), il interroge GitHub pour deux
  transitions **terminales** :
  - **succès** : issue **fermée** portant le label `done` (`closedAt` récent) ;
  - **échec définitif** : label `needs-human` posé, issue restée **ouverte**
    (`updatedAt` récent).
- **Script bip partagé `scripts/bip.py`** : le bip vivait dans `~/NicLink/bip.py`
  (dépôt AlChess) alors que c'est de l'infrastructure commune à tous les projets.
  Il a été déplacé/recréé dans `scripts/bip.py` ; le **défaut** de `SCRIPT_BIP`
  pointe désormais vers lui, et les `configs/*.conf` qui référençaient l'ancien
  chemin ont été mis à jour.

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
| `BRIDGE_NOTIF_ESPACEMENT` | `2` | Délai (secondes) entre le traitement de deux projets (issue #190) : étale les appels gh du poller au lieu d'une rafale groupée qui rendait le bouton Rafraîchir lent et faisait « sursauter » les badges. `0` = rafale immédiate (ancien comportement). |

---

## 18. Pièces jointes image dans les issues (issue #191)

L'onglet **« Nouvelle issue »** permet de **joindre une image (PNG/JPEG)** — par
exemple une maquette d'interface souhaitée — pour qu'elle soit **automatiquement
intégrée au corps** de l'issue créée, sans le détour manuel (glisser-déposer dans
un commentaire GitHub web, récupérer l'URL, la coller).

### 18.1 Pourquoi committer l'image plutôt que l'attacher

L'API GitHub **ne permet pas** d'uploader une pièce jointe arbitraire sur une
issue de façon simple/stable via un token : le glisser-déposer du web repose sur
un mécanisme interne non documenté pour un usage scripté. La solution fiable et
bien supportée retenue ici :

1. **Committer** l'image dans un dossier dédié du dépôt du projet cible :
   **`issue-attachments/`** (à la racine du `REP_TRAVAIL` du projet) ;
2. **Pousser** ce commit sur `origin` ;
3. **Référencer** l'image dans le corps Markdown de l'issue via une URL
   **`raw.githubusercontent.com/<owner>/<repo>/<branche>/issue-attachments/<fichier>`**
   — ce format s'affiche correctement dans les issues GitHub une fois postées.

La **branche** est déduite **dynamiquement** (`git rev-parse --abbrev-ref HEAD`),
jamais supposée `master`/`main` : l'URL pointe toujours vers la bonne branche.
Le nom de fichier est **horodaté** (`AAAAMMJJ-HHMMSS-<nom_original>.png`) pour
éviter toute collision.

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

### 18.3 Fonctionnement concret

- **Frontend** (`templates/index.html`, onglet Nouvelle issue) : champ
  `<input type="file" accept="image/png,image/jpeg">` + bouton **« Joindre une
  image »** à côté du corps. À la réussite, la ligne Markdown
  `![<nom_fichier>](<url>)` est insérée **automatiquement** dans le champ Corps
  (à la position du curseur), sans copier-coller manuel.
- **Backend** : route **`POST /joindre-image`** (`app/issues.py`,
  `joindre_image()`). Reçoit le fichier + le nom du projet sélectionné, **valide**
  le type (PNG/JPEG, contrôle du Content-Type **et** des magic bytes) et la
  **taille** (**≤ 5 Mo**), sauvegarde dans `issue-attachments/`, fait
  `git add` + `git commit` (« Pièce jointe issue : <fichier> ») + **`git push`**,
  puis retourne l'URL `raw.githubusercontent.com`.

### 18.4 Gestion d'erreurs

- **Push échoué** (réseau, conflit, pas de remote, droits manquants) → message
  clair et **aucune URL insérée** (elle serait cassée tant que le commit n'est
  pas sur `origin`). Le commit **reste en local** : Alain peut le pousser plus
  tard manuellement.
- **Projet dont le `REP_TRAVAIL` n'est pas un dépôt git** (ou introuvable) →
  message clair (commit/push impossibles), plutôt qu'un échec silencieux.
- **Type non supporté / fichier trop lourd / fichier vide / contenu non conforme
  à une image** → refus explicite, rien n'est écrit ni committé.

> **Note** : `issue-attachments/` n'est **pas** dans `.gitignore` — c'est
> voulu, puisque les images doivent être suivies et poussées pour que les URL
> `raw` fonctionnent.

---

## 19. Calibration automatique du TIMEOUT (issues #220, #221, #222, #223)

### 19.1 Objectif et principe général

Le champ `TIMEOUT` de l'en-tête d'une issue (§6) est aujourd'hui choisi « à
vue de nez » par Claude Chat (souvent le défaut du formulaire, 300s, ou
600s pour une tâche qui semble plus lourde). Ce système calcule, à partir de
l'**historique réel** des durées de traitement, une valeur suggérée —
`TIMEOUT_suggéré` — par combinaison (projet, `TYPE`, mode), pour aider
Claude Chat à mieux calibrer ce champ au fil du temps.

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
  **`projet|TYPE|mode`** : EWMA `duree_typique` et `variabilite` (à
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

- **`tag_reseau` n'est peuplé nulle part actuellement** :
  `_detecter_tag_reseau` retourne toujours `None` (aucun champ d'en-tête
  bridge dédié n'existe aujourd'hui pour signaler qu'une issue s'est
  déroulée dans des conditions réseau particulières). Conséquence : `F_reseau`
  et `F_local` restent tous deux à leur valeur neutre (`F` planché à 1.0,
  jamais mis à jour) tant qu'un futur champ d'en-tête dédié n'est pas créé et
  que `_detecter_tag_reseau` n'est pas branché dessus.
- **Incohérence inerte sur échec définitif** : `lire_timeout_suggere()`
  retombe toujours sur `F_local` par défaut, sans lire le tag réel de
  l'issue en échec — contrairement au cas succès (`maj_calibration_timeout`),
  qui choisit `F_reseau`/`F_local` selon `_detecter_tag_reseau(body)`. Sans
  effet tant que `tag_reseau` n'est jamais peuplé (point précédent), mais à
  corriger le jour où il le sera (lire le tag de l'issue en échec plutôt que
  de supposer `F_local`).
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

---

*Dernière mise à jour : 26 juillet 2026 — Aligne le texte historique du §14 sur l'amendement #244 (issue #245). Contexte : le paragraphe « ⚠️ Contrainte d'exécution synchrone (rappel) », hérité de #208 et volontairement laissé intact par #244 comme référence documentaire, interdisait encore catégoriquement « un mécanisme d'attente différée, de tâche en arrière-plan ou de "je répondrai plus tard" » — formulation contredite par le texte en vigueur de `consignes/globales.md` depuis #244 (l'arrière-plan encadré, avec interrogation de la sortie en boucle DANS la même exécution, y est permis ; seul conclure son tour de parole avant la fin réelle et vérifiée de l'opération reste proscrit). Un Claude Chat consultant le §14 en premier — cas fréquent, section de référence sur la délégation — pouvait lire l'interdiction absolue sans descendre jusqu'à l'encart d'injection qui la nuançait déjà, et reconduire dans une issue de build une consigne que le système n'applique plus. **§14** : le paragraphe est reformulé pour dire une seule chose, alignée sur `globales.md` — proscrit : conclure son tour de parole avant la fin réelle et vérifiée de l'opération ; permis : l'arrière-plan encadré (interrogation de la sortie en boucle DANS la même exécution) ; restent interdits sans changement : « monitor », notification, rappel programmé, formulations « je répondrai plus tard ». Reste du paragraphe conservé tel quel (aucune reprise possible après réponse, boucle `sleep` + `gh issue view` pour l'attente d'un ouvrier) ; l'encart d'injection qui suit (issues #209/#243) n'a pas été touché, sa nuance restant exacte. Recherche `arrière-plan`/`monitor`/`attente différée` sur tout le fichier : une autre occurrence trouvée hors §14 et hors pied de page — **§12.1** (ligne « Globale » du tableau des trois couches : « contrainte d'exécution synchrone et bloquante, sans attente différée, universelle depuis #243 ») — laissée telle quelle, ce résumé reste exact (l'interdit qu'elle nomme est bien l'attente différée pour conclure, pas l'arrière-plan comme technique) ; le pied de page (historique de #244 et antérieurs) laissé tel quel par consigne explicite. Aucune section renumérotée, aucun fichier `.py` ni `consignes/*.md` modifié. Précédemment — Amende la contrainte d'exécution universelle de #243 pour lever une contradiction qu'elle introduisait avec le plafond de timeout de l'outil Bash (issue #244). Contexte : le texte issu de #243 interdisait catégoriquement l'arrière-plan (« Ne lance jamais une commande en arrière-plan ») et proposait comme repli de relancer avec un timeout explicite plus long — or l'outil Bash a un timeout MAXIMUM par appel (de l'ordre de dix minutes) qu'aucun paramètre ne permet de dépasser ; si un build excède ce plafond (hypothèse plausible pour #241/#242, probablement à l'origine du basculement en arrière-plan qui avait motivé #243), l'agent se retrouvait pris entre deux interdits — attendre en un seul appel ou lancer en arrière-plan — et improviserait. Second défaut, dans la même phrase : le repli « boucle sur sa sortie DANS cette même exécution » SUPPOSE une exécution en arrière-plan (on lance, puis on interroge la sortie en boucle) ; la consigne décrivait donc le bon comportement tout en interdisant le mécanisme qui le rend possible. Le fautif n'est pas l'arrière-plan en soi, c'est de conclure son tour de parole sans avoir attendu la fin réelle de l'opération. **`consignes/globales.md`** : la fin du bullet « Contrainte d'exécution » (à partir de « Si une opération dépasse le timeout d'un appel d'outil… ») est réécrite — ce qui est interdit, c'est de CONCLURE le tour de parole avant que l'opération soit terminée et son résultat vérifié, pas l'arrière-plan comme technique ; en cas de dépassement du timeout d'un appel d'outil, deux voies restent permises : relancer avec un timeout explicite plus long tant que le plafond de l'outil le permet, OU lancer en arrière-plan À CONDITION IMPÉRATIVE d'interroger sa sortie en boucle DANS cette même exécution jusqu'à complétion réelle ; restent interdits sans changement le « monitor », la notification, le rappel programmé et toute formulation « je répondrai/j'attends… » en guise de conclusion ; rappel inchangé qu'aucune reprise n'existe (le watcher ferme l'issue dès la réponse postée). **`consignes/type_chef.md`** vérifié : sa formulation (« aucune attente différée, aucun monitor ») reste cohérente avec le nouveau texte — non touché. **§12.1** (ligne « Globale ») et **§14** (encart d'injection automatique) vérifiés : leurs résumés restent exacts sans qu'il soit besoin d'y ajouter la précision arrière-plan/plafond — non touchés. Aucune section renumérotée, aucun fichier `.py` modifié. Précédemment — Généralise l'interdiction d'attente différée à toute issue et distingue opération longue légitime du blocage sans progrès (issue #243). Contexte : les issues #241/#242 (builds Scrabble, CCW) se sont fermées `done` avec un rapport annonçant attendre une notification de fin de build ou un rappel programmé, alors que le build avait réellement abouti (`Scrabble.exe` et `Scrabble-Setup.exe` présents, datés du jour) — pas un échec de build, un rapport ne reflétant pas la réalité, produit par un agent sorti avant la fin. Deux consignes en cause, inversées par rapport à ce qu'exige une tâche longue : `consignes/globales.md` (injecté dans TOUTE issue) demandait d'abandonner toute commande « boucle/tarde anormalement (> 30s sans progrès net) » — écrit pour #214 (commande refusée par le système de permissions, bouclage réel), mais assez général pour couvrir aujourd'hui un build PyInstaller + Inno Setup (plusieurs minutes, peu de sortie visible), appliqué à la lettre ; l'interdiction qui aurait dû s'appliquer (ne jamais recourir à une attente différée, un « monitor », etc.) vivait dans `consignes/type_chef.md`, injecté SEULEMENT pour le TYPE `chef` — une issue de build n'en est pas une. Le mode de défaillance n'ayant rien de spécifique au rôle de chef (il guette toute tâche dont une étape dépasse le timeout d'un appel d'outil), la contrainte est rendue universelle. **`consignes/globales.md`** : le rappel issu de #214 est reformulé pour distinguer une commande refusée par les permissions ou bloquée SANS AUCUN PROGRÈS (→ abandon immédiat, comportement inchangé) d'une opération longue mais qui PROGRESSE normalement (build, compilation, installation de dépendances, suite de tests, clonage volumineux — → ce n'est PAS une anomalie, il faut attendre sa fin) ; le seuil de 30s ne s'applique plus qu'à l'absence de progrès, plus à la durée en soi. Nouveau rappel généralisé depuis `type_chef.md` : accomplir la tâche en une seule exécution synchrone et bloquante, jamais de commande en arrière-plan / « monitor » / notification / rappel programmé / « je répondrai quand… », relancer avec un timeout explicite plus long ou boucler DANS la même exécution en cas de dépassement du timeout d'un appel d'outil, jamais conclure sur une attente — rappel qu'aucune reprise n'existe, le watcher fermant l'issue dès la réponse postée. **`consignes/type_chef.md`** : allégé pour éviter la redondance — ne garde que la spécificité chef (boucler `sleep` + `gh issue view` en attendant la fermeture des issues ouvrières, puis synthèse finale), la contrainte générale étant désormais dans `globales.md`. **TYPE `build`** : vérification de `watcher.deduire_type_issue`/`TYPES_ISSUE` — `build` n'est PAS une valeur reconnue (`TYPES_ISSUE` = chef/ouvrier/spec_vue/spec_metier/spec_persistance/normal, et `_classer_valeur_type` n'a aucune branche pour « build » : même un en-tête explicite `| TYPE | build |` retomberait sur `normal`) ; `consignes/type_build.md` n'a donc PAS été créé — le mécanisme ne s'y prête pas sans modifier `watcher.py` (hors périmètre de cette issue), et de toute façon le vrai correctif (la contrainte universelle dans `globales.md`) couvre déjà le cas des builds sans dépendre d'un TYPE dédié. **§12.1** : la parenthèse résumant les rappels globaux (ligne « Globale ») mise à jour pour refléter la distinction blocage/progrès et la contrainte d'exécution synchrone désormais universelle. **§14** : le bloc « Contrainte d'exécution impérative » renommé « rappel » et son encart d'injection automatique mis à jour pour pointer vers `globales.md` (universel depuis #243) plutôt que `type_chef.md`, qui n'ajoute plus que la spécificité chef. **§1** : rattrapage d'une omission de #240 — la réécriture du paragraphe sur le pull automatique avait fait disparaître la parenthèse sur les projets à **périmètre dynamique** (dépôt-cible défini par issue, dépôts d'audit non rafraîchis par le pull automatique, distincts du clone de travail du watcher) ; réintroduite, adaptée au nouveau texte. Aucune section renumérotée. Précédemment — Correctif documentaire §1/§14/§16 et rattrapage de trois issues committées sans mise à jour du DOC (issue #240). Incident du 26/07 : le clone `C:\CCW\Bridge_Agent` de la VM (celui d'où s'exécute réellement `watcher.py`) avait **80 commits de retard** sur `origin/master`, sans aucun signal — le service tournait avec du code antérieur à l'issue #195, cause probable de l'incident #236 (issue fermée `done` sans commentaire de résultat). **§1** réécrit : le `git pull --ff-only` automatique de début de cycle porte bien sur `REP_TRAVAIL` avec la même logique CCL/CCW, mais ne met à jour le CODE du watcher que lorsque `REP_TRAVAIL` coïncide avec le clone du dépôt Bridge_Agent — vrai côté CCL, **faux** côté CCW en modèle unifié (#231), où `REP_TRAVAIL = \\VBOXSVR\CCW_Share` n'est même pas un dépôt git et où le clone contenant `watcher.py` (`C:\CCW\Bridge_Agent`) vit ailleurs, mis à jour par personne. L'ancienne affirmation « comportement identique CCL et CCW » est supprimée car trompeuse sur ce point précis. **§16** gagne un bloc d'avertissement opérationnel : ce clone n'est **jamais** mis à jour automatiquement ; procédure obligatoire après tout push touchant `watcher.py` — `git pull --ff-only` dans `C:\CCW\Bridge_Agent` **puis redémarrage du service** `CCW-Watcher` (`nssm restart`, un pull seul ne suffit pas : un process Python déjà démarré garde en mémoire le code chargé à son lancement) — avec la commande de contrôle rapide `git status -sb` (ne doit jamais afficher `behind`), et le cas réel des 80 commits de retard comme justification. **§14** corrigé : dans le bloc « Quand NE PAS passer par un chef » (#225), la référence au service `CCW-Watcher-<Projet>` — nom venant du modèle multi-projets abandonné par #231 — est remplacée par `CCW-Watcher`. Rattrapage de trois issues committées sans entrée de pied de page : **#237** — `commenter_issue`/`editer_dernier_commentaire` passent par `--body-file` (fichier temporaire UTF-8) au lieu de `--body`, supprimant la limite argv Windows de 32767 caractères ; `commenter_resultat_avec_retry` vérifie désormais la publication par relecture de l'issue (un exit code 0 de `gh` ne suffit plus, la présence effective du commentaire est exigée) ; nouveau marqueur `MARQUEUR_RESULTAT` (`<!-- bridge:resultat -->`) en tête du commentaire de résultat, utilisé aussi par `resultat_deja_poste` à la place de l'ancienne sous-chaîne `"## Résultat"` qui matchait à tort `"## Résultat attendu"` ; test `tests/test_verification_commentaire_237.py` ; deux effets de bord assumés — deux appels `gh` par tentative, et possibilité d'un commentaire en double si la publication réussit mais que la relecture échoue transitoirement (perte silencieuse échangée contre doublon visible). **#238** — `fermer_issue` inspecte désormais les codes de retour de `close` et `add-label`, retourne un booléen, et journalise explicitement les états incohérents (fermée sans label / label sans fermeture) sans compensation automatique. **#239** — libellé d'agent de l'ACK déduit automatiquement de `platform.system()` (« agent Linux » / « agent Windows »), avec champ optionnel `LIBELLE_AGENT` pour forcer un libellé explicite si la détection automatique ne convient pas ; le §16 avait déjà été modifié par cette issue mais aucune entrée de pied de page n'avait été ajoutée — rattrapée ici. Aucune section renumérotée. Précédemment — §3 « Créer une issue » : ajout d'une **exception `PROJET`** pour les issues `for-windows` (issue #233, suite #231). Rapport remonté par le Claude du projet `actualise` : lors de la génération d'une issue de build Windows, le champ `PROJET` avait été renseigné avec `actualise` au lieu de `bridge_agent`, en appliquant par erreur la règle générale du §3 (« nom exact du projet cible »). Or le §16.3 (modèle CCW unifié, #231) applique correctement `PROJET=bridge_agent` dans son template — c'est la config du watcher CCW unique qui compte, pas le projet réellement construit — mais le §3, consulté en premier par Claude Chat, ne mentionnait pas cette exception. Ajout d'un second bloc d'avertissement juste après celui existant (« Claude Chat doit toujours inclure `| PROJET | <nom> |` ») précisant que pour les issues `for-windows`, `PROJET` reste toujours `bridge_agent`, le nom du projet cible s'exprimant en texte dans le corps (chemins, `git clone`/`git pull`), avec renvoi au template du §16.3. Aucune section renumérotée. Précédemment — §16 « Agent Windows CCW » : documentation du **modèle CCW unifié** (issue #231), qui remplace le modèle multi-projets (#170, un service NSSM par projet). Un seul service NSSM `CCW-Watcher` surveille désormais les issues `for-windows` de `AlainDelree/Bridge_Agent`, `REP_TRAVAIL = \\VBOXSVR\CCW_Share` (accessible depuis Linux à `/home/alain/Bridge_Agent_CCW_Share/`), chaque projet buildé étant cloné dans un sous-dossier dédié `\\VBOXSVR\CCW_Share\CCW\<projet>\` — séquencement strict des builds par construction (un seul process `watcher.py`), zéro contention CPU/RAM entre builds parallèles. Validé en production avec le build PyInstaller d'`actualise`. Introduction du §16 réécrite (titre « (en préparation) » retiré, devenu opérationnel) ; nouvelle sous-section **§16.3 « Procédure — builder un projet Windows »** détaillant le template d'issue en 4 étapes (exception `git config --global --add safe.directory` sur le chemin UNC — obligatoire une seule fois par sous-dossier —, clone ou `git pull --ff-only`, `pip install -r requirements.txt`, build `python -m PyInstaller --noconfirm --onedir --noconsole`), la récupération manuelle des artefacts côté Linux et le rappel qu'aucun token GitHub Contents n'est requis (dépôts publics, seul le token Issues du service `CCW-Watcher` sert). Les scripts `ajouter_projet_ccw.ps1` et `finaliser_projet_ccw.ps1` (tableau de provisioning) marqués **« obsolète — modèle multi-projets abandonné, conservé à titre historique »** — ne plus les utiliser, mais conservés dans le dépôt sans suppression. Reste du §16 (§16.1 maintenance 90 jours, §16.2 onglet CCW, description historique du modèle multi-projets #170) laissé inchangé, hors du périmètre de cette issue. Précédemment — §14 « Délégation Chef → Ouvrier » : ajout d'un bloc **« Quand NE PAS passer par un chef »** (issue #225), inséré juste après le paragraphe « Principe » et avant « Ce n'est pas déclenché automatiquement… ». Contexte : sur le projet `actualise`, une tâche entièrement Windows avait donné lieu à une issue chef CCL dont le seul travail était de créer immédiatement un ouvrier CCW et d'attendre sa fermeture — sans étape réelle côté Linux, correct mais coûteux (deux issues, deux invocations `claude`, TIMEOUT long, attente synchrone bloquante payée pour rien). Le nouveau bloc pose le **critère de décision** : le chef se justifie quand la tâche comporte du travail réel côté Linux (avant et/ou après) dans la même unité de travail ; si la TOTALITÉ de la tâche s'exécute sous Windows, créer directement l'issue avec `| LABELS | for-windows |` (§3) plutôt qu'un chef. **Contre-exemple explicite** : un chef qui se contente de créer un ouvrier puis d'attendre sa fermeture, sans orchestration réelle, est du surcoût pur. Rappel que l'**exemple validé** plus bas dans la section (dictionnaire déposé côté Linux puis rebuild côté Windows) reste un cas où le chef EST justifié — la nouvelle règle ne le contredit pas. **⚠️ Contrepartie opérationnelle** ajoutée dans le même bloc : le rallumage automatique du watcher à la création d'une issue (§13, mécanisme 2) ne vaut QUE pour les issues `for-linux` — une issue `for-windows` directe ne démarre rien, donc vérifier dans l'onglet CCW (§16.2) que la VM `CCW-Build` tourne et que le service `CCW-Watcher-<Projet>` est démarré avant d'en envoyer une, sinon elle reste ouverte sans aucun signal. En miroir, **§3** (paragraphe décrivant le champ `LABELS`, juste après la phrase sur le cas d'usage `| LABELS | for-windows |`) gagne une phrase de renvoi croisé vers ce bloc du §14. Aucune section renumérotée ; reste du §14 (contrainte d'exécution impérative, format des titres, timeout du chef, exemple validé) et reste du §3 inchangés. Précédemment — Nouvelle section **§19 « Calibration automatique du TIMEOUT »** (issue #224), documentant de bout en bout le système mis en place par les issues #220 (extension d'`historique_durees.json`), #221 (mécanique EWMA `etat_timeout.json`/`etat_ambiance.json`), #222 (exposition du `TIMEOUT_suggéré` dans le commentaire de clôture GitHub) et #223 (exclusion des `expiree=true` du badge d'estimation de l'interface). Jusqu'ici ce système n'était documenté nulle part dans `BRIDGE_AGENT_DOC.md` — seul `CONTEXTE.md` en gardait une trace partielle, ajoutée par #221 et jamais mise à jour depuis, de toute façon plafonnée par sa limite de taille pour l'injection prompt (§12.1). La nouvelle section couvre, à partir d'une lecture du code réel de `watcher.py`/`app/issues.py` (pas une paraphrase des rapports d'issue) : l'objectif et le principe d'inspiration (RTO TCP, Jacobson/Karels), la formule complète et chacun de ses termes, les deux fichiers d'état (`logs/etat_timeout.json`, `logs/etat_ambiance.json` — partagés entre watchers, verrouillés, écriture atomique), le tableau des constantes actuelles en soulignant explicitement qu'elles sont des valeurs de DÉPART non backtestées, le canal d'exposition (bloc `⏱️/📊` dans le commentaire de clôture, sans aucune application automatique — le TIMEOUT réellement utilisé reste celui de l'en-tête, `extraire_timeout`), et une liste explicite des limitations connues (`tag_reseau` jamais peuplé donc `F_reseau`/`F_local` neutres, incohérence inerte de `lire_timeout_suggere` sur échec définitif, démarrage à froid trompeusement optimiste, aucun backtest des constantes, distinction avec le badge `estimer_duree` de #223). Aucune autre section renumérotée ni modifiée. Précédemment — Correctif horloge d'auto-extinction (issue #217) : le watcher pouvait s'éteindre **immédiatement après un traitement réel** lorsque celui-ci s'étirait au-delà du délai d'inactivité (`DELAI_INACTIVITE_MIN`, défaut 20 min). Cause : `derniere_activite` (horloge monotone d'inactivité, #200) n'était réarmée qu'**en tête de cycle**, juste après `lister_issues()` et **avant** de lancer `traiter_issue()` — donc jamais pendant le traitement (potentiellement long : plusieurs timeouts de 300 s + retries en cascade). Si le traitement d'une seule issue dépassait le délai (cas réel `watcher-scrabble.log` du 24/07/2026 : #237/#238 traités sans interruption de 08:59 à 09:22, puis extinction à 09:23:08 — 14 s après le succès de #238), l'horloge restait figée à l'instant du **début** du cycle ; le test d'extinction du cycle suivant se déclenchait alors sur une horloge périmée, ne reflétant pas le travail réellement effectué. **Correctif** (`watcher.py`, boucle principale) : réarmement de `derniere_activite` **aussi APRÈS** la boucle de traitement, dès qu'au moins une issue traitable a été traitée ce cycle (option a du diagnostic — réarmer sur le travail réel, préférée à l'option b « revérifier `lister_issues()` avant `sys.exit` » car elle satisfait plus directement l'objectif « ne jamais éteindre si du travail vient d'avoir lieu », sans appel réseau supplémentaire ni cas où une issue devenue fermée entre-temps laisserait l'extinction filer). Le flag `travail_a_faire` (calculé une fois) conditionne les deux réarmements ; l'extinction reste possible quand plus rien n'est traitable. **Test de non-régression** : `tests/test_auto_extinction_217.py` pilote le vrai `watcher.main()` avec horloge mockée (`time.monotonic`/`time.sleep` patchés) sur 3 scénarios — (1) traitement long ~23 min + issue restante → **pas** d'extinction prématurée (échoue sur le code d'avant #217, passe sur le code corrigé), (2) inactivité réelle → extinction bien déclenchée, (3) issue non-traitable (`done`) → n'empêche pas l'extinction. §13 (mécanisme 3 « Extinction automatique ») mis à jour pour décrire le double réarmement avant/après. Précédemment — Nouveau rappel global « abandon immédiat au refus de permission » (issue #214) : ajout, à la fin de `consignes/globales.md`, d'un rappel systématique — si une commande/un outil est **refusé par le système de permissions** (session non-interactive, aucune approbation possible) ou **boucle/tarde anormalement** (> 30s sans progrès net), CCL doit **abandonner immédiatement** l'approche et le signaler dans son rapport plutôt que de retenter, en basculant si possible sur un repli plus simple (lecture directe, `grep`, analyse manuelle) et sans jamais insister sur une commande déjà refusée. Motivation : comparaison des issues Scrabble #235 (timeout à 300s, bouclage sur une commande refusée) et #238 (succès) — la seule différence significative était la présence, dans #238, d'une consigne explicite d'abandon-au-lieu-de-retenter ; en session non-interactive, un refus de permission Claude Code est systématique et définitif (aucun utilisateur pour approuver), donc retenter est vain. Consigne volontairement **générale** (pas spécifique à Scrabble ni à JS/eslint) car le problème touche toute commande nécessitant une approbation (installation de paquet, exécution d'un binaire, etc.), quel que soit le projet ou le langage. §12.1 : la parenthèse résumant les rappels globaux dans le tableau des trois couches est complétée (ajout d'« abandon immédiat au refus de permission / boucle anormale ») ; la liste complète des rappels n'étant pas reproduite ailleurs dans la doc, aucune autre duplication à mettre à jour. Précédemment — Déplacement de l'injection des consignes trois couches dans `watcher.py` — couverture universelle (issue #211). Les consignes (globales/type/projet, #209) ne sont plus écrites dans le **corps** de l'issue par `app/issues.py` (chemin qui ne couvrait QUE les issues créées via le formulaire web), mais injectées dans le **prompt donné à CCL au moment du traitement** par `watcher.py` (`lancer_claude` → nouvelles `_consignes_injectees`/`_lire_consigne`, reprises de `app/issues.py`), exactement sur le modèle de `CONTEXTE.md`/`FICHIER_CONTEXTE`. Le point de passage devient **unique** : peu importe le chemin de création — formulaire web, `gh issue create` d'un chef (§14), création manuelle GitHub (§3) — `watcher.py` déduit le TYPE (`deduire_type_issue` sur le titre/corps réels) et le projet (`CFG.nom`), puis ajoute le bloc **après** le bloc `CONTEXTE` et **avant** la clause de périmètre / le garde-fou (regroupement des « règles » en fin de prompt, zone la mieux suivie). Cas particulièrement corrigé : les issues **ouvrières créées par un chef** (chemin 2, vraies tâches `mode_write`) recevaient auparavant zéro consigne — c'est justement là que les rappels de sécurité comptent le plus. `app/issues.py::construire_body` revient à un corps **en-tête + corps rédigé** seulement (suppression de `_consignes_injectees`/`_lire_consigne`/`DOSSIER_CONSIGNES` et de l'import `logging` devenu inutile) — source unique de vérité désormais côté watcher, plus de double injection. Garde-fous inchangés (#209) : `globales.md` absent → `log.warning` sans bloquer le traitement ; `type_*`/`projet_*` absents → silencieux. Conséquence assumée (comme pour `CONTEXTE.md`) : les consignes ne sont plus visibles dans le corps d'une issue sur GitHub. **§12.1 réécrite** (modèle prompt + couverture universelle des 3 chemins + emplacement dans le prompt) et **§10** mis à jour (`consignes/` = injecté dans le prompt CCL, plus « en tête de chaque issue »). Testé de bout en bout par une issue `TYPE=chef` `mode_write` créée **directement en CLI** (`gh issue create`, hors formulaire) : le prompt CCL assemblé par le watcher contient bien les consignes globales + `type_chef.md`. Précédemment — Architecture à trois couches d'injection de consignes (issue #209) : nouveau dossier `consignes/` à la racine, injecté **dans le corps de chaque issue** par `app/issues.py` (`construire_body` → `_consignes_injectees`), entre le tableau d'en-tête et le corps rédigé par Claude Chat. Trois couches, de la plus générale à la plus spécifique : **globales** (`consignes/globales.md`, **NON-optionnel** — rappels de sécurité transversaux : ne jamais pousser, backup avant modif, respect du périmètre — injecté dans TOUTE issue), **type** (`consignes/type_<type>.md`, **facultatif** — ex. `type_chef.md` reprenant la contrainte d'exécution synchrone du #208, injecté selon le TYPE déduit par `watcher.deduire_type_issue`), **projet** (`consignes/projet_<projet>.md`, **facultatif** — aucun créé par défaut). Ordre final : en-tête → globales → type (si présent) → projet (si présent) → corps. Vaut en **mono-issue comme en mode lot** (chaque bloc `#Titre:` passe par `construire_body` avec son propre TYPE). **Choix délibéré anti-piège de maintenance** : contrairement à `CONTEXTE.md`, les couches type/projet sont sans obligation de présence (un projet sans `projet_<nom>.md` fonctionne normalement, rien à créer/maintenir) et créées uniquement à la demande. Garde-fous : fichier `type_*`/`projet_*` absent → aucune injection **sans** log (normal, pas une anomalie) ; `globales.md` introuvable → `logging.warning` clair **sans jamais faire échouer** la création d'issue. Nouvelle sous-section **§12.1** décrivant l'architecture, mise à jour du **§10** (dossier `consignes/`) et du **§14** (la contrainte d'exécution synchrone du chef n'est plus à recopier manuellement — elle est injectée automatiquement via `consignes/type_chef.md`). Testé de bout en bout (issue `TYPE=chef` réelle : corps GitHub contenant, dans l'ordre, globales puis chef puis corps original). Précédemment — Finalisation du nettoyage doc MVC (issue #208, suite #207) : le §14 « Délégation Chef → Ouvrier » gagne un bloc **« ⚠️ Contrainte d'exécution impérative »** rappelant que le chef doit accomplir la TOTALITÉ de sa tâche (attente de fermeture des ouvriers + synthèse finale comprises) en **une seule exécution synchrone et bloquante** — aucune reprise n'étant possible après qu'une issue a été répondue/fermée, ne jamais recourir à une attente différée, une tâche en arrière-plan ou un « je répondrai plus tard » ; si une attente est nécessaire, boucler (`sleep` + `gh issue view`) DANS la même exécution. Cette finalisation confirme aussi l'absence des fichiers `CONTEXTE_VUE.md`/`CONTEXTE_METIER.md`/`CONTEXTE_PERSISTANCE.md` à la racine de bridge_agent (jamais créés ici ; seul `CONTEXTE.md` existe et est conservé). Précédemment — Nettoyage doc MVC (issue #207) : **suppression de l'ancien §15 « Pattern Chef + Specs MVC (évolution future) »**, purement prospectif et jamais implémenté (le watcher ne lit pas le champ `SPECS`, aucun routage par couche Vue/Métier/Persistance n'existe) ; les sections suivantes **ne sont pas renumérotées** (16, 17, 18 restent 16, 17, 18) pour préserver les références croisées existantes. Le **§14 est entièrement réécrit** et recadré « Délégation Chef → Ouvrier (changement d'environnement) » : on ne garde que l'usage réel validé — un CCL « chef » crée lui-même une issue « ouvrier » ciblant un autre environnement (typiquement CCL Linux → CCW Windows) via `gh issue create` et surveille sa fermeture avant de livrer, sur instruction explicite (pas de détection auto du rôle chef, pas de décomposition automatique générique) — avec conseil de `TIMEOUT` généreux côté chef et l'exemple validé du build Scrabble/ouvrier CCW. En complément, l'issue chef #207 délègue à 6 issues « ouvrier » (une par projet actif hors bridge_agent et ff_galerie) la suppression des fichiers `CONTEXTE_VUE.md`/`CONTEXTE_METIER.md`/`CONTEXTE_PERSISTANCE.md` — vestiges du §15 abandonné — `CONTEXTE.md` (mécanisme standard hors MVC) étant conservé partout. Précédemment — §18 (nouveau) « Pièces jointes image dans les issues » (issue #191) : l'onglet « Nouvelle issue » accepte désormais un **upload optionnel PNG/JPEG** (champ fichier + bouton « Joindre une image » à côté du corps). Nouvelle route **`POST /joindre-image`** (`app/issues.py`, `joindre_image()`) : valide le type (Content-Type **et** magic bytes) et la taille (**≤ 5 Mo**), sauvegarde dans **`issue-attachments/`** (racine du `REP_TRAVAIL`) sous un nom **horodaté** anti-collision (`AAAAMMJJ-HHMMSS-<nom>.ext`), puis `git add` + `commit` + **`git push origin HEAD:<branche>`** (branche déduite **dynamiquement**, jamais supposée master/main), et retourne l'URL **`raw.githubusercontent.com/<owner>/<repo>/<branche>/issue-attachments/<fichier>`** — format qui s'affiche correctement dans les issues GitHub. Le frontend (`static/js/app.js`, `joindreImage()`/`insererDansCorps()`) insère alors **automatiquement** `![<nom>](<url>)` dans le corps à la position du curseur. **Exception `push` assumée et documentée (§18.2)** : ce commit+push est déclenché par **ALAIN** via l'outil (son action manuelle), **pas par CCL/le watcher** — la règle « CCL ne pousse jamais » n'est donc pas violée (elle vise les modifications de code de l'agent, pas une image qu'Alain publie lui-même). Gestion d'erreurs (§18.4) : **push échoué → aucune URL insérée** (commit conservé en local, poussable plus tard), **projet sans dépôt git → message clair**, type/taille/contenu invalides refusés proprement. `issue-attachments/` volontairement **hors `.gitignore`** (les images doivent être suivies/poussées). Testé de bout en bout (dépôt jetable + remote bare : succès + URL correcte, et chemins d'échec type/taille/magic/push). Précédemment — §17 (nouveau) « Notifications centralisées — détection serveur des transitions » (issue #187) : `new_issue.py`, qui tourne en permanence sur le ThinkPad, détecte désormais LUI-MÊME par polling `gh` les transitions d'issues (fermeture `done` = succès ; label `needs-human` = échec définitif) de **tous** les projets (for-linux ET for-windows), et déclenche bip/`notify-send`/`ntfy` **localement**, y compris pour les issues traitées par la VM **CCW** — **sans aucun appel réseau initié par la VM** (la VM n'écrit que sur GitHub). Nouveau module partagé `notifications.py` (racine) factorisant `bip`/`notifier_bureau`/`notifier_ntfy`/`notifier`, importé par `watcher.py` (enveloppes minces déléguant, sites d'appel inchangés) ET par le nouveau poller `app/notifications_poller.py` (thread démon lancé par `new_issue.py`). Script bip **déplacé/recréé** de `~/NicLink/bip.py` vers `scripts/bip.py` (infrastructure partagée) ; défaut `SCRIPT_BIP` et `configs/*.conf` mis à jour. Anti-doublon (point 4) : réglage `NOTIFIER_LOCAL` (`.conf`, défaut `true`) coupant la notif du watcher + portée `BRIDGE_NOTIF_SCOPE` (env, défaut `for-windows`) du poller. **Défaut livré sans régression ni doublon** (CCL notifie via son watcher, CCW via le poller — variante propre de l'option b) ; **option (a) « centralisation complète » recommandée mais laissée au choix d'Alain** car elle fait de `new_issue.py` une dépendance dure de toute notification (or il n'a pas encore de service systemd) — implémentée et à un réglage près (`BRIDGE_NOTIF_SCOPE=all` + `NOTIFIER_LOCAL=false` partout). **Action requise côté VM CCW** : poser `NOTIFIER_LOCAL=false` dans `configs\*-ccw.conf` pour éviter un double `ntfy`. Bonus (point 5) : le poller lit les labels COURANTS à la fermeture, donc `notif_pc`/`notif_gsm` ajouté EN COURS de traitement est bien pris en compte. Filtre de récence (`BRIDGE_NOTIF_RECENCE_MIN`, défaut 30 min) + amorçage silencieux au 1er cycle évitent le spam de vieilles issues au démarrage ; état en mémoire process. Précédemment — §1 « Vue d'ensemble » : documentation du **`git pull --ff-only` automatique en début de cycle** de `watcher.py` (issue #186, suite du #185 qui l'a implémenté). Le watcher rafraîchit son clone (`REP_TRAVAIL`) au début de chaque cycle de polling, juste avant `lister_issues()` : fast-forward transparent en cas de succès ; en cas de commits locaux non poussés (divergence) le `--ff-only` échoue proprement sans RIEN écraser et le watcher poursuit sur le code local — donc aucun risque à oublier un `git push`. Comportement **identique CCL (Linux) et CCW (Windows)** puisque `watcher.py` est le script unique partagé ; les projets à périmètre dynamique (dépôt-cible par issue) ne sont pas concernés. Un `git pull`/relance manuel reste possible pour une mise à jour immédiate (confort, plus une nécessité). Aucune instruction obsolète de « git pull manuel obligatoire » à corriger dans le §16 (aucune ne subsistait). Précédemment — §16 « Agent Windows CCW » : **onglet « CCW » dans l'interface web** (issue #174, sous-section §16.2) — pilotage complet de la VM et des projets CCW depuis Linux, sans PowerShell manuel dans la VM. Backend `app/ccw.py` (routes `/ccw/*`) exécutant les scripts existants à distance via `VBoxManage guestcontrol` : état/démarrage de la VM (`demarrer_ccw.sh`), liste des projets (nouveau `lister_projets_ccw.ps1`, sortie JSON encadrée), ajout (`ajouter_projet_ccw.ps1`) et finalisation non interactive (nouveau `finaliser_projet_ccw_auto.ps1` + `mettre_a_jour_tokens_ccw.ps1` doté d'un mode `-FichierTokens`). Sécurité : tokens jamais passés en argument ni journalisés (fichier temporaire `0600` poussé puis supprimé des deux côtés dans un `finally`) ; mot de passe `ccw-admin` lu depuis `CCW_ADMIN_PASSWORD` ou `configs/ccw_admin.secret` (gitignoré). Nouvel onglet + panneau dans `templates/index.html`, fonctions `ccw*` dans `static/js/app.js`, classe `.message.avertissement` dans `style.css`. Précédemment — §16 « Agent Windows CCW » : **finalisation d'un projet CCW en une seule commande** (issue #173, suite #170) — ajout de `provisioning/windows/finaliser_projet_ccw.ps1` qui, à partir du seul `-NomProjet`, dérive le service/dossier/config (même logique qu'`ajouter_projet_ccw.ps1`), vérifie leur existence, demande `TOPIC_NTFY` et l'écrit directement dans le config (remplacement ciblé du placeholder `###TOPIC_NTFY_A_DEFINIR###`, reste du fichier préservé en UTF-8 sans BOM), rappelle avec une pause la marche à suivre pour créer le token GitHub dédié, puis **appelle** `mettre_a_jour_tokens_ccw.ps1` (pas de duplication) pour la saisie masquée + pose des tokens + redémarrage + vérif des logs, et conclut par un résumé ; `mettre_a_jour_tokens_ccw.ps1` gagne un paramètre `-NomLog` pour vérifier le bon log de service (`ccw-<nom>-service.log`) ; les rappels d'`ajouter_projet_ccw.ps1` (en-tête + fin de script) et le §16 pointent désormais vers cette commande unique au lieu des 3 étapes dispersées. Non exécuté contre une VM réelle (test manuel par Alain). Précédemment — §11 « Conventions de code » : **règle BOM UTF-8 obligatoire pour tout script `.ps1`** (issue #172) — ajout du BOM (`EF BB BF`) manquant sur `ajouter_projet_ccw.ps1` (#170) et `mettre_a_jour_tokens_ccw.ps1` (#168), qui plantaient sinon sous Windows PowerShell 5.1 avec des `UnexpectedToken` en cascade sur les accents (même signature que #151) ; règle généralisée en §11 + rappel en tête du §16 pour prévenir la récidive (`provisionner.ps1` déjà OK depuis #151). Précédemment — §16 « Agent Windows CCW » : **généralisation multi-projets de CCW** (issue #170) — ajout de `provisioning/windows/ajouter_projet_ccw.ps1` (un clone + un config `configs\<nom>-ccw.conf` + un service NSSM `CCW-Watcher-<NomProjet>` dédiés par projet, sur le modèle des watchers CCL ; paramétrable `-NomProjet`/`-Depot`, idempotent, `watcher.py` inchangé) ; documentation du modèle « un service par projet » et de la **règle d'expiration alignée** des tokens (un token fine-grained dédié par dépôt, mais tous à la même échéance ≈ 17 octobre 2026) ; commande exacte d'instanciation de Scrabble et marche à suivre pour créer son token dédié (Repository access → Scrabble uniquement, Issues read/write + Metadata read-only). Précédemment — §16 « Agent Windows CCW » : ajout de la sous-section **§16.1 Maintenance périodique (renouvellement à 90 jours)** (issue #169) — runbook séquentiel consolidé pour la fenêtre de maintenance d'octobre 2026 : tableau de repères de dates (install **2026-07-19**, expiration Windows **2026-10-17**, token GitHub aligné ~90 j mais non stocké), puis procédure en 3 étapes renvoyant aux scripts existants — vérifier (`verifier_expiration_ccw.py`), recréer la VM (`creer_vm_ccw.py --recreate` + ré-attacher un ISO frais + `lancer_provisioning.py`), renouveler les tokens (`mettre_a_jour_tokens_ccw.ps1`) — sans dupliquer le détail technique déjà présent dans le §16. Précédemment — §16 « Agent Windows CCW » : ajout du script `provisioning/windows/mettre_a_jour_tokens_ccw.ps1` (issue #168) — renouvellement des tokens `GH_TOKEN`/`CLAUDE_CODE_OAUTH_TOKEN` du service `CCW-Watcher` sans reconstruire à la main la chaîne `AppEnvironmentExtra` : saisie masquée (`Read-Host -AsSecureString`), séparateur `` `n`` impératif entre les deux paires (un espace corrompt `GH_TOKEN` → « Bad credentials »), `nssm set`/`nssm restart`, puis affichage automatique des 10 dernières lignes de `logs\ccw-service.log` pour confirmer l'absence d'erreur d'auth. Précédemment — §16 « Agent Windows CCW » : alerte d'expiration de l'éval 90 jours (issue #167) — ajout de `provisioning/windows/eval-expiration.json` (date d'installation **2026-07-19**, expiration **2026-10-17**) et du script `provisioning/windows/verifier_expiration_ccw.py` (côté Linux : calcule les jours restants, alerte + code de sortie 2 à ≤ 10 j, sinon confirmation calme ; `python3 provisioning/windows/verifier_expiration_ccw.py`) ; rappel `cron` + `ntfy` hebdomadaire proposé mais laissé à l'activation d'Alain. Précédemment — §16 « Agent Windows CCW » : ajout du script `provisioning/windows/demarrer_ccw.sh` (issue #166), wrapper de démarrage de la VM `CCW-Build` depuis CCL (headless par défaut, `--gui`/`--fenetre` pour une fenêtre, `--status` pour l'état sans rien démarrer). Précédemment — §3 « Créer une issue » : ajout d'une note sur la **convention de présentation côté Claude Chat** pour l'envoi en lot (issue #153) — quand Claude Chat prépare plusieurs issues, il les présente toutes à la suite dans un seul bloc de code (pas un bloc par issue) pour un copier-coller en un clic. Précédemment — §16 « Agent Windows CCW » : `REP_TRAVAIL` généré par `provisionner.ps1` pointe désormais vers le **chemin UNC** `\\VBOXSVR\CCW_Share` (et non la lettre automontée `$LettrePartage`), seul accessible au service `CCW-Watcher` tournant sous LocalSystem (issue #149, suite #148) ; `$LettrePartage` conservé pour référence mais plus utilisé pour construire `REP_TRAVAIL`. Précédemment — le watcher CCW tourne comme **vrai service Windows** enregistré via NSSM (issue #148, suite #147) — `provisionner.ps1` installe `NSSM.NSSM` (winget) et enregistre le service `CCW-Watcher` (`SERVICE_AUTO_START` + `AppExit Default Restart` + `AppRestartDelay 5000`, stdout/stderr → `logs\ccw-service.log`, idempotent via `nssm stop`/`remove`), en remplacement de l'ancienne tâche planifiée `-AtLogOn` qui ne redémarrait pas au boot sans session ; équivalent direct des services systemd du §13. Précédemment — provisioning **phase 2** (issue #147, suite #146) — ajout de `provisioning/windows/provisionner.ps1` (installe l'outillage dans la VM via winget + Claude Code natif, clone le dépôt, écrit `ccw.conf`, enregistre la tâche planifiée `CCW-Watcher`) et `lancer_provisioning.py` (pousse/exécute ce script depuis CCL via `VBoxManage guestcontrol`) ; `watcher.py` inchangé (portable, `LABEL` paramétrable) ; limite Task Scheduler vs `Restart=always` documentée. Précédemment — ajout du §16 et du label `for-windows` (issue #146) : provisioning phase 1 de la VM Windows CCW (`provisioning/windows/creer_vm_ccw.py` + `autounattend.xml`) destinée aux builds .exe délégués par CCL. Précédemment — Bridge_Agent v1, 4 projets actifs. §3 « Créer une issue » : ajout de l'**envoi en lot** (issue #135) — coller plusieurs blocs `#Titre:` à la suite dans le même corps déclenche le mode lot (bouton « Envoyer le lot (N issues) »), chaque bloc étant envoyé en séquence comme une issue indépendante (avec ses `PROJET`/`TIMEOUT`/`MODELE` optionnels), sans validation intermédiaire, suivi d'un résumé listant le résultat de chacune. Ajout du projet `ecole` (AlainDelree/Ecole, ~/Ecole) aux tableaux §2 et §7 (issue #101). Section 15 « Chef + Specs MVC » : champ `SPECS` (pluriel, minuscules, combinable en une ligne) — correction du champ `SPEC` introduit par erreur (issue #97, suite #96).*
