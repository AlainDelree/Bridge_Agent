#!/usr/bin/env python3
"""Tests du journal des événements /stream (issue #917, point 9) :
mesure_charge_interface.ligne_evenement_stream (logique pure) et
app.fin_issue._diffuser (écriture best-effort d'une ligne par événement
diffusé, sans jamais le contenu de l'événement).

Aucune écriture dans logs/charge_interface.log : chaque scénario qui écrit
un journal le fait dans un dossier temporaire.

Exécution :  python3 tests/test_journal_evenements_stream_917.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import json
import logging
import queue
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


def scenario_ligne_evenement_stream_format_sans_fuite():
    """La ligne est un JSON avec EXACTEMENT les champs attendus — aucun
    titre/label/timing/fichier/motif ne peut s'y trouver."""
    ligne = mci.ligne_evenement_stream("2026-11-22T10:00:00+00:00", "creation_issue", "bridge_agent", 2)
    data = json.loads(ligne)
    assert data == {
        "type": "evenement_stream",
        "horodatage": "2026-11-22T10:00:00+00:00",
        "type_evenement": "creation_issue",
        "projet": "bridge_agent",
        "nb_abonnes": 2,
    }, data
    assert set(data.keys()) == {"type", "horodatage", "type_evenement", "projet", "nb_abonnes"}


def scenario_ligne_evenement_stream_sans_projet():
    """Un événement sans projet (fichier_recu/fichier_refuse) journalise
    projet:null plutôt que de lever."""
    ligne = mci.ligne_evenement_stream("2026-11-22T10:00:00+00:00", "fichier_recu", None, 1)
    data = json.loads(ligne)
    assert data["projet"] is None, data


def scenario_diffuser_ecrit_une_ligne_sans_contenu():
    """app.fin_issue._diffuser() : la diffusion SSE écrit aussi une ligne de
    journal avec le type/projet/nb_abonnes — jamais le titre ni les labels/
    timing transmis dans le payload."""
    app = _app()
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with app.app_context(), _journal_temporaire(chemin):
            fa = queue.Queue()
            app.config["FIN_ISSUE_ABONNES"] = [fa]
            fin_issue._diffuser("creation_issue", {
                "projet": "bridge_agent", "numero": 917, "titre": "Secret — ne doit jamais fuiter",
                "labels": ["secret-label"], "timing": {"estimation": {"mediane": 42}},
            })
            # L'événement est toujours bien poussé dans la file abonnée.
            assert not fa.empty()
            derniere_ligne = chemin.read_text(encoding="utf-8").strip().splitlines()[-1]
            data = json.loads(derniere_ligne)
            assert data["type"] == "evenement_stream"
            assert data["type_evenement"] == "creation_issue"
            assert data["projet"] == "bridge_agent"
            assert data["nb_abonnes"] == 1
            contenu_brut = json.dumps(data)
            assert "Secret" not in contenu_brut
            assert "secret-label" not in contenu_brut
            assert "42" not in contenu_brut


def scenario_diffuser_compte_les_abonnes():
    """nb_abonnes reflète le nombre de files SSE actives AU MOMENT de la
    diffusion (plusieurs onglets Résultats ouverts)."""
    app = _app()
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with app.app_context(), _journal_temporaire(chemin):
            app.config["FIN_ISSUE_ABONNES"] = [queue.Queue(), queue.Queue(), queue.Queue()]
            fin_issue._diffuser("fin_issue", {"projet": "bridge_agent", "numero": 1})
            derniere_ligne = chemin.read_text(encoding="utf-8").strip().splitlines()[-1]
            data = json.loads(derniere_ligne)
            assert data["nb_abonnes"] == 3, data


def scenario_diffuser_sans_projet():
    """fichier_recu (sans champ projet) journalise projet:null, sans lever."""
    app = _app()
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with app.app_context(), _journal_temporaire(chemin):
            app.config["FIN_ISSUE_ABONNES"] = []
            fin_issue._diffuser("fichier_recu", {"fichier": "x.txt"})
            derniere_ligne = chemin.read_text(encoding="utf-8").strip().splitlines()[-1]
            data = json.loads(derniere_ligne)
            assert data["type_evenement"] == "fichier_recu"
            assert data["projet"] is None


def scenario_diffuser_echec_journal_nempeche_pas_la_diffusion():
    """Best-effort strict (en-tête de _diffuser) : une écriture de journal en
    échec ne doit jamais empêcher l'événement d'atteindre les files SSE
    abonnées."""
    app = _app()
    with app.app_context():
        fa = queue.Queue()
        app.config["FIN_ISSUE_ABONNES"] = [fa]
        with mock.patch.object(mci, "ecrire_ligne", side_effect=RuntimeError("disque plein")):
            fin_issue._diffuser("debut_issue", {"projet": "bridge_agent", "numero": 1})
        assert not fa.empty(), "l'événement doit être diffusé même si le journal échoue"


def main():
    tests = [
        ("ligne_evenement_stream : format JSON exact, aucun champ en trop",
         scenario_ligne_evenement_stream_format_sans_fuite),
        ("ligne_evenement_stream : projet absent → null, ne lève pas",
         scenario_ligne_evenement_stream_sans_projet),
        ("_diffuser : écrit une ligne sans le contenu de l'événement",
         scenario_diffuser_ecrit_une_ligne_sans_contenu),
        ("_diffuser : nb_abonnes reflète le nombre de files actives",
         scenario_diffuser_compte_les_abonnes),
        ("_diffuser : événement sans projet → projet:null",
         scenario_diffuser_sans_projet),
        ("_diffuser : échec du journal n'empêche jamais la diffusion SSE",
         scenario_diffuser_echec_journal_nempeche_pas_la_diffusion),
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
