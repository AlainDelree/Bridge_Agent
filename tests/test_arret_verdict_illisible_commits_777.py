#!/usr/bin/env python3
"""Test de non-régression — issue #777 (incident chesscoach #123, point 1) :
l'issue #123 de chesscoach a été abandonnée après TROIS tentatives
identiques alors que le worktree contenait déjà deux commits (sauvegarde +
correctif) — la preuve qu'un travail avait eu lieu était disponible sans
aucune analyse de texte, et le système a quand même tout recommencé deux
fois, faute de vérifier les commits avant de relancer une tentative dont le
verdict de clôture était illisible.

Vérifie :
1. `_commits_au_dela_sauvegarde` (fonction pure, sur dépôts git jetables) :
   liste les commits au-delà de la sauvegarde (repérée par POSITION, comme
   `_avertissement_succes_sans_commit`), [] si rien au-delà, [] si
   `tete_avant_traitement` est absent ou le dépôt inaccessible.
2. Bout en bout (`traiter_issue`, MODE_ECRITURE, worktree dédié réel) :
   une tentative dont le rapport ne contient AUCUNE ligne de verdict (#581),
   mais dont le worktree contient déjà un commit de sauvegarde ET un commit
   de correctif, arrête le traitement IMMÉDIATEMENT (une seule tentative
   consommée sur les 3 prévues), pose `needs-human`, et le commentaire de
   clôture liste le(s) commit(s) trouvé(s) au-delà de la sauvegarde.
3. Contrôle : la même situation (verdict illisible) mais SANS aucun commit
   au-delà de la sauvegarde (aucun travail réel détectable) ne déclenche PAS
   ce garde-fou — les 3 tentatives prévues sont consommées normalement,
   comme avant cette issue.

`gh` et `claude` sont remplacés par de faux exécutables (même technique que
tests/test_worktree_parallelisation_337.py) : aucun appel réseau réel.
`commenter_issue`/`ajouter_label`/`notifier` sont patchés directement en
Python pour capturer le compte-rendu de clôture (même technique que
tests/test_premier_marqueur_et_arret_rapide_763.py).

Exécution :  python3 tests/test_arret_verdict_illisible_commits_777.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import logging
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402
from garde_fou_faux_executables import (  # noqa: E402
    verifier_dossier_sous_tmp,
    verifier_faux_executables_actifs,
)


def _init_depot_git(rep: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "master", str(rep)], check=True)
    (rep / "fichier.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-q", "-m", "initial"], cwd=rep, check=True, capture_output=True)


def _commit(rep: Path, message: str, allow_empty: bool = False) -> None:
    cmd = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", message]
    if allow_empty:
        cmd.append("--allow-empty")
    else:
        subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(cmd, cwd=rep, check=True, capture_output=True)


# ─── Scénario 1 : _commits_au_dela_sauvegarde, fonction pure ───────────────────

def scenario_sans_aucun_commit_au_dela_liste_vide():
    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp) / "projet"
        rep.mkdir()
        _init_depot_git(rep)
        tete = watcher._tete_git(rep)
        _commit(rep, "avant-test777", allow_empty=True)

        assert watcher._commits_au_dela_sauvegarde(rep, tete) == []
    return {"vide_ok": True}


def scenario_avec_commit_fix_liste_non_vide():
    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp) / "projet"
        rep.mkdir()
        _init_depot_git(rep)
        tete = watcher._tete_git(rep)
        _commit(rep, "avant-test777", allow_empty=True)
        (rep / "fichier.txt").write_text("modifie\n", encoding="utf-8")
        _commit(rep, "fix-test777")

        commits = watcher._commits_au_dela_sauvegarde(rep, tete)
        assert len(commits) == 1, f"un seul commit (le fix) attendu au-delà de la sauvegarde : {commits}"
        assert "fix-test777" in commits[0]
    return {"non_vide_ok": True}


def scenario_tete_absente_ou_depot_inaccessible_liste_vide():
    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp) / "projet"
        rep.mkdir()
        _init_depot_git(rep)
        assert watcher._commits_au_dela_sauvegarde(rep, None) == []

        chemin_inexistant = Path(tempfile.gettempdir()) / "ne-devrait-pas-exister-777"
        assert watcher._commits_au_dela_sauvegarde(chemin_inexistant, "0" * 40) == []
    return {"best_effort_ok": True}


# ─── Scénario 2/3 : bout en bout via traiter_issue ─────────────────────────────

FAUX_GH = "#!/bin/bash\nexit 0\n"

# Faux `notify-send` — issue #778, même technique que
# tests/test_worktree_parallelisation_337.py (issue #611) : sans ce faux
# exécutable, un repli de création de worktree (toutes tentatives prises,
# cf. DOSSIER_WORKTREES_DEDIE isolé plus bas) appellerait le VRAI
# `notify-send` et afficherait une bulle de bureau réelle.
FAUX_NOTIFY_SEND = "#!/bin/bash\nexit 0\n"

FAUX_CLAUDE = """#!/bin/bash
# Faux `claude` — issue #777. $# -ge 2 distingue le VRAI appel de la sonde
# pre-flight (claude --print seul), qui ne doit produire aucun effet de bord.
# La passe diagnostique (`diagnostiquer_echec`, mode lecture seule, abandon
# après épuisement des tentatives) est reconnue séparément via le texte de
# son prompt dédié — ne doit ni committer, ni compter comme une tentative.
for arg in "$@"; do
    if [[ "$arg" == *"diagnostic RAPIDE"* ]]; then
        echo "RAS"
        exit 0
    fi
done
if [ "$#" -ge 2 ]; then
    echo x >> "$TEST_777_DIR/compteur_appels"
    if [ -f "$TEST_777_DIR/faire_commits" ]; then
        git -c user.email=t@t -c user.name=t commit -q --allow-empty -m "avant-777-simulation"
        echo "contenu" > fix_777.txt
        git add -A
        git -c user.email=t@t -c user.name=t commit -q -m "fix-777-simulation"
    fi
    echo "Tâche terminée, mais sans la moindre ligne de verdict de clôture."
    echo "(simulation d'un rapport illisible, issue #581/#777)."
fi
exit 0
"""


def _preparer_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for nom, contenu in (("claude", FAUX_CLAUDE), ("gh", FAUX_GH),
                         ("notify-send", FAUX_NOTIFY_SEND)):
        chemin = bin_dir / nom
        chemin.write_text(contenu, encoding="utf-8")
        chemin.chmod(chemin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _lancer_scenario(tmp_path: Path, rep_travail: Path, bin_dir: Path,
                      nom_cfg: str, numero: int, titre: str, max_essais: int):
    """Isolation complète (PATH, état global watcher.py, CFG, commenter_issue/
    ajouter_label/notifier capturés) — même esprit que
    tests/test_premier_marqueur_et_arret_rapide_763.py."""
    ancien_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
    os.environ["TEST_777_DIR"] = str(tmp_path)
    try:
        verifier_faux_executables_actifs(bin_dir, ["claude", "gh", "notify-send"])
    except Exception:
        os.environ["PATH"] = ancien_path
        raise

    ancien_dossier_verrous        = watcher.DOSSIER_VERROUS
    ancien_dossier_logs           = watcher.DOSSIER_LOGS
    ancien_fichier_historique     = watcher.FICHIER_HISTORIQUE
    ancien_fichier_etat_timeout   = watcher.FICHIER_ETAT_TIMEOUT
    ancien_fichier_etat_ambiance  = watcher.FICHIER_ETAT_AMBIANCE
    ancien_dossier_worktrees_dedie = watcher.DOSSIER_WORKTREES_DEDIE
    watcher.DOSSIER_VERROUS = tmp_path / "verrous"
    watcher.DOSSIER_LOGS = tmp_path / "logs"
    watcher.FICHIER_HISTORIQUE = watcher.DOSSIER_LOGS / "historique_durees.json"
    watcher.FICHIER_ETAT_TIMEOUT = watcher.DOSSIER_LOGS / "etat_timeout.json"
    watcher.FICHIER_ETAT_AMBIANCE = watcher.DOSSIER_LOGS / "etat_ambiance.json"
    # Issue #778 : sans cette isolation, _chemin_worktree (appelée par
    # traiter_issue pour toute issue mode_write, y compris avec
    # max_write_parallele=1) créerait le worktree dans le VRAI ~/worktrees
    # de la machine qui exécute les tests — jamais nettoyé, et source d'un
    # repli notify-send RÉEL si le chemin est déjà pris (cf. module docstring
    # ci-dessus et tests/garde_fou_faux_executables.py).
    watcher.DOSSIER_WORKTREES_DEDIE = tmp_path / "worktrees_dedies"
    verifier_dossier_sous_tmp(watcher.DOSSIER_WORKTREES_DEDIE, "DOSSIER_WORKTREES_DEDIE")

    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(
        nom=nom_cfg, depot="AlainDelree/depot-inexistant-test777",
        rep_travail=rep_travail, topic_ntfy=nom_cfg,
        max_essais=max_essais, timeout_claude=30, max_write_parallele=1,
    )
    watcher.issues_en_cours.discard(numero)
    # `_issues_write_bloquees_needs_human` (issue #576) est un état GLOBAL,
    # pas remis à zéro automatiquement entre deux scénarios de ce fichier —
    # sans ce nettoyage, une issue needs-human d'un scénario précédent
    # occuperait à tort la place MAX_WRITE_PARALLELE=1 du scénario suivant.
    ancien_bloquees = set(watcher._issues_write_bloquees_needs_human)
    watcher._issues_write_bloquees_needs_human.clear()

    commentaires, labels_poses, notifs = [], [], []
    ancien_commenter   = watcher.commenter_issue
    ancien_ajouter_label = watcher.ajouter_label
    ancien_notifier    = watcher.notifier
    ancien_notifier_fin_sse = watcher.notifier_fin_sse

    watcher.commenter_issue    = lambda num, msg: commentaires.append(msg)
    watcher.ajouter_label      = lambda num, lab: labels_poses.append(lab)
    watcher.notifier           = lambda *a, **k: notifs.append((a, k))
    watcher.notifier_fin_sse   = lambda *a, **k: None

    try:
        issue = {
            "number": numero, "title": titre,
            "body": "| PRIORITE | normale |\n| TIMEOUT | 60s |\n",
            "labels": [{"name": "mode_write"}],
        }
        watcher.traiter_issue(issue, dry_run=False)
    finally:
        watcher.CFG = ancien_cfg
        watcher.commenter_issue = ancien_commenter
        watcher.ajouter_label = ancien_ajouter_label
        watcher.notifier = ancien_notifier
        watcher.notifier_fin_sse = ancien_notifier_fin_sse
        if ancien_path:
            os.environ["PATH"] = ancien_path
        else:
            os.environ.pop("PATH", None)
        os.environ.pop("TEST_777_DIR", None)
        watcher.DOSSIER_VERROUS = ancien_dossier_verrous
        watcher.DOSSIER_LOGS = ancien_dossier_logs
        watcher.FICHIER_HISTORIQUE = ancien_fichier_historique
        watcher.FICHIER_ETAT_TIMEOUT = ancien_fichier_etat_timeout
        watcher.FICHIER_ETAT_AMBIANCE = ancien_fichier_etat_ambiance
        watcher.DOSSIER_WORKTREES_DEDIE = ancien_dossier_worktrees_dedie
        watcher.issues_en_cours.discard(numero)
        watcher._issues_write_bloquees_needs_human.clear()
        watcher._issues_write_bloquees_needs_human.update(ancien_bloquees)

    return commentaires, labels_poses


def scenario_verdict_illisible_avec_commits_arrete_immediatement():
    """Reproduction directe de l'incident chesscoach #123 : rapport sans
    ligne de verdict, mais worktree contenant déjà sauvegarde + correctif
    → arrêt dès la PREMIÈRE tentative, needs-human, commit(s) listé(s)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)
        (tmp_path / "faire_commits").touch()

        bin_dir = _preparer_bin(tmp_path)
        commentaires, labels_poses = _lancer_scenario(
            tmp_path, rep_travail, bin_dir, "test777a", numero=97771,
            titre="Test #777 — verdict illisible avec commits", max_essais=3)

        compteur = tmp_path / "compteur_appels"
        nb_appels = sum(1 for _ in compteur.read_text(encoding="utf-8").splitlines()) if compteur.exists() else 0
        assert nb_appels == 1, (
            f"une seule tentative (sur 3 prévues) aurait dû être consommée — "
            f"{nb_appels} appel(s) constaté(s) (incident chesscoach #123 : "
            f"3 tentatives identiques lancées en pure perte)")
        assert "needs-human" in labels_poses, f"label needs-human attendu, labels posés : {labels_poses}"
        assert commentaires, "un commentaire de clôture était attendu"
        message = commentaires[-1]
        assert "commit" in message.lower(), f"le message devrait lister le(s) commit(s) trouvé(s) : {message}"
        assert "fix-777-simulation" in message, f"le commit de correctif devrait être listé : {message}"
    return {"tentatives_consommees": nb_appels, "labels": labels_poses}


def scenario_verdict_illisible_sans_commit_consomme_toutes_les_tentatives():
    """Contrôle : verdict illisible mais AUCUN commit au-delà de la
    sauvegarde (aucun travail réel détectable) — ce nouveau garde-fou ne
    doit PAS se déclencher, comportement inchangé (toutes les tentatives
    consommées, abandon normal après #124)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)
        # Pas de fichier "faire_commits" : le faux claude ne committe rien.

        bin_dir = _preparer_bin(tmp_path)
        commentaires, labels_poses = _lancer_scenario(
            tmp_path, rep_travail, bin_dir, "test777b", numero=97772,
            titre="Test #777 — verdict illisible sans commit (contrôle)", max_essais=3)

        compteur = tmp_path / "compteur_appels"
        nb_appels = sum(1 for _ in compteur.read_text(encoding="utf-8").splitlines()) if compteur.exists() else 0
        assert nb_appels == 3, (
            f"les 3 tentatives prévues auraient dû être consommées (aucun "
            f"commit détecté, pas de travail probable) — {nb_appels} appel(s) constaté(s)")
        assert "needs-human" in labels_poses
    return {"tentatives_consommees": nb_appels}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur bash/git POSIX, non applicable sous Windows)")
        return 0

    tests = [
        ("_commits_au_dela_sauvegarde : sans commit après la sauvegarde → []",
         scenario_sans_aucun_commit_au_dela_liste_vide),
        ("_commits_au_dela_sauvegarde : commit de fix présent → liste non vide",
         scenario_avec_commit_fix_liste_non_vide),
        ("_commits_au_dela_sauvegarde : tête absente / dépôt inaccessible → []",
         scenario_tete_absente_ou_depot_inaccessible_liste_vide),
        ("verdict illisible + commits (backup+fix) → arrêt immédiat, 1 tentative, needs-human",
         scenario_verdict_illisible_avec_commits_arrete_immediatement),
        ("contrôle : verdict illisible SANS commit → 3 tentatives consommées normalement",
         scenario_verdict_illisible_sans_commit_consomme_toutes_les_tentatives),
    ]

    logging.getLogger().addHandler(logging.NullHandler())
    watcher.log.setLevel(logging.CRITICAL)

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
