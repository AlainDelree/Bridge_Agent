<#
  surveiller_processus_session.ps1 — Superviseur générique d'un process
  longue durée, utilisé par installer_demarrage_session.ps1 (issue #864).

  Rôle : reproduire, pour un démarrage dans la SESSION de l'utilisateur
  (tâche planifiée « à l'ouverture de session » ou, en option, service NSSM
  — voir installer_demarrage_session.ps1), le même comportement que
  systemd/watcher@.service côté Linux :
    - Restart=on-failure  : tout arrêt INATTENDU (code de sortie différent
      de ceux listés dans -CodesSansRedemarrage) relance le process après
      -DelaiRedemarrageSec secondes ;
    - SuccessExitStatus=0,42 (défaut) : un arrêt PROPRE (code 0, ou 42 —
      auto-extinction par inactivité de watcher.py, voir watcher.py::
      EXIT_INACTIVITE) n'est PAS relancé, exactement comme le gabarit
      systemd/watcher@.service déclare `SuccessExitStatus=42` ;
    - une seule instance : si -FichierPid est fourni et désigne déjà un
      process vivant au démarrage de CE script, on abandonne sans rien
      lancer (watcher.py n'a lui-même AUCUNE protection interne contre un
      double lancement du même projet — c'est l'appelant, ici, qui doit
      l'assurer, comme le fait normalement app.watchers.demarrer_watcher()
      côté interface web via watcher_actif()).

  CE script est le MÊME, que l'appelant soit une tâche planifiée (mode par
  défaut) ou un service NSSM (-ModeService) — voir installer_demarrage_
  session.ps1 : NSSM se contente alors de le relancer si LUI-MÊME
  plantait (rare, filet de sécurité), toute la logique de redémarrage du
  process SURVEILLÉ reste ici, dans la boucle ci-dessous.

  Journalisation : chaque démarrage/arrêt est horodaté dans -FichierJournal,
  AUQUEL est ajouté (en fin de cycle, une fois le process terminé) tout ce
  qu'il a écrit sur stdout/stderr — fichier SÉPARÉ du journal propre de
  l'application quand elle en gère un elle-même (watcher.py et son
  RotatingFileHandler sur logs\watcher-<nom>.log, par exemple) : même
  principe de séparation que NSSM (AppStdout/AppStderr) vis-à-vis du
  journal applicatif, pour ne jamais avoir deux écrivains sur le même
  fichier (watcher_issues_inbox.py, lui, n'écrit QUE sur stdout — ce
  fichier -FichierJournal devient alors sa SEULE trace persistante, là où
  rien n'existait jusqu'ici en dehors d'un terminal).

  Usage (appelé par installer_demarrage_session.ps1, rarement à la main) :
    powershell -File surveiller_processus_session.ps1 `
        -Commande "C:\Python312\python.exe" `
        -RepTravail "C:\Users\moi\Bridge_Agent" `
        -FichierJournal "C:\Users\moi\Bridge_Agent\logs\watcher-scrabble-session.log" `
        -FichierPid "C:\Users\moi\Bridge_Agent\logs\watcher-scrabble.pid" `
        -CodesSansRedemarrage "0,42" -DelaiRedemarrageSec 10 `
        "C:\Users\moi\Bridge_Agent\watcher.py" --config "C:\...\configs\scrabble.conf"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Commande,
    [Parameter(Mandatory = $true)][string]$RepTravail,
    [Parameter(Mandatory = $true)][string]$FichierJournal,
    [string]$FichierPid = '',
    # Chaîne "0,42" plutôt qu'un [int[]] : un [int[]] lié depuis la ligne de
    # commande brute d'une tâche planifiée (un seul jeton texte "0,42") n'est
    # PAS garanti de se scinder automatiquement en tableau — on le scinde
    # nous-mêmes ci-dessous, sans ambiguïté.
    [string]$CodesSansRedemarrage = '0,42',
    [int]$DelaiRedemarrageSec = 10,
    # Chemin + arguments du process surveillé — tout ce qui suit les
    # paramètres nommés ci-dessus (ex. "watcher.py" "--config" "x.conf").
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$ArgsEnfant = @()
)

$ErrorActionPreference = 'Stop'

$CodesArret = $CodesSansRedemarrage -split ',' | ForEach-Object { [int]$_.Trim() }

function Horodate { (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') }

function Ecrire-Journal([string]$Texte) {
    Add-Content -Path $FichierJournal -Value $Texte -Encoding UTF8
}

New-Item -ItemType Directory -Path (Split-Path $FichierJournal -Parent) -Force | Out-Null

# ── Garde-fou « une seule instance » (voir en-tête) ──────────────────────────
if ($FichierPid -and (Test-Path $FichierPid)) {
    $ancienPid = $null
    try { $ancienPid = [int](Get-Content -Path $FichierPid -ErrorAction Stop | Select-Object -First 1) } catch { }
    if ($ancienPid) {
        $procExistant = Get-Process -Id $ancienPid -ErrorAction SilentlyContinue
        if ($procExistant) {
            Ecrire-Journal ("$(Horodate) [ABANDON] une instance (PID $ancienPid) semble déjà active " +
                            "($FichierPid) — pas de second lancement.")
            exit 0
        }
    }
}

Ecrire-Journal "============================================================"
Ecrire-Journal "$(Horodate) [SUPERVISEUR] démarré — $Commande $($ArgsEnfant -join ' ')"

while ($true) {
    Ecrire-Journal "$(Horodate) [DEMARRAGE] $Commande $($ArgsEnfant -join ' ')"

    $tmpOut = [System.IO.Path]::GetTempFileName()
    $tmpErr = [System.IO.Path]::GetTempFileName()
    # -1 : sentinelle « n'a jamais pu démarrer » — absente de
    # -CodesSansRedemarrage par construction (toujours des codes positifs),
    # donc traitée comme un échec normal plus bas (nouvelle tentative après
    # le délai). Start-Process lève une exception TERMINANTE s'il échoue à
    # lancer le process (ex. verrou antivirus transitoire, exécutable
    # momentanément inaccessible) — SANS le try/catch ci-dessous, cette
    # exception remonterait hors de la boucle `while` et tuerait le
    # superviseur entier, le laissant éteint jusqu'à la prochaine ouverture
    # de session : exactement l'arrêt inattendu SANS redémarrage que ce
    # script existe pour éviter.
    $code = -1
    try {
        try {
            $proc = Start-Process -FilePath $Commande -ArgumentList $ArgsEnfant `
                -WorkingDirectory $RepTravail -NoNewWindow -PassThru `
                -RedirectStandardOutput $tmpOut -RedirectStandardError $tmpErr

            if ($FichierPid) { Set-Content -Path $FichierPid -Value $proc.Id -Encoding ASCII }

            $proc.WaitForExit()
            $code = $proc.ExitCode
        } catch {
            Ecrire-Journal "$(Horodate) [ERREUR] lancement impossible : $($_.Exception.Message)"
        }
    } finally {
        foreach ($tmp in @($tmpOut, $tmpErr)) {
            if (Test-Path $tmp) {
                $contenu = Get-Content -Path $tmp -Raw -ErrorAction SilentlyContinue
                if ($contenu) { Add-Content -Path $FichierJournal -Value $contenu -Encoding UTF8 -NoNewline }
                Remove-Item -Path $tmp -Force -ErrorAction SilentlyContinue
            }
        }
        if ($FichierPid -and (Test-Path $FichierPid)) {
            Remove-Item -Path $FichierPid -Force -ErrorAction SilentlyContinue
        }
    }

    Ecrire-Journal "$(Horodate) [ARRET] code de sortie : $code"

    if ($CodesArret -contains $code) {
        Ecrire-Journal "$(Horodate) [FIN] arrêt propre (code $code dans « $CodesSansRedemarrage ») — pas de redémarrage."
        break
    }

    Ecrire-Journal "$(Horodate) [REDEMARRAGE] code $code inattendu — nouvelle tentative dans $DelaiRedemarrageSec s…"
    Start-Sleep -Seconds $DelaiRedemarrageSec
}
