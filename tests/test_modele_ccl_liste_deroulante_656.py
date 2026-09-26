#!/usr/bin/env python3
"""Test de non-régression — issue #656 : le champ texte libre du modèle CCL
par défaut d'un projet (`MODELE_CCL` du `.conf`, onglet Configuration) devient
une liste déroulante — plus de faute de frappe silencieuse possible.

Couvre le versant SERVEUR :
- `MODELES_VALIDES`/`MODELE_DEFAUT_GLOBAL` : SOURCE UNIQUE désormais dans
  `app/projets.py` (déplacée depuis `app/issues.py`, qui l'important déjà
  soi-même `projet_par_nom` — la définir dans `app/issues.py` aurait créé un
  import circulaire) — `app.issues.MODELES_VALIDES` et
  `scripts.watcher_issues_inbox.MODELES_VALIDES` sont le MÊME objet (import,
  pas une redéfinition dupliquée) ;
- `GET /config/<projet>` (`app/projets.get_config`) expose `modeles_valides`
  (liste triée) et `modele_defaut_global`, pour que l'interface construise sa
  liste déroulante dynamiquement sans dupliquer les valeurs en dur dans le
  JavaScript ;
- un `.conf` dont le `MODELE_CCL` porte une ancienne valeur non reconnue
  (faute de frappe historique) reste chargeable sans erreur — `get_config` la
  renvoie telle quelle dans `modele_ccl`, à charge du navigateur de l'ajouter
  comme option supplémentaire (`construireOptionsModeleCCL`, voir
  static/js/tests/config.test.js pour le versant navigateur).

Exécution :  python3 tests/test_modele_ccl_liste_deroulante_656.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import app.issues as issues  # noqa: E402
import app.projets as projets  # noqa: E402
import scripts.watcher_issues_inbox as wii  # noqa: E402

APP_FLASK = flask.Flask(__name__)


def _ecrire_conf(dossier_configs: Path, nom: str, rep: Path, modele_ccl: str | None = None) -> Path:
    dossier_configs.mkdir(parents=True, exist_ok=True)
    chemin = dossier_configs / f"{nom}.conf"
    contenu = f"NOM = {nom}\nDEPOT = AlainDelree/{nom}\nREP_TRAVAIL = {rep}\nTOPIC_NTFY = topic-test\n"
    if modele_ccl is not None:
        contenu += f"MODELE_CCL = {modele_ccl}\n"
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def test_source_unique_meme_objet_partout():
    """app.issues et scripts.watcher_issues_inbox importent le MÊME objet
    MODELES_VALIDES depuis app.projets — plus deux définitions dupliquées."""
    assert issues.MODELES_VALIDES is projets.MODELES_VALIDES
    assert wii.MODELES_VALIDES is projets.MODELES_VALIDES
    assert projets.MODELES_VALIDES == {
        "claude-sonnet-5", "claude-opus-4-8", "claude-haiku-4-5", "claude-fable-5"}
    return {"modeles": sorted(projets.MODELES_VALIDES)}


def test_get_config_expose_modeles_valides_et_defaut_global():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        configs = tmp / "configs"
        rep_travail = tmp / "travail" / "demo"
        rep_travail.mkdir(parents=True)
        _ecrire_conf(configs, "demo", rep_travail, modele_ccl="claude-opus-4-8")

        ancien = projets.DOSSIER_SCRIPT
        projets.DOSSIER_SCRIPT = tmp
        try:
            with APP_FLASK.test_request_context("/config/demo"):
                rep = projets.get_config("demo")
        finally:
            projets.DOSSIER_SCRIPT = ancien

        assert not isinstance(rep, tuple), f"erreur inattendue : {rep}"
        corps = rep.get_json()
        assert corps["modeles_valides"] == sorted(projets.MODELES_VALIDES)
        assert corps["modele_defaut_global"] == "claude-sonnet-5"
        assert corps["modele_ccl"] == "claude-opus-4-8"
    return {"modeles_valides": corps["modeles_valides"]}


def test_get_config_tolere_ancienne_valeur_modele_ccl_non_reconnue():
    """Un .conf dont le MODELE_CCL est une ancienne valeur (ex. un nom de
    modèle daté, faute de frappe historique) reste chargeable sans erreur —
    charger_config()/get_config() ne valident pas MODELE_CCL contre
    MODELES_VALIDES (seul le champ MODELE d'en-tête d'une issue l'est,
    app.issues.extraire_modele_entete)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        configs = tmp / "configs"
        rep_travail = tmp / "travail" / "demo"
        rep_travail.mkdir(parents=True)
        _ecrire_conf(configs, "demo", rep_travail, modele_ccl="claude-opus-4-5")

        ancien = projets.DOSSIER_SCRIPT
        projets.DOSSIER_SCRIPT = tmp
        try:
            with APP_FLASK.test_request_context("/config/demo"):
                rep = projets.get_config("demo")
        finally:
            projets.DOSSIER_SCRIPT = ancien

        assert not isinstance(rep, tuple), f"erreur inattendue : {rep}"
        corps = rep.get_json()
        assert corps["modele_ccl"] == "claude-opus-4-5"
        assert corps["modele_ccl"] not in corps["modeles_valides"]
    return {"modele_ccl": corps["modele_ccl"]}


def main() -> int:
    tests = [
        ("MODELES_VALIDES : même objet partagé (app.issues, watcher_issues_inbox, app.projets)",
         test_source_unique_meme_objet_partout),
        ("GET /config/<projet> : expose modeles_valides + modele_defaut_global",
         test_get_config_expose_modeles_valides_et_defaut_global),
        ("GET /config/<projet> : ancien MODELE_CCL non reconnu → chargé sans erreur",
         test_get_config_tolere_ancienne_valeur_modele_ccl_non_reconnue),
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
