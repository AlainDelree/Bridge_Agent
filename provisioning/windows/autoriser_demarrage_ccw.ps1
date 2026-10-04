<#
  autoriser_demarrage_ccw.ps1 — Accorde à AlainW (ou un autre compte) le
  droit de démarrer/arrêter/interroger TOUS les services CCW-Watcher*
  existants SANS élévation UAC (issue #717, étape F du retrofit CCW).

  Contexte : un service de projet (CCW-Watcher-<Projet>) s'éteint seul après
  20 min d'inactivité (AppExit 42 Exit, issue #712) et doit être rallumé par
  `nssm start`. Le rallumage par SSH (app.ccw.demarrer_service_ccw_arriere_plan)
  fonctionne parce qu'une session SSH d'administrateur reçoit les droits
  complets — mais quand `new_issue.py` tourne NATIVEMENT sous Windows (aucun
  hôte SSH configuré), le process tourne sous le jeton NORMAL d'AlainW,
  bridé par l'UAC (groupe Administrators en « deny only », niveau Medium)
  même si AlainW est administrateur. Constat vérifié le 04/10/2026, depuis
  un PowerShell NON élevé : `nssm status` fonctionne, mais `nssm start`
  échoue avec « OpenService(): Access is denied » — l'hypothèse « UAC
  désactivé » était donc fausse.

  Ce script pose UNE FOIS, sans élévation requise ENSUITE, les droits
  START + STOP + QUERY (SDDL : `(A;;LCSWRPWPLOCRRC;;;<SID>)`) à AlainW sur
  CHAQUE service `CCW-Watcher*` déjà présent sur la machine (le service de
  base `CCW-Watcher`, SANS suffixe, est inclus — il reste toujours actif,
  volontairement, mais bénéficie aussi des boutons Démarrer/Arrêter de
  l'onglet CCW). Logique partagée avec `ajouter_projet_ccw.ps1` (persistance
  à la création/recréation d'un service) : voir
  `ccw-commun.psm1::Autoriser-DemarrageServiceCcw`.

  Idempotent : relançable sans dommage — n'écrit rien si l'entrée existe déjà
  pour ce compte, et ne retire jamais les entrées existantes (SYSTEM,
  Administrateurs, utilisateurs interactifs).

  Exécution — UNE SEULE FOIS, en PowerShell ADMINISTRATEUR (l'élévation n'est
  requise que pour POSER le droit ; s'en servir ensuite n'en a plus besoin) :
    powershell -ExecutionPolicy Bypass -File provisioning\windows\autoriser_demarrage_ccw.ps1

  Validation réelle (nssm start puis stop, en PowerShell NON élevé, sur CCW)
  à faire par Alain après fusion et exécution — hors périmètre de ce script.
#>

[CmdletBinding()]
param(
    # Compte à autoriser à démarrer/arrêter/interroger les services sans
    # élévation. Le SID est résolu dynamiquement à partir de ce nom — jamais
    # codé en dur (propre à chaque PC).
    [string]$NomCompte = 'AlainW'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Import-Module (Join-Path $PSScriptRoot 'ccw-commun.psm1') -Force
Set-PrefixeCcw 'autoriser-demarrage'

$services = Get-Service -Name 'CCW-Watcher*' -ErrorAction SilentlyContinue
if (-not $services) {
    Avert "Aucun service « CCW-Watcher* » trouvé sur cette machine."
    exit 0
}

Info "Compte cible   : $NomCompte"
Info "Services visés : $($services.Count) (CCW-Watcher*, base comprise)"
Write-Host ''

$echecs = 0
foreach ($svc in $services) {
    try {
        $resultat = Autoriser-DemarrageServiceCcw -NomService $svc.Name -NomCompte $NomCompte
        if ($resultat.Statut -eq 'déjà présent') {
            Ok "$($svc.Name) : droits déjà présents — rien à faire."
        } else {
            Ok "$($svc.Name) : droits ajoutés ($NomCompte peut démarrer/arrêter/interroger sans élévation)."
        }
    } catch {
        $echecs++
        Avert "$($svc.Name) : ÉCHEC — $($_.Exception.Message)"
    }
}

Write-Host ''
if ($echecs -gt 0) {
    Avert "$echecs service(s) en échec — voir le détail ci-dessus."
    exit 1
}
Ok "Terminé — tous les services CCW-Watcher* ont les droits requis pour $NomCompte."
