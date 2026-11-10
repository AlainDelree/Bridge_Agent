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

Chaque tâche/service est nommé `BridgeAgent-Session-<compte>-<Id>` (ex.
`BridgeAgent-Session-alain-IssuesInbox`) — le compte Windows qui lance le
script (`-CompteService`) fait partie du nom depuis l'issue #877, voir §4
bis pour le pourquoi et la transition depuis l'ancien nommage.

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

Retire **tout** ce que ce script a pu enregistrer **pour le compte
`-CompteService`** (tâches planifiées et, le cas échéant, services NSSM
d'un `-ModeService` antérieur), sous ses **deux** formes de nom (nouveau
nommage par compte, et ancien nommage pré-#877 si — et seulement si — il
appartient réellement à ce même compte, voir §4 bis) — recherche par
préfixe de nom (`BridgeAgent-Session-*`) puis par propriétaire réel pour
départager les comptes, pas besoin de redonner `-Projets`. Une tâche/un
service du même préfixe appartenant à un **autre** compte Windows n'est
jamais retiré. Les fichiers `configs\*.conf` et les journaux (`logs\`)
sont conservés.

## 4 bis. Nommage par compte Windows (issue #877)

Un nom de tâche planifiée (ou de service) est unique pour **toute la
machine**, pas par utilisateur Windows. Avant l'issue #877, les trois
tâches de ce script s'appelaient toujours `BridgeAgent-Session-
InterfaceWeb`, `BridgeAgent-Session-IssuesInbox` et `BridgeAgent-Session-
Watcher-<projet>` — sur un PC partagé par deux comptes (ou plusieurs essais
d'installation du même ami d'Alain), le second compte à s'enregistrer
échouait avec `Register-ScheduledTask : Access is denied` (`HRESULT
0x80070005`) sur la tâche déjà créée par le premier, et l'installeur
s'arrêtait net sans toucher aux autres composants demandés. Une fenêtre
PowerShell non élevée ne voyant pas non plus les tâches des autres
comptes, le diagnostic était difficile sur le moment.

Chaque nom inclut donc désormais le compte `-CompteService` :
`BridgeAgent-Session-<compte>-<Id>` (ex. `BridgeAgent-Session-alain-
IssuesInbox`, `BridgeAgent-Session-alain-Watcher-scrabble`) — le préfixe
`BridgeAgent-Session-` seul reste stable pour les commandes de ce document
qui filtrent sur lui. Deux comptes sur le même PC obtiennent donc chacun
leurs propres tâches, sans collision.

**Transition** : un compte qui avait déjà des tâches à l'ancien nom (sans
compte dans le nom) les voit détectées au prochain lancement du script —
mais **uniquement si elles lui appartiennent réellement** (vérifié par le
propriétaire réel de la tâche/du service, jamais supposé depuis le nom
seul, qui est partagé pour toute la machine) — puis remplacées
automatiquement par le nouveau nom, avec un message explicite
(« Transition de nommage (issue #877) : ancienne tâche/service « … »
détectée — remplacement par « … » »). Une ancienne tâche appartenant à un
**autre** compte n'est, elle, jamais touchée (ni listée, ni supprimée).

**Échec d'enregistrement** : si l'enregistrement d'un composant échoue par
refus d'accès (le cas ci-dessus, ou tout autre `Access is denied`), le
script affiche la cause probable et la marche à suivre (vérifier le
propriétaire réel de la tâche en console administrateur, relancer en
administrateur si elle appartient bien à ce compte, ou laisser la tâche de
l'autre compte intacte) au lieu de l'erreur système brute — puis **continue
avec les autres composants** demandés plutôt que de s'arrêter net. Le
résumé final liste alors explicitement les composants qui n'ont PAS pu
être enregistrés (« INSTALLATION PARTIELLE »), pour ne jamais laisser
croire à une installation complète qui ne l'était pas.

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

**Encodage UTF-8 (issue #875)** : `$env:PYTHONUTF8=1` et `$env:PYTHONIO
ENCODING=utf-8` sont posés aux côtés de `PYTHONUNBUFFERED` ci-dessus. Sans
eux, la sortie Python redirigée retombe sur l'encodage de la console
Windows (cp1252) : un caractère absent de cp1252 (ex. la flèche « → » du
message de mise à jour automatique du dépôt de `new_issue.py`, §3 de
`GUIDE_INSTALLATION_WINDOWS_SEUL.md`) levait une `UnicodeEncodeError` qui
arrêtait le programme en plein affichage — le superviseur le relançait
alors ~10 s plus tard, et le message de réussite (y compris dans le
bandeau de l'interface) était perdu. Les caractères accentués que cp1252
sait écrire (é, è…) n'arrêtaient rien mais produisaient des octets cp1252
mal relus comme de l'UTF-8 par le superviseur (absence de marqueur BOM =
UTF-8 par défaut pour `System.IO.StreamReader`) : « Mise à jour » devenait
« Mise ? jour ». En second rempart, indépendant de ces deux variables,
`new_issue.py`, `watcher.py` et `watcher_issues_inbox.py` reconfigurent
eux-mêmes leur sortie en UTF-8 dès leur démarrage (`watcher.forcer_utf8`,
issue #698) avec `errors="replace"` : un caractère malgré tout non
encodable ne fait donc plus jamais planter ces programmes. Le journal du
superviseur lui-même (`Ecrire-Journal`/`Purger-SortieVersJournal`) reste
écrit avec `Add-Content -Encoding UTF8` — **avec** marqueur BOM : c'est le
seul choix Unicode disponible pour `-Encoding` sous PowerShell 5.1 (la
valeur `UTF8NoBOM`, elle, n'existe que depuis PowerShell 6/7 — même
contrainte que la règle « tout `.ps1` accentué garde son BOM » de
BRIDGE_AGENT_DOC.md §11) ; un seul BOM en tout début de fichier, jamais
répété aux appels `Add-Content` suivants (qui ouvrent le fichier déjà
existant).

**Code de sortie lisible (issue #875)** : `$proc.Handle` est lu une fois,
juste après le `Start-Process -PassThru` qui lance le process surveillé
(valeur ignorée, seul l'effet de bord — « attacher » le process côté .NET
— compte) : sans cela, `$proc.ExitCode` peut lever une exception une fois
le process déjà terminé (comportement documenté de `System.Diagnostics.
Process`), ce qui laissait la ligne `[ARRET] code de sortie :` vide et
déclenchait un redémarrage « inattendu » même après un arrêt pourtant
propre (ex. l'auto-extinction par inactivité, code 42). Le code lu est
maintenant toujours affiché — la valeur elle-même, ou `illisible` si sa
lecture échoue malgré tout.

**Rotation par taille (issue #875)** : chaque `-FichierJournal` est limité
à 2 Mo (3 archives `.1`/`.2`/`.3` conservées, les plus anciennes
supprimées) — nécessaire depuis que la sortie y est recopiée en continu
(ci-dessus) : sans rotation, le journal de l'interface web en particulier
grossissait sans fin (chaque requête HTTP, dont `/heartbeat` sondé par le
navigateur toutes les quelques secondes, y ajoutait une ligne). En
complément, `new_issue.py` filtre désormais de son propre journal d'accès
werkzeug les requêtes `/heartbeat` et les fichiers statiques (`/static/…`)
lorsqu'il tourne sous ce superviseur (`$env:BRIDGE_SOUS_SUPERVISEUR_
SESSION=1`, posée par `surveiller_processus_session.ps1`) — sans effet
sous Linux ni pour `lancer_new_issue.sh`, qui ne posent jamais cette
variable.

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
   : la tâche `BridgeAgent-Session-<votre_compte>-Watcher-scrabble`
   apparaît dans le Planificateur de tâches, démarre immédiatement, et un
   `logs\watcher-scrabble.pid` + `logs\watcher-scrabble.log` apparaissent.
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
12. **(issue #875)** Reculer le dépôt de test d'un commit (`git reset
    --hard HEAD~1` dans le dépôt de travail Windows — jamais depuis Linux),
    ouvrir une session : `logs\new_issue-session.log` doit afficher le
    message complet de mise à jour automatique réussie, flèche « → » et
    accents lisibles (pas de `?` ni de plantage juste après), et le même
    message doit apparaître dans le bandeau de l'interface web. Avant ce
    correctif, `new_issue.py` plantait à cet instant précis
    (`UnicodeEncodeError`) et le message de réussite était perdu.
13. **(issue #875)** Après l'auto-extinction par inactivité d'un watcher
    (code 42, ~20 min sans issue traitable) : vérifier dans
    `logs\watcher-<nom>-session.log` que la ligne `[ARRET] code de sortie :`
    affiche bien `42` (jamais vide), suivie de `[FIN] arrêt propre` et
    **sans** redémarrage. Tuer le même watcher à la main (code non nul,
    hors `0,42`) : vérifier que le code affiché est le bon et qu'un
    redémarrage suit après ~10 s.
14. **(issue #875)** Laisser l'interface web tourner un moment sous ce
    superviseur (navigateur ouvert, `/heartbeat` actif) : vérifier que
    `logs\new_issue-session.log` ne grossit pas ligne par ligne au rythme
    du heartbeat — les requêtes `/heartbeat` et `/static/…` ne doivent plus
    y apparaître (tout le reste du trafic applicatif, lui, reste journalisé
    normalement).
15. **(issue #875)** Produire artificiellement plus de 2 Mo dans un
    `logs\*-session.log` (ex. laisser tourner longtemps, ou générer de la
    sortie répétée côté process surveillé) : vérifier l'apparition de
    `logs\*-session.log.1` (puis `.2`, `.3`) et que le fichier actif reste
    sous quelques Mo.
16. **(issue #877)** Avec un second compte Windows sur la même machine
    (ou un compte de test) : lancer `.\installer_demarrage_session.ps1
    -Projets scrabble` depuis la session de CE second compte alors que le
    premier compte a déjà ses tâches `BridgeAgent-Session-<premier>-*` en
    place. Vérifier que l'enregistrement réussit sans `Access is denied`
    (tâches `BridgeAgent-Session-<second>-*` distinctes), et que
    `Get-ScheduledTask -TaskName 'BridgeAgent-Session-<premier>-*'` montre
    les tâches du premier compte intactes, non modifiées par cette seconde
    installation.
17. **(issue #877)** Transition : sur un compte qui a déjà des tâches à
    l'ancien nom (ex. une installation d'avant ce correctif, ou renommées
    à la main pour simuler), relancer `installer_demarrage_session.ps1`
    avec les mêmes `-Projets` : vérifier le message « Transition de
    nommage (issue #877) : ancienne tâche/service « … » détectée —
    remplacement par « … » », que l'ancienne tâche a disparu, et que la
    nouvelle (`BridgeAgent-Session-<compte>-*`) est bien enregistrée et
    démarrée.
18. **(issue #877)** `-Desinstaller` depuis le second compte ci-dessus (16)
    : vérifier qu'il retire uniquement les tâches de CE compte
    (`BridgeAgent-Session-<second>-*`) et laisse celles du premier compte
    intactes.
19. **(issue #877)** Provoquer un refus d'accès réel (ex. créer à la main,
    avec les droits d'un AUTRE compte, une tâche `BridgeAgent-Session-
    <ce_compte>-IssuesInbox`, puis relancer le script sous CE compte) :
    vérifier que le message affiché explique la cause probable (collision
    de nom avec un autre compte) et la marche à suivre, que les AUTRES
    composants demandés (watchers de projet, interface web) s'enregistrent
    normalement malgré cet échec isolé, et que le résumé final affiche
    bien « INSTALLATION PARTIELLE » en listant le composant en échec.

## Voir aussi

- `provisioning/windows/provisionner.ps1` — provisioning du rôle CCW
  (machine Windows déléguée, hors périmètre de ce document).
- `provisioning/windows/ajouter_projet_ccw.ps1` — pattern NSSM/compte
  utilisateur repris ici pour `-ModeService`.
- `provisioning/windows/provisionner_new_issue_local.ps1` —
  dépendances/pare-feu de `new_issue.py`, prérequis de ce script.
- `installer_services.sh` + `systemd/watcher@.service` (racine du dépôt) —
  équivalent Linux.
