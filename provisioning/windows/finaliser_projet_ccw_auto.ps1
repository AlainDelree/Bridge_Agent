<#
  finaliser_projet_ccw_auto.ps1 — Finaliser un projet CCW À DISTANCE, sans
  aucune saisie interactive (issue #174, variante non interactive de
  finaliser_projet_ccw.ps1 / issue #173).

  Pensé pour être poussé + exécuté par l'onglet CCW de l'interface web (Linux)
  via « VBoxManage guestcontrol ». Là où finaliser_projet_ccw.ps1 demande
  TOPIC_NTFY (Read-Host), fait une pause pour créer le token puis appelle la
  version interactive de mettre_a_jour_tokens_ccw.ps1, CE script lit TOUTES les
  valeurs (TOPIC_NTFY + les deux tokens) dans un fichier « clé=valeur » fourni
  par l'appelant, puis :

    1. dérive (même logique qu'ajouter_projet_ccw.ps1) le service
       CCW-Watcher-<NomProjet>, le dossier C:\CCW\<NomProjet> et le config
       configs\<nom-minuscule>-ccw.conf, et vérifie leur existence — SAUF pour
       le projet historique « Bridge_Agent », créé par provisionner.ps1 avant
       la généralisation #170, dont le service s'appelle « CCW-Watcher » (sans
       suffixe), config configs\ccw.conf, log ccw-service.log : même spécial-cas
       que lister_projets_ccw.ps1 (issue #177) ;
    2. réécrit la ligne TOPIC_NTFY du config avec la valeur TOPIC_NTFY lue,
       QUELLE QUE SOIT sa valeur actuelle (placeholder OU topic déjà
       renseigné) — remplacement ciblé de la seule ligne « TOPIC_NTFY = … »,
       UTF-8 sans BOM — logique identique à finaliser_projet_ccw.ps1,
       dupliquée à dessein : ~10 lignes, pour rester exécutable seul sans
       dot-sourcing) ;
    3. APPELLE mettre_a_jour_tokens_ccw.ps1 en mode -FichierTokens (aucune
       duplication de la logique métier des tokens : construction de
       AppEnvironmentExtra, nssm set/restart, vérification des logs) en lui
       passant le MÊME fichier de valeurs (il n'y lit que GH_TOKEN et
       CLAUDE_CODE_OAUTH_TOKEN).

  SÉCURITÉ : les tokens ne transitent JAMAIS en argument de ligne de commande
  (invisibles dans les process/event logs Windows) — seulement via le fichier,
  poussé par guestcontrol copyto avec des permissions restreintes. Ce script
  SUPPRIME ce fichier dans un finally (nettoyage côté VM) ; l'appelant Linux
  supprime de son côté sa copie locale (nettoyage des deux côtés).

  Le code de sortie est celui de mettre_a_jour_tokens_ccw.ps1 (0 = OK,
  2 = à vérifier, 1 = abandon), pour que l'appelant conclue sans ambiguïté.

  Prérequis : le projet doit AVOIR ÉTÉ CRÉÉ par ajouter_projet_ccw.ps1.
  mettre_a_jour_tokens_ccw.ps1 doit être présent dans le MÊME dossier que ce
  script (l'appelant pousse les deux ensemble dans C:\Windows\Temp).
#>

[CmdletBinding()]
param(
    # Nom du projet, tel que passé à ajouter_projet_ccw.ps1 (ex. Scrabble).
    [Parameter(Mandatory = $true)]
    [string]$NomProjet,

    # Fichier « clé=valeur » (UTF-8) contenant TOPIC_NTFY, GH_TOKEN et
    # CLAUDE_CODE_OAUTH_TOKEN. Poussé par l'appelant, supprimé ici (finally).
    [Parameter(Mandatory = $true)]
    [string]$FichierValeurs,

    # Racine de travail dédiée à CCW côté invité (comme les autres scripts CCW).
    [string]$RepCCW = 'C:\CCW'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Info($msg)  { Write-Host "[finaliser-auto] $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "[finaliser-auto] $msg" -ForegroundColor Green }
function Avert($msg) { Write-Host "[finaliser-auto] AVERTISSEMENT : $msg" -ForegroundColor Yellow }

# Lit une valeur « CLE=valeur » dans le fichier de valeurs (helper local, ~8
# lignes, identique à celui de mettre_a_jour_tokens_ccw.ps1 : dupliqué pour que
# ce script reste autonome). Ne rogne que le CR/LF de fin ; la valeur n'est
# jamais affichée.
function Lire-ValeurFichier([string]$chemin, [string]$cle) {
    foreach ($ligne in [System.IO.File]::ReadAllLines($chemin)) {
        $idx = $ligne.IndexOf('=')
        if ($idx -lt 1) { continue }
        if ($ligne.Substring(0, $idx).Trim() -eq $cle) {
            return $ligne.Substring($idx + 1).TrimEnd("`r", "`n")
        }
    }
    return $null
}

try {
    if (-not (Test-Path $FichierValeurs)) {
        Avert "Fichier de valeurs introuvable : $FichierValeurs — abandon."
        exit 1
    }

    # -----------------------------------------------------------------------
    # 1. Dérivation des chemins (IDENTIQUE à ajouter_projet_ccw.ps1 /
    #    finaliser_projet_ccw.ps1) + vérification d'existence.
    # -----------------------------------------------------------------------
    $NomProjet  = $NomProjet.Trim()
    if ([string]::IsNullOrWhiteSpace($NomProjet)) { throw 'Nom de projet vide — abandon.' }

    # Cas particulier du projet historique « Bridge_Agent » (issue #177) : son
    # service a été créé par provisionner.ps1 AVANT la généralisation
    # multi-projets (#170), donc SANS suffixe (« CCW-Watcher » tout court) ni
    # préfixe minuscule dans les noms de config/log. On reproduit EXACTEMENT le
    # même spécial-cas que lister_projets_ccw.ps1, avec les valeurs littérales de
    # provisionner.ps1 (NomService 'CCW-Watcher', config 'ccw.conf', log
    # 'ccw-service.log', dossier C:\CCW\Bridge_Agent). Sans cela, un appel
    # « -NomProjet Bridge_Agent » ciblerait à tort le service inexistant
    # « CCW-Watcher-Bridge_Agent ». Comparaison insensible à la casse (-ieq).
    if ($NomProjet -ieq 'Bridge_Agent') {
        $NomService = 'CCW-Watcher'
        $RepDepot   = Join-Path $RepCCW 'Bridge_Agent'
        $NomConf    = 'ccw.conf'
        $NomLog     = 'ccw-service.log'
    } else {
        $nomMin     = $NomProjet.ToLowerInvariant()
        $NomService = "CCW-Watcher-$NomProjet"
        $RepDepot   = Join-Path $RepCCW $NomProjet
        $NomConf    = "$nomMin-ccw.conf"
        $NomLog     = "ccw-$nomMin-service.log"
    }
    $CheminConf = Join-Path (Join-Path $RepDepot 'configs') $NomConf

    Info "Projet      : $NomProjet"
    Info "Service     : $NomService"
    Info "Config      : $CheminConf"
    Info "Log service : logs\$NomLog"

    if (-not (Test-Path (Join-Path $RepDepot '.git'))) {
        Avert "Dossier « $RepDepot » absent : le projet « $NomProjet » n'a pas encore été créé (ajouter_projet_ccw.ps1)."
        exit 1
    }
    if (-not (Test-Path $CheminConf)) {
        Avert "Config « $CheminConf » introuvable : projet « $NomProjet » mal créé (ajouter_projet_ccw.ps1)."
        exit 1
    }
    if (-not (Get-Service -Name $NomService -ErrorAction SilentlyContinue)) {
        Avert "Service « $NomService » introuvable : projet « $NomProjet » non enregistré (ajouter_projet_ccw.ps1)."
        exit 1
    }

    # -----------------------------------------------------------------------
    # 2. TOPIC_NTFY : réécriture CIBLÉE de la ligne « TOPIC_NTFY = … » du
    #    config (logique identique à finaliser_projet_ccw.ps1, édition ciblée).
    #    On remplace la ligne QUELLE QUE SOIT sa valeur actuelle (placeholder
    #    ###TOPIC_NTFY_A_DEFINIR### OU topic déjà renseigné) — issue #176 : le
    #    topic doit rester modifiable après sa première définition, comme les
    #    tokens. Seul un topic vide côté formulaire laisse le config inchangé.
    # -----------------------------------------------------------------------
    $topic = Lire-ValeurFichier $FichierValeurs 'TOPIC_NTFY'
    if ($null -ne $topic) { $topic = $topic.Trim() }

    # Motif ciblé sur la ligne « TOPIC_NTFY = <n'importe quoi> » (multi-lignes).
    # [^\r\n]* : on s'arrête à la fin de ligne SANS avaler le CR/LF, pour
    # préserver les fins de ligne (CRLF côté Windows) telles quelles. Fonctionne
    # aussi bien pour la première définition (placeholder) que pour un changement.
    $motifTopic = '(?m)^[ \t]*TOPIC_NTFY[ \t]*=[^\r\n]*'
    $contenuConf = [System.IO.File]::ReadAllText($CheminConf)

    if ([string]::IsNullOrWhiteSpace($topic)) {
        Info 'TOPIC_NTFY non fourni — étape topic ignorée (seuls les tokens seront posés).'
    } elseif ($contenuConf -match $motifTopic) {
        # Remplacement littéral (MatchEvaluator) : aucun caractère du topic
        # n'est interprété comme référence regex ($1, $$…). Seule la ligne
        # TOPIC_NTFY change, le reste du fichier est préservé à l'identique.
        $ligneTopic  = "TOPIC_NTFY  = $topic"
        $contenuConf = [regex]::Replace($contenuConf, $motifTopic, { $ligneTopic })
        # UTF-8 SANS BOM (le parseur .conf de watcher.py l'attend ainsi).
        [System.IO.File]::WriteAllText($CheminConf, $contenuConf, (New-Object System.Text.UTF8Encoding($false)))
        Ok "TOPIC_NTFY (re)défini à « $topic » dans $CheminConf."
    } else {
        Avert "Aucune ligne TOPIC_NTFY trouvée dans $CheminConf — config inchangé (fichier inattendu ?)."
    }

    # -----------------------------------------------------------------------
    # 3. Pose des tokens : on APPELLE mettre_a_jour_tokens_ccw.ps1 en mode
    #    non interactif (-FichierTokens). Aucune duplication de la logique des
    #    tokens : construction de AppEnvironmentExtra, nssm set/restart, vérif.
    # -----------------------------------------------------------------------
    $scriptTokens = Join-Path $PSScriptRoot 'mettre_a_jour_tokens_ccw.ps1'
    if (-not (Test-Path $scriptTokens)) {
        throw "Script attendu introuvable : $scriptTokens (doit être poussé dans le même dossier)."
    }

    Info "Pose des tokens sur « $NomService » via mettre_a_jour_tokens_ccw.ps1 (mode fichier)…"
    Write-Host ''
    & $scriptTokens -NomService $NomService -RepDepot $RepDepot -NomLog $NomLog -FichierTokens $FichierValeurs
    $codeTokens = $LASTEXITCODE

    Write-Host ''
    Write-Host '======================================================================'
    if ($codeTokens -eq 0) {
        Ok "Projet « $NomProjet » FINALISÉ : TOPIC_NTFY renseigné, tokens posés, service redémarré."
    } else {
        Avert "Projet « $NomProjet » : TOPIC_NTFY et tokens appliqués, mais vérification finale non concluante (code $codeTokens)."
    }
    Write-Host '======================================================================'

    exit $codeTokens
}
finally {
    # Nettoyage côté VM : suppression du fichier de valeurs quoi qu'il arrive.
    # (L'appelant Linux supprime de son côté sa copie locale — nettoyage des
    # deux côtés.)
    if (Test-Path $FichierValeurs) {
        Remove-Item -Path $FichierValeurs -Force -ErrorAction SilentlyContinue
    }
}
