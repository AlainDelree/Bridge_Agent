## #670 — fix(provisioning): REP_TRAVAIL dérivé de $RepDepot au lieu de C:\CCW_Share (suite #668)

`provisioning/windows/provisionner.ps1` : `$RepTravail` était figé à
`"C:\CCW_Share"` (héritage de l'ancien modèle CCW unifié, issue #231,
abandonné), déconnecté de `$RepDepot` (`C:\CCW\Bridge_Agent`, déjà utilisé
pour cloner le dépôt). Conséquence : `ccw.conf` était généré avec un
`REP_TRAVAIL`/`PERIMETRE` erroné à chaque provisioning complet (constaté et
corrigé à la main le 27/09/2026, cf. #668).

`$RepTravail = "C:\CCW_Share"` devient `$RepTravail = $RepDepot` — cohérent
avec le modèle multi-projets actif et `Get-CheminsProjetCcw`
(`ccw-commun.psm1`). `REP_TRAVAIL` et `PERIMETRE` dans `ccw.conf` en
héritent automatiquement (tous deux dérivés de `$RepTravail`). Commentaires
adjacents mis à jour en conséquence.

Aucun autre usage de `$RepTravail` ni de `C:\CCW_Share` en tant que
répertoire de travail n'existe dans le script — les autres occurrences de
`C:\CCW_Share` (`$CacheDir`/`$cacheDir`, lignes 129/327/417) concernent le
cache de téléchargement, intentionnellement distinct et hors périmètre de
cette correction (confirmé par le diagnostic #668).

Sans effet sur le `ccw.conf` déjà en place (corrigé à la main) — ce
correctif protège uniquement la prochaine réinstallation Windows complète.

Vérification par relecture du code uniquement : `pwsh` n'est pas disponible
dans ce worktree Linux, donc `.\provisionner.ps1 -DryRun` n'a pas pu être
exécuté ici (script destiné au PC Windows CCW). La substitution
`$RepTravail = $RepDepot` est une réutilisation directe d'une variable déjà
initialisée (ligne 128) et éprouvée plus haut dans le script (clonage,
AppDirectory du service) — pas de risque de syntaxe PowerShell introduit.
