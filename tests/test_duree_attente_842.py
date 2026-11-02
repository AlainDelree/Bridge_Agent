#!/usr/bin/env python3
"""Test de non-régression — issue #842 : l'onglet « En attente » affiche sur
chaque ligne la durée typique estimée (même source que la pastille « ≈ » des
issues en cours de l'onglet Résultats, cf. static/js/resultats.js::
calculerBadgeEstimation / app.issues.estimer_duree) et la durée maximale
possible (TIMEOUT par tentative × nombre de tentatives du projet, ou
« infini » pour une issue critique).

Couvre `app/issues_inbox.py::_lire_item_attente`, lecture seule, sept champs
ajoutés : timeout_s, max_essais, critique, duree_max_s, mode, complexite,
duree_typique_s — sans toucher aux anciens champs (id/titre/projet/date/
condition) ni écrire quoi que ce soit sur disque.

Aucun appel réseau ni `gh` réel.

Exécution :  python3 tests/test_duree_attente_842.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import json
import os
import sys
import tempfile
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


def _deposer(tmp_path: Path, contenu: str, nom: str = "mono.txt") -> Path:
    chemin = tmp_path / nom
    chemin.write_text(contenu, encoding="utf-8")
    os.utime(chemin, (time.time() - 5, time.time() - 5))
    return chemin


def _cfg_projet(nom: str = "bridge_agent", max_essais: int = 3):
    return SimpleNamespace(nom=nom, timeout_claude=300, timeout_chef=1200, max_essais=max_essais)


def _vider_historique(tmp_path: Path):
    """Neutralise estimer_duree côté historique_durees.json (fichier absent,
    best-effort → liste vide) pour isoler le comportement de calibration
    (etat_timeout.json) dans les scénarios qui en ont besoin."""
    watcher.FICHIER_HISTORIQUE = tmp_path / "historique_absent.json"


def test_timeout_et_complexite_declares(tmp_path):
    ii.projet_par_nom = lambda nom: None
    _vider_historique(tmp_path)
    chemin = _deposer(tmp_path,
        "| PROJET | p |\n| TIMEOUT | 1200s |\n| COMPLEXITE | lourd |\n"
        "| ATTENTE | x |\n\n#Titre: T.\nCorps.\n")
    item = ii._lire_item_attente(chemin)
    assert item["timeout_s"] == 1200, item
    assert item["complexite"] == "lourd", item
    return {}


def test_sans_timeout_valeur_par_defaut_du_mode(tmp_path):
    """Sans ligne TIMEOUT, le défaut du mode s'applique — ici le plancher
    écriture (900s), AVEC un projet connu (cfg non None, condition requise
    par _parser_timeout pour appliquer ce plancher)."""
    ii.projet_par_nom = lambda nom: _cfg_projet()
    _vider_historique(tmp_path)
    chemin = _deposer(tmp_path,
        "| PROJET | bridge_agent |\n| MODE | écriture |\n| ATTENTE | x |\n\n#Titre: T.\nCorps.\n")
    item = ii._lire_item_attente(chemin)
    assert item["mode"] == "write", item
    assert item["timeout_s"] == 900, item  # PLANCHER_TIMEOUT_ECRITURE
    return {}


def test_calibration_simulee_duree_typique_connue(tmp_path):
    ii.projet_par_nom = lambda nom: _cfg_projet()
    watcher.FICHIER_HISTORIQUE = tmp_path / "hist.json"
    watcher.FICHIER_HISTORIQUE.write_text("[]", encoding="utf-8")
    watcher.FICHIER_ETAT_TIMEOUT = tmp_path / "etat.json"
    watcher.FICHIER_ETAT_TIMEOUT.write_text(json.dumps({"combinaisons": {
        "bridge_agent|normal|write|normal": {"duree_typique": 735.4, "n_observations": 6},
    }}), encoding="utf-8")
    chemin = _deposer(tmp_path,
        "| PROJET | bridge_agent |\n| MODE | écriture |\n| ATTENTE | x |\n\n#Titre: T.\nCorps.\n")
    item = ii._lire_item_attente(chemin)
    assert item["duree_typique_s"] == 735, item
    return {}


def test_sans_etat_de_calibration_renvoie_none(tmp_path):
    ii.projet_par_nom = lambda nom: _cfg_projet()
    watcher.FICHIER_HISTORIQUE = tmp_path / "hist_absent.json"
    watcher.FICHIER_ETAT_TIMEOUT = tmp_path / "etat_absent.json"
    chemin = _deposer(tmp_path,
        "| PROJET | bridge_agent |\n| MODE | écriture |\n| ATTENTE | x |\n\n#Titre: T.\nCorps.\n")
    item = ii._lire_item_attente(chemin)
    assert item["duree_typique_s"] is None, item
    return {}


def test_etat_illisible_renvoie_none_sans_exception(tmp_path):
    ii.projet_par_nom = lambda nom: _cfg_projet()
    watcher.FICHIER_HISTORIQUE = tmp_path / "hist.json"
    watcher.FICHIER_HISTORIQUE.write_text("[]", encoding="utf-8")
    watcher.FICHIER_ETAT_TIMEOUT = tmp_path / "etat.json"
    watcher.FICHIER_ETAT_TIMEOUT.write_text("{ceci n'est pas du JSON", encoding="utf-8")
    chemin = _deposer(tmp_path,
        "| PROJET | bridge_agent |\n| MODE | écriture |\n| ATTENTE | x |\n\n#Titre: T.\nCorps.\n")
    item = ii._lire_item_attente(chemin)  # ne doit lever aucune exception
    assert item["duree_typique_s"] is None, item
    return {}


def test_priorite_normale_non_critique(tmp_path):
    ii.projet_par_nom = lambda nom: _cfg_projet()
    _vider_historique(tmp_path)
    chemin = _deposer(tmp_path,
        "| PROJET | bridge_agent |\n| TIMEOUT | 1000s |\n| PRIORITE | normale |\n"
        "| ATTENTE | x |\n\n#Titre: T.\nCorps.\n")
    item = ii._lire_item_attente(chemin)
    assert item["critique"] is False, item
    assert item["duree_max_s"] == 3000, item
    return {}


def test_priorite_haute_critique_duree_max_none(tmp_path):
    ii.projet_par_nom = lambda nom: _cfg_projet()
    _vider_historique(tmp_path)
    chemin = _deposer(tmp_path,
        "| PROJET | bridge_agent |\n| TIMEOUT | 1000s |\n| PRIORITE | haute |\n"
        "| ATTENTE | x |\n\n#Titre: T.\nCorps.\n")
    item = ii._lire_item_attente(chemin)
    assert item["critique"] is True, item
    assert item["duree_max_s"] is None, item
    return {}


def test_priorite_critique_duree_max_none(tmp_path):
    ii.projet_par_nom = lambda nom: _cfg_projet()
    _vider_historique(tmp_path)
    chemin = _deposer(tmp_path,
        "| PROJET | bridge_agent |\n| TIMEOUT | 1000s |\n| PRIORITE | critique |\n"
        "| ATTENTE | x |\n\n#Titre: T.\nCorps.\n")
    item = ii._lire_item_attente(chemin)
    assert item["critique"] is True, item
    assert item["duree_max_s"] is None, item
    return {}


def test_max_essais_projet_different_de_trois(tmp_path):
    ii.projet_par_nom = lambda nom: _cfg_projet(max_essais=5)
    _vider_historique(tmp_path)
    chemin = _deposer(tmp_path,
        "| PROJET | bridge_agent |\n| TIMEOUT | 100s |\n| ATTENTE | x |\n\n#Titre: T.\nCorps.\n")
    item = ii._lire_item_attente(chemin)
    assert item["max_essais"] == 5, item
    assert item["duree_max_s"] == 500, item
    return {}


def test_projet_introuvable_max_essais_trois_par_defaut(tmp_path):
    ii.projet_par_nom = lambda nom: None
    _vider_historique(tmp_path)
    chemin = _deposer(tmp_path,
        "| PROJET | inconnu_xyz |\n| TIMEOUT | 100s |\n| ATTENTE | x |\n\n#Titre: T.\nCorps.\n")
    item = ii._lire_item_attente(chemin)
    assert item["max_essais"] == 3, item
    assert item["duree_max_s"] == 300, item
    return {}


def test_anciens_champs_inchanges(tmp_path):
    ii.projet_par_nom = lambda nom: _cfg_projet()
    _vider_historique(tmp_path)
    chemin = _deposer(tmp_path,
        "| PROJET | bridge_agent |\n| ATTENTE | après fusion |\n\n#Titre: Tâche.\nCorps.\n")
    item = ii._lire_item_attente(chemin)
    assert item["id"] == "mono.txt", item
    assert item["titre"] == "Tâche.", item
    assert item["projet"] == "bridge_agent", item
    assert item["condition"] == "après fusion", item
    assert isinstance(item["date"], float), item
    return {}


def test_lecture_seule_aucune_ecriture(tmp_path):
    ii.projet_par_nom = lambda nom: _cfg_projet()
    watcher.FICHIER_HISTORIQUE = tmp_path / "hist.json"
    watcher.FICHIER_HISTORIQUE.write_text("[]", encoding="utf-8")
    watcher.FICHIER_ETAT_TIMEOUT = tmp_path / "etat.json"
    watcher.FICHIER_ETAT_TIMEOUT.write_text(json.dumps({"combinaisons": {
        "bridge_agent|normal|write|normal": {"duree_typique": 42.0, "n_observations": 6},
    }}), encoding="utf-8")
    chemin = _deposer(tmp_path,
        "| PROJET | bridge_agent |\n| MODE | écriture |\n| ATTENTE | x |\n\n#Titre: T.\nCorps.\n")
    avant_contenu = chemin.read_text(encoding="utf-8")
    avant_mtime = chemin.stat().st_mtime
    avant_noms = sorted(p.name for p in tmp_path.iterdir())
    avant_etat = watcher.FICHIER_ETAT_TIMEOUT.read_text(encoding="utf-8")

    ii._lire_item_attente(chemin)
    ii._lire_item_attente(chemin)

    assert chemin.read_text(encoding="utf-8") == avant_contenu
    assert chemin.stat().st_mtime == avant_mtime
    assert sorted(p.name for p in tmp_path.iterdir()) == avant_noms, "aucun fichier créé"
    assert watcher.FICHIER_ETAT_TIMEOUT.read_text(encoding="utf-8") == avant_etat
    return {}


def main() -> int:
    tmp_racine = tempfile.TemporaryDirectory()
    compteur = {"n": 0}

    def _tmp_path():
        compteur["n"] += 1
        chemin = Path(tmp_racine.name) / f"t{compteur['n']}"
        chemin.mkdir(parents=True, exist_ok=True)
        return chemin

    original_projet_par_nom = ii.projet_par_nom
    original_fichier_etat = watcher.FICHIER_ETAT_TIMEOUT
    original_fichier_hist = watcher.FICHIER_HISTORIQUE

    tests = [
        ("TIMEOUT et COMPLEXITE déclarés", test_timeout_et_complexite_declares),
        ("sans TIMEOUT : défaut du mode (plancher écriture)", test_sans_timeout_valeur_par_defaut_du_mode),
        ("calibration simulée : durée typique connue", test_calibration_simulee_duree_typique_connue),
        ("sans état de calibration : None", test_sans_etat_de_calibration_renvoie_none),
        ("état illisible : None, pas d'exception", test_etat_illisible_renvoie_none_sans_exception),
        ("priorité normale : non critique", test_priorite_normale_non_critique),
        ("priorité haute : critique, duree_max_s None", test_priorite_haute_critique_duree_max_none),
        ("priorité critique : critique, duree_max_s None", test_priorite_critique_duree_max_none),
        ("MAX_ESSAIS du projet != 3", test_max_essais_projet_different_de_trois),
        ("projet introuvable : max_essais = 3", test_projet_introuvable_max_essais_trois_par_defaut),
        ("anciens champs inchangés", test_anciens_champs_inchanges),
        ("lecture seule : aucune écriture", test_lecture_seule_aucune_ecriture),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            rap = fn(_tmp_path())
            print(f"  ✓ {nom}  ({rap})")
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}\n      {e}")
        except Exception as e:  # noqa: BLE001
            echecs += 1
            print(f"  ✗ {nom} — erreur inattendue : {type(e).__name__}: {e}")
        finally:
            ii.projet_par_nom = original_projet_par_nom
            watcher.FICHIER_ETAT_TIMEOUT = original_fichier_etat
            watcher.FICHIER_HISTORIQUE = original_fichier_hist

    tmp_racine.cleanup()
    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
