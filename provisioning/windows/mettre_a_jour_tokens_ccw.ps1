<#
.SYNOPSIS
    Met à jour les tokens (GH_TOKEN, CLAUDE_CODE_OAUTH_TOKEN) du service
    Windows CCW-Watcher, sans manipulation manuelle de chaîne PowerShell.

.DESCRIPTION
    À exécuter DANS la VM CCW-Build (issue #168). Renouvellement des tokens
    (alignés ~90 j, cf. issue d'expiration #167) :

    1. Demande interactivement les deux valeurs en SecureString (elles ne
       restent pas affichées en clair une fois collées).
    2. Reconstruit la chaîne AppEnvironmentExtra
       « GH_TOKEN=…`nCLAUDE_CODE_OAUTH_TOKEN=… », le saut de ligne `n séparant
       les deux valeurs. ATTENTION : un simple espace entre elles corrompt
       silencieusement GH_TOKEN (constaté : erreur « Bad credentials »). Ce
       script supprime ce risque de syntaxe.
    3. Applique via « nssm set CCW-Watcher AppEnvironmentExtra … » puis
       redémarre le service (« nssm restart CCW-Watcher »).
    4. Attend quelques secondes, puis affiche les 10 dernières lignes de
       logs\ccw-service.log pour confirmer immédiatement l'absence d'erreur
       d'authentification, sans avoir à retaper la commande.
    5. Résumé final : OK si aucune ligne ERROR dans ces 10 lignes, sinon
       invite à vérifier manuellement.

    Le token en clair n'est JAMAIS affiché à l'écran : il n'existe en clair
    qu'en mémoire, le temps de construire la chaîne, puis les buffers non
    managés (BSTR) sont libérés.

.NOTES
    Écrit côté CCL (Linux) — non exécuté contre une VM réelle. Test manuel
    par Alain au prochain renouvellement de token.
#>

[CmdletBinding()]
param(
    # Nom du service Windows géré par NSSM.
    [string]$NomService = 'CCW-Watcher',
    # Dépôt cloné dans la VM (cf. provisionner.ps1, RepCCW\Bridge_Agent).
    [string]$RepDepot = 'C:\CCW\Bridge_Agent',
    # Secondes d'attente avant lecture des logs (laisser le watcher démarrer).
    [int]$DelaiSecondes = 6,
    # Nombre de lignes de log à afficher pour confirmation.
    [int]$NbLignesLog = 10
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Info($msg)  { Write-Host "[tokens] $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "[tokens] $msg" -ForegroundColor Green }
function Avert($msg) { Write-Host "[tokens] AVERTISSEMENT : $msg" -ForegroundColor Yellow }

# Convertit un SecureString en texte brut le temps strictement nécessaire,
# puis libère immédiatement le buffer non managé (BSTR).
function ConvertFrom-SecureStringPlain([System.Security.SecureString]$secure) {
    $ptr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

# ---------------------------------------------------------------------------
# 0. Vérifications préalables.
# ---------------------------------------------------------------------------
if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    Avert "Commande « nssm » introuvable dans le PATH. Ce script doit tourner DANS la VM CCW (NSSM installé par provisionner.ps1)."
    exit 1
}
if (-not (Get-Service -Name $NomService -ErrorAction SilentlyContinue)) {
    Avert "Service « $NomService » introuvable. Provisioning effectué ? (voir provisionner.ps1)."
    exit 1
}

$LogService = Join-Path $RepDepot 'logs\ccw-service.log'

# ---------------------------------------------------------------------------
# 1. Saisie interactive des deux valeurs (masquées).
# ---------------------------------------------------------------------------
Info 'Renouvellement des tokens du service CCW-Watcher.'
Info 'Colle chaque valeur quand demandé (elle ne restera pas affichée en clair).'
Write-Host ''

$secGh    = Read-Host -AsSecureString 'Collez la valeur de GH_TOKEN (depuis Bitwarden) '
$secOauth = Read-Host -AsSecureString 'Collez la valeur de CLAUDE_CODE_OAUTH_TOKEN (depuis Bitwarden) '

# ---------------------------------------------------------------------------
# 2. Construction de la chaîne AppEnvironmentExtra.
#    Le saut de ligne `n entre les deux paires est IMPÉRATIF (un espace
#    corrompt GH_TOKEN → « Bad credentials »). On travaille en clair le
#    strict minimum, sans jamais afficher la chaîne.
# ---------------------------------------------------------------------------
$gh    = ConvertFrom-SecureStringPlain $secGh
$oauth = ConvertFrom-SecureStringPlain $secOauth

if ([string]::IsNullOrWhiteSpace($gh) -or [string]::IsNullOrWhiteSpace($oauth)) {
    Avert 'Une des deux valeurs est vide — abandon, aucun changement appliqué.'
    exit 1
}

$envExtra = "GH_TOKEN=$gh`nCLAUDE_CODE_OAUTH_TOKEN=$oauth"

# ---------------------------------------------------------------------------
# 3. Application via NSSM puis redémarrage du service.
# ---------------------------------------------------------------------------
try {
    Info "Écriture de AppEnvironmentExtra sur « $NomService »…"
    nssm set $NomService AppEnvironmentExtra $envExtra | Out-Null

    Info "Redémarrage du service « $NomService »…"
    nssm restart $NomService | Out-Null
} finally {
    # Effacer les copies en clair de la mémoire dès que possible.
    $gh = $null; $oauth = $null; $envExtra = $null
    [System.GC]::Collect()
}

# ---------------------------------------------------------------------------
# 4. Attente puis affichage des dernières lignes de log pour confirmation.
# ---------------------------------------------------------------------------
Info "Attente de $DelaiSecondes s (démarrage du watcher)…"
Start-Sleep -Seconds $DelaiSecondes

Write-Host ''
Info "Dernières $NbLignesLog lignes de $LogService :"
Write-Host '----------------------------------------------------------------------'

$lignes = @()
if (Test-Path $LogService) {
    $lignes = @(Get-Content -Path $LogService -Encoding UTF8 -Tail $NbLignesLog)
    if ($lignes.Count -gt 0) {
        $lignes | ForEach-Object { Write-Host $_ }
    } else {
        Write-Host '(log vide)'
    }
} else {
    Avert "Fichier de log introuvable : $LogService"
}
Write-Host '----------------------------------------------------------------------'
Write-Host ''

# ---------------------------------------------------------------------------
# 5. Résumé : OK si aucune ligne ERROR dans les lignes affichées.
# ---------------------------------------------------------------------------
$erreurs = @($lignes | Where-Object { $_ -match 'ERROR|Bad credentials' })

if (-not (Test-Path $LogService)) {
    Avert 'Impossible de confirmer : log absent. Vérifie manuellement (nssm status CCW-Watcher).'
    exit 2
} elseif ($erreurs.Count -gt 0) {
    Avert "$($erreurs.Count) ligne(s) suspecte(s) (ERROR / Bad credentials) dans les $NbLignesLog dernières lignes."
    Avert 'À VÉRIFIER MANUELLEMENT : valeurs de tokens, séparateur, état du service.'
    exit 2
} else {
    Ok "Tokens mis à jour et service redémarré — aucune ligne ERROR dans les $NbLignesLog dernières lignes."
    Ok 'Tout semble OK. (Un doute ? Relis le log ci-dessus ou : Get-Content logs\ccw-service.log -Tail 30)'
    exit 0
}
