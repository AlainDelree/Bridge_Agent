<#
  configurer_ssh_ccw.ps1 — Configuration SSH du PC fixe CCW (issue #450).

  À lancer en PowerShell ADMINISTRATEUR sur le PC fixe CCW juste après une
  réinstallation Windows (Windows 11 IoT Enterprise LTSC, éval 90 jours,
  cf. §16.1 de BRIDGE_AGENT_DOC.md), AVANT toute connexion SSH depuis CCL.
  C'est la PREMIÈRE des deux étapes manuelles de remise en service du PC
  fixe, suivie de provisionner.ps1 (logiciels + service CCW-Watcher).

  Remplace la procédure faite manuellement lors de la bascule VM → PC
  physique (issue #447) : installation d'OpenSSH Server, règle pare-feu,
  clé publique CCL dans administrators_authorized_keys (accès SSH en tant
  qu'administrateur local, requis pour piloter le PC depuis l'onglet CCW),
  permissions du fichier de clés, activation de PubkeyAuthentication.

  Ce qu'il fait :
    1. installe la capacité Windows OpenSSH.Server (Add-WindowsCapability) ;
    2. démarre le service sshd et le passe en démarrage automatique ;
    3. ajoute une règle pare-feu entrante TCP/22 (nom standard Microsoft
       « OpenSSH-Server-In-TCP ») ;
    4. écrit la clé publique CCL (paramètre -ClePub) dans
       C:\ProgramData\ssh\administrators_authorized_keys ;
    5. corrige les permissions de ce fichier (SYSTEM + BUILTIN\Administrators
       en lecture/écriture, héritage désactivé — sinon sshd refuse la clé) ;
    6. force PubkeyAuthentication yes dans C:\ProgramData\ssh\sshd_config ;
    7. redémarre sshd pour appliquer la configuration.

  Paramètre :
    -ClePub <chaîne>  Clé publique ED25519 à installer — contenu de
                       ~/.ssh/ccl_ccw.pub sur CCL (Linux). Obligatoire.

  Idempotent : relançable sans dommage si une étape a déjà été faite
  (capacité déjà installée, règle pare-feu déjà présente, clé déjà dans
  authorized_keys, ligne déjà dans sshd_config — chaque étape vérifie
  l'état avant d'agir).

  Exemple :
    .\configurer_ssh_ccw.ps1 -ClePub "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5... ccl@bridge"
#>

[CmdletBinding()]
param(
    # Clé publique ED25519 de CCL (contenu de ~/.ssh/ccl_ccw.pub).
    [Parameter(Mandatory = $true)]
    [string]$ClePub
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Info($msg)  { Write-Host "[configurer_ssh_ccw] $msg" -ForegroundColor Cyan }
function Avert($msg) { Write-Host "[configurer_ssh_ccw] AVERTISSEMENT : $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------------------
# 0. Vérification élévation administrateur (toutes les étapes suivantes
#    l'exigent — mieux vaut échouer tôt avec un message clair).
# ---------------------------------------------------------------------------
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Ce script doit être lancé dans une console PowerShell ADMINISTRATEUR."
}

# ---------------------------------------------------------------------------
# 1. OpenSSH Server (capacité Windows).
# ---------------------------------------------------------------------------
Info 'Vérification de la capacité OpenSSH.Server…'
$capacite = Get-WindowsCapability -Online -Name 'OpenSSH.Server*' | Select-Object -First 1
if (-not $capacite) {
    throw "Capacité OpenSSH.Server introuvable sur ce Windows (Get-WindowsCapability)."
}
if ($capacite.State -ne 'Installed') {
    Info "Installation de la capacité $($capacite.Name)…"
    Add-WindowsCapability -Online -Name $capacite.Name | Out-Null
} else {
    Info 'OpenSSH Server déjà installé.'
}

# ---------------------------------------------------------------------------
# 2. Service sshd — démarrage automatique + démarré maintenant.
# ---------------------------------------------------------------------------
Info 'Configuration du service sshd (démarrage automatique)…'
Set-Service -Name sshd -StartupType Automatic
if ((Get-Service -Name sshd).Status -ne 'Running') {
    Start-Service sshd
    Info 'Service sshd démarré.'
} else {
    Info 'Service sshd déjà démarré.'
}

# ---------------------------------------------------------------------------
# 3. Règle pare-feu entrante TCP/22 (nom standard Microsoft, cf. doc
#    officielle OpenSSH Server sur Windows).
# ---------------------------------------------------------------------------
$NomRegle = 'OpenSSH-Server-In-TCP'
if (-not (Get-NetFirewallRule -Name $NomRegle -ErrorAction SilentlyContinue)) {
    Info "Ajout de la règle pare-feu $NomRegle (TCP/22 entrant)…"
    New-NetFirewallRule -Name $NomRegle -DisplayName 'OpenSSH Server (sshd)' `
        -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
} else {
    Info "Règle pare-feu $NomRegle déjà présente."
}

# ---------------------------------------------------------------------------
# 4. administrators_authorized_keys — installation de la clé publique CCL.
#    Fichier dédié aux comptes membres du groupe Administrators (documenté
#    par Microsoft) : sshd l'utilise à la place de ~\.ssh\authorized_keys
#    dès que l'utilisateur qui se connecte est administrateur local.
# ---------------------------------------------------------------------------
$RepSsh      = 'C:\ProgramData\ssh'
$FichierCles = Join-Path $RepSsh 'administrators_authorized_keys'
if (-not (Test-Path $RepSsh)) { New-Item -ItemType Directory -Path $RepSsh -Force | Out-Null }

$ClePubNettoyee = $ClePub.Trim()
$dejaPresente   = $false
if (Test-Path $FichierCles) {
    $dejaPresente = @(Get-Content $FichierCles -ErrorAction SilentlyContinue) -contains $ClePubNettoyee
}
if (-not $dejaPresente) {
    Add-Content -Path $FichierCles -Value $ClePubNettoyee -Encoding ascii
    Info "Clé publique ajoutée à $FichierCles."
} else {
    Info "Clé publique déjà présente dans $FichierCles."
}

# ---------------------------------------------------------------------------
# 5. Permissions strictes du fichier de clés (SYSTEM + Administrators
#    uniquement, héritage désactivé) — sshd refuse authorized_keys si les
#    permissions sont trop ouvertes (comportement documenté OpenSSH Windows).
# ---------------------------------------------------------------------------
Info 'Correction des permissions de administrators_authorized_keys…'
icacls.exe $FichierCles /inheritance:r | Out-Null
icacls.exe $FichierCles /grant 'SYSTEM:F' | Out-Null
icacls.exe $FichierCles /grant 'BUILTIN\Administrators:F' | Out-Null

# ---------------------------------------------------------------------------
# 6. sshd_config — PubkeyAuthentication yes (requis pour l'auth par clé ;
#    absent ou commenté par défaut sur certaines éditions).
# ---------------------------------------------------------------------------
$FichierConfig = Join-Path $RepSsh 'sshd_config'
$dejaActive = $false
if (Test-Path $FichierConfig) {
    $dejaActive = (Get-Content $FichierConfig) -match '^\s*PubkeyAuthentication\s+yes\s*$'
}
if (-not $dejaActive) {
    Add-Content -Path $FichierConfig -Value 'PubkeyAuthentication yes'
    Info 'PubkeyAuthentication yes ajouté à sshd_config.'
} else {
    Info 'PubkeyAuthentication déjà activé dans sshd_config.'
}

# ---------------------------------------------------------------------------
# 7. Redémarrage de sshd pour appliquer sshd_config.
# ---------------------------------------------------------------------------
Info 'Redémarrage du service sshd…'
Restart-Service sshd

Info 'Configuration SSH terminée — connexion possible depuis CCL (ssh AlainW@<hôte>).'
