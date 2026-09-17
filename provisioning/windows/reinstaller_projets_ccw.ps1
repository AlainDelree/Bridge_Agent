<#
  reinstaller_projets_ccw.ps1 — Recréer en séquence les services multi-projets
  CCW après une réinstallation Windows (issue #552, suite de #547/#451).

  CONTEXTE : REINSTALLATION_CCW.md (étape 7) couvre la remise sur pied du
  service de base CCW-Watcher, mais les 4 services dédiés actifs en
  production (CCW-Watcher-alchess, -actualise, -rummikub, -scrabble, §16 de
  BRIDGE_AGENT_DOC.md) doivent eux aussi être recréés — sans quoi il faut se
  souvenir de mémoire de la liste exacte des projets à relancer avec
  creer_projet_ccw_complet.ps1.

  Ce script se contente de SÉQUENCER l'appel à creer_projet_ccw_complet.ps1
  (racine du dépôt) pour chacun des projets ci-dessous. Il ne contourne
  aucune saisie : les deux tokens (GH_TOKEN, CLAUDE_CODE_OAUTH_TOKEN) restent
  demandés PAR PROJET, à l'intérieur de la boucle — pas de token partagé.

  SOURCE DE VÉRITÉ DE LA LISTE : le tableau $Projets ci-dessous est la seule
  liste maintenue des projets multi-projets CCW actifs. REINSTALLATION_CCW.md
  (étape 7) la reproduit à titre indicatif pour la lecture humaine, mais en
  cas de divergence (nouveau projet ajouté/retiré), CE tableau fait foi —
  mettre à jour ici en premier, puis répercuter dans la doc.

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

# Liste de référence — voir bloc de commentaire ci-dessus.
$Projets = @(
    @{ NomProjet = "alchess";   Depot = "AlainDelree/AlChess" }
    @{ NomProjet = "actualise"; Depot = "AlainDelree/Actualise" }
    @{ NomProjet = "rummikub";  Depot = "AlainDelree/Rummikub" }
    @{ NomProjet = "scrabble";  Depot = "AlainDelree/Scrabble" }
    @{ NomProjet = "testccwprojet"; Depot = "AlainDelree/Testccwprojet" }
)

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
