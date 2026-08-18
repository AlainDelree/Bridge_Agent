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

---

> **Note.** `configurer_ssh_ccw.ps1` est référencé par cette procédure mais
> n'existe pas encore dans ce dossier au moment de la rédaction — à créer
> séparément avant de pouvoir dérouler l'étape 2 telle quelle.
