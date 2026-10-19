#!/usr/bin/env python3
"""Garde-fou partagé — issue #710.

Incident du 03/10/2026 : lancée sur CCW (Windows), `test_projet_ccw_559.py`
plaçait en tête du PATH un faux `gh` écrit en script `#!/bin/bash` rendu
exécutable par `chmod` — inopérant sous Windows, qui a donc résolu et appelé
le VRAI `gh.exe` (authentifié sur le compte d'Alain), créant deux VRAIES
issues sur `AlainDelree/Bridge_Agent`.

Tous les tests qui remplacent `gh`/`git`/`claude`/`powershell` par de faux
exécutables bash doivent, après avoir placé leur dossier de faux en tête du
PATH, appeler `verifier_faux_executables_actifs` avant le moindre appel réel
au code testé : échec FERMÉ, le test s'arrête immédiatement si une seule des
commandes remplacées ne résout pas DANS ce dossier (PATH inhabituel, point de
montage `noexec`, plateforme où le shebang bash est inopérant, etc.) — jamais
une tentative avec le vrai outil.
"""

import shutil
import tempfile
from pathlib import Path


def verifier_faux_executables_actifs(bin_dir, noms):
    """Lève RuntimeError si l'une des commandes de `noms` ne résout pas vers
    un fichier DANS `bin_dir` (déjà placé en tête du PATH par l'appelant) —
    à appeler juste avant d'invoquer le code testé, jamais après."""
    bin_dir = Path(bin_dir).resolve()
    problemes = []
    for nom in noms:
        resolu = shutil.which(nom)
        if resolu is None:
            problemes.append(f"{nom} : introuvable sur le PATH (faux exécutable non résolu)")
            continue
        resolu = Path(resolu).resolve()
        if resolu.parent != bin_dir:
            problemes.append(
                f"{nom} : résolu vers {resolu} (hors de {bin_dir} — le VRAI "
                f"outil serait appelé)"
            )
    if problemes:
        raise RuntimeError(
            "GARDE-FOU #710 — faux exécutable(s) inactif(s), test interrompu "
            "AVANT tout appel pour ne jamais risquer d'atteindre le vrai "
            "outil :\n  " + "\n  ".join(problemes)
        )


def verifier_dossier_sous_tmp(chemin, nom="dossier"):
    """Lève RuntimeError si `chemin` n'est pas situé sous le répertoire
    temporaire système (`tempfile.gettempdir()`) — garde-fou issue #778.

    Incident du 19/10/2026 : les tests de l'issue #777 redirigeaient bien
    `REP_TRAVAIL` vers un dossier jetable, mais pas `DOSSIER_WORKTREES_DEDIE`
    (constante globale de `watcher.py`, par défaut `~/worktrees` — le VRAI
    dossier où vivent les worktrees du système). Deux dossiers de test y ont
    été créés et jamais nettoyés, et un repli sur échec de création a appelé
    `notify-send` pour de vrai (bulle bureau RÉELLE annonçant une issue de
    test fictive).

    À appeler juste après avoir réaffecté `watcher.DOSSIER_WORKTREES_DEDIE`
    (ou toute autre constante de chemin similaire) vers un dossier jetable,
    AVANT tout appel au code testé susceptible d'y créer un worktree —
    échec FERMÉ si ce chemin pointe par erreur vers un emplacement réel."""
    chemin = Path(chemin).resolve()
    tmp = Path(tempfile.gettempdir()).resolve()
    try:
        chemin.relative_to(tmp)
    except ValueError:
        raise RuntimeError(
            f"GARDE-FOU #778 — {nom} ({chemin}) n'est PAS sous le répertoire "
            f"temporaire système ({tmp}) — un test risquerait d'écrire/notifier "
            f"dans un emplacement réel du système."
        )
