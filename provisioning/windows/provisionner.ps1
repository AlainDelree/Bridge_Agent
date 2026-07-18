<#
  provisionner.ps1 — Provisioning LOGICIEL de la VM Windows CCW (phase 2, issue #147).

  Ce script s'exécute DANS la VM « CCW-Build » (créée en phase 1, issue #146),
  soit au premier logon, soit manuellement dans une console PowerShell élevée.
  Il installe l'outillage nécessaire à l'agent Claude Code Windows (CCW) puis
  met en place la tâche planifiée qui lancera le watcher au démarrage.

  Il est POUSSÉ et EXÉCUTÉ à distance depuis CCL par lancer_provisioning.py
  (VBoxManage guestcontrol) — mais reste utilisable seul.

  Ce qu'il fait :
    1. installe via winget : Git, GitHub CLI (gh), Python 3 ;
    2. installe pyinstaller (pip) — requis pour les builds .exe délégués ;
    3. installe Claude Code via l'installeur natif officiel (pas de Node.js) :
         irm https://claude.ai/install.ps1 | iex
    4. clone AlainDelree/Bridge_Agent (lecture seule) dans C:\CCW\Bridge_Agent ;
    5. écrit configs\ccw.conf (LABEL=for-windows, NOM=ccw, …) ;
    6. enregistre une tâche planifiée qui lance le watcher à l'ouverture de
       session, avec redémarrage automatique en cas d'échec.

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
  le clone est mis à jour par pull, la tâche planifiée est ré-enregistrée).

  Prérequis : Windows 11 (winget présent), exécution en administrateur.
#>

[CmdletBinding()]
param(
    # Dossier de travail dédié côté invité.
    [string]$RepCCW = 'C:\CCW',
    # Dépôt cloné (lecture seule).
    [string]$Depot = 'AlainDelree/Bridge_Agent',
    # Lettre du lecteur réseau où VirtualBox automonte le partage CCW_Share
    # (phase 1 : sharedfolder add … --automount). Adapter si VBox choisit
    # une autre lettre ; \\VBOXSVR\CCW_Share reste le chemin UNC de repli.
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
#    REP_TRAVAIL pointe vers le partage CCW_Share automonté (phase 1).
#    TOPIC_NTFY est un placeholder à renseigner (comme le mot de passe phase 1).
# ---------------------------------------------------------------------------
$RepConfigs = Join-Path $RepDepot 'configs'
if (-not (Test-Path $RepConfigs)) { New-Item -ItemType Directory -Path $RepConfigs | Out-Null }
$CheminConf = Join-Path $RepConfigs 'ccw.conf'

# Chemin du répertoire de travail partagé hôte<->invité (lecteur automonté).
$RepTravail = "$LettrePartage\Bridge_Agent_CCW_Share"

$contenuConf = @"
# configs/ccw.conf — Config du watcher pour l'agent Claude Code Windows (CCW).
# Généré par provisionner.ps1 (phase 2, issue #147). Format : CLE = valeur.

# ─── Requis ───────────────────────────────────────────────────────────────────
NOM         = ccw
DEPOT       = $Depot
LABEL       = for-windows
# REP_TRAVAIL : dossier partagé CCW_Share automonté par VirtualBox (phase 1).
# Adapter la lettre si VBox monte le partage ailleurs (\\VBOXSVR\CCW_Share).
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
# 6. Tâche planifiée : lance le watcher à l'ouverture de session, avec
#    redémarrage automatique en cas d'échec.
#
#    ⚠️ LIMITE vs systemd Restart=always (§13) : Task Scheduler ne propose PAS
#    de relance infinie native. On approche le comportement avec les paramètres
#    de répétition en cas d'échec (RestartCount / RestartInterval) : ici 999
#    tentatives espacées d'1 minute — soit ~16 h de résilience, PAS l'infini.
#    Le watcher lui-même reste la première ligne de robustesse (boucle interne).
# ---------------------------------------------------------------------------
$NomTache  = 'CCW-Watcher'
$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) { $pythonExe = 'python' }

Info "Enregistrement de la tâche planifiée « $NomTache »…"

$action = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument 'watcher.py --config configs\ccw.conf' `
    -WorkingDirectory $RepDepot

# Déclencheur : à l'ouverture de session de l'utilisateur courant.
$trigger = New-ScheduledTaskTrigger -AtLogOn

# Paramètres : relance en cas d'échec (approximation de Restart=always).
$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

# S'exécute sous l'utilisateur connecté (ccw-admin), au plus haut niveau.
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $NomTache `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

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
Info "La tâche « $NomTache » lancera le watcher à la prochaine ouverture de session."
