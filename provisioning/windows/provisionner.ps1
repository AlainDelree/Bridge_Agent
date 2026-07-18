<#
  provisionner.ps1 — Provisioning LOGICIEL de la VM Windows CCW (phase 2, issue #147).

  Ce script s'exécute DANS la VM « CCW-Build » (créée en phase 1, issue #146),
  soit au premier logon, soit manuellement dans une console PowerShell élevée.
  Il installe l'outillage nécessaire à l'agent Claude Code Windows (CCW) puis
  met en place le service Windows (NSSM) qui lancera le watcher au démarrage.

  Il est POUSSÉ et EXÉCUTÉ à distance depuis CCL par lancer_provisioning.py
  (VBoxManage guestcontrol) — mais reste utilisable seul.

  Ce qu'il fait :
    1. installe via winget : Git, GitHub CLI (gh), Python 3, NSSM ;
    2. installe pyinstaller (pip) — requis pour les builds .exe délégués ;
    3. installe Claude Code via l'installeur natif officiel (pas de Node.js) :
         irm https://claude.ai/install.ps1 | iex
    4. clone AlainDelree/Bridge_Agent (lecture seule) dans C:\CCW\Bridge_Agent ;
    5. écrit configs\ccw.conf (LABEL=for-windows, NOM=ccw, …) ;
    6. enregistre un vrai service Windows (via NSSM) qui lance le watcher au
       démarrage de la machine (sans session ouverte), avec redémarrage
       automatique en cas d'échec.

  ┌─────────────────────────────────────────────────────────────────────────┐
  │ AUTHENTIFICATION CLAUDE — NE PAS committer de clé API.                    │
  │ L'agent `claude` a besoin d'être authentifié pour fonctionner :          │
  │   • usage HEADLESS : définir la variable d'environnement                 │
  │       ANTHROPIC_API_KEY  (voir le placeholder plus bas — NE PAS la       │
  │       coder en dur ici ni la committer, exactement comme le mot de       │
  │       passe en phase 1) ;                                                 │
  │   • usage INTERACTIF : lancer une seule fois `claude auth login`.        │
  │ Ce script ne fixe AUCUNE clé : il rappelle seulement la marche à suivre. │
  └─────────────────────────────────────────────────────────────────────────┘

  Idempotent : relançable sans dommage (winget saute ce qui est déjà installé,
  le clone est mis à jour par pull, le service est arrêté/supprimé puis recréé).

  Prérequis : Windows 11 (winget présent), exécution en administrateur.
#>

[CmdletBinding()]
param(
    # Dossier de travail dédié côté invité.
    [string]$RepCCW = 'C:\CCW',
    # Dépôt cloné (lecture seule).
    [string]$Depot = 'AlainDelree/Bridge_Agent',
    # Lettre du lecteur réseau où VirtualBox automonte le partage CCW_Share
    # (phase 1 : sharedfolder add … --automount). Conservé pour
    # référence/documentation UNIQUEMENT : REP_TRAVAIL n'utilise PLUS cette
    # lettre mais le chemin UNC \\VBOXSVR\CCW_Share, seul accessible depuis
    # LocalSystem (issue #149, suite #148). Les lecteurs automontés en session
    # interactive ne sont pas visibles pour le service tournant sous LocalSystem.
    [string]$LettrePartage = 'E:'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Info($msg)  { Write-Host "[provisionner] $msg" -ForegroundColor Cyan }
function Avert($msg) { Write-Host "[provisionner] AVERTISSEMENT : $msg" -ForegroundColor Yellow }

$RepDepot = Join-Path $RepCCW 'Bridge_Agent'

# ---------------------------------------------------------------------------
# 1. Installations via winget (idempotent : --exact + acceptation licences).
# ---------------------------------------------------------------------------
function Installer-Winget($id, $nom) {
    Info "Installation de $nom ($id) via winget…"
    winget install --id $id --exact --silent `
        --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 0x8A15002B) {
        # 0x8A15002B = « déjà installé / aucune mise à jour disponible ».
        Avert "winget a renvoyé le code $LASTEXITCODE pour $id (peut-être déjà installé)."
    }
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget introuvable : Windows 11 attendu (App Installer). Abandon."
}

Installer-Winget 'Git.Git'            'Git'
Installer-Winget 'GitHub.cli'         'GitHub CLI (gh)'
Installer-Winget 'Python.Python.3.12' 'Python 3'
Installer-Winget 'NSSM.NSSM'          'NSSM'

# Rafraîchir le PATH de la session pour voir git/gh/python fraîchement installés.
$env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
            [System.Environment]::GetEnvironmentVariable('Path', 'User')

# ---------------------------------------------------------------------------
# 2. pyinstaller (raison d'être de CCW : builds .exe délégués par CCL).
# ---------------------------------------------------------------------------
Info 'Installation de pyinstaller (pip)…'
python -m pip install --upgrade pip
python -m pip install pyinstaller

# ---------------------------------------------------------------------------
# 3. Claude Code — installeur natif officiel (aucune dépendance Node.js).
# ---------------------------------------------------------------------------
Info 'Installation de Claude Code (installeur natif officiel)…'
irm https://claude.ai/install.ps1 | iex

# ---------------------------------------------------------------------------
# 4. Clone (lecture seule) du dépôt Bridge_Agent dans le dossier de travail.
# ---------------------------------------------------------------------------
if (-not (Test-Path $RepCCW)) { New-Item -ItemType Directory -Path $RepCCW | Out-Null }

if (Test-Path (Join-Path $RepDepot '.git')) {
    Info "Dépôt déjà cloné — mise à jour (git pull)…"
    git -C $RepDepot pull --ff-only
} else {
    Info "Clonage de $Depot dans $RepDepot…"
    git clone "https://github.com/$Depot.git" $RepDepot
}

# ---------------------------------------------------------------------------
# 5. Écriture de configs\ccw.conf.
#    REP_TRAVAIL pointe vers le partage CCW_Share via son chemin UNC
#    \\VBOXSVR\CCW_Share (accessible depuis LocalSystem, contrairement au
#    lecteur automonté en session interactive — issue #149).
#    TOPIC_NTFY est un placeholder à renseigner (comme le mot de passe phase 1).
# ---------------------------------------------------------------------------
$RepConfigs = Join-Path $RepDepot 'configs'
if (-not (Test-Path $RepConfigs)) { New-Item -ItemType Directory -Path $RepConfigs | Out-Null }
$CheminConf = Join-Path $RepConfigs 'ccw.conf'

# Chemin du répertoire de travail partagé hôte<->invité. On utilise le chemin
# UNC direct du partage VirtualBox (NOM_PARTAGE = "CCW_Share" en phase 1,
# creer_vm_ccw.py) plutôt que la lettre $LettrePartage : le service CCW-Watcher
# tourne sous LocalSystem (issue #148), qui ne voit pas les lecteurs réseau
# automontés en session interactive. \\VBOXSVR\<partage> reste, lui, accessible.
$RepTravail = "\\VBOXSVR\CCW_Share"

$contenuConf = @"
# configs/ccw.conf — Config du watcher pour l'agent Claude Code Windows (CCW).
# Généré par provisionner.ps1 (phase 2, issue #147). Format : CLE = valeur.

# ─── Requis ───────────────────────────────────────────────────────────────────
NOM         = ccw
DEPOT       = $Depot
LABEL       = for-windows
# REP_TRAVAIL : partage CCW_Share (phase 1), via son chemin UNC \\VBOXSVR\CCW_Share.
# Chemin UNC choisi car le service CCW-Watcher tourne sous LocalSystem (issue #148),
# qui n'a pas accès aux lecteurs réseau automontés en session interactive.
REP_TRAVAIL = $RepTravail

# ─── ntfy ─────────────────────────────────────────────────────────────────────
# PLACEHOLDER à renseigner LOCALEMENT (comme le mot de passe en phase 1).
# Ne PAS committer la valeur réelle du topic.
TOPIC_NTFY  = ###TOPIC_NTFY_A_DEFINIR###

# ─── Périmètre CCW (dossiers autorisés) ───────────────────────────────────────
PERIMETRE   = $RepTravail

# ─── Optionnels (défaut si commenté) ──────────────────────────────────────────
# INTERVALLE     = 10
# MAX_ESSAIS     = 3
# TIMEOUT_CLAUDE = 600
"@

Info "Écriture de $CheminConf…"
# UTF-8 sans BOM pour rester lisible par le parseur .conf de watcher.py.
[System.IO.File]::WriteAllText($CheminConf, $contenuConf, (New-Object System.Text.UTF8Encoding($false)))

# ---------------------------------------------------------------------------
# 6. Service Windows (NSSM) : lance le watcher au démarrage de la machine
#    (sans session ouverte), avec redémarrage automatique en cas d'échec.
#
#    ✅ Équivalent DIRECT des services systemd --user du §13 : démarrage au
#    boot sans session (SERVICE_AUTO_START), redémarrage automatique sur échec
#    (AppExit Default Restart + AppRestartDelay), et exécution sous LocalSystem
#    sans avoir à stocker les identifiants ccw-admin. NSSM remplace l'ancienne
#    tâche planifiée -AtLogOn, qui ne redémarrait pas au boot sans session.
#    Le watcher lui-même reste la première ligne de robustesse (boucle interne).
# ---------------------------------------------------------------------------
$NomService = 'CCW-Watcher'
$pythonExe  = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) { $pythonExe = 'python' }

# Fichier de log dédié au service (stdout/stderr capturés par NSSM).
$RepLogs = Join-Path $RepDepot 'logs'
if (-not (Test-Path $RepLogs)) { New-Item -ItemType Directory -Path $RepLogs | Out-Null }
$LogService = Join-Path $RepLogs 'ccw-service.log'

# Idempotence : si le service existe déjà, l'arrêter puis le supprimer avant
# de le recréer (script relançable sans erreur).
$svcExistant = Get-Service -Name $NomService -ErrorAction SilentlyContinue
if ($svcExistant) {
    Info "Service « $NomService » déjà présent — arrêt puis suppression avant recréation…"
    nssm stop   $NomService | Out-Null
    nssm remove $NomService confirm | Out-Null
}

Info "Enregistrement du service Windows « $NomService » (NSSM)…"

nssm install $NomService $pythonExe 'watcher.py --config configs\ccw.conf'
nssm set $NomService AppDirectory     $RepDepot
nssm set $NomService Start            SERVICE_AUTO_START
nssm set $NomService AppExit Default  Restart
nssm set $NomService AppRestartDelay  5000
# Rediriger stdout/stderr du service vers un fichier de log dédié.
nssm set $NomService AppStdout        $LogService
nssm set $NomService AppStderr        $LogService

# Démarrer immédiatement (le service repartira ensuite seul à chaque boot).
nssm start $NomService | Out-Null

# ---------------------------------------------------------------------------
# Fin.
# ---------------------------------------------------------------------------
Info 'Provisioning logiciel terminé.'
Info ''
Info 'RAPPEL — authentification Claude Code (à faire une fois, hors script) :'
Info '  • headless : setx ANTHROPIC_API_KEY "sk-ant-…"  (NE PAS committer)'
Info '  • interactif : claude auth login'
Info ''
Info "RAPPEL — renseigner TOPIC_NTFY dans $CheminConf (placeholder actuel)."
Info "Le service « $NomService » lance le watcher au démarrage (vérif : nssm status $NomService / Get-Service $NomService)."
