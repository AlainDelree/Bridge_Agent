#!/usr/bin/env python3
"""Tests du journal des rechargements de liste (issue #933 point 5) :
mesure_charge_interface.ligne_rechargement_liste /
ligne_avertissement_issue_absente (logique pure) et
app.issues._journaliser_rechargement_liste (écriture best-effort d'une ligne
par appel de /issues-liste, plus une ligne d'avertissement quand un
rechargement déclenché par un début/fin de traitement ne retrouve pas
l'issue attendue).

Aucune écriture dans logs/charge_interface.log : chaque scénario qui écrit
un journal le fait dans un dossier temporaire. Aucun accès réseau réel ni
appel `gh` (_journaliser_rechargement_liste ne fait jamais d'appel GitHub —
c'est précisément ce que ce fichier vérifie).

Exécution :  python3 tests/test_journal_rechargement_liste_933.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import json
import logging
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import mesure_charge_interface as mci  # noqa: E402
from app import issues as app_issues  # noqa: E402


def _journal_temporaire(chemin):
    """Même technique que tests/test_mesure_charge_interface_835.py et
    tests/test_journal_evenements_stream_917.py."""
    logger = logging.getLogger("bridge_agent.charge_interface")
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    mci._logger = None
    return mock.patch.object(mci, "FICHIER_JOURNAL", chemin)


def _lire_lignes(chemin):
    if not chemin.exists():
        return []
    return [json.loads(l) for l in chemin.read_text(encoding="utf-8").strip().splitlines() if l]


# ─── mesure_charge_interface.py : logique pure ───────────────────────────────

def scenario_ligne_rechargement_liste_format_sans_fuite():
    ligne = mci.ligne_rechargement_liste(
        "2026-11-23T00:30:00+00:00", "bridge_agent", 12, 933, 0.842, "debut")
    data = json.loads(ligne)
    assert data == {
        "type": "rechargement_liste",
        "horodatage": "2026-11-23T00:30:00+00:00",
        "projet": "bridge_agent",
        "nb_issues": 12,
        "numero_plus_recent": 933,
        "duree_gh_s": 0.842,
        "raison": "debut",
    }, data
    assert set(data.keys()) == {"type", "horodatage", "projet", "nb_issues",
                                 "numero_plus_recent", "duree_gh_s", "raison"}


def scenario_ligne_rechargement_liste_raison_absente():
    """Un appelant antérieur à #933 (sans `raison`) → None, pas une erreur."""
    ligne = mci.ligne_rechargement_liste(
        "2026-11-23T00:30:00+00:00", "bridge_agent", 0, None, 0.1, None)
    data = json.loads(ligne)
    assert data["raison"] is None
    assert data["numero_plus_recent"] is None


def scenario_ligne_avertissement_issue_absente_format_sans_fuite():
    ligne = mci.ligne_avertissement_issue_absente(
        "2026-11-23T00:30:19+00:00", "bridge_agent", 933, 19.4, "fin")
    data = json.loads(ligne)
    assert data == {
        "type": "avertissement_issue_absente",
        "horodatage": "2026-11-23T00:30:19+00:00",
        "projet": "bridge_agent",
        "numero": 933,
        "age_s": 19.4,
        "raison": "fin",
    }, data


def scenario_ligne_avertissement_issue_absente_age_inconnu():
    ligne = mci.ligne_avertissement_issue_absente(
        "2026-11-23T00:30:19+00:00", "bridge_agent", 933, None, "debut")
    data = json.loads(ligne)
    assert data["age_s"] is None


# ─── app.issues._journaliser_rechargement_liste ─────────────────────────────

def scenario_journalise_toujours_une_ligne_rechargement_liste():
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with _journal_temporaire(chemin):
            issues = [{"number": 933}, {"number": 917}]
            app_issues._journaliser_rechargement_liste(
                "bridge_agent", issues, 0.5, "clic", None, None)
        lignes = _lire_lignes(chemin)
        assert len(lignes) == 1, lignes
        assert lignes[0]["type"] == "rechargement_liste"
        assert lignes[0]["projet"] == "bridge_agent"
        assert lignes[0]["nb_issues"] == 2
        assert lignes[0]["numero_plus_recent"] == 933
        assert lignes[0]["duree_gh_s"] == 0.5
        assert lignes[0]["raison"] == "clic"


def scenario_journalise_liste_vide_numero_plus_recent_none():
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with _journal_temporaire(chemin):
            app_issues._journaliser_rechargement_liste(
                "bridge_agent", [], 0.2, "reveil", None, None)
        lignes = _lire_lignes(chemin)
        assert len(lignes) == 1
        assert lignes[0]["nb_issues"] == 0
        assert lignes[0]["numero_plus_recent"] is None


def scenario_pas_d_avertissement_si_raison_pas_debut_ou_fin():
    """raison='creation'/'rattrapage'/'clic'/'reveil' : jamais d'avertissement,
    même si `numero` est transmis et absent de la réponse — ces raisons
    n'attendent pas forcément une issue PRÉCISE dans cette réponse."""
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with _journal_temporaire(chemin):
            app_issues._journaliser_rechargement_liste(
                "bridge_agent", [{"number": 1}], 0.1, "creation", 933, None)
        lignes = _lire_lignes(chemin)
        assert len(lignes) == 1
        assert lignes[0]["type"] == "rechargement_liste"


def scenario_pas_d_avertissement_si_numero_absent_de_la_requete():
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with _journal_temporaire(chemin):
            app_issues._journaliser_rechargement_liste(
                "bridge_agent", [{"number": 1}], 0.1, "debut", None, None)
        lignes = _lire_lignes(chemin)
        assert len(lignes) == 1


def scenario_pas_d_avertissement_si_issue_presente():
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with _journal_temporaire(chemin):
            app_issues._journaliser_rechargement_liste(
                "bridge_agent", [{"number": 933}, {"number": 1}], 0.1, "debut", "933", None)
        lignes = _lire_lignes(chemin)
        assert len(lignes) == 1, "l'issue attendue est présente : pas d'avertissement"


def scenario_avertissement_si_debut_et_issue_absente_sans_age_connu():
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with _journal_temporaire(chemin):
            app_issues._journaliser_rechargement_liste(
                "bridge_agent", [{"number": 1}], 0.3, "debut", "933", None)
        lignes = _lire_lignes(chemin)
        assert len(lignes) == 2, lignes
        assert lignes[0]["type"] == "rechargement_liste"
        assert lignes[1]["type"] == "avertissement_issue_absente"
        assert lignes[1]["projet"] == "bridge_agent"
        assert lignes[1]["numero"] == "933"
        assert lignes[1]["age_s"] is None
        assert lignes[1]["raison"] == "debut"


def scenario_avertissement_si_fin_et_issue_absente_avec_age_calcule():
    """`cree_le` fixé à ~19.4s dans le passé (horloge réelle, pas de mock) —
    tolérance large pour le temps d'exécution du scénario lui-même."""
    cree_dt = datetime.now(timezone.utc) - timedelta(seconds=19.4)
    cree_le = cree_dt.isoformat()
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with _journal_temporaire(chemin):
            app_issues._journaliser_rechargement_liste(
                "bridge_agent", [], 0.1, "fin", "933", cree_le)
        lignes = _lire_lignes(chemin)
        assert len(lignes) == 2, lignes
        assert lignes[1]["type"] == "avertissement_issue_absente"
        age_s = lignes[1]["age_s"]
        assert age_s is not None and abs(age_s - 19.4) < 2.0, age_s


def scenario_cree_le_invalide_ne_fait_pas_echouer():
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with _journal_temporaire(chemin):
            app_issues._journaliser_rechargement_liste(
                "bridge_agent", [], 0.1, "debut", "933", "pas-une-date")
        lignes = _lire_lignes(chemin)
        assert len(lignes) == 2
        assert lignes[1]["age_s"] is None


def scenario_echec_ecriture_journal_best_effort():
    """Une exception à l'écriture (ex. répertoire logs/ inaccessible) ne doit
    jamais remonter — best-effort strict, comme le reste de ce journal."""
    with mock.patch.object(mci, "ecrire_ligne", side_effect=OSError("disque plein")):
        app_issues._journaliser_rechargement_liste(
            "bridge_agent", [{"number": 1}], 0.1, "debut", "933", None)   # ne doit pas lever


def main():
    tests = [
        ("ligne_rechargement_liste : format sans fuite",
         scenario_ligne_rechargement_liste_format_sans_fuite),
        ("ligne_rechargement_liste : raison absente → None",
         scenario_ligne_rechargement_liste_raison_absente),
        ("ligne_avertissement_issue_absente : format sans fuite",
         scenario_ligne_avertissement_issue_absente_format_sans_fuite),
        ("ligne_avertissement_issue_absente : âge inconnu → None",
         scenario_ligne_avertissement_issue_absente_age_inconnu),
        ("_journaliser_rechargement_liste : toujours une ligne rechargement_liste",
         scenario_journalise_toujours_une_ligne_rechargement_liste),
        ("_journaliser_rechargement_liste : liste vide → numero_plus_recent None",
         scenario_journalise_liste_vide_numero_plus_recent_none),
        ("_journaliser_rechargement_liste : pas d'avertissement si raison ≠ debut/fin",
         scenario_pas_d_avertissement_si_raison_pas_debut_ou_fin),
        ("_journaliser_rechargement_liste : pas d'avertissement si numero absent de la requête",
         scenario_pas_d_avertissement_si_numero_absent_de_la_requete),
        ("_journaliser_rechargement_liste : pas d'avertissement si l'issue est présente",
         scenario_pas_d_avertissement_si_issue_presente),
        ("_journaliser_rechargement_liste : avertissement (debut), âge inconnu",
         scenario_avertissement_si_debut_et_issue_absente_sans_age_connu),
        ("_journaliser_rechargement_liste : avertissement (fin), âge calculé depuis cree_le",
         scenario_avertissement_si_fin_et_issue_absente_avec_age_calcule),
        ("_journaliser_rechargement_liste : cree_le invalide → age_s None, pas d'exception",
         scenario_cree_le_invalide_ne_fait_pas_echouer),
        ("_journaliser_rechargement_liste : échec d'écriture best-effort (jamais levé)",
         scenario_echec_ecriture_journal_best_effort),
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
