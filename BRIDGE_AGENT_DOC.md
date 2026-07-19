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

**Envoi en lot (plusieurs issues d'un seul copier-coller) — issue #135 :**
coller *plusieurs* blocs `#Titre:` à la suite dans le même corps déclenche
automatiquement le **mode lot** : le bouton d'envoi devient
« Envoyer le lot (N issues) ». Chaque bloc va de son `#Titre:` jusqu'au
`#Titre:` suivant et est traité comme une issue indépendante, avec ses propres
champs d'en-tête optionnels (`PROJET`, `TIMEOUT`, `MODELE`) — à défaut, les
valeurs du formulaire (projet sélectionné, timeout, modèle) s'appliquent en
repli. Le `MODE` (lecture/écriture) et les notifications sont communs à tout le
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

La VM cible **Windows 11 IoT Enterprise LTSC 2024** en évaluation 90 jours,
d'où la recréation facile prévue.

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

---

*Dernière mise à jour : 19 juillet 2026 — §3 « Créer une issue » : ajout d'une note sur la **convention de présentation côté Claude Chat** pour l'envoi en lot (issue #153) — quand Claude Chat prépare plusieurs issues, il les présente toutes à la suite dans un seul bloc de code (pas un bloc par issue) pour un copier-coller en un clic. Précédemment — §16 « Agent Windows CCW » : `REP_TRAVAIL` généré par `provisionner.ps1` pointe désormais vers le **chemin UNC** `\\VBOXSVR\CCW_Share` (et non la lettre automontée `$LettrePartage`), seul accessible au service `CCW-Watcher` tournant sous LocalSystem (issue #149, suite #148) ; `$LettrePartage` conservé pour référence mais plus utilisé pour construire `REP_TRAVAIL`. Précédemment — le watcher CCW tourne comme **vrai service Windows** enregistré via NSSM (issue #148, suite #147) — `provisionner.ps1` installe `NSSM.NSSM` (winget) et enregistre le service `CCW-Watcher` (`SERVICE_AUTO_START` + `AppExit Default Restart` + `AppRestartDelay 5000`, stdout/stderr → `logs\ccw-service.log`, idempotent via `nssm stop`/`remove`), en remplacement de l'ancienne tâche planifiée `-AtLogOn` qui ne redémarrait pas au boot sans session ; équivalent direct des services systemd du §13. Précédemment — provisioning **phase 2** (issue #147, suite #146) — ajout de `provisioning/windows/provisionner.ps1` (installe l'outillage dans la VM via winget + Claude Code natif, clone le dépôt, écrit `ccw.conf`, enregistre la tâche planifiée `CCW-Watcher`) et `lancer_provisioning.py` (pousse/exécute ce script depuis CCL via `VBoxManage guestcontrol`) ; `watcher.py` inchangé (portable, `LABEL` paramétrable) ; limite Task Scheduler vs `Restart=always` documentée. Précédemment — ajout du §16 et du label `for-windows` (issue #146) : provisioning phase 1 de la VM Windows CCW (`provisioning/windows/creer_vm_ccw.py` + `autounattend.xml`) destinée aux builds .exe délégués par CCL. Précédemment — Bridge_Agent v1, 4 projets actifs. §3 « Créer une issue » : ajout de l'**envoi en lot** (issue #135) — coller plusieurs blocs `#Titre:` à la suite dans le même corps déclenche le mode lot (bouton « Envoyer le lot (N issues) »), chaque bloc étant envoyé en séquence comme une issue indépendante (avec ses `PROJET`/`TIMEOUT`/`MODELE` optionnels), sans validation intermédiaire, suivi d'un résumé listant le résultat de chacune. Ajout du projet `ecole` (AlainDelree/Ecole, ~/Ecole) aux tableaux §2 et §7 (issue #101). Section 15 « Chef + Specs MVC » : champ `SPECS` (pluriel, minuscules, combinable en une ligne) — correction du champ `SPEC` introduit par erreur (issue #97, suite #96).*
