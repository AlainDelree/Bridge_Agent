<#
.SYNOPSIS
    Surveille en continu les processus de build (Claude Code / ISCC) et la
    croissance du dossier de sortie d'un build en cours, sur la VM CCW.
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Dossier,
    [string[]]$Processus = @("claude", "ISCC", "python", "pyinstaller"),
    [int]$IntervalleSecondes = 10
)

function Obtenir-TailleDossier {
    param([string]$Chemin)
    if (-not (Test-Path $Chemin)) { return 0 }
    $mesure = Get-ChildItem -Path $Chemin -Recurse -File -ErrorAction SilentlyContinue |
        Measure-Object -Property Length -Sum
    if ($null -eq $mesure.Sum) { return 0 }
    return $mesure.Sum
}

function Formater-Taille {
    param([long]$Octets)
    if ($Octets -ge 1GB) { return "{0:N2} Go" -f ($Octets / 1GB) }
    if ($Octets -ge 1MB) { return "{0:N2} Mo" -f ($Octets / 1MB) }
    if ($Octets -ge 1KB) { return "{0:N2} Ko" -f ($Octets / 1KB) }
    return "$Octets o"
}

Write-Host "=== Surveillance de build ===" -ForegroundColor Cyan
Write-Host "Dossier surveillé   : $Dossier"
Write-Host "Processus surveillés: $($Processus -join ', ')"
Write-Host "Intervalle          : ${IntervalleSecondes}s"
Write-Host "Ctrl+C pour arrêter."
Write-Host ""

$tailleOrigine = Obtenir-TailleDossier -Chemin $Dossier
$tailleAvant = $tailleOrigine
$debut = Get-Date

while ($true) {
    $horodatage = Get-Date -Format "HH:mm:ss"
    $tailleActuelle = Obtenir-TailleDossier -Chemin $Dossier
    $delta = $tailleActuelle - $tailleAvant
    $ecouleTotal = (Get-Date) - $debut

    Write-Host "--- $horodatage (écoulé : $($ecouleTotal.ToString('hh\:mm\:ss'))) ---" -ForegroundColor Yellow

    foreach ($nom in $Processus) {
        $procs = Get-Process -Name $nom -ErrorAction SilentlyContinue
        if ($procs) {
            foreach ($p in $procs) {
                $dureeVie = (Get-Date) - $p.StartTime
                $cpuSec = [Math]::Round($p.CPU, 1)
                $memMo = [Math]::Round($p.WorkingSet64 / 1MB, 1)
                Write-Host ("  [ACTIF] {0,-12} PID={1,-6} CPU={2,7}s  Mem={3,7} Mo  Durée={4}" -f `
                    $p.ProcessName, $p.Id, $cpuSec, $memMo, $dureeVie.ToString('hh\:mm\:ss'))
            }
        } else {
            Write-Host ("  [absent] {0}" -f $nom) -ForegroundColor DarkGray
        }
    }

    $signeDelta = if ($delta -ge 0) { "+" } else { "" }
    Write-Host ("  Dossier : {0}  (delta : {1}{2} depuis dernier passage, {3} depuis le début)" -f `
        (Formater-Taille $tailleActuelle), $signeDelta, (Formater-Taille $delta),
        (Formater-Taille ($tailleActuelle - $tailleOrigine)))
    Write-Host ""

    $tailleAvant = $tailleActuelle
    Start-Sleep -Seconds $IntervalleSecondes
}
