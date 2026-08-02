<#
  interrompre_projet_ccw.ps1 — Interruption d'urgence d'un projet CCW pour une
  issue précise (issue #323, suite #320 — bouton « Interrompre » de l'onglet
  Résultats côté for-windows).

  Exécuté À DISTANCE depuis app/interruption.py (Linux) via « VBoxManage
  guestcontrol run », après copie du script — jamais interactif. Regroupe en
  UNE seule exécution, pour limiter le nombre d'allers-retours guestcontrol
  (chacun coûte plusieurs secondes de latence) :

    1. Arrêt du service NSSM ($Service).
    2. Vérification qu'aucun process de son arbre (watcher + éventuel claude
       orphelin dans son propre objet Job, §13/#247) ne survit — attente
       bornée (~5 s), puis kill ciblé de l'arbre SEULEMENT s'il survit encore,
       jamais par nom d'exécutable.
    3. Suppression des .lock de CE projet (dossier $RepDepot\logs\verrous),
       UNIQUEMENT si l'arbre est confirmé mort (sinon lock volontairement
       laissé en place — voir §"points de course" de l'issue).

  Chaque étape produit un statut à trois valeurs (succes / rien_a_faire /
  echec) + message, sur le même modèle que la route Flask /interrompre côté
  Linux (app/interruption.py, cas for-linux). Émis en JSON encadré par les
  mêmes marqueurs que lister_projets_ccw.ps1 (<<<CCW_JSON>>> / <<<CCW_END>>>)
  pour que l'appelant Linux réutilise le même extracteur (_extraire_projets).

  $RepDepot est dérivé côté Linux du champ « config » retourné par
  lister_projets_ccw.ps1 (parent du parent de <RepDepot>\configs\*.conf) —
  jamais reconstruit depuis $Service ni depuis le nom du projet Linux, qui
  peuvent diverger (cf. §"résolution des identités" de l'issue #323).

  Exécution en administrateur, DANS la VM CCW-Build.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Service,
    [Parameter(Mandatory=$true)][string]$RepDepot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$script:etapes = @()

function AjouterEtape([string]$Nom, [string]$Statut, [string]$Message) {
    $script:etapes += [PSCustomObject]@{ etape = $Nom; statut = $Statut; message = $Message }
}

# ─── Étape 1 : arrêt du service ─────────────────────────────────────────────
$svcInfo  = Get-CimInstance Win32_Service -Filter "Name='$Service'" -ErrorAction SilentlyContinue
$pidAvant = 0
if ($svcInfo -and $svcInfo.ProcessId) { $pidAvant = [int]$svcInfo.ProcessId }

if (-not $svcInfo) {
    AjouterEtape 'arret_service_ccw' 'rien_a_faire' "Service « $Service » introuvable — déjà désinstallé ?"
} elseif ($svcInfo.State -ne 'Running') {
    AjouterEtape 'arret_service_ccw' 'rien_a_faire' "Service « $Service » déjà arrêté (état : $($svcInfo.State))."
} else {
    try {
        $sortie = & nssm stop $Service 2>&1 | Out-String
        AjouterEtape 'arret_service_ccw' 'succes' "nssm stop $Service : $($sortie.Trim())"
    } catch {
        AjouterEtape 'arret_service_ccw' 'echec' "nssm stop a échoué : $_"
    }
}

# ─── Étape 2 : arbre de process confirmé mort (watcher + éventuel claude) ───
# Remontée par PPID depuis le PID du service AVANT arrêt — ne cible QUE cet
# arbre précis, jamais par nom d'exécutable (même esprit que #247 point 4).
function ArbreVivant([int]$Racine) {
    if ($Racine -eq 0) { return @() }
    $tousProcess = Get-CimInstance Win32_Process
    $vus         = New-Object System.Collections.Generic.HashSet[int]
    $frontiere   = ,$Racine
    $vivants     = @()
    while ($frontiere.Count -gt 0) {
        $suivante = @()
        foreach ($p in $frontiere) {
            if (-not $vus.Add($p)) { continue }
            $proc = $tousProcess | Where-Object { $_.ProcessId -eq $p }
            if ($proc) {
                $vivants += $proc
                $enfants = ($tousProcess | Where-Object { $_.ParentProcessId -eq $p }).ProcessId
                if ($enfants) { $suivante += $enfants }
            }
        }
        $frontiere = $suivante
    }
    return $vivants
}

$arbre  = ArbreVivant $pidAvant
$limite = (Get-Date).AddSeconds(5)
while ($arbre.Count -gt 0 -and (Get-Date) -lt $limite) {
    Start-Sleep -Milliseconds 250
    $arbre = ArbreVivant $pidAvant
}

if ($arbre.Count -gt 0) {
    # Toujours vivant après l'attente bornée : kill ciblé de CET arbre précis,
    # puis re-vérification courte avant de conclure.
    foreach ($p in $arbre) {
        try { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
    }
    Start-Sleep -Milliseconds 500
    $arbre = ArbreVivant $pidAvant
}

if ($pidAvant -eq 0) {
    AjouterEtape 'verification_orphelin_claude' 'rien_a_faire' 'Aucun PID de service connu avant arrêt (rien à vérifier).'
} elseif ($arbre.Count -eq 0) {
    AjouterEtape 'verification_orphelin_claude' 'succes' "Arbre de process du service (PID $pidAvant) confirmé mort."
} else {
    $liste = ($arbre | ForEach-Object { "$($_.ProcessId):$($_.Name)" }) -join ', '
    AjouterEtape 'verification_orphelin_claude' 'echec' "Process encore vivant(s) après arrêt + kill ciblé : $liste — lock NON supprimé (risque de double traitement)."
}

# ─── Étape 3 : suppression du/des .lock — SEULEMENT si l'arbre est mort ────
$dossierVerrous = Join-Path $RepDepot 'logs\verrous'
if ($arbre.Count -gt 0) {
    AjouterEtape 'suppression_verrou_ccw' 'echec' 'Sautée : arbre de process non confirmé mort (voir étape précédente).'
} elseif (-not (Test-Path $dossierVerrous)) {
    AjouterEtape 'suppression_verrou_ccw' 'rien_a_faire' "Dossier de verrous introuvable ($dossierVerrous) — rien à supprimer."
} else {
    $locks = @(Get-ChildItem -Path $dossierVerrous -Filter '*.lock' -ErrorAction SilentlyContinue)
    if ($locks.Count -eq 0) {
        AjouterEtape 'suppression_verrou_ccw' 'rien_a_faire' 'Aucun fichier .lock présent.'
    } else {
        $noms = ($locks | ForEach-Object { $_.Name }) -join ', '
        try {
            $locks | Remove-Item -Force -ErrorAction Stop
            AjouterEtape 'suppression_verrou_ccw' 'succes' "Verrou(s) supprimé(s) : $noms"
        } catch {
            AjouterEtape 'suppression_verrou_ccw' 'echec' "Échec de suppression : $_"
        }
    }
}

Write-Output '<<<CCW_JSON>>>'
Write-Output (ConvertTo-Json -Depth 4 -Compress @($script:etapes))
Write-Output '<<<CCW_END>>>'
