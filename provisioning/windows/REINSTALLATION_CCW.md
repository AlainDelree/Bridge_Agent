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
`C:\CCW\Bridge_Agent`, génère la paire de clés de bootstrap « Projet CCW »
(voir étape 8 ci-dessous), écrit `configs\ccw.conf` (avec un placeholder
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
en plus des **services dédiés**, un par projet du modèle multi-projets actif
(issue #170, cf. `BRIDGE_AGENT_DOC.md` §16) — eux aussi recréés à zéro par
la réinstallation, puisque le service NSSM et ses tokens ne survivent pas.

Rappel : les fichiers `.conf` de chaque projet (ex. `configs\alchess-ccw.conf`)
vivent dans le dépôt du projet lui-même, donc **survivent** à la
réinstallation — rien à reconstruire de ce côté. Seuls la recréation du
service NSSM et la resaisie des deux tokens (GitHub dédié + Claude Code)
par projet restent nécessaires.

**Liste non codée en dur (issue #597, suite de #552/#571)** : contrairement
à l'ancienne version de ce script, `reinstaller_projets_ccw.ps1` (ce
dossier) ne maintient plus de tableau `$Projets` figé. Il énumère
DYNAMIQUEMENT, à chaque exécution, les fichiers `configs\*-ccw.conf`
présents sur le disque (`C:\CCW\Bridge_Agent\configs\`) — un fichier par
projet dédié, créé par `ajouter_projet_ccw.ps1` à la création du projet et
jamais retiré automatiquement à sa suppression. Chaque fichier fournit à la
fois le nom du projet (préfixe avant `-ccw.conf`) et son dépôt GitHub (clé
`DEPOT=`). Le canal unifié `for-windows` (`configs\ccw.conf`, sans suffixe
projet) est explicitement exclu de cette énumération — il est déjà couvert
par les étapes 1 à 6 ci-dessus, pas par ce script.

Conséquence pratique : la liste des services dédiés recréés par l'étape 7
reflète toujours fidèlement les fichiers `configs\*-ccw.conf` réellement
présents au moment de la réinstallation — plus de risque de recréer un
projet décommissionné (fichier `.conf` absent → non recréé) ni d'oublier un
projet ajouté hors du flux CREATION standard (fichier `.conf` présent →
recréé). Ce mécanisme remplace le tableau `$Projets` qui faisait foi
jusqu'ici (issue #552) et rend caduque la distinction documentée en #571
avec `regenerer_tableaux_projets.py` (celui-ci régénère §2/§7 de
`BRIDGE_AGENT_DOC.md` depuis les `.conf`, mais dans un sous-ensemble
manuellement choisi — ici, la source de vérité est directement le disque).

Toujours en admin sur le PC fixe, depuis `C:\CCW\Bridge_Agent` :

```powershell
.\provisioning\windows\reinstaller_projets_ccw.ps1
```

Ce script séquence l'appel à `creer_projet_ccw_complet.ps1` (racine du
dépôt, §16.5 de `BRIDGE_AGENT_DOC.md`) pour chacun des projets détectés —
évitant de devoir taper une commande par projet de mémoire. Les deux tokens
restent demandés **par projet**, à l'intérieur de la boucle : le script
structure la séquence, il ne contourne pas la saisie. En cas d'échec sur un
projet, il s'arrête et affiche comment reprendre uniquement les projets
restants (`-SeulementProjets`).

Vérifier ensuite l'état de tous les services (base + dédiés) via
`provisioning\windows\lister_projets_ccw.ps1`, ou depuis CCL via l'onglet
**CCW** de l'interface web.

### 8. Paire de clés de bootstrap « Projet CCW » (issue #554, 1/3)

`provisionner.ps1` (étape 4 ci-dessus) génère automatiquement, la première
fois, une paire de clés **RSA 3072 bits** destinée au futur chiffrement des
tokens (`GH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`) transmis par la case
« Projet CCW » du formulaire de création de projet (conception #554,
mécanisme complet à suivre en #555/#556 — **pas encore implémenté à ce
stade** : cette étape ne fait que poser la paire de clés elle-même).

- **Clé privée** : `C:\CCW\cles_bootstrap\bootstrap_privee.pem` — ne quitte
  **jamais** le PC fixe. Permissions restreintes par `icacls` (SYSTEM +
  Administrateurs + le compte de service `AlainW` en lecture seule),
  héritage coupé. Ce dossier est volontairement **hors** du clone git
  `C:\CCW\Bridge_Agent` (jamais committé) et hors de `C:\CCW_Share` (point
  de montage réseau accédé depuis CCL, cf. `BRIDGE_AGENT_DOC.md` §16.3 —
  la clé privée n'a rien à y faire).
- **Clé publique** : `C:\CCW\cles_bootstrap\bootstrap_publique.pem` — pas
  sensible, à récupérer côté CCL pour chiffrer les tokens avant inclusion
  dans le corps d'une future issue. Trois façons de la récupérer :
  - **automatique (recommandé, issue #559)** : bouton « 🔄 Rafraîchir la clé
    publique » dans le bloc d'instructions de la case « Projet CCW » du
    formulaire de création de projet (`POST /projet-ccw/rafraichir-cle`,
    `app/projet_ccw.py`) — met à jour le cache local
    `configs/ccw_bootstrap_publique.pem` via la session SSH existante. À
    relancer après CETTE étape de réinstallation (nouvelle paire de clés) ;
  - **copier-coller manuel** : `provisionner.ps1` affiche son contenu PEM
    intégral en toute fin d'exécution ;
  - **via la session SSH existante** (étape 3 ci-dessus, voir aussi
    `BRIDGE_AGENT_DOC.md` §16.2) :
    ```bash
    ssh -i ~/.ssh/ccl_ccw AlainW@<ip> type C:\CCW\cles_bootstrap\bootstrap_publique.pem
    ```

Génération via `openssl.exe` (déjà présent : embarqué par Git pour Windows,
sous-dossier `usr\bin`) plutôt que `.NET` natif ou `age` — voir le
commentaire détaillé en tête de la section correspondante dans
`provisionner.ps1` pour la justification complète du choix.

> ⚠️ **La clé privée ne survit PAS à une réinstallation.** Comme le reste de
> l'état local du PC fixe, `C:\CCW\cles_bootstrap\` disparaît avec le disque
> effacé à l'étape 1 (réinstallation Windows) ; la paire de clés régénérée
> par l'étape 4 suivante n'a **aucun rapport** avec l'ancienne. Conséquence
> pratique à ne
> pas oublier (cas déjà identifié dans la conception #554) : **toute issue
> de bootstrap chiffrée avec l'ancienne clé publique, encore en attente de
> traitement au moment d'une réinstallation, devient définitivement
> indéchiffrable** — il faudra la ré-émettre depuis le formulaire une fois
> la nouvelle clé publique récupérée côté CCL. Ne pas soumettre une case
> « Projet CCW » juste avant une réinstallation planifiée du PC fixe.

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
