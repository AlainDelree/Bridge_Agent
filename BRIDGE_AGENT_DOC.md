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
> - **Côté CCW en modèle unifié** (#231) : `REP_TRAVAIL = C:\CCW_Share`
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
| `rummikub` | AlainDelree/Rummikub | ~/Rummikub | (conf local) |

Chaque projet a son propre watcher (`watcher.py --config configs/<nom>.conf`)
et son propre journal de log (`logs/watcher-<nom>.log`).

---

## 3. Créer une issue — la méthode normale

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

**Champs d'en-tête optionnels reconnus (`PROJET`, `TIMEOUT`, `MODELE`, `MODE`,
`LABELS`) :**

`| MODE | … |` (issue #326) est détecté par `new_issue.py`
(`detecterModeDansCorps`) exactement comme `TIMEOUT`/`PROJET`/`MODELE` :
la valeur reconnue pré-sélectionne le radio Mode du formulaire, puis la
ligne est retirée du corps collé (le tableau d'en-tête final est reconstruit
depuis le formulaire, pas depuis ce que Claude Chat a tapé). Seules deux
valeurs sont fonctionnelles à ce jour : `| MODE | lecture |` et
`| MODE | écriture |` (voir §5 pour le détail des modes). La reconnaissance
est **tolérante** — insensible à la casse et aux accents, plusieurs libellés
acceptés par valeur (ex. « écriture »/« ecriture »/« write » ;
« lecture »/« lecture seule »/« read ») — et le **défaut est LECTURE** si le
champ `MODE` est absent du corps ou si sa valeur n'est reconnue par aucun
synonyme : une issue doit toujours déclarer explicitement l'écriture pour
l'obtenir, jamais par omission.

Au même titre que `PROJET`/`TIMEOUT`/`MODELE`, `new_issue.py` reconnaît aussi
un champ `| LABELS | … |` dans l'en-tête du corps collé. Sa valeur est une liste de
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
repli (le champ `LABELS`, lui, est propre à chaque bloc : sans fallback). Le
`MODE` (lecture/écriture) et les notifications sont communs à tout le lot :
contrairement au mono-issue (ci-dessus), où `MODE` est auto-détecté par bloc
depuis l'en-tête, en mode lot un éventuel `| MODE | … |` dans un bloc est
ignoré — seul le radio du formulaire, choisi une fois pour tout le lot,
décide. Les issues partent **en séquence** (une à la fois, jamais en parallèle),
**sans validation intermédiaire** (aucune modale « issues en attente » ni
d'incohérence projet) : un bloc dont le `PROJET` diffère du projet sélectionné
part quand même sur *son* `PROJET` et c'est simplement signalé ; un bloc en
échec n'interrompt pas le lot. À la fin, un **résumé** liste, pour chaque bloc,
le titre + le lien de l'issue créée ou le message d'erreur, puis le corps est
vidé. Un seul bloc `#Titre:` conserve le comportement mono-issue habituel
(bouton « Envoyer sur <projet> », détection automatique du titre).

**Convention de présentation côté Claude Chat (issue #153, étendue par
#443) :** quand Claude Chat prépare plusieurs issues à la fois pour ce mode
lot, il les présente toutes à la suite dans **un seul bloc de code** (pas un
bloc séparé par issue), afin qu'Alain puisse copier l'ensemble en un clic et
le coller directement dans le champ Corps. Cette règle vaut **aussi pour une
issue unique** (mode mono-issue) : le corps est lui aussi enveloppé dans un
bloc de code, afin qu'Alain puisse utiliser le bouton copier du bloc plutôt
qu'une sélection manuelle.

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
| `mode_scratch` | **ARME la lecture active** — écriture confinée à un dossier scratch, jamais dans le projet (voir §5) |
| `needs-human` | Posé automatiquement après 3 échecs — stoppe le retraitement |
| `done` | Posé automatiquement au succès |
| `notif_pc` | Ajoute une notification bureau (notify-send) |
| `notif_gsm` | Ajoute une notification push (ntfy) |
| `notif_tous` | notify-send + ntfy |

> Sans label `notif_pc` / `notif_gsm` / `notif_tous`, aucune notification
> sonore ou push n'est déclenchée. Le bip est strictement opt-in.

---

## 5. Modes lecture seule / lecture active / écriture

Le watcher pilote un MODE à trois valeurs (issue #327 — remplace un ancien
booléen qui ne pouvait distinguer que deux états), déduit des labels de
l'issue par ordre de priorité : `mode_write` (écriture) > `mode_scratch`
(lecture active) > aucun des deux (lecture seule, défaut).

**Lecture seule (défaut)** — CCL peut lire, analyser, grep, rapporter.
Ne peut PAS écrire de fichier ni exécuter de commande modifiant le système.
Idéal pour : diagnostics, audits, lectures de fichiers, comptages.

**Lecture active (`mode_scratch`, issue #327)** — CCL peut écrire, mais
**UNIQUEMENT** dans un dossier scratch dédié, jamais dans le projet. Utile
aux outils d'analyse qui exigent un vrai fichier de config sur disque (ex.
eslint flat config ≥ 9, autres linters) — impossible à satisfaire en lecture
seule. Le livrable attendu reste un **rapport** de lecture, comme en lecture
seule : la lecture active n'autorise pas de modifier le projet, seulement
d'y faire tourner des outils qui ont besoin d'écrire un fichier temporaire.
- Chemin scratch : `/tmp/bridge_scratch_<projet>/` (`<projet>` = `NOM` du
  `.conf`), créé par le watcher juste avant le lancement de CCL, supprimé
  juste après (succès, échec ou timeout confondus) — rien n'y survit d'une
  tâche à l'autre.
- Défense en profondeur à deux niveaux (même schéma que le garde-fou
  `configs/*.conf`, §11/#318) :
  - **Niveau 1 (prompt)** : un bloc de garde-fou dédié indique explicitement
    à CCL le chemin scratch exact et lui interdit toute écriture ailleurs
    (notamment le répertoire de travail du projet), tout `git commit`/`git
    push`, et toute commande destructrice.
  - **Niveau 2 (détection technique a posteriori)** : le watcher prend une
    empreinte de l'état git du répertoire de travail juste avant le
    lancement de CCL, et la compare juste après. Toute écriture détectée
    dans le projet (malgré la consigne de niveau 1) est **restaurée**
    automatiquement et l'issue est marquée en échec (`needs-human`) — le
    prompt seul ne suffit pas à garantir le confinement, cf. non-déterminisme
    du modèle (issues #290/#291).
- Comme la lecture seule, aucun backup du projet n'est nécessaire (le projet
  n'est jamais modifié par construction) ; `--dangerously-skip-permissions`
  est ajouté (nécessaire pour écrire dans le scratch), d'où l'importance du
  niveau 2 puisque ce flag désarme aussi les protections de Claude Code.

**Mode écriture (`mode_write`)** — CCL peut modifier des fichiers, exécuter
des commandes, faire des commits git.
Garde-fous automatiques :
- Backup pinné **avant** toute modification (via `CMD_BACKUP` du `.conf`)
- **JAMAIS `git push`** — Alain pousse lui-même après vérification
- Aucune commande destructrice sans demande explicite
- Périmètre strict : CCL ne travaille que dans le dossier configuré

> `configs/*.conf` reste interdit à l'écriture **quel que soit le mode**
> (lecture active comme écriture) — garde-fou technique #318, voir §11.

---

## 6. Champs spéciaux dans le corps de l'issue

Le watcher lit ces champs dans le tableau markdown de l'en-tête :

| Champ | Valeur | Effet |
|-------|--------|-------|
| `MODE` | `lecture` ou `écriture` | Auto-détecté par `new_issue.py` (§3, issue #326) pour pré-sélectionner le radio Mode du formulaire ; c'est ce radio, pas la valeur du champ, qui arme (ou non) le label `mode_write` posé sur l'issue — donc le mode écriture de CCL. Défaut lecture si absent/non reconnu. Voir §5 pour le comportement de chaque mode. |
| `PRIORITE` | `haute` ou `critique` | Retry infini (au lieu de 3 max) |
| `TIMEOUT` | ex. `600s` | Surcharge le timeout par défaut (300s) |
| `MODELE` | ex. `claude-opus-4-5` | Force un modèle CCL spécifique pour cette issue |
| `PROJET` | ex. `bridge_agent` | Détection d'incohérence dans `new_issue.py` (issue #44). Inséré automatiquement par l'interface. Claude Chat doit l'inclure dans toutes les issues qu'il génère. |
| `TYPE` | `chef` ou `ouvrier` | Identifie le rôle de l'issue dans le pattern multi-agent. `chef` = orchestre les ouvriers. `ouvrier` = sous-tâche créée par le chef, masquée par défaut dans l'onglet Résultats. Absent = issue normale. |
| `FICHIER_CONTEXTE` | ex. chemin relatif | Fichier additionnel fourni en contexte à CCL pour cette issue (modifiable via l'onglet Configuration, voir §12) |
| `SUITE_DE` | ex. `#5` | Indique que cette issue fait suite à l'issue #N (discussion ou tâche complémentaire). Absent = issue inédite. |
| `COMPLEXITE` | `rapide` / `court` / `normal` / `lourd` | 4e dimension de la clé EWMA de calibration TIMEOUT (issue #434, voir §19), estimée par Claude Chat au moment de rédiger l'issue. Absent ou valeur non reconnue = `normal` (défaut, ~300s). CCL/CCW doit l'inclure dans les issues chef/ouvrier qu'il crée (voir `consignes/globales.md`) ; pour les issues de Claude Chat, c'est géré côté doc/prompt. |
| `RESEAU` | `oui` ou `non` | Tag réseau pour la calibration TIMEOUT (issue #220/#435, voir §19) : `oui` = issue impliquant de lourdes opérations réseau (téléchargements, builds avec fetch, etc.), `non` = issue purement locale. Lu par `_detecter_tag_reseau(body)`. Absent ou valeur non reconnue = `None` (F ignoré, facteur d'ambiance neutre). Optionnel (voir `consignes/globales.md`). |

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
| `rummikub` | /home/alain/Rummikub |

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

**Accès réseau local — mode `--lan` (issue #461).** Mode intermédiaire entre
local et externe : `python3 new_issue.py --lan` fait écouter Flask sur
`0.0.0.0:5100` (toutes les interfaces réseau) sans démarrer le tunnel
Cloudflare et sans exiger de mot de passe (`MODE_EXTERNE` reste `False`,
donc `@login_requis` ne s'active pas — cf. `app/auth.py`). Destiné à un
accès depuis un autre poste du réseau local de confiance (ex. le PC fixe
Windows sur le même réseau), sans aucune exposition vers l'extérieur.
`lancer_new_issue.sh --lan` fait de même avec journalisation.

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
    issues_inbox.py   — état de l'onglet « Résultats inbox » (§20, issue #483)
  templates/          — gabarits HTML (Jinja2)
  static/             — CSS, JS, assets statiques
  issues_inbox/       — gitignoré : dépôt de fichiers .txt d'issues à créer (§20)
    rejected/         — issues malformées, à corriger manuellement (§20)
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
  Alain colle le tout dans le champ Corps de new_issue.py — un seul copier-coller.
  Le corps est toujours présenté dans **un seul bloc de code**, qu'il s'agisse
  d'une issue unique ou d'un lot de plusieurs issues (issue #153, étendue par
  #443), afin qu'Alain puisse utiliser le bouton copier du bloc.
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
   <owner>/<Nom> --public` (sauf décoché côté web). S'il existe déjà →
   installation dessus, rien recréé.
2. **`configs/<nom>.conf`** généré depuis le gabarit interne (dépôt, répertoire
   de travail, périmètre, topic ntfy, couleur d'accent §121, etc.).
3. **Labels GitHub** requis (§4) créés sur le dépôt cible, idempotent (les
   présents sont laissés intacts).
4. **Fichier(s) de contexte** : `CONTEXTE.md` (+ les 3 fichiers Specs MVC §15 si
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

### Interrompre une issue bloquée (issue #323, suite #320)

**Symptôme visé.** Une issue en cours de traitement reste bloquée — CCL
plante, boucle, ou dépasse largement le TIMEOUT attendu sans jamais poser
`done` ni `needs-human` — et Alain veut la sortir du circuit sans attendre
indéfiniment ni sacrifier les autres issues en file pour le même watcher
(elles restent ouvertes sur GitHub, simplement en attente tant que le
watcher n'est pas relancé manuellement).

**Ce que fait le bouton.** Sur toute issue ouverte ni `done` ni
`needs-human`, le détail de l'issue affiche un bouton ⛔ « Interrompre cette
issue » (contrairement à « Interrompre et fermer », #144, qui ferme
l'issue, celui-ci ne fait que la sortir du circuit). Il appelle `POST
/interrompre` (`app/interruption.py::route_interrompre`), qui pose
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
#202) : relance manuelle requise (bouton « Lancer watcher » de l'onglet
Watchers côté CCL, onglet CCW côté CCW-Watcher).

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

### Parallélisation mode_write via git worktrees (issue #337)

Par défaut, plusieurs issues `mode_write` peuvent désormais tourner **en
parallèle**, chacune dans son propre `git worktree` (répertoire frère isolé,
sur sa propre branche) — au lieu du traitement strictement séquentiel
historique (un seul `mode_write` à la fois, dans `REP_TRAVAIL`). Les issues
`mode_lecture`/`mode_scratch` restent, elles, toujours traitées
séquentiellement dans `REP_TRAVAIL` (hors périmètre de cette issue).

- **`MAX_WRITE_PARALLELE`** (`.conf`, entier, défaut **2**) — nombre maximum
  de tâches `mode_write` concurrentes. `1` = comportement séquentiel
  historique intégral (aucun thread, aucun worktree créé, `traiter_issue`
  reste synchrone). `0` = désactivé, identique à `1`.
- **Décision de parallélisation** (`traiter_issue`, point d'entrée public
  appelé pour chaque issue) : la **première** issue `mode_write` détectée
  sans autre tâche `mode_write` déjà en cours est dispatchée dans un thread
  Python ciblant `REP_TRAVAIL` directement — **sans worktree** — nécessaire
  pour que la boucle principale (mono-thread) reste libre de détecter une
  éventuelle deuxième issue `mode_write` pendant que la première tourne
  encore ; sans cela, un `traiter_issue` bloquant sur la première tâche
  empêcherait à jamais d'en atteindre une seconde. Les issues `mode_write`
  **suivantes**, détectées pendant qu'au moins un thread est déjà actif et
  sous `MAX_WRITE_PARALLELE`, obtiennent chacune un worktree dédié.
- **Worktree** : chemin `<REP_TRAVAIL>/../<NOM_PROJET>-issue<N>` (répertoire
  frère de `REP_TRAVAIL`), branche `worktree-issue-<N>`, créés par
  `git -C <REP_TRAVAIL> worktree add <chemin> -b worktree-issue-<N>`. Si le
  chemin ou la branche existe déjà, ou si `git worktree add` échoue pour
  toute autre raison, repli propre sur le traitement séquentiel classique
  (l'issue attend qu'un slot se libère au prochain cycle) — jamais
  d'exception propagée.
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
  pendant qu'un worktree y tourne encore (premier slot) reste bloquée par
  le même verrou qu'avant, reprise au cycle suivant.
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
  dans l'onglet CCW (§16.2) que le PC fixe est joignable et que le service
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

**But :** disposer d'un agent **Claude Code Windows (CCW)** tournant sur un
**PC fixe physique dédié**, pour traiter les issues `for-windows` —
principalement les builds `.exe` (PyInstaller) qui exigent un environnement
Windows natif.

**Réinstallation du PC fixe :** procédure complète (Windows →
`configurer_ssh_ccw.ps1` → `provisionner.ps1` → tokens → vérification) dans
`provisioning/windows/REINSTALLATION_CCW.md` (issue #451).

> **⚠️ Changement de plateforme (depuis août 2026, issue #446).** CCW ne
> tourne plus dans une VM VirtualBox mais **sur un PC fixe physique**
> (Pentium G2020). De nombreux paragraphes ci-dessous décrivent encore
> l'ancienne architecture VM (VirtualBox, `VBoxManage`, chemin UNC, éval 90
> jours) : ils sont conservés à titre **historique** et signalés comme tels
> au fil du texte, mais ne décrivent plus le fonctionnement réel. Les deux
> paramètres qui changent partout dans ce §16 : `REP_TRAVAIL = C:\CCW_Share`
> (chemin **local**, plus de partage VirtualBox) et le service NSSM
> `CCW-Watcher` tourne sous le compte **`AlainW`** (utilisateur non-admin) et
> non plus sous `LocalSystem`.

**Modèle actuel (PC physique).** Un seul service NSSM `CCW-Watcher`
surveille les issues `for-windows` du dépôt `AlainDelree/Bridge_Agent`.
`REP_TRAVAIL = C:\CCW_Share` — répertoire de travail **local** sur le PC
physique, partagé entre CCL (qui y accède via le réseau local) et CCW (qui
y accède en chemin local direct). Chaque projet buildé est cloné dans un
sous-dossier dédié : `C:\CCW_Share\CCW\<projet>\`. Ce modèle garantit le
séquencement strict des builds par construction (un seul process
`watcher.py`, une issue à la fois) et supprime tout risque de contention
CPU/RAM entre deux builds parallèles.

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

**Modèle précédent abandonné.** Le modèle multi-projets (#170) — un clone
`C:\CCW\<Projet>` + un config `configs\<nom>-ccw.conf` + un service NSSM
`CCW-Watcher-<Projet>` par projet — est abandonné. Les scripts
`ajouter_projet_ccw.ps1` et `finaliser_projet_ccw.ps1` sont conservés dans
le dépôt à titre historique uniquement ; ne pas les utiliser.

**Provisioning** (dossier `provisioning/windows/`) :

| Fichier | Rôle |
|---------|------|
| `creer_vm_ccw.py` | **(obsolète — gérait la création de la VM VirtualBox, conservé à titre historique)** **(ex-phase 1)** Créait la VM VirtualBox `CCW-Build` (VBoxManage : 6 Go RAM, 4 CPU, disque fixe 40 Go, dossier partagé). Flag `--recreate` pour reconstruire à l'expiration de l'éval 90 jours. Sans objet depuis le passage à un PC fixe physique (plus de VM à créer). |
| `autounattend.xml` | **(obsolète — réponse d'installation Windows pour la VM, conservé à titre historique)** **(ex-phase 1)** Réponse d'installation Windows automatisée (OOBE, compte admin **local** `ccw-admin`, activation de PowerShell Remoting pour le pilotage à distance). Sans objet sur PC physique. |
| `provisionner.ps1` | **(ex-phase 2)** Script PowerShell historiquement exécuté **dans** la VM : installe Git, GitHub CLI, Python 3, pyinstaller (winget) + Claude Code (installeur natif, sans Node.js), clone le dépôt en lecture seule dans `C:\CCW\Bridge_Agent`, écrit `configs\ccw.conf` (`LABEL=for-windows`, `NOM=ccw`, `REP_TRAVAIL=C:\CCW_Share` — chemin **local** sur le PC physique —, `TOPIC_NTFY` placeholder), et enregistre le service Windows `CCW-Watcher` via NSSM sous le compte **`AlainW`** (non-admin). Reste utilisable comme référence des étapes d'installation logicielle, à rejouer manuellement sur le PC physique le cas échéant. |
| `lancer_provisioning.py` | **(obsolète — orchestrait le provisioning distant via `VBoxManage guestcontrol`, conservé à titre historique)** **(ex-phase 2)** Orchestration côté **Linux (CCL)** : poussait et exécutait `provisionner.ps1` dans la VM via `VBoxManage guestcontrol` (copyto + run) sous le compte `ccw-admin`. Mot de passe lu via `CCW_ADMIN_PASSWORD` (jamais en clair ni committé). Sans objet sur PC physique (pas de VM à piloter à distance) : le provisioning logiciel s'y fait directement, en local. |
| `demarrer_ccw.sh` | **(obsolète — démarrait la VM VirtualBox, conservé à titre historique)** Wrapper de démarrage de la VM `CCW-Build` depuis CCL (issue #166) : `--type headless` par défaut (silencieux si déjà démarrée), `--gui`/`--fenetre` pour une fenêtre (`--type separate`), `--status` pour l'état (`VMState`) sans rien démarrer. Sans objet sur PC physique (pas de VM à démarrer — le PC est allumé en permanence). |
| `eval-expiration.json` | **(obsolète — liée à l'éval 90 jours de la VM, conservé à titre historique)** Métadonnées de l'évaluation 90 jours (issue #167) : `date_installation` (**2026-07-19**), `eval_jours` (90), `date_expiration` (informative, **2026-10-17**). Sans objet sur PC physique (licence Windows normale, pas d'éval à durée limitée). |
| `verifier_expiration_ccw.py` | **(obsolète — vérifiait l'expiration de l'éval de la VM, conservé à titre historique)** **(côté Linux)** Lit `eval-expiration.json`, recalcule l'expiration (`date_installation` + `eval_jours`) et le nombre de jours restants. À ≤ 10 j restants (ou déjà expiré) : avertissement + **code de sortie 2** (intégrable à une vérif automatisée) ; sinon confirmation calme + code 0. Sans dépendance externe. Sans objet sur PC physique. |
| `mettre_a_jour_tokens_ccw.ps1` | **(dans la VM)** Renouvellement des tokens d'un service CCW sans manipuler à la main la chaîne PowerShell (issue #168). Demande `GH_TOKEN` puis `CLAUDE_CODE_OAUTH_TOKEN` en `Read-Host -AsSecureString` (jamais affichés en clair), reconstruit `AppEnvironmentExtra` avec le saut de ligne `` `n`` **impératif** entre les deux (un simple espace corrompt silencieusement `GH_TOKEN` → « Bad credentials »), applique via `nssm set … AppEnvironmentExtra`, fait `nssm restart`, attend puis affiche les 10 dernières lignes du log de service et conclut OK / à vérifier (code 2 si `ERROR`). Paramétrable (`-NomService`, `-RepDepot`, et `-NomLog` pour cibler le bon log de service, ex. `ccw-scrabble-service.log`, issue #173) : sert aussi bien à `CCW-Watcher` qu'aux services multi-projets `CCW-Watcher-<NomProjet>` (issue #170). Depuis l'issue #174, accepte aussi `-FichierTokens <chemin>` : les deux valeurs sont alors **lues dans un fichier** « clé=valeur » (au lieu de `Read-Host`), ce qui permet à l'onglet CCW de poser les tokens à distance sans saisie dans la VM et sans jamais les passer en argument de commande. |
| `ajouter_projet_ccw.ps1` | **(obsolète — modèle multi-projets abandonné, conservé à titre historique)** **(dans la VM)** Instancie un projet CCW **supplémentaire** sur le modèle multi-projets (issue #170), sans rien réinstaller. Paramétrable (`-NomProjet`, `-Depot owner/repo`, ou prompt interactif) : clone le dépôt en lecture seule dans `C:\CCW\<NomProjet>`, écrit `configs\<nom>-ccw.conf` (`NOM=<nom>-ccw`, `LABEL=for-windows`, `REP_TRAVAIL`/`PERIMETRE`=`C:\CCW\<NomProjet>`, `TOPIC_NTFY` placeholder), et enregistre un service NSSM dédié `CCW-Watcher-<NomProjet>` (mêmes réglages que `CCW-Watcher` : `SERVICE_AUTO_START`, `AppExit Default Restart`, `AppRestartDelay`, `logs\ccw-<nom>-service.log`). Idempotent (clone mis à jour par pull, service arrêté/supprimé avant recréation). Ne configure **pas** `AppEnvironmentExtra` : chaque projet a son propre token dédié, posé ensuite en **une seule commande** via `finaliser_projet_ccw.ps1` (rappel affiché en fin de script). |
| `lister_projets_ccw.ps1` | **(dans la VM, appelé à distance — issue #174)** Inventaire **JSON** des projets CCW : énumère les services `CCW-Watcher*` (NSSM), et pour chacun émet le nom du service, le projet dérivé, l'état (`running`/`stopped`) et le statut du placeholder `TOPIC_NTFY` (lu dans le config, sans jamais renvoyer la valeur réelle du topic). Sortie encadrée par `<<<CCW_JSON>>>…<<<CCW_END>>>` pour extraction fiable côté Linux. Exécuté par l'onglet CCW de l'interface web. |
| `finaliser_projet_ccw_auto.ps1` | **(dans la VM, appelé à distance — issue #174)** Variante **non interactive** de `finaliser_projet_ccw.ps1` : lit `TOPIC_NTFY` + les deux tokens dans un **fichier « clé=valeur »** poussé par l'appelant (jamais en argument de commande), remplace le placeholder `TOPIC_NTFY` dans le config (édition ciblée) puis **appelle** `mettre_a_jour_tokens_ccw.ps1 -FichierTokens` (aucune duplication de la logique des tokens). Supprime le fichier de valeurs dans un `finally` (nettoyage côté VM). Code de sortie = celui du script de tokens (0/2/1). |
| `finaliser_projet_ccw.ps1` | **(obsolète — modèle multi-projets abandonné, conservé à titre historique)** **(dans la VM)** Finalise en **une seule commande** un projet déjà créé par `ajouter_projet_ccw.ps1` (issue #173, suite #170), regroupant les 3 étapes manuelles auparavant dispersées. À partir du seul `-NomProjet` (argument ou prompt), **dérive** `CCW-Watcher-<NomProjet>`, `C:\CCW\<NomProjet>` et `configs\<nom>-ccw.conf` (même logique qu'`ajouter_projet_ccw.ps1`) et **vérifie** leur existence (sinon renvoie vers `ajouter_projet_ccw.ps1`). Puis : (1) demande `TOPIC_NTFY` (`Read-Host`, pas un secret) et remplace le placeholder `###TOPIC_NTFY_A_DEFINIR###` **dans** le config par édition ciblée (le reste du fichier préservé, UTF-8 sans BOM) ; (2) rappelle les réglages du token dédié à créer (repo unique, permissions, expiration alignée) avec une **pause** ; (3) **appelle** `mettre_a_jour_tokens_ccw.ps1` (pas de duplication) avec les paramètres déduits — dont `-NomLog ccw-<nom>-service.log` — pour la saisie masquée + pose des tokens + redémarrage + vérif des logs ; (4) résumé final selon le code renvoyé. |
| `surveiller_builds.ps1` | **(dans la VM, lancé manuellement — issue #370)** Surveille en continu, pendant un build en cours (PyInstaller/ISCC), les processus de build et la croissance du dossier de sortie. Paramètre `-Dossier` **obligatoire** (chemin du dossier de sortie à surveiller, ex. `installeur\output`) ; `-Processus` optionnel (liste de noms de process à surveiller, défaut `claude, ISCC, python, pyinstaller`) ; `-IntervalleSecondes` optionnel (défaut `10`). À chaque passage : affiche pour chaque process surveillé son PID/CPU/mémoire/durée de vie s'il est actif, et la taille du dossier avec le delta depuis le dernier passage et depuis le début. Exemple : `powershell -ExecutionPolicy Bypass -File provisioning\windows\surveiller_builds.ps1 -Dossier C:\CCW\actualise\installeur\output -IntervalleSecondes 15`. **Attention** : le nom de process Claude Code (`claude` par défaut dans `-Processus`) est une hypothèse à vérifier via `Get-Process` pendant un build réel — l'installeur natif Windows peut l'enregistrer sous un nom différent, auquel cas le passer explicitement en paramètre. |

> **⚠️ Obsolète (PC physique, issue #446).** Les deux paragraphes qui suivent
> décrivent l'ancienne VM **Windows 11 IoT Enterprise LTSC 2024 en évaluation
> 90 jours** et sa procédure de recréation. Le PC fixe physique tourne sous
> une licence Windows normale, sans éval à durée limitée : il n'y a **plus
> aucune expiration à surveiller ni de VM à recréer**. Conservés ci-dessous
> à titre historique.

**(obsolète)** La VM cible **Windows 11 IoT Enterprise LTSC 2024** en
évaluation 90 jours, d'où la recréation facile prévue.

**(obsolète) Expiration de l'évaluation (issue #167).** L'évaluation 90
jours de `CCW-Build` a été installée le **19 juillet 2026** et expire le
**17 octobre 2026**. Après expiration, Windows redémarre automatiquement
toutes les heures, ce qui casse en continu le service `CCW-Watcher` : il
faut recréer la VM **avant** cette date (sans urgence, via
`creer_vm_ccw.py --recreate`). Pour connaître les jours restants à tout
moment :

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
échec (`AppExit Default Restart` + `AppRestartDelay 5000`). Cela remplace
l'ancienne tâche planifiée `-AtLogOn`, qui ne redémarrait pas au boot sans
session ; la boucle interne du watcher reste la première ligne de
robustesse.

> **Compte NSSM — `AlainW`, pas `LocalSystem` (issue #446).** Sur le PC fixe
> physique, le service `CCW-Watcher` tourne sous le compte **`AlainW`**
> (utilisateur non-admin), et non plus sous `LocalSystem`. `REP_TRAVAIL`
> pointe vers `C:\CCW_Share`, un chemin **local** au PC. La justification
> historique de `LocalSystem` — un chemin UNC (`\\VBOXSVR\CCW_Share`)
> inaccessible aux lecteurs réseau montés en session interactive, alors que
> `LocalSystem` y accédait — **ne s'applique plus** : un chemin local est
> accessible normalement à n'importe quel compte, y compris `AlainW`. Le
> paramètre `$LettrePartage` (issue #149) et sa logique de résolution de
> lettre de lecteur réseau n'ont donc plus lieu d'être.

**(obsolète — provisioning distant via VM, conservé à titre historique)
Lancer le provisioning (une fois Windows installé et la session ouverte) :**

```bash
# Côté CCL (Linux), VM démarrée avec Guest Additions :
export CCW_ADMIN_PASSWORD='…'                       # jamais committé
python3 provisioning/windows/lancer_provisioning.py --dry-run   # vérif
python3 provisioning/windows/lancer_provisioning.py             # copie + exécute
```

Puis, dans la VM : renseigner `TOPIC_NTFY` dans `configs\ccw.conf` et
authentifier Claude (`ANTHROPIC_API_KEY` en variable d'environnement, ou
`claude auth login` une fois). Sur le PC physique, ces étapes se font
directement en local, sans orchestration distante via `VBoxManage`.

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

> **⚠️ Sous-section entièrement obsolète (PC physique, issue #446), conservée
> à titre historique.** Elle décrit la procédure de recréation de la VM
> `CCW-Build` à l'expiration de son éval Windows 90 jours. Sur le PC fixe
> physique, il n'y a **plus de VM ni d'éval à durée limitée** — cette
> procédure ne s'applique plus. Le renouvellement des tokens GitHub/Claude
> (étape 2 ci-dessous) reste en revanche une opération valide en tant que
> telle, indépendamment de la VM, à refaire simplement à l'échéance propre
> de chaque token.

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

> **⚠️ Étape 0 et note `safe.directory` obsolètes (PC physique, issue #446).**
> La contrainte `safe.directory` de git ne se déclenche que sur un chemin
> **UNC** dont le propriétaire diffère de l'utilisateur courant — c'était le
> cas de l'ancien partage VirtualBox `\\VBoxSvr\CCW_Share`. `C:\CCW_Share`
> est un chemin **local** appartenant au compte `AlainW` qui exécute
> `CCW-Watcher` : cette contrainte ne se pose plus, l'étape 0 est donc à
> **sauter**. Conservée ci-dessous à titre historique.

~~Étape 0 — Ajouter l'exception `safe.directory` (nécessaire sur chemin UNC,
une seule fois par sous-dossier) :~~

```bash
git config --global --add safe.directory '%(prefix)///VBoxSvr/CCW_Share/CCW/<projet>'
```

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
physique — plus de partage VirtualBox ; chemin exact de montage côté CCL
selon la configuration réseau en place).

**Dépôts sources :** publics sur GitHub — aucun token Contents requis.
Le token `CCW-Watcher` (Issues read/write sur Bridge_Agent) suffit.

**Note safe.directory (obsolète, conservée à titre historique) :** git
refusait de travailler sur le chemin UNC de l'ancien partage VirtualBox
dont le propriétaire différait de l'utilisateur courant. L'exception était
à ajouter en étape 0 de chaque première issue sur un nouveau sous-dossier.
Sans objet avec le chemin local `C:\CCW_Share` du PC physique.

**Note staging local (issue #297, historique — partage VirtualBox) :**
pattern général de contournement de la corruption de fichiers constatée sur
l'ancien partage VirtualBox `\\VBOXSVR\CCW_Share`, et checklist par projet
buildé (dont Scrabble) — voir `BUILD_WINDOWS_CCW.md`. À revalider sur le
chemin local `C:\CCW_Share` du PC physique (la cause du problème étant
spécifique aux partages réseau VirtualBox, elle ne s'applique probablement
plus, mais ce n'est pas encore confirmé).

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
> (§16.2), ce bouton s'appuie sur `VBoxManage guestcontrol` pour agir à
> distance sur la VM : il est **inopérant** sur un PC physique. En
> attendant sa refonte, utiliser la **procédure manuelle** décrite
> ci-dessus (redémarrage du service + suppression des `.lock`).

Le bouton ⛔ « Interrompre
cette issue », affiché sur toute issue ouverte ni `done` ni `needs-human` dans
l'interface, automatise cette procédure à distance depuis Linux pour les
issues `for-windows` : `POST /interrompre` (`app/interruption.py::
interrompre_windows`) copie et exécute `provisioning/windows/
interrompre_projet_ccw.ps1` dans la VM via `VBoxManage guestcontrol` — arrêt
du service NSSM (`nssm stop <Service>`), vérification bornée (~5 s, kill
ciblé si besoin) que l'arbre de process du service (watcher + éventuel
`claude` orphelin) est bien mort, puis suppression des `.lock` de
`<RepDepot>\logs\verrous\` **uniquement** si cet arbre est confirmé mort —
sinon le verrou est volontairement laissé en place, pour ne jamais risquer un
double traitement. Le label `needs-human` et un commentaire de traçabilité
sont toujours postés sur GitHub ; l'issue n'est **pas** fermée et le watcher
CCW n'est **jamais** relancé automatiquement (relance manuelle via l'onglet
CCW). Voir § « Interrompre une issue bloquée » (§13) pour le pendant côté CCL
et le détail commun de l'interface (bouton, route Flask, statuts).

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
- **Script bip partagé `scripts/traitement_fin.py`** (anciennement
  `scripts/bip.py`, renommé issue #350) : le bip vivait dans `~/NicLink/bip.py`
  (dépôt AlChess) alors que c'est de l'infrastructure commune à tous les projets.
  Il a été déplacé/recréé dans `scripts/`, renommé une première fois `bip.py`
  puis `traitement_fin.py` (#350, une fois devenu aussi le déclencheur du SSE
  de fin d'issue — voir §17.3) ; le **défaut** de `SCRIPT_BIP` pointe désormais
  vers lui. **La clé de config reste `SCRIPT_BIP`** (renommer impliquerait de
  modifier les `configs/*.conf` gitignorés, hors périmètre agent — voir §17.3
  pour la marche à suivre manuelle).

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
  `numero` ajouté) et jusqu'à `app/notifications_poller.py` (transitions
  détectées côté CCW). Comme le bip lui-même, ce POST reste **opt-in via les
  labels `notif_*`** (§4) : `notifications.notifier()` n'appelle `bip()` que si
  l'issue en porte un — sans label, la ligne reste soumise au ↻ manuel / au
  fetch post-TIMEOUT de #334, exactement comme avant #350.
- **`POST /notifier-fin-issue`** (`app/fin_issue.py`, sans `login_requis` —
  appelé par un script local, pas par un navigateur, comme `/heartbeat`) :
  pousse un événement SSE `event: fin_issue\ndata: {"projet": ..., "numero": ...}`
  à tous les onglets Résultats actuellement ouverts.
- **`GET /stream`** (`app/fin_issue.py`, protégé par `login_requis` comme
  `/events`) : générateur Flask SSE dédié, séparé de `/events` (cycle de vie)
  et de `/journal/<projet>` (log watcher). Mécanisme de diffusion : une
  **`queue.Queue` par connexion active**, ajoutée à la liste partagée
  `app.config["FIN_ISSUE_ABONNES"]` à la connexion et retirée (`finally`,
  couvre le `GeneratorExit` d'une déconnexion navigateur) à la fermeture — pas
  de broadcast global, car new_issue.py est mono-utilisateur mais plusieurs
  onglets peuvent être ouverts en même temps. Ping `: ping\n\n` toutes les 30 s
  pour maintenir la connexion (proxys, navigateur).
- **Côté navigateur** (`static/js/app.js`) : `demarrerStreamFinIssue()` ouvre
  l'`EventSource('/stream')` à l'entrée dans l'onglet Résultats
  (`basculerOnglet`), `arreterStreamFinIssue()` la ferme en le quittant. Sur
  réception d'un événement `fin_issue` dont le numéro figure dans
  `listeIssuesResultats`, appelle directement `verifierIssueApresDepassement()`
  (§ issue #334 dans `app.js`) — même fetch de vérification, même
  `remplacerLigneIssue()`, aucune logique dupliquée. La reconnexion après
  coupure est native à `EventSource`, sans code supplémentaire.

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

---

## 20. Watcher `issues_inbox` centralisé (issue #483)

### 20.1 Objectif

Jusqu'ici, une issue générée par Claude Chat devait être copiée-collée à la
main dans l'onglet **« Nouvelle issue »** de `new_issue.py` (§3). Le watcher
**`scripts/watcher_issues_inbox.py`** automatise ce geste : Claude Chat (ou
Alain en CLI) dépose un fichier `.txt` dans **`~/Bridge_Agent/issues_inbox/`**,
le watcher le détecte, le valide, crée l'issue via `gh issue create` et
nettoie — sans repasser par le formulaire web.

### 20.2 Structure disque

- **`issues_inbox/`** (gitignoré, créé automatiquement au premier lancement
  du watcher s'il n'existe pas) : fichiers `.txt` en attente, nommage libre
  (le watcher ne se fie qu'au contenu, pas au nom de fichier).
- **`issues_inbox/rejected/`** : fichiers rejetés (en-tête malformé, projet
  inconnu, échec de `gh issue create`...), renommés
  `<nom-original>__REJETE-<slug-du-motif>.txt` pour que le motif soit visible
  sans ouvrir le fichier. Laissés en place pour correction manuelle — le
  watcher ne les retraite jamais automatiquement.

### 20.3 Format attendu du fichier

Même format qu'une issue produite par Claude Chat pour le formulaire web
(§3) : un en-tête `| CHAMP | Valeur |` optionnel suivi d'une ligne
`#Titre: ...` puis le corps. Champs d'en-tête reconnus, tous optionnels sauf
`PROJET` :

| Champ     | Rôle                                                                |
|-----------|----------------------------------------------------------------------|
| `PROJET`  | **Obligatoire** — doit correspondre à `configs/<PROJET>.conf`        |
| `TIMEOUT` | Nombre (secondes, suffixe `s` toléré) — sinon défaut du projet       |
| `MODELE`  | Doit être une valeur reconnue (`claude-sonnet-5`, etc.) si fourni    |
| `MODE`    | Reconnu de façon tolérante (§5) — absent/non reconnu → `lecture`     |
| `LABELS`  | Labels GitHub additionnels, séparés par des virgules                 |

Le fichier est reparsé avec les mêmes regex que `static/js/app.js` (détection
de champ d'en-tête à la frappe côté formulaire web), pour ne jamais diverger
du format déjà produit par Claude Chat.

### 20.4 Validation avant création

Un fichier est rejeté (déplacé vers `rejected/`, jamais créé sur GitHub) si :
`PROJET` absent/vide, `configs/<PROJET>.conf` introuvable ou invalide,
`#Titre:` absent/vide, `MODELE` fourni mais non reconnu, ou `TIMEOUT` fourni
mais non numérique. Un échec de `gh issue create` (réseau, dépôt inaccessible,
timeout de 30s...) provoque le même sort, avec le message d'erreur de `gh`
en détail.

### 20.5 Journalisation (rotation par nombre de lignes)

Chaque traitement (réussi ou rejeté) ajoute une ligne à
**`logs/issues_inbox.log`** :
`<horodatage> | <projet> | OK|REJECTED | <titre> [— <détail si rejet>]`.
Rotation propre à ce watcher, **distincte** de la rotation par taille des
autres watchers (§13) : dès que le fichier dépasse **`MAX_LOG_LINES`**
(défaut 50), les lignes les plus anciennes sont supprimées — pas de fichier
`.1`/`.2`, un seul fichier plat borné en permanence à 50 lignes.

### 20.6 Concurrence

Avant de traiter un fichier `.txt`, le watcher vérifie que sa date de
dernière modification remonte à **au moins 1 seconde** — sinon il le laisse
pour le cycle de polling suivant, pour ne jamais lire un fichier encore en
cours d'écriture (dépôt via un outil qui écrit progressivement).

### 20.7 Config (optionnelle)

`configs/watcher_issues_inbox.conf` — clés `NOM`, `REP_TRAVAIL`,
`POLLING_INTERVAL` (défaut 5s), `MAX_LOG_LINES` (défaut 50), `INBOX_DIR`,
`REJECTED_DIR`, `GH_TOKEN`. Toutes optionnelles : le watcher tourne avec des
défauts sensés (dossiers sous `~/Bridge_Agent`) même sans ce fichier.
**Ce `.conf` n'est pas créé automatiquement par CCL** — garde-fou §11 (CCL ne
modifie/crée jamais `configs/*.conf`) : c'est à Alain de le créer à la main
s'il veut surcharger les défauts.

Lancement : `python3 scripts/watcher_issues_inbox.py` (boucle continue),
`--config <chemin>` pour un `.conf` alternatif, `--once` pour un seul cycle
(tests). Peut être supervisé en systemd/NSSM comme les autres watchers (§13),
en dehors du cycle de vie de `watcher.py` (générique, par projet) puisqu'il
ne traite pas des issues GitHub existantes mais alimente leur création.

### 20.8 Onglet « Résultats inbox » de `new_issue.py`

Nouvel onglet dans l'interface web, alimenté par la route
**`GET /issues-inbox/etat`** (`app/issues_inbox.py`, pure lecture disque —
aucun appel `gh`, aucune dépendance à un watcher en cours d'exécution) :

- **Alarme** pilotée **uniquement** par l'état du dossier
  `issues_inbox/rejected/` — non vide → badge 🚨 clignotant sur l'onglet
  lui-même (visible même hors de cette vue) + bandeau rouge dans le panneau ;
  vide → aucun indicateur. Volontairement **pas** de parsing de log pour cette
  décision (§ Tâche demandée de l'issue #483) : l'état du dossier est la
  seule source de vérité, plus simple et plus fiable qu'un état dérivé du log.
- **Zone détail** : tableau des fichiers présents dans `rejected/` (nom +
  date de dépôt), et un historique **purement informatif** des dernières
  lignes de `logs/issues_inbox.log` — celui-ci n'influence jamais l'alarme.
- **Rafraîchissement** : `rafraichirInbox()` (`static/js/app.js`) tourne en
  polling continu (7s) indépendamment de l'onglet actif, pour que le badge
  reste à jour même quand un autre onglet est ouvert ; bouton « Rafraîchir »
  pour un rafraîchissement immédiat.

### 20.9 Workflow utilisateur final

1. Claude Chat (ou Alain) dépose un fichier `.txt` dans `issues_inbox/`.
2. Le watcher le détecte au cycle de polling suivant, crée l'issue GitHub
   (mêmes labels/en-tête que le formulaire web), supprime le fichier, journalise.
3. Alain voit le statut dans l'onglet « Résultats inbox » de `new_issue.py`.
4. Un fichier rejeté reste visible dans `issues_inbox/rejected/` — alarme
   allumée tant qu'il n'est pas corrigé/supprimé à la main.

### 20.10 Pilotage du watcher depuis le panneau Infrastructure (issue #485)

Jusqu'ici, le watcher devait être lancé manuellement en CLI, sans suivi
depuis l'interface. Il est maintenant pilotable comme les watchers de
projet (§ « Cycle de vie des watchers », `app/watchers.py`), mais avec sa
propre logique dans `app/issues_inbox.py` puisqu'il n'y a **qu'un seul**
watcher spool (pas de paramètre projet).

**Fichier PID** : `logs/watcher-issues_inbox.pid`, même convention que les
watchers de projet (`logs/watcher-<nom>.pid`). Écrit par le lanceur
(`demarrer_watcher_inbox()`) au démarrage — le script
`scripts/watcher_issues_inbox.py` ne l'écrit jamais lui-même, seulement à sa
propre auto-extinction où il le supprime (avec le fichier d'échéance) pour
ne jamais laisser un PID orphelin visible dans l'interface.

**Durée configurable au démarrage.** Contrairement aux watchers de projet
(`DELAI_INACTIVITE_MIN` dans le `.conf`, § « Cycle de vie des watchers »),
le watcher spool tourne par défaut **indéfiniment** — il n'y a pas de notion
d'« inactivité » pertinente pour un dossier de dépôt. Au clic sur
« ▶ Démarrer », un modal (`#modal-duree-watcher-inbox`) propose trois choix
par case à cocher : Indéfiniment (défaut), 30 min, ou un nombre de minutes
libre. Le choix est transmis à `POST /issues-inbox/demarrer-watcher`
(`{duree_min: N}`, 0/absent = indéfini), qui lance le script avec l'argument
CLI `--duree-min <N>`. L'**auto-extinction est interne au script** (fonction
`boucle()`), sur le même principe que l'extinction pour inactivité de
`watcher.py` (horloge **monotone**, insensible à un changement d'heure
système) : à l'écoulement du délai, arrêt propre (`sys.exit(0)`) après
suppression de son propre fichier PID et de son fichier d'échéance.

Un fichier d'échéance séparé, **`logs/watcher-issues_inbox.echeance`**
(epoch, écrit par `demarrer_watcher_inbox()` si une durée a été choisie),
permet à l'interface d'afficher le temps restant sans dépendre de l'horloge
interne du process watcher, qui tourne dans un process séparé de Flask.

**Si le watcher tourne déjà** et qu'on clique « ↺ Relancer » avec une
nouvelle durée : `demarrer_watcher_inbox()` arrête TOUJOURS l'ancien process
(`SIGTERM`) avant de relancer — pas de refus silencieux, la nouvelle durée
remplace systématiquement l'ancienne, quel que soit l'état courant.

**Arrêt manuel.** `POST /issues-inbox/arreter-watcher` envoie un `SIGTERM`
et nettoie PID + échéance. Contrairement aux watchers CCL de projet (pas de
bouton « Arrêter » dans `#pl-zone-monitoring`, seulement Lancer/Relancer),
le watcher spool expose un bouton « ⏹ Arrêter » explicite dans le panneau :
son comportement par défaut étant « Indéfiniment », il doit pouvoir être
coupé manuellement à tout moment.

**Interface — zone `#pl-zone-extras`.** Cette zone du panneau flottant
« Infrastructure » (onglet Résultats), réservée aux futurs boutons depuis
l'issue #380 et restée vide jusqu'ici, est occupée par
`rendrePanneauLateralExtras()` (`static/js/app.js`) : une ligne d'état
🟢/⚫ « Watcher spool (issues_inbox) », alimentée par le même
`GET /issues-inbox/etat` que l'onglet « Résultats inbox » (étendu avec
`watcher_actif`/`watcher_pid`/`watcher_restant_s`). Watcher actif : temps
restant avant extinction (ou « indéfini »), boutons « ↺ Relancer » et
« ⏹ Arrêter ». Watcher inactif : bouton « ▶ Démarrer ». Les deux boutons de
démarrage ouvrent le modal de choix de durée. Rafraîchie sur le même cycle
que le reste du panneau (30 s, `rafraichirPanneauLateralResultats`).

---

*Dernière mise à jour : 25 août 2026 — §20.10 « Pilotage du watcher depuis
le panneau Infrastructure » (issue #485) : le watcher spool `issues_inbox`
devient pilotable (démarrer avec durée, relancer, arrêter) depuis
`#pl-zone-extras` (zone réservée depuis l'issue #380), au lieu d'un
lancement CLI manuel non suivi. `app/issues_inbox.py` gère le fichier PID
`logs/watcher-issues_inbox.pid` (même convention que `app/watchers.py`),
`demarrer_watcher_inbox`/`arreter_watcher_inbox` (routes
`/issues-inbox/demarrer-watcher` et `/issues-inbox/arreter-watcher`) ;
`scripts/watcher_issues_inbox.py` reçoit `--duree-min` et s'auto-éteint en
interne à l'échéance (horloge monotone, nettoyage de son propre PID).
Précédemment — 25 août 2026 — §10/§20 « Watcher `issues_inbox`
centralisé » (issue #483) : nouveau flux de création d'issues sans passage
par le formulaire web — `scripts/watcher_issues_inbox.py` scrute
`issues_inbox/`, valide et crée via `gh issue create`, journalise dans
`logs/issues_inbox.log` (rotation à 50 lignes) ; fichiers rejetés déplacés
vers `issues_inbox/rejected/`. Nouvel onglet « Résultats inbox » dans
`new_issue.py` (`app/issues_inbox.py`, route `/issues-inbox/etat`), alarme
visuelle pilotée uniquement par l'état (vide/non-vide) de `rejected/`.
Précédemment — 18 août 2026 — §16 « Agent Windows CCW » (issue
#446) : mise à jour pour le passage de CCW d'une VM VirtualBox à un **PC
fixe physique dédié** (Pentium G2020). Introduction reformulée en
conséquence. Paramètres corrigés partout dans le §16 : `REP_TRAVAIL =
C:\CCW_Share` (chemin local, remplace `\\VBOXSVR\CCW_Share`) ; service NSSM
`CCW-Watcher` tournant sous le compte **`AlainW`** (non-admin), et non plus
`LocalSystem` — la justification historique de `LocalSystem` (chemin UNC
inaccessible aux lecteurs montés en session) ne s'applique plus avec un
chemin local. Scripts `creer_vm_ccw.py`, `lancer_provisioning.py`,
`demarrer_ccw.sh` (+ `autounattend.xml`, `eval-expiration.json`,
`verifier_expiration_ccw.py`) marqués **obsolètes** dans le tableau de
provisioning (conservés à titre historique). §16.1 (maintenance/recréation
VM à 90 jours) et la contrainte `safe.directory` (§16.3) marquées
obsolètes dans leur ensemble — plus de VM ni de chemin UNC à gérer.
L'onglet CCW (§16.2) et le bouton « Interrompre » (§16.4) signalés
**partiellement obsolètes** : leurs fonctions reposant sur `VBoxManage
guestcontrol` sont inopérantes sur un PC physique, en attendant une refonte
adaptée (pas de VM à piloter).
Précédemment — §3 « Convention de présentation côté Claude Chat » (issue
#443) : la règle du bloc de code unique (issue #153), jusqu'ici formulée
pour le mode lot seulement, est étendue explicitement au cas mono-issue —
une issue unique est elle aussi présentée dans un bloc de code, afin
qu'Alain puisse utiliser le bouton copier du bloc. §11 « Conventions de
code » : le bullet « Issues » précise désormais que le corps est toujours
présenté dans un bloc de code, qu'il s'agisse d'une issue seule ou d'un
lot.*

Historique complet : voir [`CHANGELOG.md`](CHANGELOG.md).
