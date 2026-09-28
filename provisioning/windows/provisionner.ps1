<#
  provisionner.ps1 — Provisioning LOGICIEL du PC fixe Windows CCW (issue #450,
  suite #447 — le PC fixe physique a remplacé la VM VirtualBox CCW-Build).

  Ce script s'exécute SUR le PC fixe, manuellement dans une console
  PowerShell ADMINISTRATEUR (ou via la session SSH ouverte par
  configurer_ssh_ccw.ps1 — voir ce dernier pour l'étape 1 : accès SSH depuis
  CCL), après une réinstallation Windows (Windows 11 IoT Enterprise LTSC,
  éval 90 jours). Il installe l'outillage nécessaire à l'agent Claude Code
  Windows (CCW) puis met en place le service Windows (NSSM) qui lancera le
  watcher au démarrage.

  Historiquement (phase 2, issue #147), il était poussé et exécuté à
  distance depuis CCL par lancer_provisioning.py (VBoxManage guestcontrol)
  dans la VM CCW-Build — ce mode reste documenté à titre historique mais
  n'a plus lieu d'être sur le PC physique : lancement manuel uniquement.

  Ce qu'il fait :
    1. installe Git, GitHub CLI (gh), Python 3.12 et NSSM par TÉLÉCHARGEMENT
       DIRECT des installeurs officiels de chaque éditeur (PLUS de dépendance
       à winget pour ces quatre logiciels — voir « Pourquoi plus de winget »
       ci-dessous, issue #658) ;
    1bis. OpenSSL : installeur autonome officiel (Shining Light Productions)
       par défaut ; winget n'est tenté que si -TenterWinget est fourni ET
       réussit (repli automatique sur l'installeur autonome sinon) ;
    2. installe pyinstaller (pip) — requis pour les builds .exe délégués ;
    3. installe Claude Code via l'installeur natif officiel (pas de Node.js) :
         irm https://claude.ai/install.ps1 | iex
       puis ajoute explicitement C:\Users\<CompteService>\.local\bin au PATH
       **utilisateur** (l'installeur le signale en sortie sans agir dessus) ;
    4. clone AlainDelree/Bridge_Agent (lecture seule) dans C:\CCW\Bridge_Agent ;
    5. génère (une seule fois) la paire de clés RSA de chiffrement des tokens
       de bootstrap « Projet CCW » (issue #554, 1/3) — clé privée jamais
       exposée hors de la machine, voir section dédiée plus bas ;
    6. écrit configs\ccw.conf (LABEL=for-windows, NOM=ccw, …) ;
    7. désactive Windows Update (Stop-Service + Disabled + clé de registre
       NoAutoUpdate) — décision d'Alain suite au plantage ucrtbase.dll du
       27/09/2026 causé par une mise à jour cumulative (issue #658, point 5) ;
    8. enregistre un vrai service Windows (via NSSM) qui lance le watcher au
       démarrage de la machine (sans session ouverte), avec redémarrage
       automatique en cas d'échec, et un PATH complet (machine + utilisateur
       + WindowsApps) posé dans AppEnvironmentExtra (issue #658, point 1) ;
    9. affiche un résumé récapitulatif complet (logiciels + versions, service,
       PATH, étapes manuelles restantes).

  ┌─────────────────────────────────────────────────────────────────────────┐
  │ POURQUOI PLUS DE WINGET (issue #658, réinstallation réelle du            │
  │ 27/09/2026 menée avec Alain) :                                          │
  │                                                                          │
  │ Sur Windows 11 IoT Enterprise LTSC (édition du PC fixe CCW), Bootstrap-  │
  │ Winget (conservé plus bas, désormais RÉSERVÉ au repli optionnel OpenSSL) │
  │ échoue systématiquement dès sa toute première étape réelle : le paquet  │
  │ « App Installer » dépend du framework « Microsoft.VCLibs.140.00 » (SANS │
  │ le suffixe .UWPDesktop) — pour lequel :                                  │
  │   (a) aucune source de téléchargement autonome fiable n'a été trouvée,  │
  │       distincte de Microsoft.VCLibs.140.00.UWPDesktop (bien plus        │
  │       commun, et souvent confondu avec le précédent) ;                  │
  │   (b) même le contournement connu (passer ce framework en               │
  │       -DependencyPackagePath au moment MÊME de l'installation de App    │
  │       Installer) n'était pas implémenté ici, et laisse de toute façon   │
  │       App Installer provisionné au niveau MACHINE sans être enregistré  │
  │       pour l'utilisateur courant (Add-AppxPackage -Register en plus,    │
  │       nécessaire sur le profil AlainW).                                 │
  │ Décision : ne plus dépendre de winget DU TOUT pour Git/gh/Python/NSSM.  │
  │ S'il est déjà présent sur une future édition Windows, tant mieux, mais  │
  │ plus aucune étape OBLIGATOIRE n'en dépend.                              │
  └─────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────┐
  │ AUTHENTIFICATION CLAUDE — NE PAS committer de clé API.                    │
  │ L'agent `claude` a besoin d'être authentifié pour fonctionner :          │
  │   • usage HEADLESS : définir la variable d'environnement                 │
  │       ANTHROPIC_API_KEY  (voir le placeholder plus bas — NE PAS la       │
  │       coder en dur ici ni la committer, exactement comme le mot de       │
  │       passe en phase 1) ;                                                 │
  │   • usage INTERACTIF : lancer une seule fois `claude auth login`.        │
  │ Ce script ne fixe AUCUNE clé : il rappelle seulement la marche à suivre. │
  └─────────────────────────────────────────────────────────────────────────┘

  Idempotent : relançable sans dommage (chaque installeur saute ce qui est
  déjà installé, le clone est mis à jour par pull, le service est
  arrêté/supprimé puis recréé).

  Mode -DryRun / -WhatIf (issue #658) : affiche toutes les actions prévues
  (téléchargements, installations, écritures, service) SANS les exécuter —
  utile pour une relecture rapide avant la prochaine vraie réinstallation
  (~tous les 3 mois). Exemple : .\provisionner.ps1 -DryRun

  Prérequis : Windows 11, exécution en administrateur, accès Internet
  sortant (téléchargements directs des installeurs officiels). winget n'est
  PAS un prérequis : il n'est utilisé, en repli optionnel, QUE pour OpenSSL,
  et seulement si -TenterWinget est explicitement fourni.
#>

[CmdletBinding()]
param(
    # Dossier de travail dédié sur le PC fixe.
    [string]$RepCCW = 'C:\CCW',
    # Dépôt cloné (lecture seule).
    [string]$Depot = 'AlainDelree/Bridge_Agent',
    # Compte Windows non-admin sous lequel tourne le service CCW-Watcher
    # (NSSM ObjectName) — PC fixe physique, plus de justification LocalSystem
    # (issue #446, suite #447 : REP_TRAVAIL est désormais un chemin local,
    # accessible normalement à n'importe quel compte). C'est aussi, en
    # pratique, le compte interactif habituel du PC fixe (voir avertissement
    # plus bas si $env:USERNAME diffère).
    [string]$CompteService = 'AlainW',
    # Affiche les actions prévues SANS rien exécuter (issue #658). Alias
    # -WhatIf pour rester intuitif, sans dépendre de SupportsShouldProcess
    # (trop de types d'actions différents ici — téléchargements, installeurs
    # natifs, registre, service — pour le modèle ShouldProcess standard).
    [Alias('WhatIf')]
    [switch]$DryRun,
    # Tente d'abord d'installer OpenSSL via winget (bootstrap App Installer
    # inclus) avant de replier sur l'installeur autonome. Désactivé par
    # défaut depuis l'issue #658 : plus aucune étape obligatoire ne dépend de
    # winget. À fournir seulement pour retester le bootstrap winget sur une
    # future édition Windows (ex. après mise à jour du framework VCLibs).
    [switch]$TenterWinget
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Info($msg)  { Write-Host "[provisionner] $msg" -ForegroundColor Cyan }
function Avert($msg) { Write-Host "[provisionner] AVERTISSEMENT : $msg" -ForegroundColor Yellow }

$RepDepot = Join-Path $RepCCW 'Bridge_Agent'
$CacheDir = 'C:\CCW_Share\cache'

if ($DryRun) {
    Info '=== MODE -DryRun / -WhatIf : aucune action ne sera réellement exécutée. ==='
}

# Hypothèse implicite du reste du script (issue #658, point « ajout du PATH
# utilisateur ») : le compte qui EXÉCUTE ce script est le même que
# $CompteService — vrai en pratique sur ce PC fixe mono-utilisateur (AlainW
# est à la fois le compte interactif et le compte de service). Avertissement
# si ce n'est pas le cas, pour ne pas poser silencieusement le PATH sur le
# mauvais profil.
if ($env:USERNAME -ne $CompteService) {
    Avert ("Ce script tourne sous le compte '$env:USERNAME', différent de " +
           "-CompteService ('$CompteService'). Le PATH UTILISATEUR posé plus " +
           "bas (.local\bin de Claude Code) concernera '$env:USERNAME', pas " +
           "'$CompteService' — à corriger manuellement si ces comptes " +
           "diffèrent réellement sur ce PC.")
}

# ---------------------------------------------------------------------------
# Fonctions communes (téléchargement, PATH, mot de passe masqué).
# ---------------------------------------------------------------------------

# aka.ms / GitHub / slproweb servent en HTTPS/TLS 1.2 ; PowerShell 5.1 ne le
# négocie pas toujours par défaut. On le force pour éviter un échec TLS opaque.
function Forcer-TLS12 {
    try {
        [Net.ServicePointManager]::SecurityProtocol = `
            [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    } catch {
        Avert "Impossible de forcer TLS 1.2 ($($_.Exception.Message)) — on tente quand même."
    }
}

function Rafraichir-Path {
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [System.Environment]::GetEnvironmentVariable('Path', 'User')
}

# Convertit un SecureString en texte brut le temps strictement nécessaire,
# puis libère immédiatement le buffer non managé (BSTR) — même fonction que
# mettre_a_jour_tokens_ccw.ps1 (dupliquée à l'identique : chaque script CCW
# distant/manuel reste volontairement autonome, cf. ccw-commun.psm1 en tête).
function ConvertFrom-SecureStringPlain([System.Security.SecureString]$secure) {
    $ptr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

# Résout l'URL de téléchargement du dernier asset d'un dépôt GitHub dont le
# nom correspond à $Motif (wildcard -like). Repris et généralisé du pattern
# déjà utilisé (avant #658) pour trouver la licence App Installer dans
# winget-cli/releases/latest — même principe, réutilisé ici pour Git for
# Windows et GitHub CLI, qui publient tous deux via GitHub Releases avec des
# noms de fichiers versionnés (pas d'URL "latest/download/<nom fixe>" stable).
function Resoudre-AssetGitHubLatest($depot, $motif) {
    Forcer-TLS12
    Info "Résolution de la dernière release de $depot (asset '$motif')…"
    $apiUrl = "https://api.github.com/repos/$depot/releases/latest"
    try {
        $release = Invoke-RestMethod -Uri $apiUrl -Headers @{ 'User-Agent' = 'CCW-provisionner' } `
                                     -UseBasicParsing
    } catch {
        throw "Résolution de la dernière release de $depot échouée : $($_.Exception.Message). Accès Internet sortant requis."
    }
    $asset = $release.assets | Where-Object { $_.name -like $motif } | Select-Object -First 1
    if (-not $asset) {
        throw "Aucun asset correspondant à '$motif' trouvé dans la dernière release de $depot ($($release.tag_name))."
    }
    return [PSCustomObject]@{ Url = $asset.browser_download_url; Nom = $asset.name; Version = $release.tag_name }
}

# Téléchargement avec cache persistant (C:\CCW_Share survit aux
# redémarrages) — même pattern que le msixbundle winget historique : pas
# d'invalidation automatique, VIDER MANUELLEMENT le sous-dossier pour forcer
# un nouveau téléchargement.
function Telecharger-AvecCache($url, $sousDossierCache, $nomFichier) {
    $dossier = Join-Path $CacheDir $sousDossierCache
    $chemin  = Join-Path $dossier $nomFichier
    if (Test-Path $chemin) {
        Info "Utilisation du cache existant pour $nomFichier (pas de téléchargement)."
        return $chemin
    }
    Forcer-TLS12
    New-Item -ItemType Directory -Path $dossier -Force | Out-Null
    Info "Téléchargement de $nomFichier…"
    try {
        Invoke-WebRequest -Uri $url -OutFile $chemin -UseBasicParsing
    } catch {
        Remove-Item -Path $chemin -Force -ErrorAction SilentlyContinue
        throw "Téléchargement de $nomFichier échoué : $($_.Exception.Message). Accès Internet sortant requis."
    }
    return $chemin
}

# Version affichée dans le résumé final (--version, présumé sans risque). Ne
# JAMAIS utiliser ceci pour nssm (nssm.exe sans argument reconnu ouvre une
# boîte de dialogue graphique — invisible et bloquante en session SSH,
# exactement le problème du point 2 de l'issue #658).
function Decrire-Version($nomCmd, $argVersion) {
    $cmd = Get-Command $nomCmd -ErrorAction SilentlyContinue
    if (-not $cmd) { return '(introuvable)' }
    try {
        $sortie = & $nomCmd $argVersion 2>$null | Select-Object -First 1
        if ($sortie) { return "$sortie  [$($cmd.Source)]" }
    } catch { }
    return $cmd.Source
}

function Decrire-Presence($nomCmd) {
    $cmd = Get-Command $nomCmd -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source } else { return '(introuvable)' }
}

# ---------------------------------------------------------------------------
# 1. Installer-Winget — CONSERVÉE mais désormais réservée au repli optionnel
#    OpenSSL (-TenterWinget). Plus aucune étape obligatoire n'en dépend
#    (issue #658 — voir « Pourquoi plus de winget » en tête de fichier).
# ---------------------------------------------------------------------------
function Installer-Winget($id, $nom) {
    Info "Installation de $nom ($id) via winget…"
    winget install --id $id --exact --silent `
        --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 0x8A15002B) {
        # 0x8A15002B = « déjà installé / aucune mise à jour disponible ».
        Avert "winget a renvoyé le code $LASTEXITCODE pour $id (peut-être déjà installé)."
    }
}

# ---------------------------------------------------------------------------
# 1bis. Bootstrap de winget (App Installer) — RÉSERVÉ au repli optionnel
#   OpenSSL (-TenterWinget), depuis l'issue #658. Conservé tel quel pour le
#   cas où une future édition Windows (ou un correctif Microsoft du paquet
#   VCLibs) rendrait ce bootstrap à nouveau viable — voir le constat d'échec
#   systématique sur LTSC/IoT en tête de fichier.
#
#   Les éditions LTSC / IoT Enterprise EXCLUENT délibérément le Microsoft
#   Store. Or winget (fourni par le paquet « App Installer » =
#   Microsoft.DesktopAppInstaller) dépend normalement du Store pour son
#   installation et ses mises à jour automatiques. Sur ces éditions, winget
#   est donc ABSENT au départ : il faut le déployer manuellement (msixbundle
#   + licence) AVANT de l'utiliser. C'est ce que fait cette fonction
#   (idempotente : si winget est déjà là, elle ne fait rien).
#
#   DÉPENDANCE SUPPLÉMENTAIRE (issue #159, suite #158) : le msixbundle App
#   Installer exige le framework « Microsoft.WindowsAppRuntime.1.8 » (version
#   minimale 8000.616.304.0). Sur un Windows 11 « standard » ce framework est
#   fourni automatiquement par le Store ; sur LTSC/IoT (sans Store) il est ABSENT,
#   et Add-AppxProvisionedPackage échoue alors avec HRESULT 0x80073CF3
#   (dépendance manquante). On installe donc d'abord le Windows App Runtime via
#   l'installeur autonome officiel (Install-WindowsAppRuntime, appelée plus bas)
#   AVANT de provisionner App Installer, pour que la dépendance soit satisfaite.
#
#   ÉCHEC RÉSIDUEL CONNU (issue #658) : même ce bootstrap réussi ne suffit
#   PAS toujours — App Installer dépend ÉGALEMENT de
#   « Microsoft.VCLibs.140.00 » (sans le suffixe .UWPDesktop), pour lequel
#   aucune source de téléchargement autonome fiable n'a été trouvée à ce jour.
#   D'où la bascule par défaut sur des installeurs autonomes pour tout sauf,
#   optionnellement, OpenSSL.
#
#   Doc Microsoft Learn officielle sur winget :
#     https://learn.microsoft.com/windows/package-manager/winget/
#   Installation de winget sur les éditions sans Store (sideload App Installer) :
#     https://learn.microsoft.com/windows/package-manager/winget/#install-winget-on-windows-sandbox
#     https://learn.microsoft.com/windows/package-manager/winget/#install-winget-on-windows-server-and-non-store-editions
# ---------------------------------------------------------------------------
# 1ter. Windows App Runtime (Windows App SDK Runtime) — DÉPENDANCE d'App Installer
#       manquante sur LTSC/IoT (issue #159, suite #158).
#
#   Pourquoi : le msixbundle App Installer (Microsoft.DesktopAppInstaller) déployé
#   par Bootstrap-Winget dépend du framework « Microsoft.WindowsAppRuntime.1.8 »
#   (version minimale 8000.616.304.0). Sur une édition LTSC/IoT sans Store, ce
#   framework n'est PAS installé automatiquement : Add-AppxProvisionedPackage
#   échoue alors avec HRESULT 0x80073CF3, et le repli Add-AppxPackage
#   -RegisterByFamilyName échoue pareillement. Microsoft fournit un installeur
#   autonome officiel (.exe) qui déploie EN UNE FOIS tous les paquets du Windows
#   App SDK Runtime (framework, main, singleton, DDLM), silencieusement, tant
#   qu'il est lancé en élevé — acquis sur CCW-Build depuis la désactivation d'UAC.
#
#   URL VÉRIFIÉE le 2026-07-19 sur la page officielle « Latest Windows App SDK
#   downloads » + son archive (un lien figé de ce type a déjà été signalé cassé,
#   donc confirmation à chaque évolution) — variante runtime x64, dernière 1.8
#   stable disponible : 1.8.10 (build 1.8.260710003, publiée le 14/07/2026) :
#     https://learn.microsoft.com/windows/apps/windows-app-sdk/downloads
#     https://learn.microsoft.com/windows/apps/windows-app-sdk/downloads-archive
#   Flag silencieux officiel (double tiret) : --quiet — documenté ici :
#     https://learn.microsoft.com/windows/apps/windows-app-sdk/deploy-unpackaged-apps
#
#   Cache : MÊME pattern que le msixbundle (issue #158) — sous-dossier dédié du
#   partage CCW_Share (C:\CCW_Share\cache\windows-app-runtime\), réutilisé
#   si présent, peuplé sinon. Idempotent : si les paquets sont déjà là,
#   l'installeur ne fait rien. Pour forcer une nouvelle version : VIDER le cache.
# ---------------------------------------------------------------------------
function Install-WindowsAppRuntime {
    $cacheDir   = 'C:\CCW_Share\cache\windows-app-runtime'
    $exeName    = 'WindowsAppRuntimeInstall-x64.exe'
    $cacheExe   = Join-Path $cacheDir $exeName
    # Runtime x64, dernière 1.8 stable vérifiée le 2026-07-19 (voir commentaire ci-dessus).
    $runtimeUrl = 'https://aka.ms/windowsappsdk/1.8/1.8.260710003/windowsappruntimeinstall-x64.exe'

    $exePath = $null
    # $tmp reste $null si le cache est utilisé : rien à nettoyer en fin de fonction.
    $tmp     = $null

    if (Test-Path $cacheExe) {
        # (1) Cache présent : on l'utilise directement, aucun accès réseau.
        $exePath = $cacheExe
        Info 'Windows App Runtime : utilisation du cache existant (pas de téléchargement).'
    } else {
        # (2) Cache absent (premier run, ou dossier vidé manuellement) : on télécharge,
        #     PUIS on peuple le cache pour le prochain test.
        Forcer-TLS12

        # Dossier temporaire dédié (nettoyé en fin de fonction).
        $tmp     = Join-Path $env:TEMP ('winappruntime-' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmp -Force | Out-Null
        $exePath = Join-Path $tmp $exeName

        try {
            Info 'Téléchargement du Windows App Runtime (installeur autonome x64, 1.8)…'
            Invoke-WebRequest -Uri $runtimeUrl -OutFile $exePath -UseBasicParsing
        } catch {
            # Erreur réseau (VM en NAT : accès sortant requis) — message clair.
            throw ("Téléchargement du Windows App Runtime échoué : $($_.Exception.Message). " +
                   "La VM doit avoir un accès Internet sortant (NAT). " +
                   "Voir https://learn.microsoft.com/windows/apps/windows-app-sdk/downloads pour un dépannage manuel.")
        }

        # Peupler le cache persistant (best-effort : un échec de copie ne doit PAS
        # faire échouer le provisioning — on retéléchargera au run suivant).
        try {
            New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null
            Copy-Item -Path $exePath -Destination $cacheExe -Force
            Info "Windows App Runtime mis en cache dans $cacheDir."
        } catch {
            Avert "Impossible de peupler le cache Windows App Runtime ($($_.Exception.Message)) — le prochain run retéléchargera."
        }
    }

    # (3) Installation SILENCIEUSE (--quiet). Requiert l'élévation (acquise sur
    #     CCW-Build, UAC désactivé) : sans elle, l'installeur renvoie 0x80070005.
    #     Un .exe natif ne lève pas d'exception sur code non nul — on teste
    #     explicitement $LASTEXITCODE (0x0 = succès).
    try {
        Info 'Installation du Windows App Runtime (--quiet)…'
        & $exePath --quiet
        $code = $LASTEXITCODE
        if ($code -ne 0) {
            $hex = ('0x{0:X8}' -f $code)
            Avert ("L'installeur Windows App Runtime a renvoyé le code $hex " +
                   "(App Installer risquera d'échouer si la dépendance n'est pas satisfaite ; " +
                   "0x80070005 = processus non élevé — voir deploy-unpackaged-apps).")
        } else {
            Info 'Windows App Runtime installé (dépendance App Installer satisfaite).'
        }
    } catch {
        Avert "Exécution de l'installeur Windows App Runtime échouée ($($_.Exception.Message))."
    } finally {
        if ($tmp) { Remove-Item -Path $tmp -Recurse -Force -ErrorAction SilentlyContinue }
    }
}

# ---------------------------------------------------------------------------
function Bootstrap-Winget {
    # (1) Déjà disponible ? Ne rien faire (Windows 11 standard, ou relance).
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Info 'winget déjà présent — bootstrap non nécessaire.'
        return
    }

    Info 'winget absent (édition LTSC/IoT sans Store) — bootstrap manuel de App Installer…'

    # -----------------------------------------------------------------------
    # CACHE PERSISTANT du msixbundle + licence (issue #158, suite #152).
    #
    #   Le partage CCW_Share (C:\CCW_Share, local au PC fixe) SURVIT aux
    #   redémarrages : c'est un emplacement de cache idéal. Le téléchargement
    #   du msixbundle est la partie la plus longue du bootstrap ; le mettre en
    #   cache évite de le retélécharger à chaque test rapproché.
    #
    #   PAS d'invalidation automatique (aucune vérification de version) : pour
    #   forcer un nouveau téléchargement (nouvelle version d'App Installer), il
    #   suffit de VIDER MANUELLEMENT le dossier de cache ci-dessous.
    # -----------------------------------------------------------------------
    $cacheDir   = 'C:\CCW_Share\cache\winget-bootstrap'
    $msixName   = 'Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle'
    $cacheMsix  = Join-Path $cacheDir $msixName

    $msixPath    = $null
    $licensePath = $null
    # $tmp reste $null en cas de cache utilisé : pas de dossier temporaire créé,
    # donc pas de nettoyage à faire en fin de fonction (voir plus bas).
    $tmp         = $null

    # Cache valide = le msixbundle attendu ET un fichier de licence (.xml) présents.
    $cacheLicense = $null
    if (Test-Path $cacheMsix) {
        $cacheLicense = Get-ChildItem -Path $cacheDir -Filter '*.xml' -ErrorAction SilentlyContinue |
            Select-Object -First 1
    }

    if ((Test-Path $cacheMsix) -and $cacheLicense) {
        # (2) Cache présent : on l'utilise directement, aucun accès réseau.
        $msixPath    = $cacheMsix
        $licensePath = $cacheLicense.FullName
        Info 'Utilisation du cache existant (pas de téléchargement).'
    } else {
        # (3) Cache absent (premier run, ou dossier vidé manuellement) : on
        #     télécharge comme avant, PUIS on peuple le cache pour le prochain test.
        Forcer-TLS12

        # Dossier temporaire dédié (nettoyé en fin de fonction).
        $tmp = Join-Path $env:TEMP ('winget-bootstrap-' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmp -Force | Out-Null

        $msixUrl    = 'https://github.com/microsoft/winget-cli/releases/latest/download/Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle'
        $msixPath   = Join-Path $tmp $msixName
        $licenseUrl = $null

        try {
            # (3a) Résoudre le nom EXACT du fichier de licence via l'API GitHub
            #      (même helper que Git/gh, voir Resoudre-AssetGitHubLatest).
            $licenseAsset = Resoudre-AssetGitHubLatest 'microsoft/winget-cli' '*License*.xml'
            $licenseUrl  = $licenseAsset.Url
            $licensePath = Join-Path $tmp $licenseAsset.Nom
            Info "Licence détectée : $($licenseAsset.Nom)"

            # (3b) Téléchargements (msixbundle + licence).
            Info 'Téléchargement du msixbundle App Installer (dernière version)…'
            Invoke-WebRequest -Uri $msixUrl -OutFile $msixPath -UseBasicParsing
            Info 'Téléchargement du fichier de licence…'
            Invoke-WebRequest -Uri $licenseUrl -OutFile $licensePath -UseBasicParsing
        } catch {
            throw ("Bootstrap winget échoué au TÉLÉCHARGEMENT : $($_.Exception.Message). " +
                   "Accès Internet sortant requis. " +
                   "Voir https://learn.microsoft.com/windows/package-manager/winget/ pour un dépannage manuel.")
        }

        # (3c) Peupler le cache persistant pour le prochain test. Le dossier est
        #      créé au besoin (New-Item -Force). Best-effort : un échec de copie
        #      (partage momentanément indispo) ne doit PAS faire échouer le
        #      provisioning — on retéléchargera simplement au run suivant.
        try {
            New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null
            Copy-Item -Path $msixPath    -Destination $cacheMsix -Force
            Copy-Item -Path $licensePath -Destination (Join-Path $cacheDir (Split-Path $licensePath -Leaf)) -Force
            Info "msixbundle + licence mis en cache dans $cacheDir."
        } catch {
            Avert "Impossible de peupler le cache ($($_.Exception.Message)) — le prochain run retéléchargera."
        }
    }

    # Dépendance PRÉALABLE (issue #159) : installer le Windows App Runtime AVANT
    # de provisionner App Installer, sinon Add-AppxProvisionedPackage échoue avec
    # 0x80073CF3 (framework Microsoft.WindowsAppRuntime.1.8 manquant sur LTSC/IoT).
    Install-WindowsAppRuntime

    # (3) Installation hors-ligne du paquet provisionné (Store non requis).
    try {
        Info 'Installation de App Installer (Add-AppxProvisionedPackage -Online)…'
        Add-AppxProvisionedPackage -Online -PackagePath $msixPath -LicensePath $licensePath | Out-Null
    } catch {
        Avert "Add-AppxProvisionedPackage a échoué ($($_.Exception.Message)) — tentative d'enregistrement direct ensuite."
    }

    # (4) Rafraîchir le PATH puis re-vérifier.
    Rafraichir-Path

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        # 2e tentative : enregistrer le paquet pour l'utilisateur courant.
        try {
            Avert 'winget toujours absent après provisionnement — tentative Add-AppxPackage -RegisterByFamilyName…'
            Add-AppxPackage -RegisterByFamilyName -MainPackage 'Microsoft.DesktopAppInstaller_8wekyb3d8bbwe'
        } catch {
            Avert "Add-AppxPackage -RegisterByFamilyName a échoué : $($_.Exception.Message)."
        }
        Rafraichir-Path
    }

    # Nettoyage du dossier temporaire de travail (best-effort). SEUL le cache
    # persistant du partage est conservé — $tmp reste $null si le cache a été
    # utilisé (aucun téléchargement), auquel cas il n'y a rien à nettoyer.
    if ($tmp) { Remove-Item -Path $tmp -Recurse -Force -ErrorAction SilentlyContinue }

    # (5) Échec définitif : erreur claire, DISTINCTE de l'ancien « winget introuvable ».
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw ("Bootstrap winget échoué APRÈS téléchargement + enregistrement " +
               "(Add-AppxProvisionedPackage puis Add-AppxPackage -RegisterByFamilyName). " +
               "winget reste introuvable — CONNU sur LTSC/IoT depuis l'issue #658 " +
               "(dépendance Microsoft.VCLibs.140.00 non satisfaite). Le script " +
               "poursuit sur l'installeur autonome pour OpenSSL.")
    }

    Info 'Bootstrap winget réussi — App Installer déployé.'
}

# ---------------------------------------------------------------------------
# 2. Installations DIRECTES (sans winget) — Git, GitHub CLI, Python, NSSM.
#    Décision issue #658 : voir « Pourquoi plus de winget » en tête de fichier.
#    Chaque fonction est idempotente (Get-Command en tête) et respecte -DryRun.
# ---------------------------------------------------------------------------

function Installer-Git {
    if (Get-Command git -ErrorAction SilentlyContinue) {
        Info 'Git déjà présent — installation sautée (idempotent).'
        return
    }
    if ($DryRun) {
        Info ("[DRY-RUN] Résoudrait et installerait le dernier Git for Windows officiel " +
              "(github.com/git-for-windows/git, /VERYSILENT /NORESTART /NOCANCEL /SP-).")
        return
    }
    $asset = Resoudre-AssetGitHubLatest 'git-for-windows/git' '*-64-bit.exe'
    $exe   = Telecharger-AvecCache $asset.Url 'git' $asset.Nom
    Info "Installation de Git $($asset.Version) (silencieux)…"
    $p = Start-Process -FilePath $exe -ArgumentList '/VERYSILENT /NORESTART /NOCANCEL /SP-' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Installation de Git a échoué (code $($p.ExitCode))." }
    Rafraichir-Path
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "git introuvable après installation." }
    Info 'Git installé.'
}

function Installer-GitHubCli {
    if (Get-Command gh -ErrorAction SilentlyContinue) {
        Info 'GitHub CLI déjà présent — installation sautée (idempotent).'
        return
    }
    if ($DryRun) {
        Info ("[DRY-RUN] Résoudrait et installerait le dernier GitHub CLI officiel " +
              "(github.com/cli/cli, .msi, msiexec /quiet /norestart).")
        return
    }
    $asset = Resoudre-AssetGitHubLatest 'cli/cli' '*windows_amd64.msi'
    $msi   = Telecharger-AvecCache $asset.Url 'gh' $asset.Nom
    Info "Installation de GitHub CLI $($asset.Version) (silencieux)…"
    $p = Start-Process -FilePath 'msiexec.exe' -ArgumentList "/i `"$msi`" /quiet /norestart" -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Installation de GitHub CLI a échoué (code $($p.ExitCode))." }
    Rafraichir-Path
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "gh introuvable après installation." }
    Info 'GitHub CLI installé.'
}

# Python 3.12 — version FIXE : contrairement à Git/gh (GitHub Releases,
# résolus dynamiquement via l'API), python.org ne publie pas d'équivalent
# "latest" simple à interroger par API. À VÉRIFIER avant chaque
# réinstallation (~tous les 3 mois) sur https://www.python.org/downloads/windows/
# et mettre à jour ci-dessous si une version 3.12.x plus récente existe.
$script:PythonVersion    = '3.12.8'
$script:PythonNomFichier = "python-$($script:PythonVersion)-amd64.exe"
$script:PythonUrl        = "https://www.python.org/ftp/python/$($script:PythonVersion)/$($script:PythonNomFichier)"

function Installer-Python {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        Info 'Python déjà présent — installation sautée (idempotent).'
        return
    }
    if ($DryRun) {
        Info ("[DRY-RUN] Téléchargerait et installerait Python $($script:PythonVersion) " +
              "(python.org, /quiet InstallAllUsers=0 PrependPath=1 Include_test=0).")
        return
    }
    $exe = Telecharger-AvecCache $script:PythonUrl 'python' $script:PythonNomFichier
    Info "Installation de Python $($script:PythonVersion) (silencieux, par utilisateur courant)…"
    $p = Start-Process -FilePath $exe -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_test=0' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Installation de Python a échoué (code $($p.ExitCode))." }
    Rafraichir-Path
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "python introuvable après installation (PrependPath=1 modifie le PATH utilisateur — une reconnexion de session peut être nécessaire)."
    }
    Info 'Python installé.'
}

function Installer-Nssm {
    if (Get-Command nssm -ErrorAction SilentlyContinue) {
        Info 'NSSM déjà présent — installation sautée (idempotent).'
        return
    }
    if ($DryRun) {
        Info ('[DRY-RUN] Téléchargerait NSSM 2.24 (nssm.cc/release/nssm-2.24.zip), extrairait ' +
              'nssm.exe (win64) dans C:\NSSM, ajouterait C:\NSSM au PATH machine.')
        return
    }
    $nssmUrl = 'https://nssm.cc/release/nssm-2.24.zip'
    $zip     = Telecharger-AvecCache $nssmUrl 'nssm' 'nssm-2.24.zip'

    $tmpExtract = Join-Path $env:TEMP ('nssm-extract-' + [Guid]::NewGuid().ToString('N'))
    Info 'Extraction de NSSM…'
    Expand-Archive -Path $zip -DestinationPath $tmpExtract -Force
    $exeSource = Join-Path $tmpExtract 'nssm-2.24\win64\nssm.exe'
    if (-not (Test-Path $exeSource)) {
        Remove-Item -Path $tmpExtract -Recurse -Force -ErrorAction SilentlyContinue
        throw "nssm.exe introuvable après extraction (attendu : $exeSource) — archive nssm-2.24.zip inattendue."
    }

    $RepNssm = 'C:\NSSM'
    if (-not (Test-Path $RepNssm)) { New-Item -ItemType Directory -Path $RepNssm -Force | Out-Null }
    Copy-Item -Path $exeSource -Destination (Join-Path $RepNssm 'nssm.exe') -Force
    Remove-Item -Path $tmpExtract -Recurse -Force -ErrorAction SilentlyContinue

    $pathMachine = [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
    if (($pathMachine -split ';') -notcontains $RepNssm) {
        Info "Ajout de $RepNssm au PATH Machine (persistant)…"
        [System.Environment]::SetEnvironmentVariable('Path', "$pathMachine;$RepNssm", 'Machine')
    }
    Rafraichir-Path

    if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
        throw "nssm introuvable après installation dans $RepNssm — vérifier l'extraction et le PATH."
    }
    Info 'NSSM installé.'
}

# ---------------------------------------------------------------------------
# 3. OpenSSL — winget en repli OPTIONNEL (-TenterWinget) ; installeur
#    autonome officiel par défaut (issue #658, point « OpenSSL »).
# ---------------------------------------------------------------------------

# OpenSSL — installeur autonome Shining Light Productions (Win64 OpenSSL
# Light), MÊME éditeur que le paquet winget ShiningLight.OpenSSL.Light
# utilisé jusqu'ici (repli quand -TenterWinget est absent ou échoue). Version
# FIXE : slproweb.com ne publie pas de lien "latest" stable comme GitHub
# Releases — à VÉRIFIER avant chaque réinstallation (~tous les 3 mois) sur
# https://slproweb.com/products/Win32OpenSSL.html et mettre à jour si besoin.
$script:OpenSSLVersion    = '3.4.0'
$script:OpenSSLNomFichier = 'Win64OpenSSL_Light-3_4_0.exe'
$script:OpenSSLUrl        = "https://slproweb.com/download/$($script:OpenSSLNomFichier)"

# Résout le chemin de l'exécutable openssl SANS lever d'exception s'il est
# absent (contrairement à l'ancienne version, qui throw — utilisée maintenant
# uniquement en aval de Installer-OpenSSL, qui garantit sa présence).
function Resoudre-OpenSSL {
    $cmd = Get-Command openssl -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    # Pas sur le PATH : ni le paquet winget ShiningLight.OpenSSL.Light, ni
    # l'installeur autonome équivalent, n'ajoutent openssl.exe au PATH
    # automatiquement (constaté à la main puis via winget, issue #555) —
    # chemin d'installation par défaut de cet installeur :
    $candidat = Join-Path $env:ProgramFiles 'OpenSSL-Win64\bin\openssl.exe'
    if (Test-Path $candidat) {
        # Complète le PATH Machine de façon PERSISTANTE (pas seulement la
        # session courante) : un futur traitement de déchiffrement dans
        # watcher.py (#556), lancé par le service NSSM dans une session
        # distincte, doit retrouver openssl sans dépendre de ce script.
        $dossierBin  = Split-Path $candidat -Parent
        $pathMachine = [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
        if (($pathMachine -split ';') -notcontains $dossierBin) {
            Info "Ajout de $dossierBin au PATH Machine (persistant) pour openssl…"
            [System.Environment]::SetEnvironmentVariable('Path', "$pathMachine;$dossierBin", 'Machine')
        }
        Rafraichir-Path
        return $candidat
    }

    return $null
}

function Installer-OpenSSL {
    if (Resoudre-OpenSSL) {
        Info 'OpenSSL déjà présent — installation sautée (idempotent).'
        return
    }

    if ($DryRun) {
        if ($TenterWinget) {
            Info ("[DRY-RUN] Tenterait d'installer OpenSSL via winget (-TenterWinget), " +
                  "puis replierait sur l'installeur autonome $($script:OpenSSLVersion) en cas d'échec.")
        } else {
            Info ("[DRY-RUN] Téléchargerait et installerait OpenSSL $($script:OpenSSLVersion) " +
                  "(installeur autonome Shining Light Productions, /VERYSILENT /NORESTART /SP-).")
        }
        return
    }

    if ($TenterWinget) {
        Info "-TenterWinget fourni : tentative d'installer OpenSSL via winget avant le repli autonome…"
        try {
            Bootstrap-Winget
            if (Get-Command winget -ErrorAction SilentlyContinue) {
                Installer-Winget 'ShiningLight.OpenSSL.Light' 'OpenSSL'
                Rafraichir-Path
                if (Resoudre-OpenSSL) { Info 'OpenSSL installé via winget.'; return }
            } else {
                Avert 'winget toujours absent après Bootstrap-Winget — repli sur l''installeur autonome.'
            }
        } catch {
            Avert "Tentative winget pour OpenSSL échouée ($($_.Exception.Message)) — repli sur l'installeur autonome."
        }
    }

    Info "Installation d'OpenSSL $($script:OpenSSLVersion) via l'installeur autonome officiel (silencieux)…"
    $exe = Telecharger-AvecCache $script:OpenSSLUrl 'openssl' $script:OpenSSLNomFichier
    $p = Start-Process -FilePath $exe -ArgumentList '/VERYSILENT /NORESTART /SP-' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Installation d'OpenSSL a échoué (code $($p.ExitCode))." }

    # Comme le paquet winget, cet installeur n'ajoute PAS openssl au PATH
    # automatiquement (constaté empiriquement, issue #555) — Resoudre-OpenSSL
    # sait retrouver le chemin d'installation par défaut.
    if (-not (Resoudre-OpenSSL)) {
        throw "openssl introuvable après installation autonome (ni sur le PATH, ni dans le dossier d'installation par défaut)."
    }
    Info 'OpenSSL installé.'
}

# ---------------------------------------------------------------------------
# Exécution des installations (SANS winget par défaut — issue #658).
# ---------------------------------------------------------------------------
Installer-Git
Installer-GitHubCli
Installer-Python
Installer-Nssm
Installer-OpenSSL

# ---------------------------------------------------------------------------
# 4. pyinstaller (raison d'être de CCW : builds .exe délégués par CCL).
# ---------------------------------------------------------------------------
if ($DryRun) {
    Info '[DRY-RUN] Exécuterait : python -m pip install --upgrade pip ; python -m pip install pyinstaller'
} else {
    Info 'Installation de pyinstaller (pip)…'
    python -m pip install --upgrade pip
    python -m pip install pyinstaller
}

# ---------------------------------------------------------------------------
# 5. Claude Code — installeur natif officiel (aucune dépendance Node.js).
# ---------------------------------------------------------------------------
if ($DryRun) {
    Info '[DRY-RUN] Exécuterait : irm https://claude.ai/install.ps1 | iex'
} else {
    Info 'Installation de Claude Code (installeur natif officiel)…'
    irm https://claude.ai/install.ps1 | iex
}

# Ajout explicite du PATH utilisateur (issue #658) : l'installeur Claude Code
# écrit dans <profil>\.local\bin et le SIGNALE en sortie, mais ne l'ajoute pas
# lui-même au PATH utilisateur sur cette configuration — constaté le
# 27/09/2026, obligeant jusqu'ici une fermeture/réouverture de session suivie
# d'un ajout manuel. $env:USERPROFILE (pas un chemin recalculé à partir de
# -CompteService) : c'est le profil qui exécute CE script, voir l'avertissement
# en tête de fichier si ce n'est pas le même compte que -CompteService.
$CheminLocalBin = Join-Path $env:USERPROFILE '.local\bin'
if ($DryRun) {
    Info "[DRY-RUN] Ajouterait $CheminLocalBin au PATH utilisateur s'il est absent."
} else {
    $pathUtilisateur = [System.Environment]::GetEnvironmentVariable('Path', 'User')
    if ((($pathUtilisateur -split ';') | Where-Object { $_ -eq $CheminLocalBin }).Count -eq 0) {
        Info "Ajout de $CheminLocalBin au PATH utilisateur (persistant)…"
        [System.Environment]::SetEnvironmentVariable('Path', "$pathUtilisateur;$CheminLocalBin", 'User')
    } else {
        Info "$CheminLocalBin déjà présent dans le PATH utilisateur."
    }
    Rafraichir-Path
}

# ---------------------------------------------------------------------------
# 6. Clone (lecture seule) du dépôt Bridge_Agent dans le dossier de travail.
# ---------------------------------------------------------------------------
if (-not (Test-Path $RepCCW)) {
    if ($DryRun) { Info "[DRY-RUN] Créerait le dossier $RepCCW." }
    else { New-Item -ItemType Directory -Path $RepCCW | Out-Null }
}

if (Test-Path (Join-Path $RepDepot '.git')) {
    if ($DryRun) { Info "[DRY-RUN] Exécuterait : git -C $RepDepot pull --ff-only" }
    else {
        Info "Dépôt déjà cloné — mise à jour (git pull)…"
        git -C $RepDepot pull --ff-only
    }
} else {
    if ($DryRun) { Info "[DRY-RUN] Exécuterait : git clone https://github.com/$Depot.git $RepDepot" }
    else {
        Info "Clonage de $Depot dans $RepDepot…"
        git clone "https://github.com/$Depot.git" $RepDepot
    }
}

# ---------------------------------------------------------------------------
# 7. Paire de clés de chiffrement des tokens de bootstrap « Projet CCW »
#    (issue #554, 1/3 — brique clés seule ; le chiffrement côté formulaire et
#    le déchiffrement côté watcher.py font l'objet de #555/#556 à suivre).
#
#    Contexte : la future case « Projet CCW » du formulaire de création de
#    projet transmettra GH_TOKEN et CLAUDE_CODE_OAUTH_TOKEN dans le corps
#    d'une issue GitHub traitée de façon ASYNCHRONE par CCW (PC potentiellement
#    éteint à la soumission) — chiffrement asymétrique retenu plutôt que clair
#    en dur. La clé PRIVÉE ne quitte jamais cette machine ; la clé PUBLIQUE
#    n'est pas sensible et doit être récupérable côté CCL pour chiffrer.
#
#    Choix technique : RSA 3072 bits en PEM, généré via openssl.exe (installé
#    à l'étape 3 ci-dessus — winget en option, installeur autonome sinon,
#    voir Installer-OpenSSL / Resoudre-OpenSSL).
#
#    Écarté : .NET natif (System.Security.Cryptography), dont les méthodes
#    d'export PEM (ExportPkcs8PrivateKey / ExportSubjectPublicKeyInfo) ne sont
#    disponibles qu'à partir de .NET 5+ — confirmé absentes de Windows
#    PowerShell 5.1 (.NET Framework), seule version actuellement en place sur
#    CCW, ce qui aurait exigé soit de reconstruire l'encodage ASN.1/DER à la
#    main, soit d'installer PowerShell 7+/.NET 5+ en supplément. Écarté aussi :
#    `age`, pour éviter d'imposer une dépendance supplémentaire alors
#    qu'openssl couvre déjà le besoin. Le format PEM (norme ouverte,
#    contrairement au XML natif .NET) reste directement exploitable côté CCL
#    (Python) pour le chiffrement à venir.
#
#    Stockage : C:\CCW\cles_bootstrap\, un dossier LOCAL au PC fixe, frère de
#    $RepDepot mais HORS du clone git (jamais committé) et hors de
#    C:\CCW_Share (ce dernier est un point de montage réseau accédé depuis
#    CCL, cf. BRIDGE_AGENT_DOC.md §16.3 — la clé privée n'y a rien à faire).
#    Permissions restrictives sur le fichier de clé PRIVÉE (icacls,
#    héritage coupé) : SYSTEM + Administrateurs (lecture/écriture), et
#    $CompteService en lecture seule (compte sous lequel tourne
#    CCW-Watcher, futur lecteur de cette clé pour le déchiffrement en #556).
#
#    Idempotent : si la paire existe déjà (réinstallations rapprochées lors
#    d'un test), la génération est sautée — reste UNE clé par cycle de vie
#    de la machine, régénérée à chaque réinstallation Windows complète (cf.
#    rappel dans REINSTALLATION_CCW.md sur les issues de bootstrap en vol au
#    moment d'une réinstallation).
# ---------------------------------------------------------------------------
function Assurer-ClesBootstrap {
    $RepCles        = Join-Path $RepCCW 'cles_bootstrap'
    $CheminPrivee   = Join-Path $RepCles 'bootstrap_privee.pem'
    $CheminPublique = Join-Path $RepCles 'bootstrap_publique.pem'

    if ((Test-Path $CheminPrivee) -and (Test-Path $CheminPublique)) {
        Info "Paire de clés de bootstrap déjà présente ($RepCles) — génération sautée (idempotent)."
        return $CheminPublique
    }

    if ($DryRun) {
        Info "[DRY-RUN] Générerait la paire de clés RSA 3072 bits de bootstrap dans $RepCles (openssl genpkey/pkey) + icacls."
        return $CheminPublique
    }

    Info 'Génération de la paire de clés RSA de bootstrap (chiffrement tokens « Projet CCW », issue #554)…'
    $openssl = Resoudre-OpenSSL
    if (-not $openssl) { throw "openssl introuvable — Installer-OpenSSL aurait dû l'installer avant cette étape." }
    if (-not (Test-Path $RepCles)) { New-Item -ItemType Directory -Path $RepCles | Out-Null }

    & $openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out $CheminPrivee
    if ($LASTEXITCODE -ne 0) { throw "openssl genpkey a échoué (code $LASTEXITCODE)." }
    & $openssl pkey -in $CheminPrivee -pubout -out $CheminPublique
    if ($LASTEXITCODE -ne 0) { throw "openssl pkey (extraction de la clé publique) a échoué (code $LASTEXITCODE)." }

    Info 'Restriction des permissions de la clé privée (icacls)…'
    icacls.exe $CheminPrivee /inheritance:r | Out-Null
    icacls.exe $CheminPrivee /grant 'SYSTEM:F' | Out-Null
    icacls.exe $CheminPrivee /grant 'BUILTIN\Administrators:F' | Out-Null
    icacls.exe $CheminPrivee /grant "${CompteService}:R" | Out-Null

    Info "Paire de clés de bootstrap générée dans $RepCles."
    return $CheminPublique
}

$CheminCleBootstrapPublique = Assurer-ClesBootstrap

# ---------------------------------------------------------------------------
# 8. Écriture de configs\ccw.conf.
#    REP_TRAVAIL pointe vers $RepDepot (C:\CCW\Bridge_Agent), le clone du
#    dépôt déjà utilisé plus haut dans le script — cohérent avec le modèle
#    multi-projets actif et Get-CheminsProjetCcw (ccw-commun.psm1). Avant
#    l'issue #670, une valeur figée C:\CCW_Share (héritée de l'ancien
#    modèle CCW unifié, issue #231, abandonné) était déconnectée de
#    $RepDepot et provoquait un REP_TRAVAIL erroné à chaque provisioning.
#    TOPIC_NTFY est un placeholder à renseigner (comme le mot de passe phase 1).
# ---------------------------------------------------------------------------
$RepConfigs = Join-Path $RepDepot 'configs'
$CheminConf = Join-Path $RepConfigs 'ccw.conf'

# Répertoire de travail = le clone du dépôt ($RepDepot), pas un partage
# séparé — voir issue #670 (suite #668).
$RepTravail = $RepDepot

$contenuConf = @"
# configs/ccw.conf — Config du watcher pour l'agent Claude Code Windows (CCW).
# Généré par provisionner.ps1 (phase 2, issue #147). Format : CLE = valeur.

# ─── Requis ───────────────────────────────────────────────────────────────────
NOM         = ccw
DEPOT       = $Depot
LABEL       = for-windows
# REP_TRAVAIL : clone du dépôt, local au PC fixe (issue #670, suite #668).
REP_TRAVAIL = $RepTravail

# ─── ntfy ─────────────────────────────────────────────────────────────────────
# PLACEHOLDER à renseigner LOCALEMENT (comme le mot de passe en phase 1).
# Ne PAS committer la valeur réelle du topic.
TOPIC_NTFY  = ###TOPIC_NTFY_A_DEFINIR###

# ─── Périmètre CCW (dossiers autorisés) ───────────────────────────────────────
PERIMETRE   = $RepTravail

# ─── Optionnels (défaut si commenté) ──────────────────────────────────────────
# INTERVALLE     = 10
# MAX_ESSAIS     = 3
# TIMEOUT_CLAUDE = 600
"@

if ($DryRun) {
    Info "[DRY-RUN] Écrirait $CheminConf (TOPIC_NTFY en placeholder)."
} else {
    if (-not (Test-Path $RepConfigs)) { New-Item -ItemType Directory -Path $RepConfigs | Out-Null }
    Info "Écriture de $CheminConf…"
    # UTF-8 sans BOM pour rester lisible par le parseur .conf de watcher.py.
    [System.IO.File]::WriteAllText($CheminConf, $contenuConf, (New-Object System.Text.UTF8Encoding($false)))
}

# ---------------------------------------------------------------------------
# 9. Windows Update — DÉSACTIVÉ (issue #658, point 5).
#
#    Décision d'Alain suite au plantage ucrtbase.dll du 27/09/2026, causé par
#    une mise à jour cumulative Windows appliquée automatiquement sur cette
#    édition d'évaluation. Devient une étape STANDARD du provisioning pour ne
#    plus avoir à s'en souvenir manuellement à chaque réinstallation.
#    Idempotent : Set-Service -StartupType Disabled et la clé de registre
#    NoAutoUpdate ne font rien de plus si déjà en place.
# ---------------------------------------------------------------------------
function Desactiver-WindowsUpdate {
    if ($DryRun) {
        Info ('[DRY-RUN] Arrêterait le service wuauserv, le passerait en StartupType Disabled, ' +
              'et poserait HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU\NoAutoUpdate=1.')
        return
    }
    Info 'Désactivation de Windows Update (décision du 27/09/2026, plantage ucrtbase.dll)…'
    try {
        Stop-Service -Name wuauserv -Force -ErrorAction SilentlyContinue
        Set-Service -Name wuauserv -StartupType Disabled
    } catch {
        Avert "Impossible de désactiver le service wuauserv ($($_.Exception.Message)) — à vérifier manuellement (services.msc)."
    }
    try {
        $cheminAU = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
        if (-not (Test-Path $cheminAU)) { New-Item -Path $cheminAU -Force | Out-Null }
        Set-ItemProperty -Path $cheminAU -Name 'NoAutoUpdate' -Value 1 -Type DWord
        Info 'Windows Update désactivé (service + clé de registre NoAutoUpdate).'
    } catch {
        Avert "Impossible de poser la clé de registre NoAutoUpdate ($($_.Exception.Message)) — à vérifier manuellement."
    }
}

Desactiver-WindowsUpdate

# ---------------------------------------------------------------------------
# 10. Service Windows (NSSM) : lance le watcher au démarrage de la machine
#     (sans session ouverte), avec redémarrage automatique en cas d'échec.
#
#     ✅ Équivalent DIRECT des services systemd --user du §13 : démarrage au
#     boot sans session (SERVICE_AUTO_START), redémarrage automatique sur échec
#     (AppExit Default Restart + AppRestartDelay). NSSM remplace l'ancienne
#     tâche planifiée -AtLogOn, qui ne redémarrait pas au boot sans session.
#     Le watcher lui-même reste la première ligne de robustesse (boucle interne).
#
#     Compte de service — $CompteService (AlainW par défaut), PAS LocalSystem
#     (issue #446, suite #447) : PC physique, non-admin, cohérent avec un
#     compte utilisateur normal du PC. NSSM exige le mot de passe du compte
#     pour ObjectName (sauf comptes virtuels type LocalSystem).
#
#     Saisie du mot de passe — Read-Host -AsSecureString, PAS Get-Credential
#     (issue #658, point 2) : Get-Credential ouvre une fenêtre GRAPHIQUE, qui
#     reste invisible et bloque silencieusement le script (sans erreur
#     visible) quand ce script est lancé depuis une session SSH — constaté le
#     27/09/2026. Read-Host -AsSecureString fonctionne identiquement en
#     session interactive locale ou en SSH (même pattern que
#     mettre_a_jour_tokens_ccw.ps1).
#
#     PATH dans AppEnvironmentExtra — issue #658, point 1 : un service NSSM
#     ne voit ni claude.exe ni les autres exécutables installés en per-user
#     (Claude Code, Python), même si la session interactive du même compte
#     les trouve sans problème, TANT QUE le PATH n'est pas explicitement posé
#     dans AppEnvironmentExtra (l'environnement du service n'hérite pas du
#     PATH utilisateur). Les tokens (GH_TOKEN, CLAUDE_CODE_OAUTH_TOKEN) sont
#     posés PLUS TARD par mettre_a_jour_tokens_ccw.ps1 — ce dernier a été mis
#     à jour (même issue #658) pour RECONSTRUIRE cette ligne PATH à ce
#     moment-là plutôt que de la perdre : « nssm set » REMPLACE toute la
#     valeur AppEnvironmentExtra, il ne l'étend pas.
# ---------------------------------------------------------------------------
$NomService = 'CCW-Watcher'
$pythonExe  = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) { $pythonExe = 'python' }

# Fichier de log dédié au service (stdout/stderr capturés par NSSM).
$RepLogs = Join-Path $RepDepot 'logs'
$LogService = Join-Path $RepLogs 'ccw-service.log'

# Idempotence : si le service existe déjà, l'arrêter puis le supprimer avant
# de le recréer (script relançable sans erreur).
$svcExistant = Get-Service -Name $NomService -ErrorAction SilentlyContinue
if ($svcExistant) {
    if ($DryRun) {
        Info "[DRY-RUN] Arrêterait puis supprimerait le service existant « $NomService » avant recréation."
    } else {
        Info "Service « $NomService » déjà présent — arrêt puis suppression avant recréation…"
        nssm stop   $NomService | Out-Null
        nssm remove $NomService confirm | Out-Null
    }
}

if ($DryRun) {
    Info "[DRY-RUN] Enregistrerait le service Windows « $NomService » (NSSM) :"
    Info "[DRY-RUN]   $pythonExe watcher.py --config configs\ccw.conf (AppDirectory=$RepDepot)"
    Info "[DRY-RUN]   Démarrage auto, redémarrage sur échec (5000 ms), logs -> $LogService"
    Info '[DRY-RUN]   AppEnvironmentExtra = PATH (machine + .local\bin + WindowsApps), une ligne'
    Info "[DRY-RUN]   Demanderait le mot de passe de « $CompteService » (Read-Host -AsSecureString), puis démarrerait le service."
} else {
    if (-not (Test-Path $RepLogs)) { New-Item -ItemType Directory -Path $RepLogs | Out-Null }

    Info "Enregistrement du service Windows « $NomService » (NSSM)…"

    nssm install $NomService $pythonExe 'watcher.py --config configs\ccw.conf'
    nssm set $NomService AppDirectory     $RepDepot
    nssm set $NomService Start            SERVICE_AUTO_START
    nssm set $NomService AppExit Default  Restart
    nssm set $NomService AppRestartDelay  5000
    # Rediriger stdout/stderr du service vers un fichier de log dédié.
    nssm set $NomService AppStdout        $LogService
    nssm set $NomService AppStderr        $LogService

    # PATH complet du compte de service (issue #658, point 1). Une seule
    # LIGNE ici (PATH=…) : mettre_a_jour_tokens_ccw.ps1 en ajoutera deux
    # autres (GH_TOKEN, CLAUDE_CODE_OAUTH_TOKEN) plus tard, en RECONSTRUISANT
    # celle-ci plutôt qu'en la préservant à l'identique (le PATH peut évoluer
    # entre le provisioning et le renouvellement des tokens).
    $PathServiceComplet = @(
        [System.Environment]::GetEnvironmentVariable('Path', 'Machine'),
        $CheminLocalBin,
        "C:\Users\$CompteService\AppData\Local\Microsoft\WindowsApps"
    ) -join ';'
    nssm set $NomService AppEnvironmentExtra "PATH=$PathServiceComplet"

    Info "Mot de passe du compte « $CompteService » requis pour l'exécution du service :"
    $secMotDePasse = Read-Host -AsSecureString "Mot de passe de $CompteService"
    $motDePassePlain = ConvertFrom-SecureStringPlain $secMotDePasse
    try {
        nssm set $NomService ObjectName ".\$CompteService" $motDePassePlain
    } finally {
        $motDePassePlain = $null
        [System.GC]::Collect()
    }

    # Démarrer immédiatement (le service repartira ensuite seul à chaque boot).
    nssm start $NomService | Out-Null
}

# ---------------------------------------------------------------------------
# 11. Résumé final (issue #658).
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host '========================================================================' -ForegroundColor Cyan
Write-Host '  RÉSUMÉ DU PROVISIONING' -ForegroundColor Cyan
Write-Host '========================================================================' -ForegroundColor Cyan
if ($DryRun) {
    Avert 'Mode -DryRun / -WhatIf : AUCUNE action listée ci-dessus n''a été exécutée réellement.'
}
Info ''
Info 'Logiciels :'
Info "  - Git          : $(Decrire-Version 'git' '--version')"
Info "  - Python       : $(Decrire-Version 'python' '--version')"
Info "  - GitHub CLI   : $(Decrire-Version 'gh' '--version')"
Info "  - NSSM         : $(Decrire-Presence 'nssm')"
Info "  - OpenSSL      : $(Decrire-Version 'openssl' 'version')"
Info "  - Claude Code  : $(Decrire-Version 'claude' '--version')"
Info ''
if ($DryRun) {
    Info "Service « $NomService » : (non créé — mode -DryRun)"
} else {
    Info "Service « $NomService » : créé/recréé, démarré."
    Info "  AppEnvironmentExtra contient PATH (machine + $CheminLocalBin + WindowsApps)."
}
Info "Dépôt cloné dans : $RepDepot"
Info "Config écrite : $CheminConf (TOPIC_NTFY encore en placeholder)"
Info "Clé publique de bootstrap « Projet CCW » : $CheminCleBootstrapPublique"
Info ''
Info 'ÉTAPES ENCORE MANUELLES (interactives par nature — ne peuvent pas être automatisées) :'
Info '  1. Authentification Claude Code : claude auth login (interactif),'
Info '     ou headless via ANTHROPIC_API_KEY (setx, ne JAMAIS committer la clé).'
Info '  2. Saisie des tokens du service : .\mettre_a_jour_tokens_ccw.ps1'
Info '     (GH_TOKEN + CLAUDE_CODE_OAUTH_TOKEN — reconstruit aussi la ligne PATH, issue #658).'
Info "  3. Renseigner TOPIC_NTFY dans $CheminConf (placeholder actuel)."
Info ''
Info '⚠ RAPPEL (issue #658, point 4) : un compte déjà ouvert AVANT cette installation'
Info '  ne voit PAS le nouveau PATH avant reconnexion. Ferme puis rouvre la session'
Info '  (ou, mieux, redémarre la machine) avant de considérer ce provisioning terminé.'
Info ''

if (-not $DryRun -and (Test-Path $CheminCleBootstrapPublique)) {
    Info 'Clé publique de bootstrap « Projet CCW » (à récupérer côté CCL) :'
    Get-Content $CheminCleBootstrapPublique | ForEach-Object { Info "  $_" }
}
