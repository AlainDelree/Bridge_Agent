<#
  installer_demarrage_session.ps1 — Démarrage automatique des watchers
  locaux sous Windows, à l'ouverture de SESSION de l'utilisateur courant
  (issue #864, suite de l'audit de parité #862).

  Contexte : #862 a constaté qu'il n'existe aucun équivalent Windows de
  installer_services.sh + systemd/watcher@.service (démarrage auto des
  watchers de projet, redémarrage après plantage) pour une machine Windows
  SEULE (PAS le rôle CCW de provisionner.ps1/ajouter_projet_ccw.ps1, délégué
  à une SECONDE machine via des issues chiffrées et le label `for-windows`).
  CE script est pour l'usage inverse : UN agent Claude Code tournant sur SON
  PROPRE PC Windows, avec ses propres projets locaux, le watcher du dépôt
  d'issues par fichiers (issues_inbox\) et l'interface web (new_issue.py) —
  rien à voir avec un bootstrap par issues chiffrées ni le label for-windows.

  ┌─────────────────────────────────────────────────────────────────────────┐
  │ CHOIX DE CONCEPTION : démarrage de SESSION par défaut, PAS un service.  │
  │                                                                          │
  │ Un service Windows tourne dans la session 0 (SYSTEM ou un compte sans   │
  │ bureau interactif), hors de la session graphique de l'utilisateur :      │
  │   - aucune bulle de notification (toast) ni son ne peut en sortir ;      │
  │   - le trousseau Windows (Credential Manager/DPAPI) de l'utilisateur,    │
  │     où Claude Code (~\.claude) et l'agent Vibe (~\.vibe) rangent leur    │
  │     connexion, n'est PAS accessible depuis une AUTRE session que celle   │
  │     de ce même utilisateur (constat réel, issue #860, repris dans       │
  │     ajouter_projet_ccw.ps1 — un service CCW doit alors tourner SOUS le   │
  │     compte utilisateur, PAS LocalSystem, pour cette seule raison).       │
  │ Un service NSSM sous le compte utilisateur (comme ajouter_projet_ccw)    │
  │ contourne le problème du trousseau, mais reste en session 0 : bulle et   │
  │ son restent indisponibles, et NSSM exige un mot de passe (ObjectName).   │
  │                                                                          │
  │ Pour un PC PERSONNEL où l'utilisateur ouvre sa session au quotidien, un  │
  │ démarrage DANS cette session (tâche planifiée « à l'ouverture de         │
  │ session », mode par défaut ci-dessous) est donc préférable :             │
  │   - bulle + son fonctionnent normalement (bip, notify équivalent) ;      │
  │   - AUCUN mot de passe à stocker : la tâche s'appuie sur la session déjà │
  │     ouverte de l'utilisateur (LogonType Interactive), jamais sur un      │
  │     identifiant/mot de passe enregistré ;                                │
  │   - ne nécessite PAS les droits administrateur (contrairement à un       │
  │     service Windows, y compris NSSM) pour un utilisateur qui s'enregistre │
  │     lui-même comme déclencheur de SA PROPRE tâche planifiée.             │
  │ Contrepartie acceptée : rien ne démarre avant la première ouverture de   │
  │ session (pas de démarrage « machine éteinte puis rallumée sans jamais    │
  │ ouvrir de session »), cas jugé marginal pour un PC personnel.            │
  │                                                                          │
  │ -ModeService (option SECONDAIRE, voir plus bas) : pour qui préfère       │
  │ malgré tout un vrai service NSSM (démarrage sans ouverture de session),  │
  │ au prix d'un mot de passe ET de la perte de bulle/son.                   │
  └─────────────────────────────────────────────────────────────────────────┘

  Ce qu'il enregistre, pour un démarrage automatique à l'ouverture de
  session du compte -CompteService (le compte qui lance ce script, par
  défaut) :
    - un watcher par projet local déclaré, un par nom donné via -Projets
      (ex. -Projets scrabble,rummikub) — équivalent, projet par projet, de
      systemd/watcher@.service : `python watcher.py --config configs\<nom>.conf` ;
    - le watcher du dépôt d'issues par fichiers
      (scripts\watcher_issues_inbox.py), sauf -SansIssuesInbox ;
    - l'interface web new_issue.py (équivalent fonctionnel de
      lancer_new_issue.sh — horodatage démarrage/arrêt/code de sortie dans
      un journal dédié, voir surveiller_processus_session.ps1), sauf
      -SansInterfaceWeb.

  Chaque process surveillé passe par surveiller_processus_session.ps1 (même
  dossier) : redémarrage automatique en cas d'arrêt INATTENDU, pas de
  redémarrage sur un arrêt PROPRE (code 0, ou 42 pour watcher.py —
  auto-extinction par inactivité, voir watcher.py::EXIT_INACTIVITE), une
  seule instance par watcher (fichier PID vérifié avant tout lancement),
  sortie standard/erreur recopiée EN CONTINU (pas seulement à l'arrêt) vers
  le journal du superviseur. Journaux dans <dépôt>\logs\ : watcher-<nom>.log
  (watcher.py lui-même) + watcher-<nom>-session.log (superviseur, ce qui
  échapperait au premier) ; watcher_issues_inbox-session.log ;
  new_issue-session.log.

  -DelaiDemarrageWatchersSec (défaut 20, issue #871, point 2) : les watchers
  de projet et le watcher du dépôt d'issues (issues_inbox) attendent ce
  nombre de secondes avant leur tout premier lancement — L'INTERFACE WEB,
  elle, démarre SANS attendre, puisque c'est elle qui fait la mise à jour
  automatique du dépôt (`git pull`) au lancement (voir
  provisionner_new_issue_local.ps1 / NEW_ISSUE_LOCAL_WINDOWS.md). Démarrés en
  même temps qu'elle (0 s, avant #871), les watchers pouvaient charger
  l'ANCIEN code du dépôt avant la fin de cette mise à jour. Le délai
  s'applique UNIQUEMENT au tout premier lancement (pas aux redémarrages
  après plantage, déjà espacés par -DelaiRedemarrageSec du superviseur) —
  voir surveiller_processus_session.ps1 -DelaiDemarrageSec, qui porte la
  logique réelle (un Start-Sleep en tête de CE script, pas une propriété
  de déclencheur de tâche planifiée : cette dernière ne s'appliquerait pas
  au Start-ScheduledTask immédiat fait plus bas par CE script après chaque
  enregistrement — voir le commentaire de surveiller_processus_session.ps1
  pour le détail).

  Nommage (issue #877) : un nom de tâche planifiée/service est unique pour
  TOUTE la machine, pas par utilisateur Windows — deux comptes sur le même
  PC ne peuvent donc pas enregistrer chacun une tâche « BridgeAgent-Session-
  IssuesInbox » (le second échoue avec Access is denied / 0x80070005, et
  l'installeur s'arrêtait net avant #877). Chaque nom inclut donc désormais
  le compte -CompteService : BridgeAgent-Session-<compte>-<Id> (ex.
  BridgeAgent-Session-alain-IssuesInbox), le préfixe BridgeAgent-Session-
  restant stable pour les commandes de la documentation qui filtrent sur ce
  préfixe. Un compte qui avait déjà des tâches à l'ANCIEN nom (sans le
  compte, ex. BridgeAgent-Session-IssuesInbox) voit celles-ci détectées (si
  elles lui appartiennent réellement — vérifié par le Principal de la
  tâche/StartName du service, jamais supposé depuis le nom seul) puis
  remplacées automatiquement par le nouveau nom, avec un message explicite ;
  une tâche à l'ancien nom appartenant à un AUTRE compte n'est, elle, jamais
  touchée. Un échec d'enregistrement par refus d'accès affiche la cause
  probable (collision de nom avec un autre compte, ou droits insuffisants)
  et la marche à suivre, au lieu de l'erreur système brute — l'installation
  continue avec les autres composants et le signale dans le résumé final
  plutôt que de s'arrêter net.

  Idempotent : relançable sans dommage — une tâche déjà enregistrée pour un
  projet encore demandé est simplement mise à jour (Register-ScheduledTask
  -Force, jamais de doublon) ; un projet RETIRÉ de -Projets depuis la
  dernière exécution voit sa tâche désinstallée automatiquement (y compris
  -SansIssuesInbox / -SansInterfaceWeb pour les deux autres).

  -Desinstaller : retire TOUT ce que ce script a pu enregistrer pour LE
  COMPTE -CompteService (tâches planifiées ET, le cas échéant, services
  NSSM d'un -ModeService antérieur), sous les DEUX formes de nom (nouvelle
  « BridgeAgent-Session-<compte>-* » et, si elle appartient à ce même
  compte, ancienne « BridgeAgent-Session-* » pré-#877) — sans qu'il soit
  nécessaire de redonner -Projets, la recherche se fait par préfixe de nom
  puis par propriétaire réel pour l'ancienne forme, jamais par un nom
  générique de process (cf. consigne « ne jamais arrêter par nom » : chaque
  arrêt cible un identifiant de tâche/service ou un PID précis, lu depuis
  son propre fichier). Une tâche/un service du même préfixe appartenant à un
  AUTRE compte Windows n'est jamais retiré.

  Aucun mot de passe stocké (mode par défaut) : tout tourne sous le compte
  -CompteService via sa session déjà ouverte.

  Prérequis :
    - Python (avec pip) déjà installé et sur le PATH — cf. provisionner.ps1
      (fonction Installer-Python) si besoin, ou toute installation Python
      standard de python.org ;
    - les dépendances de requirements.txt installées pour new_issue.py
      (flask/werkzeug) — cf. provisionner_new_issue_local.ps1, étape 1,
      NON ré-exécutée ici (hors périmètre de CE script) ;
    - gh (GitHub CLI) authentifié pour CE compte Windows, en session
      interactive — cf. provisionner_new_issue_local.ps1, étape 3 ;
    - chaque configs\<nom>.conf des projets listés doit déjà exister (ce
      script ne les crée JAMAIS — règle générale du dépôt, voir
      BRIDGE_AGENT_DOC.md §11 : CCL/CCW ne modifie/crée jamais configs\*.conf).
    - Exécution en PowerShell NORMAL (pas besoin d'administrateur) pour le
      mode par défaut ; ADMINISTRATEUR requis uniquement pour -ModeService
      (création de service Windows).

  Exemples :
    # Deux projets + issues_inbox + interface web, mode par défaut (session) :
    .\installer_demarrage_session.ps1 -Projets scrabble,rummikub

    # Uniquement issues_inbox + interface web (aucun projet local) :
    .\installer_demarrage_session.ps1

    # Sans l'interface web (déjà lancée autrement, ex. par provisionner_new_issue_local) :
    .\installer_demarrage_session.ps1 -Projets scrabble -SansInterfaceWeb

    # Délai de démarrage des watchers porté à 40 s (machine lente) :
    .\installer_demarrage_session.ps1 -Projets scrabble -DelaiDemarrageWatchersSec 40

    # Mode service NSSM (option secondaire — bulle/son indisponibles, mot de
    # passe du compte demandé en saisie masquée), console ADMINISTRATEUR :
    .\installer_demarrage_session.ps1 -Projets scrabble -ModeService

    # Désinstallation complète (tâches ET services éventuels) :
    .\installer_demarrage_session.ps1 -Desinstaller
#>

[CmdletBinding()]
param(
    # Noms des projets locaux à surveiller — chacun doit avoir un
    # configs\<nom>.conf déjà existant (jamais créé par ce script). Vide =
    # aucun watcher de projet (seulement issues_inbox + interface web, sauf
    # -Sans... correspondants). Demandé interactivement si ni -Projets ni
    # -Desinstaller ne sont fournis.
    [string[]]$Projets,

    # Ne PAS enregistrer le watcher du dépôt d'issues par fichiers
    # (scripts\watcher_issues_inbox.py).
    [switch]$SansIssuesInbox,

    # Ne PAS enregistrer l'interface web (new_issue.py).
    [switch]$SansInterfaceWeb,

    # Arguments supplémentaires de new_issue.py (défaut : --no-browser, pour
    # éviter de rouvrir un onglet de navigateur à chaque redémarrage
    # automatique — cf. surveiller_processus_session.ps1). Exemple pour
    # exposer sur le réseau local : -ArgsInterfaceWeb --lan,--no-browser
    # (nécessite un mot de passe déjà configuré, voir new_issue.py --set-password).
    [string[]]$ArgsInterfaceWeb = @('--no-browser'),

    # Délai (secondes) avant le tout premier lancement des watchers (projets
    # + issues_inbox), PAS de l'interface web — voir l'encadré en tête de
    # fichier (issue #871, point 2). 0 = aucun délai (comportement d'avant
    # #871). Ajuster à la hausse sur une machine lente où le `git pull`
    # automatique de l'interface prend plus que quelques secondes.
    [int]$DelaiDemarrageWatchersSec = 20,

    # Compte Windows sous lequel tourne le démarrage automatique — le compte
    # qui lance ce script par défaut (cohérent avec provisionner.ps1/
    # ajouter_projet_ccw.ps1, issue #860). Changer cette valeur suppose que
    # CE script tourne malgré tout sous ce même compte au moment de
    # l'enregistrement (la tâche/le service est posé pour -CompteService,
    # pas pour l'utilisateur courant de la console si différent).
    [string]$CompteService = $env:USERNAME,

    # Retire tout ce que ce script a pu enregistrer (tâches planifiées et
    # services NSSM d'un éventuel -ModeService antérieur), puis quitte.
    # -Projets est ignoré dans ce mode (recherche par préfixe de nom).
    [switch]$Desinstaller,

    # Option SECONDAIRE (voir l'encadré en tête de fichier) : enregistre de
    # vrais services Windows (NSSM) plutôt que des tâches planifiées de
    # session. Démarre même sans ouverture de session, mais : (1) bulle de
    # notification et son NE FONCTIONNENT PAS depuis un service (session 0,
    # sans bureau interactif) ; (2) exige le mot de passe du compte
    # -CompteService (saisie masquée, jamais stocké en clair ni journalisé) ;
    # (3) nécessite une console PowerShell ADMINISTRATEUR.
    [switch]$ModeService,

    # Affiche les actions prévues sans rien enregistrer ni démarrer.
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Info($msg)  { Write-Host "[installer-demarrage-session] $msg" -ForegroundColor Cyan }
function Avert($msg) { Write-Host "[installer-demarrage-session] AVERTISSEMENT : $msg" -ForegroundColor Yellow }
function Ok($msg)    { Write-Host "[installer-demarrage-session] $msg" -ForegroundColor Green }

# Convertit un SecureString en texte brut le temps strictement nécessaire,
# puis libère immédiatement le buffer non managé (BSTR) — même fonction que
# provisionner.ps1 / ajouter_projet_ccw.ps1 (dupliquée à l'identique : ce
# script reste volontairement autonome, même convention que les scripts CCW,
# voir ccw-commun.psm1 en tête de ce dossier).
function ConvertFrom-SecureStringPlain([System.Security.SecureString]$secure) {
    $ptr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

$PrefixeTache = 'BridgeAgent-Session-'

# Nettoie un nom de compte Windows des caractères interdits dans un nom de
# tâche planifiée/service (\/:*?"<>|) — un compte de domaine (DOMAINE\user)
# ou un UPN (user@domaine) reste informatif sans faire échouer
# Register-ScheduledTask/nssm install sur le caractère '\' notamment.
function Nettoyer-NomPourTache([string]$Nom) {
    return ($Nom -replace '[\\/:*?"<>|]', '_')
}

# Suffixe de compte inclus dans CHAQUE nom de tâche/service depuis #877 : un
# nom de tâche planifiée est unique pour TOUTE LA MACHINE, pas par compte
# Windows — sans ce suffixe, un second compte sur le même PC ne peut pas
# enregistrer la tâche déjà créée par le premier (Access is denied,
# 0x80070005). Le préfixe $PrefixeTache seul reste le repère stable pour les
# commandes de la documentation qui filtrent sur « BridgeAgent-Session-* ».
$CompteSûr     = Nettoyer-NomPourTache $CompteService
$PrefixeCompte = "$PrefixeTache$CompteSûr-"

# ---------------------------------------------------------------------------
# Détermination du PROPRIÉTAIRE réel d'une tâche/service déjà enregistré —
# jamais déduit du nom seul (une ancienne tâche pré-#877, sans compte dans
# son nom, peut appartenir à N'IMPORTE QUEL compte de la machine).
# ---------------------------------------------------------------------------
function Obtenir-ProprietaireTache([string]$Nom) {
    $tache = Get-ScheduledTask -TaskName $Nom -ErrorAction SilentlyContinue
    if ($tache -and $tache.Principal -and $tache.Principal.UserId) {
        return $tache.Principal.UserId
    }
    $nomEchappe = $Nom -replace "'", "''"
    try {
        $service = Get-CimInstance -ClassName Win32_Service -Filter "Name='$nomEchappe'" -ErrorAction SilentlyContinue
        if ($service -and $service.StartName) { return $service.StartName }
    } catch {
        # Droits WMI insuffisants ou autre échec de requête : propriétaire
        # indéterminé, voir Comptes-Equivalents (prudence : jamais traité
        # comme appartenant à CE compte dans ce cas).
    }
    return $null
}

# Compare deux identités de compte en ignorant le préfixe domaine/machine
# (DOMAINE\alain ou .\alain -> alain) et la casse — approximatif par
# nécessité (impossible de tester sous Linux, voir le rapport de clôture de
# l'issue #877) mais prudent : une identité vide ou indéterminée n'est
# JAMAIS considérée comme équivalente.
function Normaliser-NomCompte([string]$Nom) {
    if ([string]::IsNullOrWhiteSpace($Nom)) { return '' }
    return (($Nom -replace '^.*\\', '').Trim().ToLowerInvariant())
}
function Comptes-Equivalents([string]$CompteA, [string]$CompteB) {
    $a = Normaliser-NomCompte $CompteA
    $b = Normaliser-NomCompte $CompteB
    if ([string]::IsNullOrEmpty($a) -or [string]::IsNullOrEmpty($b)) { return $false }
    return ($a -eq $b)
}

# Un nom « BridgeAgent-Session-* » appartient-il au compte -CompteService
# courant ? Immédiat pour le nouveau schéma (le compte est DANS le nom) ;
# pour l'ancien schéma (pré-#877, sans compte dans le nom), seul le
# propriétaire réel (Principal/StartName) tranche — jamais une supposition
# sur le nom, qui est partagé pour toute la machine.
function Est-NomCeCompte([string]$Nom) {
    if ($Nom.StartsWith($PrefixeCompte)) { return $true }
    if (-not $Nom.StartsWith($PrefixeTache)) { return $false }
    $proprietaire = Obtenir-ProprietaireTache $Nom
    return (Comptes-Equivalents $proprietaire $CompteService)
}

$RepDepot          = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$RepConfigs        = Join-Path $RepDepot 'configs'
$RepLogs           = Join-Path $RepDepot 'logs'
$CheminWatcher     = Join-Path $RepDepot 'watcher.py'
$CheminIssuesInbox = Join-Path $RepDepot 'scripts\watcher_issues_inbox.py'
$CheminNewIssue    = Join-Path $RepDepot 'new_issue.py'
$CheminWrapper     = Join-Path $PSScriptRoot 'surveiller_processus_session.ps1'
$CheminConfInbox   = Join-Path $RepConfigs 'watcher_issues_inbox.conf'

# ---------------------------------------------------------------------------
# Désinstallation d'UN composant identifié par son nom complet (tâche
# planifiée ET/OU service NSSM — les deux mécanismes partagent le même nom,
# voir en-tête de fichier) : jamais d'arrêt par nom générique de process,
# toujours par identifiant de tâche/service précis (cf. consigne du dépôt).
# ---------------------------------------------------------------------------
function Desinstaller-Composant([string]$NomComplet) {
    $trouve = $false

    $tache = Get-ScheduledTask -TaskName $NomComplet -ErrorAction SilentlyContinue
    if ($tache) {
        $trouve = $true
        if ($DryRun) {
            Info "[DRY-RUN] Arrêterait puis désinscrirait la tâche planifiée « $NomComplet »."
        } else {
            Info "Tâche planifiée « $NomComplet » trouvée — arrêt puis désinscription…"
            Stop-ScheduledTask -TaskName $NomComplet -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $NomComplet -Confirm:$false
        }
    }

    $service = Get-Service -Name $NomComplet -ErrorAction SilentlyContinue
    if ($service) {
        $trouve = $true
        if ($DryRun) {
            Info "[DRY-RUN] Arrêterait puis supprimerait le service « $NomComplet » (nssm)."
        } else {
            Info "Service « $NomComplet » trouvé — arrêt puis suppression (nssm)…"
            try {
                nssm stop   $NomComplet | Out-Null
                nssm remove $NomComplet confirm | Out-Null
            } catch {
                Avert ("Impossible de retirer le service « $NomComplet » ($($_.Exception.Message)) — " +
                       "relancer cette désinstallation depuis une console ADMINISTRATEUR si ce service " +
                       "existe toujours.")
            }
        }
    }

    return $trouve
}

# ---------------------------------------------------------------------------
# -Desinstaller : recherche par préfixe, indépendante de -Projets.
# ---------------------------------------------------------------------------
if ($Desinstaller) {
    Info "=== Désinstallation de tout ce qui porte le préfixe « $PrefixeTache » pour le compte « $CompteService » ==="
    $nomsBrut = @()
    $nomsBrut += (Get-ScheduledTask -TaskName "$PrefixeTache*" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty TaskName)
    $nomsBrut += (Get-Service -Name "$PrefixeTache*" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
    $nomsBrut = $nomsBrut | Select-Object -Unique

    # Scopé au compte -CompteService (issue #877) : les deux formes de nom
    # de CE compte (nouvelle « BridgeAgent-Session-<compte>-* », et
    # ancienne « BridgeAgent-Session-* » si elle lui appartient réellement,
    # voir Est-NomCeCompte) — jamais une tâche/un service d'un AUTRE compte,
    # même s'il partage le préfixe.
    $noms = @()
    $nomsAutreCompte = @()
    foreach ($n in $nomsBrut) {
        if (Est-NomCeCompte $n) { $noms += $n } else { $nomsAutreCompte += $n }
    }

    if ($noms.Count -eq 0) {
        Info "Rien à désinstaller pour le compte « $CompteService » (aucune tâche ni service « $PrefixeTache* » de ce compte trouvé)."
    } else {
        foreach ($n in $noms) { Desinstaller-Composant $n | Out-Null }
        Ok "Désinstallation terminée pour le compte « $CompteService » ($($noms.Count) composant(s), ancien et/ou nouveau nommage)."
    }
    if ($nomsAutreCompte.Count -gt 0) {
        Info "Ignoré(s) sans y toucher, $($nomsAutreCompte.Count) appartenant à un autre compte Windows : $($nomsAutreCompte -join ', ')"
    }
    Info "Les fichiers de configuration (configs\*.conf) et les journaux (logs\) sont conservés — rien n'est supprimé sur le disque."
    return
}

# ---------------------------------------------------------------------------
# Vérifications préalables.
# ---------------------------------------------------------------------------
if (-not (Test-Path $CheminWatcher)) {
    throw "watcher.py introuvable ($CheminWatcher) — ce script doit vivre dans provisioning\windows\ du dépôt Bridge_Agent."
}
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    throw ("python introuvable sur le PATH — installez-le d'abord " +
           "(cf. provisionner.ps1, fonction Installer-Python, ou python.org).")
}
$PythonExe = $pythonCmd.Source

if ($ModeService) {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "-ModeService requiert une console PowerShell ADMINISTRATEUR (création de service Windows)."
    }
    if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
        throw "nssm introuvable sur le PATH — -ModeService le requiert (cf. provisionner.ps1, fonction Installer-Nssm)."
    }
    Avert ("-ModeService : un service Windows tourne hors de votre session — AUCUNE bulle de notification " +
           "ni son n'en sortira (cf. encadré en tête de ce script). Préférez le mode par défaut (tâche de " +
           "session, sans mot de passe) sur un PC personnel, sauf besoin explicite d'un démarrage SANS " +
           "ouverture de session.")
}

# ---------------------------------------------------------------------------
# Liste des projets : paramètre, ou saisie interactive si absent.
# ---------------------------------------------------------------------------
if (-not $PSBoundParameters.ContainsKey('Projets')) {
    $saisie = Read-Host ("Projets locaux à surveiller, séparés par des virgules " +
                         "(ex. scrabble,rummikub — vide = aucun)")
    if ([string]::IsNullOrWhiteSpace($saisie)) { $Projets = @() }
    else { $Projets = $saisie -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ } }
}
if (-not $Projets) { $Projets = @() }

# Convention déjà implicite dans tout le dépôt (installer_services.sh,
# systemd/watcher@.service %i) : le nom de fichier configs\<nom>.conf EST le
# nom du projet — watcher.py publie son PID/journal sous ce même <nom>
# (logs\watcher-<nom>.pid/.log), jamais sous la valeur du champ NOM interne
# au .conf si elle diffère (cas non supporté, pas davantage ici qu'ailleurs).
$ProjetsValides = @()
foreach ($p in $Projets) {
    $cheminConf = Join-Path $RepConfigs "$p.conf"
    if (Test-Path $cheminConf) {
        $ProjetsValides += $p
    } else {
        Avert "Projet « $p » ignoré : configs\$p.conf introuvable (ce script ne crée jamais de .conf)."
    }
}

Info "Dépôt       : $RepDepot"
Info "Python      : $PythonExe"
Info "Compte      : $CompteService$(if ($CompteSûr -ne $CompteService) { " (nom utilisé dans les tâches : $CompteSûr)" })"
Info "Mode        : $(if ($ModeService) { 'service NSSM (secondaire)' } else { 'tâche de session (défaut)' })"
Info "Projets     : $(if ($ProjetsValides.Count -gt 0) { $ProjetsValides -join ', ' } else { '(aucun)' })"
Info "Issues_inbox: $(if ($SansIssuesInbox) { 'non' } else { 'oui' })"
Info "Interface web: $(if ($SansInterfaceWeb) { 'non' } else { "oui ($($ArgsInterfaceWeb -join ' '))" })"
Info "Délai watchers: ${DelaiDemarrageWatchersSec}s avant leur 1er lancement (interface web : sans délai)"
Write-Host ''

# ---------------------------------------------------------------------------
# Description de chaque composant désiré : Id (suffixe du nom de tâche/
# service), commande + arguments du process surveillé, fichier journal du
# superviseur, fichier PID (garde-fou « une seule instance »). NomComplet
# inclut désormais le compte (issue #877) ; NomAncien est le nom pré-#877
# (sans compte), conservé pour détecter et migrer une tâche existante de CE
# compte à l'ancien nommage — jamais pour la recréer.
# ---------------------------------------------------------------------------
function Decrire-Composant([string]$Id, [string[]]$ArgsEnfant, [string]$NomLogSession, [string]$NomPid,
                            [int]$DelaiDemarrageSec = 0) {
    [PSCustomObject]@{
        Id                = $Id
        NomComplet        = "$PrefixeCompte$Id"
        NomAncien         = "$PrefixeTache$Id"
        ArgsEnfant        = $ArgsEnfant
        FichierJournal    = Join-Path $RepLogs $NomLogSession
        FichierPid        = Join-Path $RepLogs $NomPid
        DelaiDemarrageSec = $DelaiDemarrageSec
    }
}

$Composants = @()
foreach ($p in $ProjetsValides) {
    $cheminConf = Join-Path $RepConfigs "$p.conf"
    $Composants += Decrire-Composant "Watcher-$p" @($CheminWatcher, '--config', $cheminConf) `
        "watcher-$p-session.log" "watcher-$p.pid" $DelaiDemarrageWatchersSec
}
if (-not $SansIssuesInbox) {
    # --attendre-si-occupe (issue #883) : SEUL ce lancement par tâche
    # planifiée le passe. L'interface web (new_issue.py) lance sa PROPRE
    # instance sans ce flag (app.issues_inbox.demarrer_watcher_inbox,
    # arrêt immédiat voulu, #881) et gagne presque toujours le verrou en
    # premier (elle démarre sans délai, cette tâche-ci attend
    # -DelaiDemarrageWatchersSec, 20 s par défaut). Sans ce flag, la tâche
    # planifiée trouvait alors le verrou tenu, s'arrêtait proprement (code
    # 0) et restait `Ready` pour le reste de la session : si l'interface
    # s'arrêtait ensuite (bouton « Quitter », tâche coupée, plantage), elle
    # arrêtait aussi le watcher qu'elle avait lancé, et plus personne ne
    # traitait issues_inbox/ jusqu'à son retour. Avec ce flag, cette
    # instance se met en veille au lieu de quitter et prend le relais dès
    # que le verrou de l'interface se libère — voir la docstring de module
    # de scripts/watcher_issues_inbox.py pour le détail complet.
    $argsInbox = @($CheminIssuesInbox, '--attendre-si-occupe')
    if (Test-Path $CheminConfInbox) { $argsInbox += @('--config', $CheminConfInbox) }
    $Composants += Decrire-Composant 'IssuesInbox' $argsInbox `
        'watcher_issues_inbox-session.log' 'watcher_issues_inbox.pid' $DelaiDemarrageWatchersSec
}
if (-not $SansInterfaceWeb) {
    # Pas de délai ici : c'est CE composant qui fait la mise à jour
    # automatique du dépôt (git pull) que les watchers ci-dessus attendent.
    $Composants += Decrire-Composant 'InterfaceWeb' (@($CheminNewIssue) + $ArgsInterfaceWeb) `
        'new_issue-session.log' 'new_issue.pid'
}

if (-not (Test-Path $RepLogs)) {
    if ($DryRun) { Info "[DRY-RUN] Créerait $RepLogs." } else { New-Item -ItemType Directory -Path $RepLogs -Force | Out-Null }
}

# ---------------------------------------------------------------------------
# Nettoyage des composants obsolètes (projet retiré de -Projets, ou
# -SansIssuesInbox/-SansInterfaceWeb nouvellement passé) ET transition de
# nommage (issue #877) : toute tâche/service « BridgeAgent-Session-* »
# appartenant à CE compte (nouveau nom déjà à son compte dans le nom, ancien
# nom vérifié par propriétaire réel — voir Est-NomCeCompte) mais absent de
# la liste désirée ci-dessus (qui ne contient QUE des noms nouveaux) est
# désinstallé — ce qui couvre aussi bien un projet retiré qu'une ancienne
# tâche pré-#877 encore présente pour un composant toujours désiré (elle
# sera recréée juste après, sous le nouveau nom, par la boucle principale).
# Une tâche/un service du même préfixe appartenant à un AUTRE compte n'est
# JAMAIS listé ici ni touché.
# ---------------------------------------------------------------------------
$NomsDesires = $Composants | ForEach-Object { $_.NomComplet }
$NomsExistantsBrut = @()
$NomsExistantsBrut += (Get-ScheduledTask -TaskName "$PrefixeTache*" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty TaskName)
$NomsExistantsBrut += (Get-Service -Name "$PrefixeTache*" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
$NomsExistantsBrut = $NomsExistantsBrut | Select-Object -Unique

$NomsExistants = @()
$NomsAutreCompte = @()
foreach ($n in $NomsExistantsBrut) {
    if (Est-NomCeCompte $n) { $NomsExistants += $n } else { $NomsAutreCompte += $n }
}
$NomsObsoletes = $NomsExistants | Where-Object { $NomsDesires -notcontains $_ }

foreach ($n in $NomsObsoletes) {
    $composantCorrespondant = $Composants | Where-Object { $_.NomAncien -eq $n } | Select-Object -First 1
    if ($composantCorrespondant) {
        Info ("Transition de nommage (issue #877) : ancienne tâche/service « $n » de CE compte " +
              "($CompteService) détectée — remplacement par « $($composantCorrespondant.NomComplet) »…")
    } else {
        Info "Composant obsolète « $n » (plus dans la liste désirée) — désinstallation…"
    }
    Desinstaller-Composant $n | Out-Null
}
if ($NomsAutreCompte.Count -gt 0) {
    Info "Ignoré(s) sans y toucher, $($NomsAutreCompte.Count) appartenant à un autre compte Windows : $($NomsAutreCompte -join ', ')"
}

# ---------------------------------------------------------------------------
# Construction de la ligne d'arguments du superviseur (identique, que la
# cible soit une tâche planifiée ou un service NSSM — voir en-tête de
# surveiller_processus_session.ps1).
# ---------------------------------------------------------------------------
function Quoter([string]$s) { '"' + $s + '"' }

function Construire-LigneArguments($composant) {
    $elements = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
        '-File', (Quoter $CheminWrapper),
        '-Commande', (Quoter $PythonExe),
        '-RepTravail', (Quoter $RepDepot),
        '-FichierJournal', (Quoter $composant.FichierJournal),
        '-FichierPid', (Quoter $composant.FichierPid),
        '-CodesSansRedemarrage', '0,42',
        '-DelaiRedemarrageSec', '10',
        '-DelaiDemarrageSec', $composant.DelaiDemarrageSec
    ) + ($composant.ArgsEnfant | ForEach-Object { Quoter $_ })
    return $elements -join ' '
}

# ---------------------------------------------------------------------------
# Mot de passe (UNE SEULE saisie, réutilisée pour tous les services) —
# -ModeService uniquement. Read-Host -AsSecureString, PAS Get-Credential
# (fenêtre graphique invisible/bloquante en session non interactive — même
# raison que provisionner.ps1, issue #658, point 2).
# ---------------------------------------------------------------------------
$MotDePassePlain = $null
if ($ModeService -and $Composants.Count -gt 0 -and -not $DryRun) {
    Info "Mot de passe du compte « $CompteService » requis pour les services NSSM :"
    $secMotDePasse = Read-Host -AsSecureString "Mot de passe de $CompteService"
    $MotDePassePlain = ConvertFrom-SecureStringPlain $secMotDePasse
}

# ---------------------------------------------------------------------------
# Diagnostic d'un échec d'enregistrement (issue #877) : un refus d'accès
# (Access is denied, HRESULT 0x80070005) lors de Register-ScheduledTask/nssm
# install signifie presque toujours qu'un nom IDENTIQUE existe déjà sous un
# AUTRE compte Windows de la machine (les noms de tâche/service sont
# uniques pour toute la machine) — cas déjà rencontré en essai réel avec
# deux comptes. Affiche la cause probable et la marche à suivre plutôt que
# l'erreur système brute ; le composant en échec est ensuite listé dans le
# résumé final (voir plus bas) au lieu de laisser l'installation à moitié
# faite sans le dire.
# ---------------------------------------------------------------------------
function Diagnostiquer-EchecEnregistrement([string]$NomComplet, $Exception) {
    $msg = $Exception.Message
    $estAccesRefuse = ($msg -match '0x80070005') -or ($msg -match '(?i)access is denied') -or ($msg -match '(?i)acc.s refus.')
    if ($estAccesRefuse) {
        return ("Accès refusé lors de l'enregistrement de « $NomComplet ». Cause la plus probable : une " +
                "tâche/un service du MÊME nom existe déjà sous un AUTRE compte Windows de cette machine (les " +
                "noms de tâche/service sont uniques pour TOUTE la machine, pas par utilisateur — issue #877). " +
                "Vérifiez depuis une console PowerShell ADMINISTRATEUR (une fenêtre non élevée ne voit pas les " +
                "tâches des autres comptes) : Get-ScheduledTask -TaskName '$NomComplet' | Select TaskName,@{" +
                "n='Compte';e={`$_.Principal.UserId}}. Si elle appartient bien à un autre compte, ce script " +
                "n'y touchera JAMAIS automatiquement : supprimez-la manuellement avec les droits de ce compte, " +
                "ou choisissez un -CompteService différent si le nom affiché par $CompteService ci-dessus ne " +
                "correspond pas au compte réel. Si elle appartient à CE compte ($CompteService) mais que cette " +
                "console n'a pas les droits voulus sur elle, relancez cette installation depuis une console " +
                "ADMINISTRATEUR.")
    }
    return "Échec de l'enregistrement de « $NomComplet » : $msg"
}

$Erreurs = @()
try {
    foreach ($composant in $Composants) {
        $nomComplet = $composant.NomComplet
        $ligneArgs  = Construire-LigneArguments $composant

        # Changement de mode pour un composant resté dans la liste désirée
        # (ex. relance avec -ModeService sur un projet déjà enregistré en
        # tâche de session, ou l'inverse) : le nettoyage des composants
        # OBSOLÈTES ci-dessus ne le couvre PAS (son nom reste désiré) — sans
        # ce retrait explicite de l'AUTRE mécanisme, l'ancien et le nouveau
        # tourneraient tous les deux en même temps, violant « une seule
        # instance par watcher ».
        if ($ModeService) {
            if (Get-ScheduledTask -TaskName $nomComplet -ErrorAction SilentlyContinue) {
                if ($DryRun) {
                    Info "[DRY-RUN] Retirerait l'ancienne tâche planifiée « $nomComplet » (changement de mode vers service)."
                } else {
                    Info "Ancienne tâche planifiée « $nomComplet » trouvée (changement de mode) — retrait…"
                    Stop-ScheduledTask -TaskName $nomComplet -ErrorAction SilentlyContinue
                    Unregister-ScheduledTask -TaskName $nomComplet -Confirm:$false
                }
            }
        } else {
            if (Get-Service -Name $nomComplet -ErrorAction SilentlyContinue) {
                if ($DryRun) {
                    Info "[DRY-RUN] Retirerait l'ancien service « $nomComplet » (changement de mode vers tâche de session)."
                } else {
                    Info "Ancien service « $nomComplet » trouvé (changement de mode) — retrait…"
                    try {
                        nssm stop   $nomComplet | Out-Null
                        nssm remove $nomComplet confirm | Out-Null
                    } catch {
                        Avert ("Impossible de retirer l'ancien service « $nomComplet » " +
                               "($($_.Exception.Message)) — relancer depuis une console ADMINISTRATEUR.")
                    }
                }
            }
        }

        if ($ModeService) {
            # -------------------------------------------------------------
            # Service NSSM — exécute le MÊME superviseur que le mode tâche
            # (powershell.exe + surveiller_processus_session.ps1) : NSSM
            # n'a besoin ici que de garder CE process en vie (Restart=
            # Default), toute la logique de redémarrage du process SURVEILLÉ
            # reste dans le superviseur (voir en-tête de fichier). Idempotent
            # : arrêt + suppression avant recréation, même pattern que
            # provisionner.ps1/ajouter_projet_ccw.ps1.
            # -------------------------------------------------------------
            $svcExistant = Get-Service -Name $nomComplet -ErrorAction SilentlyContinue
            if ($svcExistant) {
                if ($DryRun) {
                    Info "[DRY-RUN] Arrêterait puis supprimerait le service existant « $nomComplet » avant recréation."
                } else {
                    Info "Service « $nomComplet » déjà présent — arrêt puis suppression avant recréation…"
                    nssm stop   $nomComplet | Out-Null
                    nssm remove $nomComplet confirm | Out-Null
                }
            }

            if ($DryRun) {
                Info "[DRY-RUN] Enregistrerait le service « $nomComplet » :"
                Info "[DRY-RUN]   powershell.exe $ligneArgs"
                Info "[DRY-RUN]   Compte : $CompteService (mot de passe demandé à l'exécution réelle)."
            } else {
                try {
                    Info "Enregistrement du service « $nomComplet » (NSSM)…"
                    nssm install $nomComplet 'powershell.exe'
                    if ($LASTEXITCODE -ne 0) { throw "nssm install a échoué (code $LASTEXITCODE)." }
                    nssm set $nomComplet AppParameters  $ligneArgs
                    nssm set $nomComplet AppDirectory   $RepDepot
                    nssm set $nomComplet Start          SERVICE_AUTO_START
                    nssm set $nomComplet AppExit Default Restart
                    nssm set $nomComplet AppRestartDelay 5000
                    nssm set $nomComplet ObjectName ".\$CompteService" $MotDePassePlain
                    # $MotDePassePlain reste nécessaire pour les composants
                    # suivants de CETTE boucle — effacé une seule fois après
                    # la boucle entière (bloc finally externe, plus bas).
                    nssm start $nomComplet | Out-Null
                    if ($LASTEXITCODE -ne 0) { throw "nssm start a échoué (code $LASTEXITCODE)." }
                    Ok "Service « $nomComplet » démarré."
                } catch {
                    $diagnostic = Diagnostiquer-EchecEnregistrement $nomComplet $_.Exception
                    Avert $diagnostic
                    $Erreurs += [PSCustomObject]@{ NomComplet = $nomComplet; Message = $diagnostic }
                    continue
                }
            }
        } else {
            # -------------------------------------------------------------
            # Tâche planifiée « à l'ouverture de session » — mode par
            # défaut. LogonType Interactive : s'appuie sur la session déjà
            # ouverte de -CompteService, AUCUN mot de passe à fournir ni à
            # stocker. ExecutionTimeLimit = 0 (illimité) : la limite PAR
            # DÉFAUT du Planificateur de tâches est de 72 h — sans ce
            # réglage explicite, un watcher resterait tué par le
            # Planificateur après 3 jours, même sans plantage (découvert en
            # relecture, pas en test réel — Alain confirmera sur Windows).
            # MultipleInstances IgnoreNew : un deuxième déclenchement (ex.
            # Start-ScheduledTask relancé alors que le superviseur tourne
            # encore) n'empêche jamais l'instance déjà active.
            # -------------------------------------------------------------
            if ($DryRun) {
                Info "[DRY-RUN] Enregistrerait la tâche planifiée « $nomComplet » (déclencheur : ouverture de session de $CompteService) :"
                Info "[DRY-RUN]   powershell.exe $ligneArgs"
            } else {
                try {
                    $declencheur = New-ScheduledTaskTrigger -AtLogOn -User $CompteService
                    $action      = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $ligneArgs -WorkingDirectory $RepDepot
                    $principalTache = New-ScheduledTaskPrincipal -UserId $CompteService -LogonType Interactive -RunLevel Limited
                    $reglages    = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
                        -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

                    Info "Enregistrement de la tâche planifiée « $nomComplet »…"
                    Register-ScheduledTask -TaskName $nomComplet -Trigger $declencheur -Action $action `
                        -Principal $principalTache -Settings $reglages -Force | Out-Null

                    $etat = (Get-ScheduledTask -TaskName $nomComplet).State
                    if ($etat -ne 'Running') {
                        Start-ScheduledTask -TaskName $nomComplet
                        Ok "Tâche « $nomComplet » enregistrée et démarrée."
                    } else {
                        Ok "Tâche « $nomComplet » mise à jour (une instance tournait déjà — non redémarrée)."
                    }
                } catch {
                    $diagnostic = Diagnostiquer-EchecEnregistrement $nomComplet $_.Exception
                    Avert $diagnostic
                    $Erreurs += [PSCustomObject]@{ NomComplet = $nomComplet; Message = $diagnostic }
                    continue
                }
            }
        }
    }
} finally {
    if ($MotDePassePlain) {
        $MotDePassePlain = $null
        [System.GC]::Collect()
    }
}

# ---------------------------------------------------------------------------
# Résumé.
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host '========================================================================' -ForegroundColor Cyan
Write-Host '  RÉSUMÉ' -ForegroundColor Cyan
Write-Host '========================================================================' -ForegroundColor Cyan
if ($DryRun) { Avert 'Mode -DryRun : AUCUNE action listée ci-dessus n''a été exécutée réellement.' }
foreach ($composant in $Composants) {
    if ($Erreurs | Where-Object { $_.NomComplet -eq $composant.NomComplet }) { continue }  # listé séparément ci-dessous
    $suffixeDelai = if ($composant.DelaiDemarrageSec -gt 0) { " (démarrage différé de $($composant.DelaiDemarrageSec)s)" } else { '' }
    Info "- $($composant.NomComplet) — journal : $($composant.FichierJournal)$suffixeDelai"
}
if ($Composants.Count -eq 0) {
    Info '(aucun composant demandé — ni projet, ni issues_inbox, ni interface web)'
}
if ($Erreurs.Count -gt 0) {
    Write-Host ''
    Avert ("INSTALLATION PARTIELLE : $($Erreurs.Count) composant(s) PAS enregistré(s) sur " +
           "$($Composants.Count) demandé(s) :")
    foreach ($e in $Erreurs) {
        Write-Host "  - $($e.NomComplet)" -ForegroundColor Yellow
        Write-Host "    $($e.Message)" -ForegroundColor Yellow
    }
}
Write-Host ''
Info "Pour vérifier (ce compte)  : Get-ScheduledTask -TaskName '$PrefixeCompte*'  (ou Get-Service si -ModeService)"
Info "Pour vérifier (la machine) : Get-ScheduledTask -TaskName '$PrefixeTache*'  — console ADMINISTRATEUR pour voir les tâches des autres comptes"
Info "Pour désinstaller (ce compte) : .\installer_demarrage_session.ps1 -Desinstaller -CompteService $CompteService"
