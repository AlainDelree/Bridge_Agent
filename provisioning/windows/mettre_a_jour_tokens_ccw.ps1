<#
.SYNOPSIS
    Met à jour les tokens (GH_TOKEN, CLAUDE_CODE_OAUTH_TOKEN) du service
    Windows CCW-Watcher, sans manipulation manuelle de chaîne PowerShell.

.DESCRIPTION
    À exécuter DANS la VM CCW-Build (issue #168). Renouvellement des tokens
    (alignés ~90 j, cf. issue d'expiration #167) :

    1. Récupère les deux valeurs SANS les passer en argument de commande :
       soit interactivement en SecureString (elles ne restent pas affichées en
       clair une fois collées), soit — avec -FichierTokens (issue #174) — en les
       lisant dans un fichier « clé=valeur » poussé par l'appelant. Ce second
       mode permet à l'onglet CCW (interface web, Linux) de poser les tokens à
       distance via guestcontrol sans saisie manuelle dans la VM.

       Issue #743 : UN SEUL des deux tokens peut être fourni (vide/absent du
       fichier accepté pour l'autre) — au moins un est requis. Le token omis
       est alors reconduit TEL QUEL depuis l'environnement ACTUEL du service
       (« nssm get <service> AppEnvironmentExtra », jamais affiché ni écrit
       sur disque en dehors de la mise à jour du service elle-même). Si cette
       lecture échoue ou que la variable y est absente, abandon SANS AUCUNE
       modification, avec un message clair demandant de fournir les deux
       tokens. Comportement inchangé quand les deux tokens sont fournis.
    2. Reconstruit AppEnvironmentExtra comme TROIS lignes distinctes : PATH
       (machine + <CompteService>\.local\bin + WindowsApps), GH_TOKEN,
       CLAUDE_CODE_OAUTH_TOKEN — issue #658, point 1. AVANT cette issue, la
       ligne PATH posée par provisionner.ps1 lors du provisioning initial
       était PERDUE ici, puisque « nssm set … AppEnvironmentExtra » REMPLACE
       toute la valeur au lieu de l'étendre : un service recréé sans PATH ne
       voit alors ni claude.exe ni les autres exécutables per-user, même si
       la session interactive du même compte les trouve sans problème. Le
       PATH est donc reconstruit ICI À NEUF (pas préservé tel quel : il peut
       avoir changé depuis le provisioning, ex. nouvelle installation entre
       temps) plutôt qu'écrasé. ATTENTION séparateur : constaté le 27/09/2026
       — une chaîne UNIQUE avec des `n comme séparateur ENTRE les lignes ne
       fonctionne PAS avec « nssm set » ; chaque ligne doit être un argument
       SÉPARÉ (nssm set $Nom AppEnvironmentExtra $ligne1 $ligne2 $ligne3).
       Réconcilié avec l'ancien commentaire « BUG #558 » d'ajouter_projet_ccw.ps1
       par l'issue #659 : ce fix #558 avait été appliqué par seule lecture du
       code (jamais reproduit sur nssm réel, jamais testé avec une ligne PATH,
       absente d'AppEnvironmentExtra à l'époque) — les arguments séparés sont
       désormais la SEULE méthode dans tout le dépôt (ajouter_projet_ccw.ps1 et
       creer_projet_ccw_complet.ps1 alignés pareil).
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
    # Nom du fichier de log du service, dans <RepDepot>\logs. Par défaut celui de
    # CCW-Watcher (mono-projet) ; pour un service multi-projets CCW-Watcher-<Nom>,
    # passer 'ccw-<nom>-service.log' (cf. ajouter_projet_ccw.ps1, issue #173).
    [string]$NomLog = 'ccw-service.log',
    # Mode NON interactif (issue #174) : chemin d'un fichier « clé=valeur » (UTF-8)
    # contenant les lignes GH_TOKEN=… et CLAUDE_CODE_OAUTH_TOKEN=…. Quand ce
    # paramètre est fourni, les valeurs sont LUES depuis ce fichier au lieu d'être
    # demandées interactivement (Read-Host) — c'est ce qui permet de piloter la
    # pose des tokens à distance depuis l'onglet CCW de l'interface web (Linux)
    # sans jamais passer les secrets en argument de ligne de commande. Le fichier
    # est fourni par l'appelant (poussé via guestcontrol copyto, permissions
    # restreintes) et supprimé par lui ; ce script ne l'écrit ni ne le supprime.
    [string]$FichierTokens = '',
    # Secondes d'attente avant lecture des logs (laisser le watcher démarrer).
    [int]$DelaiSecondes = 6,
    # Nombre de lignes de log à afficher pour confirmation.
    [int]$NbLignesLog = 10,
    # Compte Windows sous lequel tourne le service (NSSM ObjectName) — même
    # défaut que provisionner.ps1. Utilisé pour reconstruire la ligne PATH de
    # AppEnvironmentExtra (issue #658, point 1) : .local\bin et WindowsApps du
    # compte de service, sans lesquels le service ne verrait ni claude.exe ni
    # les autres exécutables per-user.
    [string]$CompteService = 'AlainW'
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

# Lit une valeur « CLE=valeur » dans un fichier clé=valeur (mode non interactif,
# issue #174). Renvoie la valeur brute (tout ce qui suit le premier « = », sans
# rognage des espaces internes ; seuls le CR/LF de fin sont retirés). Renvoie
# $null si la clé est absente. La valeur n'est jamais affichée.
function Lire-ValeurFichier([string]$chemin, [string]$cle) {
    foreach ($ligne in [System.IO.File]::ReadAllLines($chemin)) {
        $idx = $ligne.IndexOf('=')
        if ($idx -lt 1) { continue }
        if ($ligne.Substring(0, $idx).Trim() -eq $cle) {
            return $ligne.Substring($idx + 1).TrimEnd("`r", "`n")
        }
    }
    return $null
}

# Lit la valeur ACTUELLE de `$cle` dans AppEnvironmentExtra du service, via
# « nssm get » (issue #743 — permet de reconduire un token non fourni sans
# effacer l'autre, puisque « nssm set » REMPLACE toute la valeur). Chaque
# variable occupe sa propre ligne dans la sortie de « nssm get » (même
# convention que ce script lui-même pose, voir section 2 ci-dessous) : même
# algorithme de recherche que Lire-ValeurFichier, appliqué aux lignes de
# sortie plutôt qu'à un fichier. $null si la lecture échoue (service/nssm
# indisponible) ou que la variable est absente. La valeur n'est NI affichée
# NI écrite sur disque — elle ne sort jamais de cette fonction/de l'appelant
# direct qui la réinjecte dans AppEnvironmentExtra.
function Lire-EnvironnementActuelService([string]$nomService, [string]$cle) {
    $lignes = & nssm get $nomService AppEnvironmentExtra 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $lignes) { return $null }
    foreach ($ligne in @($lignes)) {
        $idx = $ligne.IndexOf('=')
        if ($idx -lt 1) { continue }
        if ($ligne.Substring(0, $idx).Trim() -eq $cle) {
            return $ligne.Substring($idx + 1).TrimEnd("`r", "`n")
        }
    }
    return $null
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

$LogService = Join-Path $RepDepot (Join-Path 'logs' $NomLog)

# ---------------------------------------------------------------------------
# 1. Récupération des deux valeurs.
#    Deux sources possibles, JAMAIS en argument de ligne de commande :
#      • interactif (défaut) : Read-Host -AsSecureString (jamais affiché) ;
#      • non interactif (-FichierTokens) : lecture d'un fichier clé=valeur
#        poussé par l'appelant (onglet CCW, issue #174). Utile pour piloter la
#        pose des tokens à distance sans saisie manuelle dans la VM.
# ---------------------------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($FichierTokens)) {
    Info 'Renouvellement des tokens du service CCW-Watcher.'
    Info 'Colle chaque valeur quand demandé (elle ne restera pas affichée en clair).'
    Write-Host ''

    $secGh    = Read-Host -AsSecureString 'Collez la valeur de GH_TOKEN (depuis Bitwarden) '
    $secOauth = Read-Host -AsSecureString 'Collez la valeur de CLAUDE_CODE_OAUTH_TOKEN (depuis Bitwarden) '

    $gh    = ConvertFrom-SecureStringPlain $secGh
    $oauth = ConvertFrom-SecureStringPlain $secOauth
} else {
    if (-not (Test-Path $FichierTokens)) {
        Avert "Fichier de tokens introuvable : $FichierTokens — abandon."
        exit 1
    }
    Info 'Lecture des tokens depuis le fichier fourni (mode non interactif)…'
    $gh    = Lire-ValeurFichier $FichierTokens 'GH_TOKEN'
    $oauth = Lire-ValeurFichier $FichierTokens 'CLAUDE_CODE_OAUTH_TOKEN'
}

# ---------------------------------------------------------------------------
# 2. Résolution des DEUX valeurs : au moins une doit être fournie (issue
#    #743). Celle qui est vide/absente est reconduite depuis l'environnement
#    ACTUEL du service (Lire-EnvironnementActuelService, ci-dessus) — jamais
#    affichée ni écrite sur disque. Si elle y est introuvable (service neuf,
#    lecture impossible), abandon SANS AUCUNE modification : au moins un
#    jeton composé reste requis dans ce cas précis, message clair.
# ---------------------------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($gh) -and [string]::IsNullOrWhiteSpace($oauth)) {
    Avert 'Aucun jeton fourni — abandon, aucun changement appliqué. Fournissez au moins GH_TOKEN ou CLAUDE_CODE_OAUTH_TOKEN.'
    exit 1
}
if ([string]::IsNullOrWhiteSpace($gh)) {
    Info 'GH_TOKEN non fourni — lecture de sa valeur actuelle sur le service…'
    $gh = Lire-EnvironnementActuelService $NomService 'GH_TOKEN'
    if ([string]::IsNullOrWhiteSpace($gh)) {
        Avert "GH_TOKEN non fourni et introuvable dans l'environnement actuel du service « $NomService » — abandon, aucun changement appliqué. Fournissez les deux tokens."
        exit 1
    }
}
if ([string]::IsNullOrWhiteSpace($oauth)) {
    Info 'CLAUDE_CODE_OAUTH_TOKEN non fourni — lecture de sa valeur actuelle sur le service…'
    $oauth = Lire-EnvironnementActuelService $NomService 'CLAUDE_CODE_OAUTH_TOKEN'
    if ([string]::IsNullOrWhiteSpace($oauth)) {
        Avert "CLAUDE_CODE_OAUTH_TOKEN non fourni et introuvable dans l'environnement actuel du service « $NomService » — abandon, aucun changement appliqué. Fournissez les deux tokens."
        exit 1
    }
}

# ---------------------------------------------------------------------------
# 3. Construction des TROIS lignes de AppEnvironmentExtra (PATH, GH_TOKEN,
#    CLAUDE_CODE_OAUTH_TOKEN) — issue #658, point 1.
#
#    PATH reconstruit À NEUF (pas préservé depuis l'ancienne valeur) : « nssm
#    set … AppEnvironmentExtra » REMPLACE toute la valeur au lieu de
#    l'étendre, donc sans cette ligne le service perdrait tout accès à
#    claude.exe et aux autres exécutables per-user — constaté le 27/09/2026.
#
#    Chaque ligne est un argument SÉPARÉ passé à « nssm set » (voir plus bas) :
#    une chaîne UNIQUE avec des `n comme séparateur ne fonctionne PAS
#    (constaté le 27/09/2026 — contredit le commentaire « BUG #558 »
#    d'ajouter_projet_ccw.ps1, à réconcilier séparément si confirmé plus
#    largement). On travaille en clair le strict minimum, sans jamais
#    afficher les valeurs.
# ---------------------------------------------------------------------------

$cheminLocalBin = "C:\Users\$CompteService\.local\bin"
$cheminWindowsApps = "C:\Users\$CompteService\AppData\Local\Microsoft\WindowsApps"
$pathMachine = [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
$lignePath  = "PATH=$pathMachine;$cheminLocalBin;$cheminWindowsApps"
$ligneGh    = "GH_TOKEN=$gh"
$ligneOauth = "CLAUDE_CODE_OAUTH_TOKEN=$oauth"

# ---------------------------------------------------------------------------
# 4. Application via NSSM puis redémarrage du service.
# ---------------------------------------------------------------------------
try {
    Info "Écriture de AppEnvironmentExtra sur « $NomService » (PATH + GH_TOKEN + CLAUDE_CODE_OAUTH_TOKEN)…"
    nssm set $NomService AppEnvironmentExtra $lignePath $ligneGh $ligneOauth | Out-Null

    Info "Redémarrage du service « $NomService »…"
    nssm restart $NomService | Out-Null
} finally {
    # Effacer les copies en clair de la mémoire dès que possible.
    $gh = $null; $oauth = $null; $lignePath = $null; $ligneGh = $null; $ligneOauth = $null
    [System.GC]::Collect()
}

# ---------------------------------------------------------------------------
# 5. Attente puis affichage des dernières lignes de log pour confirmation.
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
# 6. Résumé : OK si aucune ligne ERROR dans les lignes affichées.
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
