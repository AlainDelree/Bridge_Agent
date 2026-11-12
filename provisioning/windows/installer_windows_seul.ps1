<#
  installer_windows_seul.ps1 — Installation de Bridge_Agent sur un PC Windows
  SEUL (pas de second poste CCW délégué), SANS droits d'administrateur
  (issue #874, suite de GUIDE_INSTALLATION_WINDOWS_SEUL.md et de son premier
  essai réel, §13 du guide).

  Automatise ce que le guide décrit à la main : vérification de
  l'environnement, Git/GitHub CLI/Python (winget), contournement de l'alias
  Python du Microsoft Store pour la session en cours, clonage du dépôt,
  `identite_locale.conf` (COPIE_NON_PROPRIETAIRE/MAJ_AUTO_DEPOT/
  MACHINE_SEULE, issues #868/#869/#870), dépendances de l'interface web,
  option Mistral Vibe (version figée), et un raccourci `bridge` pour ouvrir
  l'interface d'un mot depuis un terminal. CE script ne contredit jamais le
  guide : toute étape qui reste manuelle dans le guide (connexion GitHub,
  connexion Vibe, création du premier projet, démarrage de session) reste
  manuelle ici aussi — ce script ne fait qu'automatiser ce qui, dans le
  guide, est déjà sans interaction humaine obligatoire.

  ┌─────────────────────────────────────────────────────────────────────────┐
  │ DIFFÉRENCE DÉLIBÉRÉE avec provisionner.ps1 (rôle CCW) : CE script UTILISE│
  │ winget (voir « Pourquoi plus de winget » dans provisionner.ps1, issue    │
  │ #658, qui l'abandonne). Le contexte est différent : provisionner.ps1     │
  │ cible le PC fixe d'Alain (Windows 11 IoT Enterprise LTSC, où le          │
  │ bootstrap de winget échoue), ET une console ADMINISTRATEUR, ce qui rend  │
  │ les installeurs officiels téléchargés directement praticables. ICI,      │
  │ sans droits d'administrateur, ces installeurs directs (souvent des MSI   │
  │ qui demandent une élévation) ne conviennent pas, alors que winget sait   │
  │ installer Git/GitHub CLI/Python pour l'utilisateur courant SANS          │
  │ élévation — et c'est bien winget qui a été utilisé avec succès pendant  │
  │ le premier essai réel du guide (§13, Windows 11 ordinaire, constaté).    │
  │ Si winget est absent (édition sans Microsoft Store), ce script le       │
  │ signale clairement et saute l'installation automatique (§2) — à faire   │
  │ alors à la main depuis les sites officiels, comme le dit le guide.       │
  └─────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────┐
  │ CHOIX DE CONCEPTION — raccourci « bridge » (§10 de l'issue, point       │
  │ sensible) :                                                              │
  │                                                                          │
  │ 1. PAS de fonction ajoutée au profil PowerShell ($PROFILE), contrairement│
  │    à NEW_ISSUE_LOCAL_WINDOWS.md §2 (alias historique, pour --lan) : une  │
  │    fonction de profil ne se charge QUE si la politique d'exécution      │
  │    autorise le chargement des scripts de profil — sur un compte neuf,   │
  │    la politique par défaut (Restricted) bloque ce chargement, et la     │
  │    changer (Set-ExecutionPolicy) est un réglage DE LA MACHINE, que ce    │
  │    script ne doit jamais toucher (consigne explicite de la tâche).       │
  │ 2. À la place : un petit lanceur `bridge.cmd` (+ `bridge_lanceur.ps1`    │
  │    à côté) posés dans $env:USERPROFILE\.local\bin — dossier déjà ajouté │
  │    au PATH UTILISATEUR par l'installeur officiel de `uv` (§6 du guide)  │
  │    s'il est déjà passé par là, sinon ajouté ici au PATH UTILISATEUR      │
  │    (PAS machine, et affiché avant d'être fait). `bridge.cmd` invoque     │
  │    PowerShell avec `-ExecutionPolicy Bypass` POUR CET APPEL SEUL (comme  │
  │    toutes les commandes `.ps1` de ce dépôt, voir §2 du guide) : aucune   │
  │    politique d'exécution n'est modifiée de façon persistante.            │
  │ 3. `bridge.cmd` fonctionne identiquement dans PowerShell ET l'invite de  │
  │    commandes classique (cmd.exe), contrairement à une fonction de       │
  │    profil PowerShell qui ne vaudrait que pour PowerShell.                │
  │ 4. Avant de lancer une seconde fois l'interface web, le lanceur teste si │
  │    elle répond déjà sur 127.0.0.1:5100 (cas où les tâches de démarrage   │
  │    de session, §9 du guide, tournent déjà) — sinon conflit de port.      │
  │ 5. (issue #876) `new_issue.py` est démarré avec `--no-browser` : c'est   │
  │    le lanceur, pas `new_issue.py`, qui ouvre le navigateur — une seule   │
  │    fois, après avoir attendu (jusqu'à ~60 s) que le port réponde          │
  │    vraiment. Avant #876, le lanceur attendait 2 s fixes puis ouvrait son │
  │    propre onglet ET laissait `new_issue.py` ouvrir le sien : sur une mise│
  │    à jour automatique plus longue que 2 s (§3 du guide), le premier      │
  │    onglet tombait sur « Unable to connect ». La console de              │
  │    `new_issue.py` reste VISIBLE (pas -WindowStyle Hidden) : voir le      │
  │    commentaire dans `bridge_lanceur.ps1` généré, même raison.            │
  └─────────────────────────────────────────────────────────────────────────┘

  Idempotent : relançable sans dommage. `identite_locale.conf` n'est jamais
  écrasé s'il existe déjà ; un dépôt déjà cloné n'est que mis à jour en
  avance rapide (`git pull --ff-only`, jamais de réécriture) ; le raccourci
  `bridge` est régénéré avec les mêmes noms de fichiers (jamais de doublon) ;
  chaque installation (winget, uv, vibe) est sautée si déjà présente.

  Mode -DryRun : affiche toutes les actions prévues sans rien installer,
  cloner, écrire ni démarrer.

  Prérequis : une vraie console (Windows PowerShell ou Terminal — PAS
  PowerShell ISE, ni la fenêtre « (x86) », voir §2 du guide), PowerShell 5.1
  (inclus dans Windows), accès Internet sortant. AUCUN droit administrateur
  requis. Peut être lancé AVANT même d'avoir cloné le dépôt (voir §2/§3 du
  guide pour la commande qui télécharge ce seul fichier et l'exécute pour la
  session en cours, SANS modifier la politique d'exécution de la machine).

  Exemples :
    # Simulation complète (rien n'est modifié) :
    powershell -NoProfile -ExecutionPolicy Bypass -File .\installer_windows_seul.ps1 -DryRun

    # Installation standard (Mistral Vibe ET le garde-fou anti-push sont
    # ACTIFS PAR DÉFAUT depuis l'issue #876) :
    powershell -NoProfile -ExecutionPolicy Bypass -File .\installer_windows_seul.ps1

    # Sans Mistral Vibe, et sans le garde-fou anti-push (déconseillé) :
    powershell -NoProfile -ExecutionPolicy Bypass -File .\installer_windows_seul.ps1 -SansVibe -SansProtegerPush

    # Dossier différent du défaut ($env:USERPROFILE\Bridge_Agent) :
    powershell -NoProfile -ExecutionPolicy Bypass -File .\installer_windows_seul.ps1 -Dossier D:\Outils\Bridge_Agent

    # Retirer uniquement le raccourci 'bridge' (laisse tout le reste intact) :
    powershell -NoProfile -ExecutionPolicy Bypass -File .\installer_windows_seul.ps1 -RetirerRaccourciBridge
#>

[CmdletBinding()]
param(
    # Dossier où cloner (ou retrouver) la copie de l'outil — défaut conforme
    # au §3 du guide. Doit être accessible en écriture SANS administrateur :
    # un dossier protégé (Program Files, Windows) est refusé explicitement.
    [string]$Dossier = (Join-Path $env:USERPROFILE 'Bridge_Agent'),

    # Dépôt à cloner — ne changer que pour un fork/test.
    [string]$Depot = 'https://github.com/AlainDelree/Bridge_Agent.git',

    # Règle l'URL de PUSH du dépôt (PAS de fetch) sur une valeur invalide :
    # cette copie ne pourra alors jamais pousser vers le dépôt d'origine,
    # même par erreur (ex. commande lancée dans le mauvais dossier). ACTIF
    # PAR DÉFAUT depuis l'issue #876 : cette installation (réglage
    # COPIE_NON_PROPRIETAIRE) ne doit jamais pousser vers le dépôt d'Alain.
    # -SansProtegerPush désactive ce garde-fou (déconseillé).
    [switch]$SansProtegerPush,

    # Installe en plus Mistral Vibe (uv + mistral-vibe, version figée) et les
    # profils d'agent (bridge_ecriture.toml en écriture, bridge_lecture.toml
    # en lecture seule depuis l'issue #885 — tout provisioning\vibe\agents\)
    # — §6 du guide. La connexion par compte (`vibe --setup`) reste manuelle
    # (console réelle requise). ACTIF PAR DÉFAUT depuis l'issue #876 : Vibe
    # est l'agent de toute cette installation. -SansVibe l'ignore (à faire
    # soi-même plus tard si besoin).
    [switch]$SansVibe,

    # Version figée de mistral-vibe installée (sauf -SansVibe) — JAMAIS
    # "latest" (voir §6 du guide : la 3.1.1 a bloqué une première issue plus
    # de 8 minutes, cause non isolée). Ne changer que volontairement.
    [string]$VersionVibe = '3.1.0',

    # Affiche la commande prête à l'emploi de installer_demarrage_session.ps1
    # (avec ses paramètres expliqués) — ne l'exécute JAMAIS automatiquement,
    # avec ou sans cette option : §9 du guide reste une étape volontairement
    # manuelle (choix des projets à surveiller, encore inexistants à ce
    # stade de l'installation).
    [switch]$ProposerDemarrage,

    # Retire UNIQUEMENT le raccourci 'bridge' (bridge.cmd + bridge_lanceur.ps1
    # dans $env:USERPROFILE\.local\bin), sans toucher au reste de
    # l'installation (dépôt, identite_locale.conf, Vibe…), puis quitte. Le
    # dossier .local\bin lui-même n'est PAS retiré du PATH utilisateur (il
    # peut être partagé avec d'autres outils, ex. uv).
    [switch]$RetirerRaccourciBridge,

    # Affiche les actions prévues SANS rien installer, cloner, écrire ni
    # démarrer.
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Info($msg)  { Write-Host "[installer-windows-seul] $msg" -ForegroundColor Cyan }
function Avert($msg) { Write-Host "[installer-windows-seul] AVERTISSEMENT : $msg" -ForegroundColor Yellow }
function Ok($msg)    { Write-Host "[installer-windows-seul] $msg" -ForegroundColor Green }
function Etape($n, $titre) {
    Write-Host ''
    Write-Host "=== Étape $n : $titre ===" -ForegroundColor Magenta
}

# Invoke-CommandeNativeSansArret — exécute une commande EXTERNE (gh, winget,
# vibe, python…) dont la sortie d'erreur ne doit JAMAIS arrêter ce script,
# même sous $ErrorActionPreference = 'Stop' (issue #876) : sous PowerShell
# 5.1, fusionner la sortie d'erreur d'une commande native avec `2>&1`
# transforme CHAQUE ligne de cette sortie en erreur TERMINANTE
# (NativeCommandError) dès que $ErrorActionPreference vaut 'Stop' — même
# quand il ne s'agit que d'un simple message (ex. gh pas encore connecté),
# sans aucun échec réel. Remède : remettre $ErrorActionPreference à
# 'Continue' pendant CET appel précis seulement, puis le restaurer — jamais
# de façon globale ni persistante. Un vrai échec reste détectable par
# l'appelant via le code de sortie renvoyé (.CodeSortie).
function Invoke-CommandeNativeSansArret {
    param([Parameter(Mandatory)][scriptblock]$Commande)
    $precedent = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $sortie = (& $Commande 2>&1 | Out-String)
        return [PSCustomObject]@{ Sortie = $sortie; CodeSortie = $LASTEXITCODE }
    } finally {
        $ErrorActionPreference = $precedent
    }
}

# Suivi pour le résumé final (§12 de l'issue) : ce qui a été fait (mode réel),
# ce qui SERAIT fait (mode -DryRun, jamais confondu avec ce qui précède —
# issue #876), ce qui a été ignoré (déjà en place), les étapes manuelles qui
# restent — DANS L'ORDRE.
$script:ActionsFaites    = @()
$script:ActionsPrevues   = @()
$script:ActionsIgnorees  = @()
$script:EtapesManuelles  = @()

# Dossier du raccourci 'bridge' — fixe, indépendant de -Dossier, pour que
# -RetirerRaccourciBridge le retrouve même sans repasser -Dossier.
$RepBinUtilisateur   = Join-Path $env:USERPROFILE '.local\bin'
$CheminBridgeCmd     = Join-Path $RepBinUtilisateur 'bridge.cmd'
$CheminBridgeLanceur = Join-Path $RepBinUtilisateur 'bridge_lanceur.ps1'

# ---------------------------------------------------------------------------
# -RetirerRaccourciBridge : mode autonome, ne dépend d'aucune autre étape
# (même pattern que -Desinstaller dans installer_demarrage_session.ps1).
# ---------------------------------------------------------------------------
if ($RetirerRaccourciBridge) {
    Info "=== Retrait du raccourci 'bridge' ==="
    $retire = $false
    foreach ($f in @($CheminBridgeCmd, $CheminBridgeLanceur)) {
        if (Test-Path $f) {
            $retire = $true
            if ($DryRun) {
                Info "[DRY-RUN] Supprimerait $f."
            } else {
                Remove-Item -Path $f -Force
                Info "Supprimé : $f"
            }
        }
    }
    if ($retire) {
        if ($DryRun) { Info "Mode -DryRun : rien n'a été supprimé réellement — voir ce qui serait supprimé ci-dessus." }
        else { Ok "Raccourci 'bridge' retiré." }
    } else {
        Info "Raccourci 'bridge' absent — rien à retirer."
    }
    Info "$RepBinUtilisateur reste dans le PATH utilisateur (peut être partagé avec d'autres outils, ex. uv) — non retiré."
    return
}

# ---------------------------------------------------------------------------
# Étape 1 — Environnement : console (pas ISE, pas la fenêtre 32 bits sur un
# Windows 64 bits), winget présent. Voir §2 du guide pour le détail de
# chaque piège.
# ---------------------------------------------------------------------------
Etape 1 'Vérification de l''environnement'

$EnISE = ($host.Name -eq 'Windows PowerShell ISE Host')
if ($EnISE) {
    $msg = ("Cette fenêtre est 'PowerShell ISE' : des étapes manuelles qui suivent (ex. 'vibe --setup', §6 du " +
            "guide) y échouent ('Interactive mode needs a terminal'). Rouvrez 'Windows PowerShell' ou " +
            "'Terminal', puis relancez ce script.")
    if ($DryRun) { Avert $msg } else { throw $msg }
}

# PROCESSOR_ARCHITEW6432 n'existe QUE pour un process 32 bits tournant par
# WOW64 sur un Windows 64 bits — exactement la fenêtre « (x86) » du guide.
$En32SurOS64 = [bool](Get-Item Env:\PROCESSOR_ARCHITEW6432 -ErrorAction SilentlyContinue)
if ($En32SurOS64) {
    $msg = ("Cette fenêtre semble être la version 32 bits ('(x86)') de PowerShell sur un Windows 64 bits — " +
            "à éviter (§2 du guide). Rouvrez 'Windows PowerShell' (pas '(x86)'), puis relancez ce script.")
    if ($DryRun) { Avert $msg } else { throw $msg }
}

if (-not $EnISE -and -not $En32SurOS64) { Info "Console correcte (ni ISE, ni fenêtre 32 bits)." }

$WingetDisponible = [bool](Get-Command winget -ErrorAction SilentlyContinue)
if ($WingetDisponible) {
    Info "winget présent."
} else {
    Avert ("winget introuvable — l'installation automatique de Git/GitHub CLI/Python (étape 2) est IGNORÉE. " +
           "Installez-les à la main depuis leurs sites officiels (voir §2 du guide), puis relancez ce script : " +
           "les étapes déjà faites seront sautées (idempotent).")
    $script:ActionsIgnorees += "Installation via winget (winget absent)"
}

# ---------------------------------------------------------------------------
# Étape 2 — Git, GitHub CLI, Python via winget, seulement s'ils manquent.
# ---------------------------------------------------------------------------
Etape 2 'Git, GitHub CLI, Python (winget)'

function Test-WingetInstalle([string]$Id) {
    if (-not $WingetDisponible) { return $false }
    $resultat = Invoke-CommandeNativeSansArret { winget list --id $Id -e --accept-source-agreements }
    return ($resultat.Sortie -match [regex]::Escape($Id))
}

function Installer-SiAbsent([string]$Id, [string]$Nom) {
    if (Test-WingetInstalle $Id) {
        Info "$Nom ($Id) déjà installé (winget) — ignoré."
        $script:ActionsIgnorees += "$Nom déjà installé"
        return
    }
    if (-not $WingetDisponible) {
        Avert "$Nom : ni détecté par winget, ni winget disponible pour l'installer — installez-le à la main."
        return
    }
    if ($DryRun) {
        Info "[DRY-RUN] Installerait $Nom via : winget install --id $Id -e --source winget --accept-package-agreements --accept-source-agreements"
        $script:ActionsPrevues += "$Nom serait installé (winget)"
        return
    }
    Info "Installation de $Nom ($Id) via winget…"
    winget install --id $Id -e --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Avert "winget a renvoyé le code $LASTEXITCODE pour $Id — vérifiez manuellement (peut-être déjà installé autrement que via winget)."
    } else {
        Ok "$Nom installé."
        $script:ActionsFaites += "$Nom installé (winget)"
    }
}

Installer-SiAbsent 'Git.Git' 'Git'
Installer-SiAbsent 'GitHub.cli' 'GitHub CLI'
Installer-SiAbsent 'Python.Python.3.12' 'Python 3.12'

if (-not $DryRun) {
    # Les installeurs de Git/GitHub CLI inscrivent leur dossier dans le PATH
    # (Machine ou Utilisateur) au moment de l'installation, mais CETTE
    # session PowerShell ne relit pas le registre toute seule (le guide, §2,
    # demande explicitement de fermer puis rouvrir PowerShell après
    # winget install). Relire et fusionner Machine+Utilisateur évite de
    # devoir rouvrir une fenêtre — lecture seule du registre, aucun réglage
    # système modifié, PATH de CETTE session uniquement.
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [System.Environment]::GetEnvironmentVariable('Path', 'User')
}

# ---------------------------------------------------------------------------
# Étape 3 — Rendre le vrai Python utilisable dans CETTE session, sans
# modifier aucun réglage système, quand le raccourci du Microsoft Store le
# masque (piège constaté, §2 du guide).
# ---------------------------------------------------------------------------
Etape 3 'Python utilisable dans cette session'

function Resoudre-PythonReel {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and ($cmd.Source -notmatch 'WindowsApps')) {
        $resultat = Invoke-CommandeNativeSansArret { & $cmd.Source --version }
        if ($resultat.CodeSortie -eq 0 -and $resultat.Sortie -match 'Python \d') {
            return $cmd.Source
        }
    }
    # Raccourci du Store détecté (ou python introuvable) : chercher
    # l'installation réelle posée par winget/python.org sous LOCALAPPDATA.
    $racineProgs = Join-Path $env:LOCALAPPDATA 'Programs\Python'
    $dossierReel = Get-ChildItem -Path $racineProgs -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue |
        Sort-Object -Property Name -Descending | Select-Object -First 1
    if ($dossierReel) {
        $exeReel = Join-Path $dossierReel.FullName 'python.exe'
        if (Test-Path $exeReel) {
            Avert ("Le 'python' de cette session pointe vers l'alias du Microsoft Store (ou ne répond pas) — " +
                   "ajout de $($dossierReel.FullName) en tête de PATH pour CETTE fenêtre seulement (aucun " +
                   "réglage système modifié). Correction définitive (facultative) : Paramètres > Applications > " +
                   "Paramètres avancés des applications > Alias d'exécution d'application, désactiver " +
                   "'python.exe' et 'python3.exe', puis rouvrir PowerShell.")
            $env:Path = "$($dossierReel.FullName);$env:Path"
            $script:EtapesManuelles += "Désactiver les alias d'exécution 'python.exe'/'python3.exe' (Paramètres Windows), pour que 'python' fonctionne aussi dans un NOUVEAU terminal sans ce script"
            return $exeReel
        }
    }
    return $null
}

$PythonExe = Resoudre-PythonReel
if (-not $PythonExe) {
    $msg = ("Python introuvable (ni sur le PATH, ni sous $env:LOCALAPPDATA\Programs\Python) — installez-le " +
            "(winget, étape 2, ou depuis python.org), puis relancez ce script.")
    if ($DryRun) {
        # Premier passage -DryRun avant toute installation réelle (étape 2 n'a
        # encore rien installé) : Python peut légitimement ne pas encore
        # exister — ne PAS bloquer l'aperçu, continuer avec un repère textuel
        # pour les étapes suivantes (pip, Vibe, bridge.cmd) qui l'affichent.
        Avert $msg
        $PythonExe = '<python a installer — voir etape 2 ci-dessus>'
    } else {
        throw $msg
    }
}
Info "Python utilisé : $PythonExe"

# ---------------------------------------------------------------------------
# Étape 4 — Cloner (ou mettre à jour) le dépôt dans -Dossier (défaut : le
# dossier personnel, jamais un dossier protégé).
# ---------------------------------------------------------------------------
Etape 4 'Dépôt Bridge_Agent'

function Test-DossierProtege([string]$Chemin) {
    $interdits = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:ProgramW6432, $env:WINDIR, $env:SystemRoot) |
        Where-Object { $_ }
    $cheminNorm = $Chemin.TrimEnd('\').ToLowerInvariant()
    foreach ($i in $interdits) {
        $iNorm = $i.TrimEnd('\').ToLowerInvariant()
        if ($cheminNorm -eq $iNorm -or $cheminNorm.StartsWith("$iNorm\")) { return $true }
    }
    return $false
}

if (Test-DossierProtege $Dossier) {
    throw ("-Dossier '$Dossier' est un dossier protégé (Program Files / Windows) — le clonage y échoue sans " +
           "administrateur ('Permission denied', constaté §13 du guide). Choisissez un dossier du profil " +
           "utilisateur, ex. : $env:USERPROFILE\Bridge_Agent (défaut).")
}

$CheminGit = Join-Path $Dossier '.git'
if (Test-Path $CheminGit) {
    Info "Dépôt déjà présent dans $Dossier — mise à jour en avance rapide seulement (rien n'est écrasé)."
    if ($DryRun) {
        Info "[DRY-RUN] Lancerait : git -C `"$Dossier`" pull --ff-only"
    } else {
        git -C $Dossier pull --ff-only
        if ($LASTEXITCODE -ne 0) {
            Avert "git pull --ff-only ignoré ou en échec (historique divergent, ou pas de réseau) — dépôt laissé tel quel."
        } else {
            Ok "Dépôt mis à jour (ou déjà à jour)."
        }
    }
    $script:ActionsIgnorees += "Clonage (dépôt déjà présent dans $Dossier)"
} else {
    if ((Test-Path $Dossier) -and (Get-ChildItem -Path $Dossier -Force -ErrorAction SilentlyContinue)) {
        throw "'$Dossier' existe déjà, n'est pas un dépôt git, et n'est pas vide — choisissez un autre -Dossier."
    }
    if ($DryRun) {
        Info "[DRY-RUN] Lancerait : git clone $Depot `"$Dossier`""
        $script:ActionsPrevues += "Dépôt cloné dans $Dossier"
    } else {
        Info "Clonage de $Depot dans $Dossier…"
        git clone $Depot $Dossier
        if ($LASTEXITCODE -ne 0) { throw "git clone a échoué (code $LASTEXITCODE)." }
        Ok "Dépôt cloné dans $Dossier."
        $script:ActionsFaites += "Dépôt cloné dans $Dossier"
    }
}

# ---------------------------------------------------------------------------
# Étape 5 — identite_locale.conf : COPIE_NON_PROPRIETAIRE, MAJ_AUTO_DEPOT,
# MACHINE_SEULE (issues #868/#869/#870) — jamais écrasé s'il existe déjà.
# ---------------------------------------------------------------------------
Etape 5 'identite_locale.conf'

$CheminIdentite = Join-Path $Dossier 'identite_locale.conf'
if (Test-Path $CheminIdentite) {
    Info "identite_locale.conf déjà présent ($CheminIdentite) — non modifié (jamais écrasé)."
    $script:ActionsIgnorees += "identite_locale.conf déjà présent"
} elseif ($DryRun) {
    Info "[DRY-RUN] Créerait $CheminIdentite (encodage ascii, sans BOM) avec :"
    Info "[DRY-RUN]   COPIE_NON_PROPRIETAIRE = oui"
    Info "[DRY-RUN]   MAJ_AUTO_DEPOT = oui"
    Info "[DRY-RUN]   MACHINE_SEULE = oui"
    $script:ActionsPrevues += "identite_locale.conf serait créé (COPIE_NON_PROPRIETAIRE, MAJ_AUTO_DEPOT, MACHINE_SEULE)"
} else {
    $Lignes = @('COPIE_NON_PROPRIETAIRE = oui', 'MAJ_AUTO_DEPOT = oui', 'MACHINE_SEULE = oui')
    Set-Content -Path $CheminIdentite -Value $Lignes -Encoding ascii
    Ok "identite_locale.conf créé ($CheminIdentite)."
    $script:ActionsFaites += "identite_locale.conf créé (COPIE_NON_PROPRIETAIRE, MAJ_AUTO_DEPOT, MACHINE_SEULE)"

    $null = git -C $Dossier check-ignore -q 'identite_locale.conf' 2>$null
    if ($LASTEXITCODE -eq 0) {
        Info "Vérifié : git ignore bien identite_locale.conf."
    } else {
        Avert "git ne semble PAS ignorer identite_locale.conf (vérifiez .gitignore) — ne le committez jamais."
    }

    Push-Location $Dossier
    try {
        $ScriptPy = "import identite; print(identite.copie_non_proprietaire(), identite.machine_seule(), repr(identite.valeur_locale('MAJ_AUTO_DEPOT')))"
        $Resultat = (Invoke-CommandeNativeSansArret { & $PythonExe -c $ScriptPy }).Sortie
    } finally {
        Pop-Location
    }
    if ("$Resultat" -match 'True True') {
        Info "Vérifié : python lit bien identite_locale.conf ($Resultat)."
    } else {
        Avert "Vérification python de identite_locale.conf inattendue : $Resultat"
    }
}

# ---------------------------------------------------------------------------
# Étape 6 — Garde-fou anti-push : URL de push de origin réglée sur une valeur
# invalide (fetch inchangé). ACTIF PAR DÉFAUT depuis l'issue #876 — cette
# installation (réglage COPIE_NON_PROPRIETAIRE) ne doit jamais pousser vers
# le dépôt d'origine. -SansProtegerPush le désactive (déconseillé).
# ---------------------------------------------------------------------------
Etape 6 'Garde-fou anti-push'
if ($SansProtegerPush) {
    Avert ("Garde-fou anti-push DÉSACTIVÉ (-SansProtegerPush demandé) — cette copie reste capable de pousser " +
           "vers le dépôt d'origine. Déconseillé pour une installation COPIE_NON_PROPRIETAIRE.")
    $script:ActionsIgnorees += "Garde-fou anti-push désactivé (-SansProtegerPush)"
} else {
    $UrlPushInvalide = 'DESACTIVE-NE-JAMAIS-POUSSER-voir-installer_windows_seul.ps1'
    $UrlPushActuelle = (git -C $Dossier remote get-url --push origin 2>$null)
    if ($UrlPushActuelle -eq $UrlPushInvalide) {
        Info "Garde-fou déjà actif (URL de push de origin déjà invalide)."
        $script:ActionsIgnorees += "Garde-fou anti-push déjà actif"
    } elseif ($DryRun) {
        Info "[DRY-RUN] Réglerait l'URL de push de origin sur une valeur invalide ($UrlPushInvalide)."
        $script:ActionsPrevues += "Garde-fou anti-push serait activé (URL de push de origin invalidée)"
    } else {
        git -C $Dossier remote set-url --push origin $UrlPushInvalide
        Ok "URL de push de origin réglée sur une valeur invalide — cette copie ne pourra jamais pousser vers le dépôt d'origine."
        $script:ActionsFaites += "Garde-fou anti-push activé (URL de push de origin invalidée)"
    }
}

# ---------------------------------------------------------------------------
# Étape 7 — Connexion à GitHub : vérifiée, jamais automatisée (interaction
# humaine requise par gh lui-même).
# ---------------------------------------------------------------------------
Etape 7 'Connexion GitHub (gh)'

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Avert "gh (GitHub CLI) introuvable — installez-le (étape 2), puis relancez ce script."
    $script:EtapesManuelles += "Installer GitHub CLI, puis : gh auth login"
} else {
    $resultatGhAuth = Invoke-CommandeNativeSansArret { gh auth status }
    if ($resultatGhAuth.CodeSortie -eq 0) {
        Info "gh déjà authentifié pour cette session Windows."
        $script:ActionsIgnorees += "gh déjà authentifié"
    } else {
        Avert "gh n'est pas authentifié sous ce compte Windows — lancez : gh auth login (voir §4 du guide)."
        $script:EtapesManuelles += "gh auth login (voir §4 du guide — choisir GitHub.com, HTTPS, connexion par navigateur)"
    }
}

# ---------------------------------------------------------------------------
# Étape 8 — Dépendances de l'interface web (requirements.txt), sans pare-feu
# ni mode --lan (inutile pour une machine seule, §5 du guide).
# ---------------------------------------------------------------------------
Etape 8 'Dépendances de l''interface web'

$CheminRequirements = Join-Path $Dossier 'requirements.txt'
if ($DryRun) {
    Info "[DRY-RUN] Lancerait : `"$PythonExe`" -m pip install -r `"$CheminRequirements`""
    $script:ActionsPrevues += "Dépendances requirements.txt seraient installées"
} else {
    if (-not (Test-Path $CheminRequirements)) {
        throw "requirements.txt introuvable ($CheminRequirements) — dépôt incomplet ou -Dossier inattendu."
    }
    Push-Location $Dossier
    try {
        & $PythonExe -m pip install -r $CheminRequirements
        if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements.txt a échoué (code $LASTEXITCODE)." }
    } finally {
        Pop-Location
    }
    Ok "Dépendances de l'interface web installées."
    $script:ActionsFaites += "Dépendances requirements.txt installées"
}

# ---------------------------------------------------------------------------
# Étape 9 — Mistral Vibe (uv, mistral-vibe version figée, profils d'agent
# bridge_ecriture.toml + bridge_lecture.toml depuis l'issue #885) : ACTIF PAR
# DÉFAUT depuis l'issue #876 (Vibe est l'agent de toute cette installation) ;
# -SansVibe l'ignore. La connexion par compte (vibe --setup) reste manuelle
# (console réelle requise, §6 du guide).
# ---------------------------------------------------------------------------
if ($SansVibe) {
    Etape 9 'Mistral Vibe — IGNORÉ (-SansVibe)'
    Info "Mistral Vibe non installé (-SansVibe demandé) — à faire soi-même plus tard si besoin (§6 du guide)."
    $script:ActionsIgnorees += "Mistral Vibe non installé (-SansVibe)"
} else {
    Etape 9 'Mistral Vibe'

    $RepUvBin = Join-Path $env:USERPROFILE '.local\bin'
    $UvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $UvCmd -and (Test-Path (Join-Path $RepUvBin 'uv.exe'))) {
        $env:Path = "$RepUvBin;$env:Path"
        $UvCmd = Get-Command uv -ErrorAction SilentlyContinue
    }

    if ($UvCmd) {
        Info "uv déjà installé — ignoré."
        $script:ActionsIgnorees += "uv déjà installé"
    } elseif ($DryRun) {
        Info "[DRY-RUN] Installerait uv : powershell -ExecutionPolicy Bypass -Command `"irm https://astral.sh/uv/install.ps1 | iex`""
        $script:ActionsPrevues += "uv serait installé"
    } else {
        Info "Installation de uv…"
        powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
        $env:Path = "$RepUvBin;$env:Path"
        $UvCmd = Get-Command uv -ErrorAction SilentlyContinue
        if (-not $UvCmd) {
            throw "uv introuvable après installation — ouvrez une NOUVELLE fenêtre PowerShell, puis relancez ce script."
        }
        Ok "uv installé."
        $script:ActionsFaites += "uv installé"
    }

    if ($UvCmd -or $DryRun) {
        $VersionActuelle = $null
        $VibeCmd = Get-Command vibe -ErrorAction SilentlyContinue
        if ($VibeCmd) {
            $resultatVibeVersion = Invoke-CommandeNativeSansArret { vibe --version }
            if ($resultatVibeVersion.Sortie -match '(\d+\.\d+\.\d+)') { $VersionActuelle = $Matches[1] }
        }
        if ($VersionActuelle -eq $VersionVibe) {
            Info "mistral-vibe $VersionVibe déjà installé — ignoré."
            $script:ActionsIgnorees += "mistral-vibe $VersionVibe déjà installé"
        } elseif ($DryRun) {
            $depuis = if ($VersionActuelle) { $VersionActuelle } else { 'aucune' }
            Info "[DRY-RUN] Installerait mistral-vibe==$VersionVibe via uv tool install (version actuelle : $depuis)."
            $script:ActionsPrevues += "mistral-vibe==$VersionVibe serait installé"
        } else {
            Info "Installation de mistral-vibe==$VersionVibe (version figée, jamais 'latest')…"
            if ($VersionActuelle) {
                uv tool install "mistral-vibe==$VersionVibe" --force
            } else {
                uv tool install "mistral-vibe==$VersionVibe"
            }
            if ($LASTEXITCODE -ne 0) { throw "uv tool install mistral-vibe==$VersionVibe a échoué (code $LASTEXITCODE)." }
            Ok "mistral-vibe==$VersionVibe installé."
            $script:ActionsFaites += "mistral-vibe==$VersionVibe installé"
        }
    }

    # Copie TOUS les profils de provisioning\vibe\agents\ (pas seulement
    # bridge_ecriture.toml) — depuis l'issue #885, ce dossier contient aussi
    # bridge_lecture.toml (profil de lecture seule, nécessaire dès Vibe 3.1.0
    # qui a retiré l'agent intégré `plan` ; voir provisioning\vibe\README.md
    # §1 bis). Itère sur le dossier plutôt que de nommer chaque fichier : un
    # futur profil ajouté au dépôt est copié sans modifier ce script.
    $RepAgentsVibe = Join-Path $env:USERPROFILE '.vibe\agents'
    $SourceRepAgentsVibe = Join-Path $Dossier 'provisioning\vibe\agents'
    if ($DryRun) {
        Info "[DRY-RUN] Copierait tous les profils de $SourceRepAgentsVibe vers $RepAgentsVibe."
        $script:ActionsPrevues += "Profils d'agent Vibe (provisioning\vibe\agents\*.toml) seraient copiés"
    } else {
        if (-not (Test-Path $SourceRepAgentsVibe)) {
            Avert "Dossier $SourceRepAgentsVibe introuvable — dépôt incomplet ou -Dossier inattendu, aucun profil copié."
        } else {
            $ProfilsVibe = Get-ChildItem -Path $SourceRepAgentsVibe -Filter '*.toml' -File -ErrorAction SilentlyContinue
            if (-not $ProfilsVibe) {
                Avert "Aucun profil .toml trouvé dans $SourceRepAgentsVibe — dépôt incomplet ou -Dossier inattendu, aucun profil copié."
            } else {
                New-Item -ItemType Directory -Force -Path $RepAgentsVibe | Out-Null
                foreach ($Profil in $ProfilsVibe) {
                    Copy-Item -Path $Profil.FullName -Destination (Join-Path $RepAgentsVibe $Profil.Name) -Force
                    Ok "Profil $($Profil.Name) copié vers $RepAgentsVibe."
                    $script:ActionsFaites += "Profil $($Profil.Name) copié"
                }
            }
        }
    }

    $script:EtapesManuelles += "vibe --setup, dans une VRAIE console (pas ISE) — connexion par COMPTE, pas par clé API (voir §6 du guide)"
}

# ---------------------------------------------------------------------------
# Étape manuelle — Créer le premier projet : toujours APRÈS la connexion
# GitHub et celle de Vibe (dont elle dépend pour AGENT = vibe), toujours
# AVANT le démarrage automatique (qui dépend à son tour d'au moins un projet
# créé) — ordre corrigé par l'issue #876, voir §12 du guide.
# ---------------------------------------------------------------------------
if ($SansVibe) {
    $script:EtapesManuelles += "Créer le premier projet dans l'interface (bouton 'Nouveau projet', §8 du guide) — pas d'AGENT = vibe dans configs\<projet>.conf (installation sans Vibe, -SansVibe)"
} else {
    $script:EtapesManuelles += "Créer le premier projet dans l'interface (bouton 'Nouveau projet', §8 du guide), puis ajouter AGENT = vibe dans configs\<projet>.conf"
}

# ---------------------------------------------------------------------------
# Étape 10 — Raccourci 'bridge' : bridge.cmd + bridge_lanceur.ps1 dans
# $env:USERPROFILE\.local\bin (voir l'encadré de conception en tête de
# fichier). Idempotent : régénéré avec les mêmes noms, jamais de doublon.
# ---------------------------------------------------------------------------
Etape 10 'Raccourci ''bridge'''

function Test-DossierDansPathUtilisateur([string]$Chemin) {
    $pathUtilisateur = [Environment]::GetEnvironmentVariable('Path', 'User')
    if (-not $pathUtilisateur) { return $false }
    $elements = $pathUtilisateur -split ';' | ForEach-Object { $_.TrimEnd('\') }
    return ($elements -contains $Chemin.TrimEnd('\'))
}

if (-not (Test-Path $RepBinUtilisateur)) {
    if ($DryRun) { Info "[DRY-RUN] Créerait $RepBinUtilisateur." }
    else { New-Item -ItemType Directory -Force -Path $RepBinUtilisateur | Out-Null }
}

if (Test-DossierDansPathUtilisateur $RepBinUtilisateur) {
    Info "$RepBinUtilisateur déjà présent dans le PATH utilisateur."
    $script:ActionsIgnorees += "$RepBinUtilisateur déjà dans le PATH utilisateur"
} else {
    Info ("Ajout de $RepBinUtilisateur à la variable PATH de L'UTILISATEUR (pas la machine) — nécessaire pour " +
          "que la commande 'bridge' soit trouvée dans un NOUVEAU terminal.")
    if ($DryRun) {
        Info "[DRY-RUN] Ajouterait $RepBinUtilisateur au PATH utilisateur."
        $script:ActionsPrevues += "$RepBinUtilisateur serait ajouté au PATH utilisateur"
    } else {
        $pathActuel = [Environment]::GetEnvironmentVariable('Path', 'User')
        $nouveauPath = if ($pathActuel) { "$pathActuel;$RepBinUtilisateur" } else { $RepBinUtilisateur }
        [Environment]::SetEnvironmentVariable('Path', $nouveauPath, 'User')
        Ok "$RepBinUtilisateur ajouté au PATH utilisateur (visible dans un NOUVEAU terminal)."
        $script:ActionsFaites += "$RepBinUtilisateur ajouté au PATH utilisateur"
    }
}
if (($env:Path -split ';' | ForEach-Object { $_.TrimEnd('\') }) -notcontains $RepBinUtilisateur.TrimEnd('\')) {
    $env:Path = "$RepBinUtilisateur;$env:Path"
}

$ContenuLanceur = @"
# bridge_lanceur.ps1 — généré par installer_windows_seul.ps1 (ne pas modifier
# à la main ; relancer l'installeur pour régénérer avec de nouveaux chemins).
#
# CHOIX DE CONCEPTION — console de new_issue.py laissée VISIBLE (issue
# #876) : Start-Process ci-dessous n'utilise PAS -WindowStyle Hidden.
# 'bridge' est lancé depuis un terminal déjà ouvert par l'utilisateur (pas
# un double-clic ni une tâche planifiée, voir §9 du guide pour ce cas-là,
# qui masque sa fenêtre séparément) : la console de new_issue.py reste la
# seule source directe des messages de mise à jour automatique (MAJ_AUTO_
# DEPOT, §3 du guide, qui peut dépasser la minute d'attente ci-dessous) et
# de toute erreur de démarrage — la masquer rendrait justement invisible le
# défaut que ce correctif vise à signaler clairement.
`$ErrorActionPreference = 'Stop'
`$DossierDepot = '$Dossier'
`$CheminPython = '$PythonExe'
`$Port = 5100
`$DelaiMaxDemarrageSec = 60

function Test-PortOuvert(`$NomHote, `$Port, `$DelaiMs = 300) {
    `$client = New-Object System.Net.Sockets.TcpClient
    try {
        `$tache = `$client.BeginConnect(`$NomHote, `$Port, `$null, `$null)
        `$pret = `$tache.AsyncWaitHandle.WaitOne(`$DelaiMs)
        return (`$pret -and `$client.Connected)
    } catch {
        return `$false
    } finally {
        `$client.Close()
    }
}

if (-not (Test-PortOuvert '127.0.0.1' `$Port)) {
    # --no-browser : c'est CE script qui ouvre le navigateur, une seule fois,
    # seulement une fois le port confirmé ouvert (sinon new_issue.py ouvrirait
    # lui-même un premier onglet trop tôt, pendant sa mise à jour automatique
    # au démarrage — « Unable to connect » constaté, issue #876).
    Start-Process -FilePath `$CheminPython -ArgumentList 'new_issue.py', '--no-browser' -WorkingDirectory `$DossierDepot
    `$Attendu = 0
    while (-not (Test-PortOuvert '127.0.0.1' `$Port) -and `$Attendu -lt `$DelaiMaxDemarrageSec) {
        Start-Sleep -Seconds 1
        `$Attendu++
    }
    if (-not (Test-PortOuvert '127.0.0.1' `$Port)) {
        Write-Host "[bridge] L'interface web ne répond toujours pas sur 127.0.0.1:`$Port après `$DelaiMaxDemarrageSec s. Vérifiez la console de new_issue.py ouverte à côté (erreur ? mise à jour automatique anormalement longue ?), ou lancez-la à la main : `"`$CheminPython`" new_issue.py" -ForegroundColor Red
        exit 1
    }
}

Start-Process "http://127.0.0.1:`$Port"
"@

$ContenuCmd = @"
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bridge_lanceur.ps1"
"@

if ($DryRun) {
    Info "[DRY-RUN] Écrirait $CheminBridgeLanceur et $CheminBridgeCmd (dossier dépôt : $Dossier ; python : $PythonExe)."
    $script:ActionsPrevues += "Raccourci 'bridge' serait installé"
} else {
    Set-Content -Path $CheminBridgeLanceur -Value $ContenuLanceur -Encoding UTF8
    Set-Content -Path $CheminBridgeCmd -Value $ContenuCmd -Encoding ascii
    Ok "Raccourci 'bridge' installé ($CheminBridgeCmd) — utilisable dans un NOUVEAU terminal (PowerShell ou invite de commandes)."
    $script:ActionsFaites += "Raccourci 'bridge' installé"
}

# ---------------------------------------------------------------------------
# Étape 11 — -ProposerDemarrage : affiche (sans jamais exécuter) la commande
# de installer_demarrage_session.ps1 — §9 du guide, volontairement manuel
# (choix des projets à surveiller).
# ---------------------------------------------------------------------------
if ($ProposerDemarrage) {
    Etape 11 'Démarrage automatique (affichage seulement)'
    $CheminInstallerDemarrage = Join-Path $Dossier 'provisioning\windows\installer_demarrage_session.ps1'
    Info "Commande suggérée pour le démarrage automatique à l'ouverture de session (§9 du guide) :"
    Info "  powershell -NoProfile -ExecutionPolicy Bypass -File `"$CheminInstallerDemarrage`" -Projets <projet1>,<projet2> -DryRun"
    Info "Remplacez <projet1>,<projet2> par les projets déjà créés dans l'interface (vide = aucun projet, seulement issues_inbox + interface web)."
    Info "Retirez -DryRun une fois le résultat de la simulation vérifié. Jamais exécutée automatiquement par CE script."
}
$script:EtapesManuelles += "Démarrage automatique (installer_demarrage_session.ps1 -Projets <...>, §9 du guide) — après avoir créé au moins un projet"

# ---------------------------------------------------------------------------
# Étape 12 — Résumé final. En mode -DryRun, ce résumé ne doit JAMAIS laisser
# croire qu'une action a été réellement faite (issue #876) : rubrique
# « Fait » remplacée par « Serait fait (simulation) », listant ce qui a été
# accumulé dans $script:ActionsPrevues au fil des étapes ci-dessus.
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host '========================================================================' -ForegroundColor Cyan
Write-Host '  RÉSUMÉ' -ForegroundColor Cyan
Write-Host '========================================================================' -ForegroundColor Cyan

if ($DryRun) {
    Avert "Mode -DryRun : AUCUNE action n'a été faite réellement. Ce qui suit n'est qu'un aperçu."
    Write-Host ''
    Write-Host 'Serait fait (simulation) :' -ForegroundColor Green
    if ($script:ActionsPrevues.Count -eq 0) { Info '(rien à faire — tout semble déjà en place)' }
    foreach ($a in $script:ActionsPrevues) { Info "- $a" }
} else {
    Write-Host ''
    Write-Host 'Fait :' -ForegroundColor Green
    if ($script:ActionsFaites.Count -eq 0) { Info '(rien de nouveau — tout était déjà en place)' }
    foreach ($a in $script:ActionsFaites) { Ok "- $a" }
}

Write-Host ''
Write-Host 'Ignoré (déjà en place) :' -ForegroundColor Cyan
if ($script:ActionsIgnorees.Count -eq 0) { Info '(aucune étape sautée)' }
foreach ($a in $script:ActionsIgnorees) { Info "- $a" }

Write-Host ''
Write-Host 'Étapes manuelles restantes, DANS L''ORDRE :' -ForegroundColor Yellow
$n = 1
foreach ($a in $script:EtapesManuelles) {
    Avert "$n. $a"
    $n++
}

Write-Host ''
Info "Interface web : lancez 'bridge' dans un NOUVEAU terminal (après ce script), ou directement : `"$PythonExe`" `"$Dossier\new_issue.py`""
