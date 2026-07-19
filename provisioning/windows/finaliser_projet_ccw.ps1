<#
  finaliser_projet_ccw.ps1 — Finaliser un projet CCW en UNE commande (issue #173, suite #170).

  Après ajouter_projet_ccw.ps1 (clone + config + service), il restait trois
  étapes manuelles dispersées : éditer TOPIC_NTFY à la main dans le fichier
  config, créer le token GitHub dédié (forcément manuel, navigateur), puis
  relancer mettre_a_jour_tokens_ccw.ps1 avec les bons -NomService/-RepDepot
  reconstitués à partir du nom du projet. Ce script enchaîne le tout :

    1. À partir du seul -NomProjet, DÉRIVE (même logique qu'ajouter_projet_ccw.ps1)
       le service CCW-Watcher-<NomProjet>, le dossier C:\CCW\<NomProjet> et le
       config configs\<nom-minuscule>-ccw.conf, et VÉRIFIE que ces chemins
       existent (sinon : renvoie vers ajouter_projet_ccw.ps1).
    2. Demande TOPIC_NTFY (Read-Host, pas un secret) et réécrit la ligne
       « TOPIC_NTFY = … » DANS le fichier config QUELLE QUE SOIT sa valeur
       actuelle — placeholder ###TOPIC_NTFY_A_DEFINIR### OU topic déjà
       renseigné (issue #176 : topic modifiable après coup). Édition ciblée
       de la seule ligne, le reste du fichier est préservé à l'identique.
       Un topic laissé vide à la saisie laisse le config inchangé.
    3. Rappelle la marche à suivre pour créer le token GitHub dédié (repo
       unique, permissions, expiration alignée — mêmes instructions
       qu'ajouter_projet_ccw.ps1), avec une PAUSE pour le faire.
    4. Appelle DIRECTEMENT mettre_a_jour_tokens_ccw.ps1 (pas de duplication de
       code) avec les paramètres déduits à l'étape 1 : saisie masquée des deux
       tokens, pose de AppEnvironmentExtra, redémarrage du service, vérification
       finale des logs.
    5. Résumé final clair reprenant le résultat de cette vérification.

  Prérequis : le projet doit AVOIR ÉTÉ CRÉÉ au préalable par ajouter_projet_ccw.ps1
  (le clone, le config et le service doivent exister). Exécution en administrateur,
  DANS la VM CCW-Build.

  Exemple concret (Scrabble) :
    powershell -ExecutionPolicy Bypass -File provisioning\windows\finaliser_projet_ccw.ps1 `
        -NomProjet Scrabble

  Non exécuté contre une VM réelle — test manuel par Alain.
#>

[CmdletBinding()]
param(
    # Nom du projet, tel que passé à ajouter_projet_ccw.ps1 (ex. Scrabble).
    # Demandé interactivement s'il n'est pas fourni. Sert à dériver le service,
    # le dossier et le config — aucune autre saisie de chemin n'est nécessaire.
    [string]$NomProjet,

    # Racine de travail dédiée à CCW côté invité (comme ajouter_projet_ccw.ps1).
    [string]$RepCCW = 'C:\CCW'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Info($msg)  { Write-Host "[finaliser] $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "[finaliser] $msg" -ForegroundColor Green }
function Avert($msg) { Write-Host "[finaliser] AVERTISSEMENT : $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------------------
# 1. Paramètre + DÉRIVATION des chemins (même logique qu'ajouter_projet_ccw.ps1)
#    puis VÉRIFICATION de leur existence.
# ---------------------------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($NomProjet)) {
    $NomProjet = Read-Host 'Nom du projet à finaliser (ex. Scrabble)'
}
$NomProjet = $NomProjet.Trim()
if ([string]::IsNullOrWhiteSpace($NomProjet)) { throw 'Nom de projet vide — abandon.' }

# Dérivations IDENTIQUES à ajouter_projet_ccw.ps1 (casse conservée pour le
# dossier et le service, minuscules pour le préfixe config/log).
$nomMin     = $NomProjet.ToLowerInvariant()
$NomService = "CCW-Watcher-$NomProjet"
$RepDepot   = Join-Path $RepCCW $NomProjet
$NomConf    = "$nomMin-ccw.conf"
$NomLog     = "ccw-$nomMin-service.log"
$CheminConf = Join-Path (Join-Path $RepDepot 'configs') $NomConf

Info "Projet      : $NomProjet"
Info "Dossier     : $RepDepot"
Info "Service     : $NomService"
Info "Config      : $CheminConf"
Info "Log service : logs\$NomLog"
Write-Host ''

# Le projet doit exister (créé par ajouter_projet_ccw.ps1). Messages clairs
# sinon, renvoyant explicitement vers le script de création.
if (-not (Test-Path (Join-Path $RepDepot '.git'))) {
    Avert "Dossier « $RepDepot » absent (ou non cloné) : le projet « $NomProjet » n'a pas encore été créé."
    Avert 'Lance d''abord ajouter_projet_ccw.ps1 :'
    Avert "  powershell -File provisioning\windows\ajouter_projet_ccw.ps1 -NomProjet $NomProjet -Depot AlainDelree/$NomProjet"
    exit 1
}
if (-not (Test-Path $CheminConf)) {
    Avert "Fichier config « $CheminConf » introuvable : le projet « $NomProjet » n'a pas été correctement créé."
    Avert 'Relance ajouter_projet_ccw.ps1 pour (re)générer le config :'
    Avert "  powershell -File provisioning\windows\ajouter_projet_ccw.ps1 -NomProjet $NomProjet -Depot AlainDelree/$NomProjet"
    exit 1
}
if (-not (Get-Service -Name $NomService -ErrorAction SilentlyContinue)) {
    Avert "Service « $NomService » introuvable : le projet « $NomProjet » n'a pas été enregistré."
    Avert 'Relance ajouter_projet_ccw.ps1 pour (re)créer le service :'
    Avert "  powershell -File provisioning\windows\ajouter_projet_ccw.ps1 -NomProjet $NomProjet -Depot AlainDelree/$NomProjet"
    exit 1
}

# ---------------------------------------------------------------------------
# 2. TOPIC_NTFY : saisie interactive puis réécriture CIBLÉE de la ligne
#    « TOPIC_NTFY = … » dans le config (le reste du fichier reste identique
#    octet pour octet). issue #176 : la ligne est remplacée QUELLE QUE SOIT
#    sa valeur actuelle (placeholder OU topic déjà renseigné), pour que le
#    topic reste modifiable après sa première définition — au même titre que
#    les tokens. Un topic laissé vide à la saisie laisse le config inchangé.
# ---------------------------------------------------------------------------
# Lecture en UTF-8 sans BOM, comme écrit par ajouter_projet_ccw.ps1.
$contenuConf = [System.IO.File]::ReadAllText($CheminConf)

# Motif ciblé sur la ligne « TOPIC_NTFY = <n'importe quoi> » (multi-lignes).
# [^\r\n]* : on s'arrête à la fin de ligne SANS avaler le CR/LF, pour préserver
# les fins de ligne (CRLF côté Windows). Fonctionne pour la première définition
# (placeholder) comme pour une modification ultérieure.
$motifTopic = '(?m)^[ \t]*TOPIC_NTFY[ \t]*=[^\r\n]*'

$topic = Read-Host "Valeur de TOPIC_NTFY pour « $NomProjet » (ex. bridge_scrabble_xxxxx ; vide = laisser inchangé)"
$topic = $topic.Trim()

if ([string]::IsNullOrWhiteSpace($topic)) {
    Avert 'TOPIC_NTFY laissé vide — config inchangé (valeur actuelle conservée).'
} elseif ($contenuConf -match $motifTopic) {
    # Remplacement littéral (MatchEvaluator) : aucun caractère du topic n'est
    # interprété comme référence regex. Seule la ligne TOPIC_NTFY change, le
    # reste (commentaires, autres clés) est préservé à l'identique.
    $ligneTopic  = "TOPIC_NTFY  = $topic"
    $contenuConf = [regex]::Replace($contenuConf, $motifTopic, { $ligneTopic })
    # Réécriture en UTF-8 SANS BOM (le parseur .conf de watcher.py l'attend ainsi).
    [System.IO.File]::WriteAllText($CheminConf, $contenuConf, (New-Object System.Text.UTF8Encoding($false)))
    Ok "TOPIC_NTFY (re)défini à « $topic » dans $CheminConf."
} else {
    Avert "Aucune ligne TOPIC_NTFY trouvée dans $CheminConf : config inchangé (fichier inattendu ?)."
}
Write-Host ''

# ---------------------------------------------------------------------------
# 3. Rappel de création du token GitHub dédié + PAUSE.
#    Mêmes instructions qu'ajouter_projet_ccw.ps1 : repo unique, permissions,
#    expiration alignée. La pause laisse le temps de créer le token avant la
#    saisie masquée de l'étape 4.
# ---------------------------------------------------------------------------
Info 'AVANT de coller les tokens : crée le token GitHub fine-grained DÉDIÉ à ce projet'
Info '(GitHub → Settings → Developer settings → Fine-grained tokens) :'
Info "  • Repository access → AlainDelree/$NomProjet UNIQUEMENT"
Info '  • Permissions : Issues = Read and write, Metadata = Read-only'
Info '  • Expiration : LA MÊME DATE que le token Bridge_Agent (≈ 2026-10-17,'
Info "    aligné sur l'éval Windows) — ne pas laisser dériver (cf. §16)."
Write-Host ''
Read-Host 'Appuie sur Entrée une fois le token créé et copié' | Out-Null
Write-Host ''

# ---------------------------------------------------------------------------
# 4. Pose des tokens : on APPELLE directement mettre_a_jour_tokens_ccw.ps1
#    (aucune duplication de la logique de saisie masquée / AppEnvironmentExtra /
#    redémarrage / vérification). On lui passe les paramètres déduits à l'étape 1,
#    dont -NomLog pour qu'il vérifie le BON log de service (ccw-<nom>-service.log).
# ---------------------------------------------------------------------------
$scriptTokens = Join-Path $PSScriptRoot 'mettre_a_jour_tokens_ccw.ps1'
if (-not (Test-Path $scriptTokens)) {
    throw "Script attendu introuvable : $scriptTokens (doit être dans le même dossier)."
}

Info "Pose des tokens sur « $NomService » via mettre_a_jour_tokens_ccw.ps1…"
Write-Host ''
& $scriptTokens -NomService $NomService -RepDepot $RepDepot -NomLog $NomLog
# Le call operator '&' isole le exit du script appelé : il fixe $LASTEXITCODE
# et rend la main ici (0 = OK, 2 = à vérifier, 1 = abandon saisie).
$codeTokens = $LASTEXITCODE

# ---------------------------------------------------------------------------
# 5. Résumé final, à partir du code renvoyé par mettre_a_jour_tokens_ccw.ps1.
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host '======================================================================'
if ($codeTokens -eq 0) {
    Ok "Projet « $NomProjet » FINALISÉ : TOPIC_NTFY renseigné, tokens posés,"
    Ok "service « $NomService » redémarré — aucune ligne ERROR dans les derniers logs."
    Ok "Vérif à tout moment : nssm status $NomService  /  Get-Service $NomService"
} else {
    Avert "Projet « $NomProjet » : TOPIC_NTFY et tokens ont été appliqués, mais la"
    Avert "vérification finale n'est pas concluante (code $codeTokens de mettre_a_jour_tokens_ccw.ps1)."
    Avert 'Relis les dernières lignes de log affichées ci-dessus, ou :'
    Avert "  Get-Content (Join-Path $RepDepot 'logs\$NomLog') -Tail 30"
}
Write-Host '======================================================================'

exit $codeTokens
