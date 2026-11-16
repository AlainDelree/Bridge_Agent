#!/usr/bin/env python3
"""Test de la route GET /avancement/<projet>/<numero> (issue #887) : bouton
« Avancement » d'une issue en cours — commits + fichiers (committés/non
committés) du worktree dédié à cette issue, strictement en lecture.

Couvre les cas dégradés demandés par l'issue (message clair plutôt qu'un
échec) : issue en lecture seule ou en lecture active (aucun worktree de
projet à montrer), issue for-windows (machine CCW, non prise en charge dans
cette étape, sans SSH), worktree introuvable/déjà nettoyé — ainsi que le cas
nominal (mode_write, worktree réel, commits/fichiers committés et non
committés) sur un VRAI dépôt git jetable (comme test_inventaire_fichiers_788.
py), et la propriété centrale de l'issue #887 : le worktree d'une issue EN
COURS (donc verrouillée) est quand même retrouvé — à la différence du
mécanisme de RELANCE (_trouver_worktree_reutilisable, issue #725), qui
l'exclurait.

Exécution :  python3 -m pytest tests/test_avancement_887.py
"""

import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from flask import Flask

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import app.avancement as av  # noqa: E402
import watcher  # noqa: E402

APP = Flask(__name__)  # app minimale : jsonify exige un contexte applicatif.


def _git(rep, *args, check=True):
    return subprocess.run(["git", *args], cwd=rep, check=check,
                           capture_output=True, text=True)


def _init_depot(rep: Path) -> None:
    _git(rep, "init", "-q", "-b", "master")
    _git(rep, "config", "user.email", "t@t")
    _git(rep, "config", "user.name", "t")


def _appeler(nom_projet, numero, labels=None):
    chemin = f"/avancement/{nom_projet}/{numero}"
    if labels is not None:
        chemin += "?labels=" + ",".join(labels)
    with APP.test_request_context(chemin):
        reponse = av.avancement_issue(nom_projet, numero)
    if isinstance(reponse, tuple):
        corps, statut = reponse
        return corps.get_json(), statut
    return reponse.get_json(), 200


# ─── Erreurs de base ────────────────────────────────────────────────────────

def test_projet_introuvable(monkeypatch):
    monkeypatch.setattr(av, "projet_par_nom", lambda nom: None)
    corps, statut = _appeler("inexistant", "42")
    assert statut == 404
    assert "introuvable" in corps["erreur"].lower()


def test_numero_invalide(tmp_path, monkeypatch):
    monkeypatch.setattr(av, "projet_par_nom",
                         lambda nom: SimpleNamespace(nom="p", rep_travail=tmp_path))
    corps, statut = _appeler("p", "pas-un-numero")
    assert statut == 400
    assert "invalide" in corps["erreur"].lower()


# ─── Cas dégradés (issue #887, point 4) — message clair, jamais un échec ───

def test_lecture_seule_aucun_worktree_a_montrer(tmp_path, monkeypatch):
    monkeypatch.setattr(av, "projet_par_nom",
                         lambda nom: SimpleNamespace(nom="p", rep_travail=tmp_path))
    corps, statut = _appeler("p", "42", labels=["for-linux", "done"])
    assert statut == 200
    assert corps["disponible"] is False
    assert corps["raison"] == "lecture_seule"
    assert corps["message"]


def test_lecture_active_mode_scratch_aucun_worktree_a_montrer(tmp_path, monkeypatch):
    monkeypatch.setattr(av, "projet_par_nom",
                         lambda nom: SimpleNamespace(nom="p", rep_travail=tmp_path))
    corps, statut = _appeler("p", "42", labels=["for-linux", "mode_scratch"])
    assert statut == 200
    assert corps["disponible"] is False
    assert corps["raison"] == "lecture_active"


def test_for_windows_ccw_non_pris_en_charge_sans_ssh(tmp_path, monkeypatch):
    monkeypatch.setattr(av, "projet_par_nom",
                         lambda nom: SimpleNamespace(nom="p", rep_travail=tmp_path))
    # Même avec mode_write : for-windows prime, aucune tentative SSH.
    corps, statut = _appeler("p", "42", labels=["for-windows", "mode_write"])
    assert statut == 200
    assert corps["disponible"] is False
    assert corps["raison"] == "ccw"
    assert "ccw" in corps["message"].lower() or "windows" in corps["message"].lower()


def test_mode_write_worktree_introuvable_ou_deja_nettoye(tmp_path, monkeypatch):
    _init_depot(tmp_path)
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    monkeypatch.setattr(av, "projet_par_nom",
                         lambda nom: SimpleNamespace(nom="p", rep_travail=tmp_path))
    corps, statut = _appeler("p", "999", labels=["for-linux", "mode_write"])
    assert statut == 200
    assert corps["disponible"] is False
    assert corps["raison"] == "worktree_introuvable"


def test_rep_travail_introuvable(tmp_path, monkeypatch):
    monkeypatch.setattr(av, "projet_par_nom",
                         lambda nom: SimpleNamespace(nom="p", rep_travail=tmp_path / "absent"))
    corps, statut = _appeler("p", "42", labels=["for-linux", "mode_write"])
    assert statut == 404
    assert "introuvable" in corps["erreur"].lower()


# ─── Cas nominal : worktree réel, commits + fichiers committés/non committés ─

def _preparer_depot_avec_worktree(tmp_path: Path, numero: int = 42, nom_projet: str = "principal"):
    rep = tmp_path / nom_projet
    rep.mkdir()
    _init_depot(rep)
    (rep / "a.txt").write_text("ligne1\n", encoding="utf-8")
    _git(rep, "add", "-A")
    _git(rep, "commit", "-q", "-m", "initial")

    # Nom standard attendu par _candidats_worktree_issue (watcher.py) :
    # <nom_projet>-issue<numero> — ni la branche NI le simple contenu ne
    # suffisent à être reconnu comme worktree de cette issue.
    wt = tmp_path / f"{nom_projet}-issue{numero}"
    _git(rep, "worktree", "add", "-q", "-b", f"worktree-issue-{numero}", str(wt))

    (wt / "a.txt").write_text("ligne1\nligne2\n", encoding="utf-8")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", "fix dans le worktree")
    (wt / "nouveau.txt").write_text("contenu\n", encoding="utf-8")
    (wt / "a.txt").write_text("ligne1\nligne2\nligne3\n", encoding="utf-8")
    return rep, wt


def test_mode_write_avec_worktree_commits_et_fichiers(tmp_path, monkeypatch):
    rep, wt = _preparer_depot_avec_worktree(tmp_path, numero=42)
    monkeypatch.setattr(av, "projet_par_nom",
                         lambda nom: SimpleNamespace(nom="principal", rep_travail=rep))
    corps, statut = _appeler("principal", "42", labels=["for-linux", "mode_write"])
    assert statut == 200
    assert corps["disponible"] is True
    assert corps["branche"] == "worktree-issue-42"
    assert corps["branche_base"] == "master"
    assert corps["chemin"] == str(wt)

    assert len(corps["commits"]) == 1
    assert corps["commits"][0]["message"] == "fix dans le worktree"
    assert len(corps["commits"][0]["hash"]) >= 7
    assert isinstance(corps["commits"][0]["horodatage"], int)

    committes = {f["chemin"]: f for f in corps["fichiers_committes"]}
    assert committes["a.txt"]["ajoutees"] == 1
    assert committes["a.txt"]["supprimees"] == 0

    non_committes = {f["chemin"]: f for f in corps["fichiers_non_committes"]}
    assert non_committes["a.txt"]["ajoutees"] == 1          # ligne3 ajoutée, non committée
    assert non_committes["nouveau.txt"]["statut"] == "non suivi"
    assert non_committes["nouveau.txt"]["ajoutees"] == 1

    assert corps["derniere_activite"] is not None


def test_mode_write_sans_defaut_labels_retombe_sur_recherche_worktree(tmp_path, monkeypatch):
    """Sans paramètre `labels` du tout (appel direct, ex. test ou ancien
    appelant) : comportement de repli, tente quand même de retrouver un
    worktree mode_write plutôt que de supposer lecture seule."""
    rep, wt = _preparer_depot_avec_worktree(tmp_path, numero=7)
    monkeypatch.setattr(av, "projet_par_nom",
                         lambda nom: SimpleNamespace(nom="principal", rep_travail=rep))
    corps, statut = _appeler("principal", "7", labels=None)
    assert statut == 200
    assert corps["disponible"] is True


def test_working_tree_propre_aucun_fichier_non_committe(tmp_path, monkeypatch):
    rep = tmp_path / "principal"
    rep.mkdir()
    _init_depot(rep)
    (rep / "a.txt").write_text("x\n", encoding="utf-8")
    _git(rep, "add", "-A")
    _git(rep, "commit", "-q", "-m", "initial")
    wt = tmp_path / "principal-issue5"
    _git(rep, "worktree", "add", "-q", "-b", "worktree-issue-5", str(wt))
    (wt / "a.txt").write_text("x\ny\n", encoding="utf-8")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", "fix")

    monkeypatch.setattr(av, "projet_par_nom",
                         lambda nom: SimpleNamespace(nom="principal", rep_travail=rep))
    corps, statut = _appeler("principal", "5", labels=["mode_write"])
    assert statut == 200
    assert corps["fichiers_non_committes"] == []
    assert len(corps["commits"]) == 1


# ─── Propriété centrale de l'issue #887 : lecture, pas affectée par le
# verrou qui protège justement l'issue EN COURS ─────────────────────────────

def test_worktree_verrouille_par_traitement_en_cours_est_quand_meme_lu(tmp_path, monkeypatch):
    """Le bouton Avancement doit retrouver le worktree d'une issue
    ACTUELLEMENT en cours, donc verrouillée (watcher._chemin_verrou posé par
    le traitement en cours) — à la différence de
    watcher._trouver_worktree_reutilisable (RELANCE, issue #725), qui
    l'exclurait précisément parce qu'il est occupé."""
    rep, wt = _preparer_depot_avec_worktree(tmp_path, numero=42)
    cfg = SimpleNamespace(nom="principal", rep_travail=rep)
    monkeypatch.setattr(av, "projet_par_nom", lambda nom: cfg)

    verrou = watcher._chemin_verrou(wt)
    verrou.parent.mkdir(parents=True, exist_ok=True)
    verrou.write_text(f"pid={__import__('os').getpid()}\n", encoding="utf-8")
    try:
        # Démonstration contraire : RELANCE (_trouver_worktree_reutilisable)
        # exclurait ce worktree verrouillé — confirme que le test porte sur
        # le bon contraste, pas sur une coïncidence.
        ancien_cfg = watcher.CFG
        watcher.CFG = cfg
        try:
            assert watcher._trouver_worktree_reutilisable(42) is None
        finally:
            watcher.CFG = ancien_cfg

        corps, statut = _appeler("principal", "42", labels=["mode_write"])
        assert statut == 200
        assert corps["disponible"] is True
        assert corps["chemin"] == str(wt)
    finally:
        verrou.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(subprocess.run(
        [sys.executable, "-m", "pytest", "-q", __file__]).returncode)
