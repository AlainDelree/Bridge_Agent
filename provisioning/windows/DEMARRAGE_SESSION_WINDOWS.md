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

Les watchers de projet et le watcher `issues_inbox` attendent
`-DelaiDemarrageWatchersSec` (20 s par défaut, réglable) avant leur tout
premier lancement — **pas** l'interface web, qui démarre sans attendre
puisque c'est elle qui fait la mise à jour automatique du dépôt (`git
pull`) à son lancement (voir §2 bis). Ce délai ne s'applique **qu'au tout
premier lancement**, jamais aux redémarrages après plantage (déjà
espacés par le délai de redémarrage du superviseur, 10 s).

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

## 2 bis. Délai de démarrage des watchers (issue #871)

À l'ouverture de session, les trois tâches (watchers de projet,
`issues_inbox`, interface web) se déclenchent **en même temps**. Or
l'interface web tente, à chaque lancement, un `git pull --ff-only` du
dépôt (quelques secondes maximum, voir `NEW_ISSUE_LOCAL_WINDOWS.md`) —
sans précaution, un watcher démarré exactement en même temps pouvait
charger l'**ancien** code du dépôt avant la fin de cette mise à jour.

`-DelaiDemarrageWatchersSec` (20 s par défaut) fait attendre les watchers
(projets + `issues_inbox`) ce nombre de secondes avant leur tout premier
lancement, pour laisser l'interface web terminer sa mise à jour en
premier. L'interface web elle-même n'attend jamais (0 s, non réglable :
c'est elle que les autres attendent).

Ce délai est posé dans `surveiller_processus_session.ps1`
(`-DelaiDemarrageSec`, un simple `Start-Sleep` avant le tout premier
lancement), **pas** comme propriété « Delay » du déclencheur de la tâche
planifiée (`New-ScheduledTaskTrigger -AtLogOn`) : cette dernière option
existe bien sous Windows, mais ne s'appliquerait qu'aux déclenchements
futurs **par la session** — pas au `Start-ScheduledTask` que ce script
exécute lui-même, immédiatement, juste après avoir enregistré chaque
tâche (pour démarrer sans attendre la prochaine ouverture de session).
Un délai posé côté déclencheur serait donc incohérent entre une
installation/mise à jour (démarrage immédiat, sans délai) et une
reconnexion ultérieure (délai respecté) — poser le délai dans le
superviseur lui-même l'applique uniformément dans les deux cas, et
fonctionne aussi bien en `-ModeService` (NSSM relance ce même
superviseur).

Augmenter cette valeur sur une machine lente où le `git pull`
automatique dépasserait 20 s ; la mettre à `0` retrouve le comportement
démarrage simultané d'avant #871.

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

**Écriture en continu (issue #871)** : la sortie standard/erreur du
process surveillé est recopiée dans ce journal toutes les ~2 secondes
**pendant qu'il tourne encore**, pas seulement à son arrêt — avant #871,
elle n'était recopiée qu'à la fin (process arrêté), donc invisible
pendant tout le fonctionnement, et perdue en cas d'arrêt brutal de la
session (le fichier temporaire intermédiaire restait alors dans `%TEMP%`,
jamais recopié). Au pire, un arrêt brutal exactement entre deux copies
peut encore manquer quelques secondes de sortie — contre la totalité
depuis le dernier démarrage, auparavant. `$env:PYTHONUNBUFFERED=1` est
posé avant chaque lancement pour que Python (watcher.py, `new_issue.py`,
`watcher_issues_inbox.py`) n'ajoute pas son **propre** tampon interne
par-dessus : sans ce réglage, Python retient sa sortie en mémoire par
blocs dès qu'elle n'est pas un terminal (donc dans toute redirection vers
un fichier), et la copie périodique ci-dessus ne verrait rien de neuf
tant que ce tampon ne se vide pas de lui-même.

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
10. **(issue #871)** Pendant que `watcher-scrabble.log` tourne, ouvrir
    `logs\watcher-scrabble-session.log` dans un éditeur qui suit les
    ajouts (ex. `Get-Content -Wait`) : du texte apparaît par petits
    paquets au fil du fonctionnement, pas seulement à l'arrêt. Couper le
    courant/tuer la session en plein milieu d'une activité du watcher :
    au plus quelques secondes de sortie manquent à la reprise, jamais la
    totalité depuis le dernier démarrage.
11. **(issue #871)** Avec `-DelaiDemarrageWatchersSec` laissé à sa valeur
    par défaut (20 s), ouvrir une session : `logs\new_issue-session.log`
    affiche son `[DEMARRAGE]` immédiatement, alors que
    `logs\watcher-scrabble-session.log` affiche le sien ~20 s plus tard
    (ligne `[ATTENTE] démarrage différé de 20 s…` visible juste avant).
    Avec `-DelaiDemarrageWatchersSec 0`, vérifier que les deux démarrent
    au même instant (comportement d'avant #871).

## Voir aussi

- `provisioning/windows/provisionner.ps1` — provisioning du rôle CCW
  (machine Windows déléguée, hors périmètre de ce document).
- `provisioning/windows/ajouter_projet_ccw.ps1` — pattern NSSM/compte
  utilisateur repris ici pour `-ModeService`.
- `provisioning/windows/provisionner_new_issue_local.ps1` —
  dépendances/pare-feu de `new_issue.py`, prérequis de ce script.
- `installer_services.sh` + `systemd/watcher@.service` (racine du dépôt) —
  équivalent Linux.
