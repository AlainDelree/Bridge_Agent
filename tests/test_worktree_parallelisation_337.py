#!/usr/bin/env python3
"""Test de non-régression — issue #337 : parallélisation des issues mode_write
via git worktrees.

Vérifie :
- `_chemin_worktree` / `_branche_worktree` : nommage attendu (répertoire
  FRÈRE de REP_TRAVAIL, préfixé par CFG.nom ; branche `worktree-issue-<N>`).
- `_creer_worktree` : succès (dépôt git réel temporaire) et repli propre
  (retourne None, aucune exception) quand le chemin cible existe déjà ou
  quand la branche existe déjà.
- `_nettoyer_threads_ecriture_termines` / `_threads_ecriture_actifs` : purge
  bien les threads terminés de la liste thread-safe.
- Scénario de bout en bout avec `MAX_WRITE_PARALLELE = 2` et deux issues
  mode_write dispatchées dans le même cycle : la première tourne dans
  REP_TRAVAIL (aucun worktree), la seconde dans un worktree dédié créé à la
  volée — les deux tournent EN PARALLÈLE (verrous distincts par
  chemin_travail, issue #337 point 7), aboutissent toutes deux avec succès,
  et le worktree de la seconde est CONSERVÉ après coup (pas de `git worktree
  remove` ni de suppression de branche automatique).
- Non-régression : `MAX_WRITE_PARALLELE = 1` → `traiter_issue` reste
  strictement synchrone, aucun thread ni worktree créé, comportement
  identique à avant #337.

`gh` et `claude` sont remplacés par de faux exécutables (même technique que
tests/test_lecture_active_327.py) : aucun appel réseau réel. Le faux `claude`
consigne dans quel répertoire (`$PWD`) et pour quel numéro d'issue il a
tourné, et signale si le prompt reçu contenait le bloc d'avertissement
worktree — ce qui permet de vérifier la bonne cible sans dépendre du
contenu réel produit par un agent.

Exécution :  python3 tests/test_worktree_parallelisation_337.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import logging
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402

FAUX_GH = """#!/bin/bash
# Faux `gh` — issue #337. Stateful sur `issue view --json comments` (marqueur
# par NUMÉRO d'issue, cf. $3 = <numero> pour `issue comment`/`issue view`),
# nécessaire pour que commenter_resultat_avec_retry (relecture de
# confirmation, issue #237) et resultat_deja_poste fonctionnent avec DEUX
# issues traitées en parallèle sans se marcher dessus.
if [ "$1" = "issue" ] && [ "$2" = "comment" ]; then
    numero="$3"
    bodyfile=""
    prev=""
    for arg in "$@"; do
        if [ "$prev" = "--body-file" ]; then
            bodyfile="$arg"
        fi
        prev="$arg"
    done
    if [ -n "$bodyfile" ] && grep -q -- '<!-- bridge:resultat -->' "$bodyfile" 2>/dev/null; then
        touch "$TEST_337_DIR/marqueur-$numero"
    fi
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "view" ]; then
    numero="$3"
    if [ -f "$TEST_337_DIR/marqueur-$numero" ]; then
        echo '{"comments":[{"body":"<!-- bridge:resultat -->\\nfake"}]}'
    else
        echo '{"comments":[]}'
    fi
    exit 0
fi
exit 0
"""

FAUX_CLAUDE = """#!/bin/bash
# Faux `claude` — issue #337. $# -ge 2 distingue le VRAI appel
# (claude --print --dangerously-skip-permissions <prompt>) de la sonde
# pre-flight (claude --print seul, voir verifier_preflight_token), qui ne
# doit produire aucun effet de bord.
if [ "$#" -ge 2 ]; then
    prompt="${@: -1}"
    numero=$(echo "$prompt" | grep -oE 'Issue #[0-9]+' | head -1 | grep -oE '[0-9]+')
    echo "$PWD" > "$TEST_337_DIR/pwd-$numero"
    if echo "$prompt" | grep -q 'worktree isolé'; then
        touch "$TEST_337_DIR/worktree_marker-$numero"
        echo "entrée changelog #$numero" > "CHANGELOG-$numero.md"
    fi
    sleep 0.3
    echo "✅ Tâche terminée — worktree test #$numero"
fi
exit 0
"""


def _preparer_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for nom, contenu in (("claude", FAUX_CLAUDE), ("gh", FAUX_GH)):
        chemin = bin_dir / nom
        chemin.write_text(contenu, encoding="utf-8")
        chemin.chmod(chemin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _init_depot_git(rep: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "master", str(rep)], check=True)
    (rep / "fichier.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-q", "-m", "initial"], cwd=rep, check=True, capture_output=True)


def _issue_minimale(numero: int, titre: str, labels: list[str]) -> dict:
    return {
        "number": numero,
        "title": titre,
        "body": "| PRIORITE | normale |\n| TIMEOUT | 30s |\n",
        "labels": [{"name": lab} for lab in labels],
    }


def scenario_chemin_et_branche_worktree():
    """_chemin_worktree / _branche_worktree : nommage attendu."""
    ancien_cfg = watcher.CFG
    try:
        watcher.CFG = watcher.Config(
            nom="testproj", depot="AlainDelree/x",
            rep_travail=Path("/tmp/nexiste_pas/testproj"), topic_ntfy="x",
        )
        chemin = watcher._chemin_worktree(42)
        assert chemin == Path("/tmp/nexiste_pas/testproj-issue42"), chemin
        assert watcher._branche_worktree(42) == "worktree-issue-42"
    finally:
        watcher.CFG = ancien_cfg
    return {}


def scenario_creer_worktree_succes_et_repli():
    """_creer_worktree : succès (dépôt réel), puis repli propre si le chemin
    cible existe déjà, puis repli propre si la BRANCHE existe déjà (chemin
    cible différent, mais nom de branche recyclé)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(
            nom="testproj", depot="AlainDelree/x",
            rep_travail=rep_travail, topic_ntfy="x",
        )
        try:
            chemin = watcher._creer_worktree(101)
            assert chemin is not None, "la création du worktree aurait dû réussir"
            assert chemin.is_dir()
            assert (chemin / "fichier.txt").exists()
            branche = subprocess.run(
                ["git", "-C", str(chemin), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True,
            ).stdout.strip()
            assert branche == "worktree-issue-101", branche

            # Repli 1 : le chemin cible existe déjà (garde-fou #337 point 4).
            resultat_doublon = watcher._creer_worktree(101)
            assert resultat_doublon is None, "un chemin déjà existant aurait dû être refusé"

            # Repli 2 : chemin cible différent, mais la BRANCHE existe déjà.
            chemin_101b = watcher._chemin_worktree(101)
            chemin_101b_bis = chemin_101b.with_name(chemin_101b.name + "-bis")
            res = subprocess.run(
                ["git", "-C", str(rep_travail), "worktree", "add",
                 str(chemin_101b_bis), "worktree-issue-101"],
                capture_output=True, text=True,
            )
            assert res.returncode != 0, "réutiliser une branche déjà attachée à un autre worktree doit échouer"
        finally:
            watcher.CFG = ancien_cfg
        return {"worktree_cree": True, "reprises_refusees": True}


def scenario_purge_threads_termines():
    """_threads_ecriture_actifs purge bien les threads terminés."""
    ancien = list(watcher._threads_ecriture)
    watcher._threads_ecriture.clear()
    try:
        evt = threading.Event()
        t = threading.Thread(target=evt.wait, daemon=True)
        watcher._threads_ecriture.append({"numero": 999001, "worktree": None, "thread": t})
        t.start()
        assert len(watcher._threads_ecriture_actifs()) == 1
        evt.set()
        t.join(timeout=5)
        assert len(watcher._threads_ecriture_actifs()) == 0, "le thread terminé aurait dû être purgé"
    finally:
        watcher._threads_ecriture.clear()
        watcher._threads_ecriture.extend(ancien)
    return {}


def _lancer_deux_issues_paralleles(tmp_path: Path, rep_travail: Path,
                                    numero1: int, numero2: int, projet: str):
    ancien_dossier_verrous = watcher.DOSSIER_VERROUS
    watcher.DOSSIER_VERROUS = tmp_path / "verrous"
    ancien_threads = list(watcher._threads_ecriture)
    watcher._threads_ecriture.clear()
    watcher.CFG = watcher.Config(
        nom=projet, depot="AlainDelree/depot-inexistant-test337",
        rep_travail=rep_travail, topic_ntfy=projet,
        max_essais=1, timeout_claude=15, notifier_local=False,
        max_write_parallele=2,
    )
    watcher.issues_en_cours.discard(numero1)
    watcher.issues_en_cours.discard(numero2)

    try:
        issue1 = _issue_minimale(numero1, f"Test #337 — issue {numero1}", ["mode_write"])
        issue2 = _issue_minimale(numero2, f"Test #337 — issue {numero2}", ["mode_write"])

        watcher.traiter_issue(issue1, dry_run=False)
        # Snapshot immédiat : le thread de la première issue doit déjà être
        # inscrit et vivant (Thread.start() bloque jusqu'à ce que le thread
        # ait réellement démarré) pour que la décision de parallélisation
        # sur la seconde issue voie bien "au moins un thread actif".
        actifs_apres_1 = watcher._threads_ecriture_actifs()
        assert len(actifs_apres_1) == 1, f"la 1ère issue aurait dû être dispatchée en thread : {actifs_apres_1}"
        assert actifs_apres_1[0]["worktree"] is None, "la 1ère issue (premier slot) ne doit PAS utiliser de worktree"

        watcher.traiter_issue(issue2, dry_run=False)
        actifs_apres_2 = watcher._threads_ecriture_actifs()
        assert len(actifs_apres_2) == 2, f"la 2e issue aurait dû obtenir un worktree dédié : {actifs_apres_2}"
        entree_2 = next(t for t in actifs_apres_2 if t["numero"] == numero2)
        assert entree_2["worktree"] is not None, "la 2e issue aurait dû obtenir un worktree"

        # Attendre la fin des deux threads (best-effort, borné).
        for entree in actifs_apres_2:
            entree["thread"].join(timeout=15)
            assert not entree["thread"].is_alive(), f"thread issue #{entree['numero']} toujours actif après 15s"

        return entree_2["worktree"]
    finally:
        watcher.DOSSIER_VERROUS = ancien_dossier_verrous
        watcher._threads_ecriture.clear()
        watcher._threads_ecriture.extend(ancien_threads)


def scenario_parallelisation_deux_issues_mode_write():
    """Bout en bout : MAX_WRITE_PARALLELE=2, deux issues mode_write dans le
    même cycle → première dans REP_TRAVAIL, seconde dans un worktree dédié,
    les deux réussissent et se ferment, le worktree de la seconde est
    CONSERVÉ après coup (aucune suppression automatique, issue #337 point 6)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        test_dir = tmp_path / "etat_test"
        test_dir.mkdir()
        bin_dir = _preparer_bin(tmp_path)

        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        os.environ["TEST_337_DIR"] = str(test_dir)

        numero1, numero2 = 93371, 93372
        try:
            chemin_worktree = _lancer_deux_issues_paralleles(
                tmp_path, rep_travail, numero1, numero2, "test337par")
        finally:
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)
            os.environ.pop("TEST_337_DIR", None)

        # La 1ère issue a tourné dans REP_TRAVAIL, sans bloc worktree dans le prompt.
        pwd_1 = (test_dir / f"pwd-{numero1}").read_text(encoding="utf-8").strip()
        assert Path(pwd_1) == rep_travail.resolve(), f"issue #{numero1} aurait dû tourner dans REP_TRAVAIL : {pwd_1}"
        assert not (test_dir / f"worktree_marker-{numero1}").exists(), \
            f"issue #{numero1} (premier slot) n'aurait pas dû recevoir le bloc worktree"

        # La 2e a tourné dans le worktree dédié, avec le bloc d'avertissement.
        pwd_2 = (test_dir / f"pwd-{numero2}").read_text(encoding="utf-8").strip()
        assert Path(pwd_2) == chemin_worktree.resolve(), f"issue #{numero2} aurait dû tourner dans {chemin_worktree} : {pwd_2}"
        assert (test_dir / f"worktree_marker-{numero2}").exists(), \
            f"issue #{numero2} aurait dû recevoir le bloc d'avertissement worktree"

        # Les deux ont bien abouti (marqueur de résultat posté par le faux gh).
        assert (test_dir / f"marqueur-{numero1}").exists(), f"issue #{numero1} : résultat jamais posté"
        assert (test_dir / f"marqueur-{numero2}").exists(), f"issue #{numero2} : résultat jamais posté"

        # Le worktree est CONSERVÉ après coup — pas de `git worktree remove`
        # ni de suppression de branche automatique (issue #337 point 6).
        assert chemin_worktree.is_dir(), "le worktree aurait dû être conservé après le traitement"
        assert (chemin_worktree / f"CHANGELOG-{numero2}.md").exists(), \
            "l'entrée CHANGELOG-<N>.md écrite par le faux claude aurait dû survivre dans le worktree conservé"
        branche = subprocess.run(
            ["git", "-C", str(chemin_worktree), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()
        assert branche == f"worktree-issue-{numero2}", branche

        liste_worktrees = subprocess.run(
            ["git", "-C", str(rep_travail), "worktree", "list"],
            capture_output=True, text=True,
        ).stdout
        assert str(chemin_worktree) in liste_worktrees, \
            "git worktree list aurait dû toujours référencer le worktree conservé"

        return {"parallelisation_ok": True, "worktree_conserve": True}


def scenario_non_regression_max_1():
    """MAX_WRITE_PARALLELE=1 : comportement historique intégral — aucun
    thread, aucun worktree créé, traiter_issue reste synchrone."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        test_dir = tmp_path / "etat_test"
        test_dir.mkdir()
        bin_dir = _preparer_bin(tmp_path)

        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        os.environ["TEST_337_DIR"] = str(test_dir)

        ancien_dossier_verrous = watcher.DOSSIER_VERROUS
        watcher.DOSSIER_VERROUS = tmp_path / "verrous"
        ancien_threads = list(watcher._threads_ecriture)
        watcher._threads_ecriture.clear()

        numero = 93373
        watcher.CFG = watcher.Config(
            nom="test337seq", depot="AlainDelree/depot-inexistant-test337",
            rep_travail=rep_travail, topic_ntfy="test337seq",
            max_essais=1, timeout_claude=15, notifier_local=False,
            max_write_parallele=1,
        )
        watcher.issues_en_cours.discard(numero)

        try:
            issue = _issue_minimale(numero, "Test #337 — non-régression MAX=1", ["mode_write"])
            watcher.traiter_issue(issue, dry_run=False)
            # Appel synchrone : à ce point le traitement est terminé (pas de thread en vol).
            assert watcher._threads_ecriture_actifs() == [], "aucun thread ne doit être créé quand MAX_WRITE_PARALLELE=1"
        finally:
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)
            os.environ.pop("TEST_337_DIR", None)
            watcher.DOSSIER_VERROUS = ancien_dossier_verrous
            watcher._threads_ecriture.clear()
            watcher._threads_ecriture.extend(ancien_threads)

        pwd = (test_dir / f"pwd-{numero}").read_text(encoding="utf-8").strip()
        assert Path(pwd) == rep_travail.resolve(), pwd
        assert not (test_dir / f"worktree_marker-{numero}").exists()
        assert (test_dir / f"marqueur-{numero}").exists(), "résultat jamais posté"
        sibling_worktree = rep_travail.parent / f"test337seq-issue{numero}"
        assert not sibling_worktree.exists(), "aucun worktree n'aurait dû être créé"

        return {"sequentiel_preserve": True}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur bash/git POSIX, non applicable sous Windows)")
        return 0

    tests = [
        ("_chemin_worktree / _branche_worktree : nommage attendu", scenario_chemin_et_branche_worktree),
        ("_creer_worktree : succès + replis propres (chemin/branche déjà pris)", scenario_creer_worktree_succes_et_repli),
        ("_threads_ecriture_actifs : purge des threads terminés", scenario_purge_threads_termines),
        ("parallélisation de 2 issues mode_write : REP_TRAVAIL + worktree dédié, worktree conservé",
         scenario_parallelisation_deux_issues_mode_write),
        ("non-régression MAX_WRITE_PARALLELE=1 : aucun thread, aucun worktree", scenario_non_regression_max_1),
    ]

    logging.getLogger().addHandler(logging.NullHandler())
    watcher.log.setLevel(logging.CRITICAL)  # silencieux sauf échec de test lui-même

    ancien_cfg = watcher.CFG
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
    watcher.CFG = ancien_cfg

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
