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


def _jetons_en_desordre(jours_restants_liste):
    """Fabrique des jetons actifs factices, un par valeur de jours_restants
    donnée, dans l'ORDRE DE LA LISTE fournie (pas trié) — pour vérifier que
    le tri par urgence s'applique bien, pas l'ordre du fichier."""
    jetons = []
    for i, jours in enumerate(jours_restants_liste):
        echeance = (date.today() + timedelta(days=jours)).isoformat()
        jetons.append(_jeton_factice(
            service=f"svc-{i}", id=f"JETON_FACTICE_{i}", expiration=echeance,
        ))
    return jetons


def test_tri_par_jours_restants_jetons_en_desordre():
    with tempfile.TemporaryDirectory() as tmp:
        # 10, 2, 5 jours restants dans le fichier -> attendu triés 2, 5, 10.
        contenu = {"version": 1, "jetons": _jetons_en_desordre([10, 2, 5])}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        ordre = [m for m in res["messages"] if m.startswith("⚠️ Jeton")]
        assert "svc-1" in ordre[0] and "2 j restant(s)" in ordre[0], res
        assert "svc-2" in ordre[1] and "5 j restant(s)" in ordre[1], res
        assert "svc-0" in ordre[2] and "10 j restant(s)" in ordre[2], res
    return {"res": res}


def test_tri_jetons_deja_expires_en_premier():
    with tempfile.TemporaryDirectory() as tmp:
        # -3 (déjà expiré), 1, -1 jours restants -> attendu : -3, -1, 1.
        contenu = {"version": 1, "jetons": _jetons_en_desordre([-3, 1, -1])}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        ordre = [m for m in res["messages"] if m.startswith("⚠️ Jeton")]
        assert "expiré depuis 3 j" in ordre[0], res
        assert "expiré depuis 1 j" in ordre[1], res
        assert "1 j restant(s)" in ordre[2], res
    return {"res": res}


def test_tri_egalite_jours_departagee_par_id():
    with tempfile.TemporaryDirectory() as tmp:
        echeance = (date.today() + timedelta(days=3)).isoformat()
        contenu = {"version": 1, "jetons": [
            _jeton_factice(service="svc-z", id="JETON_FACTICE_Z", expiration=echeance),
            _jeton_factice(service="svc-a", id="JETON_FACTICE_A", expiration=echeance),
        ]}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        ordre = [m for m in res["messages"] if m.startswith("⚠️ Jeton")]
        assert "svc-a" in ordre[0], res
        assert "svc-z" in ordre[1], res
    return {"res": res}


def test_exactement_3_jetons_3_lignes_sans_synthese():
    with tempfile.TemporaryDirectory() as tmp:
        contenu = {"version": 1, "jetons": _jetons_en_desordre([1, 2, 3])}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        lignes_jetons = [m for m in res["messages"] if m.startswith("⚠️ Jeton")]
        assert len(lignes_jetons) == 3, res
        assert not any("autre" in m for m in res["messages"]), res
    return {"res": res}


def test_4_jetons_3_lignes_plus_1_autre():
    with tempfile.TemporaryDirectory() as tmp:
        contenu = {"version": 1, "jetons": _jetons_en_desordre([1, 2, 3, 4])}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        lignes_jetons = [m for m in res["messages"] if m.startswith("⚠️ Jeton")]
        assert len(lignes_jetons) == 3, res
        assert "+ 1 autre jeton à renouveler" in " ".join(res["messages"]), res
    return {"res": res}


def test_20_jetons_3_lignes_plus_17_autres():
    with tempfile.TemporaryDirectory() as tmp:
        # Tous à 3 jours restants (seuil orange) pour que les 20 soient en
        # alerte — au-delà de SEUIL_ORANGE (14 j), un jeton n'est plus affiché.
        contenu = {"version": 1, "jetons": _jetons_en_desordre([3] * 20)}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        lignes_jetons = [m for m in res["messages"] if m.startswith("⚠️ Jeton")]
        assert len(lignes_jetons) == 3, res
        assert "+ 17 autres" in " ".join(res["messages"]), res
    return {"res": res}


def test_niveau_rouge_meme_si_jeton_critique_masque():
    """4 jetons au seuil rouge (jours_restants=2) : les 3 premiers (triés par
    id) sont visibles, le 4e est masqué par le plafond — le niveau du
    bandeau doit rester rouge, calculé sur TOUS les jetons en alerte, pas
    seulement sur les 3 lignes affichées."""
    with tempfile.TemporaryDirectory() as tmp:
        contenu = {"version": 1, "jetons": [
            _jeton_factice(service=f"svc-{c}", id=f"JETON_FACTICE_{c}",
                            expiration=(date.today() + timedelta(days=2)).isoformat())
            for c in "ZYXW"
        ]}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        assert res["niveau"] == "rouge", res
        assert "+ 1 autre" in " ".join(res["messages"]), res
    return {"res": res}


def test_ligne_entrees_ignorees_restee_en_dernier_avec_synthese():
    with tempfile.TemporaryDirectory() as tmp:
        jetons = _jetons_en_desordre([1, 2, 3, 4])
        jetons.append(_jeton_factice(statut="statut-invalide"))
        contenu = {"version": 1, "jetons": jetons}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        assert "1 entrée(s) ignorée(s)" in res["messages"][-1], res
        assert "autre" in res["messages"][-2], res
    return {"res": res}


def test_comportement_inchange_avec_1_jeton():
    with tempfile.TemporaryDirectory() as tmp:
        contenu = {"version": 1, "jetons": _jetons_en_desordre([2])}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        assert len([m for m in res["messages"] if m.startswith("⚠️ Jeton")]) == 1, res
        assert not any("autre" in m for m in res["messages"]), res
    return {"res": res}


def test_comportement_inchange_avec_2_jetons():
    with tempfile.TemporaryDirectory() as tmp:
        contenu = {"version": 1, "jetons": _jetons_en_desordre([5, 2])}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        ordre = [m for m in res["messages"] if m.startswith("⚠️ Jeton")]
        assert len(ordre) == 2, res
        assert "2 j restant(s)" in ordre[0], res
        assert "5 j restant(s)" in ordre[1], res
        assert not any("autre" in m for m in res["messages"]), res
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
        ("tri par jours restants, jetons en désordre dans le fichier", test_tri_par_jours_restants_jetons_en_desordre),
        ("tri : jetons déjà expirés d'abord, le plus en retard en tête", test_tri_jetons_deja_expires_en_premier),
        ("tri : égalité de jours départagée par id", test_tri_egalite_jours_departagee_par_id),
        ("exactement 3 jetons → 3 lignes, sans synthèse", test_exactement_3_jetons_3_lignes_sans_synthese),
        ("4 jetons → 3 lignes + « + 1 autre jeton »", test_4_jetons_3_lignes_plus_1_autre),
        ("20 jetons → 3 lignes + « + 17 autres »", test_20_jetons_3_lignes_plus_17_autres),
        ("niveau rouge dès qu'un jeton critique existe, même masqué", test_niveau_rouge_meme_si_jeton_critique_masque),
        ("ligne des entrées ignorées toujours en dernier, après la synthèse", test_ligne_entrees_ignorees_restee_en_dernier_avec_synthese),
        ("comportement inchangé avec 1 jeton", test_comportement_inchange_avec_1_jeton),
        ("comportement inchangé avec 2 jetons", test_comportement_inchange_avec_2_jetons),
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
