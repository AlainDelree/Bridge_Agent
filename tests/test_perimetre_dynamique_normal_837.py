#!/usr/bin/env python3
"""Test de non-régression — issue #837 : un projet à périmètre dynamique
(`PERIMETRE_DYNAMIQUE = true`, issue #125) dont une issue a pour `REPO_CIBLE`
le dépôt du projet lui-même (`REP_TRAVAIL`) est traité comme un projet
NORMAL (worktree #337, parallélisme, verrou, commit de sauvegarde
habituels) — seules les issues visant un AUTRE dépôt restent sur le chemin
dynamique historique (#125), direct, sans worktree ni parallélisme.

Vérifie :
- `_traiter_comme_perimetre_dynamique` (fonction pure) : projet à périmètre
  fixe (toujours faux), projet dynamique identique/différent/absent/
  imbriqué (deux sens)/invalide.
- Dispatch `traiter_issue` (claude/gh/notify-send simulés) : issue
  d'écriture « identique » (REPO_CIBLE = REP_TRAVAIL) avec
  MAX_WRITE_PARALLELE=4 (worktree + fil, cwd/périmètre = le worktree),
  MAX_WRITE_PARALLELE=1 (chemin direct, pas de fil, mais worktree dédié
  malgré tout — comme un projet normal), places pleines (différée, aucune
  tentative de worktree) ; issue d'écriture « différente » (REPO_CIBLE ≠
  REP_TRAVAIL — chemin dynamique historique, direct, aucune place
  consommée) ; issue de lecture « identique » (contexte strictement
  identique à un projet normal en lecture).
- `_resoudre_contexte_execution` : projet à périmètre FIXE strictement
  inchangé (mêmes décisions/chemins qu'avant cette issue, REPO_CIBLE ignoré).
- `git worktree add` ne modifie pas `git status --porcelain -uall` du
  dossier principal (ce que compare le contrôle d'écriture #833 pendant un
  audit).

`gh`, `claude` et `notify-send` sont remplacés par de faux exécutables (même
technique que tests/test_worktree_parallelisation_337.py) : aucun appel
réseau réel, ni bulle bureau réelle.

Exécution :  python3 tests/test_perimetre_dynamique_normal_837.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import contextlib
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

FAUX_GH = """#!/bin/bash
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
        touch "$TEST_837_DIR/marqueur-$numero"
    fi
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "view" ]; then
    numero="$3"
    if [ -f "$TEST_837_DIR/marqueur-$numero" ]; then
        echo '{"comments":[{"body":"<!-- bridge:resultat -->\\nfake"}]}'
    else
        echo '{"comments":[]}'
    fi
    exit 0
fi
exit 0
"""

FAUX_NOTIFY_SEND = """#!/bin/bash
if [ -n "$TEST_837_DIR" ]; then
    echo "$@" >> "$TEST_837_DIR/notify-send-appels.log"
fi
exit 0
"""

FAUX_CLAUDE = """#!/bin/bash
# $# -ge 2 distingue le VRAI appel de la sonde pre-flight (claude --print seul).
if [ "$#" -ge 2 ]; then
    prompt="${@: -1}"
    numero=$(echo "$prompt" | grep -oE 'Issue #[0-9]+' | head -1 | grep -oE '[0-9]+')
    echo "$PWD" > "$TEST_837_DIR/pwd-$numero"
    if echo "$prompt" | grep -q 'worktree isolé'; then
        touch "$TEST_837_DIR/worktree_marker-$numero"
    fi
    sleep 0.2
    echo "<!-- bridge:verdict:succes -->"
    echo "✅ Tâche terminée — test #837 (#$numero)"
fi
exit 0
"""


def _preparer_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for nom, contenu in (("claude", FAUX_CLAUDE), ("gh", FAUX_GH), ("notify-send", FAUX_NOTIFY_SEND)):
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


def _issue_minimale(numero: int, titre: str, labels: list[str], repo_cible: Path | None = None) -> dict:
    body = "| PRIORITE | normale |\n| TIMEOUT | 30s |\n"
    if repo_cible is not None:
        body += f"| REPO_CIBLE | {repo_cible} |\n"
    return {
        "number": numero,
        "title": titre,
        "body": body,
        "labels": [{"name": lab} for lab in labels],
    }


@contextlib.contextmanager
def _contexte_watcher_isole(tmp_path: Path, **kwargs_config):
    """Isole tout l'état global mutable de watcher.py pour la durée d'un
    scénario de dispatch (même isolation que
    tests/test_worktree_parallelisation_337.py)."""
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


@contextlib.contextmanager
def _bin_et_env(tmp_path: Path, test_dir: Path):
    bin_dir = _preparer_bin(tmp_path)
    ancien_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
    try:
        verifier_faux_executables_actifs(bin_dir, ["claude", "gh", "notify-send"])
    except Exception:
        os.environ["PATH"] = ancien_path
        raise
    os.environ["TEST_837_DIR"] = str(test_dir)
    try:
        yield
    finally:
        if ancien_path:
            os.environ["PATH"] = ancien_path
        else:
            os.environ.pop("PATH", None)
        os.environ.pop("TEST_837_DIR", None)


# ─── _traiter_comme_perimetre_dynamique : fonction de décision pure ─────────

def scenario_decision_projet_normal():
    """Projet à périmètre FIXE : toujours faux, quel que soit le corps —
    même avec un REPO_CIBLE présent (champ sans effet pour ce projet,
    inchangé depuis #829)."""
    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(
        nom="test837dec1", depot="AlainDelree/x", rep_travail=Path("/tmp/x837-inexistant"),
        perimetre_dynamique=False,
    )
    try:
        assert watcher._traiter_comme_perimetre_dynamique("") is False
        assert watcher._traiter_comme_perimetre_dynamique("| REPO_CIBLE | /tmp/x837-inexistant |\n") is False
        assert watcher._traiter_comme_perimetre_dynamique("| REPO_CIBLE | /tmp/ailleurs |\n") is False
    finally:
        watcher.CFG = ancien_cfg
    return {"projet_normal_toujours_faux": True}


def scenario_decision_dynamique_identique_different_absent_invalide():
    """Projet dynamique : identique (chemin résolu) → faux ; différent,
    absent, ou invalide → vrai."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp).resolve()
        projet = tmp_path / "projet"
        projet.mkdir()
        ailleurs = tmp_path / "ailleurs"
        ailleurs.mkdir()

        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(
            nom="test837dec2", depot="AlainDelree/x", rep_travail=projet,
            perimetre_dynamique=True,
        )
        try:
            assert watcher._traiter_comme_perimetre_dynamique(f"| REPO_CIBLE | {projet} |\n") is False, \
                "REPO_CIBLE identique à REP_TRAVAIL : traitement normal attendu"
            assert watcher._traiter_comme_perimetre_dynamique(f"| REPO_CIBLE | {ailleurs} |\n") is True, \
                "REPO_CIBLE différent : traitement dynamique attendu"
            assert watcher._traiter_comme_perimetre_dynamique("| PRIORITE | normale |\n") is True, \
                "REPO_CIBLE absent : traitement dynamique (abandon sans repli conservé)"
            assert watcher._traiter_comme_perimetre_dynamique("| REPO_CIBLE | chemin/relatif |\n") is True, \
                "REPO_CIBLE invalide (relatif) : traitement dynamique (validation existante)"
            assert watcher._traiter_comme_perimetre_dynamique(f"| REPO_CIBLE | {tmp_path / 'absent'} |\n") is True, \
                "REPO_CIBLE invalide (inexistant) : traitement dynamique"
        finally:
            watcher.CFG = ancien_cfg
    return {"identique_different_absent_invalide_ok": True}


def scenario_decision_imbrique_deux_sens():
    """REPO_CIBLE imbriqué dans REP_TRAVAIL ou l'inverse : ni identique, ni
    le dépôt du projet lui-même → vrai (dynamique) dans les deux sens."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp).resolve()
        ancien_cfg = watcher.CFG

        parent = tmp_path / "parent"
        enfant = parent / "sous" / "cible"
        enfant.mkdir(parents=True)
        watcher.CFG = watcher.Config(
            nom="test837dec3", depot="AlainDelree/x", rep_travail=parent,
            perimetre_dynamique=True,
        )
        try:
            assert watcher._traiter_comme_perimetre_dynamique(f"| REPO_CIBLE | {enfant} |\n") is True
        finally:
            watcher.CFG = ancien_cfg

        cible = tmp_path / "cible_parent"
        outil_sous = cible / "sous" / "outil"
        outil_sous.mkdir(parents=True)
        watcher.CFG = watcher.Config(
            nom="test837dec4", depot="AlainDelree/x", rep_travail=outil_sous,
            perimetre_dynamique=True,
        )
        try:
            assert watcher._traiter_comme_perimetre_dynamique(f"| REPO_CIBLE | {cible} |\n") is True
        finally:
            watcher.CFG = ancien_cfg
    return {"imbrique_deux_sens_ok": True}


# ─── _resoudre_contexte_execution : projet à périmètre FIXE inchangé ────────

def scenario_projet_fixe_inchange():
    """Projet à périmètre fixe (perimetre_dynamique=False) : décisions et
    chemins produits par `_resoudre_contexte_execution` strictement
    identiques à avant cette issue — avec ou sans worktree, avec ou sans
    REPO_CIBLE dans le corps (ignoré)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp).resolve()
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        worktree = tmp_path / "worktree_frere"
        worktree.mkdir()
        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(
            nom="test837fixe", depot="AlainDelree/x", rep_travail=rep_travail,
            perimetre="perimetre-conf", topic_ntfy="",
        )
        try:
            # Sans worktree, sans REPO_CIBLE (cas historique de base).
            ctx = watcher._resoudre_contexte_execution(83701, "| PRIORITE | normale |\n", watcher.MODE_LECTURE, None, None)
            assert ctx.perimetre_effectif == "perimetre-conf"
            assert ctx.cwd_effectif == rep_travail
            assert ctx.chemin_outil_lecture_exec is None

            # Avec worktree (issue #337) : remplace cwd/périmètre comme avant.
            ctx2 = watcher._resoudre_contexte_execution(83702, "| PRIORITE | normale |\n", watcher.MODE_ECRITURE, worktree, None)
            assert ctx2.cwd_effectif == worktree
            assert ctx2.perimetre_effectif == str(worktree)

            # REPO_CIBLE présent dans le corps mais projet non dynamique :
            # champ totalement ignoré (comportement #829 déjà en place).
            ctx3 = watcher._resoudre_contexte_execution(
                83703, f"| REPO_CIBLE | {tmp_path / 'autre'} |\n", watcher.MODE_LECTURE, None, None)
            assert ctx3.perimetre_effectif == "perimetre-conf"
            assert ctx3.cwd_effectif == rep_travail
        finally:
            watcher.CFG = ancien_cfg
    return {"projet_fixe_inchange_ok": True}


# ─── Dispatch traiter_issue : issue « identique » (REPO_CIBLE = REP_TRAVAIL) ─

def scenario_dispatch_identique_max4_worktree_et_fil():
    """MAX_WRITE_PARALLELE=4, issue d'écriture « identique » : traitée comme
    un projet normal — worktree dédié + fil (issue #337), cwd/périmètre
    effectifs = le worktree (pas REPO_CIBLE)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        test_dir = tmp_path / "etat_test"
        test_dir.mkdir()

        numero = 83711
        with _bin_et_env(tmp_path, test_dir):
            with _contexte_watcher_isole(
                tmp_path, nom="test837d1", depot="AlainDelree/depot-inexistant-test837",
                rep_travail=rep_travail, topic_ntfy="test837d1",
                max_essais=1, timeout_claude=15, notifier_local=False,
                max_write_parallele=4, perimetre_dynamique=True,
            ):
                issue = _issue_minimale(numero, "Test #837 — identique, MAX=4", ["mode_write"], repo_cible=rep_travail)
                watcher.traiter_issue(issue, dry_run=False)
                actifs = watcher._threads_ecriture_actifs()
                assert len(actifs) == 1, f"un fil aurait dû être lancé (traitement normal) : {actifs}"
                entree = actifs[0]
                assert entree["worktree"] is not None, "un worktree dédié aurait dû être créé"
                entree["thread"].join(timeout=15)
                assert not entree["thread"].is_alive()

                chemin_worktree = entree["worktree"]
                pwd = (test_dir / f"pwd-{numero}").read_text(encoding="utf-8").strip()
                assert Path(pwd) == chemin_worktree.resolve(), \
                    f"la tâche aurait dû tourner dans le worktree (périmètre + cwd effectifs) : {pwd} != {chemin_worktree}"
                assert (test_dir / f"worktree_marker-{numero}").exists(), \
                    "le bloc d'avertissement worktree aurait dû être injecté (traitement normal #337)"
                assert (test_dir / f"marqueur-{numero}").exists(), "résultat jamais posté"
        return {"identique_max4_worktree_et_fil_ok": True}


def scenario_dispatch_identique_max1_chemin_direct():
    """MAX_WRITE_PARALLELE=1, issue d'écriture « identique » : pas de fil
    (séquentiel, comme un projet normal — #577), mais worktree dédié malgré
    tout ; REP_TRAVAIL lui-même reste totalement inchangé pendant le
    traitement."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)
        head_avant = subprocess.run(
            ["git", "-C", str(rep_travail), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()

        test_dir = tmp_path / "etat_test"
        test_dir.mkdir()

        numero = 83712
        with _bin_et_env(tmp_path, test_dir):
            with _contexte_watcher_isole(
                tmp_path, nom="test837d2", depot="AlainDelree/depot-inexistant-test837",
                rep_travail=rep_travail, topic_ntfy="test837d2",
                max_essais=1, timeout_claude=15, notifier_local=False,
                max_write_parallele=1, perimetre_dynamique=True,
            ):
                issue = _issue_minimale(numero, "Test #837 — identique, MAX=1", ["mode_write"], repo_cible=rep_travail)
                watcher.traiter_issue(issue, dry_run=False)
                assert watcher._threads_ecriture_actifs() == [], \
                    "aucun fil ne doit être créé à MAX_WRITE_PARALLELE=1 (comme un projet normal, #577)"

                chemin_worktree = watcher._chemin_worktree(numero)
                assert chemin_worktree.is_dir(), "un worktree dédié aurait dû être créé malgré tout (#577)"
                pwd = (test_dir / f"pwd-{numero}").read_text(encoding="utf-8").strip()
                assert Path(pwd) == chemin_worktree.resolve(), \
                    f"la tâche aurait dû tourner dans le worktree, pas dans REP_TRAVAIL : {pwd}"
                assert (test_dir / f"marqueur-{numero}").exists(), "résultat jamais posté"

                head_apres = subprocess.run(
                    ["git", "-C", str(rep_travail), "rev-parse", "HEAD"],
                    capture_output=True, text=True,
                ).stdout.strip()
                assert head_apres == head_avant, "REP_TRAVAIL n'aurait pas dû bouger"
        return {"identique_max1_chemin_direct_ok": True}


def scenario_dispatch_identique_places_pleines_differee():
    """Issue d'écriture « identique » mais MAX_WRITE_PARALLELE déjà atteint
    (toutes les places occupées par des fils actifs) : différée au prochain
    cycle, sans la moindre tentative de création de worktree — comme un
    projet normal (#576)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        test_dir = tmp_path / "etat_test"
        test_dir.mkdir()

        numero_bloquant, numero_differe = 83713, 83714
        with _bin_et_env(tmp_path, test_dir):
            with _contexte_watcher_isole(
                tmp_path, nom="test837d3", depot="AlainDelree/depot-inexistant-test837",
                rep_travail=rep_travail, topic_ntfy="test837d3",
                max_essais=1, timeout_claude=15, notifier_local=False,
                max_write_parallele=1, perimetre_dynamique=True,
            ):
                issue_bloquante = _issue_minimale(
                    numero_bloquant, "Test #837 — place occupée", ["mode_write"], repo_cible=rep_travail)
                watcher.issues_en_cours.add(numero_bloquant)
                watcher._issue_write_bloquee_ajouter(numero_bloquant)

                assert watcher._chemin_worktree(numero_differe).exists() is False
                issue_differee = _issue_minimale(
                    numero_differe, "Test #837 — différée", ["mode_write"], repo_cible=rep_travail)
                watcher.traiter_issue(issue_differee, dry_run=False)

                assert watcher._threads_ecriture_actifs() == [], "aucun fil n'aurait dû être lancé (place occupée)"
                assert not watcher._chemin_worktree(numero_differe).exists(), \
                    "aucune tentative de création de worktree n'aurait dû avoir lieu (issue différée)"
                assert not (test_dir / f"pwd-{numero_differe}").exists(), \
                    "claude n'aurait jamais dû être lancé pour l'issue différée"

                watcher.issues_en_cours.discard(numero_bloquant)
                watcher._issue_write_bloquee_retirer(numero_bloquant)
        return {"places_pleines_differee_ok": True}


def scenario_dispatch_different_chemin_direct_aucune_place():
    """Issue d'écriture « différente » (REPO_CIBLE ≠ REP_TRAVAIL) : chemin
    dynamique historique inchangé — direct dans REPO_CIBLE, aucun worktree,
    aucun fil, aucune place de MAX_WRITE_PARALLELE consommée."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        outil = tmp_path / "outil"
        outil.mkdir()
        _init_depot_git(outil)
        cible = tmp_path / "cible"
        cible.mkdir()
        _init_depot_git(cible)

        test_dir = tmp_path / "etat_test"
        test_dir.mkdir()

        numero = 83715
        with _bin_et_env(tmp_path, test_dir):
            with _contexte_watcher_isole(
                tmp_path, nom="test837d4", depot="AlainDelree/depot-inexistant-test837",
                rep_travail=outil, topic_ntfy="test837d4",
                max_essais=1, timeout_claude=15, notifier_local=False,
                max_write_parallele=1, perimetre_dynamique=True,
            ):
                issue = _issue_minimale(numero, "Test #837 — différente", ["mode_write"], repo_cible=cible)
                watcher.traiter_issue(issue, dry_run=False)

                assert watcher._threads_ecriture_actifs() == [], "aucun fil pour le chemin dynamique (#125)"
                assert not watcher._chemin_worktree(numero).exists(), \
                    "aucun worktree n'aurait dû être créé (REPO_CIBLE différent → chemin dynamique historique)"
                pwd = (test_dir / f"pwd-{numero}").read_text(encoding="utf-8").strip()
                assert Path(pwd) == cible.resolve(), f"la tâche aurait dû tourner dans REPO_CIBLE : {pwd}"
                assert not (test_dir / f"worktree_marker-{numero}").exists(), \
                    "aucun bloc d'avertissement worktree attendu (chemin dynamique direct)"
                assert (test_dir / f"marqueur-{numero}").exists(), "résultat jamais posté"
        return {"different_chemin_direct_ok": True}


def scenario_lecture_identique_contexte_comme_projet_normal():
    """Issue de LECTURE « identique » : `_resoudre_contexte_execution`
    produit exactement le même contexte que pour un projet normal en
    lecture (cwd/périmètre = CFG.rep_travail/CFG.perimetre, REPO_CIBLE sans
    effet une fois vérifié)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp).resolve()
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(
            nom="test837lec", depot="AlainDelree/x", rep_travail=rep_travail,
            perimetre="perimetre-conf", topic_ntfy="", perimetre_dynamique=True,
        )
        try:
            ctx = watcher._resoudre_contexte_execution(
                83716, f"| REPO_CIBLE | {rep_travail} |\n", watcher.MODE_LECTURE, None, None)
            assert ctx is not None
            assert ctx.perimetre_effectif == "perimetre-conf", \
                "REPO_CIBLE identique : le périmètre doit rester celui du .conf, pas REPO_CIBLE"
            assert ctx.cwd_effectif == rep_travail
            assert ctx.chemin_outil_lecture_exec is None, \
                "aucun chemin d'outil supplémentaire de #833 attendu (même dossier)"
        finally:
            watcher.CFG = ancien_cfg
    return {"lecture_identique_comme_normal_ok": True}


# ─── git worktree add : état du dossier principal (contrôle d'écriture #833) ─

def scenario_worktree_add_ne_modifie_pas_status_principal():
    """`git worktree add` ne modifie PAS `git status --porcelain -uall` du
    dossier PRINCIPAL — c'est exactement ce que compare le contrôle
    d'écriture #833 pendant un audit du dossier de l'outil."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        principal = tmp_path / "principal"
        principal.mkdir()
        _init_depot_git(principal)

        statut_avant = subprocess.run(
            ["git", "status", "--porcelain", "-uall"], cwd=principal,
            capture_output=True, text=True,
        ).stdout

        worktree = tmp_path / "worktree"
        res = subprocess.run(
            ["git", "-C", str(principal), "worktree", "add", str(worktree), "-b", "branche-test-837"],
            capture_output=True, text=True,
        )
        assert res.returncode == 0, res.stderr

        statut_apres = subprocess.run(
            ["git", "status", "--porcelain", "-uall"], cwd=principal,
            capture_output=True, text=True,
        ).stdout

        assert statut_avant == statut_apres == "", \
            f"git worktree add n'aurait pas dû modifier le status du dossier principal : avant={statut_avant!r} après={statut_apres!r}"
    return {"worktree_add_statut_inchange_ok": True}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur bash/git POSIX, non applicable sous Windows)")
        return 0

    # Isole DOSSIER_WORKTREES_DEDIE pour toute la durée de ce fichier — sans
    # ce réglage, _chemin_worktree (dispatch mode_write) créerait et
    # utiliserait le VRAI ~/worktrees de la machine qui exécute les tests
    # (même garde-fou que tests/test_worktree_parallelisation_337.py).
    pile = contextlib.ExitStack()
    dossier_worktrees_dedie_test = pile.enter_context(tempfile.TemporaryDirectory())
    ancien_dossier_worktrees_dedie = watcher.DOSSIER_WORKTREES_DEDIE
    watcher.DOSSIER_WORKTREES_DEDIE = Path(dossier_worktrees_dedie_test)
    verifier_dossier_sous_tmp(watcher.DOSSIER_WORKTREES_DEDIE, "DOSSIER_WORKTREES_DEDIE")

    tests = [
        ("_traiter_comme_perimetre_dynamique : projet à périmètre fixe → toujours faux",
         scenario_decision_projet_normal),
        ("_traiter_comme_perimetre_dynamique : identique → faux, différent/absent/invalide → vrai",
         scenario_decision_dynamique_identique_different_absent_invalide),
        ("_traiter_comme_perimetre_dynamique : imbriqué dans les deux sens → vrai",
         scenario_decision_imbrique_deux_sens),
        ("_resoudre_contexte_execution : projet à périmètre fixe strictement inchangé",
         scenario_projet_fixe_inchange),
        ("dispatch : issue identique, MAX_WRITE_PARALLELE=4 → worktree + fil (traitement normal)",
         scenario_dispatch_identique_max4_worktree_et_fil),
        ("dispatch : issue identique, MAX_WRITE_PARALLELE=1 → chemin direct, worktree malgré tout",
         scenario_dispatch_identique_max1_chemin_direct),
        ("dispatch : issue identique, places pleines → différée, aucune tentative de worktree",
         scenario_dispatch_identique_places_pleines_differee),
        ("dispatch : issue différente → chemin dynamique direct historique, aucune place consommée",
         scenario_dispatch_different_chemin_direct_aucune_place),
        ("issue de lecture identique : contexte strictement identique à un projet normal",
         scenario_lecture_identique_contexte_comme_projet_normal),
        ("git worktree add : status --porcelain -uall du dossier principal inchangé",
         scenario_worktree_add_ne_modifie_pas_status_principal),
    ]

    import logging
    logging.getLogger().addHandler(logging.NullHandler())
    watcher.log.setLevel(logging.CRITICAL)

    ancien_cfg = watcher.CFG
    echecs = 0
    try:
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
    finally:
        watcher.CFG = ancien_cfg
        watcher.DOSSIER_WORKTREES_DEDIE = ancien_dossier_worktrees_dedie
        pile.close()

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
