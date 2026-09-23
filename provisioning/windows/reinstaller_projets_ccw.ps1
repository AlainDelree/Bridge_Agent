<#
  reinstaller_projets_ccw.ps1 — Recréer en séquence les services multi-projets
  CCW après une réinstallation Windows (issue #552, suite de #547/#451 ;
  dérivation dynamique de la liste par #597, suite de #552).

  CONTEXTE : REINSTALLATION_CCW.md (étape 7) couvre la remise sur pied du
  service de base CCW-Watcher, mais les services dédiés actifs en production
  (CCW-Watcher-<projet>, §16 de BRIDGE_AGENT_DOC.md) doivent eux aussi être
  recréés — sans quoi il faut se souvenir de mémoire de la liste exacte des
  projets à relancer avec creer_projet_ccw_complet.ps1.

  Ce script se contente de SÉQUENCER l'appel à creer_projet_ccw_complet.ps1
  (racine du dépôt) pour chacun des projets détectés. Il ne contourne aucune
  saisie : les deux tokens (GH_TOKEN, CLAUDE_CODE_OAUTH_TOKEN) restent
  demandés PAR PROJET, à l'intérieur de la boucle — pas de token partagé.

  SOURCE DE VÉRITÉ DE LA LISTE (#597) : $Projets est dérivé DYNAMIQUEMENT, au
  moment de l'exécution, des fichiers configs\*-ccw.conf présents sur le
  disque (un fichier par projet dédié, créé par ajouter_projet_ccw.ps1 et
  supprimé au décommissionnement d'un projet — même principe que l'inventaire
  des services NSSM fait par lister_projets_ccw.ps1, mais basé sur les
  configs plutôt que sur les services : un service peut être arrêté ou
  absent sans que le projet soit décommissionné). Le canal unifié
  « for-windows » (configs\ccw.conf, sans suffixe projet, service
  CCW-Watcher de base) est explicitement exclu de cette énumération — il est
  déjà couvert par les étapes 1 à 6 de REINSTALLATION_CCW.md, pas par ce
  script. Plus aucune liste codée en dur à maintenir ici ni dans la doc.

  Usage (depuis C:\CCW\Bridge_Agent, après l'étape 6 de REINSTALLATION_CCW.md
  — service de base CCW-Watcher déjà vérifié) :
    powershell -ExecutionPolicy Bypass -File provisioning\windows\reinstaller_projets_ccw.ps1

  Pour ne rejouer qu'un sous-ensemble (ex. reprise après interruption) :
    powershell -ExecutionPolicy Bypass -File provisioning\windows\reinstaller_projets_ccw.ps1 -SeulementProjets scrabble,rummikub
#>

param(
    [string[]]$SeulementProjets
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Dérivation dynamique de $Projets depuis configs\*-ccw.conf (#597) — voir
# bloc de commentaire ci-dessus. Un fichier <nom>-ccw.conf par projet dédié ;
# configs\ccw.conf (canal unifié « for-windows », sans suffixe projet) est
# EXPLICITEMENT exclu : ce n'est pas un projet dédié pour ce script.
# ---------------------------------------------------------------------------
$RepConfigs = Join-Path $PSScriptRoot "..\..\configs"

$FichiersConf = @(Get-ChildItem -Path $RepConfigs -Filter "*-ccw.conf" -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne "ccw.conf" } |
    Sort-Object Name)

$Projets = @()
foreach ($f in $FichiersConf) {
    $nomProjet = $f.Name -replace "-ccw\.conf$", ""
    $depot = $null
    foreach ($ligne in [System.IO.File]::ReadAllLines($f.FullName)) {
        if ($ligne -match '^\s*DEPOT\s*=\s*(.+?)\s*$') {
            $depot = $Matches[1].Trim()
            break
        }
    }
    if (-not $depot) {
        Write-Host "[reinstaller-projets-ccw] ERREUR : DEPOT introuvable dans $($f.Name) — config malformée, abandon."
        exit 1
    }
    $Projets += @{ NomProjet = $nomProjet; Depot = $depot }
}

if ($Projets.Count -eq 0) {
    Write-Host "[reinstaller-projets-ccw] Aucun fichier configs\*-ccw.conf détecté (hors canal unifié ccw.conf) — rien à réinstaller."
    exit 0
}

if ($SeulementProjets) {
    $Projets = $Projets | Where-Object { $SeulementProjets -contains $_.NomProjet }
    if ($Projets.Count -eq 0) {
        Write-Host "[reinstaller-projets-ccw] ERREUR : aucun des projets demandés ($($SeulementProjets -join ', ')) n'est dans la liste de référence."
        exit 1
    }
}

Write-Host "[reinstaller-projets-ccw] Projets à (re)créer, dans l'ordre : $($Projets.NomProjet -join ', ')"
Write-Host "[reinstaller-projets-ccw] Chaque projet demandera SES DEUX propres tokens (GH_TOKEN + CLAUDE_CODE_OAUTH_TOKEN)."
Write-Host ""

$CheminScript = Join-Path $PSScriptRoot "..\..\creer_projet_ccw_complet.ps1"

foreach ($p in $Projets) {
    Write-Host "========================================================================"
    Write-Host "[reinstaller-projets-ccw] Projet : $($p.NomProjet)  (dépôt $($p.Depot))"
    Write-Host "========================================================================"
    powershell -ExecutionPolicy Bypass -File $CheminScript -NomProjet $p.NomProjet -Depot $p.Depot
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[reinstaller-projets-ccw] ERREUR sur le projet $($p.NomProjet) (code $LASTEXITCODE). Arrêt de la séquence."
        Write-Host "[reinstaller-projets-ccw] Reprise possible avec -SeulementProjets une fois le problème corrigé."
        exit 1
    }
    Write-Host ""
}

Write-Host "[reinstaller-projets-ccw] Terminé — $($Projets.Count) projet(s) traité(s) : $($Projets.NomProjet -join ', ')"
Write-Host "[reinstaller-projets-ccw] Vérif globale : provisioning\windows\lister_projets_ccw.ps1"
