## #677 — doc(ccw): section « Repérer et nettoyer les worktrees orphelins » dans REINSTALLATION_CCW.md

Suite à #669 (lecture seule, avait produit le texte prêt à coller sans
l'appliquer) : ajout de l'étape `### 9.` dans
`provisioning/windows/REINSTALLATION_CCW.md`, juste après l'étape 8 et
avant le `---` séparant la procédure Windows du prérequis Linux
`cifs-utils`. Reprend le texte proposé par #669 tel quel (repérage via
`git worktree list`, nettoyage via `worktree remove --force` +
`worktree prune` + `branch -d`/`-D`, avertissement sur la perte de
données non commitées/mergées, renvoi vers `WORKTREES.md`).

Précision ajoutée par rapport au texte de #669 (demandée explicitement
dans #677) : un encadré `> ⚠️` en tête de la section indique qu'elle
concerne surtout les clones qui **survivent** à la réinstallation (ex.
le `REP_TRAVAIL` d'un projet dédié) — si le clone est entièrement refait
par `provisionner.ps1` (`C:\CCW\Bridge_Agent`, disque effacé à l'étape
1), `.git/worktrees` repart de zéro avec le nouveau clone et il n'y a
aucun orphelin local à nettoyer de ce côté.
