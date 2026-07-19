<#
  lister_projets_ccw.ps1 — Inventaire JSON des projets CCW (issue #174).

  Exécuté À DISTANCE depuis l'onglet CCW de l'interface web (Linux) via
  « VBoxManage guestcontrol run » — jamais interactif. Énumère les services
  Windows « CCW-Watcher* » enregistrés dans la VM (NSSM) et, pour chacun,
  émet : le nom du service, le nom de projet dérivé, l'état (running/stopped)
  et l'état du placeholder TOPIC_NTFY (encore à définir ou non) lu dans le
  fichier config correspondant.

  Sortie : un objet JSON UNIQUE encadré par les marqueurs <<<CCW_JSON>>> et
  <<<CCW_END>>> pour que l'appelant Linux l'extraie de façon fiable même si un
  message parasite venait polluer stdout. Aucune donnée sensible n'est émise
  (pas de token, pas de valeur de topic — seulement un booléen placeholder).

  Convention des chemins (identique à provisionner.ps1 / ajouter_projet_ccw.ps1) :
    • service « CCW-Watcher »            → C:\CCW\Bridge_Agent, configs\ccw.conf
    • service « CCW-Watcher-<NomProjet> » → C:\CCW\<NomProjet>,
                                            configs\<nom-minuscule>-ccw.conf

  Exécution en administrateur, DANS la VM CCW-Build.
#>

[CmdletBinding()]
param(
    # Racine de travail dédiée à CCW côté invité (comme les autres scripts CCW).
    [string]$RepCCW = 'C:\CCW'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$placeholder = '###TOPIC_NTFY_A_DEFINIR###'
$resultats   = @()

# Get-Service -Name accepte le joker : on récupère tous les services CCW-Watcher*.
$services = @(Get-Service -Name 'CCW-Watcher*' -ErrorAction SilentlyContinue |
             Sort-Object Name)

foreach ($svc in $services) {
    $nom = $svc.Name

    if ($nom -eq 'CCW-Watcher') {
        # Service historique mono-projet (Bridge_Agent lui-même).
        $nomProjet = 'Bridge_Agent'
        $repDepot  = Join-Path $RepCCW 'Bridge_Agent'
        $chemConf  = Join-Path (Join-Path $repDepot 'configs') 'ccw.conf'
        $base      = $true
    } else {
        # Service multi-projets « CCW-Watcher-<NomProjet> ».
        $nomProjet = $nom.Substring('CCW-Watcher-'.Length)
        $nomMin    = $nomProjet.ToLowerInvariant()
        $repDepot  = Join-Path $RepCCW $nomProjet
        $chemConf  = Join-Path (Join-Path $repDepot 'configs') "$nomMin-ccw.conf"
        $base      = $false
    }

    # État du placeholder TOPIC_NTFY : 'placeholder' (à finaliser), 'ok'
    # (renseigné) ou 'inconnu' (config introuvable). On ne renvoie JAMAIS la
    # valeur réelle du topic — juste son statut.
    $topicStatut = 'inconnu'
    if (Test-Path $chemConf) {
        $contenu = [System.IO.File]::ReadAllText($chemConf)
        if ($contenu.Contains($placeholder)) { $topicStatut = 'placeholder' }
        else                                  { $topicStatut = 'ok' }
    }

    $resultats += [PSCustomObject]@{
        service     = $nom
        projet      = $nomProjet
        base        = $base
        etat        = "$($svc.Status)".ToLowerInvariant()   # running / stopped …
        config      = $chemConf
        topicStatut = $topicStatut
    }
}

Write-Output '<<<CCW_JSON>>>'
# @(...) force un tableau ; -Compress = une seule ligne facile à extraire.
Write-Output (ConvertTo-Json -Depth 4 -Compress @($resultats))
Write-Output '<<<CCW_END>>>'
