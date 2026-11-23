#!/usr/bin/env python3
"""Tests côté serveur de l'issue #940 (la ligne d'une nouvelle issue
n'apparaît pas tant qu'une case à cocher garde le focus — rendu de la liste
reporté indéfiniment) :
  - mesure_charge_interface.ligne_rendu_differe (logique pure) et
    app.charge_interface.route_rendu_differe (POST /journal-rendu-differe,
    best-effort, corps minuscule et strict comme route_reouverture_stream —
    voir tests/test_journal_reouverture_stream_937.py).

La logique du PLAFOND du report lui-même (differerRenduSurCoche, côté
client) est testée en JS, voir static/js/tests/app_rendu_differe_940.test.js.

Aucune écriture dans logs/charge_interface.log : chaque scénario qui écrit
un journal le fait dans un dossier temporaire. Aucun appel GitHub (cette
route est purement locale).

Exécution :  python3 tests/test_journal_rendu_differe_940.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import json
import logging
import sys
import tempfile
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import mesure_charge_interface as mci  # noqa: E402
from app import create_app  # noqa: E402


def _app():
    app = create_app()
    app.config["TESTING"] = True
    return app


def _journal_temporaire(chemin):
    """Même technique que tests/test_journal_reouverture_stream_937.py."""
    logger = logging.getLogger("bridge_agent.charge_interface")
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    mci._logger = None
    return mock.patch.object(mci, "FICHIER_JOURNAL", chemin)


# ─── mesure_charge_interface.py : logique pure ───────────────────────────────

def scenario_ligne_rendu_differe_format_sans_fuite():
    ligne = mci.ligne_rendu_differe("2026-11-23T18:55:11+00:00", "liste", 42)
    data = json.loads(ligne)
    assert data == {
        "type": "rendu_differe",
        "horodatage": "2026-11-23T18:55:11+00:00",
        "type_rendu": "liste",
        "duree_report_ms": 42,
    }, data
    assert set(data.keys()) == {"type", "horodatage", "type_rendu", "duree_report_ms"}


def scenario_ligne_rendu_differe_type_ligne():
    ligne = mci.ligne_rendu_differe("2026-11-23T18:55:11+00:00", "ligne", 987)
    data = json.loads(ligne)
    assert data["type_rendu"] == "ligne"
    assert data["duree_report_ms"] == 987


# ─── POST /journal-rendu-differe ─────────────────────────────────────────────

def scenario_route_accepte_corps_bien_forme_liste():
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with _journal_temporaire(chemin):
            app = _app()
            with app.test_client() as client:
                rep = client.post("/journal-rendu-differe",
                                   json={"type_rendu": "liste", "duree_report_ms": 123})
                assert rep.status_code == 200, rep.get_data(as_text=True)
                assert rep.get_json()["succes"] is True
            contenu = chemin.read_text(encoding="utf-8").strip().splitlines()
            assert len(contenu) == 1
            data = json.loads(contenu[0])
            assert data["type"] == "rendu_differe"
            assert data["type_rendu"] == "liste"
            assert data["duree_report_ms"] == 123


def scenario_route_accepte_corps_bien_forme_ligne():
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with _journal_temporaire(chemin):
            app = _app()
            with app.test_client() as client:
                rep = client.post("/journal-rendu-differe",
                                   json={"type_rendu": "ligne", "duree_report_ms": 0})
                assert rep.status_code == 200, rep.get_data(as_text=True)
            contenu = chemin.read_text(encoding="utf-8").strip().splitlines()
            assert json.loads(contenu[0])["type_rendu"] == "ligne"


def scenario_route_rejette_type_rendu_inconnu():
    app = _app()
    with app.test_client() as client:
        rep = client.post("/journal-rendu-differe",
                           json={"type_rendu": "tableau", "duree_report_ms": 1})
        assert rep.status_code == 400, rep.status_code
        assert rep.get_json()["succes"] is False


def scenario_route_rejette_champ_inconnu():
    app = _app()
    with app.test_client() as client:
        rep = client.post("/journal-rendu-differe", json={
            "type_rendu": "liste", "duree_report_ms": 1, "projet": "fuite potentielle",
        })
        assert rep.status_code == 400, rep.status_code


def scenario_route_rejette_champ_manquant():
    app = _app()
    with app.test_client() as client:
        rep = client.post("/journal-rendu-differe", json={"type_rendu": "liste"})
        assert rep.status_code == 400, rep.status_code


def scenario_route_rejette_duree_non_numerique():
    app = _app()
    with app.test_client() as client:
        rep = client.post("/journal-rendu-differe",
                           json={"type_rendu": "liste", "duree_report_ms": "vite"})
        assert rep.status_code == 400


def scenario_route_rejette_duree_negative():
    app = _app()
    with app.test_client() as client:
        rep = client.post("/journal-rendu-differe",
                           json={"type_rendu": "liste", "duree_report_ms": -1})
        assert rep.status_code == 400


def scenario_route_rejette_corps_trop_gros():
    from app import charge_interface as ci
    app = _app()
    with app.test_client() as client:
        rep = client.post(
            "/journal-rendu-differe",
            data="x" * (ci.TAILLE_MAX_CORPS_RESUME + 1),
            content_type="application/json")
        assert rep.status_code == 400
        assert "volumineux" in rep.get_json()["erreur"]


def scenario_route_exige_connexion_si_acces_reseau():
    """Même règle de connexion que le reste de l'interface (login_requis)."""
    app = _app()
    app.config["ACCES_RESEAU"] = True
    app.config["MOT_DE_PASSE"] = "un_hash_quelconque"
    with app.test_client() as client:
        rep = client.post("/journal-rendu-differe",
                           json={"type_rendu": "liste", "duree_report_ms": 1},
                           follow_redirects=False)
        assert rep.status_code == 302, rep.status_code
        assert "/login" in rep.headers.get("Location", "")


def main():
    tests = [
        ("ligne_rendu_differe : format sans fuite",
         scenario_ligne_rendu_differe_format_sans_fuite),
        ("ligne_rendu_differe : type 'ligne'",
         scenario_ligne_rendu_differe_type_ligne),
        ("route /journal-rendu-differe : accepte un corps bien formé (liste)",
         scenario_route_accepte_corps_bien_forme_liste),
        ("route /journal-rendu-differe : accepte un corps bien formé (ligne)",
         scenario_route_accepte_corps_bien_forme_ligne),
        ("route /journal-rendu-differe : rejette un type_rendu inconnu",
         scenario_route_rejette_type_rendu_inconnu),
        ("route /journal-rendu-differe : rejette un champ inconnu",
         scenario_route_rejette_champ_inconnu),
        ("route /journal-rendu-differe : rejette un champ manquant",
         scenario_route_rejette_champ_manquant),
        ("route /journal-rendu-differe : rejette une durée non numérique",
         scenario_route_rejette_duree_non_numerique),
        ("route /journal-rendu-differe : rejette une durée négative",
         scenario_route_rejette_duree_negative),
        ("route /journal-rendu-differe : rejette un corps trop gros",
         scenario_route_rejette_corps_trop_gros),
        ("route /journal-rendu-differe : exige la connexion comme le reste de l'interface",
         scenario_route_exige_connexion_si_acces_reseau),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            fn()
            print(f"  ✓ {nom}")
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
