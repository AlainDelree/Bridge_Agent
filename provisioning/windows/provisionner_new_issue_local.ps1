<#
  provisionner_new_issue_local.ps1 — Provisioning pour lancer new_issue.py
  NATIVEMENT sur une machine Windows (issue #690, plan hybride Windows).

  Contexte : le 28/09/2026, new_issue.py a été lancé pour la première fois
  directement sur le PC fixe Windows (CCW), à la main, en dehors de tout
  service NSSM — usage distinct de provisionner.ps1 (qui installe l'outillage
  du SERVICE CCW-Watcher headless, pas l'interface web interactive). Trois
  frictions ont chacune pris plusieurs échanges à diagnostiquer :
    - flask/werkzeug absents (aucun requirements.txt n'existait pour les
      dépendances propres de new_issue.py/app/ — désormais couvert par
      requirements.txt à la racine du dépôt) ;
    - gh non authentifié sous ce compte Windows en session INTERACTIVE (à
      distinguer de GH_TOKEN posé sur le service CCW-Watcher via
      mettre_a_jour_tokens_ccw.ps1 — une session PowerShell manuelle ne
      l'hérite pas) ;
    - aucune règle de pare-feu entrante pour le port 5100 (CCW-Watcher ne
      fait jusqu'ici que des appels sortants).

  Ce script capitalise sur ces trois points pour qu'une future machine
  Windows n'ait pas à les retraverser. Il NE remplace PAS provisionner.ps1
  (Git/gh/Python/NSSM/service) : il suppose Python et gh déjà installés
  (via provisionner.ps1, ou manuellement) et se concentre sur ce qui manque
  spécifiquement pour `new_issue.py --lan`.

  Ce qu'il fait, de façon idempotente (relançable sans dommage) :
    1. installe les dépendances Python de requirements.txt (pip saute déjà
       ce qui est satisfait) ;
    2. crée la règle de pare-feu entrante TCP pour -Port (5100 par défaut)
       si elle n'existe pas déjà (Get-NetFirewallRule avant
       New-NetFirewallRule, pour ne pas dupliquer à chaque exécution) ;
    3. vérifie l'état de `gh auth status` et invite à lancer
       `gh auth login` si le compte courant n'est pas authentifié —
       l'authentification elle-même n'est PAS automatisée (interaction
       humaine requise : navigateur ou code à saisir).

  L'alias PowerShell `bridge` (lancer `new_issue.py --lan` d'une commande)
  n'est volontairement PAS posé par ce script (modification du profil
  PowerShell personnel de l'utilisateur, $PROFILE) — voir
  NEW_ISSUE_LOCAL_WINDOWS.md (même dossier) pour la commande à copier.

  Prérequis : Python (avec pip) et GitHub CLI (gh) déjà installés sur le
  PATH — cf. provisionner.ps1 si ce n'est pas encore le cas. Exécution en
  administrateur requise (New-NetFirewallRule).

  Exemple :
    .\provisionner_new_issue_local.ps1
    .\provisionner_new_issue_local.ps1 -Port 5100
#>

[CmdletBinding()]
param(
    # Port TCP écouté par new_issue.py (cf. --port, défaut 5100 des deux côtés).
    [int]$Port = 5100
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Info($msg)  { Write-Host "[provisionner_new_issue_local] $msg" -ForegroundColor Cyan }
function Avert($msg) { Write-Host "[provisionner_new_issue_local] AVERTISSEMENT : $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------------------
# 0. Vérification élévation administrateur (requise pour New-NetFirewallRule
#    à l'étape 2 — mieux vaut échouer tôt avec un message clair, même
#    pattern que configurer_ssh_ccw.ps1).
# ---------------------------------------------------------------------------
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Ce script doit être lancé dans une console PowerShell ADMINISTRATEUR."
}

# ---------------------------------------------------------------------------
# 1. Dépendances Python (requirements.txt à la racine du dépôt).
# ---------------------------------------------------------------------------
$RepDepot         = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$CheminRequirements = Join-Path $RepDepot 'requirements.txt'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "python introuvable sur le PATH — installez-le d'abord (cf. provisionner.ps1, fonction Installer-Python)."
}
if (-not (Test-Path $CheminRequirements)) {
    throw "requirements.txt introuvable ($CheminRequirements) — dépôt incomplet ou -PSScriptRoot inattendu."
}

Info "Installation des dépendances Python ($CheminRequirements)…"
python -m pip install -r $CheminRequirements
if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements.txt a échoué (code $LASTEXITCODE)." }
Info 'Dépendances Python installées.'

# ---------------------------------------------------------------------------
# 2. Règle de pare-feu entrante pour le port de new_issue.py.
#    Le nom vérifié (Get-NetFirewallRule -DisplayName) et le nom créé
#    (New-NetFirewallRule -DisplayName) DOIVENT être rigoureusement
#    identiques (issue #691 : un ancien -Name interne divergeait du
#    -DisplayName réellement posé, cassant l'idempotence).
# ---------------------------------------------------------------------------
$NomRegle = "Bridge Agent new_issue.py ($Port/tcp)"
if (-not (Get-NetFirewallRule -DisplayName $NomRegle -ErrorAction SilentlyContinue)) {
    Info "Ajout de la règle pare-feu '$NomRegle' (TCP/$Port entrant)…"
    New-NetFirewallRule -DisplayName $NomRegle `
        -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort $Port | Out-Null
} else {
    Info "Règle pare-feu '$NomRegle' déjà présente."
}

# ---------------------------------------------------------------------------
# 3. gh auth status — vérification SANS automatiser l'authentification
#    elle-même (nécessite une interaction humaine : navigateur ou code).
# ---------------------------------------------------------------------------
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Avert "gh (GitHub CLI) introuvable sur le PATH — installez-le d'abord (cf. provisionner.ps1, fonction Installer-GitHubCli), puis relancez ce script."
} else {
    gh auth status 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Info 'gh déjà authentifié pour cette session Windows.'
    } else {
        Avert ("gh n'est pas authentifié sous ce compte Windows (courant pour une PREMIÈRE session " +
               "interactive — le GH_TOKEN du service CCW-Watcher, s'il existe, ne s'applique pas ici). " +
               "Lancez : gh auth login")
    }
}

# ---------------------------------------------------------------------------
# Résumé.
# ---------------------------------------------------------------------------
Info '=== Provisioning new_issue.py local terminé. ==='
Info "Il reste, si besoin : gh auth login (étape manuelle, voir ci-dessus)."
Info "Puis : python new_issue.py --lan   (voir NEW_ISSUE_LOCAL_WINDOWS.md pour l'alias 'bridge')."
