# DEMARRAGE_SESSION_WINDOWS — watchers locaux au démarrage, PC Windows seul

Issue #864, suite de l'audit de parité #862. Couvre `installer_demarrage_
session.ps1` et son superviseur `surveiller_processus_session.ps1` (même
dossier) — **sans rapport** avec le rôle CCW (`provisionner.ps1`,
`ajouter_projet_ccw.ps1`) : ces deux derniers servent un PC Windows
**délégué** depuis une machine Linux (bootstrap par issues chiffrées, label
`for-windows`). Ce document-ci couvre l'usage inverse : **un seul agent**
Claude Code tournant sur **son propre** PC Windows, avec ses projets locaux.

## 1. Ce que ça installe

Pour chaque élément demandé, un démarrage automatique à l'ouverture de
session de l'utilisateur, avec redémarrage automatique en cas de plantage :

- un watcher par projet local passé à `-Projets` (ex. `-Projets
  scrabble,rummikub`) — équivalent Windows, projet par projet, de
  `systemd/watcher@.service` côté Linux (`python watcher.py --config
  configs\<nom>.conf`) ;
- le watcher du dépôt d'issues par fichiers (`scripts\watcher_issues_
  inbox.py`), sauf `-SansIssuesInbox` ;
- l'interface web (`new_issue.py`), équivalent fonctionnel de `lancer_
  new_issue.sh` (horodatage démarrage/arrêt/code de sortie dans un journal
  dédié), sauf `-SansInterfaceWeb`.

Chaque `configs\<nom>.conf` des projets listés doit **déjà exister** — ce
script ne crée **jamais** de fichier `.conf` (règle générale du dépôt,
BRIDGE_AGENT_DOC.md §11).

## 2. Pourquoi une tâche de session, pas un service, par défaut

Un service Windows tourne en session 0, hors de la session graphique de
l'utilisateur : ni bulle de notification, ni son n'en sortent, et le
trousseau Windows (où Claude Code et l'agent Vibe rangent leur connexion)
n'est accessible que depuis la session de son propriétaire — un service
sous un autre compte (ou `LocalSystem`) ne le voit pas (constat réel, issue
#860). Pour un PC **personnel**, où l'utilisateur ouvre sa session tous les
jours, démarrer **dans** cette session est donc préférable : bulle et son
fonctionnent normalement, et surtout **aucun mot de passe n'est à
stocker** — la tâche planifiée s'appuie sur la session déjà ouverte
(`LogonType Interactive`), jamais sur un identifiant enregistré. Elle ne
demande pas non plus les droits administrateur.

Contrepartie acceptée : rien ne démarre tant que personne n'a ouvert de
session (cas jugé marginal sur un PC personnel).

`-ModeService` (option secondaire, voir §5) existe pour qui veut malgré
tout un vrai service NSSM (démarrage sans ouverture de session), au prix
d'un mot de passe et de la perte de la bulle/du son.

## 3. Utilisation

Depuis une console PowerShell (pas besoin d'administrateur en mode par
défaut), dans `provisioning\windows\` du dépôt :

```powershell
# Deux projets + issues_inbox + interface web (défaut) :
.\installer_demarrage_session.ps1 -Projets scrabble,rummikub

# Sans argument : demande interactivement la liste des projets.
.\installer_demarrage_session.ps1

# Aucun projet local, seulement issues_inbox + interface web :
.\installer_demarrage_session.ps1 -Projets @()

# Sans l'interface web (déjà lancée autrement) :
.\installer_demarrage_session.ps1 -Projets scrabble -SansInterfaceWeb

# Aperçu sans rien enregistrer :
.\installer_demarrage_session.ps1 -Projets scrabble -DryRun
```

**Idempotent** : relancer le script avec la même liste ne crée aucun
doublon (les tâches existantes sont mises à jour, pas recréées) ; un projet
retiré de `-Projets` depuis la dernière exécution voit sa tâche
désinstallée automatiquement (de même pour `-SansIssuesInbox` /
`-SansInterfaceWeb` nouvellement passés).

## 4. Désinstaller

```powershell
.\installer_demarrage_session.ps1 -Desinstaller
```

Retire **tout** ce que ce script a pu enregistrer (tâches planifiées et,
le cas échéant, services NSSM d'un `-ModeService` antérieur) — recherche
par préfixe de nom (`BridgeAgent-Session-*`), pas besoin de redonner
`-Projets`. Les fichiers `configs\*.conf` et les journaux (`logs\`) sont
conservés.

## 5. Option secondaire : mode service (NSSM)

```powershell
# Console ADMINISTRATEUR requise :
.\installer_demarrage_session.ps1 -Projets scrabble -ModeService
```

Enregistre de vrais services Windows (NSSM) au lieu de tâches planifiées —
démarre même sans ouverture de session, mais :

- **bulle de notification et son ne fonctionnent pas** (service en session
  0, sans bureau interactif) ;
- demande le mot de passe du compte (saisie masquée, jamais stocké en
  clair ni journalisé) ;
- nécessite une console PowerShell administrateur.

À réserver à qui a un besoin explicite de démarrage sans ouverture de
session (ex. machine qui redémarre seule la nuit) — sur un PC personnel où
l'on ouvre sa session normalement, le mode par défaut (§2) reste préférable.

## 6. Journaux

Dans `logs\` (dossier de logs du dépôt), par composant :

| Composant | Journal applicatif | Journal du superviseur |
|---|---|---|
| watcher de projet `<nom>` | `watcher-<nom>.log` (watcher.py, RotatingFileHandler) | `watcher-<nom>-session.log` |
| issues_inbox | `issues_inbox.log` (curé par l'app) | `watcher_issues_inbox-session.log` |
| interface web | (aucun — new_issue.py n'a pas de journal fichier propre) | `new_issue-session.log` |

Le journal du superviseur capture tout ce qui échappe au journal
applicatif (ex. une erreur avant même que le logger de l'application ne
soit configuré), ainsi que chaque démarrage/arrêt/code de sortie horodaté —
pour `issues_inbox` et l'interface web, qui n'écrivent eux-mêmes que sur
la sortie standard, ce journal devient leur **seule** trace persistante.

## 7. Prérequis (non couverts par ce script)

- Python (avec pip) installé et sur le PATH — `provisionner.ps1` (fonction
  `Installer-Python`) ou toute installation standard de python.org ;
- dépendances de `requirements.txt` installées (flask/werkzeug) pour
  l'interface web — voir `provisionner_new_issue_local.ps1`, étape 1 ;
- `gh` (GitHub CLI) authentifié pour ce compte Windows, en session
  interactive — voir `provisionner_new_issue_local.ps1`, étape 3 ;
- pour `-ModeService` uniquement : `nssm` sur le PATH (`provisionner.ps1`,
  fonction `Installer-Nssm`).

## 8. Points à vérifier à la main (Windows requis — non exécutable sous Linux)

Ce script a été écrit et relu sous Linux, où il ne peut pas être exécuté
(pas de PowerShell). À vérifier sur un PC Windows réel :

1. `-Projets scrabble` (un projet réel déjà configuré) sans `-ModeService`
   : la tâche `BridgeAgent-Session-Watcher-scrabble` apparaît dans le
   Planificateur de tâches, démarre immédiatement, et un `logs\watcher-
   scrabble.pid` + `logs\watcher-scrabble.log` apparaissent.
2. Fermer puis rouvrir la session : les trois tâches (projet + issues_inbox
   + interface web) redémarrent automatiquement.
3. Tuer le process `python.exe` du watcher à la main (Gestionnaire des
   tâches) : vérifier dans `logs\watcher-scrabble-session.log` qu'il
   redémarre après ~10 s.
4. Arrêter le watcher proprement (bouton de l'interface, ou laisser
   l'auto-extinction par inactivité se déclencher — code 42) : vérifier
   qu'il n'est **pas** redémarré par le superviseur (ligne `[FIN] arrêt
   propre`).
5. Relancer `installer_demarrage_session.ps1` avec un `-Projets` réduit
   (un projet retiré) : vérifier que sa tâche disparaît du Planificateur.
6. `http://127.0.0.1:5100` répond bien à l'interface web après ouverture de
   session, sans fenêtre de navigateur qui s'ouvre toute seule
   (`--no-browser` par défaut).
7. `-Desinstaller` : vérifier que toutes les tâches `BridgeAgent-Session-*`
   disparaissent et que les process associés sont bien arrêtés (Gestionnaire
   des tâches).
8. `-ModeService` (console administrateur) : vérifier que le service
   apparaît dans `services.msc`, démarre, et que `-Desinstaller` le retire
   aussi proprement que les tâches planifiées.
9. Bulle de notification et bip sonore (watcher.py) : fonctionnent en mode
   tâche de session (§2) ; vérifier qu'ils restent muets en `-ModeService`
   (comportement attendu, documenté dans l'aide du script).

## Voir aussi

- `provisioning/windows/provisionner.ps1` — provisioning du rôle CCW
  (machine Windows déléguée, hors périmètre de ce document).
- `provisioning/windows/ajouter_projet_ccw.ps1` — pattern NSSM/compte
  utilisateur repris ici pour `-ModeService`.
- `provisioning/windows/provisionner_new_issue_local.ps1` —
  dépendances/pare-feu de `new_issue.py`, prérequis de ce script.
- `installer_services.sh` + `systemd/watcher@.service` (racine du dépôt) —
  équivalent Linux.
