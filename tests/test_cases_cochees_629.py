#!/usr/bin/env python3
"""Test de `etat_cases_cochees.py` / `app/cases_cochees.py` — issue #629,
étape 5a de la refonte web (backend seul, aucun front ne les appelle encore).

Aucun test ici ne touche au vrai `logs/etat_cases_cochees.json` du dépôt :
`etat_cases_cochees.CHEMIN_ETAT`/`CHEMIN_VERROU` sont monkeypatchés vers un
fichier jetable pour chaque scénario — même précaution que
`tests/test_supprimer_projet_587.py` pour `configs/`.

Couvre :
- lecture/écriture : cocher, décocher, idempotence des deux ;
- import en masse (`importer_cases`) : idempotent, plusieurs projets à la
  fois, entrées mal formées ignorées silencieusement ;
- règle de nettoyage (`nettoyer_anciennes`) : retire les numéros ≤ (max
  connu du projet - plafond), laisse les autres projets intacts ;
- suppression de projet (`etat_cases_cochees.supprimer_projet`) : retire
  toutes les coches d'un projet, idempotent ;
- routes Flask (`app/cases_cochees.py`) : lecture, cocher/décocher, import.

Exécution :  python3 tests/test_cases_cochees_629.py
   ou :      pytest tests/test_cases_cochees_629.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import etat_cases_cochees as ecc  # noqa: E402
from app import cases_cochees as route_cc  # noqa: E402

APP_FLASK = flask.Flask(__name__)


class _EtatIsole:
    """Redirige ecc.CHEMIN_ETAT/CHEMIN_VERROU vers un fichier jetable le
    temps du bloc `with`, et restaure les chemins d'origine à la sortie —
    aucun scénario ne doit toucher au vrai fichier du dépôt."""

    def __enter__(self):
        self._ancien_chemin = ecc.CHEMIN_ETAT
        self._ancien_verrou = ecc.CHEMIN_VERROU
        self._tmp = tempfile.TemporaryDirectory()
        ecc.CHEMIN_ETAT = Path(self._tmp.name) / "etat_cases_cochees.json"
        ecc.CHEMIN_VERROU = ecc.CHEMIN_ETAT.with_suffix(".lock")
        return self

    def __exit__(self, *exc):
        ecc.CHEMIN_ETAT = self._ancien_chemin
        ecc.CHEMIN_VERROU = self._ancien_verrou
        self._tmp.cleanup()


def test_cocher_puis_lire():
    with _EtatIsole():
        ok, erreur = ecc.cocher_issue("projet_a", 12)
        assert ok and erreur is None
        assert ecc.lire_cases_cochees("projet_a") == [12]
    return {"numeros": [12]}


def test_cocher_idempotent():
    with _EtatIsole():
        ecc.cocher_issue("projet_a", 12)
        ok, erreur = ecc.cocher_issue("projet_a", 12)
        assert ok and erreur is None
        assert ecc.lire_cases_cochees("projet_a") == [12]
    return {"numeros": [12]}


def test_decocher():
    with _EtatIsole():
        ecc.cocher_issue("projet_a", 12)
        ecc.cocher_issue("projet_a", 15)
        ok, erreur = ecc.decocher_issue("projet_a", 12)
        assert ok and erreur is None
        assert ecc.lire_cases_cochees("projet_a") == [15]
    return {"numeros": [15]}


def test_decocher_idempotent_projet_absent():
    with _EtatIsole():
        ok, erreur = ecc.decocher_issue("fantome", 99)
        assert ok and erreur is None
        assert ecc.lire_cases_cochees("fantome") == []
    return {"ok": ok}


def test_decocher_dernier_retire_le_projet():
    with _EtatIsole():
        ecc.cocher_issue("projet_a", 12)
        ecc.decocher_issue("projet_a", 12)
        assert "projet_a" not in ecc._lire()
    return {"projets": list(ecc._lire().keys())}


def test_projets_distincts_isoles():
    with _EtatIsole():
        ecc.cocher_issue("projet_a", 1)
        ecc.cocher_issue("projet_b", 1)
        ecc.decocher_issue("projet_a", 1)
        assert ecc.lire_cases_cochees("projet_a") == []
        assert ecc.lire_cases_cochees("projet_b") == [1]
    return {"projet_b": [1]}


def test_import_idempotent():
    with _EtatIsole():
        cases = [{"projet": "projet_a", "numero": 1},
                 {"projet": "projet_a", "numero": 2},
                 {"projet": "projet_b", "numero": 5}]
        ok1, nb1, erreur1 = ecc.importer_cases(cases)
        assert ok1 and erreur1 is None and nb1 == 3
        ok2, nb2, erreur2 = ecc.importer_cases(cases)
        assert ok2 and erreur2 is None and nb2 == 0, \
            "rejouer le même import ne doit rien ajouter de plus"
        assert ecc.lire_cases_cochees("projet_a") == [1, 2]
        assert ecc.lire_cases_cochees("projet_b") == [5]
    return {"projet_a": [1, 2], "projet_b": [5]}


def test_import_entrees_malformees_ignorees():
    with _EtatIsole():
        cases = [{"projet": "projet_a", "numero": 1},
                 {"projet": "", "numero": 2},
                 {"projet": "projet_a", "numero": "trois"},
                 {"projet": "projet_a"},
                 {"numero": 4},
                 "pas-un-dict"]
        ok, nb, erreur = ecc.importer_cases(cases)
        assert ok and erreur is None and nb == 1
        assert ecc.lire_cases_cochees("projet_a") == [1]
    return {"nb_ajoutees": nb}


def test_nettoyage_retire_anciennes_cases():
    with _EtatIsole():
        # Plus grand numéro connu pour projet_a : 200. Plafond 50 → seuil 150.
        for n in (100, 150, 151, 200):
            ecc.cocher_issue("projet_a", n)
        ok, nb_supprimees, erreur = ecc.nettoyer_anciennes(plafond=50)
        assert ok and erreur is None
        assert nb_supprimees == 2, "100 et 150 (<= 200-50) doivent être retirés"
        assert ecc.lire_cases_cochees("projet_a") == [151, 200]
    return {"restants": [151, 200]}


def test_nettoyage_laisse_les_autres_projets_intacts():
    with _EtatIsole():
        for n in (1, 500):
            ecc.cocher_issue("projet_gros_volume", n)
        ecc.cocher_issue("projet_petit", 3)
        ok, nb_supprimees, erreur = ecc.nettoyer_anciennes(plafond=50)
        assert ok and erreur is None
        assert nb_supprimees == 1
        assert ecc.lire_cases_cochees("projet_gros_volume") == [500]
        assert ecc.lire_cases_cochees("projet_petit") == [3], \
            "un projet dont aucune case n'est trop ancienne ne doit pas être touché"
    return {"projet_petit": [3]}


def test_nettoyage_sans_rien_a_faire_ne_reecrit_pas():
    with _EtatIsole():
        ecc.cocher_issue("projet_a", 42)
        ok, nb_supprimees, erreur = ecc.nettoyer_anciennes(plafond=50)
        assert ok and erreur is None and nb_supprimees == 0
        assert ecc.lire_cases_cochees("projet_a") == [42]
    return {"nb_supprimees": 0}


def test_supprimer_projet_retire_toutes_ses_cases():
    with _EtatIsole():
        ecc.cocher_issue("projet_a", 1)
        ecc.cocher_issue("projet_a", 2)
        ecc.cocher_issue("projet_b", 9)
        ok, erreur = ecc.supprimer_projet("projet_a")
        assert ok and erreur is None
        assert ecc.lire_cases_cochees("projet_a") == []
        assert ecc.lire_cases_cochees("projet_b") == [9]
    return {"projet_b": [9]}


def test_supprimer_projet_idempotent():
    with _EtatIsole():
        ok, erreur = ecc.supprimer_projet("jamais_vu")
        assert ok and erreur is None
    return {"ok": ok}


def test_route_lire_cases():
    with _EtatIsole():
        ecc.cocher_issue("projet_a", 7)
        with APP_FLASK.test_request_context("/cases-cochees/projet_a"):
            rep = route_cc.lire_cases("projet_a")
        assert rep.get_json() == {"numeros": [7]}
    return {"numeros": [7]}


def test_route_cocher_puis_decocher():
    with _EtatIsole():
        with APP_FLASK.test_request_context(
                "/cases-cochees/projet_a/7", method="POST"):
            rep = route_cc.cocher_case("projet_a", 7)
        corps = rep.get_json()
        assert corps["succes"] is True and corps["numeros"] == [7]

        with APP_FLASK.test_request_context(
                "/cases-cochees/projet_a/7", method="DELETE"):
            rep = route_cc.decocher_case("projet_a", 7)
        corps = rep.get_json()
        assert corps["succes"] is True and corps["numeros"] == []
    return {"succes": True}


def test_route_importer():
    with _EtatIsole():
        payload = {"cases": [{"projet": "projet_a", "numero": 1},
                             {"projet": "projet_b", "numero": 2}]}
        with APP_FLASK.test_request_context(
                "/cases-cochees/importer", method="POST", json=payload):
            rep = route_cc.importer_cases_route()
        corps = rep.get_json()
        assert corps["succes"] is True and corps["nb_ajoutees"] == 2
        assert ecc.lire_cases_cochees("projet_a") == [1]
        assert ecc.lire_cases_cochees("projet_b") == [2]
    return {"nb_ajoutees": 2}


def test_route_importer_champ_manquant():
    with _EtatIsole():
        with APP_FLASK.test_request_context(
                "/cases-cochees/importer", method="POST", json={}):
            rep = route_cc.importer_cases_route()
        assert rep[1] == 400
    return {"status": 400}


def main() -> int:
    tests = [
        ("cocher puis lire", test_cocher_puis_lire),
        ("cocher — idempotent", test_cocher_idempotent),
        ("décocher", test_decocher),
        ("décocher — idempotent, projet absent", test_decocher_idempotent_projet_absent),
        ("décocher le dernier numéro retire la clé projet", test_decocher_dernier_retire_le_projet),
        ("projets distincts isolés l'un de l'autre", test_projets_distincts_isoles),
        ("import en masse — idempotent", test_import_idempotent),
        ("import — entrées malformées ignorées", test_import_entrees_malformees_ignorees),
        ("nettoyage — retire les cases trop anciennes", test_nettoyage_retire_anciennes_cases),
        ("nettoyage — laisse les autres projets intacts", test_nettoyage_laisse_les_autres_projets_intacts),
        ("nettoyage — rien à faire, pas de réécriture inutile", test_nettoyage_sans_rien_a_faire_ne_reecrit_pas),
        ("suppression de projet — retire toutes ses cases", test_supprimer_projet_retire_toutes_ses_cases),
        ("suppression de projet — idempotent", test_supprimer_projet_idempotent),
        ("route GET — lire l'état", test_route_lire_cases),
        ("route POST/DELETE — cocher puis décocher", test_route_cocher_puis_decocher),
        ("route POST — import en masse", test_route_importer),
        ("route POST — champ 'cases' manquant → 400", test_route_importer_champ_manquant),
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
