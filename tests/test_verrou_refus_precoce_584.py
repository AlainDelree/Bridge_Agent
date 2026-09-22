#!/usr/bin/env python3
"""Test de non-régression — issue #584.

Contexte : issue `#583` (canal unifié for-windows, mode_write) bloquée 48
minutes — chaque cycle du watcher affichait « un autre traitement détient
déjà le verrou sur C:\\CCW_Share ». Hypothèse initialement posée : un chemin
de sortie anticipée (refus précoce, avant tout travail réel) de
`_traiter_issue_synchrone` ne relâcherait pas le verrou, faute de
`try/finally` symétrique.

Vérification par lecture de code (voir rapport de clôture de #584) :
l'hypothèse est INFIRMÉE — le `try` qui enveloppe tout le corps de
`_traiter_issue_synchrone`, verrou compris, existe depuis l'introduction même
du mécanisme (issue #189, 2026-07-20) et couvre déjà TOUS les chemins de
sortie ajoutés depuis (succès, échec après tentative(s), échec précoce avant
tout travail réel, needs-human). Les scénarios `scenario_refus_precoce_*` et
`scenario_echec_rapide_*` ci-dessous en apportent la preuve par l'exemple et
gardent cette garantie sous test de non-régression.

Cause la plus probable de l'incident réel, en revanche : un watcher tué
BRUTALEMENT (crash, kill -9, redémarrage de service — cohérent avec « erreur
de conception de l'issue elle-même, corrigée après coup côté Alain » évoqué
dans #584) pendant qu'il détenait le verrou. Aucun `try/finally` Python ne
survit à un kill -9 : c'est le rôle du filet de sécurité par péremption
(âge du verrou, issue #322) — mais celui-ci se calcule à partir de
`max_essais × TIMEOUT_projet`, potentiellement des dizaines de minutes pour
un projet à TIMEOUT élevé (1800s dans #583), expliquant un blocage de cet
ordre de grandeur. `acquerir_verrou` gagne donc ici un filet COMPLÉMENTAIRE
(issue #584) : si le PID du watcher propriétaire (champ `pid=`, toujours
présent dès la pose) est confirmé mort, le verrou est repris IMMÉDIATEMENT,
sans attendre l'écoulement de la péremption par ancienneté.
`scenario_pid_mort_*` et `scenario_pid_vivant_*` couvrent ce filet.

`gh` et `claude` sont remplacés par de faux exécutables (même technique que
tests/test_lecture_active_327.py et tests/test_orphelin_verrou_perime_322.py)
: aucun appel réseau réel.

Exécution :  python3 tests/test_verrou_refus_precoce_584.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402

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
        touch "$TEST_584_MARQUEUR"
    fi
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "view" ]; then
    if [ -n "$TEST_584_MARQUEUR" ] && [ -f "$TEST_584_MARQUEUR" ]; then
        echo '{"comments":[{"body":"<!-- bridge:resultat -->\\nfake"}]}'
    else
        echo '{"comments":[]}'
    fi
    exit 0
fi
exit 0
"""

# $# -ge 2 distingue le VRAI appel (claude --print [--dangerously-skip-permissions]
# <prompt>) de la sonde pre-flight (claude --print, sans prompt positionnel,
# voir verifier_preflight_token) — la sonde ne doit produire aucun effet de bord.
FAUX_CLAUDE_REFUS_PRECOCE = """#!/bin/bash
if [ "$#" -ge 2 ]; then
    echo "❌ Tâche non réalisable — hors périmètre (fichiers hors C:\\\\CCW_Share). Aucune action effectuée."
    exit 0
fi
exit 0
"""

FAUX_CLAUDE_ECHEC_RAPIDE = """#!/bin/bash
if [ "$#" -ge 2 ]; then
    echo "erreur : hors périmètre" >&2
    exit 1
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


def _init_depot_git(rep: Path) -> None:
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


def _isoler_etat(tmp_path: Path, nom: str, rep_travail: Path, **kwargs_config):
    """Isole DOSSIER_VERROUS/DOSSIER_LOGS/fichiers d'état, comme dans
    test_lecture_active_327.py — jamais dans le vrai logs/ du dépôt. Retourne
    un dict des anciennes valeurs, à restaurer par l'appelant."""
    anciens = {
        "DOSSIER_VERROUS": watcher.DOSSIER_VERROUS,
        "DOSSIER_LOGS": watcher.DOSSIER_LOGS,
        "FICHIER_HISTORIQUE": watcher.FICHIER_HISTORIQUE,
        "FICHIER_ETAT_TIMEOUT": watcher.FICHIER_ETAT_TIMEOUT,
        "FICHIER_ETAT_AMBIANCE": watcher.FICHIER_ETAT_AMBIANCE,
        "CFG": watcher.CFG,
    }
    watcher.DOSSIER_VERROUS = tmp_path / "verrous"
    watcher.DOSSIER_LOGS = tmp_path / "logs"
    watcher.FICHIER_HISTORIQUE = watcher.DOSSIER_LOGS / "historique_durees.json"
    watcher.FICHIER_ETAT_TIMEOUT = watcher.DOSSIER_LOGS / "etat_timeout.json"
    watcher.FICHIER_ETAT_AMBIANCE = watcher.DOSSIER_LOGS / "etat_ambiance.json"
    watcher.CFG = watcher.Config(
        nom=nom, depot="AlainDelree/depot-inexistant-test584",
        rep_travail=rep_travail, topic_ntfy=nom, notifier_local=False,
        **kwargs_config,
    )
    return anciens


def _restaurer_etat(anciens: dict) -> None:
    watcher.DOSSIER_VERROUS = anciens["DOSSIER_VERROUS"]
    watcher.DOSSIER_LOGS = anciens["DOSSIER_LOGS"]
    watcher.FICHIER_HISTORIQUE = anciens["FICHIER_HISTORIQUE"]
    watcher.FICHIER_ETAT_TIMEOUT = anciens["FICHIER_ETAT_TIMEOUT"]
    watcher.FICHIER_ETAT_AMBIANCE = anciens["FICHIER_ETAT_AMBIANCE"]
    watcher.CFG = anciens["CFG"]


def scenario_refus_precoce_libere_verrou():
    """Une tâche mode_write qui échoue par refus précoce (claude répond ❌ en
    quelques instants, AVANT tout travail réel, exit code 0) doit relâcher le
    verrou aussi proprement qu'une tâche qui réussit — appel direct de
    `_traiter_issue_synchrone` (le worker qui pose/relâche le verrou), même
    chemin que le canal unifié for-windows mode_write, sans la complexité du
    dispatch worktree de `traiter_issue` (hors sujet ici)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "CCW_Share"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        bin_dir = _preparer_bin(tmp_path, FAUX_CLAUDE_REFUS_PRECOCE)
        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        os.environ["TEST_584_MARQUEUR"] = str(tmp_path / "marqueur_resultat")

        anciens = _isoler_etat(tmp_path, "test584a", rep_travail, max_essais=3, timeout_claude=15)
        watcher.issues_en_cours.discard(9583)

        try:
            issue = _issue_minimale(9583, "Test #584 — refus précoce", ["mode_write"])
            watcher._traiter_issue_synchrone(issue, dry_run=False)
        finally:
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)
            os.environ.pop("TEST_584_MARQUEUR", None)
            _restaurer_etat(anciens)

        verrou = watcher._chemin_verrou(rep_travail)
        assert not verrou.exists(), (
            f"le verrou {verrou} n'a PAS été relâché après un refus précoce — "
            f"reproduit le blocage de #583."
        )
        return {"verrou_relache": True}


def scenario_echec_rapide_sans_travail_libere_verrou():
    """Une tâche mode_write qui échoue rapidement de façon répétée (exit non
    nul dès la première tentative, avant tout travail réel) jusqu'à
    l'abandon définitif (needs-human) doit elle aussi relâcher le verrou."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "CCW_Share"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        bin_dir = _preparer_bin(tmp_path, FAUX_CLAUDE_ECHEC_RAPIDE)
        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        os.environ["TEST_584_MARQUEUR"] = str(tmp_path / "marqueur_non_utilise")

        anciens = _isoler_etat(tmp_path, "test584b", rep_travail, max_essais=1, timeout_claude=15)
        watcher.issues_en_cours.discard(9584)

        labels_ajoutes = []
        vrai_ajouter_label = watcher.ajouter_label

        def _capturer_ajouter_label(numero, label):
            labels_ajoutes.append(label)
            return vrai_ajouter_label(numero, label)

        watcher.ajouter_label = _capturer_ajouter_label

        try:
            issue = _issue_minimale(9584, "Test #584 — échec rapide répété", ["mode_write"])
            watcher._traiter_issue_synchrone(issue, dry_run=False)
        finally:
            watcher.ajouter_label = vrai_ajouter_label
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)
            os.environ.pop("TEST_584_MARQUEUR", None)
            _restaurer_etat(anciens)

        assert watcher.LABEL_ECHEC in labels_ajoutes, (
            f"le label '{watcher.LABEL_ECHEC}' aurait dû être posé — labels posés : {labels_ajoutes}")

        verrou = watcher._chemin_verrou(rep_travail)
        assert not verrou.exists(), (
            f"le verrou {verrou} n'a PAS été relâché après un abandon définitif — "
            f"bloquerait toute autre issue mode_write sur le même REP_TRAVAIL."
        )
        return {"verrou_relache": True}


def _attendre_mort(pid: int, delai_max: float = 5.0) -> bool:
    fin = time.monotonic() + delai_max
    while time.monotonic() < fin:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def scenario_pid_mort_repris_immediatement():
    """Filet complémentaire (issue #584) : un verrou encore JEUNE (âge très
    inférieur à la péremption) mais dont le PID propriétaire (champ `pid=`)
    est confirmé mort doit être repris IMMÉDIATEMENT — sans attendre
    l'écoulement de la péremption par ancienneté. Reproduit le cas d'un
    watcher tué brutalement pendant qu'il détenait le verrou."""
    if os.name == "nt":
        print("  (ignoré : sonde POSIX os.kill utilisée pour garantir un PID mort déterministe)")
        return {"ignore": True}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        anciens = _isoler_etat(tmp_path, "test584c", tmp_path, max_essais=3, timeout_claude=1800)

        # PID garanti mort : on lance puis on tue un vrai process, on attend
        # sa disparition effective avant de l'utiliser (même technique que
        # tests/test_orphelin_verrou_perime_322.py).
        proc_ephemere = subprocess.Popen(["sleep", "30"])
        pid_mort = proc_ephemere.pid
        proc_ephemere.kill()
        proc_ephemere.wait(timeout=5)
        assert _attendre_mort(pid_mort, delai_max=5.0)

        try:
            verrou = watcher._chemin_verrou(tmp_path)
            verrou.parent.mkdir(parents=True, exist_ok=True)
            verrou.write_text(f"pid={pid_mort} projet=test584c rep={tmp_path}\n", encoding="utf-8")
            # Verrou tout frais (mtime = maintenant) : très loin de la
            # péremption par ancienneté (max_essais=3 × timeout=1800s, soit
            # des dizaines de minutes) — seule la sonde PID peut expliquer sa
            # reprise ici.

            resultat = watcher.acquerir_verrou(tmp_path, 1800)

            assert resultat == verrou, (
                f"un verrou frais mais orphelin (PID propriétaire {pid_mort} confirmé mort) "
                f"aurait dû être repris immédiatement, sans attendre la péremption par "
                f"ancienneté : {resultat}"
            )
        finally:
            watcher.liberer_verrou(watcher._chemin_verrou(tmp_path))
            _restaurer_etat(anciens)

        return {"pid_mort": pid_mort}


def scenario_pid_vivant_reste_bloque():
    """Non-régression du filet #584 : un verrou frais dont le PID propriétaire
    est bien VIVANT reste bloquant, exactement comme avant cette issue — la
    sonde PID ne doit jamais accélérer la reprise d'un verrou réellement
    détenu."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        anciens = _isoler_etat(tmp_path, "test584d", tmp_path, max_essais=3, timeout_claude=1800)

        try:
            verrou = watcher._chemin_verrou(tmp_path)
            verrou.parent.mkdir(parents=True, exist_ok=True)
            # PID vivant garanti : celui-ci-même (process du test).
            verrou.write_text(f"pid={os.getpid()} projet=test584d rep={tmp_path}\n", encoding="utf-8")

            resultat = watcher.acquerir_verrou(tmp_path, 1800)

            assert resultat is None, (
                f"un verrou dont le PID propriétaire est bien vivant n'aurait "
                f"jamais dû être repris : {resultat}"
            )
        finally:
            _restaurer_etat(anciens)
            try:
                verrou.unlink()
            except FileNotFoundError:
                pass

        return {}


def main():
    tests = [
        ("refus précoce (❌, exit 0, avant tout travail réel) → verrou relâché",
         scenario_refus_precoce_libere_verrou),
        ("échec rapide répété → abandon définitif → verrou relâché",
         scenario_echec_rapide_sans_travail_libere_verrou),
        ("verrou frais + PID propriétaire mort → repris immédiatement",
         scenario_pid_mort_repris_immediatement),
        ("verrou frais + PID propriétaire vivant → reste bloquant",
         scenario_pid_vivant_reste_bloque),
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
