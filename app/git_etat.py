"""Vue « Git » (issue #569) : worktrees actifs et commits locaux non poussés,
par projet — lecture seule, aucune écriture git.

Première brique d'une évolution plus large de Relecture_Bridge (résumé de
diff, actions de merge) ; sert de fondation, sans dépendre des autres
briques. Remplace la nécessité de lancer `git worktree list` et
`git log --oneline @{u}..HEAD` à la main, projet par projet — dans le même
esprit que l'alerte de log de `watcher.py::verifier_accumulation_worktrees`
(issue #432), mais visible depuis l'interface plutôt que dans le seul log
brut du watcher.
"""

import subprocess
import sys
from pathlib import Path

from flask import jsonify

# app.projets ajoute la racine du projet au sys.path lors de son import (pour
# « from watcher import ») ; on l'importe donc avant watcher.
from app.projets import lister_projets
from app.auth import login_requis  # noqa: F401 (exporté pour l'enregistrement des routes)
from watcher import _lister_worktrees_secondaires, _est_depot_git


def commits_non_pousses(rep_travail: Path) -> list[str]:
    """Liste (résumé oneline, du plus récent au plus ancien) les commits de
    HEAD absents de la branche amont (`@{u}`) — équivalent de
    `git log --oneline origin/master..HEAD`, mais basé sur l'amont réellement
    configuré plutôt qu'un nom de branche figé (tous les projets ne
    s'appellent pas forcément « master »).

    Best-effort : dossier absent, pas un dépôt git, aucune amont configurée,
    ou toute erreur d'exécution git → liste vide, jamais d'exception
    propagée."""
    if not rep_travail.is_dir() or not _est_depot_git(rep_travail):
        return []
    try:
        res = subprocess.run(
            ["git", "-C", str(rep_travail), "log", "--oneline", "@{u}..HEAD"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if res.returncode != 0:
        return []  # pas d'amont configurée, ou autre erreur — silence, best-effort
    return [ligne for ligne in res.stdout.splitlines() if ligne.strip()]


def etat_git():
    """Retourne, pour chaque projet actif (`lister_projets()`) : ses
    worktrees secondaires actifs (hors REP_TRAVAIL) et ses commits locaux non
    poussés. Lecture seule (aucune commande git d'écriture)."""
    resultat = []
    for cfg in lister_projets():
        worktrees = _lister_worktrees_secondaires(cfg.rep_travail)
        commits   = commits_non_pousses(cfg.rep_travail)
        resultat.append({
            "nom":       cfg.nom,
            "depot":     cfg.depot,
            "worktrees": worktrees,
            "commits":   commits,
        })
    return jsonify(projets=resultat)
