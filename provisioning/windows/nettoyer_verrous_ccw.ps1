<#
  nettoyer_verrous_ccw.ps1 — Nettoie les verrous CCW orphelins (issue #431,
  bouton « 🔒 Nettoyer verrous CCW + redémarrer » prévu par #378) : arrête le
  service CCW-Watcher, supprime tous les .lock du dossier de verrous, puis
  relance le service.

  Cas d'usage : un verrou orphelin bloque le watcher CCW SANS qu'il y ait
  d'issue précise à interrompre — à la différence du bouton « Interrompre »
  (interrompre_projet_ccw.ps1), disponible uniquement sur une issue ouverte
  précise. Volontairement PAS de vérification d'arbre de process ici (pas de
  PID de référence sans issue ciblée) : l'attente bornée de la disparition du
  service via nssm suffit, l'objectif étant justement de déverrouiller sans
  dépendre d'une issue précise.

  Exécuté À DISTANCE depuis app/ccw.py (Linux) via « VBoxManage guestcontrol
  run », après copie du script — jamais interactif. Émis en JSON encadré par
  les mêmes marqueurs que lister_projets_ccw.ps1 (<<<CCW_JSON>>> /
  <<<CCW_END>>>), pour réutiliser le même extracteur côté Linux
  (_extraire_projets).

  $RepDepot est dérivé côté Linux du champ « config » retourné par
  lister_projets_ccw.ps1 (même règle que interrompre_projet_ccw.ps1) — jamais
  reconstruit depuis $Service ni depuis le nom du projet Linux, qui peuvent
  diverger (cf. §"résolution des identités" de l'issue #323).

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

function EtatService([string]$Nom) {
    $svc = Get-CimInstance Win32_Service -Filter "Name='$Nom'" -ErrorAction SilentlyContinue
    if ($svc) { return $svc.State }
    return $null
}

# ─── Étape 1 : arrêt du service, attente confirmée (bornée à ~5s) ──────────
$etatInitial = EtatService $Service
if (-not $etatInitial) {
    AjouterEtape 'arret_service_ccw' 'rien_a_faire' "Service « $Service » introuvable — déjà désinstallé ?"
} elseif ($etatInitial -ne 'Running') {
    AjouterEtape 'arret_service_ccw' 'rien_a_faire' "Service « $Service » déjà arrêté (état : $etatInitial)."
} else {
    try {
        $sortie = & nssm stop $Service 2>&1 | Out-String
        $limite = (Get-Date).AddSeconds(5)
        $etat   = EtatService $Service
        while ($etat -eq 'Running' -and (Get-Date) -lt $limite) {
            Start-Sleep -Milliseconds 250
            $etat = EtatService $Service
        }
        if ($etat -eq 'Running') {
            AjouterEtape 'arret_service_ccw' 'echec' "nssm stop $Service : toujours « Running » après 5s. Sortie : $($sortie.Trim())"
        } else {
            AjouterEtape 'arret_service_ccw' 'succes' "nssm stop $Service : arrêt confirmé (état : $etat). $($sortie.Trim())"
        }
    } catch {
        AjouterEtape 'arret_service_ccw' 'echec' "nssm stop a échoué : $_"
    }
}

# ─── Étape 2 : suppression de TOUS les .lock (verrous orphelins) ──────────
$dossierVerrous = Join-Path $RepDepot 'logs\verrous'
$nbSupprimes = 0
if (-not (Test-Path $dossierVerrous)) {
    AjouterEtape 'suppression_verrous' 'rien_a_faire' "Dossier de verrous introuvable ($dossierVerrous) — rien à supprimer."
} else {
    $locks = @(Get-ChildItem -Path $dossierVerrous -Filter '*.lock' -ErrorAction SilentlyContinue)
    if ($locks.Count -eq 0) {
        AjouterEtape 'suppression_verrous' 'rien_a_faire' 'Aucun fichier .lock présent.'
    } else {
        $echecs = @()
        foreach ($lock in $locks) {
            try {
                Remove-Item -Path $lock.FullName -Force -ErrorAction Stop
                $nbSupprimes++
                Write-Output "Verrou supprimé : $($lock.Name)"
            } catch {
                $echecs += $lock.Name
                Write-Output "Échec de suppression de $($lock.Name) : $_"
            }
        }
        $statutGlobal = if ($echecs.Count -eq 0) { 'succes' } else { 'echec' }
        $msg = "$nbSupprimes verrou(s) supprimé(s) sur $($locks.Count) : $(($locks | ForEach-Object { $_.Name }) -join ', ')."
        if ($echecs.Count -gt 0) { $msg += " Échecs : $($echecs -join ', ')." }
        AjouterEtape 'suppression_verrous' $statutGlobal $msg
    }
}

# ─── Étape 3 : redémarrage du service ──────────────────────────────────────
try {
    $sortie = & nssm start $Service 2>&1 | Out-String
    Start-Sleep -Milliseconds 500
    $etatFinal = EtatService $Service
    if ($etatFinal -eq 'Running') {
        AjouterEtape 'redemarrage_service_ccw' 'succes' "nssm start $Service : service relancé (état : $etatFinal)."
    } else {
        AjouterEtape 'redemarrage_service_ccw' 'echec' "nssm start $Service : état après relance = « $etatFinal ». Sortie : $($sortie.Trim())"
    }
} catch {
    $etatFinal = EtatService $Service
    AjouterEtape 'redemarrage_service_ccw' 'echec' "nssm start a échoué : $_"
}

# ─── Résumé final (nb de verrous supprimés + statut final du service) ─────
$echecEtapes = @($script:etapes | Where-Object { $_.statut -eq 'echec' })
$statutResume = if ($echecEtapes.Count -eq 0) { 'succes' } else { 'echec' }
AjouterEtape 'resume' $statutResume "$nbSupprimes verrou(s) supprimé(s) — service « $Service » : $etatFinal."

Write-Output '<<<CCW_JSON>>>'
Write-Output (ConvertTo-Json -Depth 4 -Compress @($script:etapes))
Write-Output '<<<CCW_END>>>'
