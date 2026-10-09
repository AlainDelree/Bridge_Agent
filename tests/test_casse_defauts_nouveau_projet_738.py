#!/usr/bin/env python3
"""Test de non-régression — issue #738 : les valeurs proposées pour le dépôt
GitHub et le répertoire de travail ne respectaient pas la casse saisie dans le
nom du projet (AnnuaireToken → AlainDelree/Annuairetoken et
~/Annuairetoken), pour deux raisons cumulées :
1. `depot_defaut`/`rep_defaut` (nouveau_projet.py) capitalisaient tout le nom
   (première lettre en majuscule, reste forcé en minuscules) ;
2. la casse saisie était perdue avant même d'atteindre ces fonctions — mise en
   minuscules dans `creer_projet`, l'assistant CLI, et la route
   `verifier_nouveau_projet` (app/nouveau_projet.py), ainsi que côté
   JavaScript (`.toLowerCase()` avant l'appel réseau).

Couvre :
- `casse_proposee`/`depot_defaut`/`rep_defaut` : un nom saisi avec au moins
  une majuscule interne est repris tel quel (AnnuaireToken, ChessCoach) ; un
  nom tout en minuscules garde le comportement historique (rummikub →
  Rummikub, bloc_score → Bloc_score) ;
- `rep_casse_differente` : avertissement quand le répertoire proposé n'existe
  pas mais qu'un dossier homonyme à casse différente existe déjà dans le même
  dossier parent ; absent si le répertoire existe déjà, si aucun homonyme
  n'existe, ou si l'homonyme a la MÊME casse ;
- `creer_projet` : le NOM interne (clé, .conf) reste en minuscules même si le
  dépôt/répertoire par défaut respectent la casse saisie ;
- route `verifier_nouveau_projet` : renvoie des défauts calculés depuis le nom
  TEL QUE SAISI (pas depuis sa version mise en minuscules), plus
  `rep_casse_differente` quand pertinent.

Aucun appel réseau réel : `depot_existe`/`conf_existe`/`couleurs_disponibles`
sont monkeypatchés ou isolés via un dossier configs/ jetable.

Exécution :  python3 tests/test_casse_defauts_nouveau_projet_738.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import nouveau_projet as np  # noqa: E402
from app import nouveau_projet as route_np  # noqa: E402

APP_FLASK = flask.Flask(__name__)


# ─── casse_proposee / depot_defaut / rep_defaut ──────────────────────────────

def test_nom_avec_majuscule_interne_repris_tel_quel():
    assert np.casse_proposee("AnnuaireToken") == "AnnuaireToken"
    assert np.depot_defaut("AnnuaireToken") == "AlainDelree/AnnuaireToken"
    assert np.rep_defaut("AnnuaireToken") == str(Path.home() / "AnnuaireToken")
    assert np.casse_proposee("ChessCoach") == "ChessCoach"
    assert np.depot_defaut("ChessCoach") == "AlainDelree/ChessCoach"


def test_nom_tout_minuscule_garde_comportement_historique():
    assert np.casse_proposee("rummikub") == "Rummikub"
    assert np.depot_defaut("rummikub") == "AlainDelree/Rummikub"
    assert np.casse_proposee("bloc_score") == "Bloc_score"
    assert np.rep_defaut("bloc_score") == str(Path.home() / "Bloc_score")


def test_nom_saisi_avec_majuscule_initiale_seule():
    # Une seule majuscule (initiale) compte comme « au moins une majuscule » :
    # repris tel quel, pas de différence observable avec le comportement
    # historique dans ce cas précis, mais cohérent avec la règle énoncée.
    assert np.casse_proposee("Scrabble") == "Scrabble"


# ─── rep_casse_differente ────────────────────────────────────────────────────

def test_avertissement_homonyme_casse_differente():
    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp)
        (parent / "AnnuaireToken").mkdir()
        propose = parent / "Annuairetoken"
        assert np.rep_casse_differente(str(propose)) == str(parent / "AnnuaireToken")


def test_pas_avertissement_si_aucun_homonyme():
    with tempfile.TemporaryDirectory() as tmp:
        propose = Path(tmp) / "Rummikub"
        assert np.rep_casse_differente(str(propose)) is None


def test_pas_avertissement_si_repertoire_existe_deja():
    with tempfile.TemporaryDirectory() as tmp:
        propose = Path(tmp) / "AnnuaireToken"
        propose.mkdir()
        (Path(tmp) / "Annuairetoken").mkdir()
        # Le répertoire PROPOSÉ existe déjà → pas d'avertissement de doublon
        # (c'est le cas normal d'une installation sur un projet existant).
        assert np.rep_casse_differente(str(propose)) is None


def test_pas_avertissement_si_homonyme_meme_casse():
    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp)
        (parent / "Rummikub").mkdir()
        propose = parent / "Rummikub"
        assert np.rep_casse_differente(str(propose)) is None


# ─── creer_projet : NOM interne toujours en minuscules ───────────────────────

def test_creer_projet_nom_interne_minuscule_mais_depot_rep_respectent_la_casse():
    with tempfile.TemporaryDirectory() as tmp:
        configs = Path(tmp) / "configs"
        configs.mkdir()
        ancien_configs = np.DOSSIER_CONFIGS
        ancien_depot_existe = np.depot_existe
        ancien_creer_labels = np.creer_labels
        ancien_contexte = np.creer_fichiers_contexte
        ancien_init_git = np.initialiser_git
        ancien_maj_doc = np.mettre_a_jour_doc
        ancien_enregistrer = np.etat_configs_legitimes.enregistrer
        np.DOSSIER_CONFIGS = configs
        np.depot_existe = lambda depot: True  # installation, pas de création
        np.creer_labels = lambda depot: []
        np.creer_fichiers_contexte = lambda rep, avec_specs: {
            "crees": [], "existants": [], "rep_cree": False}
        np.initialiser_git = lambda rep, depot: {
            "ok": True, "deja_git": True, "push_ok": None,
            "contenu_preexistant": [], "detail": "déjà un dépôt git — inchangé.",
            "commande_manuelle": None}
        np.mettre_a_jour_doc = lambda: {"existe": False, "ok2": False,
                                         "ok7": False, "ok_date": False}
        np.etat_configs_legitimes.enregistrer = lambda nom_fichier: None
        try:
            res = np.creer_projet("AnnuaireToken")
        finally:
            np.DOSSIER_CONFIGS = ancien_configs
            np.depot_existe = ancien_depot_existe
            np.creer_labels = ancien_creer_labels
            np.creer_fichiers_contexte = ancien_contexte
            np.initialiser_git = ancien_init_git
            np.mettre_a_jour_doc = ancien_maj_doc
            np.etat_configs_legitimes.enregistrer = ancien_enregistrer

        assert res["succes"] is True, res
        assert res["nom"] == "annuairetoken", "la clé interne reste en minuscules"
        assert res["depot"] == "AlainDelree/AnnuaireToken"
        assert res["rep"] == str(Path.home() / "AnnuaireToken")
        assert (configs / "annuairetoken.conf").exists()
    return {"depot": res["depot"], "rep": res["rep"]}


# ─── Route Flask : verifier_nouveau_projet ───────────────────────────────────

def test_route_verifier_renvoie_defauts_depuis_le_nom_tel_que_saisi():
    ancien_conf_existe = route_np.np_cli.conf_existe
    ancien_depot_existe = route_np.np_cli.depot_existe
    ancien_couleurs = route_np.np_cli.couleurs_disponibles
    route_np.np_cli.conf_existe = lambda nom: False
    route_np.np_cli.depot_existe = lambda depot: False
    route_np.np_cli.couleurs_disponibles = lambda: []
    try:
        with APP_FLASK.test_request_context(
                "/nouveau-projet/verifier?nom=AnnuaireToken"):
            rep = route_np.verifier_nouveau_projet()
    finally:
        route_np.np_cli.conf_existe = ancien_conf_existe
        route_np.np_cli.depot_existe = ancien_depot_existe
        route_np.np_cli.couleurs_disponibles = ancien_couleurs

    corps = rep.get_json()
    assert corps["nom"] == "annuairetoken", "nom renvoyé = clé interne, minuscules"
    assert corps["nom_valide"] is True
    assert corps["depot_defaut"] == "AlainDelree/AnnuaireToken"
    assert corps["rep_defaut"] == str(Path.home() / "AnnuaireToken")
    return {"depot_defaut": corps["depot_defaut"], "rep_defaut": corps["rep_defaut"]}


def test_route_verifier_nom_tout_minuscule_garde_capitalisation():
    ancien_conf_existe = route_np.np_cli.conf_existe
    ancien_depot_existe = route_np.np_cli.depot_existe
    ancien_couleurs = route_np.np_cli.couleurs_disponibles
    route_np.np_cli.conf_existe = lambda nom: False
    route_np.np_cli.depot_existe = lambda depot: False
    route_np.np_cli.couleurs_disponibles = lambda: []
    try:
        with APP_FLASK.test_request_context(
                "/nouveau-projet/verifier?nom=rummikub"):
            rep = route_np.verifier_nouveau_projet()
    finally:
        route_np.np_cli.conf_existe = ancien_conf_existe
        route_np.np_cli.depot_existe = ancien_depot_existe
        route_np.np_cli.couleurs_disponibles = ancien_couleurs

    corps = rep.get_json()
    assert corps["depot_defaut"] == "AlainDelree/Rummikub"
    return {"depot_defaut": corps["depot_defaut"]}


def test_route_verifier_avertit_homonyme_casse_differente():
    with tempfile.TemporaryDirectory() as tmp:
        ancien_home = Path.home
        parent = Path(tmp)
        (parent / "AnnuaireToken").mkdir()
        Path.home = staticmethod(lambda: parent)

        ancien_conf_existe = route_np.np_cli.conf_existe
        ancien_depot_existe = route_np.np_cli.depot_existe
        ancien_couleurs = route_np.np_cli.couleurs_disponibles
        route_np.np_cli.conf_existe = lambda nom: False
        route_np.np_cli.depot_existe = lambda depot: False
        route_np.np_cli.couleurs_disponibles = lambda: []
        try:
            with APP_FLASK.test_request_context(
                    "/nouveau-projet/verifier?nom=annuairetoken"):
                rep = route_np.verifier_nouveau_projet()
        finally:
            Path.home = ancien_home
            route_np.np_cli.conf_existe = ancien_conf_existe
            route_np.np_cli.depot_existe = ancien_depot_existe
            route_np.np_cli.couleurs_disponibles = ancien_couleurs

        corps = rep.get_json()
        assert corps["rep_defaut"] == str(parent / "Annuairetoken")
        assert corps["rep_casse_differente"] == str(parent / "AnnuaireToken"), corps
    return {"rep_casse_differente": corps["rep_casse_differente"]}


def test_route_verifier_pas_avertissement_sans_homonyme():
    ancien_conf_existe = route_np.np_cli.conf_existe
    ancien_depot_existe = route_np.np_cli.depot_existe
    ancien_couleurs = route_np.np_cli.couleurs_disponibles
    route_np.np_cli.conf_existe = lambda nom: False
    route_np.np_cli.depot_existe = lambda depot: False
    route_np.np_cli.couleurs_disponibles = lambda: []
    try:
        with APP_FLASK.test_request_context(
                "/nouveau-projet/verifier?nom=rummikub"):
            rep = route_np.verifier_nouveau_projet()
    finally:
        route_np.np_cli.conf_existe = ancien_conf_existe
        route_np.np_cli.depot_existe = ancien_depot_existe
        route_np.np_cli.couleurs_disponibles = ancien_couleurs

    corps = rep.get_json()
    assert corps["rep_casse_differente"] == ""
    return {"rep_casse_differente": corps["rep_casse_differente"]}


def main() -> int:
    tests = [
        ("casse_proposee/depot_defaut/rep_defaut — majuscule interne reprise telle quelle",
         test_nom_avec_majuscule_interne_repris_tel_quel),
        ("casse_proposee/depot_defaut/rep_defaut — tout minuscule, comportement historique",
         test_nom_tout_minuscule_garde_comportement_historique),
        ("casse_proposee — majuscule initiale seule", test_nom_saisi_avec_majuscule_initiale_seule),
        ("rep_casse_differente — avertissement si homonyme à casse différente",
         test_avertissement_homonyme_casse_differente),
        ("rep_casse_differente — rien si aucun homonyme", test_pas_avertissement_si_aucun_homonyme),
        ("rep_casse_differente — rien si le répertoire proposé existe déjà",
         test_pas_avertissement_si_repertoire_existe_deja),
        ("rep_casse_differente — rien si l'homonyme a la même casse",
         test_pas_avertissement_si_homonyme_meme_casse),
        ("creer_projet — NOM interne minuscule, dépôt/rép respectent la casse",
         test_creer_projet_nom_interne_minuscule_mais_depot_rep_respectent_la_casse),
        ("route verifier — défauts depuis le nom tel que saisi",
         test_route_verifier_renvoie_defauts_depuis_le_nom_tel_que_saisi),
        ("route verifier — nom tout minuscule garde la capitalisation",
         test_route_verifier_nom_tout_minuscule_garde_capitalisation),
        ("route verifier — avertit d'un homonyme à casse différente",
         test_route_verifier_avertit_homonyme_casse_differente),
        ("route verifier — pas d'avertissement sans homonyme",
         test_route_verifier_pas_avertissement_sans_homonyme),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            rap = fn()
            print(f"  ✓ {nom}  ({rap})" if rap else f"  ✓ {nom}")
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
