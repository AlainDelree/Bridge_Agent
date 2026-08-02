#!/usr/bin/env python3
"""Test de non-régression — issue #327 : implémentation du mode « lecture
active » (mode_scratch), préparé côté formulaire/en-tête par #326 mais pas
encore fonctionnel côté watcher.

Vérifie :
- `_deduire_mode` déduit correctement le MODE à trois valeurs des labels
  GitHub d'une issue (mode_write → ecriture, mode_scratch seul →
  lecture_active, aucun des deux → lecture, les deux → l'écriture l'emporte).
- `_chemin_scratch` valide strictement le nom de projet (aucun '../',
  aucune remontée hors de /tmp) et dérive le chemin attendu.
- Un traitement complet en lecture active (`traiter_issue`) qui n'écrit QUE
  dans le dossier scratch : succès, REP_TRAVAIL inchangé, scratch nettoyé.
- Un traitement complet en lecture active qui écrit dans REP_TRAVAIL (hors
  scratch) : détecté par le garde-fou niveau 2, restauré, issue marquée en
  échec (`needs-human`), jamais fermée/marquée `done`.

`gh` et `claude` sont tous deux remplacés par de faux exécutables (même
technique que tests/test_nettoyage_arbre_247.py et
tests/test_orphelin_verrou_perime_322.py) : aucun appel réseau réel. Le faux
`gh` est minimal mais STATEFUL sur `issue view --json comments` (via un
fichier marqueur passé par variable d'environnement) : nécessaire pour que
`commenter_resultat_avec_retry` (qui relit l'issue pour confirmer la
présence du commentaire, issue #237) fonctionne dans le scénario de succès.

Exécution :  python3 tests/test_lecture_active_327.py
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

FAUX_GH = """#!/bin/bash
# Faux `gh` — issue #327. Stateful uniquement sur `issue view --json comments`
# (marqueur touché par `issue comment` quand le body contient MARQUEUR_RESULTAT).
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
        touch "$TEST_327_MARQUEUR"
    fi
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "view" ]; then
    if [ -n "$TEST_327_MARQUEUR" ] && [ -f "$TEST_327_MARQUEUR" ]; then
        echo '{"comments":[{"body":"<!-- bridge:resultat -->\\nfake"}]}'
    else
        echo '{"comments":[]}'
    fi
    exit 0
fi
exit 0
"""


def _preparer_bin(tmp_path: Path, script_claude: str) -> Path:
    """Écrit de faux `claude` et `gh` exécutables dans tmp_path/bin, retourne
    ce dossier (à préfixer au PATH)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)

    claude_path = bin_dir / "claude"
    claude_path.write_text(script_claude, encoding="utf-8")
    claude_path.chmod(claude_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    gh_path = bin_dir / "gh"
    gh_path.write_text(FAUX_GH, encoding="utf-8")
    gh_path.chmod(gh_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return bin_dir


def _init_depot_git(rep: Path) -> None:
    """Dépôt git minimal avec un commit initial, pour que
    `_statut_git_rep_travail` ait un HEAD contre lequel comparer."""
    subprocess.run(["git", "init", "-q", "-b", "master", str(rep)], check=True)
    (rep / "fichier.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=rep, check=True, capture_output=True)


def _issue_minimale(numero: int, titre: str, labels: list[str]) -> dict:
    return {
        "number": numero,
        "title": titre,
        "body": "| PRIORITE | normale |\n| TIMEOUT | 30s |\n",
        "labels": [{"name": lab} for lab in labels],
    }


def scenario_deduction_mode():
    """_deduire_mode (issue #327) : priorité mode_write > mode_scratch >
    lecture seule par défaut."""
    assert watcher._deduire_mode(["mode_write"]) == watcher.MODE_ECRITURE
    assert watcher._deduire_mode(["mode_scratch"]) == watcher.MODE_LECTURE_ACTIVE
    assert watcher._deduire_mode([]) == watcher.MODE_LECTURE
    assert watcher._deduire_mode(["for-linux", "notif_pc"]) == watcher.MODE_LECTURE
    # Les deux labels posés à la fois (erreur) : l'écriture l'emporte, comme
    # l'ancien comportement où seul LABEL_ECRITURE testait autoriser_ecriture.
    assert watcher._deduire_mode(["mode_write", "mode_scratch"]) == watcher.MODE_ECRITURE
    return {}


def scenario_chemin_scratch_valide_et_invalide():
    """_chemin_scratch (issue #327) : dérivé de CFG.nom, validation stricte
    (aucun séparateur, aucune remontée hors de /tmp)."""
    chemin = watcher._chemin_scratch("bridge_agent")
    assert chemin == Path(tempfile.gettempdir()) / "bridge_scratch_bridge_agent", chemin

    for nom_invalide in ("", "../etc", "a/b", "a\\b", "..", "a b"):
        try:
            watcher._chemin_scratch(nom_invalide)
        except ValueError:
            continue
        raise AssertionError(f"nom de projet {nom_invalide!r} aurait dû être refusé")
    return {}


def scenario_lecture_active_ecrit_scratch_uniquement():
    """Lecture active qui n'écrit QUE dans le scratch : succès, REP_TRAVAIL
    inchangé (git status vide après restauration niveau 2 — rien à
    restaurer), scratch nettoyé (finally de traiter_issue)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        marqueur = tmp_path / "marqueur_resultat"

        # Le faux claude écrit un fichier DANS le scratch (chemin déterministe,
        # calculé indépendamment ci-dessous) puis répond succès — simule un
        # linter qui a eu besoin d'un fichier de config sur disque.
        chemin_scratch_attendu = watcher._chemin_scratch("test327c")
        script_claude = f"""#!/bin/bash
# $# -ge 2 distingue le VRAI appel (claude --print <prompt>) de la sonde
# pre-flight (claude --print, sans prompt positionnel, voir
# verifier_preflight_token) — la sonde ne doit produire aucun effet de bord.
if [ "$#" -ge 2 ]; then
    echo "config" > {chemin_scratch_attendu}/eslint.config.js
    echo "✅ Tâche terminée — lecture active OK"
fi
exit 0
"""
        bin_dir = _preparer_bin(tmp_path, script_claude)
        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        os.environ["TEST_327_MARQUEUR"] = str(marqueur)

        ancien_dossier_verrous = watcher.DOSSIER_VERROUS
        watcher.DOSSIER_VERROUS = tmp_path / "verrous"
        watcher.CFG = watcher.Config(
            nom="test327c", depot="AlainDelree/depot-inexistant-test327",
            rep_travail=rep_travail, topic_ntfy="test327c",
            max_essais=1, timeout_claude=15, notifier_local=False,
        )
        watcher.issues_en_cours.discard(9327)

        try:
            issue = _issue_minimale(9327, "Test #327 — scratch OK", ["mode_scratch"])
            watcher.traiter_issue(issue, dry_run=False)
        finally:
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)
            os.environ.pop("TEST_327_MARQUEUR", None)
            watcher.DOSSIER_VERROUS = ancien_dossier_verrous

        assert not chemin_scratch_attendu.exists(), (
            f"le dossier scratch {chemin_scratch_attendu} aurait dû être nettoyé en fin de traitement")

        statut = subprocess.run(
            ["git", "status", "--porcelain"], cwd=rep_travail,
            capture_output=True, text=True,
        ).stdout
        assert statut.strip() == "", f"REP_TRAVAIL aurait dû rester inchangé : {statut!r}"

        assert (rep_travail / "fichier.txt").read_text(encoding="utf-8") == "original\n"

        return {"scratch_nettoye": True, "projet_inchange": True}


def scenario_lecture_active_ecrit_dans_projet_restauree():
    """Lecture active qui tente d'écrire dans REP_TRAVAIL (hors scratch) :
    détecté par le garde-fou niveau 2, restauré, issue marquée en échec
    (needs-human) — jamais fermée ni marquée 'done'."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        # Le faux claude viole la consigne de confinement : modifie un fichier
        # suivi ET crée un fichier neuf, tous les deux DANS REP_TRAVAIL (cwd).
        script_claude = """#!/bin/bash
# $# -ge 2 distingue le VRAI appel (claude --print <prompt>) de la sonde
# pre-flight (voir verifier_preflight_token) — la sonde ne doit produire
# aucun effet de bord.
if [ "$#" -ge 2 ]; then
    echo "hack" > fichier.txt
    echo "malveillant" > malveillant.txt
    echo "✅ Tâche terminée — (ne devrait jamais être acceptée telle quelle)"
fi
exit 0
"""
        bin_dir = _preparer_bin(tmp_path, script_claude)
        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        os.environ["TEST_327_MARQUEUR"] = str(tmp_path / "marqueur_non_utilise")

        ancien_dossier_verrous = watcher.DOSSIER_VERROUS
        watcher.DOSSIER_VERROUS = tmp_path / "verrous"

        labels_ajoutes = []
        vrai_ajouter_label = watcher.ajouter_label

        def _capturer_ajouter_label(numero, label):
            labels_ajoutes.append(label)
            return vrai_ajouter_label(numero, label)

        watcher.ajouter_label = _capturer_ajouter_label
        watcher.CFG = watcher.Config(
            nom="test327d", depot="AlainDelree/depot-inexistant-test327",
            rep_travail=rep_travail, topic_ntfy="test327d",
            max_essais=3, timeout_claude=15, notifier_local=False,
        )
        watcher.issues_en_cours.discard(9328)

        try:
            issue = _issue_minimale(9328, "Test #327 — écriture hors scratch", ["mode_scratch"])
            watcher.traiter_issue(issue, dry_run=False)
        finally:
            watcher.ajouter_label = vrai_ajouter_label
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)
            os.environ.pop("TEST_327_MARQUEUR", None)
            watcher.DOSSIER_VERROUS = ancien_dossier_verrous

        assert watcher.LABEL_ECHEC in labels_ajoutes, (
            f"le label '{watcher.LABEL_ECHEC}' aurait dû être posé — labels posés : {labels_ajoutes}")
        assert watcher.LABEL_FAIT not in labels_ajoutes, (
            "l'issue n'aurait jamais dû être marquée 'done' après une violation niveau 2")

        assert (rep_travail / "fichier.txt").read_text(encoding="utf-8") == "original\n", (
            "le fichier suivi modifié hors scratch aurait dû être restauré à son contenu d'origine")
        assert not (rep_travail / "malveillant.txt").exists(), (
            "le fichier neuf créé hors scratch aurait dû être supprimé par la restauration"
        )

        statut = subprocess.run(
            ["git", "status", "--porcelain"], cwd=rep_travail,
            capture_output=True, text=True,
        ).stdout
        assert statut.strip() == "", f"REP_TRAVAIL aurait dû être restauré à l'identique : {statut!r}"

        assert 9328 not in watcher.issues_en_cours, "l'issue aurait dû être retirée de issues_en_cours"

        return {"restaure": True, "needs_human": True}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur bash/git POSIX, non applicable sous Windows)")
        return 0

    tests = [
        ("_deduire_mode : priorité mode_write > mode_scratch > lecture", scenario_deduction_mode),
        ("_chemin_scratch : dérivation + validation stricte du nom de projet", scenario_chemin_scratch_valide_et_invalide),
        ("lecture active écrivant uniquement dans le scratch → succès, projet inchangé, scratch nettoyé",
         scenario_lecture_active_ecrit_scratch_uniquement),
        ("lecture active écrivant dans le projet hors scratch → détecté, restauré, échec (needs-human)",
         scenario_lecture_active_ecrit_dans_projet_restauree),
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
