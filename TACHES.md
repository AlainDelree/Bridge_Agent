# Backlog Bridge_Agent

Idées et pistes non prioritaires, à réaliser éventuellement plus tard.
Alain peut modifier ce fichier directement, sans passer par une issue.

---

## Worktrees en production — points de surveillance

**Contexte** : après correction de #340, deux limites connues restent
sur le mécanisme de parallélisation des issues mode_write via git
worktrees (cf. `WORKTREES.md`) :

- Pas d'alerte sur l'accumulation de worktrees (nettoyage manuel requis).
- `issues_en_cours` sans verrou explicite inter-process.

## Projet dédié à la communication CCL ↔ CCW

**Contexte** : aujourd'hui les issues Windows passent par le projet
`bridge_agent` avec le label `for-windows`, ce qui est contre-intuitif —
bridge_agent est le projet de l'infrastructure elle-même, pas un relais
CCL↔CCW. Avec le futur setup (ThinkPad Linux + fixe Windows en parallèle),
la communication inter-agents va prendre de l'ampleur et mérite son propre
espace.

**Idée** : créer un projet dédié (ex. `ccw_relay` ou `bridge_ccw`) dont
le seul rôle est de porter les issues `for-windows`. Le watcher CCW
surveillerait ce dépôt au lieu de bridge_agent. Les issues CCW auraient
leur propre historique, leur propre CHANGELOG, leur propre CONTEXTE.md —
sans polluer bridge_agent.

**Points à concevoir** : migration des issues CCW existantes ou simple
bascule à partir d'une date, adaptation du provisioning CCW (clone du
nouveau dépôt, config NSSM), labels à recréer sur le nouveau dépôt.

**Statut** : idée en attente, setup physique (fixe Windows) pas encore
en place. À reprendre quand le nouveau hardware sera opérationnel.

## Calibration automatique du TIMEOUT — trois défauts à corriger

**Contexte** : la formule du §19 est
`TIMEOUT_suggéré = max((duree_typique + k × variabilite) × F × backoff, plancher)`
— EWMA par `projet|TYPE|mode`, demi-vie 15 issues, k=4, plancher 30 s,
facteur d'ambiance `F` de demi-vie 4 h. Cette valeur reste purement
INDICATIVE : le TIMEOUT réellement appliqué est celui de l'en-tête de
l'issue (`extraire_timeout`).

**Trois défauts identifiés le 29/07/2026** :
1. `F` n'est jamais alimenté — `_detecter_tag_reseau()` retourne toujours
   `None`, donc `F_reseau`/`F_local` restent à 1.0 et le facteur
   d'ambiance n'influence rien (déjà listé dans les limitations du §19).
2. Même si le tag existait, `maj_calibration_timeout` retombe toujours sur
   `F_local` par défaut sans le lire — c'est un second bug, distinct du
   premier.
3. La clé `projet|TYPE|mode` mélange des populations incompatibles : une
   édition de doc de 250 s et une refonte de `watcher.py` avec tests de
   1800 s finissent dans la même case. La médiane qui en sort n'a pas de
   sens (observé : 2794 s suggérés pour une issue qui en a pris 351).

**Idée** : séparer explicitement le coût de la TÂCHE et l'état de la
MACHINE (réseau, RAM, congestion) — c'est déjà la structure de la formule,
mais les deux moitiés sont mal alimentées. La composition doit rester un
PRODUIT, pas une somme : un agent enchaîne les allers-retours réseau, donc
une latence dégradée étire la durée proportionnellement au travail au lieu
d'ajouter un forfait fixe. Exemple : wifi à +40 % → une doc passe de 250 à
350 s, une refonte de 1800 à 2520 s ; une somme unique surestimerait la
première et sous-estimerait gravement la seconde.

**Deux signaux à capter, faciles et probablement les plus discriminants** :
- le TIMEOUT déclaré dans l'en-tête, comme proxy de complexité — Claude
  Chat estime déjà la difficulté au moment de rédiger ; segmenter la
  calibration là-dessus séparerait mécaniquement les deux populations,
  sans nouvelle donnée à collecter ;
- une mesure de latence réseau au démarrage du traitement, pour alimenter
  enfin `tag_reseau` et corriger du même coup le défaut 2.

**Statut** : diagnostic établi le 29/07/2026, aucune implémentation
lancée. À reprendre à froid — le sujet touche des EWMA et des choix de
modélisation qu'on prendrait mal à la légère.

##Rapport : nouvel outil surveiller_builds.ps1 — surveillance des builds CCW en temps réel

Contexte : besoin exprimé de suivre visuellement l'avancement d'un build Windows en cours (PyInstaller via Claude Code, ou compilation Inno Setup via ISCC.exe) sans devoir ouvrir le Gestionnaire des tâches ni re-scanner le dossier de sortie à la main.

Ce que fait le script : toutes les N secondes (10 par défaut), affiche :

l'état de chaque processus surveillé (présent/absent, PID, CPU cumulé, mémoire, durée d'exécution) ;
la taille totale du dossier de build surveillé, avec le delta depuis le dernier passage et depuis le début de la surveillance.

Paramètres : -Dossier (obligatoire, ex. C:\Temp\ActualiseBuild), -Processus (liste, défaut claude, ISCC, python, pyinstaller), -IntervalleSecondes (défaut 10).

Point à vérifier/ajuster à l'intégration : le nom exact du process sous lequel Claude Code tourne sur la VM CCW n'a pas été confirmé (peut être claude.exe natif ou node.exe si lancé via npm/npx) — à vérifier via Get-Process pendant un build réel avant de figer la valeur par défaut du paramètre -Processus.

Fichier joint : script complet ci-dessous, prêt à committer dans le dépôt AlainDelree/Bridge_Agent, probablement dans le même dossier que les autres scripts PowerShell (ajouter_projet_ccw.ps1, provisionner.ps1, etc.), avec documentation correspondante dans BRIDGE_AGENT_DOC.md.

<#
.SYNOPSIS
    Surveille en continu les processus de build (Claude Code / ISCC) et la
    croissance du dossier de sortie d'un build en cours, sur la VM CCW.

.DESCRIPTION
    Affiche toutes les 10 secondes (paramétrable) :
      - l'état des processus surveillés (présent/absent, CPU, mémoire, durée)
      - la taille totale du dossier de build surveillé, et sa croissance
        depuis le dernier passage.

    Pensé pour suivre en temps réel un build CCW (PyInstaller via Claude Code,
    ou compilation Inno Setup via ISCC.exe) sans avoir à ouvrir le Gestionnaire
    des tâches ni à re-scanner le dossier manuellement.

.PARAMETER Dossier
    Chemin du dossier à surveiller (ex. C:\Temp\ActualiseBuild,
    C:\Temp\ScrabbleBuild). Obligatoire.

.PARAMETER Processus
    Noms de processus à surveiller (sans .exe), séparés par une virgule.
    Par défaut : claude, ISCC, python, pyinstaller.
    Ajuster selon ce qu'affiche `Get-Process` pendant un build réel — le nom
    exact du process Claude Code peut varier selon l'installation (souvent
    "node" si lancé via npm/npx plutôt qu'un binaire natif "claude").

.PARAMETER IntervalleSecondes
    Fréquence de rafraîchissement. Par défaut 10.

.EXAMPLE
    .\surveiller_builds.ps1 -Dossier C:\Temp\ActualiseBuild

.EXAMPLE
    .\surveiller_builds.ps1 -Dossier C:\Temp\ScrabbleBuild -Processus claude,ISCC -IntervalleSecondes 5
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Dossier,

    [string[]]$Processus = @("claude", "ISCC", "python", "pyinstaller"),

    [int]$IntervalleSecondes = 10
)

function Obtenir-TailleDossier {
    param([string]$Chemin)
    if (-not (Test-Path $Chemin)) {
        return 0
    }
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

    # État des processus surveillés
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

    # Taille du dossier de build
    $signeDelta = if ($delta -ge 0) { "+" } else { "" }
    Write-Host ("  Dossier : {0}  (delta : {1}{2} depuis dernier passage, {3} depuis le début)" -f `
        (Formater-Taille $tailleActuelle), $signeDelta, (Formater-Taille $delta), (Formater-Taille ($tailleActuelle - $tailleOrigine)))
    Write-Host ""

    $tailleAvant = $tailleActuelle
    Start-Sleep -Seconds $IntervalleSecondes
}
