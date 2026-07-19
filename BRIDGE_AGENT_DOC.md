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
§16) sans repasser par `gh issue create` en ligne de commande. Plusieurs labels
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

### Watchers en services systemd utilisateur (démarrage auto + auto-restart)

Depuis l'issue #119, les watchers des projets actifs tournent en services
`systemd --user` : ils **démarrent automatiquement** (à l'ouverture de session,
et dès le boot grâce au linger) et se **relancent automatiquement** en cas de
crash (`Restart=always`, `RestartSec=10`). Plus besoin de cliquer « Lancer
watcher » après un redémarrage du PC ou un crash.

Gabarit : `systemd/watcher@.service` (une instance par projet via `%i`).
Le nom du projet paramètre le fichier de config : `watcher@alchess` lance
`watcher.py --config configs/alchess.conf`.

```bash
# Installation / réinstallation (copie le gabarit, daemon-reload,
# enable --now des 4 instances, active le linger utilisateur)
cd ~/Bridge_Agent && ./installer_services.sh

# État d'un watcher / de tous
systemctl --user status watcher@alchess
systemctl --user list-units 'watcher@*'

# Suivre le journal en direct (filet de sécurité si le crash survient AVANT
# que le log fichier logs/watcher-<nom>.log soit configuré, p. ex. .conf illisible)
journalctl --user -u watcher@alchess -f

# Arrêter / relancer / désactiver une instance
systemctl --user restart watcher@alchess
systemctl --user stop watcher@alchess
systemctl --user disable --now watcher@alchess

# Après édition du gabarit systemd/watcher@.service
cp systemd/watcher@.service ~/.config/systemd/user/ && systemctl --user daemon-reload
```

> ⚠️ **Le bouton « Lancer watcher » de l'interface devient un filet de secours,
> pas le mode de démarrage normal.** systemd est désormais la source de vérité.
> Les deux mécanismes ne se voient pas : systemd suit son process via son
> cgroup, l'interface via un fichier PID (`logs/watcher-<nom>.pid`) que le
> service n'écrit jamais. Conséquences :
> - un watcher lancé par systemd s'affiche « inactif » dans l'onglet
>   « Watchers » (pas de fichier PID) ;
> - cliquer « Lancer watcher » démarrerait un **second** process pour le même
>   projet (doublon, doubles commentaires possibles sur les issues) ;
> - « Arrêter watcher » ne tue pas l'instance systemd, et `Restart=always` la
>   relancerait de toute façon.
>
> Pour un arrêt/relance propre, passer par `systemctl --user …`. La
> neutralisation éventuelle du bouton côté interface (`app/watchers.py` +
> templates) reste à trancher — voir l'en-tête de `installer_services.sh`.

---

## 14. Vision multi-agent (évolution future)

> Section prospective — pas encore implémentée. Elle fixe une direction pour
> guider les futures évolutions du bridge et ne pas perdre l'idée.

**Principe :** un CCL « chef d'orchestre » reçoit une tâche complexe,
la découpe en sous-tâches, crée une issue GitHub par sous-tâche,
attend que les CCL « ouvriers » les traitent en parallèle, assemble
les résultats, valide la cohérence et livre une réponse complète
avant de se terminer.

**Flux :**

```
Claude Chat → crée 1 issue « tâche complexe »
   │
   ▼
CCL chef d'orchestre
   │  1. analyse la tâche et la découpe en N sous-tâches
   │  2. crée N issues GitHub (une par sous-tâche, label for-linux)
   │
   ├─→ CCL ouvrier #1  ─┐
   ├─→ CCL ouvrier #2   │  traitement en parallèle
   ├─→ …                │  (chacun ferme son issue + poste son résultat)
   └─→ CCL ouvrier #N  ─┘
   │
   │  3. attend la fermeture des N issues ouvrières
   │  4. récupère et assemble les N résultats
   │  5. valide la cohérence de l'ensemble
   ▼
CCL chef d'orchestre → poste la réponse complète → ferme l'issue mère
   │
   ▼
notification GSM/bureau
```

**Format des titres :**

- **Chef** : titre préfixé par `Chef : ` (ex. `Chef : refonte de l'onglet Résultats`).
- **Ouvrier** : titre préfixé par `Ouvrier N : ` où N est le numéro
  (ex. `Ouvrier 1 : ...`, `Ouvrier 2 : ...`).
- **Claude Chat génère toujours l'issue chef uniquement** — les ouvriers sont
  créés par le chef lui-même via `gh issue create`.

**Points à concevoir avant implémentation :**

- **Découpage** : le chef d'orchestre doit produire des sous-tâches
  indépendantes (pas de dépendances croisées entre ouvriers), sinon la
  parallélisation n'apporte rien.
- **Attente / synchronisation** : mécanisme fiable pour détecter la
  fermeture des issues ouvrières (polling GitHub ou réutilisation du watcher).
- **Anti-boucle** : empêcher qu'un ouvrier recrée à son tour des sous-issues
  (risque de récursion infinie) — ex. un flag « niveau » dans l'en-tête.
- **Périmètre & concurrence** : plusieurs CCL écrivant en parallèle dans le
  même dépôt = risque de conflits git. Prévoir un périmètre par ouvrier ou
  une sérialisation des commits (voir §5 et §8).
- **Timeout global** : le chef d'orchestre doit avoir un timeout couvrant
  l'ensemble des ouvriers, plus large que le TIMEOUT d'une issue simple.
- **Échec partiel** : décider du comportement si un ouvrier échoue
  (réponse partielle documentée vs échec global).

---

## 15. Pattern Chef + Specs MVC (évolution future)

> Section prospective — pas encore implémentée, complémentaire au pattern
> chef/ouvrier générique du §14 (celui-ci reste valable pour un découpage
> ad hoc ponctuel ; celui-ci vise un découpage fixe et récurrent par couche).

**Principe :** pour un projet donné, trois CCL spécialisés permanents
coexistent, chacun restreint à un périmètre de dossiers fixe et disposant
de son propre fichier de contexte :

| Rôle | Titre préfixé | Fichier de contexte | Périmètre (exemple) |
|------|---------------|---------------------|----------------------|
| Spec-Vue | `Spec-Vue : ` | CONTEXTE_VUE.md | templates/, static/ |
| Spec-Métier | `Spec-Métier : ` | CONTEXTE_METIER.md | modules de logique/contrôleur |
| Spec-Persistance | `Spec-Persistance : ` | CONTEXTE_PERSISTANCE.md | modèles, migrations, configs |

**Les trois rôles sont créés dès la mise en place du pattern sur un projet,
même si l'un d'eux reste peu ou pas utilisé au départ** — créer le rôle et
son contexte à l'avance coûte moins cher que devoir l'ajouter dans l'urgence
le jour où un besoin de persistance apparaît soudainement.

**Différence clé avec le chef/ouvrier du §14 :** le découpage n'est **pas**
décidé par le CCL chef à l'exécution. C'est Claude Chat qui décide, au
moment de rédiger l'issue, quel(s) Spec(s) sont concernés par la demande,
via un champ structuré dans l'en-tête :

```markdown
| SPECS | vue |
```

> Le champ `SPECS` (pluriel) accepte un ou plusieurs rôles en **minuscules**,
> séparés par des virgules sur **une seule ligne** — `vue`, `metier`,
> `persistance` — selon les couches touchées par la demande. Pour plusieurs
> couches, tout tient sur une ligne : `| SPECS | vue, metier |` (et **non**
> une ligne par valeur), ici pour une fonctionnalité qui modifie à la fois
> l'affichage et la logique. Chaque valeur route l'issue vers le Spec
> correspondant, avec son périmètre de dossiers et son fichier de contexte
> propres. Absent = pas de spécialisation (issue normale ou pattern §14).
> (Valeurs en minuscules, cohérent avec `chef`/`ouvrier` du champ `TYPE` au §6.)

**Points à concevoir avant implémentation** (en plus de ceux du §14) :

- **Routage** : le watcher (ou un dispatcher) doit lire le champ `SPECS` et
  aiguiller l'issue vers le bon CCL spécialisé, avec le bon fichier de
  contexte et le bon périmètre.
- **Multi-Spec** : une issue touchant plusieurs couches (`vue, metier`) doit
  être décomposée en issues mono-Spec (une par couche), ce qui rejoint la
  logique chef/ouvrier du §14 — le chef devient alors un simple répartiteur
  vers les Specs concernés.
- **Cohérence des contextes** : les trois fichiers `CONTEXTE_*.md` décrivent
  des périmètres disjoints ; prévoir une convention pour les points de contact
  (ex. contrat d'interface entre Vue et Métier) afin d'éviter les divergences.
- **Périmètre strict** : chaque Spec refuse de travailler hors de ses dossiers
  (cohérent avec le §7), ce qui limite mécaniquement les conflits git entre
  Specs travaillant en parallèle.

---

## 16. Agent Windows CCW (en préparation)

> Section prospective — provisioning phase 1 en place (issue #146), l'agent
> lui-même n'est pas encore opérationnel.

**But :** disposer d'un futur agent **Claude Code Windows (CCW)** tournant dans
une VM Windows, pour déléguer depuis CCL les builds `.exe` (PyInstaller) qui
exigent un environnement Windows natif. CCW jouera côté Windows le rôle que CCL
joue côté Linux : surveiller des issues et les traiter.

> ⚠️ **Rappel provisioning : tout script `.ps1` de cette section doit être créé
> avec un BOM UTF-8 (`EF BB BF`) en tête** — sans quoi Windows PowerShell 5.1 le
> lit en ANSI et plante au parsing avec des `UnexpectedToken` en cascade sur les
> lignes accentuées (cf. §11 « Conventions de code » pour la règle complète et le
> correctif ; historique : #151, #170, #172).

**Label `for-windows`** (miroir de `for-linux`, couleur `#0e8a16`) : marque les
issues destinées à l'agent Windows. Comme `for-linux` conditionne la prise en
charge par `watcher.py` côté Linux, `for-windows` conditionnera la prise en
charge par le watcher côté CCW. Créer une issue for-windows :

```bash
gh issue create --repo AlainDelree/Bridge_Agent --label "bridge,for-windows" ...
```

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
| `ajouter_projet_ccw.ps1` | **(dans la VM)** Instancie un projet CCW **supplémentaire** sur le modèle multi-projets (issue #170), sans rien réinstaller. Paramétrable (`-NomProjet`, `-Depot owner/repo`, ou prompt interactif) : clone le dépôt en lecture seule dans `C:\CCW\<NomProjet>`, écrit `configs\<nom>-ccw.conf` (`NOM=<nom>-ccw`, `LABEL=for-windows`, `REP_TRAVAIL`/`PERIMETRE`=`C:\CCW\<NomProjet>`, `TOPIC_NTFY` placeholder), et enregistre un service NSSM dédié `CCW-Watcher-<NomProjet>` (mêmes réglages que `CCW-Watcher` : `SERVICE_AUTO_START`, `AppExit Default Restart`, `AppRestartDelay`, `logs\ccw-<nom>-service.log`). Idempotent (clone mis à jour par pull, service arrêté/supprimé avant recréation). Ne configure **pas** `AppEnvironmentExtra` : chaque projet a son propre token dédié, posé ensuite en **une seule commande** via `finaliser_projet_ccw.ps1` (rappel affiché en fin de script). |
| `lister_projets_ccw.ps1` | **(dans la VM, appelé à distance — issue #174)** Inventaire **JSON** des projets CCW : énumère les services `CCW-Watcher*` (NSSM), et pour chacun émet le nom du service, le projet dérivé, l'état (`running`/`stopped`) et le statut du placeholder `TOPIC_NTFY` (lu dans le config, sans jamais renvoyer la valeur réelle du topic). Sortie encadrée par `<<<CCW_JSON>>>…<<<CCW_END>>>` pour extraction fiable côté Linux. Exécuté par l'onglet CCW de l'interface web. |
| `finaliser_projet_ccw_auto.ps1` | **(dans la VM, appelé à distance — issue #174)** Variante **non interactive** de `finaliser_projet_ccw.ps1` : lit `TOPIC_NTFY` + les deux tokens dans un **fichier « clé=valeur »** poussé par l'appelant (jamais en argument de commande), remplace le placeholder `TOPIC_NTFY` dans le config (édition ciblée) puis **appelle** `mettre_a_jour_tokens_ccw.ps1 -FichierTokens` (aucune duplication de la logique des tokens). Supprime le fichier de valeurs dans un `finally` (nettoyage côté VM). Code de sortie = celui du script de tokens (0/2/1). |
| `finaliser_projet_ccw.ps1` | **(dans la VM)** Finalise en **une seule commande** un projet déjà créé par `ajouter_projet_ccw.ps1` (issue #173, suite #170), regroupant les 3 étapes manuelles auparavant dispersées. À partir du seul `-NomProjet` (argument ou prompt), **dérive** `CCW-Watcher-<NomProjet>`, `C:\CCW\<NomProjet>` et `configs\<nom>-ccw.conf` (même logique qu'`ajouter_projet_ccw.ps1`) et **vérifie** leur existence (sinon renvoie vers `ajouter_projet_ccw.ps1`). Puis : (1) demande `TOPIC_NTFY` (`Read-Host`, pas un secret) et remplace le placeholder `###TOPIC_NTFY_A_DEFINIR###` **dans** le config par édition ciblée (le reste du fichier préservé, UTF-8 sans BOM) ; (2) rappelle les réglages du token dédié à créer (repo unique, permissions, expiration alignée) avec une **pause** ; (3) **appelle** `mettre_a_jour_tokens_ccw.ps1` (pas de duplication) avec les paramètres déduits — dont `-NomLog ccw-<nom>-service.log` — pour la saisie masquée + pose des tokens + redémarrage + vérif des logs ; (4) résumé final selon le code renvoyé. |

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
`ccw.conf` suffit à ce qu'il ne prenne que les issues Windows. Le watcher
tourne comme **vrai service Windows** enregistré via NSSM (issue #148) —
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

---

*Dernière mise à jour : 19 juillet 2026 — §16 « Agent Windows CCW » : **onglet « CCW » dans l'interface web** (issue #174, sous-section §16.2) — pilotage complet de la VM et des projets CCW depuis Linux, sans PowerShell manuel dans la VM. Backend `app/ccw.py` (routes `/ccw/*`) exécutant les scripts existants à distance via `VBoxManage guestcontrol` : état/démarrage de la VM (`demarrer_ccw.sh`), liste des projets (nouveau `lister_projets_ccw.ps1`, sortie JSON encadrée), ajout (`ajouter_projet_ccw.ps1`) et finalisation non interactive (nouveau `finaliser_projet_ccw_auto.ps1` + `mettre_a_jour_tokens_ccw.ps1` doté d'un mode `-FichierTokens`). Sécurité : tokens jamais passés en argument ni journalisés (fichier temporaire `0600` poussé puis supprimé des deux côtés dans un `finally`) ; mot de passe `ccw-admin` lu depuis `CCW_ADMIN_PASSWORD` ou `configs/ccw_admin.secret` (gitignoré). Nouvel onglet + panneau dans `templates/index.html`, fonctions `ccw*` dans `static/js/app.js`, classe `.message.avertissement` dans `style.css`. Précédemment — §16 « Agent Windows CCW » : **finalisation d'un projet CCW en une seule commande** (issue #173, suite #170) — ajout de `provisioning/windows/finaliser_projet_ccw.ps1` qui, à partir du seul `-NomProjet`, dérive le service/dossier/config (même logique qu'`ajouter_projet_ccw.ps1`), vérifie leur existence, demande `TOPIC_NTFY` et l'écrit directement dans le config (remplacement ciblé du placeholder `###TOPIC_NTFY_A_DEFINIR###`, reste du fichier préservé en UTF-8 sans BOM), rappelle avec une pause la marche à suivre pour créer le token GitHub dédié, puis **appelle** `mettre_a_jour_tokens_ccw.ps1` (pas de duplication) pour la saisie masquée + pose des tokens + redémarrage + vérif des logs, et conclut par un résumé ; `mettre_a_jour_tokens_ccw.ps1` gagne un paramètre `-NomLog` pour vérifier le bon log de service (`ccw-<nom>-service.log`) ; les rappels d'`ajouter_projet_ccw.ps1` (en-tête + fin de script) et le §16 pointent désormais vers cette commande unique au lieu des 3 étapes dispersées. Non exécuté contre une VM réelle (test manuel par Alain). Précédemment — §11 « Conventions de code » : **règle BOM UTF-8 obligatoire pour tout script `.ps1`** (issue #172) — ajout du BOM (`EF BB BF`) manquant sur `ajouter_projet_ccw.ps1` (#170) et `mettre_a_jour_tokens_ccw.ps1` (#168), qui plantaient sinon sous Windows PowerShell 5.1 avec des `UnexpectedToken` en cascade sur les accents (même signature que #151) ; règle généralisée en §11 + rappel en tête du §16 pour prévenir la récidive (`provisionner.ps1` déjà OK depuis #151). Précédemment — §16 « Agent Windows CCW » : **généralisation multi-projets de CCW** (issue #170) — ajout de `provisioning/windows/ajouter_projet_ccw.ps1` (un clone + un config `configs\<nom>-ccw.conf` + un service NSSM `CCW-Watcher-<NomProjet>` dédiés par projet, sur le modèle des watchers CCL ; paramétrable `-NomProjet`/`-Depot`, idempotent, `watcher.py` inchangé) ; documentation du modèle « un service par projet » et de la **règle d'expiration alignée** des tokens (un token fine-grained dédié par dépôt, mais tous à la même échéance ≈ 17 octobre 2026) ; commande exacte d'instanciation de Scrabble et marche à suivre pour créer son token dédié (Repository access → Scrabble uniquement, Issues read/write + Metadata read-only). Précédemment — §16 « Agent Windows CCW » : ajout de la sous-section **§16.1 Maintenance périodique (renouvellement à 90 jours)** (issue #169) — runbook séquentiel consolidé pour la fenêtre de maintenance d'octobre 2026 : tableau de repères de dates (install **2026-07-19**, expiration Windows **2026-10-17**, token GitHub aligné ~90 j mais non stocké), puis procédure en 3 étapes renvoyant aux scripts existants — vérifier (`verifier_expiration_ccw.py`), recréer la VM (`creer_vm_ccw.py --recreate` + ré-attacher un ISO frais + `lancer_provisioning.py`), renouveler les tokens (`mettre_a_jour_tokens_ccw.ps1`) — sans dupliquer le détail technique déjà présent dans le §16. Précédemment — §16 « Agent Windows CCW » : ajout du script `provisioning/windows/mettre_a_jour_tokens_ccw.ps1` (issue #168) — renouvellement des tokens `GH_TOKEN`/`CLAUDE_CODE_OAUTH_TOKEN` du service `CCW-Watcher` sans reconstruire à la main la chaîne `AppEnvironmentExtra` : saisie masquée (`Read-Host -AsSecureString`), séparateur `` `n`` impératif entre les deux paires (un espace corrompt `GH_TOKEN` → « Bad credentials »), `nssm set`/`nssm restart`, puis affichage automatique des 10 dernières lignes de `logs\ccw-service.log` pour confirmer l'absence d'erreur d'auth. Précédemment — §16 « Agent Windows CCW » : alerte d'expiration de l'éval 90 jours (issue #167) — ajout de `provisioning/windows/eval-expiration.json` (date d'installation **2026-07-19**, expiration **2026-10-17**) et du script `provisioning/windows/verifier_expiration_ccw.py` (côté Linux : calcule les jours restants, alerte + code de sortie 2 à ≤ 10 j, sinon confirmation calme ; `python3 provisioning/windows/verifier_expiration_ccw.py`) ; rappel `cron` + `ntfy` hebdomadaire proposé mais laissé à l'activation d'Alain. Précédemment — §16 « Agent Windows CCW » : ajout du script `provisioning/windows/demarrer_ccw.sh` (issue #166), wrapper de démarrage de la VM `CCW-Build` depuis CCL (headless par défaut, `--gui`/`--fenetre` pour une fenêtre, `--status` pour l'état sans rien démarrer). Précédemment — §3 « Créer une issue » : ajout d'une note sur la **convention de présentation côté Claude Chat** pour l'envoi en lot (issue #153) — quand Claude Chat prépare plusieurs issues, il les présente toutes à la suite dans un seul bloc de code (pas un bloc par issue) pour un copier-coller en un clic. Précédemment — §16 « Agent Windows CCW » : `REP_TRAVAIL` généré par `provisionner.ps1` pointe désormais vers le **chemin UNC** `\\VBOXSVR\CCW_Share` (et non la lettre automontée `$LettrePartage`), seul accessible au service `CCW-Watcher` tournant sous LocalSystem (issue #149, suite #148) ; `$LettrePartage` conservé pour référence mais plus utilisé pour construire `REP_TRAVAIL`. Précédemment — le watcher CCW tourne comme **vrai service Windows** enregistré via NSSM (issue #148, suite #147) — `provisionner.ps1` installe `NSSM.NSSM` (winget) et enregistre le service `CCW-Watcher` (`SERVICE_AUTO_START` + `AppExit Default Restart` + `AppRestartDelay 5000`, stdout/stderr → `logs\ccw-service.log`, idempotent via `nssm stop`/`remove`), en remplacement de l'ancienne tâche planifiée `-AtLogOn` qui ne redémarrait pas au boot sans session ; équivalent direct des services systemd du §13. Précédemment — provisioning **phase 2** (issue #147, suite #146) — ajout de `provisioning/windows/provisionner.ps1` (installe l'outillage dans la VM via winget + Claude Code natif, clone le dépôt, écrit `ccw.conf`, enregistre la tâche planifiée `CCW-Watcher`) et `lancer_provisioning.py` (pousse/exécute ce script depuis CCL via `VBoxManage guestcontrol`) ; `watcher.py` inchangé (portable, `LABEL` paramétrable) ; limite Task Scheduler vs `Restart=always` documentée. Précédemment — ajout du §16 et du label `for-windows` (issue #146) : provisioning phase 1 de la VM Windows CCW (`provisioning/windows/creer_vm_ccw.py` + `autounattend.xml`) destinée aux builds .exe délégués par CCL. Précédemment — Bridge_Agent v1, 4 projets actifs. §3 « Créer une issue » : ajout de l'**envoi en lot** (issue #135) — coller plusieurs blocs `#Titre:` à la suite dans le même corps déclenche le mode lot (bouton « Envoyer le lot (N issues) »), chaque bloc étant envoyé en séquence comme une issue indépendante (avec ses `PROJET`/`TIMEOUT`/`MODELE` optionnels), sans validation intermédiaire, suivi d'un résumé listant le résultat de chacune. Ajout du projet `ecole` (AlainDelree/Ecole, ~/Ecole) aux tableaux §2 et §7 (issue #101). Section 15 « Chef + Specs MVC » : champ `SPECS` (pluriel, minuscules, combinable en une ligne) — correction du champ `SPEC` introduit par erreur (issue #97, suite #96).*
