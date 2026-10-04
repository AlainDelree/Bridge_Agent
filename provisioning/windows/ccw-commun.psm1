<#
  ccw-commun.psm1 — Helpers communs aux scripts CCW LOCAUX (issue #606, suite
  du diagnostic #579 et de l'étude de faisabilité #604).

  Regroupe ce qui était dupliqué entre creer_projet_ccw_complet.ps1 (racine du
  dépôt), provisioning\windows\ajouter_projet_ccw.ps1 et
  provisioning\windows\finaliser_projet_ccw.ps1 :

    - Info / Ok / Avert    : affichage coloré préfixé (Write-Host). Le préfixe
                              (ex. « ajouter-projet ») est fixé UNE FOIS par
                              script appelant via Set-PrefixeCcw, juste après
                              Import-Module — les appels Info/Ok/Avert restent
                              ensuite identiques à l'existant, sans argument
                              de préfixe à répéter.
    - Get-CheminsProjetCcw : dérivation NomService / RepDepot / NomConf /
                              NomLog / CheminConf à partir du seul NomProjet,
                              avec le cas spécial « Bridge_Agent » (service
                              « CCW-Watcher » SANS suffixe, config ccw.conf,
                              log ccw-service.log — projet historique créé par
                              provisionner.ps1 avant la généralisation
                              multi-projets, issue #170). Même convention que
                              lister_projets_ccw.ps1 et
                              finaliser_projet_ccw_auto.ps1 (scripts DISTANTS,
                              non touchés par cette issue — leur autonomie est
                              délibérée).
    - Lire-ValeurFichier   : lecture d'une clé dans un fichier « clé = valeur »
                              (.conf), reprise de mettre_a_jour_tokens_ccw.ps1
                              (script distant, non touché — logique dupliquée
                              ici à l'identique pour les scripts locaux).

  Import (chemin relatif adapté à la position de chaque script appelant) :
    Import-Module (Join-Path $PSScriptRoot 'ccw-commun.psm1') -Force
  ou, depuis la racine du dépôt (creer_projet_ccw_complet.ps1) :
    Import-Module (Join-Path $PSScriptRoot 'provisioning\windows\ccw-commun.psm1') -Force

  NE PAS étendre ce module aux scripts DISTANTS (finaliser_projet_ccw_auto.ps1,
  mettre_a_jour_tokens_ccw.ps1, lister_projets_ccw.ps1) : poussés SEULS par
  SCP (app/ccw.py), leur autonomie sans dépendance externe est délibérée et
  documentée (#604). Seul ajouter_projet_ccw.ps1 fait exception : il est à la
  fois un script LOCAL (appelé depuis le clone git) et poussé seul par SCP
  (app/ccw.py::ccw_ajouter_projet) — ce module doit donc être ajouté à la même
  liste de fichiers copiés que lui (1 seul point d'ajout dans app/ccw.py).
#>

Set-StrictMode -Version Latest

# Préfixe utilisé par Info/Ok/Avert, fixé par le script appelant via
# Set-PrefixeCcw. Portée module (persiste entre les appels, comme un état
# statique) — sans effet sur d'autres scripts, chaque script appelant tourne
# dans son propre processus powershell.exe.
$script:PrefixeCcw = 'ccw'

function Set-PrefixeCcw {
    param([Parameter(Mandatory=$true)][string]$Prefixe)
    $script:PrefixeCcw = $Prefixe
}

function Info([string]$Msg)  { Write-Host "[$script:PrefixeCcw] $Msg" -ForegroundColor Cyan }
function Ok([string]$Msg)    { Write-Host "[$script:PrefixeCcw] $Msg" -ForegroundColor Green }
function Avert([string]$Msg) { Write-Host "[$script:PrefixeCcw] AVERTISSEMENT : $Msg" -ForegroundColor Yellow }

# Dérive les chemins/noms d'un projet CCW à partir du seul NomProjet — même
# logique que finaliser_projet_ccw_auto.ps1 / lister_projets_ccw.ps1 (cas
# spécial Bridge_Agent inclus).
function Get-CheminsProjetCcw {
    param(
        [Parameter(Mandatory=$true)][string]$NomProjet,
        [string]$RepCCW = 'C:\CCW'
    )
    if ($NomProjet -ieq 'Bridge_Agent') {
        $nomService = 'CCW-Watcher'
        $repDepot   = Join-Path $RepCCW 'Bridge_Agent'
        $nomConf    = 'ccw.conf'
        $nomLog     = 'ccw-service.log'
    } else {
        $nomMin     = $NomProjet.ToLowerInvariant()
        $nomService = "CCW-Watcher-$NomProjet"
        $repDepot   = Join-Path $RepCCW $NomProjet
        $nomConf    = "$nomMin-ccw.conf"
        $nomLog     = "ccw-$nomMin-service.log"
    }
    [PSCustomObject]@{
        NomProjet  = $NomProjet
        NomService = $nomService
        RepDepot   = $repDepot
        NomConf    = $nomConf
        NomLog     = $nomLog
        CheminConf = Join-Path (Join-Path $repDepot 'configs') $nomConf
    }
}

# Lit une valeur « CLE=valeur » dans un fichier clé=valeur (.conf). Renvoie la
# valeur brute (tout ce qui suit le premier « = », sans rognage des espaces
# internes ; seuls le CR/LF de fin sont retirés), ou $null si la clé est
# absente. Reprise à l'identique de mettre_a_jour_tokens_ccw.ps1.
function Lire-ValeurFichier {
    param([string]$chemin, [string]$cle)
    foreach ($ligne in [System.IO.File]::ReadAllLines($chemin)) {
        $idx = $ligne.IndexOf('=')
        if ($idx -lt 1) { continue }
        if ($ligne.Substring(0, $idx).Trim() -eq $cle) {
            return $ligne.Substring($idx + 1).TrimEnd("`r", "`n")
        }
    }
    return $null
}

# Accorde à un compte (AlainW par défaut) le droit de démarrer/arrêter/
# interroger un service CCW SANS élévation UAC (issue #717, étape F du
# retrofit CCW). Constat du 04/10/2026 : AlainW est administrateur, mais son
# jeton en session NORMALE est bridé par l'UAC (groupe Administrators en
# « deny only », niveau Medium) — nssm status fonctionne, nssm start échoue
# avec « OpenService(): Access is denied ». Le démarrage par SSH marche
# parce qu'une session SSH d'administrateur reçoit les droits complets.
#
# `sc.exe sdset` pose une entrée DÉDIÉE au compte visé, sans dépendre de son
# appartenance au groupe Administrateurs — ce compte peut alors démarrer/
# arrêter/interroger le service en session normale, sans élévation. Entrée
# ajoutée (A;;LCSWRPWPLOCRRC;;;<SID>) : LC (query config) + SW (enum
# dependents) + RP (start) + WP (stop) + LO (query status) + CR (user-
# defined control) + RC (read control) — démarrer/arrêter/interroger, rien
# de plus. Le SID est résolu DYNAMIQUEMENT à partir du nom de compte (propre
# à chaque PC), jamais codé en dur.
#
# Idempotent : lit le descripteur actuel via `sc.exe sdshow` (jamais `sc`,
# alias PowerShell de Set-Content), ne fait rien si une entrée pour ce SID
# est déjà présente, sinon l'insère dans la section D: (ACL discrétionnaire,
# avant la section S: — audit — si elle existe) SANS retirer les entrées
# existantes (SYSTEM, Administrateurs, utilisateurs interactifs), puis
# réécrit via `sc.exe sdset`.
function Autoriser-DemarrageServiceCcw {
    param(
        [Parameter(Mandatory=$true)][string]$NomService,
        [string]$NomCompte = 'AlainW'
    )

    $sid = (New-Object System.Security.Principal.NTAccount($NomCompte)).
        Translate([System.Security.Principal.SecurityIdentifier]).Value

    $sortieSdshow = & sc.exe sdshow $NomService
    if ($LASTEXITCODE -ne 0) {
        throw "sc.exe sdshow a échoué (code $LASTEXITCODE) pour « $NomService » — service introuvable ?"
    }
    $sddlActuel = (($sortieSdshow | Where-Object { $_.Trim() -ne '' }) -join '').Trim()
    if (-not $sddlActuel) {
        throw "sc.exe sdshow $NomService n'a renvoyé aucun descripteur exploitable."
    }

    if ($sddlActuel -match [regex]::Escape(";;;$sid)")) {
        return [PSCustomObject]@{ Service = $NomService; Statut = 'déjà présent'; Sddl = $sddlActuel }
    }

    # Découpe D: (en-tête + flags éventuels) / liste des ACE / S: (SACL,
    # optionnelle) — insertion de la nouvelle entrée à la fin de la liste des
    # ACE, avant S: si présente, sans toucher au reste.
    if ($sddlActuel -notmatch '^(D:[^(]*)((?:\([^)]*\))*)(S:.*)?$') {
        throw "Descripteur SDDL inattendu (ne commence pas par D:) pour « $NomService » : $sddlActuel"
    }
    $entete = $Matches[1]
    $aces   = $Matches[2]
    $sacl   = $Matches[3]

    $nouvelleAce = "(A;;LCSWRPWPLOCRRC;;;$sid)"
    $nouveauSddl = $entete + $aces + $nouvelleAce + $sacl

    & sc.exe sdset $NomService $nouveauSddl | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "sc.exe sdset a échoué (code $LASTEXITCODE) pour « $NomService »."
    }
    return [PSCustomObject]@{ Service = $NomService; Statut = 'ajouté'; Sddl = $nouveauSddl }
}

Export-ModuleMember -Function Set-PrefixeCcw, Info, Ok, Avert, Get-CheminsProjetCcw, Lire-ValeurFichier, Autoriser-DemarrageServiceCcw
