#!/usr/bin/env python3
"""Test de non-régression — issue #953 : l'onglet « En attente » affichait
« (sans titre) » et « Condition : (aucune condition) » pour un fichier de
relance (en-tête `| RELANCE | #N |`, jamais de `#Titre:`), impossible à
rattacher à une issue sans l'ouvrir.

Couvre `app/issues_inbox.py::_lire_item_attente`, lecture seule, nouveau
champ `relance_numero` (titre/condition eux-mêmes restent inchangés — la
décision d'affichage « Relance #N » / ligne dédiée est côté front, voir
static/js/attente.js::descriptionLigneAttente et
static/js/tests/attente.test.js).

Aucun appel réseau ni `gh` réel.

Exécution :  python3 -m pytest tests/test_titre_relance_attente_953.py
"""

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import pytest  # noqa: E402

import app.issues_inbox as ii  # noqa: E402
import watcher  # noqa: E402


@pytest.fixture(autouse=True)
def _isoler():
    """Restaure après CHAQUE test les attributs substitués dans ce fichier."""
    original_projet_par_nom = ii.projet_par_nom
    original_fichier_etat = watcher.FICHIER_ETAT_TIMEOUT
    original_fichier_hist = watcher.FICHIER_HISTORIQUE
    yield
    ii.projet_par_nom = original_projet_par_nom
    watcher.FICHIER_ETAT_TIMEOUT = original_fichier_etat
    watcher.FICHIER_HISTORIQUE = original_fichier_hist


def _deposer(tmp_path: Path, contenu: str, nom: str = "r.txt") -> Path:
    chemin = tmp_path / nom
    chemin.write_text(contenu, encoding="utf-8")
    os.utime(chemin, (time.time() - 5, time.time() - 5))
    return chemin


def _cfg_projet(nom: str = "bridge_agent", max_essais: int = 3):
    return SimpleNamespace(nom=nom, timeout_claude=300, timeout_chef=1200, max_essais=max_essais)


def _vider_historique(tmp_path: Path):
    watcher.FICHIER_HISTORIQUE = tmp_path / "historique_absent.json"
    watcher.FICHIER_ETAT_TIMEOUT = tmp_path / "etat_absent.json"


def test_relance_avec_numero_lisible(tmp_path):
    ii.projet_par_nom = lambda nom: _cfg_projet()
    _vider_historique(tmp_path)
    chemin = _deposer(tmp_path, "| PROJET | bridge_agent |\n| RELANCE | #953 |\n")
    item = ii._lire_item_attente(chemin)
    assert item["titre"] == "", item
    assert item["relance_numero"] == 953, item


def test_relance_numero_avec_dieze_optionnel(tmp_path):
    """RELANCE accepte « #953 » ou « 953 » (même tolérance que valider_relance,
    scripts/watcher_issues_inbox.py::RELANCE_RE)."""
    ii.projet_par_nom = lambda nom: _cfg_projet()
    _vider_historique(tmp_path)
    chemin = _deposer(tmp_path, "| PROJET | bridge_agent |\n| RELANCE | 953 |\n")
    item = ii._lire_item_attente(chemin)
    assert item["relance_numero"] == 953, item


def test_relance_sans_numero_lisible_ne_leve_pas_d_exception(tmp_path):
    ii.projet_par_nom = lambda nom: _cfg_projet()
    _vider_historique(tmp_path)
    chemin = _deposer(tmp_path, "| PROJET | bridge_agent |\n| RELANCE | pas-un-numero |\n")
    item = ii._lire_item_attente(chemin)  # ne doit lever aucune exception
    assert item["relance_numero"] is None, item
    assert item["titre"] == "", item


def test_relance_avec_vraie_condition_attente(tmp_path):
    """Un fichier de relance qui porte AUSSI un champ ATTENTE garde sa
    condition réelle (lue séparément, cf. lire_condition_attente) — c'est au
    front de décider de l'afficher normalement plutôt que la ligne dédiée
    (voir attente.test.js : relance avec condition)."""
    ii.projet_par_nom = lambda nom: _cfg_projet()
    _vider_historique(tmp_path)
    chemin = _deposer(tmp_path,
        "| PROJET | bridge_agent |\n| RELANCE | #953 |\n| ATTENTE | après la fusion de l'étape C |\n")
    item = ii._lire_item_attente(chemin)
    assert item["relance_numero"] == 953, item
    assert item["condition"] == "après la fusion de l'étape C", item


def test_issue_normale_avec_titre_relance_numero_absent(tmp_path):
    ii.projet_par_nom = lambda nom: _cfg_projet()
    _vider_historique(tmp_path)
    chemin = _deposer(tmp_path, "| PROJET | bridge_agent |\n\n#Titre: Mon titre.\nCorps.\n")
    item = ii._lire_item_attente(chemin)
    assert item["titre"] == "Mon titre.", item
    assert item["relance_numero"] is None, item


def test_issue_normale_sans_titre_relance_numero_absent(tmp_path):
    ii.projet_par_nom = lambda nom: _cfg_projet()
    _vider_historique(tmp_path)
    chemin = _deposer(tmp_path, "| PROJET | bridge_agent |\n\nCorps sans #Titre:.\n")
    item = ii._lire_item_attente(chemin)
    assert item["titre"] == "", item
    assert item["relance_numero"] is None, item
