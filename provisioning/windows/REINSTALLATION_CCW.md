# REINSTALLATION_CCW — réinstallation du PC fixe CCW

Procédure complète pour réinstaller de A à Z le PC fixe Windows dédié à
l'agent **CCW** (Windows 11 IoT Enterprise LTSC, évaluation 90 jours), sans
avoir à reconstruire la démarche de mémoire. Les scripts référencés vivent
tous dans ce même dossier (`provisioning/windows/`). Pour le contexte
général de l'agent CCW (rôle, architecture, onglet de pilotage), voir
`BRIDGE_AGENT_DOC.md` §16.

**Rappel important — clé SSH CCL→CCW.** La clé **privée** (`~/.ssh/ccl_ccw`
sur le ThinkPad, côté CCL) **reste en place** d'une réinstallation à
l'autre : elle n'a jamais besoin d'être régénérée ni retouchée. Seule sa
**clé publique** (`~/.ssh/ccl_ccw.pub`) doit être réinstallée sur le
Windows fraîchement réinstallé (étape 2 ci-dessous), puisque c'est
`authorized_keys` côté Windows qui est reconstruit à zéro par la
réinstallation, pas la paire de clés côté CCL.

## Procédure

### 1. Réinstallation Windows

Réinstaller Windows sur le PC fixe en utilisant la réponse d'installation
automatisée `autounattend.xml` de ce dossier (voir les commentaires en tête
du fichier pour les valeurs à adapter avant usage, notamment le mot de
passe administrateur).

### 2. Configurer l'accès SSH depuis CCL

Une fois Windows installé et une session ouverte, lancer **en admin** (PowerShell) :

```powershell
.\configurer_ssh_ccw.ps1 -ClePub "<contenu de ~/.ssh/ccl_ccw.pub>"
```

Ce script active/configure OpenSSH Server côté Windows et installe la clé
publique fournie dans `authorized_keys` de l'utilisateur SSH (`AlainW`),
pour permettre à CCL de piloter le PC fixe à distance par clé (sans mot de
passe) — voir `BRIDGE_AGENT_DOC.md` §16.2.

Le contenu à passer en `-ClePub` est celui de `~/.ssh/ccl_ccw.pub` **sur
le ThinkPad** (CCL) — la clé publique correspondant à la clé privée
`~/.ssh/ccl_ccw` mentionnée plus haut, qui elle ne bouge pas.

### 3. Vérifier la connexion SSH depuis CCL

Depuis le ThinkPad :

```bash
ssh -i ~/.ssh/ccl_ccw AlainW@<ip>
```

(`<ip>` = adresse IP locale du PC fixe.) La connexion doit s'établir sans
demande de mot de passe. En cas d'échec, revérifier l'étape 2 (OpenSSH
Server actif, clé bien copiée dans `authorized_keys`) avant de poursuivre.

### 4. Provisionner le logiciel

Toujours en admin sur le PC fixe (ou via la session SSH ouverte à l'étape
précédente) :

```powershell
.\provisionner.ps1
```

Installe Git, GitHub CLI, Python 3, PyInstaller (winget) et Claude Code
(installeur natif), clone `Bridge_Agent` en lecture seule dans
`C:\CCW\Bridge_Agent`, écrit `configs\ccw.conf` (avec un placeholder
`TOPIC_NTFY`) et enregistre le service Windows `CCW-Watcher` via NSSM.

### 5. Renseigner le topic ntfy et poser les tokens

Éditer `TOPIC_NTFY` dans `configs\ccw.conf` (remplacer le placeholder par
le topic réel), puis lancer :

```powershell
.\mettre_a_jour_tokens_ccw.ps1
```

Le script demande `GH_TOKEN` puis `CLAUDE_CODE_OAUTH_TOKEN` en saisie
masquée, les applique au service via `nssm set … AppEnvironmentExtra`, et
redémarre `CCW-Watcher`.

### 6. Vérifier que le service tourne

Confirmer que `CCW-Watcher` est bien à l'état `running`, soit localement
(`nssm status CCW-Watcher` ou services.msc sur le PC fixe), soit depuis
CCL via l'onglet **CCW** de l'interface web (`new_issue.py`) — voir
`BRIDGE_AGENT_DOC.md` §16.2.

### 7. Recréer les services multi-projets dédiés

Les étapes 1 à 6 ne remettent en place que le service de **base**
`CCW-Watcher` (canal `for-windows` de Bridge_Agent). En production tournent
en plus **4 services dédiés**, un par projet du modèle multi-projets actif
(issue #170, cf. `BRIDGE_AGENT_DOC.md` §16) — eux aussi recréés à zéro par
la réinstallation, puisque le service NSSM et ses tokens ne survivent pas :

| Projet | Dépôt GitHub |
|--------|--------------|
| `alchess` | `AlainDelree/AlChess` |
| `actualise` | `AlainDelree/Actualise` |
| `rummikub` | `AlainDelree/Rummikub` |
| `scrabble` | `AlainDelree/Scrabble` |

Rappel : les fichiers `.conf` de chaque projet (ex. `configs\alchess-ccw.conf`)
vivent dans le dépôt du projet lui-même, donc **survivent** à la
réinstallation — rien à reconstruire de ce côté. Seuls la recréation du
service NSSM et la resaisie des deux tokens (GitHub dédié + Claude Code)
par projet restent nécessaires.

Cette liste est maintenue à un seul endroit : le tableau `$Projets` dans
`reinstaller_projets_ccw.ps1` (ce dossier) fait foi en cas de divergence —
le tableau ci-dessus n'en est qu'une reproduction pour la lecture. Toujours
en admin sur le PC fixe, depuis `C:\CCW\Bridge_Agent` :

```powershell
.\provisioning\windows\reinstaller_projets_ccw.ps1
```

Ce script séquence l'appel à `creer_projet_ccw_complet.ps1` (racine du
dépôt, §16.5 de `BRIDGE_AGENT_DOC.md`) pour chacun des 4 projets — évitant
de devoir taper 4 commandes séparées de mémoire. Les deux tokens restent
demandés **par projet**, à l'intérieur de la boucle : le script structure
la séquence, il ne contourne pas la saisie. En cas d'échec sur un projet,
il s'arrête et affiche comment reprendre uniquement les projets restants
(`-SeulementProjets`).

Vérifier ensuite l'état des 5 services (base + 4 dédiés) via
`provisioning\windows\lister_projets_ccw.ps1`, ou depuis CCL via l'onglet
**CCW** de l'interface web.

---

## Prérequis côté Linux (ThinkPad) — `cifs-utils`

Sans rapport direct avec la réinstallation Windows, mais lié à
l'infrastructure CCW et à garder en mémoire au même endroit : le montage du
partage réseau avec l'option `credentials=` (utilisé pour accéder au PC fixe
CCW depuis le ThinkPad) nécessite le paquet **`cifs-utils`** côté Linux.
Sans lui, le montage échoue silencieusement ou avec une erreur peu explicite
sur `credentials=`. À installer une fois sur le ThinkPad si absent :

```bash
sudo apt install cifs-utils
```
