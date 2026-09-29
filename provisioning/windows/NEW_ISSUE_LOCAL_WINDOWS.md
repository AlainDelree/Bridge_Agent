# NEW_ISSUE_LOCAL_WINDOWS — lancer new_issue.py nativement sur Windows

Issue #690 (plan hybride Windows), suite de la première exécution native de
`new_issue.py` sur le PC fixe Windows (CCW) le 28/09/2026, faite entièrement
à la main lors de la validation de l'issue D.

Ce document couvre l'usage **interactif** de l'interface web
(`new_issue.py --lan`) directement sur une machine Windows — un usage
**distinct** du service `CCW-Watcher` (headless, provisionné par
`provisionner.ps1`) : les deux peuvent coexister sur le même PC.

## 1. Provisioning (script)

`provisionner_new_issue_local.ps1` (même dossier) installe les dépendances
Python (`requirements.txt`) et ouvre le port de pare-feu nécessaire — voir
son en-tête pour le détail. Prérequis : Python et GitHub CLI (`gh`) déjà
installés (cf. `provisionner.ps1` sinon).

```powershell
.\provisionner_new_issue_local.ps1
```

Puis, si le script signale que `gh` n'est pas authentifié pour la session
courante (étape volontairement non automatisée — nécessite une interaction
humaine) :

```powershell
gh auth login
```

## 2. Alias PowerShell `bridge` (non automatisé)

Pour lancer `new_issue.py --lan` d'une seule commande (`bridge`) sans avoir
à se souvenir du chemin ni de l'option, ajouter une fonction au profil
PowerShell personnel de l'utilisateur (`$PROFILE`). Cette étape n'est
**pas** automatisée par le script de provisioning : c'est une modification
du profil personnel de l'utilisateur, pas de l'état de la machine — mais
la commande ci-dessous est prête à copier-coller tel quel.

Ouvrir (ou créer) le profil courant :

```powershell
notepad $PROFILE
```

Ajouter la fonction suivante (adapter `C:\CCW\Bridge_Agent` si le dépôt est
cloné ailleurs — cf. `$RepDepot` dans `provisionner.ps1`) :

```powershell
function bridge {
    Push-Location C:\CCW\Bridge_Agent
    try { python new_issue.py --lan }
    finally { Pop-Location }
}
```

Enregistrer, fermer Notepad, puis recharger le profil dans la session
PowerShell courante (ou simplement en ouvrir une nouvelle) :

```powershell
. $PROFILE
```

La commande `bridge` lance alors `new_issue.py --lan` depuis n'importe quel
répertoire.

## Voir aussi

- `provisionner.ps1` — provisioning du service `CCW-Watcher` (headless,
  Git/gh/Python/NSSM/Claude Code).
- `REINSTALLATION_CCW.md` — provisioning complet après réinstallation
  Windows (suit `REINSTALLATION_WINDOWS.md`).
- `BRIDGE_AGENT_DOC.md`, section mode `--lan` (issue #461) — description
  du mode réseau local de `new_issue.py`.
