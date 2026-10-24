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

  SOURCE DE VÉRITÉ DE LA LISTE (#597, lecture corrigée par #813) : $Projets
  est dérivé DYNAMIQUEMENT, au moment de l'exécution, des fichiers
  configs\*-ccw.conf présents sur le disque — un fichier par projet dédié,
  créé par ajouter_projet_ccw.ps1 et supprimé au décommissionnement d'un
  projet. Ces fichiers ne sont PAS versionnés (.gitignore) et vivent dans le
  clone DÉDIÉ de chaque projet (C:\CCW\<Projet>\configs\<nom>-ccw.conf), pas
  dans celui de Bridge_Agent : ce script énumère donc C:\CCW\*\configs\
  *-ccw.conf (racine des clones CCW, voir calcul de $RepCCW ci-dessous), et
  non plus seulement configs\ de Bridge_Agent (qui ne contient que le canal
  unifié ccw.conf — l'ancienne énumération n'y aurait jamais rien trouvé,
  même sans réinstallation). Le canal unifié « for-windows » (configs\
  ccw.conf, sans suffixe projet, service CCW-Watcher de base) reste
  explicitement exclu de cette énumération — il est déjà couvert par les
  étapes 1 à 6 de REINSTALLATION_CCW.md, pas par ce script. Plus aucune
  liste codée en dur à maintenir ici ni dans la doc.

  CONSÉQUENCE D'UNE RÉINSTALLATION PROPRE (#813) : C:\CCW est recréé et
  chaque clone est refait par `git clone`, qui ne ramène pas ces fichiers
  non versionnés — la liste serait donc VIDE juste après une réinstallation,
  même si les projets concernés doivent être recréés. Voir le message
  d'erreur plus bas (aucun fichier trouvé) pour les deux solutions.

  Usage (depuis C:\CCW\Bridge_Agent, après l'étape 6 de REINSTALLATION_CCW.md
  — service de base CCW-Watcher déjà vérifié) :
    powershell -ExecutionPolicy Bypass -File provisioning\windows\reinstaller_projets_ccw.ps1

  Pour ne rejouer qu'un sous-ensemble (ex. reprise après interruption, ou
  pour ne recréer que les projets dont CCW a encore besoin — voir étape 7 de
  REINSTALLATION_CCW.md) :
    powershell -ExecutionPolicy Bypass -File provisioning\windows\reinstaller_projets_ccw.ps1 -SeulementProjets scrabble,rummikub
#>

param(
    [string[]]$SeulementProjets,

    # Racine des clones CCW (contient un sous-dossier par projet, chacun avec
    # son configs\<nom>-ccw.conf). Par défaut, dérivée du chemin de CE script
    # (provisioning\windows\ sous le clone Bridge_Agent) : deux niveaux au-
    # dessus donnent le clone Bridge_Agent lui-même (C:\CCW\Bridge_Agent), un
    # niveau de plus donne sa racine parente (C:\CCW) — même convention que
    # $RepCCW dans ajouter_projet_ccw.ps1, calculée ici plutôt que codée en
    # dur pour rester correcte si le dépôt est cloné ailleurs que C:\CCW.
    [string]$RepCCW = (Join-Path $PSScriptRoot "..\..\..")
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Dérivation dynamique de $Projets depuis C:\CCW\*\configs\*-ccw.conf (#597,
# chemin corrigé par #813) — voir bloc de commentaire ci-dessus. Un fichier
# <nom>-ccw.conf par projet dédié, dans le clone DÉDIÉ de ce projet (pas dans
# celui de Bridge_Agent) ; configs\ccw.conf (canal unifié « for-windows »,
# sans suffixe projet) est EXPLICITEMENT exclu : ce n'est pas un projet dédié
# pour ce script.
# ---------------------------------------------------------------------------
$FichiersConf = @(Get-ChildItem -Path (Join-Path $RepCCW "*\configs\*-ccw.conf") -File -ErrorAction SilentlyContinue |
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
    Write-Host "[reinstaller-projets-ccw] ERREUR : aucun fichier <nom>-ccw.conf détecté sous $RepCCW\*\configs\ (hors canal unifié ccw.conf)."
    Write-Host "[reinstaller-projets-ccw] Ces fichiers ne sont PAS versionnés : une réinstallation propre (disque effacé, clones refaits par git clone) les a perdus."
    Write-Host "[reinstaller-projets-ccw] Deux solutions :"
    Write-Host "[reinstaller-projets-ccw]   1. Restaurer les fichiers *-ccw.conf sauvegardés avant la réinstallation dans le dossier configs\ de chaque clone (C:\CCW\<Projet>\configs\<nom>-ccw.conf), puis relancer ce script."
    Write-Host "[reinstaller-projets-ccw]   2. Appeler creer_projet_ccw_complet.ps1 pour chaque projet de la liste (il recrée aussi le fichier de configuration)."
    exit 1
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
