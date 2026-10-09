#!/usr/bin/env python3
"""Test de non-régression — issue #740 : `app.interruption._lister_worktrees_
actifs` ne doit plus dépendre du répertoire PARENT de REP_TRAVAIL pour
trouver les worktrees actifs d'un projet.

Avant cette issue, cette fonction scannait `cfg.rep_travail.parent` par nom
de dossier (`<projet>-issue<N>`) — hypothèse valide tant que TOUS les
worktrees étaient créés en répertoire frère du projet (issue #337). Depuis
#740, les nouveaux worktrees CCL (Linux) sont créés dans un dossier dédié
(~/worktrees par défaut), pas forcément frère du projet : la fonction
interroge désormais `git worktree list` (via
`watcher._lister_worktrees_secondaires`), exact quel que soit l'emplacement.

Vérifie :
- Un worktree créé AILLEURS que le répertoire frère du projet (simule le
  nouveau dossier dédié) est quand même trouvé.
- Un worktree créé en répertoire frère du projet (ancien emplacement,
  worktree hérité, ou comportement CCW inchangé) est toujours trouvé.
- Un dossier du même nom, mais qui n'est PAS un worktree enregistré par git
  (simple dossier), n'est jamais retourné.
- Le filtre par suffixe numérique (`<projet>-issueN`) est conservé : un nom
  avec suffixe non numérique (`-bis`/`-ter`) n'est pas retourné — même
  comportement qu'avant cette issue (aucune régression volontaire sur ce
  point, hors du périmètre de #740).

Exécution :  python3 tests/test_lister_worktrees_actifs_740.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import app.interruption as interruption  # noqa: E402


def _init_depot_git(rep: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "master", str(rep)], check=True)
    (rep / "fichier.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-q", "-m", "initial"], cwd=rep, check=True, capture_output=True)


def _ajouter_worktree(rep_travail: Path, chemin: Path, branche: str) -> None:
    res = subprocess.run(
        ["git", "-C", str(rep_travail), "worktree", "add", str(chemin), "-b", branche],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr


def scenario_worktree_dossier_dedie_trouve():
    """Un worktree créé AILLEURS que le répertoire frère du projet (simule
    le nouveau dossier dédié ~/worktrees, issue #740) est trouvé — la
    recherche ne dépend plus du répertoire parent de REP_TRAVAIL."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        dossier_dedie = tmp_path / "ailleurs" / "worktrees_dedies"
        dossier_dedie.mkdir(parents=True)
        chemin_worktree = dossier_dedie / "testproj740-issue1"
        _ajouter_worktree(rep_travail, chemin_worktree, "worktree-issue-1")

        cfg = types.SimpleNamespace(nom="testproj740", rep_travail=rep_travail)
        trouves = interruption._lister_worktrees_actifs(cfg)
        assert [p.resolve() for p in trouves] == [chemin_worktree.resolve()], trouves
    return {"dossier_dedie_trouve_ok": True}


def scenario_worktree_ancien_emplacement_toujours_trouve():
    """Un worktree créé en répertoire FRÈRE du projet (ancien emplacement
    d'avant #740, ou comportement CCW inchangé) est toujours trouvé."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        chemin_worktree = tmp_path / "testproj740b-issue2"
        _ajouter_worktree(rep_travail, chemin_worktree, "worktree-issue-2")

        cfg = types.SimpleNamespace(nom="testproj740b", rep_travail=rep_travail)
        trouves = interruption._lister_worktrees_actifs(cfg)
        assert [p.resolve() for p in trouves] == [chemin_worktree.resolve()], trouves
    return {"ancien_emplacement_trouve_ok": True}


def scenario_simple_dossier_non_worktree_ignore():
    """Un dossier du même nom, mais PAS enregistré comme worktree par git
    (simple dossier), n'est jamais retourné."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        (tmp_path / "testproj740c-issue3").mkdir()

        cfg = types.SimpleNamespace(nom="testproj740c", rep_travail=rep_travail)
        trouves = interruption._lister_worktrees_actifs(cfg)
        assert trouves == [], trouves
    return {"simple_dossier_ignore_ok": True}


def scenario_suffixe_non_numerique_ignore():
    """Un worktree nommé avec un suffixe non numérique (`-bis`) n'est pas
    retourné — même filtre qu'avant cette issue (comportement préservé,
    hors périmètre de #740)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        chemin_worktree = tmp_path / "testproj740d-issue4-bis"
        _ajouter_worktree(rep_travail, chemin_worktree, "worktree-issue-4-bis")

        cfg = types.SimpleNamespace(nom="testproj740d", rep_travail=rep_travail)
        trouves = interruption._lister_worktrees_actifs(cfg)
        assert trouves == [], trouves
    return {"suffixe_non_numerique_ignore_ok": True}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur bash/git POSIX, non applicable sous Windows)")
        return 0

    tests = [
        ("issue #740 — worktree créé dans un dossier dédié (ailleurs que le parent) : trouvé",
         scenario_worktree_dossier_dedie_trouve),
        ("worktree créé en répertoire frère (ancien emplacement / CCW) : toujours trouvé",
         scenario_worktree_ancien_emplacement_toujours_trouve),
        ("simple dossier non enregistré comme worktree : jamais retourné",
         scenario_simple_dossier_non_worktree_ignore),
        ("suffixe non numérique (-bis) : ignoré, comportement préservé",
         scenario_suffixe_non_numerique_ignore),
    ]

    echecs = 0
    for nom, fn in tests:
        try:
            rap = fn()
            print(f"  ✓ {nom}  ({rap})")
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}\n      {e}")
        except Exception as e:  # noqa: BLE001
            echecs += 1
            print(f"  ✗ {nom} — erreur inattendue : {type(e).__name__}: {e}")

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
