# creer_projet_ccw_complet.ps1
#
# Enchaine TOUTES les etapes mecaniques pour ajouter un projet CCW
# (issue #492) : clone + .conf + service NSSM + PATH correct des le depart
# (evite le piege rencontre avec Scrabble : services NSSM demarres au boot
# n'heritent pas du PATH utilisateur, notamment %USERPROFILE%\.local\bin
# ou vit claude.exe).
#
# Ne demande QUE ce qui ne peut pas etre automatise : les deux tokens.
# Le reste (nom, depot, dossiers, service) est deduit du nom de projet.
#
# Usage :
#   cd C:\CCW\Bridge_Agent
#   powershell -ExecutionPolicy Bypass -File creer_projet_ccw_complet.ps1 -NomProjet actualise -Depot AlainDelree/Actualise
#
# Avant de lancer : cree le token GitHub dedie (repo unique, Issues=RW,
# Metadata=RO, expiration alignee ~2026-11-14 comme les tokens CCW recents)
# sur github.com/settings/tokens, et prepare `claude setup-token` en tete.

param(
    [Parameter(Mandatory=$true)][string]$NomProjet,
    [Parameter(Mandatory=$true)][string]$Depot,
    [string]$TopicNtfy = "hippocampe-ff-galerie-xyz123"
)

$ErrorActionPreference = "Stop"

# Helpers d'affichage (Info/Ok/Avert) et dérivation de chemins projet,
# communs aux scripts CCW locaux (issue #606).
Import-Module (Join-Path $PSScriptRoot 'provisioning\windows\ccw-commun.psm1') -Force
Set-PrefixeCcw 'creer-projet-complet'

$chemins      = Get-CheminsProjetCcw -NomProjet $NomProjet
$NomService   = $chemins.NomService
$RepTravail   = $chemins.RepDepot
$NomLog       = $chemins.NomLog
$CheminClaude = Join-Path $env:USERPROFILE ".local\bin"

# Convertit un SecureString en texte brut le temps strictement necessaire,
# puis libere immediatement le buffer non manage (BSTR) - le secret ne
# reste pas en memoire jusqu'au GC (meme pattern que
# provisioning\windows\mettre_a_jour_tokens_ccw.ps1).
function ConvertFrom-SecureStringPlain([System.Security.SecureString]$Secure) {
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try {
        return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

Info "Projet      : $NomProjet"
Info "Depot       : $Depot"
Info "Dossier     : $RepTravail"
Info "Service     : $NomService"
Write-Host ""

# --- Etape 1 : clone + .conf + service (scripts officiels existants) -------
Info "Etape 1/3 - ajouter_projet_ccw.ps1..."
powershell -ExecutionPolicy Bypass -File provisioning\windows\ajouter_projet_ccw.ps1 -NomProjet $NomProjet -Depot $Depot

# --- Etape 2 : TOPIC_NTFY (edition ciblee, meme logique que finaliser_projet_ccw.ps1) ---
Write-Host ""
Info "Etape 2/3 - TOPIC_NTFY..."
$cheminConfComplet = $chemins.CheminConf
if (-not (Test-Path $cheminConfComplet)) {
    Avert ".conf introuvable a $cheminConfComplet -- recherche automatique..."
    $trouve = Get-ChildItem -Path "C:\CCW" -Filter $chemins.NomConf -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($trouve) {
        $cheminConfComplet = $trouve.FullName
        Info "Trouve : $cheminConfComplet"
    } else {
        Avert "ERREUR : impossible de trouver le .conf. Arret."
        exit 1
    }
}
$contenuConfMaj = (Get-Content $cheminConfComplet -Raw) -replace '###TOPIC_NTFY_A_DEFINIR###', $TopicNtfy
[System.IO.File]::WriteAllText($cheminConfComplet, $contenuConfMaj, (New-Object System.Text.UTF8Encoding($false)))
Ok "TOPIC_NTFY defini a $TopicNtfy."

# --- Etape 3 : tokens + PATH correct (LA partie qui a pose probleme pour Scrabble) ---
Write-Host ""
Info "Etape 3/3 - Tokens et PATH"
Info "Cree le token GitHub dedie si pas deja fait :"
Info "  - Repository access -> $Depot UNIQUEMENT"
Info "  - Permissions : Issues = Read and write, Metadata = Read-only"
Info "  - Expiration : aligne-toi sur les tokens CCW recents (~2026-11-14)"
Write-Host ""
Read-Host "Appuie sur Entree une fois le token GitHub cree et copie (rien a taper ici)"

$ghToken = Read-Host "Colle la valeur de GH_TOKEN" -AsSecureString
$ghTokenPlain = ConvertFrom-SecureStringPlain $ghToken

Write-Host ""
Info "Genere maintenant le token Claude Code :"
Info "  claude setup-token"
Info "(lance-le dans un AUTRE terminal si besoin, puis reviens ici)"
Write-Host ""
$claudeToken = Read-Host "Colle la valeur de CLAUDE_CODE_OAUTH_TOKEN" -AsSecureString
$claudeTokenPlain = ConvertFrom-SecureStringPlain $claudeToken

# Nettoyage anti-saut-de-ligne (piege rencontre avec Scrabble : un token
# affiche sur 2 lignes visuellement par le terminal peut etre colle avec un
# vrai retour a la ligne inclus -> "Invalid Authorization header value").
$ghTokenPlain = $ghTokenPlain -replace "`r`n|`n|`r", ""
$claudeTokenPlain = $claudeTokenPlain -replace "`r`n|`n|`r", ""

Write-Host ""
Info "Longueur GH_TOKEN : $($ghTokenPlain.Length) caracteres"
Info "Longueur CLAUDE_CODE_OAUTH_TOKEN : $($claudeTokenPlain.Length) caracteres"
if ($ghTokenPlain.Length -eq 0 -or $claudeTokenPlain.Length -eq 0) {
    Avert "ERREUR : un des deux tokens est vide (saisie ratee). Arret."
    exit 1
}

# Test des DEUX tokens en isolation AVANT de les appliquer au service (issue
# #492 bis : mieux vaut echouer ici, vite et clairement, que decouvrir un 401
# apres redemarrage du service en devinant depuis les logs).
Write-Host ""
Info "Test du GH_TOKEN sur $Depot ..."
$env:GH_TOKEN = $ghTokenPlain
$testGh = gh repo view $Depot 2>&1
if ($LASTEXITCODE -ne 0) {
    Avert "ERREUR : GH_TOKEN invalide ou mal scope sur $Depot"
    Write-Host $testGh
    Avert "Verifie le token sur github.com/settings/tokens (repository access, expiration) et relance."
    exit 1
}
Ok "GH_TOKEN OK."

Info "Test du CLAUDE_CODE_OAUTH_TOKEN..."
$env:CLAUDE_CODE_OAUTH_TOKEN = $claudeTokenPlain
$testClaude = claude --print "reponds juste OK" 2>&1
if ($LASTEXITCODE -ne 0) {
    Avert "ERREUR : CLAUDE_CODE_OAUTH_TOKEN invalide"
    Write-Host $testClaude
    Avert "Regenere-le avec : claude setup-token"
    exit 1
}
Ok "CLAUDE_CODE_OAUTH_TOKEN OK."

# PATH complet + dossier claude.exe explicite (LE fix du probleme Scrabble :
# un service NSSM demarre au boot n'herite pas forcement du PATH utilisateur
# ou vit claude.exe sous %USERPROFILE%\.local\bin).
$pathActuel = $env:PATH
$nouvelExtra = "GH_TOKEN=$ghTokenPlain`nCLAUDE_CODE_OAUTH_TOKEN=$claudeTokenPlain`nPATH=$pathActuel;$CheminClaude"

Write-Host ""
Info "Ecriture de AppEnvironmentExtra (avec PATH incluant $CheminClaude)..."
nssm set $NomService AppEnvironmentExtra $nouvelExtra | Out-Null

Info "Redemarrage du service $NomService ..."
nssm restart $NomService | Out-Null
Start-Sleep -Seconds 8

Write-Host ""
Info "Dernieres lignes de $RepTravail\logs\$NomLog :"
Write-Host "----------------------------------------------------------------------"
Get-Content "$RepTravail\logs\$NomLog" -Tail 10
Write-Host "----------------------------------------------------------------------"
Write-Host ""
Ok "Projet $NomProjet cree et finalise."
Info "Verif : nssm status $NomService  /  Get-Service $NomService"
Info "Si erreur 401 ci-dessus : le GH_TOKEN a probablement un espace ou saut de ligne parasite. Relance uniquement l etape des tokens en collant plus prudemment."
