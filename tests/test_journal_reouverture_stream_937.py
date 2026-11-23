#!/usr/bin/env python3
"""Tests côté serveur de l'issue #937 (surveillance du flux /stream qui se
déclenchait en boucle) :
  - mesure_charge_interface.ligne_reouverture_stream (logique pure) et
    app.charge_interface.route_reouverture_stream (POST
    /journal-reouverture-stream, best-effort, corps minuscule et strict comme
    route_resume_precharge — voir tests/test_mesure_charge_interface_835.py) ;
  - app.fin_issue.stream_fin_issue : le battement périodique du flux /stream
    est désormais un événement SSE NOMMÉ ('event: battement\\ndata: {}\\n\\n'),
    PAS un commentaire du protocole SSE (': ping') que le navigateur
    n'exposerait à aucun gestionnaire JavaScript — cause du symptôme.

Aucune écriture dans logs/charge_interface.log : chaque scénario qui écrit
un journal le fait dans un dossier temporaire. Aucun appel GitHub (cette
route est purement locale).

Exécution :  python3 tests/test_journal_reouverture_stream_937.py
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
from app import fin_issue  # noqa: E402


def _app():
    app = create_app()
    app.config["TESTING"] = True
    return app


def _journal_temporaire(chemin):
    """Même technique que tests/test_mesure_charge_interface_835.py."""
    logger = logging.getLogger("bridge_agent.charge_interface")
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    mci._logger = None
    return mock.patch.object(mci, "FICHIER_JOURNAL", chemin)


# ─── mesure_charge_interface.py : logique pure ───────────────────────────────

def scenario_ligne_reouverture_stream_format_sans_fuite():
    ligne = mci.ligne_reouverture_stream("2026-11-23T16:44:01+00:00", 91234)
    data = json.loads(ligne)
    assert data == {
        "type": "reouverture_stream",
        "horodatage": "2026-11-23T16:44:01+00:00",
        "age_dernier_message_ms": 91234,
    }, data
    assert set(data.keys()) == {"type", "horodatage", "age_dernier_message_ms"}


def scenario_ligne_reouverture_stream_age_inconnu():
    """Jamais d'activité enregistrée (juste après le chargement de la page,
    avant toute ouverture confirmée) → None, pas une erreur."""
    ligne = mci.ligne_reouverture_stream("2026-11-23T16:43:46+00:00", None)
    data = json.loads(ligne)
    assert data["age_dernier_message_ms"] is None


# ─── POST /journal-reouverture-stream ────────────────────────────────────────

def scenario_route_accepte_corps_bien_forme():
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with _journal_temporaire(chemin):
            app = _app()
            with app.test_client() as client:
                rep = client.post("/journal-reouverture-stream",
                                   json={"age_dernier_message_ms": 91234})
                assert rep.status_code == 200, rep.get_data(as_text=True)
                assert rep.get_json()["succes"] is True
            contenu = chemin.read_text(encoding="utf-8").strip().splitlines()
            assert len(contenu) == 1
            data = json.loads(contenu[0])
            assert data["type"] == "reouverture_stream"
            assert data["age_dernier_message_ms"] == 91234


def scenario_route_accepte_age_null():
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with _journal_temporaire(chemin):
            app = _app()
            with app.test_client() as client:
                rep = client.post("/journal-reouverture-stream",
                                   json={"age_dernier_message_ms": None})
                assert rep.status_code == 200, rep.get_data(as_text=True)
            contenu = chemin.read_text(encoding="utf-8").strip().splitlines()
            assert json.loads(contenu[0])["age_dernier_message_ms"] is None


def scenario_route_rejette_champ_inconnu():
    app = _app()
    with app.test_client() as client:
        rep = client.post("/journal-reouverture-stream", json={
            "age_dernier_message_ms": 1000, "projet": "fuite potentielle",
        })
        assert rep.status_code == 400, rep.status_code
        assert rep.get_json()["succes"] is False


def scenario_route_rejette_champ_manquant():
    app = _app()
    with app.test_client() as client:
        rep = client.post("/journal-reouverture-stream", json={})
        assert rep.status_code == 400, rep.status_code


def scenario_route_rejette_valeur_non_numerique():
    app = _app()
    with app.test_client() as client:
        rep = client.post("/journal-reouverture-stream",
                           json={"age_dernier_message_ms": "pas un nombre"})
        assert rep.status_code == 400


def scenario_route_rejette_nombre_negatif():
    app = _app()
    with app.test_client() as client:
        rep = client.post("/journal-reouverture-stream",
                           json={"age_dernier_message_ms": -1})
        assert rep.status_code == 400


def scenario_route_rejette_corps_trop_gros():
    from app import charge_interface as ci
    app = _app()
    with app.test_client() as client:
        rep = client.post(
            "/journal-reouverture-stream",
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
        rep = client.post("/journal-reouverture-stream",
                           json={"age_dernier_message_ms": 1000},
                           follow_redirects=False)
        assert rep.status_code == 302, rep.status_code
        assert "/login" in rep.headers.get("Location", "")


# ─── app.fin_issue.stream_fin_issue : format du battement ───────────────────

def scenario_generateur_stream_emet_battement_nomme():
    """Queue vide pendant DELAI_PING (ici réduit pour la rapidité du test) →
    le générateur produit un ÉVÉNEMENT SSE NOMMÉ, jamais un commentaire
    (': ping') : c'est ce qui permet à sse.js de le recevoir (voir
    static/js/tests/sse.test.js)."""
    app = _app()
    with mock.patch.object(fin_issue, "DELAI_PING", 0.01):
        with app.test_request_context("/stream"):
            resp = fin_issue.stream_fin_issue()
            try:
                premier = next(resp.response)
                assert premier == "event: battement\ndata: {}\n\n", repr(premier)
                assert not premier.startswith(":"), "ne doit plus être un commentaire SSE invisible"
            finally:
                resp.response.close()


def main():
    tests = [
        ("ligne_reouverture_stream : format sans fuite",
         scenario_ligne_reouverture_stream_format_sans_fuite),
        ("ligne_reouverture_stream : âge inconnu → None",
         scenario_ligne_reouverture_stream_age_inconnu),
        ("route /journal-reouverture-stream : accepte un corps bien formé",
         scenario_route_accepte_corps_bien_forme),
        ("route /journal-reouverture-stream : accepte un âge null",
         scenario_route_accepte_age_null),
        ("route /journal-reouverture-stream : rejette un champ inconnu",
         scenario_route_rejette_champ_inconnu),
        ("route /journal-reouverture-stream : rejette un champ manquant",
         scenario_route_rejette_champ_manquant),
        ("route /journal-reouverture-stream : rejette une valeur non numérique",
         scenario_route_rejette_valeur_non_numerique),
        ("route /journal-reouverture-stream : rejette un nombre négatif",
         scenario_route_rejette_nombre_negatif),
        ("route /journal-reouverture-stream : rejette un corps trop gros",
         scenario_route_rejette_corps_trop_gros),
        ("route /journal-reouverture-stream : exige la connexion comme le reste de l'interface",
         scenario_route_exige_connexion_si_acces_reseau),
        ("stream_fin_issue : le battement est un événement SSE nommé, pas un commentaire",
         scenario_generateur_stream_emet_battement_nomme),
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
