<#
  ajouter_projet_ccw.ps1 — Instancier un NOUVEAU projet CCW dans la VM (issue #170).

  Généralisation multi-projets de CCW, sur le modèle des watchers CCL côté
  Linux : chaque projet a son propre clone, son propre config et son propre
  service NSSM. Là où provisionner.ps1 met en place l'agent CCW lui-même
  (Git/gh/Python/NSSM/OpenSSL + Claude Code + service CCW-Watcher pour
  Bridge_Agent — sans dépendre de winget depuis l'issue #658), CE script
  ajoute un projet SUPPLÉMENTAIRE une fois l'outillage déjà installé :
  il ne réinstalle rien, il se contente de cloner, configurer et enregistrer un
  service dédié.

  Ce qu'il fait, pour un projet <NomProjet> (dépôt <owner/repo>) :
    1. clone le dépôt (lecture seule) dans C:\CCW\<NomProjet> — jamais de push,
       même prudence que Bridge_Agent ;
    2. écrit configs\<nom>-ccw.conf (NOM=<nom>-ccw, DEPOT=<owner/repo>,
       LABEL=for-windows, REP_TRAVAIL / PERIMETRE = C:\CCW\<NomProjet>,
       TOPIC_NTFY = placeholder à renseigner manuellement) ;
    3. enregistre un NOUVEAU service NSSM « CCW-Watcher-<NomProjet> » qui lance
       watcher.py --config configs\<nom>-ccw.conf au démarrage (mêmes réglages
       que CCW-Watcher : SERVICE_AUTO_START, AppExit Default Restart,
       AppRestartDelay, logs\ccw-<nom>-service.log).

  Idempotent : relançable sans dommage — le clone est mis à jour par pull, et le
  service existant est arrêté/supprimé avant recréation (même pattern que
  provisionner.ps1).

  IMPORTANT — token GitHub : ce script ne configure PAS AppEnvironmentExtra.
  Chaque service CCW a son PROPRE token fine-grained (limité à SON seul dépôt),
  et TOUS les tokens partagent la MÊME date d'expiration que le token
  Bridge_Agent (≈ mi-octobre 2026, aligné sur l'éval Windows — cf. §16). La
  finalisation (TOPIC_NTFY + pose du token + redémarrage + vérif) se fait
  ENSUITE en UNE SEULE commande (issue #173, rappel affiché en fin de script) :
    powershell -File provisioning\windows\finaliser_projet_ccw.ps1 `
        -NomProjet <NomProjet>

  Prérequis : provisionner.ps1 déjà passé (Git, Python, NSSM installés).
  Exécution en administrateur, DANS la VM CCW-Build.

  Exemple concret (Scrabble, dépôt public — aucun token requis pour le clone) :
    powershell -ExecutionPolicy Bypass -File provisioning\windows\ajouter_projet_ccw.ps1 `
        -NomProjet Scrabble -Depot AlainDelree/Scrabble
#>

[CmdletBinding()]
param(
    # Nom du projet (sert au dossier C:\CCW\<NomProjet>, au nom de service
    # CCW-Watcher-<NomProjet> et, en minuscules, au préfixe du config/log).
    # Demandé interactivement s'il n'est pas fourni.
    [string]$NomProjet,

    # Dépôt GitHub au format owner/repo (ex. AlainDelree/Scrabble).
    # Demandé interactivement s'il n'est pas fourni.
    [string]$Depot,

    # Racine de travail dédiée à CCW côté invité (comme provisionner.ps1).
    [string]$RepCCW = 'C:\CCW'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Helpers d'affichage (Info/Avert) et dérivation de chemins projet, communs
# aux scripts CCW locaux (issue #606) — ce script est l'exception : à la fois
# local (dans le clone git) et poussé seul par SCP (app/ccw.py), donc le
# module est copié à ses côtés dans les deux cas (même dossier : $PSScriptRoot).
Import-Module (Join-Path $PSScriptRoot 'ccw-commun.psm1') -Force
Set-PrefixeCcw 'ajouter-projet'

# ---------------------------------------------------------------------------
# 0. Paramètres (arguments ou prompt interactif) + validation minimale.
# ---------------------------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($NomProjet)) {
    $NomProjet = Read-Host 'Nom du projet (ex. Scrabble)'
}
if ([string]::IsNullOrWhiteSpace($Depot)) {
    $Depot = Read-Host 'Dépôt GitHub au format owner/repo (ex. AlainDelree/Scrabble)'
}

$NomProjet = $NomProjet.Trim()
$Depot     = $Depot.Trim()

if ([string]::IsNullOrWhiteSpace($NomProjet)) { throw 'Nom de projet vide — abandon.' }
if ($Depot -notmatch '^[^/\s]+/[^/\s]+$') {
    throw "Dépôt « $Depot » invalide : attendu au format owner/repo (ex. AlainDelree/Scrabble)."
}

# nom en minuscules pour le préfixe du config et du log (cohérent avec les
# configs CCL : bridge_agent.conf, scrabble.conf…). Le NomProjet d'origine
# (casse conservée) sert au dossier et au nom de service, plus lisibles.
$nomMin      = $NomProjet.ToLowerInvariant()
$chemins     = Get-CheminsProjetCcw -NomProjet $NomProjet -RepCCW $RepCCW
$NomService  = $chemins.NomService
$RepDepot    = $chemins.RepDepot
$NomConf     = $chemins.NomConf
$NomLog      = $chemins.NomLog

Info "Projet      : $NomProjet"
Info "Dépôt       : $Depot"
Info "Dossier     : $RepDepot"
Info "Service     : $NomService"
Info "Config      : configs\$NomConf"
Info "Log service : logs\$NomLog"
Write-Host ''

# ---------------------------------------------------------------------------
# 1. Clone (lecture seule) du dépôt dans C:\CCW\<NomProjet>.
#    Comme Bridge_Agent : jamais de push. Un dépôt PUBLIC (ex. Scrabble) ne
#    demande aucune authentification pour le clone (seul l'accès en écriture
#    aux Issues nécessitera le token dédié posé plus tard).
# ---------------------------------------------------------------------------
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'git introuvable dans le PATH — provisionner.ps1 doit avoir été exécuté au préalable.'
}
if (-not (Test-Path $RepCCW)) { New-Item -ItemType Directory -Path $RepCCW | Out-Null }

if (Test-Path (Join-Path $RepDepot '.git')) {
    Info "Dépôt déjà cloné — mise à jour (git pull --ff-only)…"
    git -C $RepDepot pull --ff-only
} else {
    Info "Clonage de $Depot dans $RepDepot…"
    git clone "https://github.com/$Depot.git" $RepDepot
}

# ---------------------------------------------------------------------------
# 2. Écriture de configs\<nom>-ccw.conf.
#    REP_TRAVAIL / PERIMETRE pointent vers le clone dédié C:\CCW\<NomProjet>
#    (chaque projet est isolé dans son propre dossier, comme les REP_TRAVAIL
#    distincts des watchers CCL). TOPIC_NTFY reste un placeholder à renseigner
#    manuellement, comme pour ccw.conf.
# ---------------------------------------------------------------------------
$RepConfigs = Join-Path $RepDepot 'configs'
if (-not (Test-Path $RepConfigs)) { New-Item -ItemType Directory -Path $RepConfigs | Out-Null }
$CheminConf = Join-Path $RepConfigs $NomConf

# Préservation du TOPIC_NTFY déjà finalisé (issue #181, suite #170) : relancer ce
# script sur un projet déjà finalisé (ex. pour appliquer un correctif) ne doit PAS
# remettre TOPIC_NTFY au placeholder. Si le config existe déjà ET contient une
# valeur réelle (≠ placeholder), on la réutilise dans le contenu régénéré ;
# sinon (fichier absent ou encore au placeholder) → comportement inchangé.
$Placeholder     = '###TOPIC_NTFY_A_DEFINIR###'
$TopicNtfy       = $Placeholder
$topicPreserve   = $false
if (Test-Path $CheminConf) {
    $valeurExistante = Lire-ValeurFichier $CheminConf 'TOPIC_NTFY'
    if ($valeurExistante) {
        $valeur = $valeurExistante.Trim()
        if ($valeur -and $valeur -ne $Placeholder) {
            $TopicNtfy     = $valeur
            $topicPreserve = $true
        }
    }
}

$contenuConf = @"
# configs/$NomConf — Config du watcher CCW pour le projet $NomProjet.
# Généré par ajouter_projet_ccw.ps1 (multi-projets, issue #170). Format : CLE = valeur.

# ─── Requis ───────────────────────────────────────────────────────────────────
NOM         = $nomMin-ccw
DEPOT       = $Depot
LABEL       = for-windows
# REP_TRAVAIL : clone dédié du projet dans C:\CCW\$NomProjet.
REP_TRAVAIL = $RepDepot

# ─── ntfy ─────────────────────────────────────────────────────────────────────
# PLACEHOLDER à renseigner LOCALEMENT (comme pour ccw.conf / bridge_agent).
# Ne PAS committer la valeur réelle du topic.
TOPIC_NTFY  = $TopicNtfy

# ─── Périmètre CCW (dossiers autorisés) ───────────────────────────────────────
PERIMETRE   = $RepDepot

# ─── Optionnels (défaut si commenté) ──────────────────────────────────────────
# INTERVALLE     = 10
# MAX_ESSAIS     = 3
# TIMEOUT_CLAUDE = 600
"@

Info "Écriture de $CheminConf…"
# UTF-8 sans BOM pour rester lisible par le parseur .conf de watcher.py.
[System.IO.File]::WriteAllText($CheminConf, $contenuConf, (New-Object System.Text.UTF8Encoding($false)))
if ($topicPreserve) {
    Info "TOPIC_NTFY existant préservé (relance sur projet déjà finalisé) — non remis au placeholder."
}

# ---------------------------------------------------------------------------
# 3. Service Windows dédié (NSSM) : CCW-Watcher-<NomProjet>.
#    Mêmes réglages que CCW-Watcher (provisionner.ps1) : démarrage au boot sans
#    session, redémarrage automatique sur échec, logs dédiés.
#
#    IMPORTANT — séparation outillage / projet (issue #179, suite #170) :
#    watcher.py est l'OUTILLAGE PARTAGÉ du bridge, présent UNIQUEMENT dans le
#    clone Bridge_Agent (C:\CCW\Bridge_Agent). Le clone du projet
#    (C:\CCW\<NomProjet>) ne contient QUE le code du projet + son config + ses
#    logs, PAS watcher.py. On doit donc référencer watcher.py par un CHEMIN
#    ABSOLU vers Bridge_Agent, et non relativement à AppDirectory : ce dernier
#    reste le dossier du projet ($RepDepot) pour que REP_TRAVAIL/PERIMETRE et le
#    chemin relatif du config (configs\<nom>-ccw.conf) se résolvent bien AU
#    PROJET. Seul watcher.py est absolu.
# ---------------------------------------------------------------------------
if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    throw 'nssm introuvable dans le PATH — provisionner.ps1 doit avoir été exécuté au préalable.'
}

$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) { $pythonExe = 'python' }

# Chemin ABSOLU vers le watcher partagé, dans le clone Bridge_Agent (jamais dans
# le clone du projet). Bridge_Agent doit avoir été provisionné au préalable
# (provisionner.ps1) — sans lui, aucun watcher à lancer.
$CheminWatcher = Join-Path $RepCCW 'Bridge_Agent\watcher.py'
if (-not (Test-Path $CheminWatcher)) {
    throw "watcher.py introuvable : « $CheminWatcher ». Le clone Bridge_Agent " +
          "(l'outillage partagé du bridge) doit avoir été mis en place au " +
          "préalable via provisionner.ps1. watcher.py n'existe PAS dans le " +
          "clone du projet ($RepDepot) — il est propre à Bridge_Agent."
}

$RepLogs = Join-Path $RepDepot 'logs'
if (-not (Test-Path $RepLogs)) { New-Item -ItemType Directory -Path $RepLogs | Out-Null }
$LogService = Join-Path $RepLogs $NomLog

# Idempotence : si le service existe déjà, l'arrêter puis le supprimer avant de
# le recréer (même pattern que provisionner.ps1 — script relançable sans erreur).
# Préservation des tokens déjà posés (issue #181, suite #170) : nssm remove efface
# AppEnvironmentExtra (les tokens posés via l'onglet CCW / finaliser_projet_ccw.ps1).
# Avant de supprimer un service existant, on lit sa valeur actuelle pour la
# réappliquer après recréation. Première création → rien à préserver.
$envExtra        = @()
$tokensPreserve  = $false
$svcExistant = Get-Service -Name $NomService -ErrorAction SilentlyContinue
if ($svcExistant) {
    Info "Service « $NomService » déjà présent — arrêt puis suppression avant recréation…"
    # Lire AppEnvironmentExtra AVANT le remove. nssm get renvoie chaque variable
    # KEY=valeur sur sa propre ligne ; on ne garde que les lignes non vides.
    $envExtra = @(nssm get $NomService AppEnvironmentExtra 2>$null |
                  ForEach-Object { $_.Trim() } |
                  Where-Object { $_ -ne '' })
    if ($envExtra.Count -gt 0) {
        $tokensPreserve = $true
        Info "Tokens existants détectés (AppEnvironmentExtra) — seront réappliqués après recréation."
    }
    nssm stop   $NomService | Out-Null
    nssm remove $NomService confirm | Out-Null
}

Info "Enregistrement du service Windows « $NomService » (NSSM)…"

nssm install $NomService $pythonExe "`"$CheminWatcher`" --config configs\$NomConf"
nssm set $NomService AppDirectory     $RepDepot
nssm set $NomService Start            SERVICE_AUTO_START
nssm set $NomService AppExit Default  Restart
nssm set $NomService AppRestartDelay  5000
# Rediriger stdout/stderr du service vers un fichier de log dédié.
nssm set $NomService AppStdout        $LogService
nssm set $NomService AppStderr        $LogService

# Réappliquer les tokens préservés (AppEnvironmentExtra) lus avant le remove, pour
# que la relance n'efface pas les tokens déjà posés (issue #181).
#
# Réconciliation issue #658 / #659 (contradiction avec l'ancien fix #558) : le fix
# #558 (chaîne unique jointe par `n, ci-dessous jusqu'à #659) avait été appliqué
# par SEULE lecture du code, jamais reproduit sur nssm réel (cf. clôture #558 :
# l'étape « reproduire le bug » de la tâche n'a pas été faite) — et n'a jamais été
# testé avec une ligne PATH (qui contient des espaces, ex. « Program Files »),
# absente d'AppEnvironmentExtra à l'époque. #658 a lui constaté, sur ce PC fixe et
# cette version de nssm (2.24), qu'une chaîne unique jointe par `n ne pose PAS de
# ligne PATH effective, alors que des arguments SÉPARÉS (un par ligne) fonctionnent
# — y compris pour cette valeur à espaces, donc a fortiori pour des tokens qui n'en
# ont pas. C'est ce pattern (arguments séparés), déjà utilisé par
# mettre_a_jour_tokens_ccw.ps1 (post-#658), qui est retenu ici comme SEULE méthode
# dans tout le dépôt (voir aussi creer_projet_ccw_complet.ps1, aligné pareil).
#
# $envExtra peut contenir 0 à 3 lignes selon l'historique du service (PATH n'existe
# que depuis #658) : on retrouve PATH / GH_TOKEN / CLAUDE_CODE_OAUTH_TOKEN par clé
# plutôt que par position, puis on les repasse à nssm comme autant d'arguments
# distincts (pas de tableau splatté @-variable : nombre d'arguments fixé
# explicitement pour rester sans ambiguïté).
if ($tokensPreserve) {
    $parCle = @{}
    foreach ($ligne in $envExtra) {
        $idx = $ligne.IndexOf('=')
        if ($idx -gt 0) { $parCle[$ligne.Substring(0, $idx)] = $ligne }
    }
    $lignesAReappliquer = @('PATH', 'GH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN') |
        Where-Object { $parCle.ContainsKey($_) } |
        ForEach-Object { $parCle[$_] }

    switch ($lignesAReappliquer.Count) {
        1 { nssm set $NomService AppEnvironmentExtra $lignesAReappliquer[0] | Out-Null }
        2 { nssm set $NomService AppEnvironmentExtra $lignesAReappliquer[0] $lignesAReappliquer[1] | Out-Null }
        3 { nssm set $NomService AppEnvironmentExtra $lignesAReappliquer[0] $lignesAReappliquer[1] $lignesAReappliquer[2] | Out-Null }
        default { Avert "Aucune ligne PATH/GH_TOKEN/CLAUDE_CODE_OAUTH_TOKEN reconnue parmi les valeurs préservées — rien réappliqué." }
    }
    if ($lignesAReappliquer.Count -gt 0) {
        Info "Tokens existants réappliqués (AppEnvironmentExtra préservé, $($lignesAReappliquer.Count) ligne(s)) — relance sans perte."
    }
}

# Démarrer immédiatement (le service repartira ensuite seul à chaque boot).
# Il tournera mais restera inactif tant que TOPIC_NTFY et le token ne sont pas
# renseignés — c'est attendu.
nssm start $NomService | Out-Null

# ---------------------------------------------------------------------------
# Fin — rappels des actions MANUELLES restantes (hors périmètre du script).
# ---------------------------------------------------------------------------
Info ''
Info "Projet « $NomProjet » ajouté : clone + config + service « $NomService »."
Info ''
Info 'RESTE UNE SEULE COMMANDE pour finaliser (le service ne travaillera pas avant) :'
Info "     powershell -File provisioning\windows\finaliser_projet_ccw.ps1 -NomProjet $NomProjet"
Info ''
Info 'Elle enchaîne : saisie de TOPIC_NTFY (écrite dans le config), pause pour créer'
Info 'le token GitHub dédié, saisie + pose des deux tokens, redémarrage du service et'
Info 'vérification finale des logs. Rappel des réglages du token dédié à créer :'
Info "  • Repository access → $Depot UNIQUEMENT"
Info '  • Permissions : Issues = Read and write, Metadata = Read-only'
Info '  • Expiration : LA MÊME DATE que le token Bridge_Agent (≈ 2026-10-17,'
Info "    aligné sur l'éval Windows) — ne pas laisser dériver (cf. §16)."
Info ''
Info "Vérif : nssm status $NomService  /  Get-Service $NomService"
