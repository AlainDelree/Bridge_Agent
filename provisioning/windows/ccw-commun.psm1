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

Export-ModuleMember -Function Set-PrefixeCcw, Info, Ok, Avert, Get-CheminsProjetCcw, Lire-ValeurFichier
