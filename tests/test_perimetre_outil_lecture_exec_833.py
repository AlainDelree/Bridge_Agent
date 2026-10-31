#!/usr/bin/env python3
"""Test de non-régression — issue #833 : pour un projet à périmètre
dynamique (`PERIMETRE_DYNAMIQUE = true`, issue #125), ajoute au contexte
d'exécution le dossier du projet lui-même (REP_TRAVAIL, où vit le code de
l'outil) quand il est DISJOINT de REPO_CIBLE — en LECTURE et EXÉCUTION
SEULEMENT, avec un contrôle technique d'écriture réutilisant le garde-fou
#327 (`_statut_git_rep_travail`/`_restaurer_rep_travail_modifie`).

Vérifie :
- `_resoudre_contexte_execution` : REP_TRAVAIL disjoint de REPO_CIBLE →
  ajouté (`chemin_outil_lecture_exec`), `perimetre_effectif`/`cwd_effectif`
  inchangés (REPO_CIBLE seul) ; identique, imbriqué dans un sens ou dans
  l'autre, ou agent `vibe` → rien ajouté.
- `lancer_claude`/`diagnostiquer_echec` : la clause de périmètre contient les
  deux chemins et la mention « lecture et exécution seulement » quand ce
  chemin existe ; inchangée caractère pour caractère sinon.
- Écriture détectée dans ce dossier pendant une tentative, dans les TROIS
  modes (lecture, lecture active, écriture) : restaurée, échec DÉFINITIF
  (une seule tentative malgré `MAX_ESSAIS` > 1), `needs-human` posé.
- Un fichier ignoré par git écrit dans ce dossier : NON détecté (limite
  documentée de `git status --porcelain`, même sans `--ignored`).
- Un dossier qui n'est pas un dépôt git : aucun contrôle, un seul message.

`gh` et `claude` sont remplacés par de faux exécutables (même technique que
tests/test_lecture_active_327.py) : aucun appel réseau réel.

Exécution :  python3 tests/test_perimetre_outil_lecture_exec_833.py
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
from garde_fou_faux_executables import verifier_faux_executables_actifs  # noqa: E402

# Même faux `gh` que test_lecture_active_327.py — stateful uniquement sur
# `issue view --json comments` (nécessaire à commenter_resultat_avec_retry,
# issue #237, pour les scénarios qui se terminent en succès).
FAUX_GH = """#!/bin/bash
if [ "$1" = "issue" ] && [ "$2" = "comment" ]; then
    bodyfile=""
    prev=""
    for arg in "$@"; do
        if [ "$prev" = "--body-file" ]; then
            bodyfile="$arg"
        fi
        prev="$arg"
    done
    if [ -n "$bodyfile" ] && grep -q -- '<!-- bridge:resultat -->' "$bodyfile" 2>/dev/null; then
        touch "$TEST_833_MARQUEUR"
    fi
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "view" ]; then
    if [ -n "$TEST_833_MARQUEUR" ] && [ -f "$TEST_833_MARQUEUR" ]; then
        echo '{"comments":[{"body":"<!-- bridge:resultat -->\\nfake"}]}'
    else
        echo '{"comments":[]}'
    fi
    exit 0
fi
exit 0
"""


def _preparer_bin(tmp_path: Path, script_claude: str) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)

    claude_path = bin_dir / "claude"
    claude_path.write_text(script_claude, encoding="utf-8")
    claude_path.chmod(claude_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    gh_path = bin_dir / "gh"
    gh_path.write_text(FAUX_GH, encoding="utf-8")
    gh_path.chmod(gh_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return bin_dir


def _init_depot_git(rep: Path, nom_fichier: str = "fichier.txt") -> None:
    subprocess.run(["git", "init", "-q", "-b", "master", str(rep)], check=True)
    (rep / nom_fichier).write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=rep, check=True, capture_output=True)


def _issue_minimale(numero: int, titre: str, labels: list[str], repo_cible: Path) -> dict:
    body = (
        f"| REPO_CIBLE | {repo_cible} |\n"
        f"| PRIORITE | normale |\n"
        f"| TIMEOUT | 30s |\n"
    )
    return {
        "number": numero,
        "title": titre,
        "body": body,
        "labels": [{"name": lab} for lab in labels],
    }


# ─── _resoudre_contexte_execution : relations REP_TRAVAIL / REPO_CIBLE ────────

def scenario_contexte_disjoint_ajoute_chemin_outil():
    """REP_TRAVAIL disjoint de REPO_CIBLE (projet à périmètre dynamique,
    agent claude) : ajouté en lecture/exécution seule, `perimetre_effectif`
    et `cwd_effectif` restant REPO_CIBLE seul."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        outil = tmp_path / "outil"
        outil.mkdir()
        cible = tmp_path / "cible"
        cible.mkdir()
        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(
            nom="test833ctx1", depot="AlainDelree/x", rep_travail=outil,
            perimetre_dynamique=True, topic_ntfy="",
        )
        try:
            body = f"| REPO_CIBLE | {cible} |\n"
            contexte = watcher._resoudre_contexte_execution(83301, body, watcher.MODE_LECTURE, None, None)
        finally:
            watcher.CFG = ancien_cfg

        assert contexte is not None
        assert contexte.perimetre_effectif == str(cible.resolve())
        assert contexte.cwd_effectif == cible.resolve(), "le cwd doit rester REPO_CIBLE"
        assert contexte.chemin_outil_lecture_exec == outil.resolve()
        return {"disjoint_ajoute": True}


def scenario_contexte_identique_ou_imbrique_rien_ajoute():
    """Identique, REP_TRAVAIL imbriqué dans REPO_CIBLE, ou REPO_CIBLE
    imbriqué dans REP_TRAVAIL : rien n'est ajouté au contexte dans aucun des
    trois cas — cwd/perimetre restent REPO_CIBLE comme aujourd'hui."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_cfg = watcher.CFG

        # 1. Identique.
        projet = tmp_path / "identique"
        projet.mkdir()
        watcher.CFG = watcher.Config(
            nom="test833ctx2", depot="AlainDelree/x", rep_travail=projet,
            perimetre_dynamique=True, topic_ntfy="",
        )
        try:
            contexte = watcher._resoudre_contexte_execution(
                83302, f"| REPO_CIBLE | {projet} |\n", watcher.MODE_LECTURE, None, None)
        finally:
            watcher.CFG = ancien_cfg
        assert contexte.chemin_outil_lecture_exec is None, "identique : rien ne doit être ajouté"
        assert contexte.cwd_effectif == projet.resolve()

        # 2. REP_TRAVAIL imbriqué SOUS REPO_CIBLE.
        cible = tmp_path / "cible_parent"
        cible.mkdir()
        outil_sous = cible / "sous" / "outil"
        outil_sous.mkdir(parents=True)
        watcher.CFG = watcher.Config(
            nom="test833ctx3", depot="AlainDelree/x", rep_travail=outil_sous,
            perimetre_dynamique=True, topic_ntfy="",
        )
        try:
            contexte = watcher._resoudre_contexte_execution(
                83303, f"| REPO_CIBLE | {cible} |\n", watcher.MODE_LECTURE, None, None)
        finally:
            watcher.CFG = ancien_cfg
        assert contexte.chemin_outil_lecture_exec is None, "REP_TRAVAIL sous REPO_CIBLE : rien à ajouter"

        # 3. REPO_CIBLE imbriqué SOUS REP_TRAVAIL (sens inverse).
        outil_parent = tmp_path / "outil_parent"
        outil_parent.mkdir()
        cible_sous = outil_parent / "sous" / "cible"
        cible_sous.mkdir(parents=True)
        watcher.CFG = watcher.Config(
            nom="test833ctx4", depot="AlainDelree/x", rep_travail=outil_parent,
            perimetre_dynamique=True, topic_ntfy="",
        )
        try:
            contexte = watcher._resoudre_contexte_execution(
                83304, f"| REPO_CIBLE | {cible_sous} |\n", watcher.MODE_LECTURE, None, None)
        finally:
            watcher.CFG = ancien_cfg
        assert contexte.chemin_outil_lecture_exec is None, "REPO_CIBLE sous REP_TRAVAIL : rien à ajouter"

        return {"identique_et_imbrique_rien_ajoute": True}


def scenario_contexte_vibe_jamais_ajoute():
    """Agent `vibe` : REP_TRAVAIL disjoint de REPO_CIBLE, mais rien n'est
    ajouté — vibe n'a aucune option de lecture seule par répertoire."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        outil = tmp_path / "outil"
        outil.mkdir()
        cible = tmp_path / "cible"
        cible.mkdir()
        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(
            nom="test833ctx5", depot="AlainDelree/x", rep_travail=outil,
            perimetre_dynamique=True, topic_ntfy="", agent="vibe",
        )
        try:
            contexte = watcher._resoudre_contexte_execution(
                83305, f"| REPO_CIBLE | {cible} |\n", watcher.MODE_LECTURE, None, None)
        finally:
            watcher.CFG = ancien_cfg
        assert contexte.chemin_outil_lecture_exec is None, "vibe : jamais ouvert, même disjoint"
        assert contexte.cwd_effectif == cible.resolve()
        return {"vibe_jamais_ajoute": True}


def scenario_chemins_disjoints_helper():
    """_chemins_disjoints : vrai seulement quand ni égal ni contenu l'un dans
    l'autre."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp).resolve()
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        assert watcher._chemins_disjoints(a, b) is True
        assert watcher._chemins_disjoints(a, a) is False
        assert watcher._chemins_disjoints(a, a / "sous") is False
        assert watcher._chemins_disjoints(a / "sous", a) is False
        return {"chemins_disjoints_helper_ok": True}


# ─── Clause de prompt : lancer_claude et diagnostiquer_echec ──────────────────

FAUX_CLAUDE_CAPTURE_PROMPT = """#!/bin/bash
# $# -ge 2 distingue le VRAI appel de la sonde pre-flight (claude --print
# seul). Le prompt n'est PAS toujours le DERNIER argument (en MODE_LECTURE,
# --allowedTools suit le prompt, voir _construire_cmd_claude) : on capture
# donc TOUS les arguments, chacun suivi d'un saut de ligne — le texte du
# prompt reste un bloc contigu dans le fichier, seul ce qui l'entoure varie.
if [ "$#" -ge 2 ]; then
    printf '%s\\n' "$@" > "$TEST_833_PROMPT_FILE"
    echo "<!-- bridge:verdict:succes -->"
    echo "✅ Tâche terminée — test #833 (capture de prompt)"
fi
exit 0
"""


def _capturer_prompt(tmp_path: Path, appel) -> str:
    """Place le faux claude/gh en tête du PATH, exécute `appel()` (qui doit
    déclencher `lancer_claude`), retourne le texte de tous les arguments
    reçus par le faux claude — le prompt y reste un bloc contigu."""
    prompt_file = tmp_path / "prompt_capture.txt"
    bin_dir = _preparer_bin(tmp_path, FAUX_CLAUDE_CAPTURE_PROMPT)
    ancien_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
    os.environ["TEST_833_PROMPT_FILE"] = str(prompt_file)
    try:
        verifier_faux_executables_actifs(bin_dir, ["claude", "gh"])
        appel()
    finally:
        if ancien_path:
            os.environ["PATH"] = ancien_path
        else:
            os.environ.pop("PATH", None)
        os.environ.pop("TEST_833_PROMPT_FILE", None)
    return prompt_file.read_text(encoding="utf-8")


def scenario_clause_prompt_lancer_claude_disjoint():
    """lancer_claude : chemin_outil_lecture_exec fourni → la clause de
    périmètre contient les deux chemins, la mention « lecture et exécution
    seulement » et PYTHONDONTWRITEBYTECODE=1."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        outil = tmp_path / "outil"
        outil.mkdir()
        cible = tmp_path / "cible"
        cible.mkdir()
        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(nom="test833p1", depot="AlainDelree/x", rep_travail=tmp_path, topic_ntfy="")
        try:
            prompt = _capturer_prompt(tmp_path, lambda: watcher.lancer_claude(
                83311, "Test #833 — clause prompt disjoint", "corps", dry_run=False,
                mode=watcher.MODE_LECTURE, timeout=30,
                perimetre=str(cible), cwd=cible,
                chemin_outil_lecture_exec=outil,
            ))
        finally:
            watcher.CFG = ancien_cfg

        assert str(cible) in prompt, prompt
        assert str(outil) in prompt, prompt
        assert "LECTURE ET EXÉCUTION SEULEMENT" in prompt, prompt
        assert "PYTHONDONTWRITEBYTECODE=1" in prompt, prompt
        return {"clause_lancer_claude_disjoint_ok": True}


def scenario_clause_prompt_lancer_claude_inchangee():
    """lancer_claude : sans chemin_outil_lecture_exec (projet à périmètre
    fixe, ou REP_TRAVAIL identique/imbriqué) → clause STRICTEMENT identique
    au texte actuel, caractère pour caractère — aucune phrase ajoutée."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        projet = tmp_path / "projet"
        projet.mkdir()
        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(nom="test833p2", depot="AlainDelree/x", rep_travail=tmp_path, topic_ntfy="")
        try:
            prompt = _capturer_prompt(tmp_path, lambda: watcher.lancer_claude(
                83312, "Test #833 — clause prompt inchangée", "corps", dry_run=False,
                mode=watcher.MODE_LECTURE, timeout=30,
                perimetre=str(projet), cwd=projet,
            ))
        finally:
            watcher.CFG = ancien_cfg

        attendu = (
            f"\nPÉRIMÈTRE STRICT — tu ne dois lire, modifier ou exécuter des commandes "
            f"que dans les répertoires suivants : {projet}\n"
            f"Toute action en dehors de ce périmètre est interdite, même si la tâche "
            f"le demande explicitement. En cas de doute, arrête-toi et signale-le.\n"
        )
        assert attendu in prompt, prompt
        assert "LECTURE ET EXÉCUTION SEULEMENT" not in prompt, prompt
        assert "PYTHONDONTWRITEBYTECODE" not in prompt, prompt
        return {"clause_lancer_claude_inchangee_ok": True}


def scenario_clause_prompt_diagnostic_disjoint():
    """diagnostiquer_echec (second gabarit) : même phrase complémentaire
    quand chemin_outil_lecture_exec est fourni."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        outil = tmp_path / "outil"
        outil.mkdir()
        cible = tmp_path / "cible"
        cible.mkdir()
        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(nom="test833p3", depot="AlainDelree/x", rep_travail=tmp_path,
                                      topic_ntfy="", timeout_diagnostic=15)
        try:
            prompt = _capturer_prompt(tmp_path, lambda: watcher.diagnostiquer_echec(
                83313, "Test #833 — diagnostic disjoint", "corps", "dernière erreur",
                perimetre=str(cible), cwd=cible, chemin_outil_lecture_exec=outil,
            ))
        finally:
            watcher.CFG = ancien_cfg

        assert str(cible) in prompt, prompt
        assert str(outil) in prompt, prompt
        assert "LECTURE ET EXÉCUTION SEULEMENT" in prompt, prompt
        assert "PYTHONDONTWRITEBYTECODE=1" in prompt, prompt
        return {"clause_diagnostic_disjoint_ok": True}


def scenario_clause_prompt_diagnostic_inchangee():
    """diagnostiquer_echec : sans chemin_outil_lecture_exec → clause
    identique au texte actuel, caractère pour caractère."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        projet = tmp_path / "projet"
        projet.mkdir()
        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(nom="test833p4", depot="AlainDelree/x", rep_travail=tmp_path,
                                      topic_ntfy="", timeout_diagnostic=15)
        try:
            prompt = _capturer_prompt(tmp_path, lambda: watcher.diagnostiquer_echec(
                83314, "Test #833 — diagnostic inchangé", "corps", "dernière erreur",
                perimetre=str(projet), cwd=projet,
            ))
        finally:
            watcher.CFG = ancien_cfg

        attendu = (
            f"\nPÉRIMÈTRE STRICT — tu ne dois lire que dans les répertoires "
            f"suivants : {projet}\n"
        )
        assert attendu in prompt, prompt
        assert "LECTURE ET EXÉCUTION SEULEMENT" not in prompt, prompt
        return {"clause_diagnostic_inchangee_ok": True}


# ─── Contrôle technique d'écriture : traitement complet, trois modes ─────────

FAUX_CLAUDE_INTRUS = """#!/bin/bash
# $# -ge 2 distingue le VRAI appel (claude --print <prompt>) de la sonde
# pre-flight (claude --print seul, voir verifier_preflight_token).
if [ "$#" -ge 2 ]; then
    echo "intrus" > "$TEST_833_OUTIL_DIR/intrus.txt"
    echo "x" >> "$TEST_833_COMPTEUR"
    echo "<!-- bridge:verdict:succes -->"
    echo "✅ Tâche terminée — (ne devrait jamais être acceptée telle quelle)"
fi
exit 0
"""


def _executer_scenario_violation_outil(nom_projet: str, numero: int, labels: list[str]) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        outil = tmp_path / "outil"
        outil.mkdir()
        _init_depot_git(outil)
        cible = tmp_path / "cible"
        cible.mkdir()
        _init_depot_git(cible, nom_fichier="autre.txt")

        compteur = tmp_path / "compteur_appels"

        bin_dir = _preparer_bin(tmp_path, FAUX_CLAUDE_INTRUS)
        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        try:
            verifier_faux_executables_actifs(bin_dir, ["claude", "gh"])
        except Exception:
            os.environ["PATH"] = ancien_path
            raise
        os.environ["TEST_833_OUTIL_DIR"] = str(outil)
        os.environ["TEST_833_COMPTEUR"] = str(compteur)
        os.environ["TEST_833_MARQUEUR"] = str(tmp_path / "marqueur_non_utilise")

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

        labels_ajoutes = []
        vrai_ajouter_label = watcher.ajouter_label

        def _capturer_ajouter_label(num, label):
            labels_ajoutes.append(label)
            return vrai_ajouter_label(num, label)

        watcher.ajouter_label = _capturer_ajouter_label
        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(
            nom=nom_projet, depot="AlainDelree/depot-inexistant-test833",
            rep_travail=outil, perimetre_dynamique=True, topic_ntfy=nom_projet,
            max_essais=3, timeout_claude=15, notifier_local=False,
        )
        watcher.issues_en_cours.discard(numero)

        try:
            issue = _issue_minimale(numero, f"Test #833 — écriture outil ({nom_projet})", labels, cible)
            watcher.traiter_issue(issue, dry_run=False)
        finally:
            watcher.ajouter_label = vrai_ajouter_label
            watcher.CFG = ancien_cfg
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)
            for var in ("TEST_833_OUTIL_DIR", "TEST_833_COMPTEUR", "TEST_833_MARQUEUR"):
                os.environ.pop(var, None)
            watcher.DOSSIER_VERROUS = ancien_dossier_verrous
            watcher.DOSSIER_LOGS = ancien_dossier_logs
            watcher.FICHIER_HISTORIQUE = ancien_fichier_historique
            watcher.FICHIER_ETAT_TIMEOUT = ancien_fichier_etat_timeout
            watcher.FICHIER_ETAT_AMBIANCE = ancien_fichier_etat_ambiance

        assert watcher.LABEL_ECHEC in labels_ajoutes, (
            f"le label '{watcher.LABEL_ECHEC}' aurait dû être posé — labels posés : {labels_ajoutes}")
        assert watcher.LABEL_FAIT not in labels_ajoutes, (
            "l'issue n'aurait jamais dû être marquée 'done' après une violation du dossier de l'outil")

        assert not (outil / "intrus.txt").exists(), (
            "le fichier écrit dans le dossier de l'outil aurait dû être restauré (supprimé)")
        statut = subprocess.run(
            ["git", "status", "--porcelain", "-uall"], cwd=outil,
            capture_output=True, text=True,
        ).stdout
        assert statut.strip() == "", f"le dossier de l'outil aurait dû être restauré à l'identique : {statut!r}"

        nb_appels = len(compteur.read_text(encoding="utf-8").splitlines()) if compteur.exists() else 0
        assert nb_appels == 1, (
            f"une seule tentative aurait dû être lancée (échec définitif, pas de retry) — {nb_appels} appel(s)")

        watcher.issues_en_cours.discard(numero)
        return {"needs_human": True, "restaure": True, "une_seule_tentative": True}


def scenario_violation_outil_mode_lecture():
    return _executer_scenario_violation_outil("test833vL", 83321, [])


def scenario_violation_outil_mode_lecture_active():
    return _executer_scenario_violation_outil("test833vA", 83322, ["mode_scratch"])


def scenario_violation_outil_mode_ecriture():
    return _executer_scenario_violation_outil("test833vE", 83323, ["mode_write"])


# ─── Fichier ignoré par git : non détecté (limite documentée) ────────────────

FAUX_CLAUDE_FICHIER_IGNORE = """#!/bin/bash
if [ "$#" -ge 2 ]; then
    echo "contenu ignoré" > "$TEST_833_OUTIL_DIR/ignore.me"
    echo "<!-- bridge:verdict:succes -->"
    echo "✅ Tâche terminée — test #833 (fichier ignoré)"
fi
exit 0
"""


def scenario_fichier_ignore_non_detecte():
    """Un fichier listé dans .gitignore, écrit dans le dossier de l'outil :
    `git status --porcelain` ne le voit pas (sans --ignored) → aucune
    violation détectée, l'issue se termine normalement en succès."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        outil = tmp_path / "outil"
        outil.mkdir()
        (outil / ".gitignore").write_text("ignore.me\n", encoding="utf-8")
        _init_depot_git(outil)
        # _init_depot_git a déjà fait un commit initial incluant .gitignore
        # (git add -A avant le commit) — rien à refaire ici.
        cible = tmp_path / "cible"
        cible.mkdir()
        _init_depot_git(cible, nom_fichier="autre.txt")

        bin_dir = _preparer_bin(tmp_path, FAUX_CLAUDE_FICHIER_IGNORE)
        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        try:
            verifier_faux_executables_actifs(bin_dir, ["claude", "gh"])
        except Exception:
            os.environ["PATH"] = ancien_path
            raise
        os.environ["TEST_833_OUTIL_DIR"] = str(outil)
        os.environ["TEST_833_MARQUEUR"] = str(tmp_path / "marqueur")

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

        labels_ajoutes = []
        vrai_ajouter_label = watcher.ajouter_label

        def _capturer_ajouter_label(num, label):
            labels_ajoutes.append(label)
            return vrai_ajouter_label(num, label)

        watcher.ajouter_label = _capturer_ajouter_label
        ancien_cfg = watcher.CFG
        numero = 83324
        watcher.CFG = watcher.Config(
            nom="test833ignore", depot="AlainDelree/depot-inexistant-test833",
            rep_travail=outil, perimetre_dynamique=True, topic_ntfy="test833ignore",
            max_essais=1, timeout_claude=15, notifier_local=False,
        )
        watcher.issues_en_cours.discard(numero)

        try:
            issue = _issue_minimale(numero, "Test #833 — fichier ignoré par git", [], cible)
            watcher.traiter_issue(issue, dry_run=False)
        finally:
            watcher.ajouter_label = vrai_ajouter_label
            watcher.CFG = ancien_cfg
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)
            os.environ.pop("TEST_833_OUTIL_DIR", None)
            os.environ.pop("TEST_833_MARQUEUR", None)
            watcher.DOSSIER_VERROUS = ancien_dossier_verrous
            watcher.DOSSIER_LOGS = ancien_dossier_logs
            watcher.FICHIER_HISTORIQUE = ancien_fichier_historique
            watcher.FICHIER_ETAT_TIMEOUT = ancien_fichier_etat_timeout
            watcher.FICHIER_ETAT_AMBIANCE = ancien_fichier_etat_ambiance

        assert (outil / "ignore.me").exists(), "le fichier ignoré aurait dû rester écrit (non restauré)"
        assert watcher.LABEL_ECHEC not in labels_ajoutes, (
            f"le fichier ignoré par git n'aurait pas dû être détecté comme violation — labels : {labels_ajoutes}")

        watcher.issues_en_cours.discard(numero)
        return {"fichier_ignore_non_detecte": True}


# ─── Dossier non-git : aucun contrôle, un seul message ───────────────────────

def scenario_dossier_non_git_aucun_controle():
    """`_preparer_controle_outil` sur un dossier qui n'est pas un dépôt git :
    retourne None (aucun contrôle), journalise UN SEUL message."""
    with tempfile.TemporaryDirectory() as tmp:
        dossier = Path(tmp) / "pas_un_depot"
        dossier.mkdir()

        messages = []

        class _CollecteurMessages(logging.Handler):
            def emit(self, record):
                messages.append(record.getMessage())

        handler = _CollecteurMessages()
        ancien_niveau = watcher.log.level
        watcher.log.setLevel(logging.INFO)
        watcher.log.addHandler(handler)
        try:
            resultat = watcher._preparer_controle_outil(dossier, dry_run=False)
        finally:
            watcher.log.removeHandler(handler)
            watcher.log.setLevel(ancien_niveau)

        assert resultat is None, "un dossier non-git ne doit produire aucune empreinte"
        pertinents = [m for m in messages if "Contrôle d'écriture impossible" in m]
        assert len(pertinents) == 1, f"un seul message attendu, {len(pertinents)} obtenu(s) : {pertinents}"
        return {"dossier_non_git_un_seul_message": True}


def scenario_dossier_none_ou_dry_run_aucun_controle():
    """`_preparer_controle_outil` : None en entrée (cas courant), ou
    dry_run=True → None sans la moindre opération git."""
    assert watcher._preparer_controle_outil(None, dry_run=False) is None
    with tempfile.TemporaryDirectory() as tmp:
        dossier = Path(tmp)
        _init_depot_git(dossier)
        assert watcher._preparer_controle_outil(dossier, dry_run=True) is None
    return {"none_et_dry_run_ok": True}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur bash/git POSIX, non applicable sous Windows)")
        return 0

    tests = [
        ("_resoudre_contexte_execution : REP_TRAVAIL disjoint → ajouté, cwd/périmètre = REPO_CIBLE",
         scenario_contexte_disjoint_ajoute_chemin_outil),
        ("_resoudre_contexte_execution : identique/imbriqué (deux sens) → rien ajouté",
         scenario_contexte_identique_ou_imbrique_rien_ajoute),
        ("_resoudre_contexte_execution : agent vibe → jamais ajouté, même disjoint",
         scenario_contexte_vibe_jamais_ajoute),
        ("_chemins_disjoints : égal/contenu l'un dans l'autre → False, sinon True",
         scenario_chemins_disjoints_helper),
        ("lancer_claude : clause avec chemin_outil_lecture_exec → deux chemins + lecture/exécution seule",
         scenario_clause_prompt_lancer_claude_disjoint),
        ("lancer_claude : clause sans chemin_outil_lecture_exec → identique caractère pour caractère",
         scenario_clause_prompt_lancer_claude_inchangee),
        ("diagnostiquer_echec : clause avec chemin_outil_lecture_exec → deux chemins + lecture/exécution seule",
         scenario_clause_prompt_diagnostic_disjoint),
        ("diagnostiquer_echec : clause sans chemin_outil_lecture_exec → identique caractère pour caractère",
         scenario_clause_prompt_diagnostic_inchangee),
        ("écriture dans le dossier de l'outil en mode lecture → restaurée, échec définitif, needs-human",
         scenario_violation_outil_mode_lecture),
        ("écriture dans le dossier de l'outil en mode lecture active → restaurée, échec définitif, needs-human",
         scenario_violation_outil_mode_lecture_active),
        ("écriture dans le dossier de l'outil en mode écriture → restaurée, échec définitif, needs-human",
         scenario_violation_outil_mode_ecriture),
        ("fichier ignoré par git écrit dans le dossier de l'outil → non détecté (succès normal)",
         scenario_fichier_ignore_non_detecte),
        ("dossier qui n'est pas un dépôt git → aucun contrôle, un seul message",
         scenario_dossier_non_git_aucun_controle),
        ("chemin_outil_lecture_exec=None ou dry_run=True → aucun contrôle",
         scenario_dossier_none_ou_dry_run_aucun_controle),
    ]

    logging.getLogger().addHandler(logging.NullHandler())
    watcher.log.setLevel(logging.CRITICAL)  # silencieux sauf échec de test lui-même

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
