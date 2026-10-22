#!/usr/bin/env python3
"""Test de la route /inventaire-commit (issue #788) : la case à cocher de
l'onglet Résultats ajoute désormais au texte copié une section « Fichiers
modifiés » — statut + lignes +/- par fichier, SANS le contenu du patch — pour
qu'un rapport d'agent inexact (ex. accents perdus dans un fichier réécrit
entier) soit visible avant la fusion.

Le bouton Diff existant (`diff_commit`, `--stat --patch`) rend mal les
suppressions/renommages (constat de l'issue) : cette route repart de
`git show --name-status`/`--numstat` en mode `-z` (séparateurs NUL), couvert
ici sur un VRAI dépôt git jetable (ajout, modification, renommage,
suppression, fichier binaire, commit vide) plutôt que sur des chaînes NUL
construites à la main — pour que le test casse si git change ce format,
plutôt que de valider une hypothèse qui ne correspond plus à la réalité.

Exécution :  python3 -m pytest tests/test_inventaire_fichiers_788.py
"""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from flask import Flask

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import app.issues as issues  # noqa: E402

APP = Flask(__name__)  # app minimale : jsonify exige un contexte applicatif,
                        # pas besoin de create_app() (routes/watchers/etc.)


def _git(rep, *args, check=True):
    return subprocess.run(["git", *args], cwd=rep, check=check,
                           capture_output=True, text=True)


def _init_depot(rep: Path) -> None:
    _git(rep, "init", "-q", "-b", "master")
    _git(rep, "config", "user.email", "t@t")
    _git(rep, "config", "user.name", "t")


def _hash_tete(rep: Path) -> str:
    return _git(rep, "rev-parse", "HEAD").stdout.strip()


def _appeler(nom_projet, hash_commit):
    with APP.app_context():
        reponse = issues.inventaire_commit(nom_projet, hash_commit)
    if isinstance(reponse, tuple):
        corps, statut = reponse
        return corps.get_json(), statut
    return reponse.get_json(), 200


def test_projet_introuvable(monkeypatch):
    monkeypatch.setattr(issues, "projet_par_nom", lambda nom: None)
    corps, statut = _appeler("inexistant", "abc1234")
    assert statut == 404
    assert "introuvable" in corps["erreur"].lower()


def test_hash_invalide(tmp_path, monkeypatch):
    monkeypatch.setattr(issues, "projet_par_nom",
                         lambda nom: SimpleNamespace(rep_travail=tmp_path))
    corps, statut = _appeler("p", "pas-un-hash; rm -rf /")
    assert statut == 400
    assert "invalide" in corps["erreur"].lower()


def test_repertoire_travail_introuvable(tmp_path, monkeypatch):
    monkeypatch.setattr(issues, "projet_par_nom",
                         lambda nom: SimpleNamespace(rep_travail=tmp_path / "absent"))
    corps, statut = _appeler("p", "abc1234")
    assert statut == 404
    assert "introuvable" in corps["erreur"].lower()


def test_commit_introuvable(tmp_path, monkeypatch):
    _init_depot(tmp_path)
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    monkeypatch.setattr(issues, "projet_par_nom",
                         lambda nom: SimpleNamespace(rep_travail=tmp_path))
    corps, statut = _appeler("p", "0000000")
    # Même contrat d'erreur que diff_commit : le message git brut (stderr)
    # prime sur le message par défaut quand git en produit un.
    assert statut == 404
    assert corps["erreur"]


def test_commit_vide_sauvegarde_aucun_fichier(tmp_path, monkeypatch):
    """Commit `--allow-empty` (sauvegarde) : liste vide, pas d'erreur — le
    client (resultats_coches.js) l'affiche comme « aucun fichier », jamais en
    silence total ni en échec."""
    _init_depot(tmp_path)
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "avant-correctif")
    monkeypatch.setattr(issues, "projet_par_nom",
                         lambda nom: SimpleNamespace(rep_travail=tmp_path))
    corps, statut = _appeler("p", _hash_tete(tmp_path))
    assert statut == 200
    assert corps["fichiers"] == []


def test_ajout_modification_suppression_renommage_binaire(tmp_path, monkeypatch):
    _init_depot(tmp_path)
    (tmp_path / "a.txt").write_text("ligne1\nligne2\nligne3\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("à garder\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "initial")

    # Un seul commit qui combine : modification, renommage, suppression,
    # ajout texte et ajout binaire — l'inventaire doit TOUT distinguer.
    (tmp_path / "a.txt").write_text("ligne1\nligne2\nligne3\nligne4\n", encoding="utf-8")
    _git(tmp_path, "mv", "b.txt", "c.txt")
    (tmp_path / "nouveau.txt").write_text("contenu\n", encoding="utf-8")
    (tmp_path / "img.bin").write_bytes(bytes([0, 1, 2, 3, 255]))
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "correctif")

    monkeypatch.setattr(issues, "projet_par_nom",
                         lambda nom: SimpleNamespace(rep_travail=tmp_path))
    corps, statut = _appeler("p", _hash_tete(tmp_path))
    assert statut == 200
    fichiers = {f["chemin"]: f for f in corps["fichiers"]}

    assert fichiers["a.txt"]["statut"] == "modifié"
    assert fichiers["a.txt"]["ajoutees"] == 1
    assert fichiers["a.txt"]["supprimees"] == 0
    assert fichiers["a.txt"]["ancien_chemin"] is None

    assert fichiers["c.txt"]["statut"] == "renommé"
    assert fichiers["c.txt"]["ancien_chemin"] == "b.txt"

    assert fichiers["nouveau.txt"]["statut"] == "ajouté"
    assert fichiers["nouveau.txt"]["ajoutees"] == 1

    assert fichiers["img.bin"]["statut"] == "ajouté"
    assert fichiers["img.bin"]["ajoutees"] is None   # binaire : jamais un faux 0
    assert fichiers["img.bin"]["supprimees"] is None

    # Commit de suppression séparé : le statut D doit survivre seul.
    _git(tmp_path, "rm", "-q", "nouveau.txt")
    _git(tmp_path, "commit", "-q", "-m", "retrait")
    corps2, statut2 = _appeler("p", _hash_tete(tmp_path))
    assert statut2 == 200
    f2 = {f["chemin"]: f for f in corps2["fichiers"]}
    assert f2["nouveau.txt"]["statut"] == "supprimé"
    assert f2["nouveau.txt"]["supprimees"] == 1


def test_renommage_avec_dossier_commun_toujours_reconnu(tmp_path, monkeypatch):
    """Renommage vers un sous-dossier (git abrège l'affichage par défaut en
    `{ancien => nouveau}` dans --stat/--patch) : le statut et les DEUX chemins
    complets doivent rester exacts, --name-status -z n'abrège jamais."""
    _init_depot(tmp_path)
    (tmp_path / "f.txt").write_text("contenu\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    (tmp_path / "dossier").mkdir()
    _git(tmp_path, "mv", "f.txt", "dossier/f.txt")
    _git(tmp_path, "commit", "-q", "-m", "range dans un dossier")

    monkeypatch.setattr(issues, "projet_par_nom",
                         lambda nom: SimpleNamespace(rep_travail=tmp_path))
    corps, statut = _appeler("p", _hash_tete(tmp_path))
    assert statut == 200
    fichiers = {f["chemin"]: f for f in corps["fichiers"]}
    assert fichiers["dossier/f.txt"]["statut"] == "renommé"
    assert fichiers["dossier/f.txt"]["ancien_chemin"] == "f.txt"


if __name__ == "__main__":
    raise SystemExit(subprocess.run(
        [sys.executable, "-m", "pytest", "-q", __file__]).returncode)
