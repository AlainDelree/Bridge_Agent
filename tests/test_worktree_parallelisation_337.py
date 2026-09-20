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
- Issue #577 : `MAX_WRITE_PARALLELE = 1` → `traiter_issue` reste strictement
  synchrone (aucun thread créé, comme avant #337/#577) mais la tâche
  s'exécute désormais dans un worktree dédié, jamais directement dans
  REP_TRAVAIL — celui-ci reste totalement inchangé (aucun fichier ajouté,
  HEAD identique) pendant tout le traitement, même à parallélisation
  désactivée. Repli sur REP_TRAVAIL si la création du worktree échoue
  (chemin déjà pris).
- Issue #576 : une issue mode_write abandonnée en `needs-human` continue
  d'occuper sa place de `MAX_WRITE_PARALLELE` jusqu'à résolution manuelle
  (retrait du label, ou fermeture de l'issue) — avec `MAX_WRITE_PARALLELE=1`
  elle bloque tout traitement mode_write suivant ; avec une valeur plus
  haute, elle occupe une place parmi les autres sans bloquer le reste. Le
  retrait du label libère la place au prochain passage dans `traiter_issue` ;
  une fermeture manuelle (issue absente de `lister_issues()`) est détectée
  séparément par `_reconcilier_issues_en_cours_fermees`.

`gh` et `claude` sont remplacés par de faux exécutables (même technique que
tests/test_lecture_active_327.py) : aucun appel réseau réel. Le faux `claude`
consigne dans quel répertoire (`$PWD`) et pour quel numéro d'issue il a
tourné, et signale si le prompt reçu contenait le bloc d'avertissement
worktree — ce qui permet de vérifier la bonne cible sans dépendre du
contenu réel produit par un agent.

Exécution :  python3 tests/test_worktree_parallelisation_337.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import contextlib
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


# Faux `claude` — issue #576. Contrairement à FAUX_CLAUDE ci-dessus (toujours
# un succès), échoue (code 1) à la demande pour un numéro d'issue donné —
# présence du fichier marqueur $TEST_576_DIR/fail-<numero> — pour déclencher
# le chemin needs-human. Cherche le numéro d'issue dans TOUS les arguments
# (pas seulement le dernier) : la passe diagnostique (`diagnostiquer_echec`,
# mode lecture seule) ajoute `--allowedTools ...` APRÈS le prompt, qui n'est
# donc plus le dernier argument dans ce cas.
FAUX_CLAUDE_576 = """#!/bin/bash
if [ "$#" -ge 2 ]; then
    numero=""
    for arg in "$@"; do
        n=$(echo "$arg" | grep -oE 'Issue #[0-9]+' | head -1 | grep -oE '[0-9]+')
        if [ -n "$n" ]; then
            numero="$n"
        fi
    done
    if [ -n "$numero" ]; then
        echo "$PWD" > "$TEST_576_DIR/pwd-$numero"
        if [ -f "$TEST_576_DIR/fail-$numero" ]; then
            echo "erreur simulée pour #$numero" >&2
            exit 1
        fi
    fi
    sleep 0.05
    echo "✅ Tâche terminée — test #$numero"
fi
exit 0
"""


def _preparer_bin(tmp_path: Path, claude_script: str = FAUX_CLAUDE) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for nom, contenu in (("claude", claude_script), ("gh", FAUX_GH)):
        chemin = bin_dir / nom
        chemin.write_text(contenu, encoding="utf-8")
        chemin.chmod(chemin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


@contextlib.contextmanager
def _contexte_watcher_isole(tmp_path: Path, **kwargs_config):
    """Isole tout l'état global mutable de watcher.py pour la durée d'un
    scénario needs-human (issue #576) — même isolation que
    `_lancer_deux_issues_paralleles` (verrous fichier, fichiers d'état de
    calibration, threads/issues en cours), factorisée ici car partagée par
    plusieurs scénarios qui n'ont pas besoin du dispatch à deux issues.
    Inclut en plus `_issues_write_bloquees_needs_human` (#576), absent de
    l'isolation historique de #337."""
    ancien_cfg                   = watcher.CFG
    ancien_dossier_verrous       = watcher.DOSSIER_VERROUS
    ancien_dossier_logs          = watcher.DOSSIER_LOGS
    ancien_fichier_historique    = watcher.FICHIER_HISTORIQUE
    ancien_fichier_etat_timeout  = watcher.FICHIER_ETAT_TIMEOUT
    ancien_fichier_etat_ambiance = watcher.FICHIER_ETAT_AMBIANCE
    ancien_threads               = list(watcher._threads_ecriture)
    ancien_issues_en_cours       = set(watcher.issues_en_cours)
    ancien_bloquees              = set(watcher._issues_write_bloquees_needs_human)

    watcher.DOSSIER_VERROUS = tmp_path / "verrous"
    watcher.DOSSIER_LOGS = tmp_path / "logs"
    watcher.FICHIER_HISTORIQUE = watcher.DOSSIER_LOGS / "historique_durees.json"
    watcher.FICHIER_ETAT_TIMEOUT = watcher.DOSSIER_LOGS / "etat_timeout.json"
    watcher.FICHIER_ETAT_AMBIANCE = watcher.DOSSIER_LOGS / "etat_ambiance.json"
    watcher._threads_ecriture.clear()
    watcher.issues_en_cours.clear()
    watcher._issues_write_bloquees_needs_human.clear()
    watcher.CFG = watcher.Config(**kwargs_config)
    try:
        yield
    finally:
        watcher.CFG = ancien_cfg
        watcher.DOSSIER_VERROUS = ancien_dossier_verrous
        watcher.DOSSIER_LOGS = ancien_dossier_logs
        watcher.FICHIER_HISTORIQUE = ancien_fichier_historique
        watcher.FICHIER_ETAT_TIMEOUT = ancien_fichier_etat_timeout
        watcher.FICHIER_ETAT_AMBIANCE = ancien_fichier_etat_ambiance
        watcher._threads_ecriture.clear()
        watcher._threads_ecriture.extend(ancien_threads)
        watcher.issues_en_cours.clear()
        watcher.issues_en_cours.update(ancien_issues_en_cours)
        watcher._issues_write_bloquees_needs_human.clear()
        watcher._issues_write_bloquees_needs_human.update(ancien_bloquees)


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
    # Isolation (issue #520) : sans repli, enregistrer_duree()/
    # maj_calibration_timeout() écriraient réellement dans logs/historique_
    # durees.json et logs/etat_timeout.json du dépôt (mêmes constantes que
    # DOSSIER_VERROUS ci-dessus, résolues dynamiquement à l'appel).
    ancien_dossier_logs = watcher.DOSSIER_LOGS
    ancien_fichier_historique = watcher.FICHIER_HISTORIQUE
    ancien_fichier_etat_timeout = watcher.FICHIER_ETAT_TIMEOUT
    ancien_fichier_etat_ambiance = watcher.FICHIER_ETAT_AMBIANCE
    watcher.DOSSIER_LOGS = tmp_path / "logs"
    watcher.FICHIER_HISTORIQUE = watcher.DOSSIER_LOGS / "historique_durees.json"
    watcher.FICHIER_ETAT_TIMEOUT = watcher.DOSSIER_LOGS / "etat_timeout.json"
    watcher.FICHIER_ETAT_AMBIANCE = watcher.DOSSIER_LOGS / "etat_ambiance.json"
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
        watcher.DOSSIER_LOGS = ancien_dossier_logs
        watcher.FICHIER_HISTORIQUE = ancien_fichier_historique
        watcher.FICHIER_ETAT_TIMEOUT = ancien_fichier_etat_timeout
        watcher.FICHIER_ETAT_AMBIANCE = ancien_fichier_etat_ambiance
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


def scenario_max_1_isole_dans_worktree():
    """Issue #577 : MAX_WRITE_PARALLELE=1 — `traiter_issue` reste strictement
    synchrone (aucun thread créé, comme avant #577), mais la tâche s'exécute
    désormais dans un worktree dédié, jamais directement dans REP_TRAVAIL :
    celui-ci reste totalement inchangé (même HEAD, aucun fichier ajouté)
    pendant tout le traitement — Alain doit pouvoir le manipuler à tout
    moment sans risque de collision."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        head_avant = subprocess.run(
            ["git", "-C", str(rep_travail), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()
        fichiers_avant = sorted(p.name for p in rep_travail.iterdir())

        test_dir = tmp_path / "etat_test"
        test_dir.mkdir()
        bin_dir = _preparer_bin(tmp_path)

        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        os.environ["TEST_337_DIR"] = str(test_dir)

        ancien_dossier_verrous = watcher.DOSSIER_VERROUS
        watcher.DOSSIER_VERROUS = tmp_path / "verrous"
        ancien_dossier_logs = watcher.DOSSIER_LOGS
        ancien_fichier_historique = watcher.FICHIER_HISTORIQUE
        ancien_fichier_etat_timeout = watcher.FICHIER_ETAT_TIMEOUT
        ancien_fichier_etat_ambiance = watcher.FICHIER_ETAT_AMBIANCE
        watcher.DOSSIER_LOGS = tmp_path / "logs"
        watcher.FICHIER_HISTORIQUE = watcher.DOSSIER_LOGS / "historique_durees.json"
        watcher.FICHIER_ETAT_TIMEOUT = watcher.DOSSIER_LOGS / "etat_timeout.json"
        watcher.FICHIER_ETAT_AMBIANCE = watcher.DOSSIER_LOGS / "etat_ambiance.json"
        ancien_threads = list(watcher._threads_ecriture)
        watcher._threads_ecriture.clear()

        numero = 93373
        watcher.CFG = watcher.Config(
            nom="test577seq", depot="AlainDelree/depot-inexistant-test577",
            rep_travail=rep_travail, topic_ntfy="test577seq",
            max_essais=1, timeout_claude=15, notifier_local=False,
            max_write_parallele=1,
        )
        watcher.issues_en_cours.discard(numero)

        try:
            issue = _issue_minimale(numero, "Test #577 — isolation worktree à MAX=1", ["mode_write"])
            watcher.traiter_issue(issue, dry_run=False)
            # Appel synchrone : à ce point le traitement est terminé (pas de thread en vol).
            assert watcher._threads_ecriture_actifs() == [], \
                "aucun thread ne doit être créé quand MAX_WRITE_PARALLELE=1 (issue #577)"
        finally:
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)
            os.environ.pop("TEST_337_DIR", None)
            watcher.DOSSIER_VERROUS = ancien_dossier_verrous
            watcher.DOSSIER_LOGS = ancien_dossier_logs
            watcher.FICHIER_HISTORIQUE = ancien_fichier_historique
            watcher.FICHIER_ETAT_TIMEOUT = ancien_fichier_etat_timeout
            watcher.FICHIER_ETAT_AMBIANCE = ancien_fichier_etat_ambiance
            watcher._threads_ecriture.clear()
            watcher._threads_ecriture.extend(ancien_threads)

        chemin_worktree = rep_travail.parent / f"test577seq-issue{numero}"
        assert chemin_worktree.is_dir(), \
            "un worktree dédié aurait dû être créé même à MAX_WRITE_PARALLELE=1 (issue #577)"

        pwd = (test_dir / f"pwd-{numero}").read_text(encoding="utf-8").strip()
        assert Path(pwd) == chemin_worktree.resolve(), \
            f"la tâche aurait dû tourner dans le worktree, pas dans REP_TRAVAIL : {pwd}"
        assert (test_dir / f"worktree_marker-{numero}").exists(), \
            "la tâche aurait dû recevoir le bloc d'avertissement worktree dans son prompt"
        assert (test_dir / f"marqueur-{numero}").exists(), "résultat jamais posté"

        # REP_TRAVAIL reste totalement inchangé : même HEAD, aucun fichier ajouté.
        head_apres = subprocess.run(
            ["git", "-C", str(rep_travail), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()
        assert head_apres == head_avant, "REP_TRAVAIL n'aurait pas dû bouger (HEAD modifié)"
        fichiers_apres = sorted(p.name for p in rep_travail.iterdir())
        assert fichiers_apres == fichiers_avant, \
            f"REP_TRAVAIL n'aurait pas dû recevoir de nouveau fichier : {fichiers_apres} != {fichiers_avant}"
        assert not (rep_travail / f"CHANGELOG-{numero}.md").exists(), \
            "le fichier écrit par la tâche n'aurait pas dû finir dans REP_TRAVAIL"

        # Le worktree, lui, contient bien le changelog écrit par la tâche —
        # et reste conservé après coup (fusion/nettoyage manuels par Alain).
        assert (chemin_worktree / f"CHANGELOG-{numero}.md").exists(), \
            "le fichier écrit par la tâche aurait dû finir dans le worktree isolé"

        return {"isolation_max_1_ok": True}


def scenario_max_1_repli_si_worktree_echoue():
    """Issue #577 : si la création du worktree échoue (chemin cible déjà
    occupé), repli propre et direct sur REP_TRAVAIL — pas d'exception, pas de
    blocage, comportement identique au repli déjà couvert par #337 pour le
    cas parallélisé."""
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

        numero = 93374
        with _contexte_watcher_isole(
            tmp_path, nom="test577repli", depot="AlainDelree/depot-inexistant-test577",
            rep_travail=rep_travail, topic_ntfy="test577repli",
            max_essais=1, timeout_claude=15, notifier_local=False,
            max_write_parallele=1,
        ):
            try:
                # Chemin cible du worktree déjà occupé par un dossier
                # quelconque (garde-fou #337 point 4 de _creer_worktree) →
                # création refusée, repli attendu sur REP_TRAVAIL.
                chemin_cible = watcher._chemin_worktree(numero)
                chemin_cible.mkdir(parents=True)

                issue = _issue_minimale(numero, "Test #577 — repli si worktree impossible", ["mode_write"])
                watcher.traiter_issue(issue, dry_run=False)

                pwd = (test_dir / f"pwd-{numero}").read_text(encoding="utf-8").strip()
                assert Path(pwd) == rep_travail.resolve(), \
                    f"repli attendu dans REP_TRAVAIL si le worktree ne peut être créé : {pwd}"
                assert (test_dir / f"marqueur-{numero}").exists(), "résultat jamais posté"
            finally:
                if ancien_path:
                    os.environ["PATH"] = ancien_path
                else:
                    os.environ.pop("PATH", None)
                os.environ.pop("TEST_337_DIR", None)

        return {"repli_worktree_echoue_ok": True}


def scenario_needs_human_bloque_max_1():
    """Issue #576 : avec MAX_WRITE_PARALLELE=1, une issue mode_write abandonnée
    en needs-human (échec réel après épuisement des tentatives) continue
    d'occuper l'unique place — une deuxième issue mode_write est différée SANS
    même être tentée (aucun ACK, aucun appel claude) tant que le label n'est
    pas retiré. Une fois le label retiré (bouton « Relancer » #574, fichier
    RELANCE #516/#572, ou retrait manuel — simulé ici par des labels frais
    sans 'needs-human'), la place est libérée et le traitement reprend
    normalement pour les deux issues."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        test_dir = tmp_path / "etat_test"
        test_dir.mkdir()
        bin_dir = _preparer_bin(tmp_path, claude_script=FAUX_CLAUDE_576)

        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        os.environ["TEST_576_DIR"] = str(test_dir)
        # FAUX_GH (issue comment/view, marqueur de résultat posté) référence
        # TEST_337_DIR en dur — même dossier, exposé sous les deux noms.
        os.environ["TEST_337_DIR"] = str(test_dir)

        numero1, numero2 = 93761, 93762
        with _contexte_watcher_isole(
            tmp_path, nom="test576max1", depot="AlainDelree/depot-inexistant-test576",
            rep_travail=rep_travail, topic_ntfy="test576max1",
            max_essais=1, timeout_claude=15, notifier_local=False,
            max_write_parallele=1,
        ):
            try:
                (test_dir / f"fail-{numero1}").touch()
                issue1 = _issue_minimale(numero1, "Test #576 — échec définitif", ["mode_write"])
                watcher.traiter_issue(issue1, dry_run=False)

                assert numero1 in watcher.issues_en_cours, \
                    "l'issue needs-human aurait dû rester dans issues_en_cours (#576)"
                assert watcher._nb_issues_write_bloquees() == 1, \
                    "l'issue needs-human aurait dû occuper une place de MAX_WRITE_PARALLELE (#576)"
                assert not (test_dir / f"marqueur-{numero1}").exists(), \
                    "aucun résultat de succès n'aurait dû être posté (échec attendu)"

                # Deuxième issue mode_write : la seule place est occupée par
                # l'issue #1 en needs-human — différée sans même être tentée.
                issue2 = _issue_minimale(numero2, "Test #576 — différée (place occupée)", ["mode_write"])
                watcher.traiter_issue(issue2, dry_run=False)
                assert not (test_dir / f"pwd-{numero2}").exists(), \
                    "l'issue #2 n'aurait pas dû être tentée : la place unique est occupée par needs-human (#576)"
                assert numero2 not in watcher.issues_en_cours

                # Résolution : label 'needs-human' retiré (Relancer/RELANCE/manuel)
                # et cause corrigée — la place doit se libérer et l'issue #1
                # être retraitée normalement.
                (test_dir / f"fail-{numero1}").unlink()
                issue1_relance = _issue_minimale(numero1, "Test #576 — échec définitif", ["mode_write"])
                watcher.traiter_issue(issue1_relance, dry_run=False)
                assert numero1 not in watcher.issues_en_cours
                assert watcher._nb_issues_write_bloquees() == 0, \
                    "la place aurait dû être libérée après retrait du label needs-human (#576)"
                assert (test_dir / f"marqueur-{numero1}").exists(), "issue #1 relancée : résultat jamais posté"

                # La place étant libre, l'issue #2 peut maintenant être traitée.
                watcher.traiter_issue(issue2, dry_run=False)
                assert (test_dir / f"pwd-{numero2}").exists(), "issue #2 aurait dû être traitée une fois la place libérée"
                assert (test_dir / f"marqueur-{numero2}").exists(), "issue #2 : résultat jamais posté"
            finally:
                if ancien_path:
                    os.environ["PATH"] = ancien_path
                else:
                    os.environ.pop("PATH", None)
                os.environ.pop("TEST_576_DIR", None)
                os.environ.pop("TEST_337_DIR", None)

        return {"blocage_puis_liberation_ok": True}


def scenario_needs_human_compte_avec_max_superieur():
    """Issue #576 : avec MAX_WRITE_PARALLELE=2, une issue déjà bloquée en
    needs-human (simulée directement — le cheminement réel est couvert par
    `scenario_needs_human_bloque_max_1`) occupe une place parmi les autres :
    UNE tâche mode_write supplémentaire peut démarrer (place restante), mais
    une DEUXIÈME est bien différée — needs-human + 1 thread actif = 2 places
    occupées sur 2."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        test_dir = tmp_path / "etat_test"
        test_dir.mkdir()
        bin_dir = _preparer_bin(tmp_path, claude_script=FAUX_CLAUDE_576)

        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        os.environ["TEST_576_DIR"] = str(test_dir)
        # FAUX_GH (issue comment/view, marqueur de résultat posté) référence
        # TEST_337_DIR en dur — même dossier, exposé sous les deux noms.
        os.environ["TEST_337_DIR"] = str(test_dir)

        numero_bloquee, numero1, numero2 = 93763, 93764, 93765
        with _contexte_watcher_isole(
            tmp_path, nom="test576max2", depot="AlainDelree/depot-inexistant-test576",
            rep_travail=rep_travail, topic_ntfy="test576max2",
            max_essais=1, timeout_claude=15, notifier_local=False,
            max_write_parallele=2,
        ):
            try:
                watcher._issues_en_cours_ajouter(numero_bloquee)
                watcher._issue_write_bloquee_ajouter(numero_bloquee)

                issue1 = _issue_minimale(numero1, "Test #576 — place restante", ["mode_write"])
                watcher.traiter_issue(issue1, dry_run=False)
                actifs_1 = watcher._threads_ecriture_actifs()
                assert len(actifs_1) == 1, \
                    f"1 place restante (2 - 1 bloquée en needs-human) : la tâche aurait dû démarrer : {actifs_1}"

                issue2 = _issue_minimale(numero2, "Test #576 — plus de place", ["mode_write"])
                watcher.traiter_issue(issue2, dry_run=False)
                actifs_2 = watcher._threads_ecriture_actifs()
                assert len(actifs_2) == 1, \
                    "aucune place restante (1 thread actif + 1 needs-human = 2/2) : la 2e tâche n'aurait pas dû démarrer"
                assert not (test_dir / f"pwd-{numero2}").exists()

                actifs_1[0]["thread"].join(timeout=15)
                assert not actifs_1[0]["thread"].is_alive(), f"thread issue #{numero1} toujours actif après 15s"
            finally:
                if ancien_path:
                    os.environ["PATH"] = ancien_path
                else:
                    os.environ.pop("PATH", None)
                os.environ.pop("TEST_576_DIR", None)
                os.environ.pop("TEST_337_DIR", None)

        return {"place_partagee_ok": True}


def scenario_reconciliation_fermeture_manuelle():
    """Issue #576 (cas 3) : une issue needs-human fermée manuellement sur
    GitHub — plutôt qu'un simple retrait du label — doit elle aussi libérer sa
    place. Ce cas n'est PAS détecté par `traiter_issue` (qui ne revoit plus
    jamais cette issue, absente de `lister_issues()` — état `--state open`
    uniquement) mais par `_reconcilier_issues_en_cours_fermees`, appelée une
    fois par cycle en tête de boucle principale sur la liste fraîche des
    issues ouvertes."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        numero = 93766
        with _contexte_watcher_isole(
            tmp_path, nom="test576reconcil", depot="AlainDelree/depot-inexistant-test576",
            rep_travail=tmp_path / "projet_inexistant", topic_ntfy="test576reconcil",
        ):
            watcher._issues_en_cours_ajouter(numero)
            watcher._issue_write_bloquee_ajouter(numero)

            # Toujours ouverte sur GitHub (présente dans le lot, avec le label
            # needs-human toujours posé) : rien ne doit bouger.
            watcher._reconcilier_issues_en_cours_fermees(
                [{"number": numero, "labels": [{"name": "needs-human"}]}])
            assert numero in watcher.issues_en_cours
            assert watcher._nb_issues_write_bloquees() == 1

            # Disparue de la liste des issues ouvertes (fermeture manuelle) :
            # la place doit être libérée.
            watcher._reconcilier_issues_en_cours_fermees([])
            assert numero not in watcher.issues_en_cours, \
                "la place aurait dû être libérée (issue fermée manuellement, #576)"
            assert watcher._nb_issues_write_bloquees() == 0

        return {"reconciliation_fermeture_ok": True}


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
        ("issue #577 — MAX_WRITE_PARALLELE=1 : aucun thread, mais worktree dédié, REP_TRAVAIL inchangé",
         scenario_max_1_isole_dans_worktree),
        ("issue #577 — MAX_WRITE_PARALLELE=1 : repli sur REP_TRAVAIL si la création du worktree échoue",
         scenario_max_1_repli_si_worktree_echoue),
        ("issue #576 — needs-human bloque la seule place (MAX=1) puis la libère après retrait du label",
         scenario_needs_human_bloque_max_1),
        ("issue #576 — needs-human compte parmi les places (MAX=2) sans bloquer le reste",
         scenario_needs_human_compte_avec_max_superieur),
        ("issue #576 — fermeture manuelle d'une issue needs-human libère sa place",
         scenario_reconciliation_fermeture_manuelle),
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
