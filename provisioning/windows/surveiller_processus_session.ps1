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
  AUQUEL est ajouté EN CONTINU (purge toutes les -IntervalleJournalMs
  millisecondes PENDANT que le process tourne encore, pas seulement à son
  arrêt — issue #871) tout ce qu'il écrit sur stdout/stderr — fichier
  SÉPARÉ du journal propre de l'application quand elle en gère un
  elle-même (watcher.py et son RotatingFileHandler sur logs\watcher-<nom>.
  log, par exemple) : même principe de séparation que NSSM (AppStdout/
  AppStderr) vis-à-vis du journal applicatif, pour ne jamais avoir deux
  écrivains sur le même fichier (watcher_issues_inbox.py, lui, n'écrit QUE
  sur stdout — ce fichier -FichierJournal devient alors sa SEULE trace
  persistante, là où rien n'existait jusqu'ici en dehors d'un terminal).
  La purge périodique (voir Purger-SortieVersJournal plus bas) limite à
  l'intervalle de purge (quelques secondes, PAS réglable en paramètre —
  ce n'est qu'un filet de sécurité, pas un suivi au caractère près) la
  quantité de sortie qui pourrait manquer si la session entière (donc CE
  superviseur lui-même) est tuée brutalement — contre la TOTALITÉ depuis
  le dernier (re)démarrage auparavant, puisque la copie n'avait lieu
  qu'au tout dernier moment (bloc `finally`, après la fin du process).
  $env:PYTHONUNBUFFERED=1 est posé avant chaque lancement : sans lui,
  Python retient sa propre sortie en mémoire par blocs dès qu'elle n'est
  PAS un terminal (donc dans TOUTE redirection vers un fichier, comme
  ici) — la purge périodique ci-dessus ne verrait alors rien de neuf
  tant que ce tampon interne ne se vide pas de lui-même. Sans effet sur
  un -Commande qui n'est pas Python.

  $env:PYTHONUTF8=1 + $env:PYTHONIOENCODING=utf-8 (issue #875) : posés aux
  côtés de PYTHONUNBUFFERED ci-dessus. Sans eux, la sortie Python redirigée
  retombe sur l'encodage de la console Windows (cp1252), qui plante sur un
  caractère absent de cp1252 (UnicodeEncodeError — un print() contenant une
  flèche « → » arrêtait ainsi new_issue.py à CHAQUE mise à jour automatique
  réussie du dépôt) et mutile les accents qu'il sait écrire (octets cp1252
  mal relus comme de l'UTF-8 par Purger-SortieVersJournal plus bas,
  « Mise à jour » → « Mise ? jour »). En second rempart, new_issue.py,
  watcher.py et scripts/watcher_issues_inbox.py reconfigurent eux-mêmes
  leur sortie en UTF-8 dès leur démarrage (watcher.forcer_utf8) : un
  caractère malgré tout non encodable n'arrête donc plus jamais ces
  programmes, même sans ces variables.

  $env:BRIDGE_SOUS_SUPERVISEUR_SESSION=1 (issue #875) : indique à
  new_issue.py qu'il tourne sous CE superviseur, pour qu'il filtre de son
  propre journal d'accès werkzeug les requêtes répétitives (/heartbeat,
  fichiers statiques) qui, sinon, grossissent -FichierJournal sans fin.
  Sans effet sous Linux ni pour lancer_new_issue.sh (qui ne posent jamais
  cette variable).

  -FichierJournal est lui-même soumis à une rotation par taille (voir
  Roter-JournalSiNecessaire, $TailleMaxJournalMo/$NbArchivesJournal —
  issue #875) : au-delà du seuil, décalé en .1/.2/…, les plus anciens
  supprimés — nécessaire depuis que la sortie y est recopiée EN CONTINU
  (#871 ci-dessus) plutôt qu'une seule fois à l'arrêt.

  Code de sortie du process surveillé (issue #875) : lu via $proc.ExitCode
  juste après la boucle d'attente ci-dessous, dans son propre try/catch —
  une exception à CE point précis (code de sortie illisible, PAS un échec
  de lancement) est distinguée explicitement ($codeLisible = $false,
  message « illisible » dans le journal) plutôt que de se confondre avec
  un [ERREUR] lancement impossible. $proc.Handle est lu une fois, juste
  après Start-Process -PassThru (effet de bord voulu, valeur ignorée) :
  sans cet « attachement » précoce, .ExitCode peut lever une exception
  une fois le process déjà terminé (comportement documenté de
  System.Diagnostics.Process).

  -DelaiDemarrageSec (défaut 0, voir installer_demarrage_session.ps1
  -DelaiDemarrageWatchersSec) : attente, UNE SEULE FOIS avant le tout
  premier lancement (jamais répétée aux redémarrages suivants — ceux-ci
  restent régis par -DelaiRedemarrageSec), pour laisser un AUTRE composant
  démarré en même temps (l'interface web, qui fait la mise à jour
  automatique du dépôt) terminer avant que CE process-ci ne charge le
  code du dépôt de travail (issue #871, point 2). Posée ICI, dans le
  superviseur, plutôt que sur le déclencheur de la tâche planifiée
  (propriété « Delay » d'un trigger `-AtLogOn`) : cette dernière ne
  s'appliquerait qu'aux déclenchements PAR LA SESSION, pas à un
  Start-ScheduledTask lancé immédiatement après l'enregistrement (ce que
  fait installer_demarrage_session.ps1 à chaque exécution) — un
  Start-Sleep ici, en tête de script, couvre les deux cas sans exception,
  et fonctionne identiquement en -ModeService (NSSM lance ce MÊME script).

  Usage (appelé par installer_demarrage_session.ps1, rarement à la main) :
    powershell -File surveiller_processus_session.ps1 `
        -Commande "C:\Python312\python.exe" `
        -RepTravail "C:\Users\moi\Bridge_Agent" `
        -FichierJournal "C:\Users\moi\Bridge_Agent\logs\watcher-scrabble-session.log" `
        -FichierPid "C:\Users\moi\Bridge_Agent\logs\watcher-scrabble.pid" `
        -CodesSansRedemarrage "0,42" -DelaiRedemarrageSec 10 -DelaiDemarrageSec 20 `
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
    # Attente UNIQUE avant le tout premier lancement (voir en-tête) —
    # jamais ré-appliquée aux redémarrages suivants dans la boucle.
    [int]$DelaiDemarrageSec = 0,
    # Chemin + arguments du process surveillé — tout ce qui suit les
    # paramètres nommés ci-dessus (ex. "watcher.py" "--config" "x.conf").
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$ArgsEnfant = @()
)

$ErrorActionPreference = 'Stop'

# Sans effet sur un -Commande qui n'est pas Python — voir en-tête.
$env:PYTHONUNBUFFERED = '1'

# PYTHONUTF8 + PYTHONIOENCODING (issue #875) : la console Windows encode par
# défaut en cp1252. Dès que la sortie d'un programme Python est redirigée
# (ici vers un fichier temporaire, -RedirectStandardOutput/Error), Python
# garde cet encodage cp1252 — un print() contenant un caractère absent de
# cp1252 (ex. la flèche « → » du message de mise à jour automatique du dépôt
# de new_issue.py) lève alors UnicodeEncodeError et ARRÊTE le programme en
# plein affichage. Pire : les caractères accentués QUE cp1252 sait écrire
# (é, è…) produisent des octets cp1252 recopiés tels quels dans
# -FichierJournal, puis mal relus (StreamReader détecte l'absence de BOM et
# retombe sur de l'UTF-8 par défaut — voir Purger-SortieVersJournal) :
# « Mise à jour » devient « Mise ? jour ». PYTHONUTF8=1 force Python à
# utiliser l'UTF-8 pour tous ses flux (mode PEP 540, indépendant de la
# console) ; PYTHONIOENCODING=utf-8 le confirme explicitement pour
# stdout/stderr (ceinture et bretelles, au cas où -Commande n'est pas la
# même version de Python que celle qui a défini le défaut UTF8 mode). Une
# fois la sortie réellement en UTF-8 (sans BOM, comme l'écrit nativement
# l'encodeur "utf-8" de Python), elle est ensuite relue correctement par le
# StreamReader par défaut ci-dessous (même repli UTF-8 sans BOM). Sans effet
# sur un -Commande qui n'est pas Python.
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

# Repli DÉFENSIF en sus de PYTHONUTF8/PYTHONIOENCODING ci-dessus (issue
# #875) : new_issue.py, watcher.py et scripts/watcher_issues_inbox.py
# reconfigurent eux-mêmes sys.stdout/sys.stderr en UTF-8 avec
# errors="replace" dès leur démarrage (voir watcher.forcer_utf8, issue
# #698) — un caractère malgré tout non encodable ne doit donc JAMAIS arrêter
# ces programmes, même si les variables ci-dessus étaient absentes
# (lancement manuel hors de ce superviseur, par exemple).

# Indique à new_issue.py qu'il tourne sous CE superviseur (issue #875, point
# 3) : l'interface filtre alors de son propre journal d'accès werkzeug les
# requêtes répétitives (/heartbeat sondé en continu par le navigateur,
# fichiers statiques) avant qu'elles ne grossissent -FichierJournal — sans
# effet sous Linux ni pour lancer_new_issue.sh, qui ne posent jamais cette
# variable.
$env:BRIDGE_SOUS_SUPERVISEUR_SESSION = '1'

# Intervalle de purge de la sortie/erreur du process surveillé vers
# -FichierJournal PENDANT qu'il tourne encore (voir Purger-SortieVersJournal
# et la boucle principale plus bas) — pas un réglage fin, juste un filet de
# sécurité contre la perte totale d'un arrêt brutal (issue #871).
$IntervalleJournalMs = 2000

# Rotation par taille de -FichierJournal (issue #875, point 4) : depuis que
# la sortie du process surveillé y est recopiée EN CONTINU (#871), ce journal
# grossit sans fin — en particulier celui de l'interface web, où chaque
# requête HTTP (dont /heartbeat, sondé par le navigateur toutes les quelques
# secondes) ajoute une ligne. Mêmes grandeurs que watcher.py::JournalRotatif
# Date côté défaut (LOG_TAILLE_MAX_MO=1, LOG_ARCHIVES=5), légèrement
# assoupli ici (2 Mo) car ce journal n'est qu'une COPIE brute de texte
# (aucune structure à préserver) — voir Roter-JournalSiNecessaire plus bas.
# Pas des paramètres du script : comme $IntervalleJournalMs, un simple filet
# de sécurité, pas un réglage que l'appelant ait besoin d'ajuster.
$TailleMaxJournalMo = 2
$NbArchivesJournal = 3

$CodesArret = $CodesSansRedemarrage -split ',' | ForEach-Object { [int]$_.Trim() }

function Horodate { (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') }

# Rotation par taille de -FichierJournal (voir $TailleMaxJournalMo/
# $NbArchivesJournal en tête de script) : décale .1 -> .2 … -> $NbArchives
# Journal (supprimée), puis le fichier actif -> .1. Appelée en tête des deux
# seules fonctions qui écrivent dans -FichierJournal (Ecrire-Journal et
# Purger-SortieVersJournal), donc avant CHAQUE écriture — Get-Item sur un
# simple chemin est peu coûteux face à l'intervalle de purge (2 s). Toute
# exception (verrou transitoire) est avalée : au pire la rotation suivante
# rattrape, jamais une interruption du superviseur pour ce seul confort.
function Roter-JournalSiNecessaire {
    try {
        if (-not (Test-Path $FichierJournal)) { return }
        if ((Get-Item $FichierJournal).Length -lt ($TailleMaxJournalMo * 1MB)) { return }
        for ($i = $NbArchivesJournal; $i -ge 1; $i--) {
            $cible = "$FichierJournal.$i"
            if ($i -eq $NbArchivesJournal) {
                Remove-Item -Path $cible -Force -ErrorAction SilentlyContinue
            }
            $source = if ($i -eq 1) { $FichierJournal } else { "$FichierJournal.$($i - 1)" }
            if (Test-Path $source) {
                Move-Item -Path $source -Destination $cible -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
        # Avalée volontairement — voir le commentaire ci-dessus.
    }
}

function Ecrire-Journal([string]$Texte) {
    Roter-JournalSiNecessaire
    Add-Content -Path $FichierJournal -Value $Texte -Encoding UTF8
}

# Copie, SANS relire depuis le début (position suivie par l'appelant via
# -Position), tout ce qui a été écrit dans $CheminTemp depuis le dernier
# appel, vers -FichierJournal. -FileShare ReadWrite : le process surveillé
# garde SA PROPRE poignée d'écriture ouverte sur ce même fichier tout ce
# temps (redirection Start-Process) — sans ce partage explicite, l'ouverture
# en lecture ci-dessous échouerait tant qu'il tourne.
#
# Toute exception (verrou transitoire, antivirus, etc.) est AVALÉE ici,
# jamais remontée à l'appelant : cette fonction est appelée depuis la
# boucle `while (-not $proc.HasExited)` juste en dessous, À L'INTÉRIEUR du
# try/catch qui entoure Start-Process — sans ce garde-fou, une exception
# ici serait journalisée comme un faux « [ERREUR] lancement impossible »,
# sortirait de la boucle AVANT la fin réelle du process (donc $code jamais
# réassigné depuis $proc.ExitCode, resterait à -1) et provoquerait un
# second lancement du MÊME composant en parallèle de l'ancien process
# (toujours vivant, non surveillé) à la prochaine itération — exactement
# la double instance que ce script existe pour empêcher. Une purge
# manquée ici n'est qu'un retard : la purge SUIVANTE (ou celle, finale,
# du bloc `finally`) rattrapera le texte non copié.
function Purger-SortieVersJournal([string]$CheminTemp, [ref]$Position) {
    try {
        if (-not (Test-Path $CheminTemp)) { return }
        $flux = [System.IO.File]::Open($CheminTemp, [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        try {
            if ($flux.Length -le $Position.Value) { return }
            $flux.Seek($Position.Value, [System.IO.SeekOrigin]::Begin) | Out-Null
            $lecteur = New-Object System.IO.StreamReader($flux)
            $texte = $lecteur.ReadToEnd()
            $Position.Value = $flux.Position
            if ($texte) {
                Roter-JournalSiNecessaire
                Add-Content -Path $FichierJournal -Value $texte -Encoding UTF8 -NoNewline
            }
        } finally {
            $flux.Dispose()
        }
    } catch {
        # Avalée volontairement — voir le commentaire ci-dessus.
    }
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

# Attente UNIQUE avant le tout premier lancement (voir -DelaiDemarrageSec en
# en-tête) — PAS répétée aux redémarrages suivants, régis par
# -DelaiRedemarrageSec dans la boucle ci-dessous.
if ($DelaiDemarrageSec -gt 0) {
    Ecrire-Journal ("$(Horodate) [ATTENTE] démarrage différé de $DelaiDemarrageSec s " +
                    "(laisser l'interface web terminer sa mise à jour du dépôt).")
    Start-Sleep -Seconds $DelaiDemarrageSec
}

while ($true) {
    Ecrire-Journal "$(Horodate) [DEMARRAGE] $Commande $($ArgsEnfant -join ' ')"

    $tmpOut = [System.IO.Path]::GetTempFileName()
    $tmpErr = [System.IO.Path]::GetTempFileName()
    $positionOut = 0
    $positionErr = 0
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
    # Distinct de $code = -1 ci-dessus : -1 signifie « jamais démarré » (donc
    # jamais arrivé jusqu'à l'essai de lecture du code ci-dessous), alors que
    # $codeLisible = $false signifie « démarré, terminé, mais son code de
    # sortie n'a pas pu être lu » (issue #875, point 2) — deux causes
    # distinctes, deux messages distincts plus bas.
    $codeLisible = $true
    try {
        try {
            $proc = Start-Process -FilePath $Commande -ArgumentList $ArgsEnfant `
                -WorkingDirectory $RepTravail -NoNewWindow -PassThru `
                -RedirectStandardOutput $tmpOut -RedirectStandardError $tmpErr

            # Force .NET à ouvrir un handle natif du process (PROCESS_QUERY_
            # INFORMATION) DÈS MAINTENANT, pendant qu'il est garanti vivant —
            # hypothèse de l'issue #875 point 2, confirmée en relecture :
            # sans lire .Handle une première fois juste après Start-Process,
            # la propriété .ExitCode lue plus bas (une fois le process déjà
            # terminé) peut lever "Process has not exited, or the Handle
            # attribute has not been set" — contournement documenté de ce
            # comportement de System.Diagnostics.Process. La valeur elle-même
            # ($null ici) ne sert à rien, seul l'EFFET DE BORD (ouverture du
            # handle) compte.
            $null = $proc.Handle

            if ($FichierPid) { Set-Content -Path $FichierPid -Value $proc.Id -Encoding ASCII }

            # Purge PENDANT que le process tourne encore (issue #871), pas
            # seulement à son arrêt : WaitForExit(ms) sert ici à la fois
            # d'attente ET de détection de fin, sans boucle d'attente active
            # séparée (il rend dès que le process se termine, même avant le
            # délai complet).
            while (-not $proc.HasExited) {
                Purger-SortieVersJournal $tmpOut ([ref]$positionOut)
                Purger-SortieVersJournal $tmpErr ([ref]$positionErr)
                $proc.WaitForExit($IntervalleJournalMs) | Out-Null
            }
            # Lecture du code de sortie isolée dans son PROPRE try/catch
            # (issue #875, point 2) : si .Handle ci-dessus ne suffisait pas à
            # garantir sa lisibilité (cas limite non exclu), cette exception
            # ne doit pas être confondue avec un échec de LANCEMENT (catch
            # externe, message "lancement impossible" — le process, lui, a
            # bel et bien démarré et tourné).
            try {
                $code = $proc.ExitCode
            } catch {
                $codeLisible = $false
                Ecrire-Journal "$(Horodate) [ERREUR] code de sortie illisible : $($_.Exception.Message)"
            }
        } catch {
            Ecrire-Journal "$(Horodate) [ERREUR] lancement impossible : $($_.Exception.Message)"
        }
    } finally {
        # Dernière purge : ce qui a pu être écrit entre le dernier passage
        # de la boucle ci-dessus et la fin réelle du process.
        Purger-SortieVersJournal $tmpOut ([ref]$positionOut)
        Purger-SortieVersJournal $tmpErr ([ref]$positionErr)
        foreach ($tmp in @($tmpOut, $tmpErr)) {
            Remove-Item -Path $tmp -Force -ErrorAction SilentlyContinue
        }
        if ($FichierPid -and (Test-Path $FichierPid)) {
            Remove-Item -Path $FichierPid -Force -ErrorAction SilentlyContinue
        }
    }

    # Texte affiché dans les deux messages ci-dessous (issue #875, point 2) :
    # le code lui-même s'il a pu être lu, sinon « illisible » — jamais une
    # ligne vide, contrairement au symptôme constaté lors de l'essai réel.
    $texteCode = if ($codeLisible) { "$code" } else { 'illisible' }
    Ecrire-Journal "$(Horodate) [ARRET] code de sortie : $texteCode"

    if ($codeLisible -and $CodesArret -contains $code) {
        Ecrire-Journal "$(Horodate) [FIN] arrêt propre (code $code dans « $CodesSansRedemarrage ») — pas de redémarrage."
        break
    }

    Ecrire-Journal "$(Horodate) [REDEMARRAGE] code $texteCode inattendu — nouvelle tentative dans $DelaiRedemarrageSec s…"
    Start-Sleep -Seconds $DelaiRedemarrageSec
}
