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

  Prérequis : Windows 11, exécution en administrateur. winget (App Installer)
  est bootstrappé automatiquement s'il est absent — cas des éditions LTSC/IoT
  sans Microsoft Store, comme la VM CCW-Build (issue #152).
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

# ---------------------------------------------------------------------------
# 1bis. Bootstrap de winget (App Installer) — NÉCESSAIRE sur Windows *LTSC / IoT*.
#
#   Les éditions LTSC / IoT Enterprise (comme la VM CCW-Build : Windows 11 IoT
#   Enterprise LTSC 2024) EXCLUENT délibérément le Microsoft Store. Or winget
#   (fourni par le paquet « App Installer » = Microsoft.DesktopAppInstaller)
#   dépend normalement du Store pour son installation et ses mises à jour
#   automatiques. Sur ces éditions, winget est donc ABSENT au départ : il faut
#   le déployer manuellement (msixbundle + licence) AVANT de l'utiliser pour
#   Git/gh/Python/NSSM. C'est ce que fait cette fonction (idempotente : si winget
#   est déjà là, elle ne fait rien — cas d'un Windows 11 « standard »).
#
#   Doc Microsoft Learn officielle sur winget :
#     https://learn.microsoft.com/windows/package-manager/winget/
#   Installation de winget sur les éditions sans Store (sideload App Installer) :
#     https://learn.microsoft.com/windows/package-manager/winget/#install-winget-on-windows-sandbox
#     https://learn.microsoft.com/windows/package-manager/winget/#install-winget-on-windows-server-and-non-store-editions
# ---------------------------------------------------------------------------
function Bootstrap-Winget {
    # (1) Déjà disponible ? Ne rien faire (Windows 11 standard, ou relance).
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Info 'winget déjà présent — bootstrap non nécessaire.'
        return
    }

    Info 'winget absent (édition LTSC/IoT sans Store) — bootstrap manuel de App Installer…'

    # -----------------------------------------------------------------------
    # CACHE PERSISTANT du msixbundle + licence (issue #158, suite #152).
    #
    #   Le partage CCW_Share (\\VBOXSVR\CCW_Share, monté en phase 1) vit côté
    #   hôte Linux et SURVIT aux resets/redémarrages de la VM : c'est un
    #   emplacement de cache idéal. Le téléchargement du msixbundle est la
    #   partie la plus longue du bootstrap ; le mettre en cache évite de le
    #   retélécharger à chaque test rapproché de lancer_provisioning.py.
    #
    #   PAS d'invalidation automatique (aucune vérification de version) : pour
    #   forcer un nouveau téléchargement (nouvelle version d'App Installer), il
    #   suffit de VIDER MANUELLEMENT le dossier de cache ci-dessous.
    # -----------------------------------------------------------------------
    $cacheDir   = '\\VBOXSVR\CCW_Share\cache\winget-bootstrap'
    $msixName   = 'Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle'
    $cacheMsix  = Join-Path $cacheDir $msixName

    $msixPath    = $null
    $licensePath = $null
    # $tmp reste $null en cas de cache utilisé : pas de dossier temporaire créé,
    # donc pas de nettoyage à faire en fin de fonction (voir plus bas).
    $tmp         = $null

    # Cache valide = le msixbundle attendu ET un fichier de licence (.xml) présents.
    $cacheLicense = $null
    if (Test-Path $cacheMsix) {
        $cacheLicense = Get-ChildItem -Path $cacheDir -Filter '*.xml' -ErrorAction SilentlyContinue |
            Select-Object -First 1
    }

    if ((Test-Path $cacheMsix) -and $cacheLicense) {
        # (2) Cache présent : on l'utilise directement, aucun accès réseau.
        $msixPath    = $cacheMsix
        $licensePath = $cacheLicense.FullName
        Info 'Utilisation du cache existant (pas de téléchargement).'
    } else {
        # (3) Cache absent (premier run, ou dossier vidé manuellement) : on
        #     télécharge comme avant, PUIS on peuple le cache pour le prochain test.

        # GitHub sert le release en HTTPS/TLS 1.2 ; PowerShell 5.1 ne le négocie pas
        # toujours par défaut. On le force pour éviter un échec TLS opaque.
        try {
            [Net.ServicePointManager]::SecurityProtocol = `
                [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        } catch {
            Avert "Impossible de forcer TLS 1.2 ($($_.Exception.Message)) — on tente quand même."
        }

        # Dossier temporaire dédié (nettoyé en fin de fonction).
        $tmp = Join-Path $env:TEMP ('winget-bootstrap-' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmp -Force | Out-Null

        $msixUrl    = 'https://github.com/microsoft/winget-cli/releases/latest/download/Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle'
        $msixPath   = Join-Path $tmp $msixName
        $licenseUrl = $null

        try {
            # (3a) Résoudre le nom EXACT du fichier de licence. L'URL "latest/download"
            #      du msixbundle est stable, mais le fichier de licence associé porte
            #      un nom versionné (ex. « <id>_License1.xml ») qui change à chaque
            #      release. On interroge donc l'API GitHub releases/latest (JSON) pour
            #      lister les assets de CETTE release et repérer le .xml de licence.
            #      NB : l'API GitHub exige un en-tête User-Agent.
            Info 'Résolution de la licence App Installer via l''API GitHub releases/latest…'
            $apiUrl = 'https://api.github.com/repos/microsoft/winget-cli/releases/latest'
            $release = Invoke-RestMethod -Uri $apiUrl -Headers @{ 'User-Agent' = 'CCW-provisionner' } `
                                         -UseBasicParsing
            $licenseAsset = $release.assets |
                Where-Object { $_.name -like '*License*.xml' -or $_.name -like '*_License*.xml' } |
                Select-Object -First 1
            if (-not $licenseAsset) {
                # Repli : n'importe quel .xml de la release (la licence est le seul .xml publié).
                $licenseAsset = $release.assets | Where-Object { $_.name -like '*.xml' } | Select-Object -First 1
            }
            if (-not $licenseAsset) {
                throw "aucun fichier de licence (.xml) trouvé dans les assets de la release winget-cli."
            }
            $licenseUrl  = $licenseAsset.browser_download_url
            $licensePath = Join-Path $tmp $licenseAsset.name
            Info "Licence détectée : $($licenseAsset.name)"

            # (3b) Téléchargements (msixbundle + licence).
            Info 'Téléchargement du msixbundle App Installer (dernière version)…'
            Invoke-WebRequest -Uri $msixUrl -OutFile $msixPath -UseBasicParsing
            Info 'Téléchargement du fichier de licence…'
            Invoke-WebRequest -Uri $licenseUrl -OutFile $licensePath -UseBasicParsing
        } catch {
            # (6) Erreur réseau (VM en NAT : accès sortant requis) — message clair,
            #     pas de stacktrace brut.
            throw ("Bootstrap winget échoué au TÉLÉCHARGEMENT : $($_.Exception.Message). " +
                   "La VM doit avoir un accès Internet sortant (NAT). " +
                   "Voir https://learn.microsoft.com/windows/package-manager/winget/ pour un dépannage manuel.")
        }

        # (3c) Peupler le cache persistant pour le prochain test. Le dossier est
        #      créé au besoin (New-Item -Force). Best-effort : un échec de copie
        #      (partage momentanément indispo) ne doit PAS faire échouer le
        #      provisioning — on retéléchargera simplement au run suivant.
        try {
            New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null
            Copy-Item -Path $msixPath    -Destination $cacheMsix -Force
            Copy-Item -Path $licensePath -Destination (Join-Path $cacheDir (Split-Path $licensePath -Leaf)) -Force
            Info "msixbundle + licence mis en cache dans $cacheDir."
        } catch {
            Avert "Impossible de peupler le cache ($($_.Exception.Message)) — le prochain run retéléchargera."
        }
    }

    # (3) Installation hors-ligne du paquet provisionné (Store non requis).
    try {
        Info 'Installation de App Installer (Add-AppxProvisionedPackage -Online)…'
        Add-AppxProvisionedPackage -Online -PackagePath $msixPath -LicensePath $licensePath | Out-Null
    } catch {
        Avert "Add-AppxProvisionedPackage a échoué ($($_.Exception.Message)) — tentative d'enregistrement direct ensuite."
    }

    # (4) Rafraîchir le PATH (idem bloc winget existant) puis re-vérifier.
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [System.Environment]::GetEnvironmentVariable('Path', 'User')

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        # 2e tentative : enregistrer le paquet pour l'utilisateur courant.
        try {
            Avert 'winget toujours absent après provisionnement — tentative Add-AppxPackage -RegisterByFamilyName…'
            Add-AppxPackage -RegisterByFamilyName -MainPackage 'Microsoft.DesktopAppInstaller_8wekyb3d8bbwe'
        } catch {
            Avert "Add-AppxPackage -RegisterByFamilyName a échoué : $($_.Exception.Message)."
        }
        $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                    [System.Environment]::GetEnvironmentVariable('Path', 'User')
    }

    # Nettoyage du dossier temporaire de travail (best-effort). SEUL le cache
    # persistant du partage est conservé — $tmp reste $null si le cache a été
    # utilisé (aucun téléchargement), auquel cas il n'y a rien à nettoyer.
    if ($tmp) { Remove-Item -Path $tmp -Recurse -Force -ErrorAction SilentlyContinue }

    # (5) Échec définitif : erreur claire, DISTINCTE de l'ancien « winget introuvable ».
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw ("Bootstrap winget échoué APRÈS téléchargement + enregistrement " +
               "(Add-AppxProvisionedPackage puis Add-AppxPackage -RegisterByFamilyName). " +
               "winget reste introuvable. Dépannage manuel : " +
               "https://learn.microsoft.com/windows/package-manager/winget/")
    }

    Info 'Bootstrap winget réussi — App Installer déployé.'
}

# Bootstrap AVANT le premier Installer-Winget : sur LTSC/IoT (VM CCW-Build) le
# Store est absent, winget n'est donc pas fourni d'office (issue #152, suite #151).
Bootstrap-Winget

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget introuvable malgré le bootstrap : App Installer indisponible. Abandon."
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
