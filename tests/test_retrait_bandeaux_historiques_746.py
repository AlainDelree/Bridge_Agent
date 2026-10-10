#!/usr/bin/env python3
"""Test du retrait des bandeaux historiques « OAuth Token CCW » et « Éval
Windows CCW » — issue #746.

Ces deux bandeaux lisaient `provisioning/windows/eval-expiration.json` ;
l'annuaire des jetons (issues #741/#742) suit désormais ces deux échéances
(jeton Claude du service CCW ET licence d'évaluation Windows), saisies dans
l'outil AnnuaireToken. `app/eval_windows.py` est supprimé ; les seuils
(`_niveau()`, SEUIL_ORANGE=14j, SEUIL_ROUGE=5j) vivent désormais dans
`app/jetons_annuaire.py`, et le libellé du bandeau de l'annuaire devient
générique (« Échéance <service> (<id>) » au lieu de « Jeton <service>
(<id>) »), pour couvrir aussi bien un jeton qu'une licence Windows.

Couvre :
- `app/eval_windows.py` n'existe plus, `app/vues.py` ne l'importe plus ;
- les seuils déplacés dans `app/jetons_annuaire.py` restent inchangés
  (orange à 14 jours, rouge à 5 jours et à l'expiration) ;
- le nouveau libellé « Échéance » s'applique aussi bien à une entrée de
  service Windows (licence d'évaluation) qu'à un jeton classique ;
- la page se rend sans l'ancien bandeau (ni « Éval Windows CCW » ni
  « OAuth Token CCW ») mais garde le bandeau de l'annuaire ;
- `provisioning/windows/eval-expiration.json`, débarrassé de la clé
  `date_expiration_oauth_token`, reste un JSON valide et continue d'être lu
  correctement par `verifier_expiration_ccw.py` (autres clés inchangées) ;
  une ancienne copie du fichier qui contiendrait encore cette clé est
  simplement ignorée (clé surnuméraire sans effet).

Exécution :  python3 tests/test_retrait_bandeaux_historiques_746.py
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

try:
    import jinja2
except ImportError:
    jinja2 = None


def _etat_avec_fichier(tmp: Path, contenu) -> dict | None:
    chemin = tmp / "jetons.json"
    chemin.write_text(json.dumps(contenu), encoding="utf-8")
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


def test_module_eval_windows_supprime():
    chemin = RACINE / "app" / "eval_windows.py"
    assert not chemin.exists(), "app/eval_windows.py devrait être supprimé"
    return {"chemin": str(chemin)}


def test_vues_ne_mentionne_plus_eval_windows():
    contenu = (RACINE / "app" / "vues.py").read_text(encoding="utf-8")
    assert "eval_windows" not in contenu, contenu
    assert "etat_jetons_annuaire" in contenu, contenu
    return {}


def test_seuils_deplaces_dans_jetons_annuaire():
    assert ja.SEUIL_ORANGE == 14, ja.SEUIL_ORANGE
    assert ja.SEUIL_ROUGE == 5, ja.SEUIL_ROUGE
    assert ja._niveau(14) == "orange", ja._niveau(14)
    assert ja._niveau(5) == "rouge", ja._niveau(5)
    assert ja._niveau(-1) == "rouge", ja._niveau(-1)
    assert ja._niveau(15) is None, ja._niveau(15)
    return {}


def test_libelle_echeance_pour_licence_windows():
    """Une entrée d'annuaire représentant la licence d'évaluation Windows
    (service/id quelconques, rien de spécifique au jeton) obtient le même
    libellé générique « Échéance » qu'un jeton classique."""
    with tempfile.TemporaryDirectory() as tmp:
        echeance = (date.today() + timedelta(days=3)).isoformat()
        contenu = {"version": 1, "jetons": [
            _jeton_factice(service="licence-windows-ccw", id="LICENCE_EVAL_CCW",
                            expiration=echeance),
        ]}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        assert "⚠️ Échéance licence-windows-ccw (LICENCE_EVAL_CCW)" in res["messages"][0], res
        assert "Jeton" not in res["messages"][0], res
    return {"res": res}


def test_libelle_echeance_pour_jeton_classique():
    with tempfile.TemporaryDirectory() as tmp:
        echeance = (date.today() + timedelta(days=3)).isoformat()
        contenu = {"version": 1, "jetons": [
            _jeton_factice(service="service-factice", expiration=echeance),
        ]}
        res = _etat_avec_fichier(Path(tmp), contenu=contenu)
        assert res is not None
        assert res["messages"][0].startswith("⚠️ Échéance "), res
    return {"res": res}


def test_page_sans_ancien_bandeau_avec_bandeau_annuaire():
    """Rend le fragment templates/fragments/bandeaux.html : ni « Éval Windows
    CCW » ni « OAuth Token CCW » ne doivent plus y figurer, et le bandeau de
    l'annuaire doit s'afficher normalement quand jetons_annuaire est fourni."""
    if jinja2 is None:
        print("  (ignoré : jinja2 non installé)")
        return {"ignore": True}
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(RACINE / "templates")))
    gabarit = env.get_template("fragments/bandeaux.html")
    rendu = gabarit.render(
        projets=[],
        jetons_annuaire={"niveau": "orange", "messages": ["⚠️ Échéance test (X) : 1 j restant(s)"]},
    )
    assert "Éval Windows CCW" not in rendu, rendu
    assert "OAuth Token CCW" not in rendu, rendu
    assert "bandeau-eval-windows orange" in rendu, rendu
    assert "⚠️ Échéance test (X)" in rendu, rendu
    return {}


def test_page_sans_bandeau_annuaire_quand_rien_a_afficher():
    if jinja2 is None:
        print("  (ignoré : jinja2 non installé)")
        return {"ignore": True}
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(RACINE / "templates")))
    gabarit = env.get_template("fragments/bandeaux.html")
    rendu = gabarit.render(projets=[], jetons_annuaire=None)
    assert "Éval Windows CCW" not in rendu, rendu
    assert "OAuth Token CCW" not in rendu, rendu
    return {}


def test_json_eval_expiration_sans_cle_oauth_token():
    chemin = RACINE / "provisioning" / "windows" / "eval-expiration.json"
    with chemin.open(encoding="utf-8") as f:
        meta = json.load(f)
    assert "date_expiration_oauth_token" not in meta, meta
    for cle in ("machine", "windows", "eval_jours", "date_installation", "date_expiration", "note"):
        assert cle in meta, (cle, meta)
    return {}


def test_verifier_expiration_ccw_lit_toujours_le_fichier_sans_la_cle():
    """Copie jetable du vrai fichier (sans date_expiration_oauth_token) :
    verifier_expiration_ccw.py doit continuer à calculer les jours restants
    normalement à partir de date_installation + eval_jours."""
    sys.path.insert(0, str(RACINE / "provisioning" / "windows"))
    import verifier_expiration_ccw as vec  # noqa: E402

    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "eval-expiration.json"
        contenu = {
            "machine": "PC-fixe-CCW",
            "windows": "Windows 11 IoT Enterprise LTSC 2024",
            "eval_jours": 90,
            "date_installation": (date.today() - timedelta(days=10)).isoformat(),
            "date_expiration": "peu importe, recalculée",
            "note": "sans date_expiration_oauth_token",
        }
        chemin.write_text(json.dumps(contenu), encoding="utf-8")
        meta = vec.charger_meta(chemin)
        date_install = date.fromisoformat(str(meta["date_installation"]))
        eval_jours = int(meta["eval_jours"])
        jours_restants = (date_install + __import__("datetime").timedelta(days=eval_jours)
                           - date.today()).days
        assert jours_restants == 80, jours_restants
    return {}


def test_ancienne_copie_avec_cle_oauth_token_ignoree_sans_effet():
    """Une ancienne copie du fichier qui contiendrait encore
    date_expiration_oauth_token doit simplement être ignorée par
    verifier_expiration_ccw.py (clé surnuméraire sans effet sur le calcul)."""
    sys.path.insert(0, str(RACINE / "provisioning" / "windows"))
    import verifier_expiration_ccw as vec  # noqa: E402

    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "eval-expiration.json"
        contenu = {
            "machine": "PC-fixe-CCW",
            "eval_jours": 90,
            "date_installation": (date.today() - timedelta(days=10)).isoformat(),
            "date_expiration_oauth_token": "2020-01-01",
            "note": "ancienne copie, clé surnuméraire",
        }
        chemin.write_text(json.dumps(contenu), encoding="utf-8")
        meta = vec.charger_meta(chemin)
        date_install = date.fromisoformat(str(meta["date_installation"]))
        eval_jours = int(meta["eval_jours"])
        jours_restants = (date_install + __import__("datetime").timedelta(days=eval_jours)
                           - date.today()).days
        assert jours_restants == 80, jours_restants
    return {}


def main() -> int:
    tests = [
        ("app/eval_windows.py supprimé", test_module_eval_windows_supprime),
        ("app/vues.py ne mentionne plus eval_windows", test_vues_ne_mentionne_plus_eval_windows),
        ("seuils inchangés, déplacés dans app.jetons_annuaire", test_seuils_deplaces_dans_jetons_annuaire),
        ("libellé « Échéance » pour une entrée licence Windows", test_libelle_echeance_pour_licence_windows),
        ("libellé « Échéance » pour un jeton classique", test_libelle_echeance_pour_jeton_classique),
        ("page sans ancien bandeau, bandeau annuaire affiché", test_page_sans_ancien_bandeau_avec_bandeau_annuaire),
        ("page sans ancien bandeau, rien à afficher", test_page_sans_bandeau_annuaire_quand_rien_a_afficher),
        ("eval-expiration.json sans date_expiration_oauth_token, JSON valide", test_json_eval_expiration_sans_cle_oauth_token),
        ("verifier_expiration_ccw.py lit toujours le fichier sans la clé", test_verifier_expiration_ccw_lit_toujours_le_fichier_sans_la_cle),
        ("ancienne copie avec la clé oauth_token : ignorée sans effet", test_ancienne_copie_avec_cle_oauth_token_ignoree_sans_effet),
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
