#!/usr/bin/env python3
"""Test du bandeau d'expiration des jetons de l'annuaire — issue #741.

`app.jetons_annuaire.etat_jetons_annuaire()` lit en lecture seule un
`jetons.json` factice (jamais le vrai fichier d'Alain — chemin surchargé via
la variable d'environnement BRIDGE_JETONS_CHEMIN vers un dossier `/tmp`
jetable) tenu par le projet séparé annuairetoken. Toutes les valeurs ci-
dessous sont fictives (JETON_FACTICE). Aucun réseau impliqué.

Couvre :
- fichier absent → aucune alerte, silencieusement (None) ;
- fichier JSON invalide / clés version-jetons absentes → message neutre
  « jetons.json illisible, bandeau désactivé », niveau "gris" ;
- jeton actif proche de l'échéance → niveau orange/rouge selon les mêmes
  seuils que le bandeau OAuth CCW (app.eval_windows) ;
- jeton actif dont la date est dépassée → niveau rouge, « expiré depuis N j » ;
- jeton expirant aujourd'hui (jours_restants == 0) → « expire aujourd'hui » ;
- statut abandonné/expiré ou sans expiration → jamais d'alerte ;
- entrée individuelle invalide (statut inconnu, date mal formée) → ignorée
  sans faire disparaître les autres, comptée dans « N entrée(s) ignorée(s) ».

Exécution :  python3 tests/test_bandeau_jetons_annuaire_741.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import app.jetons_annuaire as ja  # noqa: E402


def _ecrire(tmp: Path, contenu) -> Path:
    chemin = tmp / "jetons.json"
    if isinstance(contenu, str):
        chemin.write_text(contenu, encoding="utf-8")
    else:
        chemin.write_text(json.dumps(contenu), encoding="utf-8")
    return chemin


def _etat_avec_fichier(tmp: Path, contenu=None):
    """Appelle etat_jetons_annuaire() avec BRIDGE_JETONS_CHEMIN pointé sur un
    fichier jetable, jamais le vrai jetons.json d'Alain."""
    chemin = tmp / "jetons.json"
    if contenu is not None:
        _ecrire(tmp, contenu)
    os.environ["BRIDGE_JETONS_CHEMIN"] = str(chemin)
    try:
        return ja.etat_jetons_annuaire()
    finally:
        del os.environ["BRIDGE_JETONS_CHEMIN"]


def _jeton_factice(**kw):
    base = {
        "id": "JETON_FACTICE_1",
        "service": "service-factice",
        "projets": [],
        "depots": [],
        "creation": "2026-01-01",
        "expiration": "",
        "statut": "actif",
        "note": "",
    }
    base.update(kw)
    return base


def test_fichier_absent_aucune_alerte():
    with tempfile.TemporaryDirectory() as tmp:
        res = _etat_avec_fichier(Path(tmp), contenu=None)
        assert res is None, res
    return {"res": res}


def test_fichier_json_invalide_message_neutre():
    with tempfile.TemporaryDirectory() as tmp:
        res = _etat_avec_fichier(Path(tmp), contenu="{ceci n'est pas du json")
        assert res is not None
        assert res["niveau"] == "gris", res
        assert "illisible" in res["messages"][0], res
    return {"res": res}


def test_fichier_sans_cle_jetons_message_neutre():
    with tempfile.TemporaryDirectory() as tmp:
        res = _etat_avec_fichier(Path(tmp), contenu={"version": 1})
        assert res is not None
        assert res["niveau"] == "gris", res
    return {"res": res}


def test_jeton_sans_expiration_aucune_alerte():
    with tempfile.TemporaryDirectory() as tmp:
        contenu = {"version": 1, "jetons": [_jeton_factice(expiration="")]}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is None, res
    return {"res": res}


def test_jeton_abandonne_proche_echeance_aucune_alerte():
    with tempfile.TemporaryDirectory() as tmp:
        bientot = (date.today() + timedelta(days=1)).isoformat()
        contenu = {"version": 1, "jetons": [
            _jeton_factice(statut="abandonné", expiration=bientot),
        ]}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is None, res
    return {"res": res}


def test_jeton_actif_orange():
    with tempfile.TemporaryDirectory() as tmp:
        echeance = (date.today() + timedelta(days=10)).isoformat()
        contenu = {"version": 1, "jetons": [
            _jeton_factice(service="svc-orange", expiration=echeance),
        ]}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        assert res["niveau"] == "orange", res
        assert "svc-orange" in res["messages"][0], res
        assert "10 j restant(s)" in res["messages"][0], res
    return {"res": res}


def test_jeton_actif_rouge():
    with tempfile.TemporaryDirectory() as tmp:
        echeance = (date.today() + timedelta(days=2)).isoformat()
        contenu = {"version": 1, "jetons": [
            _jeton_factice(service="svc-rouge", expiration=echeance),
        ]}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        assert res["niveau"] == "rouge", res
    return {"res": res}


def test_jeton_actif_expire_depasse():
    with tempfile.TemporaryDirectory() as tmp:
        passe = (date.today() - timedelta(days=3)).isoformat()
        contenu = {"version": 1, "jetons": [
            _jeton_factice(service="svc-depasse", expiration=passe),
        ]}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        assert res["niveau"] == "rouge", res
        assert "expiré depuis 3 j" in res["messages"][0], res
    return {"res": res}


def test_jeton_expire_aujourdhui():
    with tempfile.TemporaryDirectory() as tmp:
        aujourdhui = date.today().isoformat()
        contenu = {"version": 1, "jetons": [
            _jeton_factice(service="svc-jour-j", expiration=aujourdhui),
        ]}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        assert "expire aujourd'hui" in res["messages"][0], res
    return {"res": res}


def test_entree_invalide_ignoree_sans_faire_disparaitre_les_autres():
    with tempfile.TemporaryDirectory() as tmp:
        echeance = (date.today() + timedelta(days=2)).isoformat()
        contenu = {"version": 1, "jetons": [
            _jeton_factice(service="svc-valide", id="JETON_FACTICE_OK", expiration=echeance),
            _jeton_factice(service="svc-invalide", id="JETON_FACTICE_MAUVAIS",
                            statut="inconnu-statut", expiration=echeance),
            _jeton_factice(service="svc-date-cassee", id="JETON_FACTICE_DATE",
                            expiration="pas-une-date"),
        ]}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        assert "svc-valide" in " ".join(res["messages"]), res
        assert "2 entrée(s) ignorée(s)" in res["messages"][-1], res
    return {"res": res}


def test_seulement_entrees_ignorees_bandeau_quand_meme_affiche():
    with tempfile.TemporaryDirectory() as tmp:
        contenu = {"version": 1, "jetons": [
            _jeton_factice(statut="statut-invalide"),
        ]}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None, "une entrée invalide ne doit jamais disparaître en silence"
        assert "1 entrée(s) ignorée(s)" in res["messages"][0], res
    return {"res": res}


def main() -> int:
    tests = [
        ("fichier absent → aucune alerte", test_fichier_absent_aucune_alerte),
        ("JSON invalide → message neutre, niveau gris", test_fichier_json_invalide_message_neutre),
        ("clé jetons absente → message neutre", test_fichier_sans_cle_jetons_message_neutre),
        ("jeton sans expiration → aucune alerte", test_jeton_sans_expiration_aucune_alerte),
        ("jeton abandonné proche échéance → aucune alerte", test_jeton_abandonne_proche_echeance_aucune_alerte),
        ("jeton actif, seuil orange", test_jeton_actif_orange),
        ("jeton actif, seuil rouge", test_jeton_actif_rouge),
        ("jeton actif, date dépassée → rouge, « expiré depuis N j »", test_jeton_actif_expire_depasse),
        ("jeton actif expirant aujourd'hui → « expire aujourd'hui »", test_jeton_expire_aujourdhui),
        ("entrée invalide ignorée sans faire disparaître les autres", test_entree_invalide_ignoree_sans_faire_disparaitre_les_autres),
        ("seulement des entrées ignorées → bandeau quand même affiché", test_seulement_entrees_ignorees_bandeau_quand_meme_affiche),
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
